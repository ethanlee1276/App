"""Tests for the fantasy engine (in-memory SQLite, synthetic usage rows)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db
from engine.fantasy import (
    latest_season, usage_board, league_rates, buy_sell_board, game_scripts,
)


def _row(player, team, pos, wk, market, value, opp="OPP"):
    return {"sport": "nfl", "season": 2025, "period": f"{wk:03d}",
            "game_id": f"{team}-{wk:03d}", "player": player, "team": team,
            "opponent": opp, "position": pos, "home": 1,
            "market": market, "value": value}


def _seed(conn):
    rows = []
    # Riser: 20% target share for weeks 1-6, then 40% in week 7.
    # Steady: flat 40% all season. Team throws 30 targets/week split 3 ways.
    for wk in range(1, 8):
        riser_t = 12 if wk == 7 else 6
        steady_t = 12
        other_t = 30 - riser_t - steady_t
        rows += [_row("Riser", "KC", "WR", wk, "targets", riser_t),
                 _row("Riser", "KC", "WR", wk, "fp_ppr", riser_t * 1.8),
                 _row("Steady", "KC", "WR", wk, "targets", steady_t),
                 # Steady scores above his volume — sell-high bait.
                 _row("Steady", "KC", "WR", wk, "fp_ppr", steady_t * 1.8 + 5),
                 _row("Other", "KC", "WR", wk, "targets", other_t),
                 _row("Other", "KC", "WR", wk, "fp_ppr", other_t * 1.8),
                 # A bell-cow RB: 15 of the team's 25 carries, scores on volume.
                 _row("Bell Cow", "KC", "RB", wk, "carries", 15),
                 _row("Bell Cow", "KC", "RB", wk, "fp_ppr", 15 * 0.9),
                 _row("Backup", "KC", "RB", wk, "carries", 10),
                 # Backup scores BELOW his volume — buy-low bait.
                 _row("Backup", "KC", "RB", wk, "fp_ppr", 10 * 0.9 - 3)]
    db.upsert_player_logs(conn, rows)


def test_usage_board_surfaces_the_riser_first():
    conn = db.connect(":memory:")
    _seed(conn)
    assert latest_season(conn) == 2025
    board = usage_board(conn, 2025)
    # Biggest role changes on top — the delta is where the money is. Riser
    # (+20pt) and Other (-20pt, the targets Riser took) lead the board.
    assert {board[0]["player"], board[1]["player"]} == {"Riser", "Other"}
    r = next(b for b in board if b["player"] == "Riser")
    assert r["last"] == 0.4 and abs(r["l4"] - 0.2) < 1e-9
    assert abs(r["delta"] - 0.2) < 1e-9
    # RBs are measured on carry share.
    bell = next(b for b in board if b["player"] == "Bell Cow")
    assert bell["metric"] == "carry share" and bell["season"] == 0.6
    steady = next(b for b in board if b["player"] == "Steady")
    assert abs(steady["delta"]) < 0.01


def test_league_rates_recover_the_seeded_values():
    conn = db.connect(":memory:")
    _seed(conn)
    rates = league_rates(conn, 2025, min_rows=10)
    # WRs were seeded at ~1.8 PPR per target (plus Steady's bonus noise);
    # RBs at 0.9 per carry (minus Backup's shortfall).
    assert 1.6 <= rates["WR"][0] <= 2.2
    assert 0.5 <= rates["RB"][1] <= 1.1


def test_buy_sell_board_flags_the_right_players():
    conn = db.connect(":memory:")
    _seed(conn)
    bs = buy_sell_board(conn, 2025, min_fit_rows=10)
    assert any(r["player"] == "Backup" for r in bs["buy_low"])
    assert any(r["player"] == "Steady" for r in bs["sell_high"])
    # Volume-true players sit inside the sustainable band — never flagged.
    flagged = {r["player"] for r in bs["buy_low"] + bs["sell_high"]}
    assert "Bell Cow" not in flagged and "Riser" not in flagged


def test_game_scripts_archetypes_and_confidence():
    conn = db.connect(":memory:")
    games = [
        {"sport": "nfl", "season": 2026, "period": "001", "game_id": "BUF@KC",
         "home": "KC", "away": "BUF", "home_score": None, "away_score": None,
         "spread": -7.5, "total": 52.0, "roof": "open", "surface": "grass",
         "temp": None, "wind": None, "extra": None},
        {"sport": "nfl", "season": 2026, "period": "001", "game_id": "NYJ@NE",
         "home": "NE", "away": "NYJ", "home_score": None, "away_score": None,
         "spread": -1.5, "total": 38.5, "roof": "open", "surface": "grass",
         "temp": None, "wind": None, "extra": None},
        # A completed game never shows up as a script.
        {"sport": "nfl", "season": 2025, "period": "018", "game_id": "A@B",
         "home": "B", "away": "A", "home_score": 24, "away_score": 20,
         "spread": -3.0, "total": 44.0, "roof": "open", "surface": "grass",
         "temp": None, "wind": None, "extra": None},
    ]
    db.upsert_games(conn, games)
    scripts = game_scripts(conn)
    assert len(scripts) == 2
    kc = next(s for s in scripts if s["home"] == "KC")
    # 52 total, KC -7.5: implied 29.75 / 22.25, high-total big-spread read.
    assert kc["home_implied"] == 29.8 and kc["away_implied"] == 22.2
    assert kc["favorite"] == "KC"
    assert kc["archetype"] == "Favorite runs, dog throws"
    assert "79%" in kc["confidence"]
    ne = next(s for s in scripts if s["home"] == "NE")
    assert ne["archetype"] == "Nobody's good"
    assert "coin flip" in ne["confidence"]


def test_usage_rows_built_from_weekly_stats():
    from engine.ingest import nfl_usage_rows
    weekly = [{"position": "WR", "week": "3", "player_display_name": "Wide Out",
               "recent_team": "KC", "opponent_team": "LV", "targets": "9",
               "carries": "1", "receptions": "7", "receiving_air_yards": "88",
               "fantasy_points_ppr": "21.3"},
              {"position": "QB", "week": "3", "player_display_name": "Slinger",
               "recent_team": "KC", "opponent_team": "LV", "attempts": "38",
               "fantasy_points_ppr": "19.0"}]
    rows = nfl_usage_rows(weekly, 2025)
    wr = {r["market"]: r["value"] for r in rows if r["player"] == "Wide Out"}
    assert wr["targets"] == 9.0 and wr["air_yards"] == 88.0
    assert wr["fp_ppr"] == 21.3
    assert "pass_att" not in wr                     # QB-only market
    qb = {r["market"]: r["value"] for r in rows if r["player"] == "Slinger"}
    assert qb["pass_att"] == 38.0


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
