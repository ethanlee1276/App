"""One ruler for every stake — and a migration that refuses to guess.

Commit 3f86208 moved the stake converter from a twenty-unit bankroll to a
hundred-unit one. Rows logged after it are on the new ruler, rows before it
on the old, and nothing in the schema said which — so the journal has been
adding two definitions of "unit" together, and the Record page's cumulative
curve has not been a time series since.

The dangerous part of fixing that is scope. Only the Kelly path was
rescaled; the paper buckets journal a hardcoded flat 0.1 that the commit
never touched, and multiplying those by five would invent a loss that never
happened. So the script proves which categories moved FROM THE DATA and
touches nothing else — these tests are mostly about that refusal.

Run directly: `python3 tests/test_rescale.py`
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rescale as rs                                            # noqa: E402

BEFORE, AFTER = "2026-08-02T10:00:00", "2026-08-05T10:00:00"


def _row(cat, ts, stake, pnl, status="lost", sport="mlb"):
    return {"id": None, "ts": ts, "date": ts[:10], "sport": sport,
            "category": cat, "stake_units": stake, "pnl_units": pnl,
            "status": status}


def _journal():
    """A ledger with the real shape: Kelly rows that jumped 5x, and flat-
    stake rows that did not."""
    out = []
    for _ in range(40):
        out.append(_row("main", BEFORE, 0.10, -0.10))
        out.append(_row("main", AFTER, 0.50, -0.50))
        # paper buckets: a hardcoded 0.1 on both sides of the cutover
        out.append(_row("loose", BEFORE, 0.10, -0.10))
        out.append(_row("loose", AFTER, 0.10, -0.10))
        out.append(_row("longshot", BEFORE, 0.10, -0.10))
        out.append(_row("longshot", AFTER, 0.10, -0.10))
    return out


# --- what it must refuse to touch -------------------------------------------
def test_flat_stake_buckets_are_left_alone():
    """The whole risk of this migration. `loose`, `longshot`, `stale` and
    `pricedout` journal a literal 0.1 that the commit never touched;
    multiplying them by five invents money that was never staked."""
    cats = rs.by_category(_journal())
    by = {c["category"]: c for c in cats}
    assert abs(by["loose"]["jump"] - 1.0) < 0.01
    assert abs(by["longshot"]["jump"] - 1.0) < 0.01
    assert rs.affected(cats) == ["main"]


def test_a_kelly_category_that_did_not_jump_is_left_alone():
    """Evidence, not assumption. If `main` shows no discontinuity on some
    other book, there is nothing to migrate there and the script must say
    so rather than applying the factor because the category name matched."""
    flat = [_row("main", BEFORE, 0.10, -0.10) for _ in range(40)]
    flat += [_row("main", AFTER, 0.11, -0.11) for _ in range(40)]
    assert rs.affected(rs.by_category(flat)) == []


def test_a_jumped_category_outside_the_kelly_path_is_left_alone():
    """Both conditions, not either. A flat bucket whose stake happens to
    change for some unrelated reason is still not the Kelly rescale."""
    odd = [_row("stale", BEFORE, 0.10, -0.10) for _ in range(40)]
    odd += [_row("stale", AFTER, 0.90, -0.90) for _ in range(40)]
    cats = rs.by_category(odd)
    assert cats[0]["jump"] > rs.MIN_JUMP        # it did jump…
    assert rs.affected(cats) == []              # …and is still not touched


# --- the arithmetic ----------------------------------------------------------
def test_normalising_scales_only_the_old_side():
    j = [r for r in _journal() if r["category"] == "main"]
    raw = rs.roi(j)
    norm = rs.roi(j, rs.FACTOR, ["main"])
    # 40 x 0.10 + 40 x 0.50 = 24.0 as recorded
    assert abs(raw["staked"] - 24.0) < 1e-6
    # old side becomes 40 x 0.50 = 20.0, new side unchanged at 20.0
    assert abs(norm["staked"] - 40.0) < 1e-6
    # every bet lost, so ROI is -100% either way — the RATIO is scale-free
    # per bet; what the ruler distorts is the WEIGHTS between the halves.
    assert abs(raw["roi"] + 1.0) < 1e-9 and abs(norm["roi"] + 1.0) < 1e-9


def test_the_ruler_moves_pooled_roi_when_the_halves_differ():
    """The actual distortion: post-cutover rows carry five times the weight
    in a stake-weighted ROI, so a bad recent run reads worse than it is."""
    good = [_row("main", BEFORE, 0.10, +0.10, "won") for _ in range(100)]
    bad = [_row("main", AFTER, 0.50, -0.50, "lost") for _ in range(100)]
    j = good + bad
    raw = rs.roi(j)["roi"]
    norm = rs.roi(j, rs.FACTOR, ["main"])["roi"]
    # As recorded the losing half dominates; normalised they weigh equally.
    assert raw < -0.6, raw
    assert abs(norm) < 1e-6, norm


def test_the_cutover_splits_on_the_journal_timestamp():
    assert rs._side(_row("main", "2026-08-04T02:23:28", 0.1, 0)) == "old"
    assert rs._side(_row("main", "2026-08-04T02:23:30", 0.1, 0)) == "new"


def test_the_factor_is_the_ratio_of_the_two_rulers():
    assert rs.OLD_UNITS == 20.0 and rs.NEW_UNITS == 100.0
    assert rs.FACTOR == 5.0


# --- the dry run is the default ---------------------------------------------
def test_a_dry_run_writes_nothing_and_says_so():
    import contextlib
    import io

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE bets (id INTEGER PRIMARY KEY, ts TEXT, "
                 "date TEXT, sport TEXT, category TEXT, stake_units REAL, "
                 "pnl_units REAL, status TEXT)")
    conn.executemany(
        "INSERT INTO bets (ts, date, sport, category, stake_units, pnl_units,"
        " status) VALUES (?,?,?,?,?,?,?)",
        [(r["ts"], r["date"], r["sport"], r["category"], r["stake_units"],
          r["pnl_units"], r["status"]) for r in _journal()])
    conn.commit()
    snapshot = conn.execute("SELECT SUM(stake_units) FROM bets").fetchone()[0]

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rs.report(conn, apply_it=False)
    out = buf.getvalue()
    assert "DRY RUN" in out and "nothing written" in out
    assert conn.execute("SELECT SUM(stake_units) FROM bets").fetchone()[0] == snapshot
    # and it showed its working
    assert "loose" in out and "longshot" in out and "main" in out


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
