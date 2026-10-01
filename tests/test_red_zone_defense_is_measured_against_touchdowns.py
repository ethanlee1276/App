"""Red-zone defence, measured against the touchdown model before it moves
anything (#168, "TD picks the other AI's way").

The other model's touchdown reports lean on goal-line work, game script and
how a defence guards its red zone. Goal-line work was measured on
2026-09-27 (already in the chance) and script is in the model
(script_td_multiplier, engine/scriptfit). Red-zone defence was shown on
every touchdown scenario (engine/redzone) and never scored against the
model's own number. engine/tdmatchfit now scores two readings of it on the
backtest's graded rows, with the same fit, held-out gain and bar as the
other defence readings:

  rz_allowed     how often a defence lets offences in (redzone.team_rates'
                 def_rel, the scenarios' own number);
  rz_td_allowed  touchdowns allowed per red-zone play allowed.

Nothing moves until a person reads the verdict
(test_a_bad_defense_is_measured_against_touchdowns pins touchdowns.py
never importing tdmatchfit).
"""
import os
import random
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import tdmatchfit as M                               # noqa: E402


def test_touchdowns_per_red_zone_play_is_a_ratio_of_sums_centred_and_blended():
    rows = []
    for w in range(1, 6):          # 2025: DET gives up a TD every 4 red-zone plays, BUF every 10
        rows += [{"season": 2025, "period": w, "opponent": "DET", "market": "rz_car", "value": 8},
                 {"season": 2025, "period": w, "opponent": "DET", "market": "rush_td", "value": 2},
                 {"season": 2025, "period": w, "opponent": "BUF", "market": "rz_tgt", "value": 10},
                 {"season": 2025, "period": w, "opponent": "BUF", "market": "rec_td", "value": 1}]
    tab = M.rz_td_rate_table(rows)
    det, buf = tab[(2025, 4, "DET")], tab[(2025, 4, "BUF")]
    assert abs((det - buf) - (0.25 - 0.10)) < 1e-9 and det > 0 > buf, (det, buf)
    assert (2025, 1, "DET") not in tab, "no games before week 1, no prior: nothing to read"
    # 2026 week 2: one game at league rate, leaning on last season until PRIOR_GAMES.
    rows += [{"season": 2026, "period": 1, "opponent": "DET", "market": "rz_car", "value": 10},
             {"season": 2026, "period": 1, "opponent": "DET", "market": "rush_td", "value": 1},
             {"season": 2026, "period": 1, "opponent": "BUF", "market": "rz_car", "value": 10},
             {"season": 2026, "period": 1, "opponent": "BUF", "market": "rush_td", "value": 1},
             {"season": 2026, "period": 2, "opponent": "DET", "market": "rz_car", "value": 1}]
    tab = M.rz_td_rate_table(rows)
    assert (2026, 1, "DET") in tab, "week 1 reads last season alone"
    assert 0 < tab[(2026, 2, "DET")] < 0.15, "one even game pulls Detroit a fifth of the way back"


def test_red_zone_plays_allowed_is_the_scenarios_own_number():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE player_game_logs (sport, season, period, player, team, market, value)")
    conn.execute("CREATE TABLE games (sport, season, period, home, away)")

    def game(wk, home, away, hp, ap):
        conn.execute("INSERT INTO games VALUES ('nfl', 2026, ?, ?, ?)", (f"{wk:03d}", home, away))
        for team, n in ((home, hp), (away, ap)):
            conn.execute("INSERT INTO player_game_logs VALUES ('nfl', 2026, ?, 'X', ?, 'rz_car', ?)",
                         (f"{wk:03d}", team, n))
    game(1, "BUF", "NYJ", 6, 6)
    game(1, "DET", "NO", 6, 12)
    game(2, "BUF", "MIA", 6, 6)
    game(2, "DET", "CHI", 6, 12)
    from engine import redzone
    tab = M.rz_allowed_table(conn, {(2026, 3)})
    rates = redzone.team_rates(conn, 2026, before_week=3)
    assert tab[(2026, 3, "DET")] == rates["DET"]["def_rel"] > 0, "Detroit lets teams in"
    assert tab[(2026, 3, "BUF")] == rates["BUF"]["def_rel"]


