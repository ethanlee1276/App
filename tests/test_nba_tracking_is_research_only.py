"""NBA player tracking (stats.nba.com): a research backfill on the box, and the
held-out test that decides whether it is worth reading (engine/nba/tracking,
nbatrackcheck.py).

Ethan, 2026-11-05, on the data hunt's one parked source: "do it". What these
hold:

  * the request is the one nba_api 1.12.0 sends (every parameter, sorted, one
    day), with the headers nba.com's own pages send and nothing that names a
    person; a gzip answer is read; an answer with no player columns is refused;
  * the backfill stores each day and measure once, resumes where it stopped,
    waits between requests, keeps to its budget, and stops at the league's
    first refusal or a third failure in a row; today and yesterday wait;
  * the probe stores nothing; the store merges a day's measures into one row a
    player, keyed as the box's game logs are;
  * nothing the site serves or builds imports it;
  * the measurement finds tracking that carries a passer's real rate (assists
    land at random off his potential assists) and refuses tracking that is
    noise, on synthetic seasons, through the board's own projection.

Run directly: `python3 tests/test_nba_tracking_is_research_only.py`
"""
import gzip
import json
import math
import random
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.nba import tracking as TR                           # noqa: E402

HEADS = ["PLAYER_ID", "PLAYER_NAME", "TEAM_ID", "TEAM_ABBREVIATION", "GP", "W", "L", "MIN",
         "PASSES_MADE", "PASSES_RECEIVED", "AST", "SECONDARY_AST", "POTENTIAL_AST"]


class _Resp:
    def __init__(self, payload, gz=True):
        raw = json.dumps(payload).encode("utf-8")
        self._b = gzip.compress(raw) if gz else raw
        self.headers = {"Content-Encoding": "gzip"} if gz else {}

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _answer(rows):
    return {"resource": "leaguedashptstats", "parameters": {},
            "resultSets": [{"name": "LeagueDashPtStats", "headers": HEADS, "rowSet": rows}]}


def _row(pid, name, team="BOS", mins=31.5, pa=9):
    return [pid, name, 1610612738, team, 1, 1, 0, mins, 50, 48, 5, 1, pa]


def _hist(days, season=2024):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE player_game_logs (sport TEXT, season INTEGER, period TEXT, game_id TEXT, "
                 "player TEXT, team TEXT, opponent TEXT, position TEXT, home INTEGER, market TEXT, value REAL)")
    for d in days:
        conn.execute("INSERT INTO player_game_logs VALUES ('nba',?,?,'g1','Jayson Tatum','BOS','NYK','S',1,'min',36)",
                     (season, d))
    return conn


# --- the request ----------------------------------------------------------------------
def test_the_request_is_nba_apis_one_day_at_a_time():
    url = TR.url("2025-01-15", 2024, "Passing")
    assert url.startswith("https://stats.nba.com/stats/leaguedashptstats?")
    q = urllib.parse.parse_qsl(url.split("?", 1)[1], keep_blank_values=True)
    names = [k for k, _v in q]
    assert names == sorted(names), "sorted by name, as nba_api sends them"
    p = dict(q)
    assert p["DateFrom"] == p["DateTo"] == "01/15/2025"
    assert p["Season"] == "2024-25" and p["SeasonType"] == "Regular Season"
    assert p["PtMeasureType"] == "Passing" and p["PlayerOrTeam"] == "Player" and p["PerMode"] == "Totals"
    assert p["LeagueID"] == "00" and p["LastNGames"] == "0" and p["Month"] == "0"
    assert len(p) == 30 and "ISTRound" not in p, "every parameter but the one nba_api leaves out as None"
    assert TR.MEASURES == ("Passing", "Possessions", "Drives", "Rebounding")


def test_the_headers_are_the_pages_own_and_name_nobody():
    h = TR.HEADERS
    assert h["Referer"] == "https://www.nba.com/" and h["Origin"] == "https://www.nba.com"
    assert h["x-nba-stats-origin"] == "stats" and h["x-nba-stats-token"] == "true"
    assert h["User-Agent"].startswith("Mozilla/5.0") and "br" not in h["Accept-Encoding"]
    for k, v in h.items():
        assert "@" not in v and "qellys" not in v.lower(), (k, v)
    assert not any(k.lower() in ("authorization", "cookie", "from") for k in h)


