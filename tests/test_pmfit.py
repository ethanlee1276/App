"""Fitting the informed-flow weights instead of assigning them.

`engine.predmarket.score_trade` scores a Polymarket trade out of 100 by
adding up whichever signals fired — 40/30/15/8 across the size tiers, 20
for order-book impact, 15 for a niche market, 25 for a fresh wallet,
then ×1.3 when three of them stack. Every one of those is a
professional estimate, and the module has always said so.

`flag_report` grades the composite honestly. It could never grade a
COMPONENT, because the only thing `pm_flags` recorded was the total — so
a year of resolutions would still not have said which signal earned it.
That is the same shape as the game-line model, which shipped a "shrink
halfway to the market" guess for its whole life because no closing
number was ever stored anywhere.

These tests pin the breakdown being recorded (this module's own first
rule is that flow cannot be backfilled, and neither can this), the
estimator recovering a known truth, the guards that stop a thin or lucky
record from moving a weight, and the promise that nothing changes at all
until a fit exists.

Run directly: `python3 tests/test_pmfit.py`
"""

import contextlib
import math
import os
import random
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import pmfit as F
from engine import predmarket as P


@contextlib.contextmanager
def sandbox_state(state=None):
    keep, keep_cache = F.STATE_PATH, dict(F._cache)
    F.STATE_PATH = os.path.join(tempfile.mkdtemp(), "pmfit.json")
    F._cache.clear()
    if state:
        F._write_state(state)
        F._cache.clear()
    try:
        yield F.STATE_PATH
    finally:
        F.STATE_PATH = keep
        F._cache.clear()
        F._cache.update(keep_cache)


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    P.ensure_tables(conn)
    return conn


_seq = [0]


def _flags(conn, rows):
    """``rows`` is (price, side, won, "sig,sig").

    The tx counter is module-level so two calls against one connection
    cannot collide on the primary key.
    """
    base = _seq[0]
    _seq[0] += len(rows)
    conn.executemany(
        "INSERT INTO pm_flags (venue,tx,ts,wallet,slug,market,outcome,side,"
        "price,usd,score,status,won,roi,resolved_ts,signals,stack_mult) "
        "VALUES ('polymarket',?,?,?,?,?,?,?,?,?,?,'settled',?,0.0,2000,?,1.0)",
        [(f"tx{base + i}", 1000 + base + i, "0xw", "s", "M", "Yes", side,
          price, 9999, 50, won, sigs)
         for i, (price, side, won, sigs) in enumerate(rows)])
    conn.commit()


def _synthetic(conn, truth, n=4000, seed=11):
    """Tape generated from KNOWN coefficients, so the fit has an answer
    to be right or wrong about."""
    random.seed(seed)
    rows = []
    for _ in range(n):
        price = random.uniform(0.2, 0.8)
        fired = {k for k in truth if random.random() < 0.45}
        if not fired:
            continue
        z = math.log(price / (1 - price)) + sum(truth[k] for k in fired)
        p = 1 / (1 + math.exp(-z))
        rows.append((price, "BUY", 1 if random.random() < p else 0,
                     ",".join(sorted(fired))))
    _flags(conn, rows)
    return len(rows)


# --- the breakdown is recorded -----------------------------------------------
def test_a_flag_records_which_signals_fired():
    """Without this column no weight can ever be attributed, however long
    the tape runs — and this module's first rule is that flow cannot be
    backfilled."""
    conn = _db()
    trade = {"wallet": "0xa", "slug": "s", "title": "T", "outcome": "Yes",
             "side": "BUY", "price": 0.42, "usd": 150000, "ts": 1000,
             "tx": "0xt"}
    with sandbox_state():
        scored = P.score_trade(trade, {"slug": "s", "vol24": 50000,
                                       "yes": 0.44}, {}, now=1000)
    P.store_flags(conn, [scored])
    row = conn.execute("SELECT signals, stack_mult FROM pm_flags").fetchone()
    assert set(row["signals"].split(",")) == {"size", "impact", "niche"}
    assert row["stack_mult"] == 1.3


def test_the_stack_bonus_is_not_a_signal():
    """It is a multiplier on the others, stored in its own column. Listing
    it among the fireable keys would have the fitter looking for a signal
    no flag can ever carry."""
    assert P.SIG_STACK not in P.SIGNAL_KEYS
    assert set(P.SIGNAL_KEYS) == {"size", "impact", "niche", "fresh_wallet"}


def test_an_older_flag_with_no_breakdown_is_skipped_not_guessed():
    conn = _db()
    _flags(conn, [(0.5, "BUY", 1, None), (0.5, "BUY", 0, "")])
    assert F.observations(conn) == []


