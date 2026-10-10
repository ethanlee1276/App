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


def _run(rows, fast, sport="nfl", finals=None):
    """`fast` is what `fetchAllLive` keeps under `games` — LIVE games only,
    the list the cards draw — and `finals` what it keeps under `finals`.
    A test that wants a finished game passes it there, the way production
    delivers it (2026-09-14, 11:15pm: a final put nowhere was a bet back
    on UPCOMING the moment its game ended)."""
    js = f"""
    const state = {{ sport: {json.dumps(sport)} }};
    const _liveAll = {{ at: 1, games: {json.dumps(fast)},
                       finals: {json.dumps(finals or [])} }};
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
    got = _run([_row(phase="live", status="tracking")], [], finals=_fast("final"))[0]
    assert got["phase"] == "final" and got["status"] == "final_pending", got
    assert got["game"]["home_score"] == 13, "the final score rides along"


def test_the_scoreboard_keeps_finals_for_the_tracker():
    """Ethan, 2026-09-14, 11:15pm, minutes after Broncos-Chiefs ended:
    "Whatever u did shows the bets as upcoming again." `fetchAllLive`
    collected LIVE games only, so the moment a game finished every bet
    on it lost the state that had promoted it and fell back to the
    build's UPCOMING. Finals now ride under their own key — the cards
    still draw the live list alone."""
    i = APP.index("async function fetchAllLive() {")
    body = APP[i:APP.index("\n}\n", i)]
    assert 'else if (st === "final") done.push({ sport, g });' in body
    assert "_liveAll = { at: Date.now(), games: out, finals: done };" in body
    assert "return out;" in body, "the cards still get the live list alone"
    # And an upcoming bet on a game that ended before the tab was opened
    # reads FINAL, not UPCOMING.
    got = _run([_row()], [], finals=_fast("final"))[0]
    assert got["phase"] == "final" and got["status"] == "final_pending", got


def test_a_verdict_the_build_reached_is_never_rewritten():
    for st in ("cleared", "busted", "dead", "won_pending"):
        got = _run([_row(phase="live", status=st)], [], finals=_fast("final"))[0]
        assert got["status"] == st, (st, got)


def test_only_the_viewed_league_and_the_same_matchup():
    assert _run([_row()], _fast("live", sport="cfb"))[0]["phase"] == "upcoming"
    assert _run([_row()], _fast("live", home="LA", away="SF"))[0]["phase"] == "upcoming"


def test_no_fast_feed_means_exactly_the_build():
    rows = [_row()]
    assert _run(rows, [])[0] == rows[0]


# --- the number, on the same clock as the score (2026-09-14) ----------------
# Ethan, 11:01pm, fourth quarter of Broncos-Chiefs, every bet on the Live
# tab reading "in play" and nothing else: "why are we not showing the live
# lines for the live props here and not tracking the live stats like how
# sports books do it." The fast scoreboard now carries each live game's
# box rows; the tracker row reads its number off them on every poll.
def _box(state="live", players=None, home="SEA", away="NE", hs=13, as_=10,
         period="Q3", sport="nfl"):
    g = {"home": home, "away": away,
         "live": {"state": state, "home_score": hs, "away_score": as_,
                  "period": period, "clock": "4:12"}}
    if players is not None:
        g["players"] = players
    return [{"sport": sport, "g": g}]


KUPP = [{"player": "Cooper Kupp", "team": "SEA", "position": "WR",
         "stats": {"rec_yds": 57.0, "receptions": 4.0, "targets": 6.0}}]


def test_a_props_number_comes_off_the_fast_files_box_rows():
    got = _run([_row(line=62.5, side="OVER")], _box(players=KUPP))[0]
    assert got["status"] == "tracking" and got["current"] == 57.0, got


def test_an_over_past_its_line_has_cleared_and_an_under_past_it_has_died():
    over = _run([_row(line=49.5, side="OVER")], _box(players=KUPP))[0]
    assert over["status"] == "cleared" and over["current"] == 57.0, over
    under = _run([_row(line=49.5, side="UNDER")], _box(players=KUPP))[0]
    assert under["status"] == "busted", under
    # Short of the line, an under is alive and an over is still counting.
    alive = _run([_row(line=62.5, side="UNDER")], _box(players=KUPP))[0]
    assert alive["status"] == "tracking", alive


def test_the_fresher_number_replaces_the_builds():
    """The board's box score is up to forty-five minutes old on football;
    the fast file's is seconds old. The newer figure wins whatever the
    build wrote — and a verdict the build reached keeps its word while
    taking the newer number."""
    got = _run([_row(phase="live", status="tracking", current=40.0,
                     line=62.5, side="OVER")], _box(players=KUPP))[0]
    assert got["current"] == 57.0, got
    kept = _run([_row(phase="live", status="cleared", current=50.0,
                      line=49.5, side="OVER")], _box(players=KUPP))[0]
    assert kept["status"] == "cleared" and kept["current"] == 57.0, kept


def test_no_box_rows_means_the_builds_number_stands():
    """A game past the box-score cap, or a loop that predates the rows:
    the row keeps whatever the build knew rather than blanking."""
    got = _run([_row(phase="live", status="tracking", current=40.0,
                     line=62.5, side="OVER")], _box())[0]
    assert got["current"] == 40.0 and got["status"] == "tracking", got
    # And a name the box spells another way is a miss, not a wrong number.
    other = [{"player": "Cooper Kupp Sr.", "team": "SEA",
              "stats": {"rec_yds": 99.0}}]
    got = _run([_row(player="Jaxon Smith-Njigba", line=62.5, side="OVER")],
               _box(players=other))[0]
    assert "current" not in got or got["current"] is None, got


def test_the_name_join_folds_like_the_servers_normalizer():
    """One rule, two languages. `trackerNameKey` must fold a name exactly
    as `oddsapi.normalize_name` does, or a journaled name and ESPN's box
    spelling meet on the server and miss on the page."""
    sys.path.insert(0, str(ROOT))
    from engine.sources.oddsapi import normalize_name
    names = ["Amon-Ra St. Brown", "Ronald Acuña Jr.", "Ja'Marr Chase",
             "A\u2019ja Wilson", "Kenneth Walker III", "D.J. Moore",
             "Marvin Harrison Jr.", "Patrick Mahomes II", "  Travis  Kelce "]
    js = f"""
    {_fn()}
    console.log(JSON.stringify({json.dumps(names)}.map(trackerNameKey)));
    """
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout)
    want = [normalize_name(n) for n in names]
    assert got == want, list(zip(names, got, want))


def test_a_team_market_tracks_from_the_score():
    """The same arithmetic `assemble_live_picks` does at build time: a
    total is both scores, a team total the team's, a spread the team's
    margin against the negated line — and a moneyline has no number,
    the score line says it."""
    total = _run([_row(player="NE@SEA", market="total", line=44.5, side="OVER")],
                 _box())[0]
    assert total["current"] == 23 and total["status"] == "tracking", total
    tt = _run([_row(player="SEA", market="team_total", line=10.5, side="OVER")],
              _box())[0]
    assert tt["current"] == 13 and tt["status"] == "cleared", tt
    # SEA −3.5 journals as line 3.5 side OVER; up 3 is not covering.
    sp = _run([_row(player="SEA", market="spread", line=3.5, side="OVER")],
              _box())[0]
    assert sp["current"] == 3 and sp["status"] == "tracking", sp
    # The away side's margin is its own.
    ne = _run([_row(player="NE", market="spread", line=-3.5, side="OVER")],
              _box())[0]
    assert ne["current"] == -3, ne
    ml = _run([_row(player="SEA", market="moneyline", line=0.5, side="OVER")],
              _box())[0]
    assert ml.get("current") is None and ml["status"] == "tracking", ml


def test_a_spread_never_locks_early():
    """A margin swings both ways — up 10 in the third can be down 4 at
    the whistle — so a spread tracks without a verdict until the final,
    exactly as the build treats it."""
    got = _run([_row(player="SEA", market="spread", line=3.5, side="OVER")],
               _box(hs=27, as_=10))[0]
    assert got["current"] == 17 and got["status"] == "tracking", got


def test_the_score_is_lifted_from_the_fast_files_live_block():
    """The real fast file keeps the score under `live`; the line under a
    bet (`gameLine`) reads `game.home_score`, the build's layout. Without
    the lift the row said "NE @ SEA" beside a game in its third quarter."""
    got = _run([_row()], _box(hs=21, as_=14, period="Q4"))[0]
    assert (got["game"]["home_score"], got["game"]["away_score"]) == (21, 14), got
    assert got["game"]["period"] == "Q4" and got["game"]["state"] == "live", got


def test_a_spread_prints_the_number_he_took():
    """The journal stores a spread NEGATED (ledger: "line = -spread"), so
    a SEA −3.5 ticket is line 3.5 — and the tab printed "SEA +3.5" on
    every favourite it ever showed. The text, the status copy and the
    market-line comparison all speak in the number he took."""
    body = APP[APP.index("function renderLivePicks() {"):]
    body = body[:body.index("\n}\n")]
    # The sentence lives in trackerBetText since 2026-09-22 (shared with
    # the phone home deck); the tab binds it as betTxt.
    assert "const betTxt = trackerBetText;" in body
    txt = APP[APP.index("function trackerBetText(r)"):]
    txt = txt[:txt.index("\n}\n")]
    i = txt.index('if (r.market === "spread") {')
    assert "const took = -r.line;" in txt[i:i + 900], "betTxt prints the stored line"
    j = body.index('if (r.current != null && r.market === "spread")')
    spread = body[j:j + 1200]
    assert "covering ${spreadTxt}" in spread and "needs ${Math.ceil(need)} more" in spread
    k = body.index("const marketLine = (r) =>")
    ml = body[k:k + 2600]
    assert 'const took = r.market === "spread" ? -r.line : r.line;' in ml
    assert "Number(now) < Number(took)" in ml, "the better-or-worse call compares the stored line"


def test_the_footnote_no_longer_blames_the_refresh_cycle():
    body = APP[APP.index("function renderLivePicks() {"):]
    assert "Stat lines update with the board’s refresh cycle" not in body
    assert "update every few seconds while a game runs" in body


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