def test_a_gzip_answer_is_read_and_a_strange_one_refused():
    seen = {}

    def opener(req, timeout=None):
        seen["url"], seen["headers"] = req.full_url, dict(req.header_items())
        return _Resp(_answer([_row(1628369, "Jayson Tatum")]))
    heads, rows = TR.fetch("2025-01-15", 2024, "Passing", opener=opener)
    assert heads == HEADS and rows[0][1] == "Jayson Tatum"
    assert seen["headers"].get("Referer") == "https://www.nba.com/"
    bad = lambda req, timeout=None: _Resp({"resultSets": [{"headers": ["X"], "rowSet": []}]}, gz=False)  # noqa: E731
    try:
        TR.fetch("2025-01-15", 2024, "Passing", opener=bad)
        raise AssertionError("an answer without the player columns was taken")
    except TR.TrackUnavailable as exc:
        assert "PLAYER_ID" in str(exc)


# --- the backfill ---------------------------------------------------------------------
def _store():
    return TR.open_store(":memory:")


def test_the_backfill_stores_each_day_once_and_resumes():
    days = ["2025-01-13", "2025-01-14", "2025-01-15"]
    hist, store = _hist(days), _store()
    asked, slept = [], []

    def opener(req, timeout=None):
        q = dict(urllib.parse.parse_qsl(req.full_url.split("?", 1)[1], keep_blank_values=True))
        asked.append((q["DateFrom"], q["PtMeasureType"]))
        return _Resp(_answer([_row(1628369, "Jayson Tatum"), _row(1627759, "Jaylen Brown")]))
    res = TR.backfill(hist, store, [2024], max_requests=5, opener=opener, sleep=slept.append,
                      today="2025-06-01", log=lambda *_: None)
    assert res["asked"] == 5 and res["stored"] == 5 and res["rows"] == 10
    assert res["left"] == 7 and "--max" in res["stopped"]
    assert len(slept) == 4 and all(TR.PACE_S <= s <= TR.PACE_S * 1.5 for s in slept), "it waits between requests"
    first = list(asked)
    res = TR.backfill(hist, store, [2024], opener=opener, sleep=lambda s: None, today="2025-06-01",
                      log=lambda *_: None)
    assert res["stored"] == 7 and res["left"] == 0 and res["stopped"] == "done"
    assert len(set(asked)) == len(asked) == 12, "no day and measure asked twice"
    assert first[0] == ("01/13/2025", "Passing"), "oldest first"
    n, = store.execute("SELECT COUNT(*) FROM done").fetchone()
    assert n == 12
    assert TR.backfill(hist, store, [2024], opener=opener, today="2025-06-01")["stopped"] == "nothing left to fetch"


def test_today_and_yesterday_wait():
    hist, store = _hist(["2025-01-13", "2025-01-14", "2025-01-15"]), _store()
    left = TR.todo(hist, store, [2024], today="2025-01-15")
    assert {d for d, _s, _m in left} == {"2025-01-13"}


def test_the_season_asked_for_is_read_off_the_date():
    """A store that labels a season by the year it ends (the replica the lab
    built did) still asks the league for the season it names that day by."""
    hist = _hist(["2024-11-02", "2025-03-01"], season=2025)
    assert TR.game_days(hist, [2024]) == [("2024-11-02", 2024), ("2025-03-01", 2024)]
    assert TR.stored_seasons(hist) == [2024]
    seen = []

    def opener(req, timeout=None):
        seen.append(dict(urllib.parse.parse_qsl(req.full_url.split("?", 1)[1], keep_blank_values=True))["Season"])
        return _Resp(_answer([_row(1, "A B")]))
    TR.backfill(hist, _store(), [2024], max_requests=2, opener=opener, sleep=lambda s: None,
                today="2025-06-01", log=lambda *_: None)
    assert seen == ["2024-25", "2024-25"]
    assert "--probe" not in TR.probe(hist, opener=opener)[0]


