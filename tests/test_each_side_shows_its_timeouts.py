"""Each side's timeouts left, under the football score and in the bar.

Ethan, 2026-11-16, circling the score on a live Panthers @ Saints page and
the bar at the top of the screen: "Add so we can see how many timeouts each
team has". ESPN's football scoreboard carries them in the same situation
block the field's spot and down come from (`homeTimeouts`, `awayTimeouts`);
nothing read them. Now the parse keeps them for a game in progress when both
read as a count (livescores.parse_espn_rows -> LiveStatus.timeouts), the
fast file and the game's own file carry them only when present, the game
summary's situation stands in when the scoreboard's has none, and the page
draws three bars for each side, lit for each one left: under the club's name
and record in the score, under its crest in the bar.

WHAT IS NOT VERIFIED HERE, said plainly as test_live_situation.py says it:
`site.api.espn.com` is blocked from the container this was written in, so
the keys are ESPN's as its scoreboard documents them, and the parse fails
open: a block without them draws no bars at all.
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine.sources.livescores import parse_espn_rows  # noqa: E402


class _Harness:
    """A sibling test module, imported when a test first needs it (never at
    module scope: test_doctor)."""
    def __init__(self, name):
        self._name = name

    def __getattr__(self, attr):
        import importlib
        return getattr(importlib.import_module(self._name), attr)


SB = _Harness("test_every_sport_gets_the_basketball_scoreboard")
GPT = _Harness("test_the_game_page_wears_the_team_colours")
LIVE = _Harness("test_the_live_trackers")


def _event(state="in", sit=None, period=4):
    return {"date": "2026-11-15T18:00Z",
            "status": {"type": {"state": state, "shortDetail": "Final" if state == "post" else ""},
                       "period": period, "displayClock": "1:17"},
            "competitions": [{"competitors": [
                {"homeAway": "home", "team": {"abbreviation": "NO", "id": "18"}, "score": "14"},
                {"homeAway": "away", "team": {"abbreviation": "CAR", "id": "29"}, "score": "17"}],
                "situation": dict({"downDistanceText": "2nd & 7 at NO 37", "possessionText": "NO 37",
                                   "possession": "18"}, **(sit or {}))}]}


def _live(sit=None, state="in"):
    return parse_espn_rows({"events": [_event(state, sit)]})[0]["live"]


def test_the_parse_keeps_both_counts_for_a_game_in_progress():
    assert _live({"homeTimeouts": 1, "awayTimeouts": 3}).timeouts == {"home": 1, "away": 3}
    assert _live({"homeTimeouts": "2", "awayTimeouts": "0"}).timeouts == {"home": 2, "away": 0}, "a numeric string is a count"


def test_a_count_it_cannot_stand_behind_is_none():
    assert _live().timeouts is None, "no keys, no bars"
    assert _live({"homeTimeouts": 2}).timeouts is None, "one side alone is not drawn"
    assert _live({"homeTimeouts": True, "awayTimeouts": 2}).timeouts is None, "a bool is not a count"
    assert _live({"homeTimeouts": "x", "awayTimeouts": 2}).timeouts is None
    assert _live({"homeTimeouts": 12, "awayTimeouts": 2}).timeouts is None, "no side has twelve"
    assert _live({"homeTimeouts": 1, "awayTimeouts": 3}, state="post").timeouts is None, \
        "a final keeps the last block; it is not a game with timeouts to use"


def test_the_fast_file_and_the_games_file_carry_them_only_when_present():
    import livescore_build as B
    row = parse_espn_rows({"events": [_event("in", {"homeTimeouts": 1, "awayTimeouts": 3})]})[0]
    bare = parse_espn_rows({"events": [_event("in")]})[0]
    assert B._row(row, "nfl")["live"]["timeouts"] == {"home": 1, "away": 3}
    assert "timeouts" not in B._row(bare, "nfl")["live"], "absent, not empty: a missing count is not a zero"
    # The game summary's situation stands in when the scoreboard's had none.
    payload = {"drives": {"previous": [], "current": None},
               "header": {"competitions": [{"competitors": [
                   {"homeAway": "home", "team": {"id": "18", "abbreviation": "NO"}},
                   {"homeAway": "away", "team": {"id": "29", "abbreviation": "CAR"}}],
                   "situation": {"homeTimeouts": 2, "awayTimeouts": 1}}]}}
    doc = B.pbp_doc("nfl", {"event_id": "401", "home": "NO", "away": "CAR", "live": {"state": "live"}}, payload)
    assert doc["situation"]["timeouts"] == {"home": 2, "away": 1}


def _bars(html, cls):
    """[(label, lit, total)] for each side's bars, in the order drawn."""
    out = []
    for m in re.finditer(rf'<span class="{cls}" role="img" aria-label="([^"]+)">((?:<i(?: class="on")?></i>)*)</span>', html):
        out.append((m.group(1), m.group(2).count('class="on"'), m.group(2).count("<i")))
    return out


def test_the_score_draws_three_bars_a_side_under_the_name_and_record():
    got = SB._board(SB._doc("nfl", "NO", "CAR", timeouts={"home": 1, "away": 3}, period="Q4"))
    assert _bars(got, "pbp-sb-tos") == [("3 timeouts left", 3, 3), ("1 timeout left", 1, 3)], _bars(got, "pbp-sb-tos")
    away = got[got.index('<div class="pbp-sb-side away">'):got.index('<div class="pbp-sb-mid">')]
    team = away[away.index('<div class="pbp-sb-team">'):away.index('<b class="pbp-sb-pts">')]
    assert team.index('class="pbp-sb-rec"') < team.index('class="pbp-sb-tos"'), "under the record, in the club's own column"
    assert re.search(r'<b class="pbp-sb-pts">17</b>', away), "the score itself is as it was"


