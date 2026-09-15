"""The comparison six other diagnostics never made.

guardfit, bleed, selcheck, selfit and barcheck all take --sport and all
default to mlb, so the +12-point over-claim has been measured six ways and
never once compared against another sport. That comparison decides what to
repair: if the sports miss by the same share it lives in what they SHARE —
the shrink, the de-vig, the credibility guard, the edge gate — and NFL
inherits it at kickoff. If they differ it is baseball's projection layer,
and one engine-wide correction would damage the sports already honest.

Pinned here:

  * both scales are always reported, because ranking sports on absolute
    points is the fault this repo hit three times in one week,
  * a thin sport is shown and kept OUT of the test, since its bar would
    reconcile anything with anything,
  * "cannot be answered yet" is a verdict, not a failure,
  * agreement is reported as weak evidence, because Q fails to reject far
    more easily than it rejects.

Run directly: `python3 tests/test_gapcheck.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gapcheck as gc                                           # noqa: E402
from engine import ledger                                       # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _board(spec, category="main"):
    """spec: {sport: (n, claimed, landed_rate)} — deterministic."""
    conn = ledger.connect(":memory:")
    k = 0
    for sport, (n, claim, land) in spec.items():
        wins = round(n * land)
        for i in range(n):
            k += 1
            conn.execute(
                "INSERT INTO bets (ts,sport,date,player,market,side,line,book,"
                "odds,hit_prob,edge,status,category) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("2026-08-01T12:00:00", sport, "2026-08-01", f"P{k}", "m1",
                 "OVER", 1.5, "dk", -110, claim, 0.04,
                 "won" if i < wins else "lost", category))
    conn.commit()
    return conn


# --- both scales, always -----------------------------------------------------
def test_the_gap_is_reported_in_points_and_as_a_share_of_the_claim():
    """A sport claiming 15% and one claiming 58% cannot be ranked on
    points: three points is a fifth of the first and a twentieth of the
    second. Reporting one scale is how the loss miner's five-point bar, the
    Lab's ROI tile and selfit's signed threshold all went wrong."""
    s = gc.by_sport(gc.load(_board({"a": (100, 0.60, 0.48)})))[0]
    assert abs(s["points"] - 0.12) < 1e-9
    assert abs(s["relative"] - 0.20) < 1e-9


def test_the_test_runs_on_the_relative_scale():
    """Points are not comparable across sports; the share is."""
    assert gc.SCALE == "relative"
    # two sports with the same SHARE but different points must agree
    a = gc.agree(gc.by_sport(gc.load(_board(
        {"a": (300, 0.60, 0.48), "b": (300, 0.30, 0.24)}))))
    assert a["ok"] and not a["differ"], a
    # …and the same POINTS but different shares must not be forced together
    pts = gc.by_sport(gc.load(_board({"a": (300, 0.60, 0.48),
                                      "b": (300, 0.30, 0.18)})))
    assert abs(pts[0]["points"] - pts[1]["points"]) < 1e-9
    assert abs(pts[0]["relative"] - pts[1]["relative"]) > 0.15


def test_the_error_is_poisson_binomial():
    """A sport whose claims run 12% to 70% is badly served by n*p̄(1-p̄)."""
    import inspect
    src = inspect.getsource(gc.by_sport)
    assert "hit_prob" in src and "(1 - float(r[\"hit_prob\"]))" in src


# --- thin sports are shown, not tested ---------------------------------------
def test_a_thin_sport_is_listed_but_excluded_from_the_test():
    """A 30-bet sport carries a bar wide enough to reconcile anything with
    anything. Including it manufactures agreement."""
    sports = gc.by_sport(gc.load(_board(
        {"mlb": (247, 0.579, 0.457), "wnba": (30, 0.55, 0.50)})))
    assert {s["sport"] for s in sports} == {"mlb", "wnba"}
    a = gc.agree(sports)
    assert a["ok"] is False and a["usable"] == ["mlb"]


def test_one_sport_alone_cannot_answer_the_question():
    a = gc.agree(gc.by_sport(gc.load(_board({"mlb": (247, 0.579, 0.457)}))))
    assert a["ok"] is False and a["k"] == 1


def test_cannot_be_answered_is_printed_as_a_verdict():
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        gc.report(_board({"mlb": (247, 0.579, 0.457), "wnba": (30, 0.55, 0.5)}))
    out = buf.getvalue()
    assert "CANNOT BE ANSWERED YET" in out
    assert "real answer, not a failure" in out
    assert "NFL should be treated as exposed" in out


# --- the agreement test ------------------------------------------------------
def test_sports_missing_by_the_same_share_are_not_separated():
    a = gc.agree(gc.by_sport(gc.load(_board(
        {"mlb": (247, 0.579, 0.457), "wnba": (140, 0.520, 0.409),
         "ufc": (90, 0.640, 0.500)}))))
    assert a["ok"] and a["differ"] is False
    assert a["i2"] < 0.25, a


def test_a_broken_baseball_beside_honest_sports_is_separated():
    """The reading that would clear NFL."""
    a = gc.agree(gc.by_sport(gc.load(_board(
        {"mlb": (247, 0.579, 0.457), "wnba": (200, 0.520, 0.515),
         "ufc": (150, 0.640, 0.633)}))))
    assert a["ok"] and a["differ"] is True
    assert a["p"] < gc.ALPHA and a["i2"] > 0.5


def test_the_chi_square_tail_is_accurate_enough_for_a_verdict():
    """Wilson–Hilferty, because there is no scipy here. It only has to be
    finer than a decision at 0.05."""
    for x, df, want in ((3.841, 1, 0.050), (5.991, 2, 0.050),
                        (7.815, 3, 0.050), (9.210, 2, 0.010),
                        (11.345, 3, 0.010)):
        assert abs(gc._chi2_sf(x, df) - want) < 0.005, (x, df)
    assert gc._chi2_sf(0.0, 2) == 1.0 and gc._chi2_sf(5.0, 0) == 1.0


def test_agreement_is_reported_as_weak_evidence():
    """Q fails to reject far more easily than it rejects, and a reader who
    takes 'consistent' as 'the engine is fine' has been misled by a null."""
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        gc.report(_board({"mlb": (247, 0.579, 0.457),
                          "wnba": (140, 0.520, 0.409),
                          "ufc": (90, 0.640, 0.500)}))
    out = buf.getvalue()
    assert "weak evidence" in out
    assert "no reason yet" in out and "nflguard" in out


def test_a_difference_points_at_the_projection_layers_not_the_gate():
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        gc.report(_board({"mlb": (247, 0.579, 0.457),
                          "wnba": (200, 0.520, 0.515),
                          "ufc": (150, 0.640, 0.633)}))
    out = buf.getvalue()
    assert "THEY DIFFER" in out
    assert "per-sport projection" in out
    assert "One engine-wide correction would be wrong here" in out


# --- housekeeping ------------------------------------------------------------
def test_it_writes_nothing():
    src = open(os.path.join(ROOT, "gapcheck.py"), encoding="utf-8").read()
    for forbidden in ("UPDATE ", "INSERT ", "DELETE ", "commit()",
                      "write_text"):
        assert forbidden not in src, forbidden


def test_an_empty_journal_says_so():
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        gc.report(ledger.connect(":memory:"))
    assert "No settled bets on this machine" in buf.getvalue()


def test_the_paper_buckets_can_be_asked_the_same_question():
    """selcheck measured `main` and `loose` 13 points apart in calibration,
    so the buckets are different populations and the question is worth
    asking of each."""
    conn = _board({"mlb": (100, 0.58, 0.46)}, category="loose")
    assert gc.by_sport(gc.load(conn, "loose"))[0]["n"] == 100
    assert gc.load(conn, "main") == []


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
