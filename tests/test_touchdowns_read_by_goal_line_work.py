"""Touchdowns read the way the other model reads them: goal-line work,
counted, and every scorer in the game ranked with his seat.

Ethan, 2026-09-27, with its Jets @ Lions and Chargers @ Bills touchdown
reports: "this is how I want us searching for touchdown picks for the most
likely bets". Every one of its scorers starts from goal-line work in plain
counts — Gibbs "11 red-zone carries, 5 inside the 5", St. Brown "6
red-zone targets, 3 inside the 10" — and each game ends in a ranked table
of six candidates with the reason each is or is not a pick ("Gibbs = the
most likely TD, but the price kills it").

Measured first (engine/tdfeatures, 22,099 graded player-weeks): the
counts add nothing to the chance itself (AUC 0.7212 -> 0.7214), because
xFP and the red-zone share already carry them. So the chance is
untouched; what changes is what the card SAYS and the game plan's new
"Who scores" step.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import gameplan as P                                  # noqa: E402
from engine import gate                                            # noqa: E402
from engine.touchdowns import RedZoneUsage                         # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def test_goal_line_work_reads_as_counts():
    # Gibbs through two games: 11 red-zone carries, 5 inside the 5, 2
    # red-zone targets, 1 inside the 10 — stored as per-game averages.
    rz = RedZoneUsage(carries_inside_5=2.5, carries_inside_10=5.5, targets_inside_10=1.0,
                      targets_goal_line=0.5, rz_touch_share=0.6, measured=True, games=2)
    assert rz.goal_line() == {"games": 2, "rz_car": 11, "i5_car": 5, "rz_tgt": 2, "i10_tgt": 1}
    assert rz.goal_line_text() == ("11 red-zone carries (5 inside the 5), 2 red-zone targets "
                                   "(1 inside the 10) in his last 2 games")
    st = RedZoneUsage(targets_inside_10=3.0, targets_goal_line=1.5, measured=True, games=2)
    assert st.goal_line_text() == "6 red-zone targets (3 inside the 10) in his last 2 games"
    assert RedZoneUsage(measured=False, games=0).goal_line_text() == ""
    assert RedZoneUsage(measured=True, games=1).goal_line_text() == "No red-zone touches in his last 1 game"


def test_the_touchdown_chain_says_it_and_carries_it():
    from engine import touchdowns as T
    from engine.models import Prop, Game, Team, DefenseProfile, Weather, ANYTIME_TD
    prop = Prop(player="Jahmyr Gibbs", team="DET", opponent="NYJ", position="RB", market=ANYTIME_TD,
                logs=[], career_avg=0.0, vs_opponent_avg=None, lines=[])
    game = Game(home="DET", away="NYJ", weather=Weather(dome=True, measured=True), total=48.5, spread=-6.5)
    opp = Team(abbr="NYJ", name="NYJ", defense=DefenseProfile(team="NYJ"))
    rz = RedZoneUsage(carries_inside_5=2.5, carries_inside_10=5.5, targets_inside_10=1.0,
                      targets_goal_line=0.5, rz_touch_share=0.6, measured=True, games=2)
    p_with, info = T.td_probability(prop, game, opp, 0.3, red_zone=rz)
    assert "Goal-line work: 11 red-zone carries (5 inside the 5)" in " ".join(info["reasons"])
    assert info["goal_line"]["i5_car"] == 5 and info["goal_line_text"].startswith("11 red-zone carries")
    rz_same = RedZoneUsage(carries_inside_5=2.5, carries_inside_10=5.5, targets_inside_10=1.0,
                           targets_goal_line=0.0, rz_touch_share=0.6, measured=True, games=2)
    assert T.td_probability(prop, game, opp, 0.3, red_zone=rz_same)[0] == p_with, \
        "said, not re-counted: the counts measured to add nothing to the chance"


GAME = {"home": "DET", "away": "NYJ", "date": "2026-09-27", "kickoff": "13:00", "spread": -6.5, "total": 48.5,
        "scan": {"units": {}, "injuries": [], "method": {"teams": 32}}}


def _scorer(player, team, prob, odds, **kw):
    return {"player": player, "team": team, "opponent": "NYJ" if team == "DET" else "DET",
            "position": kw.pop("position", "RB"), "model_prob": prob, "odds": odds, "book": "DraftKings",
            "implied_total": 27.5 if team == "DET" else 21.0, **kw}


FIELD = [
    _scorer("Jahmyr Gibbs", "DET", 0.70, -320,
            goal_line_text="11 red-zone carries (5 inside the 5) in his last 2 games"),
    _scorer("Amon-Ra St. Brown", "DET", 0.61, -125, position="WR",
            goal_line_text="6 red-zone targets (3 inside the 10) in his last 2 games"),
    _scorer("Breece Hall", "NYJ", 0.57, -105),
    _scorer("Sam LaPorta", "DET", 0.40, 195, position="TE"),
    _scorer("Garrett Wilson", "NYJ", 0.37, 180, position="WR"),
    _scorer("Jameson Williams", "DET", 0.36, 165, position="WR"),
    _scorer("Adonai Mitchell", "NYJ", 0.30, 260, position="WR", injury_status="Questionable"),
    _scorer("Other Game", "KC", 0.80, -200),
]
BOARD = [{"player": "Amon-Ra St. Brown", "market": "anytime_td", "game": "NYJ@DET", "tier": "top",
          "tier_label": "Top pick"}]


def test_who_scores_ranks_the_game_and_says_each_seat():
    rows = P.who_scores(GAME, FIELD, BOARD, None)
    assert [r["player"] for r in rows] == ["Jahmyr Gibbs", "Amon-Ra St. Brown", "Breece Hall", "Sam LaPorta",
                                           "Garrett Wilson", "Jameson Williams"], \
        "six, likeliest first; a questionable player and another game's are not in it"
    gibbs, asb, hall, laporta = rows[:4]
    assert gibbs["why"][0] == "11 red-zone carries (5 inside the 5) in his last 2 games"
    assert gibbs["why"][-1].startswith("Likely — but -320 is past the board's -250 cap, so it is priced out")
    assert asb["on_board"] and asb["why"][-1] == "On the Most Likely board — Top pick."
    assert hall["why"][-1] == "Clears the bar; the board's seats went to likelier picks."
    assert laporta["why"][-1].startswith("A real chance, not a likely one")


def test_the_plan_carries_it_and_the_field_is_paid():
    plans = P.build({"games": [GAME], "td_field": FIELD, "likely_board": {"rows": BOARD}}, "nfl")
    steps = [s["key"] for s in plans[0]["steps"]]
    assert steps.index("who") == steps.index("matchup") + 1
    assert "td_field" in gate.PAID_KEYS
    assert "${step(by.who, rows(by.who, \"who\"))}" in APP
    src = open(os.path.join(ROOT, "engine", "pipeline.py"), encoding="utf-8").read()
    assert '"td_field": [{k: r.get(k) for k in _TD_FIELD_KEYS} for r in ls_watch]' in src
    usage = open(os.path.join(ROOT, "engine", "nflusage.py"), encoding="utf-8").read()
    assert "'i10_tgt')" in usage


def test_a_quarterbacks_touchdown_rate_is_scaled_as_measured():
    """tdearlyfit / the replay: quarterbacks claimed 11.2% and scored 14.5%
    after calibration; ×1.40 on the rate, fitted leave-one-season-out
    (1.35-1.55 every fold), lands the held-out seasons at 14.6% vs 14.5%."""
    from engine import touchdowns as T
    from engine.models import Prop, Game, Team, DefenseProfile, Weather, ANYTIME_TD
    assert T.QB_TD_RATE_SCALE == 1.40
    game = Game(home="BUF", away="LAC", weather=Weather(dome=True, measured=True), total=50.0, spread=-7.0)
    opp = Team(abbr="LAC", name="LAC", defense=DefenseProfile(team="LAC"))

    def prob(pos):
        prop = Prop(player="Josh Allen", team="BUF", opponent="LAC", position=pos, market=ANYTIME_TD,
                    logs=[], career_avg=0.0, vs_opponent_avg=None, lines=[])
        return T.td_probability(prop, game, opp, 0.2)
    qb, info = prob("QB")
    import math
    assert "Quarterback: scoring rate ×1.40" in " ".join(info["reasons"])
    # The same inputs without the scale: p = 1 - exp(-rate) → 1 - (1-p)^1.4.
    raw = 1 - math.exp(-math.log(1 / (1 - qb)) / 1.40)
    assert qb > raw and abs((1 - (1 - raw) ** 1.40) - qb) < 1e-9
    src = open(os.path.join(ROOT, "tdearlyfit.py"), encoding="utf-8").read()
    assert "MIN_PRIOR_WEEKS" in src and "TD_CARRY_GAMES" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
