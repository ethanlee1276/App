"""One command that answers "why is this page empty".

Answering that has taken a different ad-hoc command every time. Over two
days the CFB board needed: a `journalctl` grep, a python one-liner for
`generated_at`, an `ls -l` for WNBA, a curl for the CFBD key, and another
one-liner for the talent layer. Each was written fresh, several were
wrong, and two of them measured something other than what they were read
as —

  * the journalctl grep came back empty and was read as "the refresh is
    not running". The background loop is `refresh_all(quiet=True)`, so a
    SUCCESSFUL refresh prints nothing either. Silence proved nothing.
  * the curl used `cut -d= -f2-` on /etc/qellys/env and returned 401,
    read as "the key is bad". `secrets._read_into_environ` strips
    surrounding quotes and `cut` does not, so the two were sending
    different keys. The app's key was fine — 138 schools.

The facts were on disk the whole time. This prints them together, so the
first question is answered before anyone has to invent a way to ask it.

IT READS FILES, NOT THE RUNNING PROCESS, on purpose: a board frozen
because its build returns without writing looks perfectly healthy from
inside the loop that just "succeeded" at it. Both views are printed, and
the two disagreeing is itself the finding.

Run directly: `python3 tests/test_show_boards.py`
"""

import io
import json
import os
import sys
import tempfile
import time
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())

import launch


def _board(name, payload=None, age_hours=0.0, exists=True):
    path = os.path.join(tempfile.mkdtemp(), f"{name}.json")
    if exists:
        with open(path, "w") as f:
            json.dump(payload if payload is not None else {}, f)
        if age_hours:
            t = time.time() - age_hours * 3600
            os.utime(path, (t, t))
    launch.BOARD_FILES[name] = path
    return name


def _run():
    buf = io.StringIO()
    with redirect_stdout(buf):
        launch.show_boards()
    return buf.getvalue()


# --- it reports the three things a reader needs ---------------------------
def test_it_prints_every_board_it_knows_about():
    out = _run()
    for sport in ("MLB", "NFL", "NBA", "WNBA", "CFB"):
        assert sport in out, sport


def test_a_stale_board_is_flagged_not_just_listed():
    """A number in a column is easy to skim past; the flag is not."""
    _board("stalecfb", {"games": [1]}, age_hours=5)
    assert "STALE" in _run()


def test_a_fresh_board_is_not_flagged():
    name = _board("freshone", {"games": [1, 2]})
    out = [ln for ln in _run().splitlines() if name.upper() in ln]
    assert out and "STALE" not in out[0], out


def test_a_missing_file_says_so_rather_than_reading_as_zero():
    """"0 games" and "there is no board" are different problems."""
    _board("goneboard", exists=False)
    assert "FILE MISSING" in _run()


def test_an_unreadable_board_is_named_not_crashed_on():
    path = os.path.join(tempfile.mkdtemp(), "bad.json")
    with open(path, "w") as f:
        f.write("{not json")
    launch.BOARD_FILES["badboard"] = path
    assert "UNREADABLE" in _run()


def test_it_shows_the_game_and_pick_counts():
    _board("counted", {"games": [1, 2, 3], "recommendations": [1]})
    assert "counted" in [b for b in launch.BOARD_FILES]
    out = _run()
    assert "COUNTE" in out.upper()


# --- the two views, side by side ------------------------------------------
def test_it_reads_the_files_rather_than_the_loops_own_opinion():
    """The whole point. A build that returns without writing reports ok,
    and the board underneath it has not moved."""
    doc = launch.show_boards.__doc__ or ""
    assert "not from the running process" in doc.lower() \
        or "reads FILES" in doc


def test_it_reads_the_loops_view_from_the_heartbeat_file():
    """NOT from `_BOARD_RUNS`. This command is its own process, so the
    server's in-memory record is not in it — the first cut printed
    nothing at all here, silently dropping the half of the output that
    carries the finding. The heartbeat is written every cycle for
    exactly this."""
    import inspect
    src = inspect.getsource(launch.show_boards)
    assert "heartbeat.json" in src
    # Not merely absent as a NAME — the comment explaining why it is not
    # read mentions it, and should. What must not happen is a READ.
    used = [ln for ln in src.splitlines()
            if "_BOARD_RUNS" in ln and not ln.strip().startswith("#")]
    assert not used, used


def test_a_missing_heartbeat_says_so_rather_than_printing_nothing():
    """Absent output reads as "nothing to report", which is the wrong
    conclusion when the loop is dead."""
    assert "cannot say whether the loop is alive" in _run()


def test_a_stale_heartbeat_is_called_out():
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    assert "THE LOOP ITSELF IS NOT TICKING" in src


def test_the_parse_census_shows_when_a_feed_was_read_away():
    """`listed` vs `kept` is how "the feed is down" is told apart from
    "we discarded its games"."""
    _board("censused", {"games": [], "feed": {"listed": 47, "kept": 0}})
    out = _run()
    assert "feed listed 47, kept 0" in out


