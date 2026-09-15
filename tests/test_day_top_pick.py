"""One pick for the DAY, not one per league.

Ethan, 2026-09-15: "a model that picks one pick for the pick of the day,
which is a guaranteed lock for the day." Singular. `potd.build` chooses
one per SPORT, so a reader on the MLB page and a reader on the NFL page
were each shown a different "Pick of the Day" and neither was the day's.

WHAT THIS IS NOT is a second model. `potd.rank_key` already orders picks
on three quantities that know nothing about which sport produced them —
which witness stands behind the fair, the edge in points, the payout —
so the cross-league answer is that comparator over a longer list. These
tests hold that it stays that way: a cross-sport bar invented here would
be a second set of numbers measured on nothing.

Run directly: `python3 tests/test_day_top_pick.py`
"""

import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import potd                                       # noqa: E402

TODAY = "2026-03-04"          # any day; never read from the clock


def _board(date=TODAY, **pick):
    """One published board carrying one pick of the day."""
    if not pick:
        return {"pick_of_the_day": {"date": date, "pick": None,
                                    "note": "the board had no rows"}}
    return {"pick_of_the_day": {"date": date, "pick": dict(pick)}}


def _sharp(odds=-130, fair=0.60, **extra):
    return dict(player="AAA", market="moneyline", odds=odds,
                sharp_anchored=True, sharp_fair=fair, fair_prob=fair,
                evidence="sharp", **extra)


def _model(odds=-130, fair=0.70, **extra):
    return dict(player="BBB", market="moneyline", odds=odds,
                model_prob=fair, fair_prob=fair, evidence="model", **extra)


# ── the comparison ──────────────────────────────────────────────────

def test_the_better_witness_wins_across_leagues_not_the_bigger_edge():
    """THE INVERSION THE WHOLE MODULE TURNS ON, now across boards. A
    model-only 10-point disagreement is a louder claim than a sharp
    book's 2, and much more often simply wrong. If this ever flips, the
    cross-league feature is handing every day to the weakest witness on
    the site."""
    got = potd.day_top_pick(
        {"nfl": _board(**_sharp()), "mlb": _board(**_model())}, TODAY)
    assert got["sport"] == "nfl", got["sport"]
    assert [r["sport"] for r in got["runners_up"]] == ["mlb"], got


def test_a_qualifying_pick_always_beats_a_below_bar_one():
    """`build` publishes its best available when nothing clears, so a
    below-bar row is on the board BY DESIGN. Letting one outrank a pick
    that cleared every gate would quietly undo the gates — and it would
    do it silently, because both cards look the same from here."""
    got = potd.day_top_pick({
        # The below-bar row is given the STRONGER witness on purpose:
        # tier alone would hand it the day.
        "nfl": _board(**_sharp(), below_bar="the price drifted"),
        "mlb": _board(**_model()),
    }, TODAY)
    assert got["sport"] == "mlb", got["sport"]
    assert not got["pick"].get("below_bar"), got["pick"]


def test_when_nothing_clears_anywhere_the_best_lean_is_shown_and_labelled():
    """The page is never blank — and never pretends. Same two states the
    per-league card has."""
    got = potd.day_top_pick(
        {"nfl": _board(**_sharp(), below_bar="the price drifted")}, TODAY)
    assert got["pick"]["below_bar"] == "the price drifted"
    assert "best available" in got.get("note", ""), got.get("note")


def test_the_league_travels_with_the_pick():
    """A top pick nobody can find is not one. The card names the league
    and the page opens it."""
    got = potd.day_top_pick({"cfb": _board(**_sharp())}, TODAY)
    assert got["sport"] == "cfb"
    assert got["pick"]["sport"] == "cfb", got["pick"]


def test_a_tie_on_every_measured_quantity_resolves_the_same_way_twice():
    """Two identical picks in different leagues must not depend on which
    board finished writing first. TOP_PICK_LEAGUES is the tiebreak, and it
    is an ORDER rather than a claim that one league's picks are better —
    that claim would be an assertion measured on nothing."""
    same = dict(market="moneyline", odds=-130, sharp_anchored=True,
                sharp_fair=0.60, fair_prob=0.60, evidence="sharp")
    a = potd.day_top_pick(
        {"mlb": _board(player="M", **same), "nfl": _board(player="N", **same)},
        TODAY)
    b = potd.day_top_pick(
        {"nfl": _board(player="N", **same), "mlb": _board(player="M", **same)},
        TODAY)
    assert a["sport"] == b["sport"] == "nfl", (a["sport"], b["sport"])


