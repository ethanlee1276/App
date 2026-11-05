"""The top of a game page is one picture: no black block, no seams.

Ethan, 2026-11-02, his open Duo (703 by 1000, the installed app), the top of
a live Chiefs-Broncos game circled: "fix how the colors glitch out here".
Three things painted the top of the page over the clubs' wash, each its
own way:

  * the strip that holds the clock's place in the installed app
    (styles.css html.ios-home body::before) painted the page's black, so a
    black block sat over the docked sidebar;
  * the site's bar painted the clubs' gradient across its own width;
  * the compact score bar painted a darker copy across a screen's width
    centred on the column, so it met the bar in a hard seam at the
    sidebar's edge.

Now every one of them paints the wash's own picture (the shade over the
wash, the size of the screen, pinned to the screen's corner; detail.js
gpPin says where the two bars sit). These hold:

  * one rule paints all of them, the compact bar keeps no colour of its own,
    and the shade lives where the strip and the bar can reach it;
  * gpPin measures the two bars on every draw and when the column resizes,
    and leaving the game takes the site bar's pins off;
  * where the sidebar is docked the score bar spans its column (it ran
    under the sidebar, back button and all, and off the other edge), and
    a short fade below it, never beside it, says where it ends;
  * the scroll-driven sheen that slides the site's bar's first layer
    (styles.css glass-drift) is off on this page: on it, that layer is the
    shade, so the bar's colours slid away from the rest as the page moved;
  * in a browser at the open Duo's size with a 40px status bar, the row
    under the clock runs on without a jump and without the page's black,
    and so does a row through the site's bar and the score bar across the
    sidebar's edge, scrolled; the same under the clock on a phone with the
    score bar away.

Run directly: `python3 tests/test_the_top_of_the_game_page_is_one_picture.py`
"""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731
CSS, JS = READ("web", "css", "detail.css"), READ("web", "js", "detail.js")
PICTURE = ("#view-pbp.gp-on > .gp-wash, body.gp-on .topbar, #view-pbp.gp-on .gp-compact,\n"
           "html.store-ios body.gp-on::before, html.ios-home body.gp-on::before,\n"
           "html.store-ios.team-tint body.gp-on::before, html.ios-home.team-tint body.gp-on::before {\n"
           "  background: var(--gp-shade), var(--gp-wash) #0C0B0A;\n"
           "  background-size: 100vw 100vh; background-repeat: no-repeat;\n"
           "  background-position: var(--gp-x, 0px) var(--gp-y, 0px);\n}")


def _fn(src, name):
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i)]


def test_one_rule_paints_every_surface_at_the_top():
    assert PICTURE in CSS, "the wash, the site's bar, the compact bar and the clock's strip paint one picture"
    rule = CSS[CSS.index(".gp-compact { position: absolute;"):]
    rule = rule[:rule.index("}")]
    assert "background" not in rule, "the compact bar keeps no colour of its own"
    assert "--gp-bar-shade" not in CSS, "nor the darker copy it used to paint"
    body = CSS[CSS.index("body.gp-on { --wa:"):]
    body = body[:body.index("}")]
    assert "--gp-shade: linear-gradient(180deg," in body and "#0C0B0A 820px" in body, \
        "the shade is the body's, so the strip and the site's bar outside the view can paint it"
    view = CSS[CSS.index("#view-pbp.gp-on {\n  /* The glass"):]
    assert "--gp-shade:" not in view[:view.index("\n}\n")], "one shade, not two that could drift"
    assert "body.gp-on .topbar { border-bottom-color: transparent; animation: none; }" in CSS, \
        "no rule under the bar on the wash, and no sheen sliding its shade with the scroll"
    assert "box-shadow: none;" in rule, "no shadow to halo its sides"
    fade = CSS[CSS.index(".gp-compact::after {"):]
    fade = fade[:fade.index("}")]
    assert "top: 100%; height: 12px;" in fade and "left: 10px; right: 10px;" in fade, "a short fade below it, never beside it"
    docked = CSS[CSS.index("/* WHERE THE SIDEBAR STANDS BESIDE THE PAGE at those sizes"):]
    docked = docked[:docked.index("\n}\n")]
    assert "(pointer: coarse) and (min-width: 600px) and (max-width: 720px) and (min-height: 700px)," in docked, "the open Duo upright"
    assert ".gp-compact { left: 0; right: 0; width: auto; transform: translateY(-115%); }" in docked
    assert ".gp-compact.on { transform: none; }" in docked


