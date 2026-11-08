import json
from dataclasses import replace
from pathlib import Path

from lesson_agent import graph


def lines(run_dir):
    return [json.loads(x) for x in (Path(run_dir) / "rejection_log.jsonl").read_text(encoding="utf-8").splitlines()]


def test_flawed_then_good_passes_on_retry(mock_settings):
    out = graph.run("Introduction to RAG", mock_settings)
    assert out["status"] == "pass" and len(out["attempts"]) == 2 and out["best_attempt"] == 1
    recs = lines(out["run_dir"])
    assert recs[0]["passed"] is False and recs[1]["passed"] is True
    assert {"sentence_length", "no_idioms", "claims_grounded"} <= {c["id"] for c in recs[0]["failed_checks"]}


def test_good_writer_ships_first_attempt(mock_settings):
    s = replace(mock_settings, mock_writer_mode="good")
    out = graph.run("Introduction to RAG", s)
    assert out["status"] == "pass" and len(out["attempts"]) == 1


def test_injected_error_is_caught_by_the_grounding_check(mock_settings):
    s = replace(mock_settings, mock_writer_mode="good")
    out = graph.run("Introduction to RAG", s, inject_error=True)
    first = out["attempts"][0]
    failed = [r["id"] for r in first["results"] if not r["passed"]]
    assert failed == ["claims_grounded"]  # only the grounding check, because the false line is short and simple
    assert first["injected_error"] in first["lesson"]
    assert out["status"] == "pass" and len(out["attempts"]) == 2
    assert first["injected_error"] not in out["final_lesson"]


def test_loop_stops_after_max_retries_and_flags_human_review(mock_settings):
    s = replace(mock_settings, mock_writer_mode="always_bad")
    out = graph.run("Introduction to RAG", s)
    assert len(out["attempts"]) == 3  # 1 try + 2 retries
    assert out["status"] == "needs_human_review"
    assert (Path(out["run_dir"]) / "NEEDS_HUMAN_REVIEW.md").exists()
    assert (Path(out["run_dir"]) / "final_lesson.md").exists()  # best attempt still ships, with reasons


def test_max_retries_is_respected(mock_settings):
    s = replace(mock_settings, mock_writer_mode="always_bad", max_retries=1)
    assert len(graph.run("t", s)["attempts"]) == 2
    s0 = replace(mock_settings, mock_writer_mode="always_bad", max_retries=0)
    assert len(graph.run("t", s0)["attempts"]) == 1


def test_best_attempt_has_fewest_fails_not_just_the_last(mock_settings, monkeypatch):
    from lesson_agent import generator
    good = (Path(__file__).resolve().parent.parent / "examples" / "good_lesson.md").read_text(encoding="utf-8")
    bad = (Path(__file__).resolve().parent.parent / "examples" / "bad_lesson.md").read_text(encoding="utf-8")
    drafts = iter([good.replace("It gives the AI the right facts at the right time.",
                                "It gives the AI the right facts at exactly the right time before it writes any answer for the user who asked."),
                   bad, bad])
    monkeypatch.setattr(generator, "write_lesson", lambda *a, **k: (next(drafts), "x"))
    out = graph.run("t", mock_settings)
    assert out["status"] == "needs_human_review"
    assert out["best_attempt"] == 0  # attempt 0 had 1 fail; the later ones had many


def test_nonempty_attempt_beats_empty_retry(mock_settings, monkeypatch):
    from lesson_agent import generator
    bad = (Path(__file__).resolve().parent.parent / "examples" / "bad_lesson.md").read_text(encoding="utf-8")
    drafts = iter([bad, "", ""])
    monkeypatch.setattr(generator, "write_lesson", lambda *a, **k: (next(drafts), ""))
    out = graph.run("t", mock_settings)
    assert out["status"] == "needs_human_review"
    assert out["best_attempt"] == 0
    assert out["final_lesson"].strip() == bad.strip()


def test_all_empty_attempts_write_clear_diagnostic(mock_settings, monkeypatch):
    from lesson_agent import generator
    monkeypatch.setattr(generator, "write_lesson", lambda *a, **k: ("", "empty response"))
    out = graph.run("t", mock_settings)
    assert out["status"] == "needs_human_review"
    assert out["best_attempt"] is None
    assert "No lesson generated" in out["final_lesson"]
    recs = lines(out["run_dir"])
    assert all([c["id"] for c in r["failed_checks"]] == ["draft_nonempty"] for r in recs)


def test_rejection_log_records_feedback_diff_and_summary(mock_settings):
    out = graph.run("Introduction to RAG", mock_settings)
    r1 = lines(out["run_dir"])[1]
    assert r1["feedback_received"], "retry must record the feedback it received"
    assert r1["diff_from_previous"] and r1["diff_stats"]["lines_removed"] > 0
    assert r1["writer_change_summary"]
    md = (Path(out["run_dir"]) / "rejection_log.md").read_text(encoding="utf-8")
    assert "What really changed" in md


def test_memory_rules_reach_the_writer(mock_settings, monkeypatch):
    from lesson_agent import generator
    seen = {}

    def spy(settings, topic, ctx, memory_rules, previous=None, feedback=None):
        seen.setdefault("rules", memory_rules)
        return (Path(__file__).resolve().parent.parent / "examples" / "good_lesson.md").read_text(encoding="utf-8"), ""

    graph.run("t", mock_settings)  # first run fills memory (flawed draft fails 3 checks)
    monkeypatch.setattr(generator, "write_lesson", spy)
    graph.run("t", mock_settings)
    assert len(seen["rules"]) == 3 and any("15 words" in r for r in seen["rules"])
    seen.clear()
    graph.run("t", mock_settings, use_memory=False)
    assert seen["rules"] == []
