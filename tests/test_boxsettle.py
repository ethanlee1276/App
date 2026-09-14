"""Football props grade the night the game ends, off the box score.

Ethan, Tuesday 2026-09-15: "I still see some edge bets not graded from
last nights nfl games." A prop graded only from nflverse's weekly file
(the next morning) or the college Monday backfill, while the box score
sat on the play-by-play page twelve seconds after the whistle.
"""

import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import boxsettle as B, db, ledger  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TODAY = dt.date.today()
YESTERDAY = (TODAY - dt.timedelta(days=1)).isoformat()


def _world():
    t = Path(tempfile.mkdtemp())
    L = ledger.connect(t / "l.db")
    ledger.configure_bankroll(L, starting=1000, unit_pct=1)
    H = db.connect(t / "h.db")
    return L, H


def _bet(L, sport, date, player, market="rec_yds", line=60.5, game_day=""):
    L.execute(
        "INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, "
        "odds, stake_units, stake_dollars, status, category) VALUES "
        "(?, ?, ?, ?, ?, ?, 'OVER', ?, -110, 1, 10, 'open', 'main')",
        (f"{YESTERDAY}T12:00:00", sport, date, game_day, player, market, line))
    L.commit()


def _game(H, sport, season, period, game_id, home, away, date, final=True, extra=None):
    H.execute(
        "INSERT INTO games (sport, season, period, game_id, date, home, away, "
        "home_score, away_score, extra) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (sport, season, period, game_id, date, home, away,
         24.0 if final else None, 20.0 if final else None,
         json.dumps(extra) if extra else None))
    H.commit()


def _team(abbr, tid, name):
    return {"abbreviation": abbr, "id": tid, "displayName": name}


def _nfl_summary():
    return {"boxscore": {"players": [
        {"team": _team("DET", "8", "Detroit Lions"), "statistics": [
            {"name": "receiving", "labels": ["REC", "YDS", "AVG", "TD", "LONG", "TGTS"],
             "athletes": [{"athlete": {"displayName": "Amon-Ra St. Brown",
                                       "position": {"abbreviation": "WR"}},
                           "stats": ["7", "81", "11.6", "1", "24", "9"]}]},
            {"name": "rushing", "labels": ["CAR", "YDS", "AVG", "TD", "LONG"],
             "athletes": [{"athlete": {"displayName": "Jahmyr Gibbs",
                                       "position": {"abbreviation": "RB"}},
                           "stats": ["19", "94", "4.9", "0", "22"]}]}]},
        {"team": _team("KC", "12", "Kansas City Chiefs"), "statistics": [
            {"name": "receiving", "labels": ["REC", "YDS", "AVG", "TD", "LONG", "TGTS"],
             "athletes": [{"athlete": {"displayName": "Travis Kelce",
                                       "position": {"abbreviation": "TE"}},
                           "stats": ["4", "38", "9.5", "0", "15", "6"]}]}]}]}}


def _fetchers(payload, rows=None):
    calls = {"rows": 0, "summary": []}
    def fetch_rows(league):
        calls["rows"] += 1
        return rows or [{"away": "KC", "home": "DET", "event_id": "401777"}]
    def fetch_summary(league, eid):
        calls["summary"].append((league, eid))
        return payload
    return calls, fetch_rows, fetch_summary


def test_a_finished_nfl_game_grades_its_props_off_the_box_score():
    L, H = _world()
    _bet(L, "nfl", "2026-W02", "Amon-Ra St. Brown", game_day=YESTERDAY)
    _game(H, "nfl", 2026, "002", "KC@DET", "DET", "KC", YESTERDAY)
    calls, fr, fs = _fetchers(_nfl_summary())
    res = B.ingest_for_open(L, H, "nfl", log=lambda *a: None, fetch_rows=fr, fetch_summary=fs)
    assert res["games"] == 1 and res["rows"] >= 3, res
    assert calls["summary"] == [("nfl", "401777")]
    rows = H.execute("SELECT game_id, market, value FROM player_game_logs "
                     "WHERE sport='nfl' AND player='Amon-Ra St. Brown' ORDER BY market").fetchall()
    assert {r["game_id"] for r in rows} == {"DET-002-box"}, [dict(r) for r in rows]
    got = {r["market"]: r["value"] for r in rows}
    assert got["rec_yds"] == 81 and got["receptions"] == 7 and got["anytime_td"] == 1
    # The settler grades it on the same pass, and the bet is a winner.
    assert ledger.settle_from_history(L, H) == 1
    assert L.execute("SELECT status, actual FROM bets").fetchone()["status"] == "won"
    # Nothing open: nothing fetched.
    res2 = B.ingest_for_open(L, H, "nfl", log=lambda *a: None, fetch_rows=fr, fetch_summary=fs)
    assert res2 == {"games": 0, "rows": 0, "purged": 0, "skipped": []}
    assert calls["summary"] == [("nfl", "401777")]


