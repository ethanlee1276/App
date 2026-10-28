"""A highlight fades out, it is not cut off (web/css/styles.css; Ethan,
2026-10-28, a Home tile held under his finger with its bottom circled:
"when something is highlighted make it look more smooth, the highlight is
cut off like it's in a box").

A sideways strip clips whatever leaves its box. The Home strip held its
tiles in 4px over and 6px under, and a lifted tile's glow (--glow: 0 8px
30px) left that box on every side, so it ended in straight lines: the box
he saw. The strip keeps room for it now (24px over, 40px under, the view's
gutter beside it), its margins give the room back so the tiles sit where
they did, and nothing else on the page moves but the tiles' 16px of air
under the sort row, whose buttons keep their whole tap.

Run directly: `python3 tests/test_a_highlight_fades_out.py`
"""
import os
import re
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

CSS = Path(ROOT, "web", "css", "styles.css").read_text(encoding="utf-8")
ROOM = ".games-scroller { padding: 24px 2px 40px 26px; margin: -4px 0 -34px -26px; scroll-padding-inline: 26px 2px; }"


def _glow():
    """--glow's reach over and under a tile: blur less the drop, blur plus it."""
    m = re.search(r"--glow: 0 (\d+)px (\d+)px rgba", CSS)
    drop, blur = int(m.group(1)), int(m.group(2))
    return blur - drop, blur + drop


def test_the_strip_keeps_room_for_the_glow_and_gives_it_back():
    over, under = _glow()
    assert (over, under) == (22, 38), "the glow the room was measured for"
    assert ROOM in CSS, "24px over, 40px under, the gutter at the left; the margins give it back"
    assert over <= 24 and under <= 40, "the room covers the glow"
    for before in (".games-scroller { display: flex; gap: 15px; overflow-x: auto; overflow-y: hidden;",
                   ".games-scroller { padding-bottom: 8px; }", ".hero-games { padding-bottom: 6px; }"):
        assert CSS.index(before) < CSS.index(ROOM), ("after every earlier padding of the strip", before)
    phone = "@media (max-width: 760px) {\n  .games-scroller { padding-inline: 12px; margin-inline: -12px; scroll-padding-inline: 12px; }\n}"
    small = "@media (max-width: 359px) {\n  .games-scroller { padding-inline: 10px; margin-inline: -10px; scroll-padding-inline: 10px; }\n}"
    assert phone in CSS and small in CSS, "a phone's strip runs the screen's width, the view's gutter inside it"
    for gutter in (".view { display: none; padding: 22px 26px 60px; }", ".view { padding: 14px 12px 48px; }",
                   ".view { padding-left: 10px; padding-right: 10px; }"):
        assert gutter in CSS, ("the strip's gutters are the view's", gutter)


def _reach(shadow: str):
    """How far a computed box-shadow reaches over and under its box: the
    largest of each layer's blur plus spread, less or plus its drop."""
    up = down = 0.0
    for layer in re.split(r",(?![^(]*\))", shadow or ""):
        if "inset" in layer:
            continue
        nums = [float(n) for n in re.findall(r"(-?[\d.]+)px", re.sub(r"rgba?\([^)]*\)", "", layer))]
        x, y, blur, spread = (nums + [0, 0, 0, 0])[:4]
        up, down = max(up, blur + spread - y), max(down, blur + spread + y)
    return up, down


# --- in a browser ----------------------------------------------------------------
MEASURE = """(() => {
  const s = document.querySelector('.games-scroller'), c = s.querySelector('.game-card');
  const r = (e) => e.getBoundingClientRect();
  const sel = document.getElementById('games-sort'), sr = r(sel);
  const hit = document.elementFromPoint(sr.left + sr.width / 2, sr.bottom - 2);
  return { s: r(s).toJSON(), c: r(c).toJSON(), head: r(document.getElementById('games-head')).toJSON(),
           shadow: getComputedStyle(c).boxShadow, wide: document.scrollingElement.scrollWidth, vw: innerWidth,
           sortHit: !!hit && (hit === sel || sel.contains(hit)) };
})()"""


def test_in_a_browser_a_lifted_tiles_glow_stays_inside_the_strip():
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
    errs, got = [], {}
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                for width in (440, 1280):
                    ctx = browser.new_context(viewport={"width": width, "height": 956}, service_workers="block")
                    page = ctx.new_page()
                    page.on("pageerror", lambda e: errs.append(str(e)))
                    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb.tour','done');"
                                         "localStorage.setItem('qb-seen-intro','1');}catch(e){}")
                    page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl", wait_until="load")
                    page.wait_for_selector(".games-scroller .game-card", timeout=15000)
                    page.wait_for_timeout(1200)
                    page.evaluate("document.querySelector('.games-scroller').scrollIntoView({block: 'center'})")
                    page.wait_for_timeout(300)
                    rest = page.evaluate(MEASURE)                 # where the tiles sit, untouched
                    page.hover(".games-scroller .game-card")
                    page.wait_for_timeout(500)
                    got[width] = dict(page.evaluate(MEASURE), rest=rest["c"])   # lifted (and tilted): the glow on
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert not errs, errs
    for width, g in got.items():
        s, c = g["s"], g["c"]
        up, down = _reach(g["shadow"])
        assert down >= 30, ("lifted: a shadow or a glow is on", g["shadow"])
        assert c["top"] - up >= s["top"] - 0.5, (width, "the glow's top fades inside the strip", s, c, g["shadow"])
        assert c["bottom"] + down <= s["bottom"] + 0.5, (width, "and its foot", s, c, g["shadow"])
        assert s["top"] >= g["head"]["bottom"] - 0.5 and g["sortHit"], (width, "the sort row keeps its whole tap")
        assert g["wide"] <= g["vw"], (width, "nothing runs off sideways")
    phone, wide = got[440], got[1280]
    assert phone["s"]["left"] == 0 and phone["s"]["right"] == 440, "a phone's strip runs the screen's width"
    assert abs(phone["rest"]["left"] - 12) < 0.5, ("its first tile still starts at the gutter", phone["rest"])
    assert wide["s"]["right"] < 1000 and abs(wide["rest"]["left"] - wide["s"]["left"] - 26) < 0.5, \
        ("a computer's strip reaches into the gutter on its left only", wide["s"], wide["rest"])


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
