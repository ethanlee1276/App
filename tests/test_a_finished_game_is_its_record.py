"""A finished game's page is ESPN's page for it, and the chat bar sits at the
foot of the open Duo.

Ethan, 2026-10-30, two screenshots of yesterday's Panthers @ Packers on his
open Duo:

  * the field circled: "why do we have the game cast on this screen. It's
    just supposed to be the espn page with the past game data". The field
    (or the ballpark) draws the play in progress, and a final has none: its
    page is the score, the recap, the leaders, the scoring and the tabs. The
    Gamecast tab drops its "Last play" card the same way, and the basketball
    and hockey arenas open on the shot chart, with no Live view offered.
  * the chat bar circled: "move the chat bar down more". Under 761px
    chat.css keeps 84px under the bar for the phone's tab bar, and the open
    Duo shows the sidebar instead of that bar, so the chat bar floated a
    hand's width up and ran across the menu. Where the tab bar steps aside,
    the bar sits at the foot, from the menu's edge (or the screen's, with
    the menu slid away).

Run directly: `python3 tests/test_a_finished_game_is_its_record.py`
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731
DETAIL, GC, HOOPS, RINK = (READ("web", "js", "detail.js"), READ("web", "js", "gamecast.js"),
                           READ("web", "js", "hoopscast.js"), READ("web", "js", "rinkcast.js"))
CSS, CHAT_CSS = READ("web", "css", "styles.css"), READ("web", "css", "chat.css")


def test_a_final_draws_no_field_and_no_last_play():
    page = DETAIL[DETAIL.index("async function renderPbpPage("):]
    assert '${lv.state === "final" ? "" : `<div class="card pbp-parkcard">' in page, "no field or ballpark on a final"
    assert ('${lv.state === "final" ? "" : lastPlayHTML(d, league, faces)}${leadersHTML(d, league, faces)}'
            '${scoringHTML(d, league)}') in GC, "the Gamecast tab opens on the leaders and the scoring"


def test_the_arenas_open_a_final_on_the_shot_chart():
    want = 'const viewFor = (d) => (S.view === "live" && (d.live || {}).state === "final" ? "shots" : S.view);'
    for name, src in (("hoopscast", HOOPS), ("rinkcast", RINK)):
        assert want in src, name
        stage = src[src.index("function stageHTML("):]
        stage = stage[:stage.index("\n  }\n")]
        assert "const view = viewFor(d);" in stage, name
        assert '.filter(([key]) => key !== "live" || (d.live || {}).state !== "final")' in stage, \
            (name, "no Live view on a final")
        # The view is only ever read through viewFor (and set by the reader's tap).
        reads = [m.start() for m in re.finditer(r"S\.view\b", src)]
        assert len(reads) == 3, (name, "S.view read past viewFor", len(reads))
    chips = RINK[RINK.index("function chipsHTML("):]
    assert chips.index("const view = viewFor(d);") < chips.index('if (view === "shots")')


def test_the_chat_bar_sits_at_the_foot_where_the_tab_bar_steps_aside():
    # chat.css's phone rule keeps the tab bar's 84px…
    assert "bottom: calc(84px + env(safe-area-inset-bottom, 0px) - var(--tb-drop));" in CHAT_CSS
    # …and the layout that hides the tab bar takes it back, beside the menu.
    at = CSS.index("  .tabbar, .riding-tray { display: none; }\n  body, body.has-tray { padding-bottom: 0; }")
    block = CSS[at:CSS.index("\n}\n", at)]
    for want in ("html .gch-fab { left: calc(var(--sidebar-w) + 10px); right: 10px;\n"
                 "    bottom: calc(12px + env(safe-area-inset-bottom, 0px)); }",
                 "html body.has-tray .gch-fab { bottom: calc(12px + env(safe-area-inset-bottom, 0px)); }",
                 "html.sb-hidden .gch-fab { left: 10px; }"):
        assert want in block, want


# --- in a browser, the open Duo's size --------------------------------------------
def _doc(state):
    import test_every_game_has_a_page as T
    doc = dict(T._browser_doc())
    doc.pop("archive", None)                   # the live loop's own file, as yesterday's game is
    doc["live"] = dict(doc.get("live") or {}, state=state)
    if state == "live":
        doc["live"].update(period="Q4", clock="2:00")
    return doc


SEE = """() => { const q = (s) => document.querySelector(s), r = (e) => e && e.getBoundingClientRect();
  const fab = q('#gch-fab'), sb = q('#sidebar');
  return { park: !!q('#pbp-body .pbp-parkcard'), last: !!q('#pbp-body .gc-last'), leaders: !!q('#pbp-body .gc-leaders'),
           fab: fab && !fab.hidden && getComputedStyle(fab).display !== 'none'
             ? { bottom: Math.round(r(fab).bottom), left: Math.round(r(fab).left), right: Math.round(r(fab).right) } : null,
           sbRight: sb ? Math.round(r(sb).right) : null, h: innerHeight, w: innerWidth,
           hidden: document.documentElement.classList.contains('sb-hidden') }; }"""


def _answer(body):
    """A route handler with one parameter: Playwright hands a second (the
    request) to any handler that takes two, defaults included."""
    return lambda route: route.fulfill(status=200, content_type="application/json", body=body)


def _run():
    from playwright.sync_api import sync_playwright
    import rendercheck
    srv, port = rendercheck._serve()
    got, errs = {}, []
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                for state in ("final", "live"):
                    doc = _doc(state)
                    ctx = browser.new_context(viewport={"width": 703, "height": 1000}, service_workers="block",
                                              is_mobile=True, has_touch=True)
                    page = ctx.new_page()
                    page.on("pageerror", lambda e: errs.append(str(e)))
                    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    page.route("**/data/pbp/nfl_401.json*", _answer(json.dumps(doc)))
                    page.route("**/api/chat/**", lambda r: r.fulfill(status=200, content_type="application/json",
                                                                     body=json.dumps({"room": "nfl_401", "msgs": []})))
                    page.route("**/api/game?*", lambda r: r.fulfill(status=404, content_type="application/json", body="{}"))
                    page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb.tour','done');}catch(e){}")
                    page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#pbp/nfl/401", wait_until="load")
                    try:
                        page.wait_for_function("() => !!document.querySelector('#pbp-body .gc-leaders')", timeout=20000)
                    except Exception:                               # noqa: BLE001
                        # What the page did draw, rather than a bare timeout.
                        raise AssertionError((state, page.evaluate(
                            "[...document.querySelectorAll('#pbp-body .card')].map(c => c.className)"), errs)) from None
                    page.wait_for_timeout(1200)
                    # The bar shows once the chat's card under the scoreboard is off screen.
                    page.evaluate("window.scrollTo({top: document.documentElement.scrollHeight, behavior: 'instant'})")
                    page.wait_for_timeout(900)
                    rows = [page.evaluate(SEE)]
                    if state == "final":
                        page.click("#sb-grip")
                        page.wait_for_timeout(700)
                        rows.append(page.evaluate(SEE))
                    got[state] = rows
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    return got, errs


def test_in_a_browser_on_the_open_duo():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    got, errs = _run()
    assert not errs, errs
    final, slid = got["final"]
    assert not final["park"] and not final["last"] and final["leaders"], ("a final is its record", final)
    live = got["live"][0]
    assert live["park"] and live["last"], ("a game being played keeps its field and its last play", live)
    for row in (final, slid, live):
        fab = row["fab"]
        assert fab, ("the chat bar is up on a game the live loop keeps", row)
        assert row["h"] - fab["bottom"] <= 16, ("at the foot, not 84px up for a tab bar that is not drawn", row)
        assert fab["right"] <= row["w"] - 8, row
    assert final["fab"]["left"] >= final["sbRight"], ("beside the menu, not over it", final)
    assert slid["hidden"] and slid["fab"]["left"] <= 12, ("the menu slid away, the bar takes the width", slid)


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
