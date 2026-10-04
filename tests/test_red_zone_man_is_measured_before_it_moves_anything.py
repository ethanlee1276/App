"""A touchdown scan's red-zone man-coverage argument is measured first.

Ethan, 2026-10-04, from the Bengals @ Jaguars touchdown scan: "Jacksonville
plays roughly 65% man coverage in the red zone … Higgins currently has the
highest receiving grade against man coverage." engine/tdmanfit asks it on
top of the touchdown model. Checks: the play-by-play's "T.Higgins" and the
log's "Tee Higgins Jr." are one man; his man edge comes from last season's
targets and needs both samples; only dropbacks inside the defence's own 20
count, and a week reads only the weeks before it, leaning on last season;
an effect planted on top of the model passes and no effect does not.

Run directly: `python3 tests/test_red_zone_man_is_measured_before_it_moves_anything.py`
"""
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import tdmanfit as F                                     # noqa: E402
from engine.tdfeatures import logit, sigmoid                         # noqa: E402


def test_one_name_whichever_feed_spells_it():
    for a, b in (("T.Higgins", "Tee Higgins"), ("Tee Higgins Jr.", "T.Higgins"),
                 ("Ja'Marr Chase", "J.Chase"), ("A.St. Brown", "Amon-Ra St. Brown")):
        assert F.name_key(a) == F.name_key(b), (a, b, F.name_key(a), F.name_key(b))


def _play(gid, pid, rec, yds, yl=50, d="JAX", pos="CIN"):
    return {"game_id": gid, "play_id": str(pid), "posteam": pos, "defteam": d, "yardline_100": str(yl),
            "receiver_player_name": rec, "yards_gained": str(yds), "complete_pass": "1"}


def _part(gid, pid, mz, pos="CIN"):
    return {"nflverse_game_id": gid, "play_id": str(pid), "possession_team": pos,
            "defense_man_zone_type": mz, "defense_coverage_type": ""}


def test_the_man_edge_needs_both_samples_and_points_the_right_way():
    part, plays = [], []
    pid = 0
    for i in range(12):                       # vs man: 12 targets, 12 yards each
        pid += 1
        part.append(_part("2025_05_CIN_JAX", pid, "MAN_COVERAGE"))
        plays.append(_play("2025_05_CIN_JAX", pid, "T.Higgins", 12))
    for i in range(25):                       # vs zone: 25 targets, 6 yards each
        pid += 1
        part.append(_part("2025_05_CIN_JAX", pid, "ZONE_COVERAGE"))
        plays.append(_play("2025_05_CIN_JAX", pid, "T.Higgins", 6))
    for i in range(5):                        # a man sample too thin to judge
        pid += 1
        part.append(_part("2025_05_CIN_JAX", pid, "MAN_COVERAGE"))
        plays.append(_play("2025_05_CIN_JAX", pid, "M.Gesicki", 20))
    edges = F.man_edges(part, plays)
    assert edges[F.name_key("Tee Higgins")] > 0.5, "twice the yards against man is a big man edge"
    assert F.name_key("Mike Gesicki") not in edges


def test_only_red_zone_dropbacks_count_and_a_week_reads_the_weeks_before():
    part, plays = [], []
    for wk, mz, yl in ((1, "MAN_COVERAGE", 12), (1, "ZONE_COVERAGE", 60), (2, "MAN_COVERAGE", 8),
                       (2, "ZONE_COVERAGE", 15), (3, "MAN_COVERAGE", 5)):
        gid = f"2026_{wk:02d}_CIN_JAX"
        part.append(_part(gid, wk * 10 + len(part), mz))
        plays.append(_play(gid, wk * 10 + len(plays), "X.Y", 0, yl=yl))
    looks = F.rz_looks(part, plays)
    assert len(looks) == 4, "the play at the 60 is not a red-zone look"
    assert all(t == "JAX" for _w, t, _m in looks)
    rates = F.rz_man_rates(looks)
    assert rates[2]["JAX"] == 1.0, "week 2 reads week 1 only"
    assert abs(rates[3]["JAX"] - 2 / 3) < 1e-9 and abs(rates[4]["JAX"] - 0.75) < 1e-9
    blended = F.rz_man_rates(looks, prior={"JAX": 0.0, "KC": 0.5})
    assert 0 < blended[2]["JAX"] < 0.1, "one play barely moves last season's rate"
    assert blended[2]["KC"] == 0.5, "a defence with no plays yet reads last season"


def test_samples_need_both_numbers_and_only_receivers():
    rows = [{"season": 2026, "week": "2026-W04", "player": "Tee Higgins", "position": "WR",
             "opponent": "JAX", "prob": 0.35, "scored": 1},
            {"season": 2026, "week": "04", "player": "Chase Brown", "position": "RB",
             "opponent": "JAX", "prob": 0.5, "scored": 0},
            {"season": 2026, "week": "04", "player": "Nobody Known", "position": "WR",
             "opponent": "JAX", "prob": 0.2, "scored": 0}]
    got = F.samples(rows, {2026: {"t higgins": 0.5}}, {2026: {4: {"league": 0.4, "JAX": 0.65}}})
    assert len(got) == 1 and abs(got[0][3] - 0.5 * 0.25) < 1e-9
    assert got[0][1] == (2026, 4, "JAX")


def _data(effect, seasons=(2022, 2023, 2024, 2025), n=5000, seed=3):
    rnd = random.Random(seed)
    out = []
    for s in seasons:
        b = effect(s)
        for i in range(n):
            p = rnd.uniform(0.05, 0.5)
            x = rnd.gauss(0, 0.1)
            y = 1 if rnd.random() < sigmoid(logit(p) + b * x) else 0
            out.append((s, (s, i // 6), logit(p), x, y))
    return out


def test_a_real_effect_passes_and_none_does_not():
    assert F.judge(_data(lambda s: 4.0))["passed"]
    for seed in (1, 2):
        assert not F.judge(_data(lambda s: 0.0, seed=seed))["passed"]
    assert not F.judge(_data(lambda s: 8.0 if s == 2023 else 0.0, seed=4))["passed"]


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
