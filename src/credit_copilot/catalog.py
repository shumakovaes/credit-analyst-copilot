"""A narrow public data contract shared by demo and Risk Desk views."""
CATALOG = {
    "accounts": {"account_id": "INT", "client_id": "INT", "district_id": "INT", "opened_at": "DATE"},
    "loans": {"loan_id": "INT", "account_id": "INT", "client_id": "INT", "district_id": "INT",
              "issued_at": "DATE", "original_amount": "DECIMAL", "months": "INT", "payment": "DECIMAL", "status": "TEXT"},
    "applications": {"application_id": "TEXT", "account_id": "INT", "as_of": "DATE", "amount": "DECIMAL",
                     "decision": "TEXT", "payment_to_income": "DOUBLE", "model_score": "DOUBLE",
                     "model_version": "TEXT", "created_at": "TIMESTAMP", "data_mode": "TEXT"},
    "rule_checks": {"application_id": "TEXT", "code": "TEXT", "status": "TEXT", "reason": "TEXT"},
    "dataset": {"mode": "TEXT", "as_of": "DATE", "description": "TEXT"},
}

GLOSSARY = """
Все суммы в CZK. Розничные учебные данные, не корпоративные кредиты.
loans.original_amount — сумма при выдаче, НЕ текущая задолженность.
Статусы: A завершён без проблем; B завершён с невыплаченным долгом;
C действует без проблем на момент наблюдения; D действует, клиент имеет задолженность.
Завершённые кредиты — только A/B. Доля B среди A/B — историческая доля, не годовая PD.
applications.decision: checks_passed / manual_review / rule_violation. Это результат учебных проверок, не решение о выдаче.
payment_to_income — (новый платёж + действующие платежи) / заявленный доход; 0.45 означает 45%.
NULL — неизвестно; не заменяй неизвестную нагрузку или оценку нулём.
applications.model_score — выход исторической модели или синтетический fixture; не годовая PD.
Не сравнивай оценки разных model_version как сопоставимые без явного уточнения.
rule_checks.status: passed / failed / unknown. Заявка может иметь несколько нарушенных правил.
created_at — время проверки, as_of — дата данных для заявки; это разные временные оси.
Исторических снимков портфеля и остатков задолженности в контракте нет.
На вопрос об изменении риска портфеля во времени уточни, интересуют ли пользователя
выдачи по месяцам или журнал заявок; не выдумывай динамику исходных статусов.
В таблицах нет ФИО, паспортов, телефонов, паролей или номеров карт.
""".strip()

EXAMPLES = [
    "Сколько кредитов в портфеле и какова сумма при выдаче?",
    "Покажи распределение кредитов по статусам",
    "Покажи заявки с долговой нагрузкой выше 45%",
    "Какие заявки не прошли проверку и по каким причинам?",
    "Покажи выдачи по месяцам",
    "Какова доля проблемных среди завершённых кредитов?",
    "Какие регионы имеют наибольшую сумму выдач?",
    "Сколько заявок требует ручной проверки?",
    "Покажи заявки без данных о долговой нагрузке",
    "Как изменился риск портфеля?",
]
