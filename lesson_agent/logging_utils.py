"""Write the run outputs: final lesson + rejection log (JSONL for machines, Markdown for humans)."""
from __future__ import annotations

import difflib
import json
from pathlib import Path

from . import text_utils as T


def _cell(text: str, limit: int = 300) -> str:
    """Keep arbitrary model/API text on one safe Markdown table row."""
    return T.shorten(" ".join((text or "").split()), limit).replace("|", "/")


def make_diff(prev: str, new: str, max_lines: int = 60) -> tuple[str, dict]:
    diff = list(difflib.unified_diff(prev.splitlines(), new.splitlines(), "previous", "new", n=0, lineterm=""))
    added = sum(1 for d in diff if d.startswith("+") and not d.startswith("+++"))
    removed = sum(1 for d in diff if d.startswith("-") and not d.startswith("---"))
    text = "\n".join(diff[:max_lines]) + ("\n... (diff cut)" if len(diff) > max_lines else "")
    return text, {"lines_added": added, "lines_removed": removed}


def attempt_record(run_id: str, topic: str, i: int, a: dict) -> dict:
    results = a.get("results", [])
    bad = [r for r in results if not r["passed"]]
    return {
        "run_id": run_id,
        "topic": topic,
        "attempt": i,
        "passed": not bad,
        "n_failed": len(bad),
        "failed_checks": [
            {"id": r["id"], "dimension": r["dimension"], "reason": r["reason"],
             "evidence": r.get("evidence", ""), "evidence_verified": r.get("verified")}
            for r in bad
        ],
        "passed_checks": [r["id"] for r in results if r["passed"]],
        "injected_error": a.get("injected_error"),
        "memory_rules_used": a.get("memory_rules", []),
        "feedback_received": [{"id": f["id"], "reason": f["reason"]} for f in a.get("feedback_received", [])],
        "writer_change_summary": a.get("writer_summary", ""),
        "generation_error": a.get("generation_error", ""),
        "diff_from_previous": a.get("diff", ""),
        "diff_stats": a.get("diff_stats"),
        "lesson_words": T.count_words(a["lesson"]),
    }


def write_run_outputs(run_dir: Path, run_id: str, topic: str, attempts: list[dict], final: dict) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "attempts").mkdir(exist_ok=True)
    recs = [attempt_record(run_id, topic, i, a) for i, a in enumerate(attempts)]
    for i, a in enumerate(attempts):
        (run_dir / "attempts" / f"attempt_{i}.md").write_text(a["lesson"], encoding="utf-8")
    with open(run_dir / "rejection_log.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (run_dir / "final_lesson.md").write_text(final["lesson"], encoding="utf-8")
    (run_dir / "rejection_log.md").write_text(_markdown_log(topic, recs, final), encoding="utf-8")
    summary = {"run_id": run_id, "topic": topic, "status": final["status"], "attempts": len(attempts),
               "shipped_attempt": final["best_attempt"],
               "failed_checks_per_attempt": [[c["id"] for c in r["failed_checks"]] for r in recs]}
    (run_dir / "run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if final["status"] != "pass":
        best = final.get("best_attempt")
        if best is None:
            lines = ["# NEEDS HUMAN REVIEW", "", "No non-empty lesson was generated.",
                     "The final lesson file contains a diagnostic message, not lesson content.", ""]
            errors = [a.get("generation_error") for a in attempts if a.get("generation_error")]
            for error in errors:
                lines.append(f"- Writer error: {error}")
        else:
            lines = ["# NEEDS HUMAN REVIEW", "",
                     f"The lesson failed {len(recs[best]['failed_checks'])} check(s) after all retries.",
                     "This is the best non-empty attempt. A human must review it before submission.", ""]
            for c in recs[best]["failed_checks"]:
                lines += [f"- **{c['id']}**: {c['reason']}"]
        (run_dir / "NEEDS_HUMAN_REVIEW.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _markdown_log(topic: str, recs: list[dict], final: dict) -> str:
    best = final.get("best_attempt")
    shipped = str(best) if best is not None else "none (no non-empty draft)"
    out = [f"# Rejection log: {topic}", "",
           f"**Final status:** {'PASS (ships)' if final['status'] == 'pass' else 'NEEDS HUMAN REVIEW'}  ",
           f"**Attempts:** {len(recs)}  **Shipped attempt:** {shipped}", ""]
    for r in recs:
        out.append(f"## Attempt {r['attempt']}: {'PASS' if r['passed'] else 'FAIL (' + str(r['n_failed']) + ' checks)'}")
        if r.get("generation_error"):
            out += ["", f"**Writer API error:** {_cell(r['generation_error'])}"]
        if r.get("injected_error"):
            out += ["", f"> Deliberate test error injected: \"{r['injected_error']}\""]
        if r["memory_rules_used"]:
            out += ["", "**Rules from memory given to the writer:**"] + [f"- {m}" for m in r["memory_rules_used"]]
        if r["failed_checks"]:
            out += ["", "| Check | Why it failed | Evidence |", "|---|---|---|"]
            for c in r["failed_checks"]:
                out.append(f"| `{c['id']}` | {_cell(c['reason'])} | {_cell(c['evidence'], 110)} |")
        if r["attempt"] > 0:
            out += ["", "**Feedback the writer received:**"] + [f"- `{f['id']}`: {T.shorten(f['reason'], 160)}" for f in r["feedback_received"]]
            out += ["", f"**Writer says it changed:** {r['writer_change_summary'] or '(nothing reported)'}"]
            st = r["diff_stats"] or {}
            out += ["", f"**What really changed (diff):** +{st.get('lines_added', 0)} / -{st.get('lines_removed', 0)} lines", "",
                    "```diff", r["diff_from_previous"], "```"]
        out.append("")
    return "\n".join(out)
