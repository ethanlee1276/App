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


def test_pitcher_aware_shifts_win_probability():
    """Same seeded games, same prices — adding each starter's walk-forward
    runs-allowed record must move P(home win) through the pitcher term, and
    the ace's team must look stronger than the ratings-only floor says."""
    conn = _conn()
    _seed_history(conn)
    starters = []
    for d in range(1, 21):
        date = f"2026-05-{d:02d}"
        starters.append({"sport": "mlb", "season": 2026, "period": date,
                         "game_id": "BBB@AAA", "team": "AAA", "pitcher": "Ace Guy"})
        starters.append({"sport": "mlb", "season": 2026, "period": date,
                         "game_id": "BBB@AAA", "team": "BBB", "pitcher": "Bat Practice"})
    db.upsert_game_starters(conn, starters)
    db.upsert_games(conn, [_game("2026-06-01", "AAA", "BBB", 4, 1)])
    db.upsert_game_starters(conn, [
        {"sport": "mlb", "season": 2026, "period": "2026-06-01",
         "game_id": "BBB@AAA", "team": "AAA", "pitcher": "Ace Guy"},
        {"sport": "mlb", "season": 2026, "period": "2026-06-01",
         "game_id": "BBB@AAA", "team": "BBB", "pitcher": "Bat Practice"},
    ])
    db.upsert_odds_history(conn, [
        _ml("2026-06-01", "AAA", "BBB", "AAA", -110),
        _ml("2026-06-01", "AAA", "BBB", "BBB", -110),
    ])
    base = backtest_moneylines(conn, "mlb", min_team_games=15)
    pa = backtest_moneylines(conn, "mlb", min_team_games=15, use_pitchers=True)
    # Identical game set either way; the pitcher variant knows both starters.
    assert pa.games_quoted == base.games_quoted == 1
    assert pa.starters_known == 1 and base.starters_known == 0
    # Ace Guy's team allowed 2/game with him up; Bat Practice bled 5/game —
    # the pitcher term must push the home probability above the ratings floor.
    assert pa.mean_home_prob > base.mean_home_prob
    assert "pitcher-aware" in pa.summary() and "ratings only" in base.summary()


def test_starter_ingest_rows_come_from_slate_games():
    from engine.ingest import mlb_starter_rows
    from engine.mlb.models import MLBGame, Pitcher

    class Slate:
        games = [MLBGame(home="NYY", away="BOS", park="yankee",
                         pitchers={"NYY": Pitcher(name="Ace Guy", throws="R"),
                                   "BOS": Pitcher(name="TBD", throws="R")})]
    rows = mlb_starter_rows(Slate(), "2026-06-10")
    assert rows == [{"sport": "mlb", "season": 2026, "period": "2026-06-10",
                     "game_id": "BOS@NYY", "team": "NYY", "pitcher": "Ace Guy"}]

    conn = _conn()
    assert db.upsert_game_starters(conn, rows) == 1
    assert db.starters_by_game(conn, "mlb") == {
        ("2026-06-10", "BOS@NYY"): {"NYY": "Ace Guy"}}


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
