"""The MLB board was waiting, not computing — and what it takes to stop.

Measured on the production droplet 2026-08-16:

    $ time python3 mlb_build.py 2026-08-16 --cached-odds --out /tmp/x.json
    real    7m39.450s
    user    0m0.007s
    sys     0m0.013s

Seven and a half minutes of wall clock against effectively zero CPU. That
pairing is the whole diagnosis: nothing was being computed, ~600 HTTP
requests were being made one after another. Resizing the droplet from one
core to two changed nothing, because cores were never the constraint.

These tests pin the three things the fix has to get right, and none of
them is "it is faster" — that is measured on the box with the command
above. They are:

  * THE DEDUP SURVIVES. A cold build makes 870 `fetch_game_log` calls and
    only 300 requests, and the entire saving comes from `_get_json`'s
    mtime check. Three threads missing the same file at the same instant
    would undo it and TRIPLE the request count — a "speed-up" that hits
    the rate limit harder than the bug did.
  * THE CACHE FILES STAY WHOLE. Concurrent writers to one path used to
    interleave. `_read_cached_json` already downgrades a torn file to a
    miss, so the damage was a re-fetch rather than a wrong number — which
    is still request amplification pointed straight at the rate limit.
  * THE BOARD DOES NOT MOVE. Same props, same order, whatever the pool
    size and whatever the thread scheduler does. A faster board that
    reorders itself is not the same board.

And the one thing a warm pass must never do: decide whether we price.
Every wave here is warming only — kill it entirely and the build is what
it was before the fix, correct and slow.
"""

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.mlb.sources import mlbstats as ms          # noqa: E402
from engine.mlb.sources import statslogs as sl         # noqa: E402
from engine.mlb.models import TOTAL_BASES, HITS, HOME_RUNS  # noqa: E402
from engine.sources.fetch import DataUnavailable       # noqa: E402


# --- fetch_many: order, dedup, and the cap ----------------------------------
def test_results_come_back_in_input_order():
    """Requests finish in whatever order the network hands them back; the
    board is built from this list, so the LIST has to be ordered by input.
    Sleeping longest on the first item is the case a naive as-completed
    implementation gets wrong."""
    def slow_first(n):
        time.sleep(0.05 if n == 0 else 0.0)
        return n * 10

    assert ms.fetch_many(slow_first, [(i,) for i in range(8)]) == \
        [0, 10, 20, 30, 40, 50, 60, 70]


def test_a_repeated_argument_is_fetched_once():
    """THE REGRESSION THIS FILE EXISTS FOR. Three hitter markets ask for one
    player's game log, and 870 calls collapse to 300 requests only because
    the second and third find a fresh file. Concurrently they would all miss
    together, so the pool has to collapse them itself."""
    calls = []
    lock = threading.Lock()

    def count(pid, group, season):
        with lock:
            calls.append((pid, group, season))
        return {"pid": pid}

    args = [(7, "hitting", 2026)] * 3 + [(8, "hitting", 2026)]
    out = ms.fetch_many(count, args)
    assert len(calls) == 2, f"{len(calls)} requests for 2 distinct players"
    assert [o["pid"] for o in out] == [7, 7, 7, 8], "duplicates still answered"


def test_no_more_than_the_cap_are_ever_in_flight():
    """Three hundred simultaneous requests is how a season ends with the
    droplet's IP blocked. The cap is the only rate limiting there is."""
    live = {"now": 0, "peak": 0}
    lock = threading.Lock()

    def watched(_i):
        with lock:
            live["now"] += 1
            live["peak"] = max(live["peak"], live["now"])
        time.sleep(0.02)
        with lock:
            live["now"] -= 1

    ms.fetch_many(watched, [(i,) for i in range(60)], workers=4)
    assert live["peak"] <= 4, f"{live['peak']} requests in flight, cap was 4"
    assert live["peak"] > 1, "nothing ran concurrently at all"


