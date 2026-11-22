"""The NFL's inactives: the board read fresh in their window, and ESPN's other feeds timed against it (step ACH,
22 November 2026).

Ethan: "find a faster inactives source than ESPN's injury board". On the Sunday the 4:25 games' lists reached our
picks 25 to 42 minutes after they came out, up to ten of them our copy's age. What these hold:

  * from 100 minutes before an NFL kickoff to 5 after (off the scoreboard copy the score loop keeps), the NFL
    board's copy is believed a minute, not ten; other leagues, other hours and the switch's off keep ten;
  * the watcher reads, while a game is in its window, the board and in turn the game's summaries, gamecast and
    both clubs' rosters, and finds a man marked inactive whatever the page's shape: his ``active`` false, his
    ``didNotPlay`` true, a status word or a sentence that says it, with his club where the page names it;
  * it notes each man's first sighting in each feed and sets it against the board's, at the middle of each
    read's gap, and publishes counts and times only, never a name or ESPN's words;
  * out of a window it asks nothing; it never raises; the launcher starts it;
  * after each other board's build the sweep builds the NFL again when a held game's picks are due, its post time
    passed with both clubs' lists on the board, or its deadline passed: they post then, not at the next sweep.

    python3 tests/test_the_inactives_are_read_fresh_and_timed.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import inactiveswatch as W                             # noqa: E402
from engine.sources import espninjuries as E                      # noqa: E402

T0 = dt.datetime(2026, 11, 23, 1, 20, tzinfo=dt.timezone.utc).timestamp()     # Vikings at 49ers, 8:20 PM ET


def _fresh():
    W._STATE.clear()
    W._TURN[0] = 0
    W._PRUNED[0] = ""


def test_the_board_is_believed_a_minute_in_the_window_only():
    ks = [T0]
    assert E.ttl_for("nfl", T0 - 100 * 60, ks) == 60 and E.ttl_for("nfl", T0 + 5 * 60, ks) == 60
    assert E.ttl_for("nfl", T0 - 101 * 60, ks) == E.INJURY_TTL == 600, "before the window"
    assert E.ttl_for("nfl", T0 + 6 * 60, ks) == 600, "after it"
    assert E.ttl_for("nba", T0 - 60 * 60, ks) == 600, "another league"
    os.environ[E.INACTIVES_FRESH_ENV] = "off"
    try:
        assert E.ttl_for("nfl", T0 - 60 * 60, ks) == 600, "the switch off"
    finally:
        os.environ.pop(E.INACTIVES_FRESH_ENV, None)
    copy = Path(tempfile.mkdtemp()) / "espn_nfl_scoreboard.json"
    copy.write_text(json.dumps({"events": [{"id": "1", "date": "2026-11-23T01:20Z"}, {"id": "2"}, "x"]}),
                    encoding="utf-8")
    assert E.nfl_kickoffs(copy) == [T0], "read off the copy's own dates"
    assert E.nfl_kickoffs(copy.with_name("none.json")) == [], "no copy: no window"
    src = (ROOT / "engine" / "sources" / "espninjuries.py").read_text(encoding="utf-8")
    assert "ttl=ttl_for(league), user_agent=DEFAULT_AGENT)" in src


def test_a_man_is_found_inactive_whatever_the_pages_shape():
    ids = {"25": "SF", "16": "MIN"}
    roster = {"team": {"$ref": "http://x/teams/25?lang=en"},
              "entries": [{"playerId": 11, "displayName": "Jordan Mason", "jersey": "24", "active": False},
                          {"playerId": 12, "displayName": "Kyle Juszczyk", "jersey": "44", "active": True},
                          {"playerId": 13, "jersey": "9", "active": False,
                           "athlete": {"$ref": "http://x/athletes/13?lang=en"}}]}
    found, shapes = W.marks(roster, ids)
    assert found == {("SF", "entries[].active"): {"jordan mason": "11", "id:13": "13"}}, found
    assert shapes == {"entries[].active": {"false": 2, "true": 1}}
    summary = {"injuries": [{"team": {"id": "16", "abbreviation": "MIN"},
                             "injuries": [{"athlete": {"id": "21", "displayName": "C.J. Ham"}, "status": "Out",
                                           "shortComment": "Ham (knee) is inactive for Sunday's game against "
                                                           "the 49ers."}]}],
               "rosters": [{"team": {"abbreviation": "WSH"},
                            "roster": [{"athlete": {"displayName": "Noah Brown", "id": "31"},
                                        "status": {"type": {"name": "INACTIVE"}}, "didNotPlay": False},
                                       {"athlete": {"displayName": "Zach Ertz", "id": "32"}, "didNotPlay": True}]}],
               "news": {"articles": [{"headline": "Ham is inactive for Sunday's game against the 49ers, and more"}]},
               "header": {"competitions": [{"competitors": [{"team": {"id": "25", "displayName": "San Francisco "
                                                                      "49ers", "location": "San Francisco",
                                                                      "abbreviation": "SF", "isActive": True}}]}]}}
    found, shapes = W.marks(summary, ids)
    assert found == {("MIN", "injuries[].injuries[].shortComment=says"): {"c j ham": "21"},
                     ("WAS", "rosters[].roster[].status.type.name=word"): {"noah brown": "31"},
                     ("WAS", "rosters[].roster[].didNotPlay"): {"zach ertz": "32"}}, found
    assert shapes["news.articles[].headline=says"] == {"inactive": 1}, "a headline is no man's mark"
    assert W.marks({"a": [1, "b", None]}) == ({}, {})


def test_the_board_reads_its_inactives_as_the_build_does():
    games = [{"event": "401", "home": "SF", "away": "MIN", "home_id": "25", "away_id": "16", "t0": T0}]
    stamp = dt.datetime.fromtimestamp(T0 - 85 * 60, dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    early = dt.datetime.fromtimestamp(T0 - 30 * 3600, dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    rows = [{"team": "San Francisco 49ers", "player": "Jordan Mason", "status": "Out", "date": stamp,
             "comment": "Mason (ankle) is inactive for Sunday's game against the Vikings.",
             "face": "https://a.espncdn.com/i/headshots/nfl/players/full/11.png"},
            {"team": "San Francisco 49ers", "player": "Old Man", "status": "Out", "date": early,
             "comment": "Man is inactive for Thursday's game."},
            {"team": "Minnesota Vikings", "player": "C.J. Ham", "status": "Questionable", "date": stamp,
             "comment": "Ham is questionable."}]
    assert W.board_marks(rows, games, T0 - 80 * 60) == {("SF", "board"): {"jordan mason": ("11", T0 - 85 * 60)}}


def _scoreboard(*starts):
    teams = [("SF", "MIN", "25", "16"), ("DET", "GB", "8", "9"), ("PHI", "DAL", "21", "6"), ("KC", "LV", "12", "13")]
    rows = []
    for i, t in enumerate(starts):
        h, a, hid, aid = teams[i]
        iso = dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
        rows.append({"event_id": f"40{i}", "home": h, "away": a, "home_id": hid, "away_id": aid,
                     "live": types.SimpleNamespace(start_time=iso, state="pre")})
    return lambda: rows


def test_the_watch_times_each_feed_against_the_board_and_publishes_no_names():
    _fresh()
    root, out = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp()) / "inactives_watch.json"
    now = [T0 - 90 * 60]
    asked = []
    mason = {"team": {"$ref": "http://x/teams/25"},
             "entries": [{"playerId": 11, "displayName": "Jordan Mason", "jersey": "24", "active": False}]}

    def get(url):
        asked.append(url)
        if "competitors/25/roster" in url:
            return "ok", mason, 900
        if "cdn.espn.com" in url:
            return "HTTP 404", None, 0
        return "ok", {"header": {}}, 100

    board = {"rows": [], "t": now[0] - 10}
    filed = dt.datetime.fromtimestamp(now[0] + 50, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def read_board():
        return board["rows"], board["t"]

    kw = dict(now=lambda: now[0], scoreboard=_scoreboard(T0), board=read_board, get=get, root=root, out=out)
    assert W.watch_once(**kw) == W.TICK_S
    assert len(asked) == 5 and sum("roster" in u for u in asked) == 2, asked
    board["rows"] = [{"team": "San Francisco 49ers", "player": "Jordan Mason", "status": "Out", "date": filed,
                      "comment": "Mason is inactive for Sunday's game.",
                      "face": "https://a.espncdn.com/i/headshots/nfl/players/full/11.png"}]
    board["t"] = now[0] + 55
    now[0] += 60
    assert W.watch_once(**kw) == W.TICK_S
    doc = json.loads(out.read_text(encoding="utf-8"))
    g = doc["games"][0]
    assert g["game"] == "MIN@SF" and g["kickoff"] == "2026-11-23T01:20:00Z"
    sf = g["clubs"]["SF"]
    # The roster showed him at the first read (no gap before it: its middle is the read); the board's copy at
    # +55 s, 65 s after the one before it, its middle +22.5 s; filed +50 s.
    assert sf["board"]["n"] == 1 and sf["board"]["filed_first"] == filed
    assert sf["core_roster"] == {"n": 1, "first": W._iso(T0 - 90 * 60), "both": 1, "ahead_min": 0.4,
                                 "ahead_of_filed_min": 0.8,
                                 "places": {"entries[].active": {"n": 1, "first": W._iso(T0 - 90 * 60), "both": 1,
                                                                 "ahead_min": 0.4, "ahead_of_filed_min": 0.8}}}, sf
    assert g["feeds"]["gamecast"]["status"] == "HTTP 404" and g["feeds"]["core_roster"]["reads"] == 4
    assert g["feeds"]["core_roster"]["shapes"] == {"entries[].active": {"false": 1}}
    text = out.read_text(encoding="utf-8")
    assert "mason" not in text.lower() and "inactive for" not in text, "counts and times only"
    kept = json.loads((root / "2026-11-22.json").read_text(encoding="utf-8"))
    assert "jordan mason" in kept["games"]["400"]["feeds"]["board"]["clubs"]["SF"]["men"], "the box keeps the names"
    assert kept["games"]["400"]["feeds"]["core_roster"]["clubs"]["SF"]["counts"] == [[T0 - 90 * 60, 1]], \
        "the other club's roster page says nothing about this club's count"
    _fresh()
    lines = W.report_lines(W.report(kept))
    assert any("core_roster" in ln and "+0.4 min against the board" in ln for ln in lines), lines


def test_each_place_of_a_page_is_timed_apart():
    # On the Sunday (the 4:25 games, read by the box): the core API's roster had `active` false for about 58 men a
    # club and `didNotPlay` true for its seven inactives. The place that marks the list is timed on its own.
    _fresh()
    root, out = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp()) / "w.json"
    now = [T0 - 90 * 60]
    flags = {"dnp": False}

    def get(url):
        if "competitors/25/roster" not in url:
            return "HTTP 404", None, 0
        return "ok", {"team": {"$ref": "http://x/teams/25"}, "entries": [
            {"playerId": 1, "displayName": "Jordan Mason", "jersey": "24", "active": False, "didNotPlay": flags["dnp"]},
            {"playerId": 2, "displayName": "George Kittle", "jersey": "85", "active": False, "didNotPlay": False}]}, 1

    kw = dict(now=lambda: now[0], scoreboard=_scoreboard(T0), board=lambda: ([], T0 - 100 * 60), get=get,
              root=root, out=out)
    W.watch_once(**kw)
    flags["dnp"] = True
    now[0] += 60
    W.watch_once(**kw)
    places = json.loads(out.read_text(encoding="utf-8"))["games"][0]["clubs"]["SF"]["core_roster"]["places"]
    assert places["entries[].active"]["n"] == 2 and places["entries[].active"]["first"] == W._iso(T0 - 90 * 60)
    assert places["entries[].didNotPlay"] == {"n": 1, "first": W._iso(T0 - 89 * 60), "both": 0}, places


def test_a_full_slate_is_read_in_turn_and_nothing_is_asked_out_of_a_window():
    _fresh()
    root, out = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp()) / "w.json"
    asked = []

    def get(url):
        asked.append(url)
        return "ok", {}, 2

    kw = dict(scoreboard=_scoreboard(T0, T0, T0, T0), board=lambda: ([], T0), get=get, root=root, out=out)
    W.watch_once(now=lambda: T0 - 60 * 60, **kw)
    assert len(asked) == W.PER_TICK == 16
    W.watch_once(now=lambda: T0 - 59 * 60, **kw)
    assert len(asked) == 32 and len(set(asked)) == 20, "the second tick goes on where the first stopped"
    asked.clear()
    assert W.watch_once(now=lambda: T0 - 3 * 3600, **kw) == W.IDLE_S and asked == [], "out of the window"
    assert W.watch_once(now=lambda: T0 + 21 * 60, **kw) == W.IDLE_S and asked == []

    def down():
        raise OSError("refused")
    assert W.watch_once(now=lambda: T0, scoreboard=down, root=root, out=out) == W.IDLE_S, "never raises"
    os.environ[W.ENV] = "off"
    try:
        assert W.watch_once(now=lambda: T0 - 60 * 60, **kw) == W.IDLE_S and asked == []
    finally:
        os.environ.pop(W.ENV, None)


def _lists(clubs, filed):
    stamp = dt.datetime.fromtimestamp(filed, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    names = {"SF": "San Francisco 49ers", "MIN": "Minnesota Vikings"}
    return [{"team": names[c], "player": f"{c} Man {i}", "status": "Out", "date": stamp,
             "comment": f"Man {i} is inactive for Sunday's game."} for c in clubs for i in range(3)]


def test_a_held_nfl_game_is_built_again_once_it_is_due():
    import launch as L
    held = {"home": "SF", "away": "MIN", "kickoff": "20:20", "date": "2026-11-22", "post_at": "2026-11-23T00:05:00Z"}
    board = {"game_parlays": {"games": [held, dict(held, home="DET", away="GB", kept=True),
                                        dict(held, home="PHI", away="DAL", posted_before=True)]}}
    at = lambda m: dt.datetime.fromtimestamp(T0 - m * 60, dt.timezone.utc)                   # noqa: E731
    both, one = _lists(("SF", "MIN"), T0 - 85 * 60), _lists(("SF",), T0 - 85 * 60)
    assert L._nfl_due_now(at(80), board, both) == [], "before its post time, lists or not"
    assert L._nfl_due_now(at(74), board, both) == ["MIN@SF"], "its post time passed and both lists in"
    assert L._nfl_due_now(at(74), board, one) == [], "one club's list: it waits"
    assert L._nfl_due_now(at(49), board, []) == ["MIN@SF"], "its deadline"
    assert L._nfl_due_now(at(74), {"game_parlays": {"games": [dict(held, post_at=None)]}}, both) == [], "posted"
    assert L._nfl_due_now(at(74), {"x": 1}, both) == [] and L._nfl_due_now(at(74), [], both) == []
    built = []
    was = L.refresh_nfl, L._resting_board, L._note_board, L._NFL_DUE_LAST[0]
    L.refresh_nfl = lambda quiet=False: built.append(quiet) or True
    L._resting_board = lambda name: False
    L._note_board = lambda name, ok: None
    try:
        L._NFL_DUE_LAST[0] = 0.0
        assert L._nfl_when_due(True, due=["MIN@SF"]) == ["MIN@SF"] and built == [True]
        assert L._nfl_when_due(True, due=["MIN@SF"]) == [] and built == [True], "once a gap"
        L._NFL_DUE_LAST[0] = 0.0
        assert L._nfl_when_due(True, due=[]) == [] and built == [True], "nothing due"
        os.environ[L.NFL_DUE_ENV] = "off"
        assert L._nfl_when_due(True, due=["MIN@SF"]) == [] and built == [True], "the switch off"
    finally:
        os.environ.pop(L.NFL_DUE_ENV, None)
        L.refresh_nfl, L._resting_board, L._note_board, L._NFL_DUE_LAST[0] = was
    src = (ROOT / "launch.py").read_text(encoding="utf-8")
    body = src[src.index("def refresh_all("):src.index("    # In SPORT_PRIORITY order", src.index("def refresh_all("))]
    assert 'if step != "nfl" and _nfl_when_due(quiet):' in body, "asked after each other board's build"


def test_the_launcher_starts_it():
    src = (ROOT / "launch.py").read_text(encoding="utf-8")
    assert "def _inactives_watcher() -> None:" in src and "wait = _iw.watch_once()" in src
    assert 'threading.Thread(target=_inactives_watcher, daemon=True, name="inactiveswatch").start()' in src
    assert src.index('name="inactiveswatch").start()') < src.index('name="reportwatch").start()')


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    fails = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as exc:                              # noqa: BLE001
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed.")
    sys.exit(1 if fails else 0)
