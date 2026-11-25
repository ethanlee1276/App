"""A college game counts once in every read of a player's games (step AFE, 25 November 2026).

The player page's game log has merged a college game's stored copies since 16 November (engine/gamelog.collapse).
The market cards above it did not: on the live college board on 25 November, 112 of 186 market logs held a game
twice. Miami (Ohio)'s 3 November game against Buffalo sat as "BUFF" on the 3rd and as "BUF" on the 4th, Kent State's
game at Sacramento State on 30 and 31 October, a game at Ohio State twice on 19 September, and a receiver's line
beside a copy of him on the other side with nothing caught. Scoop Smith's rushing chart showed 31 yards twice; his game
log, once. The college prop model's form (engine/cfb/props) read the same copies as games.

Now three reads merge as the game log merges (engine/gamelog.games_once):

  * the market cards' logs, on the board and on a searched player's page (engine/statlogs `_query_once`), say the
    game log's games, each once, with its numbers, side and day;
  * the head-to-head (`versus`) says a meeting once;
  * the college prop model's rows (engine/cfb/props `_read_log_rows`) hold each game once, so its last three, five
    and ten are games he played.

Other leagues read as before. Offline. Run directly: `python3 tests/test_a_college_game_counts_once_in_every_read.py`
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db, gamelog, statlogs  # noqa: E402


def _row(player, team, opp, home, period, gid, pos="WR", sport="cfb", season=2026, **stats):
    return [{"sport": sport, "season": season, "period": period, "game_id": gid, "player": player, "team": team,
             "opponent": opp, "position": pos, "home": home, "market": m, "value": float(v)} for m, v in stats.items()]


def _file():
    """A history file holding the live board's four kinds of copy."""
    path = os.path.join(tempfile.mkdtemp(), "history.db")
    rows = []
    # Scoop Smith, Miami (Ohio). Buffalo as "BUFF" (the play file, the Eastern day) and "BUF" (a box copy, the UTC day).
    rows += _row("Scoop Smith", "M-OH", "BUFF", 1, "2026-11-03", "401", rush_yds=31, carries=3)
    rows += _row("Scoop Smith", "M-OH", "BUF", 1, "2026-11-04", "BUF@M-OH-box", rush_yds=31, carries=3)
    # ...and a copy of him on Buffalo's side, nothing caught.
    rows += _row("Scoop Smith", "BUFF", "M-OH", 0, "2026-11-04", "401x", rec_yds=0, receptions=0)
    # At UMass: his line, and a copy on UMass's side with nothing.
    rows += _row("Scoop Smith", "M-OH", "MASS", 0, "2026-10-10", "402", rec_yds=33, receptions=1, rush_yds=20, carries=1)
    rows += _row("Scoop Smith", "MASS", "M-OH", 1, "2026-10-10", "402x", rec_yds=0, receptions=0)
    for d, opp, home, ry, c, rec, yds in (("2026-11-24", "WMU", 0, 19, 3, 2, 46), ("2026-11-18", "KENT", 0, 25, 1, 1, 11),
                                          ("2026-10-24", "CMU", 0, 14, 2, 2, 24), ("2026-10-17", "AKR", 1, 69, 1, 1, 0),
                                          ("2026-09-26", "CONN", 1, 5, 1, 6, 34), ("2026-09-12", "HC", 1, 10, 1, 1, 23)):
        rows += _row("Scoop Smith", "M-OH", opp, home, d, "g" + d, rush_yds=ry, carries=c, receptions=rec, rec_yds=yds)
    # Wayne Harris, Kent State: the game at Sacramento State on two days; Terik Mulder: the game at Ohio State twice.
    rows += _row("Wayne Harris", "KENT", "SAC", 0, "2026-10-30", "403", rec_yds=122, receptions=3, targets=6)
    rows += _row("Wayne Harris", "KENT", "SAC", 0, "2026-10-31", "403b", rec_yds=122, receptions=3, targets=6)
    rows += _row("Terik Mulder", "KENT", "OSU", 0, "2026-09-19", "404", rec_yds=3, receptions=1, targets=2)
    rows += _row("Terik Mulder", "KENT", "OSU", 0, "2026-09-19", "KENT@OSU", rec_yds=3, receptions=1, targets=2)
    for who in ("Wayne Harris", "Terik Mulder"):
        for d, opp, home, yds, rec in (("2026-11-24", "EMU", 0, 21, 2), ("2026-11-18", "M-OH", 1, 17, 1),
                                       ("2026-11-11", "BGSU", 0, 13, 1), ("2026-10-03", "OHIO", 1, 22, 2)):
            rows += _row(who, "KENT", opp, home, d, "k" + d, rec_yds=yds, receptions=rec, targets=rec + 1)
    # An NFL week stored twice under two ids is read as stored: the NFL is not merged here.
    rows += _row("Byron Young", "LA", "SF", 1, "011", "LA-011", pos="LB", sport="nfl", tackles_ast=4)
    rows += _row("Byron Young", "PHI", "DAL", 0, "011", "PHI-011", pos="DT", sport="nfl", tackles_ast=2)
    conn = db.connect(path)
    db.upsert_player_logs(conn, rows)
    conn.commit()
    conn.close()
    return path


