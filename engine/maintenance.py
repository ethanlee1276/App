"""Daily self-maintenance — the learning loop feeds itself.

The journal/backtest data pipeline needs three chores done every day:

  1. ingest yesterday's completed games (scores + player logs + starters —
     free, from MLB's own API);
  2. settle any open journal picks against those results;
  3. harvest yesterday's closing odds (metered — only when the credit budget
     comfortably allows).

Doing them by hand every day is exactly the kind of manual dependency a
learning engine shouldn't have, so ``launch.py`` calls :func:`run_if_due` in
its background cycle: the first cycle of each calendar day runs the chores
(catching up from each sport's own last stored final — however long the
machine was closed — capped at ``MAX_CATCH_UP_DAYS``), every other cycle
is a no-op. Ingestion is idempotent, so overlap with manual runs is
harmless.

Those chores reach *yesterday*, which is right for ingest and closing odds
but wrong for the journal: it meant tonight's picks stayed "open" until
the next morning even though the games had ended hours earlier, and the
only fix was running ``--settle`` by hand. :func:`settle_open` closes that
gap. It runs on the ordinary refresh cycle, throttled, and grades games as
they finish — so the Record page keeps up with the night on its own.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "cache" / "maintenance.json"

# How far back a catch-up reaches when the DATABASE cannot say where it
# left off (fresh install, no finals stored). When it can, the window is
# derived, not fixed — see _catch_up_start.
CATCH_UP_DAYS = 7
# The derived window's ceiling. Ethan's laptop was closed for eight days in
# August 2026 and the fixed one-week window silently dropped the first of
# them — the exact failure a "catch-up" exists to prevent. Deriving the
# start from the DB heals any gap; the cap keeps a machine that was off for
# a whole off-season from grinding through months of slates on first boot.
MAX_CATCH_UP_DAYS = 45
# Never auto-harvest below this measured remaining quota — daily closes are a
# nice-to-have; live odds for today's picks always come first.
HARVEST_MIN_REMAINING = 3000
# Hard per-day cap on what an auto-harvest may spend.
HARVEST_DAY_BUDGET = 400


def _load_state(path: Path) -> dict:
    # Coerce: a caller passing a plain string used to fall into the bare
    # `except` below (str has no .read_text), get {} back, and so lose the
    # throttle SILENTLY — settle_open would run its full pass on every
    # cycle instead of every fifteen minutes. A path is a path.
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return {}


def _save_state(path: Path, state: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state))


BACKUP_DIR = ROOT / "data" / "backups"
BACKUP_EVERY_DAYS = 7
BACKUP_KEEP = 6
# What a backup protects: the databases (history + ledger — months of
# ingested truth and the bet journal) and the append-only files that can
# NEVER be rebuilt if lost (the line-move snapshots; the UFC dossiers you
# typed by hand). Secrets are deliberately excluded.
#
# accounts.db was added 2026-08-15 and is the most irreplaceable of the
# lot, because it is the only one that holds data belonging to somebody
# other than us: every account, every user's synced bet log and fantasy
# leagues, and (since billing) the customer_id that ties a paying person
# to their subscription. Losing history.db costs a re-ingest; losing this
# costs other people their records and leaves us charging cards we can no
# longer match to accounts. It was omitted at first only because the file
# did not exist when this list was written.
BACKUP_FILES = ("data/history.db", "data/ledger.db", "data/accounts.db",
                "data/cache/line_history.jsonl", "data/ufc_dossiers.json")
#: Directories backed up whole, newest-state, non-recursively. The
#: pre-account profiles are one JSON file per device name, so there is no
#: fixed filename to list.
BACKUP_GLOBS = ("data/profiles/*.json",)


def _maybe_backup(state: dict, today: _dt.date, log,
                  root: Path | None = None,
                  backup_dir: Path | None = None) -> None:
    """Weekly zip of everything irreplaceable. Live SQLite files are copied
    through the sqlite backup API so a mid-write snapshot can't corrupt."""
    last = state.get("last_backup")
    if last:
        try:
            if (today - _dt.date.fromisoformat(last)).days < BACKUP_EVERY_DAYS:
                return
        except ValueError:
            pass
    import sqlite3
    import tempfile
    import zipfile
    root = root or ROOT
    backup_dir = backup_dir or BACKUP_DIR
    backup_dir.mkdir(parents=True, exist_ok=True)
    out = backup_dir / f"backup_{today.isoformat()}.zip"
    wrote = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in BACKUP_FILES:
            src = root / rel
            if not src.exists():
                continue
            if src.suffix == ".db":
                with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
                    tmp_path = Path(tmp.name)
                s = sqlite3.connect(str(src))
                d = sqlite3.connect(str(tmp_path))
                s.backup(d)
                d.close(); s.close()
                zf.write(tmp_path, arcname=rel)
                tmp_path.unlink(missing_ok=True)
            else:
                zf.write(src, arcname=rel)
            wrote += 1
        for pattern in BACKUP_GLOBS:
            head, _, tail = pattern.rpartition("/")
            for src in sorted((root / head).glob(tail)):
                zf.write(src, arcname=f"{head}/{src.name}")
                wrote += 1
    # Prune: keep the newest BACKUP_KEEP.
    zips = sorted(backup_dir.glob("backup_*.zip"))
    for old in zips[:-BACKUP_KEEP]:
        old.unlink(missing_ok=True)
    state["last_backup"] = today.isoformat()
    log(f"  backup: {wrote} file(s) → {out.name} "
        f"({len(list(backup_dir.glob('backup_*.zip')))} kept)")


