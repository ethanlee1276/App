"""A league out of season wears grey, and is still a button.

Ethan, 2026-11-06, circling the league row in a phone screenshot: "whatever
sport is no longer going, like the season is over, we should grey out there
button up here since there is no point for a user too use the page.
Obviously still keep the page accessible and able too click."

What these hold:

  * the server names the leagues out of season in the heartbeat the page
    already reads (`launch._seasons_public`): a league the season table
    holds outside every phase (MLB and the WNBA on the day Ethan asked),
    and one in its postseason whose own board says the season has ended,
    the same word that takes it out of the odds plan, so the row and the
    credits never disagree; a failure is {} (nothing greyed), never an
    error and never a heartbeat lost;
  * the page greys exactly those buttons (app.js `markSeasons`) and leaves
    them buttons: no `disabled`, no `aria-disabled`, no `pointer-events`,
    nothing taken out of the tab order; the tooltip says the season is
    over;
  * the grey can be seen at both widths: the in-season leagues' codes rest
    on `--text-mute`, so an off-season code rests on the faint tier below
    it; a hover, a keyboard focus or the open page lifts it back; on phones
    the crest's glyph greys with it;
  * in a browser, at phone and computer widths: MLB and the WNBA grey and
    nothing else does, a click on MLB still opens MLB, and a season that
    comes back takes the grey off.

Run directly: `python3 tests/test_a_league_out_of_season_wears_grey.py`
(the browser check with QB_BROWSER_TESTS=1 and /usr/bin/python3).
"""
import datetime as dt
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import launch                                                       # noqa: E402
from engine import oddsplan                                         # noqa: E402

CSS = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
LEAGUES = ("nfl", "cfb", "mlb", "nba", "wnba", "nhl", "ufc")
BOARDS = ("MLB_OUT", "NBA_OUT", "WNBA_OUT", "NHL_OUT", "CFB_OUT")
ASKED = dt.date(2026, 11, 6)


class _Boards:
    """Every postseason board pointed at a scratch folder: missing (which
    says nothing) until a test writes one."""

    def __enter__(self):
        self.dir = tempfile.mkdtemp()
        self.saved = {k: getattr(launch, k) for k in BOARDS}
        for k in BOARDS:
            setattr(launch, k, os.path.join(self.dir, "missing.json"))
        launch._SEASONS_OVER[:] = [0.0, frozenset()]
        return self

    def write(self, attr, body):
        path = os.path.join(self.dir, attr.lower() + ".json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(body, fh)
        setattr(launch, attr, path)

    def __exit__(self, *exc):
        for k, v in self.saved.items():
            setattr(launch, k, v)
        launch._SEASONS_OVER[:] = [0.0, frozenset()]
        return False


def _fn(name: str) -> str:
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i)]


def _rule(selector: str) -> str:
    i = CSS.index(selector + " {")
    return CSS[i:CSS.index("}", i) + 1]


# --- the server: which leagues are out ------------------------------------------
def test_the_calendar_names_the_leagues_not_playing():
    with _Boards():
        assert launch._seasons_public(ASKED) == {"over": ["mlb", "wnba"]}, \
            "the day Ethan asked: baseball and the WNBA are done, the rest are playing"
        assert launch._seasons_public(dt.date(2027, 2, 1)) == {"over": ["cfb", "mlb", "wnba"]}, \
            "February: the NFL's playoffs, the NBA and the NHL still on"
        july = launch._seasons_public(dt.date(2027, 7, 4))
        assert july == {"over": ["cfb", "nba", "nfl", "nhl"]}, july
        for day in (ASKED, dt.date(2027, 2, 1), dt.date(2027, 7, 4), dt.date(2027, 12, 25)):
            over = launch._seasons_public(day)["over"]
            assert over == sorted(over) and set(over) <= set(LEAGUES), (day, over)
            assert "ufc" not in over, "the UFC fights all year"


def test_a_postseason_its_board_says_has_ended_greys_before_the_calendar_does():
    """The table runs baseball's postseason to 4 November whatever the World
    Series does; the board knows the night the last out is made."""
    day = dt.date(2026, 10, 30)
    assert oddsplan.season_phase("mlb", day) not in (None, "regular"), "a postseason day"
    with _Boards() as b:
        assert launch._seasons_public(day) == {"over": ["wnba"]}, "a board that cannot be read says nothing"
        b.write("MLB_OUT", {"games": [{}], "upcoming": {"date": "2026-10-31", "days_ahead": 1}})
        assert launch._seasons_public(day) == {"over": ["wnba"]}, "a game tonight: still playing"
        b.write("MLB_OUT", {"games": []})
        assert launch._seasons_public(day) == {"over": ["mlb", "wnba"]}, "the World Series is over"
        assert set(launch._seasons_over(day)) <= set(launch._seasons_public(day)["over"]), \
            "a league out of the odds plan is grey in the row"


