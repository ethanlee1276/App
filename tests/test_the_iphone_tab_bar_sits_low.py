"""The iPhone app's tab bar sits low (web/css/styles.css "THE CAPSULE'S FOOT";
Ethan, 2026-10-28, a screenshot from his iPhone with the bar circled: "this
bar should be lower on the screen").

The capsule stood 8px above the home indicator's whole strip (34pt on his
phone), so its foot was 42pt off the bottom of the screen with the page
showing under it. What these hold:

  * it comes down by as much of that strip as there is, up to 20px
    (--tb-drop): its foot 22pt off the edge with a home indicator, where
    iOS 26's own floating tab bars sit and still clear of the indicator,
    and 8px on a phone with a Home button, as before;
  * everything that rides above it (the page's last lines, the riding pill,
    the slip, the game chat bar, the toasts, the karma notes, the plans
    button) comes down by the same 20px, so each keeps its gap to the bar;
  * nothing moves anywhere else: a Safari tab keeps its bar flush with the
    bottom, and a computer has no bar.

Run directly: `python3 tests/test_the_iphone_tab_bar_sits_low.py`
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
READ = lambda *p: (ROOT / Path(*p)).read_text(encoding="utf-8")  # noqa: E731
CSS = READ("web", "css", "styles.css")

#: Each rule that floats something above the bar, with the drop taken off.
RIDERS = (
    ("web/css/styles.css", "html.store-ios body, html.ios-home body { padding-bottom: "
                           "calc(96px + env(safe-area-inset-bottom) - var(--tb-drop)); }"),
    ("web/css/styles.css", "padding-bottom: calc(156px + env(safe-area-inset-bottom) - var(--tb-drop)); }"),
    ("web/css/styles.css", "bottom: calc(98px + env(safe-area-inset-bottom, 0px) - var(--tb-drop)); }"),
    ("web/css/styles.css", "#qb-slip { bottom: calc(58px + env(safe-area-inset-bottom) - var(--tb-drop)); }"),
    ("web/css/styles.css", "bottom: calc(100px + env(safe-area-inset-bottom, 0px) - var(--tb-drop)); }"),
    ("web/css/chat.css", "bottom: calc(84px + env(safe-area-inset-bottom, 0px) - var(--tb-drop)); }"),
    ("web/css/chat.css", "body.has-tray .gch-fab { bottom: calc(144px + env(safe-area-inset-bottom, 0px) - var(--tb-drop)); }"),
    ("web/css/karma.css", "bottom: calc(96px + env(safe-area-inset-bottom, 0px) - var(--tb-drop)); z-index: 92;"),
    ("web/css/account.css", "bottom: calc(74px + env(safe-area-inset-bottom, 0px) - var(--tb-drop));"),
)


def test_the_drop_is_the_iphone_apps_alone():
    root = CSS[CSS.index(":root {"):]
    assert re.search(r"--tb-drop:\s*0px;", root[:root.index("\n}\n")]), "0 unless the iPhone app's capsule is up"
    set_ = "html.store-ios, html.ios-home { --tb-drop: min(20px, env(safe-area-inset-bottom, 0px)); }"
    assert set_ in CSS
    assert CSS.rfind("@media (max-width: 760px) {", 0, CSS.index(set_)) > CSS.rfind("}\n}", 0, CSS.index(set_)), \
        "on a phone's width only, where the capsule is"
    assert len(re.findall(r"--tb-drop:", CSS)) == 2, "set in one place"


def test_the_capsule_and_everything_above_it_come_down_together():
    assert "left: 12px; right: 12px; bottom: calc(8px + env(safe-area-inset-bottom) - var(--tb-drop));" in CSS
    for path, rule in RIDERS:
        assert rule in READ(*path.split("/")), (path, rule)
    # Nothing that reaches the bottom edge, or sits on a screen without the
    # bar, moves: the menu, the sheets, the wall's own docks.
    for keep in (".more-scrim, .more-sheet { bottom: calc(-1 * var(--vgap)); }",
                 "body.walled.on-wall .a2hs { bottom: calc(12px + env(safe-area-inset-bottom, 0px)); }"):
        assert keep in CSS, keep
    assert "body.walled.on-wall .pw-dock { bottom: calc(12px + env(safe-area-inset-bottom, 0px)); }" in \
        READ("web", "css", "account.css")


# --- on an iPhone's screen ----------------------------------------------------------
IPHONE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 26_0 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/26.0 Mobile/15E148 Safari/604.1")
W, H = 393, 852
PROBE = """(async () => {
  // The rooms' own sheets load on first use; the probe loads them itself.
  await Promise.all(['css/chat.css', 'css/karma.css', 'css/account.css'].map((href) => new Promise((ok) => {
    const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = href;
    l.onload = l.onerror = ok; document.head.appendChild(l); })));
  const made = {};
  for (const [k, html] of [['toast', '<div class="tf-toast">x</div>'], ['crash', '<div class="crash-note">x</div>'],
                           ['chat', '<button class="gch-fab">x</button>'], ['notes', '<div class="kr-notes"></div>'],
                           ['dock', '<div class="pw-dock">x</div>']]) {
    const t = document.createElement('template'); t.innerHTML = html; made[k] = t.content.firstChild;
    document.body.appendChild(made[k]);
  }
  // A custom property keeps its text ("min(20px, 34px)"); a length reads it out.
  const ruler = document.createElement('div'); ruler.style.cssText = 'position: fixed; bottom: var(--tb-drop);';
  document.body.appendChild(ruler);
  const px = (e) => e ? Math.round(parseFloat(getComputedStyle(e).bottom)) : null;
  const tab = document.querySelector('.tabbar').getBoundingClientRect();
  return { home: document.documentElement.classList.contains('ios-home'),
           drop: getComputedStyle(ruler).bottom,
           foot: Math.round(innerHeight - tab.bottom), top: Math.round(innerHeight - tab.top),
           pad: Math.round(parseFloat(getComputedStyle(document.body).paddingBottom)),
           tray: px(document.querySelector('.riding-tray')), slip: px(document.getElementById('qb-slip')),
           toast: px(made.toast), crash: px(made.crash), chat: px(made.chat), notes: px(made.notes), dock: px(made.dock) };
})()"""


def _measure(standalone: bool, inset: int) -> dict:
    from playwright.sync_api import sync_playwright
    sys.path.insert(0, str(ROOT / "tests"))
    import rendercheck
    me = {"signed_in": True, "email": "you@example.com", "profile": {"handle": "ethan", "name": "Ethan", "color": 1}}
    ful = lambda b: (lambda r: r.fulfill(status=200, content_type="application/json", body=b))  # noqa: E731
    srv, port = rendercheck._serve()
    errs = []
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": W, "height": H}, screen={"width": W, "height": H},
                                          user_agent=IPHONE_UA, is_mobile=True, has_touch=True,
                                          service_workers="block")
                page = ctx.new_page()
                page.on("pageerror", lambda e: errs.append(str(e)))
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/**", ful("{}"))
                page.route("**/api/account/me*", ful(json.dumps(me)))
                page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb-seen-intro','1');"
                                     "localStorage.setItem('qb.tour','done');localStorage.setItem('qb.a2hs','off');}catch(e){}")
                if standalone:
                    page.add_init_script("Object.defineProperty(navigator, 'standalone', { get: () => true });")
                # The home indicator's strip, as iOS reports it to the page (Chromium's own is 0).
                ctx.new_cdp_session(page).send("Emulation.setSafeAreaInsetsOverride",
                                               {"insets": {"top": 59 if inset else 20, "bottom": inset,
                                                           "left": 0, "right": 0}})
                page.goto(f"http://127.0.0.1:{port}/index.html", wait_until="load")
                page.wait_for_selector(".tabbar", timeout=15000)
                page.wait_for_timeout(1200)
                got = page.evaluate(PROBE)
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert not errs, errs
    return got


def test_on_an_iphone_the_bar_sits_low_and_its_riders_with_it():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    app = _measure(True, 34)
    assert app["home"] and app["drop"] == "20px", app
    assert app["foot"] == 22, f"the capsule's foot 22pt off the edge, clear of the indicator (8-13pt): {app}"
    assert app["top"] < 100, app
    # Each rider 20px lower than it was, so its gap to the bar is the same.
    want = {"pad": 96 + 34 - 20, "tray": 98 + 34 - 20, "slip": 58 + 34 - 20, "toast": 100 + 34 - 20,
            "crash": 100 + 34 - 20, "chat": 84 + 34 - 20, "notes": 96 + 34 - 20, "dock": 74 + 34 - 20}
    assert {k: app[k] for k in want} == want, app
    assert app["pad"] > app["top"] and app["tray"] > app["top"], "the page's end and the pill clear the bar"
    old = _measure(True, 0)                       # a phone with a Home button: no strip, nothing moves
    assert old["drop"] == "0px" and old["foot"] == 8 and old["pad"] == 96, old
    tab = _measure(False, 34)                     # Safari: the bar flush with the bottom, as it was
    assert not tab["home"] and tab["drop"] == "0px" and tab["foot"] == 0, tab
    assert (tab["slip"], tab["chat"], tab["notes"], tab["dock"]) == (58 + 34, 84 + 34, 96 + 34, 74 + 34), tab


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
