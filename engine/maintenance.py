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
(catching up as far as ``CATCH_UP_DAYS`` if the site wasn't opened for a
while), every other cycle is a no-op. Ingestion is idempotent, so overlap
with manual runs is harmless.

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

# How far back a catch-up reaches when the site hasn't been opened in days.
CATCH_UP_DAYS = 7
# Never auto-harvest below this measured remaining quota — daily closes are a
# nice-to-have; live odds for today's picks always come first.
HARVEST_MIN_REMAINING = 3000
# Hard per-day cap on what an auto-harvest may spend.
HARVEST_DAY_BUDGET = 400


def _load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state))


BACKUP_DIR = ROOT / "data" / "backups"
BACKUP_EVERY_DAYS = 7
BACKUP_KEEP = 6
# What a backup protects: the databases (history + ledger — months of
# ingested truth and the bet journal) and the append-only files that can
# NEVER be rebuilt if lost (the line-move snapshots; the UFC dossiers you
# typed by hand). Secrets are deliberately excluded.
BACKUP_FILES = ("data/history.db", "data/ledger.db",
                "data/cache/line_history.jsonl", "data/ufc_dossiers.json")


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
    # Prune: keep the newest BACKUP_KEEP.
    zips = sorted(backup_dir.glob("backup_*.zip"))
    for old in zips[:-BACKUP_KEEP]:
        old.unlink(missing_ok=True)
    state["last_backup"] = today.isoformat()
    log(f"  backup: {wrote} file(s) → {out.name} "
        f"({len(list(backup_dir.glob('backup_*.zip')))} kept)")


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
    cmd = [sys.executable, "harvest_odds.py", "mlb",
           "--from", day.isoformat(), "--to", day.isoformat(),
           "--markets", "total_bases,h2h",
           "--budget", str(HARVEST_DAY_BUDGET), "--yes"]
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True,
                              text=True, timeout=600)
        lines = (proc.stdout + proc.stderr).strip().splitlines()
        harvested = next((l.strip() for l in lines if l.strip().startswith("Harvested")),
                         lines[-1].strip() if lines else "")
        log(f"  closes: {harvested}")
    except Exception as exc:  # noqa: BLE001 — maintenance must never crash the site
        log(f"  ⚠️  closes: auto-harvest failed ({exc})")


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
SETTLE_EVERY_S = 900             # 15 minutes between intraday passes
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
        res = ingest.ingest_mlb_results(hconn, days[0], days[-1], with_logs=True)
        # NBA nights grade intraday too — CDN boxscores go final within
        # minutes of the buzzer. Only dates with open NBA picks are pulled.
        try:
            from .sources.nbadata import ingest_nba_date
            for d in days:
                if lconn.execute(
                        "SELECT 1 FROM bets WHERE status='open' AND "
                        "sport='nba' AND date=? LIMIT 1", (d,)).fetchone():
                    ingest_nba_date(hconn, d)
        except Exception:  # noqa: BLE001 — free-feed hiccup; daily pass catches up
            pass
        settled = ledger.settle_from_history(lconn, hconn)
        if settled:
            ledger.export_json(lconn, ROOT / "web" / "data" / "record.json")
            log(f"  settled {settled} pick(s) from {res['games']} finished "
                f"game(s) ({days[0]}"
                + (f" → {days[-1]}" if days[-1] != days[0] else "") + ")")
    except Exception as exc:  # noqa: BLE001 — never take the site down
        log(f"  ⚠️  auto-settle failed: {exc}")
    state["last_settle_ts"] = now
    _save_state(state_path, state)
    return settled


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
    start = yesterday - _dt.timedelta(days=CATCH_UP_DAYS - 1)
    if state.get("last_done"):
        try:
            # Re-ingest from the last maintained day (idempotent) — its games
            # may have finished after that run.
            start = max(start, _dt.date.fromisoformat(state["last_done"])
                        - _dt.timedelta(days=1))
        except ValueError:
            pass
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
        n = ledger.settle_from_history(lconn, db.connect())
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
    # over the same catch-up window. This is what settles NBA picks and the
    # NBA stale-line flags. Skipped July–September: no games exist.
    if (today.month >= 10 or today.month <= 6) and start <= yesterday:
        try:
            from . import db as _ndb
            from .sources.nbadata import ingest_nba_date
            nconn = _ndb.connect()
            tot_g = tot_l = 0
            d = start
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
