# Design Document

## 1. What problem this solves

The lesson is not the product. The product is a **system that decides, without a human, if a lesson is good enough to ship**.
So the evaluator is the most important part. I built and tested it first, and the writer second.

## 2. Architecture

```
prepare -> generate -> evaluate -> router -> finalize -> memory_update
              ^                       |
              +-------- retry --------+   (max 2 retries)
```

| Node | Job | Why separate |
|---|---|---|
| prepare | read top failures from memory, make writer rules | memory is read once per run |
| generate | writer model makes the lesson (on retry: sees old lesson + feedback) | writer knows nothing about scoring code |
| evaluate | runs all applicable checks, even if some fail; empty drafts stop before LLM checks | one retry gets complete feedback |
| router | `pass -> finalize`, `fail and retries left -> generate`, else `finalize` | the stop rule lives in one small function |
| finalize | pick best non-empty attempt, write lesson + rejection log | an empty retry never replaces usable lesson text |
| memory_update | store check results in SQLite | learning happens after the output is safe |

**Why LangGraph:** this is a loop with state and a counter. Conditional edges make the pass/fail loop clear and testable.
n8n can do it, but loops with state are easier to read and unit test in code.

## 3. The rubric: hard pass/fail

Each check is a yes/no question. No scores, no partial credit. 12 checks cover the dimensions in the brief (see README table).
The target learner changes the rules: sentences ≤ 15 words, every term defined at first use, no idioms or Latin short forms,
everyday examples (exam, school, library).

**Code vs LLM split.** An LLM cannot count words or syllables reliably. So everything measurable is Python (7 checks).
The LLM only does what needs meaning (5 checks): are claims true to the sheet, are key points taught,
is the example correct, is the order clear, are there unexplained terms.

## 4. Why the evaluator can be trusted

| Risk | Safe-guard |
|---|---|
| Judge agrees with the writer by habit | Different model, different prompt, temperature 0, JSON only |
| "Is this accurate?" invites a guess | Judge first lists every claim, then checks each against the fact sheet |
| Judge says "supported" without proof | It must quote the fact sheet. If the quote is not in the sheet, the claim fails |
| Judge invents a complaint | It must quote the lesson. A complaint with a quote we cannot find is dropped |
| Judge returns broken JSON | One retry, then the check **fails** (fail closed) |
| Judge omits claim verdicts | Claims are checked in batches; missing IDs get a targeted retry |
| Writer returns an empty draft | One immediate writer retry; empty drafts cannot be selected as the best lesson |
| Claim true in life but not in the sheet | Counts as a fail. Strict on purpose: the sheet is the only truth |
| Writer writes "to the test" | Writer gets a general style guide, not the numbers. Numbers come back only as feedback |

I test the evaluator on one good and one bad hand-made lesson (`scripts/judge_reliability.py`).
It must pass the good lesson every time, fail the bad lesson on the listed checks every time, and give the same answer on repeat runs.

**Trade-off:** dropping complaints we cannot verify lowers false fails, but it can let a real problem pass.
The code checks and the reliability test reduce this risk. I accept it because endless false fails would send every lesson to human review.

## 4b. Grounding

`data/fact_sheet.md` is the only source of truth. I verify it against the original paper (Lewis et al., 2020) and public docs.
Fixing the evaluator to a small, checked source is better than trusting a model's memory.

## 5. Retry and stop rule

Feedback sent to the writer: check id, reason, and exact evidence for every failed check, plus the old lesson.
Max 2 retries, so the loop always ends. Empty writer replies get one immediate retry. After that: ship the best non-empty attempt with `status = needs_human_review`
and `NEEDS_HUMAN_REVIEW.md`. Calls are bounded: at most 6 writer calls, plus batched judge calls and targeted retries for missing verdicts.

## 6. Rejection log (a required output)

For every attempt: failed checks with reason and evidence, the feedback the writer received,
what the writer **says** it changed, and the **real** text diff. The writer's summary can be wrong,
so the diff makes the record checkable.

## 7. Memory and self-evolving

SQLite stores every check result. Before a run, the 3 checks that failed most on the first attempt in the **last 10 runs**
become plain rules in the writer prompt (each check has a `writer_rule` in the rubric).

- Top 3 only: keeps the prompt short.
- Last-10-runs window: fixed problems stop being injected.
- `python -m lesson_agent health`: flags checks that **always fail** (maybe impossible) or **never fail** (maybe too easy).
  This is how the rubric itself gets sharpened.
- `scripts/memory_experiment.py`: same topic, same sheet, memory OFF then ON. Compares first-attempt pass rate.
  It is the proof that the rules help, not just a claim.

**Known weakness:** when a rule works, the failure disappears from the window, the rule drops out, and the failure may return.
A "sticky rule" for a minimum number of runs would fix this. I did not build it.

## 8. Deliberate-error test

`--inject-error` adds one false but simple sentence to the first draft. Because it is short and plain,
only the grounding check can catch it. The test asserts exactly that, and that the retry removes the line.

## 9. Testing

60 offline tests: each code check, each judge safe-guard (fake JSON, fake quotes, missing verdicts),
the loop (pass first try, pass on retry, always-bad, max-retries, best-attempt choice), the log content,
memory window and health, and the API request shape. The mock provider tests plumbing only.
Quality testing needs real models.

## 10. What I would do next

1. Build a larger test set for the judge (20+ lessons with human labels) and report precision and recall per check.
2. Add human feedback on the rubric (does a real learner understand the lesson?).
3. Sticky memory rules and a per-check dashboard.
4. Support many topics: one fact sheet per topic, built from retrieved sources instead of by hand.