# --- and it says what to do -----------------------------------------------
def test_it_names_the_usual_cause_of_a_frozen_board():
    out = _run()
    assert "returns without writing" in out
    assert "keeping the" in out


def test_the_college_build_gets_the_same_ceiling_as_the_mlb_one():
    """`_run_build`'s default is 180s, and its own header says the big
    model boards pass their own. MLB learned that when a board too slow
    for three minutes was killed every cycle and froze at its last write
    — which is the shape CFB has been stuck in. This was the last slate
    build still on the small ceiling."""
    import inspect
    src = inspect.getsource(launch.refresh_cfb)
    assert "_run_build(args, timeout=600)" in src


def test_it_is_reachable_from_the_command_line():
    with open(os.path.join(ROOT, "launch.py"), encoding="utf-8") as f:
        src = f.read()
    assert 'if "--boards" in argv:' in src
    assert "show_boards()" in src


# --- which code is serving, beside which code is on disk -------------------
def _heartbeat_root(beat):
    from pathlib import Path
    import launch
    tmp = Path(tempfile.mkdtemp())
    (tmp / "web" / "data").mkdir(parents=True)
    (tmp / "web" / "data" / "heartbeat.json").write_text(json.dumps(beat))
    return tmp


DISK = "f00d123"


def _run_with_root(tmp):
    """show_boards under a repointed ROOT. `_git` is stubbed because the
    tempdir ROOT is not a git checkout — the stub answers the one
    question show_boards asks it (what is on disk) with DISK."""
    import launch
    saved_root, saved_git = launch.ROOT, launch._git
    launch.ROOT = tmp
    launch._git = lambda *a, **k: (True, DISK)
    try:
        return _run()
    finally:
        launch.ROOT, launch._git = saved_root, saved_git


def test_it_prints_the_serving_commit_and_updater_state():
    out = _run_with_root(_heartbeat_root(
        {"at_epoch": time.time(), "at": "now", "boards": {},
         "commit": "abc1234", "auto_update": True}))
    assert "abc1234" in out
    assert "auto-update ON" in out


def test_disk_ahead_of_the_loop_is_called_out_by_name():
    """A pull that landed without a restart is the one state auto-update
    can silently die in — the code is there, and nothing runs it."""
    out = _run_with_root(_heartbeat_root(
        {"at_epoch": time.time(), "at": "now", "boards": {},
         "commit": "abc1234", "auto_update": True}))
    assert "on disk but not running" in out
    assert DISK in out


def test_matching_commits_raise_no_alarm():
    out = _run_with_root(_heartbeat_root(
        {"at_epoch": time.time(), "at": "now", "boards": {},
         "commit": DISK, "auto_update": True}))
    assert "on disk but not running" not in out


def test_updater_off_names_the_consequence():
    out = _run_with_root(_heartbeat_root(
        {"at_epoch": time.time(), "at": "now", "boards": {},
         "commit": DISK, "auto_update": False}))
    assert "manual deploy" in out


# --- the timer's word beats the process's flag -----------------------------
def _timer_root(beat, au):
    tmp = _heartbeat_root(beat)
    (tmp / "data").mkdir()
    (tmp / "data" / "autoupdate.json").write_text(json.dumps(au))
    return tmp


def _live_beat():
    return {"at_epoch": time.time(), "at": "now", "boards": {},
            "commit": DISK, "auto_update": False}


def test_a_healthy_timer_reports_on_with_its_last_check():
    out = _run_with_root(_timer_root(_live_beat(),
        {"at_epoch": time.time() - 120, "ok": True, "note": "up to date"}))
    assert "auto-update ON (timer" in out


def test_a_failing_timer_names_the_reason_on_the_screen():
    """The whole reason the state file exists: the in-process updater
    failed every five minutes for an hour and nothing anywhere said so
    or why."""
    out = _run_with_root(_timer_root(_live_beat(),
        {"at_epoch": time.time() - 120, "ok": False,
         "note": "pull failed: fatal: could not read from remote"}))
    assert "timer FAILING" in out
    assert "could not read from remote" in out


def test_a_timer_that_stopped_running_is_its_own_alarm():
    out = _run_with_root(_timer_root(_live_beat(),
        {"at_epoch": time.time() - 3600, "ok": True, "note": "up to date"}))
    assert "STALLED" in out


def test_no_state_file_falls_back_to_the_process_flag():
    out = _run_with_root(_heartbeat_root(_live_beat()))
    assert "manual deploy" in out



# --- a failed refresh names its reason on the one screen -------------------
def test_a_failed_board_refresh_carries_its_reason():
    """2026-08-31: MLB showed FAILED with nothing else, and the reason —
    the build timing out under a background fitter's CPU load — was
    captured by _run_build, printed to a journal nobody was reading, and
    dropped by the run record. The note now rides the heartbeat."""
    out = _run_with_root(_heartbeat_root(
        {"at_epoch": time.time(), "at": "now",
         "boards": {"mlb": {"ok": False, "at": "2026-08-31T19:00:43",
                            "note": "exit 1: TimeoutExpired after 600s"}},
         "commit": DISK, "auto_update": True}))
    assert "FAILED" in out
    assert "TimeoutExpired after 600s" in out


