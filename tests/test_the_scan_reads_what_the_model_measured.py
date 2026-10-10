"""The scan's reads count what the model measured, and week 1 has a matchup.

Ethan, 2026-09-24, after the first scan: "clearly my test that I did with
the other AI does find edge … it predicted Chris Olave going off because
the Lions defense fucking sucks … Jahmyr Gibbs to get a touchdown … St.
Brown to get a touchdown … Sam LaPorta to get three catches … something
that our site did not recommend. So clearly there's a gap."

Two gaps were real, and this file holds both fixed:

* WEEK 1 HAD NO MATCHUP. engine/defensevs.ratings returned {} before any
  game was played, so every defence priced as average in week 1 — while
  weeks 2 and 3 ran about 90% on last season's rating. Last season's
  rating was measured on weeks 1-3 of 2022-2025 before it was used.
* THE SCAN COUNTED THE WRONG THINGS. Its reads counted unit EPA ranks (no
  lift in four seasons) and ignored the two things the model prices
  with: what the defence gives up in the bet's own stat, and the points
  the lines expect the team to score. Saints @ Lions read all four
  players neutral. The reads now count those, show the rest as notes,
  and point at the touchdown props.
"""
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import defensevs as D, gamescan as G                 # noqa: E402

NFLVERSE = open(os.path.join(ROOT, "engine", "sources", "nflverse.py"), encoding="utf-8").read()


def _row(team, opp, wk, pos, **stats):
    return {"season_type": "REG", "week": str(wk), "team": team, "opponent_team": opp,
            "position": pos, **{k: str(v) for k, v in stats.items()}}


def _season():
    rows = []
    for wk in range(1, 5):
        rows.append(_row("NO", "DET", wk, "WR", receiving_yards=150, receptions=11, receiving_tds=1))
        rows.append(_row("NO", "DET", wk, "QB", passing_yards=290, passing_tds=2))
        rows.append(_row("GB", "CHI", wk, "WR", receiving_yards=90, receptions=7, receiving_tds=0))
        rows.append(_row("GB", "CHI", wk, "QB", passing_yards=180, passing_tds=1))
    return rows


def test_week_one_starts_from_last_season():
    prior = D.ratings(_season(), 99)
    assert D.ratings([], 1, prior=prior) == {}, "the old behaviour, still the default (college)"
    wk1 = D.ratings([], 1, prior=prior, week_one_prior=True)
    det = wk1["DET"]["qb_pass_yds"]
    assert det["factor"] == prior["DET"]["qb_pass_yds"]["factor"] > 1.0
    assert det["games"] == 0 and det["last_season"] is True
    mult, why, card = D.effect("DET", wk1["DET"], "WR", "rec_yds")
    assert mult > 1.0 and "last season DET allowed the 1st-most passing yards" in why
    assert "no game yet this season" in card["text"] and card["last_season"]
    assert "DV.ratings(rows, upto_week, prior=prior, week_one_prior=True)" in NFLVERSE


def test_the_points_come_from_posted_lines_only():
    g = types.SimpleNamespace(home="DET", away="NO", total=49.5, spread=-7.0,
                              total_is_posted=True, spread_is_posted=True)
    pts, words = G.implied_points(g)
    assert pts == {"DET": 28.25, "NO": 21.25}
    assert words["DET"] == "−7 at home, total 49.5" and words["NO"] == "+7 on the road, total 49.5"
    g.total_is_posted = False
    assert G.implied_points(g) == ({}, {}), "a default 44 is not the market's opinion"


def test_the_reads_see_the_scorer_rows():
    result = {"recommendations": [{"player": "Amon-Ra St. Brown", "market": "rec_yds", "side": "OVER", "line": 74.5}],
              "longshot_watch": [{"player": "Jahmyr Gibbs", "market": "anytime_td", "side": "OVER", "line": 0.5}],
              "most_likely": [{"player": "Jahmyr Gibbs", "market": "anytime_td", "side": "yes", "line": None},
                              {"player": "Sam LaPorta", "market": "receptions", "side": "OVER", "line": 3.5}]}
    got = [(r["player"], r["market"]) for r in G.scan_props(result)]
    assert got == [("Amon-Ra St. Brown", "rec_yds"), ("Jahmyr Gibbs", "anytime_td")], \
        "each scorer once; Most Likely stat rows are already in recommendations"


def test_a_scorer_row_is_read_at_the_models_chance():
    usage = {("DET", "jahmyr gibbs"): {"carry_share": 0.6, "carries_pg": 15, "games": 17}}
    scan = G.scan_game("DET", "NO", ratings={"DET": {"off": {}, "def": {}}, "NO": {"off": {}, "def": {}}},
                       charts={}, defenders_now={}, usage=usage,
                       allowed={"NO": {"rb_td": {"rank": 4, "of": 32, "pg": 1.2}}},
                       points={"DET": 28.25}, line_words={"DET": "−7 at home, total 49.5"},
                       props=[{"player": "Jahmyr Gibbs", "team": "DET", "position": "RB",
                               "market": "anytime_td", "side": "OVER", "odds": -190, "model_prob": 0.66}])
    read = scan["players"][0]
    assert read["read"] in ("breakout", "good") and "anytime_td" in read["lean"]
    micro = scan["microscope"][0]
    assert (micro["market"], micro["prob"], micro["clears"]) == ("anytime_td", 0.66, True)


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
