"""The four leagues that never got their own fast clock.

Sibling to `test_live_scores.py`, which guards the MLB half of the same
fix. That file is about ONE league's scoreboard escaping the model board;
this one is about the four it left behind.

`live_build.py` named the gap in its own docstring the day it shipped:
"MLB, NFL, NBA, WNBA and CFB never got the same treatment." It fixed one.
`app.js` LIVE_FEEDS still pointed NFL at `data/recommendations.json` and
CFB at `data/cfb.json` — the model boards — so a score that changes every
play waited on a build that prices a whole slate. That is the identical
2026-08-16 bug that made MLB scores run 8-15 minutes behind.

THE PART THAT IS EASY TO GET WRONG is not the fetch, it is IDENTITY. The
front end merges a fast row onto its board row on `away@home`, keeping
the board's odds grid and live win-probability track. A key that does not
match does not raise — it drops both, silently, which is what wholesale
replacement did on 2026-08-18 ("the live probablility chart definitly
doesnt show or work"). So every league resolves its sides the way its own
board resolves them, and that is what most of this file is about.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import livescore_build as B                                  # noqa: E402
from engine.sources import livescores as L                   # noqa: E402


def _event(hab, hname, aab, aname, *, eid="401", state="in",
           situation=None, hid="1", aid="2"):
    comp = {"competitors": [
        {"homeAway": "home", "score": "21",
         "team": {"abbreviation": hab, "id": hid, "displayName": hname}},
        {"homeAway": "away", "score": "17",
         "team": {"abbreviation": aab, "id": aid, "displayName": aname}}]}
    if situation is not None:
        comp["situation"] = situation
    return {"events": [{
        "id": eid, "date": "2026-09-06T20:00Z",
        "status": {"type": {"state": state, "shortDetail": "Q2"},
                   "period": 2},
        "competitions": [comp]}]}


# --- identity, per league ---------------------------------------------------
def test_nfl_sides_are_the_nflverse_codes_the_board_carries():
    """ESPN writes WSH and LAR where nflverse writes WAS and LA."""
    r = L.parse_espn_rows(_event("WSH", "Washington Commanders",
                                 "LAR", "Los Angeles Rams"), "nfl")[0]
    assert (r["home"], r["away"]) == ("WAS", "LA"), r


def test_nba_sides_are_the_cdn_tricodes_not_espns_abbreviations():
    """`nbadata.parse_schedule_day` stores `teamTricode`, and ESPN
    disagrees with it on six of thirty teams. Resolving off the
    abbreviation would have missed a fifth of the league's merges."""
    for espn, name, want in [
            ("WSH", "Washington Wizards", "WAS"),
            ("GS", "Golden State Warriors", "GSW"),
            ("NO", "New Orleans Pelicans", "NOP"),
            ("NY", "New York Knicks", "NYK"),
            ("SA", "San Antonio Spurs", "SAS"),
            ("UTAH", "Utah Jazz", "UTA")]:
        r = L.parse_espn_rows(_event(espn, name, "BOS", "Boston Celtics"),
                              "nba")[0]
        assert r["home"] == want, (espn, name, r["home"])


def test_wnba_sides_resolve_off_the_same_kind_of_table():
    r = L.parse_espn_rows(_event("LV", "Las Vegas Aces",
                                 "NY", "New York Liberty"), "wnba")[0]
    assert (r["home"], r["away"]) == ("LVA", "NYL"), r


def test_college_keeps_the_key_its_own_board_keys_on():
    """`cfbdata._team_key` is CALLED, not copied — including its
    `espn:{id}` fallback, which is most of an opening-weekend slate."""
    r = L.parse_espn_rows(_event("MSU", "Michigan State Spartans",
                                 "", "Some FCS School", aid="77"), "cfb")[0]
    assert (r["home"], r["away"]) == ("MSU", "espn:77"), r


def test_an_unknown_name_falls_back_rather_than_dropping_the_game():
    """An expansion team or a rename must cost the card its lines, not
    its existence."""
    r = L.parse_espn_rows(_event("XYZ", "Somewhere Expansion Club",
                                 "BOS", "Boston Celtics"), "nba")[0]
    assert r["home"] == "XYZ", r


# --- the rows ---------------------------------------------------------------
def test_the_row_carries_the_event_id_every_deeper_endpoint_takes():
    r = L.parse_espn_rows(_event("KC", "Kansas City Chiefs",
                                 "BUF", "Buffalo Bills", eid="9912"), "nfl")[0]
    assert r["event_id"] == "9912"


def test_football_situation_rides_along_and_basketball_has_none():
    foot = B._row(L.parse_espn_rows(
        _event("KC", "Kansas City Chiefs", "BUF", "Buffalo Bills",
               situation={"downDistanceText": "2nd & 7 at KC 45",
                          "possession": "1"}), "nfl")[0])
    assert foot["live"]["yard_line"] == 45.0, foot
    assert foot["live"]["possession"] == "KC", foot
    hoop = B._row(L.parse_espn_rows(
        _event("BOS", "Boston Celtics", "NY", "New York Knicks"), "nba")[0])
    # ABSENT, NOT NULL. "this sport has no such thing" and "we could not
    # read it" are different facts and must not share a value.
    assert "yard_line" not in hoop["live"], hoop
    assert "possession" not in hoop["live"], hoop


def test_the_frozenset_view_still_answers_the_way_attach_live_needs():
    """`parse_espn_scoreboard` is now derived from the rows. Its callers
    must not be able to tell."""
    pay = _event("WSH", "Washington Commanders", "DAL", "Dallas Cowboys")
    got = L.parse_espn_scoreboard(pay)
    assert set(got) == {frozenset(("WAS", "DAL"))}, got
    assert got[frozenset(("WAS", "DAL"))].home_score == 21


