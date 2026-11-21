"""An open fold and your place on the page outlast leaving the app (FOLDKEEP1).

Ethan, 2026-11-16, with a game report's "Parlays for this game" open: "when
you click on a menu then leave the app and come back, it closes the menu and
doesn't save ur spot on the page so fix that."

Three things did it: coming back draws the page again with what changed
while the app was away (refreshOnReturn → renderAll), and a drawn <details>
starts shut; a new version reloads the page when it is put away or brought
back (register-sw.js); and a phone can drop a page it put away and load it
again. Pinned here (js/app.js):

  * every fold the reader opens or shuts is remembered for the page it is on
    (a toggle within a moment of a tap or a key), and put back wherever the
    page is drawn: renderAll keeps the place across its drawing (placeHold,
    placeKeep), and the settle pass every drawing goes through opens them;
  * the place (league and address, scroll, folds) is written down when the
    page is put away, when it is left, and when a scroll or a fold settles;
  * a load at the same address within two hours opens the folds and goes
    back to the scroll once the page is tall enough, until a touch;
  * a load anywhere else, or later, opens where it always did.

Run directly: `python3 tests/test_your_place_outlasts_leaving_the_app.py`
(the browser half with QB_BROWSER_TESTS=1 and Playwright)
"""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")


def _fn(name):
    i = APP.index(f"function {name}(")
    depth, j = 0, APP.index("{", i)
    for k in range(j, len(APP)):
        depth += {"{": 1, "}": -1}.get(APP[k], 0)
        if depth == 0:
            return APP[i:k + 1]


def test_a_redraw_keeps_the_folds_and_the_scroll():
    body = _fn("renderAll")
    hold = body.index("const _place = placeHold();")
    assert body.index("if (_meta && _boardFor && _boardFor !== _meta.api) return;") < hold, "after the guards"
    assert hold < body.index('if (state.view === "game") renderGamePage();')
    assert body.rstrip().endswith("placeKeep(_place);\n}"), "kept after every page is drawn"
    keep = _fn("placeKeep")
    assert "if (!h || h.view !== state.view || h.addr !== placeAddr()) return;" in keep, "only the same page"
    assert keep.index("foldsApply(document);") < keep.index("window.scrollTo({ top: h.y"), "the folds before the scroll"
    settle = _fn("settleNow")
    assert 'if (roots.some((r) => r.querySelector && r.querySelector("details")) && foldsApply(document)' in settle
    assert settle.index("foldsApply(document)") < settle.index("if (_settle.obs) _settle.obs.takeRecords();")
    # The scroll a drawing took goes back where the pass opened folds, but
    # never against a touch, a page just opened, or a load going back.
    assert "&& keepY != null && !_placePending && _touchedAt < keepAt && Date.now() - _viewSwitchAt > 2500" in settle
    settled = _fn("domSettled")
    assert "if (_settle.y == null) { _settle.y = _readerY; _settle.yAt = Date.now(); }" in settled, \
        "the place before the drawing, from the reader's own last scroll"
    assert "_readerY = window.scrollY || 0; placeSaveSoon();" in APP
    assert "_viewSwitchAt = Date.now();" in _fn("_switchViewNow")
    assert "return moved;" in _fn("foldsApply")


def test_only_a_fold_the_reader_moves_is_remembered():
    assert '["click", "keydown"].forEach((ev) =>\n    document.addEventListener(ev, () => { _foldTapAt = Date.now(); }, true));' in APP
    assert 'document.addEventListener("toggle", (e) => {' in APP
    assert 'if (!d || d.tagName !== "DETAILS" || Date.now() - _foldTapAt > 1000) return;' in APP
    name = _fn("foldName")
    assert 'if (d.id) return `#${d.id}`;' in name
    assert '.replace(/[\\d.,:%+\\u2212-]+/g, "#")' in name, "a title's numbers change; its words do not"
    assert "${state.sport" in _fn("placeAddr"), "each league's page is its own place"


def test_the_place_is_written_down_when_the_app_is_put_away():
    assert 'if (document.visibilityState === "hidden") placeSave();' in APP
    assert 'window.addEventListener("pagehide", placeSave);' in APP
    assert 'window.addEventListener("scroll", () => { _readerY = window.scrollY || 0; placeSaveSoon(); }, ' \
           '{ passive: true });' in APP
    save = _fn("placeSave")
    assert "const back = _placePending && _placePending.a === addr ? _placePending.y : null;" in save, \
        "a load still going back keeps the place it is going back to"
    assert "/* private mode" in save


def test_a_load_at_the_same_address_goes_back_to_it():
    assert 'var PLACE_TTL_MS = 2 * 60 * 60 * 1000;' in APP
    boot = APP[APP.index("\ninitialView();\nwatchSectionSubs();\n"):]
    assert boot.index("placeRestore();") < 200, "right after the first page is drawn and watched"
    rest = _fn("placeRestore")
    assert "if (!p || !p.a || !(Date.now() - (p.at || 0) < PLACE_TTL_MS)) return;" in rest
    assert "if (_touchedAt > began || _foldTapAt > began || Date.now() - began > 10000) return done();" in rest, \
        "a touch ends it"
    assert 'if (document.visibilityState === "hidden") { began = Date.now();' in rest, \
        "a page reloaded while away starts its clock when it is looked at"
    assert rest.index("foldsApply(document);") < rest.index("const room = document.documentElement.scrollHeight"), \
        "the folds open before the page is measured"
    for name in ("PLACE_KEY", "PLACE_TTL_MS", "_foldMemo", "_foldTapAt", "_placeTimer", "_placePending"):
        assert f"var {name} = " in APP, name


