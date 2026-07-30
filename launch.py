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


MLB_OUT = "web/data/mlb_recommendations.json"
NFL_OUT = "web/data/recommendations.json"
NBA_OUT = "web/data/nba.json"


def _slate_games(path: str) -> int:
    """Real game count on a built board (0 when missing/unreadable)."""
    try:
        with open(path) as fh:
            return len(json.load(fh).get("games", []))
    except Exception:
        return 0


def _games_on_slate(path: str) -> int:
    """How many games the last build found — the per-refresh odds cost."""
    try:
        with open(path) as fh:
            return max(1, len(json.load(fh).get("games", [])))
    except Exception:
        return 10


def _budget_share() -> float:
    """This sport's slice of the daily odds allowance: one share per LIVE
    slate. October runs three at once (MLB playoffs, NFL, NBA) — without
    the split they'd jointly plan to spend the month several times over."""
    live = sum(1 for p in (MLB_OUT, NFL_OUT, NBA_OUT) if _slate_games(p) > 0)
    return 1.0 / max(1, live)


def _slate_kickoffs(path: str) -> list:
    """Kickoff epochs from the last build — what tells the pacer WHEN the
    day's credits are worth spending. Unparseable or absent times simply
    drop out; an empty list means the pacer behaves time-blind, as before."""
    out = []
    try:
        with open(path) as fh:
            games = json.load(fh).get("games", [])
        for g in games:
            k = g.get("kickoff") or ""
            if "T" not in k:
                continue                     # "HH:MM" NFL style — no date, skip
            try:
                out.append(_dt.datetime.fromisoformat(
                    k.replace("Z", "+00:00")).timestamp())
            except ValueError:
                continue
    except Exception:
        return []
    return out


def _odds_affordable(out_path: str, quiet: bool, sport: str | None = None) -> bool:
    """Decide whether this refresh can afford to re-pull odds.

    Scores are free and always refresh; odds are metered, so they only ride
    along when the budget allows. This is what keeps live tracking from
    silently burning a month's quota in an evening.
    """
    if not _with_odds():
        return False
    try:
        from engine.oddsbudget import should_refresh
    except Exception:
        return True
    ok, reason = should_refresh(_games_on_slate(out_path) + 1,
                                kickoffs=_slate_kickoffs(out_path),
                                sport=sport, share=_budget_share())
    if not quiet:
        print(f"       {reason}")
    # NOTE: the refresh clock is NOT stamped here. Authorization is not a
    # pull — _finish_paid_pull stamps it only once the API actually
    # answered, so a network blip can't burn the day's one sparse pull.
    return ok


def _paid_pull_baseline() -> str:
    """The quota timestamp before a paid attempt — advancing past this is
    the proof the API answered."""
    try:
        from engine.oddsbudget import load as _bload
        return _bload().last_seen_iso
    except Exception:
        return ""


def _finish_paid_pull(spend: bool, before_seen: str, ok: bool, tail: str,
                      label: str, sport: str | None = None) -> None:
    """Confirm (or defer) an authorized paid pull after the build ran.

    Landed → the refresh clock stamps now. Didn't land → a short retry
    cooldown, and the failure is printed EVEN IN QUIET MODE: the old flow
    stamped the clock at authorization time and said nothing, so a failed
    window pull silently stranded the board on stale prices for 12h."""
    if not spend:
        return
    try:
        from engine.oddsbudget import paid_pull_result, FAILED_PULL_RETRY_S
        landed = paid_pull_result(before_seen, sport=sport)
    except Exception:
        return
    if not landed:
        print(f"  ⚠️  {label}: paid odds pull authorized but the API never "
              f"answered (build {'ok' if ok else 'failed'}"
              + (f": {tail}" if tail else "")
              + f") — retrying in ~{FAILED_PULL_RETRY_S // 60} min")


def _slate_date() -> str:
    """The BASEBALL day, which rolls at 5 AM local — not midnight.

    West-coast games run past 12:00, and flipping the board on the
    calendar tick yanked still-live bets off the Live tab in the 7th
    inning. Until 5 AM the slate (board, tracker, journal date) stays on
    the night being played; results ingest and settling use the real
    calendar independently."""
    return (_dt.datetime.now() - _dt.timedelta(hours=5)).date().isoformat()


def refresh_mlb(quiet: bool = False) -> bool:
    """Build today's MLB slate into web/data/mlb_recommendations.json."""
    date = _slate_date()
    out = MLB_OUT
    args = ["mlb_build.py", date, "--out", out]
    # games>0: an empty offseason slate never spends a paid pull. The first
    # build of a season runs cached, writes the games, and the next cycle
    # (60s later) is eligible — a one-cycle bootstrap, not a gap.
    spend = _slate_games(out) > 0 and _odds_affordable(out, quiet, sport="mlb")
    before_seen = _paid_pull_baseline() if spend else ""
    if spend:
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
    _finish_paid_pull(spend, before_seen, ok, tail, "MLB", sport="mlb")
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
    out = NFL_OUT
    args = ["nfl_build.py", str(season), str(week), "--out", out]
    spend = _slate_games(out) > 0 and _odds_affordable(out, quiet, sport="nfl")
    before_seen = _paid_pull_baseline() if spend else ""
    if spend:
        args.append("--odds")
        if quiet:
            args.append("--active-odds")
    elif _with_odds():
        args.append("--cached-odds")   # keep last paid prices; never overwrite with proxies
    ok, tail = _run_build(args)
    _finish_paid_pull(spend, before_seen, ok, tail, "NFL", sport="nfl")
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
    """NBA slate (Scalpy) — a full member of the paid-pull rotation.

    It was cached-only for its first season scaffold, which meant the
    board could never see a real price: nothing ever seeded the cache.
    Now it paces on its own clock like MLB/NFL, holding its pull for its
    own pre-game window. The games>0 gate keeps the offseason free."""
    args = ["nba_build.py", _slate_date(), "--out", NBA_OUT]
    spend = _slate_games(NBA_OUT) > 0 and _odds_affordable(NBA_OUT, quiet,
                                                           sport="nba")
    before_seen = _paid_pull_baseline() if spend else ""
    if spend:
        args.append("--odds")
    elif _with_odds():
        args.append("--cached-odds")
    ok, tail = _run_build(args)
    _finish_paid_pull(spend, before_seen, ok, tail, "NBA", sport="nba")
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