#: Game-bet journal markets → the Odds API's own market keys. Props
#: resolve through oddshistory.resolve_market_keys; these three are the
#: journal's game-bet vocabulary, which the API spells differently.
_HARVEST_GAME_MARKETS = {"moneyline": "h2h", "spread": "spreads",
                         "total": "totals", "team_total": "totals"}

#: Sports the auto-harvest may spend on. CFB is DELIBERATELY absent: the
#: odds-history parsers key teams through SPORT_CONFIG's map, and CFB's
#: is built at run time from the ESPN feed inside cfb_build — a harvest
#: today would store school names no settle pass can join to bets. The
#: gap and its fix are written down in docs/IDEAS.md.
_HARVEST_SPORTS = ("mlb", "nfl")


def _harvest_targets(day: _dt.date) -> list[tuple[str, str]]:
    """(sport, markets-csv) for each sport that JOURNALED bets on ``day``.

    Driven by the journal rather than a hardcoded sport, because the
    hardcode was the bug: "mlb, total_bases,h2h" meant every NFL bet of
    the season would have settled with no closing line — no CLV, no
    process grade, none of the learning the whole ladder feeds on.
    Harvesting exactly the markets bet keeps the credit spend at the
    floor the CLI's own help text argues for.
    """
    from . import ledger as _led
    out = []
    try:
        conn = _led.connect()
    except Exception:
        return out
    try:
        for sport in _HARVEST_SPORTS:
            rows = [r[0] for r in conn.execute(
                "SELECT DISTINCT market FROM bets WHERE sport=? AND date=?",
                (sport, day.isoformat()))]
            if not rows:
                continue
            markets = sorted({_HARVEST_GAME_MARKETS.get(m, m) for m in rows})
            out.append((sport, ",".join(markets)))
    except Exception:
        return out
    finally:
        conn.close()
    return out


def _maybe_harvest(day: _dt.date, log) -> None:
    """Harvest yesterday's closing odds — only when clearly affordable."""
    if not os.environ.get("ODDS_API_KEY"):
        return
    try:
        from .oddsbudget import load, is_measured
        st = load()
        if not is_measured(st) or st.remaining < HARVEST_MIN_REMAINING:
            have = st.remaining if is_measured(st) else "unknown"
            log(f"  closes: auto-harvest skipped (quota {have}, reserve "
                f"{HARVEST_MIN_REMAINING}) — picks still journal, but prop CLV "
                f"for {day} won't fill in")
            return
    except Exception:
        return
    targets = _harvest_targets(day)
    if not targets:
        return                            # nothing journaled, nothing owed
    for sport, markets in targets:
        cmd = [sys.executable, "harvest_odds.py", sport,
               "--from", day.isoformat(), "--to", day.isoformat(),
               "--markets", markets,
               "--budget", str(HARVEST_DAY_BUDGET), "--yes"]
        try:
            proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True,
                                  text=True, timeout=600)
            lines = (proc.stdout + proc.stderr).strip().splitlines()
            harvested = next(
                (l.strip() for l in lines if l.strip().startswith("Harvested")),
                lines[-1].strip() if lines else "")
            log(f"  closes ({sport}): {harvested}")
        except Exception as exc:  # noqa: BLE001 — must never crash the site
            log(f"  ⚠️  closes ({sport}): auto-harvest failed ({exc})")


# --- Intraday settle --------------------------------------------------------
# The daily chores above only reach *yesterday*, and only fire on the first
# cycle of a new calendar day. That left every night's picks sitting open
# until the following morning: games end at 11pm, the journal still says
# "open", and the Record page is a day behind until someone runs --settle
# by hand. This pass closes that gap — it runs on the ordinary refresh
# cycle and grades games as they finish.
#
# MLB's results API is free and keyless, so the only cost is politeness;
# the throttle exists for that reason, not for a budget.
# Ethan, 2026-08-18: "it should be automatic like every 5 mins scan if
# props have been won or lost". Five minutes it is — the pass is a no-op
# query when nothing recent is open, and the results it pulls are the free
# league feeds, so the shorter clock costs nothing.
SETTLE_EVERY_S = 300             # 5 minutes between intraday passes
# How far back an intraday pass will reach for still-open picks. The daily
# chores handle anything older (and reach CATCH_UP_DAYS), so this only has
# to cover "tonight, and last night if the launcher was closed".
SETTLE_LOOKBACK_DAYS = 3