def test_the_two_bars_are_pinned_where_they_sit():
    pin = _fn(JS, "gpPin")
    assert 'el.style.setProperty("--gp-x", `${-Math.round(r.left)}px`);' in pin
    assert 'el.style.setProperty("--gp-y", `${-Math.round(y)}px`);' in pin
    assert "at(bar, parseFloat(getComputedStyle(stick).top) || 0);" in pin, "where the bar rests, not where it slides"
    assert "_gpPinRO.observe(view);" in pin and 'window.addEventListener("resize", gpPin);' in pin
    assert "gpPin();" in _fn(JS, "gpWashOn") and "gpPin();" in _fn(JS, "gpWire"), "on every draw"
    off = _fn(JS, "gpWashOff")
    assert 'top.style.removeProperty("--gp-x"); top.style.removeProperty("--gp-y");' in off


ROW = """() => {
  const bar = document.querySelector('.gp-compact'), side = document.getElementById('sidebar');
  const back = bar && bar.querySelector('[data-gp-back]'), brand = document.getElementById('brand-home');
  const r = bar ? bar.getBoundingClientRect() : null, s = side ? side.getBoundingClientRect() : null;
  const b = back ? back.getBoundingClientRect() : null, w = brand ? brand.getBoundingClientRect() : null;
  const strip = getComputedStyle(document.body, '::before');
  return { on: !!(bar && bar.classList.contains('on')), top: r ? Math.round(r.top) : null, left: r ? Math.round(r.left) : null,
           right: r ? Math.round(r.right) : null, bottom: r ? Math.round(r.bottom) : null,
           x: bar ? getComputedStyle(bar).getPropertyValue('--gp-x').trim() : '',
           back: b ? [Math.round(b.left), Math.round(b.top), Math.round(b.bottom)] : null,
           brandRight: w ? Math.round(w.right) : 0,
           sideRight: s && s.width ? Math.round(s.right) : 0, strip: strip.content, stripH: parseFloat(strip.height) || 0,
           standalone: document.documentElement.classList.contains('ios-home') };
}"""


def _row(png: bytes, y: int, x0: int = 0, x1: int | None = None):
    """The colours along one row of a screenshot (points y, x0..x1 at two
    pixels a point), and its biggest jump between neighbouring points."""
    try:
        from PIL import Image
    except ImportError:                  # the browser test asks for Pillow first
        return [], 0
    im = Image.open(io.BytesIO(png)).convert("RGB")
    pix, (w, _) = im.load(), im.size
    px = [pix[x, 2 * y] for x in range(2 * x0, min(w, 2 * (x1 if x1 is not None else w)), 2)]
    jump = max(max(abs(a[c] - b[c]) for c in range(3)) for a, b in zip(px, px[1:]))
    return px, jump


