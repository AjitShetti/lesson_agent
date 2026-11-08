"""Small text helpers used by the code checks. No LLM here."""
from __future__ import annotations

import re

_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’\-]*")


def clean_inline(line: str) -> str:
    line = re.sub(r"^\s*([-*+]|\d+[.)])\s+", "", line)  # list markers
    line = re.sub(r"[*_`]+", "", line)  # emphasis / code marks
    return line.strip()


def body_lines(md: str):
    """Yield non-empty lines that are not headings."""
    for raw in md.splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        yield clean_inline(s)


def sentences(md: str) -> list[str]:
    """Split body text into sentences. Each list item is its own unit."""
    out: list[str] = []
    for line in body_lines(md):
        for part in re.split(r"(?<=[.!?])[\"”']?\s+", line):
            part = part.strip()
            if part:
                out.append(part)
    return out


def headings(md: str) -> list[str]:
    return [m.group(2).strip() for m in re.finditer(r"^(#{2,3})\s+(.*)$", md, flags=re.M)]


def words(text: str) -> list[str]:
    return _WORD.findall(text)


def count_words(text: str) -> int:
    return len(words(text))


def syllables(word: str) -> int:
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    if len(w) <= 3:
        return 1
    w = re.sub(r"(?:[^laeiouy]es|ed|[^laeiouy]e)$", "", w)
    w = re.sub(r"^y", "", w)
    return max(1, len(re.findall(r"[aeiouy]{1,2}", w)))


def flesch_reading_ease(md: str) -> float:
    sents = sentences(md)
    ws = [w for s in sents for w in words(s)]
    if not sents or not ws:
        return 0.0
    syl = sum(syllables(w) for w in ws)
    return 206.835 - 1.015 * (len(ws) / len(sents)) - 84.6 * (syl / len(ws))


def normalize(text: str) -> str:
    """Lowercase, remove markdown marks and quotes, collapse spaces. Used to verify quotes."""
    t = text.lower()
    t = re.sub(r"[*_`#>]+", "", t)
    t = t.replace("’", "'").replace("“", '"').replace("”", '"')
    t = re.sub(r"[\"']", "", t)
    t = re.sub(r"^\s*([-+]|\d+[.)])\s+", "", t, flags=re.M)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def quote_in(quote: str, source: str) -> bool:
    """True if `quote` appears (after normalizing) inside `source`."""
    q = normalize(quote or "")
    return len(q) >= 8 and q in normalize(source)


def shorten(text: str, n: int = 160) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= n else text[: n - 1] + "…"
