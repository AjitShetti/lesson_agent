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
    handler = {
        "extract_claims": _extract_claims,
        "verify_claims": _verify_claims,
        "coverage": _coverage,
        "teaches_by_example": _example,
        "flow": _flow,
        "unexplained_terms": lambda s, u: json.dumps({"terms": []}),
    }[task]
    return handler(settings, user)


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
def _extract_claims(settings, user: str) -> str:
    lesson = _tag(user, "lesson")
    claims = []
    for i, s in enumerate(T.sentences(lesson), 1):
        if T.count_words(s) < 6:
            continue
        kind = "analogy" if s.startswith("Think of") else "example" if ("Meena" in s or '"' in s or "helpbot" in s.lower()) else "fact"
        claims.append({"id": f"c{i}", "quote": s, "type": kind})
    return json.dumps({"claims": claims})


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


def _verify_claims(settings, user: str) -> str:
    sheet = _tag(user, "fact_sheet")
    claims = json.loads(_tag(user, "claims"))
    verdicts = []
    for c in claims:
        q = c["quote"]
        false_hit = any(re.search(p, q, re.I) for p in _FALSE_PATTERNS) and not _NEGATION.search(q)
        if false_hit:
            verdicts.append({"id": c["id"], "verdict": "contradicted", "sheet_quote": "",
                             "reason": "The fact sheet says RAG does not retrain the LLM and does not remove all mistakes."})
        else:
            verdicts.append({"id": c["id"], "verdict": "supported", "sheet_quote": _best_sheet_line(q, sheet), "reason": "(mock)"})
    return json.dumps({"verdicts": verdicts})


def _coverage(settings, user: str) -> str:
    lesson = _tag(user, "lesson")
    low = lesson.lower()
    kps = json.loads(_tag(user, "key_points"))
    kw = {k["id"]: k.get("mock_keywords", []) for k in json.loads(
        (Path(settings.data_dir) / "key_points.json").read_text(encoding="utf-8"))["key_points"]}
    sents = T.sentences(lesson)
    out = []
    for k in kps:
        hit = [w for w in kw.get(k["id"], []) if w in low]
        ok = len(hit) >= max(1, len(kw.get(k["id"], [])) // 2)
        quote = next((s for s in sents if hit and hit[0] in s.lower()), sents[0] if sents else "")
        out.append({"id": k["id"], "covered": ok, "quote": quote, "reason": "(mock keyword match)"})
    return json.dumps({"points": out})


def _example(settings, user: str) -> str:
    lesson = _tag(user, "lesson")
    sents = T.sentences(lesson)
    analogy = next((s for s in sents if s.startswith("Think of")), "")
    start = next((s for s in sents if "Meena" in s), "")
    return json.dumps({
        "has_everyday_analogy": {"ok": bool(analogy), "quote": analogy},
        "has_worked_example": {"ok": bool(start), "quote": start},
        "example_is_correct": {"ok": bool(analogy and start), "reason": "(mock)"},
    })


def _flow(settings, user: str) -> str:
    return json.dumps({"ok": True, "problem_quote": "", "reason": ""})