def _run_autosettle() -> None:
    """Grade tonight's picks as the games finish, without being asked.

    The daily chores only reach yesterday and only fire once per calendar
    day, so before this every night's board stayed "open" until the next
    morning. This throttles itself to every 15 minutes and is a no-op when
    nothing recent is open, so it is cheap to call on every cycle."""
    try:
        from engine.maintenance import settle_open
        settle_open()
    except Exception as exc:  # noqa: BLE001 — chores must never take the site down
        print(f"  ⚠️  auto-settle failed: {exc}")


def _background_refresher(interval: int) -> None:
    """Keep the served data fresh while the server runs (quiet after startup)."""
    while True:
        time.sleep(interval)
        # Catches the date rolling over while the server runs overnight.
        _run_maintenance()
        # Closes out tonight's games as they end, rather than tomorrow.
        _run_autosettle()
        refresh_all(quiet=True)


# Every page the site serves, and the container whose text proves it
# actually rendered. A page can fetch its data fine and still throw while
# drawing it — the failure that leaves a blank panel and no clue anywhere.
SWEEP_VIEWS = [
    ("MLB Recommended", "?sport=mlb#recommended", "#view-recommended"),
    ("MLB Edge Board", "?sport=mlb#edge", "#edge-board"),
    ("MLB Scanner", "?sport=mlb#scanner", "#scanner-body"),
    ("MLB Long Shots", "?sport=mlb#longshots", "#view-longshots"),
    ("MLB Trending", "?sport=mlb#trending", "#trending"),
    ("MLB Players", "?sport=mlb#players", "#players"),
    ("Record", "?sport=mlb#record", "#record-body"),
    ("NFL Recommended", "?sport=nfl#recommended", "#view-recommended"),
    ("Polymarket", "?sport=mlb#intel", "#intel-body"),
    ("Fantasy", "?sport=mlb#fantasy", "#fantasy-body"),
    ("NBA Recommended", "?sport=nba#recommended", "#view-recommended"),
    ("NBA Players", "?sport=nba#players", "#players"),
    ("UFC", "?sport=mlb#ufc", "#ufc-body"),
    ("Why Us", "?sport=mlb#why", "#why-body"),
]

_SWEEP_JS = r"""
import { chromium } from 'playwright';
const VIEWS = %s;
const PORT = process.argv[2];
const b = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
for (const [name, hash, sel] of VIEWS) {
  const p = await b.newPage({ viewport: { width: 1280, height: 1000 } });
  const errs = [];
  p.on('pageerror', e => errs.push('crash: ' + e.message));
  p.on('console', m => { const t = m.text();
    if (m.type() === 'error' && !/404|Failed to load resource/.test(t)) errs.push('console: ' + t.slice(0,110)); });
  let txt = '';
  try {
    await p.goto(`http://127.0.0.1:${PORT}/${hash}`, { waitUntil: 'domcontentloaded', timeout: 15000 });
    await p.waitForTimeout(1200);
    txt = (await p.locator(sel).first().innerText()).replace(/\s+/g, ' ').trim();
  } catch (e) { errs.push('render: ' + String(e).slice(0, 90)); }
  console.log(JSON.stringify({ name, chars: txt.length, errs }));
  await p.close();
}
await b.close();
"""


def _browser_sweep(ok: str, warn: str, bad: str) -> None:
    """Render every page in a headless browser and report JS errors.

    Reading the code has repeatedly missed what looking at the page found
    — a phantom arbitrage on the Scanner, a parlay calculator reporting
    zero cost. This is optional: it needs Node and Playwright, and skips
    with instructions when they aren't installed."""
    import json as _json
    import tempfile
    try:
        have = subprocess.run(
            ["node", "-e", "import('playwright').then(()=>0,()=>process.exit(1))"],
            capture_output=True, cwd=str(ROOT), timeout=30)
        missing = have.returncode != 0
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        # Node isn't installed at all — the common case, and it must not
        # take the whole checklist down with it.
        missing = True
    if missing:
        print("\n  Page render sweep: skipped (optional).")
        print("    Catches JavaScript errors no data check can see. To enable:")
        print("      npm install playwright && npx playwright install chromium")
        return

    print("\n  Page render sweep (headless browser):")
    port = 8973
    server = None
    try:
        # The sweep's own server must not narrate every asset fetch into
        # the middle of the checklist.
        class _Quiet(Handler):
            def log_message(self, *a, **kw):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", port), _Quiet)
        server.live_mode = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False,
                                         dir=str(ROOT)) as fh:
            fh.write(_SWEEP_JS % _json.dumps(SWEEP_VIEWS))
            script = fh.name
        proc = subprocess.run(["node", script, str(port)], cwd=str(ROOT),
                              capture_output=True, text=True, timeout=180)
        Path(script).unlink(missing_ok=True)
        seen = 0
        for line in proc.stdout.splitlines():
            try:
                r = _json.loads(line)
            except ValueError:
                continue
            seen += 1
            if r["errs"]:
                print(f"{bad} {r['name']}: {r['errs'][0]}")
            elif r["chars"] < 25:
                print(f"{warn} {r['name']}: rendered almost nothing "
                      f"({r['chars']} chars) — check the page")
            else:
                print(f"{ok} {r['name']}: rendered ({r['chars']:,} chars)")
        if not seen:
            print(f"{warn} sweep produced no output: "
                  f"{(proc.stderr or '').strip().splitlines()[-1:] or ''}")
    except Exception as exc:  # noqa: BLE001 — a check must never crash
        print(f"{warn} Page render sweep failed: {exc}")
    finally:
        if server is not None:
            server.shutdown()


