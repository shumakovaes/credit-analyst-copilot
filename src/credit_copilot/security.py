"""Conservative PostgreSQL subset. Execute regenerated AST, never raw model SQL."""
from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, OptimizeError
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import traverse_scope

from .catalog import CATALOG


class QueryError(Exception):
    def __init__(self, code, message, repairable=False):
        super().__init__(message)
        self.code, self.message, self.repairable = code, message, repairable


@dataclass(frozen=True)
class ApprovedQuery:
    sql: str
    tables: tuple[str, ...]


ALLOWED_FUNCTIONS = {"COUNT", "SUM", "AVG", "MIN", "MAX", "ROUND", "ABS", "COALESCE", "NULLIF",
                     "CAST", "EXTRACT", "TIMESTAMP_TRUNC", "DATE_TRUNC", "LOWER", "UPPER", "IF", "CASE", "AND", "OR"}
ALLOWED_NODES = set("""Select Union With CTE Subquery Table TableAlias Identifier Column Alias From Join
Where Group Having Order Ordered Limit Offset Distinct Star Literal Null Boolean Paren Tuple
EQ NEQ GT GTE LT LTE And Or Not Is In Between Like ILike Add Sub Mul Div Mod Neg
Count Sum Avg Min Max Round Abs Coalesce Nullif Cast DataType DataTypeParam Extract
TimestampTrunc DateTrunc Lower Upper Case If Var""".split())
SAFE_TYPES = {"INT", "BIGINT", "SMALLINT", "FLOAT", "DOUBLE", "DECIMAL", "DATE", "TIMESTAMP",
              "TIMESTAMPTZ", "TEXT", "VARCHAR", "BOOLEAN"}


def check_sql(sql: str, max_rows=200) -> ApprovedQuery:
    if not isinstance(sql, str) or not sql.strip() or len(sql) > 8000:
        raise QueryError("invalid_sql", "Нужен SQL длиной от 1 до 8000 символов.", True)
    try:
        statements = sqlglot.parse(sql, read="postgres")
    except (ParseError, RecursionError):
        raise QueryError("syntax", "Не удалось разобрать PostgreSQL SELECT. Исправьте синтаксис.", True) from None
    if len(statements) != 1 or not isinstance(statements[0], (exp.Select, exp.Union)):
        raise QueryError("not_select", "Разрешён ровно один SELECT, включая нерекурсивный WITH.")
    tree = statements[0]
    if any(w.args.get("recursive") for w in tree.find_all(exp.With)):
        raise QueryError("recursive", "Рекурсивные запросы запрещены.")
    for node in tree.walk():
        if type(node).__name__ not in ALLOWED_NODES:
            raise QueryError("unsupported_operation", f"Конструкция {type(node).__name__} не разрешена политикой SQL.")
        if isinstance(node, exp.Func) and node.sql_name() not in ALLOWED_FUNCTIONS:
            raise QueryError("function", "Функция не входит в разрешённый аналитический набор.")
        if isinstance(node, exp.DataType) and node.this.name not in SAFE_TYPES:
            raise QueryError("cast", "Преобразование в этот тип запрещено.")
        if isinstance(node, exp.Literal) and len(node.this) > 500:
            raise QueryError("literal_size", "Слишком длинная константа.")
        if isinstance(node, exp.Star) and not isinstance(node.parent, exp.Count):
            raise QueryError("star", "Укажите нужные столбцы явно; звёздочка допустима только в COUNT(*).", True)
    joins = list(tree.find_all(exp.Join))
    if len(joins) > 3 or any(j.args.get("kind") == "CROSS" or not (j.args.get("on") or j.args.get("using")) for j in joins):
        raise QueryError("join", "Допустимо до трёх JOIN с явным ON или USING; CROSS JOIN запрещён.")
    tables = set()
    for scope in traverse_scope(tree):
        for source in scope.sources.values():
            if isinstance(source, exp.Table):
                if source.catalog or source.db != "copilot_data" or source.name not in CATALOG or not isinstance(source.this, exp.Identifier):
                    raise QueryError("table", "Таблица вне разрешённой схемы copilot_data.")
                tables.add(source.name)
    if not tables:
        raise QueryError("no_source", "Ответ должен опираться на таблицы кредитных данных.", True)
    # Resolve aliases, CTE scopes and ambiguous/nonexistent columns against the contract.
    try:
        tree = qualify(tree, dialect="postgres", schema={"copilot_data": CATALOG},
                       expand_stars=False, validate_qualify_columns=True, identify=True)
    except (OptimizeError, ValueError):
        raise QueryError("column", "Неизвестный или неоднозначный столбец. Сверьте имена и псевдонимы с каталогом.", True) from None
    for node in list(tree.find_all(exp.Limit)) + list(tree.find_all(exp.Offset)):
        value = node.expression
        if not isinstance(value, exp.Literal) or not value.is_int or not 0 <= int(value.this) <= 10000:
            raise QueryError("pagination", "LIMIT/OFFSET должны быть целыми числами от 0 до 10000.")
    requested = tree.args.get("limit")
    effective = min(int(requested.expression.this), max_rows + 1) if requested else max_rows + 1
    tree = tree.limit(effective, copy=False)
    return ApprovedQuery(tree.sql(dialect="postgres"), tuple(sorted(tables)))
