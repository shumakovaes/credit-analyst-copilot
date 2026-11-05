CREATE SCHEMA copilot_data;
CREATE TABLE copilot_data.dataset (
    mode text NOT NULL, as_of date NOT NULL, description text NOT NULL
);
CREATE TABLE copilot_data.accounts (
    account_id integer PRIMARY KEY, client_id integer NOT NULL,
    district_id integer NOT NULL, opened_at date NOT NULL
);
CREATE TABLE copilot_data.loans (
    loan_id integer PRIMARY KEY, account_id integer UNIQUE REFERENCES copilot_data.accounts,
    client_id integer NOT NULL, district_id integer NOT NULL, issued_at date NOT NULL,
    original_amount numeric(14,2) NOT NULL CHECK(original_amount > 0),
    months integer NOT NULL, payment numeric(14,2) NOT NULL,
    status text NOT NULL CHECK (status IN ('A','B','C','D'))
);
CREATE TABLE copilot_data.applications (
    application_id text PRIMARY KEY, account_id integer REFERENCES copilot_data.accounts,
    as_of date NOT NULL, amount numeric(14,2) NOT NULL,
    decision text NOT NULL CHECK(decision IN ('checks_passed','manual_review','rule_violation')),
    payment_to_income double precision, model_score double precision, model_version text,
    created_at timestamp NOT NULL, data_mode text NOT NULL
);
CREATE TABLE copilot_data.rule_checks (
    application_id text REFERENCES copilot_data.applications,
    code text NOT NULL, status text NOT NULL CHECK(status IN ('passed','failed','unknown')),
    reason text NOT NULL, PRIMARY KEY(application_id, code)
);
