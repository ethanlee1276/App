#!/usr/bin/env python3
"""One-command launcher — refresh live data for both leagues, then serve.

    python3 launch.py                 # → http://localhost:8000
    python3 launch.py 9000            # custom port
    python3 launch.py --refresh 0     # refresh once at startup, don't keep polling
    python3 launch.py --check         # readiness checklist (no server) — run this first
    python3 launch.py --reset-budget  # after swapping in a new ODDS_API_KEY

On startup this pulls the newest data it can reach for **both NFL and MLB**,
writes it to ``web/data/``, and then starts the live server. While it runs it
keeps that data fresh in the background (default every 60s).

Scores and odds refresh on **separate cadences on purpose**. Live scores come
from free, unlimited feeds, so they update every cycle. Sportsbook odds are
metered — a full MLB slate costs about one request per game, and the free plan
allows 500 a *month* — so they only re-pull when the budget in
``engine.oddsbudget`` says it's affordable. Without that, an evening of live
tracking would silently exhaust a month's quota in under an hour and the board
would go stale with no explanation.

Anything unreachable (blocked network, a league in its offseason, no odds key)
is skipped with a clear message and the last-known data is kept, so the site
always comes up. Player props and live scores need no key; the game-level bets
(moneyline / spread / totals) also need team ratings — run ``ingest.py`` once.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import subprocess
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

from server import Handler, LIVE_FILES  # reuse the --live server
from engine.secrets import load_local_secrets

ROOT = Path(__file__).parent
load_local_secrets()  # pull ODDS_API_KEY from secrets.local into the environment


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


def _games_on_slate(path: str) -> int:
    """How many games the last build found — the per-refresh odds cost."""
    try:
        with open(path) as fh:
            return max(1, len(json.load(fh).get("games", [])))
    except Exception:
        return 10


def _odds_affordable(out_path: str, quiet: bool) -> bool:
    """Decide whether this refresh can afford to re-pull odds.

    Scores are free and always refresh; odds are metered, so they only ride
    along when the budget allows. This is what keeps live tracking from
    silently burning a month's quota in an evening.
    """
    if not _with_odds():
        return False
    try:
        from engine.oddsbudget import should_refresh, mark_refreshed
    except Exception:
        return True
    ok, reason = should_refresh(_games_on_slate(out_path) + 1)
    if not quiet:
        print(f"       {reason}")
    if ok:
        mark_refreshed()
    return ok


def refresh_mlb(quiet: bool = False) -> bool:
    """Build today's MLB slate into web/data/mlb_recommendations.json."""
    date = _dt.date.today().isoformat()
    out = "web/data/mlb_recommendations.json"
    args = ["mlb_build.py", date, "--out", out]
    if _odds_affordable(out, quiet):
        args.append("--odds")
        if quiet:                     # background cycle: only re-price what's live/soon
            args.append("--active-odds")
    elif _with_odds():
        # Budget says don't SPEND — but the last paid pull's prices are cached
        # and free. Without this, every 60s score refresh rebuilt the slate
        # with proxy lines, silently wiping real prices off the site for all
        # but the minute after each paid pull.
        args.append("--cached-odds")
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
    out = "web/data/recommendations.json"
    args = ["nfl_build.py", str(season), str(week), "--out", out]
    if _odds_affordable(out, quiet):
        args.append("--odds")
        if quiet:
            args.append("--active-odds")
    elif _with_odds():
        args.append("--cached-odds")   # keep last paid prices; never overwrite with proxies
    ok, tail = _run_build(args)
    if not quiet:
        print(f"  NFL  {season} wk {week}: {'refreshed' if ok else 'unavailable — kept existing data'}"
              + (f"  ({tail})" if not ok and tail else ""))
    return ok


def refresh_predmarkets(quiet: bool = False) -> bool:
    """Polymarket markets + trade tape → web/data/predmarkets.json.

    Free keyless endpoints with short-TTL caching, so riding the normal
    refresh cycle costs nothing metered. Recording runs on every build —
    the tape cannot be backfilled."""
    ok, tail = _run_build(["pm_build.py", "--out", "web/data/predmarkets.json"])
    if not quiet:
        print(f"  PM   markets: {'refreshed' if ok else 'unavailable — kept existing data'}"
              + (f"  ({tail})" if not ok and tail else ""))
    return ok


def refresh_fantasy(quiet: bool = False) -> bool:
    """Fantasy usage boards from the local DB — zero network."""
    ok, tail = _run_build(["fantasy_build.py", "--out", "web/data/fantasy.json"])
    if not quiet:
        print(f"  FF   fantasy: {'refreshed' if ok else 'unavailable'}"
              + (f"  ({tail})" if not ok and tail else ""))
    return ok


