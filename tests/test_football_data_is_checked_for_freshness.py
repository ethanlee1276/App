"""Every NFL week table is checked against the last week played.

Ethan, 2026-09-25: "is there any more scans or runs or anything you can
do too make sure we don't run into issue like that I have too find." Two
holes: `doctor.check_ingest_freshness` skipped the NFL outright (its
period is a week, not a date), and the unit ratings the matchup tape
ranks refreshed on Tuesdays only, with no retry. engine/freshness answers
both; the doctor, the nightly maintenance and the NFL build ask it.
"""
import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import db, freshness                                  # noqa: E402

TODAY = dt.date(2026, 9, 25)          # a Friday: week 3 ended Monday the 21st


def _box(units_through=3, stats_through=3):
    c = db.connect(":memory:")
    games, logs = [], []
    for wk, day in ((1, "2026-09-07"), (2, "2026-09-14"), (3, "2026-09-21"), (4, "2026-09-27")):
        played = wk <= 3
        games.append({"sport": "nfl", "season": 2026, "period": f"{wk:03d}", "game_id": f"A@B{wk}",
                      "home": "B", "away": "A", "home_score": 20 if played else None,
                      "away_score": 17 if played else None, "date": day, "spread": 0.0,
                      "total": 44.0, "roof": "", "surface": "", "temp": None, "wind": None,
                      "extra": None})
        if wk <= stats_through:
            for mk, v in (("rec_yds", 50.0), ("snap_pct", 0.8)):
                logs.append({"sport": "nfl", "season": 2026, "period": f"{wk:03d}",
                             "game_id": f"A@B{wk}", "player": "P", "team": "A", "opponent": "B",
                             "position": "WR", "home": 0, "market": mk, "value": v})
    db.upsert_games(c, games)
    db.upsert_player_logs(c, logs)
    for wk in range(1, units_through + 1):
        c.execute("INSERT INTO team_units (sport, season, period, team, side, opp, plays, epa) "
                  "VALUES ('nfl', 2026, ?, 'A', 'off', 'B', 60, 1.0)", (str(wk),))
    return c


def test_a_current_box_is_current():
    r = freshness.football_weeks(_box(), "nfl", TODAY)
    assert r["played"] == 3 and r["behind"] == [], r
    assert freshness.line(r).endswith("All current.")


def test_unit_ratings_a_week_behind_are_named():
    r = freshness.football_weeks(_box(units_through=2), "nfl", TODAY)
    assert r["behind"] == ["unit ratings"], r
    assert "BEHIND: unit ratings" in freshness.line(r)


def test_a_week_inside_its_grace_is_not_due():
    """Week 3's Monday game two days ago is due; on Tuesday it is not."""
    r = freshness.football_weeks(_box(units_through=2, stats_through=2), "nfl", dt.date(2026, 9, 22))
    assert r["played"] == 2 and r["behind"] == [], r


def test_the_doctor_the_nightly_and_the_build_ask_it():
    doctor = open(os.path.join(ROOT, "doctor.py"), encoding="utf-8").read()
    assert "check_football_weeks, check_odds_budget" in doctor
    maint = open(os.path.join(ROOT, "engine", "maintenance.py"), encoding="utf-8").read()
    assert 'if today.weekday() == 1 or _units_behind:' in maint
    build = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()
    assert '_fresh.line(_fresh.football_weeks(_fdb.connect(), "nfl"))' in build


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
