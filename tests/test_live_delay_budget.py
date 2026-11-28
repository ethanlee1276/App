"""How far behind the game the live pages are allowed to run.

Ethan, 2026-09-10, watching Patriots at Seahawks on the play-by-play
page: "its working now but definetly delayed." And again, 2026-10-25,
timing it against his television: "I'd say there's about a 45-second
delay between what actually happens on the TV compared to ... our app.
... the play-by-play, the score, all of it is very delayed."

Every term is a constant in this repo, so the delay is a sum somebody
can add up rather than a feeling:

  livescore_build.TTL        the scoreboard cache — score, clock, down
  espnplays.LIVE_TTL         the summary cache — THE PLAY LIST ITSELF
  live_build.SCOREBOARD_TTL  baseball's schedule call — score, count
  mlb pbp.LIVE_TTL           baseball's pitches
  NHL_PBP_TTL                hockey's rink events
  launch.SCORES_FAST_S       how long the score loops sleep between passes
  PASS_BUDGET_S              how long one pass works (measured, below)
  PBP_POLL_MS                how often the open game page asks
  LIVE_TICK_MS/LIVE_READ_MS  how often the Live tab asks, and one read's life
  Caddy Cache-Control        how long a shared cache may hold the file

WHAT THE SECOND COMPLAINT FOUND, measured on the live site: the files
were rewritten every 16.5 seconds (twelve asleep, four and a half
working), but the scoreboard cache under them was TWENTY — longer than a
pass — so the score and clock moved on every other write, about every
thirty-three seconds. Then the page asked every twelve, and the Live tab
answered from one read for thirty and asked again on the board's own
thirty-second reload. Each number was defensible alone; the sum was most
of a minute before ESPN's own lag behind the broadcast, which is not
ours and cannot be tuned from here.

The rule now: EVERY CACHE UNDER THE LOOP IS SHORTER THAN THE LOOP'S
SLEEP, so every pass reads the source afresh, and the sum is pinned.
"""

import re
import sys
import threading
import time
from pathlib import Path
from _app import app_js  # noqa: E402  (app.js and the rooms it loads on first use)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APP = app_js()
CADDY = (ROOT / "deploy" / "Caddyfile").read_text()

#: One pass of livescore_build on the box, measured 2026-10-25 from the
#: files' own write gaps (16.5s apart on a 12s sleep), rounded up.
PASS_BUDGET_S = 6


def _ms(name):
    m = re.search(rf"const {re.escape(name)} = (\d+);", APP)
    assert m, f"{name} is gone — the budget below cannot be added up"
    return int(m.group(1))


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\nfunction ", i + 20)]


def test_every_cache_under_the_loop_is_shorter_than_its_sleep():
    """A cache that outlives the loop's sleep is read stale on some pass,
    and the reader pays the difference — the twenty-second scoreboard
    under a twelve-second loop was exactly that."""
    import launch
    import live_build
    import livescore_build
    from engine.mlb.sources import pbp as mlbpbp
    from engine.sources import espnplays

    for name, ttl in (("livescore_build.TTL", livescore_build.TTL),
                      ("espnplays.LIVE_TTL", espnplays.LIVE_TTL),
                      ("live_build.SCOREBOARD_TTL", live_build.SCOREBOARD_TTL),
                      ("mlb pbp.LIVE_TTL", mlbpbp.LIVE_TTL),
                      ("livescore_build.NHL_PBP_TTL", livescore_build.NHL_PBP_TTL)):
        assert ttl <= launch.SCORES_FAST_S, (
            f"{name} is {ttl}s under a loop that sleeps {launch.SCORES_FAST_S}s — "
            f"some passes would read their own last copy")


def test_the_score_loops_run_on_their_own_fast_clock():
    import launch
    src = (ROOT / "launch.py").read_text()
    assert launch.SCORES_FAST_S <= 6, launch.SCORES_FAST_S
    for fn in ("_live_scores_refresher", "_live_mlb_refresher"):
        i = src.index(f"def {fn}(")
        seg = src[i:src.index("\ndef ", i + 1)]
        assert "wait = SCORES_FAST_S" in seg, fn
    # The fight card keeps its own twelve (tests/test_ufc_live.py).
    i = src.index("def _live_ufc_refresher(")
    assert "wait = LIVE_FAST_S" in src[i:src.index("\ndef ", i + 1)]


def test_the_game_page_budget_stays_under_twenty_seconds():
    """Worst case from a snap to the open game page, ESPN's own lag aside:
    the loop asleep, one pass working, the page's poll. Was 12 + 20 + 12
    plus the pass — forty-eight — on the score and clock."""
    import launch
    page = _ms("PBP_POLL_MS") / 1000
    worst = launch.SCORES_FAST_S + PASS_BUDGET_S + page
    assert worst <= 20, (
        f"{worst}s worst case: loop {launch.SCORES_FAST_S} + pass {PASS_BUDGET_S} + page {page}")


