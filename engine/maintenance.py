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
        n = ledger.settle_from_history(ledger.connect(), db.connect())
        log(f"  journal: settled {n} pick(s)" if n else "  journal: nothing to settle")
    except Exception as exc:  # noqa: BLE001
        log(f"  ⚠️  journal settle failed: {exc}")

    if harvest:
        _maybe_harvest(yesterday, log)

    if ingest_ok:
        _save_state(state_path, {"last_done": today.isoformat()})
    return True
