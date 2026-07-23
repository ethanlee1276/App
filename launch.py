#!/usr/bin/env python3
"""One-command launcher — refresh live data for both leagues, then serve.

    python3 launch.py                 # → http://localhost:8000
    python3 launch.py 9000            # custom port
    python3 launch.py --refresh 0     # refresh once at startup, don't keep polling

On startup this pulls the newest data it can reach for **both NFL and MLB**,
writes it to ``web/data/``, and then starts the live server. While it runs it
keeps that data fresh in the background (default every 90s) so live scores — and
book lines, if you've set ``ODDS_API_KEY`` — stay current during games.

Anything unreachable (blocked network, a league in its offseason, no odds key)
is skipped with a clear message and the last-known data is kept, so the site
always comes up. Player props and live scores need no key; the game-level bets
(moneyline / spread / totals) also need team ratings — run ``ingest.py`` once.
"""

from __future__ import annotations

import datetime as _dt
import os
import subprocess
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

from server import Handler, LIVE_FILES  # reuse the --live server

ROOT = Path(__file__).parent


def _run_build(args: list[str]) -> tuple[bool, str]:
    """Run a build script as a subprocess. Returns (ok, last_output_line)."""
    try:
        proc = subprocess.run([sys.executable, *args], cwd=str(ROOT),
                              capture_output=True, text=True, timeout=180)
    except Exception as exc:  # noqa: BLE001 — never let a refresh crash the server
        return False, str(exc)
    out = (proc.stdout + proc.stderr).strip().splitlines()
    tail = out[-1] if out else ""
    return proc.returncode == 0, tail


def _with_odds() -> bool:
    return bool(os.environ.get("ODDS_API_KEY"))


def refresh_mlb(quiet: bool = False) -> bool:
    """Build today's MLB slate into web/data/mlb_recommendations.json."""
    date = _dt.date.today().isoformat()
    args = ["mlb_build.py", date, "--out", "web/data/mlb_recommendations.json"]
    if _with_odds():
        args.append("--odds")
    ok, tail = _run_build(args)
    if not quiet:
        print(f"  MLB  {date}: {'refreshed' if ok else 'unavailable — kept existing data'}"
              + (f"  ({tail})" if not ok and tail else ""))
    return ok


def _current_nfl_week():
    """Best-effort (season, week) for the games nearest today, or None in the
    offseason / when the schedule can't be reached."""
    try:
        from engine.sources.nflverse import load_schedules, _s
        rows = load_schedules()
    except Exception:
        return None
    today = _dt.date.today()
    best = None  # (abs_days, season, week)
    for r in rows:
        gd = _s(r, "gameday")
        try:
            d = _dt.date.fromisoformat(gd[:10])
            season, week = int(_s(r, "season")), int(_s(r, "week"))
        except Exception:
            continue
        diff = abs((d - today).days)
        if best is None or diff < best[0]:
            best = (diff, season, week)
    # Only treat it as "current" if the nearest game is within a week.
    if best and best[0] <= 7:
        return best[1], best[2]
    return None


def refresh_nfl(quiet: bool = False) -> bool:
    """Build the current NFL week into web/data/recommendations.json."""
    wk = _current_nfl_week()
    if not wk:
        if not quiet:
            print("  NFL  no current slate (offseason / schedule unavailable) — kept existing data")
        return False
    season, week = wk
    args = ["nfl_build.py", str(season), str(week), "--out", "web/data/recommendations.json"]
    if _with_odds():
        args.append("--odds")
    ok, tail = _run_build(args)
    if not quiet:
        print(f"  NFL  {season} wk {week}: {'refreshed' if ok else 'unavailable — kept existing data'}"
              + (f"  ({tail})" if not ok and tail else ""))
    return ok


def refresh_all(quiet: bool = False) -> None:
    refresh_mlb(quiet=quiet)
    refresh_nfl(quiet=quiet)


def _background_refresher(interval: int) -> None:
    """Keep the served data fresh while the server runs (quiet after startup)."""
    while True:
        time.sleep(interval)
        refresh_all(quiet=True)


def main() -> None:
    argv = sys.argv[1:]
    interval = 90
    if "--refresh" in argv:
        i = argv.index("--refresh")
        try:
            interval = int(argv[i + 1]); del argv[i:i + 2]
        except (ValueError, IndexError):
            print("--refresh needs a number of seconds (0 to disable)."); return
    ports = [a for a in argv if not a.startswith("--")]
    port = int(ports[0]) if ports else 8000

    print("Gridiron Edge — grabbing the newest live data for both leagues…")
    if not _with_odds():
        print("  (no ODDS_API_KEY set — using model/proxy lines; live scores still update)")
    refresh_all()

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.live_mode = True

    if interval > 0:
        t = threading.Thread(target=_background_refresher, args=(interval,), daemon=True)
        t.start()
        print(f"Auto-refresh every {interval}s (set --refresh 0 to disable).")

    print(f"\nGridiron Edge running (LIVE data) → http://localhost:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
