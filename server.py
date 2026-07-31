#!/usr/bin/env python3
"""Zero-dependency web server for the betting engine.

Serves the static dashboard in ``web/`` and exposes a live JSON API at
``/api/recommendations`` that re-runs the engine on every request — so the
threshold controls in the UI recalculate against the real model, not a cached
file. Uses only the Python standard library.

    python3 server.py           # http://localhost:8000, sample data
    python3 server.py 9000      # custom port
    python3 server.py --live    # serve pre-built live data (see LAUNCH.md)
"""

from __future__ import annotations

import json
import re
import sys
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from engine.pipeline import run_slate
from engine.mlb.pipeline import run_mlb_slate
from engine.rules import RuleConfig

ROOT = Path(__file__).parent
WEB = ROOT / "web"
SLATE = ROOT / "data" / "sample_slate.json"
MLB_SLATE = ROOT / "data" / "mlb_sample_slate.json"

# In --live mode the API serves these freshly-built files (written by
# mlb_build.py / nfl_build.py --out ...) instead of re-running the sample slate.
LIVE_FILES = {
    "nfl": WEB / "data" / "recommendations.json",
    "mlb": WEB / "data" / "mlb_recommendations.json",
    "nba": WEB / "data" / "nba.json",
}

# Sleeper league-sync proxy: the browser can't always call api.sleeper.app
# directly (CORS), so the site talks to us and we forward READ-ONLY requests.
# Allowlisted paths only — this must never become an open proxy.
SLEEPER_BASE = "https://api.sleeper.app/v1/"
_SLEEPER_OK = re.compile(
    r"^(user/[A-Za-z0-9_]{1,40}"
    r"|user/\d{1,25}/leagues/nfl/\d{4}"
    r"|league/\d{1,25}(/rosters|/users|/drafts)?"
    r"|draft/\d{1,25}(/picks)?"
    r"|players/nfl)$")


def sleeper_path_ok(path: str) -> bool:
    return bool(_SLEEPER_OK.match(path))


CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".webmanifest": "application/manifest+json",
}


