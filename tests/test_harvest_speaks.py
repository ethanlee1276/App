"""A harvest that broke and a harvest that had a quiet day look different.

Ethan, 2026-09-15, approving work on the Pinnacle closes: "is there
anything else you can work on for this that you don't need the droplet
for." This.

TWO SILENCES WERE STACKED HERE. `lineledger.record` returned 0 when the
write threw and 0 when there was simply nothing to write — opposite
facts, one number — and then nfl_build and mlb_build each wrapped the
call in `except Exception: pass` and printed nothing at all. A harvest
broken on the day it shipped would have read as a quiet Tuesday for as
long as nobody went looking. That is the same failure shape as the
rankings section that returned "" for a month and the Live tab that
could not tell "nothing on" from "the feed failed", and it is the one
this codebase keeps re-learning.

THE SECOND HALF IS THE BACKTEST'S DIAGNOSIS, and it guards money rather
than tidiness. `backtest_sharp_anchor` printed "harvest Pinnacle closes
first" on every empty result — whether the sharp rows were missing, the
soft rows were missing, or both were on disk and the keys never joined.
Two of those three are free to fix and the advice it gave was to go buy
a historical harvest. `test_the_report_never_sends_us_shopping_for_data_we_have`
is the assertion that costs real dollars when it regresses.

Run directly: `python3 tests/test_harvest_speaks.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import lineledger as L                            # noqa: E402
from engine.gamebacktest import SharpAnchorReport             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _Game:
    """A slate game carrying both books' prices."""

    def __init__(self, **kw):
        self.home, self.away, self.date = "KC", "DEN", "2026-09-15"
        self.total = self.spread = None
        self.home_ml = self.away_ml = 0
        self.sharp_home_ml = self.sharp_away_ml = 0
        self.sharp_total = self.sharp_spread = None
        for k, v in kw.items():
            setattr(self, k, v)


class _Conn:
    """Enough of a connection for `db.upsert_odds_history` to count rows."""

    def __init__(self, fail=False):
        self.fail, self.rows = fail, []

    def executemany(self, _sql, rows):
        if self.fail:
            raise RuntimeError("database is locked")
        self.rows.extend(rows)
        return self

    def execute(self, *_a, **_k):
        if self.fail:
            raise RuntimeError("database is locked")
        return self

    def commit(self):
        if self.fail:
            raise RuntimeError("database is locked")

    def __getattr__(self, _n):
        return lambda *a, **k: self


# --- the harvest says which of the two silences it is -------------------------
def test_a_write_that_threw_says_FAILED_and_names_the_error():
    """The case that could hide forever. It must be loud and it must
    carry the exception, because "it failed" without the reason is the
    same dead end one level up."""
    note = L.record_note(_Conn(fail=True), "nfl",
                         [_Game(home_ml=-350, away_ml=280)])
    assert "FAILED" in note, note
    assert "database is locked" in note, note


def test_a_quiet_day_says_it_had_nothing_and_does_not_say_FAILED():
    """A slate where no game carried a price is a true zero, and it must
    not read as a fault — a page that cries wolf gets ignored on the day
    the wolf turns up."""
    for games in ([], [_Game()]):
        note = L.record_note(_Conn(), "nfl", games)
        assert "FAILED" not in note, note
        assert "nothing to store" in note, note


def test_a_working_harvest_counts_the_sharp_book_separately():
    """Rows stored is NOT the number that matters. The whole sharp-anchor
    measurement is Pinnacle's de-vig against the shopped field, so a
    build writing plenty of rows and none of them sharp is a build that
    looks healthy and collects nothing we can measure with."""
    conn = _Conn()
    note = L.record_note(conn, "nfl", [_Game(home_ml=-350, away_ml=280,
                                             sharp_home_ml=-340,
                                             sharp_away_ml=290)])
    assert "FAILED" not in note, note
    assert L.SHARP_BOOK in note, note
    assert "4 row(s)" in note, note          # 2 shopped + 2 sharp
    assert "2 shopped" in note and f"2 from {L.SHARP_BOOK}" in note, note


def test_a_harvest_with_no_sharp_pair_says_so_in_as_many_words():
    """The exact state that would make the anchor unmeasurable while
    every other number on the build log looked fine."""
    note = L.record_note(_Conn(), "nfl", [_Game(home_ml=-350, away_ml=280)])
    assert "NONE" in note and L.SHARP_BOOK in note, note
    assert "cannot be measured" in note, note


