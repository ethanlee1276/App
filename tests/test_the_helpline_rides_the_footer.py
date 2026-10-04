"""21+ and 1-800-GAMBLER: in the footer of every page with a pick or a bet,
and on the pages that hide the footer. Zoom stays allowed.

History. Audit 2026-09-30, P1-8 (roadmap #7) put one extra line above every
view: "21+ only · Gambling problem? Call or text 1-800-GAMBLER · Estimates,
not advice". Ethan, 2026-10-01, circling it on the phone Home: "Please
remove what I circled it's ugly and we have other spots to display this
info." The other spots are what this file pins:

  * the footer's full notice on every page that shows a pick, a price or
    a bet (tests/test_preservation.py pins the words and the quiet list);
  * the paywall and the checkout, which hide the site footer and print
    their own line;
  * the Ask room, which hides the footer and carries the line in its intro.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "web" / "index.html").read_text()
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 3]


def test_no_line_sits_above_the_views():
    assert 'class="rg-line"' not in HTML and ".rg-line" not in CSS


def test_the_footer_carries_the_full_notice():
    i = HTML.index('<div class="footer-full">')
    block = HTML[i:HTML.index("</div>", i)]
    assert "21 or older" in block and "1-800-GAMBLER" in block


def test_the_pages_that_hide_the_footer_print_their_own_line():
    for fn in ("paywallHTML", "checkoutHTML"):
        body = re.sub(r"\s+", " ", _fn(fn))
        assert re.search(r'class="pw-legal[^"]*">21\+ · Not betting advice · Gambling problem\? '
                         r"Call <b>1-800-GAMBLER</b>", body), fn
    assert '<span class="ask-help">21+ · 1-800-GAMBLER</span>' in _fn("renderAsk")
    # Those are the pages whose footer is hidden (walled, Ask).
    assert "body.walled .topbar, body.walled .footer { display: none !important; }" in CSS
    assert "body.ask-open .footer { display: none; }" in CSS


def test_the_viewport_allows_zoom():
    vp = HTML[HTML.index('name="viewport"'):]
    vp = vp[:vp.index(">")]
    assert "user-scalable=no" not in vp and "maximum-scale" not in vp


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
    sys.exit(0)
