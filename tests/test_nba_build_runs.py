"""nba_build.main() actually EXECUTES, on the WNBA's ESPN feed shapes.

The college board's execution harness (test_cfb_build_runs.py) exists
because four source-text test files passed while the real main() crashed
every cycle. The WNBA board then produced the same lesson twice in one
morning: `_recent_slate` called names that only exist inside main(), and
`_live_block` read only Scalpy's numeric `status` while the ESPN rows it
now receives carry a string `state` — so the 8:56 PM board showed 3:00
and 5:00 games as not started even after the parser learned to say
"live". Both bugs lived on the path between modules, exactly where
unit tests of either module cannot see.

So this file runs the real `main()` with `--league wnba`, argv and all,
stubbing ONLY `espnhoops.fetch_scoreboard` (the network) plus the
databases (throwaway :memory:) and the publish writer (plain JSON dump).
The real ESPN parser, the real `parse_schedule_day`, the real
`_live_block` and the real branch logic all execute.

The scenarios are the last three days' actual weather:

    every fetch dark                -> "unreachable"       (was impossible:
                                       the parser swallowed the failure)
    empty day, lookback has games   -> "no games today"
    empty day, lookback dark        -> "schedule unknown"  (was "offseason"
                                       off our own dead network)
    empty day, lookback empty       -> "offseason"
    a LIVE game on the slate        -> live block, running score, clock
    a FINAL game                    -> final block, settled score
    a scheduled game                -> live is None

Run directly: `python3 tests/test_nba_build_runs.py`
"""

import datetime
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

import nba_build
from engine import db as _edb
from engine import gate as _gate
from engine import ledger as _ledger
from engine.sources import espnhoops
from engine.sources.fetch import DataUnavailable

DATE = "2026-08-31"


def _espn_event(state="pre", home_score="54", away_score="49",
                clock="Q3 4:21", completed=False):
    """A raw ESPN scoreboard event, the shape the real parser reads."""
    return {"id": "401736123", "date": f"{DATE}T23:00Z",
            "competitions": [{
                "competitors": [
                    {"homeAway": "home", "score": home_score,
                     "team": {"abbreviation": "LV",
                              "displayName": "Las Vegas Aces"}},
                    {"homeAway": "away", "score": away_score,
                     "team": {"abbreviation": "NY",
                              "displayName": "New York Liberty"}}],
                "status": {"period": 3, "displayClock": "4:21",
                           "type": {"state": state, "completed": completed,
                                    "shortDetail": clock}}}]}


def _run_main(boards, out_path):
    """The real main(), network and databases stubbed, nothing else.

    `boards` maps ISO date -> raw ESPN scoreboard payload, or an
    Exception to raise. Every fetch — the slate, yesterday, the schedule
    density window, the offseason lookback — goes through this one stub,
    exactly as they share the real `fetch_scoreboard`.
    """
    def fake_scoreboard(date, ttl=None, league="wnba"):
        got = boards.get(str(date)[:10], {"events": []})
        if isinstance(got, Exception):
            raise got
        return got

    mem = lambda *a, **k: _edb.__dict__["_orig_connect_for_test"](":memory:")

    def plain_publish(payload, path, name=""):
        with open(path, "w") as f:
            json.dump(payload, f)
        return str(path), str(path)

    _edb.__dict__["_orig_connect_for_test"] = _edb.connect
    _lmem = (lambda path=None, _o=_ledger.connect: _o(":memory:"))
    patches = [
        (espnhoops, "fetch_scoreboard", fake_scoreboard),
        (nba_build, "connect", mem),
        (_edb, "connect", mem),
        (_ledger, "connect", _lmem),
        (_ledger, "export_json", lambda *a, **k: None),
        (_gate, "publish", plain_publish),
    ]
    saved = [(m, n, getattr(m, n)) for m, n, _ in patches]
    argv = sys.argv
    sys.argv = ["nba_build.py", DATE, "--league", "wnba", "--out", out_path]
    try:
        for m, n, v in patches:
            setattr(m, n, v)
        nba_build.main()
    finally:
        sys.argv = argv
        for m, n, v in saved:
            setattr(m, n, v)
        del _edb.__dict__["_orig_connect_for_test"]


def _board(boards):
    out_path = os.path.join(tempfile.mkdtemp(), "wnba.json")
    _run_main(boards, out_path)
    with open(out_path) as f:
        return json.load(f)


