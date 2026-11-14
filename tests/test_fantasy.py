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




def _seed_a_quarterback(conn):
    """Twelve weeks of the shape that breaks a touch fit: heavy scoring,
    almost no touches. Two scrambles a week and 22 PPR points, because
    the points came from throwing and throwing is not a regressor."""
    rows = []
    for wk in range(1, 13):
        rows += [_row("Pocket Passer", "BUF", "QB", wk, "carries", 2),
                 _row("Pocket Passer", "BUF", "QB", wk, "fp_ppr", 22.0)]
    db.upsert_player_logs(conn, rows)


def test_the_touch_fit_refuses_the_position_it_cannot_price():
    """`fp ≈ a*targets + b*carries` with no intercept cannot see passing,
    so for a quarterback the coefficients absorb whatever correlates with
    him playing. Both boards already skip QBs before looking a rate up —
    but `fantasy_build` publishes this dict into fantasy.json whole, so
    the fabricated coefficients shipped to the browser with nothing
    reading them. Absent beats approximate."""
    conn = db.connect(":memory:")
    _seed(conn)
    _seed_a_quarterback(conn)
    rates = league_rates(conn, 2025, min_rows=10)
    assert "QB" not in rates, rates
    # The real positions are untouched — this refuses one fit, it does
    # not narrow the board.
    assert "WR" in rates and "RB" in rates, rates


def test_what_the_quarterback_fit_would_have_claimed():
    """The stakes, stated as arithmetic rather than as an opinion.

    Two carries a week and 22 points: a fit that sees only carries has to
    put 11 PPR points on a carry, and the 3.0 clamp then files that as a
    plausible-looking 3.0. That is the failure mode — not an obviously
    broken number, a fabricated one of believable size.
    """
    from engine.fantasy import NO_VOLUME_FIT
    conn = db.connect(":memory:")
    _seed_a_quarterback(conn)
    assert 22.0 / 2 > 3.0, "the seed no longer produces a clamped fit"
    assert "QB" in NO_VOLUME_FIT
    assert league_rates(conn, 2025, min_rows=10) == {}


def test_both_boards_still_agree_with_the_fit_about_quarterbacks():
    """The refusal is not a new rule, it is the rule both consumers
    already followed moved to where the number is made. If either board
    ever stops skipping QBs it will now get None instead of a fake
    coefficient, which is the safe direction."""
    import inspect
    from engine import fantasy, fantasy_draft
    for src in (inspect.getsource(fantasy.buy_sell_board),
                inspect.getsource(fantasy_draft._players)):
        assert '"QB"' in src, "a board stopped naming the position it skips"



def test_the_first_weeks_of_a_season_read_what_they_have():
    """Ethan, 2026-09-14, the Monday after Week 1: "the fantasy pages
    including the calendar is completely empty." Four weeks is the
    floor once four weeks exist; before that the floor is the season's
    own age, and every row says how many weeks it stands on."""
    from engine.fantasy import week_floor, weeks_ingested, _weekly
    conn = db.connect(":memory:")
    rows = []
    for wk in (1,):
        rows += [_row("Riser", "KC", "WR", wk, "targets", 6),
                 _row("Riser", "KC", "WR", wk, "fp_ppr", 10),
                 _row("Steady", "KC", "WR", wk, "targets", 12),
                 _row("Steady", "KC", "WR", wk, "fp_ppr", 20)]
    db.upsert_player_logs(conn, rows)
    data = _weekly(conn, 2025)
    assert weeks_ingested(data) == 1 and week_floor(data) == 1
    board = usage_board(conn, 2025)
    assert {b["player"] for b in board} == {"Riser", "Steady"}
    assert all(b["weeks"] == 1 and b["l4"] is None and b["delta"] == 0.0 for b in board)
    # The floor grows with the season and stops at four: with six weeks
    # in, a two-week player is still cut.
    conn2 = db.connect(":memory:")
    _seed(conn2)                                       # seven weeks
    db.upsert_player_logs(conn2, [_row("Late Add", "KC", "WR", 6, "targets", 4),
                                  _row("Late Add", "KC", "WR", 7, "targets", 4)])
    assert week_floor(_weekly(conn2, 2025)) == 4
    assert "Late Add" not in {b["player"] for b in usage_board(conn2, 2025)}


def test_buy_sell_reads_the_first_weeks_too():
    conn = db.connect(":memory:")
    rows = []
    for wk in (1, 2):
        rows += [_row("Bell Cow", "KC", "RB", wk, "carries", 15),
                 _row("Bell Cow", "KC", "RB", wk, "fp_ppr", 15 * 0.9),
                 _row("Backup", "KC", "RB", wk, "carries", 10),
                 _row("Backup", "KC", "RB", wk, "fp_ppr", 10 * 0.9 - 4)]
    db.upsert_player_logs(conn, rows)
    bs = buy_sell_board(conn, 2025, min_fit_rows=2)
    names = {r["player"] for rows in bs.values() if isinstance(rows, list) for r in rows}
    assert "Backup" in names, bs


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
