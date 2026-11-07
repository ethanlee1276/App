"""EXP-008: the NBA board's spread against a shape built from his minutes — the arithmetic and the guards.

research/exp8_nba_shape_box.py prices each NBA player-game two ways at one
centre (his rate per minute times his role's base minutes): the board's own
shape (engine/nba/prob at the cv the live build measures) and a compound
one (his minutes spread times a count given minutes). What these hold: the
regular season is read and a game he did not play is never scored; a game
is scored only from the games before it, at the board's own centre; the
board's shape here is exactly the board's over-chance; the compound shape
is a distribution centred where the board's is; the cv is the live build's
own rule; the splits follow the complete seasons and never touch the one
under way; and the bar finds a shape built from minutes where a league was
built that way and not where it was not.

Run directly: `python3 tests/test_nba_shape_lab.py`
"""
import datetime as dt
import math
import os
import random
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db, hoops_fit as HF                             # noqa: E402
from engine.hoops import NBA                                       # noqa: E402
from engine.nba import prob as P                                   # noqa: E402
from engine.nba.minutes import base_minutes, role_minutes          # noqa: E402
from research import exp8_nba_shape_box as E8                     # noqa: E402

COLS = "(sport, season, period, game_id, player, team, opponent, position, home, market, value)"


def _write(rows):
    path = os.path.join(tempfile.mkdtemp(), "history.db")
    conn = db.connect(path)
    conn.executemany(f"INSERT INTO player_game_logs {COLS} VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    return path


def _league(seasons=(2024, 2025, 2026), players=30, games=50, seed=1, direct=False):
    """A made-up league. Each player-season a role (minutes) and a rate per
    minute for each stat; a game's minutes vary around the role, with the
    odd night he barely plays and the odd night he does not. In the
    compound league a stat is a count with mean rate × his minutes that
    night; with ``direct`` it comes from his mean whatever his minutes
    (points normal at cv 0.30, the others negative binomial at cv 0.40).
    The last season has six games: one under way."""
    rng = random.Random(seed)
    rows = []

    def pois(lam):
        k, t = 0, math.exp(-lam)
        u, acc = rng.random(), t
        while u > acc:
            k += 1
            t *= lam / k
            acc += t
        return k

    def nb(m, phi):
        if phi <= 1:
            return pois(m)
        r = m / (phi - 1)
        return pois(rng.gammavariate(r, m / r))
    for season in seasons:
        n = games if season != seasons[-1] else 6
        for p in range(players):
            role = rng.uniform(18, 36)
            rates = {"pts": rng.uniform(0.35, 0.8), "reb": rng.uniform(0.1, 0.35), "ast": rng.uniform(0.05, 0.3)}
            for g in range(n):
                date = (dt.date(season, 10, 22) + dt.timedelta(days=int(g * 172 / games))).isoformat()
                m = 0.0 if rng.random() < 0.04 else max(1.0, min(48.0, rng.gauss(role, 4.5) - (12 if rng.random() < 0.07 else 0)))
                st = {"min": round(m, 1)}
                for s, r in rates.items():
                    if m == 0:
                        st[s] = 0.0
                    elif direct:
                        mu = r * role
                        st[s] = (float(max(0, round(rng.gauss(mu, 0.30 * mu)))) if s == "pts"
                                 else float(nb(mu, 1 + (0.4 * mu) ** 2 / mu if mu > 0 else 1)))
                    else:
                        st[s] = float(nb(r * m, 2.0 if s == "pts" else 1.1))
                for mk, v in st.items():
                    rows.append(("nba", season, date, f"P{p}-{date}", f"P{p}", "T", "O", "S", 1, mk, v))
    return _write(rows)


def _player(games, season=2025, name="Ace"):
    """One player's box-score rows: ``games`` = [(date, minutes, points)]."""
    rows = []
    for date, m, pts in games:
        for mk, v in (("min", m), ("pts", pts), ("reb", 5.0 if m else 0.0), ("ast", 3.0 if m else 0.0)):
            rows.append(("nba", season, date, f"{name}-{date}", name, "T", "O", "S", 1, mk, v))
    return rows


def test_the_regular_season_is_read_and_a_game_he_missed_is_never_scored():
    games = [("2025-10-22", 30.0, 20.0), ("2025-10-24", 32.0, 24.0), ("2025-10-26", 0.0, 0.0),
             ("2025-10-28", 28.0, 18.0), ("2025-10-30", 34.0, 30.0), ("2025-11-01", 31.0, 22.0),
             ("2026-04-20", 36.0, 40.0)]
    lg = E8.logs(E8.open_db(_write(_player(games))))
    assert [d for d, _st in lg[("Ace", 2025)]][-1] == "2025-11-01", "a playoff date is left out"
    rows = [r for r in E8.rows_from(lg, [2025]) if r["stat"] == "pts"]
    assert [r["date"] for r in rows] == ["2025-10-30", "2025-11-01"], "three games he played come first; the DNP is not one"
    r = rows[0]
    mins = [28.0, 32.0, 30.0]
    assert r["rate"] == (20.0 + 24.0 + 18.0) / sum(mins)
    assert r["base"] == base_minutes(role_minutes(mins)[0], NBA) and r["mu"] == r["rate"] * r["base"]
    assert (r["y"], r["m"]) == (30.0, 34.0)
    bench = [(d, 10.0, 4.0) for d, _m, _p in games[:6]]
    assert not E8.rows_from(E8.logs(E8.open_db(_write(_player(bench, name="Bench")))), [2025]), \
        "a role under MIN_BASE minutes is not one the books hang props on"


def test_the_boards_shape_here_is_the_boards_own_over_chance():
    for mu in (7.3, 24.6):
        f = E8.cdf_site("pts", mu, 0.31)
        for t in (3, 10, 22, 30):
            assert abs((1 - f[t]) - P.p_over_normal(mu, t + 0.5, max(0.1, 0.31 * mu))) < 1e-12
    for stat, mu in (("reb", 6.4), ("ast", 2.2)):
        f = E8.cdf_site(stat, mu, 0.45)
        for t in (0, 1, 4, 9):
            assert abs((1 - f[t]) - P.p_over_negbin(mu, t + 0.5, 0.45)) < 1e-9


def test_the_compound_shape_is_a_distribution_centred_where_the_boards_is():
    conn = E8.open_db(_league(seasons=(2025, 2026), players=12, games=40, seed=4))
    lg = E8.logs(conn)
    rows = E8.rows_from(lg, [2025])
    fit = E8.Fit(rows, {})
    assert abs(sum(fit.quad)) < 1e-9 and len(fit.quad) == E8.Q
    assert fit.cv == {s: NBA.sd_cv[s] for s in E8.STATS}, "no measured cv, the inherited one"
    x = min((r for r in rows if r["stat"] == "ast"), key=lambda r: r["mu"])
    f = fit.cdf_c(x)
    assert all(0 <= a <= b <= 1 + 1e-12 for a, b in zip(f, f[1:]))
    floor = sum(max(0.0, 1.0 - x["base"] - e) for e in fit.quad) / E8.Q * x["rate"]
    assert abs(sum(1 - v for v in f) - (x["mu"] + floor)) < 0.02, "its mean is the board's centre"


def test_the_cv_is_the_live_builds_own_rule():
    path = _league(seasons=(2024, 2025), players=30, games=40, seed=2)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    live, _counts = HF.fit_stat_cvs(conn, "nba")
    mine = E8.site_cvs(E8.logs(E8.open_db(path)), lambda s, d: True)
    assert mine == {s: live[s] for s in E8.STATS}, (mine, live)


def test_the_splits_follow_the_complete_seasons_and_never_the_one_under_way():
    lg = E8.logs(E8.open_db(_league(players=8, games=40, seed=3)))
    assert E8.complete_seasons(lg) == [2024, 2025], "2026 has six games: under way"
    train, valid, hold, labels, keep = E8.splits(lg)
    assert {r["s"] for r in train} == {2024} and {r["s"] for r in valid + hold} == {2025}
    assert all(r["date"] < "2026-01-01" for r in valid) and all(r["date"] >= "2026-01-01" for r in hold)
    assert keep(2024, "2024-11-01") and not keep(2025, "2025-11-01")
    one = {k: v for k, v in lg.items() if k[1] == 2025}
    train, valid, hold, labels, keep = E8.splits(one)
    assert all(r["date"] < "2025-12-15" for r in train) and all(r["date"] >= "2026-02-10" for r in hold)
    assert all("2025-12-15" <= r["date"] < "2026-02-10" for r in valid)
    assert E8.splits({k: v for k, v in lg.items() if k[1] == 2026}) is None
    assert "NOT YET" in E8.render(E8.study(E8.open_db(_league(seasons=(2026,), players=4, seed=3))))


def test_the_holdout_waits_for_the_flag():
    conn = E8.open_db(_league(seed=1))
    first = E8.study(conn)
    assert set(first["periods"]) == {"validation"}
    assert all(v.startswith("REJECTED") or "not yet read" in v for v in first["decisions"].values())
    read = E8.study(conn, holdout=True)
    assert set(read["periods"]) == {"validation", "holdout"}
    assert read["periods"]["validation"] == first["periods"]["validation"]


def test_it_finds_a_shape_built_from_minutes_and_not_one_that_is_not():
    """The bar both ways on made-up leagues of 30 players (the box has
    about fifteen times that). Measured over ten leagues each: where a stat
    is his minutes times a rate, C advanced in 19 of 30 stat tests (points
    in all 10); where a stat comes from his mean whatever his minutes, in
    none of 30."""
    for seed in (1, 2, 3):
        built = E8.study(E8.open_db(_league(seed=seed)), holdout=True)["decisions"]
        assert built["pts"] == "ADVANCE", (seed, built)
        flat = E8.study(E8.open_db(_league(seed=seed, direct=True)), holdout=True)["decisions"]
        assert not [d for d in flat.values() if d == "ADVANCE"], (seed, flat)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
