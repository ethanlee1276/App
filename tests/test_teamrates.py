"""Team-strength ratings computed from historical scores."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.db import connect, upsert_games
from engine.teamrates import compute_team_ratings, attach_ratings
from engine.models import Game, Weather


def _game_row(season, gid, home, away, hs, as_):
    return {"sport": "nfl", "season": season, "period": f"W{gid}", "game_id": gid,
            "home": home, "away": away, "home_score": hs, "away_score": as_,
            "spread": 0.0, "total": 44.0, "roof": "", "surface": "grass"}


def _seed():
    conn = connect(":memory:")
    # AAA blows everyone out; CCC gets blown out; BBB is average.
    rows = [
        _game_row(2026, "1", "AAA", "BBB", 30, 10),   # AAA +20, BBB -20
        _game_row(2026, "2", "AAA", "CCC", 27, 13),   # AAA +14, CCC -14
        _game_row(2026, "3", "BBB", "CCC", 24, 17),   # BBB +7,  CCC -7
        _game_row(2026, "4", "CCC", "BBB", 14, 21),   # CCC -7,  BBB +7
    ]
    upsert_games(conn, rows)
    return conn


def test_ratings_rank_teams_by_margin():
    conn = _seed()
    r = compute_team_ratings(conn, "nfl", seasons=[2026], shrink=0.0)
    # AAA strongest, CCC weakest, BBB in the middle.
    assert r["AAA"] > r["BBB"] > r["CCC"]
    # Ratings are league-relative (margins), so the strongest is +, weakest -.
    assert r["AAA"] > 0 > r["CCC"]
    # AAA averaged +17 over two games (no shrink).
    assert abs(r["AAA"] - 17.0) < 1e-6


def test_shrinkage_pulls_small_samples_toward_zero():
    conn = _seed()
    raw = compute_team_ratings(conn, "nfl", seasons=[2026], shrink=0.0)
    shrunk = compute_team_ratings(conn, "nfl", seasons=[2026], shrink=6.0)
    # AAA has only 2 games, so shrinkage should noticeably temper its rating.
    assert abs(shrunk["AAA"]) < abs(raw["AAA"])
    assert shrunk["AAA"] > 0        # still positive, just regressed


def test_attach_ratings_sets_game_fields():
    ratings = {"AAA": 8.0, "CCC": -6.0}
    g = Game(home="AAA", away="CCC", weather=Weather(dome=True))
    n = attach_ratings([g], ratings)
    assert n == 1
    assert g.home_rating == 8.0 and g.away_rating == -6.0
    # A team missing from the ratings keeps the league-average default.
    g2 = Game(home="AAA", away="ZZZ", weather=Weather(dome=True))
    attach_ratings([g2], ratings)
    assert g2.home_rating == 8.0 and g2.away_rating == 0.0


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
