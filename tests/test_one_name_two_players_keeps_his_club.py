"""One name, two players: a card and a game log keep his club's games (step AFF, 25 November 2026).

The history file keeps a player's games under his name, and the NFL has two Byron Youngs. On the live board on 25
November his Tackles + Assists chart held weeks 6, 7 and 8 twice each, one game from each man (Carolina and Arizona,
Dallas and Las Vegas, Washington and the Chargers), and his game log the same. A player is on one club in a week (or a
day), so a week or day holding two clubs under one name is two men:

  * engine/statlogs.other_clubs names the other man's clubs: those whose games share a week or a day with his;
  * the board's card reads his club's games (the board row's club; a searched name, the club of its newest game), ten
    of them, the other man's left out;
  * the player page's game log asks for his club (`team`) and reads the same games;
  * a player traded between clubs (never two in one week) keeps every game.

Offline. Run directly: `python3 tests/test_one_name_two_players_keeps_his_club.py`
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db, gamelog, statlogs  # noqa: E402


def _rows(player, team, weeks, opp, value, season=2026, market="tackles_ast", pos="LB"):
    return [{"sport": "nfl", "season": season, "period": f"{w:03d}", "game_id": f"{team}-{w:03d}", "player": player,
             "team": team, "opponent": opp(w), "position": pos, "home": w % 2, "market": market,
             "value": float(value(w))} for w in weeks]


def _file():
    path = os.path.join(tempfile.mkdtemp(), "history.db")
    rows = []
    # The Rams' Byron Young, weeks 1-12; the other Byron Young (Philadelphia), weeks 1-11.
    rows += _rows("Byron Young", "LA", range(1, 13), lambda w: f"R{w:02d}", lambda w: 4 + w % 3)
    rows += _rows("Byron Young", "PHI", range(1, 12), lambda w: f"P{w:02d}", lambda w: 1)
    # A man traded mid-season: Las Vegas weeks 1-5, Philadelphia from week 6.
    rows += _rows("Jakobi Meyers", "LV", range(1, 6), lambda w: f"V{w:02d}", lambda w: 50, market="rec_yds", pos="WR")
    rows += _rows("Jakobi Meyers", "PHI", range(6, 12), lambda w: f"E{w:02d}", lambda w: 60, market="rec_yds", pos="WR")
    for team, weeks, tag in (("LV", range(1, 6), "V"), ("PHI", range(6, 12), "E")):
        rows += _rows("Jakobi Meyers", team, weeks, lambda w, t=tag: f"{t}{w:02d}", lambda w: 4, market="receptions",
                      pos="WR")
    conn = db.connect(path)
    db.upsert_player_logs(conn, rows)
    conn.commit()
    conn.close()
    return path


def test_the_other_mans_clubs():
    rows = [(2026, "006", "LA"), (2026, "006", "PHI"), (2026, "007", "LA"), (2026, "007", "PHI"), (2026, "012", "LA")]
    assert statlogs.other_clubs(rows, "LA") == {"PHI"}
    assert statlogs.other_clubs(rows, "PHI") == {"LA"}
    assert statlogs.other_clubs(rows) == {"PHI"}, "no club given: the club of the newest game"
    traded = [(2026, "005", "LV"), (2026, "006", "PHI"), (2026, "007", "PHI")]
    assert statlogs.other_clubs(traded, "PHI") == set() and statlogs.other_clubs(traded) == set()
    assert statlogs.other_clubs(rows, "LAR") == set(), "a club the rows never name drops nothing"
    assert statlogs.other_clubs([]) == set()


def test_the_board_card_reads_his_clubs_ten_games():
    path = _file()
    rec = [{"player": "Byron Young", "team": "LA", "market": "tackles_ast"},
           {"player": "Jakobi Meyers", "team": "PHI", "market": "rec_yds"}]
    board = statlogs.for_board(rec, "nfl", db_path=path)
    logs = board["Byron Young"]["Tackles + Assists"]
    assert [g["week"] for g in logs] == list(range(12, 2, -1)), [g["week"] for g in logs]
    assert all(g["opponent"].startswith("R") for g in logs), "the Rams' man's games only"
    rec[0]["team"] = "PHI"
    other = statlogs.for_board(rec, "nfl", db_path=path)["Byron Young"]["Tackles + Assists"]
    assert [g["week"] for g in other] == list(range(11, 1, -1)) and all(g["opponent"].startswith("P") for g in other)
    meyers = board["Jakobi Meyers"]["Receiving Yards"]
    assert [g["week"] for g in meyers] == list(range(11, 1, -1)), "a traded man keeps every game"


def test_a_searched_name_reads_the_club_of_its_newest_game():
    got = statlogs.for_player("nfl", "Byron Young", db_path=_file())["Tackles + Assists"]
    assert got[0]["week"] == 12 and all(g["opponent"].startswith("R") for g in got)


def test_the_game_log_reads_the_club_the_page_asks_for():
    path = _file()
    la = gamelog.season_log("nfl", "Byron Young", 2026, db_path=path, team="LA")
    phi = gamelog.season_log("nfl", "Byron Young", 2026, db_path=path, team="PHI")
    plain = gamelog.season_log("nfl", "Byron Young", 2026, db_path=path)
    assert len(la["games"]) == 12 and {g["team"] for g in la["games"]} == {"LA"}
    assert len(phi["games"]) == 11 and {g["team"] for g in phi["games"]} == {"PHI"}
    assert plain["games"] == la["games"], "no club asked: the club of the newest game"
    meyers = gamelog.season_log("nfl", "Jakobi Meyers", 2026, db_path=path, team="PHI")
    assert len(meyers["games"]) == 11, "a traded man's season is whole"


def test_the_page_asks_for_his_club():
    gl = (ROOT / "web" / "js" / "gamelog.js").read_text(encoding="utf-8")
    pp = (ROOT / "web" / "js" / "playerpage.js").read_text(encoding="utf-8")
    srv = (ROOT / "server.py").read_text(encoding="utf-8")
    assert "async function glFetch(sport, player, season, team) {" in gl and 'q.set("team", String(team))' in gl
    assert "glFetch(d.sport, d.player, d.season, d.team)" in pp
    assert "glFetch(sport, player, season || (PLR_PICK[key] || {}).log, team)" in pp
    assert 'club = (q.get("team") or [""])[0][:8].strip().upper()' in srv and "team=club or None" in srv


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
