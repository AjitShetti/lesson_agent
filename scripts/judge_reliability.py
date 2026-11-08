"""Is the evaluator trustworthy? Run it several times on a known-good and a known-bad lesson.

    python scripts/judge_reliability.py --runs 3            # uses the models in your .env
    python scripts/judge_reliability.py --runs 3 --provider mock

Pass if: the good lesson passes every check on every run, the bad lesson fails every check in
examples/expectations.json on every run, and no check changes its answer between runs on the same text.
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lesson_agent.config import Settings  # noqa: E402
from lesson_agent.rubric import evaluate, load_context  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--provider", choices=["mock"])
    a = ap.parse_args()
    s = Settings.from_env(**({"writer_provider": "mock", "judge_provider": "mock"} if a.provider == "mock" else {}))
    ctx = load_context(s)
    exp = json.loads((ROOT / "examples" / "expectations.json").read_text(encoding="utf-8"))
    print(f"Judge: {s.judge_provider}/{s.judge_model}  (temperature {s.judge_temperature})")
    if s.judge_provider == "mock":
        print("NOTE: mock judge = plumbing only. Run with real models to test real quality.\n")

    ok = True
    for name in ("good_lesson", "bad_lesson"):
        text = (ROOT / "examples" / f"{name}.md").read_text(encoding="utf-8")
        passes = defaultdict(list)
        for _ in range(a.runs):
            for r in evaluate(text, ctx):
                passes[r["id"]].append(r["passed"])
        print(f"== {name}  ({a.runs} runs)")
        print(f"{'check':24} {'passed':>8}  note")
        for cid, vals in passes.items():
            n = sum(vals)
            note = ""
            if 0 < n < len(vals):
                note, ok = "UNSTABLE (answer changed between runs)", False
            want_fail = cid in exp.get("bad_lesson", {}).get("must_fail", [])
            if name == "good_lesson" and n != len(vals):
                note, ok = (note or "WRONG: good lesson must pass"), False
            if name == "bad_lesson" and want_fail and n != 0:
                note, ok = (note or "WRONG: bad lesson must fail"), False
            print(f"{cid:24} {n}/{len(vals):<5}  {note}")
        print()
    print("RESULT:", "evaluator behaves as expected" if ok else "evaluator needs work (see notes above)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
