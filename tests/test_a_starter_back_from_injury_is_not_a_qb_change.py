"""A team's usual quarterback back from injury is a return, not a change.

Ethan, 2026-09-26, on Seattle's "QB change: Sam Darnold starts over Drew
Lock": "Drew Lock has started one game for Seattle so far in 2026, and it
was week two versus Arizona. He did not start week one, but Darnold did get
injured and Lock took over. For the 2025 season, Lock did not start any
games." Two games of volume made Lock the "starter", so the depth chart
naming Darnold again read as a benching. engine/qbchange now knows each
team's usual starter (last season's leading passer, or this season's
first game's) and calls it what it is: he is back, nothing is marked down.
"""
import os
import sys
from types import SimpleNamespace as NS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import qbchange as Q                                      # noqa: E402


def _row(name, team, week, att, yds):
    return {"player_display_name": name, "recent_team": team, "position": "QB",
            "season_type": "REG", "week": week, "attempts": att, "passing_yards": yds}


def _seattle():
    specs = [NS(player="Drew Lock", position="QB", usage_role="starter"),
             NS(player="Sam Darnold", position="QB", usage_role="backup")]
    prior = [_row("Sam Darnold", "SEA", w, 32, 250) for w in range(1, 18)] + [_row("Drew Lock", "SEA", 9, 3, 12)]
    # Week 1: Darnold hurt early, Lock threw more; week 2 Lock started.
    now = [_row("Sam Darnold", "SEA", 1, 9, 70), _row("Drew Lock", "SEA", 1, 24, 190),
           _row("Drew Lock", "SEA", 2, 36, 260)]
    return Q.quarterbacks(specs, now, prior, 3, lambda p: "SEA")


def test_the_usual_starter_is_last_seasons_leader():
    qb = _seattle()
    assert qb["teams"]["SEA"]["starter"] == "Drew Lock", "volume alone still ranks Lock first"
    assert "Sam Darnold" in qb["usual"]["SEA"]


def test_darnold_back_at_qb1_is_a_return_and_moves_nothing():
    ch = Q.changes(_seattle(), [], {"SEA": "Sam Darnold"})["SEA"]
    assert (ch["status"], ch["tier"], ch["replacement"]) == ("RETURNS", "return", "Sam Darnold"), ch
    assert Q.headline(ch) == "Sam Darnold is back at QB — Drew Lock started while he was out"
    assert "starts over" not in Q.headline(ch)
    wr = NS(team="SEA", position="WR", market="rec_yds", player="Jaxon Smith-Njigba")
    mult, reason, card = Q.effect(wr, NS(qb_changes={"SEA": ch}))
    assert mult == 1.0 and reason == "" and card["note"] == "His usual quarterback is back — nothing to adjust"
    own = Q.effect(NS(team="SEA", position="QB", market="pass_yds", player="Sam Darnold"),
                   NS(qb_changes={"SEA": ch}))[2]
    assert own["note"] == "Back as the starter; Drew Lock started while he was out"


def test_a_real_benching_is_still_a_change():
    qb = {"teams": {"KC": {"starter": "Patrick Mahomes", "backup": "Gardner Minshew"}},
          "passing": {"Patrick Mahomes": (600.0, 4000.0)}, "usual": {"KC": ["Patrick Mahomes"]}}
    ch = Q.changes(qb, [], {"KC": "Gardner Minshew"})["KC"]
    assert ch["status"] == "BENCHED" and "starts over Patrick Mahomes" in Q.headline(ch)


def test_the_page_and_the_scenario_say_it():
    js = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    assert js.count('status === "RETURNS" ? "QB back" : "QB change"') == 2
    from engine import tdscenarios as S
    read = {"player": "Jaxon Smith-Njigba", "team": "SEA", "opp": "WAS", "pos": "WR",
            "usage": {"tgt_share": 0.41}, "td": {"model_prob": 0.44, "odds": 105, "book": "BetMGM",
                                                  "implied_total": 24.0, "rz_chances": 3.1,
                                                  "qb_change": "Sam Darnold is back at QB — Drew Lock started while he was out"}}
    s = S.score(read, {"def": {"passing": {"rank": 28}}}, rz_own={"off": 12.1, "off_rel": 0.38},
                rz_opp={"def": 8.5, "def_rel": -0.04})
    assert any(l.startswith("QB: Sam Darnold is back at QB") for l in s["lines"]), s["lines"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
