"""The tool that asks whether every field we publish reaches a page.

Ethan, 2026-09-09: *"we are using every single piece of data we have"*.
The FILE half came back clean. The FIELD half is `engine/feedaudit.py`,
and this is the test for the tool rather than for the answer — the answer
lives in build output, which is not in git and which a test must not read
(tests/test_backup_remote.py has the long version of why).

What matters about a tool like this is not that it finds things. It is
that a person believes it when it does. So the properties under test are
the ones that decide whether it gets ignored:

  * it does not report a field a page actually reads;
  * it does not report the inside of a map indexed by a variable, or a
    dict keyed by dates or team codes — those keys are DATA;
  * it separates "nobody reads this and it is full of numbers" from
    "nobody reads this and it is empty here", because only the first is
    reliably interesting;
  * it never exits nonzero, so it can never fail a deploy over a lead
    nobody has classified.

    python3 tests/test_feedaudit.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import feedaudit  # noqa: E402


def test_a_field_the_page_reads_is_not_reported():
    blob = 'renderThing(d.hit_prob); const x = row["stake_units"];'
    assert feedaudit._named("hit_prob", blob)
    assert feedaudit._named("stake_units", blob)


def test_a_comment_naming_a_field_is_not_a_reader():
    """THE HAZARD THAT MATTERS, and the first version of this test missed
    it: the fixture said "the closing line" with a space, so the token was
    never in the string and the check passed no matter how loose the match
    was. This codebase's comments name fields constantly — a comment is
    the most likely thing to be mistaken for a reader, so it is the thing
    to test with.

    Quoted, dotted or bracketed, or it does not count."""
    comment = "// closing_line is filled by the nightly harvest, not here"
    assert not feedaudit._named("closing_line", comment), \
        "a comment mentioning the field counted as somebody rendering it"
    assert feedaudit._named("closing_line", "row.closing_line")
    assert feedaudit._named("closing_line", 'b["closing_line"]')


def test_keys_that_are_data_are_not_mistaken_for_fields():
    """A dict keyed by a date or a team code is rows, not a schema.
    Reporting `days.2026-08-25` as an unrendered field is the kind of
    noise that gets a tool switched off."""
    for data_key in ("2026-08-25", "CLEM", "NYJ", "42"):
        assert feedaudit._DATA_KEY.match(data_key), data_key
    for real_field in ("hit_prob", "closing_line", "why_tag", "coverage"):
        assert not feedaudit._DATA_KEY.match(real_field), real_field
    # …and the walk actually USES it. Testing the regex alone left the
    # `continue` that applies it free to be deleted.
    walked = feedaudit._walk({"days": {"2026-08-25": {"n": 1}},
                              "2026-08-25": {"n": 1},
                              "keeper": 1})
    assert "keeper" in walked
    assert not [w for w in walked if "2026-08-25" in w], walked


def test_a_map_indexed_by_a_variable_is_not_walked_into():
    """`market_words[m]` means every word inside it is read without ever
    being named. Descending would report the whole table as unused."""
    walked = feedaudit._walk({"market_words": {"moneyline": "Moneyline"},
                              "real_block": {"inner_field": 1}})
    assert "market_words" in walked, "the map itself is still checked"
    assert "market_words.moneyline" not in walked
    assert "real_block.inner_field" in walked, \
        "an ordinary nested block is still walked"


def test_empty_everywhere_is_told_apart_from_carrying_values():
    """The distinction the report leans on. A field with real numbers in
    it that nobody renders is the interesting kind; one that is empty
    here is usually a corner this machine has no data for."""
    doc = {"a": {"filled": 3, "blank": None},
           "b": {"filled": 7, "blank": ""},
           "rows": [{"filled": 1, "blank": []}]}
    assert feedaudit._emptiness(doc, "blank") is True
    assert feedaudit._emptiness(doc, "filled") is False
    assert feedaudit._emptiness(doc, "not_here_at_all") is None


def _fixture(tmp, doc):
    import json
    (tmp / "sample.json").write_text(json.dumps(doc), encoding="utf-8")
    return str(tmp)


def test_the_report_names_what_is_unread_and_stays_quiet_about_the_rest():
    """The whole thing, end to end, on a feed built for the purpose —
    rather than on whatever this machine happens to have in web/data."""
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        d = _fixture(Path(td), {
            "shown_field": 5,          # a page reads this
            "hidden_field": 42,        # nobody does, and it has a value
            "blank_field": None,       # nobody does, and it is empty here
        })
        lines, leads = feedaudit.audit(data_dir=d, blob='x.shown_field')
        text = "\n".join(lines)
    assert "shown_field" not in text, "reported a field the page reads"
    assert "hidden_field" in text, "missed a field carrying a value"
    assert "blank_field" in text
    assert "[always empty]" in text
    # …and the mark is on the empty one, not on the one with a value.
    for line in text.splitlines():
        if "hidden_field" in line:
            assert "[always empty]" not in line, line
        if "blank_field" in line:
            assert "[always empty]" in line, line
    assert leads == 2, leads


def test_the_report_never_fails_a_build():
    """A lead is not a defect. Exiting nonzero over one would put this in
    the deploy's way and it would be switched off within a week."""
    import contextlib, io, tempfile
    from pathlib import Path
    quiet = io.StringIO()
    with tempfile.TemporaryDirectory() as td, contextlib.redirect_stdout(quiet):
        # WITH A LEAD IN IT. An empty directory finds nothing, so exiting
        # 0 there proved nothing at all — the first version of this test
        # passed against a tool that failed on every lead.
        _fixture(Path(td), {"nobody_reads_this": 41})
        assert feedaudit._main(["--data-dir", td]) == 0
        assert feedaudit._main(["--data-dir", td, "--all"]) == 0
        assert feedaudit._main(["--data-dir", td, "nope.json"]) == 0
    assert "nobody_reads_this" in quiet.getvalue(), \
        "the fixture did not actually produce a lead to not-fail on"


def test_every_internal_carries_a_reason():
    """The allow-list is how a real gap hides. "Probably internal" with
    no sentence beside it is the thing to refuse."""
    assert feedaudit.INTERNAL, "the allow-list is empty"
    for name, why in feedaudit.INTERNAL.items():
        assert isinstance(why, str) and len(why) > 12, \
            f"{name} is allow-listed without saying why"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
