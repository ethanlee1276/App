"""The live football page says each thing once (2026-11-15).

Ethan, on the live NE @ DET page (a desktop screenshot): "also we dont need
the drive chart since we have one at the top of the screen. go look through
the live page bc it seems likes there is alot of repeated stuff."

What the page drew, counted on a render of that game's own file: the ball's
spot four times (the field under the score, the drive card's field, the
"Ball on" strip under the photograph, the drive chart), the drive's "10
plays, 60 yards, 5:32" three times, our win chance twice (the card's chip
and the Win probability card), and on a desktop the plays twice, side by
side (the Play-By-Play tab and the rail beside it).

Now, while the field under the score is drawn (detail.js gpFieldModel), and
its small copy at the top of the screen once the page scrolls:

  * no drive chart while the game is on (a final keeps it: no field above);
  * the drive card heads itself with the last play and its time, and leaves
    out the Down and Ball on tiles and the "Current drive" line;
  * the card's win chip goes when our Win probability card is drawn;
  * the photograph leaves out its "Ball on" strip;
  * the compact bar says the down and the spot under the clock;
  * on the Play-By-Play tab the rail holds our picks on the game instead of
    a second list of the plays.

    python3 tests/test_the_live_page_says_each_thing_once.py
    QB_BROWSER_TESTS=1 python3 tests/test_the_live_page_says_each_thing_once.py
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))


class _Harness:
    """A sibling test module, imported when a test first needs it (never at
    module scope: test_doctor)."""
    def __init__(self, name):
        self._name = name

    def __getattr__(self, attr):
        import importlib
        return getattr(importlib.import_module(self._name), attr)


CARD = _Harness("test_the_drive_card_says_what_happened")
LIVE = _Harness("test_the_live_trackers")

DETAIL = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
GC = (ROOT / "web" / "js" / "gamecast.js").read_text(encoding="utf-8")
DETAIL_CSS = (ROOT / "web" / "css" / "detail.css").read_text(encoding="utf-8")


def _fn(src, head):
    i = src.index(head)
    return src[i:src.index("\n}\n", i)]


def _card(play, opts, live=None):
    doc = CARD._doc(play, live)
    return CARD.G._node(f"return QBGamecast.driveView({json.dumps(doc)}, 'nfl', {{}}, {json.dumps(opts)});")


def test_under_the_field_the_card_heads_itself_with_the_last_play():
    html = _card(CARD.PUNT, {"top": True, "win": True})
    if html is None:
        return
    words = CARD._text(html)
    head = CARD._text(html[html.index('<div class="gc-dv-head">'):html.index('<span class="gc-dv-end">')])
    assert head == "TB Last play · Q2 13:52 Punt", head
    for gone in ("Current drive", "0 plays, 0 yards", "Down 1st & 10", "Ball on DAL 32", "Win % (our model)"):
        assert gone not in words, (gone, words)
    assert "gc-dv-tiles" not in html and "gc-dv-chip" not in html and "gc-dv-lhead" not in html
    # What it adds to the field above stays: the drawing, the sentence, the people.
    assert "Riley Dixon punts to the DAL 16; KaVontae Turpin brings it back 16 yards to the DAL 32." in words
    assert "data-gc-dv-replay" in html and 'class="gc-dv-pin"' in html


def test_the_win_chip_goes_only_when_the_page_draws_our_card():
    html = _card(CARD.PUNT, {"top": True, "win": False})
    if html is None:
        return
    assert "Win % (our model)" in CARD._text(html) and "gc-dv-chip" not in html
    both = _card(CARD.PUNT, {"top": False, "win": True})
    words = CARD._text(both)
    assert "Win % (our model)" not in words and "Last play · Q2 13:52" in words and "Current drive" in words


def test_with_no_field_above_the_card_is_the_card_it_was():
    html = _card(CARD.PUNT, {})
    if html is None:
        return
    words = CARD._text(html)
    for kept in ("Current drive", "0 plays, 0 yards, 0:00", "Down 1st & 10", "Ball on DAL 32",
                 "Win % (our model)", "Last play · Q2 13:52"):
        assert kept in words, (kept, words)


def test_no_play_yet_under_the_field_is_no_card():
    doc = CARD._doc(CARD.PUNT)
    doc["plays"] = []
    doc["drive"] = {"team": "DAL", "plays": 0, "yards": 0, "elapsed": "0:00", "period": 2}
    got = CARD.G._node(f"""const d = {json.dumps(doc)};
      return [QBGamecast.driveView(d, 'nfl', {{}}, {{ top: true }}), QBGamecast.driveView(d, 'nfl', {{}})];""")
    if got is None:
        return
    assert got[0] == "", "the field under the score already says all it would"
    assert "Current drive" in got[1]


def test_the_replay_redraws_the_card_with_the_same_options():
    assert "_dvLast = { d, league, faces, opts: o };" in GC
    assert "driveViewHTML(_dvLast.d, _dvLast.league, _dvLast.faces, _dvLast.opts)" in GC


def test_the_plays_tab_draws_each_thing_once():
    body = _fn(DETAIL, "function gpPlaysHTML(d, league, faces, boardGame, lastPlay, GC)")
    assert "const top = !!gpFieldModel(d, league, lv);" in body
    assert "g.driveView(d, league, faces, { top, win: !!ours })" in body
    assert "const chart = !live && g.gameChart ? g.gameChart(d, league) : \"\";" in body, "no drive chart while live"
    assert "pbpParkHTML(d, league, boardGame, lastPlay, { strip: !top })" in body
    park = _fn(APP, "function pbpParkHTML(d, league, boardGame, hitRow, opts)")
    assert "${isFootball && o.strip !== false ? pbpFieldPosHTML(d, hitRow) : \"\"}" in park


def test_the_rail_holds_the_picks_on_the_plays_tab_and_the_plays_elsewhere():
    page = _fn(DETAIL, "function gpFootballHTML(o)")
    assert '${tab === "plays" ? gpRailPicksHTML(d, league) : `<div class="card pbp-railcard">' in page
    rail = _fn(DETAIL, "function gpRailPicksHTML(d, league)")
    assert 'class="card pbp-railcard gp-rail-picks"' in rail and "pbpPropsHTML(d, league)" in rail
    # A phone folds the rail card away, as before: its tabs are one tap apart.
    assert "@media (max-width: 980px) { .pbp-has-tabs .pbp-railcard { display: none; } }" in DETAIL_CSS


def test_the_compact_bar_says_the_down_under_the_clock():
    bar = _fn(DETAIL, "function gpCompactHTML(d, league, lv, tabs, tab)")
    assert '<span class="gp-c-down">${escapeHtml(m.words)}</span>' in bar
    assert "${escapeHtml(gpClockWord(league, lv))}${down}</span>" in bar
    assert ".gp-c-down { display: block;" in DETAIL_CSS


# --- the page in a browser (opt-in) ------------------------------------------------
def test_the_live_page_in_a_browser_at_390_and_1280():
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
    fb["live"]["win_prob"] = {"home": "DAL", "away": "TB", "home_win_prob": 0.61, "away_win_prob": 0.39,
                              "basis": "score and clock against the pregame line"}
    strip = {"generated_at": fb["generated_at"], "league": "nfl", "games": [
        {"event_id": "e9", "home": "DAL", "away": "TB", "live": fb["live"], "plays_state": "ok"}]}
    serve = lambda body: (lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(body)))
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
                    page.wait_for_selector(".gc-dv [data-gc-dv-replay]", timeout=15000)
                    page.evaluate("document.querySelectorAll('#tour-overlay, .tour-pop').forEach((n) => n.remove())")
                    got = page.evaluate("""(() => {
                      const q = (s) => document.querySelector(s), n = (s) => document.querySelectorAll(s).length;
                      const t = (s) => (q(s) ? q(s).textContent.replace(/\\s+/g, ' ').trim() : '');
                      return { field: n('.gp-field .gp-fd'), head: t('.gc-dv .gc-dv-head'), tiles: n('.gc-dv-tiles'),
                               chip: n('.gc-dv .gc-win'), ours: n('.pbp-panel .pbp-wp'), strip: n('.pbp-parkcard .pbp-fpos'),
                               park: n('.pbp-parkcard .pbp-park'), down: t('.gp-compact .gp-c-down') };
                    })()""")
                    assert got["field"] == 1, got
                    assert "Last play · Q3 11:02" in got["head"] and "Current drive" not in got["head"], got
                    assert got["tiles"] == 0 and got["strip"] == 0 and got["park"] == 1, got
                    assert got["ours"] == 1 and got["chip"] == 0, "our win card once, no chip beside the play"
                    assert got["down"] == "3rd & 8 · TB 24", got
                    page.click('.pbp-tab[data-pbp-tab="plays"]')
                    page.wait_for_selector(".pbp-panel .gp-dr", state="attached", timeout=5000)
                    tab = page.evaluate("""(() => {
                      const rail = document.querySelector('.pbp-rail');
                      const shown = (e) => !!e && getComputedStyle(e).display !== 'none' && e.getBoundingClientRect().height > 0;
                      return { chart: document.querySelectorAll('.gc-chart').length,
                               picks: shown(rail.querySelector('.gp-rail-picks')),
                               railPlays: rail.querySelectorAll('.pbp-group, .lb-play').length,
                               drives: document.querySelectorAll('.pbp-panel .gp-dr').length,
                               wide: document.scrollingElement.scrollWidth };
                    })()""")
                    assert tab["chart"] == 0, "no drive chart on a live game"
                    assert tab["railPlays"] == 0 and tab["drives"] >= 1, tab
                    assert tab["picks"] == (width > 980), tab
                    assert tab["wide"] <= width, tab
                    page.click('.pbp-tab[data-pbp-tab="stats"]')
                    page.wait_for_selector(".pbp-rail .pbp-group", state="attached", timeout=5000)
                    assert not page.query_selector(".pbp-rail .gp-rail-picks"), "the plays come back beside the other tabs"
                    assert not errors, errors
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc(limit=6)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
