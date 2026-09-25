"""The matchup scan ranks teams on THIS season once it has two games.

Ethan, 2026-09-25, on Jets @ Lions going into week 4 — the Jets' defence
27th, Detroit's 13th: "I know for a fact that the Jets defense is ranked
better then the lions defense right now ... Make sure we are using up to
date information." The ratings leaned on last season as four games' worth
of evidence, so week 4's ranks were 57% last season's, and the card never
said so. From two games on a rank is this season's alone
(gamescan.CURRENT_LEADS_GAMES, CURRENT_SHARE); before that the card says how much of it
is last season.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import gamescan as G                                 # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _rows(season, weeks, epa_allowed):
    """Two teams trading games; `epa_allowed` per team is what its defence
    gives up a play."""
    out = []
    for w in range(1, weeks + 1):
        for team, opp in (("NYJ", "DET"), ("DET", "NYJ")):
            out.append({"sport": "nfl", "season": season, "period": str(w), "team": team,
                        "side": "def", "opp": opp, "plays": 60, "epa": epa_allowed[team] * 60})
            out.append({"sport": "nfl", "season": season, "period": str(w), "team": team,
                        "side": "off", "opp": opp, "plays": 60, "epa": 0.0})
    return out


def test_three_games_lead_on_this_season_with_last_season_still_in():
    """Ethan, 2026-09-25, twice: the Jets' defence is better than Detroit's
    RIGHT NOW — and, the same night, "2026 data should outweigh 2025 data
    by just a tiny bit but 2025 data should def be used." So this season
    leads at CURRENT_SHARE from two games on and last season stays in."""
    last = _rows(2025, 17, {"NYJ": 0.15, "DET": -0.05})    # 2025: Jets' D poor, Detroit's good
    now = _rows(2026, 3, {"NYJ": -0.20, "DET": 0.05})      # 2026: the other way round, clearly
    r = G.ratings_from_rows(now, last)
    assert r["NYJ"]["blend"] == G.CURRENT_SHARE == 0.55 and r["NYJ"]["games"] == 3
    assert r["NYJ"]["def"]["overall"]["rank"] == 1, "the Jets' defence, this season leading"
    assert r["DET"]["def"]["overall"]["rank"] == 2
    # …and the number is the blend, not this season's alone: 55/45.
    assert abs(r["NYJ"]["def"]["overall"]["value"] - (0.55 * -0.20 + 0.45 * 0.15)) < 1e-6
    # A modest edge this season does not overturn a big gap last season —
    # that is the rule as asked ("outweigh … by just a tiny bit").
    r2 = G.ratings_from_rows(_rows(2026, 3, {"NYJ": -0.10, "DET": 0.05}), last)
    assert r2["DET"]["def"]["overall"]["rank"] == 1
    assert G.season_share(0) == 0.0 and G.season_share(1) == 0.2
    assert G.season_share(2) == G.season_share(10) == 0.55
    assert G.season_share(3, has_prior=False) == 1.0


def test_one_game_leans_on_last_season_and_says_how_much():
    last = _rows(2025, 17, {"NYJ": 0.15, "DET": -0.05})
    now = _rows(2026, 1, {"NYJ": -0.10, "DET": 0.05})
    r = G.ratings_from_rows(now, last)
    assert r["NYJ"]["blend"] == round(1 / (1 + G.PRIOR_GAMES), 2)


def test_the_card_says_which_season_the_ranks_are():
    fn = APP[APP.index("function scanTapeHTML("):]
    fn = fn[:fn.index("\n}\n")]
    assert "tapeBasis(scan, away, home)" in fn
    basis = APP[APP.index("function tapeBasis("):]
    basis = basis[:basis.index("\n}\n")]
    assert "last season" in basis and "this season" in basis


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
