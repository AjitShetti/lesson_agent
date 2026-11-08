"""Checks that need MEANING are done by an LLM judge, in just TWO calls per attempt:

  call 1 "ground"  -> claims_grounded
  call 2 "review"  -> key_points_covered, teaches_by_example, flow_coherent, no_unexplained_terms

Two calls keep us inside free-tier daily limits (a full 3-attempt run needs about 6 judge calls).

Safe-guards (the judge is only trusted when its evidence can be checked by plain code):
1. Different vendor + prompt from the writer, temperature 0, JSON only.
2. The judge gives a verdict for every numbered sentence, one by one. Not one big "is it accurate?".
3. "Supported" needs a word-for-word quote from the fact sheet. If the quote is not in the sheet, the claim fails.
4. Verdicts must point at a real sentence number, and every complaint needs a word-for-word quote from the lesson.
   One we cannot find is dropped (judge noise). We fail only on evidence we can verify.
5. If the judge returns broken JSON twice, the checks FAIL (fail closed). They never pass by accident.
"""
from __future__ import annotations

import re

from .. import llm, prompts
from .. import text_utils as T
from . import code_checks


class JudgeError(RuntimeError):
    pass


def _res(passed: bool, reason: str = "OK", evidence: str = "", **extra) -> dict:
    return {"passed": passed, "reason": reason, "evidence": evidence, **extra}


def _list(x) -> list:
    return x if isinstance(x, list) else []


def _dict(x) -> dict:
    return x if isinstance(x, dict) else {}


def _call_json(ctx, task: str, user: str) -> dict:
    """Ask the judge for JSON. One more try if the reply is not valid JSON, then give up."""
    system = prompts.JUDGE_SYSTEM.format(learner=ctx.rubric["learner"])
    last_err = None
    for attempt in range(2):
        extra = "" if attempt == 0 else "\n\nYour last reply was not valid JSON. Reply with JSON only."
        raw = llm.complete(ctx.settings, "judge", task, system, user + extra, json_mode=True)
        try:
            data = llm.parse_json(raw)
            if isinstance(data, dict):
                return data
            last_err = "JSON root is not an object"
        except ValueError as e:
            last_err = str(e)
    raise JudgeError(f"judge returned invalid JSON for '{task}': {last_err}")


# ================================================================ call 1: accurate & grounded
def judge_grounding(lesson: str, ctx) -> dict[str, dict]:
    sents = T.sentences(lesson)
    data = _call_json(ctx, "ground", prompts.ground(sents, ctx.fact_sheet))
    verdicts = {}
    for v in _list(data.get("verdicts")):
        n = v.get("n") if isinstance(v, dict) else None
        if isinstance(n, int) and 1 <= n <= len(sents):  # safe-guard 4: only real sentence numbers count
            verdicts[n] = v
    facts = {n: v for n, v in verdicts.items() if v.get("verdict") != "not_a_fact"}
    if not facts:
        return {"claims_grounded": _res(False, "The judge found no factual claims, so nothing could be checked. Treated as a fail.")}
    bad = []
    for n, v in sorted(facts.items()):
        if v.get("verdict") != "supported":
            bad.append((sents[n - 1], f"{v.get('verdict')}: {v.get('reason', '')}".strip()))
        elif not T.quote_in(v.get("sheet_quote", ""), ctx.fact_sheet):  # safe-guard 3
            bad.append((sents[n - 1], "judge said supported but its quote is not in the fact sheet"))
    stats = {"claims_checked": len(facts), "sentences_without_verdict": len(sents) - len(verdicts)}
    if not bad:
        return {"claims_grounded": _res(True, f"All {len(facts)} factual claims are supported by the fact sheet.", **stats)}
    listed = " | ".join(f'"{T.shorten(q, 110)}" → {why}' for q, why in bad[:4])
    return {"claims_grounded": _res(
        False, f"{len(bad)} of {len(facts)} factual claims are not supported by the fact sheet: {listed}",
        evidence=bad[0][0], verified=True, **stats)}