def _open_bet_days(lconn, today: _dt.date, lookback: int) -> list[str]:
    """Distinct slate dates that still have open picks, newest-relevant
    first. Anything older than the lookback is the daily job's problem."""
    floor = (today - _dt.timedelta(days=lookback - 1)).isoformat()
    rows = lconn.execute(
        "SELECT DISTINCT date FROM bets WHERE status='open' AND date >= ? "
        "AND date <= ? ORDER BY date", (floor, today.isoformat())).fetchall()
    return [r[0] for r in rows if r[0]]


# --- cache hygiene ----------------------------------------------------------
# Per-game / per-date fetch caches. Each is a cheap re-fetch keyed to one
# game, player or day, and once that day is weeks past nothing ever reads it
# again — but the files accumulate forever (a full season of boxscores,
# linescores and game logs runs to thousands).
#
# This is an ALLOWLIST on purpose. The same directory holds state that is
# NOT refetchable — line_history.jsonl (the line-movement record behind
# CLV), depth_snapshots.json (the camp watch's daily depth charts),
# odds_budget.json (credit accounting) — plus expensive downloads
# (pbp_*.csv is ~100MB). A denylist would quietly destroy the next such
# file someone adds; an allowlist can only ever delete what it names.
#: PER-KEY CACHES — one file per game, per date, per market, per mint.
#: These are the ones that grow without a ceiling, and every one of them
#: is free to fetch again.
#:
#: THE LIST WENT STALE, WHICH IS WHY tests/test_cacheclass.py EXISTS.
#: `mlb_pbp_` was missed when it shipped: play-by-play payloads are about
#: 640 KB and a night's starters are ~150 of them, so the cache grew
#: roughly 96 MB a night and `prune_cache` never touched a byte of it.
#: Every other MLB prefix was here; that one was typed nowhere. So were
#: `wnba_box_` (while `nba_box_` was present), every Polymarket prefix,
#: and Rocket Radar's per-mint holder files. A list somebody has to
#: remember to extend is the same failure as a cache version somebody has
#: to remember to bump — so the test now requires every cache filename in
#: the source to appear in THIS tuple or in KEEP_CACHE_PREFIXES, with a
#: reason. Adding a new fetch and no classification fails the suite.
PRUNABLE_CACHE_PREFIXES = (
    "mlb_box_", "mlb_line_", "mlb_live_", "mlb_schedule_", "mlb_teamsched_",
    "mlb_results_", "mlb_tx_", "mlb_log_", "mlb_person_", "mlb_splits_",
    "mlb_pbp_", "mlb_roster_", "mlb_pensched_", "mlb_watchsched_",
    "standings_mlb_",
    "nba_box_", "wnba_box_", "wnba_schedule_",
    "espn_mma_", "espn_nfl_", "espn_injuries_", "espn_cfb_", "meteo_",
    "mma_scoreboard_", "mma_live_", "mma_ev_", "mma_comp_", "mma_cptr_",
    "pm_evt_", "pm_mkt_", "pm_wtrades_", "pm_pnl_", "pm_leaderboard_",
    "nws_pt_", "nws_fc_", "sol_holders_", "sleeper_trend_",
    # College kickoff forecasts (engine/cfb/wx.py): hours-long TTL,
    # keyless refetch, tiny — the same class as meteo_ and nws_*.
    "cfb_wx_",
)

#: DELIBERATELY KEPT, each for a reason that costs something to ignore.
#: The value is why, and the test prints it when a classification is
#: missing — so the next person deciding is deciding, not guessing.
KEEP_CACHE_PREFIXES = {
    "odds_": "paid API credits — refetching spends real quota",
    "savant_": "per pitcher-season, bounded by roster size, and slow to rebuild",
    "pbp_": "nflverse per-SEASON bulk (~100 MB each); bounded, not per-game",
    "pbp_participation_": "nflverse per-season bulk, same",
    "player_stats_": "nflverse per-season bulk, same",
    "snap_counts_": "nflverse per-season bulk, same",
    "depth_charts_": "nflverse per-season bulk, same",
    "roster_": "nflverse per-season bulk, same",
    "injuries_": "nflverse per-season bulk, same",
    "line_": "line_history.jsonl is accumulated history, not a fetch cache",
    "maintenance": "this module's own state",
}
CACHE_KEEP_DAYS = 30


#: Boards whose surface has been retired: nothing builds them any more,
#: and a stale copy sitting on the public path is a page the site still
#: serves while no code refreshes it — frozen scores wearing a live
#: site's masthead. The daily chores delete these from web/data and
#: data/built wherever they linger (the dev tree, the droplet after a
#: deploy). Named files only, same posture as every other allowlist here.
#:
#:   nfl_preseason.json — the preseason section, retired 2026-08-25
#:   (Ethan: "get rid of the pre season section for nfl"). The engine
#:   stays dormant for a future August; the FILE must not.
RETIRED_BOARDS = ("nfl_preseason.json",)


