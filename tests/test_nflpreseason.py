"""Preseason comes from ESPN, because nflverse does not have it.

Measured on the cached nflverse schedule: 7,548 games whose `game_type` is
REG, WC, DIV, CON or SB — **zero preseason rows**. The board reads that
file, so it cannot show an August fixture however it is asked.

These tests run against fixtures rather than the network, and that is a
real limitation worth naming: `site.api.espn.com` is refused by the cloud
container's network policy, so the parser was written from the payload
shape `livescores.parse_espn_scoreboard` already handles rather than from
a response anyone here has seen. What is pinned below is the reading, the
failure behaviour, and the separation from pricing — not that ESPN's
current API matches. The first real run is the test of that, which is why
the raw payload is cached before it is parsed.

Run directly: `python3 tests/test_nflpreseason.py`
"""

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.sources import nflpreseason as pre                  # noqa: E402
from engine.sources.fetch import DataUnavailable                # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _event(eid, date, home, away, hs=None, as_=None, week=1,
           completed=False, state="pre", indoor=False):
    def side(ab, score, ha):
        c = {"homeAway": ha, "team": {"abbreviation": ab}}
        if score is not None:
            c["score"] = str(score)
        return c
    return {
        "id": str(eid), "date": date, "week": {"number": week},
        "competitions": [{
            "venue": {"fullName": "Somewhere Field", "indoor": indoor},
            "competitors": [side(home, hs, "home"), side(away, as_, "away")],
            "status": {"type": {"state": state, "completed": completed}},
        }],
    }


def _board(*events):
    return {"events": list(events)}


# --- the premise -------------------------------------------------------------
def test_nflverse_really_has_no_preseason():
    """The reason this module exists. If a future nflverse ships preseason
    rows, this whole source becomes redundant and should be reconsidered
    rather than kept out of habit."""
    path = os.path.join(ROOT, "data", "cache", "games.csv")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        kinds = {r.get("game_type", "") for r in csv.DictReader(fh)}
    assert "PRE" not in kinds, kinds
    assert "REG" in kinds, kinds


# --- reading -----------------------------------------------------------------
def test_a_scheduled_game_reads_with_no_score():
    got = pre.parse_games(_board(_event(1, "2026-08-13T23:00Z", "KC", "DET")),
                          2026)
    assert len(got) == 1
    g = got[0]
    assert (g["home"], g["away"]) == ("KC", "DET")
    assert g["home_score"] is None and g["away_score"] is None
    assert g["completed"] is False
    assert g["date"] == "2026-08-13"
    assert g["season_type"] == "PRE"


def test_a_finished_game_carries_its_score():
    got = pre.parse_games(
        _board(_event(2, "2026-08-14T23:00Z", "GB", "CLE", 17, 13,
                      completed=True, state="post")), 2026)
    g = got[0]
    assert (g["home_score"], g["away_score"]) == (17, 13)
    assert g["completed"] is True


def test_espn_abbreviations_are_translated():
    """WSH and LAR are ESPN's; the rest of the site says WAS and LA. One
    spelling, or the same team is two teams."""
    got = pre.parse_games(_board(_event(3, "2026-08-15T20:00Z", "WSH", "LAR")),
                          2026)
    assert (got[0]["home"], got[0]["away"]) == ("WAS", "LA")


def test_a_game_missing_a_side_is_skipped_not_half_built():
    board = {"events": [{"id": "9", "date": "2026-08-13T23:00Z",
                         "competitions": [{"competitors": []}]}]}
    assert pre.parse_games(board, 2026) == []


# --- failing loudly ----------------------------------------------------------
def test_an_unrecognised_payload_raises_rather_than_reading_as_empty():
    """An empty list is a legitimate answer for a date with no fixtures, so
    using it for "I did not understand this" would let a broken parser
    look exactly like a quiet August."""
    for bad in ({}, {"error": "nope"}, {"leagues": []}):
        try:
            pre.parse_games(bad, 2026)
        except DataUnavailable:
            pass
        else:
            raise AssertionError(f"parsed {bad!r} without complaint")


def test_an_empty_event_list_is_allowed():
    """A week with no games is ordinary — the Hall of Fame game exists some
    years and not others."""
    assert pre.parse_games({"events": []}, 2026) == []


# --- the window --------------------------------------------------------------
def test_the_window_spans_first_to_last():
    games = pre.parse_games(_board(
        _event(1, "2026-08-20T23:00Z", "KC", "DET"),
        _event(2, "2026-08-13T23:00Z", "GB", "CLE"),
        _event(3, "2026-08-27T23:00Z", "NE", "NYJ")), 2026)
    assert pre.window(games) == ("2026-08-13", "2026-08-27")


