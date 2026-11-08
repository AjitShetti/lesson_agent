# Design Document

This file records **every design choice and its trade-off**. Part A is the audit against the assessment brief.
Part B is the decision log (D1-D18). Part C lists what was removed during the simplification and why.
Part D is the verification evidence. Part E is the honest list of limits.

---

## Part A. Audit against the assessment brief

### A1. Requirement checklist

| Brief requirement | Status | Where / evidence |
|---|---|---|
| Input: a topic (`Introduction to RAG`) | Met | `python -m lesson_agent run --topic "Introduction to RAG"` (this is the default topic) |
| Generate a standalone beginner lesson: what it is, why it matters, how it works | Met | Writer prompt requires `What is / Why / How / Example / Summary`; `required_sections` check enforces the order |
| Evaluate with hard pass/fail checkpoints, no partial credit | Met | `data/rubric.json`: 12 checks, each returns `passed: true/false`; a lesson ships only if all 12 pass |
| Dimensions: accurate and grounded, beginner-friendly language, teaches by example, no unexplained jargon, covers key points, coherent flow | Met | Each check has a `dimension` field. See the table in `README.md` |
| Regenerate on fail, feed the reasons back, max 1-2 retries, always terminates | Met | `graph.py` router; `MAX_RETRIES=2`; tested (`test_loop_stops_after_max_retries...`) |
| Output: passing lesson + rejection log (what failed, why, what changed on retry) | Met | `final_lesson.md`, `rejection_log.md/.jsonl`; log has reason, evidence, feedback sent, the writer's own change summary, and the real diff |
| Self-evolving: learn from repeated failures to sharpen prompts/rubrics | Met (prompts automatic, rubric assisted) | Memory turns top first-attempt failures into writer rules. `health` flags checks that always/never fail so a person can sharpen the rubric |
| Memory persists across runs | Met | SQLite `memory/memory.db` |
| Stack: LangGraph / Python + API, any model | Met | Python + LangGraph; Groq writer, Gemini judge |
| Deliverable: README with setup and run instructions | Met | `README.md` |
| Deliverable: final lesson as a document | Needs you | `sample_run_real/final_lesson.md` is a verified passing lesson to paste into Google Docs/Notion. You may prefer your own run |
| Deliverable: Loom video (15-20 min) | Needs you | a full spoken script is kept locally, not in the repo |

### A2. Findings from running the original code with real models

I ran the **unmodified** code against the real Groq writer and Gemini judge before changing anything.
The offline tests (60) all passed, but the real pipeline had never completed a clean passing run
(the earlier "passing" runs in `outputs/` were mock runs; the real "Explain RAG" runs all ended in `needs_human_review`).

| # | Finding | Evidence | Fix |
|---|---|---|---|
| F1 | **Judge made 6 or more calls per attempt, but the Gemini free tier allows 20 requests per day per model.** One 3-attempt run could not fit. | Live 429 body: `GenerateRequestsPerDayPerProjectPerModel-FreeTier`, `quotaValue: 20` | Judge reduced to 2 calls per attempt (D6) |
| F2 | The default judge model `gemini-2.5-flash` was already over quota, and `-2.0-flash` / `-2.5-flash-lite` return 404 for this key. | Live responses | Default judge is now `gemini-flash-latest`; README and `.env.example` explain the daily limit and how to switch model |
| F3 | The claim-verification reply for a ~950-word lesson needs about 7,500 output tokens against a cap of 8,192, so it sits next to truncation and invalid JSON. The old code worked around this with batching. | Measured: `completion_tokens: 7565` for one lesson. Real run: `invalid JSON for 'ground'` on all 3 attempts | Judge answers with a sentence number and a short quote instead of copying the sentence back; token cap raised to 16,384 (D7) |
| F4 | `jargon_defined` kept failing, and the retry feedback could not fix it. The writer wrote good plain explanations ("Create embeddings. We turn each chunk into a list of numbers.") that the structural check does not accept, and the feedback never said which forms are accepted. | Real run: same 3 terms failed on attempts 0, 1 and 2 | The feedback now says the accepted forms and gives a ready sentence from `data/jargon.json` for each term (D10) |
| F5 | The good fixture lesson contained statements the fact sheet does not support (ChatGPT/Claude, "a few sentences long", "cannot answer questions about them"). A strict judge correctly fails it, so `judge_reliability.py` could never pass with a real judge. | Real reliability run: `claims_grounded` WRONG, then UNSTABLE | Fixture lesson rewritten to use only fact-sheet statements (D8) |
| F6 | Quota detection stopped on any Gemini 429 containing "exceeded your current quota". That text is in **per-minute** limits too, which are worth waiting for. | Gemini error text | Only a daily limit (`per day`), `insufficient_quota` or an inactive billing account stops at once |
| F7 | CLI printed `FAIL: draft_nonempty` when the real cause was a writer API error, and hid judge quota errors. | Real run with a bad provider name | CLI prints writer and judge errors |
| F8 | `.env` hazards seen in the original file: `WRITER_MODEL=   # comment` was read as the model name `# exact model ID...`; the provider was `console.groq.com`; the Groq key was stored as `XAI_API_KEY`. | Real run: `Writer: groq/# exact model ID from your xAI console` | Inline comments are now ignored by the loader; the aliases and the legacy key fallback were removed (D14); `.env.example` is rewritten. **Your own `.env` still needs the fix described in the final message** |
| F9 | The old video outline said "11 hard pass/fail checks"; the rubric has 12. | Count of `data/rubric.json` | Fixed; the outline was later replaced by a local script |
| F10 | A Groq outage (HTTP 503, "model over capacity") ended one run. | Live response | Not a code defect: retries with backoff ran, the failure was reported clearly. Re-run |
| F11 | A model that never answers (`gemini-3.7-flash`) made my own test run stall for about 30 minutes: 6 attempts x 120-second timeouts. | Observed | A timeout is now retried once, then fails with a clear message (D14) |

