"""Tests for the walk-forward moneyline backtest (in-memory SQLite)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db
from engine.gamebacktest import backtest_moneylines, moneyline_closes


def _conn():
    return db.connect(":memory:")


def _game(date, home, away, hs, as_):
    return {"sport": "mlb", "season": 2026, "period": date,
            "game_id": f"{away}@{home}", "home": home, "away": away,
            "home_score": hs, "away_score": as_, "spread": 0.0, "total": None,
            "roof": "open", "surface": "grass", "temp": None, "wind": None,
            "extra": "generic"}


def _ml(date, home, away, team, odds, hour="23"):
    return {"sport": "mlb", "taken_at": f"{date}T{hour}:00:00Z",
            "event_id": f"{date}-{away}@{home}", "home": home, "away": away,
            "player": team, "market": "moneyline", "book": "best",
            "line": 0.0, "over_odds": odds, "under_odds": None}


def test_moneyline_closes_keeps_last_snapshot_per_date():
    conn = _conn()
    db.upsert_odds_history(conn, [
        _ml("2026-06-10", "NYY", "BOS", "NYY", -130, hour="18"),
        _ml("2026-06-10", "NYY", "BOS", "NYY", -145, hour="22"),   # the close
        _ml("2026-06-10", "NYY", "BOS", "BOS", 125, hour="22"),
    ])
    closes = moneyline_closes(conn, "mlb")
    assert closes[("2026-06-10", "NYY", "BOS")] == {"NYY": -145, "BOS": 125}


def _seed_history(conn, n_days=20):
    """AAA beats BBB daily (5-2), and CCC splits with DDD — builds ratings."""
    games = []
    for d in range(1, n_days + 1):
        date = f"2026-05-{d:02d}"
        games.append(_game(date, "AAA", "BBB", 5, 2))
        games.append(_game(date, "CCC", "DDD", 3, 3 + (d % 2)))
    db.upsert_games(conn, games)


def test_walk_forward_settles_against_real_scores():
    conn = _conn()
    _seed_history(conn)
    # Judgment day: the dominant team is priced as only a slight favorite —
    # the model (which watched AAA win 20 straight by 3) should pounce.
    db.upsert_games(conn, [_game("2026-06-01", "AAA", "BBB", 4, 1)])
    db.upsert_odds_history(conn, [
        _ml("2026-06-01", "AAA", "BBB", "AAA", -110),
        _ml("2026-06-01", "AAA", "BBB", "BBB", -110),
    ])
    r = backtest_moneylines(conn, "mlb", min_team_games=15)
    assert r.games_seen == 41
    assert r.games_quoted == 1          # only judgment day had a price
    assert r.n_bets == 1 and r.wins == 1
    assert r.net > 0 and r.roi > 0
    assert "REAL closing moneylines" in r.summary()


def test_needs_history_before_pricing():
    conn = _conn()
    # A priced game on day one: no team history, so nothing should be priced.
    db.upsert_games(conn, [_game("2026-06-01", "AAA", "BBB", 4, 1)])
    db.upsert_odds_history(conn, [
        _ml("2026-06-01", "AAA", "BBB", "AAA", -110),
        _ml("2026-06-01", "AAA", "BBB", "BBB", -110),
    ])
    r = backtest_moneylines(conn, "mlb", min_team_games=15)
    assert r.games_seen == 1 and r.games_quoted == 0 and r.n_bets == 0
    assert "harvest h2h odds first" in r.summary()


def test_losing_pick_costs_the_stake():
    conn = _conn()
    _seed_history(conn)
    # Model will love AAA again, but this time the upset lands.
    db.upsert_games(conn, [_game("2026-06-01", "AAA", "BBB", 1, 7)])
    db.upsert_odds_history(conn, [
        _ml("2026-06-01", "AAA", "BBB", "AAA", -115),
        _ml("2026-06-01", "AAA", "BBB", "BBB", -105),
    ])
    r = backtest_moneylines(conn, "mlb", min_team_games=15)
    if r.n_bets:                        # graded above Pass -> must have lost
        assert r.wins == 0 and r.net < 0


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
