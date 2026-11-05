import json
import sqlite3
from contextlib import closing
from pathlib import Path


class Audit:
    """Local service journal, separate from the read-only analytical connection."""
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=5)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
                created_at TEXT NOT NULL, payload TEXT NOT NULL)""")
            conn.execute("CREATE INDEX IF NOT EXISTS ix_conversation ON runs(conversation_id,created_at)")
            conn.commit()

    def save(self, result):
        with closing(sqlite3.connect(self.path, timeout=5)) as conn:
            conn.execute("INSERT INTO runs VALUES (?,?,?,?)", (result["run_id"], result["conversation_id"], result["created_at"], json.dumps(result, ensure_ascii=False)))
            conn.commit()

    def get(self, run_id):
        with closing(sqlite3.connect(self.path, timeout=5)) as conn:
            row = conn.execute("SELECT payload FROM runs WHERE run_id=?", (str(run_id),)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, conversation_id, limit=30):
        with closing(sqlite3.connect(self.path, timeout=5)) as conn:
            rows = conn.execute("SELECT payload FROM runs WHERE conversation_id=? ORDER BY created_at DESC LIMIT ?", (str(conversation_id), limit)).fetchall()
        return [json.loads(row[0]) for row in reversed(rows)]

    def context(self, conversation_id):
        # No query results, trace, SQL, or numerical answers are sent back to the LLM.
        return [{"question": r["question"], "status": r["status"],
                 "clarification": r["answer"] if r["status"] == "clarify" else None}
                for r in self.list(conversation_id, 6)]
