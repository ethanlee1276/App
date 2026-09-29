"""closerepair.py: settled NFL closes rebuilt from pregame prices only.

Ethan, 2026-09-29: "Yes, repair the closes" — after the close check showed
the NFL "closes" were in-game lines. The repair places each settled NFL
prop on its game (our stat logs give his team that week, the schedule its
kickoff, Eastern), reads only quotes from the week before that kickoff,
and rewrites closing_line / closing_odds — never a grade. Dry run by
default; --apply keeps the old values in a file first.

Fixture ledger, history DB and snapshots in a temp directory — never the box's.

Run directly: `python3 tests/test_the_close_repair_keeps_only_pregame_prices.py`
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import closerepair as CR                                         # noqa: E402
from engine import db, ledger                                    # noqa: E402

SCHEDULE = [{"season": "2026", "week": "3", "gameday": "2026-09-27", "gametime": "16:25",
             "home_team": "SEA", "away_team": "CIN"},
            {"season": "2026", "week": "3", "gameday": "2026-09-28", "gametime": "20:15",
             "home_team": "CHI", "away_team": "PHI"}]
KICK_SEA = CR.kickoff_epoch("2026-09-27", "16:25")      # 20:25 UTC Sunday
KICK_CHI = CR.kickoff_epoch("2026-09-28", "20:15")


def _fixtures():
    tmp = Path(tempfile.mkdtemp())
    conn = ledger.connect(tmp / "ledger.db")
    rows = [
        # (player, market, side, line, status, closing_line, closing_odds, category)
        ("AJ Barner", "rec_yds", "UNDER", 19.5, "lost", 69.5, None, "board"),         # in-game close
        ("Joe Burrow", "pass_yds", "UNDER", 255.5, "lost", 349.5, None, "likely_live"),
        ("Colston Loveland", "rec_yds", "UNDER", 29.5, "lost", 59.5, -110, "board"),  # Monday night
        ("Nobody Known", "receptions", "OVER", 3.5, "won", 2.5, None, "board"),       # no stat log
        ("SEA", "moneyline", "OVER", 0.5, "won", None, None, "likely"),               # game market
        ("Open Guy", "rec_yds", "OVER", 30.5, "open", None, None, "board"),           # not settled
    ]
    for player, market, side, line, status, cl, co, cat in rows:
        conn.execute("INSERT INTO bets (ts, sport, date, player, market, side, line, odds, hit_prob, "
                     "stake_units, status, pnl_units, closing_line, closing_odds, category) VALUES "
                     "('t','nfl','2026-W03',?,?,?,?,-110,0.6,0.1,?,0,?,?,?)",
                     (player, market, side, line, status, cl, co, cat))
    conn.commit()
    h = db.connect(tmp / "history.db")
    h.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, market, value) "
                  "VALUES ('nfl', 2026, ?, ?, ?, ?, ?, ?)",
                  [("003", "g1", "AJ Barner", "SEA", "rec_yds", 69),
                   ("003", "g1", "Joe Burrow", "CIN", "pass_yds", 282),
                   ("003", "g2", "Colston Loveland", "CHI", "rec_yds", 31)])
    h.commit()
    snaps = [
        # Barner: pregame 19.5 at two books, then the in-game 69.5 three hours in.
        {"ts": KICK_SEA - 3600, "player": "AJ Barner", "market": "rec_yds", "book": "fd",
         "line": 19.5, "over_odds": -110, "under_odds": -115},
        {"ts": KICK_SEA - 3600, "player": "AJ Barner", "market": "rec_yds", "book": "dk",
         "line": 20.5, "over_odds": -110, "under_odds": -110},
        {"ts": KICK_SEA + 3 * 3600, "player": "AJ Barner", "market": "rec_yds", "book": "fd",
         "line": 69.5, "over_odds": -110, "under_odds": -110},
        # Burrow: only an in-game quote — no pregame close at all.
        {"ts": KICK_SEA + 7200, "player": "Joe Burrow", "market": "pass_yds", "book": "fd",
         "line": 349.5, "over_odds": -110, "under_odds": -110},
        # Loveland: two pregame quotes; the later one is the close. Then in-game.
        {"ts": KICK_CHI - 86400, "player": "Colston Loveland", "market": "rec_yds", "book": "fd",
         "line": 28.5, "over_odds": -110, "under_odds": -110},
        {"ts": KICK_CHI - 1800, "player": "Colston Loveland", "market": "rec_yds", "book": "fd",
         "line": 29.5, "over_odds": -120, "under_odds": +100},
        {"ts": KICK_CHI + 5400, "player": "Colston Loveland", "market": "rec_yds", "book": "fd",
         "line": 59.5, "over_odds": -110, "under_odds": -110},
        # A quote from last season for the same man — far outside the week.
        {"ts": KICK_CHI - 400 * 86400, "player": "Colston Loveland", "market": "rec_yds",
         "book": "fd", "line": 12.5, "over_odds": -110, "under_odds": -110},
    ]
    return tmp, conn, h, snaps


def test_only_pregame_quotes_make_the_close():
    _tmp, conn, h, snaps = _fixtures()
    p = CR.plan(conn, h, SCHEDULE, snaps, [])
    by = {c["player"]: c for c in p["changes"]}
    assert by["AJ Barner"]["new_line"] == 20.0            # median of 19.5 and 20.5 at the last pregame instant
    assert by["AJ Barner"]["new_odds"] == -115            # his UNDER, at his 19.5
    assert by["Joe Burrow"]["new_line"] is None and by["Joe Burrow"]["new_odds"] is None, \
        "an in-game quote alone is no close"
    assert by["Colston Loveland"]["new_line"] == 29.5 and by["Colston Loveland"]["new_odds"] == 100
    assert "Nobody Known" not in by and "SEA" not in by and "Open Guy" not in by
    assert [r for _b, r in p["unplaced"]] == ["no stat log for him that week"]
    assert p["examined"] == 4 and p["placed"] == 3


def test_the_dry_run_writes_nothing_and_lists_every_change():
    tmp, conn, h, snaps = _fixtures()
    before = [tuple(r) for r in conn.execute("SELECT closing_line, closing_odds FROM bets ORDER BY id")]
    text = CR.render(CR.plan(conn, h, SCHEDULE, snaps, []))
    after = [tuple(r) for r in conn.execute("SELECT closing_line, closing_odds FROM bets ORDER BY id")]
    assert before == after
    assert "AJ Barner" in text and "line   69.5 → 20" in text
    assert "'lost the close' goes from 0-3 to 0-1" in text   # Barner's under: 19.5 → 20 is still against him


def test_apply_writes_the_closes_and_keeps_the_old_ones():
    tmp, conn, h, snaps = _fixtures()
    p = CR.plan(conn, h, SCHEDULE, snaps, [])
    path = CR.apply_changes(conn, p["changes"], tmp / "backups")
    got = dict(conn.execute("SELECT player, closing_line FROM bets").fetchall())
    assert got["AJ Barner"] == 20.0 and got["Joe Burrow"] is None and got["Colston Loveland"] == 29.5
    assert got["Nobody Known"] == 2.5, "an unplaced bet is left as it was"
    saved = json.loads(path.read_text())
    assert {s["closing_line"] for s in saved} == {69.5, 349.5, 59.5}
    # Grades untouched.
    assert dict(conn.execute("SELECT player, status FROM bets").fetchall())["AJ Barner"] == "lost"
    # A second plan finds nothing left to change.
    assert CR.plan(conn, h, SCHEDULE, snaps, [])["changes"] == []


def test_a_harvested_price_counts_only_before_kickoff():
    _tmp, conn, h, snaps = _fixtures()
    import datetime as dt
    iso = lambda e: dt.datetime.fromtimestamp(e, dt.timezone.utc).isoformat()
    harvested = [{"player": "Joe Burrow", "market": "pass_yds", "taken_at": iso(KICK_SEA - 600),
                  "line": 262.5, "over_odds": -115, "under_odds": -105},
                 {"player": "Joe Burrow", "market": "pass_yds", "taken_at": iso(KICK_SEA + 600),
                  "line": 270.5, "over_odds": -115, "under_odds": -105}]
    by = {c["player"]: c for c in CR.plan(conn, h, SCHEDULE, snaps, harvested)["changes"]}
    assert by["Joe Burrow"]["new_line"] == 262.5


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
