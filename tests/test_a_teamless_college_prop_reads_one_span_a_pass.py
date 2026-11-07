"""A teamless college prop's team is read from one span of the season, once
a pass, and the settle rules exactly as before (engine/ledger._cfb_team_span,
_recent_cfb_team, _CFB_TEAM_SPAN_SQL; settle_from_history's grade_parts
absent_cfb, absent_nfl, their bet counts and absent_team_reads).

The 18:10 settle pass on Saturday 7 November, with the day-file fix live,
still spent 37.6 of its 38.7 grading seconds in the absent-player rule. A
college prop with no team on it looks for his team on his own stat rows of
the 45 days before its date, and that read names no season: no index serves
a day range without one, so it planned as a walk of every college stat row
the box keeps, every season and market, then a sort. Kept per window, it
ran once for each distinct date among the teamless props still waiting,
every five-minute pass. What these hold:

  * the settle notes one span covering every open teamless college prop's
    window, and inside the pass's name index the span is read once, through
    the season, whatever the number of dates;
  * every bet comes out exactly as it does outside an index;
  * a window the span does not hold is read on its own, and answers the same;
  * the span read plans through the primary key with its season, where the
    plain read can only use the sport;
  * the grade's parts split the rule's time by half, count the bets that
    reached each, and count the team reads.

Run directly: `python3 tests/test_a_teamless_college_prop_reads_one_span_a_pass.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db, ledger                                      # noqa: E402

SPAN_HEAD = ledger._CFB_TEAM_SPAN_SQL.split("{marks}")[0]


class _Counting:
    """A history connection that counts the college team reads by kind."""
    def __init__(self, conn):
        self.conn, self.plain, self.span = conn, 0, 0

    def execute(self, sql, args=()):
        if sql == ledger._CFB_TEAM_SQL:
            self.plain += 1
        elif sql.startswith(SPAN_HEAD):
            self.span += 1
        return self.conn.execute(sql, args)


def _log(day, player, team, market="rec_yds", value=40.0, box=True, season=2026):
    return {"sport": "cfb", "season": season, "period": day,
            "game_id": f"{team}-{day}" + ("-box" if box else ""), "player": player,
            "team": team, "opponent": "X", "position": "WR", "home": 1,
            "market": market, "value": value}


def _game(day, home, away):
    return {"sport": "cfb", "season": 2026, "period": day, "game_id": f"{away}@{home}-{day}",
            "home": home, "away": away, "home_score": 31, "away_score": 17, "spread": 0.0,
            "total": 50.5, "roof": "", "surface": "", "temp": None, "wind": None, "extra": None}


def _history():
    """Ohio State's and Boise State's Saturdays, filed; their stars' earlier
    rows name their schools; nobody's rows on the days the props are dated."""
    h = db.connect(":memory:")
    db.upsert_player_logs(h, [
        _log("2026-10-10", "Chris Olave", "OSU"),
        _log("2026-10-10", "José Núñez", "BOIS"),
        _log("2026-08-30", "José Núñez", "UNM"),         # his old school, older row
        *[_log(d, "A Teammate", "OSU") for d in ("2026-10-17", "2026-10-24", "2026-10-31")],
        *[_log(d, "B Teammate", "BOIS") for d in ("2026-10-17", "2026-10-24", "2026-10-31")],
        _log("2026-10-24", "B Teammate", "BOIS", box=False),   # the play file, too
        _log("2025-11-01", "Chris Olave", "OSU", season=2025),
    ])
    db.upsert_games(h, [_game(d, "OSU", "MICH") for d in ("2026-10-17", "2026-10-24", "2026-10-31")]
                    + [_game(d, "BOIS", "UNLV") for d in ("2026-10-17", "2026-10-24", "2026-10-31")])
    return h


BETS = [  # (date, player, market): every one teamless, none with a stat row that day
    ("2026-10-17", "Chris Olave", "rush_yds"),
    ("2026-10-24", "Chris Olave", "rush_yds"),
    ("2026-10-31", "Chris Olave", "rush_yds"),
    ("2026-10-24", "Jose Nunez", "rush_yds"),
    ("2026-10-31", "José Núñez", "receptions"),   # a play-file market
    ("2026-10-31", "Nobody Known", "rush_yds"),   # no rows, on no roster: stays open
]


def _journal():
    led = ledger.connect(":memory:")
    ledger.configure_bankroll(led, starting=1000, unit_pct=1.0)
    for day, player, market in BETS:
        led.execute(
            "INSERT INTO bets (ts, sport, date, player, market, side, line, book, odds, "
            "stake_units, stake_dollars, status, category) VALUES "
            "('t','cfb',?,?,?,'OVER',10.5,'FanDuel',-110,0.1,1.0,'open','main')",
            (day, player, market))
    led.commit()
    return led


