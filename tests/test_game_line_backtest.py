"""Grading the spread/total model — and grading the grader first.

The game-bet layer shipped with no market shrink and no credibility ceiling
(see test_game_bet_discipline.py). Fixing that raised the obvious question:
is the tempered version any good? Which could not be answered, because the
closing numbers it would have to be graded against were never stored. The
build asked the odds API for h2h, spreads and totals every day, attached all
three to the slate, priced bets off all three, and journaled only h2h.

So: engine.lineledger writes them on every build (free — already in memory),
engine.sources.oddshistory stores them on a paid harvest, and
gamebacktest.backtest_game_lines replays them through the PRODUCTION pricer.

The important tests here are the last two. A backtest that cannot fail is
not a measurement, so this file checks the harness against a synthetic
season where the truth is known both ways: priced at fair value it must
LOSE roughly the vig, and against a book hanging a biased number it must
find the bias. An instrument that only ever returns good news is an
instrument you cannot use to decide anything.
"""

import datetime
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db, lineledger
from engine.gamebacktest import (backtest_game_lines, game_line_closes,
                                 _settle_total, _settle_spread)


class _Game:
    """The slate-game shape the odds adapter fills in."""
    def __init__(self, **kw):
        self.home = kw.get("home", "BOS")
        self.away = kw.get("away", "NYY")
        self.date = kw.get("date", "2026-08-01")
        self.total = kw.get("total")
        self.total_over_odds = kw.get("too", -110)
        self.total_under_odds = kw.get("tuo", -110)
        self.spread = kw.get("spread")
        self.spread_home_odds = kw.get("sho", -110)
        self.spread_away_odds = kw.get("sao", -110)
        self.home_ml = kw.get("home_ml")
        self.away_ml = kw.get("away_ml")


# --- keeping the numbers we already paid for --------------------------------
def test_the_build_writes_the_spread_and_total_it_pulled():
    rows = lineledger.rows_for_games("mlb", [_Game(total=8.5, spread=-1.5,
                                                   home_ml=-140, away_ml=120)])
    got = {(r["market"], r["player"]): r for r in rows}
    assert got[("total", "TOTAL")]["line"] == 8.5
    assert got[("spread", "BOS")]["line"] == -1.5
    assert got[("moneyline", "BOS")]["over_odds"] == -140
    assert got[("moneyline", "NYY")]["over_odds"] == 120


def test_a_pickem_spread_is_stored_rather_than_treated_as_missing():
    """0.0 is a real line. `if spread:` would drop every pick'em."""
    rows = lineledger.rows_for_games("nfl", [_Game(spread=0.0)])
    assert [r for r in rows if r["market"] == "spread"]


def test_a_game_with_no_price_stores_nothing():
    """A row of Nones would make "we never saw a line" and "the line was
    even" the same stored fact — the confusion this table exists to stop."""
    assert lineledger.rows_for_games("mlb", [_Game()]) == []


def test_snapshots_are_minute_resolution():
    """The launcher rebuilds every 60s. At second resolution each build
    would mint a new primary key and one game would become a million rows."""
    now = datetime.datetime(2026, 8, 1, 19, 30, 45,
                            tzinfo=datetime.timezone.utc)
    rows = lineledger.rows_for_games("mlb", [_Game(total=8.5)], now=now)
    assert rows[0]["taken_at"] == "2026-08-01T19:30:00Z"


def test_recording_never_breaks_a_build():
    """A board that goes dark because its telemetry could not write has
    failed for the least important reason available."""
    assert lineledger.record(None, "mlb", [_Game(total=8.5)]) == 0


def test_the_close_is_the_last_snapshot_of_the_day():
    conn = db.connect(":memory:")
    for stamp, line in (("12:00", 8.5), ("18:00", 9.0), ("22:00", 9.5)):
        db.upsert_odds_history(conn, [{
            "sport": "mlb", "taken_at": f"2026-08-01T{stamp}:00Z",
            "event_id": "e1", "home": "BOS", "away": "NYY", "player": "TOTAL",
            "market": "total", "book": "best", "line": line,
            "over_odds": -110, "under_odds": -110}])
    closes = game_line_closes(conn, "mlb", "total")
    assert closes[("2026-08-01", "BOS", "NYY")][0] == 9.5


# --- settlement -------------------------------------------------------------
def test_totals_settle_including_the_push():
    assert _settle_total(8.5, "Over", 5, 4) == (True, False)
    assert _settle_total(8.5, "Under", 5, 4) == (False, False)
    assert _settle_total(9.0, "Over", 5, 4) == (False, True)     # exact = push


def test_spreads_settle_from_the_home_number():
    # Home -1.5, home wins by 3 -> home covers.
    assert _settle_spread(-1.5, True, 6, 3) == (True, False)
    # Same game backing the AWAY side.
    assert _settle_spread(-1.5, False, 6, 3) == (False, False)
    # Home -3.0, home wins by exactly 3 -> push either way.
    assert _settle_spread(-3.0, True, 6, 3) == (False, True)


