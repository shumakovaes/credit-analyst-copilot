import json
import os
from uuid import uuid4

import httpx
import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
API = os.getenv("COPILOT_API_URL", "http://127.0.0.1:8001").rstrip("/")
STATUS = {"success": "Готово", "clarify": "Нужно уточнение", "refused": "Запрос отклонён",
          "blocked": "Остановлен проверкой", "failed": "Не удалось выполнить", "provider_error": "Ошибка подключения модели"}
NAMES = {"loan_count": "Кредитов", "original_amount_czk": "Сумма при выдаче, CZK", "status": "Статус",
         "application_id": "Заявка", "account_id": "Счёт", "payment_to_income": "Долговая нагрузка",
         "decision": "Результат проверки", "code": "Правило", "reason": "Причина", "month": "Месяц",
         "completed_count": "Завершённых кредитов", "bad_count": "Завершено с долгом", "bad_share": "Доля B среди A/B",
         "district_id": "Регион", "manual_review_count": "Заявок на ручной проверке"}


def call(method, path, raw=False, **kwargs):
    try:
        response = httpx.request(method, API+path, timeout=100, **kwargs)
        response.raise_for_status()
        return response.content if raw else response.json()
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("detail", "Ошибка API")
        except ValueError:
            detail = f"HTTP {exc.response.status_code}"
        st.error(str(detail))
    except httpx.RequestError:
        st.error("API недоступен. Запустите сервис и проверьте COPILOT_API_URL.")
    return None


def show_run(run, prefix):
    status = run["status"]
    if status == "success":
        st.caption(f"{STATUS[status]} · {run['elapsed_ms']/1000:.2f} с · исправлений: {run['repairs']} · источник: {run['dataset']['mode']}")
        st.write(run["answer"])
    elif status == "clarify":
        st.info(run["answer"])
    else:
        st.warning(f"{STATUS[status]}: {run['answer']}")
    result = run.get("result")
    if result:
        frame = pd.DataFrame(result["rows"], columns=result["columns"])
        if result["truncated"]:
            st.warning("Результат усечён. Уточните фильтры; график показывает только возвращённые строки.")
        st.dataframe(frame.rename(columns=NAMES), hide_index=True, width="stretch")
        chart = run["chart"]
        if chart["kind"] != "none" and not frame.empty:
            render = px.bar if chart["kind"] == "bar" else px.line
            fig = render(frame, x=chart["x"], y=chart["y"], labels=NAMES, color_discrete_sequence=["#2D6CBA"])
            fig.update_layout(height=300, margin={"t":20,"b":40})
            st.plotly_chart(fig, width="stretch", key=prefix+"chart")
    with st.expander("SQL и журнал шагов"):
        st.caption("Выполненный SQL" if result else "Последняя попытка SQL; выполнение не подтверждено")
        if run.get("sql"):
            st.code(run["sql"], language="sql")
        for i, event in enumerate(run["trace"], 1):
            st.markdown(f"**{i}. {event['step']} · {event['status']}**")
            st.text(event["detail"])
            if event.get("sql"):
                st.code(event["sql"], language="sql")
        st.caption("Это технический журнал действий, а не внутренние рассуждения модели.")
    left, right = st.columns(2)
    left.download_button("Отчёт JSON", json.dumps(run, ensure_ascii=False, indent=2),
                         file_name=f"copilot-{run['run_id']}.json", mime="application/json", key=prefix+"json")
    if result:
        csv = call("GET", f"/runs/{run['run_id']}/csv", raw=True)
        if csv is not None:
            right.download_button("Таблица CSV", csv, file_name=f"copilot-{run['run_id']}.csv", mime="text/csv", key=prefix+"csv")


st.set_page_config(page_title="Credit Analyst Copilot", page_icon="◈", layout="wide")
st.sidebar.title("◈ Analyst Copilot")
st.sidebar.caption("Вопрос → SQL → проверяемый ответ")
page = st.sidebar.radio("Раздел", ["Помощник", "История запросов", "Данные и SQL-проверка"], label_visibility="collapsed")
config = call("GET", "/config")
if config is None:
    st.title("Credit Analyst Copilot")
    st.stop()
