"""Does a bad defence raise a receiver's touchdown chance beyond the model's
number? engine/tdmatchfit measures it before anything moves.

Ethan, 2026-09-25: "The Detroit Lions secondary ... is completely ass right
now ... I bet on Chris Olave to get a touchdown ... Dalton Kincaid to get a
touchdown ... and they all did. So you need to think like that too."

The model gives backs a measured defence term and receivers none
(engine/defensefit). This module scores the opponent's defence, two ways,
on the backtest's own graded rows with scanfit's fit, held-out gain and
bar. Here: the tables centre on the league and lean on last season until
PRIOR_GAMES, a defence that truly matters PASSES, and noise fails.
"""
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import tdmatchfit as M                               # noqa: E402


def test_the_defence_table_centres_on_the_league_and_leans_on_last_season():
    rows = []
    for t, v in (("DET", 0.20), ("BUF", -0.10), ("KC", -0.10)):          # 2025: Detroit soft
        rows += [{"season": 2025, "period": w, "team": t, "def_epa": v} for w in range(1, 18)]
    for t, v in (("DET", -0.10), ("BUF", -0.10), ("KC", -0.10)):         # 2026: Detroit average so far
        rows += [{"season": 2026, "period": w, "team": t, "def_epa": v} for w in (1, 2)]
    tab = M.defense_epa_table(rows)
    assert abs(tab[(2025, 10, "DET")] - 0.20) < 1e-9 and abs(tab[(2025, 10, "BUF")] + 0.10) < 1e-9, \
        "mid-2025: centred on the league, Detroit +0.20 above it"
    # 2026 week 2: one game says average, last season says soft; 1/(1+4) of the way there.
    det = tab[(2026, 2, "DET")]
    assert 0 < det < 0.20, det
    assert (2026, 1, "DET") in tab, "week 1 reads last season alone"


def test_touchdowns_allowed_are_by_position_group_and_market():
    rows = [{"season": 2025, "period": w, "opponent": "DET", "position": "WR", "market": "rec_td", "value": 2}
            for w in range(1, 6)]
    rows += [{"season": 2025, "period": w, "opponent": "BUF", "position": "WR", "market": "rec_td", "value": 0}
             for w in range(1, 6)]
    rows += [{"season": 2025, "period": w, "opponent": "DET", "position": "RB", "market": "rush_td", "value": 1}
             for w in range(1, 6)]
    tab = M.td_allowed_table(rows)
    assert tab[(2025, 4, "DET", "WR")] > 0 > tab[(2025, 4, "BUF", "WR")], "Detroit allows more to receivers"
    assert (2025, 4, "DET", "RB") in tab and (2025, 4, "DET", "TE") not in tab


def _graded(effect: float, seed: int = 1):
    """Graded rows where a receiver's real scoring rate is prob·(1 + effect·x)."""
    rng = random.Random(seed)
    rows, epa = [], {}
    teams = ["T%02d" % i for i in range(32)]
    for season in (2022, 2023, 2024, 2025):
        strength = {t: rng.uniform(-0.15, 0.15) for t in teams}
        for wk in range(4, 18):
            for t in teams:
                epa[(season, wk, t)] = strength[t]
            for _ in range(40):
                opp = rng.choice(teams)
                p = rng.uniform(0.10, 0.45)
                real = max(0.01, min(0.95, p * (1 + effect * strength[opp] / 0.1)))
                rows.append({"season": season, "week": wk, "position": rng.choice(["WR", "TE"]),
                             "opponent": opp, "prob": p, "scored": 1 if rng.random() < real else 0})
    return rows, epa


def test_a_defence_that_matters_passes_and_noise_fails():
    rows, epa = _graded(effect=0.6)
    res = M.study(M.points(rows, epa, {}))
    wr = res[("defense_epa", "anytime_td", "WR")]
    assert wr["b"] > 0 and wr["passes"], wr
    rows, epa = _graded(effect=0.0, seed=2)
    res = M.study(M.points(rows, epa, {}))
    assert not res[("defense_epa", "anytime_td", "WR")]["passes"]
    assert "PASSES" in M.report(M.study(M.points(*_graded(0.6), {})))


def test_the_command_line_exists_and_moves_nothing():
    src = open(os.path.join(ROOT, "engine", "tdmatchfit.py"), encoding="utf-8").read()
    assert "python3 -m engine.tdmatchfit" in src and 'if __name__ == "__main__":' in src
    td = open(os.path.join(ROOT, "engine", "touchdowns.py"), encoding="utf-8").read()
    assert "tdmatchfit" not in td, "the verdict is read by a person before a number moves"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
