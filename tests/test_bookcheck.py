"""bookcheck: is the edge real, or is it the outlier book?

engine/odds.best_over_line shops for the longest price and then de-vigs
THAT BOOK'S OWN quote to get the fair the edge is measured against. The
further out of line a book is, the more likely it is chosen AND the lower
its own de-vigged fair — so the edge grows with the outlier, mechanically,
before the model says anything.

Whether that matters is empirical, and the discriminator is which
benchmark the results FOLLOW:

    the field is right    → we bet a price longer than the truth, land at
                            the field's rate, and BEAT the taken price
    the outlier is right  → we bet the truth, land at the taken price's
                            rate, and MISS the field's

Both worlds have the same measured gap between taken price and field. Only
the outcomes separate them, which is why a gap alone is not a finding.

Run directly: `python3 tests/test_bookcheck.py`
"""

import contextlib
import datetime
import io
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bookcheck as bc                                        # noqa: E402


def _odds(p):
    return round(100 * (1 - p) / p) if p < 0.5 else -round(100 * p / (1 - p))


def world(field_is_right, n=2500, seed=4, outlier_book="Hard Rock", gap=0.03):
    """Three books agree; one posts a longer price. Either the field has
    the true probability or the outlier does — identical measured gap,
    opposite truths."""
    rnd = random.Random(seed)
    snaps, bets = [], []
    ts = time.time()
    day = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    for i in range(n):
        p_field = rnd.uniform(0.12, 0.30)
        p_out = p_field - gap
        true_p = p_field if field_is_right else p_out
        for bk in ("A", "B", "C"):
            snaps.append({"ts": ts, "player": f"P{i}", "market": "home_runs",
                          "book": bk, "line": 0.5, "over_odds": _odds(p_field)})
        snaps.append({"ts": ts, "player": f"P{i}", "market": "home_runs",
                      "book": outlier_book, "line": 0.5,
                      "over_odds": _odds(p_out)})
        bets.append({"sport": "mlb", "market": "home_runs", "player": f"P{i}",
                     "side": "OVER", "book": outlier_book, "odds": _odds(p_out),
                     "hit_prob": 0.25, "date": day, "stake_units": 0.1,
                     "pnl_units": 0.0,
                     "status": "won" if rnd.random() < true_p else "lost"})
    return bc.pair(bets, bc.consensus_by_date(snaps))


