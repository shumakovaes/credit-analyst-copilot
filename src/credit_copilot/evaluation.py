import json
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .agent import AnalystAgent
from .db import Database
from .providers import make_provider
from .settings import Settings


def canonical(rows):
    """Multiset of rows; aliases and column order ignored, numeric values rounded."""
    def value(v):
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return "number:" + str(round(float(v), 6))
        return json.dumps(v, ensure_ascii=False, sort_keys=True)
    return Counter(tuple(sorted(value(v) for v in row.values())) for row in rows)


def evaluate(output, settings=None):
    settings = settings or Settings()
    db = Database(settings)
    agent = AnalystAgent(settings, db, make_provider(settings))
    cases = json.loads(Path("evals/cases.json").read_text(encoding="utf-8"))
    selected = [c for c in cases if settings.provider == "live" or c["demo"]]
    results = []
    for case in selected:
        run = agent.run(case["question"])
        passed = run["status"] == case["expected_status"]
        if passed and case.get("gold_sql"):
            gold = db.execute(case["gold_sql"])
            passed = not gold["truncated"] and not run["result"]["truncated"] and canonical(gold["rows"]) == canonical(run["result"]["rows"])
        results.append({"id":case["id"], "question":case["question"], "expected_status":case["expected_status"],
                        "status":run["status"], "passed":passed, "attempts":run["attempts"],
                        "repairs":run["repairs"], "elapsed_ms":run["elapsed_ms"], "sql":run["sql"]})
    passed_count = sum(r["passed"] for r in results)
    latencies = sorted(r["elapsed_ms"] for r in results)
    report = {"created_at":datetime.now(timezone.utc).isoformat(), "provider_mode":settings.provider,
              "model":agent.provider.name, "dataset":db.metadata(), "llm_quality_measured":settings.provider == "live",
              "cases_run":len(results), "cases_skipped":len(cases)-len(results), "checks_passed":passed_count,
              "live_case_pass_rate":passed_count/len(results) if settings.provider == "live" else None,
              "latency_median_ms":statistics.median(latencies), "latency_max_ms":max(latencies),
              "repair_count":sum(r["repairs"] for r in results), "cases":results,
              "limitations":["Demo validates fixed plans and plumbing; it does not measure LLM accuracy.",
                 "Live set is small and hand-authored; results are model/version/dataset-specific.",
                 "Answer comparison ignores aliases and column order, preserves row multiplicity, rounds numbers to 6 decimals.",
                 "Truncated results fail equivalence checks. Textual semantic correctness and chart quality are not automatically judged."]}
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"provider_mode":settings.provider, "llm_quality_measured":settings.provider == "live",
            "checks_passed":passed_count, "cases_run":len(results), "report":str(path)}
