"""An empty board that knows why it is empty must not say "no games".

REPORTED 2026-08-30: "cfb is not showing picks or live games" on
Saturday the 29th — the opening Saturday of the college season, the
biggest CFB day there is.

TWO PLACES A PERSON WOULD LOOK, AND BOTH LIED.

The page. `cfb_build` and `nba_build` publish `status: "unreachable"`
with the fetch error in `note` when the schedule feed cannot be reached,
and `gate.redact` passes both through to the browser untouched. The
empty state had a branch for "not built" and none for this, so it fell
through to "No games on the board right now · Nothing is scheduled or in
progress for this slate yet. Check back closer to game time." On an
opening Saturday that is not a near-miss; it is the opposite of the
truth, and it sends a reader away to wait for games that were always
there.

The log. `cfb_build` keeps the last board when there IS one and says so,
which `refresh_cfb` detected. With no previous board it publishes the
empty payload and returns — also exit 0 — and its last line is "No
previous board to keep...". That missed the check and printed
"refreshed": the journal reporting a current board while the feed was
down and the board was empty.

So the same failure was invisible on the page AND in the journal, which
is why it took a person noticing on their phone. Neither half is a
theory about what happened on the droplet; both are wrong regardless of
what did.

Run directly: `python3 tests/test_cfb_silent_saturday.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _app():
    with open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8") as f:
        return f.read()


def _empty_state():
    src = _app()
    i = src.index('el.innerHTML = state.data.status === "unreachable"')
    return src[i:src.index("// Nothing else to show", i)]


# --- the page -------------------------------------------------------------
def test_the_page_has_a_branch_for_a_feed_it_could_not_reach():
    body = _empty_state()
    assert 'state.data.status === "unreachable"' in body
    assert "Couldn’t reach the schedule feed" in body


def test_it_says_this_is_not_an_empty_slate():
    """The whole point. "No games" and "we could not load the games" are
    opposite claims and only one of them sends a reader away."""
    body = _empty_state()
    assert "not an empty slate" in body


def test_the_reason_the_build_wrote_down_is_shown():
    """`note` carries the actual fetch error. It survives the gate, so
    the only thing between it and the reader was this branch."""
    body = _empty_state()
    assert "state.data.note" in body
    assert "escapeHtml(String(state.data.note)" in body


def test_the_unreachable_branch_is_tested_before_no_games():
    """Order matters: an unreachable board also has zero games, so a
    later branch would never be reached."""
    body = _empty_state()
    assert body.index('"unreachable"') < body.index('"not built"')
    assert body.index('"unreachable"') < body.index("No games on the board")


def test_the_other_two_empty_states_still_work():
    body = _empty_state()
    assert "This slate hasn’t been built yet" in body
    assert "No games on the board right now" in body
    assert "No slate loaded" in body


def test_the_reason_survives_the_gate_which_is_why_this_is_reachable():
    from engine import gate
    got = gate.redact({"sport": "cfb", "games": [], "recommendations": [],
                       "status": "unreachable",
                       "note": "Could not fetch ESPN: 403 Forbidden"},
                      "cfb.json")
    assert got.get("status") == "unreachable"
    assert "403" in (got.get("note") or "")


# --- the log --------------------------------------------------------------
#: The two lines `cfb_build` prints, verbatim. `_run_build` returns only
#: the LAST line, and "schedule unreachable" is on the first of them —
#: which is why the check has to match on these.
KEPT_TAIL = "  Keeping the last board rather than publishing an empty one."
EMPTY_TAIL = ("  No previous board to keep, so an empty one was published "
              "with the reason on it.")


def _word(tail, ok=True):
    """The word `refresh_cfb` prints for a given build tail."""
    kept = ok and "Keeping the last board" in tail
    unreachable = ok and "No previous board to keep" in tail
    return ("kept last board (schedule unreachable)" if kept else
            "EMPTY BOARD — schedule unreachable, nothing to keep"
            if unreachable else ("refreshed" if ok else "unavailable"))


def test_both_build_messages_are_still_the_ones_being_matched():
    """The check is a string match against another file's output, so it
    breaks silently if that wording moves. Asserted here rather than
    trusted."""
    with open(os.path.join(ROOT, "cfb_build.py"), encoding="utf-8") as f:
        src = f.read()
    assert "Keeping the last board rather than publishing an " in src
    assert "No previous board to keep, so an empty one was published " in src


def test_an_empty_board_is_not_reported_as_refreshed():
    assert _word(EMPTY_TAIL) == \
        "EMPTY BOARD — schedule unreachable, nothing to keep"


def test_a_kept_board_still_reports_as_kept():
    assert _word(KEPT_TAIL) == "kept last board (schedule unreachable)"


def test_a_real_build_still_reports_as_refreshed():
    assert _word("CFB 2026-08-29: 61 games, 12 recommended") == "refreshed"
    assert _word("anything", ok=False) == "unavailable"


def test_launch_carries_the_same_two_tests():
    """The logic above mirrors `refresh_cfb`; assert the real one agrees
    rather than testing a copy of it."""
    with open(os.path.join(ROOT, "launch.py"), encoding="utf-8") as f:
        src = f.read()
    block = src[src.index("def refresh_cfb("):]
    block = block[:block.index("\ndef ")]
    assert 'kept = ok and "Keeping the last board" in tail' in block
    assert 'unreachable = ok and "No previous board to keep" in tail' in block
    assert "EMPTY BOARD" in block


def test_the_build_still_exits_zero_which_is_why_the_word_matters():
    """Nothing here changes the exit code, deliberately: a non-zero exit
    would make the refresh loop treat a recoverable feed blip as a crash.
    The signal has to be the word in the log, not the status code."""
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "cfb.json")
        p = subprocess.run(
            [sys.executable, "cfb_build.py", "2026-08-29", "--out", out],
            cwd=ROOT, capture_output=True, text=True, timeout=280)
    lines = (p.stdout + p.stderr).strip().splitlines()
    if not lines or "unreachable" not in " ".join(lines).lower():
        return                      # this box can reach ESPN; nothing to say
    assert p.returncode == 0, p.returncode
    assert _word(lines[-1]) != "refreshed", lines[-1]


# --- the reason the journal could not answer it --------------------------
def test_the_quiet_loop_leaves_no_trace_of_a_successful_build():
    """WHY THE FORENSIC FAILED, stated so nobody repeats it. The
    background loop calls `refresh_all(quiet=True)`; every `refresh_*`
    prints only when NOT quiet; `_run_build` captures the subprocess
    output and surfaces it only on failure. A successful quiet build is
    therefore completely silent, and a whole Saturday of them looks
    exactly like a loop that never reached CFB.

    The Aug 29 journal bears it out: the only CFB build lines all day
    were three NON-quiet startup builds, twenty-one hours apart."""
    with open(os.path.join(ROOT, "launch.py"), encoding="utf-8") as f:
        src = f.read()
    assert "refresh_all(quiet=True)" in src
    block = src[src.index("def _run_build("):]
    block = block[:block.index("\ndef ")]
    assert "capture_output=True" in block
    assert "if proc.returncode != 0:" in block


def test_every_board_records_what_its_build_did():
    """`heartbeat.json` answered "is the LOOP alive" and could not answer
    "did THIS BOARD rebuild" — the question a dark sport actually
    raises, and the one that matters most for CFB, whose board is also
    its live-games feed."""
    with open(os.path.join(ROOT, "launch.py"), encoding="utf-8") as f:
        src = f.read()
    assert '"boards": dict(_BOARD_RUNS)' in src
    block = src[src.index("def _note_board("):]
    block = block[:block.index("\ndef refresh_all(")]
    for key in ('"ok"', '"at"', '"at_epoch"'):
        assert key in block, key


def test_the_record_says_ok_or_not_ok_and_when():
    import launch
    launch._BOARD_RUNS.clear()
    assert launch._note_board("cfb", True) is True
    assert launch._note_board("nfl", False) is False
    assert launch._BOARD_RUNS["cfb"]["ok"] is True
    assert launch._BOARD_RUNS["nfl"]["ok"] is False
    assert launch._BOARD_RUNS["cfb"]["at_epoch"] > 0


def test_the_recorder_wraps_the_call_rather_than_replacing_it():
    """A LOOP OVER A TABLE OF NAMES WOULD HAVE BEEN TIDIER AND WORSE.
    `test_cfb_page` and `test_memecoins` both grep launch.py for the
    literal `refresh_cfb(quiet=quiet)` / `refresh_memes(`, guarding
    against a refresher that is defined and never called. Reaching the
    functions through `globals()[f"refresh_{name}"]` passed the suite's
    own new tests and broke both of those — a real guarantee traded for
    a cosmetic one. The wrapper keeps every call site literal."""
    with open(os.path.join(ROOT, "launch.py"), encoding="utf-8") as f:
        src = f.read()
    block = src[src.index("def refresh_all("):]
    block = block[:block.index("\n\ndef ")]
    for name in ("mlb", "nfl", "nba", "wnba", "cfb", "ufc", "memes",
                 "fantasy", "predmarkets"):
        assert f"refresh_{name}(quiet=quiet)" in block, name
        assert f'_note_board("{name}"' in block, name
    assert "globals()" not in block


def test_cfb_now_has_the_fast_scoreboard_it_was_missing():
    """RE-ANCHORED BECAUSE THE GAP CLOSED, and the old wording is worth
    keeping: "`LIVE_FAST` is MLB-only, so CFB's live games are read out
    of the model board. That is the single root cause behind both halves
    of the report: no rebuild means no picks AND no live games."

    Half of that is now fixed. `livescore_build.py` writes
    data/live_cfb.json from one keyless ESPN request, so a college
    Saturday that cannot afford a model rebuild still shows its games in
    progress — the two failures have been separated, which is the whole
    point. The board pointer stays asserted below because the MERGE still
    depends on it: the fast file knows the score, the board knows the
    lines, and dropping either is how the live win-probability chart
    went missing on 2026-08-18."""
    src = _app()
    i = src.index("const LIVE_FAST = {")
    seg = src[i:i + 400]
    assert 'cfb: "data/live_cfb.json"' in seg, seg
    assert 'mlb: "data/live_mlb.json"' in seg, seg
    assert 'cfb: "data/cfb.json"' in src, "the board pointer the merge needs"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
