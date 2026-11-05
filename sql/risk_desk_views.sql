-- Additive adapter only: no change to clean/raw or to the first project's code.
CREATE SCHEMA copilot_data;
CREATE VIEW copilot_data.accounts AS
SELECT account_id, client_id, district_id, opened_at FROM clean.accounts;
CREATE VIEW copilot_data.loans AS
SELECT l.loan_id, l.account_id, a.client_id, a.district_id, l.issued_at,
       l.amount AS original_amount, l.months, l.payment, l.status::text
FROM clean.loans l JOIN clean.accounts a USING(account_id);
CREATE VIEW copilot_data.applications AS
SELECT application_id::text, account_id, (request->>'as_of')::date AS as_of,
       (request->>'amount')::numeric AS amount, result->>'status' AS decision,
       (result->'rules'->>'payment_to_income')::double precision AS payment_to_income,
       (result->'model'->>'score')::double precision AS model_score,
       result->'model'->>'model_version' AS model_version,
       created_at AT TIME ZONE 'UTC' AS created_at, dataset_mode AS data_mode
FROM clean.applications;
CREATE VIEW copilot_data.rule_checks AS
SELECT a.application_id::text, c->>'code' AS code, c->>'status' AS status, c->>'reason' AS reason
FROM clean.applications a CROSS JOIN LATERAL jsonb_array_elements(a.result->'rules'->'checks') c;
CREATE VIEW copilot_data.dataset AS
SELECT mode, reference_date AS as_of, 'Credit Risk Desk; read-only views; created_at in UTC'::text AS description
FROM raw.dataset;
