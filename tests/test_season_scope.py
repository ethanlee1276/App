"""More history must not silently rewrite what "this season" means.

Backfilling 2021-2026 was supposed to help — deeper variance fits, real
calibration, walk-forward backtests. But two live code paths read the
history table with no season bound, which was *correct by accident* while
only the current season was ingested. The moment the backfill landed they
started answering a different question:

  * MLB form blends a "season" window at 20%; unbounded, that window
    became a six-year career average.
  * CFB team ratings would rate a roster that turns over ~25% a year on
    players who have graduated.

These tests pin the season bound so a future refactor cannot quietly
widen it again.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.db import connect, upsert_player_logs
from engine.mlb.bookmenu import logs_by_player, add_book_listed_props


def _log(season, day, player, value, team="NYY", opponent="BOS"):
    return {"sport": "mlb", "season": season, "period": f"{season}-0{day}",
            "game_id": f"{season}{day}", "player": player, "team": team,
            "opponent": opponent, "position": "OF", "home": 1,
            "market": "total_bases", "value": value}


def _seed():
    """A player who was excellent years ago and ordinary now."""
    conn = connect(":memory:")
    rows = [_log(2021, d, "Old Timer", 4.0) for d in range(1, 6)]
    rows += [_log(2026, d, "Old Timer", 1.0) for d in range(1, 6)]
    upsert_player_logs(conn, rows)
    return conn


def test_logs_by_player_bounds_to_the_requested_season():
    conn = _seed()
    rec = logs_by_player(conn, "total_bases", seasons=[2026])["old timer"]
    assert len(rec["logs"]) == 5
    # Every log is from 2026 — none of the 4.0s from five years ago.
    assert all(g.value == 1.0 for g in rec["logs"])
    assert all(g.date.startswith("2026") for g in rec["logs"])


def test_unbounded_call_still_returns_everything():
    """The backtest wants all of it; only the live path narrows."""
    conn = _seed()
    rec = logs_by_player(conn, "total_bases")["old timer"]
    assert len(rec["logs"]) == 10


def test_book_menu_prop_carries_only_current_season_form():
    """The whole point: a prop built from the book's menu must project the
    player who exists now, not his 2021 self."""
    conn = _seed()

    class _Slate:
        props: list = []

    slate = _Slate()
    slate.props = []
    book_only = [{"player": "Old Timer", "market": "total_bases",
                  "home": "NYY", "away": "BOS",
                  "lines": [{"book": "dk", "line": 1.5,
                             "over_odds": -110, "under_odds": -110}]}]
    added = add_book_listed_props(slate, book_only, conn, seasons=[2026])
    assert added == 1
    prop = slate.props[0]
    assert len(prop.logs) == 5
    # career_avg here is the average of the logs handed in. Season-scoped
    # that is 1.0; unbounded it would be 2.5 and the prop would look like a
    # screaming over on a 1.5 line.
    assert abs(prop.career_avg - 1.0) < 1e-6


def test_cfb_ratings_are_fit_on_one_season():
    """`cfb_build` must scope team ratings to the season being built.

    Read at the source level on purpose: the alternative is standing up a
    full CFB build, and what needs pinning is one argument.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "cfb_build.py")).read()
    i = src.index("compute_team_ratings(conn, \"cfb\"")
    call = src[i:src.index(")", src.index("shrink", i))]
    assert "seasons=" in call, (
        "cfb_build must bound team ratings to one season — college rosters "
        "turn over every year, so an unbounded fit rates graduated players")


def test_team_form_baseline_stops_at_the_season_boundary():
    """"season run differential" must mean THIS season.

    Unbounded it becomes a multi-year average, so a team playing exactly to
    its current normal reads as hot or cold purely because a past year was
    different.
    """
    from engine.db import connect as _c, upsert_games
    from engine.mlb.teamform import team_form

    conn = _c(":memory:")
    rows = []
    gid = 0

    def _g(season, date, home, away, hs, as_):
        nonlocal gid
        gid += 1
        return {"sport": "mlb", "season": season, "period": date,
                "game_id": str(gid), "home": home, "away": away,
                "home_score": hs, "away_score": as_}

    # 2025: AAA was a juggernaut, winning by 10 every night into October.
    for d in range(1, 9):
        rows.append(_g(2025, f"2025-09-{d:02d}", "AAA", "BBB", 10, 0))
    # 2026: a different roster — still winning, but by exactly 1.
    for d in range(1, 9):
        rows.append(_g(2026, f"2026-07-{d:02d}", "AAA", "BBB", 5, 4))
    upsert_games(conn, rows)

    f = team_form(conn, "2026-07-09", window_days=7)["AAA"]
    # Baseline is 2026's +1.0, not the +5.5 a two-year blend would give —
    # under which this team's ordinary week would read as ice cold.
    assert abs(f["season_diff_pg"] - 1.0) < 1e-6
    assert abs(f["delta_diff"]) < 1e-6, (
        "delta_diff compared this week against a multi-year baseline")
    # 8 wins this season, not 16 — the streak must not run through an
    # offseason and chain last September's wins onto this July's.
    assert f["streak"] == 8


def test_recent_seasons_spans_the_turn_of_the_year():
    """An NBA game in March belongs to the season that started last October."""
    from engine.seasons import season_of, recent_seasons

    assert season_of("nba", "2022-03-05") == 2021
    assert season_of("nba", "2021-11-05") == 2021
    assert season_of("mlb", "2026-07-31") == 2026     # inside one year
    # Live projections read this season and last — 20 games of "recent form"
    # in November reach back into the previous season.
    assert recent_seasons("nba", "2026-11-05") == [2026, 2025]


def test_nba_player_history_bounds_to_the_seasons_asked_for():
    from engine.db import connect as _c, upsert_player_logs
    from nba_build import player_history

    conn = _c(":memory:")
    logs = []
    for season, date in ((2021, "2022-03-05"), (2026, "2026-11-05")):
        for m, v in (("min", 30.0), ("pts", 20.0), ("reb", 5.0), ("ast", 4.0)):
            logs.append({"sport": "nba", "season": season, "period": date,
                         "game_id": f"g{season}", "player": "A Guard",
                         "team": "BOS", "opponent": "MIA", "position": "S",
                         "home": 1, "market": m, "value": v})
    upsert_player_logs(conn, logs)

    wide = player_history(conn, {"BOS"}, sport="nba")
    assert len(wide["A Guard"]["by_week"]) == 2
    recent = player_history(conn, {"BOS"}, sport="nba", seasons=[2026, 2025])
    assert list(recent["A Guard"]["by_week"]) == ["2026-11-05"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
