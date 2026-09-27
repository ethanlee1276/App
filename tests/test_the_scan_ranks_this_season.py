"""The matchup scan's ranks: this season and last, and how much of each.

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


def test_this_season_takes_over_as_its_games_come_in():
    """Ethan, 2026-09-25, twice: the Jets' defence is better than Detroit's
    RIGHT NOW — and, the same night, "2025 data should def be used." That
    was first a flat 55% this season from two games on. MEASURED on
    2022-2025 (scanblendfit.py, 2026-09-27), two or three games predict
    the rest of a season less than that: the best share grows with the
    games, games / (games + 6). So a clear turnaround shows by midseason,
    not after two weeks, and last season never leaves."""
    last = _rows(2025, 17, {"NYJ": 0.15, "DET": -0.05})    # 2025: Jets' D poor, Detroit's good
    three = G.ratings_from_rows(_rows(2026, 3, {"NYJ": -0.20, "DET": 0.05}), last)
    assert three["NYJ"]["blend"] == round(3 / 9, 2) and three["NYJ"]["games"] == 3
    assert abs(three["NYJ"]["def"]["overall"]["value"] - (3 / 9 * -0.20 + 6 / 9 * 0.15)) < 1e-4
    assert three["DET"]["def"]["overall"]["rank"] == 1, "three games are not yet enough"
    six = G.ratings_from_rows(_rows(2026, 6, {"NYJ": -0.20, "DET": 0.05}), last)
    assert six["NYJ"]["blend"] == 0.5
    assert six["NYJ"]["def"]["overall"]["rank"] == 1, "by six the turnaround leads"
    assert G.unit_share(0) == 0.0 and G.unit_share(2) == 0.25 and G.unit_share(6) == 0.5
    assert abs(G.unit_share(3, new_qb=True) - 3 / 6.5) < 1e-12, "a new QB's offence takes over faster"
    assert G.unit_share(3, has_prior=False) == 1.0
    # Player usage keeps its own split; nothing measured it yet.
    assert G.season_share(2) == G.season_share(10) == 0.55


def test_one_game_leans_on_last_season_and_says_how_much():
    last = _rows(2025, 17, {"NYJ": 0.15, "DET": -0.05})
    now = _rows(2026, 1, {"NYJ": -0.10, "DET": 0.05})
    r = G.ratings_from_rows(now, last)
    assert r["NYJ"]["blend"] == round(1 / (1 + G.UNIT_PRIOR_GAMES), 2)


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