def test_a_sell_is_read_as_a_bet_on_the_other_side():
    conn = _db()
    _flags(conn, [(0.30, "SELL", 1, "impact")])
    obs = F.observations(conn)
    assert len(obs) == 1
    # The SELL's implied probability is 1 - 0.30 = 0.70.
    assert abs(obs[0]["offset"] - math.log(0.7 / 0.3)) < 1e-9


# --- the estimator -----------------------------------------------------------
def test_it_recovers_known_coefficients():
    conn = _db()
    truth = {"impact": 0.8, "fresh_wallet": 0.4, "niche": 0.0, "size": 0.0}
    _synthetic(conn, truth)
    got = {c.key: c for c in F.fit_signals(conn)["coefficients"]}
    assert set(got) == set(truth)
    for k, want in truth.items():
        assert abs(got[k].beta - want) < 0.25, (k, got[k].beta, want)
        assert got[k].se < 0.15


def test_a_signal_the_price_already_knew_measures_at_zero():
    """The finding no hit-rate table can produce. A signal that fires on
    trades the market had already priced correctly wins often and adds
    nothing — its coefficient, offset by the price, is zero."""
    conn = _db()
    _synthetic(conn, {"niche": 0.0, "impact": 0.9})
    got = {c.key: c.beta for c in F.fit_signals(conn)["coefficients"]}
    assert abs(got["niche"]) < 0.2, got
    assert got["impact"] > 0.5, got


def test_zero_becomes_zero_points_rather_than_a_deleted_signal():
    """"We looked and this one does not predict anything" is a thing the
    card should be able to say, so the signal keeps firing and keeps
    showing on the receipts at nought."""
    coefs = [F.Coefficient("impact", beta=0.9, se=0.05, n=900),
             F.Coefficient("niche", beta=-0.02, se=0.05, n=900)]
    pts = F.points_from(coefs)
    assert pts["niche"] == 0
    assert "niche" in pts               # present, not dropped
    assert pts["impact"] > 0


def test_no_single_signal_may_run_away_with_the_whole_score():
    coefs = [F.Coefficient("impact", beta=9.0, se=0.05, n=900),
             F.Coefficient("niche", beta=0.01, se=0.05, n=900)]
    pts = F.points_from(coefs)
    assert pts["impact"] <= F.SCORE_CEIL * F.MAX_SHARE


# --- the guards --------------------------------------------------------------
def test_a_thin_record_is_held():
    conn = _db()
    _flags(conn, [(0.5, "BUY", i % 2, "impact") for i in range(30)])
    out = F.fit_signals(conn)
    assert out["coefficients"] == []
    whys = " ".join(h.held for h in out["held"])
    assert "needs" in whys


def test_a_signal_with_too_few_firings_is_held_while_others_fit():
    conn = _db()
    _synthetic(conn, {"impact": 0.8, "size": 0.3})
    # …plus a handful of a third signal, well under the floor.
    _flags(conn, [(0.5, "BUY", 1, "fresh_wallet") for _ in range(10)])
    out = F.fit_signals(conn)
    fitted = {c.key for c in out["coefficients"]}
    held = {h.key for h in out["held"]}
    assert "impact" in fitted
    assert "fresh_wallet" in held


def test_perfect_separation_is_held_not_adopted():
    """Every flag carrying the signal won. The maximum likelihood is an
    infinite weight, which is what a small lucky sample looks like."""
    conn = _db()
    rows = [(0.5, "BUY", 1, "impact") for _ in range(500)]
    rows += [(0.5, "BUY", 0, "niche") for _ in range(500)]
    _flags(conn, rows)
    out = F.fit_signals(conn)
    assert out["coefficients"] == []
    assert any("converge" in h.held or "needs" in h.held for h in out["held"])


def test_measured_refuses_a_corrupt_or_thin_state():
    for bad in ({"points": {"impact": 20}, "n": 5},
                {"points": {}, "n": 900},
                {"points": {"impact": "banana"}, "n": 900},
                {"points": {"impact": 500}, "n": 900}):
        with sandbox_state(bad):
            assert F.measured() is None, bad
            assert F.points_for("impact") is None