def test_the_pool_size_is_clamped_at_both_ends():
    """`QB_MLB_WORKERS` is the knob to reach for if MLB ever starts refusing
    us — including turning concurrency off entirely with 1. It must not be
    able to ask for three hundred."""
    saved = os.environ.get("QB_MLB_WORKERS")
    try:
        for value, want in (("1", 1), ("0", 1), ("-5", 1),
                            ("999", 16), ("16", 16), ("", ms.FETCH_WORKERS),
                            ("banana", ms.FETCH_WORKERS)):
            os.environ["QB_MLB_WORKERS"] = value
            assert ms._workers() == want, f"{value!r} gave {ms._workers()}"
        del os.environ["QB_MLB_WORKERS"]
        assert ms._workers() == ms.FETCH_WORKERS
    finally:
        os.environ.pop("QB_MLB_WORKERS", None)
        if saved is not None:
            os.environ["QB_MLB_WORKERS"] = saved


def test_one_failure_is_a_none_and_the_rest_still_run():
    """A warm pass is not allowed to have an opinion about whether the build
    continues. The sequential pass behind it makes the same call and handles
    the failure the way it always did."""
    def sometimes(n):
        if n == 2:
            raise DataUnavailable("no boxscore for that game")
        return n

    assert ms.fetch_many(sometimes, [(i,) for i in range(5)]) == \
        [0, 1, None, 3, 4]


def test_the_first_429_stops_the_wave():
    """`solrpc.py` learned this the expensive way: a burst that gets 429ed
    writes no cache, so the next tick fires the identical burst. Once the
    host is refusing, the rest of the wave cannot succeed and every request
    in it digs the hole deeper."""
    seen = []
    lock = threading.Lock()

    def refused(n):
        with lock:
            seen.append(n)
        time.sleep(0.01)
        raise DataUnavailable("Too Many Requests", status=429)

    ms.fetch_many(refused, [(i,) for i in range(200)], workers=4)
    assert len(seen) < 200, "the wave ran to completion against a 429"
    assert len(seen) <= 20, f"{len(seen)} requests fired after the first 429"


def test_a_404_is_not_a_reason_to_stop():
    """The opposite case, and why the status had to be carried at all: "that
    game has no boxscore" is about ONE resource. Standing the wave down on
    it would drop every other player on the slate."""
    seen = []
    lock = threading.Lock()

    def missing(n):
        with lock:
            seen.append(n)
        raise DataUnavailable("Not Found", status=404)

    ms.fetch_many(missing, [(i,) for i in range(40)], workers=4)
    assert len(seen) == 40, f"only {len(seen)} of 40 ran"


def test_a_pool_that_will_not_start_falls_back_instead_of_failing():
    """`one()` swallows what the FETCH raises; this is what the POOL raises
    — "can't start new thread" on a loaded box, most of all. It reached
    `build_live_slate`'s warm calls, none of which are guarded, so the
    machine being busy would have failed the build outright. Warming is
    never allowed to be that."""
    import concurrent.futures
    saved = ms.ThreadPoolExecutor

    def refuses(*a, **kw):
        raise RuntimeError("can't start new thread")

    try:
        ms.ThreadPoolExecutor = refuses
        out = ms.fetch_many(lambda n: n * 2, [(i,) for i in range(6)])
    finally:
        ms.ThreadPoolExecutor = saved
    assert out == [0, 2, 4, 6, 8, 10], "the fallback did not do the work"
    assert saved is concurrent.futures.ThreadPoolExecutor    # restored


def test_concurrency_is_actually_won():
    """The arithmetic from the bug report, in miniature: 32 waits of 40ms is
    1.28s serially and must not be."""
    def wait(_i):
        time.sleep(0.04)

    t0 = time.monotonic()
    ms.fetch_many(wait, [(i,) for i in range(32)], workers=8)
    took = time.monotonic() - t0
    assert took < 0.6, f"32 x 40ms took {took:.2f}s — barely better than 1.28s"