def test_a_refusal_stops_the_run_at_once_and_three_failures_in_a_row_stop_it():
    days = [f"2025-01-{d:02d}" for d in range(10, 20)]
    hist = _hist(days)

    def refused(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", None, None)
    res = TR.backfill(hist, _store(), [2024], opener=refused, sleep=lambda s: None, today="2025-06-01",
                      log=lambda *_: None)
    assert res["asked"] == 1 and res["stored"] == 0 and "refused" in res["stopped"]

    def hangs(req, timeout=None):
        raise TimeoutError("timed out")
    res = TR.backfill(hist, _store(), [2024], opener=hangs, sleep=lambda s: None, today="2025-06-01",
                      log=lambda *_: None)
    assert res["asked"] == TR.STOP_AFTER and "in a row" in res["stopped"]


def test_the_backfill_keeps_to_its_time_budget():
    hist, store = _hist([f"2025-01-{d:02d}" for d in range(10, 20)]), _store()
    t = [0.0]

    def clock():
        return t[0]

    def sleep(s):
        t[0] += 60.0
    ok = lambda req, timeout=None: _Resp(_answer([_row(1, "A B")]))  # noqa: E731
    res = TR.backfill(hist, store, [2024], minutes=3, opener=ok, sleep=sleep, clock=clock,
                      today="2025-06-01", log=lambda *_: None)
    assert res["stored"] == 3 and "budget" in res["stopped"] and res["left"] == 37


def test_the_store_merges_a_days_measures_under_the_logs_names():
    store = _store()
    TR.keep(store, "2025-01-15", 2024, "Passing", HEADS, [_row(1628369, "Nikola Jokić", "DEN", 34.0, 17)])
    TR.keep(store, "2025-01-15", 2024, "Rebounding", ["PLAYER_ID", "PLAYER_NAME", "TEAM_ABBREVIATION", "MIN",
                                                      "REB_CHANCES"], [[1628369, "Nikola Jokić", "DEN", 34.0, 21]])
    got = TR.load(store)
    row = got[("2025-01-15", "nikola jokic")]
    assert row["POTENTIAL_AST"] == 17 and row["REB_CHANCES"] == 21 and row["_min"] == 34.0
    assert row["_team"] == "DEN" and "PLAYER_ID" not in row and "GP" not in row
    # Stored again, replaced, never doubled.
    TR.keep(store, "2025-01-15", 2024, "Passing", HEADS, [_row(1628369, "Nikola Jokić", "DEN", 34.0, 18)])
    assert TR.load(store)[("2025-01-15", "nikola jokic")]["POTENTIAL_AST"] == 18
    n, = store.execute("SELECT COUNT(*) FROM rows").fetchone()
    assert n == 2


def test_the_probe_stores_nothing():
    keep = TR.open_store
    TR.open_store = lambda *a, **k: (_ for _ in ()).throw(AssertionError("the probe opened the store"))
    try:
        lines = TR.probe(day="2025-01-15", opener=lambda req, timeout=None: _Resp(_answer([_row(1, "A B")])))
    finally:
        TR.open_store = keep
    assert lines[0].startswith("2025-01-15 Passing: ok, 1 player(s)") and "potential assists 9" in lines[0]
    assert lines[1].startswith("columns: PLAYER_ID") and lines[-1] == "Nothing stored."
    down = TR.probe(day="2025-01-15", opener=lambda req, timeout=None: (_ for _ in ()).throw(TimeoutError("t")))
    assert "did not answer" in down[0] and "refusing this box's address" in down[1]


def test_nothing_on_the_site_imports_it():
    pat = re.compile(r"nba\.tracking|nba import tracking|from \.tracking|from \.\.nba\.tracking|import tracking\b")
    files = [p for p in (ROOT / "engine").rglob("*.py") if p != ROOT / "engine" / "nba" / "tracking.py"]
    files += [ROOT / "launch.py", ROOT / "server.py"] + sorted(ROOT.glob("*_build.py"))
    hits = [str(p.relative_to(ROOT)) for p in files if p.exists() and pat.search(p.read_text(encoding="utf-8"))]
    assert not hits, hits
    assert "nba_tracking" not in (ROOT / "deploy" / "backup.sh").read_text(encoding="utf-8"), \
        "a store that can be fetched again stays out of the nightly backup"
    assert str(TR.STORE).endswith("data/research/nba_tracking.db")


# --- the measurement ------------------------------------------------------------------
def _poisson(rng, lam):
    lam = max(0.0, lam)
    if lam > 30:
        return max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))
    k, p, t = 0, 1.0, math.exp(-lam)
    while True:
        p *= rng.random()
        if p <= t:
            return k
        k += 1