def _reachable(url: str, timeout: int = 6, ua: str = "gridiron-edge/preflight") -> bool:
    import urllib.error
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"User-Agent": ua})
        urllib.request.urlopen(req, timeout=timeout).read(64)
        return True
    except urllib.error.HTTPError:
        return True   # got an HTTP response (e.g. 401 without a key) = host is reachable
    except Exception:
        return False


def preflight() -> None:
    """Print a readiness checklist — what's live-ready and what still needs a step."""
    ok, warn, bad = "  ✅", "  ⚠️ ", "  ❌"
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
        ("UFC fighter data (ESPN MMA)", "https://site.web.api.espn.com/apis/search/v2?query=jones&limit=1"),
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
    # Products that are legitimately dark part of the year — a missing or
    # old file then is the calendar working, not a fault to chase.
    import datetime as _dtm
    _month = _dtm.date.today().month
    seasonal = {}
    if 3 <= _month <= 8:
        seasonal["NFL board"] = "offseason — sample fallback active, live board returns in September"
    if 7 <= _month <= 9:
        seasonal["NBA (Scalpy)"] = "offseason — live board returns when the schedule posts in October"
    for name, rel in products:
        p = ROOT / rel
        note = seasonal.get(name)
        if not p.is_file():
            if note:
                print(f"{ok} {name}: not built — {note}")
            else:
                print(f"{warn} {name}: never built — appears on the first launch")
            continue
        age_min = (_time.time() - p.stat().st_mtime) / 60
        age = (f"{age_min:.0f} min ago" if age_min < 120
               else f"{age_min / 60:.1f} h ago")
        stale = age_min > 180
        if stale and note:
            print(f"{ok} {name}: built {age} — {note}")
        else:
            print(f"{ok if not stale else warn} {name}: built {age}"
                  + ("  → stale; is the launcher running?" if stale else ""))

    # Every board the site serves must be parseable and carry the keys the
    # page reads. A truncated or half-written JSON renders as a blank panel
    # with no error anywhere — the failure mode hardest to notice by eye.
    print("\n  Page data contracts:")
    import json as _json
    contracts = [
        ("MLB board", "web/data/mlb_recommendations.json",
         ("recommendations", "counts")),
        ("NFL board", "web/data/recommendations.json",
         ("recommendations", "counts")),
        ("Record", "web/data/record.json", ("overall", "recent")),
        ("Polymarket", "web/data/predmarkets.json", ()),
        ("Fantasy", "web/data/fantasy.json", ()),
        ("NBA", "web/data/nba.json", ()),
        ("UFC", "web/data/ufc.json", ()),
    ]
    for name, rel, keys in contracts:
        p = ROOT / rel
        if not p.is_file():
            continue                      # freshness section already said so
        try:
            data = _json.loads(p.read_text())
        except Exception as exc:  # noqa: BLE001
            print(f"{bad} {name}: JSON is corrupt ({exc}) — the page will "
                  f"render blank. Delete it and let the launcher rebuild.")
            continue
        missing = [k for k in keys if k not in data]
        if missing:
            print(f"{warn} {name}: missing key(s) {', '.join(missing)} — "
                  f"the page may render empty")
        else:
            extra = ""
            recs = data.get("recommendations")
            if isinstance(recs, list):
                scan = data.get("market_scan") or {}
                st = scan.get("stale") or []
                total = (st[0].get("total_found") if st else 0) or len(st)
                extra = f" · {len(recs)} props"
                if st:
                    extra += (f", {len(st)} stale-line flag(s)"
                              + (f" shown of {total} found" if total > len(st)
                                 else ""))
                    if len(st) == total and total > 50:
                        extra += "  ← rebuild: pre-dedupe board"
            print(f"{ok} {name}: valid{extra}")

    _browser_sweep(ok, warn, bad)

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
        import datetime as _dt
        from engine import ledger
        lconn = ledger.connect()
        open_n = lconn.execute("SELECT COUNT(*) FROM bets WHERE status='open'").fetchone()[0]
        settled = lconn.execute("SELECT COUNT(*) FROM bets "
                                "WHERE status IN ('won','lost','push')").fetchone()[0]
        void_n = lconn.execute("SELECT COUNT(*) FROM bets WHERE status='void'").fetchone()[0]
        print(f"{ok} Bet journal: {settled:,} settled, {open_n:,} open"
              + (f", {void_n:,} void (player never appeared — zero P&L)" if void_n else ""))
        # "70 open" is never the useful sentence. Tonight's picks are
        # supposed to be open; anything from a finished day is a symptom,
        # and the two look identical in a single total. Break it down by
        # slate date, and for each stale day say whether the results are
        # even in the history DB — that separates "the games were never
        # ingested" from "they were, but nothing matched", which are
        # completely different problems with different fixes.
        today = _dt.date.today().isoformat()
        hconn = None
        try:
            from engine import db as _hdb
            hconn = _hdb.connect()
        except Exception:
            pass
        def _games(d: str) -> tuple[int, int]:
            """(final, total) games ingested for a slate date."""
            if hconn is None:
                return (0, 0)
            try:
                r = hconn.execute(
                    "SELECT COUNT(*), SUM(CASE WHEN home_score IS NOT NULL "
                    "THEN 1 ELSE 0 END) FROM games WHERE sport='mlb' AND period=?",
                    (d,)).fetchone()
                return (int(r[1] or 0), int(r[0] or 0))
            except Exception:
                return (0, 0)

        for day in ledger.open_by_day(lconn, today)[:8]:
            parts = ", ".join(f"{n} {c}" for c, n in sorted(day["counts"].items()))
            if "-W" in (day["date"] or ""):
                # NFL journals under week labels, not ISO days — the MLB
                # per-date ingest queries below would misread them as
                # "results never ingested".
                print(f"{ok}   {day['date']}: {parts} — NFL week; grades "
                      f"daily in season as the weekly stats post")
                continue
            if not day["stale"]:
                # "Settles as games end" is only reassuring if you know
                # whether the games have ended. Say it outright, so an
                # evening with picks still open is obviously normal and a
                # finished slate with picks still open obviously isn't.
                fin, tot = _games(day["date"])
                if tot and fin >= tot:
                    print(f"{warn}   {day['date']}: {parts} — all {tot} game(s) "
                          f"are final but these are still open. Run: "
                          f"python3 launch.py --settle {day['date']}")
                elif tot:
                    print(f"{ok}   {day['date']}: {parts} — today's board, "
                          f"{fin}/{tot} game(s) final so far; the rest settle "
                          f"as they end")
                else:
                    print(f"{ok}   {day['date']}: {parts} — today's board, "
                          f"settles as games end")
                continue
            # A stale day can be in three states, and the first two used to
            # be conflated: SOME log rows existed (an evening settle caught
            # the early games), so the check said "ingested, the rest are
            # harmless scratches" about a night the launcher simply wasn't
            # up to finish. Count final GAMES, not log rows — partial is
            # the common case and it is not harmless, just unfinished.
            logs = 0
            if hconn is not None:
                try:
                    logs = hconn.execute(
                        "SELECT COUNT(*) FROM player_game_logs WHERE period=?",
                        (day["date"],)).fetchone()[0]
                except Exception:
                    logs = -1
            fin, tot = _games(day["date"])
            if logs == 0 and tot == 0:
                print(f"{warn}   {day['date']}: {parts} — no results ingested "
                      f"for that date. Run: python3 launch.py --settle {day['date']}")
            elif not tot or fin < tot:
                have = f"{fin}/{tot} game(s) final in the DB" if tot else \
                       f"only {logs:,} log rows stored"
                print(f"{warn}   {day['date']}: {parts} — results only PARTIALLY "
                      f"ingested ({have}). Start the launcher (auto-settle "
                      f"catches up on launch) or run: "
                      f"python3 launch.py --settle {day['date']}")
            else:
                print(f"{warn}   {day['date']}: {parts} — all {tot} game(s) are "
                      f"final but these players never appeared (projected "
                      f"lineup that sat, late scratch). The next settle pass "
                      f"VOIDS them — the book voids these bets too.")
        if hconn is not None:
            hconn.close()
        lconn.close()
    except Exception as exc:  # noqa: BLE001
        print(f"{warn} ledger unreadable: {exc}")

    # Auto-settle heartbeat: proves the loop is actually running.
    try:
        import datetime as _dt
        import json as _json
        st = _json.loads((ROOT / "data" / "cache" / "maintenance.json").read_text())
        ts = st.get("last_settle_ts")
        if ts:
            mins = (_dt.datetime.now().timestamp() - float(ts)) / 60
            print(f"{ok} Auto-settle: last ran {mins:.0f} min ago "
                  f"(every 15 min while the launcher is up)")
        else:
            print(f"{warn} Auto-settle: hasn't run yet — it starts the next "
                  f"time you run `python3 launch.py`")
    except Exception:
        print(f"{warn} Auto-settle: no record yet — it starts the next time "
              f"you run `python3 launch.py`")

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


