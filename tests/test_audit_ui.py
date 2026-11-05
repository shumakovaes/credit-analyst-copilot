from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from streamlit.testing.v1 import AppTest

from credit_copilot.audit import Audit
from credit_copilot.api import csv_cell


def test_context_excludes_query_results(tmp_path):
    audit = Audit(tmp_path / "audit.sqlite3")
    record = {"run_id":str(uuid4()), "conversation_id":"conversation", "created_at":"2025-01-01",
              "question":"Сколько?", "status":"success", "answer":"secret-result-value", "result":{"secret":123}}
    audit.save(record)
    assert "secret" not in str(audit.context("conversation"))


def test_csv_formula_escaping():
    assert csv_cell("=SUM(A1)") == "'=SUM(A1)"
    assert csv_cell(-123) == -123


@pytest.mark.integration
def test_ui_chat_history_policy(client, monkeypatch):
    def transport(method, url, **kwargs):
        kwargs.pop("timeout", None)
        return client.request(method, urlsplit(url).path, **kwargs)
    monkeypatch.setattr("httpx.request", transport)
    ui = AppTest.from_file(Path("streamlit_app.py").resolve(), default_timeout=30).run()
    assert not ui.exception
    # First main-page button is the example submit; sidebar button is selected by label.
    next(b for b in ui.button if b.label == "Задать вопрос").click().run()
    assert not ui.exception
    assert len(ui.session_state.messages) == 1
    assert ui.session_state.messages[0]["status"] == "success"
    ui.sidebar.radio[0].set_value("История запросов").run()
    assert not ui.exception
    ui.sidebar.radio[0].set_value("Данные и SQL-проверка").run()
    ui.text_area[0].set_value("DELETE FROM copilot_data.loans")
    next(b for b in ui.button if b.label == "Проверить SQL").click().run()
    assert not ui.exception and len(ui.error) == 1
