"""A price nobody can date cannot be told apart from a wrong one.

Ethan, 2026-09-03: *"The lines on the most likely best bet page ... are
completely wrong so we are giving bad bets. A lot of the money lines and
shit are wrong."* — in the same message as *"All pages keep going stale
... it was stale almost 3 hours till just now."*

THE ARITHMETIC WAS NOT THE PROBLEM, and that was checked before this
file was written. Driven end to end — `price_moneyline` →
`moneyline_to_dict` → `likely.from_game_bet`, and the college route
through `cfb.pipeline.evaluate_play` → `cfb_build.to_game_bet` — the
side, the price and the probability agree with the book on every case,
including the flip to the likely side that turns a +190 dog card into
the favourite at its own price. Spreads keep their number and negate it
only when they flip; totals keep theirs and swap Over for Under.

What the board could not say is HOW OLD the price beside a pick is. On a
board that had not rebuilt in three hours every one of them was three
hours stale, and a stale price at a sportsbook looks exactly like a
wrong one.

MLB has stamped `odds_status.priced_at` since the pacing telemetry went
in, and the page already draws it — `oddsClockHTML` renders "last pulled
3:32 PM yesterday" off that field. NFL stamped only `at`, which is the
BUILD's clock and reads like the price's when it sits beside a price,
and the two are hours apart whenever a cycle rebuilds on `--cached-odds`
without paying for a pull. College published no `odds_status` at all, so
the clock had nothing to draw at all — and college is the board he named.

Run directly: `python3 tests/test_price_age.py`
"""

import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _src(name):
    return open(os.path.join(ROOT, name), encoding="utf-8").read()


def _stamped(ts, board=None):
    """Run cfb_build._write against a budget state and return odds_status.

    `ts` rather than `sport_ts`: a class body looks names up in its own
    namespace and then the module's, skipping the enclosing function, so
    a parameter sharing a name with a method defined below it is not
    visible here at all.
    """
    import cfb_build
    from engine import oddsbudget

    class Fake:
        last_refresh_ts = ts
        def sport_ts(self, s):
            return ts if s == "cfb" else 0.0

    real = oddsbudget.load
    oddsbudget.load = lambda *a, **k: Fake()
    try:
        out = dict(board or {"sport": "cfb", "games": [],
                             "recommendations": [], "game_bets": []})
        with tempfile.TemporaryDirectory() as td:
            cfb_build._write(out, os.path.join(td, "web", "data", "cfb.json"))
        return out.get("odds_status") or {}
    finally:
        oddsbudget.load = real


# --- college, the board he named -------------------------------------------
def test_the_college_board_says_when_its_prices_were_pulled():
    """It published no odds_status at all, so the page's odds clock had
    nothing to read and every college price was undated."""
    three_h = time.time() - 3 * 3600
    got = _stamped(three_h)
    assert "priced_at" in got, "the college board still cannot date its prices"
    assert abs(got["priced_at"] - three_h) < 2, got


def test_it_is_stamped_on_every_path_out():
    """`_write` is the one door every college board leaves by — six call
    sites, several of them early returns. The furniture that lived inside
    `if args.odds or args.cached_odds:` is exactly what went missing from
    every cycle that did not spend, and that comment is already in
    cfb_build.py. This one cannot be reached by a path that skips it."""
    src = _src("cfb_build.py")
    body = src[src.index("def _write("):]
    assert "priced_at" in body, "the stamp left the single writer"
    # and no other exit publishes the board behind its back
    assert body.count("gate.publish(") == 1


def test_an_unreadable_budget_costs_a_note_and_never_the_board():
    """Freshness furniture must not be able to fail a build."""
    import cfb_build
    from engine import oddsbudget
    real = oddsbudget.load

    def boom(*a, **k):
        raise RuntimeError("budget state unreadable")

    oddsbudget.load = boom
    try:
        out = {"sport": "cfb", "games": [], "recommendations": []}
        with tempfile.TemporaryDirectory() as td:
            cfb_build._write(out, os.path.join(td, "web", "data", "cfb.json"))
    finally:
        oddsbudget.load = real


def test_never_pulled_is_absent_rather_than_invented():
    """A box that has never paid for a college price must not be given a
    time — the clock draws nothing, which is the honest answer, and a
    fabricated "pulled just now" beside a stale line is the bug wearing a
    freshness badge."""
    got = _stamped(0.0)
    assert got.get("priced_at") is None, got


# --- the NFL half ----------------------------------------------------------
def test_the_nfl_board_stamps_the_price_clock_beside_the_build_clock():
    """`at` is when the BUILD ran. With `--cached-odds` — which the
    launcher passes deliberately to keep the last paid prices rather than
    overwrite them with proxies — the two are hours apart, and only one
    of them answers "is this line still live"."""
    src = _src("nfl_build.py")
    i = src.index('odds_status["at"] =')
    seg = src[i:i + 1200]
    assert 'odds_status["priced_at"]' in seg, \
        "the NFL board still dates its prices by the build's clock alone"
    assert 'sport_ts("nfl")' in seg, "the stamp is not read per sport"


def test_all_three_football_and_baseball_boards_agree_on_the_field():
    """One name, one source, one unit (epoch seconds) — the page reads a
    single field and a second spelling would be a second bug."""
    for f in ("mlb_build.py", "nfl_build.py", "cfb_build.py"):
        assert '"priced_at"' in _src(f), f"{f} does not stamp priced_at"
    for f in ("mlb_build.py", "nfl_build.py", "cfb_build.py"):
        assert "oddsbudget" in _src(f), f"{f} reads it from somewhere else"


def test_the_page_draws_it_and_needs_no_change():
    """The renderer was already there and already correct; it was being
    handed nothing on two of the three boards."""
    app = _src(os.path.join("web", "js", "app.js"))
    i = app.index("function oddsClockHTML(")
    body = app[i:app.index("\nfunction ", i + 10)]
    assert "os.priced_at" in body, "the odds clock no longer reads the field"
    assert "last pulled" in body


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
