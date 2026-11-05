"""Admin-only setup. Never imported by API startup; never receives natural-language SQL."""
from datetime import date, datetime
from pathlib import Path

import psycopg
from psycopg import sql
from .catalog import CATALOG

READER = "credit_copilot_reader"


def install_reader(conn, password):
    role = conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (READER,)).fetchone()
    if not role:
        conn.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS").format(sql.Identifier(READER), sql.Literal(password)))
    # Existing roles are NOT silently altered or given a new password.
    conn.execute(sql.SQL("GRANT USAGE ON SCHEMA copilot_data TO {}").format(sql.Identifier(READER)))
    objects = sql.SQL(", ").join(sql.Identifier("copilot_data", table) for table in CATALOG)
    conn.execute(sql.SQL("GRANT SELECT ON {} TO {}").format(objects, sql.Identifier(READER)))
    conn.execute(sql.SQL("ALTER ROLE {} SET default_transaction_read_only = on").format(sql.Identifier(READER)))
    db = conn.execute("SELECT current_database()").fetchone()[0]
    conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(db), sql.Identifier(READER)))


def initialize(admin_url, password, adapter=False):
    with psycopg.connect(admin_url, connect_timeout=5) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(849761)")
        exists = conn.execute("SELECT to_regclass('copilot_data.dataset')").fetchone()[0]
        if exists:
            description = conn.execute("SELECT description FROM copilot_data.dataset").fetchone()[0]
            if adapter != description.startswith("Credit Risk Desk"):
                raise ValueError("This database already holds a different data source. Use a separate database.")
            install_reader(conn, password)
            return {"status": "already_initialized"}
        script = "risk_desk_views.sql" if adapter else "demo_schema.sql"
        conn.execute((Path("sql") / script).read_text(encoding="utf-8"))
        if not adapter:
            conn.execute("INSERT INTO copilot_data.dataset VALUES ('synthetic', '2025-01-01', 'Independent synthetic fixtures v1; not model-quality evidence')")
            for i in range(1, 25):
                conn.execute("INSERT INTO copilot_data.accounts VALUES (%s,%s,%s,%s)", (i, 100+i, 1+i%4, date(2022, 1, 1)))
                conn.execute("INSERT INTO copilot_data.loans VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                             (1000+i, i, 100+i, 1+i%4, date(2024, 1+(i-1)%6, 10), 24000+i*6000, 24, (24000+i*6000)/24, "ABCD"[(i-1)%4]))
            for i in range(1, 33):
                burden = None if i % 8 == 0 else round(.15 + (i % 6)*.10, 2)
                decision = "manual_review" if burden is None else "rule_violation" if burden > .45 else "checks_passed"
                score = None if burden is None else round(.02 + (i%5)*.06, 2)
                conn.execute("INSERT INTO copilot_data.applications VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                             (f"DEMO-{i:03d}", 1+(i-1)%24, date(2025,1,1), 120000, decision, burden, score,
                              "synthetic-example-v1" if score is not None else None, datetime(2025,1,1+(i-1)%4,10,i), "synthetic"))
                status = "unknown" if burden is None else "failed" if burden > .45 else "passed"
                reason = "Нет заявленных дохода и платежей" if burden is None else f"Нагрузка {burden:.0%}; учебный предел 45%"
                conn.execute("INSERT INTO copilot_data.rule_checks VALUES (%s,'payment_to_income',%s,%s)", (f"DEMO-{i:03d}",status,reason))
                conn.execute("INSERT INTO copilot_data.rule_checks VALUES (%s,'available_limit','passed','Заявленный лимит 200000 CZK')", (f"DEMO-{i:03d}",))
        install_reader(conn, password)
    return {"status": "initialized", "source": "credit-risk-desk" if adapter else "synthetic"}
