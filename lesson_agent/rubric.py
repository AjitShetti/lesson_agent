"""Load the rubric and run every check. Result shape is the same for code and LLM checks."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .checks import code_checks, llm_judge
from .checks.llm_judge import JudgeError
from .config import Settings
from .llm import LLMError

CODE_CHECKS = {
    "draft_nonempty": code_checks.draft_nonempty,
    "sentence_length": code_checks.sentence_length,
    "readability": code_checks.readability,
    "no_idioms": code_checks.no_idioms,
    "jargon_defined": code_checks.jargon_defined,
    "required_sections": code_checks.required_sections,
    "lesson_length": code_checks.lesson_length,
}


@dataclass
class EvalContext:
    settings: Settings
    rubric: dict
    fact_sheet: str
    key_points: list
    jargon: list
    idioms: list


def load_context(settings: Settings) -> EvalContext:
    d = Path(settings.data_dir)
    return EvalContext(
        settings=settings,
        rubric=json.loads((d / "rubric.json").read_text(encoding="utf-8")),
        fact_sheet=(d / "fact_sheet.md").read_text(encoding="utf-8"),
        key_points=json.loads((d / "key_points.json").read_text(encoding="utf-8"))["key_points"],
        jargon=json.loads((d / "jargon.json").read_text(encoding="utf-8"))["terms"],
        idioms=json.loads((d / "idioms.json").read_text(encoding="utf-8"))["phrases"],
    )


def _run_judge(lesson: str, ctx: EvalContext) -> dict[str, dict]:
    """Run the judge calls once each. Returns {check id: result}. A failed call fails ALL of its checks."""
    out: dict[str, dict] = {}
    provider_error = None
    for ids, call in llm_judge.CALLS:
        failure = None
        if provider_error:  # the provider is down or out of quota: do not call it again
            failure = {"passed": False, "reason": f"Judge provider error: {provider_error}", "evidence": "", "execution_error": True}
        else:
            try:
                out.update(call(lesson, ctx))
                continue
            except JudgeError as e:  # fail closed
                failure = {"passed": False, "reason": f"Judge error (treated as fail): {e}", "evidence": ""}
            except LLMError as e:  # provider/configuration errors need a person, not another rewrite
                provider_error = str(e)
                failure = {"passed": False, "reason": f"Judge provider error: {e}", "evidence": "", "execution_error": True}
        out.update({check_id: dict(failure) for check_id in ids})
    return out


def evaluate(lesson: str, ctx: EvalContext) -> list[dict]:
    """Run every check. An empty draft only gets `draft_nonempty` (nothing else can be judged)."""
    has_text = bool(lesson.strip())
    judged = _run_judge(lesson, ctx) if has_text else {}
    results = []
    for chk in ctx.rubric["checks"]:
        if chk["type"] == "code":
            if not has_text and chk["id"] != "draft_nonempty":
                continue
            r = CODE_CHECKS[chk["id"]](lesson, ctx, chk.get("params", {}))
        elif not has_text:
            continue
        else:
            r = judged[chk["id"]]  # KeyError here = the rubric lists an LLM check that no judge call answers
        r.update(id=chk["id"], dimension=chk["dimension"], type=chk["type"], question=chk["question"])
        results.append(r)
    return results


def failed(results: list[dict]) -> list[dict]:
    return [r for r in results if not r["passed"]]