def remove_retired_boards(log=None, root: Path | None = None) -> int:
    """Delete retired boards from the public path and the private copy.

    Returns how many files went. Safe to run any time, safe twice —
    everything it may touch is named in RETIRED_BOARDS and nothing
    rebuilds those, so a second pass finds nothing.
    """
    base = root or (Path(__file__).resolve().parents[1])
    n = 0
    for rel in ("web/data", "data/built"):
        for name in RETIRED_BOARDS:
            p = base / rel / name
            try:
                if p.is_file():
                    p.unlink()
                    n += 1
                    if log:
                        log(f"  retired board removed: {rel}/{name}")
            except OSError:
                continue
    return n


def prune_cache(max_age_days: int = CACHE_KEEP_DAYS, log=None,
                cache_dir: Path | None = None) -> tuple[int, int]:
    """Delete stale per-game/per-date fetch caches. Returns (files, bytes).

    Only files whose names start with a PRUNABLE_CACHE_PREFIXES entry are
    ever touched, and only when older than ``max_age_days``. Everything
    else in the cache — accumulated history, budget state, big downloads —
    is left alone by construction.
    """
    import time as _time
    from .sources.fetch import CACHE_DIR
    root = Path(cache_dir) if cache_dir else CACHE_DIR
    if not root.is_dir():
        return 0, 0
    cutoff = _time.time() - max_age_days * 86400
    n = freed = 0
    for f in root.iterdir():
        if not f.is_file() or not f.name.startswith(PRUNABLE_CACHE_PREFIXES):
            continue
        try:
            st = f.stat()
            if st.st_mtime >= cutoff:
                continue
            f.unlink()
        except OSError:
            continue
        n += 1
        freed += st.st_size
    if n and log:
        log(f"  cache: pruned {n:,} stale fetch file(s), freed "
            f"{freed / 1e6:.1f} MB (kept everything newer than "
            f"{max_age_days} days, and all history/budget state)")
    return n, freed


def ingest_for_open_bets(lconn, hconn, days: list[str], log=print) -> dict:
    """Pull results for every SPORT that has an open pick on these days.

    Both settle paths used to ingest baseball and nothing else, so a WNBA or
    UFC pick could never grade from them: `settle_from_history` compares a
    bet to a stored stat line, and nobody had stored one. The date then kept
    its open pick forever, which is why `--settle all` began at the same
    old date every night, reported zero settled, and did it again tomorrow.

    Each league is pulled only on dates that actually have an open pick in
    it, and each pull is isolated — one league's feed hiccup must not skip
    the next league's ingest, nor the settle that runs after all of them.
    """
    from . import ingest

    res = {"games": 0}
    if _has_open(lconn, "mlb", days):
        try:
            res = ingest.ingest_mlb_results(hconn, days[0], days[-1],
                                            with_logs=True)
        except Exception as exc:  # noqa: BLE001
            log(f"  ⚠️  MLB results ingest skipped ({exc}) — settling on "
                "what's already ingested")
    for league, ingest_day in (("nba", _nba_day), ("wnba", _wnba_day)):
        if ingest_day is None:
            continue
        for d in days:
            if not _has_open(lconn, league, [d]):
                continue
            try:
                ingest_day(hconn, d)
            except Exception:  # noqa: BLE001
                log(f"  ⚠️  {league.upper()} results for {d} unavailable — "
                    f"those picks stay open")
    return res


def _has_open(lconn, sport: str, days: list[str]) -> bool:
    if not days:
        return False
    marks = ",".join("?" * len(days))
    return bool(lconn.execute(
        f"SELECT 1 FROM bets WHERE status='open' AND sport=? "
        f"AND date IN ({marks}) LIMIT 1", (sport, *days)).fetchone())


def _hoops_ingesters():
    """(nba, wnba) day-ingest callables, or None where unavailable.

    Imported through a function so a broken or missing source module
    degrades to "that league does not grade intraday" rather than taking
    the whole settle pass down with it.
    """
    nba = wnba = None
    try:
        from .sources.nbadata import ingest_nba_date as nba
    except Exception:  # noqa: BLE001
        nba = None
    try:
        from .sources import espnhoops as _h

        def wnba(conn, date):
            return _h.ingest_day(conn, date, league="wnba")
    except Exception:  # noqa: BLE001
        wnba = None
    return nba, wnba


_nba_day, _wnba_day = _hoops_ingesters()


