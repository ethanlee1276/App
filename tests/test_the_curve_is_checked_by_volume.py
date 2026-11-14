"""The receiving curve is checked by receiver volume, each season held out.

Ethan, 2026-10-22, after Luther Burden III cleared lines the board had
rated under the books: "The app and you have to be better." curvecheck.py
asks whether engine/yardagefit's fitted curve is too cautious on a steady,
high-volume receiver. Its answer (no change) is in its docstring; these
hold the parts the answer stands on.

What these hold: a line is a book's half-number in k × projection's own
unit; the tiers cover every projection once; the lean taken out is
the least-squares line; every held-out season is fitted without itself,
and each row is priced once per line; and the command reads a history and
prints the table.

Run directly: `python3 tests/test_the_curve_is_checked_by_volume.py`
"""
import io
import math
import os
import random
import sqlite3
import sys
import tempfile
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

import curvecheck as C                                             # noqa: E402
from engine import db                                              # noqa: E402
from engine import yardagefit as Y                                 # noqa: E402


def _history(path, seasons=(2023, 2024, 2025), players=60, weeks=17, seed=7):
    rnd = random.Random(seed)
    conn = db.connect(path)
    rows = []
    for season in seasons:
        for i in range(players):
            median = rnd.uniform(10, 90)
            for wk in range(1, weeks + 1):
                v = 0.0 if rnd.random() < 0.08 else round(median * math.exp(rnd.gauss(0, 0.6)))
                for market, value in (("rec_yds", v), ("receptions", round(v / 12))):
                    rows.append({"sport": "nfl", "season": season, "period": f"{wk:03d}",
                                 "game_id": f"T{i % 32}-{wk:03d}", "player": f"P{i}",
                                 "team": f"T{i % 32}", "opponent": "X", "position": "WR",
                                 "home": 1, "market": market, "value": value})
    db.upsert_player_logs(conn, rows)
    conn.commit()
    return conn


def test_a_line_is_a_books_half_number_in_its_own_unit():
    assert C.half(40.1) == 40.5 and C.half(40.9) == 40.5 and C.half(3.52) == 3.5
    assert C.half(0.75 * 54.4) == 40.5 and C.half(0.75 * 4.7) == 3.5


def test_the_tiers_cover_every_projection_once():
    for market, edges in C.TIERS.items():
        for mu in (1.0, 1.5, 14.99, 15.0, 59.9, 80.0, 250.0, 6.9, 7.0, 98.0):
            if mu < edges[-1]:
                assert C.tier_of(mu, edges) is not None, (market, mu)
        assert C.tier_of(0.5, edges) is None
    assert C.tier_of(54.4, C.TIERS["rec_yds"]) == "45-60"
    assert C.tier_of(4.7, C.TIERS["receptions"]) == "4-5.5"
    assert C.tier_of(120, C.TIERS["rec_yds"]) == "80-+"


def test_the_lean_taken_out_is_the_least_squares_line():
    rows = [{"mu": float(m), "actual": 5.0 + 0.8 * m} for m in range(2, 40)]
    a, b = C.shrink(rows)
    assert abs(a - 5.0) < 1e-9 and abs(b - 0.8) < 1e-9
    moved = C._with_mu([{"mu": 0.0, "actual": 1.0}], -5.0, 1.0)
    assert moved[0]["mu"] > Y.MIN_PROJECTION, "never a projection the curve refuses"


def test_each_season_is_held_out_and_each_row_priced_once_per_line():
    with tempfile.TemporaryDirectory() as tmp:
        conn = _history(os.path.join(tmp, "h.db"))
        data = Y.rows(conn, "rec_yds")
        conn.close()
    said = []
    got = C.cells(data, "rec_yds", say=said.append)
    assert [s.split(",")[1].split()[0] for s in said] == ["2023", "2024", "2025"], said
    tiered = [d for d in data if C.tier_of(d["mu"], C.TIERS["rec_yds"])]
    for k in C.KS:
        priced = [d for d in tiered if C.half(k * d["mu"]) > 0]
        assert sum(v[0] for (t, kk), v in got.items() if kk == k) == len(priced), k
    for n, claimed, landed in got.values():
        assert 0 <= claimed <= n and 0 <= landed <= n


def test_the_command_reads_a_history_and_prints_the_table():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "h.db")
        _history(path).close()
        out = io.StringIO()
        with redirect_stdout(out):
            assert C.main(["--db", path, "rec_yds", "--plain"]) == 0
    text = out.getvalue()
    assert "=== rec_yds: the plain normal" in text and "45-60" in text
    assert "each cell: claimed / landed, then landed minus claimed in points" in text


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
