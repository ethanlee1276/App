"""Polymarket is asked for a compressed page (engine/sources/polysports).

The box, 2026-11-14, Ethan's catch-up (step OY): every college read the
build makes had been refused "HTTP Error 406: Not Acceptable" since college
joined, and the probe printed the body this time:

    {"error":"gzip_required","hint":"send the header Accept-Encoding: gzip.
     /events and /events/keyset pages with limit above 50 are served
     compressed only."}

College's soonest hundred and its two-day window both ask for more than
fifty; only the page of twenty answered, oldest first, so 19 games of a
71-game night carried Polymarket's price. Every ask now says it takes gzip
(`polysports.ACCEPT`) and `fetch.fetch_text` unpacks the body. A stand-in
venue here refuses exactly as the real one did unless it is asked that way.

    python3 tests/test_polymarket_is_asked_for_a_compressed_page.py
"""
import gzip
import http.server
import json
import sys
import tempfile
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.sources import fetch as F                           # noqa: E402
from engine.sources import polysports as PS                     # noqa: E402

REFUSAL = (b'{"error":"gzip_required","hint":"send the header Accept-Encoding: gzip. /events and '
           b'/events/keyset pages with limit above 50 are served compressed only."}')
EVENTS = [{"slug": f"cbb-a{i}-b{i}-2026-11-14", "startDate": "2026-11-14T23:00:00Z", "markets": []}
          for i in range(60)]


class _Venue(http.server.BaseHTTPRequestHandler):
    """Gamma's rule as its own refusal states it."""
    asked: list = []

    def do_GET(self):                                            # noqa: N802
        q = parse_qs(urlparse(self.path).query)
        limit = int((q.get("limit") or ["20"])[0])
        takes_gzip = "gzip" in (self.headers.get("Accept-Encoding") or "")
        type(self).asked.append((limit, takes_gzip, self.headers.get("User-Agent")))
        if limit > 50 and not takes_gzip:
            self.send_response(406)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(REFUSAL)))
            self.end_headers()
            self.wfile.write(REFUSAL)
            return
        body = json.dumps(EVENTS[:limit]).encode()
        if takes_gzip:
            body = gzip.compress(body)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        if takes_gzip:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_a):                                  # quiet
        pass


def _venue():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Venue)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def _with_venue(fn):
    _Venue.asked = []
    srv, base = _venue()
    keep_gamma, keep_cache = PS.GAMMA, F.CACHE_DIR
    PS.GAMMA, F.CACHE_DIR = base, Path(tempfile.mkdtemp())
    try:
        return fn()
    finally:
        PS.GAMMA, F.CACHE_DIR = keep_gamma, keep_cache
        srv.shutdown()


def test_the_soonest_hundred_answers_when_it_is_asked_for_gzip():
    page = dict(PS.SHAPES["cbb"])["page"]
    assert int(page["limit"]) > 50, "the page that was refused is still the first one asked"
    got = _with_venue(lambda: PS.fetch_series_events("10470", params=page, shape="page",
                                                     timeout=PS.SLOW["cbb"]))
    assert len(got) == 60 and got[0]["slug"] == "cbb-a0-b0-2026-11-14", "every event, unpacked"
    assert _Venue.asked == [(100, True, F.USER_AGENT)], _Venue.asked


def test_without_the_header_the_venue_refuses_as_the_box_saw():
    def bare():
        try:
            F.fetch_text(f"{PS.GAMMA}/events?series_id=10470&limit=100", "poly_test_bare.json", ttl=0)
        except F.DataUnavailable as exc:
            return exc
        return None
    exc = _with_venue(bare)
    assert exc is not None and exc.status == 406, "the stand-in refuses the way the box was refused"


def test_every_league_and_every_ask_says_it_takes_gzip():
    assert PS.ACCEPT == {"Accept-Encoding": "gzip"}
    src = (ROOT / "engine" / "sources" / "polysports.py").read_text(encoding="utf-8")
    assert src.count("headers=ACCEPT") == 3, "the series, the tag and /sports"
    got = _with_venue(lambda: PS.fetch_events("nba", limit=200))
    assert len(got) == 60 and _Venue.asked[-1][1] is True, "a league that answered before still answers"
    assert "**ACCEPT" in src[src.index("def probe("):], "the box's probe asks the way the build asks"


def test_the_probe_reads_what_the_build_reads():
    keep = PS.SPORT_KEYS, PS.SPORT_TAGS

    class _Sports(_Venue):
        def do_GET(self):                                        # noqa: N802
            if self.path.startswith("/sports"):
                body = gzip.compress(json.dumps([{"sport": "cbb", "series": "10470"}]).encode())
                self.send_response(200)
                self.send_header("Content-Encoding", "gzip")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            super().do_GET()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Sports)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    keep_gamma = PS.GAMMA
    PS.GAMMA = f"http://127.0.0.1:{srv.server_address[1]}"
    PS.SPORT_TAGS = {**PS.SPORT_TAGS, "cbb": ()}
    try:
        lines = PS.probe("cbb")
    finally:
        PS.GAMMA = keep_gamma
        PS.SPORT_KEYS, PS.SPORT_TAGS = keep
        srv.shutdown()
    page = next(ln for ln in lines if ln.startswith("series 10470, page:"))
    assert page.startswith("series 10470, page: 200,") and "cbb-a0-b0" in page, page
    assert "gzip_required" not in "\n".join(lines)


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc(limit=3)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
