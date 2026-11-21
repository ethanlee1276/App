"""The books' chance for the board's thin picks, from their main lines.

engine/fieldcurve reads each book's two-sided MAIN line as one point on the
market's curve, with a shape measured on 2022-2025 games (variance = PHI x
mean; fieldcurvefit.py), and gives the field's chance at any line.
research/thinmarket_box.py (EXP-R06) tries pricetrust's rule on the board
picks that have no three-book field at their own line, with pricetrust's
bar and one read. What these hold: the distributions are the distributions
they claim; a book's centre reproduces its own price; the field leaves out
the proxy, one-sided books and duplicates and needs three; the fitter
recovers a planted PHI; and the box test passes where our chance runs above
a true curve, does not where we are right, and reads once.
"""
import datetime as dt
import json
import math
import os
import random
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import fieldcurvefit as FF                                            # noqa: E402
from engine import fieldcurve as FC, ledger                           # noqa: E402
from research import thinmarket_box as TM                            # noqa: E402

BOOKS3 = [("dk", 4.5, -105, -115), ("fd", 4.5, 100, -120), ("mgm", 3.5, -160, 130)]


def test_the_gamma_tail_is_the_integral_it_claims():
    def pdf(x, k, th):
        return math.exp((k - 1) * math.log(x) - x / th - math.lgamma(k) - k * math.log(th))
    for k, th, x in ((2.4, 20.0, 60.0), (12.0, 20.0, 230.0)):
        n = 20000
        h = x / n
        integral = sum(pdf((i + 0.5) * h, k, th) for i in range(n)) * h
        assert abs(FC._gamma_p(k, x / th) - integral) < 1e-5


def test_a_count_has_the_mean_and_spread_it_claims():
    for m, phi in ((3.3, 1.194), (33.0, 1.772)):
        pmf = FC._count_pmf(m, phi, 400)
        mu = sum(k * p for k, p in enumerate(pmf))
        var = sum((k - mu) ** 2 * p for k, p in enumerate(pmf))
        assert abs(sum(pmf) - 1) < 1e-9 and abs(mu - m) < 1e-6 and abs(var / mu - phi) < 1e-6
    pois = FC._count_pmf(1.4, 0.795, 60)
    assert abs(sum(k * p for k, p in enumerate(pois)) - 1.4) < 1e-9, "at PHI under one, a Poisson"


def test_a_books_centre_reproduces_its_own_price():
    for market, line, fair in (("receptions", 4.5, 0.52), ("rec_yds", 55.5, 0.48), ("pass_att", 32.5, 0.5)):
        c = FC.centre(market, line, fair)
        assert abs(FC.over_chance(market, c, line) - fair) < 1e-6
    assert FC.centre("anytime_td", 0.5, 0.4) is None, "no shape, no centre"
    assert FC.centre("receptions", 4.5, 0.995) is None, "too lopsided to pin a middle"


def test_a_whole_number_line_leaves_the_push_out():
    m = 4.0
    pmf = FC._count_pmf(m, FC.PHI["receptions"], 40)
    over = 1 - sum(pmf[:5])
    assert abs(FC.over_chance("receptions", m, 4.0) - over / (1 - pmf[4])) < 1e-12


def test_the_field_is_three_books_quoting_both_sides():
    noise = [("proxy", 2.5, -300, 200), ("cz", 4.5, -110, None), ("dk", 6.5, 150, -190)]
    got = FC.field_chance("receptions", BOOKS3 + noise, 2.5, "OVER")
    assert got is not None and got[1] == 3, "the proxy, a one-sided book and a second dk quote are left out"
    over, books, m = got
    under, _, _ = FC.field_chance("receptions", BOOKS3, 2.5, "UNDER")
    assert abs(over + under - 1) < 1e-12 and over > 0.75, "an alt over below the middle is likely"
    assert FC.field_chance("receptions", BOOKS3[:2], 2.5, "OVER") is None, "two books are not a field"


def test_the_fitter_recovers_a_planted_spread():
    rng = random.Random(5)

    def nb(m, phi):
        r = m / (phi - 1)
        lam = rng.gammavariate(r, m / r)
        k, t = 0, math.exp(-lam)
        u, s = rng.random(), t
        while u > s:
            k += 1
            t *= lam / k
            s += t
        return k
    rows = []
    for season in ("2024", "2025"):
        for p in range(120):
            m = rng.uniform(2.5, 7.0)
            for _g in range(14):
                rows.append({"season_type": "REG", "season": season, "player_display_name": f"P{p}",
                             "team": "T", "position": "WR", "receptions": str(nb(m, 1.5))})
    got, thirds, n = FF.phi(FF.groups(rows), "receptions")
    assert 200 <= n <= 240 and abs(got - 1.5) < 0.1, (n, got)   # a few low-mean seasons fall under the floor
    assert all(abs(t - 1.5) < 0.2 for _mu, t in thirds), thirds


