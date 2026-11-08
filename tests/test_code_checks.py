from conftest import read

from lesson_agent.checks import code_checks as C


def run(fn, text, ctx, **params):
    return fn(text, ctx, params)


def test_good_lesson_passes_every_code_check(ctx):
    good = read("good_lesson.md")
    for chk in ctx.rubric["checks"]:
        if chk["type"] == "code":
            fn = getattr(C, chk["id"])
            r = fn(good, ctx, chk["params"])
            assert r["passed"], f"{chk['id']}: {r['reason']}"


def test_bad_lesson_fails_the_expected_code_checks(ctx):
    bad = read("bad_lesson.md")
    expected_fail = {"sentence_length", "readability", "no_idioms", "jargon_defined", "lesson_length", "required_sections"}
    for chk in ctx.rubric["checks"]:
        if chk["id"] in expected_fail:
            r = getattr(C, chk["id"])(bad, ctx, chk["params"])
            assert not r["passed"], f"{chk['id']} should fail on the bad lesson"


def test_sentence_length_counts_words_exactly(ctx):
    ok = "## A\n\n" + " ".join(["word"] * 15) + "."
    too_long = "## A\n\n" + " ".join(["word"] * 16) + "."
    assert run(C.sentence_length, ok, ctx, max_words=15)["passed"]
    r = run(C.sentence_length, too_long, ctx, max_words=15)
    assert not r["passed"] and "16 words" in r["reason"]


def test_sentence_length_ignores_headings_and_splits_list_items(ctx):
    text = "## " + " ".join(["heading"] * 30) + "\n\n- One short item.\n- Another short item."
    assert run(C.sentence_length, text, ctx, max_words=15)["passed"]


def test_idiom_and_latin_short_forms_are_caught(ctx):
    assert not run(C.no_idioms, "It is a piece of cake.", ctx)["passed"]
    assert not run(C.no_idioms, "Use tools, e.g. a search box.", ctx)["passed"]
    assert run(C.no_idioms, "It is easy to learn.", ctx)["passed"]


def test_idiom_needs_whole_phrase(ctx):
    assert run(C.no_idioms, "The ballpoint pen is blue.", ctx)["passed"]  # 'ballpark' is not 'ballpoint'


def test_jargon_needs_definition_next_to_term(ctx):
    undefined = "We store each chunk in a database. It is fast."
    defined = "A chunk is a small piece of a document. We store it."
    called = "Each small piece is called a chunk. We store it."
    assert not C.jargon_defined(undefined, ctx, {})["passed"]
    assert C.jargon_defined(defined, ctx, {})["passed"]
    assert C.jargon_defined(called, ctx, {})["passed"]


def test_jargon_definition_in_next_sentence_is_accepted(ctx):
    text = "We use a prompt here. A prompt is the text we send."
    assert C.jargon_defined(text, ctx, {})["passed"]


def test_jargon_definition_far_away_is_rejected(ctx):
    text = "We use a prompt here. It is quick. Many people like it. A prompt is the text we send."
    assert not C.jargon_defined(text, ctx, {})["passed"]


def test_jargon_acronym_is_case_sensitive(ctx):
    assert C.jargon_defined("The rag on the table is old.", ctx, {})["passed"]  # 'rag' cloth is not RAG


def test_required_sections_order(ctx):
    order = ctx.rubric["checks"][-2]["params"]["order"] if False else ["what is", "why", "how", "example", "summary|recap"]
    right = "## What is X?\n## Why X?\n## How X works\n## Example: a\n## Summary"
    wrong = "## Why X?\n## What is X?\n## How X works\n## Example: a\n## Summary"
    assert C.required_sections(right, ctx, {"order": order})["passed"]
    assert not C.required_sections(wrong, ctx, {"order": order})["passed"]


def test_lesson_length_bounds(ctx):
    short = "word " * 100
    ok = ("word " * 10 + ".\n") * 50
    assert not C.lesson_length(short, ctx, {"min_words": 400, "max_words": 900})["passed"]
    assert C.lesson_length(ok, ctx, {"min_words": 400, "max_words": 900})["passed"]
