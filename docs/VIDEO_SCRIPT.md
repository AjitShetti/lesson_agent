# Loom outline (target 17 minutes, face visible)

The brief asks the video to show three things: (1) the workflow running end to end, (2) the evaluator catching a deliberate error, (3) a face-visible walkthrough. Rows below are marked with the one they cover.

| Time | Show | Say |
|---|---|---|
| 0:00-1:30 | Face + README diagram (3) | Who I am. The lesson is not the product; the system that decides "ship or not" is. |
| 1:30-4:00 | `DESIGN.md` + `data/rubric.json` (3) | 12 hard pass/fail checks, mapped to the six dimensions in the brief. Why code for measurable checks and an LLM only for meaning. Why this learner changes the rules. |
| 4:00-6:30 | `checks/llm_judge.py` (3) | Two judge calls per attempt. Safe-guards: different vendor, a verdict per numbered sentence, the quote must be in the fact sheet, fail closed. |
| 6:30-10:00 | Terminal: `python -m lesson_agent run` (1) | Full loop end to end. Show attempt 0 fail, the feedback, attempt 1 pass. Open `rejection_log.md`: reason, feedback, writer summary, real diff. |
| 10:00-13:00 | Terminal: `run --inject-error` (2) | The false line. The evaluator fails `claims_grounded` and quotes it. The retry removes it. Open `attempt_0.md` to show the line. |
| 13:00-15:00 | `scripts/judge_reliability.py --runs 1` (2) | Good lesson passes, bad lesson fails, no wrong or unstable checks. |
| 15:00-17:00 | `python -m lesson_agent health`, then `DESIGN.md` section on memory (3) | Memory turns the top first-attempt failures into writer rules. Always/never-failing checks show where the rubric needs sharpening. Honest limits. |
| 17:00-18:00 | Face (3) | Trade-offs (see `DESIGN.md`) and what I would do next. |

Before recording:
- Run everything once with real keys. Gemini's free tier allows about 20 requests per day per model name, and one attempt uses 2 judge calls. Plan the day: one `run` (up to 6), one `run --inject-error` (up to 6), one `judge_reliability --runs 1` (4). Switch `JUDGE_MODEL` to another Gemini model if one runs out.
- Keep one failing run on purpose so the rejection log has content.
- `scripts/memory_experiment.py` needs many calls. Only run it with a paid judge key, or skip it and say so.