---

## Part B. Decision log

Each entry: **choice**, **alternatives**, **why**, **trade-off**. Entries marked **(changed in audit)** differ from the original code.

### D1. The evaluator is the product, not the lesson
**Choice:** build and test the "should this ship?" decision first; the writer second.
**Why:** the brief says the point is the generate, evaluate, regenerate loop that decides on its own.
**Trade-off:** more engineering effort on the judge than on the writer. The lesson quality depends on the writer model, which is easy to swap.

### D2. LangGraph for the loop
**Choice:** a small `StateGraph`: `prepare -> generate -> evaluate -> router -> (generate | finalize) -> memory_update`.
**Alternatives:** n8n (visual, but loops with state and unit tests are harder), a plain `while` loop (simpler still), LangChain chains (no natural loop).
**Why:** the brief lists LangGraph; conditional edges make the stop rule a single readable function (`router`).
**Trade-off:** one extra dependency. A plain `while` loop would be about as short; the graph buys a clear diagram for the video.

| Node | Job | Why separate |
|---|---|---|
| prepare | read top failures from memory, make writer rules | memory is read once per run |
| generate | writer makes the lesson (on retry it sees the old lesson + feedback) | writer knows nothing about the scoring code |
| evaluate | run all checks | one retry gets complete feedback, not one failure at a time |
| router | `pass -> finalize`, `fail and retries left -> generate`, else `finalize` | the stop rule lives in one place |
| finalize | pick the best non-empty attempt, write outputs | an empty retry never replaces usable text |
| memory_update | store check results | learning happens after the output is safe |

### D3. Hard pass/fail rubric, all 12 must pass
**Choice:** each check is a yes/no question; the lesson ships only if every check passes.
**Alternatives:** weighted score with a threshold.
**Why:** the brief says "no partial credit"; a threshold hides which dimension failed, and a yes/no reason is directly usable as writer feedback.
**Trade-off:** strict. One weak check blocks shipping. Mitigated by `health` (D13), which flags checks that always fail.

### D4. Code for what can be measured, an LLM only for meaning
**Choice:** 7 checks in Python (length, readability, idioms, jargon placement, sections, word count, non-empty); 5 by the LLM (grounded, key points, example, flow, unexplained terms).
**Why:** an LLM cannot count words or syllables reliably; code gives the same answer every time and costs no API calls.
**Trade-off:** the code checks are heuristics. Flesch scores use a simple syllable rule; `jargon_defined` checks *placement* of a definition, not its quality (the LLM check covers meaning).

### D5. Writer and judge are from different vendors
**Choice:** Groq (writer) and Gemini (judge); the judge runs at temperature 0, JSON only.
**Why:** a judge from the same model family tends to agree with the writer's mistakes.
**Trade-off:** two keys and two quotas to manage. Both providers are free-tier friendly.

### D6. Two judge calls per attempt **(changed in audit)**
**Choice:** call 1 `ground` answers `claims_grounded`; call 2 `review` answers `key_points_covered`, `teaches_by_example`, `flow_coherent` and `no_unexplained_terms`.
**Was:** six separate calls (extract claims, verify claims in batches of 8, coverage, example, flow, unexplained terms), plus a targeted retry for missing verdicts.
**Why:** (a) free-tier daily limit (F1); (b) fewer moving parts to explain; (c) the lesson is read once per call instead of six times.
**Trade-off:** each call is a bigger task, so a single bad reply fails every check in its group (fail closed, see D7). The prompts keep each question separate in the JSON, and all quotes are still checked by code, so focus is not lost in practice (see Part D).

