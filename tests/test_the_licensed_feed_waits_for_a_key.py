"""The licensed scores feed and its timing, off until there is a key
(engine/sources/balldontlie, engine/feedlatency; RS6).

The live scores come from ESPN's public scoreboard, which nobody licensed
to us. BALLDONTLIE sells the same scores under a key. The paper's item: a
client, and a logger that reads both feeds side by side, the switch only
where the licensed one is as fast or faster. What these hold:

  * without BALLDONTLIE_API_KEY nothing runs: `enabled()` is False, a call
    says how to set the key and never names one, and the launcher starts
    no thread;
  * the client asks the way BALLDONTLIE's own SDK does: the key bare in
    Authorization, lists as name[], cursor pages, 401 and 429 told apart;
  * each league's game comes out in one shape (NBA and NFL's visitor team,
    MLB's away team and its runs), its state read from the feed's words;
  * the logger writes a sighting the first time each feed shows a new
    score, ESPN's at its fetch time, never a copy already read, nothing
    before the first score, and asks BALLDONTLIE nothing while ESPN shows
    no live game; a refused key puts it to sleep, a 429 pauses it;
  * the report pairs the scores both showed, compares the middles of each
    feed's reading gaps, and gives the verdict only past MIN_PAIRS.

Run directly: `python3 tests/test_the_licensed_feed_waits_for_a_key.py`
"""
import io
import json
import os
import sys
import tempfile
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.pop("BALLDONTLIE_API_KEY", None)

from engine import feedlatency as FL                              # noqa: E402
from engine.models import LiveStatus                              # noqa: E402
from engine.sources import balldontlie as B                       # noqa: E402

READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731
KEY = "test-key-not-real"


class _Resp:
    def __init__(self, payload, headers=None):
        self._b = json.dumps(payload).encode()
        self.headers = headers or {}

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _opener(pages, seen):
    def op(req, timeout=None):
        seen.append(req)
        return _Resp(pages.pop(0), {"X-RateLimit-Remaining": "59"})
    return op


def test_without_a_key_nothing_runs_and_nothing_names_a_key():
    os.environ.pop(B.KEY_ENV, None)
    B.load_local_secrets = lambda *a, **k: None          # the box's own files are not this test's
    assert B.enabled() is False
    try:
        B.games("nba", ["2026-11-05"])
        raise AssertionError("a call without a key must refuse")
    except B.BDLUnavailable as exc:
        assert "setenv.sh BALLDONTLIE_API_KEY" in str(exc) and "ESPN" in str(exc)
    src = READ("launch.py")
    start = src.index("from engine.sources import balldontlie as _bdl")
    assert "if _bdl.enabled():" in src[start:start + 200], "no key, no thread"
    assert src.index("if _bdl.enabled():", start) < src.index("target=_feed_latency_watcher", start)
    assert B.main([]) == 0


def test_the_client_asks_the_way_the_sdk_does():
    seen = []
    pages = [{"data": [{"id": 1}], "meta": {"next_cursor": 7}}, {"data": [{"id": 2}], "meta": {}}]
    rows = B.pages("nba/v1/games", {"dates": ["2026-11-05", "2026-11-04"]}, key=KEY, opener=_opener(pages, seen))
    assert [r["id"] for r in rows] == [1, 2]
    req = seen[0]
    assert req.get_header("Authorization") == KEY, "the key goes bare, as the SDK sends it"
    assert req.full_url.startswith("https://api.balldontlie.io/nba/v1/games?")
    assert "dates%5B%5D=2026-11-05" in req.full_url and "dates%5B%5D=2026-11-04" in req.full_url
    assert "per_page=100" in req.full_url and "cursor" not in req.full_url, "no cursor on the first page"
    assert "cursor=7" in seen[1].full_url
    assert B.query({"a": None, "b": [1, 2], "c": "x"}) == [("b[]", "1"), ("b[]", "2"), ("c", "x")]

    def refuse(code):
        def op(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, code, "no", {}, io.BytesIO(b"{}"))
        return op
    for code, kind, words in ((401, B.BDLUnavailable, "refused the key"), (429, B.BDLRateLimited, "rate")):
        try:
            B.get("nba/v1/games", {}, key=KEY, opener=refuse(code))
            raise AssertionError(code)
        except kind as exc:
            assert words in str(exc) and KEY not in str(exc), exc
    lines = B.probe(key=KEY, opener=lambda req, timeout=None: _Resp({"data": []}, {"X-RateLimit-Limit": "60"}),
                    today="2026-11-05")
    assert len(lines) == 4 and all("ok, 0 row(s)" in ln and "x-ratelimit-limit: 60" in ln for ln in lines), lines
    assert not any(KEY in ln for ln in lines)


