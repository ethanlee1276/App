"""Does the over-claim depend on the PRICE? Measured, applied to nothing.

Ethan, 2026-09-02, reading his own book: "ok so what should we do then,
can we dive deeper into that and fix it" — about the +200-and-longer
band landing 12.5% against a claimed 27.9%, and the smallest-stake
quartile returning -15.2%.

THE TRAP THIS AVOIDS, and it is the reason the module reports rather
than corrects. The raw touchdown model — the plus-money market — does
not over-claim at all. Across 22,099 graded player-weeks it claims .155
and lands .200, and EVERY probability band lands above its claim, all
well outside two standard errors. So "the model is over-confident on
long shots" is false about the surface, and raising those probabilities
to fix the surface would make the board worse.

What over-claims is the SELECTED subset, because selection is what
turns an under-claiming surface into an over-claiming board: it keeps
the rows where model minus market is largest, which is exactly where
the model's error is most positive. That is the winner's curse
`engine/selectionfit.py` was written for, now visible from both ends —
and its own docstring names the weakness the journal has now exposed:
"a single pooled number applied to every price is a blunt instrument."

So this pins the diagnostic, not a correction. Sixteen bets in the band
that matters cannot fit a parameter, and a price-dependent haircut
chosen on the sample that suggested it is precisely what the module's
walk-forward holdout exists to refuse.

Run directly: `python3 tests/test_haircut_bands.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine import ledger, selectionfit as S                  # noqa: E402


def _book(rows):
    """A journal of settled bets: (odds, claimed, won) each."""
    conn = ledger.connect(":memory:")
    for i, (odds, prob, won) in enumerate(rows):
        conn.execute(
            "INSERT INTO bets (ts, sport, date, player, market, side, line, "
            "book, odds, hit_prob, stake_units, stake_dollars, status, "
            "category) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'main')",
            (f"2026-08-{10 + (i % 18):02d}T12:00:00", "nfl", "2026-W01",
             f"P{i}", "rec_yds", "OVER", 45.5, "DK", odds, prob, 1.0, 10.0,
             "won" if won else "lost"))
    conn.commit()
    return conn


# --- the bands themselves --------------------------------------------------
def test_the_bands_match_the_other_tool_that_reports_them():
    """`stakecheck.py` prints the same four buckets. Two tools that
    disagree about which bets are in which band produce two answers to
    one question, and the reader has no way to tell which is which."""
    labels = [b[0] for b in S.PRICE_BANDS]
    assert labels == ["shorter than +100", "+100 to +119",
                      "+120 to +199", "+200 and longer"]
    src = open(os.path.join(ROOT, "stakecheck.py"), encoding="utf-8").read()
    for label in labels:
        assert label in src, label


def test_a_price_lands_in_exactly_one_band():
    seen = {}
    for odds in (-500, -110, -100, 100, 119, 120, 199, 200, 5000):
        got = S._band_of(odds)
        assert got is not None, odds
        seen.setdefault(got, []).append(odds)
    assert S._band_of(-110) == "shorter than +100"
    assert S._band_of(100) == "+100 to +119"
    assert S._band_of(120) == "+120 to +199"
    assert S._band_of(200) == "+200 and longer"
    assert S._band_of(None) is None and S._band_of("x") is None


def test_the_shape_the_droplet_showed_is_reported_band_by_band():
    """A book that is honest at short prices and badly over-claiming at
    long ones — the shape one pooled shift cannot fit."""
    rows = []
    rows += [(-130, 0.60, i < 60) for i in range(100)]      # honest
    rows += [(300, 0.30, i < 10) for i in range(100)]       # over-claims
    conn = _book(rows)
    got = S.bands(conn)
    conn.close()
    by = {b["band"]: b for b in got["bands"]}
    short = by["shorter than +100"]
    long_ = by["+200 and longer"]
    assert short["n"] == 100 and long_["n"] == 100
    assert abs(short["gap"]) < 0.02, short
    assert long_["gap"] < -0.15, long_
    assert long_["real"] is True and "over-claiming" in \
        [l for l in S.band_lines(got) if "+200" in l][0]


def test_a_band_under_the_floor_says_collecting_rather_than_guessing():
    """Sixteen bets is the situation that prompted all this, and the
    honest output on sixteen bets is the count."""
    conn = _book([(300, 0.30, i < 2) for i in range(16)])
    got = S.bands(conn)
    conn.close()
    band = [b for b in got["bands"] if b["band"] == "+200 and longer"][0]
    assert band["n"] == 16 and band["enough"] is False and band["real"] is False
    line = [l for l in S.band_lines(got) if "+200" in l][0]
    assert f"collecting: 16 of {S.MIN_SETTLED}" in line


def test_a_noise_sized_gap_is_called_noise():
    conn = _book([(-130, 0.55, i % 2 == 0) for i in range(120)])
    got = S.bands(conn)
    conn.close()
    band = [b for b in got["bands"] if b["band"] == "shorter than +100"][0]
    assert band["enough"] is True
    line = [l for l in S.band_lines(got) if "shorter" in l][0]
    assert "noise" in line or "over-claiming" in line


def test_an_under_claiming_band_is_never_acted_on():
    """The same rule the pooled fit keeps: we do not raise stakes on a
    finding that we are too pessimistic."""
    conn = _book([(300, 0.20, i < 60) for i in range(120)])
    got = S.bands(conn)
    conn.close()
    line = [l for l in S.band_lines(got) if "+200" in l][0]
    assert "under-claiming — never acted on" in line


# --- it corrects nothing ---------------------------------------------------
def test_the_band_report_applies_nothing():
    """The load-bearing one. A band correction fitted on the sample that
    suggested it is what `_holdout` exists to refuse, and sixteen bets
    cannot fit a parameter."""
    src = open(os.path.join(ROOT, "engine", "selectionfit.py"),
               encoding="utf-8").read()
    at = src.index("def bands(")
    body = src[at:src.index("\ndef band_lines(", at)]
    for banned in ("apply_haircut", "shift_for", "_save", "refresh("):
        assert banned not in body, banned
    assert "report only" in body
    # `shift_for` is what the board actually calls; it must not have
    # grown a band argument behind this measurement's back.
    import inspect
    assert list(inspect.signature(S.shift_for).parameters) == ["sport", "path"]


def test_the_report_reaches_a_human_on_both_paths():
    """A measurement nobody can read is not a measurement — the same
    rule that got `likely_report` written."""
    launch = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    assert "sf.band_lines(got)" in launch
    maint = open(os.path.join(ROOT, "engine", "maintenance.py"),
                 encoding="utf-8").read()
    assert "selectionfit.band_lines(" in maint


def test_it_survives_a_journal_with_nothing_in_it():
    conn = ledger.connect(":memory:")
    got = S.bands(conn)
    conn.close()
    assert got["n"] == 0 and len(got["bands"]) == len(S.PRICE_BANDS)
    assert all(b["n"] == 0 for b in got["bands"])
    assert S.band_lines(got)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
