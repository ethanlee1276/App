"""The open Duo wears Liquid Glass — built from light, never from blur.

Ethan, 2026-10-24: "they use a lot of that liquid glass shit. So I feel like
the iPhone Duo app could have like a cool liquid glass effect". Apple's
material bends what is behind it; a page can only do that with SVG
displacement (Chromium only, a GPU cost every frame) or a backdrop blur,
and backdrop-filter is what resprung Ethan's iPhone four times. So the glass
(styles.css "LIQUID GLASS ON THE DUO") is the part the eye reads as glass:
a tinted pane, a lit rim, a sheen, capsules, and the sheen sliding with the
scroll where the browser can drive that itself.

What these hold: no blur anywhere in it; every rim and sheen a token with a
light-theme twin; the open shapes by finger (the Duo on its side is 951
wide, past the desktop line, so it is the finger that tells it from a
laptop) while a mouse keeps the plain desktop; the moving sheen only for
readers who have not asked for less motion, only where scroll timelines
exist; solid panes for anyone asking for less transparency or more
contrast; and, in Chromium, the floating pane really is a rounded, lit
pane on the open Duo and really is not on a laptop of the same size.

Run directly: `python3 tests/test_the_duo_wears_glass.py` (the browser half
with QB_BROWSER_TESTS=1 and Playwright)
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
GLASS = CSS[CSS.index("LIQUID GLASS ON THE DUO"):]
# The slice opens inside the section's own header comment: drop to its end first.
GLASS_CODE = re.sub(r"/\*.*?\*/", "", GLASS.split("*/", 1)[1], flags=re.S)
TOKENS = ("--glass-tint", "--glass-tint-strong", "--glass-rim", "--glass-rim-soft", "--glass-sheen",
          "--glass-sheen-soft", "--glass-depth", "--glass-gold")


def test_nothing_in_the_glass_blurs():
    assert "backdrop-filter" not in GLASS_CODE and "blur(" not in GLASS_CODE and "url(#" not in GLASS_CODE


def test_every_rim_and_sheen_is_a_token_with_a_light_twin():
    # In the sheet's one :root and its one light block (test_one_root_and_shared_percents).
    nc = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    i = nc.index(":root {")
    dark = nc[i:nc.index("\n}", i)]
    j = nc.index(':root[data-theme="light"] {')
    light = nc[j:nc.index("\n}", j)]
    for t in TOKENS:
        assert f"{t}:" in dark, t
    for t in TOKENS[:-1]:
        assert f"{t}:" in light, f"{t} has no light-theme value"


def test_the_open_duo_is_told_by_finger_and_a_mouse_keeps_the_desktop():
    queries = re.findall(r"@media ([^{]+)\{\s*\.topbar \{", GLASS_CODE)
    assert queries, "the glass block is found"
    clauses = [c.strip() for c in queries[0].split(",")]
    assert len(clauses) == 3 and all(c.startswith("(pointer: coarse)") for c in clauses), clauses
    assert clauses[0] == "(pointer: coarse) and (min-width: 700px) and (min-height: 480px) and (min-aspect-ratio: 5/4)"


def test_the_sheen_moves_only_for_readers_who_want_motion():
    i = GLASS_CODE.index("@supports (animation-timeline: scroll())")
    block = GLASS_CODE[i:GLASS_CODE.index("@keyframes glass-drift")]
    assert "@media (prefers-reduced-motion: no-preference)" in block and "animation-timeline: scroll(root)" in block
    assert GLASS_CODE.count("animation-timeline: scroll(root)") == 1


def test_less_transparency_or_more_contrast_gets_solid_panes():
    i = GLASS_CODE.index("@media (prefers-reduced-transparency: reduce), (prefers-contrast: more)")
    block = GLASS_CODE[i:]
    assert "background-image: none; animation: none;" in block
    for sel in (".tabbar { background-color: var(--panel); }", ".topbar { background-color: var(--topbar-bg); }",
                ".sidebar { background-color: var(--bg-2); }"):
        assert sel in block, sel


def test_the_phone_tab_bar_keeps_its_size_and_place():
    i = GLASS_CODE.index("@media (max-width: 760px) and (pointer: coarse)")
    block = GLASS_CODE[i:GLASS_CODE.index("}\n}", i)]
    for prop in ("position", "height", "padding", "bottom", "grid-template"):
        assert prop + ":" not in block, f"the glass moved the tab bar ({prop})"


def test_in_a_browser_the_duo_gets_a_lit_floating_pane_and_a_laptop_does_not():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    import rendercheck
    srv, port = rendercheck._serve()
    got = {}
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                for name, touch, theme in (("duo", True, "dark"), ("duo light", True, "light"), ("laptop", False, "dark")):
                    ctx = browser.new_context(viewport={"width": 951, "height": 543}, is_mobile=touch, has_touch=touch,
                                              service_workers="block")
                    page = ctx.new_page()
                    page.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb.tour', 'done'); } catch (e) {}")
                    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    page.goto(f"http://127.0.0.1:{port}/index.html", wait_until="load")
                    page.wait_for_timeout(900)
                    if theme == "light":
                        page.evaluate("document.documentElement.setAttribute('data-theme', 'light')")
                    got[name] = page.evaluate("""() => { const s = getComputedStyle(document.querySelector('.sidebar'));
                        const t = getComputedStyle(document.querySelector('.topbar'));
                        return { radius: parseFloat(s.borderTopLeftRadius), shadow: s.boxShadow, bg: s.backgroundImage,
                                 bar: t.backgroundImage, blur: s.backdropFilter + t.backdropFilter }; }""")
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    duo, light, laptop = got["duo"], got["duo light"], got["laptop"]
    assert duo["radius"] > 0 and "inset" in duo["shadow"] and "gradient" in duo["bg"] and "gradient" in duo["bar"], duo
    assert "none" in duo["blur"] or not duo["blur"].strip(), duo["blur"]
    assert light["bg"] != duo["bg"], "the light theme has its own panes"
    assert laptop["radius"] == 0 and "inset" not in laptop["shadow"], laptop


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