def test_in_a_browser_the_top_runs_on_as_one():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
        import PIL  # noqa: F401
    except ImportError:
        print("      (skipped: no Playwright or no Pillow)")
        return
    import rendercheck
    import test_the_game_page_wears_the_team_colours as G           # the same game file the colour test draws
    doc = G._doc()
    body = json.dumps(doc)
    board = json.dumps({"games": [{"event_id": doc["event_id"], "home": doc["home"], "away": doc["away"], "live": doc["live"]}]})
    chromium = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium")
    srv, port = rendercheck._serve()
    found, errors = {}, []
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists(chromium):
                kw["executable_path"] = chromium
            browser = pw.chromium.launch(**kw)
            try:
                # The open Duo upright, docked sidebar; then a phone, the score bar away.
                for name, (w, h, scroll) in {"duo": (703, 1000, True), "phone": (390, 844, False)}.items():
                    ctx = browser.new_context(viewport={"width": w, "height": h}, is_mobile=True, has_touch=True,
                                              device_scale_factor=2, service_workers="block")
                    page = ctx.new_page()
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    try:
                        ctx.new_cdp_session(page).send("Emulation.setSafeAreaInsetsOverride",
                                                       {"insets": {"top": 40, "bottom": 20, "left": 0, "right": 0}})
                    except Exception:                                # noqa: BLE001
                        print("      (skipped: this Chromium cannot emulate the clock's strip)")
                        ctx.close()
                        return
                    page.route(lambda url: not url.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    page.route("**/data/pbp/nfl_401873030.json*",
                               lambda r: r.fulfill(status=200, content_type="application/json", body=body))
                    page.route("**/data/live_nfl.json*", lambda r: r.fulfill(status=200, content_type="application/json", body=board))
                    page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb.tour','done');}catch(e){}"
                                         "Object.defineProperty(navigator, 'standalone', { get: () => true });")
                    page.goto(f"http://127.0.0.1:{port}/index.html#pbp/nfl/401873030", wait_until="load")
                    page.wait_for_selector(".gp .pbp-hero", timeout=20000)
                    page.evaluate("document.querySelectorAll('#tour-overlay, .tour-pop').forEach((n) => n.remove())")
                    g = page.evaluate(ROW)
                    if scroll:
                        # Down until the score bar is down at the top, as a reader scrolls.
                        for _ in range(40):
                            page.evaluate("window.scrollBy(0, 120)")
                            page.wait_for_timeout(120)
                            g = page.evaluate(ROW)
                            if g["on"] and g["top"] is not None and abs(g["top"]) < 2:
                                break
                        page.wait_for_timeout(400)                   # its slide is over
                        g = page.evaluate(ROW)
                    # SAMPLED AGAIN WHILE A SLIDE MAY STILL BE RUNNING (gate 27,
                    # 2026-11-05: the Duo read the page's black under the clock
                    # once, under the gate's load, and passed three times alone).
                    # Up to six looks, 300 ms apart; a top that never paints
                    # still fails on the last one.
                    for look in range(6):
                        shot = page.screenshot(clip={"x": 0, "y": 0, "width": w, "height": 120})
                        under = _row(shot, 4)[0]
                        if not under or min(sum(p) for p in under) >= 90 or look == 5:
                            break
                        page.wait_for_timeout(300)
                        g = page.evaluate(ROW)
                    # 4 points down: under the clock, above every word. And on
                    # the Duo, a row through the site's bar and the score bar
                    # (between the wordmark's end and the bar's back button),
                    # across the sidebar's edge where the two meet.
                    inner = None
                    if scroll and g["back"] and g["brandRight"]:
                        y = (g["back"][1] + g["back"][2]) // 2
                        inner = _row(shot, y, g["brandRight"] + 2, g["back"][0] - 2)
                    found[name] = (g, _row(shot, 4), inner)
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert not errors, errors
    for name, (g, (px, jump), _) in found.items():
        assert g["standalone"] and g["strip"] == '""' and g["stripH"] >= 40, (name, "the clock's strip is drawn", g)
        darkest = min(sum(p) for p in px)
        assert darkest >= 90, (name, f"the page's black under the clock: {min(px, key=sum)}")
        assert jump <= 6, (name, f"a seam under the clock: {jump} levels between neighbours")
    duo, _, inner = found["duo"]
    assert duo["on"] and abs(duo["top"]) < 2, ("the score bar is down", duo)
    assert duo["sideRight"] > 150 and duo["left"] >= duo["sideRight"] and duo["right"] <= 703, \
        ("the docked sidebar, and the bar in its column: not under the sidebar, not off the edge", duo)
    assert duo["back"] and duo["back"][0] >= duo["sideRight"], ("its way back shows", duo)
    assert duo["x"] == f"{-duo['left']}px", ("the bar is pinned where it sits", duo)
    assert inner and inner[0], ("a row between the wordmark and the bar's back button", duo)
    # The scroll-driven sheen (styles.css glass-drift) slid the site's bar's
    # shade by the scroll: 40 levels darker than the score bar beside it.
    assert inner[1] <= 6, f"a seam where the site's bar meets the score bar: {inner[1]} levels"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}")
    print(f"\n{sum(1 for n in globals() if n.startswith('test_'))} tests passed.")
