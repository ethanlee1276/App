"""A college Saturday is sixty games, and the live board saw a dozen.

Ethan, 2026-09-19: *"none of the live play by play is working for CFB
games."*

Two defects, and the first one is the "none".

ONE — THE FAST SCOREBOARD ASKED FOR ESPN'S DEFAULT. `cfbdata` has
passed `groups=80&limit=900` since the day it was written, with a
docstring saying exactly why: *"ESPN defaults to a couple of dozen
events and a September Saturday has 60+, so the default would silently
drop half the slate."* `livescores.fetch_rows` called the same endpoint
BARE. So most college games were not in `live_cfb.json` at all — no
score, no state, no plays, and no deep file to open. The same rule
honoured in one place and not the other.

TWO — THE PLAY BUDGET WAS A RANKING THAT NEVER MOVED. `PLAYS_MAX_GAMES`
is eight, for a measured reason (a summary is a few hundred kilobytes
and this box OOM-killed seven test children on 2026-09-04), and the
eight were taken in SCOREBOARD order, which is kickoff order, which does
not change while a game is on. The noon window held the budget until it
finished. So even with the slate fixed, twenty-two live games would have
no plays and no deep file — and the deep file is what the play-by-play
PAGE reads, so clicking any of them showed nothing.

The cap is not the lever. The ORDER is: least-recently-served first,
with the deep file's own mtime as the cursor, so nothing is stored
between passes. Same ceiling, same requests, all of the slate — thirty
live games against eight is a refresh every four passes, under a minute
on a twelve-second clock.

AND A GAME WAITING ITS TURN KEEPS THE PLAYS IT HAD, or the round robin
would trade a dead strip for a blinking one.

Run directly:
`python3 tests/test_every_live_college_game_reaches_the_play_feed.py`
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

import livescore_build as B                                   # noqa: E402
from engine.models import LiveStatus                           # noqa: E402
from engine.sources import cfbdata, espnplays, livescores      # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _tmp():
    return Path(tempfile.mkdtemp())


# --- one: the whole slate ----------------------------------------------
def test_the_live_college_scoreboard_asks_for_every_fbs_game():
    """THE "NONE". A bare college scoreboard is ESPN's default handful."""
    q = livescores.SCOREBOARD_QUERY.get("cfb", "")
    assert f"groups={livescores.FBS_GROUP}" in q, q
    assert "limit=" in q, q
    assert int(q.split("limit=")[1].split("&")[0]) >= 900, q


def test_it_is_the_same_group_the_rest_of_the_college_code_uses():
    """Two constants for one ESPN group id is how they drift apart."""
    assert livescores.FBS_GROUP == cfbdata.FBS_GROUP


def test_the_leagues_that_fit_in_the_default_ask_for_nothing():
    """Sixteen NFL games and a dozen hoops fit inside ESPN's default, so
    those entries are ABSENT rather than empty — a table of empty strings
    invites somebody to `.get(league)` and get a falsy answer from two
    different situations."""
    assert set(livescores.SCOREBOARD_QUERY) == {"cfb"}, \
        livescores.SCOREBOARD_QUERY


def test_the_query_reaches_the_url_that_is_actually_fetched():
    """A table nothing reads is the defect this repo keeps shipping —
    the fix has to be ON THE REQUEST, so this watches the string
    `fetch_rows` hands to the fetcher."""
    asked = []
    real = livescores.fetch_text
    try:
        def fake(url, name, ttl=0, user_agent=None):
            asked.append(url)
            return json.dumps({"events": []})
        livescores.fetch_text = fake
        livescores.fetch_rows("cfb")
        livescores.fetch_rows("nfl")
    finally:
        livescores.fetch_text = real
    assert "groups=80" in asked[0] and "limit=900" in asked[0], asked[0]
    assert "?" not in asked[1], "the NFL url grew a query it does not need"


def test_the_summary_endpoint_is_not_broken_by_the_query():
    """`espnplays.ESPN_SUMMARY` builds itself by swapping the scoreboard
    url's LAST SEGMENT. Putting the query on the table rather than on
    `fetch_rows` would have made that slice cut into the middle of a
    parameter and pointed every college summary at nothing."""
    for lg, url in espnplays.ESPN_SUMMARY.items():
        assert url.endswith("/summary"), (lg, url)
        assert "?" not in url, (lg, url)