if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = str(uuid4())
    st.session_state.messages = []
if st.sidebar.button("Новый диалог"):
    st.session_state.conversation_id = str(uuid4())
    st.session_state.messages = []
st.sidebar.divider()
st.sidebar.markdown("**Только чтение**")
st.sidebar.caption(f"Источник: {config['dataset']['mode']}\n\nСрез: {config['dataset']['as_of']}\n\nВалюта: CZK")
st.sidebar.caption("Учебная аналитика розничных кредитов")
if config["provider_mode"] == "demo":
    st.info("ДЕМО БЕЗ LLM · Вопросы из примеров обрабатываются заранее заданными SQL-планами. Проверки и выполнение в PostgreSQL настоящие.")
else:
    st.info(f"LLM · {config['model']} · Модели передаются вопрос, описание схемы и ошибки; строки результата остаются локально.")
    if not config["llm_configured"]:
        st.warning("Заполните COPILOT_LLM_MODEL и COPILOT_LLM_API_KEY в локальном .env и перезапустите API.")
if config["dataset"]["mode"] == "synthetic":
    st.caption("Все записи и оценки риска в этой базе синтетические. Они проверяют работу приложения, а не качество модели.")

if page == "Помощник":
    st.title("Спросите о кредитном портфеле")
    st.caption("Проверьте выдачи, долговую нагрузку и причины нарушений. В каждом ответе доступны SQL и источник цифр.")
    with st.form("example_form"):
        example = st.selectbox("Готовый вопрос", config["examples"])
        example_submit = st.form_submit_button("Задать вопрос", type="primary")
    typed = st.chat_input("Напишите вопрос или ответьте на уточнение")
    question = example if example_submit else typed
    if question:
        with st.spinner("Формирую и проверяю запрос…"):
            run = call("POST", "/ask", json={"question": question, "conversation_id": st.session_state.conversation_id})
        if run:
            st.session_state.messages.append(run)
    for run in st.session_state.messages:
        with st.chat_message("user"):
            st.write(run["question"])
        with st.chat_message("assistant"):
            show_run(run, "chat-"+run["run_id"])
    if not st.session_state.messages:
        st.markdown("**Например:** какие заявки нарушили правила и что нужно проверить аналитику?")
        st.caption("Если вопрос неоднозначен, помощник попросит уточнение. Учебные проверки не являются решением о выдаче кредита.")

elif page == "История запросов":
    st.title("История текущего диалога")
    runs = call("GET", "/conversations/"+st.session_state.conversation_id)
    if runs:
        selected = st.selectbox("Запрос", list(reversed(runs)), format_func=lambda r: f"{r['created_at'][:19]} · {r['question']}")
        show_run(selected, "history-"+selected["run_id"])
    else:
        st.info("В этом диалоге пока нет запросов.")
    st.caption("История сохраняется локально. Новый диалог не использует контекст предыдущего.")

else:
    st.title("Данные и границы доступа")
    st.write(config["dataset"]["description"])
    with st.expander("Бизнес-словарь", expanded=True):
        st.text(config["glossary"])
    with st.expander("Разрешённые таблицы и столбцы"):
        st.json({"copilot_data": config["catalog"]})
    st.subheader("Проверка SQL без выполнения")
    sql = st.text_area("SQL", "SELECT status, COUNT(*) AS loan_count FROM copilot_data.loans GROUP BY status", height=120)
    if st.button("Проверить SQL"):
        result = call("POST", "/sql/check", json={"sql": sql})
        if result:
            if result["allowed"]:
                st.success("Запрос прошёл статическую проверку. Выполнение не запускалось.")
                st.code(result["sql"], language="sql")
            else:
                st.error(result["reason"])
    st.caption(f"До {config['max_rows']} строк, SQL timeout {config['statement_timeout_ms']} мс, до {config['max_attempts']} попыток. Роль PostgreSQL не имеет прав записи в аналитические таблицы.")
