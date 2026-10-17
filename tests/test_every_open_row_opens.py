"""Every Most Likely row opens its pick, on every page that draws one.

Ethan, 2026-09-23, a screenshot of the Most Likely page: "it's not letting
me click on any of these props and pull up the charts and shit on the
most likely page."

The v5 row (web/js/app.js `likelyRow`, 2026-09-22) is a
<button data-open="prop:…">. Each page that drew one bound the click
itself; the home preview and the one-league Tonight page did, and the
Most Likely page — the one that draws the most of them — did not, nor
did your own league's block on Tonight-every-league. The site-wide card
handler reads data-prop and skips buttons on purpose, so nothing caught
the tap. Measured in a headless phone browser against the demo board:
before, a tap left the page on #likely; after, it opens
#pick/josh-jacobs-anytime-td with its bar graph.

Now one document listener opens every [data-open] row, wherever drawn.
This drives that listener in node with a fake tap.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _listener() -> str:
    """The one document click listener that reads [data-open]."""
    i = APP.index('e.target.closest("[data-open]")')
    start = APP.rindex('document.addEventListener("click", (e) => {', 0, i)
    end = APP.index("\n});", i) + 4
    return APP[start:end]


def test_the_listener_is_site_wide_and_opens_through_openfrom():
    body = _listener()
    assert body.startswith('document.addEventListener("click"'), "on the document, so no page can forget it"
    assert "openFrom(row.dataset.open)" in body
    assert "a, button" not in body, "a row IS a button; skipping buttons was the bug"
    for page in ("function renderLikely(", "function renderTonight(", "function renderTonightAll("):
        i = APP.index(page)
        j = APP.index("\nfunction ", i + 1)
        assert 'querySelectorAll("[data-open]")' not in APP[i:j], f"{page} binds its own again: rows open twice"


def test_a_tap_on_a_row_or_inside_it_opens_the_pick():
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed")
        return
    prog = """
const opened = [];
const handlers = [];
const document = { addEventListener: (t, fn) => { if (t === "click") handlers.push(fn); } };
function openFrom(spec) { opened.push(spec); }
%s
const row = { dataset: { open: "prop:Josh Jacobs|anytime_td|OVER|0.5" } };
const inside = { closest: (sel) => sel === "[data-open]" ? row : null };
const outside = { closest: () => null };
handlers.forEach((h) => h({ target: inside }));
handlers.forEach((h) => h({ target: outside }));
console.log(JSON.stringify(opened));
""" % _listener()
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == ["prop:Josh Jacobs|anytime_td|OVER|0.5"], "one tap, one open; a tap elsewhere, none"


def test_the_row_still_carries_where_it_goes():
    i = APP.index("function likelyRow(")
    row = APP[i:APP.index("\nfunction ", i + 1)]
    assert '<button class="ml-row" type="button"${likelyOpen(r)}' in row


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
            traceback.print_exc(limit=3)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