# --- the cache files stay whole ---------------------------------------------
def _hammer(path, bodies, rounds=40):
    """Writers racing one path while a reader watches. Returns (torn, reads)."""
    torn = []
    stop = threading.Event()

    def read():
        while not stop.is_set():
            try:
                json.loads(path.read_text())
            except FileNotFoundError:
                pass
            except ValueError:
                torn.append(1)

    watcher = threading.Thread(target=read, daemon=True)
    watcher.start()
    try:
        for _ in range(rounds):
            ts = [threading.Thread(target=ms._write_cache, args=(path, b))
                  for b in bodies]
            for t in ts:
                t.start()
            for t in ts:
                t.join()
    finally:
        stop.set()
        watcher.join(timeout=2)
    return torn


def test_a_reader_never_sees_half_a_file(tmp=None):
    """The named hazard. Bodies of very different lengths, because a torn
    file is what you get when a long one is truncated by a short one."""
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "mlb_log_hitting_1_2026.json"
        bodies = [json.dumps({"n": i, "pad": "x" * (i * 4000)})
                  for i in range(1, 6)]
        torn = _hammer(path, bodies)
        assert not torn, f"{len(torn)} torn reads"
        assert json.loads(path.read_text())          # and a whole file survives


def test_no_temp_files_are_left_behind():
    """A racing writer that cleaned up with a fixed name would delete its
    neighbour's file; one that never cleans up fills the cache directory."""
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "mlb_box_1.json"
        _hammer(path, [json.dumps({"n": i}) for i in range(4)], rounds=10)
        leftovers = [p.name for p in Path(d).iterdir() if p.name != path.name]
        assert not leftovers, f"left behind: {leftovers}"


# --- a fake wire, so a whole cold build can be counted -----------------------
GAMES = 15
HITTERS = 9

#: Thirty real team ids, two per game — a full slate, and every matchup
#: distinct. (An earlier draft of this fixture gave all fifteen games the
#: same pair, which the doubleheader rule correctly collapsed to ONE prop
#: game: the fake slate was 1/15th the size it claimed and the request
#: count looked wonderful.)
TEAM_IDS = sorted(ms.TEAM_ID_ABBR)

#: A few real venues, so the park map and the weather warm both do work.
VENUES = ["Wrigley Field", "Coors Field", "Fenway Park", "Petco Park",
          "Oracle Park"]


def _matchup(n: int) -> tuple[int, int]:
    if DOUBLEHEADER["on"] and n == GAMES - 1:
        return TEAM_IDS[0], TEAM_IDS[1]
    return TEAM_IDS[(2 * n) % 30], TEAM_IDS[(2 * n + 1) % 30]


def _fake_wire(counts, lock, fail=None):
    """statsapi + open-meteo, synthesized from the URL. Counts every call."""
    def urlopen(req, timeout=None):                    # noqa: ARG001
        url = req.full_url if hasattr(req, "full_url") else str(req)
        with lock:
            counts[url] = counts.get(url, 0) + 1
        if fail is not None and fail(url):
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)
        return _Body(json.dumps(_answer(url)).encode())
    return urlopen


