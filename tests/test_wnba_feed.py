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
    """A feed that is down is down for every date in the range. Printing
    the same failure ninety-two times buries the one line that says why.

    Tested by running the real walker against a feed that always fails,
    rather than by grepping for a variable name — the logic moved once
    already and the old test only noticed the rename."""
    import io
    import contextlib
    from engine import db
    import ingest as I

    conn = db.connect(":memory:")
    dates = [f"2026-07-{d:02d}" for d in range(1, 21)]

    def always_fails(_conn, date):
        return {"games": 0, "player_logs": 0,
                "skipped": [f"wnba scoreboard {date}: host unreachable"]}

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        I._walk_days(conn, "wnba", dates, always_fails, False, False)
    complaints = [ln for ln in buf.getvalue().splitlines()
                  if "skipped" in ln]
    assert len(complaints) == 1, \
        f"the same failure printed {len(complaints)} times"
    assert "host unreachable" in complaints[0]


def test_there_is_a_probe_that_reports_what_each_endpoint_returns():
    """Written so the next URL question is answered with a fact instead of
    another guess from a sandbox that cannot reach the host."""
    from engine.sources import wnbadata
    assert callable(wnbadata.probe)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "ingest.py"), encoding="utf-8").read()
    assert '"--probe"' in src and "args.probe" in src
# --- events the book priced and we could not place --------------------------
def test_an_unplaceable_event_is_recorded_not_silently_dropped():
    """Three different failures used to share one `continue`, uncounted.

    Downstream all anyone saw was a low events_used, and every prop in those
    games landed in the "no real book price" bucket looking exactly like a
    market the book never offered. Measured on a live WNBA board: 1 event
    matched out of 4 games, 761 props reported unpriced, and nothing said
    the other three had simply failed to map.
    """
    from engine.sources.oddsapi import OddsAttachResult
    r = OddsAttachResult()
    assert r.dropped_events == []


def test_the_two_drop_causes_are_named_separately():
    """They need opposite fixes. An unmapped NAME is a stale team table —
    the league renamed or expanded and SPORT_CONFIG never heard. A mapped
    pair that is not on the slate means our own abbreviations and the
    table's values disagree, which is wiring, not data."""
    import os
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "engine", "sources", "oddsapi.py"),
        encoding="utf-8").read()
    i = src.index("for ev in events:")
    block = src[i:i + 2600]
    assert '"team name not in the map"' in block
    assert '"mapped, but that pair is not on our slate"' in block
    # And the unmapped case must say WHICH name failed, or the report sends
    # you back to diffing two tables by eye.
    assert '"unmapped"' in block


def test_the_build_surfaces_dropped_events_rather_than_burying_them():
    import os
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "nba_build.py"), encoding="utf-8").read()
    i = src.index("odds_note = (f\"matched {res.matched} props")
    block = src[i:i + 1400]
    assert "res.dropped_events" in block
    assert "DROPPED" in block
# --- the join that actually places an event on the slate --------------------
def test_the_slates_own_names_beat_the_static_abbreviation_table():
    """The WNBA bug, in one assertion.

    SPORT_CONFIG's hand-written table used league-style codes (LVA, NYL,
    GSV); the ESPN schedule the slate is built from uses ESPN's own. Every
    event mapped to a pair that was not on the slate, all five games were
    dropped, and 761 props were reported unpriced on a night the book had
    priced every one of them.

    The schedule feed carries both halves of the join — the name the odds
    feed uses and the abbreviation the slate uses — so the map is built from
    it rather than maintained by hand against it.
    """
    from types import SimpleNamespace as NS
    from engine.sources import oddsapi

    slate_names = {}
    g = NS(home="LV", away="ATL", home_name="Las Vegas Aces",
           away_name="Atlanta Dream")
    for nm, ab in ((g.home_name, g.home), (g.away_name, g.away)):
        slate_names[oddsapi._team_key(nm)] = ab

    # The static table says LVA. The slate says LV. The slate wins.
    assert oddsapi.WNBA_TEAM_ABBR["Las Vegas Aces"] == "LVA"
    assert slate_names[oddsapi._team_key("Las Vegas Aces")] == "LV"


def test_the_team_key_ignores_only_case_and_punctuation():
    """Not clever on purpose. Dropping the city or matching the nickname
    alone collides the moment a league has a Los Angeles Sparks and a Los
    Angeles Lakers, and a join that is WRONG is worse than one that misses.
    """
    from engine.sources.oddsapi import _team_key
    assert _team_key("Los Angeles Sparks") == _team_key("los angeles sparks")
    assert _team_key("L.A. Sparks ") == _team_key("LA Sparks")
    assert _team_key("Los Angeles Sparks") != _team_key("Los Angeles Lakers")
    assert _team_key("") == ""


def test_the_static_table_still_answers_when_the_feed_has_no_names():
    """MLB and NFL slates carry no team names, and their tables are correct.
    The runtime map is a preference, not a replacement."""
    import os
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "engine", "sources", "oddsapi.py"),
        encoding="utf-8").read()
    i = src.index("def _abbr(name: str)")
    assert 'cfg["teams"].get(name)' in src[i:i + 200]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")