def _seasons(signal: bool, seed: int = 7, players: int = 30, days: int = 60):
    """Two synthetic seasons. Each passer has a true rate of potential
    assists a minute; his assists land off them at a rate that swings game to
    game (his teammates' shooting). With ``signal`` the stored tracking is
    those potential assists; without it, a count unrelated to him."""
    from engine.sources.oddsapi import normalize_name
    rng = random.Random(seed)
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE player_game_logs (sport TEXT, season INTEGER, period TEXT, game_id TEXT, "
                 "player TEXT, team TEXT, opponent TEXT, position TEXT, home INTEGER, market TEXT, value REAL)")
    track = {}
    rates = [(rng.uniform(0.08, 0.45), rng.uniform(0.08, 0.45)) for _ in range(players)]
    for season in (2023, 2024):
        start = date(season, 11, 1)
        for p in range(players):
            name = f"Passer {p} Test"
            pa_rate, noise_rate = rates[p]
            for d in range(days):
                day = (start + timedelta(days=d)).isoformat()
                mins = max(12.0, rng.gauss(30.0, 3.0))
                pa = _poisson(rng, mins * pa_rate)
                conv = rng.uniform(0.15, 0.85)
                ast = sum(1 for _ in range(pa) if rng.random() < conv)
                vals = {"min": round(mins, 1), "ast": ast, "pts": _poisson(rng, mins * 0.5),
                        "reb": _poisson(rng, mins * 0.18)}
                for market, v in vals.items():
                    conn.execute("INSERT INTO player_game_logs VALUES ('nba',?,?,?,?,'BOS','NYK','S',1,?,?)",
                                 (season, day, f"g{season}{d}", name, market, float(v)))
                track[(day, normalize_name(name))] = {
                    "_min": round(mins, 1), "_team": "BOS",
                    "POTENTIAL_AST": float(pa if signal else _poisson(rng, mins * noise_rate)),
                    "PASSES_MADE": float(_poisson(rng, mins * 1.1))}
    return conn, track


#: Two synthetic seasons hold about 1,500-1,800 judged games each.
JUDGED = 1000


def _measure(signal: bool):
    import nbatrackcheck as C
    from engine import hoopsreplay as HR
    from engine.hoops import NBA
    conn, track = _seasons(signal)
    hist = HR.histories(conn, "nba")
    res = C.measure(C.collect(hist, track, NBA, markets=("ast",)), NBA)
    return C, res, C.verdict(res["ast"], JUDGED)


def test_the_measurement_finds_a_passers_real_rate():
    C, res, (ok, why) = _measure(True)
    m = res["ast"]
    assert m["use"] == ["POTENTIAL_AST", "PASSES_MADE"], m["use"]
    assert m["dropped"] == ["SECONDARY_AST", "AST_POINTS_CREATED|AST_PTS_CREATED"], "named, not guessed"
    assert set(m["seasons"]) == {2023, 2024} and all(r["fitted_on"] == [2024 if s == 2023 else 2023]
                                                     for s, r in m["seasons"].items()), "each judged on the other"
    assert ok, why
    for r in m["seasons"].values():
        assert r["rmse"]["tracked"] < r["rmse"]["alone"] * (1 - C.GAIN)
        assert r["coef"][2] > 0, "potential assists carry positive weight"
    text = "\n".join(C.report(res, min_judged=JUDGED))
    assert "assists: MEASURES on every season judged" in text and "Read-only: nothing was written" in text


def test_the_measurement_refuses_tracking_that_is_noise():
    C, res, (ok, why) = _measure(False)
    assert not ok and why and all("squared error" in w or "Brier" in w for w in why), why
    assert "assists: does not measure" in "\n".join(C.report(res, min_judged=JUDGED))
    # At the real bar, two synthetic seasons are too few to judge at all.
    ok, why = C.verdict(res["ast"])
    assert not ok and why[0].startswith("not judged")


def test_two_seasons_are_needed_to_judge():
    import nbatrackcheck as C
    ok, why = C.verdict({"seasons": {2024: {"n": 5000}}})
    assert not ok and len(why) == 1 and "two are needed" in why[0]


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