def test_each_leagues_game_in_one_shape():
    nba = B.normalize("nba", {"id": 9, "date": "2026-11-05", "status": "3rd Qtr", "period": 3, "time": "5:31",
                              "postseason": False, "home_team_score": 77, "visitor_team_score": 70,
                              "home_team": {"abbreviation": "NYK", "full_name": "New York Knicks"},
                              "visitor_team": {"abbreviation": "BOS", "full_name": "Boston Celtics"}})
    assert (nba["away"], nba["home"], nba["away_score"], nba["home_score"], nba["state"], nba["clock"]) == \
        ("BOS", "NYK", 70, 77, "live", "5:31")
    nfl = B.normalize("nfl", {"id": 3, "date": "2026-11-08T18:00:00.000Z", "status": "Final", "week": 10,
                              "home_team_score": 24.0, "visitor_team_score": 20.0,
                              "home_team": {"abbreviation": "KC", "full_name": "Kansas City Chiefs"},
                              "visitor_team": {"abbreviation": "BUF", "full_name": "Buffalo Bills"}})
    assert nfl["date"] == "2026-11-08" and nfl["state"] == "final" and nfl["home_score"] == 24
    mlb = B.normalize("mlb", {"id": 4, "date": "2026-07-01", "status": "Top 5th", "period": 5,
                              "home_team": {"abbreviation": "NYY", "display_name": "New York Yankees"},
                              "away_team": {"abbreviation": "BOS", "display_name": "Boston Red Sox"},
                              "home_team_data": {"runs": 3}, "away_team_data": {"runs": 2}})
    assert (mlb["away"], mlb["away_score"], mlb["home_score"], mlb["state"]) == ("BOS", 2, 3, "live")
    assert B.state_of("2026-11-06T00:30:00Z", 0) == "pre" and B.state_of("Halftime", None) == "live"
    try:
        B.games("wnba", ["2026-11-05"], key=KEY)
        raise AssertionError("not in the SDK")
    except B.BDLUnavailable as exc:
        assert "nba, nfl, mlb" in str(exc)


def _reset():
    B.RATE.clear()
    FL._LAST.clear()
    FL._SEEN_AT.clear()
    FL._SEEDED.clear()
    FL._PAUSE[0] = 0.0
    FL._OFF[0] = False
    FL._PRUNED[0] = ""
    FL._LAST_ON[0] = []


def _row(away_score, home_score, state="live"):
    return {"away": "BOS", "home": "NYK", "away_name": "Boston Celtics", "home_name": "New York Knicks",
            "live": LiveStatus(state=state, away_score=away_score, home_score=home_score, period="Q3",
                               clock="5:31", start_time="2026-11-06T00:30:00Z")}


def _bdl(away_score, home_score):
    return {"away": "BOS", "home": "NYK", "away_name": "Boston Celtics", "home_name": "New York Knicks",
            "away_score": away_score, "home_score": home_score, "period": 3, "clock": "5:20"}


def test_the_logger_writes_each_feeds_first_sighting_of_a_score():
    _reset()
    root = Path(tempfile.mkdtemp())
    asked = []
    seq = iter([
        # (espn rows, espn fetched at, bdl games, bdl answered at)
        ([_row(0, 0)], 1000.0, [_bdl(0, 0)], 1001.0),       # before the first score: nothing
        ([_row(2, 0)], 1008.0, [_bdl(0, 0)], 1009.0),       # ESPN shows 2-0 first
        ([_row(2, 0)], 1008.0, [_bdl(2, 0)], 1017.0),       # the same ESPN copy: not read again
        ([_row(2, 3)], 1024.0, [_bdl(2, 3)], 1023.0),       # BALLDONTLIE sooner by a second
    ])
    cur = {}

    def espn(sport):
        if sport != "nba":
            return [], 0.0
        cur["s"] = next(seq)
        return cur["s"][0], cur["s"][1]

    def bdl(sport, dates):
        asked.append((sport, dates))
        return cur["s"][2], cur["s"][3]
    waits = [FL.watch_once(espn=espn, bdl=bdl, root=root, log=lambda *_: None) for _ in range(4)]
    assert waits == [FL.every_s()] * 4
    assert all(a == ("nba", ["2026-11-05"]) for a in asked), "the game's own Eastern date"
    recs = FL.read_day("2026-11-05", root)
    got = [(r["feed"], tuple(r["score"]), r["t"], r["iv"]) for r in recs]
    assert got == [("espn", (2, 0), 1008.0, 8.0), ("bdl", (2, 0), 1017.0, 8.0),
                   ("espn", (2, 3), 1024.0, 16.0), ("bdl", (2, 3), 1023.0, 6.0)], got
    assert all(r["game"] == "2026-11-05:BOS@NYK" for r in recs)
    # A restart does not write today's last scores again.
    FL._LAST.clear()
    FL._SEEDED.clear()
    FL._seed("2026-11-05", root)
    assert FL._LAST[("espn", "2026-11-05:BOS@NYK")][0] == (2, 3)