def why_empty(sport: str = "mlb", min_conf: float = 6.0,
              min_edge: float = 0.02, max_juice: int = -350) -> None:
    """Explain an empty board: which gate is actually filtering everything.

    Reads the board the site is already serving and walks every prop
    through the four independent gates a recommendation must clear, so
    "0 recommended" stops being a mystery and becomes a number you can
    point at."""
    import json as _json
    from engine.betting import favourite_surcharge, net_edge
    rel = ("web/data/mlb_recommendations.json" if sport == "mlb"
           else "web/data/recommendations.json")
    p = ROOT / rel
    if not p.is_file():
        print(f"No board built yet at {rel} — start the launcher first.")
        return
    recs = _json.loads(p.read_text()).get("recommendations", [])
    if not recs:
        print(f"{rel} has no analyzed props at all.")
        return

    real = [r for r in recs if r.get("has_market") is not False]
    print(f"{sport.upper()} board: {len(recs)} analyzed, {len(real)} with a real price\n")

    rows = []
    for r in real:
        odds = int(r.get("odds") or -110)
        hit = float(r.get("hit_prob") or 0)
        rows.append({
            "label": f"{r.get('player','?')} {r.get('side','')} {r.get('line','')} "
                     f"{r.get('market','')}",
            "odds": odds, "net": net_edge(hit, odds),
            "need": 0.003 + favourite_surcharge(odds),
            "edge": float(r.get("edge") or 0),
            "conf": float(r.get("confidence") or 0),
            "grade": r.get("grade", "Pass"),
            "stake": float(r.get("stake_units") or 0),
            # A pre-game model cannot price a game already in progress —
            # every prop on a started game is blocked no matter how good
            # the number looks.
            "started": any("already started" in w
                           for w in (r.get("warnings") or [])),
        })
    started_n = sum(1 for x in rows if x["started"])
    if started_n:
        print(f"⏱  {started_n} / {len(rows)} props are on games that have "
              f"ALREADY STARTED — blocked regardless of edge.\n")

    from engine.betting import MARKET_SHRINK, MAX_CREDIBLE_EDGE
    # A prop whose TEMPERED edge exceeds this was, before tempering, a
    # disagreement bigger than MAX_CREDIBLE_EDGE — treated as bad data,
    # not alpha, and graded Pass regardless of everything else.
    ceiling = MAX_CREDIBLE_EDGE * MARKET_SHRINK
    grades: dict[str, int] = {}
    for x in rows:
        grades[x["grade"]] = grades.get(x["grade"], 0) + 1
    print("Grades the engine actually assigned:")
    for g, n in sorted(grades.items(), key=lambda kv: -kv[1]):
        print(f"  {n:>5}  {g}")
    print(f"\nCredibility ceiling: any edge above {ceiling:.1%} is graded Pass "
          f"as bad data\n  {sum(1 for x in rows if x['edge'] > ceiling)} / "
          f"{len(rows)} props exceed it\n")

    gates = [
        ("game hasn't started yet", lambda x: not x["started"]),
        ("engine graded it (grade ≠ Pass)", lambda x: x["grade"] != "Pass"),
        ("beats the price at all (net edge > 0)", lambda x: x["net"] > 0),
        ("clears the graded bar (net ≥ 0.3pt + chalk surcharge)",
         lambda x: x["net"] >= x["need"]),
        (f"credible (edge ≤ {ceiling:.0%})", lambda x: x["edge"] <= ceiling),
        (f"confidence ≥ {min_conf}", lambda x: x["conf"] >= min_conf),
        (f"edge-vs-fair ≥ {min_edge:.0%} (slider)", lambda x: x["edge"] >= min_edge),
        (f"price ≥ {max_juice} (slider)", lambda x: x["odds"] >= max_juice),
    ]
    print("Each gate on its own:")
    for name, fn in gates:
        print(f"  {sum(1 for x in rows if fn(x)):>5} / {len(rows)}   {name}")
    print("\nCumulative (a pick must clear every one):")
    surviving = rows
    for name, fn in gates:
        surviving = [x for x in surviving if fn(x)]
        print(f"  {len(surviving):>5} left after: {name}")

    if surviving:
        print(f"\n{len(surviving)} prop(s) SHOULD be recommended — if the board "
              f"shows none, that's a bug worth reporting.")
    else:
        # Name the gate that eliminated the most survivors — the real cause.
        worst, worst_n = None, -1
        for name, fn in gates:
            pool = rows
            for n2, f2 in gates:
                if n2 == name:
                    continue
                pool = [x for x in pool if f2(x)]
            killed = len(pool)
            if killed > worst_n:
                worst, worst_n = name, killed
        print(f"\nBinding gate: “{worst}” — {worst_n} prop(s) clear everything "
              f"else and die there.")

    def show(title, items):
        print(f"\n{title}")
        if not items:
            print("  (none)")
            return
        for x in items:
            short = (x["label"][:44] + "…") if len(x["label"]) > 45 else x["label"]
            why = "" if x["edge"] <= ceiling else "  ← edge too big to believe"
            print(f"  {short:<46} {x['odds']:>5}  net {x['net']*100:+6.2f}pt  "
                  f"need {x['need']*100:5.2f}pt  conf {x['conf']:4.1f}  "
                  f"edge {x['edge']*100:5.2f}%  {x['grade']}{why}")

    # The band that matters: beats its price AND is believable. If this is
    # empty the board is empty for a real reason, not a filter accident.
    window = [x for x in rows if x["net"] >= x["need"] and x["edge"] <= ceiling
              and not x["started"]]
    window.sort(key=lambda x: -(x["net"] - x["need"]))
    show(f"In the recommendable window — beats the price and stays under the "
         f"{ceiling:.0%} credibility ceiling ({len(window)} total):", window[:10])
    show("Biggest net edges overall (mostly rejected as bad data):",
         sorted(rows, key=lambda x: -(x["net"] - x["need"]))[:5])
    near = [x for x in rows if x["edge"] <= ceiling and x["net"] < x["need"]]
    show("Just missed the price bar (credible, but not enough edge):",
         sorted(near, key=lambda x: -(x["net"] - x["need"]))[:5])


