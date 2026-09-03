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

def test_the_pick_column_counts_what_cleared_not_what_was_evaluated():
    """Ethan, 2026-09-03: "The 612 rows in the array are candidates, not
    picks."

    `recommendations` holds every prop the board EVALUATED. The per-row
    `recommended` flag — set in engine/pipeline from the grade — is what
    actually cleared. Printing the array's length called college's 612
    candidates 612 picks, and made a real zero unreadable next to it."""
    recs = [{"recommended": i < 10} for i in range(285)]
    _board("clearing", {"games": [1], "recommendations": recs})
    out = _run()
    line = [l for l in out.splitlines() if "CLEARING" in l.upper()]
    assert line, out
    assert "10 of 285" in line[0], line[0]


def test_the_report_reads_the_private_copy_not_the_stripped_one():
    """THE THIRD TOOL TO MAKE THIS MISTAKE. Ethan, 2026-09-03: "The zero
    in the recs column is the paywall again."

    BOARD_FILES points at web/data — the copies `gate.redact` empties —
    so with the wall up this screen called every board 0 picks, in the
    one place somebody looks when they suspect a build is broken. Board
    lint and the empty-board explainer both learned it before this, and
    `gate.board_source`'s own docstring names three tools before those."""
    import json as _json
    import tempfile as _tf
    root = _tf.mkdtemp()
    pub = os.path.join(root, "web", "data", "walled.json")
    priv = os.path.join(root, "data", "built", "walled.json")
    os.makedirs(os.path.dirname(pub)); os.makedirs(os.path.dirname(priv))
    # what a stranger is served, and what the subscriber's copy holds
    _json.dump({"games": [1], "recommendations": [],
                "locked": {"recommendations": 7},
                "locked_reason": "subscription"}, open(pub, "w"))
    _json.dump({"games": [1],
                "recommendations": [{"recommended": True}] * 7}, open(priv, "w"))
    launch.BOARD_FILES["walled"] = pub
    out = _run()
    line = [l for l in out.splitlines() if "WALLED" in l.upper()]
    assert line, out
    assert "7 of 7" in line[0], \
        f"the report is still measuring the redacted board: {line[0]}"


def test_a_board_pointed_outside_web_data_is_read_where_it_points():
    """`board_source` falls back to the module-global data/built for a
    path it cannot place — right for its own callers, wrong for a
    CONFIGURABLE map, which would then be answered with this checkout's
    private copy of the same basename. Same shadowing as the gate fixture
    leak, arriving from the other side."""
    import json as _json
    import tempfile as _tf
    # deliberately named for a real board, somewhere that is not web/data
    p = os.path.join(_tf.mkdtemp(), "cfb.json")
    _json.dump({"games": [1, 2], "recommendations": [{"recommended": True}],
                "status": "elsewhere"}, open(p, "w"))
    launch.BOARD_FILES["cfb"] = p
    out = _run()
    line = [l for l in out.splitlines() if l.strip().startswith("CFB")]
    assert line, out
    assert "1 of 1" in line[0] and "elsewhere" in line[0], \
        f"the report read a board it was not pointed at: {line[0]}"


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


def test_the_load_flag_no_longer_names_a_culprit_it_cannot_see():
    """Ethan, 2026-09-03: "The oversubscription warning is misattributed.
    It says something outside the loop is eating the core, but the culprit
    is the loop's own NFL build."

    Three earlier hunts DID end outside the loop, and the screen turned
    that history into an assertion it makes on its own authority. A full
    cycle is thirteen builds; during one, high load is the loop working.
    `--boards` is its own process and cannot tell from inside which it
    is, so it must offer both and hand over the command that settles it."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    at = src.index("def show_boards")
    body = src[at:src.index("\ndef ", at + 10)]
    flag = body[body.index("OVERSUBSCRIBED"):][:220]
    assert "outside the loop is" not in flag, \
        f"the screen still asserts a cause it cannot observe: {flag!r}"
    assert "ps aux" in flag, "it no longer says how to settle it"


def test_the_screen_reports_memory_against_the_units_own_cap():
    """Load recovers on its own; memory does not. 2026-09-02 was an OOM
    crash loop, and the number that predicts it — one child holding most
    of the unit's cap — was the one thing this screen could not say."""
    import io as _io
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    i = src.index("def _memory_headroom"); j = src.index("\ndef ", i + 10)
    ns = {}
    exec(src[i:j], ns)                                    # noqa: S102

    def _open(path, *a, **k):
        if path == "/sys/fs/cgroup/memory.max":
            return _io.StringIO("1600000000")             # the droplet's cap
        if path == "/proc/4242/status":
            return _io.StringIO("Name:\tpython3\nVmRSS:\t1318359 kB\n")
        if path.endswith("/status"):
            return _io.StringIO("Name:\tsh\nVmRSS:\t2048 kB\n")
        raise OSError
    ns["open"] = _open
    ns["os"] = type("O", (), {"listdir": staticmethod(lambda p: ["4242", "9"])})()
    out = ns["_memory_headroom"]()
    assert "1350 MB" in out and "1600 MB" in out and "84%" in out, out
    assert "OOM" in out, "84% of the cap passes without a word of warning"


def test_no_cap_means_no_line_rather_than_an_invented_percentage():
    """A laptop has no cgroup ceiling. A share of an unlimited budget is
    not a number, and printing one would be the fabrication this repo
    refuses everywhere else."""
    import io as _io
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    i = src.index("def _memory_headroom"); j = src.index("\ndef ", i + 10)
    ns = {}
    exec(src[i:j], ns)                                    # noqa: S102
    ns["open"] = lambda p, *a, **k: _io.StringIO("max")
    assert ns["_memory_headroom"]() == ""


def test_a_broken_memory_probe_cannot_take_the_screen_down():
    """It is a diagnostic. The one thing it must never be is the fault."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    at = src.index("def show_boards")
    body = src[at:src.index("\ndef ", at + 10)]
    call = body[body.index("_memory_headroom()"):][:200]
    assert "except Exception" in call, \
        "the memory probe is not wrapped where it is called"


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