# ── the staleness refusal ───────────────────────────────────────────

def test_yesterdays_pick_is_never_todays_top_pick():
    """THE FAILURE THIS FEATURE WOULD OTHERWISE INVENT. Every board
    publishes on its own schedule, and a league out of season leaves a
    perfectly well-formed pick on disk from whenever it last ran.
    Nothing about that card looks wrong; only its date says so."""
    got = potd.day_top_pick(
        {"mlb": _board(date="2026-03-03", **_sharp())}, TODAY)
    assert got["pick"] is None, got["pick"]
    assert any("has not rebuilt today" in k for k in got["census"]), got["census"]


def test_a_board_with_no_date_at_all_is_refused_rather_than_trusted():
    """An older board predating the date field would otherwise sail
    through every check — the emptiest possible evidence read as
    agreement."""
    got = potd.day_top_pick({"mlb": {"pick_of_the_day": {
        "pick": _sharp()}}}, TODAY)
    assert got["pick"] is None, got["pick"]


def test_a_fresh_league_still_wins_when_a_stale_one_looks_stronger():
    """The refusal has to bite BEFORE the ranking, or a stale sharp pick
    beats a live model one every time and the top pick silently stops
    moving."""
    got = potd.day_top_pick({
        "nfl": _board(date="2026-03-01", **_sharp()),
        "mlb": _board(**_model()),
    }, TODAY)
    assert got["sport"] == "mlb", got["sport"]


# ── it never goes quiet ─────────────────────────────────────────────

def test_a_day_with_no_top_pick_says_which_league_failed_and_why():
    """A census, not a shrug — the funnel `likely.build` keeps and the
    one `potd.choose` keeps, for the same reason."""
    got = potd.day_top_pick({"mlb": _board(), "nfl": {}}, TODAY)
    assert got["pick"] is None
    assert len(got["census"]) == 2, got["census"]
    assert any("mlb" in k for k in got["census"]), got["census"]
    assert any("nfl" in k for k in got["census"]), got["census"]


def test_a_board_that_threw_is_named_rather_than_skipped():
    got = potd.day_top_pick(
        {"mlb": {"pick_of_the_day_error": "KeyError: home"}}, TODAY)
    assert any("could not choose" in k for k in got["census"]), got["census"]


def test_the_log_line_is_never_empty_whatever_it_is_handed():
    """A cross-board step that prints nothing on a day it chose nothing
    is the failure `lineledger.record_note` and the rankings section
    were both dragged out of."""
    for arg in ({}, None, {"pick": None, "census": {"mlb: no board": 1}},
                potd.day_top_pick({"nfl": _board(**_sharp())}, TODAY),
                {"pick": {"odds": None}}):
        line = potd.top_pick_line(arg)
        assert line and line.strip(), arg
        assert line.startswith("top pick:"), line


def test_a_card_without_its_tier_is_not_described_as_none():
    """`_card` always sets `evidence`; a card assembled anywhere else
    might not, and "None fair 60%" in a build log reads like a measured
    absence rather than a missing field."""
    card = _sharp()
    card.pop("evidence")                  # as a card built elsewhere would be
    line = potd.top_pick_line({"sport": "nfl", "pick": card, "runners_up": []})
    assert "None fair" not in line, line
    assert "sharp fair" in line, line


# ── it must stay a comparison ───────────────────────────────────────

def test_the_cross_league_chooser_invents_no_bar_of_its_own():
    """Every threshold this reasons about has to be one `potd` already
    measured. A cross-sport constant introduced here would be a second
    set of numbers to keep honest, fitted to nothing."""
    body = inspect.getsource(potd.day_top_pick)
    assert "rank_key" in body, "the shared comparator is no longer used"
    # THE FIRST VERSION OF THIS ASSERTION WAS VACUOUS — it ended in
    # `or "rank_key" in body`, which the line above had just proved, so
    # it could never fail. What it was reaching for is checkable
    # directly: the band this publishes must be potd's own constants,
    # not numbers typed again here.
    out = potd.day_top_pick({}, TODAY)
    assert out["band"] == [potd.MIN_ODDS, potd.MAX_ODDS], out["band"]
    assert out["min_ev"] == potd.MIN_EV, out["min_ev"]


def test_an_empty_slate_is_a_fact_rather_than_an_exception():
    got = potd.day_top_pick({}, TODAY)
    assert got["pick"] is None
    assert got["note"], got


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
