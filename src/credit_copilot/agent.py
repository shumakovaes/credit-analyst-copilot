import time
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from .providers import ProviderError
from .security import QueryError, check_sql


class State(TypedDict, total=False):
    question: str
    history: list
    plan: dict
    sql: str | None
    error: dict | None
    attempts: int
    status: str
    trace: list
    result: dict
    answer: str
    chart: dict


def event(state, step, status, detail, **extra):
    # This is an operational trace, not model chain-of-thought.
    return [*state.get("trace", []), {"step": step, "status": status, "detail": detail, **extra}]


class AnalystAgent:
    def __init__(self, settings, database, provider):
        self.settings, self.database, self.provider = settings, database, provider
        graph = StateGraph(State)
        graph.add_node("generate", self.generate)
        graph.add_node("validate", self.validate)
        graph.add_node("execute", self.execute)
        graph.add_node("answer", self.answer)
        graph.add_edge(START, "generate")
        graph.add_conditional_edges("generate", lambda s: "validate" if s["status"] == "generated" else "answer")
        graph.add_conditional_edges("validate", self.after_validation)
        graph.add_conditional_edges("execute", self.after_execution)
        graph.add_edge("answer", END)
        self.graph = graph.compile()

    def generate(self, state):
        attempt = state.get("attempts", 0) + 1
        start = time.perf_counter()
        try:
            p = self.provider.generate(state["question"], state["history"], state.get("error"), state.get("sql"))
            if len(p.message) > 600 or (p.action == "query" and not p.sql) or (p.action != "query" and not p.message.strip()):
                raise ProviderError("План модели не соответствует контракту; запрос не выполнен.")
            status = "generated" if p.action == "query" else "clarify" if p.action == "clarify" else "refused"
            return {"attempts": attempt, "plan": p.model_dump(), "sql": p.sql, "status": status, "error": None,
                    "trace": event(state, "generate" if attempt == 1 else "repair", status,
                                   "Получен план запроса" if status == "generated" else p.message,
                                   attempt=attempt, sql=p.sql, elapsed_ms=round((time.perf_counter()-start)*1000, 2))}
        except ProviderError as exc:
            return {"attempts": attempt, "status": "provider_error", "answer": str(exc),
                    "trace": event(state, "generate", "error", str(exc), attempt=attempt)}

    def validate(self, state):
        try:
            approved = check_sql(state["sql"], self.settings.max_rows)
            return {"sql": approved.sql, "status": "validated",
                    "trace": event(state, "validate", "passed", "AST, таблицы, столбцы, функции и лимит проверены.", sql=approved.sql)}
        except QueryError as exc:
            return self.failure(state, "validate", exc)

    def execute(self, state):
        try:
            result = self.database.execute(state["sql"])
            return {"result": result, "sql": result["sql"], "status": "success",
                    "trace": event(state, "execute", "success", f"Получено строк: {len(result['rows'])}.",
                                   elapsed_ms=result["elapsed_ms"], plan_cost=result["plan_cost"], truncated=result["truncated"])}
        except QueryError as exc:
            return self.failure(state, "execute", exc)

    def failure(self, state, step, exc):
        retry = exc.repairable and state["attempts"] < self.settings.max_attempts
        status = "retry" if retry else "blocked" if not exc.repairable else "failed"
        return {"status": status, "error": {"code": exc.code, "message": exc.message}, "answer": exc.message,
                "trace": event(state, step, status, exc.message, code=exc.code)}

    @staticmethod
    def after_validation(state):
        return "execute" if state["status"] == "validated" else "generate" if state["status"] == "retry" else "answer"

    @staticmethod
    def after_execution(state):
        return "generate" if state["status"] == "retry" else "answer"

    def answer(self, state):
        chart = {"kind": "none", "x": None, "y": None}
        status = state["status"]
        if status == "success":
            result = state["result"]
            rows = result["rows"]
            if not rows:
                answer = "По условиям запроса записей не найдено. Пустой результат не означает отсутствие риска."
            elif len(rows) == 1:
                answer = "Результат запроса: " + "; ".join(f"{k} = {'нет данных' if v is None else v}" for k, v in rows[0].items()) + "."
            else:
                answer = f"Получено строк: {len(rows)}. Значения приведены в таблице и рассчитаны показанным SQL."
            if result["truncated"]:
                answer += f" Показаны первые {self.settings.max_rows} строк; результат усечён, это не полный итог."
            requested = state["plan"]["chart"]
            if requested["kind"] != "none" and rows and requested["x"] in result["columns"] and requested["y"] in result["columns"]:
                if all(isinstance(row[requested["y"]], (int,float)) and not isinstance(row[requested["y"]],bool) for row in rows):
                    chart = requested
        elif status in ("clarify", "refused"):
            answer = state["plan"]["message"]
        else:
            answer = state.get("answer", "Запрос не выполнен.")
        return {"answer": answer, "chart": chart,
                "trace": event(state, "answer", status, "Ответ сформирован из результата запроса; строки БД не отправлялись в LLM.")}

    def run(self, question, history=None):
        start = time.perf_counter()
        state = self.graph.invoke({"question": question, "history": history or [], "attempts": 0, "trace": []},
                                  config={"recursion_limit": 20})
        return {"status": state["status"], "answer": state["answer"], "sql": state.get("sql"),
                "result": state.get("result"), "chart": state["chart"], "trace": state["trace"],
                "attempts": state["attempts"], "repairs": max(0, state["attempts"] - 1),
                "elapsed_ms": round((time.perf_counter()-start)*1000, 2),
                "provider_mode": self.provider.mode, "model": self.provider.name}
