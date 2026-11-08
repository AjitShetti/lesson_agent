"""All prompts live here, so they are easy to read, test, and improve.

The WRITER gets a general style guide. It does NOT get the exact numbers of the rubric
(for example "15 words"). This is on purpose: it stops the writer from just "writing to the test".
The numbers come back only as feedback after a fail, or as a learned rule from memory.
"""
from __future__ import annotations

import json

# ----------------------------------------------------------------------------- writer
WRITER_SYSTEM = """You are a teacher who writes beginner lessons.

Learner: {learner}

Style guide:
- Use short, simple sentences. One idea in each sentence.
- Use simple, common words. No idioms, no slang, no Latin short forms.
- The first time you use a technical term, explain it in plain words right there.
- Include one clear everyday analogy and one separate worked example that follows a question through the RAG steps.
- Use the open-book exam analogy from the fact sheet when it fits. Keep any worked-example facts clearly inside the example.
- At first use, write: "RAG stands for Retrieval-Augmented Generation. Retrieval means finding useful information for a question."
- At first use, write: "Indexing means preparing documents before questions arrive." Do not name indexing several sentences before its definition.
- Spell out AI as artificial intelligence and explain it at first use. Define a large language model before using LLM alone.
- Use ONLY the facts in <fact_sheet>. Do not add facts that are not in it.
- Write in Markdown with these sections, in this order:
  # <title>
  ## What is <topic>?
  ## Why do we need <topic>?
  ## How does <topic> work?
  ## Example: <short name>
  (optional) ## What <topic> can and cannot do
  ## Summary

Output format:
- Write only the lesson. Start with the "# " title line.
- On a RETRY only: after the lesson, write a line `---CHANGES---` and then 1 to 3 short bullets
  that say what you changed and why.
- On a RETRY, return the complete revised lesson first. Never return only the change bullets.
"""


def writer_user(topic, key_points, fact_sheet, memory_rules, previous=None, feedback=None, jargon=None) -> str:
    kp = "\n".join(f"- {k['text']}" for k in key_points)
    parts = [
        f"Topic: {topic}",
        "The lesson must cover these key points:\n" + kp,
        f"<fact_sheet>\n{fact_sheet}\n</fact_sheet>",
    ]
    if jargon:
        terms = "\n".join(f"- {item['term']}: {item['plain']}" for item in jargon)
        parts.append("Use these simple definitions at the first use of each term:\n" + terms)
    if memory_rules:
        parts.append(
            "Rules learned from past failures (follow them):\n" + "\n".join(f"- {r}" for r in memory_rules)
        )
    if previous is not None:
        fb = "\n".join(
            f"- [{f['id']}] {f['reason']}" + (f"\n  Evidence: \"{f['evidence']}\"" if f.get("evidence") else "")
            for f in (feedback or [])
        )
        parts.append(
            "This is a RETRY. The reviewer rejected the previous lesson.\n"
            f"<previous_lesson>\n{previous}\n</previous_lesson>\n"
            f"<reviewer_feedback>\n{fb}\n</reviewer_feedback>\n"
            "Fix every problem in the feedback. Keep the parts that were fine. "
            "Return the full new lesson, then ---CHANGES---."
        )
    return "\n\n".join(parts)


# ----------------------------------------------------------------------------- judge
JUDGE_SYSTEM = """You are a strict reviewer of learning content.
The target learner: {learner}
Rules:
- Answer ONLY with JSON that follows the schema in the task. No text outside the JSON.
- When you quote, copy the text EXACTLY as it appears. Never rewrite a quote.
- Judge only what is written. Do not use your own outside knowledge to excuse a problem.
- If you are not sure, choose the stricter answer."""


def ground(sentences: list[str], fact_sheet: str) -> str:
    """Judge call 1: one verdict for every lesson sentence, checked ONLY against the fact sheet.

    Sentences are numbered so the judge answers with a number, not a copy of the sentence.
    That keeps the reply short (a long lesson has about 100 sentences).
    """
    numbered = "\n".join(f"[{n}] {s}" for n, s in enumerate(sentences, 1))
    return f"""<fact_sheet>
{fact_sheet}
</fact_sheet>

<lesson_sentences>
{numbered}
</lesson_sentences>

Task: give exactly one verdict for EVERY numbered sentence. Choose one:
- "not_a_fact"   = an analogy, a made-up story or sample data, or a sentence that only organizes the lesson
                  (for example "This is the first problem." or "RAG also has limits.")
- "supported"    = a statement about what the topic is, how it works, why it is needed, or its good and bad points,
                  and the fact sheet says the same thing
- "contradicted" = a statement of that kind, and the fact sheet says the opposite
- "unsupported"  = a statement of that kind, and the fact sheet does not say it
Compare ONLY with the fact sheet. Do not use outside knowledge. A statement that is true in real life
but missing from the sheet is "unsupported".
For "supported" you MUST give "sheet_quote": a short piece (at most 15 words) copied exactly from the fact sheet.
For "contradicted" and "unsupported" you MUST give "reason" (at most 20 words).

Output JSON: {{"verdicts": [{{"n": 1, "verdict": "supported", "sheet_quote": "..."}}, {{"n": 2, "verdict": "not_a_fact"}}, {{"n": 3, "verdict": "unsupported", "reason": "..."}}]}}"""


def review(lesson: str, key_points: list[dict]) -> str:
    """Judge call 2: key points, example, flow and unexplained terms in one pass."""
    kp = json.dumps([{"id": k["id"], "text": k["text"]} for k in key_points], ensure_ascii=False, indent=1)
    return f"""<lesson>
{lesson}
</lesson>

<key_points>
{kp}
</key_points>

Task: review the lesson in four parts. Every quote must be copied exactly from the lesson.

1. "key_points": for each key point, check every part of its text. A point with several steps is covered only if the lesson teaches every step.
   If covered, give one or more exact quotes that together show all parts. If not covered, list the missing parts.
2. "example": answer three yes/no questions.
   - has_everyday_analogy: does the lesson compare the topic to something from daily life? Quote it.
   - has_worked_example: does the lesson follow one concrete question through the steps of the topic? Quote the start of it.
   - example_is_correct: do the analogy and the worked example match how the topic really works, with no wrong steps?
3. "flow": read the lesson from top to bottom as the learner. Does any sentence or section use an idea BEFORE the lesson explains it,
   or jump in a way that would confuse the learner? If yes, set "ok" to false and quote the sentence that causes the problem.
4. "unexplained_terms": list every technical word or phrase that the learner could not understand from this lesson alone.
   Include a term if the lesson never explains it, or explains it only AFTER first using it.
   Do not flag a term if the same sentence or the next sentence explains it in plain words. A short description of a process can explain its name.
   Do not flag a common word just because it can also be technical in another context.
   Do not flag familiar everyday analogy phrases when the nearby text explains the comparison in plain words.
   For each real problem, quote the sentence with the first use. If there are none, use an empty list.

Output JSON: {{
 "key_points": [{{"id": "kp_what", "covered": true, "quotes": ["..."], "missing_parts": []}}],
 "example": {{"has_everyday_analogy": {{"ok": true, "quote": "..."}},
              "has_worked_example": {{"ok": true, "quote": "..."}},
              "example_is_correct": {{"ok": true, "reason": "..."}}}},
 "flow": {{"ok": true, "problem_quote": "", "reason": ""}},
 "unexplained_terms": [{{"term": "...", "quote": "exact sentence with the first use", "reason": "..."}}]
}}"""
