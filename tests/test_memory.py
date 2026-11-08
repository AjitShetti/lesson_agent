from lesson_agent.memory import Memory


def attempt(*fails, all_ids=("a", "b", "c")):
    return {"results": [{"id": i, "passed": i not in fails} for i in all_ids]}


RUBRIC = {"checks": [{"id": i, "writer_rule": f"rule {i}"} for i in "abc"]}


def test_top_failures_and_rules(tmp_path):
    m = Memory(tmp_path / "m.db")
    m.record_run("r1", "t", True, [attempt("a", "b")], "pass")
    m.record_run("r2", "t", True, [attempt("a")], "pass")
    assert m.top_failures(n=2) == [("a", 2), ("b", 1)]
    assert m.rules(RUBRIC, n=1) == ["rule a"]


def test_old_failures_leave_the_window(tmp_path):
    m = Memory(tmp_path / "m.db")
    m.record_run("r1", "t", True, [attempt("a")], "pass")
    for i in range(2, 5):
        m.record_run(f"r{i}", "t", True, [attempt()], "pass")
    assert m.top_failures(window=3) == []  # the old failure is outside the last 3 runs
    assert m.top_failures(window=10) == [("a", 1)]


def test_only_first_attempt_failures_count_as_writer_mistakes(tmp_path):
    m = Memory(tmp_path / "m.db")
    m.record_run("r1", "t", True, [attempt(), attempt("b")], "pass")
    assert m.top_failures() == []


def test_health_flags_always_and_never_failing_checks(tmp_path):
    m = Memory(tmp_path / "m.db")
    for i in range(6):
        m.record_run(f"r{i}", "t", True, [attempt("a")], "pass")  # a always fails; b, c never fail
    flags = {f["check"]: f["flag"] for f in m.health(min_runs=5)}
    assert flags["a"] == "ALWAYS FAILS" and flags["b"] == "NEVER FAILS"
    assert Memory(tmp_path / "m2.db").health(min_runs=5) == []  # too few runs: no flags


def test_first_attempt_stats_split_by_memory(tmp_path):
    m = Memory(tmp_path / "m.db")
    m.record_run("r1", "t", False, [attempt("a")], "pass")
    m.record_run("r2", "t", True, [attempt()], "pass")
    assert m.first_attempt_stats(False)["first_attempt_pass_rate"] == 0.0
    assert m.first_attempt_stats(True)["first_attempt_pass_rate"] == 1.0