def refresh_nba(quiet: bool = False) -> bool:
    """NBA slate (Scalpy). Cached odds between budgeted pulls, like MLB."""
    args = ["nba_build.py", _dt.date.today().isoformat(),
            "--out", "web/data/nba.json"]
    if _with_odds():
        args.append("--cached-odds")
    ok, tail = _run_build(args)
    if not quiet:
        print(f"  NBA  slate: {'refreshed' if ok else 'unavailable'}"
              + (f"  ({tail})" if not ok and tail else ""))
    return ok


def refresh_ufc(quiet: bool = False) -> bool:
    """UFC card (Scalpy MMA). Cached odds between budgeted pulls."""
    args = ["ufc_build.py", "--out", "web/data/ufc.json"]
    if _with_odds():
        args.append("--cached-odds")
    ok, tail = _run_build(args)
    if not quiet:
        print(f"  UFC  card: {'refreshed' if ok else 'unavailable'}"
              + (f"  ({tail})" if not ok and tail else ""))
    return ok


def refresh_all(quiet: bool = False) -> None:
    refresh_mlb(quiet=quiet)
    refresh_nfl(quiet=quiet)
    refresh_predmarkets(quiet=quiet)
    refresh_fantasy(quiet=quiet)
    refresh_nba(quiet=quiet)
    refresh_ufc(quiet=quiet)


def _run_maintenance() -> None:
    """Daily chores (results ingest, journal settle, closing-odds harvest).
    First call of each day does the work; the rest are no-ops."""
    try:
        from engine.maintenance import run_if_due
        run_if_due()
    except Exception as exc:  # noqa: BLE001 — chores must never take the site down
        print(f"  ⚠️  daily maintenance failed: {exc}")


def _background_refresher(interval: int) -> None:
    """Keep the served data fresh while the server runs (quiet after startup)."""
    while True:
        time.sleep(interval)
        # Catches the date rolling over while the server runs overnight.
        _run_maintenance()
        refresh_all(quiet=True)


def _reachable(url: str, timeout: int = 6) -> bool:
    import urllib.error
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "gridiron-edge/preflight"})
        urllib.request.urlopen(req, timeout=timeout).read(64)
        return True
    except urllib.error.HTTPError:
        return True   # got an HTTP response (e.g. 401 without a key) = host is reachable
    except Exception:
        return False