def settle_now(day: str | None = None) -> None:
    """Ingest a day's results and grade the journal against them, now.

    The daily chores only run on the first refresh cycle of a new day, so
    a night's picks normally grade tomorrow morning. This does it on
    demand — run it after the games end to see tonight's board settle,
    and it prints the open/settled counts per bucket either side of the
    run so nothing has to be taken on faith."""
    import datetime as _dt
    day = day or _dt.date.today().isoformat()
    try:
        _dt.date.fromisoformat(day)
    except ValueError:
        print(f"--settle takes a date like 2026-07-26 (got {day!r}).")
        return
    from engine import db, ingest, ledger

    def counts(conn):
        rows = conn.execute(
            "SELECT category, status, COUNT(*) FROM bets GROUP BY category, status")
        return {(r[0], r[1]): r[2] for r in rows}

    lconn = ledger.connect()
    before = counts(lconn)
    print(f"Settling {day} …")
    hconn = db.connect()
    try:
        res = ingest.ingest_mlb_results(hconn, day, day, with_logs=True)
        print(f"  results: {res['games']} game(s), "
              f"{res['player_logs']:,} player log rows")
        for s in res.get("skipped", []):
            print(f"  ⚠️  {s}")
        if not res["games"]:
            print("  (no finished games ingested for that date yet — if "
                  "tonight's games are still in progress, run this again "
                  "after they end)")
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠️  results ingest failed: {exc}")
    n = ledger.settle_from_history(lconn, hconn)
    ledger.export_json(lconn, ROOT / "web" / "data" / "record.json")
    after = counts(lconn)
    print(f"  journal: settled {n} pick(s)")
    for cat in ("main", "longshot"):
        b_open, a_open = before.get((cat, "open"), 0), after.get((cat, "open"), 0)
        graded = sum(v for (c, s), v in after.items()
                     if c == cat and s in ("won", "lost", "push"))
        print(f"  {cat:>8}: open {b_open} → {a_open}   ({graded} graded total)")
    print("Record page updated.")