class _Body:
    def __init__(self, raw):
        self.raw = raw

    def read(self):
        return self.raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _answer(url: str) -> dict:
    if "open-meteo" in url:
        return {"current": {"temperature_2m": 71, "relative_humidity_2m": 50,
                            "wind_speed_10m": 7, "wind_direction_10m": 180,
                            "precipitation_probability": 0}}
    if "/boxscore" in url:
        pk = int(url.split("/game/")[1].split("/")[0])
        # A game the projected-lineup chain reached: that is a PAST game, so
        # its card is always posted however empty tonight's are.
        home_id, away_id = _matchup((pk - 1000) % GAMES)
        if NO_CARDS["on"] and pk < 2000:
            return {"teams": {side: {"team": {"id": tid}, "battingOrder": [],
                                     "players": {}}
                              for side, tid in (("home", home_id),
                                                ("away", away_id))}}
        return {"teams": {
            side: {"team": {"id": tid},
                   "battingOrder": [pk * 100 + off + i for i in range(HITTERS)],
                   "players": {f"ID{pk * 100 + off + i}": {
                       "person": {"id": pk * 100 + off + i,
                                  "fullName": f"Hitter {pk}-{off}-{i}"},
                       "position": {"abbreviation": "CF"}} for i in range(HITTERS)}}
            for side, tid, off in (("home", home_id, 0), ("away", away_id, 50))}}
    if "stats=gameLog" in url:
        pid = int(url.split("/people/")[1].split("/")[0])
        hitting = "group=hitting" in url
        return {"stats": [{"splits": [
            {"date": f"2026-08-0{n + 1}", "opponent": {"id": 138}, "isHome": True,
             "game": {"gamePk": 700000 + pid % 97 + n},
             "stat": ({"hits": n % 3, "totalBases": n % 4, "homeRuns": n % 2,
                       "plateAppearances": 4} if hitting else
                      {"strikeOuts": 4 + n % 5, "outs": 15 + n % 4,
                       "gamesStarted": 1, "inningsPitched": "5.0"})}
            for n in range(9)]}]}
    if "/people/" in url:
        pid = int(url.rstrip("/").split("/people/")[1].split("?")[0])
        return {"people": [{"id": pid, "fullName": f"Person {pid}",
                            "batSide": {"code": "R"},
                            "pitchHand": {"code": "R"},
                            "primaryPosition": {"abbreviation": "CF"}}]}
    if "/playByPlay" in url:
        return {"allPlays": []}
    if "teamId=" in url:
        # `projected_lineup`'s first request: the team's last few games. Its
        # SECOND request needs the gamePk out of this reply, which is the one
        # dependent chain in the build and the reason that call goes into the
        # pool whole rather than being flattened.
        tid = int(url.split("teamId=")[1].split("&")[0])
        return {"dates": [{"date": "2026-08-15", "games": [{
            "gamePk": 2000 + tid,
            "status": {"abstractGameState": "Final"},
            "teams": {"home": {"team": {"id": tid}},
                      "away": {"team": {"id": TEAM_IDS[0]}}},
        }]}]}
    if "/schedule" in url:
        return {"dates": [{"date": "2026-08-16", "games": [{
            "gamePk": 1000 + n,
            "gameDate": f"2026-08-16T{17 + n % 6}:05:00Z",
            "status": {"abstractGameState": "Preview"},
            "teams": {
                "home": {"team": {"id": _matchup(n)[0]},
                         "probablePitcher": {"id": 90000 + n * 2,
                                             "fullName": f"Starter H{n}",
                                             "pitchHand": {"code": "R"}}},
                "away": {"team": {"id": _matchup(n)[1]},
                         "probablePitcher": {"id": 90001 + n * 2,
                                             "fullName": f"Starter A{n}",
                                             "pitchHand": {"code": "L"}}}},
            "venue": {"name": VENUES[n % len(VENUES)]},
        } for n in range(GAMES)]}]}
    return {}


#: Set to blank every boxscore's batting order, which is the state of a real
#: slate all morning: no card posted, so every hitter comes from
#: `projected_lineup` — last game's order — instead. It is a different code
#: path with a two-request dependent chain in it, and leaving it out of these
#: fixtures made one test below pass for the wrong reason.
NO_CARDS = {"on": False}

#: Make the LAST game repeat the first game's matchup, which is what a
#: doubleheader looks like coming off the schedule. Props are built for one
#: leg of a pair, so a warm pass that reads the schedule alone cannot know
#: which starters it is allowed to ask for.
DOUBLEHEADER = {"on": False}


