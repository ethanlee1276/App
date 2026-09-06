"""Does an NFL bet survive the whole trip — board, results, settle, close?

Written 2026-09-06, three days before the first Week 1 kickoff, because
every measurement this book makes had until then been a BASEBALL verdict:
football had zero settled bets, so none of the machinery downstream of an
NFL pick had ever run on one.

WHAT THE REHEARSAL FOUND. The settle path was sound — `nfl_build` stamps
"2026-W01", `_hist_where` maps that to season+period "001", and both the
stat-log and schedule row builders write exactly that. Seven markets,
journalled and graded correctly, including a loss and a longshot.

The CLOSING-LINE path was not, and the failure was invisible. Both close
indexes are keyed by CALENDAR date — `closing_odds_by_date` files a
harvested price under `taken_at[:10]`, `closing_lines_by_date` files a
free snapshot under its timestamp's day — while both lookups indexed with
`bet["date"]`. For the daily sports that IS a calendar date. For the NFL
it is a week label, so nothing could ever match and no NFL bet could
receive a close. It reads as "no close harvested yet", which is why it
would have survived the season.

That mattered because CLV is the one edge this book has measured
(+2.05% ± 0.27%, t = +7.5 over 931 bets) and the football half of it
would have been silently missing.

`engine/gamecal.py` already names this class of failure —"A harvest keyed
by date cannot join a schedule keyed by week" — and works around it
locally. The fix here is the join both needed: `games.date`, the kickoff
date every source ships and this table always discarded.

Run directly: `python3 tests/test_week1_capture.py`
"""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db as hist_db          # noqa: E402
from engine import ingest as ing          # noqa: E402
from engine import ledger                 # noqa: E402

SEASON, WEEK = 2026, 1
WEEK_LABEL = f"{SEASON}-W{WEEK:02d}"
KICKOFF = "2026-09-13"

#: One nflverse weekly row. Chase: 101 rec yards, 7 catches, 1 TD.
WEEKLY = [{"season": SEASON, "week": WEEK, "season_type": "REG",
           "player_display_name": "Ja'Marr Chase", "position": "WR",
           "recent_team": "CIN", "opponent_team": "CLE",
           "receiving_yards": 101.0, "receptions": 7.0, "targets": 11.0,
           "carries": 0.0, "rushing_yards": 0.0, "passing_yards": 0.0,
           "receiving_tds": 1.0, "rushing_tds": 0.0, "passing_tds": 0.0}]

#: One schedule row. CIN 27, CLE 20 — CIN by 7.
SCHEDULE = [{"season": str(SEASON), "week": str(WEEK), "home_team": "CLE",
             "away_team": "CIN", "gameday": KICKOFF, "home_score": "20",
             "away_score": "27", "spread_line": "-2.5", "total_line": "44.5",
             "roof": "outdoors", "surface": "grass"}]


def _books():
    tmp = tempfile.mkdtemp()
    return (ledger.connect(os.path.join(tmp, "l.db")),
            hist_db.connect(os.path.join(tmp, "h.db")))


def _rec(**kw):
    base = {"side": "OVER", "odds": -110, "book": "dk", "hit_prob": 0.56,
            "edge": 0.05, "confidence": 0.6, "grade": "B",
            "stake_units": 1.0, "recommended": True}
    return {**base, **kw}


def _ingest(h):
    """What `ingest_nfl_results` does: all three builders, then the games."""
    hist_db.upsert_player_logs(h, ing.nfl_player_log_rows(WEEKLY, SEASON)
                               + ing.nfl_usage_rows(WEEKLY, SEASON)
                               + ing.nfl_td_rows(WEEKLY, SEASON))
    hist_db.upsert_games(h, ing.nfl_game_rows(SCHEDULE, {SEASON}))


def test_every_market_a_week_one_board_can_produce_settles():
    """THE REHEARSAL. Not one market — all of them, plus a loss, because a
    happy path that only proves overs win proves very little."""
    l, h = _books()
    ledger.log_recommendations(l, {"sport": "nfl", "date": WEEK_LABEL,
        "recommendations": [
            _rec(player="Ja'Marr Chase", market="rec_yds", line=74.5),
            _rec(player="CIN", market="moneyline", line=0.5, odds=-140),
            _rec(player="CIN@CLE", market="total", line=44.5),
            _rec(player="CIN", market="spread", line=-2.5),
            _rec(player="CIN", market="team_total", line=23.5),
            # Seven catches against 8.5 is a LOSS, and it has to be
            # recorded as one.
            _rec(player="Ja'Marr Chase", market="receptions", line=8.5),
        ]})
    _ingest(h)
    ledger.settle_from_history(l, h)
    got = {(r["market"], r["status"]) for r in
           l.execute("SELECT market, status FROM bets")}
    assert got == {("rec_yds", "won"), ("moneyline", "won"),
                   ("total", "won"), ("spread", "won"),
                   ("team_total", "won"), ("receptions", "lost")}, got