def _tailscale_ip() -> str | None:
    """The machine's Tailscale address (100.64.0.0/10), when Tailscale is
    installed and up — the URL a phone on the same tailnet can open from
    ANYWHERE, not just home Wi-Fi. See docs/PHONE.md for the setup."""
    import subprocess
    candidates = (
        ["tailscale", "ip", "-4"],
        ["/Applications/Tailscale.app/Contents/MacOS/Tailscale", "ip", "-4"],
    )
    for cmd in candidates:
        try:
            out = subprocess.run(cmd, capture_output=True, text=True,
                                 timeout=3).stdout.strip().splitlines()
            if out and out[0].startswith("100."):
                return out[0].strip()
        except (OSError, subprocess.SubprocessError):
            continue
    return None


def nfl_baseline() -> None:
    """Phase-1 audit: is the ingested base complete enough to price Week 1?

    Checks the layers Week-1 projections stand on — weekly stats, pbp
    aggregates (xFP / roles / EPA / PROE / pace), final scores, and
    harvested closing lines — and says which are thin BEFORE the season
    exposes it. `python3 launch.py --nfl-baseline`.
    """
    from engine import db, teamprofiles
    conn = db.connect()
    row = conn.execute("SELECT MAX(season) FROM player_game_logs "
                       "WHERE sport='nfl'").fetchone()
    season = int(row[0]) if row and row[0] is not None else None
    if season is None:
        print("No NFL data ingested at all — run `python3 ingest.py nfl` first.")
        return
    print(f"NFL baseline audit — season {season}\n")

    def check(label, n, want, unit=""):
        mark = "✅" if n >= want else "⚠️ "
        print(f"  {mark} {label}: {n:,}{unit}" +
              ("" if n >= want else f"  (want ≥ {want:,} — thin)"))

    def market_n(m):
        return conn.execute(
            "SELECT COUNT(*) FROM player_game_logs WHERE sport='nfl' "
            "AND season=? AND market=?", (season, m)).fetchone()[0]

    # Weekly stat layer — what settles bets and feeds projections.
    # Wants calibrated against a COMPLETE ingested season (2025 actuals),
    # set just under observed so "complete" passes and "partial" warns.
    for m, want in (("pass_yds", 500), ("rush_yds", 1500), ("rec_yds", 2400),
                    ("receptions", 4000), ("anytime_td", 1500),
                    ("snap_pct", 6000)):
        check(f"weekly {m} rows", market_n(m), want)
    # pbp layer — measured roles and the new efficiency profiles.
    for m, want in (("xfp", 4000), ("rz_tgt", 4000), ("i5_car", 4000)):
        check(f"pbp {m} rows", market_n(m), want)
    games = conn.execute(
        "SELECT COUNT(*) FROM games WHERE sport='nfl' AND season=? "
        "AND home_score IS NOT NULL", (season,)).fetchone()[0]
    check("final scores", games, 250)
    # The UPCOMING season's schedule — game scripts and Week-1 slates
    # build on it, and openers' lines land here weeks before kickoff.
    upcoming = conn.execute(
        "SELECT COUNT(*) FROM games WHERE sport='nfl' AND season=?",
        (season + 1,)).fetchone()[0]
    if upcoming:
        check(f"{season + 1} schedule rows", upcoming, 272)
        lines = conn.execute(
            "SELECT COUNT(*) FROM games WHERE sport='nfl' AND season=? "
            "AND spread IS NOT NULL AND total IS NOT NULL",
            (season + 1,)).fetchone()[0]
        print(f"  ·  {lines} upcoming game(s) already carry posted lines — "
              "the game-scripts panel runs on these")
    else:
        print(f"  ⚠️  no {season + 1} schedule ingested — run "
              "`python3 ingest.py nfl`")
    closes = conn.execute(
        "SELECT COUNT(*) FROM odds_history WHERE sport='nfl'").fetchone()[0]
    if closes:
        check("harvested odds snapshots", closes, 1000)
    else:
        # Not a Week-1 blocker: the closes harvest accrues from September.
        print("  ·  odds snapshots: none yet — the maintenance harvest "
              "accrues these once NFL lines go live (CLV layer, not a "
              "Week-1 blocker)")

    profs = teamprofiles.season_profiles(conn)
    check("team efficiency profiles (EPA/PROE/pace)", len(profs), 32)
    if profs:
        base = teamprofiles.league_baseline(profs)
        cov = {s: sum(1 for p in profs.values() if p.get(s) is not None)
               for s in ("off_epa", "def_epa", "proe", "pace")}
        print(f"\n  League baseline: EPA/play {base.get('off_epa')} · "
              f"PROE {base.get('proe')} · pace {base.get('pace')}s · "
              f"{base.get('plays_per_game')} plays/g")
        print("  Stat coverage: " + ", ".join(
            f"{s} {n}/{len(profs)}" for s, n in cov.items()))
        if any(n < len(profs) for n in cov.values()):
            print("  ⚠️  EPA/pace gaps — rerun `python3 ingest.py nfl` to "
                  "re-aggregate (the cached pbp file already has the columns).")
        if base.get("proe") is not None and abs(base["proe"]) > 0.5:
            print("  ⚠️  PROE stored in percentage points (pre-fix rows) — "
                  "rerun `python3 ingest.py nfl` to restate as fractions.")
    else:
        print("\n  ⚠️  No team profiles yet — run `python3 ingest.py nfl` "
              "(Tuesday maintenance also refreshes them in season).")


