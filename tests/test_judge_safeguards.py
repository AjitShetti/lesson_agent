"""The LLM judge can be wrong. These tests prove the safe-guards around it work."""
import json

from conftest import read

from lesson_agent import llm, rubric
from lesson_agent.checks import llm_judge as J

LESSON = "# T\n\n## What is X?\n\nRAG finds facts first. Then the LLM writes the answer. RAG does not train the LLM again.\n"


def fake(replies):
    """replies: dict task -> str or callable(user) -> str"""
    def _complete(settings, role, task, system, user, json_mode=False):
        r = replies.get(task, "not json")
        return r(user) if callable(r) else r
    return _complete


def test_invalid_json_twice_fails_closed(ctx, monkeypatch):
    monkeypatch.setattr(llm, "complete", fake({"extract_claims": "not json at all"}))
    results = rubric.evaluate(LESSON, ctx)
    r = next(x for x in results if x["id"] == "claims_grounded")
    assert not r["passed"] and "invalid JSON" in r["reason"]


def test_supported_verdict_without_real_sheet_quote_counts_as_unsupported(ctx, monkeypatch):
    claims = {"claims": [{"id": "c1", "quote": "RAG finds facts first.", "type": "fact"}]}
    verdicts = {"verdicts": [{"id": "c1", "verdict": "supported", "sheet_quote": "RAG is always 100 percent right", "reason": "x"}]}
    monkeypatch.setattr(llm, "complete", fake({"extract_claims": json.dumps(claims), "verify_claims": json.dumps(verdicts)}))
    r = J.claims_grounded(LESSON, ctx, {})
    assert not r["passed"] and "not in the fact sheet" in r["reason"]


def test_supported_verdict_with_real_sheet_quote_passes(ctx, monkeypatch):
    claims = {"claims": [{"id": "c1", "quote": "RAG finds facts first.", "type": "fact"}]}
    real = "RAG stands for Retrieval-Augmented Generation."
    verdicts = {"verdicts": [{"id": "c1", "verdict": "supported", "sheet_quote": real, "reason": "x"}]}
    monkeypatch.setattr(llm, "complete", fake({"extract_claims": json.dumps(claims), "verify_claims": json.dumps(verdicts)}))
    assert J.claims_grounded(LESSON, ctx, {})["passed"]


def test_claim_quote_not_in_lesson_is_dropped(ctx, monkeypatch):
    claims = {"claims": [
        {"id": "c1", "quote": "RAG finds facts first.", "type": "fact"},
        {"id": "c2", "quote": "This sentence is not in the lesson at all.", "type": "fact"},
    ]}
    real = "RAG stands for Retrieval-Augmented Generation."
    verdicts = {"verdicts": [{"id": "c1", "verdict": "supported", "sheet_quote": real, "reason": "x"}]}
    monkeypatch.setattr(llm, "complete", fake({"extract_claims": json.dumps(claims), "verify_claims": json.dumps(verdicts)}))
    r = J.claims_grounded(LESSON, ctx, {})
    assert r["passed"] and r["dropped_claims"] == 1


def test_missing_verdict_is_a_fail(ctx, monkeypatch):
    claims = {"claims": [{"id": "c1", "quote": "RAG finds facts first.", "type": "fact"}]}
    monkeypatch.setattr(llm, "complete", fake({"extract_claims": json.dumps(claims), "verify_claims": json.dumps({"verdicts": []})}))
    assert not J.claims_grounded(LESSON, ctx, {})["passed"]


