"""Checks that can be MEASURED are done in plain Python, not by an LLM.

Why: an LLM cannot count words or syllables reliably. Code gives the same answer every time.
Every check returns the same shape: {"passed", "reason", "evidence", ...}.
"""
from __future__ import annotations

import re

from .. import text_utils as T


def _res(passed: bool, reason: str = "OK", evidence: str = "", **extra) -> dict:
    return {"passed": passed, "reason": reason, "evidence": evidence, **extra}


def draft_nonempty(lesson: str, ctx, params: dict) -> dict:
    """Reject empty writer responses before asking the judge to evaluate them."""
    body = "\n".join(T.body_lines(lesson))
    words = T.count_words(body)
    if words:
        return _res(True, f"Draft contains {words} body words.", words=words)
    return _res(False, "The writer returned no lesson text.", evidence="", words=0, verified=True)


def sentence_length(lesson: str, ctx, params: dict) -> dict:
    limit = params.get("max_words", 15)
    long_ones = [(T.count_words(s), s) for s in T.sentences(lesson) if T.count_words(s) > limit]
    if not long_ones:
        return _res(True, f"All sentences have {limit} words or fewer.")
    long_ones.sort(key=lambda x: -x[0])
    examples = "; ".join(f'"{T.shorten(s, 90)}" ({n} words)' for n, s in long_ones[:3])
    return _res(
        False,
        f"{len(long_ones)} sentence(s) have more than {limit} words. Split them. Worst: {examples}",
        evidence=T.shorten(long_ones[0][1], 200),
        count=len(long_ones),
        verified=True,
    )


def readability(lesson: str, ctx, params: dict) -> dict:
    floor = params.get("min_flesch", 60)
    score = T.flesch_reading_ease(lesson)
    if score >= floor:
        return _res(True, f"Flesch Reading Ease is {score:.0f} (needs {floor}+).", score=round(score, 1))
    return _res(
        False,
        f"Flesch Reading Ease is {score:.0f}. It must be {floor} or higher. Use shorter words and shorter sentences.",
        score=round(score, 1),
    )


def no_idioms(lesson: str, ctx, params: dict) -> dict:
    hits = []
    body = "\n".join(T.body_lines(lesson))
    for phrase in ctx.idioms:
        pat = r"(?<!\w)" + re.escape(phrase) + r"(?!\w)"
        if re.search(pat, body, flags=re.I):
            sent = next((x for x in T.sentences(lesson) if re.search(pat, x, flags=re.I)), phrase)
            hits.append((phrase, T.shorten(sent, 160)))
    if not hits:
        return _res(True, "No idioms or Latin short forms found.")
    listed = ", ".join(f'"{p}"' for p, _ in hits[:6])
    return _res(False, f"Found phrases that are hard for the learner: {listed}. Use plain words.", evidence=hits[0][1], verified=True)


# A definition must sit NEXT TO the term: "TERM stands for ...", "TERM is a ...", "TERM (...)", or "called TERM".
_AFTER = re.compile(
    r"^\s*(\(|,?\s*(?:which |that )?(?:means|mean|stands for|refers to|is|are)\b)", re.I
)
_BEFORE = re.compile(r"\b(called|known as|named)\s+(?:an?\s+|the\s+)?$", re.I)
# A next sentence that starts like this explains the sentence before it.
_RESTATE = re.compile(r"^(in simple words|in other words|this means|that means|it means)\b", re.I)


def term_regex(term: str, case_sensitive: bool = False) -> re.Pattern:
    return re.compile(r"(?<![\w-])" + re.escape(term) + r"(?:s|es)?(?![\w])", 0 if case_sensitive else re.I)


def _defines(sentence: str, rx: re.Pattern) -> bool:
    for m in rx.finditer(sentence):
        if _AFTER.match(sentence[m.end() : m.end() + 40]) or _BEFORE.search(sentence[max(0, m.start() - 25) : m.start()]):
            return True
    return False


def defined_nearby(sents: list[str], i: int, rx: re.Pattern) -> bool:
    """True if sentence `i` or the one after it puts a definition next to the term."""
    nxt = sents[i + 1] if i + 1 < len(sents) else ""
    return _defines(sents[i], rx) or _defines(nxt, rx) or bool(_RESTATE.match(nxt))


def jargon_defined(lesson: str, ctx, params: dict) -> dict:
    """Heuristic: a term needs a definition right next to it, in its first sentence or the next one.

    This checks STRUCTURE (a definition is placed next to first use). It cannot judge if the
    definition is good. The LLM check `no_unexplained_terms` covers meaning.
    """
    sents = T.sentences(lesson)
    problems = []
    for entry in ctx.jargon:
        rx = term_regex(entry["term"], entry.get("case_sensitive", False))
        idx = next((i for i, s in enumerate(sents) if rx.search(s)), None)
        if idx is not None and not defined_nearby(sents, idx, rx):  # idx None: term not used, nothing to define
            problems.append((entry["term"], sents[idx]))
    if not problems:
        return _res(True, "Every technical term is defined where it first appears.")
    names = ", ".join(f'"{t}"' for t, _ in problems)
    plain = {e["term"]: e["plain"] for e in ctx.jargon}
    examples = " ".join(f'"{t} is {plain[t]}."' for t, _ in problems[:4])
    return _res(
        False,
        f"No definition next to the first use of: {names}. Define each term in the same sentence or the next one, "
        f"in the form 'X is ...', 'X means ...', 'X (...)' or 'called X'. For example: {examples}",
        evidence=T.shorten(problems[0][1], 200),
        terms=[t for t, _ in problems],
        verified=True,
    )


def required_sections(lesson: str, ctx, params: dict) -> dict:
    order = params["order"]
    heads = [h.lower() for h in T.headings(lesson)]
    pos = -1
    missing = []
    for pat in order:
        found = next((i for i in range(pos + 1, len(heads)) if re.search(pat, heads[i])), None)
        if found is None:
            missing.append(pat.split("|")[0])
        else:
            pos = found
    if not missing:
        return _res(True, "All sections are present in the right order.")
    return _res(
        False,
        f"Missing or out-of-order sections: {', '.join(missing)}. Required order: {' → '.join(p.split('|')[0] for p in order)}.",
        evidence="Headings found: " + " | ".join(T.headings(lesson)),
        verified=True,
    )


def lesson_length(lesson: str, ctx, params: dict) -> dict:
    lo, hi = params.get("min_words", 400), params.get("max_words", 900)
    n = T.count_words("\n".join(T.body_lines(lesson)))
    if lo <= n <= hi:
        return _res(True, f"{n} words (allowed {lo}-{hi}).", words=n)
    return _res(False, f"The lesson has {n} words. It must have {lo} to {hi} words.", words=n)