# --- the harness, checked against a known answer ----------------------------
def _season(bias: float, days: int = 120):
    """A season where the book's number is the TRUE expected total plus
    ``bias``. At bias 0 there is no edge to find; at bias 1 there is one."""
    random.seed(7)
    conn = db.connect(":memory:")
    teams = [f"T{i:02d}" for i in range(30)]
    strength = {t: random.gauss(0, 1.2) for t in teams}
    base, games, odds = 4.5, [], []
    d0 = datetime.date(2026, 4, 1)
    for day in range(days):
        date = (d0 + datetime.timedelta(days=day)).isoformat()
        random.shuffle(teams)
        for i in range(0, 30, 2):
            h, a = teams[i], teams[i + 1]
            hs = max(0, round(random.gauss(base + strength[h] - strength[a] * .5, 3.0)))
            as_ = max(0, round(random.gauss(base + strength[a] - strength[h] * .5, 3.0)))
            games.append({"sport": "mlb", "season": 2026, "period": date,
                          "game_id": f"{a}@{h}", "home": h, "away": a,
                          "home_score": hs, "away_score": as_, "spread": 0.0,
                          "total": None, "roof": "open", "surface": "grass",
                          "temp": None, "wind": None, "extra": ""})
            true_total = 2 * base + (strength[h] + strength[a]) * .5
            odds.append({"sport": "mlb", "taken_at": f"{date}T22:00:00Z",
                         "event_id": f"{date}-{a}@{h}", "home": h, "away": a,
                         "player": "TOTAL", "market": "total", "book": "best",
                         "line": round((true_total + bias) * 2) / 2,
                         "over_odds": -110, "under_odds": -110})
    db.upsert_games(conn, games)
    db.upsert_odds_history(conn, odds)
    return conn


def test_a_fairly_priced_book_beats_us_by_about_the_vig():
    """The control that matters. If the harness shows profit against a book
    priced at the truth, every positive result it ever gives is worthless."""
    r = backtest_game_lines(_season(0.0), "mlb", "total")
    assert r.games_quoted > 1000, "fixture too small to conclude anything"
    assert r.n_bets > 200
    assert r.roi < 0, f"found {r.roi:+.1%} of edge in a fairly priced market"
    assert r.roi > -0.20, "losing far more than the vig means a settlement bug"


def test_a_biased_book_is_detected():
    """And the other direction: an instrument that cannot find an edge that
    IS there makes a negative result meaningless."""
    r = backtest_game_lines(_season(1.0), "mlb", "total")
    assert r.roi > 0.05, f"missed a full run of standing bias (ROI {r.roi:+.1%})"
    decided = r.n_bets - r.pushes
    assert r.wins / decided > 0.55


def test_the_bigger_the_bias_the_bigger_the_result():
    """Monotonic, or the number is not measuring what it claims."""
    rois = [backtest_game_lines(_season(b), "mlb", "total").roi
            for b in (0.0, 1.0, 2.0)]
    assert rois[0] < rois[1] < rois[2], rois


# --- what the report is careful to say --------------------------------------
def test_a_thin_sample_refuses_to_be_a_verdict():
    conn = _season(0.0, days=20)
    r = backtest_game_lines(conn, "mlb", "total")
    if 0 < r.n_bets < 100:
        assert "not a verdict" in r.summary()


def test_an_empty_run_says_where_the_data_comes_from():
    conn = db.connect(":memory:")
    r = backtest_game_lines(conn, "mlb", "total")
    s = r.summary()
    assert "No stored total closes" in s
    assert "lineledger" in s and "harvest_odds.py" in s


def test_the_projection_error_leads_the_report():
    """The ROI is the seductive number and the least reliable one. How far
    the projection sits from the closing number is the finding — an inflated
    edge board is that error wearing a percentage."""
    r = backtest_game_lines(_season(0.0), "mlb", "total")
    s = r.summary()
    assert s.index("off the closing number") < s.index("ROI")
    assert r.mae > 0


def test_an_unregistered_sport_is_refused_not_replayed_through_the_nfl():
    conn = db.connect(":memory:")
    try:
        backtest_game_lines(conn, "kabaddi", "total")
    except ValueError as exc:
        assert "kabaddi" in str(exc)
    else:
        raise AssertionError("replayed a sport with a borrowed baseline")


def test_the_replay_uses_the_shipping_pricer():
    """A backtest of a model you do not run is a number about nothing."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "engine", "gamebacktest.py"),
        encoding="utf-8").read()
    fn = src[src.index("def backtest_game_lines("):]
    assert "price_total(" in fn and "price_spread(" in fn
    assert 'card["credible"]' in fn, "the ceiling under test is not exercised"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