def preflight() -> None:
    """Print a readiness checklist — what's live-ready and what still needs a step."""
    ok, warn = "  ✅", "  ⚠️ "
    print("Gridiron Edge — preflight check\n")

    v = sys.version_info
    print(f"{ok if v >= (3, 9) else warn} Python {v.major}.{v.minor}"
          + ("" if v >= (3, 9) else "  → need 3.9+"))

    # Team ratings (needed for moneyline / spread / totals to have an edge).
    try:
        from engine.db import connect
        conn = connect()
        for sport in ("nfl", "mlb"):
            n = conn.execute("SELECT COUNT(*) FROM games WHERE sport=?", (sport,)).fetchone()[0]
            if n:
                print(f"{ok} Team ratings ({sport.upper()}): {n} games ingested")
            else:
                print(f"{warn} Team ratings ({sport.upper()}): none — run "
                      f"`python3 ingest.py {sport}` so game bets have an edge")
        conn.close()
    except Exception as exc:  # noqa: BLE001
        print(f"{warn} Team ratings: could not read the database ({exc})")

    # Odds key (optional — only needed for real book lines).
    if os.environ.get("ODDS_API_KEY"):
        print(f"{ok} ODDS_API_KEY: set — real sportsbook lines will be used")
    else:
        print(f"{warn} ODDS_API_KEY: not set — model/proxy lines only "
              f"(optional; get a free key at the-odds-api.com)")

    # Live data hosts — every feed all six products depend on.
    print("\n  Live data hosts (need to be reachable from this network):")
    hosts = [
        ("MLB scores/lineups", "https://statsapi.mlb.com/api/v1/schedule?sportId=1"),
        ("MLB Statcast (Savant)", "https://baseballsavant.mlb.com/"),
        ("NFL live scores (ESPN)", "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"),
        ("NFL schedules (nflverse)", "https://raw.githubusercontent.com/nflverse/nflverse-data/master/README.md"),
        ("NFL weekly stats/pbp (releases)", "https://github.com/nflverse/nflverse-data/releases"),
        ("NBA schedule/boxscores (CDN)", "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"),
        ("Polymarket markets (Gamma)", "https://gamma-api.polymarket.com/markets?limit=1"),
        ("Polymarket tape (Data API)", "https://data-api.polymarket.com/trades?limit=1"),
        ("Polymarket leaderboard", "https://lb-api.polymarket.com/leaderboard?window=all&limit=1"),
        ("Sleeper (fantasy sync)", "https://api.sleeper.app/v1/state/nfl"),
        ("Sportsbook odds (all sports)", "https://api.the-odds-api.com/v4/sports/"),
        ("Weather (Open-Meteo)", "https://api.open-meteo.com/v1/forecast?latitude=40&longitude=-74&hourly=temperature_2m"),
    ]
    for name, url in hosts:
        up = _reachable(url)
        print(f"{ok if up else warn} {name}: {'reachable' if up else 'blocked/unreachable here'}")

    # Per-product data freshness — what each page is actually serving.
    print("\n  Product data (web/data/*.json — age since last build):")
    import time as _time
    products = [
        ("MLB board", "web/data/mlb_recommendations.json"),
        ("NFL board", "web/data/recommendations.json"),
        ("Record / journal", "web/data/record.json"),
        ("Polymarket intel", "web/data/predmarkets.json"),
        ("Fantasy football", "web/data/fantasy.json"),
        ("NBA (Scalpy)", "web/data/nba.json"),
        ("UFC (Scalpy MMA)", "web/data/ufc.json"),
    ]
    for name, rel in products:
        p = ROOT / rel
        if not p.is_file():
            print(f"{warn} {name}: never built — appears on the first launch")
            continue
        age_min = (_time.time() - p.stat().st_mtime) / 60
        age = (f"{age_min:.0f} min ago" if age_min < 120
               else f"{age_min / 60:.1f} h ago")
        stale = age_min > 180
        print(f"{ok if not stale else warn} {name}: built {age}"
              + ("  → stale; is the launcher running?" if stale else ""))

    # Database inventory — the raw truth every model reads.
    print("\n  Databases:")
    try:
        from engine.db import connect
        conn = connect()
        def _n(sql, args=()):
            try:
                return conn.execute(sql, args).fetchone()[0]
            except Exception:
                return 0
        rows = [
            ("MLB player-game logs", _n("SELECT COUNT(*) FROM player_game_logs WHERE sport='mlb'")),
            ("MLB plate-appearance logs", _n("SELECT COUNT(*) FROM player_game_logs WHERE sport='mlb' AND market='pa'")),
            ("NFL player-game logs", _n("SELECT COUNT(*) FROM player_game_logs WHERE sport='nfl'")),
            ("NFL xFP rows (play-by-play)", _n("SELECT COUNT(*) FROM player_game_logs WHERE sport='nfl' AND market='xfp'")),
            ("NBA player-game logs", _n("SELECT COUNT(*) FROM player_game_logs WHERE sport='nba'")),
            ("Polymarket trades on tape", _n("SELECT COUNT(*) FROM pm_trades")),
            ("Polymarket flags stored", _n("SELECT COUNT(*) FROM pm_flags")),
        ]
        for name, n in rows:
            print(f"{ok if n else warn} {name}: {n:,}"
                  + ("" if n else "  → run the matching ingest (see GUIDE.md)"))
        conn.close()
    except Exception as exc:  # noqa: BLE001
        print(f"{warn} history DB unreadable: {exc}")
    try:
        from engine import ledger
        lconn = ledger.connect()
        open_n = lconn.execute("SELECT COUNT(*) FROM bets WHERE status='open'").fetchone()[0]
        settled = lconn.execute("SELECT COUNT(*) FROM bets WHERE status!='open'").fetchone()[0]
        print(f"{ok} Bet journal: {settled:,} settled, {open_n:,} open")
        lconn.close()
    except Exception as exc:  # noqa: BLE001
        print(f"{warn} ledger unreadable: {exc}")

    # UFC dossiers + backups.
    doss = ROOT / "data" / "ufc_dossiers.json"
    print(f"{ok if doss.is_file() else warn} UFC dossiers: "
          + ("present" if doss.is_file()
             else "not created — copy data/ufc_dossiers.sample.json (no dossier, no bet)"))
    backups = sorted((ROOT / "data" / "backups").glob("backup_*.zip"))
    if backups:
        print(f"{ok} Backups: {len(backups)} kept, newest {backups[-1].name}")
    else:
        print(f"{warn} Backups: none yet — the first weekly backup runs with "
              f"daily maintenance")

    print("\n  When everything above is ✅ (or intentionally skipped), run:  python3 launch.py")


def main() -> None:
    argv = sys.argv[1:]
    if "--reset-budget" in argv:
        from engine.oddsbudget import reset, summary
        reset()
        print("Odds budget reset — the next call will read the new key's real quota.")
        print("  " + summary())
        return
    if "--check" in argv:
        preflight()
        return
    interval = 60      # scores are free; odds are budgeted separately
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

    # Daily chores run in the background so the site is up immediately; the
    # first cycle of each day ingests yesterday's results (catching up to a
    # week if the site wasn't opened), settles the pick journal, and harvests
    # yesterday's closing odds when the budget clearly allows.
    threading.Thread(target=_run_maintenance, daemon=True).start()

    if interval > 0:
        t = threading.Thread(target=_background_refresher, args=(interval,), daemon=True)
        t.start()
        print(f"Auto-refresh every {interval}s (scores free; odds budgeted).")
        try:
            from engine.oddsbudget import summary as _bsum
            if _with_odds():
                print("  " + _bsum())
        except Exception:
            pass

    print(f"\nGridiron Edge running (LIVE data) → http://localhost:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
