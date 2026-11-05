import os

import pytest
from fastapi.testclient import TestClient
from psycopg.conninfo import conninfo_to_dict

from credit_copilot.bootstrap import initialize
from credit_copilot.db import Database
from credit_copilot.settings import Settings
from credit_copilot.audit import Audit


@pytest.fixture(scope="session")
def pg_settings():
    admin = os.getenv("COPILOT_TEST_ADMIN_URL")
    reader = os.getenv("COPILOT_TEST_DATABASE_URL")
    if not admin or not reader:
        pytest.skip("Set COPILOT_TEST_ADMIN_URL and COPILOT_TEST_DATABASE_URL for PostgreSQL integration tests")
    a, r = conninfo_to_dict(admin), conninfo_to_dict(reader)
    if not a["dbname"].endswith("_test") or a["dbname"] != r["dbname"]:
        pytest.fail("Use the same dedicated _test database for both connections")
    initialize(admin, r.get("password", "reader_local"))
    return Settings(_env_file=None, database_url=reader, provider="demo")


@pytest.fixture
def db(pg_settings):
    return Database(pg_settings)


@pytest.fixture
def client(pg_settings, tmp_path, monkeypatch):
    from credit_copilot import api
    audit = Audit(tmp_path / "audit.sqlite3")
    monkeypatch.setattr(api, "resources", lambda: (pg_settings, Database(pg_settings), audit))
    with TestClient(api.app) as client:
        yield client
