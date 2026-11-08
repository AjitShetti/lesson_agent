"""Checks that need MEANING are done by an LLM judge. Safe-guards:

1. Different model + different prompt from the writer, temperature 0, JSON only.
2. Claims are listed FIRST, then each is checked against the fact sheet (no "is it accurate?" in one shot).
3. "Supported" needs a word-for-word quote from the fact sheet. If the quote is not in the sheet, the claim counts as unsupported.
4. Every complaint needs a word-for-word quote from the lesson. A complaint we cannot find in the lesson is dropped
   (it is judge noise). We then fail only on evidence we can verify.
5. If the judge returns broken JSON twice, the check FAILS (fail closed). It never passes by accident.
"""
from __future__ import annotations

import re

from .. import llm, prompts
from .. import text_utils as T


class JudgeError(RuntimeError):
    pass


def _res(passed: bool, reason: str = "OK", evidence: str = "", **extra) -> dict:
    return {"passed": passed, "reason": reason, "evidence": evidence, **extra}


def _call_json(ctx, task: str, user: str) -> dict:
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


# ---------------------------------------------------------------- accurate & grounded
def claims_grounded(lesson: str, ctx, params: dict) -> dict:
    claims = _call_json(ctx, "extract_claims", prompts.extract_claims(lesson)).get("claims", [])
    if not isinstance(claims, list):
        claims = []
    claims = [dict(c) for c in claims if isinstance(c, dict)]
    for index, claim in enumerate(claims, 1):
        claim.setdefault("id", f"c{index}")
    dropped = [c for c in claims if not T.quote_in(c.get("quote", ""), lesson)]
    claims = [c for c in claims if c not in dropped]
    facts = [c for c in claims if c.get("type") == "fact"]
    if not facts:
        return _res(False, "The judge found no factual claims, so nothing could be checked. Treated as a fail.")
    batch_size = max(1, int(params.get("batch_size", 8)))
    by_id = {}
    for start in range(0, len(facts), batch_size):
        batch = facts[start : start + batch_size]
        data = _call_json(ctx, "verify_claims", prompts.verify_claims(ctx.fact_sheet, batch))
        batch_verdicts = data.get("verdicts", [])
        if not isinstance(batch_verdicts, list):
            batch_verdicts = []
        by_id.update({v.get("id"): v for v in batch_verdicts if isinstance(v, dict) and v.get("id")})

        # Large responses can omit IDs. Retry only the missing claims in a smaller request.
        missing = [c for c in batch if c["id"] not in by_id]
        if missing:
            retry = _call_json(ctx, "verify_claims", prompts.verify_claims(ctx.fact_sheet, missing))
            retry_verdicts = retry.get("verdicts", [])
            if isinstance(retry_verdicts, list):
                by_id.update({v.get("id"): v for v in retry_verdicts if isinstance(v, dict) and v.get("id")})
    bad = []
    for c in facts:
        v = by_id.get(c["id"])
        if v is None:
            bad.append((c["quote"], "no verdict from the judge after a targeted retry"))
        elif v.get("verdict") != "supported":
            bad.append((c["quote"], f"{v.get('verdict')}: {v.get('reason', '')}".strip()))
        elif not T.quote_in(v.get("sheet_quote", ""), ctx.fact_sheet):
            bad.append((c["quote"], "judge said supported but its quote is not in the fact sheet"))
    if not bad:
        return _res(True, f"All {len(facts)} factual claims are supported by the fact sheet.",
                    claims_checked=len(facts), dropped_claims=len(dropped))
    listed = " | ".join(f'"{T.shorten(q, 110)}" → {why}' for q, why in bad[:4])
    return _res(False, f"{len(bad)} of {len(facts)} factual claims are not supported by the fact sheet: {listed}",
                evidence=bad[0][0], verified=True, claims_checked=len(facts), dropped_claims=len(dropped))


