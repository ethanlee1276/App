"""One bad feed froze the whole site for three hours. Executed, not read.

Ethan, 2026-09-03: *"All pages keep going stale. It causes all the live
games and bets to freeze as well. it was stale almost 3 hours till just
now."*

`refresh_all` rebuilds thirteen boards in sequence. Every `refresh_*`
already handles its OWN build failing — a subprocess that dies returns
False and the board keeps its last good copy, which is why a broken
build shows up as one stale board and not thirteen. What nothing caught
was an exception RAISED around one of those calls: a helper reading a
board that will not parse, a schedule lookup against a feed that has
gone away, anything before or after the subprocess.

One of those and the function unwinds. Every board AFTER the one that
raised never runs. The background refresher catches it, prints a line,
sleeps, and tries again with the same input — so a fault that lasts
three hours keeps the WHOLE site frozen for three hours, and then
everything comes back at once when it clears. That is the shape of the
report, down to "till just now".

AND NFL IS FIRST IN THE ORDER, which is the worst possible place for it:
the sport he ranks first, with everything else downstream.

THE LIVE GAMES FREEZE FOR THE SAME REASON, one layer up, and
tests/test_cfb_silent_saturday.py already wrote it down: `LIVE_FAST` is
MLB-only, so every other sport reads its live games out of the model
board. No rebuild means no picks AND no scores.

WHY THIS FILE RUNS refresh_all INSTEAD OF READING IT. "Is there a
try/except in the file" is not the question — the question is whether
board eleven still rebuilds when board one raises, and only running it
answers that. The stubs stand in for the builds; the sequencing under
test is this function's own.

Run directly: `python3 tests/test_refresh_cascade.py`
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import launch                                                # noqa: E402

BOARDS = ("nfl", "cfb", "mlb", "nba", "wnba", "ufc",
          "predmarkets", "memes", "fantasy")
TAIL = ("refresh_sport_rosters", "refresh_injuries", "refresh_news",
        "refresh_standings", "_arbitrate_parlays", "_journal_parlays",
        "_seal_forecasts", "_run_futures", "_publish_feed")


def _cycle(raisers=()):
    """Run one refresh_all with every step stubbed. Returns what ran.

    Restores every name afterwards: this mutates module globals, and a
    file that leaves `launch.refresh_nfl` stubbed would hand the next
    test a build that never happens."""
    ran, saved = [], {}

    def stub(name, boom):
        def f(quiet=False, *a, **k):
            ran.append(name)
            if boom:
                raise RuntimeError(f"{name} upstream feed timed out")
            return True
        return f

    names = [(b, f"refresh_{b}") for b in BOARDS] + [(t, t) for t in TAIL]
    for label, attr in names:
        saved[attr] = getattr(launch, attr)
        setattr(launch, attr, stub(label, label in raisers))
    # The frozen-board warning reads real files and prints; it is not
    # what is under test here.
    saved["_warn_if_frozen"] = launch._warn_if_frozen
    launch._warn_if_frozen = lambda *a, **k: None
    try:
        launch.refresh_all(quiet=True)
    finally:
        for attr, fn in saved.items():
            setattr(launch, attr, fn)
    return ran


# --- the report ------------------------------------------------------------
def test_a_board_that_raises_does_not_take_the_other_twelve_with_it():
    """THE BUG. NFL raises the way a feed helper does, and every board
    after it must still rebuild."""
    ran = _cycle(raisers={"nfl"})
    missed = [b for b in BOARDS if b not in ran]
    assert missed == [], f"boards that never rebuilt after NFL raised: {missed}"
    assert all(t in ran for t in TAIL), \
        f"the tail steps were skipped: {[t for t in TAIL if t not in ran]}"


def test_two_failures_in_one_cycle_are_both_contained():
    """A fault that hits more than one feed must not be the one case
    that still cascades."""
    ran = _cycle(raisers={"nfl", "mlb"})
    assert [b for b in BOARDS if b not in ran] == []


def test_a_tail_step_that_raises_does_not_cost_the_feed():
    """The tail is sequenced last because it reads what the boards
    wrote, but a failure there must not eat the steps after it either."""
    ran = _cycle(raisers={"_arbitrate_parlays"})
    assert "_publish_feed" in ran, "the live feed stopped publishing"
    assert "_run_futures" in ran


def test_the_failure_is_recorded_where_the_box_can_be_asked():
    """A raise used to leave one line in a log nobody tails. It is now
    on the board's own record — the same shape a failed BUILD leaves, so
    `--boards` cannot tell the two apart by accident — and in the step
    ledger the heartbeat publishes."""
    _cycle(raisers={"nfl"})
    assert "nfl" in launch._STEP_FAIL, "nothing recorded which step failed"
    assert "RuntimeError" in launch._STEP_FAIL["nfl"], launch._STEP_FAIL
    rec = launch._BOARD_RUNS.get("nfl") or {}
    assert rec.get("ok") is False, rec
    assert "note" in rec, "the board is marked failed with no reason"


def test_a_healthy_cycle_records_no_failure():
    """The ledger describes the LAST cycle, so a fault that has cleared
    must not still be shown — that would be the mirror of the bug, a
    site reporting broken while it works."""
    _cycle(raisers={"nfl"})
    assert launch._STEP_FAIL
    _cycle()
    assert launch._STEP_FAIL == {}, \
        f"a recovered cycle still reports failures: {launch._STEP_FAIL}"


def test_every_board_still_rebuilds_when_nothing_raises():
    ran = _cycle()
    assert [b for b in BOARDS if b not in ran] == []


# --- the shape the fix depends on ------------------------------------------
def _refresh_all_block():
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    block = src[src.index("def refresh_all("):]
    return block[:block.index("\n\ndef ")]


def test_every_step_is_isolated():
    """A step added later without the wrapper is the bug returning, and
    it would look exactly like working code."""
    block = _refresh_all_block()
    for b in BOARDS:
        assert f'_isolated("{b}")' in block, f"{b} is not isolated"
    for t in ("rosters", "injuries", "news", "standings", "parlays",
              "parlay-journal", "forecast-seal", "futures", "feed"):
        assert f'_isolated("{t}"' in block, f"{t} is not isolated"


def test_the_call_sites_stay_literal():
    """Held from tests/test_cfb_silent_saturday.py, which explains why:
    two other files grep launch.py for the literal call to prove a
    refresher is not defined-and-never-called, and an indirection
    through globals() would pass here while defeating them."""
    block = _refresh_all_block()
    for b in BOARDS:
        assert f"refresh_{b}(quiet=quiet)" in block, b
        assert f'_note_board("{b}"' in block, b
    assert "globals()" not in block


def test_the_heartbeat_carries_the_failed_step():
    """"Why is the whole site three hours old" has to be answerable off
    the box without a journal dig."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    i = src.index("def _write_heartbeat(")
    body = src[i:src.index("\ndef ", i + 10)]
    assert '"step_fail"' in body, \
        "the heartbeat does not say which step failed"


if __name__ == "__main__":
    fails = ran_n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran_n += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{ran_n} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