def settle_open(log=print, state_path: Path | None = None,
                today: _dt.date | None = None, now: float | None = None,
                force: bool = False) -> int:
    """Grade any open pick whose game has finished. Returns picks settled.

    Safe to call on every refresh cycle: it throttles itself, does nothing
    when the journal has no recent open picks, and never raises — a
    maintenance chore must not be able to take the site down.
    """
    import time as _time
    state_path = state_path or STATE_PATH
    today = today or _dt.date.today()
    now = now if now is not None else _time.time()
    state = _load_state(state_path)
    last = state.get("last_settle_ts")
    if not force and isinstance(last, (int, float)) and now - last < SETTLE_EVERY_S:
        return 0

    settled = 0
    try:
        from . import db, ingest, ledger
        lconn = ledger.connect()
        days = _open_bet_days(lconn, today, SETTLE_LOOKBACK_DAYS)
        if not days:
            # Nothing to do — still stamp the clock so we don't re-check
            # the journal every single cycle.
            state["last_settle_ts"] = now
            _save_state(state_path, state)
            return 0
        hconn = db.connect()
        # One ingest spanning the open days; it is idempotent, and games
        # still in progress simply aren't returned as finished yet.
        #
        # Its OWN try: a fetch hiccup (blocked host, rate limit, a corrupt
        # cache file) must not skip the settle below. Everything already in
        # the history DB can still grade tonight's bets — letting one bad
        # response strand the whole journal is how bets sat open for days.
        # Re-file hoops bets journaled under the other league FIRST — a
        # WNBA pick stored as 'nba' can never meet its results, and the
        # ingest below decides which sports to fetch from the bets' own
        # labels, so relabeling after it wastes a pass.
        try:
            moved = ledger.relabel_cross_league(lconn, hconn)
            if moved:
                log(f"  re-filed {moved} hoops bet(s) under the league "
                    f"that actually played them")
        except Exception as exc:  # noqa: BLE001
            log(f"  ⚠️  league relabel skipped: {exc}")
        # Long-shot markets (home runs, anytime TDs) may NEVER sit in the
        # headline record — the journal gate refuses them at the door, and
        # this sweep re-files any stray that got in some other way, so the
        # main record can only ever describe picks the model stands behind.
        try:
            strays = ledger.move_longshots_out_of_main(lconn)
            if strays:
                log(f"  re-filed {strays} long-shot bet(s) out of the "
                    f"headline record into their own bucket")
        except Exception as exc:  # noqa: BLE001
            log(f"  ⚠️  long-shot re-file skipped: {exc}")
        res = ingest_for_open_bets(lconn, hconn, days, log)
        settled = ledger.settle_from_history(lconn, hconn)
        # Self-healing: any bet ever graded off a partial stat line gets
        # re-graded once the real final number is in.
        fixed = ledger.resettle_mismatches(lconn, hconn)
        if fixed:
            log(f"  ⚠️  corrected {len(fixed)} bet(s) graded off partial "
                "stats: " + "; ".join(
                    f"{f['player']} {f['market']} {f['was']}→{f['now']}"
                    for f in fixed[:5]))
        # Parlay tickets grade off their legs' verdicts in the singles
        # journal — AFTER the settle above, or every ticket finds its legs
        # still open. This used to live only in the manual --settle handler,
        # so tickets journaled nightly and then sat "waiting" until someone
        # happened to run that command by hand. The auto-settle is the thing
        # that actually keeps the journal current; the tickets belong to it.
        parlays_moved = 0
        try:
            from . import parlayledger
            pr = parlayledger.settle(lconn)
            rp = parlayledger.resettle(lconn)
            parlays_moved = pr["settled"] + len(rp["fixed"]) + rp["reopened"]
            if pr["settled"]:
                log(f"  parlays: graded {pr['settled']} ticket(s)")
            if rp["fixed"] or rp["reopened"]:
                log(f"  ⚠️  parlays re-audited: {len(rp['fixed'])} re-graded,"
                    f" {rp['reopened']} reopened with their legs")
        except Exception as exc:  # noqa: BLE001
            log(f"  ⚠️  parlay settle skipped: {exc}")
        # The learning step: every fresh grade re-mines the journal for
        # loss patterns, so a slice that just crossed the evidence bar
        # starts vetoing picks on the very next build — no human runs it.
        if settled or fixed:
            try:
                from . import losspatterns
                lp = losspatterns.refresh(lconn)
                if lp["closed"]:
                    log(f"  loss patterns: {len(lp['closed'])} slice(s) "
                        "self-closed — see the Record page")
            except Exception as exc:  # noqa: BLE001
                log(f"  ⚠️  loss-pattern mining skipped: {exc}")
            # The journal fitters: temperature + player memory for every
            # sport with no deep-history harness (hoops, college, UFC).
            # A sport crosses its 200-bet floor the night it happens.
            try:
                from . import journalfit
                jf = journalfit.refresh(lconn)
                for f in jf["temperatures"]["fitted"]:
                    log(f"  journal fit: {f['key']} temperature "
                        f"T={f['temperature']} on {f['n']} settled bets")
                for f in jf["memory"]["fitted"]:
                    if f["adopted"]:
                        log(f"  journal fit: {f['key']} player memory on "
                            f"({f['players']} corrected)")
            except Exception as exc:  # noqa: BLE001
                log(f"  ⚠️  journal fit skipped: {exc}")
            # The selection haircut: one pooled number per sport, measuring
            # what OUR PICKS are worth rather than what the surface is.
            # Refits every settle pass; un-shifts its own prior work first.
            try:
                from . import selectionfit
                sf = selectionfit.refresh(lconn)
                for name, e in [("pooled", sf["pooled"])] + sorted(
                        sf["sports"].items()):
                    if e.get("applied"):
                        log(f"  selection haircut ({name}): claimed "
                            f"{e['claimed'] * 100:.1f}%, landed "
                            f"{e['landed'] * 100:.1f}% over {e['n']} bets — "
                            f"shift {e['shift']:+.3f} log-odds")
            except Exception as exc:  # noqa: BLE001
                log(f"  ⚠️  selection haircut skipped: {exc}")
            # The hypothesis lab's free step: every stored hypothesis
            # re-earns its status against the grown journal. Arithmetic
            # only — the paid propose step is CLI-invoked, never here.
            try:
                from . import hypotheses
                hs = hypotheses.retest(lconn)
                closed_h = [h for h in hs.get("hypotheses") or []
                            if h.get("action") == "close"]
                if closed_h:
                    log(f"  hypotheses: {len(closed_h)} confirmed "
                        "closure(s) enforcing — see the Record page")
            except Exception as exc:  # noqa: BLE001
                log(f"  ⚠️  hypothesis retest skipped: {exc}")
            # The prose lanes: nightly postmortem + weekly brief. These
            # DO spend (pennies), so they carry their own guards — no
            # key = silent skip, one entry per night/week, and they
            # stand down for the month once the LLM cap is spent. They
            # run before the export so the page ships tonight's column.
            try:
                from . import prose
                prose.nightly(lconn, log)
                prose.weekly(lconn, log)
                # And the lab's paid propose, weekly under the same cap —
                # the one recurring manual step, retired.
                prose.weekly_lab(lconn, log)
            except Exception as exc:  # noqa: BLE001
                log(f"  ⚠️  prose lanes skipped: {exc}")
            # The Lab: replay every walk-forward harness this machine's
            # data supports and publish the result. Weekly on its own
            # clock, CPU only — no API, no spend. It answers the one
            # question the forward record cannot yet, on a thin sample:
            # does the model forecast better than guessing?
            try:
                from . import lab
                lab.run_if_due(hconn=hconn, log=log)
            except Exception as exc:  # noqa: BLE001
                log(f"  ⚠️  backtest lab skipped: {exc}")
        if settled or fixed or parlays_moved:
            ledger.export_json(lconn, ROOT / "web" / "data" / "record.json")
        if settled:
            log(f"  settled {settled} pick(s) from {res['games']} finished "
                f"game(s) ({days[0]}"
                + (f" → {days[-1]}" if days[-1] != days[0] else "") + ")")
    except Exception as exc:  # noqa: BLE001 — never take the site down
        log(f"  ⚠️  auto-settle failed: {exc}")
    state["last_settle_ts"] = now
    _save_state(state_path, state)
    return settled


