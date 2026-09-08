"""A preregistration can name the SIDE it is about, not only the grade.

WHERE THE QUESTION CAME FROM. The refusal audit that shipped on
2026-09-09 (`backtest.py --gate --real-lines`, 3,339 real-priced NFL
props) printed a segment table, and one row of it was ugly: of the 83
props the gate admitted, the 61 OVERs returned -24.7% at a flat unit and
the 22 UNDERs returned +20.8%. That is roughly 1.9 standard errors, in a
table nobody asked in advance, read after the fact — which is precisely
the shape of evidence `engine.prereg` exists to refuse to convict on and
to collect forward instead.

`verdict` could not express it. It splits a population on GRADE, with
optional filters for market, journal bucket and price band; the side a
bet took was not among them, so "do our OVERs lose" could not be
registered at all. This adds `sides` / `compare_sides` under exactly the
rule `markets` and `price_band` were added under before it:

  * optional, so nothing that does not carry them changes behaviour;
  * inside `_terms_hash` only when a test carries them, so no standing
    registration's fingerprint moves and none of them is voided;
  * enforced in `verdict` AND selected by `ROW_SQL`, because a filter the
    journal query does not feed reads an absent field, matches nothing,
    and sits at "0 of N" forever while looking perfectly healthy. That
    is not hypothetical — it is what nearly killed `TD_EDGE_NFL`, and
    `test_one_query_shape_serves_both_callers` next door exists because
    it happened a second time with `market`.
"""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import prereg                                   # noqa: E402


def _sided(n_over, over_wins, n_under, under_wins, date="2026-09-20"):
    """A pool split purely by SIDE — same grade, same price on both
    arms, so only the side can be separating them."""
    out = [{"date": date, "sport": "nfl", "grade": "A", "odds": -110,
            "side": "OVER", "market": "rec_yds",
            "status": "won" if i < over_wins else "lost"}
           for i in range(n_over)]
    out += [{"date": date, "sport": "nfl", "grade": "A", "odds": -110,
             "side": "UNDER", "market": "rec_yds",
             "status": "won" if i < under_wins else "lost"}
            for i in range(n_under)]
    return out


def _side_test(**kw):
    t = {"id": "side-split-fixture", "claim": "overs lose, unders do not",
         "sport": "nfl", "population": ["A"], "compare_to": ["A"],
         "sides": ["OVER"], "compare_sides": ["UNDER"],
         "metric": "ROI at a flat 1u, split on the side taken",
         "min_n": 60, "z_threshold": 1.96, "registered": "2026-09-09",
         "decides": "a side-aware shrink"}
    t.update(kw)
    t["hash"] = prereg._terms_hash(t)
    return t


def test_a_side_scoped_test_only_counts_that_side():
    """The whole point. Both arms are graded A, so if the side filter did
    nothing the population would be all 140 rows rather than the 80
    OVERs."""
    v = prereg.verdict(_side_test(), _sided(80, 30, 60, 40))
    assert v["n"] == 80, v
    assert v["n_reference"] == 60, v


def test_the_side_filter_applies_to_the_reference_too():
    """A filter on one arm only is worse than no filter: the comparison
    would be OVERs against everything-including-those-same-OVERs, which
    shrinks the very gap the test is registered to measure."""
    v = prereg.verdict(_side_test(), _sided(80, 30, 60, 40))
    # 60 unders, not the 140 rows in the pool.
    assert v["n_reference"] == 60
    # And the arms are disjoint: nothing is counted on both sides.
    assert v["n"] + v["n_reference"] == 140


def test_the_side_is_matched_however_the_registration_spells_it():
    """A population is a hand-typed list. `bets.side` is upper-cased by
    every writer, so a test registered as `["over"]` would collect
    nothing forever while reporting a healthy "0 of 60" — the failure
    mode this module keeps rediscovering."""
    v = prereg.verdict(_side_test(sides=["over"], compare_sides=["under"]),
                       _sided(80, 30, 60, 40))
    assert v["n"] == 80 and v["n_reference"] == 60, v
    # And a journal row with stray whitespace or lower case still lands.
    rows = _sided(80, 30, 60, 40)
    for r in rows:
        r["side"] = f" {r['side'].lower()} "
    v = prereg.verdict(_side_test(), rows)
    assert v["n"] == 80 and v["n_reference"] == 60, v


def test_a_test_that_names_no_side_still_counts_both():
    """Every registration made before today omits the field. If its
    absence filtered rather than passed through, the standing tests would
    silently stop collecting."""
    t = _side_test()
    t.pop("sides"), t.pop("compare_sides")
    t["hash"] = prereg._terms_hash(t)
    v = prereg.verdict(t, _sided(80, 30, 60, 40))
    assert v["n"] == 140, v


def test_a_row_with_no_side_is_counted_by_neither_arm():
    """A game bet carries a team, not an over/under. It must not fall
    into the OVER arm by default — a side-blind row silently graded as an
    OVER is the same class of bug as the `home_runs` rows that were
    journalled with the UNDER's probability wearing the OVER's side."""
    rows = _sided(80, 30, 60, 40)
    for r in rows[:10]:
        r["side"] = ""
    v = prereg.verdict(_side_test(), rows)
    assert v["n"] == 70, v
    assert v["n"] + v["n_reference"] == 130


def test_the_side_is_part_of_what_is_frozen():
    """If the side were outside the fingerprint, the arm that decides the
    answer could be swapped after seeing the data — turning a losing
    claim into a winning one with an edit. That is the exact move the
    hash exists to make visible."""
    base = _side_test()
    swapped = dict(base, sides=["UNDER"], compare_sides=["OVER"])
    assert prereg._terms_hash(swapped) != base["hash"]
    assert prereg.verdict(swapped, _sided(80, 30, 60, 40))["status"] == "void"


def test_the_side_fields_did_not_void_any_older_test():
    """Same rule the market filter and the price band were added under.
    `_terms_hash` keys only on fields a test carries, so a field none of
    them carries cannot move their fingerprints — and a voided
    preregistration reports nothing at all, which would throw every
    standing test away in silence."""
    for test in (prereg.B_MINUS, prereg.A_BAND_NFL, prereg.RECEPTIONS_A_NFL,
                 prereg.TD_EDGE_NFL, prereg.TD_EDGE_NFL_XFP,
                 prereg.LONG_PRICE_MLB):
        assert "sides" not in test, test["id"]
        assert "compare_sides" not in test, test["id"]
    path = os.path.join(tempfile.mkdtemp(), "prereg.json")
    for v in prereg.report([], path):
        assert v["status"] != "void", v


def test_the_journal_query_carries_the_side():
    """A filter the journal query does not select reads an absent field,
    matches nothing, and reports "0 of N" forever while looking healthy.
    Read from a real ledger rather than from the SQL string, so the
    column has to exist as well as be named."""
    from engine import ledger
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "t.db"))
    for side in ("OVER", "UNDER"):
        conn.execute(
            "INSERT INTO bets (date, sport, player, market, side, odds, "
            "grade, status, category, stake_units) VALUES "
            "(?,?,?,?,?,?,?,?,?,?)",
            ("2026-09-20", "nfl", f"P {side}", "rec_yds", side, -110,
             "A", "won", "main", 1.0))
    conn.commit()
    rows = prereg.rows_for(conn)
    assert {r["side"] for r in rows} == {"OVER", "UNDER"}, rows
    assert "side" in prereg.ROW_SQL


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