### D7. Judge safe-guards: trust only what code can check
| Risk | Safe-guard |
|---|---|
| Judge agrees by habit | Different vendor and prompt, temperature 0, JSON only |
| "Is this accurate?" invites a guess | One verdict per numbered lesson sentence, compared only with the fact sheet |
| Judge says "supported" without proof | It must copy a short quote from the fact sheet. If that quote is not in the sheet, the claim fails |
| Judge invents a sentence | It answers with a sentence **number**; a number outside the lesson is ignored. It cannot make up a claim **(changed in audit)** |
| Judge invents a complaint | Every complaint (flow, unexplained term) needs a quote from the lesson. A quote we cannot find is dropped |
| Judge flags a term that is defined next to it | The complaint is dropped if the plain-code rule finds a definition next to the term (same function as `jargon_defined`) |
| Broken JSON | One retry, then the checks of that call **fail** (fail closed). They never pass by accident |
| Claim true in life but not in the sheet | Counts as a fail. The sheet is the only truth (D8) |

**Why numbered sentences (changed in audit):** the old reply copied every lesson sentence back plus a `reason`, which for a long lesson needs about 7,500 tokens and risks truncation (F3). A number plus a 15-word quote cuts the reply size by more than half, and makes invented claims impossible.
**Trade-offs:** (1) dropping unverifiable complaints lowers false fails but can let a real problem pass; the code checks and the reliability test reduce this. (2) The judge decides which sentences are facts. If it skips a sentence, that sentence is not checked; the result records `sentences_without_verdict` so this is visible (it was 0 in every real run I made). (3) A strict judge sometimes flips on borderline sentences; see D8 and Part E.

### D8. The fact sheet is the only source of truth, and it is strict
**Choice:** `data/fact_sheet.md` is the only thing a claim is checked against.
**Why:** a small checked source is better than trusting a model's memory.
**Trade-off:** a true statement missing from the sheet fails (for example "ChatGPT is an LLM"). This is on purpose but makes lessons plainer. The sheet must be correct: **verify it against the Lewis et al. (2020) paper before submitting.**
**Audit change:** the good fixture lesson was rewritten to use only fact-sheet statements (F5).

### D9. The writer gets a style guide, not the rubric numbers
**Choice:** the writer prompt says "short sentences", not "15 words". The exact numbers reach the writer only as retry feedback or as a learned memory rule.
**Why:** it stops the writer from just writing to the test, and it makes the feedback loop do real work.
**Trade-off:** the first draft often fails the numeric checks. In my real run attempt 0 failed 4 checks (sentence length, word count, grounding, flow) and the lesson passed on attempt 2, the last allowed. Giving the writer the numbers would raise first-try passes. I kept the original choice because it is what makes the rejection log interesting; it is the first thing to relax if you want fewer retries.

### D10. Retry feedback is specific and actionable
**Choice:** feedback = check id + reason + exact evidence for each failed check, plus the previous lesson. The writer must return the full lesson, then `---CHANGES---` with its own summary.
**Audit change:** for `jargon_defined` the reason now names the accepted forms ("X is ...", "X means ...", "X (...)", "called X") and gives a ready sentence from `data/jargon.json` for each missing term (F4).
**Trade-off:** the writer is told how to satisfy a heuristic. That is acceptable: the goal is a clear definition next to the term, which is also what a learner needs.

### D11. Stop rule and provider errors
**Choice:** at most 1 + 2 attempts. The brief allows 1-2 retries, so `Settings` lowers any larger `MAX_RETRIES` or `--max-retries` to 2 (added after the independent review). After that, ship the best non-empty attempt (fewest failed checks; ties go to the latest) with `status = needs_human_review` and `NEEDS_HUMAN_REVIEW.md`. An empty writer reply gets one immediate re-ask. A **provider error** (quota, bad key, outage) stops the loop at once instead of burning retries, because rewriting cannot fix it.
**Trade-off:** a transient judge outage ends the run early; it can be re-run. This is better than sending three lessons to a broken judge.

### D12. The rejection log records the writer's claim and the truth
**Choice:** for every attempt: failed checks with reason and evidence, the feedback the writer received, what the writer **says** it changed, and the **real** diff.
**Why:** the writer's summary can be wrong; the diff makes it checkable.
**Trade-off:** extra output files. `rejection_log.md` is for people, `rejection_log.jsonl` for tools.

