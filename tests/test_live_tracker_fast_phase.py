"""The Live tab's tracked bets take their phase from the fast scoreboard.

Ethan, 2026-09-14: "NFL edge bets and most likely bets were not displaying
that they were live. But the games were showing live."

`live_picks` is assembled when the BOARD is built (every ~45 minutes for
football) and a row's `phase` is the game's state at that moment; the game
cards beside it read the twelve-second scoreboard. `liveTrackerRows` joins
the two on the matchup, in the viewed league, and only ever moves a row
forward. Run in node against the function as it sits in app.js.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()


def _fn():
    i = APP.index("/* Tracker rows with their phase read off the fast scoreboard")
    j = APP.index("function renderLivePicks() {")
    return APP[i:j]


def _run(rows, fast, sport="nfl"):
    js = f"""
    const state = {{ sport: {json.dumps(sport)} }};
    const _liveAll = {{ at: 1, games: {json.dumps(fast)} }};
    {_fn()}
    console.log(JSON.stringify(liveTrackerRows({json.dumps(rows)})));
    """
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _row(**kw):
    r = {"player": "Cooper Kupp", "market": "rec_yds", "phase": "upcoming",
         "status": "upcoming", "game": {"home": "SEA", "away": "NE"}}
    r.update(kw)
    return r


def _fast(state, sport="nfl", home="SEA", away="NE"):
    return [{"sport": sport, "g": {"home": home, "away": away,
                                   "home_score": 13, "away_score": 10,
                                   "period": "Q3", "live": {"state": state}}}]


def test_render_reads_the_promoted_rows():
    body = APP[APP.index("function renderLivePicks() {"):]
    assert "liveTrackerRows((state.data || {}).live_picks || [])" in body


def test_the_bets_redraw_when_the_scoreboard_lands():
    """`renderAll` draws the tracker before it reaches `renderLiveBoard`,
    so on the Live tab's first paint `_liveAll` is empty and every bet
    wears the build's phase until the next poll. 2026-09-14, third
    quarter of Broncos-Chiefs: "still showing upcoming for all these
    bets." The board redraws them from the scoreboard it just fetched."""
    body = APP[APP.index("async function renderLiveBoard() {"):]
    body = body[:body.index("\n}\n")]
    i = body.index("await fetchAllLive()")
    j = body.index("renderLivePicks()")
    assert i < j, "the bets must redraw AFTER the scoreboard is fetched"
    assert body.index("pressureWarm(") > j, "and before the slower warm-up, not after it"


def test_an_upcoming_bet_goes_live_with_its_game():
    got = _run([_row()], _fast("live"))[0]
    assert got["phase"] == "live" and got["status"] == "tracking", got
    assert got["game"]["home_score"] == 13, "the score rides along for the line under the bet"


def test_a_finished_game_moves_the_bet_to_final():
    got = _run([_row(phase="live", status="tracking")], _fast("final"))[0]
    assert got["phase"] == "final" and got["status"] == "final_pending", got


def test_a_verdict_the_build_reached_is_never_rewritten():
    for st in ("cleared", "busted", "dead", "won_pending"):
        got = _run([_row(phase="live", status=st)], _fast("final"))[0]
        assert got["status"] == st, (st, got)


def test_only_the_viewed_league_and_the_same_matchup():
    assert _run([_row()], _fast("live", sport="cfb"))[0]["phase"] == "upcoming"
    assert _run([_row()], _fast("live", home="LA", away="SF"))[0]["phase"] == "upcoming"


def test_no_fast_feed_means_exactly_the_build():
    rows = [_row()]
    assert _run(rows, [])[0] == rows[0]


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
