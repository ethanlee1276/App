"""The Most Likely board's -250 cap covers everything pooled into it.
Ethan, 2026-09-27, on Gibbs at -320 seated as a Top pick through the
matchup picks while the main list would never post him: "Yes cap at -250,
and make sure the matchup picks are wrapped in the most likely picks"."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import likelyboard as LB                                # noqa: E402
from engine import matchpicks as MP                                 # noqa: E402
from engine import tdscenarios as TS                                # noqa: E402
from engine.likely import HEAVIEST_PRICE                            # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _td(player, odds, prob, **kw):
    return {"kind": "td", "player": player, "team": "DET", "opponent": "NYJ", "position": "RB",
            "market": "anytime_td", "market_label": "Anytime TD", "side": "YES", "line": 0.5,
            "odds": odds, "book": "DraftKings", "model_prob": prob, **kw}


def test_one_cap_everywhere():
    assert HEAVIEST_PRICE == -250 and MP.PROP_MAX_JUICE == HEAVIEST_PRICE


def test_pooled_rows_past_the_cap_are_listed_not_seated():
    result = {"games": [], "most_likely": [],
              "matchup_picks": [{"away": "NYJ", "home": "DET",
                                 "td": [_td("Jahmyr Gibbs", -320, 0.70), _td("Amon-Ra St. Brown", -125, 0.55)],
                                 "props": []}],
              "td_scenarios": [_td("David Montgomery", -270, 0.60)]}
    board = LB.build(result)
    seated = {r["player"] for r in board["rows"]}
    assert seated == {"Amon-Ra St. Brown"}
    assert {(c["player"], c["odds"], c["source"]) for c in board["capped"]} == {
        ("Jahmyr Gibbs", -320, "matchup"), ("David Montgomery", -270, "scenario")}


def test_the_main_lists_held_pick_is_its_own_business():
    # A pick the main list posted and then held after its price moved past
    # the cap keeps its seat — "a posted pick never disappears".
    held = _td("Derrick Henry", -270, 0.68, held=True)
    board = LB.build({"games": [], "most_likely": [held], "matchup_picks": [], "td_scenarios": []})
    assert [r["player"] for r in board["rows"]] == ["Derrick Henry"] and board["capped"] == []


def test_the_scenarios_and_matchup_picks_refuse_it_at_the_source():
    assert TS._past_cap(-320) and TS._past_cap("-251") and not TS._past_cap(-250) and not TS._past_cap(None)
    src = open(os.path.join(ROOT, "engine", "matchpicks.py"), encoding="utf-8").read()
    assert src.count('< PROP_MAX_JUICE') >= 2, "the touchdown picks and the prop picks both hold to it"


def test_the_page_folds_matchup_picks_and_scenarios_into_the_board():
    assert 'function matchupPicksHTML() {\n  if (oneBoardOn()) return "";' in APP
    assert 'function tdScenariosHTML() {\n  if (oneBoardOn()) return "";' in APP
    assert "if (oneBoardOn()) return obGameHTML(g);" in APP


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