# --- two: whose turn it is ---------------------------------------------
def _game(ev, state="live"):
    return {"event_id": str(ev), "home": "UGA", "away": "BAMA",
            "home_id": "61", "away_id": "333",
            "live": {"state": state, "start_time": f"2026-09-19T{ev}:00Z"}}


def _served(pbp_dir, league, ev, when):
    p = Path(pbp_dir) / f"{league}_{ev}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{}")
    os.utime(p, (when, when))
    return p


def test_a_game_never_served_goes_first():
    d = _tmp()
    _served(d, "cfb", "10", 1000.0)
    _served(d, "cfb", "11", 2000.0)
    order = [g["event_id"] for g in B._round_robin(
        [_game("10"), _game("11"), _game("12")], "cfb", d)]
    assert order[0] == "12", order


def test_the_least_recently_served_leads_the_rest():
    """THE WHOLE FIX. Kickoff order is fixed for the length of a game, so
    the same eight won every pass; this order changes the moment a game
    is served."""
    d = _tmp()
    _served(d, "cfb", "10", 5000.0)
    _served(d, "cfb", "11", 1000.0)
    _served(d, "cfb", "12", 3000.0)
    order = [g["event_id"] for g in B._round_robin(
        [_game("10"), _game("11"), _game("12")], "cfb", d)]
    assert order == ["11", "12", "10"], order


def test_another_leagues_deep_file_is_not_this_leagues_cursor():
    """The files share a directory and differ only by prefix."""
    d = _tmp()
    _served(d, "nfl", "10", 9000.0)
    order = [g["event_id"] for g in B._round_robin(
        [_game("10"), _game("11")], "cfb", d)]
    assert order[0] == "10", order


def test_no_deep_directory_leaves_the_order_alone():
    live = [_game("11"), _game("10")]
    assert B._round_robin(live, "cfb", None) == live


def test_the_cap_itself_did_not_move():
    """The cap was measured against this box's one core and an OOM. The
    fix is the ORDER; raising the cap would be re-opening 2026-09-04."""
    assert B.PLAYS_MAX_GAMES == 8


# --- and a game waiting its turn keeps its strip ------------------------
def _prev(*games):
    return {"games": list(games)}


def test_a_capped_game_keeps_the_plays_it_had_last_pass():
    """Without this the round robin trades a dead strip for a blinking
    one: six plays on the pass it was fetched, empty for the next three."""
    g = _game("12")
    n = B._carry_forward([g], "cfb", _prev(
        {"event_id": "12", "plays": [{"event": "a run"}],
         "drive": {"team": "UGA"}}))
    assert n == 1
    assert g["plays"] == [{"event": "a run"}], g
    assert g["drive"] == {"team": "UGA"}, g
    assert g["plays_state"] == "carried", g


def test_a_carried_strip_is_labelled_rather_than_passed_off_as_current():
    """A stale drive shown as the live one is worse than no drive: it is
    a wrong answer where there was an honest gap."""
    js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    i = js.index("function playsHTML(")
    body = js[i:js.index("\nfunction ", i + 10)]
    assert 'plays_state === "carried"' in body, \
        "the page cannot tell a carried strip from a fresh one"
    assert "behind" in body, "nothing says the strip is behind"


def test_a_game_with_no_previous_plays_is_not_given_any():
    g = _game("12")
    assert B._carry_forward([g], "cfb", _prev({"event_id": "12"})) == 0
    assert "plays" not in g, g
    assert B._carry_forward([g], "cfb", None) == 0


def test_the_carry_reads_ONE_file_for_the_whole_league():
    """Re-reading each capped game's deep file would put the cost back
    exactly where the cap took it out — and a finished WNBA game's file
    is 392 plays."""
    import inspect
    src = inspect.getsource(B._carry_forward)
    assert "open(" not in src and "read_text" not in src, \
        "the carry-forward is reading files per game"


def test_the_previous_file_is_read_once_and_never_raises():
    d = _tmp()
    assert B._previous(d, "cfb") is None
    (d / "live_cfb.json").write_text("{ not json")
    assert B._previous(d, "cfb") is None
    # VALID JSON THAT IS NOT A PAYLOAD. A bare list or a null parses
    # fine and then `_carry_forward` calls `.get` on it — and that call
    # is OUTSIDE the per-game guard, so it would take the whole league's
    # scoreboard down rather than one card's plays. Mutation found this:
    # deleting the isinstance check passed until a non-dict was tried.
    for junk in ("[]", "null", '"a string"'):
        (d / "live_cfb.json").write_text(junk)
        assert B._previous(d, "cfb") is None, junk
    (d / "live_cfb.json").write_text(json.dumps({"games": [{"event_id": "1"}]}))
    assert B._previous(d, "cfb") == {"games": [{"event_id": "1"}]}


