"""The LLM judge can be wrong. These tests prove the safe-guards around it work."""
import json

from lesson_agent import llm, rubric
from lesson_agent.checks import llm_judge as J

LESSON = "# T\n\n## What is X?\n\nRAG finds facts first. Then the LLM writes the answer. RAG does not train the LLM again.\n"
SHEET_QUOTE = "RAG stands for Retrieval-Augmented Generation."  # a real line of data/fact_sheet.md


def fake(replies):
    """replies: dict task -> str. The two judge tasks are "ground" and "review"."""
    calls = []

    def _complete(settings, role, task, system, user, json_mode=False):
        calls.append(task)
        return replies.get(task, "not json")

    _complete.calls = calls
    return _complete


def verdict(n=1, verdict="supported", sheet_quote=SHEET_QUOTE, reason="x"):
    """One judge verdict. Sentence 1 of LESSON is "RAG finds facts first."; sentence 2 is "Then the LLM writes the answer."."""
    return {"n": n, "verdict": verdict, "sheet_quote": sheet_quote, "reason": reason}


def ground(ctx, monkeypatch, *verdicts):
    monkeypatch.setattr(llm, "complete", fake({"ground": json.dumps({"verdicts": list(verdicts)})}))
    return J.judge_grounding(LESSON, ctx)["claims_grounded"]


def review(ctx, monkeypatch, **parts):
    monkeypatch.setattr(llm, "complete", fake({"review": json.dumps(parts)}))
    return J.judge_review(LESSON, ctx)


# ---------------------------------------------------------------- fail closed
def test_invalid_json_twice_fails_every_check_of_that_call(ctx, monkeypatch):
    monkeypatch.setattr(llm, "complete", fake({}))
    results = {r["id"]: r for r in rubric.evaluate(LESSON, ctx)}
    for check_id in ("claims_grounded", "key_points_covered", "teaches_by_example", "flow_coherent", "no_unexplained_terms"):
        assert not results[check_id]["passed"] and "invalid JSON" in results[check_id]["reason"]


def test_one_attempt_costs_exactly_two_judge_calls(ctx, monkeypatch):
    good = fake({"ground": json.dumps({"verdicts": [verdict()]}), "review": json.dumps({})})
    monkeypatch.setattr(llm, "complete", good)
    rubric.evaluate(LESSON, ctx)
    assert good.calls == ["ground", "review"]


def test_provider_error_marks_execution_error_and_skips_later_calls(ctx, monkeypatch):
    calls = []

    def broken(*args, **kwargs):
        calls.append(1)
        raise llm.LLMError("Out of quota.")

    monkeypatch.setattr(llm, "complete", broken)
    results = {r["id"]: r for r in rubric.evaluate(LESSON, ctx)}
    assert results["claims_grounded"]["execution_error"] and results["flow_coherent"]["execution_error"]
    assert len(calls) == 1  # the second judge call is not even tried


def test_empty_draft_is_never_sent_to_the_judge(ctx, monkeypatch):
    def must_not_be_called(*args, **kwargs):
        raise AssertionError("judge was called")

    monkeypatch.setattr(llm, "complete", must_not_be_called)
    results = rubric.evaluate("  \n", ctx)
    assert [r["id"] for r in results] == ["draft_nonempty"] and not results[0]["passed"]


# ---------------------------------------------------------------- claims_grounded
def test_supported_verdict_without_real_sheet_quote_counts_as_unsupported(ctx, monkeypatch):
    r = ground(ctx, monkeypatch, verdict(sheet_quote="RAG is always 100 percent right"))
    assert not r["passed"] and "not in the fact sheet" in r["reason"]


def test_supported_verdict_with_real_sheet_quote_passes(ctx, monkeypatch):
    assert ground(ctx, monkeypatch, verdict())["passed"]


def test_contradicted_claim_fails_and_quotes_the_lesson_sentence(ctx, monkeypatch):
    r = ground(ctx, monkeypatch, verdict(verdict="contradicted", sheet_quote="", reason="the sheet says no"))
    assert not r["passed"] and r["evidence"] == "RAG finds facts first." and "the sheet says no" in r["reason"]


def test_verdict_for_a_sentence_that_does_not_exist_is_ignored(ctx, monkeypatch):
    r = ground(ctx, monkeypatch, verdict(1), verdict(n=99, verdict="unsupported"))
    assert r["passed"] and r["claims_checked"] == 1


def test_sentences_marked_not_a_fact_are_not_checked_against_the_sheet(ctx, monkeypatch):
    r = ground(ctx, monkeypatch, verdict(1), verdict(n=2, verdict="not_a_fact"))
    assert r["passed"] and r["claims_checked"] == 1 and r["sentences_without_verdict"] == 1


