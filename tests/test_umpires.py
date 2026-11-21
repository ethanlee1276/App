"""Tests for the umpire model (in-memory SQLite, fixture boxscores)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db
from engine.mlb.umpires import umpire_profiles, attach_umpires, UmpProfile
from engine.mlb.sources.statslogs import parse_officials


def test_parse_officials_finds_the_plate_ump():
    box = {"officials": [
        {"official": {"fullName": "First Base Guy"}, "officialType": "First Base"},
        {"official": {"fullName": "Big Zone Bob"}, "officialType": "Home Plate"},
    ]}
    assert parse_officials(box) == "Big Zone Bob"
    assert parse_officials({}) == ""
    assert parse_officials({"officials": []}) == ""


def _seed(conn, ump, dates, runs_per_game, ks_per_starter):
    games, umps, starters, logs = [], [], [], []
    for i, date in enumerate(dates):
        gid = "BBB@AAA"
        games.append({"sport": "mlb", "season": 2026, "period": date,
                      "game_id": gid, "home": "AAA", "away": "BBB",
                      "home_score": runs_per_game / 2, "away_score": runs_per_game / 2,
                      "spread": 0.0, "total": None, "roof": "open",
                      "surface": "grass", "temp": None, "wind": None,
                      "extra": "generic"})
        umps.append({"sport": "mlb", "season": 2026, "period": date,
                     "game_id": gid, "umpire": ump})
        for team, pitcher in (("AAA", f"P{ump}A"), ("BBB", f"P{ump}B")):
            starters.append({"sport": "mlb", "season": 2026, "period": date,
                             "game_id": gid, "team": team, "pitcher": pitcher})
            logs.append({"sport": "mlb", "season": 2026, "period": date,
                         "game_id": f"{pitcher}-{date}", "player": pitcher,
                         "team": team, "opponent": "X", "position": "SP",
                         "home": 1, "market": "strikeouts",
                         "value": ks_per_starter})
    db.upsert_games(conn, games)
    db.upsert_game_umpires(conn, umps)
    db.upsert_game_starters(conn, starters)
    db.upsert_player_logs(conn, logs)


def test_profiles_measure_k_and_run_environment():
    conn = db.connect(":memory:")
    # Big Zone Bob: 8 games, starters average 8 Ks, 7 runs/game.
    # Tiny Zone Tim: 8 games, starters average 4 Ks, 10 runs/game.
    _seed(conn, "Big Zone Bob", [f"2026-06-{d:02d}" for d in range(1, 9)], 7.0, 8.0)
    _seed(conn, "Tiny Zone Tim", [f"2026-06-{d:02d}" for d in range(11, 19)], 10.0, 4.0)
    profs = umpire_profiles(conn)
    bob, tim = profs["Big Zone Bob"], profs["Tiny Zone Tim"]
    # Bob's games run K-heavy vs the pooled league sample; Tim's run K-light.
    assert bob.k_factor > 1.0 > tim.k_factor
    # And the run environment points the other way.
    assert bob.run_factor < 1.0 < tim.run_factor
    # Shrinkage + clamp keep even extreme splits inside a sane band.
    assert 0.90 <= tim.k_factor and bob.k_factor <= 1.10
    assert bob.games == 8


def test_attach_sets_factors_and_skips_unknowns():
    from engine.mlb.models import MLBGame
    profs = {"Big Zone Bob": UmpProfile("Big Zone Bob", k_factor=1.07,
                                        run_factor=0.96, games=20)}
    known = MLBGame(home="AAA", away="BBB", park="generic",
                    plate_umpire="Big Zone Bob")
    unannounced = MLBGame(home="CCC", away="DDD", park="generic")
    assert attach_umpires([known, unannounced], profs) == 1
    assert known.ump_k_factor == 1.07 and known.ump_run_factor == 0.96
    # No announcement -> exactly neutral, never a guess.
    assert unannounced.ump_k_factor == 1.0 and unannounced.ump_run_factor == 1.0


def test_projection_moves_with_the_ump():
    from engine.mlb.models import MLBGame, MLBProp, MLBGameLog, STRIKEOUTS
    from engine.mlb.projection import build_mlb_projection
    from engine.models import SportsbookLine

    def proj(k_factor):
        game = MLBGame(home="AAA", away="BBB", park="generic",
                       plate_umpire="Big Zone Bob", ump_k_factor=k_factor)
        prop = MLBProp("Ace Guy", "AAA", "BBB", "SP", STRIKEOUTS,
                       [MLBGameLog(i, "X", 7) for i in range(1, 11)], 7.0, None,
                       [SportsbookLine("proxy", 6.5)])
        return build_mlb_projection(prop, game)

    wide, neutral = proj(1.08), proj(1.0)
    assert wide.mean > neutral.mean
    assert any("Plate ump Big Zone Bob elevates strikeouts" in r
               for r in wide.reasons)
    assert not any("Plate ump" in r for r in neutral.reasons)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
