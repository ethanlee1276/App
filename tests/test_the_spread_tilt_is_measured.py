"""The spread moves no NFL player's volume, measured.

Ethan's Bills @ Rams reports, 2026-10-12: "the market's extra attempts come
from Buffalo being an underdog". The board had one script term, +0.4% a
point on an underdog's passing yards, catches and receiving yards
(engine/matchup.SCRIPT_COEF_PASS), measured once, on catches, before the
board had its defence step or a player's last season. Measured again on the
base the board has now (`python3 qbscriptfit.py`): dropping it cut the
error in every season 2022-2025 for all three markets, and the five older
seasons did not disagree; a quarterback's own attempts and completions
against the spread failed their bar. So nothing is tilted, and the card says
so. Offline, on fixtures.

Run directly: `python3 tests/test_the_spread_tilt_is_measured.py`
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import qbscriptfit as Q                                           # noqa: E402
from engine import matchup as M                                   # noqa: E402
from engine.models import DefenseProfile, Game, GameLog, Prop, Weather  # noqa: E402


def _prop(market, position, team="BUF", opp="LA"):
    return Prop(player="X", team=team, opponent=opp, position=position, market=market,
                logs=[GameLog(week=1, opponent=opp, value=30.0)], career_avg=30.0,
                vs_opponent_avg=None, lines=[])


def test_the_tilt_is_retired_and_the_note_says_why():
    assert M.SCRIPT_MARKETS == frozenset(), "the spread tilt reaches no market"
    src = open(os.path.join(ROOT, "engine", "matchup.py"), encoding="utf-8").read()
    note = src[src.index("MEASURED AGAIN 2026-10-12 AND RETIRED"):src.index("SCRIPT_COEF_PASS = 0.004")]
    assert "qbscriptfit.py" in note and "every season 2022-2025" in note
    assert "QB pass_yds   +1.57  +0.59  +1.34  +1.34" in note
    flat = " ".join(line.lstrip("#: ").strip() for line in note.splitlines()).lower()
    assert "an underdog quarterback does not throw for more" in flat


def test_a_big_underdog_gets_no_tilt_and_no_script_reason():
    """The same prop, ten points either side of the number, prices the same."""
    d = DefenseProfile(team="LA")
    for market, pos in (("pass_yds", "QB"), ("pass_att", "QB"), ("receptions", "WR"), ("rec_yds", "TE")):
        dog = M.evaluate_matchup(_prop(market, pos), d, Game(home="LA", away="BUF", weather=Weather(), spread=-10.0))
        fav = M.evaluate_matchup(_prop(market, pos), d, Game(home="LA", away="BUF", weather=Weather(), spread=10.0))
        assert dog.multiplier == fav.multiplier, market
        assert not [r for r in dog.reasons + fav.reasons if r.startswith("Game script:")], market


def test_the_spread_is_read_from_his_side():
    """nflverse's spread_line is positive when the HOME side is favoured; the
    board's sign is negative when HIS side is."""
    games = {"g": {"home_team": "LA", "away_team": "BUF", "spread_line": "3.5"}}
    assert Q.team_spread({"game_id": "g", "team": "BUF"}, games) == 3.5
    assert Q.team_spread({"game_id": "g", "team": "LA"}, games) == -3.5
    assert Q.team_spread({"game_id": "g", "team": "LA"}, {"g": {"home_team": "LA", "spread_line": ""}}) is None
    assert Q.team_spread({"game_id": "nope", "team": "LA"}, games) is None


def _season(slope, seed):
    """Points whose outcome follows ``slope`` exactly, spread -10..10."""
    out = []
    for i in range(40):
        ts = -10.0 + (i * 7 + seed) % 21
        base = 30.0 + (i % 5)
        out.append({"m": "pass_att", "s": seed, "base": base, "ts": ts, "y": base * (1.0 + slope * ts)})
    return out


def test_the_harness_finds_a_real_slope_and_refuses_a_flat_one():
    real = {s: _season(0.01, s) for s in (1, 2, 3, 4)}
    held = Q.held_out(real, "pass_att")
    assert len(held) == 4 and all(abs(b - 0.01) < 1e-9 and c > 0 for _s, b, _n, c in held)
    flat = {s: _season(0.0, s) for s in (1, 2, 3, 4)}
    assert all(b == 0.0 and c == 0.0 for _s, b, _n, c in Q.held_out(flat, "pass_att")), \
        "no slope, no improvement: the bar (every season > 0) is not met"
    # Dropping a tilt the outcomes do not follow cuts the error; dropping
    # one they do follow adds it.
    for p in (x for s in flat.values() for x in s):
        p["m"] = "receptions"
    assert all(c > 0 for _s, _n, c in Q.dropping_cuts(flat, "receptions"))
    tilted = {s: _season(2 * M.SCRIPT_COEF_PASS, s) for s in (1, 2)}
    for p in (x for s in tilted.values() for x in s):
        p["m"] = "receptions"
    assert all(c < 0 for _s, _n, c in Q.dropping_cuts(tilted, "receptions"))


def test_the_runbook_says_how_to_measure_it_again():
    run = open(os.path.join(ROOT, "docs", "WHEN_YOU_ARE_HOME.md"), encoding="utf-8").read()
    assert "python3 qbscriptfit.py" in run


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
