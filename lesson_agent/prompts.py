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


def extract_claims(lesson: str) -> str:
    return f"""<lesson>
{lesson}
</lesson>

Task: list every statement in the lesson. For each one give:
- "id": c1, c2, ...
- "quote": the exact sentence from the lesson
- "type": one of
    "fact"    = a statement about what the topic is, how it works, why it is needed, or its good and bad points
    "analogy" = a comparison to daily life
    "example" = a made-up story, scenario, or sample data

Output JSON: {{"claims": [{{"id": "c1", "quote": "...", "type": "fact"}}]}}"""


def verify_claims(fact_sheet: str, claims: list[dict]) -> str:
    return f"""<fact_sheet>
{fact_sheet}
</fact_sheet>

<claims>
{json.dumps(claims, ensure_ascii=False, indent=1)}
</claims>

Task: for each claim, compare it ONLY with the fact sheet. Choose a verdict:
- "supported"    = the fact sheet says the same thing
- "contradicted" = the fact sheet says the opposite
- "unsupported"  = the fact sheet does not say it
For "supported" you MUST give "sheet_quote": text copied exactly from the fact sheet.
Do not use outside knowledge. A claim that is true in real life but missing from the sheet is "unsupported".
Return exactly one verdict for every input claim ID. Do not omit claims. If a claim cannot be checked, mark it "unsupported" and explain why.

Output JSON: {{"verdicts": [{{"id": "c1", "verdict": "supported", "sheet_quote": "...", "reason": "..."}}]}}"""


def coverage(lesson: str, key_points: list[dict]) -> str:
    kp = json.dumps([{"id": k["id"], "text": k["text"]} for k in key_points], ensure_ascii=False, indent=1)
    return f"""<lesson>
{lesson}
</lesson>

<key_points>
{kp}
</key_points>

Task: for each key point, check every part of its text. A point with several steps is covered only if the lesson teaches every step.
If covered, copy one or more exact lesson quotes that together show all parts. If not covered, list the missing parts.
Output JSON: {{"points": [{{"id": "kp_what", "covered": true, "quotes": ["...", "..."], "missing_parts": [], "reason": "..."}}]}}"""


def teaches_by_example(lesson: str) -> str:
    return f"""<lesson>
{lesson}
</lesson>

Task: answer three yes/no questions.
1. has_everyday_analogy: does the lesson compare the topic to something from daily life? Quote it.
2. has_worked_example: does the lesson follow one concrete question through the steps of the topic? Quote the start of it.
3. example_is_correct: do the analogy and the worked example match how the topic really works, with no wrong steps?

Output JSON: {{"has_everyday_analogy": {{"ok": true, "quote": "..."}},
"has_worked_example": {{"ok": true, "quote": "..."}},
"example_is_correct": {{"ok": true, "reason": "..."}}}}"""


def flow(lesson: str) -> str:
    return f"""<lesson>
{lesson}
</lesson>

Task: read the lesson from top to bottom as the learner. Does any sentence or section use an idea BEFORE the lesson explains it,
or jump in a way that would confuse the learner? If yes, copy the exact sentence that causes the problem.
Output JSON: {{"ok": true, "problem_quote": "", "reason": ""}}
Set "ok" to false if there is any such problem."""


def unexplained_terms(lesson: str) -> str:
    return f"""<lesson>
{lesson}
</lesson>

Task: list every technical word or phrase that the learner could not understand from this lesson alone.
Include a term if the lesson never explains it, or explains it only AFTER first using it.
Do not flag a term if the same sentence or the next sentence explains it in plain words. A short description of a process can explain its name.
Do not flag a common word just because it can also be technical in another context.
Do not flag familiar everyday analogy phrases when the nearby text explains the comparison in plain words.
For each real problem, quote the first-use sentence and the nearby definition you checked.
Output JSON: {{"terms": [{{"term": "...", "quote": "exact sentence with the first use", "definition_quote": "exact nearby definition or empty string", "reason": "..."}}]}}
If there are none, output {{"terms": []}}."""