def test_nothing_is_asked_with_no_live_game_and_a_refusal_or_a_429_backs_off():
    _reset()
    root = Path(tempfile.mkdtemp())
    asked = []
    w = FL.watch_once(espn=lambda s: ([_row(1, 0, state="final")], 5.0),
                      bdl=lambda s, d: asked.append(s) or ([], 6.0), root=root)
    assert w == FL.IDLE_S and asked == [], "no live game: BALLDONTLIE is not asked"

    def limited(s, d):
        raise B.BDLRateLimited("429")
    t = [5000.0]
    FL.watch_once(espn=lambda s: ([_row(2, 0)], t[0]), bdl=limited, now=lambda: t[0], root=root)
    assert FL._PAUSE[0] == 5000.0 + FL.BACKOFF_S
    FL.watch_once(espn=lambda s: ([_row(2, 0)], t[0]), bdl=lambda s, d: asked.append(s) or ([], t[0]),
                  now=lambda: t[0] + 10, root=root)
    assert asked == [], "paused after a 429"

    def refused(s, d):
        raise B.BDLUnavailable("BALLDONTLIE refused the key (401). Check BALLDONTLIE_API_KEY.")
    _reset()
    logs = []
    FL.watch_once(espn=lambda s: ([_row(2, 0)], 1.0), bdl=refused, root=root, log=logs.append)
    assert FL._OFF[0] is True and logs and "Asleep" in logs[0]
    assert FL.watch_once(espn=lambda s: ([_row(2, 0)], 2.0), bdl=lambda s, d: asked.append(s) or ([], 2.0),
                         root=root) == FL.IDLE_S and asked == []


def test_codes_or_names_match_the_two_feeds_games():
    row = {"home": "LA", "away": "WAS", "home_name": "Los Angeles Rams", "away_name": "Washington Commanders"}
    assert FL.match("nfl", row, [{"home": "LAR", "away": "WSH", "home_name": "", "away_name": ""}])
    assert FL.match("nfl", row, [{"home": "X", "away": "Y", "home_name": "Los Angeles Rams",
                                  "away_name": "Washington Commanders"}])
    assert FL.match("nba", {"home": "GSW", "away": "NYK"}, [{"home": "GS", "away": "NY"}])
    assert FL.match("nba", {"home": "GSW", "away": "NYK"}, [{"home": "NYK", "away": "GSW"}]) is None


def test_the_timer_paces_itself_to_the_plans_own_rate():
    """Ethan's probe on the box, 2026-11-05: the free key allows 5 requests a
    minute, and the timer asked every 8 s. It reads the plan's limit off the
    answers and keeps to 80% of it across the live leagues."""
    _reset()
    assert FL.every_s(1) == FL.FAST_S, "no limit heard yet: the score loop's own rhythm"
    B.note_rate({"X-RateLimit-Limit": "5", "X-RateLimit-Remaining": "4", "X-RateLimit-Reset": "1793918129"})
    assert B.RATE == {"limit": 5, "remaining": 4, "reset": 1793918129.0}
    assert FL.every_s(1) == 15.0 and FL.every_s(2) == 30.0
    B.note_rate({"x-ratelimit-limit": "600"})
    assert FL.every_s(1) == FL.FAST_S and FL.every_s(2) == FL.FAST_S
    B.note_rate({"x-ratelimit-reset": "20", "x-ratelimit-limit": "five"})
    assert 0 < B.RATE["reset"] - __import__("time").time() <= 20.5 and B.RATE["limit"] == 600, \
        "a reset in seconds from now, and a bad number leaves the old one"
    _reset()
    B.note_rate({"x-ratelimit-limit": "5"})
    nba_only = lambda s: ([_row(2, 0)], 1.0) if s == "nba" else ([], 0.0)   # noqa: E731
    both = lambda s: ([_row(2, 0)], 1.0)                                       # noqa: E731
    assert FL.watch_once(espn=nba_only, bdl=lambda s, d: ([], 1.0), root=Path(tempfile.mkdtemp())) == 15.0
    assert FL.watch_once(espn=both, bdl=lambda s, d: ([], 1.0), root=Path(tempfile.mkdtemp())) == 30.0