# ================================================================ call 2: the four teaching checks
def judge_review(lesson: str, ctx) -> dict[str, dict]:
    data = _call_json(ctx, "review", prompts.review(lesson, ctx.key_points))
    return {
        "key_points_covered": _key_points(data, lesson, ctx),
        "teaches_by_example": _example(data, lesson),
        "flow_coherent": _flow(data, lesson),
        "no_unexplained_terms": _unexplained_terms(data, lesson),
    }


def _key_points(data: dict, lesson: str, ctx) -> dict:
    got = {p.get("id"): p for p in _list(data.get("key_points")) if isinstance(p, dict)}
    missing = []
    for k in ctx.key_points:
        p = got.get(k["id"], {})
        quotes = _list(p.get("quotes"))
        if not (p.get("covered") and quotes and all(T.quote_in(q, lesson) for q in quotes)):
            missing.append(k)
    if not missing:
        return _res(True, f"All {len(ctx.key_points)} key points are covered.")
    names = "; ".join(f"[{k['id']}] {T.shorten(k['text'], 90)}" for k in missing)
    return _res(False, f"{len(missing)} key point(s) are missing or not clearly taught: {names}",
                evidence=names, missing=[k["id"] for k in missing])


def _example(data: dict, lesson: str) -> dict:
    d = _dict(data.get("example"))
    problems = []
    for key, label in (("has_everyday_analogy", "no everyday analogy"), ("has_worked_example", "no worked example")):
        part = _dict(d.get(key))
        if not part.get("ok") or not T.quote_in(part.get("quote", ""), lesson):
            problems.append(label)
    correct = _dict(d.get("example_is_correct"))
    if not correct.get("ok"):
        problems.append("example does not match how the topic works: " + str(correct.get("reason", "invalid judge response")))
    if not problems:
        return _res(True, "The lesson has an everyday analogy and a correct worked example.")
    return _res(False, "; ".join(problems))


def _flow(data: dict, lesson: str) -> dict:
    d = _dict(data.get("flow"))
    if d.get("ok", False):
        return _res(True, "The ideas build on each other in a clear order.")
    quote = d.get("problem_quote", "")
    if quote and not T.quote_in(quote, lesson):  # complaint we cannot verify: judge noise
        return _res(True, "Judge complaint dropped: its quote is not in the lesson.", dropped=True)
    return _res(False, d.get("reason") or "The flow is not clear.", evidence=quote, verified=bool(quote))


def _unexplained_terms(data: dict, lesson: str) -> dict:
    sents = T.sentences(lesson)
    real = []
    for t in _list(data.get("unexplained_terms")):
        t = _dict(t)
        term, quote = t.get("term"), t.get("quote", "")
        if isinstance(term, str) and T.quote_in(quote, lesson) and not _defined_at_first_use(sents, term, quote):
            real.append(t)
    if not real:
        return _res(True, "The judge found no unexplained technical terms.")
    names = ", ".join(f'"{t["term"]}"' for t in real[:6])
    return _res(False, f"Terms the learner cannot understand from the lesson: {names}.",
                evidence=real[0]["quote"], verified=True, terms=[t["term"] for t in real])


def _defined_at_first_use(sents: list[str], term: str, quote: str) -> bool:
    """Drop a judge complaint when the plain code rule sees a definition next to the term.

    "large language model (LLM)" is tried as the full text, the part without brackets, and the part inside them.
    """
    names = {term, re.sub(r"\s*\([^)]*\)", "", term).strip(), *re.findall(r"\(([^)]+)\)", term)}
    regexes = [code_checks.term_regex(n.strip()) for n in names if n.strip()]
    i = next((n for n, s in enumerate(sents) if T.quote_in(quote, s)), None)  # sentence the judge quoted
    if i is None:  # quote spans several sentences: use the first sentence that mentions the term
        i = next((n for n, s in enumerate(sents) if any(rx.search(s) for rx in regexes)), None)
    return i is not None and any(code_checks.defined_nearby(sents, i, rx) for rx in regexes)


# The two judge calls, with the checks each one answers. rubric.evaluate runs them in this order.
CALLS = [
    (["claims_grounded"], judge_grounding),
    (["key_points_covered", "teaches_by_example", "flow_coherent", "no_unexplained_terms"], judge_review),
]