def _run(paired, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        bc.report(paired, **kw)
    return " ".join(buf.getvalue().split())


# --- the structure being examined --------------------------------------------
def _code_of(fn) -> str:
    """A function's executable source: no docstring, no comments.

    A structural assertion about what a function DOES must not be
    answerable by what someone wrote about it. `ast.unparse` drops
    comments outright; the docstring is removed by hand.
    """
    import ast
    import inspect
    import textwrap
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    node = tree.body[0]
    body = node.body
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        body = body[1:]
    return "\n".join(ast.unparse(st) for st in body)


def test_the_fair_really_does_come_from_the_taken_book():
    """The premise. If best_over_line ever starts de-vigging against a
    field, this whole file is measuring a problem that no longer exists."""
    from engine import odds
    src = _code_of(odds.best_over_line)
    # THE CONTRACT, NOT THE ARGUMENT LIST. This matched the call
    # character for character and went red when a `hold` argument was
    # threaded through — a change that leaves the premise untouched. What
    # matters is that the fair comes from THIS line's own two prices.
    assert "devig_two_way(ln.over_odds, ln.under_odds" in src
    # NOR THE PROSE. This read the raw source and went red a second time
    # when a comment explaining why the sharp reference is dropped from
    # the SHOP but kept in `devig.board_fair`'s consensus used the word
    # — an edit that cannot change where the fair comes from, because a
    # comment cannot. `_code_of` hands over the executable statements
    # with the docstring and every comment removed, so the word can only
    # appear here by being called.
    assert "consensus" not in src


# --- the two worlds ----------------------------------------------------------
def test_an_outlier_the_field_disagrees_with_is_called_out():
    out = _run(world(field_is_right=False))
    assert "THE OUTLIER WAS NOT VALUE" in out
    assert "de-vigging that same book's quote" in out
    assert "measure against the FIELD" in out


def test_genuine_line_shopping_is_not_called_a_problem():
    """The positive control, and the one that matters most — a tool that
    always says the structure is broken is not a measurement."""
    out = _run(world(field_is_right=True))
    assert "THE OUTLIER WAS REAL VALUE" in out
    assert "shopping is earning its keep" in out


def test_the_gap_alone_is_never_the_finding():
    """Both worlds have the SAME gap between the taken price and the
    field. Only the outcomes separate them, so a report that convicted on
    the gap would convict on working line shopping too."""
    for right in (True, False):
        p = world(field_is_right=right)
        gap = sum(b["outlier"] for b in p) / len(p)
        assert gap > 0.02, right          # the gap is there either way
    assert "NOT VALUE" in _run(world(False))
    assert "REAL VALUE" in _run(world(True))


def test_an_ambiguous_book_refuses_to_call_it():
    """A half-point outlier on a few hundred bets cannot be told from
    nothing, and saying so is the point. Ambiguity is a property of the
    GAP being small, not of n being small — a big enough outlier convicts
    on a short sample and should."""
    out = _run(world(field_is_right=True, n=400, gap=0.004))
    assert "NOT SEPARABLE YET" in out
    assert "what it BUYS is what needs more bets" in out


# --- the consensus itself ----------------------------------------------------
def test_a_field_of_two_is_not_a_consensus():
    ts = time.time()
    snaps = [{"ts": ts, "player": "P", "market": "home_runs", "book": bk,
              "line": 0.5, "over_odds": 400} for bk in ("A", "B")]
    assert bc.consensus_by_date(snaps) == {}
    snaps.append({"ts": ts, "player": "P", "market": "home_runs", "book": "C",
                  "line": 0.5, "over_odds": 400})
    assert len(bc.consensus_by_date(snaps)) == 1


def test_the_consensus_is_a_median_so_one_stale_book_cannot_define_it():
    ts = time.time()
    snaps = [{"ts": ts, "player": "P", "market": "home_runs", "book": bk,
              "line": 0.5, "over_odds": o}
             for bk, o in (("A", 300), ("B", 300), ("C", 300), ("D", 5000))]
    (median, n, spread), = bc.consensus_by_date(snaps).values()
    assert n == 4
    assert abs(median - bc._implied(300)) < 1e-9, "an outlier moved the field"
    assert spread > 0.2


def test_only_the_last_quote_per_book_counts():
    """A book that drifted all day should contribute where it ended, not an
    average over its own movement."""
    ts = time.time()
    snaps = [{"ts": ts - 3600, "player": "P", "market": "home_runs",
              "book": "A", "line": 0.5, "over_odds": 1000},
             {"ts": ts, "player": "P", "market": "home_runs", "book": "A",
              "line": 0.5, "over_odds": 300}]
    snaps += [{"ts": ts, "player": "P", "market": "home_runs", "book": bk,
               "line": 0.5, "over_odds": 300} for bk in ("B", "C")]
    (median, n, _s), = bc.consensus_by_date(snaps).values()
    assert n == 3, "a book was counted twice"
    assert abs(median - bc._implied(300)) < 1e-9


# --- guards ------------------------------------------------------------------
def test_unders_are_skipped_because_snapshots_carry_the_over_price():
    ts = time.time()
    day = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    snaps = [{"ts": ts, "player": "P", "market": "hits", "book": bk,
              "line": 1.5, "over_odds": -110} for bk in ("A", "B", "C")]
    bets = [{"sport": "mlb", "market": "hits", "player": "P", "side": "UNDER",
             "book": "A", "odds": -110, "hit_prob": 0.5, "date": day,
             "status": "won", "stake_units": 1.0, "pnl_units": 0.9}]
    assert bc.pair(bets, bc.consensus_by_date(snaps)) == []


def test_no_snapshots_says_what_is_missing():
    out = _run([])
    assert "No settled OVER bets" in out
    assert "linemoves" in out


def test_concentration_is_flagged_where_it_bites():
    out = _run(world(field_is_right=False))
    assert "of these bets are at one book" in out
    assert "furthest from the field" in out


def test_it_never_edits_the_pricing_path():
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "bookcheck.py"), encoding="utf-8").read()
    assert "write_text" not in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
