"""The sidebar comes down the page with you, open or slid away (styles.css
"THE SIDEBAR COMES DOWN THE PAGE WITH YOU").

Ethan, 2026-10-30, his open Duo with the sidebar circled: "this menu no
matter swiped open or close, should follow you all the way down when you
scroll down". It was `position: sticky`, and a sticky box holds only inside
its own grid cell: the shell ends where the footer starts (and, under 1280,
where Home's rail folds under the page), so the last screen of every page
pushed the bar up and off — 148 to 237px of it gone at the foot of the
dashboard, on the Duo either way up, an iPad on its side and a laptop.

What these hold, wherever the sidebar stands beside the page:

  * it is fixed under the top bar at the shell's left edge, by the same
    arithmetic the dots use, so the two never part;
  * main is put in the second column by name (a fixed bar no longer fills
    the first, and main would slide into it), the stale bar spans from
    main's column, and the footer starts where the bar's column ends —
    nothing the page draws sits under the bar;
  * slid away, the footer takes the room back; the wall keeps its one column;
  * in a browser, at the foot of a long page the bar and its dots are
    exactly where they were at the top, open or hidden.

Run directly: `python3 tests/test_the_sidebar_follows_the_page.py`
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

CSS = ROOT.joinpath("web", "css", "styles.css").read_text(encoding="utf-8")
SHELL_LEFT = "max(0px, (100% - 1760px) / 2)"


def _block(head):
    at = CSS.index(head)
    end = CSS.index("\n}\n", CSS.index("@media ", at)) + 3
    return CSS[at:end]


def _query(block):
    i = block.index("@media ") + len("@media ")
    return block[i:block.index(" {\n", i)]


def test_it_is_wherever_the_dots_are():
    mine, dots = _block("/* THE SIDEBAR COMES DOWN THE PAGE WITH YOU"), _block("/* THE SIDEBAR SLIDES AWAY")
    assert _query(mine) == _query(dots), "the bar is fixed exactly where it stands beside the page"


def test_it_is_fixed_under_the_top_bar_where_the_shell_starts():
    block = _block("/* THE SIDEBAR COMES DOWN THE PAGE WITH YOU")
    assert (".sidebar { position: fixed; top: var(--topbar-h); bottom: auto; left: " + SHELL_LEFT + ";\n"
            "    width: var(--sidebar-w); }") in block
    dots = _block("/* THE SIDEBAR SLIDES AWAY")
    assert f"left: calc({SHELL_LEFT} + var(--sidebar-w) - 12px);" in dots, "the dots ride the same edge"
    assert "transition" not in block, "a layout property is never animated (tests/test_design_tells.py)"


def test_nothing_the_page_draws_sits_under_it():
    block = _block("/* THE SIDEBAR COMES DOWN THE PAGE WITH YOU")
    for want in (".shell > main { grid-column: 2; }",
                 ".shell > #stalebar { grid-column: 2 / -1; }",
                 f".footer {{ margin-left: calc({SHELL_LEFT} + var(--sidebar-w)); }}",
                 "html.sb-hidden .footer, body.two-pane .footer { margin-left: auto; }",
                 "body.walled.on-wall .shell > main, body.walled.on-wall .shell > #stalebar { grid-column: 1 / -1; }"):
        assert want in block, want
    # The stale bar's own rule still spans every column (tests/test_shell_grid.py) — the
    # docked override outranks it by the `.shell >`, since it comes earlier in the file.
    assert CSS.index(".shell > #stalebar { grid-column: 2 / -1; }") < CSS.index("#stalebar { grid-column: 1 / -1;")


SEE = """() => { const q = (s) => document.querySelector(s), r = (e) => e.getBoundingClientRect();
  const sb = r(q('#sidebar')), g = r(q('#sb-grip')), m = r(q('main')), f = r(q('.footer')), t = r(q('.topbar'));
  return {y: Math.round(scrollY), max: document.documentElement.scrollHeight - innerHeight,
          sbTop: Math.round(sb.top), sbBottom: Math.round(sb.bottom), sbLeft: Math.round(sb.left), sbRight: Math.round(sb.right),
          gripTop: Math.round(g.top), barBottom: Math.round(t.bottom), mainLeft: Math.round(m.left),
          footLeft: Math.round(f.left), footTop: Math.round(f.top), h: innerHeight, w: innerWidth,
          wide: document.scrollingElement.scrollWidth,
          hidden: document.documentElement.classList.contains('sb-hidden')}; }"""

# `html { scroll-behavior: smooth }`: a plain scrollTo glides, so the test jumps.
FOOT = "window.scrollTo({top: document.documentElement.scrollHeight, behavior: 'instant'})"
TOP = "window.scrollTo({top: 0, behavior: 'instant'})"

LONG = """() => { const v = document.querySelector('.view.active') || document.querySelector('main');
  const d = document.createElement('div'); d.className = 'test-tall'; d.style.height = '3000px'; v.appendChild(d); }"""


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
                for name, w, h, touch in (("laptop", 1280, 800, False), ("duo upright", 703, 1000, True),
                                          ("duo on its side", 951, 543, True), ("ipad on its side", 1133, 744, True)):
                    ctx = browser.new_context(viewport={"width": w, "height": h}, service_workers="block",
                                              is_mobile=touch, has_touch=touch)
                    page = ctx.new_page()
                    page.on("pageerror", lambda e: errs.append(str(e)))
                    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
                    page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb.tour','done');}catch(e){}")
                    page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#recommended", wait_until="load")
                    page.wait_for_timeout(1500)
                    page.evaluate(LONG)
                    rows = [page.evaluate(SEE)]
                    page.evaluate(FOOT)
                    page.wait_for_timeout(500)
                    rows.append(page.evaluate(SEE))
                    page.click("#sb-grip")
                    page.wait_for_timeout(600)
                    page.evaluate(FOOT)
                    page.wait_for_timeout(500)
                    rows.append(page.evaluate(SEE))
                    page.click("#sb-grip")
                    page.wait_for_timeout(600)
                    page.evaluate(TOP)
                    page.wait_for_timeout(400)
                    if name == "laptop":
                        got["stale"] = page.evaluate("""() => { const s = document.getElementById('stalebar');
                            s.hidden = false; s.textContent = 'These numbers are old.';
                            const b = s.getBoundingClientRect(), sb = document.getElementById('sidebar').getBoundingClientRect();
                            const out = [Math.round(b.left), Math.round(sb.right)]; s.hidden = true; return out; }""")
                        got["wall"] = page.evaluate("""() => { document.body.classList.add('walled', 'on-wall');
                            const m = document.querySelector('main').getBoundingClientRect(),
                                  s = document.querySelector('.shell').getBoundingClientRect();
                            const out = [Math.round(m.left - s.left), Math.round(s.width - m.width)];
                            document.body.classList.remove('walled', 'on-wall'); return out; }""")
                    got[name] = rows
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    return got, errs


def test_in_a_browser_it_is_where_it_was_at_the_foot_of_the_page():
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
    for name in ("laptop", "duo upright", "duo on its side", "ipad on its side"):
        top, foot, hidden_foot = got[name]
        assert top["y"] == 0 and foot["y"] >= 2500 and foot["y"] == foot["max"], ("scrolled to the foot", name, foot)
        assert 0 <= top["sbTop"] - top["barBottom"] <= 10, ("under the top bar (the Duo's pane floats 10px below)", name, top)
        assert foot["sbTop"] == top["sbTop"] and foot["sbBottom"] == top["sbBottom"], ("it came down with you", name, top, foot)
        assert foot["gripTop"] == top["gripTop"] and hidden_foot["gripTop"] == top["gripTop"], ("and so did the dots", name)
        assert foot["footTop"] < foot["h"], ("the footer is on screen at the foot", name, foot)
        assert foot["footLeft"] >= foot["sbRight"] - 1 and foot["mainLeft"] >= foot["sbRight"] - 1, \
            ("nothing the page draws sits under the bar", name, foot)
        assert hidden_foot["hidden"] and hidden_foot["sbRight"] <= 12, ("slid away", name, hidden_foot)
        assert hidden_foot["footLeft"] < foot["footLeft"] and hidden_foot["mainLeft"] < foot["mainLeft"], \
            ("slid away, the page and its footer take the room back", name, foot, hidden_foot)
        for row in (top, foot, hidden_foot):
            assert row["wide"] == row["w"], ("nothing runs off the side", name, row)
    left, edge = got["stale"]
    assert left >= edge, ("the stale bar starts in main's column, clear of the bar", got["stale"])
    assert got["wall"] == [0, 0], ("the wall keeps its one column, full width", got["wall"])


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
