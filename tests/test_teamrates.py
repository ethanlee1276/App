"""Team-strength ratings computed from historical scores."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.db import connect, upsert_games
from engine.teamrates import compute_team_ratings, attach_ratings, TeamRating
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
    # AAA strongest, CCC weakest, BBB in the middle (compare net margin).
    assert r["AAA"].net > r["BBB"].net > r["CCC"].net
    # Ratings are league-relative (margins), so the strongest is +, weakest -.
    assert r["AAA"].net > 0 > r["CCC"].net
    # AAA averaged +17 margin over two games (no shrink).
    assert abs(r["AAA"].net - 17.0) < 1e-6
    # net == off - def by construction.
    assert abs(r["AAA"].net - (r["AAA"].off - r["AAA"].def_)) < 1e-6


def test_shrinkage_pulls_small_samples_toward_zero():
    conn = _seed()
    raw = compute_team_ratings(conn, "nfl", seasons=[2026], shrink=0.0)
    shrunk = compute_team_ratings(conn, "nfl", seasons=[2026], shrink=6.0)
    # AAA has only 2 games, so shrinkage should noticeably temper its rating.
    assert abs(shrunk["AAA"].net) < abs(raw["AAA"].net)
    assert shrunk["AAA"].net > 0        # still positive, just regressed


def test_attach_ratings_sets_game_fields():
    ratings = {
        "AAA": TeamRating(net=8.0, off=5.0, def_=-3.0, games=10),
        "CCC": TeamRating(net=-6.0, off=-4.0, def_=2.0, games=10),
    }
    g = Game(home="AAA", away="CCC", weather=Weather(dome=True))
    n = attach_ratings([g], ratings)
    assert n == 1
    assert g.home_rating == 8.0 and g.away_rating == -6.0
    assert g.home_off == 5.0 and g.away_def == 2.0
    # A team missing from the ratings keeps the league-average default.
    g2 = Game(home="AAA", away="ZZZ", weather=Weather(dome=True))
    attach_ratings([g2], ratings)
    assert g2.home_rating == 8.0 and g2.away_rating == 0.0


def test_mlb_results_parse_only_completed_games():
    """Final scores drive team ratings, so unplayed and cancelled games must
    never reach the DB (a 0-0 cancellation would poison the ratings)."""
    from engine.mlb.sources.mlbstats import parse_results
    from engine.ingest import mlb_result_rows

    payload = {"dates": [{"games": [
        {"officialDate": "2026-07-20",
         "status": {"abstractGameState": "Final", "codedGameState": "F"},
         "venue": {"name": "Yankee Stadium"},
         "teams": {"home": {"team": {"id": 147}, "score": 7},
                   "away": {"team": {"id": 111}, "score": 3}}},
        {"officialDate": "2026-07-20", "status": {"abstractGameState": "Preview"},
         "venue": {"name": "Fenway Park"},
         "teams": {"home": {"team": {"id": 111}}, "away": {"team": {"id": 147}}}},
        {"officialDate": "2026-07-20",
         "status": {"abstractGameState": "Final", "codedGameState": "C"},
         "venue": {"name": "Wrigley Field"},
         "teams": {"home": {"team": {"id": 112}, "score": 0},
                   "away": {"team": {"id": 158}, "score": 0}}},
    ]}]}
    res = parse_results(payload)
    assert len(res) == 1
    assert res[0]["home"] == "NYY" and res[0]["home_score"] == 7.0
    assert res[0]["away"] == "BOS" and res[0]["away_score"] == 3.0

    rows = mlb_result_rows(res)
    assert rows[0]["sport"] == "mlb" and rows[0]["season"] == 2026
    assert rows[0]["home_score"] == 7.0        # the bug this fixes: was None
    assert rows[0]["extra"] == "yankee"        # venue mapped to a park profile


def test_player_log_ingest_is_idempotent_across_dates():
    """A game log's recency index shifts as newer games arrive, so history must
    be keyed on the real game date — otherwise re-ingesting files the same game
    under a new key and corrupts the record the backtest learns from."""
    from engine.db import upsert_player_logs, entries_for_market
    from engine.ingest import mlb_rows_from_slate
    from engine.mlb.data_loader import MLBSlate
    from engine.mlb.models import MLBProp, MLBGameLog, MLBGame
    from engine.models import SportsbookLine

    def slate(extra):
        dates = ["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04"][:3 + extra]
        n = len(dates)
        logs = [MLBGameLog(game=n - i, opponent="X", value=float(len(dates) - i), date=d)
                for i, d in enumerate(reversed(dates))]
        prop = MLBProp("Aaron Judge", "NYY", "BOS", "RF", "total_bases", logs, 2.0,
                       None, [SportsbookLine("proxy", 1.5)], bats="R", lineup_spot=2)
        return MLBSlate(date=dates[-1], games=[MLBGame(home="NYY", away="BOS", park="yankee")],
                        props=[prop])

    conn = connect(":memory:")
    for extra in (0, 1):        # ingest on two consecutive days
        _, prows = mlb_rows_from_slate(slate(extra), f"2026-06-0{3 + extra}")
        upsert_player_logs(conn, prows)

    rows = conn.execute("SELECT period FROM player_game_logs").fetchall()
    assert len(rows) == 4, "overlapping ingests must not duplicate games"
    entries = entries_for_market(conn, "mlb", "total_bases", min_games=1)
    # Chronological order, oldest first — what the walk-forward backtest needs.
    assert entries[0]["values"] == [1.0, 2.0, 3.0, 4.0]


def test_ingested_mlb_results_produce_ratings():
    """End to end: real finals in the DB must yield ranked team ratings."""
    from engine.ingest import mlb_result_rows

    results = []
    for i in range(1, 16):
        d = f"2026-06-{i:02d}"
        results += [
            {"date": d, "home": "NYY", "away": "MIA", "home_score": 8, "away_score": 2, "venue": ""},
            {"date": d, "home": "BOS", "away": "NYY", "home_score": 3, "away_score": 5, "venue": ""},
            {"date": d, "home": "MIA", "away": "BOS", "home_score": 2, "away_score": 6, "venue": ""},
        ]
    conn = connect(":memory:")
    upsert_games(conn, mlb_result_rows(results))
    r = compute_team_ratings(conn, "mlb", seasons=[2026])
    assert r["NYY"].net > r["BOS"].net > r["MIA"].net
    assert r["NYY"].off > 0 and r["MIA"].def_ > 0   # MIA allows more than average


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
