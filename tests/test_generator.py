from lesson_agent import generator, llm


def test_empty_writer_reply_is_retried_once(mock_settings, ctx, monkeypatch):
    replies = iter(["---CHANGES---\n- nothing", "# A lesson\n\nRAG finds facts first."])
    calls = []

    def complete(*args, **kwargs):
        calls.append(args)
        return next(replies)

    monkeypatch.setattr(llm, "complete", complete)
    lesson, summary = generator.write_lesson(mock_settings, "RAG", ctx, [])
    assert lesson.startswith("# A lesson")
    assert "asked again" in summary
    assert len(calls) == 2


def test_split_output_preserves_empty_lesson_as_empty():
    lesson, summary = generator.split_output("---CHANGES---\n- Removed the bad line.")
    assert lesson == ""
    assert summary == "- Removed the bad line."
