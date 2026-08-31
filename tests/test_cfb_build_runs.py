"""cfb_build.main() actually EXECUTES its empty-slate branches now.

THE LESSON THIS FILE EXISTS TO KEEP. The college board crashed every
cycle for most of a day on an UnboundLocalError at a line four separate
test files had opinions about — and every one of them passed, because
they asserted on SOURCE TEXT (a status string exists, one branch precedes
another) or called the module-level helper directly, where the shadowing
local could not reach. A test that reads a function's source is not a
test that the function executes.

So this file runs the real `main()`, argv and all, with only the network
layer stubbed — the same scenarios the last three days actually
produced, each one a branch that either burned or was built during the
burn:

    feed unreachable, no board     -> "unreachable", written
    feed unreachable, board kept   -> nothing written at all
    empty day, season running      -> "no games today"   (the crash site)
    empty day, lookback dark       -> "schedule unknown"
    empty day, lookback empty      -> "offseason"
    events listed, none readable   -> "feed unreadable"

The DB is a throwaway sqlite and the writer is a plain JSON dump: the
contract under test is which branch runs and what it publishes, not the
gate or the parlay screen.

Run directly: `python3 tests/test_cfb_build_runs.py`
"""

import datetime
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

import cfb_build
from engine.sources import cfbdata
from engine.sources.fetch import DataUnavailable

DATE = "2026-08-31"


def _game_event():
    return {"competitions": [{"competitors": [
        {"homeAway": "home", "team": {"abbreviation": "BAMA",
                                      "displayName": "Alabama", "id": "333"}},
        {"homeAway": "away", "team": {"abbreviation": "UGA",
                                      "displayName": "Georgia", "id": "61"}}]}]}


def _nameless_event():
    return {"competitions": [{"competitors": [
        {"homeAway": "home", "team": {"abbreviation": "", "displayName": "",
                                      "id": ""}},
        {"homeAway": "away", "team": {"abbreviation": "", "displayName": "",
                                      "id": ""}}]}]}


def _run_main(scoreboards, out_path):
    """The real main(), with the network stubbed and nothing else.

    `scoreboards` maps ISO date -> payload dict, or an Exception to
    raise. Every caller of `fetch_scoreboard` — the slate, the history
    window, the lookback — goes through the same stub, exactly as they
    share the real function.
    """
    def fake_scoreboard(date, ttl=None):
        got = scoreboards.get(str(date)[:10], {"events": []})
        if isinstance(got, Exception):
            raise got
        return got

    def unavailable(*_a, **_k):
        raise DataUnavailable("stubbed off")

    def plain_write(out, path):
        with open(path, "w") as f:
            json.dump(out, f)

    patches = [
        (cfbdata, "fetch_scoreboard", fake_scoreboard),
        (cfbdata, "fetch_teams", unavailable),
        (cfbdata, "fetch_conferences", lambda *a, **k: {}),
        (cfb_build, "connect",
         lambda: __import__("engine.db", fromlist=["db"]).connect(":memory:")),
        (cfb_build, "_write", plain_write),
    ]
    saved = [(m, n, getattr(m, n)) for m, n, _ in patches]
    argv = sys.argv
    sys.argv = ["cfb_build.py", DATE, "--out", out_path]
    try:
        for m, n, v in patches:
            setattr(m, n, v)
        cfb_build.main()
    finally:
        sys.argv = argv
        for m, n, v in saved:
            setattr(m, n, v)


def _board(scoreboards, prior=None):
    out_path = os.path.join(tempfile.mkdtemp(), "cfb.json")
    if prior is not None:
        with open(out_path, "w") as f:
            json.dump(prior, f)
    _run_main(scoreboards, out_path)
    if not os.path.exists(out_path):
        return None
    with open(out_path) as f:
        return json.load(f)


def _lookback_days():
    day = datetime.date.fromisoformat(DATE)
    return [(day - datetime.timedelta(days=n)).isoformat()
            for n in range(1, cfb_build.NEARBY_DAYS + 1)]


# --- the crash site, executed ---------------------------------------------
def test_an_empty_day_in_a_running_season_builds_without_crashing():
    """THE LINE THAT KILLED THE BOARD. Zero games today, games in the
    lookback — main() must reach `_recent_games` and come back. Under
    the shadowing bug this exact call died with UnboundLocalError, and
    every source-text test passed while it did."""
    boards = {DATE: {"events": []},
              _lookback_days()[1]: {"events": [_game_event()]}}
    got = _board(boards)
    assert got is not None
    assert got["status"] == "no games today", got.get("status")
    assert "season is running" in got["note"]


def test_an_empty_day_with_a_dark_lookback_is_unknown():
    boards = {DATE: {"events": []}}
    for d in _lookback_days():
        boards[d] = DataUnavailable("dark")
    got = _board(boards)
    assert got["status"] == "schedule unknown", got.get("status")
    assert "not a claim" in got["note"]


def test_an_empty_day_with_an_empty_lookback_is_the_offseason():
    got = _board({DATE: {"events": []}})
    assert got["status"] == "offseason", got.get("status")


def test_a_listed_slate_the_parser_cannot_read_says_so():
    got = _board({DATE: {"events": [_nameless_event()] * 3}})
    assert got["status"] == "feed unreadable", got.get("status")
    assert got["feed"] == {"listed": 3, "kept": 0}


# --- the unreachable pair --------------------------------------------------
def test_an_unreachable_feed_with_no_prior_board_publishes_the_reason():
    got = _board({DATE: DataUnavailable("espn 403")})
    assert got["status"] == "unreachable"
    assert "espn 403" in got["note"]


def test_an_unreachable_feed_keeps_a_prior_board_and_writes_nothing():
    """The deliberate no-write: rewriting would refresh generated_at and
    hide the staleness a reader needs. This is the branch that made the
    freeze invisible, and the frozen-board alarm exists because of it."""
    prior = {"generated_at": "2026-08-30T15:27:09", "status": "",
             "games": [{"home": "BAMA", "away": "UGA"}]}
    got = _board({DATE: DataUnavailable("espn 403")}, prior=prior)
    assert got == prior, "the prior board was rewritten"


# --- the empty boards still carry their furniture --------------------------
def test_every_empty_status_still_ships_the_boards_shape():
    """The page indexes these keys before it looks at status; a missing
    one is a TypeError in the render, which is its own blank page."""
    got = _board({DATE: {"events": []}})
    for key in ("games", "recommendations", "most_likely", "market_scan",
                "counts", "date", "sport"):
        assert key in got, key


def test_the_census_travels_on_the_readable_empty_day():
    got = _board({DATE: {"events": []}})
    assert got["feed"] == {"listed": 0, "kept": 0}


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
