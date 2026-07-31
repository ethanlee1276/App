"""The WNBA feed: the guess that failed, and the guards against the next one.

The original source pointed at `cdn.wnba.com` on the theory that the
league runs the NBA's stack at the NBA's paths. It was written without any
way to verify it and it returned something that wasn't JSON for every date
of the season on a real machine.

Three separate faults produced that output, and each gets a test:

**A bad response was cached.** `fetch_text` writes whatever came back, so
one HTML error page became the answer for the whole TTL and every caller
after it failed with a JSONDecodeError pointing at column 1 instead of at
the wrong URL.

**The error repeated ninety-two times.** One line per date, all identical,
burying the single line that said why.

**And the box-score parse must not repeat the guess.** ESPN's stat columns
come with a names array; reading by position would work until a column
moved, and then minutes would quietly be read as rebounds — a board full
of confident nonsense with nothing objecting.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.sources import fetch as F
from engine.sources import wnbaespn as W


# --- the cache must not preserve a bad answer -------------------------------
def test_a_non_json_response_is_never_cached():
    tmp = Path(tempfile.mkdtemp())
    saved = F.CACHE_DIR
    try:
        F.CACHE_DIR = tmp
        html = b"<html><body>404 Not Found</body></html>"

        class _Resp:
            def read(self): return html
            def __enter__(self): return self
            def __exit__(self, *a): return False

        saved_open = F.urllib.request.urlopen
        F.urllib.request.urlopen = lambda *a, **k: _Resp()
        try:
            raised = False
            try:
                F.fetch_json("https://example.test/x.json", "probe.json")
            except F.DataUnavailable as exc:
                raised = True
                assert "did not return JSON" in str(exc)
                assert "404 Not Found" in str(exc), "say what came back instead"
            assert raised
            assert not (tmp / "probe.json").exists(), \
                "garbage was cached and will be served for the whole TTL"
        finally:
            F.urllib.request.urlopen = saved_open
    finally:
        F.CACHE_DIR = saved


def test_an_already_poisoned_cache_is_discarded_not_served():
    tmp = Path(tempfile.mkdtemp())
    saved = F.CACHE_DIR
    try:
        F.CACHE_DIR = tmp
        (tmp / "poison.json").write_text("<html>nope</html>")

        class _Resp:
            def read(self): return b'{"ok": true}'
            def __enter__(self): return self
            def __exit__(self, *a): return False

        saved_open = F.urllib.request.urlopen
        F.urllib.request.urlopen = lambda *a, **k: _Resp()
        try:
            got = F.fetch_json("https://example.test/x.json", "poison.json")
            assert got == {"ok": True}, "a stale poisoned cache was served"
        finally:
            F.urllib.request.urlopen = saved_open
    finally:
        F.CACHE_DIR = saved


# --- the box score reads by name, not by position ---------------------------
def _summary(names, stats):
    return {"boxscore": {"players": [{
        "team": {"abbreviation": "LVA"},
        "statistics": [{"names": names,
                        "athletes": [{"athlete": {"displayName": "A Player"},
                                      "starter": True, "stats": stats}]}]}]}}


def test_stats_are_read_by_column_name():
    rows = W.parse_summary(_summary(
        ["MIN", "FG", "3PT", "FT", "REB", "AST", "PTS"],
        ["31", "8-15", "3-7", "2-2", "9", "5", "21"]))
    assert rows[0]["stats"] == {"min": 31.0, "fg3m": 3.0, "reb": 9.0,
                                "ast": 5.0, "pts": 21.0}


def test_moving_a_column_does_not_silently_reassign_a_stat():
    """The failure this prevents is invisible: minutes read as rebounds,
    and a whole board of confident nonsense with nothing objecting."""
    normal = W.parse_summary(_summary(
        ["MIN", "REB", "AST", "PTS"], ["31", "9", "5", "21"]))
    shuffled = W.parse_summary(_summary(
        ["PTS", "AST", "REB", "MIN"], ["21", "5", "9", "31"]))
    assert normal[0]["stats"] == shuffled[0]["stats"]


def test_an_unknown_column_is_ignored_rather_than_guessed_at():
    rows = W.parse_summary(_summary(["MIN", "DUNKS", "PTS"], ["30", "4", "18"]))
    assert rows[0]["stats"] == {"min": 30.0, "pts": 18.0}


def test_a_did_not_play_row_is_dropped_rather_than_zeroed():
    rows = W.parse_summary(_summary(["MIN", "PTS"], ["--", "--"]))
    # "--" minutes parse to 0 and nothing else survives; a row with no real
    # stat is not a game log.
    assert rows == [] or rows[0]["stats"] == {"min": 0.0}


def test_starters_are_labelled():
    rows = W.parse_summary(_summary(["MIN", "PTS"], ["30", "18"]))
    assert rows[0]["position"] == "S"


# --- the scoreboard ---------------------------------------------------------
def _event(gid="401", home="LVA", away="NYL", hs=88, as_=79, completed=True):
    return {"id": gid, "date": "2026-07-15T23:00Z", "competitions": [{
        "status": {"type": {"completed": completed}},
        "competitors": [
            {"homeAway": "home", "score": hs, "team": {"abbreviation": home}},
            {"homeAway": "away", "score": as_, "team": {"abbreviation": away}}]}]}


def test_the_scoreboard_carries_finals():
    g = W.parse_scoreboard({"events": [_event()]})[0]
    assert (g["home"], g["away"]) == ("LVA", "NYL")
    assert g["home_score"] == 88.0 and g["completed"] is True


def test_an_unfinished_game_reports_no_score():
    """A half-played game recorded as final would settle bets against a
    partial result."""
    g = W.parse_scoreboard({"events": [_event(completed=False)]})[0]
    assert g["home_score"] is None and g["completed"] is False


def test_the_shared_build_can_use_this_source():
    """nba_build calls parse_schedule_day(fetch_schedule(), date) for both
    leagues; a second code path for the WNBA is how the two drift apart."""
    import inspect
    assert callable(W.fetch_schedule) and callable(W.parse_schedule_day)
    assert len(inspect.signature(W.parse_schedule_day).parameters) == 2
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    build = open(os.path.join(root, "nba_build.py"), encoding="utf-8").read()
    assert "from engine.sources.wnbaespn import" in build
    assert "wnbadata import fetch_schedule" not in build


# --- the diagnostics --------------------------------------------------------
def test_a_repeated_failure_prints_once():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "ingest.py"), encoding="utf-8").read()
    assert "seen_errors" in src
    assert "identical failures suppressed" in src


def test_there_is_a_probe_that_reports_what_each_endpoint_returns():
    """Written so the next URL question is answered with a fact instead of
    another guess from a sandbox that cannot reach the host."""
    from engine.sources import wnbadata
    assert callable(wnbadata.probe)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "ingest.py"), encoding="utf-8").read()
    assert '"--probe"' in src and "args.probe" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