def test_a_429_waits_for_the_minute_and_espn_is_still_read():
    _reset()
    root = Path(tempfile.mkdtemp())
    t = [5000.0]
    B.RATE["reset"] = 5040.0

    def limited(s, d):
        raise B.BDLRateLimited("429")
    FL.watch_once(espn=lambda s: ([_row(2, 0)], t[0]) if s == "nba" else ([], 0.0), bdl=limited,
                  now=lambda: t[0], root=root)
    assert FL._PAUSE[0] == 5040.0, "until the plan's minute turns over"
    asked = []
    t[0] = 5010.0
    FL.watch_once(espn=lambda s: ([_row(2, 3)], t[0]) if s == "nba" else ([], 0.0),
                  bdl=lambda s, d: asked.append(s) or ([_bdl(2, 3)], t[0]), now=lambda: t[0], root=root)
    assert asked == [], "paused"
    recs = FL.read_day("2026-11-05", root)
    assert [(r["feed"], tuple(r["score"])) for r in recs] == [("espn", (2, 0)), ("espn", (2, 3))], \
        "ESPN's sightings go on while BALLDONTLIE waits"
    t[0] = 5041.0
    FL.watch_once(espn=lambda s: ([_row(2, 3)], t[0]) if s == "nba" else ([], 0.0),
                  bdl=lambda s, d: asked.append(s) or ([_bdl(2, 3)], t[0]), now=lambda: t[0], root=root)
    assert asked == ["nba"] and FL.read_day("2026-11-05", root)[-1]["feed"] == "bdl"


def test_the_probe_says_a_plan_without_an_endpoint_is_not_a_bad_key():
    def op(req, timeout=None):
        if "box_scores/live" in req.full_url:
            raise urllib.error.HTTPError(req.full_url, 401, "no", {}, io.BytesIO(b"{}"))
        return _Resp({"data": [{"id": 1, "status_state": "pre"}]}, {"X-RateLimit-Limit": "5"})
    lines = B.probe(key=KEY, opener=op, today="2026-11-05")
    assert lines[-1] == "nba/v1/box_scores/live: not in this key's plan (401); the key itself works", lines[-1]
    assert all("ok, 1 row(s)" in ln for ln in lines[:3])

    def refuse_all(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "no", {}, io.BytesIO(b"{}"))
    assert all("refused the key" in ln for ln in B.probe(key=KEY, opener=refuse_all, today="2026-11-05"))
    assert B.state_of("7:00 pm ET", 0, "in_progress") == "live" and B.state_of("", 4, "post") == "final"
    assert B.state_of("Q2 5:00", 2, "") == "live" and B.state_of("x", 0, "pre") == "pre"


def _write(root, recs):
    p = root / "2026-11-05.jsonl"
    with open(p, "a", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r) + "\n")


