import csv
import io
import threading
from datetime import datetime, timezone
from functools import lru_cache
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .agent import AnalystAgent
from .audit import Audit
from .catalog import CATALOG, EXAMPLES, GLOSSARY
from .db import Database
from .providers import ProviderError, make_provider, REPAIR_EXAMPLE
from .security import QueryError, check_sql
from .schemas import Ask
from .settings import Settings

app = FastAPI(title="Credit Analyst Copilot", version="0.1.0", description="Read-only SQL analyst; local single-user application.")
capacity = threading.BoundedSemaphore(2)


@lru_cache
def resources():
    settings = Settings()
    return settings, Database(settings), Audit(settings.audit_path)


@app.get("/health")
def health():
    settings, db, audit = resources()
    try:
        data = db.metadata()
        with db.connect() as conn:
            db.assert_restricted_role(conn)
    except QueryError as exc:
        raise HTTPException(503, exc.message) from None
    return {"status": "ok", "provider_mode": settings.provider, "data_mode": data["mode"]}


@app.get("/config")
def config():
    settings, db, audit = resources()
    try:
        metadata = db.metadata()
    except QueryError as exc:
        raise HTTPException(503, exc.message) from None
    return {"provider_mode": settings.provider, "model": settings.llm_model if settings.provider == "live" else "deterministic-demo-v1",
            "llm_configured": bool(settings.llm_model and settings.llm_api_key.get_secret_value()),
            "dataset": metadata, "max_rows": settings.max_rows, "max_attempts": settings.max_attempts,
            "statement_timeout_ms": settings.statement_timeout_ms,
            "examples": EXAMPLES + ([REPAIR_EXAMPLE] if settings.provider == "demo" else []),
            "catalog": CATALOG, "glossary": GLOSSARY}


@app.post("/ask", status_code=201)
def ask(request: Ask):
    if not request.question.strip():
        raise HTTPException(422, "Введите непустой вопрос.")
    if not capacity.acquire(blocking=False):
        raise HTTPException(429, "Два запроса уже выполняются. Повторите позже.")
    try:
        settings, db, audit = resources()
        conversation_id = str(request.conversation_id or uuid4())
        try:
            metadata = db.metadata()
            agent = AnalystAgent(settings, db, make_provider(settings))
        except (QueryError, ProviderError) as exc:
            raise HTTPException(503, str(exc)) from None
        result = agent.run(request.question.strip(), audit.context(conversation_id))
        result.update({"run_id": str(uuid4()), "conversation_id": conversation_id,
                       "created_at": datetime.now(timezone.utc).isoformat(), "question": request.question.strip(),
                       "dataset": metadata, "currency": "CZK"})
        audit.save(result)
        return result
    finally:
        capacity.release()


@app.get("/conversations/{conversation_id}")
def conversation(conversation_id: UUID):
    return resources()[2].list(conversation_id)


@app.get("/runs/{run_id}")
def get_run(run_id: UUID):
    result = resources()[2].get(run_id)
    if result is None:
        raise HTTPException(404, "Запуск не найден.")
    return result


def csv_cell(value):
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        return "'" + value
    return value


@app.get("/runs/{run_id}/csv")
def export(run_id: UUID):
    record = get_run(run_id)
    result = record.get("result")
    if result is None:
        raise HTTPException(409, "У этого запуска нет таблицы результата.")
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["__source_mode", "__provider_mode", *result["columns"]])
    for row in result["rows"]:
        writer.writerow([record["dataset"]["mode"], record["provider_mode"], *[csv_cell(row[k]) for k in result["columns"]]])
    return Response("\ufeff"+buffer.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="copilot-{run_id}.csv"'})


class SQLCheck(BaseModel):
    sql: str = Field(min_length=1, max_length=8000)


@app.post("/sql/check")
def sql_check(request: SQLCheck):
    try:
        approved = check_sql(request.sql, resources()[0].max_rows)
        return {"allowed": True, "sql": approved.sql, "tables": approved.tables, "executed": False}
    except QueryError as exc:
        return {"allowed": False, "code": exc.code, "reason": exc.message, "executed": False}
