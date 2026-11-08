"""Offline fake models. They let you test the PLUMBING (graph, retry, logs, memory) without API keys.

IMPORTANT: this is NOT a quality test. The mock judge uses simple rules.
Real quality testing needs real models (see scripts/judge_reliability.py).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import text_utils as T

_FALSE_PATTERNS = [
    r"\bretrains?\b", r"\btrains? the (llm|model) (on|each|every)", r"for ever", r"\bforever\b",
    r"(remove|removes|removed|removes? all|completely removed)\b.*\bhallucinations?\b",
    r"always correct", r"never (make|makes) mistakes?", r"\b100%",
]
_NEGATION = re.compile(r"\b(does not|do not|cannot|can still|not)\b", re.I)


def _tag(user: str, name: str) -> str:
    m = re.search(rf"<{name}>\n?(.*?)\n?</{name}>", user, flags=re.S)
    return m.group(1) if m else ""


def respond(settings, role: str, task: str, system: str, user: str) -> str:
    if role == "writer":
        return _writer(settings, user)
    return {"ground": _ground, "review": _review}[task](settings, user)


# ------------------------------------------------------------------ writer
def _writer(settings, user: str) -> str:
    ex = Path(settings.examples_dir)
    good = (ex / "good_lesson.md").read_text(encoding="utf-8")
    flawed = (ex / "flawed_draft.md").read_text(encoding="utf-8")
    bad = (ex / "bad_lesson.md").read_text(encoding="utf-8")
    is_retry = "<previous_lesson>" in user
    mode = settings.mock_writer_mode
    if mode == "always_bad":
        return bad + ("\n---CHANGES---\n- (mock) tried again but changed nothing useful" if is_retry else "")
    if mode == "good":
        return good
    if not is_retry:
        return flawed
    return good + (
        "\n---CHANGES---\n"
        "- Split the very long sentence into two short ones.\n"
        "- Removed the idiom.\n"
        "- Replaced the wrong claim about retraining with the correct fact."
    )


# ------------------------------------------------------------------ judge
def _best_sheet_line(sentence: str, sheet: str) -> str:
    sw = set(re.findall(r"[a-z]{4,}", sentence.lower()))
    best, score = "", -1
    for line in sheet.splitlines():
        line = line.lstrip("- ").strip()
        if len(line) < 12:
            continue
        sc = len(sw & set(re.findall(r"[a-z]{4,}", line.lower())))
        if sc > score:
            best, score = line, sc
    return best


def _ground(settings, user: str) -> str:
    """Judge call 1. Known-false patterns are 'contradicted'; analogy and story sentences are not facts."""
    sheet = _tag(user, "fact_sheet")
    verdicts = []
    for line in _tag(user, "lesson_sentences").splitlines():
        m = re.match(r"\[(\d+)\] (.*)", line)
        if not m:
            continue
        n, s = int(m.group(1)), m.group(2)
        if T.count_words(s) < 6 or s.startswith("Think of") or "Meena" in s or '"' in s or "helpbot" in s.lower():
            verdicts.append({"n": n, "verdict": "not_a_fact"})
        elif any(re.search(p, s, re.I) for p in _FALSE_PATTERNS) and not _NEGATION.search(s):
            verdicts.append({"n": n, "verdict": "contradicted",
                             "reason": "The fact sheet says RAG does not retrain the LLM and does not remove all mistakes."})
        else:
            verdicts.append({"n": n, "verdict": "supported", "sheet_quote": _best_sheet_line(s, sheet)})
    return json.dumps({"verdicts": verdicts})


def _review(settings, user: str) -> str:
    """Judge call 2. Key points by keyword match; the example needs 'Think of ...' and 'Meena'."""
    lesson = _tag(user, "lesson")
    low = lesson.lower()
    sents = T.sentences(lesson)
    keywords = {k["id"]: k.get("mock_keywords", []) for k in json.loads(
        (Path(settings.data_dir) / "key_points.json").read_text(encoding="utf-8"))["key_points"]}
    points = []
    for k in json.loads(_tag(user, "key_points")):
        kw = keywords.get(k["id"], [])
        hit = [w for w in kw if w in low]
        quote = next((s for s in sents if hit and hit[0] in s.lower()), sents[0] if sents else "")
        points.append({"id": k["id"], "covered": len(hit) >= max(1, len(kw) // 2), "quotes": [quote]})
    analogy = next((s for s in sents if s.startswith("Think of")), "")
    start = next((s for s in sents if "Meena" in s), "")
    return json.dumps({
        "key_points": points,
        "example": {
            "has_everyday_analogy": {"ok": bool(analogy), "quote": analogy},
            "has_worked_example": {"ok": bool(start), "quote": start},
            "example_is_correct": {"ok": bool(analogy and start), "reason": "(mock)"},
        },
        "flow": {"ok": True, "problem_quote": "", "reason": ""},
        "unexplained_terms": [],
    })
