"""Add to Home Screen: the app-shaped install, and the one rule it must obey.

Ethan, 2026-08-15: *"i also wanna make sure when that happens people can
easily add it to there home screen and use it like an app."*

THE RULE THAT OUTRANKS EVERY OTHER PWA CONVENTION HERE: this site's value
is that its numbers are current. The standard service-worker pattern —
serve the cache, revalidate in the background — would show last night's
board inside a window with no address bar, and the reader would have no
way to tell. A stale line is a bet at a price that no longer exists, and
the app frame makes it MORE convincing, not less.

So the worker is network-first, `/data/` and `/api/` are never cached at
all, and the cache is a fallback for the shell only. Those are the
assertions that matter below; the manifest ones are ordinary plumbing.

Three separate mechanisms make this installable because the platforms do
not agree: the manifest (Android's install prompt), the apple- metas
(iOS launching standalone rather than inside Safari), and the
standardised spelling for everything else. All of them require HTTPS,
which is why none of it does anything until the site is behind TLS —
that is a fact about the deployment, not a gap in this file.
"""

import json
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


HTML = _read("web", "index.html")
SW = _read("web", "sw.js")
CSS = _read("web", "css", "styles.css")
MANIFEST = json.loads(_read("web", "manifest.webmanifest"))


# --- the safety property ------------------------------------------------------
def test_the_worker_never_caches_a_live_number():
    """THE ONE THAT MATTERS. Every board, price and record lives under
    /data/, and every session and payment under /api/. Caching either is
    how an installed app shows a stale line as though it were live, or
    serves one signed-in user the page of another."""
    fetch = SW[SW.index('addEventListener("fetch"'):]
    assert '"/api/"' in fetch and '"/data/"' in fetch
    # Both must bail BEFORE respondWith, not merely be mentioned.
    api = fetch.index('"/api/"')
    data = fetch.index('"/data/"')
    respond = fetch.index("respondWith")
    assert api < respond and data < respond, \
        "the skip happens after the response is taken over"
    for i in (api, data):
        line = fetch[fetch.rindex("\n", 0, i):fetch.index("\n", i)]
        assert "return" in line, f"not an early return: {line.strip()}"


def test_it_is_network_first_not_cache_first():
    """Cache-first is the usual advice and it is wrong here: it would
    serve last night's board from disk and only then go looking for
    tonight's."""
    fetch = SW[SW.index("respondWith"):]
    assert fetch.index("fetch(req)") < fetch.index("caches.match"), \
        "the cache is consulted before the network — that serves stale prices"


def test_only_the_shell_is_cached_not_every_image():
    """The first cut cached any successful same-origin GET, and the venue
    photo library landed in it the moment anyone scrolled a board —
    unbounded growth on a phone, for pictures. Measured in a browser: the
    cache held /img/venues/variants/baseball-violet.jpg."""
    assert "req.destination" in SW
    assert "unbounded" in SW.lower()
    fetch = SW[SW.index("respondWith"):]
    assert "keep &&" in fetch or "keep&&" in fetch, \
        "the destination filter is computed and then not used"


def test_an_old_cache_cannot_outlive_a_deploy():
    """A shell cached under a previous version, still served after new
    code ships, is the same bug as a stale board wearing different
    clothes."""
    act = SW[SW.index('addEventListener("activate"'):]
    act = act[:act.index("addEventListener(\"fetch\"")]
    assert "caches.delete" in act and "!== VERSION" in act


# --- the manifest -------------------------------------------------------------
def test_the_manifest_says_it_is_an_app():
    assert MANIFEST["display"] == "standalone", \
        "display is not standalone, so it opens as a browser tab"
    assert MANIFEST["name"] and MANIFEST["short_name"]
    assert MANIFEST["start_url"].startswith("/")
    assert MANIFEST["scope"] == "/"


def test_the_manifest_colours_match_the_page():
    """`black-translucent` lets the page paint under the status bar, so a
    theme-color that disagrees with the real background draws a seam
    across the top of the phone."""
    theme = re.search(r'name="theme-color" content="([^"]+)"', HTML).group(1)
    assert MANIFEST["theme_color"].lower() == theme.lower()
    assert MANIFEST["background_color"].lower() == theme.lower()


def test_every_declared_icon_exists_and_is_the_size_it_claims():
    """A manifest pointing at a missing icon fails the install silently:
    the prompt simply never appears, with nothing in the console."""
    for icon in MANIFEST["icons"]:
        path = os.path.join(ROOT, "web", icon["src"])
        assert os.path.isfile(path), f"missing icon: {icon['src']}"
        with open(path, "rb") as fh:
            head = fh.read(24)
        assert head[:8] == b"\x89PNG\r\n\x1a\n", f"not a PNG: {icon['src']}"
        w, h = struct.unpack(">II", head[16:24])
        want = icon["sizes"].split("x")
        assert (w, h) == (int(want[0]), int(want[1])), \
            f"{icon['src']} is {w}x{h}, manifest claims {icon['sizes']}"


def test_android_and_ios_are_both_wired():
    """Three mechanisms, because the platforms agree on none of it. The
    apple- meta is what makes iOS launch WITHOUT Safari's chrome; drop it
    and Add to Home Screen still works and still uses the icon, it just
    opens a bookmark."""
    assert 'rel="manifest"' in HTML, "Android has no install prompt without this"
    assert 'name="apple-mobile-web-app-capable" content="yes"' in HTML
    assert 'name="mobile-web-app-capable" content="yes"' in HTML
    assert 'name="apple-touch-icon"' in HTML or 'rel="apple-touch-icon"' in HTML


def test_the_notch_is_handled_at_both_ends():
    """Standalone + black-translucent means the page paints under the
    status bar. Without the top inset the clock sits on the wordmark.

    `viewport-fit=cover` is what makes the insets non-zero at all — the
    bottom tab bar had an inset rule for weeks that did nothing because
    of its absence."""
    assert "viewport-fit=cover" in HTML
    assert "safe-area-inset-top" in CSS
    assert "safe-area-inset-bottom" in CSS


def test_everything_pinned_to_the_bar_uses_one_token():
    """The bar grows by the inset on a notched phone. Four other rules
    pin themselves to its bottom edge, and each said a bare 64px — so
    all four would have sat that many pixels too high on exactly the
    devices this feature is for."""
    assert "--topbar-h:" in CSS
    # No rule may still hardcode the old height as a vertical offset.
    for bad in ("top: 64px", "inset: 64px"):
        assert bad not in CSS, f"still pinned to a bare {bad!r}"


def test_registration_is_a_separate_file_and_cannot_break_the_page():
    """Separate so script-src can drop 'unsafe-inline' later without this
    being the last thing holding it open. Guarded because
    navigator.serviceWorker is undefined on an insecure origin, which is
    every LAN and Tailscale address — reading .register off undefined
    would throw on the last line of every page load."""
    reg = _read("web", "js", "register-sw.js")
    assert '"serviceWorker" in navigator' in reg
    assert reg.index('"serviceWorker" in navigator') < reg.index(".register(")
    assert ".catch(" in reg, "a failed registration becomes an uncaught rejection"
    assert "register-sw.js" in HTML


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
