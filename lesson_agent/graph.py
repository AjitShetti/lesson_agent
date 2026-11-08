"""The agent loop, built with LangGraph.

    START -> prepare -> generate -> evaluate -> router --(all pass)-----------> finalize -> memory_update -> END
                           ^                       |
                           +----(fail, retries left)

Stop rule: at most `max_retries` retries (default 2). Then the best non-empty attempt is selected.
If it still fails, status = "needs_human_review" and the failure reasons ship with it.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from . import generator, logging_utils, rubric
from .llm import LLMError
from .memory import Memory


class State(TypedDict, total=False):
    run_id: str
    topic: str
    use_memory: bool
    inject_error: bool
    memory_rules: list
    retries_used: int
    lesson: str
    feedback: list  # failed checks of the last attempt (sent to the writer)
    attempts: list  # one dict per attempt: lesson, results, feedback_received, diff, ...
    final_lesson: str
    status: str
    best_attempt: int | None
    run_dir: str


def build_graph(settings, ctx):
    # ---------------------------------------------------------------- nodes
    def prepare(state: State) -> dict:
        rules: list[str] = []
        if state.get("use_memory", True):
            mem = Memory(settings.memory_db)
            rules = mem.rules(ctx.rubric, n=3, window=10)
            mem.close()
        return {"memory_rules": rules, "attempts": [], "retries_used": 0, "feedback": []}

    def generate(state: State) -> dict:
        attempts = list(state["attempts"])
        i = len(attempts)
        is_retry = i > 0
        prev = state.get("lesson") if is_retry else None
        generation_error = ""
        try:
            lesson, summary = generator.write_lesson(
                settings, state["topic"], ctx, state.get("memory_rules", []),
                previous=prev, feedback=state.get("feedback") if is_retry else None,
            )
        except LLMError as e:
            lesson, summary, generation_error = "", "", str(e)
        injected = None
        if state.get("inject_error") and i == 0 and lesson.strip():  # deliberate test error, first attempt only
            lesson, injected = generator.inject_error(lesson)
        diff, stats = ("", None)
        if is_retry:
            diff, stats = logging_utils.make_diff(prev, lesson)
        attempts.append({
            "lesson": lesson, "writer_summary": summary, "injected_error": injected,
            "memory_rules": state.get("memory_rules", []),
            "feedback_received": state.get("feedback", []) if is_retry else [],
            "generation_error": generation_error,
            "diff": diff, "diff_stats": stats,
        })
        return {"lesson": lesson, "attempts": attempts, "retries_used": i}

    def evaluate(state: State) -> dict:
        attempts = list(state["attempts"])
        results = rubric.evaluate(state["lesson"], ctx)
        attempts[-1] = {**attempts[-1], "results": results}
        return {"attempts": attempts, "feedback": rubric.failed(results)}

    def router(state: State) -> str:
        if any(a.get("generation_error") for a in state["attempts"]):
            return "finalize"
        if any(r.get("execution_error") for r in state["attempts"][-1].get("results", [])):
            return "finalize"
        if not state["feedback"]:
            return "finalize"
        if state["retries_used"] < settings.max_retries:
            return "generate"
        return "finalize"

    def finalize(state: State) -> dict:
        attempts = state["attempts"]
        n_fail = [len(rubric.failed(a["results"])) for a in attempts]
        nonempty = [i for i, attempt in enumerate(attempts) if attempt.get("lesson", "").strip()]
        if nonempty:
            # An empty model response must never beat a real draft, even if it has fewer check failures.
            best = min(nonempty, key=lambda i: (n_fail[i], -i))  # fewest fails; tie -> latest
            lesson = attempts[best]["lesson"]
            status = "pass" if n_fail[best] == 0 else "needs_human_review"
        else:
            best = None
            lesson = "# No lesson generated\n\nThe writer returned an empty response on every attempt. Rerun after checking the model configuration.\n"
            status = "needs_human_review"
        run_dir = Path(settings.output_dir) / state["run_id"]
        final = {"lesson": lesson, "status": status, "best_attempt": best}
        logging_utils.write_run_outputs(run_dir, state["run_id"], state["topic"], attempts, final)
        return {"final_lesson": lesson, "status": status, "best_attempt": best, "run_dir": str(run_dir)}

    def memory_update(state: State) -> dict:
        mem = Memory(settings.memory_db)
        mem.record_run(state["run_id"], state["topic"], state.get("use_memory", True), state["attempts"], state["status"])
        mem.close()
        return {}

    # ---------------------------------------------------------------- wiring
    g = StateGraph(State)
    g.add_node("prepare", prepare)
    g.add_node("generate", generate)
    g.add_node("evaluate", evaluate)
    g.add_node("finalize", finalize)
    g.add_node("memory_update", memory_update)
    g.add_edge(START, "prepare")
    g.add_edge("prepare", "generate")
    g.add_edge("generate", "evaluate")
    g.add_conditional_edges("evaluate", router, {"generate": "generate", "finalize": "finalize"})
    g.add_edge("finalize", "memory_update")
    g.add_edge("memory_update", END)
    return g.compile()


def new_run_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]


def run(topic: str, settings, *, use_memory: bool = True, inject_error: bool = False) -> dict[str, Any]:
    ctx = rubric.load_context(settings)
    app = build_graph(settings, ctx)
    init: State = {"run_id": new_run_id(), "topic": topic, "use_memory": use_memory, "inject_error": inject_error}
    return app.invoke(init, {"recursion_limit": 3 * (settings.max_retries + 2) + 10})
