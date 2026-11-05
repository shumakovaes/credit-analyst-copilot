import pytest
from credit_copilot.providers import DEMO_PLANS
from credit_copilot.security import check_sql, QueryError


@pytest.mark.parametrize("candidate", [
    "DROP TABLE copilot_data.loans",
    "SELECT loan_id FROM copilot_data.loans; DELETE FROM copilot_data.loans",
    "WITH removed AS (DELETE FROM copilot_data.loans RETURNING loan_id) SELECT loan_id FROM removed",
    "SELECT loan_id INTO TEMP stolen FROM copilot_data.loans",
    "SELECT loan_id FROM copilot_data.loans FOR UPDATE",
    "SELECT rolpassword FROM pg_catalog.pg_authid",
    "SELECT loan_id FROM clean.loans",
    "SELECT loan_id FROM loans",
    "SELECT pg_read_file('/etc/passwd') FROM copilot_data.dataset",
    "SELECT pg_sleep(100) FROM copilot_data.dataset",
    "SELECT set_config('transaction_read_only','off',false) FROM copilot_data.dataset",
    "SELECT nextval('some_sequence') FROM copilot_data.dataset",
    "SELECT pg_advisory_lock(1) FROM copilot_data.dataset",
    "SELECT dblink('secret','select 1') FROM copilot_data.dataset",
    "SELECT COUNT(*) FROM copilot_data.loans l CROSS JOIN copilot_data.loans x",
    "SELECT COUNT(*) FROM copilot_data.loans l, copilot_data.loans x",
    "SET ROLE postgres",
    "COPY copilot_data.loans TO PROGRAM 'bad-command'",
    "WITH RECURSIVE x AS (SELECT loan_id FROM copilot_data.loans) SELECT loan_id FROM x",
    "SELECT CAST('pg_authid' AS regclass) FROM copilot_data.dataset",
    "SELECT CAST(description AS XML) FROM copilot_data.dataset",
    "WITH loans AS (SELECT rolpassword FROM pg_catalog.pg_authid) SELECT rolpassword FROM loans",
    "SELECT loan_id FROM copilot_data.loans UNION SELECT oid FROM pg_catalog.pg_authid",
    "SELECT loan_id FROM copilot_data.loans LIMIT ALL",
    "SELECT loan_id FROM copilot_data.loans LIMIT (SELECT 10)",
    "SELECT pg_catalog.sum(original_amount) FROM copilot_data.loans",
    "SELECT description FROM copilot_data.dataset WHERE description ~ '(a+)+$'",
    "SELECT * FROM copilot_data.loans",
])
def test_rejects_unsafe_or_unsupported_sql(candidate):
    with pytest.raises(QueryError):
        check_sql(candidate)


def test_example_queries_pass_and_regenerate():
    for p in DEMO_PLANS:
        if p.sql:
            checked = check_sql(p.sql)
            assert 'LIMIT 201' in checked.sql
            assert checked.tables
            assert check_sql(checked.sql).sql == checked.sql


def test_cte_and_comments_are_handled_by_parser():
    result = check_sql("WITH summary AS (SELECT status, COUNT(*) AS n FROM copilot_data.loans GROUP BY status) SELECT status,n FROM summary ORDER BY n DESC -- DROP TABLE is only a comment")
    assert result.tables == ("loans",)


def test_unknown_column_repairable():
    with pytest.raises(QueryError) as caught:
        check_sql("SELECT invented_balance FROM copilot_data.loans")
    assert caught.value.code == "column" and caught.value.repairable


def test_limit_preserves_small_user_limit():
    assert "LIMIT 3" in check_sql("SELECT loan_id FROM copilot_data.loans LIMIT 3").sql
    assert "LIMIT 201" in check_sql("SELECT loan_id FROM copilot_data.loans LIMIT 9000").sql
