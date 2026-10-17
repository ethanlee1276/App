"""Honest ranges — conformal intervals around every pick's projection, coverage tested held out.

Ethan, 2026-10-16: "add everything now. 1-13" — idea 11: one projection
and one chance never say how wide the outcomes really are.

What these hold: a score is the miss over the square root of the number;
the range's quantile is the ⌈(n+1)p⌉-th score (the finite-sample
correction); on misses drawn from a known spread the ranges cover their
share out of sample, and the range's chance for a side matches the truth;
the journal counts a pick journaled twice once and only graded picks with a
projection; the held-out split is by date, oldest two thirds calibrating;
a range that is too narrow fails its coverage; and the pick page shows the
ranges, the line and both chances, labelled. No test touches the network.

Run directly: `python3 tests/test_honest_ranges_around_every_pick.py`
"""
import json
import math
import os
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import conformal as C                                # noqa: E402
from engine import ideas as ID                                   # noqa: E402

LAB = ROOT / "web" / "js" / "lab.js"


def test_the_score_and_the_finite_sample_quantile():
    assert C.score(63.0, 71.0) == 1.0, "8 yards over a projection of 63: one unit of sqrt(64)"
    xs = list(range(1, 20))
    assert C._q(xs, 0.5) == 10 and C._q(xs, 0.9) == 18 and C._q(xs, 0.99) == 19
    assert C.fit(list(range(50))) is None, "fewer than 100 graded picks calibrate nothing"


def _picks(n, seed=1, spread=1.0, start=0):
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        proj = rnd.uniform(20, 90)
        actual = max(0.0, proj + rnd.gauss(0, spread) * C.scale(proj))
        out.append(("nfl", "rec_yds", f"2025-W{(start + i) // 60 + 1:02d}", "over", round(proj) + 0.5, proj, 0.55, actual))
    return out


def test_the_ranges_cover_their_share_and_the_side_chance_is_right():
    rows = _picks(3000)
    cal = C.fit([C.score(r[5], r[7]) for r in rows[:2000]])
    for lv in C.LEVELS:
        inside = sum(C.interval(cal, r[5], lv)[0] <= r[7] <= C.interval(cal, r[5], lv)[1] for r in rows[2000:])
        assert abs(inside / 1000 - lv) < 0.04, (lv, inside)
    p = C.chance_over(cal, 50.0, 50.0)
    assert abs(p - 0.5) < 0.05, "a line at the projection is about even"
    assert C.chance_over(cal, 50.0, 40.0) > 0.8 > 0.2 > C.chance_over(cal, 50.0, 60.0)
    assert abs(C.side_chance(cal, 50.0, 45.5, "Under") - (1 - C.chance_over(cal, 50.0, 45.5))) < 1e-12


def test_the_journal_counts_a_pick_once_and_only_graded_ones():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE bets (id INTEGER PRIMARY KEY, sport, market, date, player, side, line, projection, "
                 "hit_prob, actual, status, category)")
    rows = [("nfl", "rec_yds", "2025-W03", "Puka Nacua", "over", 70.5, 78.0, 0.6, 90.0, "won", "likely"),
            ("nfl", "rec_yds", "2025-W03", "Puka Nacua", "over", 70.5, 78.0, 0.6, 90.0, "won", "board"),
            ("nfl", "rec_yds", "2025-W02", "Puka Nacua", "over", 70.5, 76.0, 0.6, 50.0, "lost", "likely"),
            ("nfl", "rec_yds", "2025-W04", "Puka Nacua", "over", 70.5, 76.0, 0.6, None, "open", "likely"),
            ("nfl", "rec_yds", "2025-W04", "Davante Adams", "over", 60.5, None, 0.6, 70.0, "won", "likely")]
    conn.executemany("INSERT INTO bets (sport, market, date, player, side, line, projection, hit_prob, actual, status, "
                     "category) VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    got = C.journal_rows(conn)
    assert [(r[2], r[7]) for r in got] == [("2025-W02", 50.0), ("2025-W03", 90.0)]


def test_the_held_out_split_and_a_range_too_narrow_fails():
    rows = _picks(900)
    v = C.held_out(rows)["nfl|rec_yds"]
    assert v["n"] == 300 and v["holds"] and v["brier_n"] > 250
    drift = rows[:600] + [r[:7] + (r[5] + (r[7] - r[5]) * 2.5,) for r in rows[600:]]
    bad = C.held_out(drift)["nfl|rec_yds"]
    assert not bad["holds"] and bad["coverage"]["0.8"] < 0.7, "misses that widen after calibration break coverage"
    few = C.held_out(rows[:300])["nfl|rec_yds"]
    assert not few["holds"], "100 newest picks is not 150"


def test_the_pick_page_shows_the_ranges_and_both_chances():
    d = tempfile.mkdtemp()
    old = os.environ.get("QB_MODELS_DIR")
    os.environ["QB_MODELS_DIR"] = d
    try:
        assert C.ideas_section([], [], {"recommendations": []}, "nfl") == {"rows": {}}
        C.save(C.measure(_picks(900)))
        board = {"recommendations": [{"player": "Puka Nacua", "market": "rec_yds", "side": "over", "line": 70.5,
                                      "projection": 78.2, "hit_prob": 0.63, "proj_low": 55, "proj_high": 101},
                                     {"player": "Bo Nix", "market": "pass_yds", "line": 230.5, "projection": 240}]}
        sec = C.ideas_section([], [], board, "nfl")
        p = C.pick_view(sec, "Puka Nacua", "rec_yds")
        r50, r80 = p["ranges"]["0.5"], p["ranges"]["0.8"]
        assert r80[0] < r50[0] < 78.2 < r50[1] < r80[1]
        assert 0.5 < p["range_chance"] < 0.8 and p["model_chance"] == 0.63 and p["verdict"]["holds"]
        assert C.pick_view(sec, "Bo Nix", "pass_yds") is None, "no calibration for that market, no range"
    finally:
        if old is None:
            os.environ.pop("QB_MODELS_DIR", None)
        else:
            os.environ["QB_MODELS_DIR"] = old
        shutil.rmtree(d)
    assert ID.SECTIONS["range"] == "conformal"
    node = shutil.which("node")
    if not node:
        print("      (skipped the drawing: no Node)")
        return
    script = ("const vm = require('vm'); const fs = require('fs'); const ctx = { window: {} }; vm.createContext(ctx);"
              f"vm.runInContext(fs.readFileSync({json.dumps(str(LAB))}, 'utf8'), ctx); const L = ctx.window.QBLab;"
              f"process.stdout.write(JSON.stringify({{h: L.pickHTML({json.dumps({'sections': {'range': p}})})}}));")
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1200:]
    h = json.loads(out.stdout)["h"]
    assert "How wide it really is" in h and "lb-range" in h and "70.5" in h
    assert "The model’s own range" in h and "Measured · holds" in h and math.isfinite(len(h))


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