def _graded(effect: float, seed: int):
    """Graded rows where a scorer's real rate is prob·(1 + effect·x) for x
    the opponent's red-zone softness."""
    rng = random.Random(seed)
    rows, rz = [], {}
    teams = ["T%02d" % i for i in range(32)]
    for season in (2022, 2023, 2024, 2025):
        soft = {t: rng.uniform(-0.3, 0.3) for t in teams}
        for wk in range(4, 18):
            for t in teams:
                rz[(season, wk, t)] = soft[t]
            for _ in range(40):
                opp = rng.choice(teams)
                p = rng.uniform(0.10, 0.45)
                real = max(0.01, min(0.95, p * (1 + effect * soft[opp] / 0.2)))
                rows.append({"season": season, "week": wk, "position": rng.choice(["WR", "TE", "RB"]),
                             "opponent": opp, "prob": p, "scored": 1 if rng.random() < real else 0})
    return rows, rz


def test_a_red_zone_defence_that_matters_passes_pooled_and_noise_fails():
    rows, rz = _graded(effect=0.3, seed=5)                     # ~26% per SD
    res = M.study(M.points(rows, {}, {}, rz_allowed=rz, rz_rate=rz))
    for sig in ("rz_allowed", "rz_td_allowed"):
        r = res[(sig, "anytime_td", "ALL")]
        assert r["b"] > 0 and r["passes"] and r["decides"], (sig, r)
        assert not res[(sig, "anytime_td", "WR")]["passes"], "a group row never decides"
    # Seed 4 is one the shared bar passes on pure noise (t 2.0 for WR):
    # the pooled, clustered rule does not.
    rows, rz = _graded(effect=0.0, seed=4)
    res = M.study(M.points(rows, {}, {}, rz_allowed=rz, rz_rate=rz))
    assert not res[("rz_allowed", "anytime_td", "ALL")]["passes"]
    assert "(by group, reading only)" in M.report(res) and "clustered" in M.report(res)


def test_noise_rarely_passes_the_pre_registered_rule():
    passed = 0
    for seed in range(20, 40):
        rows, rz = _graded(effect=0.0, seed=seed)
        res = M.study(M.points(rows, {}, {}, rz_allowed=rz))
        passed += bool(res[("rz_allowed", "anytime_td", "ALL")]["passes"])
    assert passed <= 1, f"{passed} of 20 noise runs passed"


def test_the_clustered_error_counts_an_opponent_season_once():
    """Players facing the same defence share its luck. With a shared shock
    per opponent that has nothing to do with x, the per-row t overstates
    the evidence and the clustered t does not."""
    import random as _r
    from engine import scanfit as S
    rng = _r.Random(11)
    pts = []
    for c in range(40):                       # 40 opponent-seasons
        x = rng.uniform(-1, 1)
        shock = rng.uniform(-0.6, 0.6)        # its luck, unrelated to x
        for _ in range(60):
            e = rng.uniform(0.1, 0.4)
            y = 1 if rng.random() < max(0.0, min(1.0, e * (1 + shock))) else 0
            pts.append((e, x, y, 2025, c))
    f = S.fit(pts)
    naive = abs(f["b"]) / f["se"]
    clustered = M.clustered_t(pts, f["a"], f["b"])
    assert clustered < naive, (clustered, naive)
    one_each = [p[:4] + (i,) for i, p in enumerate(pts)]
    assert abs(M.clustered_t(one_each, f["a"], f["b"]) - naive) < 0.35 * max(naive, 1.0), \
        "with every row its own cluster it is the ordinary robust t"


def test_the_run_scores_all_four_readings():
    import inspect
    src = inspect.getsource(M.run)
    assert "rz_allowed_table(conn, keys)" in src and "rz_td_rate_table(rz_rows)" in src
    assert M.SIGNALS == ("defense_epa", "td_allowed", "rz_allowed", "rz_td_allowed")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