def _last_result_day(hconn, sport: str) -> _dt.date | None:
    """The newest day this sport has a stored FINAL for, or None.

    The database is the only honest witness to what has been ingested —
    the state file's `last_done` says the chores RAN, not that they
    covered every day, and trusting it is how an eight-day lid-closed
    stretch ended in a hand-typed `--from/--to` backfill."""
    try:
        r = hconn.execute(
            "SELECT MAX(period) FROM games WHERE sport=? "
            "AND home_score IS NOT NULL", (sport,)).fetchone()
        return _dt.date.fromisoformat(str(r[0])) if r and r[0] else None
    except Exception:                                         # noqa: BLE001
        return None


def _catch_up_start(hconn, sport: str, yesterday: _dt.date) -> _dt.date:
    """Where this sport's results ingest resumes: GAP-AWARE, not fixed.

    From the sport's own last stored final (that day is re-read — its late
    games may have finished after the run that stored the early ones), so
    any stretch of downtime heals itself on the next pass, however long it
    was. The old one-week window remains only as the fallback when the DB
    cannot answer, and MAX_CATCH_UP_DAYS caps the reach either way."""
    floor = yesterday - _dt.timedelta(days=CATCH_UP_DAYS - 1)
    cap = yesterday - _dt.timedelta(days=MAX_CATCH_UP_DAYS - 1)
    last = _last_result_day(hconn, sport) if hconn is not None else None
    return max(last or floor, cap)


