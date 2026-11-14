"""The carry and route chart's X sits below the phone's status bar, and stays in reach.

Ethan, 2026-10-13, a screenshot of Christian McCaffrey's route chart from
his phone with the X circled under the clock and the battery: "fix this
issue where the X button is stuck up top in the bar so I can't even click
it." The site runs edge to edge under the iPhone's status bar
(viewport-fit=cover, black-translucent), and the chart overlay began at the
very top of the screen with nothing taking the inset off — the header and
its X sat in the strip where iOS keeps the taps for itself. And on a long
chart the X scrolled away with the card, so a closed hand had to scroll
back up to find it.

Pinned here:

  * the overlay's padding takes the status bar's inset off the top (and
    the home bar's off the bottom), on a phone and everywhere else;
  * the X is sticky, 8px from the overlay's padded top — the padding
    already carries the inset, and adding it to `top` as well put the X a
    whole status bar too low (measured: 126px under a 59px bar);
  * BROWSER HALF, opt-in (`QB_BROWSER_TESTS=1`): Chromium with the
    iPhone's 59px inset emulated draws the X below the bar, keeps it on
    screen after the chart scrolls, and closes on one tap. The old sheet,
    run the same way, put it at 10px — under the bar.

    QB_BROWSER_TESTS=1 python3 tests/test_the_chart_close_clears_the_status_bar.py
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CSS = (ROOT / "web" / "css" / "carrychart.css").read_text(encoding="utf-8")


def _rule(src: str, selector: str, start: int = 0) -> str:
    i = src.index(selector + " {", start)
    return src[i:src.index("}", i)]


def _phone(src: str) -> str:
    i = src.index("@media (max-width: 600px)")
    return src[i:src.index("\n}", i)]


def _code(src: str) -> str:
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


def test_the_overlay_takes_the_status_bar_off_the_top_everywhere():
    css = _code(CSS)
    base = _rule(css, "#cc-overlay")
    assert "env(safe-area-inset-top" in base and "env(safe-area-inset-bottom" in base, base
    phone = _phone(css)
    over = _rule(phone, "#cc-overlay")
    assert "env(safe-area-inset-top" in over, "the phone layout puts the card back under the bar"
    card = _rule(phone, ".cc")
    assert "env(safe-area-inset-bottom" in card, "the card's last rows sit under the home bar"


def test_the_x_is_sticky_and_counts_the_inset_once():
    css = _code(CSS)
    x = _rule(css, ".cc-x")
    assert "position: sticky" in x and "position: absolute" not in x
    top = re.search(r"(?<![-\w])top:\s*([^;]+);", x).group(1).strip()
    assert top == "8px", f"the X's top is {top!r} — the overlay's padding already carries the inset"
    # In the flow at the top right, taking back the room it would push the
    # header down by, on a phone as on a desktop.
    assert "margin: -8px -8px -26px auto" in x
    assert "margin: -4px -6px -30px auto" in _rule(_phone(css), ".cc-x")


def test_the_header_still_leaves_room_for_the_x():
    assert "padding-right: 40px" in _rule(_code(CSS), ".cc-head")


# --- the browser, opt-in -----------------------------------------------------
PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<style>{styles}</style><style>{chart}</style></head><body>
<div id="cc-overlay" class="open"><div class="cc" role="dialog">
  <button class="cc-x" type="button" aria-label="Close">×</button>
  <div class="cc-body"><header class="cc-head"><span class="cc-face"></span>
    <div class="cc-who"><span class="cc-eyebrow">Route chart</span><h2 class="cc-name">A Receiver</h2></div></header>
    <div style="height: 2400px"></div></div></div></div>
<script>document.querySelector('.cc-x').addEventListener('click',
  () => document.getElementById('cc-overlay').classList.remove('open'));</script>
</body></html>"""


def test_in_a_browser_the_x_clears_a_59px_status_bar_and_stays_in_reach():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    chromium = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium")
    styles = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")
    html = PAGE.replace("{styles}", styles).replace("{chart}", CSS)
    with sync_playwright() as pw:
        kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
        if os.path.exists(chromium):
            kw["executable_path"] = chromium
        browser = pw.chromium.launch(**kw)
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1,
                                      is_mobile=True, has_touch=True)
            page = ctx.new_page()
            try:
                ctx.new_cdp_session(page).send("Emulation.setSafeAreaInsetsOverride",
                                               {"insets": {"top": 59, "bottom": 34}})
            except Exception:                                   # noqa: BLE001
                print("      (skipped: this Chromium cannot emulate a status bar)")
                return
            page.set_content(html)
            x = page.locator(".cc-x").bounding_box()
            assert x["y"] >= 59, f"the X is at {x['y']:.0f}px, under a 59px status bar"
            page.evaluate("document.getElementById('cc-overlay').scrollTop = 900")
            page.wait_for_timeout(100)
            x2 = page.locator(".cc-x").bounding_box()
            assert 59 <= x2["y"] < 120, f"after scrolling the X is at {x2['y']:.0f}px"
            page.touchscreen.tap(x2["x"] + x2["width"] / 2, x2["y"] + x2["height"] / 2)
            assert not page.evaluate("document.getElementById('cc-overlay').classList.contains('open')")
        finally:
            browser.close()


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