def test_one_parse_not_two():
    """The frozenset map is a VIEW over the rows, not a second walk of
    the payload — that duplication is what forced live_build.py to
    re-read the raw MLB payload to recover home and away."""
    import inspect
    src = inspect.getsource(L.parse_espn_scoreboard)
    assert "parse_espn_rows(" in src, src
    assert "competitors" not in src, "it walks the payload again"


# --- the build --------------------------------------------------------------
def test_every_configured_league_is_reachable_by_name():
    assert set(L.ESPN_SCOREBOARD) == {"nfl", "cfb", "nba", "wnba"}
    for lg, url in L.ESPN_SCOREBOARD.items():
        assert url.startswith("https://site.api.espn.com/"), (lg, url)
        assert url.endswith("/scoreboard"), (lg, url)


def test_an_unreachable_feed_is_an_empty_board_that_says_why():
    """Never raise: this runs every few seconds beside a live site. And
    never return a silent empty list — an empty board and a refused
    request look identical to every reader downstream, which is the
    failure shape this repo keeps finding."""
    real = B.fetch_rows

    def boom(league, ttl=20):
        from engine.sources.fetch import DataUnavailable
        raise DataUnavailable("host refused")
    B.fetch_rows = boom
    try:
        got = B.build("nfl")
    finally:
        B.fetch_rows = real
    assert got["games"] == []
    assert "unreachable" in got["note"], got
    assert "host refused" in got["note"], got


def test_an_unreadable_feed_is_also_named_rather_than_swallowed():
    real = B.fetch_rows

    def boom(league, ttl=20):
        raise ValueError("not json")
    B.fetch_rows = boom
    try:
        got = B.build("cfb")
    finally:
        B.fetch_rows = real
    assert got["games"] == []
    assert "ValueError" in got["note"], got


def test_the_write_is_atomic_and_lands_where_the_page_looks(tmp=None):
    import tempfile
    real = B.fetch_rows
    B.fetch_rows = lambda league, ttl=20: L.parse_espn_rows(
        _event("KC", "Kansas City Chiefs", "BUF", "Buffalo Bills"), league)
    try:
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            B.write("nfl", out)
            f = out / "live_nfl.json"
            assert f.is_file()
            assert not list(out.glob("*.tmp")), "the temp file was left behind"
            blob = json.loads(f.read_text())
            assert blob["league"] == "nfl"
            assert blob["games"][0]["home"] == "KC"
    finally:
        B.fetch_rows = real


def test_no_prices_ever_reach_this_file():
    """Copied from live_build.py's contract: scores and game state only.
    A score is a public fact and engine/gate.py has no reason to redact
    one — which is only true while nothing priced rides along."""
    r = B._row(L.parse_espn_rows(
        _event("KC", "Kansas City Chiefs", "BUF", "Buffalo Bills"), "nfl")[0])
    flat = json.dumps(r)
    for banned in ("odds", "edge", "ev_per_unit", "stake", "book", "grade"):
        assert banned not in flat, (banned, flat)


# --- the registry ------------------------------------------------------------
def test_every_scoreboard_the_builder_writes_is_registered_with_the_gate():
    """THE ONE THAT ONLY THE DROPLET COULD CATCH, until now. engine/gate.py
    keeps a hand-listed registry of every board the site can build; a
    file on disk it has never heard of fails `test_gate` — but only on a
    machine that has BUILT the file, and the dev container never runs the
    fast loop. live_mlb.json shipped that way once (its registry comment
    tells the story); live_{nfl,cfb,nba,wnba}.json shipped the same way
    on 2026-09-04 and cost a three-hour deploy gate. Derived from the
    builder's own league table so the next league cannot repeat it."""
    from engine import gate
    for lg in L.ESPN_SCOREBOARD:
        name = f"live_{lg}.json"
        assert name in gate.KNOWN_BOARDS, f"{name} is built and unregistered"
        # Free, like live_mlb.json: an unknown board is treated as gated,
        # which would put a public scoreboard behind the paywall.
        assert name in gate.FREE_FILES, f"{name} is registered but gated"


# --- the wiring -------------------------------------------------------------
def _app():
    return (ROOT / "web" / "js" / "app.js").read_text()


def test_the_page_reads_all_five_fast_feeds():
    src = _app()
    i = src.index("const LIVE_FAST = {")
    seg = src[i:i + 400]
    for lg in ("mlb", "nfl", "cfb", "nba", "wnba"):
        assert f'data/live_{lg}.json' in seg, (lg, seg)


def test_the_launcher_actually_runs_it():
    src = (ROOT / "launch.py").read_text()
    assert "_live_scores_refresher" in src
    assert 'target=_live_scores_refresher' in src, \
        "the refresher is defined and never started"
    # TO THE END OF THE FUNCTION, not a byte count. A window guessed in
    # characters passes or fails on how long the docstring is, which is
    # not what is being asserted.
    i = src.index("def _live_scores_refresher")
    seg = src[i:src.index("\ndef ", i + 1)]
    assert '"livescore_build.py"' in seg, seg[:200]
    assert "LIVE_FAST_S" in seg and "LIVE_IDLE_S" in seg, \
        "it no longer chooses its cadence from what came back"


def test_the_status_page_can_see_them_go_stale():
    src = _app()
    i = src.index("const STATUS_BOARDS = [")
    seg = src[i:i + 1400]
    for lg in ("nfl", "cfb", "nba", "wnba"):
        assert f'"live_{lg}.json"' in seg, (lg, seg)


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