def _plain(logs):
    return [(g["date"], g["opponent"], bool(g["home"]), g["value"]) for g in logs]


def test_the_market_logs_say_the_game_logs_games_each_once():
    path = _file()
    for who in ("Scoop Smith", "Wayne Harris", "Terik Mulder"):
        chart = statlogs.for_player("cfb", who, db_path=path)
        log = gamelog.season_log("cfb", who, 2026, db_path=path)
        assert chart and log, who
        for label, logs in chart.items():
            days = [g["date"] for g in logs]
            assert len(days) == len(set(days)), (who, label, days)
        # The game log's games, market by market, in its order, with its numbers.
        cols = {"Rushing Yards": "rushing.yds", "Carries": "rushing.car", "Receiving Yards": "receiving.yds",
                "Receptions": "receiving.rec", "Targets": "receiving.tgt"}
        for label, col in cols.items():
            if label not in chart:
                continue
            want = [(g["date"], g["opponent"], bool(g["home"]), g["values"][col])
                    for g in log["games"] if g["values"].get(col) is not None][:statlogs.N_GAMES]
            assert _plain(chart[label]) == want, (who, label, _plain(chart[label]), want)
    chart = statlogs.for_player("cfb", "Scoop Smith", db_path=path)
    assert [(d, o, v) for d, o, _h, v in _plain(chart["Rushing Yards"])][:3] == [
        ("2026-11-24", "WMU", 19.0), ("2026-11-18", "KENT", 25.0), ("2026-11-03", "BUFF", 31.0)]
    assert ("2026-10-10", "MASS", False, 33.0) in _plain(chart["Receiving Yards"])
    assert not [g for g in chart["Receiving Yards"] if g["opponent"] == "M-OH"], "his copy on the other side"
    assert [g["date"] for g in statlogs.for_player("cfb", "Wayne Harris", db_path=path)["Receiving Yards"]].count(
        "2026-10-30") == 1
    assert "2026-10-31" not in [g["date"] for g in statlogs.for_player("cfb", "Wayne Harris", db_path=path)["Receptions"]]


def test_the_board_reads_the_same_games():
    path = _file()
    board = statlogs.for_board([{"player": "Scoop Smith"}, {"player": "Terik Mulder"}], "cfb", db_path=path)
    assert board["Scoop Smith"] == statlogs.for_player("cfb", "Scoop Smith", db_path=path)
    assert [g["date"] for g in board["Terik Mulder"]["Receptions"]].count("2026-09-19") == 1


def test_a_meeting_is_said_once():
    path = _file()
    for who, opp, day in (("Wayne Harris", "SAC", "2026-10-30"), ("Terik Mulder", "OSU", "2026-09-19")):
        got = statlogs.versus("cfb", who, opp, db_path=path)
        assert [g["date"] for g in got["games"]] == [day], (who, got)
        assert got["games"][0]["stats"]["Receptions"] in (1.0, 3.0)


def test_the_college_models_form_reads_each_game_once():
    from engine.cfb import props as P
    conn = db.connect(_file())
    try:
        out = P._read_log_rows(conn, [2025, 2026])
    finally:
        conn.close()
    scoop = out["M-OH"]["scoop smith"]
    assert [(p, o, v) for p, o, _h, v, _pr in scoop["rush_yds"]][:3] == [
        ("2026-11-24", "WMU", 19.0), ("2026-11-18", "KENT", 25.0), ("2026-11-03", "BUFF", 31.0)]
    for slot in (scoop, out["KENT"]["wayne harris"], out["KENT"]["terik mulder"]):
        for market, rows in slot.items():
            if market in ("player", "position"):
                continue
            days = [r[0] for r in rows]
            assert len(days) == len(set(days)), (market, days)
            assert days == sorted(days, reverse=True), "newest first, as compute_form reads them"
    assert [r[0] for r in out["KENT"]["wayne harris"]["receptions"]].count("2026-10-30") == 1
    assert all(not r[4] for r in scoop["rush_yds"]), "this season's games are not carried ones"


def test_the_nfl_reads_as_stored():
    path = _file()
    got = statlogs.for_player("nfl", "Byron Young", db_path=path)
    assert got == {} or all(len(v) >= 1 for v in got.values())
    src = (ROOT / "engine" / "statlogs.py").read_text(encoding="utf-8")
    assert "if sport in ONE_A_WEEK:\n        return _query_once(conn, sport, markets, players)" in src
    assert gamelog.ONE_A_WEEK == ("cfb",)


def test_each_read_is_keyed_on_the_merge_it_reads_through():
    props = (ROOT / "engine" / "cfb" / "props.py").read_text(encoding="utf-8")
    assert "code=(__file__, oddsapi.__file__, gamelog.__file__)" in props
    src = (ROOT / "engine" / "statlogs.py").read_text(encoding="utf-8")
    assert "code=(__file__, gamelog.__file__)" in src


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