# --- the two halves, through the build ---------------------------------
class _Slate:
    """ESPN stood in for: a college Saturday of `n` live games."""

    def __init__(self, n):
        self.n = n
        self.summaries = []

    def rows(self, league, ttl=0):
        # `LiveStatus`, not a dict — `_row` reads it by attribute, and a
        # fixture shaped like the OUTPUT rather than like `fetch_rows`'s
        # real return is a fixture that proves nothing about the build.
        return [{"event_id": f"{i:02d}", "home": "UGA", "away": "BAMA",
                 "home_name": "Georgia", "away_name": "Alabama",
                 "home_id": "61", "away_id": "333",
                 "live": LiveStatus(
                     state="live", period="Q2", clock="5:00",
                     start_time=f"2026-09-19T{i:02d}:00Z",
                     home_score=7, away_score=3)}
                for i in range(self.n)]

    def summary(self, league, event_id, ttl=0):
        self.summaries.append(event_id)
        return {"drives": {"current": {
            "team": {"abbreviation": "UGA"},
            "plays": [{"period": {"number": 2}, "clock": {"displayValue": "5:00"},
                       "start": {"down": 1, "distance": 10},
                       "statYardage": 7, "type": {"text": "Rush"},
                       "text": "a run"}]}}}


def _run(slate, out_dir, passes=1):
    real_rows, real_sum = B.fetch_rows, espnplays.fetch_summary
    try:
        B.fetch_rows = slate.rows
        espnplays.fetch_summary = slate.summary
        for _ in range(passes):
            B.write("cfb", out_dir)
    finally:
        B.fetch_rows, espnplays.fetch_summary = real_rows, real_sum
    return json.loads((out_dir / "live_cfb.json").read_text())


def test_every_live_game_has_a_deep_file_within_a_few_passes():
    """THE READER'S BUG, END TO END: the play-by-play page reads
    `data/pbp/{league}_{event}.json`, so a game the sweep never fetched
    opens to nothing. Thirty live games, a cap of eight, four passes."""
    d = _tmp()
    slate = _Slate(30)
    _run(slate, d, passes=4)
    files = {p.name for p in (d / "pbp").glob("cfb_*.json")}
    assert len(files) == 30, f"{len(files)} of 30 games have a deep file"
    assert len(slate.summaries) == 32, len(slate.summaries)


def test_one_pass_still_respects_the_budget():
    d = _tmp()
    slate = _Slate(30)
    _run(slate, d, passes=1)
    assert len(slate.summaries) == B.PLAYS_MAX_GAMES, slate.summaries
    assert len({p.name for p in (d / "pbp").glob("cfb_*.json")}) == 8


def test_no_live_game_is_left_with_an_empty_strip_once_it_has_had_a_turn():
    """Fetched or carried, every live card has plays on it.

    THREE passes for twenty games at eight a pass, not two — a game that
    has never been fetched has nothing to carry either, and the claim
    here is about a game that has had its turn, not about the first
    minute of a Saturday. Written as the arithmetic rather than as a
    number so it still means something if the cap moves."""
    d = _tmp()
    n, cap = 20, B.PLAYS_MAX_GAMES
    _run(_Slate(n), d, passes=-(-n // cap))
    got = json.loads((d / "live_cfb.json").read_text())
    for g in got["games"]:
        assert g.get("plays"), (g["event_id"], g.get("plays_state"))
    assert {g["plays_state"] for g in got["games"]} == {"ok", "carried"}


def test_the_note_separates_carried_from_scores_only():
    """Ethan's standing complaint is failures that read as ordinary empty
    results. "22 past the cap" says nothing about whether those cards
    have plays on them."""
    d = _tmp()
    _run(_Slate(20), d, passes=2)
    note = json.loads((d / "live_cfb.json").read_text())["plays_note"]
    assert "carried forward" in note, note
    assert "scores only" in note, note


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{fails} failed" if fails else f"\n{ran} tests passed.")
    sys.exit(1 if fails else 0)