def test_the_report_compares_the_middles_and_waits_for_enough():
    root = Path(tempfile.mkdtemp())
    recs = []
    for i in range(FL.MIN_PAIRS):
        # ESPN read every 8 s, BALLDONTLIE every 16: BALLDONTLIE's raw time
        # looks 4 s late, but the middles say the two published together.
        g, sc = f"2026-11-05:G{i}@H", [i + 1, 0]
        recs += [{"t": 100.0 + i, "iv": 8.0, "feed": "espn", "sport": "nba", "game": g, "score": sc},
                 {"t": 104.0 + i, "iv": 16.0, "feed": "bdl", "sport": "nba", "game": g, "score": sc}]
    recs.append({"t": 1.0, "iv": None, "feed": "espn", "sport": "nba", "game": "2026-11-05:G0@H", "score": [99, 0]})
    _write(root, recs)
    rep = FL.report(days=1, today="2026-11-05", root=root)["nba"]
    assert rep["n"] == FL.MIN_PAIRS and rep["only_espn"] == 1 and rep["only_bdl"] == 0
    assert rep["median_raw_s"] == -4.0 and rep["median_s"] == 0.0
    assert rep["verdict"].startswith("BALLDONTLIE as fast or faster"), rep["verdict"]
    root2 = Path(tempfile.mkdtemp())
    _write(root2, recs[:20])
    rep2 = FL.report(days=1, today="2026-11-05", root=root2)["nba"]
    assert rep2["verdict"] == f"collecting (10 of {FL.MIN_PAIRS} score changes)", rep2["verdict"]
    root3 = Path(tempfile.mkdtemp())
    _write(root3, [dict(r, t=r["t"] + (12.0 if r["feed"] == "bdl" else 0.0)) for r in recs])
    rep3 = FL.report(days=1, today="2026-11-05", root=root3)["nba"]
    assert rep3["verdict"].startswith("ESPN faster by 12.0 s"), rep3["verdict"]
    lines = FL.report_lines({}, enabled=False)
    assert "this shell cannot see the service's settings" in lines[0] and "nothing recorded yet" in lines[1]
    assert "no BALLDONTLIE key on this box" not in " ".join(lines), \
        "run by hand, the shell's settings say nothing about the service's"
    assert any("→ ESPN faster" in ln for ln in FL.report_lines(FL.report(1, "2026-11-05", root3), True))


def test_the_watcher_leaves_a_note_the_report_reads():
    """6 November: the report, run by hand, said there was no key on a box
    whose service had one. The watcher now leaves its own note each time it
    looks, and the report words what that note says."""
    _reset()
    root = Path(tempfile.mkdtemp())
    assert FL.read_state(root) is None
    B.RATE.update({"limit": 5, "remaining": 4})
    t = [7000.0]
    FL.watch_once(espn=lambda s: ([_row(1, 0, state="final")], t[0]), bdl=lambda s, d: ([], t[0]),
                  now=lambda: t[0], root=root)
    st = FL.read_state(root)
    assert st["at"] == 7000.0 and st["on"] == [] and st["next_s"] == FL.IDLE_S and st["asleep"] is False
    assert st["limit"] == 5 and st["paused_until"] is None
    line = FL.watcher_line(st, enabled=False, now=7030.0)
    assert "last looked just now" in line and "no NBA or NFL game was on" in line and "5 a minute" in line
    FL.watch_once(espn=lambda s: ([_row(2, 0)], t[0]) if s == "nba" else ([], 0.0),
                  bdl=lambda s, d: ([_bdl(2, 0)], t[0]), now=lambda: t[0], root=root)
    st = FL.read_state(root)
    assert st["on"] == ["nba"] and st["next_s"] == FL.every_s(1)
    assert "with NBA on; reading every" in FL.watcher_line(st, enabled=False, now=7000.0)
    late = FL.watcher_line(st, enabled=True, now=7000.0 + 4 * FL.IDLE_S)
    assert "not running now" in late, late

    def refused(s, d):
        raise B.BDLUnavailable("BALLDONTLIE refused the key (401)")
    FL.watch_once(espn=lambda s: ([_row(2, 3)], t[0]) if s == "nba" else ([], 0.0), bdl=refused,
                  now=lambda: t[0], root=root, log=lambda *_: None)
    st = FL.read_state(root)
    assert st["asleep"] is True and "asleep, BALLDONTLIE refused the key" in FL.watcher_line(st, True, 7000.0)
    lines = FL.report_lines({}, enabled=False, state=st, now=7000.0)
    assert lines[0].startswith("  the watcher: asleep") and "this shell cannot see" not in lines[0]
    assert not list(root.glob(".*.tmp")), "the note is swapped in whole"
    assert FL.prune("2026-11-05", root) == 0 and FL.read_state(root), "the note is not a day to drop"
    _reset()


def test_old_days_are_dropped_once_a_day():
    _reset()
    root = Path(tempfile.mkdtemp())
    for day in ("2026-08-01", "2026-09-30", "2026-11-05"):
        (root / f"{day}.jsonl").write_text("{}\n")
    assert FL.prune("2026-11-05", root) == 1
    assert sorted(p.stem for p in root.glob("*.jsonl")) == ["2026-09-30", "2026-11-05"]
    (root / "2026-08-02.jsonl").write_text("{}\n")
    assert FL.prune("2026-11-05", root) == 0, "once a day"


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