def _settle(indexed: bool):
    led, hist = _journal(), _Counting(_history())
    ledger.take_grade_parts()
    if indexed:
        with ledger.name_index():
            ledger.settle_from_history(led, hist)
    else:
        ledger.settle_from_history(led, hist)
    rows = [tuple(r) for r in led.execute(
        "SELECT date, player, market, status, why_note FROM bets ORDER BY id")]
    return rows, hist, ledger.take_grade_parts()


def test_the_span_is_read_once_a_pass_and_every_bet_rules_the_same():
    plain, plain_hist, _ = _settle(indexed=False)
    kept, kept_hist, parts = _settle(indexed=True)
    assert kept == plain, (kept, plain)
    assert plain_hist.plain == len(BETS) and plain_hist.span == 0, \
        ("outside an index, one window read a bet", plain_hist.plain, plain_hist.span)
    assert kept_hist.span == 1 and kept_hist.plain == 0, (kept_hist.span, kept_hist.plain)
    status = {(d, p, m): s for d, p, m, s, _w in kept}
    # Two days' Olave props and Núñez's rush voided off filed box scores;
    # the play-file market waits; the stranger stays open.
    assert status[("2026-10-24", "Chris Olave", "rush_yds")] == "void"
    assert status[("2026-10-24", "Jose Nunez", "rush_yds")] == "void"
    assert status[("2026-10-31", "Nobody Known", "rush_yds")] == "open"
    assert parts["absent_team_reads"] == 1
    assert parts["absent_n_cfb"] == len(BETS) and "absent_n_nfl" not in parts
    assert 0.0 <= parts["absent_cfb"] <= parts["absent"] + 0.1


def test_the_span_covers_every_teamless_college_props_window():
    rows = [
        {"sport": "cfb", "market": "rush_yds", "category": "main", "team": None, "date": "2026-10-24"},
        {"sport": "cfb", "market": "rec_yds", "category": "main", "team": "", "date": "2026-11-07"},
        {"sport": "cfb", "market": "rec_yds", "category": "main", "team": "OSU", "date": "2026-08-01"},
        {"sport": "cfb", "market": "spread", "category": "main", "team": None, "date": "2026-08-02"},
        {"sport": "cfb", "market": "rec_yds", "category": "predmarket", "team": None, "date": "2026-08-03"},
        {"sport": "nfl", "market": "rec_yds", "category": "main", "team": None, "date": "2026-W09"},
        {"sport": "cfb", "market": "rec_yds", "category": "main", "team": None, "date": "W09"},
    ]
    assert ledger._cfb_team_span(rows) == ("2026-09-09", "2026-11-07")
    assert ledger._cfb_team_span(rows[2:]) is None
    assert ledger.CFB_TEAM_LOOKBACK_DAYS == 45


def test_a_window_the_span_does_not_hold_is_read_on_its_own_and_answers_the_same():
    h = _Counting(_history())
    asks = [("2026-09-01", "2026-10-16", "chris olave"), ("2026-07-16", "2026-08-31", "jose nunez"),
            ("2025-09-17", "2025-11-01", "chris olave"), ("2026-09-01", "2026-10-16", "nobody")]
    plain = [ledger._recent_cfb_team(h, a, b, t) for a, b, t in asks]
    assert plain == ["OSU", "UNM", "OSU", None], plain
    with ledger.name_index():
        ledger._name_index_now()["cfb_team_span"] = ("2026-09-15", "2026-11-07")
        kept = [ledger._recent_cfb_team(h, a, b, t) for a, b, t in asks]
        assert h.span == 3, "three windows outside the span, each read once"
        again = [ledger._recent_cfb_team(h, a, b, t) for a, b, t in asks]
        assert h.span == 3 and again == kept
        inside = ledger._recent_cfb_team(h, "2026-09-16", "2026-10-31", "jose nunez")
        assert inside == "BOIS" and h.span == 4, "the span itself, read once"
        assert ledger._recent_cfb_team(h, "2026-10-01", "2026-11-07", "chris olave") == "OSU"
        assert h.span == 4
    assert kept == plain


def test_the_span_read_goes_through_the_season():
    h = db.connect(":memory:")
    sql = ledger._CFB_TEAM_SPAN_SQL.format(marks="?,?")
    plan = " ".join(str(tuple(r)) for r in h.execute(
        "EXPLAIN QUERY PLAN " + sql, (2025, 2026, "2026-09-23", "2026-11-07")))
    assert "sqlite_autoindex_player_game_logs_1 (sport=? AND season=?" in plan, plan
    old = " ".join(str(tuple(r)) for r in h.execute(
        "EXPLAIN QUERY PLAN " + ledger._CFB_TEAM_SQL, ("2026-09-23", "2026-11-07")))
    assert "season=?" not in old, "the plain read cannot use a season it does not name"


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