FOLDS = """<details id="kt-fold"><summary>Keep me open</summary><div style="height:2400px">one</div></details>
<details class="kt-noid"><summary>Second fold · {n} of 5</summary><div style="height:900px">two</div></details>"""
INIT = """try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb.tour', 'done');
  localStorage.setItem('qb_intro_v1', '1'); } catch (e) {}
SEED
document.addEventListener('DOMContentLoaded', () => {
  const st = document.createElement('style');
  st.textContent = '#about-body { display: none !important; }';
  document.head.appendChild(st);
  const v = document.getElementById('view-about');
  if (v) v.insertAdjacentHTML('beforeend', FOLDS_JSON);
});"""


def _browser(run):
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return None
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return None
    sys.path.insert(0, str(ROOT))
    import rendercheck
    srv, port = rendercheck._serve()
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                def page_for(seed=""):
                    ctx = browser.new_context(viewport={"width": 412, "height": 823}, is_mobile=True, has_touch=True,
                                              device_scale_factor=1, service_workers="block")
                    page = ctx.new_page()
                    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    page.add_init_script(INIT.replace("SEED", seed)
                                         .replace("FOLDS_JSON", json.dumps(FOLDS.replace("{n}", "3"))))
                    return ctx, page
                return run(page_for, f"http://127.0.0.1:{port}/index.html?sport=nfl#about")
            finally:
                browser.close()
    finally:
        srv.shutdown()


def _ready(page):
    page.wait_for_function("() => typeof placeHold === 'function' && !!document.getElementById('kt-fold')",
                           timeout=20000)
    # Past the moment a page that just opened leaves its scroll to the landing.
    page.wait_for_timeout(2700)


def test_in_a_browser_a_redraw_and_a_reload_keep_the_folds_and_the_place():
    def run(page_for, url):
        ctx, page = page_for()
        page.goto(url, wait_until="load")
        _ready(page)
        out = {"addr": page.evaluate("placeAddr()")}
        page.click("#kt-fold > summary")
        page.click(".kt-noid > summary")
        page.evaluate("window.scrollTo({ top: 1500, behavior: 'instant' })")
        page.wait_for_timeout(900)
        out["saved"] = page.evaluate("JSON.parse(localStorage.getItem('qb_place'))")
        # A drawing that builds the folds shut again, a number in a title changed.
        page.evaluate("""(html) => { document.getElementById('kt-fold').remove();
            document.querySelector('.kt-noid').remove();
            document.getElementById('view-about').insertAdjacentHTML('beforeend', html); }""",
                      FOLDS.replace("{n}", "4"))
        page.wait_for_timeout(300)
        out["redrawn"] = page.evaluate("[document.getElementById('kt-fold').open, document.querySelector('.kt-noid').open]")
        # renderAll's way: the page measured while the folds are shut, the scroll clamped, then kept.
        out["kept"] = page.evaluate("""(html) => { const h = placeHold();
            document.getElementById('kt-fold').remove(); document.querySelector('.kt-noid').remove();
            document.getElementById('view-about').insertAdjacentHTML('beforeend', html);
            void document.body.offsetHeight; const clamped = Math.round(scrollY);
            placeKeep(h);
            return [clamped, Math.round(scrollY), document.getElementById('kt-fold').open,
                    document.querySelector('.kt-noid').open]; }""", FOLDS.replace("{n}", "5"))
        # A new version reloads the page: it comes back where it was.
        page.reload(wait_until="load")
        _ready(page)
        page.wait_for_timeout(1500)
        out["reloaded"] = page.evaluate("[Math.round(scrollY), document.getElementById('kt-fold').open, "
                                        "document.querySelector('.kt-noid').open]")
        ctx.close()
        return out
    got = _browser(run)
    if got is None:
        return
    assert got["addr"].startswith("nfl|") and got["addr"].endswith("#about"), got["addr"]
    saved = got["saved"]
    assert saved["a"] == got["addr"] and saved["y"] == 1500, saved
    assert sorted(saved["f"].values()) == [True, True] and "#kt-fold|1" in saved["f"], saved
    assert got["redrawn"] == [True, True], ("a redraw shut the folds", got["redrawn"])
    clamped, y, *opened = got["kept"]
    assert clamped < 1500, ("the test page never clamped, so it checks nothing", got["kept"])
    assert y == 1500 and opened == [True, True], ("renderAll's drawing lost the place", got["kept"])
    assert got["reloaded"] == [1500, True, True], ("a reload lost the place", got["reloaded"])


def test_in_a_browser_another_address_or_an_old_place_opens_at_the_top():
    def run(page_for, url):
        out = {}
        now = int(time.time() * 1000)
        for name, addr, at in (("elsewhere", "nfl|/index.html#methodology", now),
                               ("old", "nfl|/index.html#about", now - 3 * 3600 * 1000),
                               ("other league", "nba|/index.html#about", now)):
            place = {"a": addr, "y": 1500, "f": {"#kt-fold|1": True}, "at": at}
            ctx, page = page_for(f"try {{ localStorage.setItem('qb_place', {json.dumps(json.dumps(place))}); }} "
                                 "catch (e) {}")
            page.goto(url, wait_until="load")
            _ready(page)
            page.wait_for_timeout(1500)
            out[name] = page.evaluate("[Math.round(scrollY), document.getElementById('kt-fold').open]")
            ctx.close()
        return out
    got = _browser(run)
    if got is None:
        return
    for name, (y, opened) in got.items():
        assert y == 0 and opened is False, (name, y, opened)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
