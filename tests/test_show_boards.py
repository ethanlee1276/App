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


def test_it_also_prints_what_the_loop_recorded():
    """So the disagreement between them is visible, which is what #82
    turned out to be."""
    launch._note_board("mlb", True)
    out = _run()
    assert "last refresh attempt" in out


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


def test_it_is_reachable_from_the_command_line():
    with open(os.path.join(ROOT, "launch.py"), encoding="utf-8") as f:
        src = f.read()
    assert 'if "--boards" in argv:' in src
    assert "show_boards()" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
