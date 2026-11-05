import os
from uuid import uuid4

import psycopg
import pytest

from credit_copilot.agent import AnalystAgent
from credit_copilot.db import Database
from credit_copilot.providers import plan
from credit_copilot.security import QueryError
from credit_copilot.settings import Settings
from test_agent import ScriptedProvider

pytestmark = pytest.mark.integration


def test_reader_cannot_write_even_if_readonly_setting_disabled(db):
    with db.connect() as conn:
        conn.execute("SET TRANSACTION READ WRITE")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("DELETE FROM copilot_data.loans")


def test_reader_has_default_readonly_transaction(db):
    with db.connect() as conn:
        assert conn.execute("SHOW transaction_read_only").fetchone()["transaction_read_only"] == "on"
        Database.assert_restricted_role(conn)


def test_admin_connection_is_rejected_by_executor():
    url = os.getenv("COPILOT_TEST_ADMIN_URL")
    if not url: pytest.skip("No integration database")
    with pytest.raises(QueryError, match="административных"):
        Database(Settings(_env_file=None, database_url=url)).execute("SELECT COUNT(*) FROM copilot_data.loans")


def test_row_limit_and_expensive_plan(pg_settings):
    limited = Database(pg_settings.model_copy(update={"max_rows": 5})).execute("SELECT loan_id FROM copilot_data.loans ORDER BY loan_id")
    assert len(limited["rows"]) == 5 and limited["truncated"] is True
    with pytest.raises(QueryError) as error:
        Database(pg_settings.model_copy(update={"max_plan_cost": .0001})).execute("SELECT COUNT(*) FROM copilot_data.loans")
    assert error.value.code == "expensive"


def test_server_statement_timeout(db):
    # This bypasses the application AST only to verify PostgreSQL cancellation itself.
    # pg_sleep is separately rejected by the application's policy tests.
    with db.connect() as conn:
        conn.execute("SET LOCAL statement_timeout = '50ms'")
        with pytest.raises(psycopg.errors.QueryCanceled):
            conn.execute("SELECT pg_sleep(.2)")


def test_nonfinite_results_do_not_escape_into_json(db):
    with pytest.raises(QueryError) as error:
        db.execute("SELECT CAST('NaN' AS DOUBLE PRECISION) AS value FROM copilot_data.dataset")
    assert error.value.code == "non_finite_result"


def test_repair_after_real_database_grouping_error(db, pg_settings):
    provider = ScriptedProvider([plan("SELECT status, COUNT(*) AS n FROM copilot_data.loans"),
                                 plan("SELECT status, COUNT(*) AS n FROM copilot_data.loans GROUP BY status ORDER BY status")])
    result = AnalystAgent(pg_settings, db, provider).run("Кредиты по статусам")
    assert result["status"] == "success" and result["repairs"] == 1
    assert len(result["result"]["rows"]) == 4
    assert provider.calls[1]["error"]["code"] == "execution"


def test_api_answer_history_export_and_conversation_isolation(client):
    assert client.get("/health").status_code == 200
    cid = str(uuid4())
    response = client.post("/ask", json={"conversation_id": cid, "question": "Сколько кредитов в портфеле и какова сумма при выдаче?"})
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["result"]["rows"] == [{"loan_count": 24, "original_amount_czk": 2376000.0}]
    assert result["provider_mode"] == "demo" and result["dataset"]["mode"] == "synthetic"
    assert client.get("/runs/"+result["run_id"]).json() == result
    csv = client.get("/runs/"+result["run_id"]+"/csv").text
    assert "synthetic,demo,24,2376000.0" in csv
    assert len(client.get("/conversations/"+cid).json()) == 1
    assert client.get("/conversations/"+str(uuid4())).json() == []
    assert client.post("/sql/check", json={"sql":"DROP TABLE copilot_data.loans"}).json()["allowed"] is False


def test_clarification_then_followup(client):
    cid = str(uuid4())
    result = client.post("/ask", json={"conversation_id":cid, "question":"Как изменился риск портфеля?"}).json()
    assert result["status"] == "clarify"
    followup = client.post("/ask", json={"conversation_id":cid, "question":"По месяцам"}).json()
    assert followup["status"] == "success" and len(followup["result"]["rows"]) == 6


def test_empty_and_invalid_input(client):
    assert client.post("/ask", json={"question":"   "}).status_code == 422
    assert client.post("/ask", json={"question":"x"*2001}).status_code == 422
    assert client.get("/runs/"+str(uuid4())).status_code == 404
    refused = client.post("/ask",json={"question":"Удали все кредиты"}).json()
    assert refused["status"] == "refused" and refused["result"] is None


def test_explicit_demo_repair_scenario(client):
    result = client.post("/ask",json={"question":"Покажи демонстрацию исправления SQL"}).json()
    assert result["status"] == "success" and result["repairs"] == 1
    assert result["result"]["rows"] == [{"loan_count":24}]


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_invalid_nonfinite_question_is_a_validation_error(client, value):
    response = client.post("/ask", content='{"question":' + value + '}',
                           headers={"Content-Type":"application/json"})
    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert error["loc"] == ["body", "question"] and "input" not in error


def test_export_escapes_formula_in_generated_column_name(client, monkeypatch):
    import csv
    import io
    from types import SimpleNamespace
    from credit_copilot import api
    from credit_copilot.providers import plan

    provider = SimpleNamespace(mode="demo", name="header-regression-fixture",
        generate=lambda *args: plan('SELECT COUNT(*) AS "=1+1" FROM copilot_data.loans'))
    monkeypatch.setattr(api, "make_provider", lambda settings: provider)
    run = client.post("/ask", json={"question":"Количество кредитов"}).json()
    assert run["status"] == "success" and run["result"]["rows"] == [{"=1+1":24}]
    exported = client.get('/runs/' + run['run_id'] + '/csv')
    rows = list(csv.reader(io.StringIO(exported.text.lstrip('\ufeff'))))
    assert rows[0] == ['__source_mode', '__provider_mode', "'=1+1"]
    assert rows[1] == ['synthetic', 'demo', '24']