### D13. Memory and self-evolution
**Choice:** SQLite stores every check result. Before a run, the 3 checks that failed most on the **first attempt** in the **last 10 runs** become plain rules in the writer prompt (each check has a `writer_rule` in the rubric). `health` flags checks that always fail (maybe impossible) or never fail (maybe too easy).
**Why:** top 3 keeps the prompt short; a 10-run window means fixed problems stop being injected; first-attempt failures are the writer's habits, while later failures are partly caused by feedback.
**Trade-offs / weakness:** when a rule works, the failure leaves the window, the rule drops out, and the failure may return. A "sticky rule" would fix this; I did not build it. The memory *effect* needs many runs to measure (`scripts/memory_experiment.py`), which the free judge quota cannot support (Part E).

### D14. One HTTP path for all models **(changed in audit)**
**Choice:** `llm.complete()` posts an OpenAI-style `chat/completions` request with `requests`. Providers: `groq`, `gemini`, `openai`, plus `mock`. No vendor SDKs.
**Retry policy:** retry 429, 5xx and network errors with waits of 2, 5, 15, 30, 60 seconds, or the server's `Retry-After`. A daily-quota 429 stops at once (F6). Other 4xx errors stop at once. A request that **times out** is retried only once: a hung model (seen with `gemini-3.7-flash`, which stalled one test for about 30 minutes before this rule) will not answer on the 5th try either. `CALL_INTERVAL_SECONDS` spaces calls to one provider.
**Trade-off:** fewer providers and fewer special cases (Part C). If you switch to a model that rejects `temperature` or `response_format`, the call now fails with the provider's message instead of silently retrying without them.

### D15. A mock provider for offline plumbing tests
**Choice:** `mock_llm.py` returns canned lessons and rule-based judge answers.
**Why:** tests and the first demo need no API key or quota.
**Trade-off:** it says nothing about lesson quality. Every place that uses it says so.

### D16. Configuration through environment variables
**Choice:** `.env` -> `Settings`. A value that starts with `#` after the `=` counts as empty and falls back to the default model (F8).
**Trade-off:** none worth noting; it removes one confusing failure.

### D17. The deliberate-error test
**Choice:** `--inject-error` adds one false but simple sentence to the first draft: *"RAG retrains the model on your documents every time you ask a question."*
**Why:** because it is short and plain, only the grounding check (and, in real runs, the flow check) can catch it. The test asserts that the check fails, quotes the line, and the retry removes it.

### D18. Testing
**Choice:** 67 offline tests: each code check; each judge safe-guard (fake JSON, fake quotes, missing or invented sentence numbers, provider errors, one attempt = 2 calls); the loop (pass first try, pass on retry, always-bad, max-retries, best-attempt choice); the log content; memory window and health; request shape and retry rules.
**Plus** a real-model reliability script (`scripts/judge_reliability.py`) that runs a hand-made good lesson and bad lesson through the real judge and reports checks that give the wrong or an unstable answer.

---

## Part C. What the simplification removed

| Removed | Why it was safe to remove |
|---|---|
| Anthropic native request path, xAI provider | Not used in this assignment; each was an extra code path and tests. Groq, Gemini, OpenAI share one path |
| Legacy `XAI_API_KEY` as a Groq key; `console.groq.com` provider alias; per-provider base-URL env variables | Config oddities that caused F8. One variable per provider now |
| Retry-without-`temperature`/`response_format` on HTTP 400 | A hidden second code path; see the trade-off in D14 |
| Parsing Groq's "try again in 217ms" message | `Retry-After` plus the backoff schedule is enough |
| Claim batching (8 per call) and the targeted retry for missing verdicts | The numbered-sentence reply is short enough for one call (D7) |
| Separate extract-claims and verify-claims calls, and four more separate judge prompts | Replaced by two prompts (D6) |
| Old single-`quote` response shape for key points | Compatibility for a prompt version that no longer exists |
| A second definition-detection regex inside the LLM judge | The judge now reuses the one in `code_checks` (`defined_nearby`) |
| `sample_run_mock/` (output of fake models), `docs/VIDEO_SCRIPT.md` (short outline replaced by a fuller local script), and the empty `.gitkeep` files | Files with no purpose: the real sample replaces the mock one, and the code creates `memory/` and `outputs/` itself |
| `REGISTRY` mixing code and LLM checks | Code checks have a table; LLM checks come from the two judge calls, and a rubric check that no call answers raises an error instead of silently passing |

