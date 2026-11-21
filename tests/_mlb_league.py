"""A made-up MLB league in the box's own play tables, for the EXP-007 lab tests.

tests/test_mlb_strikeouts_lab.py and tests/test_mlb_strikeout_lines_lab.py
both score EXP-007's models on it: `_league` writes plate appearances
(mlb_pa) and the games table (mlb_games) to a fresh history.db through the
site's own schema and hands back a read-only connection, the way the box
script opens the real one.
"""
import datetime as dt
import math
import os
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db                                              # noqa: E402
from research import exp7_mlb_strikeouts_box as E7                # noqa: E402

COLS = "(game_pk, at_bat, season, date, pitcher_id, pitcher, team, event_type)"


def _write(pa, games):
    path = os.path.join(tempfile.mkdtemp(), "history.db")
    conn = db.connect(path)
    conn.executemany(f"INSERT INTO mlb_pa {COLS} VALUES (?,?,?,?,?,?,?,?)", pa)
    conn.executemany("INSERT INTO mlb_games (game_pk, season, date, game_type) VALUES (?,?,?,?)", games)
    conn.commit()
    conn.close()
    return E7.open_db(path)


def _league(seasons=(2025, 2026), pitchers=30, starts_each=28, seed=3, same_rate=False, missing=0, direct=False):
    """A made-up league where strikeouts ARE batters faced times a rate:
    each pitcher-season a true rate (one shared rate with ``same_rate``)
    and a usual length; a start's batters faced around it, each batter
    struck out at his rate; a reliever finishes every side. With
    ``direct`` the strikeouts come straight from the pitcher's own mean
    instead, spread wider than batters faced explain (a gamma-Poisson of
    size 2) and placed among the batters at random. ``missing``
    regular-season finals are listed with no plays (a backfill not done)."""
    rng = random.Random(seed)
    pa, games, pk = [], [], 1000

    def poisson(lam):
        k, term = 0, math.exp(-lam)
        u, acc = rng.random(), term
        while u > acc:
            k += 1
            term *= lam / k
            acc += term
        return k
    for season in seasons:
        rates = [0.235 if same_rate else rng.uniform(0.15, 0.32) for _ in range(pitchers)]
        usual = [rng.uniform(18, 27) for _ in range(pitchers)]
        means = [rng.uniform(3.0, 8.0) for _ in range(pitchers)]
        for g in range(starts_each):
            date = (dt.date(season, 3, 28) + dt.timedelta(days=6 * g)).isoformat()
            for i in range(0, pitchers, 2):
                pk += 1
                ab = 0
                for pit, batting in ((i, f"T{i + 1}"), (i + 1, f"T{i}")):
                    bf = max(3, round(rng.gauss(usual[pit], 3.5)))
                    if direct:
                        k = poisson(rng.gammavariate(2.0, means[pit] / 2.0))
                        bf = max(bf, k)
                        ks = set(rng.sample(range(bf), k))
                    for j in range(bf):
                        hit = (j in ks) if direct else rng.random() < rates[pit]
                        pa.append((pk, ab, season, date, 100 + pit, f"P{pit}", batting,
                                   "strikeout" if hit else "field_out"))
                        ab += 1
                    for _ in range(4):
                        out = "strikeout" if rng.random() < 0.25 else "single"
                        pa.append((pk, ab, season, date, 900 + pit, f"R{pit}", batting, out))
                        ab += 1
                games.append((pk, season, date, "R"))
    for j in range(missing):
        games.append((90000 + j, seasons[-1], f"{seasons[-1]}-09-20", "R"))
    return _write(pa, games)
