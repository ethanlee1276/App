"""`--boards`: the screen built to answer "why is the site stale".

Two findings from 2026-09-08, both the same shape — the answer was
already recorded and the reader never asked for it.

Ethan pasted a `--boards` run showing the last cycle's time as `nfl 99s,
cfb 16s` and nothing at all for MLB, NBA or WNBA, then: "chase it".

  1. THE SCREEN NEVER PRINTED `step_fail`. The heartbeat has carried it
     since the three-hour freeze of 2026-09-03, and its own comment says
     it exists because a raise "left nothing behind but one line in a log
     nobody was tailing". Leaving it off this screen kept it exactly that
     far out of reach: the one tool built to answer "why is the site
     stale" was not reading the field written to answer it. Same shape as
     reading the paywalled copy of a board, and as an `odds_status`
     filtered down to the keys somebody thought to name.

  2. `_STEP_S` WAS NEVER CLEARED. It is written per step and read under
     the heading "where the last cycle's time went" — so a cycle that
     stopped at CFB still reported MLB's seconds from whichever earlier
     cycle last reached it, and the total was a sum across cycles. The
     board records beside it carry their own timestamps and can stand
     alone; a bare duration cannot.

The clear belongs to the CYCLE, not to `refresh_all`: maintenance,
autosettle and doctor are timed before the boards start, and a clear
inside `refresh_all` would erase all three every cycle — losing exactly
the "on fitter days those chores ARE the long cycle" case they were
added to measure.
"""

import contextlib
import io
import json
import os
import pathlib
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import launch                                                # noqa: E402


def _run(beat=None):
    """Stand up a tree holding one heartbeat, run --boards, return output."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    (tmp / "web" / "data").mkdir(parents=True)
    if beat is not None:
        (tmp / "web" / "data" / "heartbeat.json").write_text(json.dumps(beat))
    old = launch.ROOT
    launch.ROOT = tmp
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            launch.show_boards()
        return buf.getvalue()
    finally:
        launch.ROOT = old


def _sweep_with_every_step_stubbed():
    """Run refresh_all with each of its steps replaced by a no-op.

    The house rule is that the suite must not read the box it runs on,
    and every step in the sweep builds a board or pulls a feed. The
    coverage check below is the guard on this stub list: a step added to
    the sweep and not stubbed here would reach the network, so the test
    fails naming it rather than quietly going online."""
    names = {n for n in dir(launch)
             if (n.startswith("refresh_") and n != "refresh_all")
             or n in ("_arbitrate_parlays", "_journal_parlays",
                      "_seal_forecasts", "_run_futures", "_publish_feed",
                      "_note_board", "_warn_if_frozen")}
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    sweep = src.split("\ndef refresh_all", 1)[1].split("\ndef ", 1)[0]
    called = set(re.findall(r"(\w+)\(quiet=quiet\)", sweep))
    assert called <= names, f"unstubbed step(s) would run for real: {called - names}"
    saved = {n: getattr(launch, n) for n in names}
    for n in names:
        setattr(launch, n, lambda *a, **k: True)
    try:
        launch.refresh_all(quiet=True)
    finally:
        for n, v in saved.items():
            setattr(launch, n, v)


def _beat(**kw):
    base = {"at": "2026-09-08T19:29:51", "at_epoch": 1789000000,
            "interval_s": 300,
            "boards": {"nfl": {"ok": True, "at": "2026-09-08T19:28:00"},
                       "cfb": {"ok": True, "at": "2026-09-08T19:29:00"}},
            "step_s": {"nfl": 99.0, "cfb": 16.0},
            "step_fail": {}}
    base.update(kw)
    return base


# ---------------------------------------------------------------- step_fail

def test_a_step_that_raised_is_named_on_the_screen():
    """The whole finding. `step_fail` has been written every cycle since
    2026-09-03 and was never displayed anywhere, so the answer to "why is
    the whole site three hours old" sat in heartbeat.json unread."""
    out = _run(_beat(step_fail={"mlb": "KeyError: 'home'"}))
    assert "mlb" in out, out
    assert "KeyError: 'home'" in out, out


