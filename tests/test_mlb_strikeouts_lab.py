"""EXP-007: a starter's strikeouts, batters faced first — the arithmetic and the guards.

research/exp7_mlb_strikeouts_box.py asks whether strikeouts read as batters
faced times a strikeout rate (B), or A's mean with B's shape (H), beat the
direct model (A) on the box's own plate appearances. What these hold: a
start is the pitcher his opponents saw first, regular season only, with a
strikeout double play counted; a start is scored only from the starts
before it; B is a distribution with the mean it claims, and H is B
stretched; the fit finds the shrink a made-up league was built with, and
lands on its grid's edge where there is nothing to shrink; the test finds
batters faced where a league was built on them and not where it was not;
the splits
follow the seasons the table holds; and the holdout is read only with the
flag, only on a complete season, and never off a grid's edge.

Run directly: `python3 tests/test_mlb_strikeouts_lab.py`
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
from engine.form import MLB_WINDOW_WEIGHTS, compute_form           # noqa: E402
from engine.models import GameLog                                  # noqa: E402
from engine.nflusage import ewma_opps                              # noqa: E402
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


def test_a_start_is_the_pitcher_his_opponents_saw_first():
    d = "2026-05-01"
    pa = [(1, 0, 2026, d, 1, "Home Ace", "AWY", "strikeout"), (1, 1, 2026, d, 1, "Home Ace", "AWY", "strikeout_double_play"),
          (1, 2, 2026, d, 1, "Home Ace", "AWY", "field_out"), (1, 3, 2026, d, 1, "Home Ace", "AWY", "walk"),
          (1, 4, 2026, d, 1, "Home Ace", "AWY", "single"),
          (1, 5, 2026, d, 2, "Road Ace", "HOM", "strikeout"), (1, 6, 2026, d, 2, "Road Ace", "HOM", "field_out"),
          (1, 7, 2026, d, 2, "Road Ace", "HOM", "field_out"), (1, 8, 2026, d, 2, "Road Ace", "HOM", "field_out"),
          (1, 10, 2026, d, 3, "Home Pen", "AWY", "strikeout"), (1, 11, 2026, d, 3, "Home Pen", "AWY", "strikeout"),
          (1, 12, 2026, d, 4, "Road Pen", "HOM", "strikeout"),
          (2, 0, 2026, "2026-10-08", 1, "Home Ace", "AWY", "strikeout"),
          (2, 1, 2026, "2026-10-08", 2, "Road Ace", "HOM", "strikeout"),
          (3, 0, 2026, "2026-05-06", 2, "Road Ace", "HOM", "strikeout"),
          (3, 1, 2026, "2026-05-06", 5, "Other", "AWY", "walk")]
    conn = _write(pa, [(1, 2026, d, "R"), (2, 2026, "2026-10-08", "F")])
    got = {(s["game"], s["pid"]): (s["bf"], s["k"]) for s in E7.starts(conn)}
    assert got[(1, 1)] == (5, 2), "five batters, a strikeout double play counted"
    assert got[(1, 2)] == (4, 1)
    assert not {pid for _g, pid in got} & {3, 4}, "a reliever is never the starter"
    assert not [g for g, _p in got if g == 2], "a postseason game is left out"
    assert (3, 2) in got and (3, 5) in got, "a game mlb_games has not listed yet is kept"
    assert E7.coverage(conn)[2026] == (2, 1)


def test_a_start_is_read_only_from_the_starts_before_it():
    ks, bfs = [5, 7, 3, 9, 4], [20, 24, 18, 26, 22]
    ss = [{"pid": 7, "season": 2026, "date": f"2026-05-{10 + 5 * i:02d}", "game": i, "bf": b, "k": k}
          for i, (k, b) in enumerate(zip(ks, bfs))]
    ss += [{"pid": 8, "season": 2026, "date": f"2026-05-{10 + 5 * i:02d}", "game": 50 + i, "bf": 22, "k": 6}
           for i in range(3)]
    rows = E7.rows_from(ss)
    assert [(r["who"], r["y"]) for r in rows] == [("7|2026", 9.0), ("7|2026", 4.0)], "three starts behind it first"
    r = rows[0]
    logs = [GameLog(week=0, opponent="", value=v) for v in (3.0, 7.0, 5.0)]
    assert r["mu_a"] == compute_form(logs, 5.0, None, weights=MLB_WINDOW_WEIGHTS).mean
    assert r["mu_o"] == ewma_opps([20.0, 24.0, 18.0], E7.BF_HALF_LIFE)
    assert (r["k_sum"], r["bf_sum"], r["o"]) == (15.0, 62.0, 26.0)
    ss[4]["k"] = 15
    assert E7.rows_from(ss)[0] == r, "a later start changes nothing about an earlier one"


def test_b_is_a_distribution_with_its_mean_and_h_is_b_stretched():
    rows = E7.rows_from(E7.starts(_league(seasons=(2026,), pitchers=12, starts_each=14)))
    fit = E7.Fit(rows)
    x = min(rows, key=lambda r: r["mu_a"])
    pmf = fit.bf_pmf(x)
    assert abs(sum(p for _o, p in pmf) - 1) < 1e-12 and min(o for o, _p in pmf) >= 1
    f = fit.cdf_b(x)
    assert all(0 <= a <= b <= 1 + 1e-12 for a, b in zip(f, f[1:]))
    assert abs(sum(1 - v for v in f) - fit.mean_b(x)) < 0.02, "the CDF's own mean is the mean it claims"
    stretched = fit.cdf_b(x, scale=2.0)
    assert stretched[4] == f[2] and stretched[5] == f[2], "H is B's shape moved to another mean"
    assert fit.cdf_a(x, 0.0) <= fit.cdf_a(x, 5.0) and fit.cdf_a(x, 1e9) == 1.0


def test_the_fit_finds_the_shrink_the_league_was_built_with():
    """True rates spread over 0.15-0.32 give a between-pitcher variance of
    0.0024 against a batter's 0.18, an empirical-Bayes k near 74 batters;
    one shared rate leaves nothing to learn from a pitcher's own record, and
    the fit runs to its grid's top — which the holdout guard refuses."""
    fit = E7.Fit(E7.rows_from(E7.starts(_league(seasons=(2026,), pitchers=40, starts_each=28))))
    assert fit.k in (50.0, 100.0), fit.k
    assert abs(fit.league - 0.235) < 0.01 and not E7.on_edge(fit)
    flat = E7.Fit(E7.rows_from(E7.starts(_league(seasons=(2026,), pitchers=40, starts_each=28, same_rate=True))))
    assert flat.k == E7.K_GRID[-1] and E7.on_edge(flat)


