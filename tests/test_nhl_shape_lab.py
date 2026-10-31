"""EXP-009: the NHL board's count shape against a shape built from his ice time — the arithmetic and the guards.

research/exp9_nhl_shape_box.py prices each NHL skater-game two ways at one
centre, the board's own projection as the NHL walk makes it: the board's
own count and a compound one (his ice-time spread times a count given ice
time). What these hold: every game feeds a projection but only a
regular-season game he played is scored, and never one right after his ice
time moved; the centre, the dispersion and the position priors are the
walk's own; the board's shape here is exactly the board's over-chance; the
compound shape is a distribution centred where the board's is; the splits
follow the complete seasons and never touch the one under way; the
holdout waits for the flag; and the bar finds a shape built from ice time
where a league was built that way and not where the board's own spreads
are the truth.

Run directly: `python3 tests/test_nhl_shape_lab.py`
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
from engine.nhl import backtest as NB                              # noqa: E402
from engine.nhl import model as M                                  # noqa: E402
from research import exp9_nhl_shape_box as E9                      # noqa: E402

COLS = "(sport, season, period, game_id, player, team, opponent, position, home, market, value)"


def _write(rows):
    path = os.path.join(tempfile.mkdtemp(), "history.db")
    conn = db.connect(path)
    conn.executemany(f"INSERT INTO player_game_logs {COLS} VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    return path


def _game(name, season, date, pos, st):
    return [("nhl", season, date, f"{name}-{date}", name, "T", "O", pos, 1, mk, v) for mk, v in st.items()]


def _league(seasons=(2023, 2024, 2025), players=36, games=82, seed=1, flat=False):
    """A made-up league. Each player-season a role (ice time) and a rate per
    minute for each stat; a night's ice time is the role times a ratio near
    one, with the odd short night, and a player sits out now and then. In
    the compound league a stat is a count with mean rate × that night's ice
    time (shots and blocks over-dispersed); with ``flat`` it comes from his
    mean whatever his ice time, with the board's own spreads (1.25 for
    shots and blocks, Poisson for points). A third of the players are
    defencemen; two nights after April 15 are playoff games; the last
    season has six games: one under way."""
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

    built = {"sog": 1.15, "points": 1.0, "blocks": 1.3}
    board = {"sog": M.SOG_DISPERSION, "points": 1.0, "blocks": M.SOG_DISPERSION}
    for season in seasons:
        n = games if season != seasons[-1] else 6
        days = [(dt.date(season, 10, 10) + dt.timedelta(days=int(g * 178 / games))).isoformat() for g in range(n)]
        if n == games:
            days += [f"{season + 1}-04-20", f"{season + 1}-04-23"]
        for p in range(players):
            pos = "D" if p % 3 == 0 else "C"
            role = rng.uniform(17, 24) if pos == "D" else rng.uniform(10, 20)
            rates = {"sog": rng.uniform(0.04, 0.16), "points": rng.uniform(0.01, 0.05),
                     "blocks": rng.uniform(0.04, 0.10) if pos == "D" else rng.uniform(0.01, 0.04)}
            for date in days:
                if rng.random() < 0.03:
                    continue
                ratio = rng.uniform(0.15, 0.5) if rng.random() < 0.05 else max(0.4, min(1.6, rng.gauss(1.0, 0.13)))
                toi = role * ratio
                st = {"toi": round(toi, 2)}
                for s, r in rates.items():
                    st[s] = float(nb(r * role, board[s]) if flat else nb(r * toi, built[s]))
                rows += _game(f"P{p}", season, date, pos, st)
    return _write(rows)


def test_every_game_feeds_a_projection_but_only_a_regular_season_game_he_played_is_scored():
    st = {"toi": 18.0, "sog": 3.0, "points": 1.0, "blocks": 1.0}
    days = ["2024-10-10", "2024-10-12", "2024-10-14", "2024-10-16", "2024-10-18"]
    rows = []
    for d in days:
        rows += _game("Ace", 2024, d, "C", st)
    rows += _game("Ace", 2024, "2024-10-20", "C", dict(st, toi=0.0))          # dressed, never played
    rows += _game("Ace", 2024, "2024-10-22", "C", st)
    rows += _game("Ace", 2024, "2025-04-20", "C", st)                          # a playoff night
    players = E9.skaters(E9.open_db(_write(rows)))
    got = E9.rows_from(players, E9.league_by_date(players), [2024])
    assert [(r.date, r.stat) for r in got] == [("2024-10-22", s) for s in E9.STATS]
    assert got[0].y == 3.0 and got[0].t == 18.0 and got[0].who == "Ace|2024"
    swing = []
    for i in range(20):
        d = (dt.date(2024, 10, 10) + dt.timedelta(days=2 * i)).isoformat()
        swing += _game("Bee", 2024, d, "D", dict(st, toi=9.0 if i >= 15 else 18.0))
    players = E9.skaters(E9.open_db(_write(swing)))
    got = E9.rows_from(players, E9.league_by_date(players), [2024])
    scored = {r.date for r in got}
    assert "2024-11-13" in scored and not scored & {"2024-11-15", "2024-11-17"}, \
        "three nights into half his ice time, his last five have moved past ROLE_SWING: the board passes"


def test_the_centre_the_dispersion_and_the_priors_are_the_walks_own():
    path = _league(players=12, games=40, seed=2)
    conn = E9.open_db(path)
    players = E9.skaters(conn)
    league = E9.league_by_date(players)
    walk = NB._all_games(conn)
    walk_league = NB._league_by_date(walk)
    for day, by in league.items():
        for grp, rates in by.items():
            for s in E9.STATS:
                assert abs(rates[s] - walk_league[day][grp][s]) < 1e-9, (day, grp, s)
    rows = E9.rows_from(players, league, [2023, 2024])
    assert len(rows) > 600
    for x in rows[::37]:
        name = x.who.split("|")[0]
        games = walk[name]["games"]
        i = next(k for k, g in enumerate(games) if g["date"] == x.date)
        view = {"position": walk[name]["position"], "games": games[:i][::-1][:M.RECENT_GAMES]}
        proj = M.skater_projection(view, x.stat, walk_league[x.date], {}, "")
        assert (proj["mean"], proj["disp"], proj["toi"]) == (x.mu, x.disp, x.toi), (x.who, x.date, x.stat)


def test_the_boards_shape_here_is_the_boards_own_over_chance():
    for stat, mu, disp in (("sog", 2.7, 1.31), ("sog", 4.4, 1.0), ("points", 0.62, 1.0), ("blocks", 1.3, 1.6)):
        x = E9.Row("A|2024", 2024, "2025-01-05", stat, 0.0, 18.0, mu, disp, 18.0)
        f = E9.cdf_site(x)
        for t in range(len(f) - 1):
            want = M.skater_prob({"mean": mu, "disp": disp}, stat, t + 0.5, "OVER")
            assert abs((1 - f[t]) - want) < 1e-9, (stat, mu, disp, t)


def test_the_compound_shape_is_a_distribution_centred_where_the_boards_is():
    players = E9.skaters(E9.open_db(_league(seasons=(2024, 2025), players=12, games=50, seed=4)))
    rows = E9.rows_from(players, E9.league_by_date(players), [2024])
    fit = E9.Fit(rows)
    assert len(fit.quad) == E9.Q and abs(sum(fit.quad) / E9.Q - 1.0) < 1e-12
    assert fit.spread[0] < 1.0 < fit.spread[2]
    assert all(0.5 < v < 3.0 for v in list(fit.phi.values()) + list(fit.phi_n.values())), (fit.phi, fit.phi_n)
    for stat in E9.STATS:
        x = min((r for r in rows if r.stat == stat), key=lambda r: r.mu)
        for f in (fit.cdf_c(x), fit.cdf_n(x)):
            assert all(0 <= a <= b <= 1 + 1e-12 for a, b in zip(f, f[1:]))
            assert abs(sum(1 - v for v in f) - x.mu) < 0.01, (stat, sum(1 - v for v in f), x.mu)


def test_the_splits_follow_the_complete_seasons_and_never_the_one_under_way():
    players = E9.skaters(E9.open_db(_league(players=8, games=60, seed=3)))
    assert E9.complete_seasons(players) == [2023, 2024], "2025 has six games: under way"
    train, valid, hold, labels = E9.splits(players)
    assert {r.s for r in train} == {2023} and {r.s for r in valid + hold} == {2024}
    assert all(r.date < "2025-01-01" for r in valid) and all(r.date >= "2025-01-01" for r in hold)
    assert all(r.date < f"{r.s + 1}-04-15" for r in train + valid + hold), "no playoff night is scored"
    one = {k: dict(v, games=[g for g in v["games"] if g.season == 2024]) for k, v in players.items()}
    train, valid, hold, labels = E9.splits(one)
    assert all(r.date < "2024-12-15" for r in train) and all(r.date >= "2025-02-10" for r in hold)
    assert all("2024-12-15" <= r.date < "2025-02-10" for r in valid)
    now = {k: dict(v, games=[g for g in v["games"] if g.season == 2025]) for k, v in players.items()}
    assert E9.splits(now) is None
    assert "NOT YET" in E9.render(E9.study(E9.open_db(_league(seasons=(2025,), players=4, seed=3))))


def test_the_holdout_waits_for_the_flag():
    conn = E9.open_db(_league(seed=1))
    first = E9.study(conn)
    assert set(first["periods"]) == {"validation"}
    assert all(v.startswith("REJECTED") or "not yet read" in v for v in first["decisions"].values())
    read = E9.study(conn, holdout=True)
    assert set(read["periods"]) == {"validation", "holdout"}
    assert read["periods"]["validation"] == first["periods"]["validation"]
    assert "decision (98.33% intervals" in E9.render(read)


def test_it_finds_a_shape_built_from_ice_time_and_not_where_the_boards_spread_is_the_truth():
    """The bar both ways on made-up leagues of 90 skaters (the box has about
    ten times that). Measured over ten leagues of each kind: where a count
    comes from that night's ice time, C advanced in 9 of 30 stat tests
    (shots 5 of 10, points 1, blocks 3); where it comes from his mean
    whatever his ice time, with the board's own spreads, in 1 of 30. The
    described refit N beat the board's spread with its interval under zero
    in 11 of 30 and 5 of 30, the five all shots: the board's 1.25 is a
    spread around the true mean, and a forecast's spread also carries its
    own centre's error (the refit read 1.27-1.37 there)."""
    for seed in (1, 5):
        built = E9.study(E9.open_db(_league(players=90, seed=seed)), holdout=True)["decisions"]
        assert built["sog"] == "ADVANCE", (seed, built)
        flat = E9.study(E9.open_db(_league(players=90, seed=seed, flat=True)), holdout=True)["decisions"]
        assert "ADVANCE" not in flat.values(), (seed, flat)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