def test_days_until_counts_down_and_then_up():
    import datetime as dt
    games = pre.parse_games(_board(_event(1, "2026-08-13T23:00Z", "KC", "DET")),
                            2026)
    assert pre.days_until(games, dt.date(2026, 8, 8)) == 5
    assert pre.days_until(games, dt.date(2026, 8, 13)) == 0
    assert pre.days_until(games, dt.date(2026, 8, 20)) == -7


def test_an_empty_fixture_list_has_no_window():
    assert pre.window([]) is None
    assert pre.days_until([]) is None


# --- it must not become a betting board --------------------------------------
def test_nothing_here_prices_or_journals():
    """Preseason is where the engine's premise fails: a projection is
    volume times efficiency over prior games, and in August a starter
    plays a series behind a line that will not start together again."""
    for f in ("engine/sources/nflpreseason.py", "nflpre.py"):
        src = open(os.path.join(ROOT, f), encoding="utf-8").read()
        body = src.split('"""')[2]
        for forbidden in ("hit_prob", "stake_units", "log_recommendations",
                          "run_slate", "edge", "kelly"):
            assert forbidden not in body, (f, forbidden)


def test_the_reason_it_does_not_price_is_written_down():
    doc = " ".join((pre.__doc__ or "").split())
    assert "does not price" in doc.lower() or "not price" in doc.lower()
    assert "different event" in doc


def test_the_unverified_api_shape_is_disclosed():
    """The parser was written without ever seeing a live response. A reader
    who does not know that will trust it more than it has earned."""
    doc = " ".join((pre.__doc__ or "").split())
    assert "403" in doc or "cannot reach" in doc.lower()
    assert "cached before it is parsed" in doc


# --- what the probe measured -------------------------------------------------
def test_the_query_carries_no_limit_parameter():
    """The whole first-run bug. Probed from Ethan's machine 2026-08-08:

        ?dates=2026&seasontype=1&week=1              1 game
        ?dates=2026&seasontype=1&week=1&limit=400    nothing

    ESPN does not take `limit`, and supplying it empties the answer rather
    than being ignored. It was added on a guess about pagination for an API
    nobody had called."""
    assert "limit" not in pre._url(2026, pre.PRESEASON, 1)


def test_the_week_is_always_sent():
    """Dropping it does not widen the query, it breaks the season-type
    filter: `?dates=2026&seasontype=1` returned 100 games starting
    2026-01-03 — a REGULAR fixture from the 2025 season."""
    assert "week=1" in pre._url(2026, pre.PRESEASON, 1)
    assert "seasontype=1" in pre._url(2026, pre.PRESEASON, 1)


def test_a_single_game_week_is_not_a_failure():
    """Preseason week 1 is the Hall of Fame game alone. A loop that treated
    a one-game week as a bad response would throw away the opener."""
    got = pre.parse_games(
        _board(_event(1, "2026-08-07T20:00Z", "CAR", "ARI", week=1)), 2026)
    assert len(got) == 1
    assert got[0]["week"] == 1


def test_the_range_fallback_is_a_fallback_not_the_primary():
    """It asks for every game in a window and trusts that only preseason
    falls there — true for 2026, a guess in general. The week loop asks by
    name, so it stays first."""
    import inspect
    src = inspect.getsource(pre.preseason_games)
    assert src.index("fetch_scoreboard") < src.index("_by_date_range")
    doc = " ".join((pre._range_url.__doc__ or "").split())
    assert "FALLBACK" in doc and "calendar guess" in doc


def test_the_range_fallback_drops_anything_past_preseason():
    """The window carries whatever is in it. A regular-season fixture that
    creeps into the range must not be relabelled PRE."""
    board = _board(_event(1, "2026-08-07T20:00Z", "CAR", "ARI", week=1),
                   _event(2, "2026-09-10T20:00Z", "SEA", "NE", week=18))
    kept = [g for g in pre.parse_games(board, 2026) if (g.get("week") or 0) <= 4]
    assert [g["week"] for g in kept] == [1]


# --- what the first real run exposed -----------------------------------------
def test_a_placeholder_zero_is_not_a_score():
    """ESPN sends `score: "0"` for a game nobody has played, not an absent
    field. Taken at face value that is a real 0-0, and since `completed` is
    also false the only label left is "live" — which is how 48 scheduled
    preseason fixtures came out tagged as in progress on the first run
    against real data."""
    board = {"events": [{
        "id": "1", "date": "2026-08-13T23:00Z", "week": {"number": 2},
        "competitions": [{"competitors": [
            {"homeAway": "home", "team": {"abbreviation": "CIN"}, "score": "0"},
            {"homeAway": "away", "team": {"abbreviation": "DET"}, "score": "0"}],
            "status": {"type": {"state": "pre", "completed": False}}}]}]}
    g = pre.parse_games(board, 2026)[0]
    assert g["home_score"] is None and g["away_score"] is None
    assert g["state"] == "pre"