def test_it_says_the_sweep_continued_so_a_raise_is_not_read_as_an_outage():
    """`_isolated` contains a failure to its own step — the rest of the
    boards do rebuild. A screen that named the raise without saying that
    would turn one dead board into a reported site-wide outage."""
    out = _run(_beat(step_fail={"mlb": "KeyError: 'home'"}))
    assert "isolated" in out, out
    assert "the rest of the sweep continued" in out, out


def test_every_step_that_raised_is_listed_not_just_the_first():
    """Two boards failing for two different reasons is two fixes. A
    screen that printed only one of them would send the reader back for
    a second paste to find the other."""
    out = _run(_beat(step_fail={"mlb": "KeyError: 'home'",
                                "wnba": "TimeoutError: feed"}))
    assert "KeyError: 'home'" in out, out
    assert "TimeoutError: feed" in out, out
    assert "2 step(s) raised" in out, out


def test_a_clean_cycle_says_nothing_about_failures():
    """The screen is read every day. A permanent empty "failures:"
    heading is noise, and noise is how a real one gets skimmed past."""
    every = {n: {"ok": True, "at": "2026-09-08T19:29:00"}
             for n in launch.BOARD_FILES}
    out = _run(_beat(boards=every))
    assert "raised last cycle" not in out, out
    assert "no record at all" not in out, out


# ------------------------------------------------- nothing raised, yet short

def test_boards_with_no_record_at_all_are_named_when_nothing_raised():
    """Ethan's actual paste: NFL and CFB timed, MLB/NBA/WNBA absent, and
    `step_fail` empty. Silence there reads as "all well", which is the
    one thing it is not."""
    out = _run(_beat())
    assert "no record at all" in out, out
    for name in ("mlb", "nba", "wnba"):
        assert name in out, out


def test_a_sweep_still_in_flight_is_not_reported_as_one_that_stopped():
    """Ethan's paste, explained. `_BUILD_LOCK` makes a cycle SKIP the
    sweep when a build is already running, and the skipped cycle still
    writes a heartbeat — carrying the boards the in-progress build had
    reached so far. NFL and CFB timed with nothing after them is what a
    startup build eleven boards from done looks like, and it is also
    exactly what a loop dying after CFB looks like."""
    out = _run(_beat(warming=True, swept="skipped — a build was already "
                                         "running"))
    assert "IN FLIGHT" in out, out
    assert "not one that stopped" in out, out


def test_a_skipped_cycle_says_the_timings_belong_to_an_earlier_sweep():
    """Without this the reader takes `step_s` as this cycle's, which is
    the whole reason the paste read as a dying loop."""
    out = _run(_beat(swept="skipped — a build was already running"))
    assert "skipped" in out, out
    assert "EARLIER sweep" in out, out


def test_a_cycle_that_did_sweep_sends_the_reader_to_the_sport_not_the_loop():
    """The third reading, and the only one where the loop is innocent
    and the board is genuinely absent: the sweep ran, the step did not
    raise, so the sport refused itself — a budget, a season window, an
    empty slate. Pointing that reader at the refresher wastes the hunt."""
    out = _run(_beat(swept="ran"))
    assert "did sweep" in out, out
    assert "the sport's own gate" in out, out


def test_the_screen_does_not_guess_when_the_heartbeat_can_say():
    """The first cut of this message offered two possibilities and left
    the reader to pick between them. The box knew which it was."""
    flight = _run(_beat(warming=True, swept="skipped — a build was "
                                            "already running"))
    ran = _run(_beat(swept="ran"))
    assert flight != ran
    assert "the sport's own gate" not in flight, flight
    assert "IN FLIGHT" not in ran, ran


