"""Task #60's other half — the OUTCOME reconciliation of the sim joint.

`tests/test_simjoint.py` defends the structural gates under which the sim
is allowed to price a pair. This file defends the thing those gates cannot
give: the verdict machinery that grades the sim's joints against what
actually happened, and the switch that verdict controls.

Three disciplines pinned here:

  * THE COMPARISON IS PURE DEPENDENCE. All three competitors — chance
    (independence), the 27,613-game prior, the sim — are scored from the
    SAME two marginals. Slip different marginals into one arm and the
    measurement silently grades the projection model instead of the
    question #60 asked.
  * THE BAR CANNOT MOVE AFTER THE ANSWER. Verdict thresholds are code,
    the pair floor is a named constant, and the losing branch names the
    exact switch to flip — no interpretive step between a bad number and
    the rollback.
  * THE SWITCH KILLS PRICING AND NOTHING ELSE. `simjoint.ENABLED = False`
    must starve every ticket of simulated correlation while the journal
    keeps recording — evidence-gathering is how a benched model earns an
    appeal, so benching must not also blind it.

Run directly: `python3 tests/test_simrecon.py`
"""

import json
import math
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import simrecon                                              # noqa: E402
from engine.mlb import simjoint                              # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = open(os.path.join(ROOT, "simrecon.py"), encoding="utf-8").read()


# --- the bar -----------------------------------------------------------------
def test_the_bar_is_declared_before_any_result():
    """Same discipline as engine/nfl/prefit.py: the pass/fail criteria sit
    in the header, above every line that could compute a number."""
    assert SRC.index("THE BAR, DECLARED BEFORE ANY RESULT") \
        < SRC.index("def main")
    assert simrecon.MIN_PAIRS == 500
    # The losing branch names the exact rollback, not a vague instruction.
    assert "simjoint.ENABLED = False" in SRC


def test_the_comparison_is_pure_dependence():
    """One call site scores a pair, and it hands all three competitors the
    SAME p1 and p2 — pinned by the code forms, in one statement."""
    i = SRC.index("def _score_pair(")
    body = SRC[i:SRC.index("\ndef ", i + 1)]
    assert "tally.add(p1 * p2, joint_two(p1, p2, PRIOR_RHO), p_both" in body


def _tally(rows):
    t = simrecon.Tally()
    t.rows = rows
    return t


def _row(sim, prior, hit=False):
    return {"ind": prior, "prior": prior, "sim": sim,
            "b_ind": 0.0, "b_prior": 0.0, "b_sim": 0.0,
            "hit": hit, "adjacent": None}


def test_verdict_needs_the_floor_before_it_answers():
    t = _tally([_row(0.1, 0.5)] * (simrecon.MIN_PAIRS - 1))
    assert "KEEP COLLECTING" in simrecon.verdict(t)


def test_verdict_calls_a_clear_win_an_improvement():
    """Sim beats prior on most rows with realistic spread — comfortably
    past two standard errors at this sample size."""
    rows = [_row(0.30 + (i % 7) * 0.01, 0.33 + (i % 5) * 0.01)
            for i in range(600)]
    v = simrecon.verdict(_tally(rows))
    assert "IMPROVEMENT" in v


def test_verdict_calls_a_dead_heat_a_kept_seat_not_a_win():
    """Zero difference with zero variance is the degenerate case that once
    read as an improvement (d <= -2*se holds at 0 <= 0). A tie is a tie."""
    v = simrecon.verdict(_tally([_row(0.31, 0.31)] * 600))
    assert "KEEPS ITS SEAT" in v


def test_verdict_orders_the_rollback_when_the_prior_wins():
    rows = [_row(0.36 + (i % 7) * 0.01, 0.30 + (i % 5) * 0.01)
            for i in range(600)]
    v = simrecon.verdict(_tally(rows))
    assert "WORSE THAN THE PRIOR" in v and "ENABLED = False" in v


