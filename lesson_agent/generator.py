"""The writer. One prompt. On a retry it also gets the old lesson and the reviewer feedback."""
from __future__ import annotations

import re

from . import llm, prompts

CHANGES_MARK = "---CHANGES---"
INJECTED_FALSE_SENTENCE = "RAG retrains the model on your documents every time you ask a question."


def write_lesson(settings, topic, ctx, memory_rules, previous=None, feedback=None) -> tuple[str, str]:
    """Return (lesson_markdown, writer_change_summary)."""
    system = prompts.WRITER_SYSTEM.format(learner=ctx.rubric["learner"])
    user = prompts.writer_user(topic, ctx.key_points, ctx.fact_sheet, memory_rules, previous, feedback, ctx.jargon)
    for empty_retry in range(2):
        extra = ""
        if empty_retry:
            extra = (
                "\n\nYour previous response was empty or contained only change notes. "
                "Return the complete Markdown lesson now. Start with a # title and include every required section."
            )
        raw = llm.complete(settings, "writer", "write", system, user + extra)
        lesson, summary = split_output(raw)
        if lesson.strip():
            if empty_retry:
                summary = "\n".join(filter(None, [summary, "(writer had to be asked again after an empty reply)"]))
            return lesson, summary
    return "", "Writer returned an empty response twice."


def split_output(raw: str) -> tuple[str, str]:
    raw = raw.strip()
    raw = re.sub(r"^```(?:markdown|md)?\s*\n|\n```\s*$", "", raw)  # remove a code fence around the lesson
    lesson, _, changes = raw.partition(CHANGES_MARK)
    start = lesson.find("# ")
    lesson = lesson[start:] if start > 0 else lesson
    lesson = lesson.strip()
    return (lesson + "\n" if lesson else ""), changes.strip()


def inject_error(lesson: str) -> tuple[str, str]:
    """TEST MODE: put one false sentence into the 'How' section. Used to show the evaluator catches it."""
    lines = lesson.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"^##\s+how", line, flags=re.I):
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            # insert right after the first body line of the section
            lines[j + 1 : j + 1] = ["", INJECTED_FALSE_SENTENCE] if j + 1 <= len(lines) else [INJECTED_FALSE_SENTENCE]
            return "\n".join(lines) + "\n", INJECTED_FALSE_SENTENCE
    return lesson.rstrip() + "\n\n" + INJECTED_FALSE_SENTENCE + "\n", INJECTED_FALSE_SENTENCE
