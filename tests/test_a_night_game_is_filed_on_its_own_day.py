"""A college night game is filed on its own day, once (step AHV, 26 November 2026).

The nightly count (step AFG, heartbeat cfb_copies) found 25,028 college stat rows on 25 November that copied a
game already on file, eleven days after the 14 November cleanup removed 130,078. The biggest kind, 17,401 rows,
was one game a day apart under the same two teams and the same ESPN number (A'Marion Peterson's UTSA at Texas on
09-19 and 09-20). The writer:

  * the mirror's schedule (engine/sources/cfbfastr) dated a game by its UTC day, so a Saturday night kickoff sat
    in the games table on Sunday beside the scoreboard's Saturday row, and only the mirror's row named the ESPN
    number the play file joins on (engine/ingest.cfb_games_for). The nightly play file filed every night game
    under Sunday again, beside the Saturday rows the cleanup kept.

What holds now:

  * the mirror dates a game on its US Eastern day, the scoreboard's (`cfbfastr._date`);
  * the ESPN number joins the game's earliest day when an older row of the same pair stands a day or less before;
  * the box-score backfill reads each game once, under its ESPN number, on its earliest day
    (`cfbdata.one_row_a_game`), where it read one copy for every games row (and none at all for an away@home key);
  * the cleanup also takes one game under another code for one side (BUF and BUFF), and still leaves two players
    of one name apart ("the other side", "other");
  * the nightly count says how many copies are of games played since the cleanup, and each kind's newest example.

    python3 tests/test_a_night_game_is_filed_on_its_own_day.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import cfbdedupe, db  # noqa: E402


def test_the_mirror_dates_a_night_game_on_its_eastern_day():
    from engine.sources import cfbfastr as C
    assert C._date("2026-09-20T00:30:00.000Z") == "2026-09-19", "8:30 pm Eastern on Saturday"
    assert C._date("2026-11-29T03:30:00Z") == "2026-11-28", "10:30 pm Eastern, standard time"
    assert C._date("2026-09-19T16:00:00.000Z") == "2026-09-19"
    assert C._date("2026-09-19") == "2026-09-19", "a date alone is kept"
    assert C._date("") == "" and C._date(None) == ""
    row = {"game_id": "401856693", "season": "2026", "week": "4", "season_type": "regular",
           "start_date": "2026-09-20T00:30:00.000Z", "completed": "TRUE", "neutral_site": "FALSE",
           "home_id": "251", "home_team": "Texas", "home_division": "fbs", "home_points": "38",
           "away_id": "2636", "away_team": "UTSA", "away_division": "fbs", "away_points": "17"}
    g = C.parse_schedule([row], 2026)["games"][0]
    assert g["period"] == "2026-09-19", g


def _games_file(rows):
    path = os.path.join(tempfile.mkdtemp(), "history.db")
    conn = db.connect(path)
    db.upsert_games(conn, rows)
    conn.commit()
    return conn


def _game(period, gid, extra=None, home="TEX", away="UTSA"):
    return {"sport": "cfb", "season": 2026, "period": period, "game_id": gid, "home": home, "away": away,
            "home_score": 38.0, "away_score": 17.0, "extra": json.dumps(extra or {})}


def test_the_espn_number_joins_the_games_earliest_day():
    from engine.ingest import cfb_games_for
    conn = _games_file([
        # The scoreboard's Saturday row, rekeyed to away@home overnight; it names no ESPN number.
        _game("2026-09-19", "UTSA@TEX", {"week": 4}),
        # The mirror's Sunday row from before this step, which does.
        _game("2026-09-20", "UTSA@TEX", {"espn_game_id": "401856693"}),
        # A rematch three weeks later is its own game.
        _game("2026-10-11", "UTSA@TEX", {"espn_game_id": "401856999"}),
        # A game only the mirror has stands on its own day.
        _game("2026-09-27", "RICE@TEX", {"espn_game_id": "401856700"}, away="RICE"),
    ])
    try:
        got = cfb_games_for(conn, 2026)
    finally:
        conn.close()
    assert got["401856693"]["period"] == "2026-09-19", got["401856693"]
    assert got["UTSA@TEX"]["period"] == "2026-09-19"
    assert got["401856999"]["period"] == "2026-10-11"
    assert got["401856700"]["period"] == "2026-09-27"


def test_the_box_score_backfill_reads_each_game_once_on_its_earliest_day():
    from engine.sources import cfbdata as D
    conn = _games_file([
        _game("2026-09-19", "UTSA@TEX", {"week": 4}),
        _game("2026-09-20", "UTSA@TEX", {"espn_game_id": "401856693"}),
        _game("2026-09-19", "401856694", home="OU", away="SMU"),
        _game("2026-09-26", "KENT@OSU", {"week": 5}, home="OSU", away="KENT"),
    ])
    try:
        rows = conn.execute("SELECT game_id, period, home, away, extra FROM games WHERE sport='cfb' "
                            "ORDER BY period, game_id").fetchall()
        got = D.one_row_a_game(rows)
        assert got == [{"game_id": "401856694", "period": "2026-09-19", "home": "OU", "away": "SMU"},
                       {"game_id": "401856693", "period": "2026-09-19", "home": "TEX", "away": "UTSA"}], got
        asked = []
        real = D.fetch_summary, D.parse_summary
        D.fetch_summary = lambda eid: asked.append(eid) or {}
        D.parse_summary = lambda payload: [{"player": "A'Marion Peterson", "team": "UTSA", "position": "RB",
                                            "stats": {"rush_att": 5.0}}]
        try:
            res = D.ingest_player_logs(conn, "2026-09-01", "2026-09-30", quiet=True)
        finally:
            D.fetch_summary, D.parse_summary = real
        assert sorted(asked) == ["401856693", "401856694"], asked
        assert res["games"] == 2
        logs = conn.execute("SELECT period, game_id FROM player_game_logs WHERE sport='cfb' "
                            "AND player=\"A'Marion Peterson\" ORDER BY game_id").fetchall()
        assert [tuple(r) for r in logs] == [("2026-09-19", "401856693"), ("2026-09-19", "401856694")], \
            [tuple(r) for r in logs]
    finally:
        conn.close()


def _log(player, team, opp, period, gid, market="rush_yds", value=10.0):
    return {"sport": "cfb", "season": 2026, "period": period, "game_id": gid, "player": player, "team": team,
            "opponent": opp, "position": "RB", "home": 1, "market": market, "value": value}


def _logs_file():
    path = os.path.join(tempfile.mkdtemp(), "history.db")
    conn = db.connect(path)
    db.upsert_player_logs(conn, [
        # The night game a day apart, same teams: the Saturday row stays.
        _log("A'Marion Peterson", "UTSA", "TEX", "2026-09-19", "401856693"),
        _log("A'Marion Peterson", "UTSA", "TEX", "2026-09-20", "401856693"),
        # The opponent under another code.
        _log("Scoop Smith", "M-OH", "BUFF", "2026-11-03", "401858249"),
        _log("Scoop Smith", "M-OH", "BUF", "2026-11-04", "BUF@M-OH-box"),
        # His school under another code.
        _log("Ty Buffalo", "BUF", "WMU", "2026-10-03", "WMU@BUF-box"),
        _log("Ty Buffalo", "BUFF", "WMU", "2026-10-03", "401858004"),
        # The other side: can be two players of one name, so both stay.
        _log("Dru DeShields", "KENT", "AKR", "2026-10-24", "401858003", market="pass_yds", value=294.0),
        _log("Dru DeShields", "AKR", "KENT", "2026-10-24", "401858003x", market="pass_yds", value=19.0),
        # Other: neither school nor opponent shared, two players of one name, both stay.
        _log("Chris Jones", "OSU", "MICH", "2026-11-21", "401858100-box"),
        _log("Chris Jones", "TEX", "TAMU", "2026-11-22", "401858101-box"),
        # A copy of a game played since the cleanup.
        _log("Wayne Harris", "KENT", "OHIO", "2026-11-18", "401858300", market="rec_yds"),
        _log("Wayne Harris", "KENT", "OHIO", "2026-11-19", "401858300", market="rec_yds"),
    ])
    conn.commit()
    return conn


def test_the_cleanup_takes_one_game_under_another_code_and_leaves_two_players_apart():
    conn = _logs_file()
    try:
        plan = cfbdedupe.plan_logs(conn, 2026)
        kept = lambda: {tuple(r) for r in conn.execute(  # noqa: E731
            "SELECT player, team, opponent, period FROM player_game_logs WHERE sport='cfb'")}
        assert plan["by_kind"] == {"same teams": 2, "another code": 2}, plan["by_kind"]
        assert len(plan["delete"]) == 4 and plan["groups"] == 4
        cfbdedupe.apply(conn, plan, {"delete": [], "fill": []})
        left = kept()
        assert ("A'Marion Peterson", "UTSA", "TEX", "2026-09-19") in left
        assert ("A'Marion Peterson", "UTSA", "TEX", "2026-09-20") not in left
        assert ("Scoop Smith", "M-OH", "BUFF", "2026-11-03") in left, "the official row stays"
        assert ("Ty Buffalo", "BUFF", "WMU", "2026-10-03") in left and ("Ty Buffalo", "BUF", "WMU", "2026-10-03") \
            not in left, "ESPN's row before the box copy"
        assert {("Dru DeShields", "KENT", "AKR", "2026-10-24"), ("Dru DeShields", "AKR", "KENT", "2026-10-24"),
                ("Chris Jones", "OSU", "MICH", "2026-11-21"), ("Chris Jones", "TEX", "TAMU", "2026-11-22")} <= left
        assert len(left) == 8, left
    finally:
        conn.close()


def test_the_nightly_count_says_the_copies_since_the_cleanup():
    conn = _logs_file()
    try:
        got = cfbdedupe.census(conn, 2026)
    finally:
        conn.close()
    assert cfbdedupe.CLEANED == "2026-11-14"
    assert got["since"] == {"day": "2026-11-14", "copies": 2,
                            "kinds": {"a day apart, same teams": 1, "other": 1}}, got["since"]
    assert got["latest"]["a day apart, same teams"] == (
        "Wayne Harris, rec_yds, 2026-11-18: 401858300 (KENT v OHIO) and 401858300 on 2026-11-19 (KENT v OHIO)"), \
        got["latest"]
    launch = (ROOT / "launch.py").read_text(encoding="utf-8")
    assert '"since", "latest") if k in doc}' in launch


def test_the_writers_say_why():
    src = (ROOT / "engine" / "sources" / "cfbfastr.py").read_text(encoding="utf-8")
    assert "THE SAME DAY AS THE SCOREBOARD'S (step AHV" in src
    src = (ROOT / "engine" / "ingest.py").read_text(encoding="utf-8")
    assert "THE ESPN NUMBER JOINS THE GAME'S EARLIEST DAY TOO (step AHV" in src
    src = (ROOT / "engine" / "sources" / "cfbdata.py").read_text(encoding="utf-8")
    assert "for g in one_row_a_game(rows):" in src


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    fails = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as exc:                              # noqa: BLE001
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
