import json
import math
import time
from datetime import date, datetime
from decimal import Decimal

import psycopg
from psycopg.rows import dict_row

from .catalog import CATALOG
from .security import QueryError, check_sql


def plain(value):
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, float) and not math.isfinite(value):
        raise QueryError("non_finite_result", "Запрос вернул бесконечное или неопределённое число. Исправьте выражение.", True)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


class Database:
    def __init__(self, settings):
        self.settings = settings

    def connect(self):
        return psycopg.connect(self.settings.database_url.get_secret_value(), connect_timeout=3, row_factory=dict_row)

    def metadata(self):
        try:
            with self.connect() as conn:
                row = conn.execute("SELECT mode, as_of, description FROM copilot_data.dataset").fetchone()
                if not row:
                    raise QueryError("empty_dataset", "Набор данных не инициализирован.")
                return {k: plain(v) for k, v in row.items()}
        except psycopg.Error:
            raise QueryError("database_unavailable", "База недоступна или не инициализирована.") from None

    @staticmethod
    def assert_restricted_role(conn):
        role = conn.execute("""SELECT rolsuper, rolcreaterole, rolcreatedb, rolreplication, rolbypassrls
                              FROM pg_catalog.pg_roles WHERE rolname=current_user""").fetchone()
        if role is None or any(role.values()):
            raise QueryError("unsafe_role", "API требует отдельную роль без административных прав.")
        if conn.execute("SELECT has_schema_privilege(current_user, 'copilot_data', 'CREATE') AS allowed").fetchone()["allowed"]:
            raise QueryError("unsafe_role", "Роль API не должна создавать объекты в copilot_data.")
        for table in CATALOG:
            result = conn.execute("SELECT has_table_privilege(current_user, %s, 'INSERT, UPDATE, DELETE, TRUNCATE, TRIGGER') AS allowed",
                                  ("copilot_data." + table,)).fetchone()
            if result["allowed"]:
                raise QueryError("unsafe_role", "Роль API не должна иметь права изменения разрешённых таблиц.")

    def execute(self, candidate):
        approved = check_sql(candidate, self.settings.max_rows)
        start = time.perf_counter()
        try:
            with self.connect() as conn:
                conn.execute("SET TRANSACTION READ ONLY")
                self.assert_restricted_role(conn)
                conn.execute("SELECT set_config('statement_timeout', %s, true)", (str(self.settings.statement_timeout_ms),))
                conn.execute("SELECT set_config('lock_timeout', '500', true)")
                conn.execute("SELECT set_config('search_path', 'pg_catalog', true)")
                plan = conn.execute("EXPLAIN (FORMAT JSON) " + approved.sql).fetchone()["QUERY PLAN"][0]["Plan"]
                if plan["Total Cost"] > self.settings.max_plan_cost:
                    raise QueryError("expensive", "Запрос слишком дорогой. Сузьте период или упростите соединения.", True)
                cursor = conn.execute(approved.sql)
                names = [d.name for d in cursor.description]
                if len(names) != len(set(names)):
                    raise QueryError("duplicate_columns", "Задайте уникальные псевдонимы столбцов результата.", True)
                fetched = cursor.fetchmany(self.settings.max_rows + 1)
                truncated = len(fetched) > self.settings.max_rows
                rows = [{k: plain(v) for k, v in row.items()} for row in fetched[:self.settings.max_rows]]
                if len(json.dumps(rows, ensure_ascii=False).encode()) > self.settings.max_result_bytes:
                    raise QueryError("result_size", "Результат слишком большой. Выберите меньше столбцов или строк.", True)
                return {"sql": approved.sql, "tables": list(approved.tables), "columns": names,
                        "rows": rows, "truncated": truncated, "plan_cost": plan["Total Cost"],
                        "elapsed_ms": round((time.perf_counter() - start) * 1000, 2)}
        except psycopg.errors.QueryCanceled:
            raise QueryError("timeout", "Превышено ограничение времени SQL-запроса.", True) from None
        except (psycopg.errors.UndefinedColumn, psycopg.errors.AmbiguousColumn, psycopg.errors.GroupingError,
                psycopg.errors.DatatypeMismatch, psycopg.errors.DivisionByZero, psycopg.errors.SyntaxError):
            raise QueryError("execution", "PostgreSQL отклонил выражение: проверьте столбцы, группировку, типы и деление на ноль.", True) from None
        except psycopg.Error:
            raise QueryError("database_error", "Запрос не выполнен: проверьте подключение и права reader-роли.") from None