def run_if_due(force: bool = False, harvest: bool = True, log=print,
               state_path: Path | None = None, today: _dt.date | None = None) -> bool:
    """Run the daily chores if they haven't run yet today.

    Returns True when the chores ran (successfully or not), False when they
    were already done today. A failed results ingest leaves the day unmarked
    so the next cycle retries; everything else is best-effort.
    """
    state_path = state_path or STATE_PATH
    today = today or _dt.date.today()
    state = _load_state(state_path)
    if not force and state.get("last_done") == today.isoformat():
        return False

    yesterday = today - _dt.timedelta(days=1)
    try:
        from . import db as _cdb
        _hconn = _cdb.connect()
    except Exception:                                         # noqa: BLE001
        _hconn = None
    start = _catch_up_start(_hconn, "mlb", yesterday)
    log(f"Daily maintenance: results {start} → {yesterday}, journal settle"
        + (", closing odds" if harvest else "") + "…")

    ingest_ok = True
    if start <= yesterday:
        try:
            from . import db, ingest
            conn = db.connect()
            res = ingest.ingest_mlb_results(conn, start.isoformat(),
                                            yesterday.isoformat(), with_logs=True)
            log(f"  results: {res['games']} games, "
                f"{res['player_logs']:,} log rows processed")
            for s in res.get("skipped", []):
                log(f"  ⚠️  {s}")
            ingest_ok = res["games"] > 0 or not res.get("skipped")
        except Exception as exc:  # noqa: BLE001
            ingest_ok = False
            log(f"  ⚠️  results ingest failed: {exc}")

    try:
        from . import db, ledger
        lconn = ledger.connect()
        hconn = db.connect()
        n = ledger.settle_from_history(lconn, hconn)
        fixed = ledger.resettle_mismatches(lconn, hconn)
        if fixed:
            log(f"  ⚠️  corrected {len(fixed)} bet(s) graded off partial stats: "
                + "; ".join(f"{f['player']} {f['market']} {f['was']}→{f['now']}"
                            for f in fixed[:5]))
        ledger.export_json(lconn, ROOT / "web" / "data" / "record.json")
        log(f"  journal: settled {n} pick(s)" if n else "  journal: nothing to settle")
    except Exception as exc:  # noqa: BLE001
        log(f"  ⚠️  journal settle failed: {exc}")

    # NFL schedule refresh: one cached CSV, once a day. Books post next
    # season's lines all summer and nflverse updates the coach stamps as
    # staffs change — this is what keeps the game scripts and the
    # offseason panel current without anyone re-running ingest by hand.
    try:
        from . import db as _db
        from .ingest import nfl_game_rows
        from .sources.nflverse import load_schedules
        yr = today.year if today.month >= 3 else today.year - 1
        rows = nfl_game_rows(load_schedules(), {yr, yr + 1})
        if rows:
            n = _db.upsert_games(_db.connect(), rows)
            log(f"  nfl schedule: {n} row(s) refreshed (seasons {yr}-{yr + 1})")
    except Exception as exc:  # noqa: BLE001
        log(f"  ⚠️  nfl schedule refresh failed: {exc}")

    # NBA results — final boxscores from the free CDN, one date at a time
    # over its OWN derived window (an NBA gap and an MLB gap are different
    # sizes). This is what settles NBA picks and the NBA stale-line flags.
    # Skipped July–September: no games exist.
    nstart = _catch_up_start(_hconn, "nba", yesterday)
    if (today.month >= 10 or today.month <= 6) and nstart <= yesterday:
        try:
            from . import db as _ndb
            from .sources.nbadata import ingest_nba_date
            nconn = _ndb.connect()
            tot_g = tot_l = 0
            d = nstart
            while d <= yesterday:
                res = ingest_nba_date(nconn, d.isoformat())
                tot_g += res["games"]
                tot_l += res["player_logs"]
                if any("schedule" in s for s in res.get("skipped", [])):
                    # The schedule host is down — every later date would
                    # fail identically, so say it once and stop.
                    log(f"  ⚠️  {res['skipped'][0]}")
                    break
                d += _dt.timedelta(days=1)
            if tot_g or tot_l:
                log(f"  nba results: {tot_g} game(s), {tot_l:,} log rows")
        except Exception as exc:  # noqa: BLE001
            log(f"  ⚠️  nba results ingest failed: {exc}")

    # WNBA results — the block that never existed. Until 2026-08-18 a WNBA
    # day was ingested only when an open bet pointed at it (settle_open's
    # ingest_for_open_bets), so quiet stretches left holes in the history
    # that later surfaced as missing faces and thin projections. Same
    # shape as the NBA block, in the WNBA's own season window (May–Oct).
    if 5 <= today.month <= 10 and _wnba_day is not None:
        wstart = _catch_up_start(_hconn, "wnba", yesterday)
        if wstart <= yesterday:
            try:
                from . import db as _wdb
                wconn = _wdb.connect()
                tot_g = tot_l = 0
                d = wstart
                while d <= yesterday:
                    res = _wnba_day(wconn, d.isoformat())
                    tot_g += res["games"]
                    tot_l += res["player_logs"]
                    if any("scoreboard" in s for s in res.get("skipped", [])):
                        log(f"  ⚠️  {res['skipped'][0]}")
                        break
                    d += _dt.timedelta(days=1)
                if tot_g or tot_l:
                    log(f"  wnba results: {tot_g} game(s), {tot_l:,} log rows")
            except Exception as exc:  # noqa: BLE001
                log(f"  ⚠️  wnba results ingest failed: {exc}")

    # NFL weekly results — the layer that settles NFL props and TDs. The
    # nflverse weekly-stats file updates within a day of games, so a daily
    # pull keeps the journal graded all season. Skipped March–July: no new
    # stats exist and the download is pure waste.
    if today.month >= 8 or today.month <= 2:
        try:
            from . import db as _rdb
            from .ingest import ingest_nfl_results
            season = today.year if today.month >= 8 else today.year - 1
            res = ingest_nfl_results(_rdb.connect(), season)
            if res["player_logs"]:
                log(f"  nfl results: {res['player_logs']:,} weekly stat rows "
                    f"(season {season})")
            for s in res.get("skipped", []):
                log(f"  ⚠️  {s}")
        except Exception as exc:  # noqa: BLE001
            log(f"  ⚠️  nfl results ingest failed: {exc}")

        # Settle the anytime-TD quote journal against the rows the pull
        # above just wrote, and refit the measured one-sided hold once
        # the sample clears its gate (engine/holdwatch — the number that
        # retires the "vig assumed at 6%" caveat).
        try:
            from . import db as _qdb
            from . import holdwatch as _hw
            _qconn = _qdb.connect()
            _ns = _hw.settle(_qconn)
            if _ns:
                log(f"  hold journal: {_ns} anytime-TD quote(s) settled")
            _fit = _hw.fit(_qconn)
            if _fit:
                log(f"  hold measured: {_fit['hold'] - 1:.1%} off "
                    f"{_fit['n']:,} settled quotes")
        except Exception as exc:  # noqa: BLE001
            log(f"  ⚠️  hold journal skipped: {exc}")

        # The season-boundary backfill (Ethan circled the card's own
        # confession, 2026-08-26: "Red-zone usage inferred … play-by-play
        # not ingested"). In August and September the CURRENT season has
        # no stats to pull, and if LAST season was never ingested on this
        # box, the TD model's measured red-zone roles, snap shares and
        # carried touchdown histories all read an empty table — every
        # card wears the inferred-usage caveat through exactly the weeks
        # the season arrives. One guarded pull of the prior season fills
        # all of it (weekly stats + usage + TD rows + snaps + pbp); the
        # guard row makes it run once per box, not once per night.
        if today.month in (8, 9):
            try:
                from . import db as _bdb
                from .ingest import ingest_nfl
                _bconn = _bdb.connect()
                prior = today.year - 1
                have_rz = _bconn.execute(
                    "SELECT 1 FROM player_game_logs WHERE sport='nfl' "
                    "AND season=? AND market='rz_tgt' LIMIT 1",
                    (prior,)).fetchone()
                if not have_rz:
                    res = ingest_nfl(_bconn, [prior])
                    log(f"  nfl backfill: season {prior} ingested — "
                        f"{res.get('player_logs', 0):,} log rows, "
                        f"{res.get('pbp_rows', 0):,} pbp rows (measured "
                        f"red-zone roles now available)")
                    for s in res.get("skipped", []):
                        log(f"  ⚠️  {s}")
            except Exception as exc:  # noqa: BLE001
                log(f"  ⚠️  nfl prior-season backfill failed: {exc}")

        # Play-by-play refresh — the measured red-zone roles. The file is
        # ~100MB, so once a week (Tuesdays, after Monday night) is the
        # right cadence, not daily.
        if today.weekday() == 1:
            try:
                from . import db as _pdb
                from .sources.nflpbp import (load_pbp_rows, aggregate_pbp,
                                             xfp_player_rows)
                season = today.year if today.month >= 8 else today.year - 1
                agg = aggregate_pbp(load_pbp_rows(season))
                n = _pdb.upsert_player_logs(_pdb.connect(),
                                            xfp_player_rows(agg, season))
                if n:
                    log(f"  nfl pbp: {n:,} xFP/red-zone rows refreshed")
            except Exception as exc:  # noqa: BLE001
                log(f"  ⚠️  nfl pbp refresh failed: {exc}")

    # Keep the fetch cache from growing without bound (a season of
    # per-game files runs to thousands). Never blocks the chores.
    try:
        prune_cache(log=log)
    except Exception as exc:  # noqa: BLE001
        log(f"  ⚠️  cache prune skipped: {exc}")

    # Boards whose surface is retired leave the public path too — a file
    # nothing rebuilds is a page frozen at its last build, still served.
    try:
        remove_retired_boards(log=log)
    except Exception as exc:  # noqa: BLE001
        log(f"  ⚠️  retired-board sweep skipped: {exc}")

    # The book report card (roadmap #7) — which book prices sharpest,
    # measured off our own snapshots. Daily because the chores are; the
    # numbers move on a weekly rhythm and the page says when they were
    # cut. Facts about BOOKS only, which is why the gate publishes it
    # free (see FREE_FILES).
    try:
        from . import booksharp, gate
        doc = booksharp.payload()
        if doc.get("books"):
            gate.publish(doc, Path("web/data/bookreport.json"),
                         "bookreport.json")
            log(f"  book report: {sum(1 for b in doc['books'] if b['ranked'])}"
                f" book(s) ranked")
    except Exception as exc:  # noqa: BLE001
        log(f"  ⚠️  book report skipped: {exc}")

    if harvest:
        _maybe_harvest(yesterday, log)

    if state_path == STATE_PATH:
        # Real runs only — an injected state path means a test harness, and
        # tests must never write archives into the working tree.
        try:
            _maybe_backup(state, today, log)
        except Exception as exc:  # noqa: BLE001 — never block the chores
            log(f"  ⚠️  backup failed: {exc}")

    if ingest_ok:
        state["last_done"] = today.isoformat()
    # On ingest failure the day stays unmarked (so the next cycle retries)
    # but the rest of the state — e.g. the backup timestamp — persists.
    _save_state(state_path, state)
    return True