def test_it_finds_batters_faced_where_they_matter_and_not_where_they_do_not():
    """The bar's power both ways, on made-up leagues of only 30 starters (the
    box has five times that): where strikeouts are batters faced times a
    rate, B advanced on 19 of 20 seeds when measured; where they come
    straight from a pitcher's mean with a spread batters faced do not
    explain, it advanced on none and was rejected on all 20."""
    built = [E7.study(_league(seed=s), holdout=True)["decisions"]["B v A"] for s in range(1, 5)]
    assert built.count("ADVANCE") >= 3, built
    straight = [E7.study(_league(seed=s, direct=True), holdout=True)["decisions"]["B v A"] for s in range(1, 5)]
    assert all(d.startswith("REJECTED") for d in straight), straight


def test_the_splits_follow_the_seasons_the_table_holds():
    def rows(season, n, start="03-28"):
        d0 = dt.date.fromisoformat(f"{season}-{start}")
        return [{"s": season, "date": (d0 + dt.timedelta(days=i % 180)).isoformat()} for i in range(n)]
    two = rows(2024, 100) + rows(2025, 600) + rows(2026, 600)
    train, valid, hold, labels, seasons = E7.splits(two)
    assert seasons == [2025, 2026] and {x["s"] for x in train} == {2025}, "a season under the minimum counts for nothing"
    assert all(x["date"] < "2026-07-01" for x in valid) and all(x["date"] >= "2026-07-01" for x in hold)
    assert len(valid) + len(hold) == 600 and labels[0] == "2025-2025"
    train, valid, hold, labels, seasons = E7.splits(rows(2026, 600))
    assert seasons == [2026] and all(x["date"] < "2026-06-01" for x in train)
    assert all("2026-06-01" <= x["date"] < "2026-07-15" for x in valid) and all(x["date"] >= "2026-07-15" for x in hold)
    assert E7.splits(rows(2026, 100)) is None


def test_the_holdout_is_read_only_with_the_flag_on_a_whole_season_off_no_edge():
    conn = _league()
    first = E7.study(conn)
    assert "holdout" not in first["periods"] and first["periods"]["validation"]["n"] >= E7.MIN_PART
    assert not first["edge"] and not first["waiting"]
    assert all(("not yet read" in v) or v.startswith("REJECTED") for v in first["decisions"].values())
    read = E7.study(conn, holdout=True)
    assert read["periods"]["validation"] == first["periods"]["validation"], "the flag changes nothing it already showed"
    assert "holdout" in read["periods"] or all(v.startswith("REJECTED") for v in read["decisions"].values())
    short = E7.study(_league(missing=60), holdout=True)
    assert short["waiting"] and "holdout" not in short["periods"], "a season still filling is not read"
    flat = E7.study(_league(same_rate=True), holdout=True)
    assert flat["edge"] and "holdout" not in flat["periods"], "a constant on its grid's edge needs an amendment first"
    assert "NOT YET" in E7.render(E7.study(_league(seasons=(2026,), pitchers=6, starts_each=10)))


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