def test_the_live_tab_budget_stays_under_twenty_seconds():
    """The Live tab asked on the board's thirty-second reload and answered
    from one read kept thirty: up to a minute on its own."""
    import launch
    tick, read = _ms("LIVE_TICK_MS") / 1000, _ms("LIVE_READ_MS") / 1000
    assert read < tick, "a read kept as long as the tick serves the tick its own last answer"
    worst = launch.SCORES_FAST_S + PASS_BUDGET_S + tick
    assert worst <= 20, worst
    body = APP[APP.index("async function fetchAllLive("):]
    body = body[:body.index("\n}\n")]
    assert "_liveAll.games.length ? LIVE_READ_MS : LIVE_IDLE_READ_MS" in body
    # The model boards (odds grid, win-probability track) are not re-read
    # on the fast clock; only the small scoreboards are.
    assert "Date.now() - kept.at < LIVE_BOARD_MS" in body
    assert _ms("LIVE_BOARD_MS") >= 30000


def test_the_live_tab_has_its_own_clock_and_stops_off_the_tab():
    tick = _fn("liveTickArm")
    assert "if (!(games || []).length) return;" in tick, "it ticks with nothing in progress"
    assert 'if (state.view !== "live") return;' in tick, "it keeps polling a tab nobody is on"
    assert "liveSig(now) !== _liveDrawnSig" in tick, "it redraws whether or not anything moved"
    board = APP[APP.index("async function renderLiveBoard("):]
    board = board[:board.index("\n}\n")]
    assert "_liveDrawnSig = liveSig(games);" in board and "liveTickArm(games);" in board


def test_the_game_page_asks_every_poll_and_redraws_only_on_news():
    i = APP.index("async function renderPbpPage(")
    body = APP[i:APP.index("\nfunction ", i + 20)]
    assert "renderPbpPage(true);" in body and "}, PBP_POLL_MS);" in body
    # ONE clock: two draws in flight each armed a timer, and the page then
    # polled twice as often as it said (seen in a browser, 2026-10-25: six
    # fetches in fifteen seconds on a five-second poll).
    j = body.index("const again = () => {")
    assert "if (_pbpTimer) clearTimeout(_pbpTimer);" in body[j:j + 120]
    # Its own polls skip an unchanged file; a tab or a toggle always draws,
    # and half a minute without a draw draws anyway, so "updated … ago"
    # still shows a loop that stopped.
    assert "tick === true && d && drawn === _pbpDrawn.key && Date.now() - _pbpDrawn.at < 30000" in body
    strip = _fn("pbpStripGames")
    assert "Date.now() - _pbpStrip.at < PBP_POLL_MS - 1000" in strip


def test_no_shared_cache_may_hold_a_live_file_for_a_minute():
    """The board files earn their minute of cache; the files rewritten
    every pass do not, and a request directive does not reach a CDN."""
    assert '@built path /data/*.json' in CADDY
    i = CADDY.index("@fast path")
    rule = CADDY[i:i + 200]
    # Both shapes, because the wildcard in /data/*.json sits in the last
    # segment and pbp/ is a directory deeper.
    assert "/data/live_*.json" in rule, rule
    assert "/data/pbp/*.json" in rule, rule
    assert 'header @fast Cache-Control "no-cache"' in CADDY, rule
    # AFTER the 60-second rule, or it is overwritten by it.
    assert CADDY.index("@fast path") > CADDY.index("@built path"), \
        "the fast rule is stated before the one it must override"


def test_the_pages_still_ask_the_server_every_time():
    """`no-cache`, not `no-store`, since 2026-10-25: both ask the server on
    every fetch; `no-cache` lets an unmoved file answer 304 with no body,
    which matters at a five-second poll. Never a plain fetch, which a
    browser may answer from its own copy without asking."""
    i = APP.index("async function renderPbpPage(")
    body = APP[i:APP.index("\nfunction ", i + 20)]
    j = body.index("data/pbp/")
    assert 'cache: "no-cache"' in body[j:j + 220], body[j:j + 220]
    assert 'boardFetch(url, { cache: "no-cache" })' in _fn("pbpStripGames")
    live = APP[APP.index("async function fetchAllLive("):]
    assert 'fetch(LIVE_FAST[sport], { cache: "no-cache" })' in live[:live.index("\n}\n")]


def test_a_pass_fetches_its_summaries_together():
    """Eight games under the cap were fetched one after another, so the
    pass — and the next — waited on all eight. Four at a time now, in
    order, a failure kept to its own game."""
    import livescore_build as LB
    from engine.sources import espnplays

    lock = threading.Lock()
    flight = {"now": 0, "max": 0}

    def fake(league, event_id, ttl=None):
        with lock:
            flight["now"] += 1
            flight["max"] = max(flight["max"], flight["now"])
        time.sleep(0.15)
        with lock:
            flight["now"] -= 1
        if event_id == "e3":
            raise RuntimeError("feed down")
        return {"id": event_id}

    real = espnplays.fetch_summary
    espnplays.fetch_summary = fake
    try:
        games = [{"event_id": f"e{i}"} for i in range(8)]
        t0 = time.monotonic()
        got = list(LB._summaries("nfl", games))
        took = time.monotonic() - t0
    finally:
        espnplays.fetch_summary = real
    assert [g.get("id") if isinstance(g, dict) else "x" for g in got] == \
        ["e0", "e1", "e2", "x", "e4", "e5", "e6", "e7"]
    assert isinstance(got[3], RuntimeError)
    assert flight["max"] == LB.SUMMARY_WORKERS, flight
    assert took < 8 * 0.15 * 0.5, f"{took:.2f}s — fetched one after another"


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
