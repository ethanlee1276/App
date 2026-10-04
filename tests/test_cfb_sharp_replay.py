"""The sharp-anchor replay grades college, and the backtest command runs it.

Ethan, 2026-09-07: "make sure you do the same exact work to make CFB
just as good."

`backtest_sharp_anchor` replays a season betting only price
disagreements — the shopped soft close against the sharp book's
de-vigged pair — and is the retrospective grade for the strategy the
college edge board now runs on (tests/test_cfb_sharp_first.py). It
never needed a college branch: a college `period` is a date, the key
every harvest is filed under, so the join is the one baseball has
always had. What was missing was the command — `moneyline_backtest.py`
admitted mlb and nfl — and a harvest hint that told every sport to
harvest baseball.

Run directly: `python3 tests/test_cfb_sharp_replay.py`
"""

import contextlib
import io
import json
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db                                        # noqa: E402
from engine.gamebacktest import backtest_sharp_anchor        # noqa: E402


def _college(conn, with_harvest=True):
    """One college Saturday: Toledo beats Bowling Green 27-24. Pinnacle
    closed −200/+170 (Toledo 63% fair); the shopped best paid −150 on
    Toledo — +5% EV on the price alone — filed under the game's date,
    which is also its period."""
    db.upsert_games(conn, [{
        "sport": "cfb", "season": 2026, "period": "2026-09-12", "game_id": "c1",
        "home": "TOL", "away": "BGSU", "home_score": 27, "away_score": 24,
        "spread": -3.5, "total": 52.5, "roof": None, "surface": None,
        "temp": None, "wind": None, "date": None,
        "extra": json.dumps({"neutral": False, "ml": [-160, 140]})}])
    if with_harvest:
        for book, h, a in (("Pinnacle", -200, 170), ("best", -150, 140)):
            for team, odds in (("TOL", h), ("BGSU", a)):
                conn.execute(
                    "INSERT INTO odds_history (sport, taken_at, event_id, home, away, "
                    "player, market, book, line, over_odds, under_odds) VALUES "
                    "('cfb', '2026-09-12T23:00:00Z', 'x', 'TOL', 'BGSU', ?, 'moneyline', "
                    "?, NULL, ?, NULL)", (team, book, odds))
    conn.commit()
    conn.row_factory = sqlite3.Row
    return conn


def test_the_replay_prices_a_college_game_from_its_dated_harvest():
    r = backtest_sharp_anchor(_college(db.connect(":memory:")), "cfb")
    assert r.sport == "cfb" and r.games_seen == 1
    assert r.games_priced == 1 and r.n_bets == 1 and r.wins == 1, r.summary()
    assert r.summary().startswith("CFB sharp-anchor backtest · Pinnacle de-vig")
    # No harvest, no game priced — and the hint says which sport to harvest.
    r0 = backtest_sharp_anchor(_college(db.connect(":memory:"), with_harvest=False), "cfb")
    assert r0.games_priced == 0
    assert "python3 harvest_odds.py cfb --from" in r0.summary(), r0.summary()
    assert "harvest_odds.py mlb" not in r0.summary()


def test_the_hint_names_every_sport_it_is_printed_for():
    for sport in ("mlb", "nfl", "cfb"):
        conn = db.connect(":memory:")
        conn.row_factory = sqlite3.Row
        assert f"harvest_odds.py {sport} " in backtest_sharp_anchor(conn, sport).summary()


def test_the_backtest_command_runs_college_as_the_sharp_replay_alone():
    """College's model is measured by `engine.gamecal --sport cfb` and
    `gamerank.measure_cfb`, which walk the opponent-adjusted ratings the
    board ships; `backtest_moneylines` walks the plain rating the pro
    leagues use. The command says so and prints the replay, which has
    no model in it."""
    import moneyline_backtest as MB
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "h.db")
        _college(db.connect(path)).close()
        argv, sys.argv = sys.argv, ["moneyline_backtest.py", "cfb", "--db", path]
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                MB.main()
        finally:
            sys.argv = argv
    text = out.getvalue()
    assert "sharp-anchor replay only" in text and "engine.gamecal --sport cfb" in text, text
    assert "CFB sharp-anchor backtest" in text
    assert "1 with both a Pinnacle pair and a soft price" in text, text
    assert "CFB moneyline backtest · real" not in text, "the plain model walk ran for college"


def test_the_command_admits_college():
    import inspect
    import moneyline_backtest as MB
    src = inspect.getsource(MB.main)
    assert 'choices=["mlb", "nfl", "cfb"]' in src
    # The pro leagues still get the model walk.
    assert "backtest_moneylines(conn, args.sport" in src


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
