"""The touchdown value board keeps a census of why each scorer was refused.

It sat empty all of 2026-09-25 (long_shots: 0 on every build) with no
record of which bar turned each man away — Ethan: "I only see minus 100
and minus 200 bets in the most likely bets." `touchdowns.value_board_census`
counts the refusals (outside the odds window, model too far from the
price, no edge after the market shrink, under the grade bar, the
concentration cap) and names the nearest misses with the numbers the bar
read; `build_td_longshots` fills it into the board's td_census.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import touchdowns as T                               # noqa: E402
from engine.longshots import LongShot                            # noqa: E402


def _ls(player, odds, model, implied, ev, grade, caveats=()):
    return LongShot(player=player, team="BAL", opponent="DAL", market="anytime_td",
                    market_label="Anytime TD", book="BetMGM", odds=odds, model_prob=model,
                    implied_prob=implied, edge=round(model - implied, 4), ev_per_unit=ev,
                    confidence=5.0, stake_units=0.0, grade=grade, expected_opportunities=2.0,
                    primary_reason="", caveats=list(caveats), book_prob=implied)


def test_every_refusal_is_counted_and_the_nearest_misses_are_named():
    picked = _ls("Derrick Henry", -212, 0.64, 0.60, 0.05, "B")
    graded = [picked,
              _ls("Zay Flowers", 125, 0.52, 0.44, 0.09, "Pass"),                      # graded Pass with EV: under the bar
              _ls("Rashod Bateman", 300, 0.30, 0.22, -0.01, "Pass"),                   # no EV
              _ls("Mark Andrews", 150, 0.41, 0.33, 0.03, "Pass",
                  caveats=["Model disagrees with the market by 16% — too large to trust, treated as a pricing/data error"]),
              _ls("Justice Hill", 400, 0.20, 0.17, 0.02, "C")]                          # graded, not picked: the cap
    c = T.value_board_census(candidates=[None] * 9, graded=graded, picked=[picked], outside=4)
    assert c["priced"] == 9 and c["graded"] == 5 and c["picked"] == 1
    assert c["refused"] == {"under the grade bar": 1, "no edge after the market shrink": 1,
                            "model too far from the price": 1, "concentration cap": 1,
                            "outside the odds window": 4}, c["refused"]
    assert [r["player"] for r in c["nearest"]] == ["Zay Flowers", "Mark Andrews", "Justice Hill", "Rashod Bateman"]
    z = c["nearest"][0]
    assert (z["model_prob"], z["book_prob"], z["edge"], z["ev"], z["grade"], z["why"]) == \
        (0.52, 0.44, 0.08, 0.09, "Pass", "under the grade bar")


def test_the_builder_fills_it_and_the_board_publishes_it():
    src = open(os.path.join(ROOT, "engine", "touchdowns.py"), encoding="utf-8").read()
    assert 'census["value_board"] = value_board_census(candidates, picks, chosen, outside)' in src
    pipe = open(os.path.join(ROOT, "engine", "pipeline.py"), encoding="utf-8").read()
    assert "build_td_longshots(candidates, census=census)" in pipe
    assert '"td_census": td_census,' in pipe, "the census is on the board"
    assert T.CENSUS_NEAREST == 10


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