def test_the_longshot_bucket_grades_at_its_own_price():
    """anytime_td is a LONGSHOT_MARKET: skipped by the main journal on
    purpose and logged to its own bucket. It still has to settle."""
    l, h = _books()
    ledger.log_longshots(l, {"sport": "nfl", "date": WEEK_LABEL,
        "long_shots": [_rec(player="Ja'Marr Chase", market="anytime_td",
                            line=0.5, odds=145)]})
    _ingest(h)
    ledger.settle_from_history(l, h)
    b = l.execute("SELECT status, pnl_units FROM bets").fetchone()
    assert b["status"] == "won"
    assert abs(b["pnl_units"] - 0.145) < 1e-6, dict(b)


def test_the_ingest_carries_the_kickoff_date():
    """`games` threw this away for as long as it existed. Everything below
    depends on it now."""
    row = ing.nfl_game_rows(SCHEDULE, {SEASON})[0]
    assert row["date"] == KICKOFF
    assert row["period"] == "001", "the week is still the period"
    l, h = _books()
    hist_db.upsert_games(h, [row])
    assert h.execute("SELECT date FROM games").fetchone()["date"] == KICKOFF


def test_a_daily_sport_passes_straight_through():
    """THE REGRESSION THAT WOULD HURT MOST. Every MLB bet in the journal
    grades through this helper; for an ISO-dated slate it must return the
    label unchanged and ask the database nothing."""
    _, h = _books()
    for sport, date in (("mlb", "2026-09-06"), ("cfb", "2026-09-05"),
                        ("nfl", "2026-09-13"), ("wnba", "2026-08-01")):
        assert ledger.close_dates(h, {"sport": sport, "date": date}) == [date]
    # A missing date is still a pass-through, not a lookup.
    assert ledger.close_dates(h, {"sport": "mlb", "date": ""}) == [""]


def test_a_week_label_resolves_to_the_day_the_game_was_played():
    l, h = _books()
    _ingest(h)
    assert ledger.close_dates(h, {"sport": "nfl", "date": WEEK_LABEL}) == [KICKOFF]


def test_a_team_narrows_the_week_to_its_own_fixture():
    """A week holds Thursday, Sunday and Monday games. A player plays in
    one of them, and his close is filed under that day."""
    l, h = _books()
    _ingest(h)
    hist_db.upsert_games(h, [{"sport": "nfl", "season": SEASON,
        "period": "001", "game_id": "KC@BUF", "home": "BUF", "away": "KC",
        "home_score": 21.0, "away_score": 24.0, "date": "2026-09-10"}])
    assert ledger.close_dates(h, {"sport": "nfl", "date": WEEK_LABEL},
                              "CIN") == [KICKOFF]
    assert ledger.close_dates(h, {"sport": "nfl", "date": WEEK_LABEL},
                              "BUF") == ["2026-09-10"]
    # Without a team the whole week comes back, LATEST FIRST: a close is
    # the last price before kickoff, so the later day is the better guess.
    assert ledger.close_dates(h, {"sport": "nfl", "date": WEEK_LABEL}) == [
        KICKOFF, "2026-09-10"]


def test_an_nfl_bet_finally_receives_a_closing_line():
    """THE BUG, END TO END. Before `games.date` this was None for every
    NFL bet ever placed, and looked exactly like an unharvested close."""
    l, h = _books()
    ledger.log_recommendations(l, {"sport": "nfl", "date": WEEK_LABEL,
        "recommendations": [_rec(player="Ja'Marr Chase", market="rec_yds",
                                 line=74.5)]})
    _ingest(h)
    # The market closed two points higher, on the day of the game. Stored
    # under the NORMALISED name, which is what the harvest writes.
    h.execute("INSERT INTO odds_history (sport,taken_at,event_id,home,away,"
              "player,market,book,line,over_odds,under_odds) VALUES "
              "('nfl',?,'e1','CLE','CIN','jamarr chase','rec_yds','dk',"
              "76.5,-108,-112)", (KICKOFF + "T16:55:00",))
    h.commit()
    ledger.settle_from_history(l, h)
    b = l.execute("SELECT side, line, closing_line FROM bets").fetchone()
    assert b["closing_line"] == 76.5, dict(b)
    # An over wants the line to rise: +2.0 points our way.
    assert abs(ledger._bet_clv(b) - 2.0) < 1e-9


def test_no_bridge_is_not_a_crash():
    """A history DB with no games rows — a fresh clone, or one that has
    not re-ingested since the column shipped — must yield no close rather
    than an exception in the settling path."""
    l, h = _books()
    assert ledger.close_dates(h, {"sport": "nfl", "date": WEEK_LABEL}) == []
    assert ledger.close_at({("x", "2026-09-13"): 1.0}, "x", []) is None


def test_close_at_takes_the_first_date_offered():
    """The ordering `close_dates` chose has to survive the lookup."""
    idx = {("x", "2026-09-13"): {"line": 51.5},
           ("x", "2026-09-10"): {"line": 49.5}}
    assert ledger.close_at(idx, "x", ["2026-09-13", "2026-09-10"])["line"] == 51.5
    assert ledger.close_at(idx, "x", ["2026-09-10", "2026-09-13"])["line"] == 49.5
    assert ledger.close_at(idx, "nobody", ["2026-09-13"]) is None


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails
          else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
