"""Does memory really help?  Same topic, same fact sheet, same models. Only the memory rules differ.

Phase A: N runs with memory OFF (also builds the failure history).
Phase B: N runs with memory ON (top 3 learned rules are added to the writer prompt).
Compare the first-attempt pass rate and the average number of failed checks on the first attempt.

    python scripts/memory_experiment.py --runs 5

Honest limits: small N is noisy. Writers vary from run to run. Use N >= 5 and read the numbers as a hint, not a proof.
"""
import argparse
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lesson_agent import graph  # noqa: E402
from lesson_agent.config import Settings  # noqa: E402
from lesson_agent.memory import Memory  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--topic", default="Introduction to RAG")
    ap.add_argument("--provider", choices=["mock"])
    a = ap.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="memexp-"))
    over = {"writer_provider": "mock", "judge_provider": "mock"} if a.provider == "mock" else {}
    s = Settings.from_env(memory_db=tmp / "mem.db", output_dir=tmp / "out", **over)
    if s.writer_provider == "mock":
        print("NOTE: the mock writer ignores memory rules, so it cannot show any effect. Use real models.\n")

    print(f"Phase A: {a.runs} runs, memory OFF")
    for i in range(a.runs):
        out = graph.run(a.topic, s, use_memory=False)
        print(f"  run {i + 1}: first attempt failed {[r['id'] for r in out['attempts'][0]['results'] if not r['passed']]}")
    print(f"\nPhase B: {a.runs} runs, memory ON")
    for i in range(a.runs):
        out = graph.run(a.topic, s, use_memory=True)
        print(f"  run {i + 1}: rules {len(out['memory_rules'])}, first attempt failed "
              f"{[r['id'] for r in out['attempts'][0]['results'] if not r['passed']]}")

    m = Memory(s.memory_db)
    off, on = m.first_attempt_stats(False), m.first_attempt_stats(True)
    print("\n                         memory OFF   memory ON")
    print(f"first-attempt pass rate  {off['first_attempt_pass_rate']:>10.0%}   {on['first_attempt_pass_rate']:>9.0%}")
    print(f"avg failed checks (1st)  {off['avg_failed_checks_first_attempt']:>10.2f}   {on['avg_failed_checks_first_attempt']:>9.2f}")
    print("\nRubric health:", m.health(min_runs=5) or "no flags")
    m.close()
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
