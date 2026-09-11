"""A board frozen for twenty hours reported itself to nobody.

THE EVIDENCE, 2026-08-31. `cfb.json` carried
`generated_at: 2026-08-30T15:27:09` — twenty hours old — and
`journalctl -u qellys --since today | grep CFB` returned nothing at all.

Every link in that chain worked as designed:

  * `cfb_build` cannot reach the schedule, takes the "keep the last
    board" branch, WRITES NOTHING — deliberately, because rewriting
    would refresh `generated_at` and hide the very staleness a reader
    needs — and exits 0.
  * `_run_build` sees returncode 0 and swallows the subprocess output;
    it only forwards it on failure.
  * `refresh_cfb` detects the kept board correctly and prints it behind
    `if not quiet`.
  * The background loop is `refresh_all(quiet=True)`. PRODUCTION IS
    ALWAYS QUIET.

So a degraded state was detected accurately and reported to no one, and
#82 stayed open for three weeks over it. `_run_build`'s own header
already carries the doctrine — "failures now print unconditionally: one
line, into stdout, which systemd forwards to the journal" — and a board
frozen for a day is not a smaller problem than a build that exited 1.

AND THE EMPTY GREP IS NOT THE EVIDENCE. A successful quiet refresh
prints nothing either, so silence alone proves nothing; it was the FILE
TIMESTAMP that showed the freeze. `_warn_if_frozen` checks the same
thing the timestamp did, which is why it covers sports that cannot yet
describe themselves and any sport added later by someone who never reads
this file.

Run directly: `python3 tests/test_frozen_board.py`
"""

import io
import os
import sys
import tempfile
import time
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())

import launch


def _src():
    with open(os.path.join(ROOT, "launch.py"), encoding="utf-8") as f:
        return f.read()


def _board(name, age_hours=0.0, exists=True):
    """Register a board file of a given age and return its key."""
    path = os.path.join(tempfile.mkdtemp(), f"{name}.json")
    if exists:
        with open(path, "w") as f:
            f.write("{}")
        if age_hours:
            old = time.time() - age_hours * 3600
            os.utime(path, (old, old))
    launch.BOARD_FILES[name] = path
    launch._STALE_SAID.pop(name, None)
    return name


def _said(name):
    buf = io.StringIO()
    with redirect_stdout(buf):
        launch._note_board(name, True)
    return buf.getvalue()


# --- the alarm ------------------------------------------------------------
def test_a_freshly_written_board_says_nothing():
    """Silence is right when nothing is wrong; the loop runs every
    minute and must not narrate."""
    assert _said(_board("freshboard")) == ""


def test_a_board_that_stopped_being_written_says_so():
    """THE TWENTY-HOUR CASE."""
    out = _said(_board("frozenboard", age_hours=20))
    assert "BOARD FROZEN" in out
    assert "20.0h" in out


def test_a_missing_board_is_its_own_louder_alarm():
    out = _said(_board("goneboard", exists=False))
    assert "BOARD MISSING" in out


def test_it_names_the_usual_cause_so_the_next_step_is_obvious():
    out = _said(_board("frozen2", age_hours=20))
    assert "returning without" in out and "keeping the last board" in out


def test_a_board_just_under_the_threshold_stays_quiet():
    hours = (launch.STALE_BOARD_SECONDS / 3600) * 0.9
    assert _said(_board("nearlystale", age_hours=hours)) == ""


# --- it must not become noise ---------------------------------------------
def test_a_stuck_board_is_reported_at_most_once_per_window():
    """The loop ticks every minute. Without this a stuck board writes a
    line a minute and buries everything else in the journal."""
    name = _board("repeater", age_hours=20)
    assert "BOARD FROZEN" in _said(name)
    assert _said(name) == ""


def test_but_it_does_repeat_eventually():
    """Reported once and never again is how a problem gets forgotten."""
    name = _board("repeater2", age_hours=20)
    _said(name)
    launch._STALE_SAID[name] = time.time() - launch.STALE_REPEAT_SECONDS - 1
    assert "BOARD FROZEN" in _said(name)


# --- and it is wired to every board ---------------------------------------
def test_every_slate_board_is_watched():
    for sport in ("mlb", "nfl", "nba", "wnba", "cfb"):
        assert sport in launch.BOARD_FILES, sport


def test_the_check_runs_on_every_refresh():
    import inspect
    assert "_warn_if_frozen(name)" in inspect.getsource(launch._note_board)


def test_it_runs_after_the_heartbeat_is_recorded():
    """So a raise here cannot cost the record of the run itself."""
    import inspect
    src = inspect.getsource(launch._note_board)
    assert src.index("_BOARD_RUNS[name]") < src.index("_warn_if_frozen")


def test_an_unreadable_path_does_not_raise_into_the_loop():
    assert "except OSError:" in _src()


# --- the gate that hid it ---------------------------------------------------
def test_cfbs_degraded_words_no_longer_wait_for_a_non_quiet_run():
    """The exact line that reported to nobody. Production is always
    quiet, so `if not quiet` meant never."""
    src = _src()
    # The list of degraded words grows; what matters is that the gate is
    # not `if not quiet` alone.
    assert "if not quiet or kept or unreachable or unreadable" in src


def test_a_genuine_refresh_still_keeps_its_silence():
    """Ungating the degraded states must not turn the loop into a
    narrator — the reason it is quiet in the first place."""
    import inspect
    src = inspect.getsource(launch.refresh_cfb)
    at = src.index("if not quiet or kept")
    assert "kept or unreachable or unreadable" in src[at:at + 120]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