def _iso(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat()


def _ledger(weeks, per_week, gap, seed, truth="curve"):
    """A journal of thin board picks (over 3.5 receptions, main lines at 4.5
    and 5.5 only) and the snapshots behind them; ``gap`` is how far our
    chance runs above the field's curve; ``truth`` says which number the
    outcomes follow."""
    rng = random.Random(seed)
    d = tempfile.mkdtemp()
    db, snaps = os.path.join(d, "ledger.db"), os.path.join(d, "lines.jsonl")
    conn = ledger.connect(db)
    t0 = dt.datetime(2026, 9, 10, 17, tzinfo=dt.timezone.utc).timestamp()
    with open(snaps, "w") as fh:
        for w in range(weeks):
            for i in range(per_week):
                player = f"Player {w}-{i}"
                shift = rng.choice((-60, -40, -20, 0, 20))
                quotes = [("dk", 4.5, -105 + shift, -115 - shift), ("fd", 4.5, 100 + shift, -120 - shift),
                          ("mgm", 5.5, 130 + shift, -160 - shift)]
                t = t0 + w * 7 * 86400 + i * 60
                for b, line, o, u in quotes:
                    fh.write(json.dumps({"ts": t - 3600, "player": player, "market": "receptions", "book": b,
                                         "line": line, "over_odds": o, "under_odds": u}) + "\n")
                market = FC.field_chance("receptions", quotes, 3.5, "OVER")[0]
                ours = min(0.97, market + gap)
                p_true = market if truth == "curve" else ours
                won = rng.random() < p_true
                conn.execute("INSERT INTO bets (ts, sport, date, game_day, team, player, market, side, line, odds, "
                             "hit_prob, edge, grade, stake_units, stake_dollars, status, category, pnl_units) "
                             "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             (_iso(t), "nfl", f"2026-W{w + 1:02d}", "2026-09-14", "T", player, "receptions",
                              "OVER", 3.5, -180, round(ours, 4), round(ours - market - 0.03, 4), "Strong",
                              0.1, 0, "won" if won else "lost", "board", 0))
    conn.commit()
    conn.close()
    return db, snaps


def test_thin_picks_are_the_ones_pricetrust_could_not_price_and_the_curve_prices_them():
    db, snaps = _ledger(2, 30, 0.12, 1)
    rep = TM.study(TM.PT.open_ledger(db), snaps)
    assert rep["thin"] == 60 and rep["curve_priced"] == {"receptions": 60}
    assert rep["pricetrust_sources"] == {"none": 60}, "no three-book field at 3.5"
    assert rep["decision"]["verdict"] == "NOT YET"


def test_it_passes_where_we_run_above_a_true_curve_and_not_where_we_are_right():
    """The bar's power, as pricetrust states its own: on made-up seasons of 80
    thin picks a week, it passes most runs where the curve is the truth and
    our chance a 12-point overclaim (33 of 40 seeds when measured), and
    almost never where our chance is the truth (1 of 40)."""
    def verdicts(truth, seeds):
        out = []
        for seed in seeds:
            db, snaps = _ledger(6, 80, 0.12, seed, truth=truth)
            out.append(TM.study(TM.PT.open_ledger(db), snaps)["decision"])
        return out
    right = verdicts("curve", range(1, 11))
    assert sum(d["verdict"] == "PASSES" for d in right) >= 6, [d["verdict"] for d in right]
    passed = next(d for d in right if d["verdict"] == "PASSES")
    assert passed["weeks"] == 3 and passed["choice"]["w"] >= 0.5, "one read: the first weeks that reach the bar"
    wrong = verdicts("ours", range(1, 11))
    assert sum(d["verdict"] == "PASSES" for d in wrong) <= 2, [d["verdict"] for d in wrong]


def test_the_decision_weeks_are_fixed_once_reached():
    weeks = [{"n": 40}, {"n": 40}, {"n": 40}, {"n": 500}]
    decide, later = TM.decision_weeks(weeks)
    assert len(decide) == 3 and len(later) == 1
    decide, later = TM.decision_weeks([{"n": 30}, {"n": 30}, {"n": 30}, {"n": 30}])
    assert len(decide) == 4 and later == [], "under the bar's minimums, every week waits"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