def test_a_failure_greys_nothing_and_never_costs_the_heartbeat():
    def torn(*_a, **_k):
        raise RuntimeError("a torn season table")
    real = oddsplan.season_phase
    oddsplan.season_phase = torn
    try:
        assert launch._seasons_public(ASKED) == {}
    finally:
        oddsplan.season_phase = real


def test_the_heartbeat_carries_the_list():
    tmp = Path(tempfile.mkdtemp())
    (tmp / "web" / "data").mkdir(parents=True)
    saved_root = launch.ROOT
    with _Boards():
        before = launch._seasons_public()
        launch.ROOT = tmp
        try:
            launch._write_heartbeat(60)
        finally:
            launch.ROOT = saved_root
        after = launch._seasons_public()
    beat = json.loads((tmp / "web" / "data" / "heartbeat.json").read_text(encoding="utf-8"))
    assert beat.get("seasons") in (before, after), beat.get("seasons")
    assert isinstance(beat["seasons"].get("over"), list)


# --- the page: grey, and still a button -------------------------------------------
def test_the_page_greys_the_named_buttons_and_leaves_them_buttons():
    fn = _fn("markSeasons")
    assert '.sportbar-in .sport-btn[data-kind="league"]' in fn, "the league row's buttons, no others"
    assert 'classList.toggle("off-season", off)' in fn, "greyed when out, ungreyed when back"
    assert "Season over" in fn and "titleBase" in fn, "the tooltip says why, and gets its own words back"
    code = re.sub(r"//[^\n]*", "", fn)
    for word in ("disabled", "aria-disabled", "pointer-events", "tabindex", "inert", "preventDefault"):
        assert word not in code, f"{word}: a league out of season is still a button"
    assert "if (!seasons || !Array.isArray(seasons.over)) return;" in fn, \
        "a heartbeat without the list (an older server) changes nothing"
    assert "markSeasons(hb.seasons);" in _fn("loadHeartbeat")


def test_the_grey_shows_at_both_widths_and_lifts_when_reached_for():
    rest = _rule(".sportbar-in .sport-btn")
    assert "color: var(--text-mute)" in rest, "the in-season leagues' codes rest on --text-mute"
    off = _rule(".sportbar-in .sport-btn.off-season")
    assert "--hue: var(--text-mute)" in off, "the crest, the hover and the lit state lose the league's colour"
    assert "color: var(--text-faint)" in off, \
        "below the in-season tier at rest: on --text-mute a computer showed no grey at all"
    at = CSS.index(off)
    assert CSS.index('.sportbar-in .sport-btn[data-sport="ufc"] { --hue') < at, "after every league's colour"
    assert at < CSS.index(".sportbar-in .sport-btn:hover { color: var(--hue); }"), "a hover lifts it"
    assert at < CSS.index(".sportbar-in .sport-btn.active { color: var(--hue);"), "the open page lifts it"
    assert ".sportbar-in .sport-btn.off-season:focus-visible { color: var(--hue); }" in CSS, "a keyboard lifts it"
    crest = ".sportbar-in .sport-btn.off-season:not(.active) .crest { color: var(--text-faint); }"
    assert crest in CSS, "the phone's crest greys with its code"
    assert CSS.index(crest) < CSS.index(".sportbar-in .sport-btn.active .crest { outline-color: transparent; color: var(--hue);")
    for rule in re.findall(r"[^{}]*\.off-season[^{}]*\{[^}]*\}", CSS):
        for word in ("pointer-events", "cursor", "display", "visibility"):
            assert word not in rule, f"{word} in {rule.strip()}: it stays a button"


