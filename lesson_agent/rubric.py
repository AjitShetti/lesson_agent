"""Load the rubric and run every check. Result shape is the same for code and LLM checks."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .checks import code_checks, llm_judge
from .checks.llm_judge import JudgeError
from .config import Settings
from .llm import LLMError

REGISTRY = {
    "draft_nonempty": code_checks.draft_nonempty,
    "sentence_length": code_checks.sentence_length,
    "readability": code_checks.readability,
    "no_idioms": code_checks.no_idioms,
    "jargon_defined": code_checks.jargon_defined,
    "required_sections": code_checks.required_sections,
    "lesson_length": code_checks.lesson_length,
    "claims_grounded": llm_judge.claims_grounded,
    "key_points_covered": llm_judge.key_points_covered,
    "teaches_by_example": llm_judge.teaches_by_example,
    "flow_coherent": llm_judge.flow_coherent,
    "no_unexplained_terms": llm_judge.no_unexplained_terms,
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


def evaluate(lesson: str, ctx: EvalContext) -> list[dict]:
    """Run all applicable checks; short-circuit empty drafts to avoid meaningless judge calls."""
    results = []
    for chk in ctx.rubric["checks"]:
        if chk["id"] != "draft_nonempty" and not lesson.strip():
            # An empty reply cannot be judged for meaning. Save calls and report the actual failure.
            continue
        fn = REGISTRY[chk["id"]]
        try:
            r = fn(lesson, ctx, chk.get("params", {}))
        except JudgeError as e:  # fail closed
            r = {"passed": False, "reason": f"Judge error (treated as fail): {e}", "evidence": ""}
        except LLMError as e:  # provider/configuration errors need a person, not another rewrite
            r = {"passed": False, "reason": f"Judge provider error: {e}", "evidence": "", "execution_error": True}
        r.update(id=chk["id"], dimension=chk["dimension"], type=chk["type"], question=chk["question"])
        results.append(r)
    return results


def failed(results: list[dict]) -> list[dict]:
    return [r for r in results if not r["passed"]]
