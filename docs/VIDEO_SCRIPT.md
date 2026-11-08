# Loom outline (target 17 minutes, face visible)

| Time | Show | Say |
|---|---|---|
| 0:00-1:30 | Face + README diagram | Who I am. The lesson is not the product; the system that decides "ship or not" is. |
| 1:30-4:00 | `DESIGN.md` + `data/rubric.json` | 11 hard pass/fail checks. Why code for measurable checks and LLM only for meaning. Why this learner changes the rules. |
| 4:00-6:30 | `checks/llm_judge.py` | Safe-guards: different model, claim list first, quote must be in the fact sheet, fail closed. |
| 6:30-10:00 | Terminal: `python -m lesson_agent run` | Full loop end to end. Show attempt 0 fail, feedback, attempt 1 pass. Open `rejection_log.md`: reason, feedback, writer summary, real diff. |
| 10:00-13:00 | Terminal: `run --inject-error` | The false line. Evaluator fails `claims_grounded` and quotes it. Retry removes it. Open `attempt_0.md` to show the line. |
| 13:00-15:00 | `judge_reliability.py` | Good lesson passes, bad lesson fails, no unstable checks. |
| 15:00-17:00 | `memory_experiment.py`, `health` | Memory OFF vs ON numbers. Always/never-failing checks. Honest limits. |
| 17:00-18:00 | Face | Trade-offs and what I would do next. |

Before recording: run everything once with real keys. Keep one failing run on purpose so the log has content.
