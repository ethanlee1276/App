"""#77's instrument: does the market shrink help or hurt the top rows?

The replay says the top of the likelihood board underclaims even after
the fitted temperature (top-1 60.0% claimed, 67.4% landed), while the
page prints a number already shrunk halfway to the book. Whether that
shrink is closing the gap or dragging good numbers toward a lazy
consensus needs harvested closes, which only the droplet holds — so
`tdbook.shrink_report` runs there, weekly, from the maintenance pass.

This file grades the instrument itself on synthetic slates where the
right answer is known by construction: a world where the market's number
is the truth, one where the model's is, the ordering comparison, and the
refusal below the slate floor. An instrument that has never been read
against a known answer is the kind that gets believed anyway.

Run directly: `python3 tests/test_shrink_check.py`
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine.tdbook import (shrink_report, MIN_SHRINK_SLATES,
                          REG_SEASON_WEEKS)


def _row(season, week, cal, fair, scored, player="p"):
    return {"season": season, "week": week, "cal": cal, "fair": fair,
            "rank": 0, "player": player, "odds": -110, "scored": scored}


def _slates(n, gap):
    """Ten rows a slate; the book sits `gap` from the model, and the
    landed rate at the top (60%, exactly, by construction) matches
    whichever of the two the scenario puts at 0.60. cal and fair move
    together, so both rankings agree and only calibration is live.

    THE SEPARATION IS LARGE ON PURPOSE. The verdict speaks only when a
    slate bootstrap separates first from second place, and the first
    cut of this file proved the refusal works by tripping it: claims
    six points apart against a landed rate known to ±7.7 on 40 slates
    is genuinely unknowable, and the report said so. A test of the
    clear-verdict path has to build a world where the answer is clear.
    """
    rows = []
    for i in range(n):
        for j in range(10):
            top = j == 9
            cal = (0.10 + 0.01 * j) if top is False else 0.20
            scored = 1 if (top and (i * 3) % 5 < 3) else 0   # 60% exactly
            rows.append(_row(2024, i, cal, cal + gap, scored, f"p{j}"))
    return rows


def _slates_market_is_truth(n=200):
    return _slates(n, +0.40)          # model 0.20, book 0.60 — book lands


def _slates_model_is_truth(n=200):
    rows = _slates(n, -0.40)          # book at -0.20 is nonsense; flip it
    for r in rows:
        r["cal"], r["fair"] = r["cal"] + 0.40, r["cal"]
    return rows                       # model 0.60, book 0.20 — model lands


def test_when_the_market_is_the_truth_the_report_says_so():
    lines = "\n".join(shrink_report(_slates_market_is_truth(), depths=(1,)))
    assert "the market" in lines, lines
    assert "(inside the noise)" not in lines, lines


def test_when_the_model_is_the_truth_the_report_says_that_instead():
    lines = "\n".join(shrink_report(_slates_model_is_truth(), depths=(1,)))
    assert "the model" in lines, lines


def test_the_ordering_panel_sees_a_reordering_the_shrink_causes():
    """Player X: model 0.50, book 0.30 → shrunk 0.40. Player Y: model
    0.45, book 0.55 → shrunk 0.50. The model ranks X first, the page
    ranks Y first — and Y scores 70% of the time to X's 40%, so ranking
    by the shrunk number picks the better scorer."""
    rows = []
    for i in range(40):
        rows.append(_row(2024, i, 0.50, 0.30, 1 if i % 5 < 2 else 0, "X"))
        rows.append(_row(2024, i, 0.45, 0.55, 1 if i % 10 < 7 else 0, "Y"))
    lines = "\n".join(shrink_report(rows, depths=(1,)))
    assert "shrunk ranks better" in lines, lines


def test_too_few_slates_is_a_refusal_not_a_verdict():
    lines = shrink_report(_slates_market_is_truth(5))
    assert "NOT ANSWERED" in lines[0], lines
    assert str(MIN_SHRINK_SLATES) in lines[0]


def test_the_refusal_says_why_waiting_will_not_close_it():
    """Ethan ran this on 2026-09-16, two weeks after the last run, and
    the priced-slate count had gone DOWN — 14 to 12. The old refusal said
    "the harvest is young; the question stays open", which is advice to
    wait, and waiting cannot work: a slate is one (season, week) and a
    regular season holds 18 of them against a floor of 30. One season
    cannot reach it. The refusal has to say that rather than imply the
    opposite."""
    lines = shrink_report(_slates_market_is_truth(5))
    blob = "\n".join(lines)
    assert str(REG_SEASON_WEEKS) in blob, blob
    assert "Waiting cannot close this" in blob, blob
    assert "second season" in blob, blob


def test_the_refusal_shows_the_slates_it_actually_found():
    """So the next run can be compared with the last one instead of
    reduced to a single number that went the wrong way unexplained."""
    lines = shrink_report(_slates_market_is_truth(5))
    blob = "\n".join(lines)
    assert "slates found:" in blob, blob
    assert "seasons with a priced row:" in blob, blob


def test_two_seasons_present_points_at_the_funnel_instead():
    """The arithmetic only applies while one season is all there is. With
    two, the shortfall is something dropping rows and the refusal has to
    send the reader to the funnel rather than repeat the season maths."""
    rows = _slates_market_is_truth(5)
    for r in rows[: len(rows) // 2]:
        r["season"] = r["season"] - 1
    blob = "\n".join(shrink_report(rows))
    assert "Waiting cannot close this" not in blob, blob
    assert "names the step that is dropping them" in blob, blob


def test_no_rows_at_all_is_the_same_refusal():
    lines = shrink_report([])
    assert "NOT ANSWERED" in lines[0], lines


def test_a_depth_no_slate_can_answer_sits_out_silently():
    """Slates carry 10 rows; top 40 has no slate deep enough. The line
    is absent, never a crash and never a fabricated zero."""
    lines = shrink_report(_slates_market_is_truth(), depths=(1, 40))
    assert not any("top 40" in ln for ln in lines), lines


def test_the_weekly_pass_carries_the_check():
    with open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "engine", "maintenance.py"),
            encoding="utf-8") as f:
        src = f.read()
    assert "shrink_report(board_priced(" in src


def test_the_weekly_pass_tracks_the_devig_bands_too():
    """#65: the +455-800 band finding came from a CLI nobody would
    remember to re-run. Both sports, weekly, refusing without closes."""
    with open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "engine", "maintenance.py"),
            encoding="utf-8") as f:
        src = f.read()
    at = src.index("devig bands")
    block = src[at - 1200:at + 800]
    assert "from .devigfit import collected, report_lines" in block
    assert '("nfl", "cfb")' in block
    assert "stays open" in block


def test_the_flag_that_runs_it_is_discoverable():
    """#77 read as though the measurement still had to be built. It did
    not: `tdbook --shrink` has worked since it shipped — AND WAS IN NO
    USAGE TEXT. `tdbook`'s own help line listed `--roi` and `--rank` and
    stopped.

    A flag nobody can find is a flag nobody runs, which is most of why a
    question with a working answer sat open. (The first fix here added a
    SECOND `--shrink` to `tdbacktest`; that is two doors onto one report
    and is how they drift. Reverted — `tdbacktest` points at this one
    instead.)
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "engine", "tdbook.py"), encoding="utf-8") as f:
        src = f.read()
    assert '"--shrink" in argv' in src, "the flag is gone"
    assert "shrink_report(rows)" in src, "the flag parses and reaches nothing"
    assert "--shrink to ask" in src, "the flag is not in the usage text"


def test_there_is_exactly_one_door_onto_the_shrink_report():
    """Two entry points to one measurement is how they drift — and the
    pointer from `tdbacktest` has to name the real one, or a reader
    lands where the task told them to go and finds nothing."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "engine", "tdbacktest.py"),
              encoding="utf-8") as f:
        other = f.read()
    assert '"--shrink" in argv' not in other, \
        "tdbacktest grew its own --shrink again — one report, one door"
    assert "engine.tdbook --shrink" in other, \
        "tdbacktest no longer points at where the question is answered"


def test_the_weekly_pass_still_runs_it_too():
    """The CLI is an ADDITION, not a replacement. The weekly pass is what
    makes the answer arrive without anybody deciding to ask, which was
    the original point (#65's finding came from a CLI nobody remembered
    to re-run)."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "engine", "maintenance.py"),
              encoding="utf-8") as f:
        src = f.read()
    assert "shrink_report(board_priced(_sc))" in src, \
        "the weekly shrink check is gone — the CLI does not replace it"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