# --- the history arm ---------------------------------------------------------
def _seed_db(path, dates=14, teams=("AAA", "BBB")):
    """A tiny but real-shaped MLB log store: two lineups, shared per-game
    environment so teammate outcomes genuinely co-move."""
    import random
    random.seed(5)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE player_game_logs (sport TEXT, season INT, period TEXT,"
        " game_id TEXT, player TEXT, team TEXT, opponent TEXT, position TEXT,"
        " home INT, market TEXT, value REAL)")
    rows = []
    for team, opp in ((teams[0], teams[1]), (teams[1], teams[0])):
        for d in range(1, dates + 1):
            date = f"2026-06-{d:02d}"
            gid = f"{teams[1]}@{teams[0]}-{d}"
            env = random.gauss(1.0, 0.3)
            for i in range(1, 10):
                name = f"{team} Bat {i}"
                pa = max(3, round(random.gauss(4.6 - i * 0.09, 0.4)))
                p = min(.5, max(.05, 0.26 * env))
                hits = sum(1 for _ in range(pa) if random.random() < p)
                hrs = sum(1 for _ in range(hits) if random.random() < 0.1)
                tb = hits + 3 * hrs + sum(1 for _ in range(hits - hrs)
                                          if random.random() < 0.25)
                for mk, v in (("hits", hits), ("total_bases", tb),
                              ("home_runs", hrs), ("pa", pa)):
                    rows.append(("mlb", 2026, date, gid, name, team, opp,
                                 "", 1, mk, float(v)))
    conn.executemany(
        "INSERT INTO player_game_logs VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    return conn


def test_the_history_arm_replays_scores_and_gates():
    """End to end on a synthetic store: lineups replayed from prior games
    only, the marginal gate consulted, pairs scored by all three arms."""
    with tempfile.TemporaryDirectory() as td:
        conn = _seed_db(os.path.join(td, "h.db"))
        t, notes = simrecon.run_history(conn, days=2, trials=1500,
                                        fit_trials=1000,
                                        progress=lambda *a: None)
    assert notes["team_games"] == 4
    assert notes["lineups_scored"] + notes["gate_failed"] \
        + notes["too_few_hitters"] == 4
    if t.n:                       # gate can bench a noisy fit at low trials
        r = t.rows[0]
        for k in ("ind", "prior", "sim"):
            assert 0.0 < r[k] < -math.log(simrecon.EPS) + 1
        assert all(r["adjacent"] in (True, False) for r in t.rows)


def test_replay_projections_see_only_prior_games():
    """The walk-forward's one law. The replay slices strictly earlier
    periods before projecting — pinned at the code site."""
    i = SRC.index("def run_history(")
    body = SRC[i:SRC.index("\ndef _score_pair", i)]
    assert "if g[0][0] < period" in body, "the as-of cut is gone"


# --- the forward arm ---------------------------------------------------------
def test_forward_grades_dedupes_and_waits():
    """Three journal lines: a pair recorded twice (the later, pre-first-
    pitch write must win), and one leg the DB has never heard of (stays
    ungraded rather than guessed)."""
    with tempfile.TemporaryDirectory() as td:
        conn = _seed_db(os.path.join(td, "h.db"), dates=3)
        jp = os.path.join(td, "j.jsonl")
        pair = {"date": "2026-06-02", "team": "AAA", "game_number": 1,
                "a": ["AAA Bat 1", "hits", 0.5],
                "b": ["AAA Bat 2", "hits", 0.5]}
        rows = [dict(pair, p1=.5, p2=.5, sim_joint=.30),
                dict(pair, p1=.6, p2=.55, sim_joint=.36),
                {"date": "2026-06-02", "team": "AAA", "game_number": 1,
                 "a": ["A Ghost", "hits", 0.5],
                 "b": ["AAA Bat 2", "hits", 0.5],
                 "p1": .5, "p2": .5, "sim_joint": .3}]
        with open(jp, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        t, notes = simrecon.run_forward(conn, jp)
    assert notes["recorded"] == 2, "the duplicate must collapse"
    assert notes["graded"] == 1 and notes["ungraded"] == 1
    assert t.n == 1


def test_a_doubleheader_leg_grades_against_its_own_half():
    """Two log rows share one date; the -G2 suffix picks the second game.
    Values are planted so the two halves give OPPOSITE answers."""
    with tempfile.TemporaryDirectory() as td:
        conn = sqlite3.connect(os.path.join(td, "h.db"))
        conn.execute(
            "CREATE TABLE player_game_logs (sport TEXT, season INT,"
            " period TEXT, game_id TEXT, player TEXT, team TEXT,"
            " opponent TEXT, position TEXT, home INT, market TEXT,"
            " value REAL)")
        for gid, v in (("B@A", 0.0), ("B@A-G2", 2.0)):
            for player in ("P One", "P Two"):
                conn.execute(
                    "INSERT INTO player_game_logs VALUES "
                    "('mlb', 2026, '2026-06-01', ?, ?, 'A', 'B', '', 1,"
                    " 'hits', ?)", (gid, player, v))
        row = {"date": "2026-06-01", "team": "A", "game_number": 2,
               "a": ["P One", "hits", 0.5], "b": ["P Two", "hits", 0.5],
               "p1": .5, "p2": .5, "sim_joint": .3}
        assert simrecon._forward_outcome(conn, row) is True
        row["game_number"] = 1
        assert simrecon._forward_outcome(conn, row) is False


# --- the journal and the switch ----------------------------------------------
def test_build_journals_every_solved_pair():
    """The forward arm's food. Reuses test_simjoint's fixture slate; the
    journal must land one line per solved pair, carrying the fields the
    grader joins on."""
    from tests.test_simjoint import _slate, _legs
    old = simjoint.LOG_PATH
    with tempfile.TemporaryDirectory() as td:
        simjoint.LOG_PATH = os.path.join(td, "j.jsonl")
        try:
            j = simjoint.build(_slate(), _legs(["Hitter 1", "Hitter 2"]),
                               trials=6000)
            assert j["rho"], "fixture must solve at least one pair"
            lines = [json.loads(l) for l in
                     open(simjoint.LOG_PATH, encoding="utf-8")]
        finally:
            simjoint.LOG_PATH = old
    assert len(lines) == len(j["rho"])
    for r in lines:
        for k in ("date", "team", "game_number", "a", "b",
                  "p1", "p2", "sim_joint"):
            assert k in r, k
    assert lines[0]["date"] == "2026-08-05"


def test_an_unwritable_journal_never_touches_the_board():
    from tests.test_simjoint import _slate, _legs
    old = simjoint.LOG_PATH
    simjoint.LOG_PATH = os.path.join(os.sep, "nonexistent-9x", "j.jsonl")
    try:
        j = simjoint.build(_slate(), _legs(["Hitter 1", "Hitter 2"]),
                           trials=6000)
    finally:
        simjoint.LOG_PATH = old
    assert j["rho"], "a dead journal must not cost the pricing its joint"


def test_the_switch_kills_pricing_and_nothing_else():
    """ENABLED = False starves rho_for; build() must not read the flag at
    all, so the journal keeps gathering the evidence for an appeal."""
    a = {"player": "X", "market": "hits", "line": 0.5}
    b = {"player": "Y", "market": "hits", "line": 0.5}
    key = simjoint.pair_key(("X", "hits", 0.5), ("Y", "hits", 0.5))
    joints = {"rho": {key: 0.2}}
    assert simjoint.rho_for(joints, a, b, 0.186) is not None
    simjoint.ENABLED = False
    try:
        assert simjoint.rho_for(joints, a, b, 0.186) is None
    finally:
        simjoint.ENABLED = True
    src = open(os.path.join(ROOT, "engine", "mlb", "simjoint.py"),
               encoding="utf-8").read()
    i = src.index("def build(")
    body = src[i:src.index("\ndef _journal", i)]
    assert "ENABLED" not in body, \
        "benching the sim must not also blind the journal"


def test_the_journal_stays_out_of_git():
    gi = open(os.path.join(ROOT, ".gitignore"), encoding="utf-8").read()
    assert "data/simrecon_log.jsonl" in gi


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