def test_the_note_is_written_on_failure_and_cleared_on_success():
    import launch
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    at = src.index("def _run_build")
    body = src[at:src.index("\ndef ", at + 10)]
    assert "_LAST_BUILD_NOTE[0] = str(exc)[:240]" in body
    assert '_LAST_BUILD_NOTE[0] = ("" if proc.returncode == 0' in body
    at = src.index("def _note_board")
    body = src[at:src.index("\ndef ", at + 10)]
    assert '_BOARD_RUNS[name]["note"] = _LAST_BUILD_NOTE[0]' in body

def test_every_cycle_step_is_clocked_and_the_bill_is_printed():
    """Ethan, 2026-09-01: "im noticing all the pages are stale 45 mins.
    we gotta stop that issue." Every page's age is the cycle length, the
    cycle is a sequential sum on one core, and nothing measured the
    addends — so the first fix is a ledger: every step laps into
    _STEP_S, the heartbeat publishes it, and --boards prints it worst
    first. A staleness complaint becomes one paste, not a profiling
    session over SSH."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    at = src.index("def refresh_all(")
    body = src[at:src.index("\ndef ", at + 10)]
    # Every _note_board'ed build laps, and so does every tail chore —
    # counted, so a new step added without a lap goes red here.
    #
    # COUNTED ON THE CALL, NOT ON THE SEMICOLON. This read `'; lap("'`,
    # which also pinned the one-line `step(); lap("x")` layout. On
    # 2026-09-03 each step gained a `with _isolated(...)` wrapper — one
    # bad feed was unwinding refresh_all and taking every later board
    # with it — so the laps moved onto their own lines and this went red
    # while every step was still being clocked. The guarantee is that
    # each step laps; the punctuation between them is not the guarantee.
    assert body.count('lap("') == body.count("_note_board(") + 9, body
    # And each one is isolated, so a step that raises cannot cost the
    # rest of the cycle — the same count, from the other end.
    assert body.count("_isolated(") == body.count('lap("'), body
    for chore in ("maintenance", "autosettle", "doctor"):
        assert f'_STEP_S["{chore}"]' in src, f"{chore} is not clocked"
    assert '"step_s": dict(_STEP_S),' in src, "the heartbeat lost the bill"
    at = src.index("def show_boards")
    body = src[at:src.index("\ndef ", at + 10)]
    assert "where the last cycle's time went" in body
    assert "key=lambda kv: -kv[1]" in body, "the bill must read worst first"


def test_the_boards_screen_reads_the_load_average_first():
    """Three staleness hunts have ended at a process OUTSIDE the loop
    eating the core (fitter cascade 08-31; two forgotten formfit copies
    09-01, load 5+ on one vCPU while every page aged 45 minutes). The
    number was in `uptime` all along — the screen must ask for it so a
    person doesn't have to remember to."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    at = src.index("def show_boards")
    body = src[at:src.index("\ndef ", at + 10)]
    assert "os.getloadavg()" in body
    assert "OVERSUBSCRIBED" in body, "a high load must say what to run next"
    assert "l5 > cores * 1.5" in body, \
        "the flag keys off sustained load per core, not a one-second spike"


def test_slow_moving_boards_get_a_floor_between_rebuilds():
    """The cycle bill, first cycle after the rogue fitters died
    (2026-09-01): predmarkets 72s and fantasy 13s of 524s — a sixth of
    every page's age spent re-asking two questions whose answers move
    on a clock of minutes. Stamped like futures: the LOOP (quiet) skips
    a board younger than its floor; a hand-run launch still rebuilds."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    assert "PREDMARKETS_EVERY_S = 600" in src
    assert "FANTASY_EVERY_S = 900" in src
    for fn, stamp, every in (("refresh_predmarkets", ".pm_built",
                              "PREDMARKETS_EVERY_S"),
                             ("refresh_fantasy", ".fantasy_built",
                              "FANTASY_EVERY_S")):
        at = src.index(f"def {fn}(")
        body = src[at:src.index("\ndef ", at + 10)]
        assert f'if quiet and not _due("{stamp}", {every}):' in body, fn
        assert f'_stamp("{stamp}")' in body, f"{fn} never stamps a success"
        # Gated on `quiet` so `python3 launch.py` by hand still rebuilds.
        assert body.index("if quiet and not _due(") < body.index("_run_build(")


def test_builds_run_niced_below_the_serving_process():
    """One core serves the pages AND chews the builds. At equal priority
    a ten-minute board rebuild makes every tap feel broken while it runs
    — the 2026-08-31 CPU-starvation cascade, from inside the house."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    at = src.index("def _run_build")
    body = src[at:src.index("\ndef ", at + 10)]
    assert "os.nice(10)" in body and "preexec_fn=nicer" in body


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