def _lan_ip() -> str | None:
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
    if "--clean-cache" in argv:
        # Corrupt/empty cache files are now treated as misses automatically,
        # but sweeping them keeps the next fetch from paying a needless
        # round-trip — and proves which file was poisoned.
        import json as _json
        from engine.sources.fetch import CACHE_DIR as _CD
        bad, checked = [], 0
        for f in sorted(_CD.glob("*.json")):
            checked += 1
            try:
                _json.loads(f.read_text())
            except Exception:
                bad.append(f)
        for f in bad:
            try:
                f.unlink()
            except OSError:
                pass
        print(f"Cache check: {checked} JSON file(s) scanned, "
              f"{len(bad)} unreadable removed"
              + (": " + ", ".join(f.name for f in bad[:8]) if bad else
                 " — all clean."))
        import time as _t
        from engine.maintenance import (prune_cache, CACHE_KEEP_DAYS,
                                        PRUNABLE_CACHE_PREFIXES)
        # Where the space actually is, so a big number is explainable
        # instead of alarming: grouped by file family, with the age of the
        # oldest member (that's what says when pruning starts helping).
        fams: dict = {}
        total = files = 0
        now = _t.time()
        for f in _CD.iterdir():
            if not f.is_file():
                continue
            st = f.stat()
            total += st.st_size
            files += 1
            fam = next((p for p in PRUNABLE_CACHE_PREFIXES
                        if f.name.startswith(p)), None)
            if fam is None:
                fam = f.name if st.st_size > 5e6 else "other (kept)"
            d = fams.setdefault(fam, [0, 0, 0.0])
            d[0] += 1
            d[1] += st.st_size
            d[2] = max(d[2], (now - st.st_mtime) / 86400)
        print(f"Cache size: {total / 1e6:.1f} MB across {files:,} file(s).")
        for fam, (n_f, size, age) in sorted(fams.items(),
                                            key=lambda kv: -kv[1][1])[:10]:
            prunable = fam in PRUNABLE_CACHE_PREFIXES
            print(f"  {fam:<26} {n_f:>6,} file(s)  {size / 1e6:>7.1f} MB  "
                  f"oldest {age:>4.0f}d  "
                  + ("prunes at 30d" if prunable else "kept always"))
        n, freed = prune_cache(log=lambda m: print(m.strip()))
        if not n:
            print(f"  Nothing older than {CACHE_KEEP_DAYS} days yet — "
                  f"pruning starts as these age out. History, budget state "
                  f"and big downloads are never pruned.")
        return
    if "--data-audit" in argv:
        # "Is my data still there?" answered by counting it, not by
        # promising. Everything below is PERMANENT storage; none of it is
        # reachable by the cache pruner (asserted at the end).
        from pathlib import Path as _P
        from engine import db as _db, ledger as _led, calibrate as _cal
        from engine.sources.fetch import CACHE_DIR as _CD
        h = _db.connect()
        print("PERMANENT DATA — stats, results and journal\n")
        rows = h.execute(
            "SELECT sport, COUNT(*) n, COUNT(DISTINCT season) s, "
            "MIN(period) a, MAX(period) b FROM player_game_logs "
            "GROUP BY sport ORDER BY n DESC").fetchall()
        for r in rows:
            print(f"  {r['sport'].upper():<5} player stats : {r['n']:>9,} rows  "
                  f"{r['s']} season(s)  {r['a']} → {r['b']}")
        for r in h.execute(
                "SELECT sport, COUNT(*) n, SUM(home_score IS NOT NULL) f "
                "FROM games GROUP BY sport ORDER BY n DESC"):
            print(f"  {r['sport'].upper():<5} games        : {r['n']:>9,} "
                  f"({r['f'] or 0:,} with final scores)")
        for tbl, label in (("team_weeks", "team EPA/PROE/pace"),
                           ("odds_history", "harvested odds"),
                           ("game_starters", "starting pitchers"),
                           ("game_umpires", "umpires")):
            try:
                n = h.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                print(f"  {'':<5} {label:<13}: {n:>9,} rows")
            except Exception:
                pass
        c = _led.connect()
        b = c.execute(
            "SELECT COUNT(*) n, SUM(status='open') o, "
            "SUM(status IN ('won','lost','push')) s FROM bets").fetchone()
        print(f"\n  BET JOURNAL       : {b['n']:,} bet(s) — "
              f"{b['s'] or 0:,} settled, {b['o'] or 0:,} open")
        for r in c.execute("SELECT category, COUNT(*) n FROM bets "
                           "GROUP BY category ORDER BY n DESC"):
            print(f"     {r['category']:<16} {r['n']:>7,}")
        print(f"  bankroll          : ${_led.bankroll(c):,.2f}")
        cal = _P(_cal.DEFAULT_PATH)
        print(f"  calibration model : "
              f"{'present' if cal.exists() else 'not fitted yet'}")
        # The guarantee, checked rather than claimed.
        print("\nPRUNE SAFETY")
        cache = _CD.resolve()
        for label, p in (("history DB", _db.DEFAULT_DB),
                         ("ledger DB", _led.DEFAULT_DB),
                         ("calibration", _cal.DEFAULT_PATH)):
            inside = cache in _P(p).resolve().parents
            print(f"  {label:<12} {_P(p).resolve()}  "
                  f"{'⚠️ INSIDE CACHE' if inside else '✅ outside the cache'}")
        print(f"  The pruner only ever looks in {cache} and only deletes "
              f"per-game fetch files there.")
        return
    if "--nfl-baseline" in argv:
        nfl_baseline()
        return
    if "--why-empty" in argv:
        i = argv.index("--why-empty")
        sport = argv[i + 1] if len(argv) > i + 1 and not argv[i + 1].startswith("-") else "mlb"
        why_empty(sport)
        return
    if "--repair-journal" in argv:
        from engine import ledger
        conn = ledger.connect()
        before, before_ls = ledger.performance(conn), ledger.longshot_report(conn)
        moved = ledger.move_longshots_out_of_main(conn)
        after, after_ls = ledger.performance(conn), ledger.longshot_report(conn)
        ledger.export_json(conn, ROOT / "web" / "data" / "record.json")
        print(f"Moved {moved} long-shot row(s) out of the headline record "
              f"(markets: {', '.join(sorted(ledger.LONGSHOT_MARKETS))}).\n")
        print(f"  MAIN record   {before['wins']}-{before['losses']}-{before['pushes']}"
              f" → {after['wins']}-{after['losses']}-{after['pushes']}")
        print(f"    net  {before['net_units']:+.2f}u → {after['net_units']:+.2f}u"
              f"    ROI {before['roi']:+.1%} → {after['roi']:+.1%}")
        print(f"  LONG SHOTS    {before_ls['wins']}-{before_ls['losses']}"
              f" → {after_ls['wins']}-{after_ls['losses']}")
        print(f"    net  {before_ls['net_units']:+.2f}u → {after_ls['net_units']:+.2f}u"
              f"    ROI {before_ls['roi']:+.1%} → {after_ls['roi']:+.1%}")
        print(f"  bankroll restated to ${ledger.bankroll(conn):,.2f}")
        print("\nRecord page updated — the two buckets are now fully separate.")
        return
    if "--resize-unstaked" in argv:
        from engine import ledger
        conn = ledger.connect()
        before = ledger.performance(conn)
        card = ledger.unstaked_scorecard(conn)
        if card.get("n"):
            print(f"The 0.00-unit picks, graded: {card['wins']}-{card['losses']} "
                  f"({card['hit_rate']:.1%} hit rate)")
            print(f"  they needed {card['break_even']:.1%} to break even at the "
                  f"prices offered → {card['edge_pts']:+.2f} points "
                  f"{'ABOVE' if card['edge_pts'] > 0 else 'below'} the line")
            print(f"  flat-stake ROI: {card['roi']:+.1%}"
                  + ("  ← they were genuinely profitable; tell me and I'll "
                     "loosen the thresholds" if card["roi"] > 0 else
                     "  ← they won often but still lost money to the juice"))
        n = ledger.resize_unstaked(conn)
        ledger.export_json(conn, ROOT / "web" / "data" / "record.json")
        after = ledger.performance(conn)
        print(f"Sized {n} previously-unstaked pick(s) at 0.1u (units only, "
              f"no dollars).")
        print(f"  record  {before['wins']}-{before['losses']}-{before['pushes']} "
              f"→ {after['wins']}-{after['losses']}-{after['pushes']}")
        print(f"  net     {before['net_units']:+.2f}u → {after['net_units']:+.2f}u"
              f"   ROI {before['roi']:+.1%} → {after['roi']:+.1%}")
        print("Record page updated.")
        return
    if "--settle" in argv:
        i = argv.index("--settle")
        day = argv[i + 1] if len(argv) > i + 1 and not argv[i + 1].startswith("-") else None
        settle_now(day)
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
    #
    # The startup settle ignores the 15-minute throttle on purpose: opening
    # the site is an explicit "catch me up", and the most common way to
    # arrive here is the morning after a slate, wanting last night graded.
    def _startup_chores() -> None:
        _run_maintenance()
        try:
            from engine.maintenance import settle_open
            settle_open(force=True)
        except Exception as exc:  # noqa: BLE001
            print(f"  ⚠️  auto-settle failed: {exc}")

    threading.Thread(target=_startup_chores, daemon=True).start()

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
    lan = _lan_ip()
    if lan:
        print(f"  On your phone (same Wi-Fi):     → http://{lan}:{port}")
        print("  (If the phone can't connect, macOS may be asking to allow "
              "incoming connections for Python — click Allow.)")
    ts = _tailscale_ip()
    if ts:
        print(f"  On your phone ANYWHERE (Tailscale): → http://{ts}:{port}")
        print("  (Type the http:// part — Safari silently upgrades to https "
              "and fails. Real https:// URL: `tailscale serve --bg "
              f"{port}`, see docs/PHONE.md.)")
    else:
        print("  Away from home? Free setup with Tailscale — see docs/PHONE.md")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
