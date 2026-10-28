"""Your players, live: each followed player's line from the game he is in,
every league on one strip at the top of the Live tab (engine/yourplayers).

Ethan, 2026-10-25: "create things I've never even thought of." The lines
come from the box scores the fast loop already writes, nothing new is
fetched, and a game not started has no line.

    python3 tests/test_your_players_live.py
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import yourplayers as YP                             # noqa: E402


def test_each_sport_reads_like_a_box_score():
    assert YP.line({"line": {"batting": {"ab": 4, "h": 2, "hr": 1, "rbi": 3, "bb": 0}}}) == "2/4, 1 HR, 3 RBI"
    assert YP.line({"line": {"pitching": {"ip": "6.1", "k": 9, "er": 1, "p": 97}}}) == "6.1 IP, 9 K, 1 ER, 97 P"
    assert YP.line({"stats": {"receptions": 6, "rec_yds": 94, "rec_td": 1}}) == "6 rec, 94 yds, 1 TD"
    assert YP.line({"stats": {"pass_yds": 241, "pass_td": 2, "carries": 4, "rush_yds": 31}}) \
        == "241 pass yds, 2 TD · 4 car, 31 yds"
    assert YP.line({"stats": {"pts": 31.0, "reb": 8, "ast": 0, "fg3m": 4}}) == "31 pts, 8 reb, 4 3PM"
    assert YP.line({"stats": {"goals": 1, "assists": 0, "sog": 5}}, "nhl") == "1 G, 5 SOG"
    assert YP.line({"stats": {"saves": 31, "shots_against": 33, "goals_against": 2}}, "nhl") == "31 saves, 2 GA"
    assert YP.line({"stats": {}}) == "" and YP.line(None) == ""


def _doc(league, eid, state, players, home="CIN", away="PIT"):
    return {"league": league, "event_id": eid, "home": home, "away": away,
            "live": {"state": state, "detail": "Q3 4:12", "home_score": 17, "away_score": 14},
            "players": players}


def test_a_live_game_and_a_just_finished_one_are_on_and_a_scheduled_one_is_not():
    now = time.time()
    with tempfile.TemporaryDirectory() as d:
        pbp = Path(d) / "pbp"
        pbp.mkdir()
        chase = {"player": "Ja'Marr Chase", "team": "CIN", "stats": {"receptions": 6, "rec_yds": 94}}
        (pbp / "nfl_1.json").write_text(json.dumps(_doc("nfl", "1", "live", [chase])))
        (pbp / "nba_2.json").write_text(json.dumps(_doc("nba", "2", "final", [
            {"player": "LeBron James", "team": "LAL", "stats": {"pts": 28}}], home="LAL", away="BOS")))
        (pbp / "nba_3.json").write_text(json.dumps(_doc("nba", "3", "scheduled", [
            {"player": "Jayson Tatum", "team": "BOS", "stats": {"pts": 0}}])))
        old = pbp / "mlb_4.json"
        old.write_text(json.dumps(_doc("mlb", "4", "final", [
            {"player": "Pete Alonso", "team": "NYM", "line": {"batting": {"ab": 4, "h": 1}}}])))
        os.utime(old, (now - YP.FINAL_FOR_S - 60,) * 2)
        idx = YP.index(pbp, Path(d) / "none.json", now=now)
        got = idx[YP._fold("ja'marr chase")][0]
        assert got["line"] == "6 rec, 94 yds" and got["status"] == "Q3 4:12" and got["opp"] == "PIT"
        assert got["score"] == "PIT 14–17 CIN" and got["league"] == "nfl" and got["event_id"] == "1"
        assert idx[YP._fold("LeBron James")][0]["status"] == "Final"
        assert YP._fold("Jayson Tatum") not in idx, "a game not started has no line"
        assert YP._fold("Pete Alonso") not in idx, "a final from hours ago has left the strip"


def test_hockey_lines_come_from_the_league_box_and_open_the_espn_game():
    with tempfile.TemporaryDirectory() as d:
        pbp = Path(d) / "pbp"
        pbp.mkdir()
        (pbp / "nhl_401.json").write_text(json.dumps(_doc("nhl", "401", "live", [
            {"player": "Sidney Crosby", "team": "PIT", "stats": {"pts": 0}}], home="PIT", away="NYR")))
        box = Path(d) / "live_nhl_box.json"
        box.write_text(json.dumps({"games": [{"away": "NYR", "home": "PIT", "state": "live", "players": [
            {"player": "Sidney Crosby", "team": "PIT", "stats": {"goals": 2, "assists": 1, "sog": 6}}]}]}))
        rows = YP.index(pbp, box)[YP._fold("Sidney Crosby")]
        assert len(rows) == 1 and rows[0]["line"] == "2 G, 1 A, 6 SOG" and rows[0]["event_id"] == "401"


def test_mine_is_the_members_player_watches_live_games_first():
    idx = {YP._fold("A One"): [{"player": "A One", "state": "final"}],
           YP._fold("B Two"): [{"player": "B Two", "state": "live"}]}
    watches = [{"kind": "player", "value": "a one"}, {"kind": "team", "value": "CIN"},
               {"kind": "player", "value": "B. Two"}, {"kind": "player", "value": "B Two"}]
    assert [r["player"] for r in YP.mine(watches, idx)] == ["B Two", "A One"]
    assert YP.mine([], idx) == []


def test_the_server_and_the_live_tab():
    srv = (ROOT / "server.py").read_text()
    get = srv[srv.index("    def _alerts_get(self, path: str, query: dict | None = None):"):srv.index("    def _alerts_post(")]
    assert get.index("sign in first") < get.index('if path == "live":'), "the member's own watches"
    # And a linked lineup's starters by name (tests/test_your_fantasy_lineup_live.py).
    assert "YP.mine(AL.list_watches(conn, who[\"id\"])," in get
    app = (ROOT / "web" / "js" / "app.js").read_text()
    board = app[app.index("async function renderLiveBoard()"):]
    assert '— every game in progress across the sports we model</span></div><div class="yp-host"></div>' in board
    assert "const ypMount = (host) => _acctUser && _acctUser.signed_in && loadRoom(" in app
    assert '.then((ok) => ok && yourPlayersMount(host.querySelector(".yp-host")));' in app
    quiet = board[board.index("if (!games.length) {"):board.index("const darkWhy")]
    assert 'sports we model</span></div><div class="yp-host"></div>' in quiet and "ypMount(host);" in quiet, \
        "the strip is on with nothing live too: a finished game's lines stay for hours"
    assert "ypMount(host);" in board[board.index("const darkWhy"):], "and with games on"
    chat = (ROOT / "web" / "js" / "chat.js").read_text()
    fn = chat[chat.index("function ypHTML("):chat.index("function ypBind(")]
    assert "chEsc(r.player)" in fn and "chEsc(r.line)" in fn and 'if (!rows.length) return "";' in fn
    mount = chat[chat.index("async function yourPlayersMount("):]
    assert "_acctUser.signed_in" in mount[:200] and '"/api/alerts/live"' in mount[:600]


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
