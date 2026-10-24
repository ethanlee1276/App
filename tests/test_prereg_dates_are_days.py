"""The exclusion rule was a no-op on every football bet in the journal.

FOUND 2026-09-09, off the droplet. A count of NFL prop bets came back
grouped under a month of `2026-W0`, which is not a month — it is the
first seven characters of a SEASON-WEEK LABEL. `bets.date` does not hold
the same kind of thing for every sport: `engine.sources.nflverse` builds
its slate with `date=f"{season}-W{week:02d}"`, the pipeline copies that
onto the result, and `ledger.log_recommendations` writes it straight into
the column. MLB and CFB write ISO days.

WHY THAT IS FATAL HERE SPECIFICALLY. `engine.ledger` has already had to
reason about the mixed formats twice — in `--stranded` and in the record
window — and both times reached the same conclusion: inside its own year
a week label string-sorts ABOVE every ISO day, because "W" sorts above
any digit. For a display window that is the safe direction, and the
ledger says so: a current-season week gets included rather than silently
dropped.

`verdict` is the one place where including is the harmful default. Its
single non-negotiable rule is that bets which existed when the idea did
cannot test it, enforced by `date > registered` — and a week label passes
that comparison unconditionally, whenever the bet was actually taken. So
every NFL bet has been counted as "after" every registration, on a module
whose entire purpose is that they are not. Two live registrations,
`RECEPTIONS_A_NFL` and `TD_EDGE_NFL_XFP`, are NFL tests.

The fix drops what it cannot place and REPORTS the drop. A test blocked
outright by the journal's date format has to be distinguishable from a
quiet week, or the silent zero is just the same failure with its sign
flipped.
"""

import datetime
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import prereg                                   # noqa: E402

WEEK = "2026-W01"          # what the NFL journal actually holds
DAY = "2026-09-20"         # what every other sport holds


def _t(**kw):
    t = dict(prereg.RECEPTIONS_A_NFL, registered="2026-08-27",
             z_threshold=1.96)
    t.update(kw)
    t["hash"] = prereg._terms_hash(t)
    return t


def _rows(n, date, wins=0, sport="nfl", grade="A", market="receptions"):
    return [{"date": date, "sport": sport, "grade": grade, "market": market,
             "odds": -110, "category": "main",
             "status": "won" if i < wins else "lost"} for i in range(n)]


def test_a_week_label_cannot_pass_the_exclusion_rule():
    """THE bug. These 200 bets could have been taken before the
    registration or after it; the journal does not say. Waving them
    through is asking the sample that suggested an idea to confirm it,
    which is the one thing preregistration is for."""
    v = prereg.verdict(_t(), _rows(200, WEEK, wins=20))
    assert v["n"] == 0, v
    assert v["status"] == "collecting"


def test_the_dropped_rows_are_counted_and_said_out_loud():
    """A silent zero is the same failure with the sign flipped: a test
    that can NEVER collect looks exactly like one that has not collected
    yet, and nobody goes looking."""
    v = prereg.verdict(_t(), _rows(200, WEEK, wins=20))
    assert v["undated"] == 200, v
    assert "season-week label" in v["reading"]


def test_the_sentence_survives_onto_a_decided_verdict():
    """A test that reaches its sample on ISO rows while quietly dropping
    a pile of football ones must still say so — the verdict is about a
    narrower population than the reader assumes."""
    rows = _rows(120, DAY, wins=60) + _rows(40, WEEK, wins=4)
    v = prereg.verdict(_t(min_n=80), rows)
    assert v["status"] == "decided", v
    assert v["n"] == 120 and v["undated"] == 40, v
    assert "season-week label" in v["reading"]


def test_a_clean_run_says_nothing_about_dates():
    """The sentence is a report of a real problem, not decoration. With
    every row placeable it must not appear at all."""
    v = prereg.verdict(_t(min_n=80), _rows(120, DAY, wins=60))
    assert v["undated"] == 0
    assert "season-week" not in v["reading"]


def test_parsing_alone_would_have_made_this_worse():
    """The obvious fix is `date.fromisoformat`, and it is a trap. On
    3.11+ that accepts the ISO WEEK form and returns a real date in the
    WRONG YEAR with no error, so a parse-only guard would have converted
    the football journal's labels into December days and buried the bug
    under a plausible number. The shape check is what is load-bearing."""
    assert datetime.date.fromisoformat(WEEK).year == 2025
    assert prereg._is_day(WEEK) is False
    assert prereg._is_day(DAY) is True


def test_a_date_that_is_not_a_day_is_dropped_rather_than_guessed():
    for bad in (WEEK, "2026-W1", "", None, "2026-02-31", "2026-9-9", 5):
        assert prereg._is_day(bad) is False, bad


def test_an_iso_day_still_counts_exactly_as_it_did():
    """The other sports must be untouched. This is a fix to what the rule
    reads, not to what it decides."""
    v = prereg.verdict(_t(min_n=80), _rows(120, DAY, wins=60))
    assert v["n"] == 120 and v["status"] == "decided"
    # And the registration boundary still bites on real days.
    assert prereg.verdict(_t(), _rows(200, "2026-08-01", wins=20))["n"] == 0
    assert prereg.verdict(_t(), _rows(200, "2026-08-27", wins=20))["n"] == 0


def test_the_week_label_is_really_what_the_journal_writes():
    """Anchor the claim in the code rather than in a reading of one
    droplet dump. If any link in this chain changes, the comment above is
    a story about something that no longer happens."""
    import inspect
    from engine import ledger, pipeline
    from engine.sources import nflverse
    assert 'date=f"{season}-W{week:02d}"' in inspect.getsource(nflverse)
    assert '"date": slate.date,' in inspect.getsource(pipeline)
    assert 'date = result.get("date", "")' in inspect.getsource(
        ledger.log_recommendations)


def test_the_two_live_nfl_registrations_are_the_ones_this_was_hiding_from():
    """Not decoration: these are registered and collecting right now, and
    both are NFL, which is why the no-op mattered rather than being a
    curiosity."""
    for t in (prereg.RECEPTIONS_A_NFL, prereg.TD_EDGE_NFL_XFP):
        assert t["sport"] == "nfl", t["id"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
