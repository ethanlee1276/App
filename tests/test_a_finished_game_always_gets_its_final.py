"""A finished game always gets its final: a past day with a game that has no
final is read again (engine/maintenance.reread_days_without_final), FINALS1.

Found on the Nuggets' team page on 17 November 2026: 7-5 by the standings, 6-5
by the finals on file. Their game at Phoenix on 30 October, a late West Coast
tip, had a row and no score; so did the Lakers at the Warriors that night and
the Bruins at Anaheim on 16 October. A league's night resumes from its newest
day with a final, and the settle pass files finals during the day for the games
bets ride on, so by the next night a later day already had finals and the day
with the late game was never read again. What these hold:

  * the days read again are the ones, inside the window and before the
    night's own start, on which a stored game has no final: oldest first, a few
    a night, never a day already read too often (a postponed game never gets a
    score), never a week label;
  * each read is counted in the chores' state, days that left the window are
    forgotten, and a read that fails is said and the night goes on;
  * every daily league's night does it: MLB, the NBA, the WNBA, college
    basketball and the NHL.

    python3 tests/test_a_finished_game_always_gets_its_final.py
"""
import datetime as dt
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db, maintenance as M                                     # noqa: E402

TODAY = dt.date(2026, 11, 18)


def _games(*rows):
    c = db.connect(":memory:")
    c.executemany("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score) "
                  "VALUES (?,?,?,?,?,?,?,?)",
                  [(sp, 2026, day, f"{a}@{h}-{day}", h, a, hs, as_) for (sp, day, h, a, hs, as_) in rows])
    c.commit()
    return c


def test_the_days_read_again_are_the_ones_with_a_game_and_no_final():
    c = _games(("nba", "2026-10-30", "PHX", "DEN", None, None), ("nba", "2026-10-30", "BOS", "NYK", 110, 104),
               ("nba", "2026-11-02", "GSW", "LAL", 120, 118), ("nba", "2026-11-05", "MIA", "HOU", None, None),
               ("nba", "2026-09-10", "OKC", "SAS", None, None),           # outside the window
               ("nba", "2026-11-17", "DEN", "PHX", None, None),           # the night's own range reads it
               ("nhl", "2026-10-30", "ANA", "BOS", None, None),
               ("nfl", "010", "NYJ", "BUF", None, None))
    days = M.days_without_final(c, "nba", dt.date(2026, 11, 17), TODAY, {})
    assert days == [dt.date(2026, 10, 30), dt.date(2026, 11, 5)], days
    assert M.days_without_final(c, "nba", dt.date(2026, 11, 17), TODAY, {"nba:2026-10-30": M.REREAD_TRIES}) == \
        [dt.date(2026, 11, 5)], "a day read too often is left alone"
    assert M.days_without_final(c, "nfl", dt.date(2026, 11, 17), TODAY, {}) == [], "a week label is no day"
    assert M.days_without_final(None, "nba", dt.date(2026, 11, 17), TODAY, {}) == []
    many = _games(*[("nhl", f"2026-11-{d:02d}", "ANA", "BOS", None, None) for d in range(1, 12)])
    assert len(M.days_without_final(many, "nhl", dt.date(2026, 11, 17), TODAY, {})) == M.REREAD_DAYS_PER_NIGHT


def test_a_read_files_the_final_and_is_counted():
    c = _games(("nba", "2026-10-30", "PHX", "DEN", None, None))
    state = {"final_rereads": {"nba:2026-09-01": 2}}
    asked, said = [], []

    def ingest(day):
        asked.append(day)
        c.execute("UPDATE games SET home_score=112, away_score=105 WHERE sport='nba' AND period=?", (day,))
        return {"games": 1, "player_logs": 30}
    got = M.reread_days_without_final(state, c, "nba", dt.date(2026, 11, 17), TODAY, ingest, said.append)
    assert asked == ["2026-10-30"] and got == 1
    assert state["final_rereads"] == {"nba:2026-10-30": 1}, "counted, and a day out of the window forgotten"
    assert said == ["  nba results: read again 2026-10-30 (a game there had no final): 1 game(s)"], said
    assert M.reread_days_without_final(state, c, "nba", dt.date(2026, 11, 17), TODAY, ingest, said.append) == 0
    assert asked == ["2026-10-30"], "the final is on file: nothing to read again"


