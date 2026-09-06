"""Football obeys the bankroll caps, and does not price a shut market.

Ethan, 2026-09-06: "we have like 106 open edge bets for NFL and that can
be really confusing for a user because I don't know if they're gonna put
in 106 bets so I feel like we should kind of tune that in a little bit
unless that's the model allowing it."

It was not the model allowing it. Two gates that exist were not reaching
the football board:

  * engine/correlation.py calls itself §9 of docs/NFL_MODEL.md, its flags
    are football relationships, and its §10 caps are 5u per game and 15u
    per slate. Baseball's pipeline was its only caller. A hundred and six
    picks at a full unit each is the whole bankroll on one weekend.
  * engine/calibrate.is_reliable shuts a market whose fit ran to the edge
    of its grid or whose curve can only ever name one side — but it
    answers from a fitted store, and a market the store has never heard
    of falls through to the neutral default and is allowed. The yardage
    finding (AUC 0.479 against real closes, fix specified and declined)
    held only while its curve happened to be on the box.

Run directly: `python3 tests/test_football_exposure.py`
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import calibrate
from engine.correlation import GAME_CAP_U, SLATE_CAP_U, apply_exposure_caps
from engine.staking import MIN_STAKE_UNITS


def test_a_market_measurement_has_shut_stays_shut_with_no_fitted_store():
    """An empty models directory must not re-open the yardage markets."""
    empty = tempfile.mkdtemp()
    assert calibrate.is_reliable("nfl", "rush_yds", path=os.path.join(empty, "c.json")) is False
    assert calibrate.is_reliable("nfl", "rec_yds", path=os.path.join(empty, "c.json")) is False
    # Everything else keeps answering from the store, as before.
    for market in ("pass_yds", "receptions", "anytime_td", "spread", "total"):
        assert calibrate.is_reliable("nfl", market, path=os.path.join(empty, "c.json")) is True, market
    # The finding was about OUR pricing of the NFL's yardage, and it does
    # not silently travel to another sport that was measured separately.
    assert calibrate.is_reliable("cfb", "rush_yds", path=os.path.join(empty, "c.json")) is True
    assert calibrate.is_reliable("mlb", "hits", path=os.path.join(empty, "c.json")) is True


def test_disabling_calibration_is_not_a_licence_to_price_a_shut_market():
    """`set_enabled(False)` turns the corrections off — a backtest or a
    tool asking for raw model numbers. It must not re-open a market
    nothing can price, so the shut is checked before that switch."""
    calibrate.set_enabled(False)
    try:
        assert calibrate.is_reliable("nfl", "rush_yds") is False
        assert calibrate.is_reliable("nfl", "pass_yds") is True
    finally:
        calibrate.set_enabled(True)


def test_the_shut_names_the_measurement_that_shut_it():
    why = calibrate.shut_reason("nfl", "rush_yds")
    assert "0.479" in why and "beat a line" in why
    assert calibrate.shut_reason("nfl", "REC_YDS"), "case-insensitive"
    assert calibrate.shut_reason("nfl", "pass_yds") == ""
    assert calibrate.shut_reason("", "") == ""


def _slate(n_props, n_games, stake=1.0):
    """A football week: `n_props` props and `n_games` game bets, one unit
    each, spread over enough fixtures that the SLATE cap is what binds."""
    props = [{"player": f"P{i}", "market": "pass_yds", "team": f"T{i}",
              "opponent": f"O{i}", "game_date": "2026-W01",
              "recommended": True, "stake_units": stake, "grade": "A"}
             for i in range(n_props)]
    games = [{"home": f"H{i}", "away": f"A{i}", "date": "2026-W01",
              "market": "spread", "recommended": True, "stake_units": stake,
              "grade": "A"} for i in range(n_games)]
    return props, games


def test_a_week_of_106_bets_is_capped_to_the_slate_limit():
    props, games = _slate(46, 60)
    assert len(props) + len(games) == 106
    notes = apply_exposure_caps(props, games)
    live = [r for r in props + games if r.get("recommended")]
    total = sum(r["stake_units"] for r in live)
    assert 106.0 > total, "uncapped it asked for the whole bankroll"
    assert total <= SLATE_CAP_U + 0.5, f"{total}u against a {SLATE_CAP_U}u cap"
    assert notes and "15u cap" in notes[0] and "scaled by" in notes[0]
    # Uniform scaling: the count survives, the exposure does not. That is
    # the measured policy — a ranked trim kept the losers.
    assert len(live) == 106, "no pick was dropped at this size"
    assert all(abs(r["stake_units"] - round(SLATE_CAP_U / 106, 2)) < 0.02 for r in live)
    assert all("scaled" in (r.get("stake_basis") or "") for r in live)


def test_a_stake_scaled_under_the_floor_comes_off_the_board():
    # 400 bets: the factor drives every stake under the 0.1u minimum, and
    # a stake that small is a rounding artefact with a ticket.
    props, games = _slate(200, 200)
    apply_exposure_caps(props, games)
    live = [r for r in props + games if r.get("recommended")]
    assert live == [], "everything fell under the floor and none of it was dropped"
    assert all(r["grade"] == "Pass" and r["stake_units"] == 0.0 for r in props + games)
    assert any("minimum" in w for w in props[0]["warnings"])


def test_a_board_inside_the_caps_is_left_alone():
    props, games = _slate(4, 4, stake=1.0)
    notes = apply_exposure_caps(props, games)
    assert notes == []
    assert all(r["stake_units"] == 1.0 for r in props + games)
    assert all("stake_basis" not in r for r in props + games)


def test_both_football_builds_run_the_flags_and_the_caps():
    for name in ("nfl_build.py", "cfb_build.py"):
        src = (ROOT / name).read_text()
        assert "from engine.correlation import flag_correlations, apply_exposure_caps" in src, name
        assert "apply_exposure_caps(" in src, name
        assert "flag_correlations(" in src, name
    nfl = (ROOT / "nfl_build.py").read_text()
    # Before the journal, and before the drawdown rule that halves stakes
    # — the ledger must record what we would actually bet.
    assert nfl.index("apply_exposure_caps(") < nfl.index("drawdown_factor")
    assert nfl.index("apply_exposure_caps(") < nfl.index("log_recommendations(lconn, result)")
    cfb = (ROOT / "cfb_build.py").read_text()
    assert cfb.index("apply_exposure_caps(") < cfb.index('"sport": "cfb", "date": args.date')
    assert GAME_CAP_U == 5.0 and SLATE_CAP_U == 15.0 and MIN_STAKE_UNITS == 0.1


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
