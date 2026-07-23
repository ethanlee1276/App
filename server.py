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
import sys
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
}

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quieter logging
        sys.stderr.write("  %s\n" % (fmt % args))

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/api/recommendations", "/api/recommendations/"):
            return self._api(parse_qs(parsed.query), sport="nfl")
        if parsed.path in ("/api/mlb/recommendations", "/api/mlb/recommendations/"):
            return self._api(parse_qs(parsed.query), sport="mlb")
        return self._static(parsed.path)

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
                self._send(200, live.read_bytes(), ".json")
                return
            # No build yet → fall through to the sample pipeline below so the
            # page still loads (with a clear note in LAUNCH.md on how to build).

        config = RuleConfig(
            min_confidence=qf("min_confidence", 6.0),
            min_edge=qf("min_edge", 0.02) / (100 if qf("min_edge", 0.02) > 1 else 1),
        )
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
        target = (WEB / path.lstrip("/")).resolve()
        # Prevent path traversal outside the web root.
        if not str(target).startswith(str(WEB.resolve())) or not target.is_file():
            self._send(404, b"Not found", ".html")
            return
        self._send(200, target.read_bytes(), target.suffix)

    def _send(self, code: int, body: bytes, suffix: str):
        self.send_response(code)
        self.send_header("Content-Type", CONTENT_TYPES.get(suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    args = sys.argv[1:]
    live = "--live" in args
    ports = [a for a in args if not a.startswith("--")]
    port = int(ports[0]) if ports else 8000

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.live_mode = live  # read by Handler._api

    mode = "LIVE data" if live else "sample data"
    print(f"Gridiron Edge running ({mode}) → http://localhost:{port}")
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