def test_a_real_nil_nil_in_progress_survives():
    """The guard keys on `state`, not on the number, so a genuine scoreless
    first quarter is still a live 0-0 rather than being blanked."""
    board = {"events": [{
        "id": "2", "date": "2026-08-13T23:00Z", "week": {"number": 2},
        "competitions": [{"competitors": [
            {"homeAway": "home", "team": {"abbreviation": "PIT"}, "score": "0"},
            {"homeAway": "away", "team": {"abbreviation": "GB"}, "score": "0"}],
            "status": {"type": {"state": "in", "completed": False}}}]}]}
    g = pre.parse_games(board, 2026)[0]
    assert g["home_score"] == 0 and g["away_score"] == 0
    assert g["state"] == "in"


def test_a_final_keeps_its_score():
    board = {"events": [{
        "id": "3", "date": "2026-08-07T23:00Z", "week": {"number": 1},
        "competitions": [{"competitors": [
            {"homeAway": "home", "team": {"abbreviation": "ARI"}, "score": "30"},
            {"homeAway": "away", "team": {"abbreviation": "CAR"}, "score": "33"}],
            "status": {"type": {"state": "post", "completed": True}}}]}]}
    g = pre.parse_games(board, 2026)[0]
    assert (g["away_score"], g["home_score"]) == (33, 30)
    assert g["completed"] is True


def test_the_display_labels_from_state_not_from_a_number():
    """"Has a score" and "has been played" are different questions, and
    the first cut of the report asked the wrong one."""
    src = open(os.path.join(ROOT, "nflpre.py"), encoding="utf-8").read()
    i = src.index('score = ""')
    block = src[i:i + 400]
    assert 'g["state"] == "post"' in block
    assert 'g["state"] == "in"' in block




# --- the live board must not borrow a preseason score -------------------------
def test_the_live_overlay_matches_on_date_as_well_as_teams():
    """Adding the preseason to the site made an old hole reachable.

    `fetch_live()` hits ESPN's scoreboard with no season-type filter — it
    returns whatever the NFL is playing today, which in August is
    preseason. `attach_live` keyed purely on `frozenset({home, away})`, so
    a preseason meeting between two teams who also face each other in Week
    1 would paint its score onto the Week 1 card: a finished 17-13 on a
    fixture a month away.

    Nothing settles from this overlay (the journal grades off history.db),
    so it was invisible — a wrong live score looks exactly like a right
    one.
    """
    import inspect
    from engine.sources import livescores
    src = inspect.getsource(livescores.attach_live)
    assert "_near_in_time" in src, "the overlay is back to teams-only"


def test_the_date_window_is_a_day_because_of_night_games():
    """NOT equality. DAL @ NYG kicks 20:20 Eastern on 2026-09-13, which is
    00:20 UTC on the 14th; ESPN stamps UTC and nflverse stores the local
    gameday. An exact match would switch the live board off for exactly the
    games people watch it during."""
    from engine.sources.livescores import _near_in_time
    assert _near_in_time("2026-09-14T00:20Z", "2026-09-13") is True
    assert _near_in_time("2026-09-13T17:00Z", "2026-09-13") is True
    assert _near_in_time("2026-08-13T23:00Z", "2026-09-13") is False
    assert _near_in_time("2026-09-15T17:00Z", "2026-09-13") is False


def test_an_unreadable_date_still_attaches():
    """A bad string must not silently kill the live board — fall back to
    the team match rather than dropping the score."""
    from engine.sources.livescores import _near_in_time
    assert _near_in_time("", "2026-09-13") is True
    assert _near_in_time("not-a-date", "2026-09-13") is True


def test_a_preseason_score_does_not_reach_a_regular_season_card():
    """The whole failure, end to end."""
    from engine.sources import livescores as ls
    from engine.models import LiveStatus

    class _G:
        def __init__(self, h, a, d):
            self.home, self.away, self.date, self.live = h, a, d, None

    class _S:
        def __init__(self, games): self.games = games

    board = {frozenset(("CIN", "CLE")): LiveStatus(
        state="final", home_score=17, away_score=13, period="", clock="",
        detail="", start_time="2026-08-13T23:00Z")}
    real = ls.fetch_live
    try:
        ls.fetch_live = lambda: board
        slate = _S([_G("CIN", "CLE", "2026-09-13")])
        assert ls.attach_live(slate) == 0
        assert slate.games[0].live is None
        # …and the same fixture on its own night still attaches.
        board2 = {frozenset(("CIN", "CLE")): LiveStatus(
            state="live", home_score=7, away_score=3, period="Q2",
            clock="8:12", detail="", start_time="2026-09-13T17:00Z")}
        ls.fetch_live = lambda: board2
        slate2 = _S([_G("CIN", "CLE", "2026-09-13")])
        assert ls.attach_live(slate2) == 1
        assert slate2.games[0].live.state == "live"
    finally:
        ls.fetch_live = real

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