def test_an_unreadable_state_file_costs_the_fit_not_the_feed():
    with sandbox_state() as path:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{ not json")
        F._cache.clear()
        assert F.measured() is None
        trade = {"wallet": "0xa", "slug": "s", "title": "T", "outcome": "Yes",
                 "side": "BUY", "price": 0.42, "usd": 150000, "ts": 1000,
                 "tx": "0xt"}
        assert P.score_trade(trade, None, {}, now=1000)["score"] > 0


# --- what reaches the feed ---------------------------------------------------
def _score(trade=None, market=None):
    trade = trade or {"wallet": "0xa", "slug": "s", "title": "T",
                      "outcome": "Yes", "side": "BUY", "price": 0.42,
                      "usd": 150000, "ts": 1000, "tx": "0xt"}
    market = market if market is not None else {"slug": "s", "vol24": 50000,
                                                "yes": 0.44}
    return P.score_trade(trade, market, {}, now=1000)


def test_nothing_changes_until_a_fit_exists():
    with sandbox_state():
        pts = {s["key"]: s["pts"] for s in _score()["signals"]}
    assert pts == {"size": 30, "impact": 20, "niche": 15}


def test_a_fitted_weight_reaches_the_score():
    with sandbox_state({"points": {"size": 30, "impact": 45, "niche": 0,
                                   "fresh_wallet": 25},
                        "n": 900, "fit_at": 0}):
        pts = {s["key"]: s["pts"] for s in _score()["signals"]}
    assert pts["impact"] == 45
    assert pts["niche"] == 0


def test_the_size_tiers_keep_their_shape_under_one_fitted_weight():
    """The fit says what "size fired" is worth; the tier table says how
    much of it a $10K trade earns against a $500K one."""
    with sandbox_state({"points": {"size": 40, "impact": 20, "niche": 15,
                                   "fresh_wallet": 25},
                        "n": 900, "fit_at": 0}):
        big = _score({"wallet": "0xa", "slug": "s", "title": "T",
                      "outcome": "Yes", "side": "BUY", "price": 0.42,
                      "usd": 600000, "ts": 1000, "tx": "0x1"}, None)
        small = _score({"wallet": "0xa", "slug": "s", "title": "T",
                        "outcome": "Yes", "side": "BUY", "price": 0.42,
                        "usd": 12000, "ts": 1000, "tx": "0x2"}, None)
    bp = [s["pts"] for s in big["signals"] if s["key"] == "size"][0]
    sp = [s["pts"] for s in small["signals"] if s["key"] == "size"][0]
    assert bp > sp > 0


def test_the_note_names_the_signals_the_record_killed():
    with sandbox_state({"points": {"impact": 45, "niche": 0,
                                   "fresh_wallet": 0, "size": 30},
                        "n": 900, "fit_at": 0}):
        note = F.note()
    assert note and "900" in note
    assert "fresh_wallet" in note and "niche" in note


def test_the_note_is_silent_with_no_fit():
    with sandbox_state():
        assert F.note() is None


def test_refresh_persists_and_is_readable_back():
    conn = _db()
    _synthetic(conn, {"impact": 0.8, "size": 0.3, "niche": 0.0})
    with sandbox_state():
        out = F.refresh(conn)
        assert out["adopted"]
        assert F.measured() is not None
        assert F.points_for("impact") == out["adopted"]["impact"]


# --- the board says what changed ---------------------------------------------
def _app_js():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return open(os.path.join(root, "web", "js", "app.js"),
                encoding="utf-8").read()


def test_the_report_card_renders_the_fitted_weights():
    """A score that quietly started meaning something different is the
    worst version of this change. The weights go on the page."""
    src = _app_js()
    assert "function intelWeights(" in src
    assert "intelWeights(v.weights)" in src


def test_a_signal_measured_at_nothing_still_shows_a_row():
    """"We looked and this one does not predict anything" is the finding.
    Dropping the row would hide it."""
    src = _app_js()
    block = src[src.index("function intelWeights("):]
    block = block[:block.index("\n}\n") + 3]
    assert "no measured edge" in block
    # …and the rows are built from every key in `points`, not a filtered
    # subset, so a zero cannot fall out on the way to the page.
    assert "Object.keys(pts)" in block


def test_the_panel_is_silent_when_the_build_shipped_no_weights():
    """An older payload, or a locked board, must not render an empty
    section header with nothing under it."""
    src = _app_js()
    block = src[src.index("function intelWeights("):]
    block = block[:block.index("\n}\n") + 3]
    assert 'if (!w) return "";' in block


def test_the_build_attaches_the_weights_to_the_report_card():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "pm_build.py"), encoding="utf-8").read()
    assert "from engine import pmfit" in src
    assert 'validation["weights"]' in src
    # A fitter must never take the build down.
    fit = src[src.index("from engine import pmfit"):]
    assert "except Exception" in fit[:900]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