def _cold_build(workers: str, fail=None, no_cards: bool = False,
                doubleheader: bool = False):
    """One cold build against the fake wire. Returns (slate, url counts)."""
    import tempfile
    from pathlib import Path
    counts: dict = {}
    lock = threading.Lock()
    saved_cache, saved_open = ms.CACHE_DIR, urllib.request.urlopen
    saved_workers = os.environ.get("QB_MLB_WORKERS")
    with tempfile.TemporaryDirectory() as d:
        try:
            ms.CACHE_DIR = Path(d)
            urllib.request.urlopen = _fake_wire(counts, lock, fail)
            os.environ["QB_MLB_WORKERS"] = workers
            NO_CARDS["on"] = no_cards
            DOUBLEHEADER["on"] = doubleheader
            slate = sl.build_live_slate("2026-08-16")
        finally:
            ms.CACHE_DIR, urllib.request.urlopen = saved_cache, saved_open
            NO_CARDS["on"] = DOUBLEHEADER["on"] = False
            os.environ.pop("QB_MLB_WORKERS", None)
            if saved_workers is not None:
                os.environ["QB_MLB_WORKERS"] = saved_workers
    return slate, counts


def _shape(slate):
    """Everything about the board that must not depend on scheduling."""
    return ([(g.home, g.away, g.park, g.lineups_confirmed) for g in slate.games],
            [(p.player, p.team, p.opponent, p.market, p.lineup_spot,
              p.career_avg, p.career_games, p.lines[0].line)
             for p in slate.props])


def test_a_cold_build_asks_for_nothing_twice():
    """THE POINT OF THE WHOLE CHANGE, stated as a request count. 15 games x
    18 hitters x 3 markets is 810 game-log CALLS; the wire must see one
    request per player. A pool that lost the dedup would show 3."""
    slate, counts = _cold_build("8")
    assert slate.games and slate.props
    repeated = {u: n for u, n in counts.items() if n > 1}
    assert not repeated, f"{len(repeated)} URLs fetched more than once"

    logs = [u for u in counts if "stats=gameLog" in u]
    assert len(logs) == GAMES * 2 * HITTERS + GAMES * 2, \
        f"{len(logs)} game-log requests for 270 hitters + 30 starters"


def test_the_board_is_the_same_board_at_any_pool_size():
    """A faster board that reorders itself is not the same board.
    `test_mlb_live` pins `hitters[0].lineup_spot == 1`; this pins every row
    of a full slate against a serial build of the same slate."""
    serial, _ = _cold_build("1")
    pooled, _ = _cold_build("8")
    assert _shape(serial) == _shape(pooled)
    assert len(pooled.props) == GAMES * (2 * HITTERS * 3 + 2 * 2), \
        f"{len(pooled.props)} props built"


def _with_pools_dead(**kw):
    """The same build with every wave returning nothing, as if deleted."""
    saved = ms.fetch_many, sl.fetch_many
    try:
        dead = lambda fn, args, workers=None: [None] * len(args)  # noqa: E731
        ms.fetch_many = sl.fetch_many = dead
        return _cold_build("8", **kw)
    finally:
        ms.fetch_many, sl.fetch_many = saved


def test_the_build_is_correct_with_the_warm_passes_dead():
    """The safety property that makes warming the right shape for this fix.
    Every wave is a cache warm-up, so removing them entirely can only cost
    time — the sequential passes still make every call themselves."""
    crippled, _ = _with_pools_dead()
    warm, _ = _cold_build("8")
    assert _shape(crippled) == _shape(warm)