def test_every_build_takes_the_note_and_none_takes_the_bare_count():
    """`record` returns 0 for both silences; only `record_note` can tell
    them apart. A build reverting to the bare call goes quiet again."""
    import re
    for fn in ("nfl_build.py", "cfb_build.py", "mlb_build.py"):
        src = open(os.path.join(ROOT, fn), encoding="utf-8").read()
        # Strip comments so prose about `record` does not count as a call.
        code = "\n".join(ln for ln in src.splitlines()
                         if not ln.lstrip().startswith("#"))
        bare = re.findall(r"lineledger\.record\((?!_note)", code)
        assert not bare, f"{fn} still takes the bare count ({len(bare)})"
        assert "lineledger.record_note(" in code, f"{fn} harvests nothing"


def test_no_build_swallows_the_harvest_without_printing():
    """The outer half of the double silence. `except Exception: pass`
    around the call is what made the inner one survive."""
    for fn in ("nfl_build.py", "cfb_build.py", "mlb_build.py"):
        src = open(os.path.join(ROOT, fn), encoding="utf-8").read()
        i = 0
        while True:
            i = src.find("lineledger.record_note(", i + 1)
            if i < 0:
                break
            after = src[i:i + 500]
            j = after.find("except Exception")
            assert j >= 0, f"{fn}: the harvest call has no handler"
            tail = after[j:j + 200]
            assert "pass" not in tail.split("\n")[1], \
                f"{fn} swallows its harvest without printing"


# --- the backtest names the cause instead of guessing at it -------------------
def _report(**kw):
    return SharpAnchorReport(sport="nfl", sharp="Pinnacle", games_seen=1424, **kw)


def test_nothing_stored_points_at_the_build_log_not_at_a_purchase():
    d = _report(sharp_rows=0, soft_rows=0).diagnosis()
    assert "NOTHING STORED" in d, d
    assert "line ledger" in d and "record_note" in d, d


def test_a_missing_sharp_pair_is_called_a_parse_bug():
    """The build already asks for this book on every pull. If its pair is
    absent the price is being dropped, not unbought — and buying history
    would paper over the bug while it kept dropping tomorrow's."""
    d = _report(sharp_rows=0, soft_rows=900).diagnosis()
    assert "parse bug" in d, d
    assert "paper over" in d, d


def test_keys_that_never_join_are_called_a_keying_problem():
    """Both books on disk, neither joining — the failure this repo has
    already paid for once (DROPLET_CHECKS, the moneyline doctor)."""
    d = _report(sharp_rows=900, soft_rows=900, matched_sharp=0,
                matched_soft=0, sharp_key="('2026-09-15', 'KC', 'DEN')").diagnosis()
    assert "keying problem" in d, d
    assert "2026-09-15" in d, "the diagnosis shows a real key to eyeball"


def test_one_book_matching_and_not_the_other_asks_which_day_stopped():
    d = _report(sharp_rows=900, soft_rows=900, matched_sharp=800,
                matched_soft=0).diagnosis()
    assert "different times, or one stopped" in d, d
    assert "WHEN_YOU_ARE_HOME" in d, "it names the query that answers it"


def test_the_report_never_sends_us_shopping_for_data_we_have():
    """THE ONE THAT COSTS MONEY WHEN IT REGRESSES. The old report told us
    to buy a historical harvest on every empty result, including the two
    states where the rows were already on disk and free to fix."""
    have_rows = (
        _report(sharp_rows=900, soft_rows=900, matched_sharp=0, matched_soft=0),
        _report(sharp_rows=900, soft_rows=900, matched_sharp=800, matched_soft=0),
        _report(sharp_rows=0, soft_rows=900),
    )
    # THE MARKERS ARE THE COMMAND, NOT THE WORD. A first draft of this
    # test banned "purchase" and flagged the sentence "that is a parse
    # bug, not a missing purchase" — which is the diagnosis REFUSING to
    # send us shopping. What must be absent is the invocation.
    for rep in have_rows:
        text = (rep.diagnosis() + " " + rep.summary()).lower()
        for marker in ("harvest_odds.py", "--budget", "--books pinnacle"):
            assert marker not in text, (marker, rep.diagnosis())

    # And the state where buying really IS the answer still says so.
    empty = _report(sharp_rows=0, soft_rows=0)
    assert "line ledger" in empty.diagnosis(), \
        "an empty store should point at the harvest that is not running"


def test_the_empty_summary_shows_the_funnel_and_not_a_guess():
    rep = _report(sharp_rows=0, soft_rows=12, matched_soft=10)
    out = rep.summary()
    assert "Stored" in out and "Matched" in out, out
    assert "0 Pinnacle game-key(s), 12 shopped" in out, out
    assert "10 found a soft price" in out, out


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