def test_the_cycle_publishes_whether_it_swept_at_all():
    """The field the three readings above are decided on. A skipped
    cycle wrote a heartbeat indistinguishable from a sweeping one — same
    shape, same fields, `boards` and `step_s` describing a build that had
    not finished."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    cycle = src.split("def _background_refresher", 1)[1].split("\ndef ", 1)[0]
    assert "_write_heartbeat(interval, swept=_swept)" in cycle, cycle[-400:]
    assert '_swept = "ran"' in cycle
    assert "_swept = \"skipped" in cycle
    beat = src.split("def _write_heartbeat", 1)[1].split("\ndef ", 1)[0]
    assert '"swept": swept' in beat
    assert '"warming": _WARMING' in beat


def test_the_skip_branch_is_still_a_skip_and_not_a_queue():
    """The behaviour under the new field is unchanged and must stay
    that way: the loop runs on a timer, so the next tick beats piling up
    behind a build already writing the same files."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    cycle = src.split("def _background_refresher", 1)[1].split("\ndef ", 1)[0]
    assert "_BUILD_LOCK.acquire(blocking=False)" in cycle


def test_the_no_record_branch_yields_to_an_actual_failure():
    """A cycle that raised at MLB also leaves NBA and WNBA without a
    record. Printing both readings would let the reader take the weaker
    one — "it just didn't get there" — over the traceback that says why."""
    out = _run(_beat(step_fail={"mlb": "KeyError: 'home'"}))
    assert "KeyError: 'home'" in out, out
    assert "no record at all" not in out, out


def test_a_heartbeat_with_no_boards_key_makes_no_claim_about_boards():
    """An old heartbeat, or one written before the first cycle finished,
    knows nothing about which boards ran. Reporting all five as missing
    from that would be inventing a finding out of an absent field."""
    out = _run(_beat(boards={}, step_s={}))
    assert "no record at all" not in out, out


# --------------------------------------------------------- the timing clear

def test_the_step_clock_is_cleared_once_per_cycle_by_the_cycle_owner():
    """Not by refresh_all. maintenance, autosettle and doctor are timed
    before the boards start; a clear inside refresh_all would wipe all
    three every cycle."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    cycle = src.split("def _background_refresher", 1)[1].split("\ndef ", 1)[0]
    sweep = src.split("\ndef refresh_all", 1)[1].split("\ndef ", 1)[0]
    assert "_STEP_S.clear()" in cycle, "the cycle owner must clear the clock"
    assert "_STEP_S.clear()" not in sweep, \
        "refresh_all clearing it erases maintenance/autosettle/doctor"


def test_the_clear_runs_before_the_first_step_is_timed():
    """After any of them and the clear eats the step it follows — the
    screen would then report a cycle permanently missing its own
    maintenance pass."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    cycle = src.split("def _background_refresher", 1)[1].split("\ndef ", 1)[0]
    assert cycle.index("_STEP_S.clear()") < cycle.index('_STEP_S["maintenance"]')


def test_a_sweep_does_not_erase_the_chores_timed_before_it():
    """The behavioural half, and the regression that sent the clear here
    in the first place: maintenance, autosettle and doctor are timed
    before the boards start. A sweep that cleared the clock would drop
    all three every cycle — and the case they were added to catch is
    precisely the day those chores ARE the long cycle."""
    launch._STEP_S.clear()
    launch._STEP_S["maintenance"] = 41.0
    _sweep_with_every_step_stubbed()
    assert launch._STEP_S.get("maintenance") == 41.0, launch._STEP_S
    assert "nfl" in launch._STEP_S, launch._STEP_S
    launch._STEP_S.clear()


def test_step_fail_is_still_cleared_by_the_sweep_that_owns_it():
    """Unchanged, and load-bearing: `_STEP_FAIL` describes refresh_all's
    steps only, so a stale entry would name a board that has already
    recovered — the screen's new failure block would then be wrong on
    every quiet cycle after a bad one."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    sweep = src.split("\ndef refresh_all", 1)[1].split("\ndef ", 1)[0]
    assert "_STEP_FAIL.clear()" in sweep


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