# --- in a browser -----------------------------------------------------------------
def test_in_a_browser_mlb_and_the_wnba_grey_and_still_open():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    from test_every_page_opens_clean import _board

    body = json.dumps(_board())
    hb = json.dumps({"cycle_p50_s": 60, "seasons": {"over": ["mlb", "wnba"]}})
    rows_js = """[...document.querySelectorAll('.sportbar-in .sport-btn[data-kind="league"]')].map(b => ({
        sport: b.dataset.sport, off: b.classList.contains('off-season'), title: b.title,
        base: b.dataset.titleBase, color: getComputedStyle(b).color,
        disabled: b.disabled || b.getAttribute('aria-disabled') === 'true' || b.tabIndex < 0,
        events: getComputedStyle(b).pointerEvents}))"""
    # A tier's colour, read off a fresh element: it has no colour to move
    # from, so it is never caught halfway through a transition the way a
    # button can be on a busy machine (gate 81 read the NFL button mid-way).
    tier_js = """(v) => { const p = document.createElement('span'); p.style.color = `var(${v})`;
                          document.body.appendChild(p); const c = getComputedStyle(p).color; p.remove(); return c; }"""

    def settled(page, sport, want):
        """The button's colour once its 120 ms colour transition has run
        (read straight after the class lands, it is still the old one).

        An ARROW, not a bare expression: the page's own Content-Security-
        Policy (server.py, `script-src 'self'`) refuses the eval Playwright
        polls a bare expression with, so one that is not true at the first
        look throws an EvalError instead of waiting. Only a timeout is
        caught; anything else is a broken check and fails as one."""
        from playwright.sync_api import TimeoutError as Timeout
        read = f"""getComputedStyle(document.querySelector('.sportbar-in .sport-btn[data-sport="{sport}"]')).color"""
        try:
            page.wait_for_function(f"(want) => {read} === want", arg=want, timeout=3000)
        except Timeout:
            pass
        return page.evaluate(read)
    chromium = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium")
    srv, port = rendercheck._serve()
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists(chromium):
                kw["executable_path"] = chromium
            browser = pw.chromium.launch(**kw)
            try:
                for vp, mobile in (({"width": 390, "height": 844}, True), ({"width": 1366, "height": 800}, False)):
                    ctx = browser.new_context(viewport=vp, is_mobile=mobile, has_touch=mobile,
                                              service_workers="block")
                    page = ctx.new_page()
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.add_init_script("try { localStorage.setItem('qb-seen-intro', '1');"
                                         " localStorage.setItem('qb.tour', 'done'); } catch (e) {}")
                    page.route(lambda url: not url.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
                    page.route("**/data/heartbeat.json*",
                               lambda r: r.fulfill(status=200, content_type="application/json", body=hb))
                    for pat in ("**/api/recommendations*", "**/data/recommendations*.json*"):
                        page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=body))
                    page.goto(f"http://127.0.0.1:{port}/index.html?sport=nba#recommended", wait_until="load")
                    page.wait_for_selector(".sportbar-in .sport-btn.off-season", timeout=10000)
                    where = f"{vp['width']}px"
                    faint, mute = page.evaluate(tier_js, "--text-faint"), page.evaluate(tier_js, "--text-mute")
                    assert faint != mute, (faint, mute)
                    for sport in ("mlb", "wnba"):
                        got = settled(page, sport, faint)
                        assert got == faint, (where, sport, got, faint)
                    got = settled(page, "nfl", mute)
                    assert got == mute, (where, "an in-season league keeps its tier", got, mute)
                    by = {r["sport"]: r for r in page.evaluate(rows_js)}
                    assert {s for s, r in by.items() if r["off"]} == {"mlb", "wnba"}, (where, by)
                    assert by["mlb"]["title"].startswith("Season over"), (where, by["mlb"])
                    assert not by["nfl"]["title"].startswith("Season over"), (where, by["nfl"])
                    assert not any(r["disabled"] for r in by.values()), (where, by)
                    assert all(r["events"] != "none" for r in by.values()), (where, by)
                    page.click('.sportbar-in .sport-btn[data-sport="mlb"]')
                    page.wait_for_function("() => document.documentElement.dataset.league === 'mlb'", timeout=8000)
                    got = settled(page, "mlb", mute)
                    assert got == mute, (where, "its page opens, and the open league is lifted out of the faint tier", got)
                    now = {r["sport"]: r for r in page.evaluate(rows_js)}
                    assert now["mlb"]["off"], (where, "still out of season while open")
                    page.evaluate("markSeasons({over: []})")
                    back = page.evaluate(rows_js)
                    assert not any(r["off"] for r in back), (where, "a season that comes back takes the grey off")
                    assert all(r["title"] == (r["base"] or "") for r in back), (where, back)
                    page.evaluate("markSeasons(undefined); markSeasons({}); markSeasons({over: 'mlb'})")
                    assert not any(r["off"] for r in page.evaluate(rows_js)), "a malformed list changes nothing"
                    assert not errors, (where, errors)
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