def test_overtime_has_fewer_and_the_summary_stands_in():
    ot = SB._board(SB._doc("nfl", "NO", "CAR", timeouts={"home": 2, "away": 1}, period="Q5"))
    assert [t for _, _, t in _bars(ot, "pbp-sb-tos")] == [2, 2], "two a side in an NFL overtime"
    college = SB._board(SB._doc("cfb", "NO", "CAR", timeouts={"home": 1, "away": 0}, period="Q5"))
    assert [(n, t) for _, n, t in _bars(college, "pbp-sb-tos")] == [(0, 1), (1, 1)], "one in a college overtime"
    summary = SB._board(dict(SB._doc("nfl", "NO", "CAR"), situation={"timeouts": {"home": 0, "away": 2}}))
    assert _bars(summary, "pbp-sb-tos") == [("2 timeouts left", 2, 3), ("0 timeouts left", 0, 3)]


def test_no_bars_where_there_is_no_count_or_no_football():
    for doc in (SB._doc("nfl", "NO", "CAR"),                                     # no count
                SB._doc("nfl", "NO", "CAR", timeouts={"home": 1, "away": 3}, state="final"),
                SB._doc("nba", "BOS", "LAL", timeouts={"home": 1, "away": 3})):  # the scorer's table has its own
        html = SB._board(doc)
        assert "pbp-sb-tos" not in html, doc["league"]


def test_the_bar_at_the_top_carries_them_under_each_crest():
    got = GPT._node("""
      const d = { away: "MIN", home: "DET", drive: { team: "MIN", plays: 3, yards: 15, start_yard_line: 40 } };
      const lv = { state: "live", period: "Q4", clock: "1:17", yard_line: 25, possession: "MIN", detail: "2nd & 7 at DET 25",
                   home_score: 14, away_score: 17, timeouts: { home: 0, away: 2 } };
      return [gpCompactHTML(d, "nfl", lv, [["plays", "Plays"]], "plays"),
              gpCompactHTML(d, "nfl", { ...lv, timeouts: null }, [["plays", "Plays"]], "plays")];
    """)
    if got is None:
        return
    bar, bare = got
    assert _bars(bar, "gp-c-tos") == [("2 timeouts left", 2, 3), ("0 timeouts left", 0, 3)], _bars(bar, "gp-c-tos")
    assert bar.count('<span class="gp-c-crest">') == 2
    assert "gp-c-tos" not in bare and "gp-c-crest" not in bare, "no count, the bar as it was"


def test_in_a_browser_the_bars_sit_clear_of_the_clock_at_390_and_1280():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    chromium = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium")
    fb = LIVE._fb_doc()
    fb["event_id"] = "e9"
    fb["live"]["timeouts"] = {"home": 2, "away": 3}
    strip = {"generated_at": fb["generated_at"], "league": "nfl", "games": [
        {"event_id": "e9", "home": "DAL", "away": "TB", "live": fb["live"], "plays_state": "ok"}]}
    serve = lambda body: (lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(body)))  # noqa: E731
    srv, port = rendercheck._serve()
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--disable-background-networking"]}
            if os.path.exists(chromium):
                kw["executable_path"] = chromium
            browser = pw.chromium.launch(**kw)
            try:
                for width in (390, 1280):
                    ctx = browser.new_context(viewport={"width": width, "height": 900}, is_mobile=width < 600,
                                              has_touch=width < 600, service_workers="block")
                    page = ctx.new_page()
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.route(lambda url: not url.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    page.route("**/data/pbp/nfl_e9.json*", serve(fb))
                    page.route("**/data/live_nfl.json*", serve(strip))
                    page.goto(f"http://127.0.0.1:{port}/#pbp/nfl/e9", wait_until="load")
                    page.wait_for_selector(".pbp-hero .pbp-sb-tos", timeout=15000)
                    got = page.evaluate("""(() => {
                      const box = (e) => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; };
                      const tos = [...document.querySelectorAll('.pbp-hero .pbp-sb-tos')];
                      const mid = document.querySelector('.pbp-hero .pbp-sb-mid');
                      const hit = (a, b) => a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3];
                      return { lit: tos.map((t) => t.querySelectorAll('i.on').length), n: tos.map((t) => t.children.length),
                               clear: tos.every((t) => !hit(box(t), box(mid))), h: tos.map((t) => box(t)[3] - box(t)[1]) };
                    })()""")
                    assert got["lit"] == [3, 2] and got["n"] == [3, 3], got
                    assert got["clear"], ("the bars stay clear of the clock's lines", got)
                    assert all(h > 2 for h in got["h"]), got
                    page.evaluate("window.scrollTo(0, 1400)")
                    page.wait_for_selector(".gp-compact.on .gp-c-tos", timeout=5000)
                    bar = page.evaluate("[...document.querySelectorAll('.gp-compact .gp-c-tos')].map((t) => t.querySelectorAll('i.on').length)")
                    assert bar == [3, 2], bar
                    assert not errors, errors
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()


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
