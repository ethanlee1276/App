"""What floats over the page wears the glass; the page itself does not.

Ethan, 2026-10-24: "carry the Liquid Glass look onto more stuff without
overdoing it". The line drawn (styles.css "GLASS FOR WHAT FLOATS"): the
layers that float over the page — toasts, the crash note, the slip's pill
and sheet, the pull-to-refresh pill, a chart's tooltip, the dialogs, and
the iPhone app's top bar — get the Duo's glass; the cards, tables and words
stay solid, so nothing anybody reads changes. What these hold:

  - every floating layer named takes the sheen and the lit rim, and no blur
    anywhere in the section (backdrop-filter resprung Ethan's iPhone);
  - nothing that is the page itself (a card, a table, a row) is in it;
  - the light theme has its own panes (the tokens' twins), and anyone who
    asks the system for less transparency or more contrast gets solid ones;
  - in Chromium the tour card and a toast really are lit panes, the iPhone
    app's top bar is glass and a browser tab's is not.

Run directly: `python3 tests/test_what_floats_wears_glass.py` (the browser
half with QB_BROWSER_TESTS=1 and Playwright)
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
CC = open(os.path.join(ROOT, "web", "css", "carrychart.css"), encoding="utf-8").read()
SOCIAL = open(os.path.join(ROOT, "web", "css", "social.css"), encoding="utf-8").read()
SECTION = CSS[CSS.index("GLASS FOR WHAT FLOATS"):]
CODE = re.sub(r"/\*.*?\*/", "", SECTION.split("*/", 1)[1], flags=re.S)
FLOATS = (".tf-toast", ".crash-note", ".slip-bar", '[id="ptr"]', ".slip-panel", ".pk-card", ".ffd-card",
          ".tour-card", ".a2hs-card", ".graph-tip")
SHOTS = os.environ.get("QB_SHOTS_DIR", "")


def test_every_floating_layer_takes_the_glass_and_nothing_blurs():
    for sel in FLOATS:
        rule = next((m.group(1) for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", CODE)
                     if sel in m.group(1) and "glass-sheen" in m.group(2)), None)
        assert rule, f"{sel} floats and is not glass"
    assert "html.store-ios .topbar, html.ios-home .topbar" in CODE, "the iPhone app's top bar is the tab bar's twin"
    assert "backdrop-filter" not in CODE and "blur(" not in CODE
    # A toast floats above the tab bar (and the iPhone app's capsule), never on it.
    assert ".tf-toast { bottom: calc(78px + env(safe-area-inset-bottom, 0px)); }" in CODE
    assert "html.store-ios .tf-toast, html.ios-home .tf-toast" in CODE
    assert ".cc { background-image: var(--glass-sheen-soft); box-shadow: var(--glass-rim), var(--glass-depth); }" in CC
    # The feed's ⋯ menu floats over the posts (2026-10-25).
    pop = re.search(r"\.fd-popover \{([^{}]*)\}", SOCIAL).group(1)
    assert "var(--glass-sheen-soft)" in pop and "var(--glass-rim)" in pop and "blur(" not in pop


def test_the_page_itself_stays_solid():
    for page in (".card", ".rank-table", ".al-row", ".pick-card", ".wl-item", ".gs-card"):
        assert not re.search(r"(^|[\s,])" + re.escape(page) + r"([\s,{:.]|$)", CODE), f"{page} is the page, not a layer over it"


def test_less_transparency_or_more_contrast_gets_solid_panes():
    at = CODE.index("@media (prefers-reduced-transparency: reduce), (prefers-contrast: more)")
    solid = CODE[at:]
    for sel in FLOATS:
        assert sel in solid, sel
    assert "background-image: none" in solid and "background: var(--topbar-bg)" in solid
    assert "prefers-reduced-transparency: reduce" in CC
    assert re.search(r"prefers-reduced-transparency: reduce\), \(prefers-contrast: more\) \{\s*\.fd-popover \{ background-image: none;", SOCIAL)


def test_in_a_browser_the_layers_are_lit_panes_and_a_tabs_bar_is_not_glass():
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
    probe = """() => { const s = (q) => { const e = document.querySelector(q); if (!e) return null;
        const c = getComputedStyle(e); return { bg: c.backgroundImage, shadow: c.boxShadow, blur: c.backdropFilter }; };
        const t = document.querySelector('.tf-toast'), b = document.querySelector('.tabbar');
        const gap = t && b ? b.getBoundingClientRect().top - t.getBoundingClientRect().bottom : null;
        return { tour: s('.tour-card'), toast: s('.tf-toast'), bar: s('.topbar'), gap }; }"""
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                for name, query, theme, solid in (("ios", "?app=ios", "dark", False), ("ios light", "?app=ios", "light", False),
                                                  ("tab", "", "dark", False), ("solid", "?app=ios", "dark", True)):
                    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                              device_scale_factor=2, service_workers="block",
                                              reduced_motion="reduce")
                    page = ctx.new_page()
                    if solid:
                        page.emulate_media(forced_colors="none")
                        cdp = ctx.new_cdp_session(page)
                        cdp.send("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-reduced-transparency", "value": "reduce"}]})
                    page.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb.tour', 'done'); } catch (e) {}")
                    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    page.goto(f"http://127.0.0.1:{port}/index.html{query}#recommended", wait_until="load")
                    page.wait_for_timeout(1000)
                    if theme == "light":
                        page.evaluate("document.documentElement.setAttribute('data-theme', 'light')")
                    page.evaluate("tourOpen(0); tfToast('Saved to My Bets')")
                    page.wait_for_timeout(500)
                    got[name] = page.evaluate(probe)
                    if SHOTS:
                        page.screenshot(path=os.path.join(SHOTS, f"floats_{name.replace(' ', '_')}.png"))
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    for name in ("ios", "ios light"):
        g = got[name]
        for layer in ("tour", "toast"):
            assert g[layer] and "gradient" in g[layer]["bg"] and "inset" in g[layer]["shadow"], (name, layer, g[layer])
        assert "gradient" in g["bar"]["bg"] and "inset" in g["bar"]["shadow"], (name, g["bar"])
        assert all(not isinstance(v, dict) or v["blur"] in ("none", "") for v in g.values()), g
        assert g["gap"] is not None and g["gap"] > 0, ("the toast sits on the tab bar", g["gap"])
    assert got["ios"]["tour"]["bg"] != got["ios light"]["tour"]["bg"], "the light theme has its own panes"
    assert "inset" not in got["tab"]["bar"]["shadow"], ("a browser tab's top bar is not the app's glass", got["tab"]["bar"])
    s = got["solid"]
    assert s["tour"]["bg"] == "none" and s["toast"]["bg"] == "none", s


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