def test_the_official_file_replaces_the_provisional_rows():
    L, H = _world()
    _bet(L, "nfl", "2026-W02", "Amon-Ra St. Brown", game_day=YESTERDAY)
    _game(H, "nfl", 2026, "002", "KC@DET", "DET", "KC", YESTERDAY)
    calls, fr, fs = _fetchers(_nfl_summary())
    B.ingest_for_open(L, H, "nfl", log=lambda *a: None, fetch_rows=fr, fetch_summary=fs)
    assert H.execute("SELECT COUNT(*) FROM player_game_logs WHERE game_id LIKE '%-box'").fetchone()[0] > 0
    # nflverse lands: the same game, keyed the official way.
    db.upsert_player_logs(H, [{"sport": "nfl", "season": 2026, "period": "002",
                               "game_id": "DET-002", "player": "Amon-Ra St. Brown",
                               "team": "DET", "opponent": "KC", "position": "WR",
                               "home": 1, "market": "rec_yds", "value": 83.0}])
    res = B.ingest_for_open(L, H, "nfl", log=lambda *a: None, fetch_rows=fr, fetch_summary=fs)
    assert res["purged"] > 0 and res["games"] == 0, res
    assert H.execute("SELECT COUNT(*) FROM player_game_logs WHERE game_id LIKE '%-box'").fetchone()[0] == 0
    assert calls["summary"] == [("nfl", "401777")], "a game with official rows was fetched again"
    # One source on disk: the settler sees one row, the official one.
    assert ledger.settle_from_history(L, H) == 1
    assert L.execute("SELECT actual FROM bets").fetchone()["actual"] == 83.0


def test_only_finished_games_with_open_props_are_fetched():
    L, H = _world()
    _bet(L, "nfl", "2026-W02", "Amon-Ra St. Brown", game_day=YESTERDAY)
    _game(H, "nfl", 2026, "002", "KC@DET", "DET", "KC", YESTERDAY, final=False)   # in play
    _game(H, "nfl", 2026, "002", "NE@SEA", "SEA", "NE", YESTERDAY)                # final, same week
    old = (TODAY - dt.timedelta(days=20)).isoformat()
    _game(H, "nfl", 2026, "001", "X@Y", "Y", "X", old)                            # final, outside the lookback
    recent = (TODAY - dt.timedelta(days=5)).isoformat()
    _game(H, "nfl", 2026, "001", "A@B", "B", "A", recent)                         # final, in reach, no open prop
    calls, fr, fs = _fetchers(_nfl_summary(), rows=[
        {"away": "KC", "home": "DET", "event_id": "401777"},
        {"away": "NE", "home": "SEA", "event_id": "401778"},
        {"away": "A", "home": "B", "event_id": "401700"}])
    res = B.ingest_for_open(L, H, "nfl", log=lambda *a: None, fetch_rows=fr, fetch_summary=fs)
    assert [e for _, e in calls["summary"]] == ["401778"], calls
    assert "no stat lines" in " ".join(res["skipped"]) or res["games"] == 0
    # A game bet is not a prop: it never triggers a summary fetch.
    L.execute("DELETE FROM bets"); L.commit()
    _bet(L, "nfl", "2026-W02", "SEA", market="spread", line=-3.5, game_day=YESTERDAY)
    calls2, fr2, fs2 = _fetchers(_nfl_summary())
    B.ingest_for_open(L, H, "nfl", log=lambda *a: None, fetch_rows=fr2, fetch_summary=fs2)
    assert calls2["summary"] == []


def test_college_rows_are_keyed_like_the_backfill_and_grade():
    from engine.sources.cfbdata import _team_key
    mich, osu = _team("MICH", "130", "Michigan Wolverines"), _team("OSU", "194", "Ohio State Buckeyes")
    home, away = _team_key(mich), _team_key(osu)
    L, H = _world()
    _bet(L, "cfb", YESTERDAY, "Donovan Edwards", market="rush_yds", line=70.5, game_day=YESTERDAY)
    _game(H, "cfb", 2026, YESTERDAY, "401999", home, away, YESTERDAY,
          extra={"espn_game_id": "401999"})
    payload = {"boxscore": {"players": [
        {"team": mich, "statistics": [
            {"name": "rushing", "labels": ["CAR", "YDS", "AVG", "TD", "LONG"],
             "athletes": [{"athlete": {"displayName": "Donovan Edwards",
                                       "position": {"abbreviation": "RB"}},
                           "stats": ["18", "112", "6.2", "2", "41"]}]}]},
        {"team": osu, "statistics": [
            {"name": "receiving", "labels": ["REC", "YDS", "AVG", "TD", "LONG"],
             "athletes": [{"athlete": {"displayName": "Some Receiver",
                                       "position": {"abbreviation": "WR"}},
                           "stats": ["5", "60", "12.0", "0", "20"]}]}]}]}}
    calls, fr, fs = _fetchers(payload)
    res = B.ingest_for_open(L, H, "cfb", log=lambda *a: None, fetch_rows=fr, fetch_summary=fs)
    assert res["games"] == 1, res
    assert calls["summary"] == [("cfb", "401999")] and calls["rows"] == 0, \
        "the schedule kept the ESPN id; the scoreboard was not needed"
    rows = {r["market"]: r for r in H.execute(
        "SELECT * FROM player_game_logs WHERE sport='cfb' AND player='Donovan Edwards'")}
    assert rows["rush_yds"]["game_id"] == "401999-box"
    assert rows["rush_yds"]["period"] == YESTERDAY and rows["rush_yds"]["team"] == home
    assert rows["anytime_td"]["value"] == 2.0
    assert ledger.settle_from_history(L, H) == 1
    assert L.execute("SELECT status FROM bets").fetchone()["status"] == "won"


def test_the_settle_loop_reads_the_box_score_after_the_finals():
    src = open(os.path.join(ROOT, "engine", "maintenance.py"), encoding="utf-8").read()
    i = src.index("def ingest_for_open_bets(")
    body = src[i:src.index("\ndef ", i + 1)]
    assert "boxsettle.ingest_for_open(lconn, hconn, league, log=log)" in body
    assert body.index("livescores.ingest_finals(") < body.index("boxsettle.ingest_for_open(")
    assert body.index("boxsettle.ingest_for_open(") < body.rindex("return res")
    # Isolated per league: one feed's failure never skips the other's.
    tail = body[body.index("boxsettle.ingest_for_open("):]
    assert "except Exception as exc:" in tail


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
