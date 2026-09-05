"""The obvious way to look at a published pick returns nothing, silently.

Ethan's card sided UNDER 58.5 while its own insight said the model
"projects 71.6038" — a projection ABOVE the line it was betting below.
The first move is to open `web/data/recommendations.json` and read the
row. That is the PUBLIC copy: `recommendations` is a paid key, so with
the paywall on the picks have been stripped and the query returns
nothing at all, with no error.

`gate.board_source`'s docstring already lists three tools that learned
this the same way — `parlays.arbitrate_slate`, `parlaycheck.py` and
`--odds-doctor` — each of which "read an empty list and reported
honestly on nothing". A one-liner typed at a prompt was the fourth,
which is why this is a command in the repo instead.
"""

import io
import contextlib
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import launch
from engine import gate

ROOT = Path(__file__).resolve().parent.parent

PICK = {
    "player": "Kyren Williams", "market": "rush_yds", "side": "UNDER",
    "line": 58.5, "odds": -114, "book": "thescore bet",
    "projection": 71.6038, "hit_prob": 0.574, "edge": 0.044, "grade": "A",
    "recommended": True,
    "lines": [{"book": "thescore bet", "line": 58.5,
               "over_odds": -114, "under_odds": -114},
              {"book": "fanduel", "line": 78.5,
               "over_odds": -110, "under_odds": -110}],
    "reasons": ["Model sides UNDER — projects 71.6038 under the 58.5 line"],
}


def _tree():
    """A board tree with the picks in the PRIVATE copy and stripped from
    the public one — production's shape with the paywall on."""
    root = Path(tempfile.mkdtemp())
    (root / "web" / "data").mkdir(parents=True)
    (root / "data" / "built").mkdir(parents=True)
    (root / "data" / "built" / "recommendations.json").write_text(
        json.dumps({"recommendations": [PICK]}))
    (root / "web" / "data" / "recommendations.json").write_text(
        json.dumps({"recommendations": []}))
    return root


def _run(name, root):
    saved = launch.__file__
    buf = io.StringIO()
    try:
        launch.__file__ = str(root / "launch.py")
        with contextlib.redirect_stdout(buf):
            launch.inspect_pick(name)
    finally:
        launch.__file__ = saved
    return buf.getvalue()


def test_it_finds_a_pick_the_public_copy_has_had_stripped_out():
    root = _tree()
    public = json.loads(
        (root / "web" / "data" / "recommendations.json").read_text())
    assert public["recommendations"] == [], "premise: the public copy is empty"
    out = _run("Kyren Williams", root)
    assert "Kyren Williams" in out
    assert "rush_yds" in out and "UNDER" in out


def test_it_reads_through_the_gate_rather_than_the_public_path():
    import inspect
    src = inspect.getsource(launch.inspect_pick)
    assert "gate.board_source" in src
    assert '"web" / "data"' in src, "the public path is only the LOOKUP key"


def test_it_prints_every_book_because_the_sides_are_shopped_apart():
    """`betting.pick_side` shops the over and the under separately, so the
    chosen side can be priced at a different number than a reader
    assumes. The book list is what separates "wrong side" from "wrong
    line displayed"."""
    out = _run("Kyren Williams", _tree())
    assert "78.5" in out and "58.5" in out
    assert "shopped SEPARATELY" in out


def test_it_says_when_the_projection_is_on_the_wrong_side_of_the_line():
    out = _run("Kyren Williams", _tree())
    assert "is ABOVE the" in out
    assert "siding UNDER" in out


def test_a_projection_below_the_line_is_not_flagged():
    root = _tree()
    doc = {"recommendations": [dict(PICK, projection=41.0)]}
    (root / "data" / "built" / "recommendations.json").write_text(
        json.dumps(doc))
    out = _run("Kyren Williams", root)
    assert "is below the" in out and "is ABOVE the" not in out


def test_a_name_with_no_pick_says_where_it_looked():
    out = _run("Nobody At All", _tree())
    assert "No published pick" in out
    assert "recommendations.json" in out


def test_it_searches_the_longshot_boards_too():
    """A touchdown pick lives under `long_shots`, not `recommendations`."""
    root = _tree()
    (root / "data" / "built" / "recommendations.json").write_text(json.dumps(
        {"long_shots": [{"player": "Amon-Ra St. Brown", "market": "anytime_td",
                         "odds": -127, "grade": "Lean"}]}))
    out = _run("Amon-Ra", root)
    assert "Amon-Ra St. Brown" in out and "long_shots" in out


# --- the arithmetic check ----------------------------------------------------
def test_a_row_that_contradicts_itself_is_called_out():
    """`raw_prob` is the probability the CHOSEN side cashes, so an UNDER
    row already contains P(over) as `1 - raw_prob`. `prob_over` is
    `1 - normal_cdf(line, mu, sigma)`, which is above 0.5 whenever the
    mean is above the line — for ANY positive sigma. A row with a
    projection above its line and an implied P(over) below 0.5 did not
    come from one computation."""
    out = _capture({"line": 58.5, "projection": 71.6, "proj_high": 101.6,
                    "raw_prob": 0.597778, "side": "UNDER"})
    assert "MISMATCH" in out
    assert "P(over 58.5) = 0.402" in out
    assert "P(over 58.5) = 0.669" in out, "it must show what the projection says"


def test_a_consistent_row_is_not_flagged():
    out = _capture({"line": 58.5, "projection": 71.6, "proj_high": 101.6,
                    "raw_prob": 0.669, "side": "OVER"})
    assert "MISMATCH" not in out and "consistent" in out


def test_an_under_below_its_line_is_consistent():
    out = _capture({"line": 58.5, "projection": 41.0, "proj_high": 71.0,
                    "raw_prob": 0.7, "side": "UNDER"})
    assert "MISMATCH" not in out


def test_a_row_missing_the_numbers_is_skipped_rather_than_guessed():
    assert _capture({"line": 58.5, "side": "UNDER"}) == ""
    assert _capture({"projection": 71.6, "raw_prob": 0.6}) == ""


def test_it_works_without_a_spread_to_reconstruct_sigma_from():
    """`proj_high` gives the sd. Without it the expected probability
    cannot be computed, but the SIDE contradiction still can."""
    out = _capture({"line": 58.5, "projection": 71.6,
                    "raw_prob": 0.597778, "side": "UNDER"})
    assert "MISMATCH" in out
    assert "says P(over" not in out


def _capture(row):
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        launch._print_prob_check(row)
    return buf.getvalue()


def test_the_flag_is_wired_and_asks_for_a_name():
    import inspect
    src = inspect.getsource(launch)
    assert '"--inspect-pick" in argv' in src
    assert "usage: launch.py --inspect-pick" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