def test_a_failed_read_is_said_and_the_night_goes_on():
    c = _games(("nhl", "2026-10-22", "ANA", "BOS", None, None), ("nhl", "2026-10-25", "LAK", "EDM", None, None))
    said = []

    def ingest(day):
        if day == "2026-10-22":
            raise RuntimeError("the feed said 503")
        return {"games": 1}
    state: dict = {}
    assert M.reread_days_without_final(state, c, "nhl", dt.date(2026, 11, 17), TODAY, ingest, said.append) == 1
    assert said[0].startswith("  ⚠️  nhl results: 2026-10-22 read again") and "503" in said[0], said
    assert state["final_rereads"] == {"nhl:2026-10-22": 1, "nhl:2026-10-25": 1}
    # Three nights of a postponed game, and then it is left alone.
    for _ in range(2):
        M.reread_days_without_final(state, c, "nhl", dt.date(2026, 11, 17), TODAY, ingest, said.append)
    assert M.days_without_final(c, "nhl", dt.date(2026, 11, 17), TODAY, state["final_rereads"]) == []


def test_a_hockey_game_with_no_row_at_all_is_found_on_the_club_pages():
    from engine.sources import nhldata as N
    c = _games(("nhl", "2026-10-16", "ANA", "BOS", None, None), ("nhl", "2026-10-15", "MTL", "TOR", 3, 2))
    pages = {"MTL": {"games": [
        {"gameType": 2, "gameState": "OFF", "gameDate": "2026-10-15", "homeTeam": {"abbrev": "MTL"},
         "awayTeam": {"abbrev": "TOR"}},                                   # on file with its final
        {"gameType": 2, "gameState": "FINAL", "gameDate": "2026-10-16", "homeTeam": {"abbrev": "NYR"},
         "awayTeam": {"abbrev": "MTL"}},                                   # no row at all
        {"gameType": 1, "gameState": "OFF", "gameDate": "2026-09-28", "homeTeam": {"abbrev": "MTL"},
         "awayTeam": {"abbrev": "OTT"}},                                   # preseason: not a result
        {"gameType": 2, "gameState": "FUT", "gameDate": "2026-11-20", "homeTeam": {"abbrev": "MTL"},
         "awayTeam": {"abbrev": "BUF"}}]},
             "BOS": {"games": [{"gameType": 2, "gameState": "OFF", "gameDate": "2026-10-16",
                                "homeTeam": {"abbrev": "ANA"}, "awayTeam": {"abbrev": "BOS"}}]}}

    def fetch(team, season):
        if team not in pages:
            raise N.DataUnavailable("no page")
        return pages[team]
    owed = N.days_owed(c, 2026, "2026-11-18", teams=("MTL", "BOS", "XXX"), fetch=fetch)
    assert owed == ["2026-10-16"], owed
    asked = []
    M.reread_days_without_final({}, c, "nhl", dt.date(2026, 11, 17), TODAY, lambda d: asked.append(d) or {"games": 2},
                                lambda *_: None, owed=owed + ["2026-11-01"])
    assert asked == ["2026-10-16", "2026-11-01"], asked
    src = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    assert '_owed = _nhl.days_owed(hconn2, _nhl_season("nhl", today.isoformat()), today.isoformat())' in src


def test_every_daily_league_reads_its_days_again():
    src = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    body = src[src.index("def _run_chores("):]
    for sport, call in (("mlb", "_ing_mlb.ingest_mlb_results(_mconn, day, day, with_logs=True)"),
                        ("nba", "ingest_nba_date(nconn, day)"), ("wnba", "_wnba_day(wconn, day)"),
                        ("cbb", "_cbb_day(cconn, day)"), ("nhl", "_nhl.ingest_day(hconn2, day)")):
        assert f'reread_days_without_final(state, _hconn, "{sport}"' in body, sport
        assert call in body, call


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