def test_the_same_holds_on_a_morning_with_no_lineups_posted():
    """THE CASE THAT MADE THE TEST ABOVE A FALSE NEGATIVE. Every fixture in
    this file posts both cards, so `projected_lineup` — the one dependent
    two-request chain in the build — never ran, and a draft in which warm
    pass B CONSUMED the pooled projection passed anyway. It should not have:
    `fetch_many` turns a fault into None, so that draft would have deleted a
    whole team's hitters rather than merely slowing them down. Pass 2 does
    the projecting; the pool only warms what it will read."""
    warm, _ = _cold_build("8", no_cards=True)
    hitters = [p for p in warm.props if p.market in (TOTAL_BASES, HITS,
                                                     HOME_RUNS)]
    assert hitters, "the projected-lineup path produced no hitters at all"
    assert all(g.lineups_confirmed is False for g in warm.games), \
        "projected orders are being reported as confirmed"

    crippled, _ = _with_pools_dead(no_cards=True)
    assert _shape(crippled) == _shape(warm)


def test_a_doubleheader_does_not_warm_the_leg_it_will_not_price():
    """The one place a warm pass could ask for MORE than the build needs.

    Both legs' starters are in the schedule payload, but props are built for
    exactly one leg — and which one is not known until the doubleheader
    bookkeeping has run. Warming off the schedule alone therefore buys two
    game-log requests for a game nobody prices. That is small, and it is
    also the entire claim that this change adds no requests, so it is worth
    a test rather than a footnote."""
    slate, counts = _cold_build("8", doubleheader=True)
    warmed = {int(u.split("/people/")[1].split("/")[0]) for u in counts
              if "stats=gameLog" in u and "group=pitching" in u}
    priced = {p.person_id for p in slate.props
              if p.market not in (TOTAL_BASES, HITS, HOME_RUNS)}
    assert priced, "no pitcher props on the fixture at all"
    assert warmed == priced, (
        f"{len(warmed - priced)} starter(s) fetched for a leg never priced: "
        f"{sorted(warmed - priced)}")
    # And the pair really did collapse, or the assertion above is vacuous.
    assert len(slate.games) == GAMES
    assert sum(1 for g in slate.games if g.doubleheader) == 2


def _log_requests(counts) -> int:
    return sum(n for u, n in counts.items() if "stats=gameLog" in u)


def test_a_rate_limited_slate_does_not_take_the_whole_build_down():
    """If MLB does start refusing us mid-slate, the board loses the players
    it could not price and keeps the games. It must not raise: `mlb_build.py`
    turns an exception here into `sys.exit(2)` and no board at all."""
    slate, _counts = _cold_build("4", fail=lambda u: "stats=gameLog" in u)
    assert len(slate.games) == GAMES
    assert slate.props == [], "priced a prop off a log we never got"


def test_the_warm_waves_stand_down_instead_of_piling_on():
    """What the 429 rule is worth, measured against itself.

    BE PRECISE ABOUT WHAT IT DOES AND DOES NOT DO. The sequential pass
    behind a warm wave still asks for every game log itself and still gets
    refused — warming is not allowed to decide that, which is the property
    the rest of this file exists to protect. So the breaker bounds the WAVE,
    not the build: it stops the ~300 warm requests being added on top of the
    810 the old code already made. Making the build itself notice that it
    is being refused, rather than publishing a silently empty board, is a
    separate and larger change (docs/NEXT.md)."""
    _s, hot = _cold_build("4", fail=lambda u: "stats=gameLog" in u)
    saved = ms.BACKOFF_STATUS
    try:
        ms.BACKOFF_STATUS = set()                  # the same run, fuel on
        _s2, blind = _cold_build("4", fail=lambda u: "stats=gameLog" in u)
    finally:
        ms.BACKOFF_STATUS = saved
    assert _log_requests(hot) < _log_requests(blind) - 200, \
        f"{_log_requests(hot)} with the rule, {_log_requests(blind)} without"