def _dark_everywhere():
    """Every date the build could ask about, unreachable."""
    day = datetime.date.fromisoformat(DATE)
    boards = {}
    for n in range(-2, nba_build.LOOKBACK_DAYS + 2):
        boards[(day - datetime.timedelta(days=n)).isoformat()] = \
            DataUnavailable("espn 403")
    return boards


# --- the failure the swallowed exception made impossible -------------------
def test_a_dark_feed_says_unreachable_not_offseason():
    """Before the parse fix this published "offseason": the parser ate
    DataUnavailable and returned [], today looked empty, and the lookback
    counted ten fetch failures as ten quiet days."""
    got = _board(_dark_everywhere())
    assert got["status"] == "unreachable", got.get("status")
    assert "espn 403" in got["note"]


def test_a_dark_lookback_is_unknown_not_offseason():
    boards = _dark_everywhere()
    boards[DATE] = {"events": []}
    got = _board(boards)
    assert got["status"] == "schedule unknown", got.get("status")
    assert "not a claim" in got["note"]


def test_yesterday_failing_does_not_take_down_a_read_slate():
    """One shared try meant yesterday's dead scoreboard threw away a
    slate that had already been fetched. The b2b read degrades; the
    slate stays up."""
    boards = _dark_everywhere()
    boards[DATE] = {"events": [_espn_event(state="in")]}
    got = _board(boards)
    assert got["status"] != "unreachable", got.get("status")
    assert len(got["games"]) == 1


# --- the honest empties ----------------------------------------------------
def test_an_empty_day_in_a_running_season_is_a_quiet_date():
    lookback = (datetime.date.fromisoformat(DATE)
                - datetime.timedelta(days=3)).isoformat()
    got = _board({DATE: {"events": []},
                  lookback: {"events": [_espn_event()]}})
    assert got["status"] == "no games today", got.get("status")
    assert "season is running" in got["note"]


def test_an_empty_day_with_an_empty_lookback_is_the_offseason():
    got = _board({DATE: {"events": []}})
    assert got["status"] == "offseason", got.get("status")


# --- the live block, through the real main() -------------------------------
def test_a_live_espn_game_publishes_live_state_and_running_score():
    """THE SECOND INCH. The parser learned "live" on 2026-08-30 and the
    board still drew every game as not started, because `_live_block`
    read only Scalpy's numeric status. This is that game, through the
    whole chain."""
    got = _board({DATE: {"events": [_espn_event(state="in")]}})
    live = got["games"][0]["live"]
    assert live is not None, "a live game published no live block"
    assert live["state"] == "live"
    assert live["home_score"] == 54 and live["away_score"] == 49
    assert live["detail"] == "Q3 4:21"


def test_a_final_espn_game_publishes_final_with_settled_score():
    got = _board({DATE: {"events": [_espn_event(
        state="post", completed=True, clock="Final",
        home_score="88", away_score="80")]}})
    live = got["games"][0]["live"]
    assert live["state"] == "final"
    assert live["home_score"] == 88 and live["away_score"] == 80


def test_a_scheduled_game_publishes_no_live_block():
    got = _board({DATE: {"events": [_espn_event(state="pre")]}})
    assert got["games"][0]["live"] is None


# --- _live_block on both feed shapes, directly -----------------------------
def test_live_block_reads_scalpys_numeric_status():
    b = nba_build._live_block({"status": 2, "home_score": 61,
                               "away_score": 58})
    assert b == {"state": "live", "home_score": 61, "away_score": 58,
                 "detail": "in progress"}
    f = nba_build._live_block({"status": 3, "home_score": 100,
                               "away_score": 95})
    assert f["state"] == "final" and f["detail"] == "final"
    assert nba_build._live_block({"status": 1}) is None


def test_live_block_keeps_final_scores_out_of_a_live_espn_game():
    """`home_score` is None until the game completes — settlement reads
    it, and a third-quarter score there grades bets against a game still
    being played. The display copy rides in the live pair."""
    b = nba_build._live_block({"state": "live", "home_score": None,
                               "away_score": None, "live_home_score": 54,
                               "live_away_score": 49, "clock": "Q3 4:21"})
    assert b["home_score"] == 54 and b["detail"] == "Q3 4:21"


def test_live_block_reads_an_espn_final_by_completed_flag():
    b = nba_build._live_block({"state": "final", "completed": True,
                               "home_score": 88, "away_score": 80,
                               "clock": "Final"})
    assert b["state"] == "final" and b["home_score"] == 88


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
    print(f"\n{len(fns)} tests passed.")
