"""Every view has to say where it lands you. Most of them never did.

Ethan, 2026-08-23, with a screen recording from his phone: "every time on
mobile I click on a player to see the chart, it will load me at the bottom
of the page which I don't like it need to be at the top of the page."

NOTHING EVER SCROLLED. `_switchViewNow` reset the position for exactly one
destination — the game page — and every other view inherited whatever
offset the document happened to be at. On a desktop board that is
invisible, because you are usually near the top when you click. On a phone
you scroll a long way into a list of picks, tap one, and the prop page
opens at that same offset — and the prop page is SHORTER than the board,
so the offset is past its end and the browser pins you to the bottom. The
page looks like it loaded upside down.

The fix is not "always jump to the top", which breaks the other half:
backing out of a pick you opened from row 30 must not dump you at row 1 of
a list you were reading. So a detail page remembers the board, and hands
it back on the way out.

TWO THINGS HERE WERE ONLY FOUND BY MEASURING, and both are pinned below
because neither is visible in the source:

  * `behavior: "auto"` does not mean instant. It means "defer to CSS", and
    this stylesheet sets `html { scroll-behavior: smooth }` — so the first
    version of this fix asked for an immediate jump and got a 600ms
    animation. Measured, the position was still travelling 243 → 953 →
    2076 half a second after the switch. Only "instant" overrides a sheet.
  * the browser's own scroll restoration and this app's cannot both be
    right on a hash-routed SPA, and the browser's arrives later.

Opt in to the live half with QB_BROWSER_TESTS=1; the source checks always
run.

    QB_BROWSER_TESTS=1 python3 tests/test_scroll_landing.py

Run directly: `python3 tests/test_scroll_landing.py`
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _js():
    return open(os.path.join(ROOT, "web", "js", "app.js"),
                encoding="utf-8").read()


def _fn(src, name):
    """A function body by brace matching, past its parameter list."""
    i = src.index("function " + name + "(")
    j, depth = src.index("(", i), 0
    while j < len(src):
        if src[j] == "(":
            depth += 1
        elif src[j] == ")":
            depth -= 1
            if not depth:
                break
        j += 1
    start, d = src.index("{", j), 0
    for k in range(start, len(src)):
        if src[k] == "{":
            d += 1
        elif src[k] == "}":
            d -= 1
            if not d:
                return src[i:k + 1]
    raise AssertionError(name + " never closes")


# --- the source ---------------------------------------------------------------
def test_every_view_change_sets_a_position():
    """The bug was an omission, not a wrong value: only the game branch
    scrolled, and it reached that line through an early return the other
    dozen views never touch."""
    js = _js()
    body = _fn(js, "_switchViewNow")
    assert body.count("_landScroll(") == 2, (
        "the game page returns early, so it needs its own call — and the "
        "tail needs the one that covers every other view")
    # …and the tail call is the LAST thing, after the async renders above
    # it, not buried in the dispatch.
    tail = body[body.rindex("_landScroll("):]
    assert tail.count("if (") == 0, "the final landing is inside a branch"


def test_it_asks_for_instant_and_not_for_auto():
    """"auto" defers to CSS, and the sheet says smooth. This is the whole
    reason the first attempt animated instead of jumping."""
    land = _fn(_js(), "_landScroll")
    assert 'behavior: "instant"' in land, (
        'behavior "auto" reads as instant and is not — it inherits '
        "html { scroll-behavior: smooth }")
    css = open(os.path.join(ROOT, "web", "css", "styles.css"),
               encoding="utf-8").read()
    assert "scroll-behavior: smooth" in css, (
        "if the sheet ever stops setting this, the comment in _landScroll "
        "stops being true and should be rewritten rather than left")


def test_opening_a_detail_remembers_the_board_and_leaving_gives_it_back():
    js = _js()
    body = _fn(js, "_switchViewNow")
    assert "const leaving = state.view;" in body, (
        "the offset belongs to the view being left, and one line later "
        "there is no way to ask which that was")
    i, j = body.index("const leaving"), body.index("state.view = name;")
    assert "_boardReturn = { view: leaving, y: window.scrollY }" in body[i:j], (
        "the board position is captured after the view already moved")
    land = _fn(js, "_landScroll")
    assert "DETAIL_VIEWS.includes(leaving)" in land, (
        "any view returning to the remembered one would restore, including "
        "a fresh tab tap")
    assert "_boardReturn = null" in land, (
        "the memory outlives its trip and restores on an unrelated visit")


def test_the_detail_views_are_named_once():
    js = _js()
    assert 'const DETAIL_VIEWS = ["prop", "game"];' in js, (
        "prop and game are the two views with no tab of their own; if a "
        "third is added it belongs in this list, not in a new condition")


def test_the_app_takes_the_wheel_from_the_browser():
    """On a hash-routed SPA the browser restores the offset it saw when
    the hash changed — the OLD view's offset applied to the NEW view's
    content, arriving a frame after ours."""
    js = _js()
    assert 'history.scrollRestoration = "manual"' in js
    assert '"scrollRestoration" in history' in js, (
        "assigning it unguarded throws on anything that lacks it")


# --- the behaviour ------------------------------------------------------------
def test_a_prop_opens_at_the_top_and_the_board_keeps_its_place():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck

    chromium = os.environ.get(
        "CHROMIUM_PATH", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    srv, port = rendercheck._serve()
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage",
                           "--disable-gpu"]}
            if os.path.exists(chromium):
                kw["executable_path"] = chromium
            browser = pw.chromium.launch(**kw)
            # A PHONE, because that is the only shape the bug appears in:
            # the boards are short enough on a desktop that the inherited
            # offset is usually zero.
            page = browser.new_page(viewport={"width": 390, "height": 844},
                                    is_mobile=True, has_touch=True)
            page.goto(f"http://127.0.0.1:{port}/index.html", wait_until="load")
            page.wait_for_timeout(1500)
            got = page.evaluate("""async () => {
              // This container has no slate, so the board is short. Give it
              // the height a real one has — the offset is the whole point.
              const v = document.getElementById('view-recommended');
              const tall = document.createElement('div');
              tall.style.height = '4000px';
              v.appendChild(tall);
              const settle = async () => {
                for (let i = 0; i < 10; i++)
                  await new Promise(r => requestAnimationFrame(r));
                await new Promise(r => setTimeout(r, 250));
                return Math.round(window.scrollY);
              };
              window.scrollTo({ top: 1500, behavior: 'instant' });
              await settle();
              const board = Math.round(window.scrollY);
              openProp('not|a|real|prop|id');
              const onProp = await settle();
              document.getElementById('pp-back').click();
              const backOnBoard = await settle();
              // A plain tab tap from mid-page goes to the top.
              window.scrollTo({ top: 1200, behavior: 'instant' });
              await settle();
              switchView('record', true);
              const onTab = await settle();
              return { board, onProp, backOnBoard, onTab };
            }""")
            browser.close()
    finally:
        srv.shutdown()

    assert got["board"] > 500, f"the board never scrolled: {got}"
    assert got["onProp"] == 0, (
        f"the prop page opened {got['onProp']}px down — this is the bug: {got}")
    assert abs(got["backOnBoard"] - got["board"]) <= 2, (
        f"going back lost the reader's place: {got}")
    assert got["onTab"] == 0, f"a tab tap kept the old offset: {got}"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
