"""On a live game page the sport row hops between games.

Ethan, 2026-10-27, a screenshot of the Timberwolves at the Cavaliers' page
with the row of leagues circled: "if ur on the live page like how this
screenshot is you should be able to click on the sport up top and bounce
between like pages." A league's button there set the board's sport and
left the page where it was. What these hold (js/detail.js pbpHop, js/app.js
the sport buttons and markSportRow):

  - on a game page, another league's button opens that league's game in
    progress, the first on its strip; with none on, its latest final;
    with neither, the Live tab on that league;
  - the newest tap wins, and a hop that lands after the reader left the
    page does nothing; Back still goes where the first game was opened from;
  - the row lights the game's own league on a game page, whichever sport
    was in force before (one opened from Live can be any league's: an NFL
    game under a lit CFB), and the sport in force everywhere else;
  - a board game's or a pick's page, which belongs to the sport just left,
    goes back to where it was opened rather than saying the game is not on
    the slate.

Offline; the browser half is opt-in (QB_BROWSER_TESTS=1) and aborts every
request that leaves the page's own server.

    python3 tests/test_the_sport_row_hops_between_games.py
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from _app import app_js  # noqa: E402  (app.js and the rooms it loads on first use)

APP = app_js()
DETAIL = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")


def _fn(src, name):
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 3]


HOP = DETAIL[DETAIL.index("let _pbpHopSeq = 0;"):]
HOP = HOP[:HOP.index("\n}\n") + 3]


def _hop(strips, taps, leave=False):
    """Run pbpHop against stub strips; the taps go in one after another
    without waiting, as fast fingers do."""
    js = f"""
    const strips = {json.dumps(strips)};
    const out = {{ opened: [], views: [], lit: [] }};
    const state = {{ view: "pbp", pbp: {{ league: "nba", event: "1" }}, pbpFrom: "live", sport: "nba" }};
    let _liveChip = "all", _liveChipSport = "nba";
    const markSportRow = (l) => out.lit.push(l);
    const pbpStripGames = async (lg) => {{ await new Promise((r) => setTimeout(r, 5)); return strips[lg] || []; }};
    const openPbp = (lg, ev, from) => out.opened.push([lg, ev, from]);
    const switchView = (v) => out.views.push(v);
    {HOP}
    (async () => {{
      const runs = {json.dumps(taps)}.map((lg) => pbpHop(lg));
      if ({json.dumps(leave)}) state.view = "live";
      await Promise.all(runs);
      out.chip = _liveChip;
      console.log(JSON.stringify(out));
    }})();"""
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _g(eid, state, start="2026-10-27T23:00:00Z"):
    return {"event_id": eid, "home": "H", "away": "A", "live": {"state": state, "start_time": start}}


# --- the choice ----------------------------------------------------------------------
def test_a_league_with_a_game_on_opens_it():
    # The strip's own order: live first, by start, then the day's next starts, then finals.
    strips = {"nfl": [_g("n1", "live"), _g("n2", "live"), _g("n3", "scheduled"), _g("n0", "final")]}
    out = _hop(strips, ["nfl"])
    assert out["opened"] == [["nfl", "n1", "live"]], "the first game on, and Back stays where it was"
    assert out["lit"] == ["nfl"], "lit the moment it is tapped"
    assert out["views"] == []


def test_none_on_its_latest_final_then_the_live_tab():
    strips = {"mlb": [_g("m9", "scheduled"), _g("m1", "final", "2026-10-27T17:00:00Z"),
                      _g("m2", "final", "2026-10-27T20:00:00Z")],
              "mlb_pk": [{"game_pk": 776655, "home": "NYY", "away": "BOS", "live": {"state": "final"}}]}
    assert _hop(strips, ["mlb"])["opened"] == [["mlb", "m2", "live"]], "the latest final"
    pk = _hop({"mlb": strips["mlb_pk"]}, ["mlb"])
    assert pk["opened"] == [["mlb", "776655", "live"]], "baseball's games go by their game_pk"
    dark = _hop({"nhl": [_g("h1", "scheduled")]}, ["nhl"])
    assert dark["opened"] == [] and dark["views"] == ["live"] and dark["chip"] == "nhl", \
        "nothing on and nothing over: the Live tab on that league, which says so"


def test_the_newest_tap_wins_and_a_page_left_is_left():
    strips = {"nfl": [_g("n1", "live")], "mlb": [_g("m1", "live")]}
    out = _hop(strips, ["nfl", "mlb"])
    assert out["opened"] == [["mlb", "m1", "live"]], out
    assert _hop(strips, ["nfl"], leave=True)["opened"] == [], "the reader moved on while it looked"


# --- the wiring ----------------------------------------------------------------------
def test_the_buttons_hop_on_a_game_page_and_switch_the_board_everywhere():
    h = APP[APP.index("// On a game page, another league's button opens that league's game (pbpHop)."):]
    h = h[:h.index("}));")]
    assert 'const hop = state.view === "pbp" && state.pbp && state.pbp.league !== b.dataset.sport' in h
    # A league that is already the board's still hops (a game opened from Live).
    assert "if (state.sport === b.dataset.sport) { if (hop) pbpHop(b.dataset.sport); return; }" in h
    assert h.index("applySport();") < h.rindex("if (hop) pbpHop(b.dataset.sport);"), "the board switches as ever"
    # A board game's or a pick's page held the sport just left: it showed
    # "That game isn't on the current slate". Back to where it was opened.
    assert 'else if (state.view === "game" || state.view === "prop") detailBack();' in h


def test_the_row_lights_the_games_own_league():
    row = _fn(APP, "sportRowLeague")
    assert 'state.view === "pbp" && state.pbp' in row and "g.league : state.sport" in row
    assert "markSportRow();" in _fn(APP, "applySport")
    view = APP[APP.index("function _switchViewNow("):]
    view = view[:view.index('if (name === "prop") {')]
    assert "markSportRow();" in view, "every view switch marks it"
    nav = _fn(APP, "applyNavLeagues")
    assert "code === sportRowLeague()" in nav, "a league hidden in Settings still shows while its game is open"


# --- in a browser (opt-in) -------------------------------------------------------------
def test_tapping_the_leagues_in_a_browser():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    from tests import test_the_live_trackers as FB
    from tests import test_the_nba_live_page as NBA

    nba = NBA._deep()
    nba["event_id"] = "401700001"
    nfl = FB._fb_doc()
    nfl["event_id"] = "401700002"
    mlb = {"league": "mlb", "event_id": "776655", "home": "NYY", "away": "BOS", "events": [],
           "live": {"state": "final", "home_score": 5, "away_score": 3}, "current": {"inning": 9}}
    row = lambda d: {"event_id": d["event_id"], "home": d["home"], "away": d["away"], "live": d["live"]}  # noqa: E731
    files = {"data/live_nba.json": {"games": [row(nba)]},
             "data/live_nfl.json": {"games": [row(nfl)]},
             "data/live_mlb.json": {"games": [{"game_pk": 776655, "home": "NYY", "away": "BOS", "live": mlb["live"]}]},
             "data/live_nhl.json": {"games": [{"event_id": "9", "home": "BOS", "away": "NYR",
                                               "live": {"state": "scheduled", "start_time": "2030-01-01T00:00:00Z"}}]},
             f"data/pbp/nba_{nba['event_id']}.json": nba, f"data/pbp/nfl_{nfl['event_id']}.json": nfl,
             "data/pbp/mlb_776655.json": mlb}
    chromium = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium")
    srv, port = rendercheck._serve()
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists(chromium):
                kw["executable_path"] = chromium
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                          service_workers="block")
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.route(lambda url: not url.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                serve = lambda body: (lambda r: r.fulfill(status=200, content_type="application/json",  # noqa: E731
                                                          body=json.dumps(body)))
                for path, body in files.items():
                    page.route(f"**/{path}*", serve(body))
                # On the college board, then a basketball game from a link.
                page.goto(f"http://127.0.0.1:{port}/index.html?sport=cfb#pbp/nba/{nba['event_id']}", wait_until="load")

                def until(js, what):
                    for _ in range(150):
                        if page.evaluate(js):
                            return
                        page.wait_for_timeout(100)
                    raise AssertionError(f"{what}: {page.evaluate('location.hash')}, lit "
                                         + str(page.evaluate(LIT)))

                LIT = """(() => [...document.querySelectorAll('.sportbar-in .sport-btn.active[data-sport]')]
                          .map((b) => b.dataset.sport))()"""
                until(f"location.hash === '#pbp/nba/{nba['event_id']}' && !!document.querySelector('.hc-score')",
                      "the basketball game page")
                assert page.evaluate(LIT) == ["nba"], "the game's own league is lit, not the college board's"
                tap = lambda lg: page.click(f'.sportbar-in .sport-btn[data-sport="{lg}"]')  # noqa: E731
                tap("nfl")
                until(f"location.hash === '#pbp/nfl/{nfl['event_id']}' && !!document.querySelector('.pbp-hero')",
                      "NFL: its game in progress")
                assert page.evaluate(LIT) == ["nfl"]
                tap("mlb")
                until("location.hash === '#pbp/mlb/776655'", "MLB: none on, its final")
                tap("nhl")
                until("document.getElementById('view-live').classList.contains('active')", "NHL: the Live tab")
                assert page.evaluate(LIT) == ["nhl"]
                page.wait_for_timeout(500)
                chip = page.evaluate("""(() => { const c = document.querySelector('[data-chip].active, [data-chip][aria-pressed="true"]');
                                                  return c ? c.dataset.chip : null; })()""")
                assert chip == "nhl", f"the Live tab on hockey, not {chip}"
                # Opened from the college board and left again: the game's own
                # league while its page is open, the board never switched, and
                # the college board's league lit again once the page is left.
                page.goto(f"http://127.0.0.1:{port}/index.html?sport=cfb#pbp/nfl/{nfl['event_id']}", wait_until="load")
                until(f"location.hash === '#pbp/nfl/{nfl['event_id']}' && !!document.querySelector('.pbp-hero')",
                      "the NFL game page from the college board")
                assert page.evaluate(LIT) == ["nfl"] and page.evaluate("state.sport") == "cfb"
                page.evaluate("location.hash = '#live'")
                until("document.getElementById('view-live').classList.contains('active')", "back to the Live tab")
                assert page.evaluate(LIT) == ["cfb"], "leaving the game page lights the board's league again"
                assert not errors, errors
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()


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