def test_no_factual_claims_is_a_fail(ctx, monkeypatch):
    assert not ground(ctx, monkeypatch)["passed"]
    assert not ground(ctx, monkeypatch, verdict(verdict="not_a_fact"))["passed"]


def test_judge_sees_numbered_sentences_not_headings(ctx, monkeypatch):
    seen = {}
    monkeypatch.setattr(llm, "complete", lambda settings, role, task, system, user, json_mode=False: seen.update(user=user) or "{}")
    J.judge_grounding(LESSON, ctx)
    assert "[1] RAG finds facts first." in seen["user"] and "[3] RAG does not train the LLM again." in seen["user"]
    assert "What is X?" not in seen["user"]


# ---------------------------------------------------------------- key points
def test_coverage_needs_quote_from_lesson(ctx, monkeypatch):
    pts = [{"id": k["id"], "covered": True, "quotes": ["made up quote not in lesson"]} for k in ctx.key_points]
    r = review(ctx, monkeypatch, key_points=pts)["key_points_covered"]
    assert not r["passed"] and len(r["missing"]) == len(ctx.key_points)


def test_coverage_accepts_multiple_exact_quotes_per_point(ctx, monkeypatch):
    ctx.key_points = [{"id": "kp_compound", "text": "Find facts, then write an answer."}]
    pts = [{"id": "kp_compound", "covered": True, "quotes": ["RAG finds facts first.", "Then the LLM writes the answer."]}]
    assert review(ctx, monkeypatch, key_points=pts)["key_points_covered"]["passed"]


# ---------------------------------------------------------------- example
EXAMPLE_OK = {
    "has_everyday_analogy": {"ok": True, "quote": "RAG finds facts first."},
    "has_worked_example": {"ok": True, "quote": "Then the LLM writes the answer."},
    "example_is_correct": {"ok": True, "reason": "x"},
}


def test_example_passes_when_all_three_answers_are_good(ctx, monkeypatch):
    assert review(ctx, monkeypatch, example=EXAMPLE_OK)["teaches_by_example"]["passed"]


def test_example_fails_when_quote_is_not_in_lesson_or_example_is_wrong(ctx, monkeypatch):
    bad = {**EXAMPLE_OK, "has_everyday_analogy": {"ok": True, "quote": "an invented analogy sentence"},
           "example_is_correct": {"ok": False, "reason": "wrong step"}}
    r = review(ctx, monkeypatch, example=bad)["teaches_by_example"]
    assert not r["passed"] and "no everyday analogy" in r["reason"] and "wrong step" in r["reason"]


# ---------------------------------------------------------------- flow
def test_flow_complaint_with_fake_quote_is_dropped(ctx, monkeypatch):
    flow = {"ok": False, "problem_quote": "words that do not exist in the lesson", "reason": "bad"}
    assert review(ctx, monkeypatch, flow=flow)["flow_coherent"]["passed"]


def test_flow_complaint_with_real_quote_fails(ctx, monkeypatch):
    flow = {"ok": False, "problem_quote": "Then the LLM writes the answer.", "reason": "LLM not explained"}
    r = review(ctx, monkeypatch, flow=flow)["flow_coherent"]
    assert not r["passed"] and r["verified"]


# ---------------------------------------------------------------- unexplained terms
def terms(ctx, monkeypatch, lesson, *items):
    monkeypatch.setattr(llm, "complete", fake({"review": json.dumps({"unexplained_terms": list(items)})}))
    return J.judge_review(lesson, ctx)["no_unexplained_terms"]


def test_unexplained_terms_unverifiable_terms_are_ignored(ctx, monkeypatch):
    r = terms(ctx, monkeypatch, LESSON, {"term": "HNSW", "quote": "HNSW graphs are used here", "reason": "?"})
    assert r["passed"]


def test_unexplained_terms_defined_next_sentence_are_ignored(ctx, monkeypatch):
    lesson = "A prompt is used here. A prompt is the text sent to the LLM."
    assert terms(ctx, monkeypatch, lesson, {"term": "prompt", "quote": "A prompt is used here.", "reason": "?"})["passed"]


def test_unexplained_term_with_brackets_is_ignored_when_the_short_form_is_defined(ctx, monkeypatch):
    lesson = "We use a large language model (LLM) here. An LLM is a program that reads and writes text."
    item = {"term": "large language model (LLM)", "quote": "We use a large language model (LLM) here.", "reason": "?"}
    assert terms(ctx, monkeypatch, lesson, item)["passed"]


def test_unexplained_terms_still_fails_for_undefined_term(ctx, monkeypatch):
    lesson = "HNSW graphs speed up this search."
    r = terms(ctx, monkeypatch, lesson, {"term": "HNSW", "quote": lesson, "reason": "not defined"})
    assert not r["passed"] and r["terms"] == ["HNSW"]


def test_judge_is_configured_for_repeatable_answers(mock_settings):
    assert mock_settings.judge_temperature == 0.0