# ---------------------------------------------------------------- key points
def key_points_covered(lesson: str, ctx, params: dict) -> dict:
    data = _call_json(ctx, "coverage", prompts.coverage(lesson, ctx.key_points))
    points = data.get("points", [])
    if not isinstance(points, list):
        points = []
    got = {p.get("id"): p for p in points if isinstance(p, dict) and p.get("id")}
    missing = []
    for k in ctx.key_points:
        p = got.get(k["id"])
        quotes = p.get("quotes", []) if isinstance(p, dict) else []
        if not isinstance(quotes, list):
            quotes = []
        if not quotes and isinstance(p, dict) and isinstance(p.get("quote"), str):
            quotes = [p["quote"]]  # accept the old single-quote response shape
        evidence_ok = bool(quotes) and all(T.quote_in(q, lesson) for q in quotes)
        if not p or not p.get("covered") or not evidence_ok:
            missing.append(k)
    if not missing:
        return _res(True, f"All {len(ctx.key_points)} key points are covered.")
    names = "; ".join(f"[{k['id']}] {T.shorten(k['text'], 90)}" for k in missing)
    return _res(False, f"{len(missing)} key point(s) are missing or not clearly taught: {names}",
                evidence=names, missing=[k["id"] for k in missing])


# ---------------------------------------------------------------- example
def teaches_by_example(lesson: str, ctx, params: dict) -> dict:
    d = _call_json(ctx, "teaches_by_example", prompts.teaches_by_example(lesson))
    problems = []
    for key, label in (("has_everyday_analogy", "no everyday analogy"), ("has_worked_example", "no worked example")):
        part = d.get(key, {})
        if not isinstance(part, dict) or not part.get("ok") or not T.quote_in(part.get("quote", ""), lesson):
            problems.append(label)
    ok_correct = d.get("example_is_correct", {})
    if not isinstance(ok_correct, dict) or not ok_correct.get("ok"):
        reason = ok_correct.get("reason", "") if isinstance(ok_correct, dict) else "invalid judge response"
        problems.append("example does not match how the topic works: " + str(reason))
    if not problems:
        return _res(True, "The lesson has an everyday analogy and a correct worked example.")
    return _res(False, "; ".join(problems))


# ---------------------------------------------------------------- flow
def flow_coherent(lesson: str, ctx, params: dict) -> dict:
    d = _call_json(ctx, "flow", prompts.flow(lesson))
    if d.get("ok", False):
        return _res(True, "The ideas build on each other in a clear order.")
    q = d.get("problem_quote", "")
    if q and not T.quote_in(q, lesson):  # complaint we cannot verify: judge noise
        return _res(True, "Judge complaint dropped: its quote is not in the lesson.", dropped=True)
    return _res(False, d.get("reason", "The flow is not clear."), evidence=q, verified=bool(q))


# ---------------------------------------------------------------- unexplained terms
def no_unexplained_terms(lesson: str, ctx, params: dict) -> dict:
    d = _call_json(ctx, "unexplained_terms", prompts.unexplained_terms(lesson))
    terms = d.get("terms", [])
    if not isinstance(terms, list):
        terms = []
    real = [
        t for t in terms
        if isinstance(t, dict)
        and isinstance(t.get("term"), str)
        and T.quote_in(t.get("quote", ""), lesson)
        and not _has_local_definition(lesson, t.get("term", ""), t.get("quote", ""))
    ]
    if not real:
        return _res(True, "The judge found no unexplained technical terms.")
    names = ", ".join(f'"{t["term"]}"' for t in real[:6])
    return _res(False, f"Terms the learner cannot understand from the lesson: {names}.",
                evidence=real[0]["quote"], verified=True, terms=[t["term"] for t in real])


_DEFINITION_CUE = r"(?:is|are|means|mean|stands for|refers to|is called)\b"


def _has_local_definition(lesson: str, term: str, first_quote: str) -> bool:
    """Filter judge complaints when a term is plainly defined at first use or next sentence."""
    if not term:
        return False
    sentences = T.sentences(lesson)
    idx = next((i for i, sentence in enumerate(sentences) if T.quote_in(first_quote, sentence)), None)
    variants = [term]
    variants.extend(re.findall(r"\(([^)]+)\)", term))
    base = re.sub(r"\s*\([^)]*\)", "", term).strip()
    if base and base not in variants:
        variants.append(base)
    if idx is None:
        idx = next((i for i, sentence in enumerate(sentences)
                    if any(re.search(rf"(?<!\w){re.escape(v.strip())}(?!\w)", sentence, re.I)
                           for v in variants if v.strip())), None)
    if idx is None:
        return False

    nearby = " ".join(sentences[idx : idx + 2])
    for variant in variants:
        escaped = re.escape(variant.strip())
        if not escaped:
            continue
        if re.search(rf"(?<!\w){escaped}(?!\w)\s+{_DEFINITION_CUE}", nearby, re.I):
            return True
        if re.search(rf"\b(?:called|known as|named)\s+(?:an?\s+|the\s+)?{escaped}(?!\w)", nearby, re.I):
            return True
    return False
