"""The pages that are not app views must not sit in the app's grid.

FOUND LIVE, 2026-08-22, from a screenshot: the whole Terms of Service
rendered in a strip down the left of a 1900px screen with the rest of the
page empty. The Privacy Policy did the same.

THE CAUSE. `.shell` is the app's layout — `grid-template-columns: 240px
minmax(0, 1fr)`, where the 240px is the sidebar. terms.html and
privacy.html wrapped their content in `.shell` but have no sidebar, so
`<main>` became the FIRST grid item and rendered inside the column
reserved for one.

404.html and maintenance.html never used it, which is why they were fine
and why they are the pattern.

WHY IT SURVIVED. Nothing measured it. The suite read these files as text
and the browser sweeps drove the app, not the standalone pages. A layout
bug is invisible to a test that never lays anything out — so this file
asserts the structural rule, and the width check below runs a real
browser when one is available.

    python3 tests/test_standalone_pages.py
    QB_BROWSER_TESTS=1 python3 tests/test_standalone_pages.py
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Every page that is served on its own URL rather than as a hash view.
STANDALONE = ("terms.html", "privacy.html", "404.html", "maintenance.html")


def _read(name):
    """Markup only. The comments on these pages explain the .shell bug and
    quote the tags involved — `<main>` and `class="shell"` both appear in
    prose — so counting tags in the raw file counts the explanation too.
    This repo has now made that mistake often enough to have a habit."""
    raw = open(os.path.join(ROOT, "web", name), encoding="utf-8").read()
    return re.sub(r"<!--.*?-->", " ", raw, flags=re.S)


def _raw(name):
    return open(os.path.join(ROOT, "web", name), encoding="utf-8").read()


def test_no_standalone_page_wraps_itself_in_the_app_grid():
    for name in STANDALONE:
        html = _read(name)
        assert 'class="shell"' not in html, (
            "%s is inside .shell, whose first column is 240px and reserved "
            "for a sidebar this page does not have — its content will "
            "render in a strip down the left" % name)


def test_every_standalone_page_has_exactly_one_main():
    for name in STANDALONE:
        html = _read(name)
        assert html.count("<main") == 1, name
        assert html.count("</main>") == 1, name


def test_the_tags_still_balance():
    """The .shell wrapper was removed by hand, and the risk of that is a
    stray </div>."""
    for name in STANDALONE:
        html = _read(name)
        opens = len(re.findall(r"<div\b", html))
        closes = len(re.findall(r"</div>", html))
        assert opens == closes, (
            "%s has %d <div> and %d </div>" % (name, opens, closes))


def test_the_legal_pages_have_a_readable_column():
    css = open(os.path.join(ROOT, "web", "css", "styles.css"),
               encoding="utf-8").read()
    rule = css[css.index(".legal {"):]
    rule = rule[:rule.index("}")]
    assert "max-width" in rule and "margin" in rule and "auto" in rule, (
        "the legal column is neither bounded nor centred")


def test_the_wrapper_that_replaced_it_is_styled():
    css = open(os.path.join(ROOT, "web", "css", "styles.css"),
               encoding="utf-8").read()
    assert ".legal-main" in css


# --- the measurement, when there is a browser -------------------------------
def test_the_column_is_centred_in_a_real_browser():
    """Opt-in, like tests/test_linkcolor.py's sweep and for the same
    reason: driving Chromium inside a busy suite is where flaky tests come
    from. The structural checks above run every time and are what catch
    the regression; this is the one that proves the fix."""
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
            pg = b.new_page(viewport={"width": 1400, "height": 900})
            for name in ("terms.html", "privacy.html"):
                pg.goto("http://127.0.0.1:%d/%s" % (port, name))
                m = pg.evaluate("""() => {
                  const r = document.querySelector('.legal')
                    .getBoundingClientRect();
                  return {left: Math.round(r.left),
                          right: Math.round(window.innerWidth - r.right)};
                }""")
                # Centred: the gaps either side are within a few pixels.
                assert abs(m["left"] - m["right"]) < 12, (
                    "%s is not centred — %dpx left, %dpx right. That is "
                    "the .shell bug." % (name, m["left"], m["right"]))
                assert m["left"] > 100, (
                    "%s starts %dpx from the edge on a 1400px screen"
                    % (name, m["left"]))
            b.close()
        srv.shutdown()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("  ok  %s" % fn.__name__)
    print()
    print("%d tests passed." % len(fns))
