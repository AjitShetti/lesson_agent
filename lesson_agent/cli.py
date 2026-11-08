"""Command line.  python -m lesson_agent run --topic "Introduction to RAG" """
from __future__ import annotations

import argparse
from pathlib import Path

from .config import Settings
from .memory import Memory


def _settings(a) -> Settings:
    over = {}
    if getattr(a, "provider", None) == "mock":
        over.update(writer_provider="mock", judge_provider="mock")
    if getattr(a, "max_retries", None) is not None:
        over["max_retries"] = a.max_retries
    if getattr(a, "memory_db", None):
        over["memory_db"] = Path(a.memory_db)
    if getattr(a, "output_dir", None):
        over["output_dir"] = Path(a.output_dir)
    return Settings.from_env(**over)


def cmd_run(a) -> None:
    from . import graph

    s = _settings(a)
    print(f"Writer: {s.writer_provider}/{s.writer_model}   Judge: {s.judge_provider}/{s.judge_model}")
    if "mock" in (s.writer_provider, s.judge_provider):
        print("NOTE: mock provider = offline plumbing test. It does not test lesson quality.")
    out = graph.run(a.topic, s, use_memory=not a.no_memory, inject_error=a.inject_error)
    print()
    for i, at in enumerate(out["attempts"]):
        bad = [r["id"] for r in at["results"] if not r["passed"]]
        tag = "PASS" if not bad else "FAIL: " + ", ".join(bad)
        extra = f"   (injected error: \"{at['injected_error']}\")" if at.get("injected_error") else ""
        print(f"  attempt {i}: {tag}{extra}")
        if at.get("generation_error"):
            print(f"             writer error: {at['generation_error']}")
        for r in at["results"]:
            if r.get("execution_error"):
                print(f"             judge error: {' '.join(r['reason'].split())[:160]}")
                break
    print()
    print(f"Status: {out['status'].upper()}   shipped attempt: {out['best_attempt']}")
    print(f"Output folder: {out['run_dir']}")
    print("  final_lesson.md  rejection_log.md  rejection_log.jsonl  run_summary.json  attempts/")


def cmd_health(a) -> None:
    s = _settings(a)
    mem = Memory(s.memory_db)
    top = mem.top_failures()
    print("Top first-attempt failures (last 10 runs):", top or "none yet")
    flags = mem.health(min_runs=a.min_runs)
    print("\nRubric health:")
    if not flags:
        print(f"  no flags (needs at least {a.min_runs} runs, and a check that always or never fails)")
    for f in flags:
        print(f"  {f['check']}: {f['flag']} - {f['advice']}")
    print("\nFirst-attempt stats:", mem.first_attempt_stats())


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="lesson_agent", description="Self-evaluating lesson generator")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="generate -> evaluate -> regenerate")
    r.add_argument("--topic", default="Introduction to RAG")
    r.add_argument("--provider", choices=["mock"], help="use the offline mock models")
    r.add_argument("--inject-error", action="store_true", help="put one false sentence in attempt 0 (demo)")
    r.add_argument("--no-memory", action="store_true", help="do not add learned rules to the writer prompt")
    r.add_argument("--max-retries", type=int)
    r.add_argument("--memory-db")
    r.add_argument("--output-dir")
    r.set_defaults(fn=cmd_run)

    h = sub.add_parser("health", help="show memory and rubric health")
    h.add_argument("--min-runs", type=int, default=5)
    h.add_argument("--memory-db")
    h.set_defaults(fn=cmd_health)

    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