def test_missing_claim_verdicts_are_retried_in_smaller_request(ctx, monkeypatch):
    claims = {"claims": [
        {"id": "c1", "quote": "RAG finds facts first.", "type": "fact"},
        {"id": "c2", "quote": "Then the LLM writes the answer.", "type": "fact"},
    ]}
    real = "RAG is a method where a system first finds relevant information from an outside source, and then gives that information to a large language model (LLM) to help it write an answer."
    calls = []

    def reply(user):
        calls.append(user)
        if len(calls) == 1:
            verdicts = [{"id": "c1", "verdict": "supported", "sheet_quote": real, "reason": "same meaning"}]
        else:
            verdicts = [{"id": "c2", "verdict": "supported", "sheet_quote": real, "reason": "same meaning"}]
        return json.dumps({"verdicts": verdicts})

    monkeypatch.setattr(llm, "complete", fake({"extract_claims": json.dumps(claims), "verify_claims": reply}))
    result = J.claims_grounded(LESSON, ctx, {"batch_size": 2})
    assert result["passed"]
    assert len(calls) == 2


def test_flow_complaint_with_fake_quote_is_dropped(ctx, monkeypatch):
    reply = json.dumps({"ok": False, "problem_quote": "words that do not exist in the lesson", "reason": "bad"})
    monkeypatch.setattr(llm, "complete", fake({"flow": reply}))
    assert J.flow_coherent(LESSON, ctx, {})["passed"]


def test_flow_complaint_with_real_quote_fails(ctx, monkeypatch):
    reply = json.dumps({"ok": False, "problem_quote": "Then the LLM writes the answer.", "reason": "LLM not explained"})
    monkeypatch.setattr(llm, "complete", fake({"flow": reply}))
    r = J.flow_coherent(LESSON, ctx, {})
    assert not r["passed"] and r["verified"]


def test_unexplained_terms_unverifiable_terms_are_ignored(ctx, monkeypatch):
    reply = json.dumps({"terms": [{"term": "HNSW", "quote": "HNSW graphs are used here", "reason": "?"}]})
    monkeypatch.setattr(llm, "complete", fake({"unexplained_terms": reply}))
    assert J.no_unexplained_terms(LESSON, ctx, {})["passed"]


def test_unexplained_terms_defined_next_sentence_are_ignored(ctx, monkeypatch):
    lesson = "A prompt is used here. A prompt is the text sent to the LLM."
    reply = json.dumps({"terms": [{
        "term": "prompt", "quote": "A prompt is used here.",
        "definition_quote": "A prompt is the text sent to the LLM.", "reason": "?",
    }]})
    monkeypatch.setattr(llm, "complete", fake({"unexplained_terms": reply}))
    assert J.no_unexplained_terms(lesson, ctx, {})["passed"]


def test_unexplained_terms_still_fails_for_undefined_term(ctx, monkeypatch):
    lesson = "HNSW graphs speed up this search."
    reply = json.dumps({"terms": [{"term": "HNSW", "quote": lesson, "reason": "not defined"}]})
    monkeypatch.setattr(llm, "complete", fake({"unexplained_terms": reply}))
    assert not J.no_unexplained_terms(lesson, ctx, {})["passed"]


def test_coverage_needs_quote_from_lesson(ctx, monkeypatch):
    pts = [{"id": k["id"], "covered": True, "quote": "made up quote not in lesson"} for k in ctx.key_points]
    monkeypatch.setattr(llm, "complete", fake({"coverage": json.dumps({"points": pts})}))
    r = J.key_points_covered(LESSON, ctx, {})
    assert not r["passed"] and len(r["missing"]) == len(ctx.key_points)


def test_coverage_accepts_multiple_exact_quotes_per_point(ctx, monkeypatch):
    ctx.key_points = [{"id": "kp_compound", "text": "Find facts, then write an answer."}]
    pts = [{"id": "kp_compound", "covered": True, "quotes": [
        "RAG finds facts first.", "Then the LLM writes the answer."
    ]}]
    monkeypatch.setattr(llm, "complete", fake({"coverage": json.dumps({"points": pts})}))
    r = J.key_points_covered(LESSON, ctx, {})
    assert r["passed"]


def test_json_in_code_fence_is_parsed(ctx):
    assert llm.parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert llm.parse_json('Here you go: {"a": 1} Thanks') == {"a": 1}


def test_judge_is_configured_for_repeatable_answers(mock_settings):
    assert mock_settings.judge_temperature == 0.0
