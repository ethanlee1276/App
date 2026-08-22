"""Nothing on the top bar may be pushed out of reach.

Ethan, 2026-08-22, from his phone: *"The search button is now gone."*

It was, and it was not hidden — it was CLIPPED. `.slate-meta` carries the
icon row with `justify-content: flex-end` and `overflow: hidden`, so when
the row runs out of room the icons overflow their own container to the
LEFT and the earliest one disappears under the wordmark. `.brand-home` was
`flex-shrink: 0`, so the brand never gave way and the icons always lost.

Two icons were added that morning — Instagram and Discord — and search
went off the edge. Nothing said so: no overflow scrollbar, no wrap, no
console warning. A control that silently stops existing is the worst shape
this class of bug can take, because the page looks fine.

THE LAYOUT ETHAN ASKED FOR, and it is also the fix: *"Maybe we put it on
the bottom bar where the menu button is, then move the menu button too be
like three bars on the top left."* The drawer opens from a hamburger at
top left, where it has room and where a drawer belongs; its old tab-bar
slot goes to Search, which is a destination, which is what a tab bar is
for. That also deletes the tab bar's habit of synthesising a click on a
hidden button to reach the drawer.

    python3 tests/test_topbar_layout.py
    QB_BROWSER_TESTS=1 python3 tests/test_topbar_layout.py
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, "web", "index.html")
CSS = os.path.join(ROOT, "web", "css", "styles.css")
APP = os.path.join(ROOT, "web", "js", "app.js")


def _read(p):
    return open(p, encoding="utf-8").read()


def _markup():
    """Comments here quote the bug and name the ids involved."""
    return re.sub(r"<!--.*?-->", " ", _read(HTML), flags=re.S)


def _decls():
    return re.sub(r"/\*.*?\*/", " ", _read(CSS), flags=re.S)


def _code():
    s = re.sub(r"/\*.*?\*/", " ", _read(APP), flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", s)


def _media(width):
    """The whole `@media (max-width: Npx)` block, brace-matched.

    A non-greedy `.*?\n\}` stops at the first nested rule's closing
    brace, which is three lines in — so the first draft of this file
    searched roughly one selector and concluded the rest was missing."""
    decls = _decls()
    out, at = [], 0
    needle = "@media (max-width: %s)" % width
    while True:
        i = decls.find(needle, at)
        if i < 0:
            break
        depth, seen, end = 0, False, None
        for j in range(decls.index("{", i), len(decls)):
            if decls[j] == "{":
                depth += 1
                seen = True
            elif decls[j] == "}":
                depth -= 1
                if seen and depth == 0:
                    end = j + 1
                    break
        assert end, needle + " never closes"
        out.append(decls[i:end])
        at = end
    # ALL of them, joined. There are four blocks at 900px in this sheet
    # and the browser applies every one — taking only the first found a
    # rule about hero cards and concluded the bar was unstyled.
    assert out, "no " + needle + " block at all"
    return "\n".join(out)


# --- the layout -------------------------------------------------------------
def test_the_drawer_opens_from_the_top_left():
    html = _markup()
    i = html.index('id="menu-toggle"')
    j = html.index('id="brand-home"')
    assert i < j, "the hamburger is not before the wordmark"
    decls = _decls()
    assert "display: none !important" not in re.sub(
        r"\s+", " ", decls[decls.index(".menu-toggle"):][:400]), (
        "the hamburger is hidden on phones again")


def test_the_hamburger_is_visible_on_a_phone():
    """It was `display: none !important` at ≤760px, and the tab bar
    reached the drawer by clicking it anyway — a hidden control driving
    the visible one."""
    decls = _decls()
    block = _media("760px")
    # EVERY .menu-toggle rule in the block, not the first — there is a
    # nested @media for 380px that only resizes it, and taking the first
    # match found that one.
    hits = re.findall(r"\.menu-toggle[^{]*\{([^}]*)\}", block)
    assert hits, "the phone block says nothing about the hamburger"
    assert any("display: grid" in h for h in hits), (
        "the hamburger is not shown on phones: %r" % hits)


def test_the_tab_bar_ends_with_search_not_menu():
    html = _markup()
    assert 'id="tb-search"' in html
    assert 'id="tb-menu"' not in html, (
        "the tab bar still opens the drawer, so search has nowhere to go")


def test_nothing_synthesises_a_click_on_the_hamburger():
    code = _code()
    assert 'getElementById("menu-toggle")' not in code or \
        "t.click()" not in code, (
        "a hidden button is still being clicked programmatically")


def test_search_still_reaches_the_player_page():
    """BOTH buttons, and through one handler. A fixed slice forward from
    the tab-bar listener used to be enough; it stopped being enough the
    moment the two buttons started sharing a function, which is a change
    that made the code better and the test red. The claim was never about
    adjacency — it is that pressing either control lands on the player
    page."""
    code = _code()
    i = code.index("const goSearch =")
    body = code[i:i + 260]
    assert 'switchView("players"' in body, "search goes nowhere"
    for btn in ('getElementById("tb-search")',
                'getElementById("nav-search")'):
        j = code.index(btn)
        assert "goSearch" in code[j:j + 160], f"{btn} is not wired to it"


def test_the_desktop_bar_has_a_search_control():
    """Ethan, 2026-08-22: "there is no search button or bar on the website
    now. its on mobile but not the desktop page."

    Mine. His earlier instruction — "put it on the bottom bar where the
    menu button is" — describes the phone, because the bottom bar only
    exists on the phone. I moved the control there and deleted the topbar
    one, which left every screen over 760px with no way to search."""
    html = _markup()
    assert 'id="nav-search"' in html, "the desktop bar has no search again"
    i = html.index('id="nav-search"')
    assert html.rindex('<div class="slate-meta">', 0, i) > 0, \
        "search is no longer in the topbar's icon row"


def test_the_two_search_controls_are_never_both_on_screen():
    """Two identical buttons on one screen is a worse answer than one,
    and the icon row running out of room is what clipped a control in the
    first place."""
    phone = re.sub(r"\s+", " ", _media("760px"))
    assert "#nav-search { display: none; }" in phone, \
        "the phone shows both the topbar icon and the tab bar's Search"
    assert ".tabbar { display: none; }" in re.sub(r"\s+", " ", _decls()), \
        "the tab bar is no longer hidden on desktop"


def test_the_search_control_exists_on_every_width():
    """THIS TEST USED TO ASSERT THE OPPOSITE, and it was wrong — it pinned
    my mistake rather than a requirement. It said the top bar must NOT
    carry a search button, on the reasoning that two buttons is two places
    to maintain and one of them was the one that got clipped.

    True about maintenance, and it deleted the feature on desktop: the
    tab bar that replaced it is `display: none` above 760px, so from
    2026-08-22 until Ethan noticed, no laptop could search at all. Two
    controls that share one handler and never appear together is not two
    places to maintain; it is one destination with two doors, which is
    what a responsive layout is.

    The real requirement is that SOME search control is reachable at
    every width."""
    html = _markup()
    assert 'id="nav-search"' in html and 'id="tb-search"' in html
    # And exactly one of them is on screen at any given width.
    phone = re.sub(r"\s+", " ", _media("760px"))
    assert "#nav-search { display: none; }" in phone


# --- why it broke, so it cannot break the same way --------------------------
def test_the_brand_yields_before_the_controls_do():
    """The mechanism. With the brand unshrinkable, the icons are what
    overflow — and they overflow into a container that clips them."""
    decls = _decls()
    for width in ("900px", "760px"):
        hit = re.search(r"\.brand-home\s*\{([^}]*)\}", _media(width))
        if not hit:
            continue
        assert "flex-shrink: 0" not in hit.group(1), (
            "at %s the brand refuses to shrink, so the icons are what "
            "give way — and they give way by vanishing" % width)


def test_the_controls_never_shrink_to_nothing():
    hit = re.search(r"\.meta-ico[^{]*\{([^}]*)\}", _media("900px"))
    assert hit, "the ≤900px block says nothing about the icons"
    assert "flex-shrink: 0" in hit.group(1)


def test_the_things_that_give_way_are_the_repeated_ones():
    """The freshness stamp and the date both appear elsewhere on the
    page. A control does not."""
    block = _media("900px")
    assert re.search(r"#data-source,\s*#slate-date\s*\{[^}]*display:\s*none",
                     block), "the date and the stamp still compete for space"


# --- measured -----------------------------------------------------------------
def test_no_control_is_clipped_at_any_phone_width():
    """The assertion the structural checks above are a proxy for. Opt-in,
    like tests/test_linkcolor.py's sweep and for the same reason — driving
    Chromium inside a busy suite is where flaky tests come from."""
    if not os.environ.get("QB_BROWSER_TESTS"):
        print("      (browser half skipped — set QB_BROWSER_TESTS=1)")
        return
    import http.server
    import socketserver
    import threading

    web = os.path.join(ROOT, "web")

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=web, **kw)

        def log_message(self, *a):
            pass

    with socketserver.TCPServer(("127.0.0.1", 0), Quiet) as srv:
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b = pw.chromium.launch(
                executable_path=os.environ.get("CHROMIUM_PATH")
                or "/opt/pw-browsers/chromium")
            for w in (320, 360, 390, 430, 560, 768, 900, 1280):
                pg = b.new_page(viewport={"width": w, "height": 844})
                pg.goto("http://127.0.0.1:%d/index.html" % port)
                pg.wait_for_timeout(700)
                bad = pg.evaluate("""() => {
                  const bar = document.querySelector('.topbar');
                  const br = bar.getBoundingClientRect();
                  const out = [];
                  const seen = [];
                  for (const el of bar.querySelectorAll(
                        '.menu-toggle, .brand-home, .slate-meta > *')) {
                    const cs = getComputedStyle(el);
                    const r = el.getBoundingClientRect();
                    if (cs.display === 'none' || r.width < 2) continue;
                    const id = el.id || el.className.toString().split(' ')[0];
                    if (r.left < br.left - 1 || r.right > br.right + 1)
                      out.push('clipped:' + id);
                    seen.push({id, l: r.left, r: r.right});
                  }
                  seen.sort((a, b) => a.l - b.l);
                  for (let i = 1; i < seen.length; i++)
                    if (seen[i].l < seen[i - 1].r - 1)
                      out.push('overlap:' + seen[i - 1].id + '/' + seen[i].id);
                  return out;
                }""")
                pg.close()
                assert not bad, "at %dpx: %s" % (w, bad)
            b.close()
        srv.shutdown()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("  ok  %s" % fn.__name__)
    print()
    print("%d tests passed." % len(fns))