_TLS_HINTED = False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quieter logging
        sys.stderr.write("  %s\n" % (fmt % args))

    def handle_one_request(self):
        # A TLS ClientHello (first byte 0x16) on this plain-HTTP port means
        # a phone typed — or Safari silently upgraded to — https://. Without
        # this check the log sprays cipher-suite bytes as "Bad request
        # version" garbage; name the actual problem once instead.
        try:
            peek = self.rfile.peek(1)[:1]
        except Exception:
            peek = b""
        if peek == b"\x16":
            global _TLS_HINTED
            if not _TLS_HINTED:
                _TLS_HINTED = True
                sys.stderr.write(
                    "  ↳ A device tried HTTPS against this HTTP-only server.\n"
                    "    On the phone, spell out http:// in the address —\n"
                    "    Safari silently upgrades bare addresses to https.\n"
                    "    Want a real https:// URL? Run:  tailscale serve --bg 8000\n"
                    "    then use the https://…ts.net link it prints. docs/PHONE.md has details.\n")
            self.close_connection = True
            return
        super().handle_one_request()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/api/recommendations", "/api/recommendations/"):
            return self._api(parse_qs(parsed.query), sport="nfl")
        if parsed.path in ("/api/mlb/recommendations", "/api/mlb/recommendations/"):
            return self._api(parse_qs(parsed.query), sport="mlb")
        if parsed.path in ("/api/nba/recommendations", "/api/nba/recommendations/"):
            return self._api(parse_qs(parsed.query), sport="nba")
        if parsed.path.startswith("/api/sleeper/"):
            return self._sleeper(parsed.path[len("/api/sleeper/"):].strip("/"))
        return self._static(parsed.path)

    def _sleeper(self, path: str):
        """Forward an allowlisted read to Sleeper's free public API. The big
        players file gets a day-long disk cache; everything else 5 minutes."""
        if not sleeper_path_ok(path):
            return self._send(404, b'{"error":"unsupported sleeper path"}', ".json")
        from engine.sources.fetch import fetch_text, DataUnavailable
        # players/nfl is ~5MB and changes daily; draft picks are polled DURING
        # a live draft, where five minutes of cache would show a board three
        # rounds stale. Everything else can sit for five minutes.
        ttl = (86400 if path == "players/nfl"
               else 10 if path.endswith("/picks") else 300)
        cache = "sleeper_" + re.sub(r"[^A-Za-z0-9]+", "_", path) + ".json"
        try:
            body = fetch_text(SLEEPER_BASE + path, cache, ttl=ttl)
        except DataUnavailable as exc:
            return self._send(502, json.dumps({"error": str(exc)}).encode(), ".json")
        self._send(200, body.encode(), ".json")

    # --- API ---------------------------------------------------------------
    def _api(self, query: dict, sport: str = "nfl"):
        def qf(name, default):
            try:
                return float(query.get(name, [default])[0])
            except (TypeError, ValueError):
                return default

        # Live mode: serve the pre-built file if one exists. The frontend
        # re-applies the confidence/edge filters client-side, so the sliders
        # still work against this data.
        if getattr(self.server, "live_mode", False):
            live = LIVE_FILES.get(sport)
            if live and live.is_file():
                self._send(200, live.read_bytes(), ".json",
                           mtime=live.stat().st_mtime)
                return
            # No build yet → fall through to the sample pipeline below so the
            # page still loads (with a clear note in LAUNCH.md on how to build).

        # The site's slider sends min_edge in PERCENT (0, 0.5, 1, 2, …). The
        # old ">1 means percent" guess turned a 1% or 0.5% setting into a
        # 100%/50% edge floor that filtered every prop. No real edge floor
        # exceeds 20%, so anything above that is percent; below is a fraction.
        raw_edge = qf("min_edge", 2.0)
        config = RuleConfig(
            min_confidence=qf("min_confidence", 6.0),
            min_edge=raw_edge / 100.0 if raw_edge >= 0.2 else raw_edge,
            max_juice=int(qf("max_juice", -350)),
        )
        # NBA has no sample pipeline — the built file is the only source.
        # (The frontend re-applies its filters client-side either way.)
        if sport == "nba":
            live = LIVE_FILES["nba"]
            if live.is_file():
                self._send(200, live.read_bytes(), ".json",
                           mtime=live.stat().st_mtime)
            else:
                # Full shared-schema shape even when nothing is built — a
                # stub missing keys crashed the frontend renderers once.
                self._send(200, json.dumps({
                    "date": "", "status": "not built", "sport": "nba",
                    "games": [], "recommendations": [], "game_bets": [],
                    "long_shots": [], "longshot_watch": [],
                    "market_scan": {}, "counts": {"props_analyzed": 0,
                                                  "recommended": 0},
                }).encode(), ".json")
            return
        try:
            if sport == "mlb":
                result = run_mlb_slate(MLB_SLATE, config)
            else:
                result = run_slate(SLATE, config)
            payload = json.dumps(result).encode()
        except Exception as exc:  # surface engine errors as JSON
            self._send(500, json.dumps({"error": str(exc)}).encode(), ".json")
            return
        self._send(200, payload, ".json")

    # --- Static files ------------------------------------------------------
    def _static(self, path: str):
        if path in ("/", ""):
            path = "/index.html"
        # Browsers probe /favicon.ico on their own, before they have parsed
        # the <link rel="icon"> that points at our SVG. We only ship the one
        # icon, so hand it back here too — otherwise every single page load
        # logs a 404 that means nothing.
        if path == "/favicon.ico":
            path = "/favicon.svg"
        target = (WEB / path.lstrip("/")).resolve()
        # Prevent path traversal outside the web root. is_relative_to (not a
        # string prefix) so a sibling like web2/ could never slip through.
        if not target.is_relative_to(WEB.resolve()) or not target.is_file():
            self._send(404, b"Not found", ".html")
            return
        self._send(200, target.read_bytes(), target.suffix,
                   mtime=target.stat().st_mtime)

    def _send(self, code: int, body: bytes, suffix: str, mtime: float | None = None):
        self.send_response(code)
        self.send_header("Content-Type", CONTENT_TYPES.get(suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # When the payload came from a file on disk, say when that file was
        # last written. The site's freshness chip used to time its own
        # fetch, which is always a few seconds old — so a phone across town
        # read "Updated 4s ago" over a board the laptop stopped rebuilding
        # hours earlier. This is the age of the DATA, and it needs no build
        # script to cooperate: every payload is a file, and a build that
        # fails leaves the old one (and its old timestamp) in place.
        if mtime is not None:
            self.send_header("Last-Modified", formatdate(mtime, usegmt=True))
            self.send_header("Access-Control-Expose-Headers", "Last-Modified")
        self.end_headers()
        self.wfile.write(body)


def _lan_ip():
    """This machine's LAN address — the URL a phone on the same Wi-Fi can
    open. The UDP connect never sends a packet; it just makes the OS pick
    the outbound interface. None when there's no usable network."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        finally:
            s.close()
        return None if ip.startswith("127.") else ip
    except OSError:
        return None


def main() -> None:
    args = sys.argv[1:]
    live = "--live" in args
    ports = [a for a in args if not a.startswith("--")]
    port = int(ports[0]) if ports else 8000

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.live_mode = live  # read by Handler._api

    mode = "LIVE data" if live else "sample data"
    print(f"Qellys Book running ({mode}) → http://localhost:{port}")
    lan = _lan_ip()
    if lan:
        print(f"  On your phone (same Wi-Fi): http://{lan}:{port}")
    if live:
        for sport, path in LIVE_FILES.items():
            state = "ready" if path.is_file() else "not built yet — see LAUNCH.md"
            print(f"  {sport.upper()}: {path.relative_to(ROOT)} ({state})")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
