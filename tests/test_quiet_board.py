"""A priced card the model turned down must not read as a late feed.

`engine.gamebets._calibration_note` puts the measured market haircut on
a CARD, and its own docstring says why: "a board that quietly stopped
recommending spreads would be the worst version of this change — the
user sees fewer plays and is told nothing."

It was written for FEWER plays. `engine.gamecal` has since measured the
college spread and moneyline at NO edge over the close, so their shrink
is 0.0, every disagreement collapses onto the market by construction,
and there are Saturdays with no game bets at all. No cards means nowhere
for the note to ride, and the page fell through to copy about waiting
for real sportsbook prices — false on a day when the prices are there
and the model simply had nothing to say about them.

Run directly: `python3 tests/test_quiet_board.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import gamecal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


# --- the notes reach the payload --------------------------------------
def test_board_notes_cover_every_market_a_game_board_prices():
    assert gamecal.BOARD_MARKETS == ("spread", "total", "moneyline")


def test_board_notes_skip_a_market_with_nothing_measured():
    notes = gamecal.board_notes("quidditch")
    assert notes == {}


def test_board_notes_never_raise_on_a_broken_market():
    saved = gamecal.note_for
    try:
        gamecal.note_for = lambda *a, **k: (_ for _ in ()).throw(RuntimeError())
        assert gamecal.board_notes("cfb") == {}
    finally:
        gamecal.note_for = saved


def test_a_measured_market_produces_a_note_worth_showing():
    """Fed a real measurement, the note has to say what was measured and
    on how much — a bare "no edge" is a claim without evidence."""
    entry = {"sport": "cfb", "market": "spread", "n": 2055, "slope": -0.0367,
             "se": 0.04, "shrink": 0.0, "hit_rate": 0.4836, "fit_at": 0}
    saved = dict(gamecal._cache)
    try:
        gamecal._cache["cfb:spread"] = entry
        note = gamecal.note_for("cfb", "spread")
        assert note and "2055" in note.replace(",", "")
        assert "48.4%" in note or "no information" in note
        assert gamecal.board_notes("cfb", ("spread",)) == {"spread": note}
    finally:
        gamecal._cache.clear()
        gamecal._cache.update(saved)


def test_both_football_builds_put_the_notes_on_the_board():
    for build in ("cfb_build.py", "nfl_build.py"):
        source = _read(build)
        assert "board_notes" in source, build
        assert "line_calibration" in source, build


# --- the page reads them ----------------------------------------------
def _app():
    return _read("web", "js", "app.js")


def test_the_page_has_a_branch_for_a_priced_card_with_nothing_on_it():
    app = _app()
    assert "function pricedButQuiet()" in app
    assert "line_calibration" in app


def test_the_quiet_branch_runs_before_the_waiting_on_prices_copy():
    """Order is the whole fix. The fallback sentence is about a missing
    feed; reaching it on a priced card is what this exists to stop."""
    app = _app()
    quiet = app.index("const quiet = pricedButQuiet();")
    fallback = app.index("Waiting on real sportsbook prices")
    assert quiet < fallback


def test_the_quiet_branch_yields_to_a_real_feed_problem():
    """A broken odds pull is the more urgent explanation, and it is still
    true when nothing cleared the bar."""
    app = _app()
    body = app[app.index("function noMarketExplainer()"):]
    body = body[:body.index("\n}\n")]
    assert body.index("os.error") < body.index("pricedButQuiet()")
    assert body.index("os.checked === false") < body.index("pricedButQuiet()")


def test_the_quiet_branch_does_not_speak_for_the_props_board():
    """Books post player props close to kickoff and the page says so.
    Counting props here would pre-empt that with a sentence about
    game-line calibration, which is about a different market."""
    app = _app()
    body = app[app.index("function pricedButQuiet()"):]
    body = body[:body.index("\nfunction noMarketExplainer()")]
    assert "d.game_bets" in body
    assert "recommendations" not in body.split("// GAME BETS ONLY")[1]


def test_the_quiet_copy_calls_it_a_verdict_not_a_missing_feed():
    app = _app()
    body = app[app.index("function pricedButQuiet()"):]
    body = body[:body.index("\nfunction noMarketExplainer()")]
    assert "verdict" in body and "not a missing feed" in body


def test_the_notes_are_escaped_before_they_reach_the_page():
    body = _app()
    body = body[body.index("function pricedButQuiet()"):]
    body = body[:body.index("\nfunction noMarketExplainer()")]
    assert "escapeHtml" in body


def test_one_passing_bet_silences_the_whole_branch():
    """It only speaks for an EMPTY board. A board with a play on it is
    not quiet and this copy must never render beside a pick."""
    body = _app()
    body = body[body.index("function pricedButQuiet()"):]
    body = body[:body.index("\nfunction noMarketExplainer()")]
    assert re.search(r"filter\(passesGameBet\)\.length\)\s*return null", body)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
