"""Memory that survives between runs (SQLite). It learns from the logs in a simple, checkable way.

- Every run stores which checks failed on each attempt.
- Before a new run, the top failing checks of the LAST `window` runs become rules in the writer prompt.
  (A window means old, fixed problems stop being injected. Prompt stays short: top 3 only.)
- `health()` flags checks that ALWAYS fail or NEVER fail. These may be bad checks: sharpen the rubric.
- `first_attempt_stats()` lets you measure if memory really helps (see scripts/memory_experiment.py).
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs(
  run_id TEXT PRIMARY KEY, ts REAL, topic TEXT, memory_on INTEGER,
  attempts INTEGER, first_attempt_passed INTEGER, final_status TEXT);
CREATE TABLE IF NOT EXISTS check_events(
  run_id TEXT, attempt INTEGER, check_id TEXT, passed INTEGER);
"""


class Memory:
    def __init__(self, db_path: Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.executescript(SCHEMA)

    def close(self):
        self.db.close()

    # ------------------------------------------------------------ write
    def record_run(self, run_id: str, topic: str, memory_on: bool, attempts: list[dict], status: str) -> None:
        first = attempts[0]["results"] if attempts else []
        first_ok = int(bool(first) and all(r["passed"] for r in first))
        self.db.execute(
            "INSERT OR REPLACE INTO runs VALUES(?,?,?,?,?,?,?)",
            (run_id, time.time(), topic, int(memory_on), len(attempts), first_ok, status),
        )
        for i, a in enumerate(attempts):
            for r in a.get("results", []):
                self.db.execute("INSERT INTO check_events VALUES(?,?,?,?)", (run_id, i, r["id"], int(r["passed"])))
        self.db.commit()

    # ------------------------------------------------------------ read
    def top_failures(self, n: int = 3, window: int = 10) -> list[tuple[str, int]]:
        """Checks that failed most on the FIRST attempt in the last `window` runs."""
        rows = self.db.execute(
            """SELECT check_id, COUNT(*) c FROM check_events
               WHERE attempt=0 AND passed=0
                 AND run_id IN (SELECT run_id FROM runs ORDER BY ts DESC LIMIT ?)
               GROUP BY check_id ORDER BY c DESC, check_id LIMIT ?""",
            (window, n),
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    def rules(self, rubric: dict, n: int = 3, window: int = 10) -> list[str]:
        by_id = {c["id"]: c for c in rubric["checks"]}
        return [by_id[cid]["writer_rule"] for cid, _ in self.top_failures(n, window) if cid in by_id]

    def health(self, min_runs: int = 5) -> list[dict]:
        """Flag checks that always fail or never fail (over all attempts). Needs enough runs."""
        n_runs = self.db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        out = []
        if n_runs < min_runs:
            return out
        for cid, total, fails in self.db.execute(
            "SELECT check_id, COUNT(*), SUM(1-passed) FROM check_events GROUP BY check_id"
        ):
            rate = fails / total
            if rate == 1.0:
                out.append({"check": cid, "flag": "ALWAYS FAILS", "advice": "Check may be impossible or too strict. Review it."})
            elif rate == 0.0:
                out.append({"check": cid, "flag": "NEVER FAILS", "advice": "Check may be too easy or broken. Test it on a bad lesson."})
        return out

    def first_attempt_stats(self, memory_on: bool | None = None) -> dict:
        q = "SELECT COUNT(*), COALESCE(SUM(first_attempt_passed),0) FROM runs"
        args: tuple = ()
        if memory_on is not None:
            q += " WHERE memory_on=?"
            args = (int(memory_on),)
        n, ok = self.db.execute(q, args).fetchone()
        fails = 0.0
        if n:
            ids = "SELECT run_id FROM runs" + (" WHERE memory_on=?" if memory_on is not None else "")
            total_fails = self.db.execute(
                f"SELECT COUNT(*) FROM check_events WHERE attempt=0 AND passed=0 AND run_id IN ({ids})", args
            ).fetchone()[0]
            fails = total_fails / n
        return {"runs": n, "first_attempt_pass_rate": (ok / n) if n else None, "avg_failed_checks_first_attempt": fails}
