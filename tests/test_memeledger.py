"""Did the coins we called actually go up — and would we admit it if not?

Ethan, 2026-08-19: "track which meme coins we recommend and if they
actually gain value or lose value after we recommend them … make it real
and accurate."

Rocket Radar published a ranked board with no memory. This is the memory,
on the terms the sports record has always used: the call is filed at the
price we saw, before the outcome is known, and it is never deleted.

FOUR THINGS ARE DEFENDED HERE, and every one of them is a way this kind
of track record normally lies.

  * ONE CALL PER COIN PER CHANNEL PER DAY. The loop rebuilds every few
    minutes and a coin sits on the board for hours; one row per
    appearance would file the same idea three hundred times and let a
    single lucky coin outvote a hundred bad ones.
  * THE PATH, NOT THE ENDPOINT. A coin that went 5x and round-tripped
    and a coin that never moved both close at 0%. Peak and trough since
    the call are carried so the record can tell them apart.
  * A COIN THAT VANISHES IS AN OUTCOME. Mints leave the feed because
    liquidity died. Dropping them leaves a board of survivors, which is
    the single easiest way to fake a record in this asset class — and
    the first version of the path summary did exactly that, filtering on
    `seen > 0` and reporting "gone: 0" while a third of the calls had
    gone to nothing.
  * THE MEDIAN, NOT THE MEAN. One 50x makes a mean meaningless. The mean
    is not computed anywhere in the module.

Run directly: `python3 tests/test_memeledger.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine import memeledger as ml                             # noqa: E402

T0 = 1_700_000_000.0


def _board(prices, rocket=(), exits=()):
    coins = [{"mint": m, "symbol": m[:5], "name": m, "price_usd": p,
              "market_cap": 1e6, "liquidity": 5e4, "momentum": 70, "risk": 30}
             for m, p in prices.items() if p is not None]
    return {"coins": coins, "rocket": list(rocket), "exits": list(exits)}


def _conn():
    return ml.connect(":memory:")


# --- the unit of a call ------------------------------------------------------
def test_a_coin_on_the_board_all_day_is_one_call():
    """The loop rebuilds every few minutes. Without this the record is a
    popularity contest between coins that lingered."""
    conn = _conn()
    b = _board({"A": 1.0}, ["A"])
    assert ml.log_calls(conn, b, now=T0) == 1
    for i in range(1, 20):
        assert ml.log_calls(conn, b, now=T0 + i * 300) == 0
    assert conn.execute("SELECT COUNT(*) FROM meme_calls").fetchone()[0] == 1


def test_both_channels_are_graded():
    """"This one is falling apart" is a claim that can be wrong, and a
    desk that only grades its buys is grading half its opinions."""
    conn = _conn()
    ml.log_calls(conn, _board({"A": 1.0, "B": 1.0}, ["A"], ["B"]), now=T0)
    got = {r[0]: r[1] for r in conn.execute(
        "SELECT channel, COUNT(*) FROM meme_calls GROUP BY channel")}
    assert got == {"rocket": 1, "exit": 1}


def test_a_coin_with_no_usable_price_is_not_filed():
    """A call we cannot mark later is not a call, and a zero would divide
    into every return that followed it."""
    conn = _conn()
    b = _board({"A": 1.0}, ["A", "B"])
    b["coins"].append({"mint": "B", "symbol": "B", "name": "B",
                       "price_usd": 0, "momentum": 9, "risk": 9})
    assert ml.log_calls(conn, b, now=T0) == 1


# --- the path ----------------------------------------------------------------
def test_the_peak_ratchets_and_the_close_does_not_erase_it():
    """The headline finding this exists for: 5x then round-trip must not
    read the same as never moved."""
    conn = _conn()
    ml.log_calls(conn, _board({"A": 1.0}, ["A"]), now=T0)
    for i, px in enumerate([2.0, 8.0, 0.5], start=1):
        ml.mark(conn, _board({"A": px}), now=T0 + i * 3600)
    r = ml.recent(conn, 1, now=T0 + 4 * 3600)[0]
    assert round(r["peak"], 3) == 7.0, r["peak"]      # +700% at its best
    assert round(r["last"], 3) == -0.5                # closed at -50%
    assert round(r["trough"], 3) == -0.5


def test_a_horizon_is_stamped_once_and_never_moves():
    """A mark is a fact about a moment. Re-stamping it would let a later
    recovery rewrite what the 1h number was."""
    conn = _conn()
    ml.log_calls(conn, _board({"A": 1.0}, ["A"]), now=T0)
    ml.mark(conn, _board({"A": 3.0}), now=T0 + 3700)
    ml.mark(conn, _board({"A": 0.1}), now=T0 + 4000)
    rows = conn.execute("SELECT horizon, pct FROM meme_marks").fetchall()
    assert [(r["horizon"], round(r["pct"], 2)) for r in rows] == [("1h", 2.0)]


# --- survivorship ------------------------------------------------------------
def test_a_vanished_coin_is_counted_not_dropped():
    """The bug this module was written to prevent, and then committed in
    its own first draft: the path summary filtered on `seen > 0`, so a
    coin that disappeared before its first mark left the record entirely
    and `gone` read 0."""
    conn = _conn()
    ml.log_calls(conn, _board({"A": 1.0, "GHOST": 1.0}, ["A", "GHOST"]), now=T0)
    ml.mark(conn, _board({"A": 1.2}), now=T0 + 3700)          # GHOST is gone
    path = ml.report(conn, now=T0 + 3700)["channels"]["rocket"]["path"]
    assert path["n"] == 2, "a call vanished from the record"
    assert path["gone"] == 1
    assert path["never_marked"] == 1
    assert path["followed"] == 1


def test_a_vanished_coin_is_never_imputed_as_minus_one_hundred():
    """A dead pool is unsellable, which is not quite the same claim as
    worthless. Quietly imputing a number is how a record starts arguing
    for itself — the count sits beside the median instead."""
    conn = _conn()
    ml.log_calls(conn, _board({"A": 1.0, "GHOST": 1.0}, ["A", "GHOST"]), now=T0)
    ml.mark(conn, _board({"A": 1.5}), now=T0 + 3700)
    path = ml.report(conn, now=T0 + 3700)["channels"]["rocket"]["path"]
    assert round(path["median_last"], 3) == 0.5, \
        "the vanished coin was folded into the median"


def test_a_coin_that_comes_back_stops_being_gone():
    conn = _conn()
    ml.log_calls(conn, _board({"A": 1.0}, ["A"]), now=T0)
    ml.mark(conn, _board({}), now=T0 + 3700)
    assert ml.recent(conn, 1, now=T0 + 3700)[0]["gone"] is True
    ml.mark(conn, _board({"A": 2.0}), now=T0 + 7400)
    assert ml.recent(conn, 1, now=T0 + 7400)[0]["gone"] is False


# --- the reporting refuses to flatter ---------------------------------------
def test_the_module_never_computes_a_mean():
    """One 50x makes an average meaningless, and an average is what a
    promoter would quote."""
    src = open(os.path.join(ROOT, "engine", "memeledger.py"),
               encoding="utf-8").read()
    # Narrowed after the first version failed on the HIT RATE, which
    # divides a count by len(pcts) and is a perfectly good statistic. The
    # thing being banned is an average of the RETURNS, and the only way to
    # get one is to sum them.
    for banned in ("statistics.mean", "sum(pcts)", "def _mean", "np.mean"):
        assert banned not in src, banned
    assert "_median" in src, "the median is what leads"


def test_the_path_and_the_horizons_describe_the_same_calls():
    """They did not at first: the path summarised every call including
    ones filed four minutes ago, whose peak is necessarily near zero, and
    printed "median peaked +3%" directly above a 24h median in the
    thousands. Two populations, read as a contradiction."""
    conn = _conn()
    ml.log_calls(conn, _board({"OLD": 1.0}, ["OLD"]), now=T0)
    ml.mark(conn, _board({"OLD": 4.0}), now=T0 + 3700)
    # A call filed seconds ago must not dilute the path medians.
    ml.log_calls(conn, _board({"NEW": 1.0}, ["NEW"]), now=T0 + 90000)
    path = ml.report(conn, now=T0 + 90000)["channels"]["rocket"]["path"]
    assert path["n"] == 1, "a brand-new call entered the path summary"


def test_the_worst_case_is_reported_beside_the_best():
    conn = _conn()
    ml.log_calls(conn, _board({"A": 1.0, "B": 1.0}, ["A", "B"]), now=T0)
    ml.mark(conn, _board({"A": 5.0, "B": 0.02}), now=T0 + 3700)
    m = ml.report(conn, now=T0 + 3700)["channels"]["rocket"]["marks"]["1h"]
    assert round(m["best"], 2) == 4.0 and round(m["worst"], 2) == -0.98
    assert m["down_80"] == 1, "a coin that lost 98% is not counted as a rug"
    assert m["hit_rate"] == 0.5


def test_the_export_is_atomic():
    """The page polls this file. A truncate-and-write caught mid-poll
    serves half a JSON document — the same lesson the board's own writer
    already carries."""
    src = open(os.path.join(ROOT, "engine", "memeledger.py"),
               encoding="utf-8").read()
    assert "tmp.replace(p)" in src


def test_the_build_files_and_marks_on_every_cycle():
    build = open(os.path.join(ROOT, "memes_build.py"), encoding="utf-8").read()
    assert "memeledger.log_calls" in build and "memeledger.mark" in build
    assert "memerecord.json" in build
    # Its own failure domain: a broken ledger costs the record, not the board.
    i = build.index("memeledger.log_calls")
    assert "try:" in build[max(0, i - 700):i]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