**Honest size note:** the source is about 1,420 lines (was about 1,520); tests about 625 lines (was about 705). The main gain is in **concepts to explain**: 6 judge calls became 2, 5 providers became 3 with one request path, and 3 special-case retry rules disappeared.

**Kept on purpose:** the 12-check rubric, the memory design, the rejection log with real diff, the mock provider, both scripts, and the strict fact-sheet rule. Each maps to a line in the brief.

---

## Part D. Verification evidence

All real-model runs used the Groq writer `qwen/qwen3.8-27b` and a Gemini judge.

| Test | Result |
|---|---|
| Offline test suite | 67 passed |
| Mock end-to-end with `--inject-error` | attempt 0 fails `sentence_length`, `no_idioms`, `claims_grounded`; attempt 1 passes |
| **Real end-to-end with `--inject-error`** (`sample_run_real/`; judge `gemini-3.5-flash`) | attempt 0 failed `sentence_length`, `claims_grounded` (quoted the injected line as `contradicted`), `lesson_length`, `flow_coherent`; attempt 1 failed `claims_grounded` (one sentence beyond the fact sheet); **attempt 2 passed all 12 checks**. Judge gave a verdict on every sentence (0 skipped) |
| **Real end-to-end, plain `run`, final code** (judge `gemini-3.1-flash-lite`) | attempt 0 failed `sentence_length`, `jargon_defined`, `claims_grounded`, `key_points_covered`; attempt 1 failed `jargon_defined`; **attempt 2 passed all 12 checks** |
| Real judge reliability (`judge_reliability.py`) | Good lesson passes 12/12 and bad lesson fails 12/12, 3 of 3 runs. Details below |

**Real judge reliability, final code and fixtures** (`scripts/judge_reliability.py --runs 3`, judge `gemini-3.1-flash-lite`):

| Lesson | Result over 3 runs |
|---|---|
| Hand-made good lesson | all 12 checks pass on 3 of 3 runs |
| Hand-made bad lesson (idioms, long sentences, false claims, no structure) | all 12 checks fail on 3 of 3 runs |
| Unstable checks | none |

How I got there (this is the evidence that the evaluator is strict but fair, so I am recording it):
- Run on `gemini-flash-lite-latest` with the first version of the fixture: good lesson failed `claims_grounded` because the fixture contained sentences beyond the fact sheet. The judge was right; the fixture was fixed (F5).
- Run on `gemini-3.5-flash`: one more sentence beyond the sheet was found ("It cannot answer questions about them"). The real writer made the same mistake on its own in a separate run, and the judge flagged it the same way.
- Run on `gemini-3.5-flash-lite` and `gemini-flash-lite-latest`: two borderline sentences flipped (`LLM stands for large language model`, `a large pile of text`). I rewrote them to use the fact sheet's own wording.
- Final run above: stable.
- The bad lesson failed every check in every run on every judge I tried.

**Caveats on this evidence:** the error-injection run used `gemini-3.5-flash`, the plain run and the reliability run used `gemini-3.1-flash-lite`; the default `gemini-flash-latest` had no quota left when I tested (F2), so I could not run the final code against that exact model. Reliability was measured over 3 runs, which shows stability but is not a statistical proof.

---

## Part E. Limits and what I would do next

**Limits I know about**
1. The judge picks which sentences are facts; a skipped sentence is not checked (it is counted in the result).
2. A strict LLM judge can flip on borderline sentences. The reliability script exists to find them; the fixture lesson needed several edits before it was stable (Part D).
3. Both real runs I made passed, but both on the last allowed attempt (attempt 2). A different draw can end in `needs_human_review`; that is the designed fallback, not a crash. The brief caps retries at 1-2, so `MAX_RETRIES` must stay at 2 or below. The honest way to get more headroom is to give the writer the numeric limits (D9).
4. Gemini's free tier (about 20 requests/day/model) limits how many real runs fit in a day. `scripts/memory_experiment.py` needs far more calls, so I did **not** run it with real models; it runs offline with the mock (where the mock writer ignores memory, so it shows no effect).
5. The fact sheet is small and I did not verify it line by line against the paper. You must do this (README, "Before you submit").
6. `jargon_defined` only checks that a definition sits next to the term, not that it is good.

**Next steps**
1. A larger labelled test set for the judge (20+ lessons) with precision and recall per check.
2. Real-learner feedback on the rubric.
3. Sticky memory rules and a per-check dashboard.
4. One fact sheet per topic, built from retrieved sources instead of by hand.
5. Consider giving the writer the numeric limits (D9) if first-try passes matter more than a rich rejection log.
