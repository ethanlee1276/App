"""The freshness chip has to measure the DATA, not the fetch.

The site's header says how old the board is. It used to time its own
fetch, which is always a few seconds — so a phone across town read
"Updated 4s ago" over a board the laptop had stopped rebuilding hours
earlier. That is the one number you check when you're away from the
machine, and it could not fail in the honest direction.

The server now sends Last-Modified from the file it just read, so the
answer comes from the build rather than the request. No build script has
to cooperate: every payload is a file on disk, and a build that fails
leaves the previous file — and its older timestamp — in place, which is
exactly the signal wanted.
"""

import os
import re
import sys
import threading
import time
import urllib.request
from email.utils import parsedate_to_datetime
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _serve():
    """A real server on a throwaway port; returns (base_url, shutdown)."""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    httpd.live_mode = False
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{httpd.server_address[1]}", httpd.shutdown


def test_a_served_file_carries_its_build_time():
    base, stop = _serve()
    try:
        path = os.path.join(ROOT, "web", "index.html")
        r = urllib.request.urlopen(base + "/index.html")
        stamp = r.headers["Last-Modified"]
        assert stamp, "no Last-Modified — the chip has nothing to measure"
        served = parsedate_to_datetime(stamp).timestamp()
        # HTTP dates are whole seconds, so allow a second of rounding.
        assert abs(served - os.path.getmtime(path)) < 1.5
    finally:
        stop()


def test_an_old_file_reports_as_old():
    """The failure mode in one test: freeze the build, keep serving."""
    base, stop = _serve()
    target = os.path.join(ROOT, "web", "favicon.svg")
    original = os.path.getmtime(target)
    try:
        three_hours_ago = time.time() - 3 * 3600
        os.utime(target, (three_hours_ago, three_hours_ago))
        r = urllib.request.urlopen(base + "/favicon.svg")
        served = parsedate_to_datetime(r.headers["Last-Modified"]).timestamp()
        age_min = (time.time() - served) / 60
        assert age_min > 170, f"served age was {age_min:.0f} min, expected ~180"
    finally:
        os.utime(target, (original, original))
        stop()


def test_the_header_is_readable_cross_origin():
    # Last-Modified is not a CORS-safelisted response header; without this
    # the phone's JS sees null whenever the page isn't same-origin.
    base, stop = _serve()
    try:
        r = urllib.request.urlopen(base + "/index.html")
        exposed = (r.headers.get("Access-Control-Expose-Headers") or "")
        assert "Last-Modified" in exposed
    finally:
        stop()


def _app_js():
    with open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8") as fh:
        return fh.read()


def test_the_chip_prefers_the_build_time_over_the_fetch_time():
    app = _app_js()
    assert 'res.headers.get("Last-Modified")' in app
    assert "state.builtAt" in app
    fn = app[app.index("function updateAgo()"):]
    fn = fn[:fn.index("\n}\n")]
    # The fetch time may only be a fallback…
    assert "state.builtAt : state.lastLoad" in fn
    # …and when it IS the fallback, staleness must not be claimed: it can
    # only ever report seconds, so it would never fire and would quietly
    # imply everything is fine.
    assert re.search(r"const stale = known &&", fn)


def test_a_frozen_board_is_called_out():
    app = _app_js()
    m = re.search(r"STALE_AFTER_MS = (\d+) \* 60 \* 1000", app)
    assert m, "no staleness threshold"
    # The refresh loop rebuilds every 60s. Long enough not to flicker on a
    # slow cycle, short enough to catch a sleeping laptop within a coffee
    # break.
    assert 3 <= int(m.group(1)) <= 20
    fn = app[app.index("function updateAgo()"):]
    fn = fn[:fn.index("\n}\n")]
    assert "Stale" in fn
    assert 'classList.toggle("stale"' in fn
    # A stale board must not also show the live-game dot; "a game is running
    # right now" is a claim frozen data cannot make.
    assert "state.livePolling && !stale" in fn


def _css():
    with open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8") as fh:
        return fh.read()


def test_the_stale_state_is_styled():
    assert re.search(r"\.live-refresh\.stale \{", _css())


def test_the_healthy_state_is_quieter_than_the_stale_one():
    """The base chip shipped RED — red pill, red border, red text reading
    "Updated 1m ago" — while `.stale` below it was amber. Backwards, and it
    cost a real morning: a board that was working was read as broken,
    because the one chip describing its health was the loudest thing on the
    page. Whatever the fresh state is, it must not be the alarm."""
    css = _css()
    base = re.search(r"\n\.live-refresh \{([^}]*)\}", css).group(1)
    stale = re.search(r"\n\.live-refresh\.stale \{([^}]*)\}", css).group(1)
    reds = ("251, 44, 70", "#fb2c46", "#ff8a97", "var(--bad)")
    assert not any(r in base for r in reds), \
        "the healthy refresh chip is wearing the alarm colour again"
    # And the degraded state still has to differ from it, or the distinction
    # is gone in the other direction.
    assert stale.strip() and stale != base


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