# --- the play-by-play half --------------------------------------------------
def test_warm_starts_pools_every_pitchers_recent_starts():
    """~150 playByPlay fetches of ~640KB each, pulled five at a time from
    inside the pricing loop. They are the largest payloads a build asks for
    and they were the last serial wave left."""
    from engine.mlb import velocity as v
    from engine.mlb.sources import pbp

    live = {"now": 0, "peak": 0}
    lock = threading.Lock()
    asked = []

    def fake_pbp(game_pk, ttl=None):                   # noqa: ARG001
        with lock:
            live["now"] += 1
            live["peak"] = max(live["peak"], live["now"])
            asked.append(game_pk)
        time.sleep(0.01)
        with lock:
            live["now"] -= 1
        return {"allPlays": []}

    saved = v.recent_start_pks, pbp.fetch_playbyplay
    try:
        v.recent_start_pks = lambda pid, season, limit=5: [
            {"date": "2026-08-0%d" % (i + 1), "game_pk": pid * 10 + i}
            for i in range(limit)]
        pbp.fetch_playbyplay = fake_pbp
        v.warm_starts([501, 502, 503, 504, 505, 506], 2026)
    finally:
        v.recent_start_pks, pbp.fetch_playbyplay = saved

    assert len(asked) == 30, f"{len(asked)} starts fetched for 6 pitchers"
    assert live["peak"] > 1, "the starts went out one at a time"


def test_warm_starts_shrugs_off_a_pitcher_it_cannot_read():
    """A starter whose game log will not load is skipped, exactly as
    `velocity_history` skips him. Warming never decides anything."""
    from engine.mlb import velocity as v
    from engine.mlb.sources import pbp

    got = []
    saved = v.recent_start_pks, pbp.fetch_playbyplay
    try:
        def flaky(pid, season, limit=5):
            if pid == 502:
                raise DataUnavailable("no game log")
            return [{"date": "2026-08-01", "game_pk": pid * 10}]
        v.recent_start_pks = flaky
        pbp.fetch_playbyplay = lambda pk, ttl=None: got.append(pk) or {}
        v.warm_starts([501, 502, 503], 2026)
    finally:
        v.recent_start_pks, pbp.fetch_playbyplay = saved
    assert sorted(got) == [5010, 5030]


def test_the_pricing_path_warms_before_it_prices():
    """ORDER IS THE WHOLE VALUE HERE. `build_mlb_projection` reaches
    `delta_for` on the very first pitcher prop, so a warm pass that runs
    after the loop warms a cache the loop has already filled one request at
    a time — the change would measure as zero and look like it worked."""
    from engine.mlb import velocity as v
    from engine.mlb import openers as op
    from engine.mlb.data_loader import MLBSlate
    from engine.mlb.models import PITCHER_MARKETS
    from engine.mlb.pipeline import run_mlb_slate

    slate, _ = _cold_build("4")
    one = slate.games[0]
    trimmed = MLBSlate(date=slate.date, games=[one],
                       props=[p for p in slate.props
                              if p.team in (one.home, one.away)])
    starters = {p.person_id for p in trimmed.props
                if p.market in PITCHER_MARKETS}
    assert starters, "no starter on the trimmed slate to warm"

    order: list = []
    warmed: list = []
    saved = v.warm_starts, v.delta_for, v.projected_tto, op.opener_flag
    try:
        def warm(ids, season, limit=5):                 # noqa: ARG001
            order.append("warm")
            warmed.extend(ids)
        v.warm_starts = warm
        v.delta_for = lambda pid, season: order.append("delta") and None
        v.projected_tto = lambda pid, season: order.append("tto") and None
        op.opener_flag = lambda pid, season: order.append("opener") and None
        run_mlb_slate(trimmed)
    finally:
        v.warm_starts, v.delta_for, v.projected_tto, op.opener_flag = saved

    assert order, "the pricing path never reached the velocity tell at all"
    assert order[0] == "warm", f"priced before warming: {order[:3]}"
    assert order.count("warm") == 1, "warmed once per prop instead of per slate"
    assert set(warmed) == starters, "the warm pass was handed the wrong pitchers"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
