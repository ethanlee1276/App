"""The stale-line shadow book gets a verdict per sport.

Ethan, 2026-09-07: "I just want a wining nfl model for our best bets AND
edge models."

The best-measured signal in this repository is not a model. A book
pricing a prop a point under the field beat the eventual close 64.8% of
the time on 30,448 quotes (`marketscan.stale_quotes`), and every such
flag has been journaled since as a flat 0.1u shadow bet. Closing-line
value is evidence; settlement is money. `ledger.stale_verdict` reads the
shadow book per sport and says, by arithmetic, whether the flags have
earned the right to be picks. These tests pin the arithmetic and each
guard that holds it.

Run directly: `python3 tests/test_stale_verdict.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import ledger                                    # noqa: E402


def _book(rows):
    """``rows`` is ``[(sport, odds, won)]``; every row a settled stale flag
    at a flat 0.1u, distinct players so the journal's unique key holds."""
    conn = ledger.connect(":memory:")
    for i, (sport, odds, won) in enumerate(rows):
        dec = (odds / 100.0 + 1.0) if odds > 0 else (100.0 / -odds + 1.0)
        pnl = 0.1 * (dec - 1.0) if won else -0.1
        conn.execute(
            "INSERT INTO bets (ts, sport, date, player, market, side, line, book, odds, "
            "projection, hit_prob, edge, confidence, grade, stake_units, status, actual, "
            "pnl_units, category) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'stale')",
            ("2026-09-01T00:00:00", sport, "2026-09-01", f"P{i}", "rec_yds", "OVER", 50.5,
             "DraftKings", odds, 0.0, 0.5, 0.012, 0.0, "", 0.1,
             "won" if won else "lost", 1.0 if won else 0.0, pnl))
    conn.commit()
    return conn


def _flags(sport, n, hit, odds=-110):
    wins = round(n * hit)
    return [(sport, odds, i < wins) for i in range(n)]


def test_a_thin_book_is_held_whatever_it_shows():
    v = ledger.stale_verdict(_book(_flags("nfl", 40, 0.70)))
    assert v["nfl"]["verdict"] == "hold" and "needs 200" in v["nfl"]["why"], v


def test_a_hit_rate_under_the_taken_break_even_is_held():
    """At −110 the break-even is 52.4%; 50% over 300 flags is real money
    lost and reads as such."""
    v = ledger.stale_verdict(_book(_flags("nfl", 300, 0.50)))
    r = v["nfl"]
    assert r["verdict"] == "hold" and "standard errors" in r["why"], r
    assert abs(r["break_even"] - 0.5238) < 1e-3 and r["z"] < 0 and r["roi"] < 0


def test_a_real_edge_promotes_and_the_arithmetic_is_right():
    """64% at −110 over 300 flags: 11.6 points over break-even on a 2.9-
    point standard error — the CLV measurement's own gap, cashed."""
    v = ledger.stale_verdict(_book(_flags("nfl", 300, 0.64)))
    r = v["nfl"]
    assert r["verdict"] == "promote", r
    assert r["n"] == 300 and r["wins"] == 192
    assert abs(r["hit_rate"] - 0.64) < 1e-9
    assert abs(r["se"] - (0.5238 * 0.4762 / 300) ** 0.5) < 1e-3
    assert 3.9 < r["z"] < 4.1, r["z"]
    # 192 wins at 0.1u × 0.909 less 108 losses at 0.1u, over 30u staked.
    assert abs(r["roi"] - ((192 * 0.1 * (100 / 110) - 108 * 0.1) / 30.0)) < 1e-4   # rounded to 4


def test_break_even_follows_the_prices_actually_taken():
    """Flags at +120 need only 45.5%; a 50% hit rate there is an edge,
    and the same 50% at −110 is a loss. One bar per book, not per repo."""
    plus = ledger.stale_verdict(_book(_flags("nfl", 300, 0.50, odds=120)))["nfl"]
    minus = ledger.stale_verdict(_book(_flags("nfl", 300, 0.50, odds=-110)))["nfl"]
    assert abs(plus["break_even"] - 0.4545) < 1e-3 and plus["z"] > 0 and plus["roi"] > 0
    assert minus["z"] < 0 and minus["roi"] < 0
    assert plus["verdict"] == "hold" and "standard errors" in plus["why"]  # +1.7σ, not two


def test_beating_the_rate_is_not_beating_the_vig():
    """A book whose wins sit on the short prices and whose losses sit on
    the long ones: 200 flags at −400 all won and 100 at +400 all lost is
    66.7% against a 60% average break-even — two and a third standard
    errors clear — and −16.7% ROI. The third guard is the one for this."""
    rows = _flags("nfl", 200, 1.0, odds=-400) + _flags("nfl", 100, 0.0, odds=400)
    r = ledger.stale_verdict(_book(rows))["nfl"]
    assert r["z"] > 2.0 and r["roi"] < 0, r
    assert r["verdict"] == "hold" and "not the vig" in r["why"], r


def test_sports_are_judged_apart():
    rows = _flags("mlb", 300, 0.64) + _flags("nfl", 300, 0.48)
    v = ledger.stale_verdict(_book(rows))
    assert v["mlb"]["verdict"] == "promote" and v["nfl"]["verdict"] == "hold", v
    assert set(v) == {"mlb", "nfl"}


def test_an_empty_book_says_nothing_and_the_report_carries_the_verdicts():
    conn = ledger.connect(":memory:")
    assert ledger.stale_verdict(conn) == {}
    import inspect
    src = inspect.getsource(ledger)
    assert '"stale_verdicts": stale_verdict(conn, since=since)' in src
    # And nothing promotes on its own: no pipeline reads the verdict yet.
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in ("engine/pipeline.py", "engine/mlb/pipeline.py", "nfl_build.py", "mlb_build.py",
                 "cfb_build.py"):
        assert "stale_verdict" not in open(os.path.join(root, name)).read(), name


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
