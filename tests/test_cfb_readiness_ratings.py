"""CFB readiness audit, Phase 6 — what the ratings are built from.

Two defects the audit found in `cfb_build.py`'s rating step, pinned:
the build bypassed the pooled-season rule every other build runs, and an
FCS buy game counted at full weight in the FBS host's rating.
"""

import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db as hist_db
from engine import teamrates as TR


def _game(season, period, home, away, hs, as_):
    return {"sport": "cfb", "season": season, "period": period,
            "game_id": f"{away}@{home}-{period}", "home": home, "away": away,
            "home_score": hs, "away_score": as_, "spread": None, "total": None,
            "roof": "", "surface": "", "temp": None, "wind": None, "extra": None}


def _db():
    conn = hist_db.connect(":memory:")
    rows = []
    # last season: A beat B by 10 three times, B beat C by 10 three times
    for i in range(3):
        rows.append(_game(2025, f"2025-10-0{i+1}", "A", "B", 30, 20))
        rows.append(_game(2025, f"2025-10-1{i+1}", "B", "C", 30, 20))
    # this season: one game each; A hosts an FCS visitor and wins 70–0
    rows.append(_game(2026, "2026-09-05", "A", "espn:9999", 70, 0))
    rows.append(_game(2026, "2026-09-05", "B", "C", 24, 21))
    hist_db.upsert_games(conn, rows)
    return conn


def test_an_fcs_buy_game_is_left_out_when_asked_and_only_then():
    conn = _db()
    with_fcs = TR.compute_team_ratings(conn, "cfb", seasons=[2026], shrink=8.0)
    assert with_fcs["A"].games == 1 and "espn:9999" in with_fcs
    # 70–0 shrunk by 1/9: off (70−base)/9, def (0−base)/9 → net ≈ 70/9
    assert abs(with_fcs["A"].net - 70 / 9) < 1e-3      # rounded to 3 places
    without = TR.compute_team_ratings(conn, "cfb", seasons=[2026], shrink=8.0,
                                      exclude_prefix="espn:")
    assert "A" not in without and "espn:9999" not in without
    assert without["B"].games == 1 and without["C"].games == 1


def test_a_one_game_season_is_carried_by_last_season():
    conn = _db()
    got, used = TR.ratings_for_season(conn, "cfb", 2026, shrink=8.0,
                                      exclude_prefix="espn:")
    assert used == [2025, 2026]
    # A: three 10-point wins last year, no FBS game yet this year
    assert got["A"].games == 3 and got["A"].net > 0
    # B: 3 losses + 3 wins + one 3-point win → 7 games, near zero
    assert got["B"].games == 7
    assert got["C"].net < 0


def test_the_college_build_prices_on_the_adjusted_rating():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(here, "cfb_build.py"), encoding="utf-8").read()
    assert "teamrates.adjusted_ratings_for_season(" in src
    assert "home_field=fit.home_field" in src
    # the variance is re-fitted around the projection actually priced
    assert "fit_from_history(conn, all_seasons_adj or all_seasons" in src
    assert '"method": "opponent-adjusted"' in src


def test_the_college_build_uses_the_pooled_rule_like_every_other_build():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(here, "cfb_build.py"), encoding="utf-8").read()
    assert "teamrates.ratings_for_season(" in src
    assert 'exclude_prefix=_fallback' in src
    assert "seasons=[day.year])" not in src.split("ratings_for_season")[0][-400:]


# ---------------------------------------------------------------------------
# Opponent adjustment (Ethan, 2026-09-02: "3. Whatever u think" → built).
# ---------------------------------------------------------------------------

def _schedule_db():
    """D is a 30-point better team than C. A beat weak C by 20; B beat
    strong D by 3. Averaging margins says A > B; adjusting for who they
    played says B > A — B's three points came against a far better team."""
    conn = hist_db.connect(":memory:")
    rows = [_game(2026, "2026-09-05", "D", "C", 40, 10),
            _game(2026, "2026-09-12", "A", "C", 30, 10),
            _game(2026, "2026-09-12", "B", "D", 24, 21),
            _game(2026, "2026-09-19", "C", "D", 7, 35),
            _game(2026, "2026-09-19", "D", "A", 28, 14)]
    hist_db.upsert_games(conn, rows)
    return conn


def test_opponent_adjustment_credits_the_schedule():
    conn = _schedule_db()
    plain = TR.compute_team_ratings(conn, "cfb", seasons=[2026], shrink=2.0)
    adj = TR.compute_adjusted_ratings(conn, "cfb", seasons=[2026], shrink=2.0)
    assert plain["A"].net > plain["B"].net, (plain["A"], plain["B"])
    assert adj["B"].net > adj["A"].net, (adj["B"], adj["A"])
    assert adj["D"].net > adj["A"].net > adj["C"].net
    assert all(r.games == plain[t].games for t, r in adj.items())
    # the contract every consumer relies on: net = off − def
    for r in adj.values():
        assert abs(r.net - (r.off - r.def_)) < 2e-3


def test_the_adjusted_rating_reproduces_a_planted_structure():
    """Four teams, every pair home and away, true strengths +9/+3/−3/−9
    and a 3-point home field: with no shrink the solver must hand the
    strengths back (up to the ridge, set to 0 here)."""
    conn = hist_db.connect(":memory:")
    true = {"W": 9.0, "X": 3.0, "Y": -3.0, "Z": -9.0}
    base = TR.SCORING_BASELINE.get("cfb", 0.0) or 27.0
    TR.SCORING_BASELINE["cfb"] = base
    rows, i = [], 0
    for h in true:
        for a in true:
            if h == a:
                continue
            i += 1
            margin = true[h] - true[a] + 3.0
            rows.append(_game(2026, f"2026-10-{i:02d}", h, a,
                              base + margin / 2, base - margin / 2))
    hist_db.upsert_games(conn, rows)
    adj = TR.compute_adjusted_ratings(conn, "cfb", seasons=[2026], shrink=0.0,
                                      home_field=3.0)
    for t, v in true.items():
        assert abs(adj[t].net - v) < 0.05, (t, adj[t].net, v)


def test_the_adjusted_pooling_follows_the_same_rule():
    conn = _db()
    got, used = TR.adjusted_ratings_for_season(conn, "cfb", 2026, shrink=8.0,
                                               exclude_prefix="espn:")
    assert used == [2025, 2026]
    assert "espn:9999" not in got and got["A"].games == 3


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
