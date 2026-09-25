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
# Never auto-harvest below this measured remaining quota — live odds for
# today's picks always come first. Was 3000; Ethan, 2026-09-07, setting the
# credit budget the data plan asked him for: "set the harvest floor to 1000
# and day budget 400". A thinner floor buys more weeks of prop closes on a
# lean month; the day cap below is what keeps one night from spending it.
HARVEST_MIN_REMAINING = 1000
# Hard per-day cap on what an auto-harvest may spend — ACROSS every day it
# reaches back to, not per harvest run (see _maybe_harvest).
HARVEST_DAY_BUDGET = 400
# How far back the nightly walks for days that bet and never got a close.
# Thirty days covers a month of outages, declined harvests and thin-quota
# nights; a bet older than that has long since settled on a schedule close.
HARVEST_BACKFILL_DAYS = 30


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


#: Below this many graded college player-games, the CFB touchdown board
#: has nobody to price and the backfill runs. One FBS season is ~16,000
#: player-games; anything under a few thousand is an empty table or a
#: half-finished pull, not a season.
CFB_MIN_PLAYER_ROWS = 5_000

#: Below this many college games carrying a closing spread, the market
#: haircut cannot be measured and the backfill runs. Four ingested
#: seasons are 3,132; `engine.gamecal.MIN_N` needs 400 graded
#: observations before it will adopt anything at all.
CFB_MIN_CLOSES = 1_000

#: How stale a cached copy of the season being PLAYED may be before the
#: nightly re-reads it. The mirror publishes a finished week within a day
#: or so; the default seven-day TTL is for seasons that are over.
CFB_RESULTS_TTL = 6 * 3600

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


def cfb_player_seasons(today, have: int) -> list[int]:
    """Which college seasons the nightly should ingest player logs for.

    ``have`` is the all-time count of college anytime_td rows, which is
    what gates the one-time historical backfill.

    TWO RULES, AND THE SECOND ONE WAS MISSING FOR A SEASON.

    The historical backfill runs once per box, on the four seasons before
    this one. Note what has never been in that list: the season being
    PLAYED. `(4, 3, 2, 1)` is 2022-2025 in 2026, so a box that ran it
    came away with four years of history and nothing from the year its
    board is pricing.

    The second rule is the current season, and it now runs EVERY NIGHT
    the season is on. It used to be `elif today.weekday() == 0` — Mondays
    only, and unreachable on any day until `have` fell under the floor,
    which it never does again after the first backfill.

    Ethan, 2026-09-18: "CFB still hasn't graded any edge bets or most
    likely bets ... it's been like that since week zero." Every college
    player-market bet settles against these rows. The results half of
    this nightly already refreshes the current season in season, which is
    why `games` was current to the day while the player half was a month
    behind. Same rule on both halves now.
    """
    season = today.year if today.month >= 8 else today.year - 1
    in_season = today.month >= 8 or today.month <= 1
    seasons: list[int] = []
    if have < CFB_MIN_PLAYER_ROWS:
        seasons = [today.year - n for n in (4, 3, 2, 1)]
    if in_season and season not in seasons:
        seasons.append(season)
    return seasons


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


#: The journal's game-bet vocabulary → the Odds API's own keys, from the
#: module that owns the translation. It used to be a private copy here,
#: and the copy was the bug: `resolve_market_keys` did NOT translate
#: game markets, so the nightly (which pre-translated with this map)
#: asked for "spreads" while `harvest_odds.py --markets spread` asked
#: for "spread", which the API has never had. One map now, and this name
#: is kept as an alias so the nightly's own call site still reads the way
#: it always did.
from .sources.oddshistory import GAME_MARKET_KEYS as _HARVEST_GAME_MARKETS

#: Sports the auto-harvest may spend on. CFB joined 2026-08-26, once the
#: blocker was removed rather than worked around: its team map is built
#: at run time from the ESPN feed inside cfb_build, so a harvest used to
#: store school names no settle pass could join to a bet. cfb_build now
#: writes every name it resolves to data/feedstate/cfb_teams.json
#: (engine/cfbteams) and the history parsers read it per call, so the
#: names join. `_harvest_targets` still refuses CFB while that map is
#: empty — spending credits to store unjoinable rows is the failure this
#: gate exists to prevent, and an empty map is exactly that state.
_HARVEST_SPORTS = ("mlb", "nfl", "cfb")

#: The Yes-only markets whose hold is measured rather than assumed
#: (engine/holdwatch). Each fits its OWN number: a touchdown book and a
#: home-run book do not price the same juice, and the pricing path asks
#: per (sport, market) already.
HOLD_MARKETS = (("nfl", "anytime_td"), ("mlb", "home_runs"),
                ("cfb", "anytime_td"))


def _cfb_map_ready() -> bool:
    """Has any cfb_build written school names down yet?

    The harvest is credit-spending, and a harvest keyed through an empty
    map stores rows no settle pass can join — the exact waste the old
    "CFB is deliberately absent" rule prevented. One priced board fills
    the map for the schools it saw, so this is normally true from the
    first Saturday of the season onward.
    """
    try:
        from .cfbteams import load as _load_cfb
        return bool(_load_cfb())
    except Exception:                                        # noqa: BLE001
        return False


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
            if sport == "cfb" and not _cfb_map_ready():
                continue        # no map yet — the rows would not join
            markets = sorted({_HARVEST_GAME_MARKETS.get(m, m) for m in rows})
            out.append((sport, ",".join(markets)))
    except Exception:
        return out
    finally:
        conn.close()
    return out


def _day_has_closes(hconn, sport: str, day: _dt.date) -> bool:
    """Did a harvest ever land on this sport and calendar day?

    The harvest stamps its snapshot on the day it was asked for (23:00
    UTC by default), so the calendar prefix is the join. One row is
    enough: the CLI dedupes per event and per market on its own, so the
    question here is only "has this day been visited", never "is it
    complete" — a day the harvest reached and ran out of budget on is
    revisited by the CLI's own skip logic, not by this test.
    """
    try:
        return hconn.execute(
            "SELECT 1 FROM odds_history WHERE sport=? AND taken_at LIKE ? LIMIT 1",
            (sport, f"{day.isoformat()}%")).fetchone() is not None
    except Exception:                                        # noqa: BLE001
        return True                     # unreadable: spend nothing on it


def _backfill_days(yesterday: _dt.date, hconn,
                   days: int = HARVEST_BACKFILL_DAYS) -> list:
    """``[(day, sport, markets)]`` for every earlier day that bet and
    holds no close, newest first — the order a grader wants them in."""
    out = []
    for back in range(1, days + 1):
        d = yesterday - _dt.timedelta(days=back)
        for sport, markets in _harvest_targets(d):
            if not _day_has_closes(hconn, sport, d):
                out.append((d, sport, markets))
    return out


def _run_harvest(sport: str, day: _dt.date, markets: str, budget: int, log) -> None:
    cmd = [sys.executable, "harvest_odds.py", sport,
           "--from", day.isoformat(), "--to", day.isoformat(),
           "--markets", markets, "--budget", str(int(budget)), "--yes"]
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True,
                              text=True, timeout=600)
        lines = (proc.stdout + proc.stderr).strip().splitlines()
        harvested = next(
            (l.strip() for l in lines if l.strip().startswith("Harvested")),
            lines[-1].strip() if lines else "")
        log(f"  closes ({sport} {day}): {harvested}")
    except Exception as exc:  # noqa: BLE001 — must never crash the site
        log(f"  ⚠️  closes ({sport} {day}): auto-harvest failed ({exc})")


def _maybe_harvest(day: _dt.date, log, budget_path=None, hconn=None) -> None:
    """Harvest yesterday's closing odds, then walk back through earlier
    days that bet and never got one — all of it inside one day's budget.

    THE BUDGET IS THE DAY'S, NOT THE RUN'S. The old loop handed every
    harvest run its own HARVEST_DAY_BUDGET, which was fine while there
    was one run a night and would be N × 400 the moment there were N.
    Spend is now metered from the API's own remaining count, read from
    the budget state the CLI updates on every response: each run is told
    only what is left of the day, and the walk stops when the day is
    spent or the balance reaches the floor.

    WHY WALK BACK AT ALL. A night the harvest was declined — quota under
    the floor, the API down, the box off — left that day's bets settling
    with no close, for good: nothing ever came back for them, and a bet
    with no close cannot be graded on closing-line value. Ethan,
    2026-09-07: "build the price history ... grade every card on closing
    line value first". Newest first, because the most recent ungraded
    week is the one the scoreboard is missing.
    """
    if not os.environ.get("ODDS_API_KEY"):
        return
    try:
        from .oddsbudget import load, is_measured
        kw = {"path": budget_path} if budget_path else {}
        st = load(**kw)
        if not is_measured(st) or st.remaining < HARVEST_MIN_REMAINING:
            have = st.remaining if is_measured(st) else "unknown"
            log(f"  closes: auto-harvest skipped (quota {have}, reserve "
                f"{HARVEST_MIN_REMAINING}) — picks still journal, but prop CLV "
                f"for {day} won't fill in")
            return
    except Exception:
        return
    start = st.remaining

    def left() -> int:
        """Credits still spendable today, and never past the floor."""
        try:
            cur = load(**kw).remaining
        except Exception:                                    # noqa: BLE001
            return 0
        return max(0, min(HARVEST_DAY_BUDGET - (start - cur),
                          cur - HARVEST_MIN_REMAINING))

    if hconn is None:
        try:
            from . import db as _hdb
            hconn = _hdb.connect()
        except Exception:                                    # noqa: BLE001
            hconn = None
    queue = [(day, s, m) for s, m in _harvest_targets(day)]
    if hconn is not None:
        queue += _backfill_days(day, hconn)
    for d, sport, markets in queue:
        budget = left()
        if budget <= 0:
            log(f"  closes: day budget spent ({HARVEST_DAY_BUDGET}) or at the "
                f"floor — {sport} {d} waits for tomorrow's walk")
            break
        _run_harvest(sport, d, markets, budget, log)


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
DESK_EVERY_S = 3600              # the exchange is asked about open tickets hourly
# How far back an intraday pass will reach for still-open picks. The daily
# chores handle anything older (and reach CATCH_UP_DAYS), so this only has
# to cover "tonight, and last night if the launcher was closed".
SETTLE_LOOKBACK_DAYS = 3


def _open_bet_days(lconn, today: _dt.date, lookback: int) -> list[str]:
    """Distinct CALENDAR days that still have open picks, oldest first.
    Anything older than the lookback is the daily job's problem.

    THE COLUMN IS NOT THE CALENDAR, AND FOR FOOTBALL IT NEVER WAS.
    ``bets.date`` is the SLATE LABEL — an ISO day for the daily sports, and
    for the NFL a WEEK, "2026-W01". Windowing on it compares that label
    against "2026-09-08" as text, and 'W' sorts after every digit, so no
    week label is ever inside any window this function can build. Every NFL
    pick was invisible here.

    That cost far more than one skipped ingest. `settle_open` returns
    EARLY when this list comes back empty, so on a night whose only open
    picks were football, the intraday settle did not run at all — no
    ingest, no grade, no parlay pass. And `_has_open(lconn, "nfl", days)`
    can never be true against a list this cannot contain, which is why no
    football results pull could be wired to that gate.

    `ledger.day_expr` is the one expression for "the day this bet belongs
    to", and its own docstring says why there must only be one: several
    readers window the journal and they have to agree. It reads
    ``game_day`` — the real kickoff date, taken from nflverse's
    ``gameday`` when the pick was journalled — and falls back to ``date``
    for the daily sports, where the label already IS the day.

    Rows journalled BEFORE ``game_day`` existed carry no kickoff date, so
    they still fall back to a week label and still sit outside the window.
    That is not made wrong by this change and inventing a day for them
    would be worse; ``--backfill-days`` is what moves them.
    """
    from . import ledger
    day = ledger.day_expr()
    floor = (today - _dt.timedelta(days=lookback - 1)).isoformat()
    rows = lconn.execute(
        f"SELECT DISTINCT {day} AS d FROM bets WHERE status='open' "
        f"AND {day} >= ? AND {day} <= ? ORDER BY d",
        (floor, today.isoformat())).fetchall()
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
    # THE TWO BASKETBALL SCOREBOARDS livescore_build ADDED. One file per
    # league, overwritten every poll, so these do not grow in COUNT the
    # way `mlb_pbp_{pk}` does — but `test_cacheclass._classified` passed
    # them on a prefix match against `espn_nfl_` while `prune_cache`
    # matches whole prefixes and would never have touched them. A rule
    # that says a file is classified and a pruner that skips it is the
    # gap the classification test exists to close.
    "espn_nba_", "espn_wnba_",
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
    "cfb_rosters_": ("cfbfastR per-season roster, one file a season; the settler "
                     "reads it OFFLINE for a first-appearance player's school "
                     "(engine/cfbroster) — pruning it would blind that read"),
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
    # FOOTBALL, WHICH HAD NO INTRADAY RESULTS PULL AT ALL. Both leagues
    # grade a game bet off `games.home_score`, and until now the only
    # writer of one was the once-a-day nflverse schedule refresh — so an
    # NFL final at 11pm could not settle a thing until the next morning's
    # chores, which `docs/DROPLET_CHECKS.md` recorded as intended
    # ("Wednesday's final settles on Thursday's pass"). Ethan, 2026-09-10,
    # half an hour after the Week 1 opener: "also none of the nfl bets
    # settled from tonight yet."
    #
    # `livescores.ingest_finals` fills the blank score on a fixture the
    # schedule already wrote, from the same keyless scoreboard the live
    # board polls every twelve seconds. Not the day loop above: one
    # scoreboard call covers the whole slate, so it is asked once per
    # league rather than once per open day.
    #
    # PLAYER PROPS ARE NOT SETTLED BY THIS. Their actuals live in
    # `player_game_logs`, which for the NFL comes from the nflverse weekly
    # file and still lands within a day. Game bets — moneyline, spread,
    # total, team total — are what this closes, and they are the ones
    # whose answer was on the screen already.
    # THE NFL'S STAT LINES, DURING THE DAY AND NOT ONLY AT NIGHT. Finals
    # below settle the game bets, but a prop grades from nflverse's weekly
    # stat file, and that file was pulled ONCE, in the nightly chores. On
    # a Sunday slate nflverse publishes the box scores overnight — after
    # our pull has already run — so every Sunday prop sat open until
    # Tuesday. Ethan, Monday 2026-09-14: "none of the nfl bets from Sunday
    # settled." The pull is cheap to repeat (the CSV is cached 12h, the
    # upsert is idempotent) and is throttled here on its own ingest_log
    # row so a five-minute settle loop asks nflverse at most every few
    # hours, and only while an NFL pick is open.
    # ONLY WHILE THE FILE IS STILL OWED. A game day whose every finished
    # game is already in the official file has nothing left to pull for;
    # a day whose games have not finished cannot be in it yet. The pull
    # is for the hours in between — Sunday night to Monday morning —
    # and runs hourly there (2026-09-15; it was every four hours on any
    # game day, landed or not, which is both slower than the file and
    # four 15 MB downloads a day for nothing).
    owed = [d for d in days
            if _has_open(lconn, "nfl", [d]) and _nfl_day_wanted(hconn, d)]
    if owed:
        try:
            if _nfl_stats_due(hconn):
                season = _nfl_season_of(owed[-1])
                res_nfl = ingest.ingest_nfl_results(hconn, season)
                db_log = getattr(ingest, "db", None)
                if db_log is not None:
                    db_log.log_ingest(hconn, "nfl", NFL_STATS_KIND, str(season),
                                      int(res_nfl.get("player_logs") or 0))
                if res_nfl.get("player_logs"):
                    log(f"  NFL weekly stats: {res_nfl['player_logs']:,} row(s) "
                        f"pulled for the open props")
                for sk in res_nfl.get("skipped", []):
                    log(f"  ⚠️  {sk}")
        except Exception as exc:  # noqa: BLE001
            log(f"  ⚠️  NFL weekly stats unavailable ({exc}) — props stay "
                f"open until the next pull")
    for league in ("nfl", "cfb"):
        if not _has_open(lconn, league, days):
            continue
        try:
            from .sources import livescores
            fin = livescores.ingest_finals(hconn, league)
            if fin["games"]:
                log(f"  {league.upper()} finals: {fin['games']} game(s) "
                    f"scored from the live scoreboard")
            for s in fin["skipped"]:
                log(f"  ⚠️  {s}")
        except Exception as exc:  # noqa: BLE001
            log(f"  ⚠️  {league.upper()} finals unavailable ({exc}) — those "
                f"picks stay open until the daily pass")
    # THE BOX SCORE, the night the game ends (engine/boxsettle). After
    # the finals, because it only reads a game with a stored final, and
    # before the settle, because that is what it exists to feed. Ethan,
    # 2026-09-15: "I still see some edge bets not graded from last
    # nights nfl games" — Monday's props waited for a file that
    # publishes the next morning.
    for league in ("nfl", "cfb"):
        if not _has_open(lconn, league, days):
            continue
        try:
            from . import boxsettle
            bx = boxsettle.ingest_for_open(lconn, hconn, league, log=log)
            if bx["games"]:
                log(f"  {league.upper()} box scores: {bx['rows']} stat line(s) "
                    f"from {bx['games']} finished game(s), provisional until "
                    f"the official file lands")
            if bx["purged"]:
                log(f"  {league.upper()} box scores: {bx['purged']} provisional "
                    f"row(s) replaced by the official file")
            for s in bx["skipped"]:
                log(f"  ⚠️  {s}")
        except Exception as exc:  # noqa: BLE001
            log(f"  ⚠️  {league.upper()} box scores unavailable ({exc}) — "
                f"those props wait for the official file")
    return res


#: How the intraday NFL stats pull records itself, and how often it may run.
NFL_STATS_KIND = "weekly_stats_intraday"
#: Hourly, and only while a finished game with an open pick is missing
#: from the file — see `_nfl_day_wanted`. nflverse publishes Sunday's
#: stats in the small hours of Monday; an hour is the most a graded
#: Sunday now waits on us rather than on them.
NFL_STATS_EVERY_S = 3600


def _nfl_day_wanted(hconn, day: str) -> bool:
    """Is the weekly file still owed for this game day?

    True when the schedule has no row for the day (unknown is not
    covered — ask the file), or when a finished game on it has a team
    with no official row yet. False when nothing on the day has finished
    (the file cannot carry it) or every finished game's teams are filed
    (nothing left to fetch; a player still absent then is the absent-
    player rule's question, not the ingest's).
    """
    games = hconn.execute(
        "SELECT season, period, home, away, home_score, away_score FROM games "
        "WHERE sport='nfl' AND date=?", (str(day)[:10],)).fetchall()
    if not games:
        return True
    finals = [g for g in games
              if g["home_score"] is not None and g["away_score"] is not None]
    if not finals:
        return False
    played = {t for g in finals for t in (g["home"], g["away"])}
    filed = {r[0] for r in hconn.execute(
        "SELECT DISTINCT team FROM player_game_logs WHERE sport='nfl' "
        "AND season=? AND period=? AND game_id NOT LIKE '%-box'",
        (int(finals[0]["season"]), str(finals[0]["period"])))}
    return not played <= filed


def _nfl_season_of(day: str) -> int:
    """The NFL season a calendar day belongs to: August onward is that
    year's season; January and February are the previous year's."""
    d = _dt.date.fromisoformat(str(day)[:10])
    return d.year if d.month >= 8 else d.year - 1


def _nfl_stats_due(hconn, now: float | None = None) -> bool:
    """Has it been NFL_STATS_EVERY_S since the last intraday stats pull?

    Read off ingest_log rather than a state file, so the throttle lives
    beside the thing it throttles and a hand-run ingest counts too.
    """
    import time as _time
    row = hconn.execute(
        "SELECT ts FROM ingest_log WHERE sport='nfl' AND kind=? "
        "ORDER BY id DESC LIMIT 1", (NFL_STATS_KIND,)).fetchone()
    if not row or not row[0]:
        return True
    try:
        last = _dt.datetime.fromisoformat(str(row[0])).replace(
            tzinfo=_dt.timezone.utc).timestamp()
    except ValueError:
        return True
    return ((now if now is not None else _time.time()) - last) >= NFL_STATS_EVERY_S


def _has_open(lconn, sport: str, days: list[str]) -> bool:
    """Does this league have an open pick on any of these CALENDAR days?

    Matched on `ledger.day_expr` for the same reason `_open_bet_days`
    selects it: the days handed in are calendar days, and an NFL bet's
    ``date`` column is a week label that can never equal one. Matching on
    the raw column meant a football league could not answer yes here even
    when the caller had just been told the day was open.
    """
    if not days:
        return False
    from . import ledger
    marks = ",".join("?" * len(days))
    return bool(lconn.execute(
        f"SELECT 1 FROM bets WHERE status='open' AND sport=? "
        f"AND {ledger.day_expr()} IN ({marks}) LIMIT 1",
        (sport, *days)).fetchone())


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
        hconn = db.connect()
        # PLACE THE STRANDED ROWS FIRST, on every pass, before the window is
        # built from them. `_open_bet_days` reads `game_day`, and a row
        # without one sits under its week label outside every window — it
        # is not merely ungraded, it stops this function from running the
        # results ingest at all (see `_open_bet_days`). The stamping at the
        # journal door was fixed on 2026-09-11, but 134 rows were already
        # stranded on the droplet and the repair was a command a person
        # had to run by hand: `--backfill-days --apply`. Ethan, 2026-09-14,
        # from work: "None of the nfl edge or most likely bets settled" —
        # he could not run it, and a repair that waits for a keyboard is
        # not a repair. `backfill_game_days` only ever fills a NULL and
        # never touches `date`, the settle key, so running it every cycle
        # cannot unsettle anything; it scans `game_day IS NULL` and is
        # cheap when there is nothing to do.
        try:
            bf = ledger.backfill_game_days(lconn, hconn)
            if bf.get("filled"):
                log(f"  placed {bf['filled']} journal row(s) on their game "
                    f"day ({bf.get('unresolved', 0)} still on a week label)")
        except Exception as exc:  # noqa: BLE001
            log(f"  ⚠️  game-day backfill skipped: {exc}")
        days = _open_bet_days(lconn, today, SETTLE_LOOKBACK_DAYS)
        if not days:
            # Nothing to do — still stamp the clock so we don't re-check
            # the journal every single cycle.
            state["last_settle_ts"] = now
            _save_state(state_path, state)
            return 0
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
        # And the football half of the same problem: NFL stale-line flags
        # journalled as baseball by a defaulted sport. Same placement and
        # the same reason as the relabel above — a bet under the wrong
        # league can never meet its results, and the ingest below picks
        # which sports to fetch from the bets' own labels.
        try:
            refiled = ledger.repair_football_filed_as_baseball(lconn)
            if refiled:
                log(f"  re-filed {refiled} football bet(s) out of the "
                    f"baseball book")
        except Exception as exc:  # noqa: BLE001
            log(f"  ⚠️  football re-file skipped: {exc}")
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
        # THE DESK, hourly. Its tickets grade against the exchange, not
        # the history database, and until 2026-09-15 nothing on any
        # clock asked the exchange (see `ledger.settle_predmarket`).
        last_desk = state.get("last_desk_ts")
        if not (isinstance(last_desk, (int, float)) and now - last_desk < DESK_EVERY_S):
            try:
                dk = ledger.settle_predmarket(lconn)
                if dk.get("error"):
                    log(f"  ⚠️  desk settle skipped: {dk['error']}")
                elif dk["settled"] or dk["voided"]:
                    log(f"  desk: {dk['settled']} ticket(s) graded, "
                        f"{dk['voided']} voided, of {dk['checked']} asked")
                settled += dk["settled"] + dk["voided"]
            except Exception as exc:  # noqa: BLE001
                log(f"  ⚠️  desk settle failed: {exc}")
            state["last_desk_ts"] = now
            _save_state(state_path, state)
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
                # AND WHETHER ONE NUMBER IS THE RIGHT SHAPE. The pooled
                # haircut assumes the over-claim is the same size at
                # every price; the droplet's book says it grows with the
                # price. Reported weekly, applied never — a band earns a
                # correction by clearing the floor on its own.
                try:
                    for _bl in selectionfit.band_lines(
                            selectionfit.bands(lconn)):
                        log("  " + _bl)
                except Exception as _bexc:  # noqa: BLE001
                    log(f"  ⚠️  haircut band check skipped: {_bexc}")
                for name, e in [("pooled", sf["pooled"])] + sorted(
                        sf["sports"].items()):
                    if e.get("applied"):
                        log(f"  selection haircut ({name}): claimed "
                            f"{e['claimed'] * 100:.1f}%, landed "
                            f"{e['landed'] * 100:.1f}% over {e['n']} bets — "
                            f"shift {e['shift']:+.3f} log-odds")
            except Exception as exc:  # noqa: BLE001
                log(f"  ⚠️  selection haircut skipped: {exc}")
            # The correlation priors, refit against our own history. The
            # last fitter on this site that a human had to remember to
            # run: you typed the command, read a table and hand-copied
            # five numbers into engine/parlays.MEASURED. It costs about
            # a second — eleven pairings over the logs table — and it
            # only displaces a standing number when it is measured on at
            # least as many games, so a thin database cannot make the
            # parlay pricer worse.
            try:
                from . import corrfit
                cf = corrfit.refresh(hconn)
                for a in cf["adopted"]:
                    sup = a.get("superseded")
                    log(f"  correlation refit: {a['key']} rho={a['r']:+.3f} "
                        f"on {a['n']:,} games"
                        + (f" — SUPERSEDES {sup['was']:+.3f}, which this "
                           f"code cannot reproduce ({sup['sigma']} sigma out)"
                           if sup else ""))
            except Exception as exc:  # noqa: BLE001
                log(f"  ⚠️  correlation refit skipped: {exc}")
            # The game-line model, graded against the closing numbers.
            # This is the fitter that had nothing to fit until this week:
            # spreads and totals were priced, argued about and never
            # measured, because no closing number was stored anywhere. The
            # schedule feed was carrying them the whole time. What it
            # measures is the fraction of a disagreement with the close
            # that has actually held up, and that fraction replaces the
            # flat "shrink halfway to the market" guess on the pricing
            # path. It can only make the board quieter (gamecal
            # .MAX_ADOPTED), so a thin or unlucky database cannot talk
            # this model into betting more.
            try:
                from . import gamecal
                gc = gamecal.refresh(hconn)
                for a in gc["adopted"]:
                    log(f"  game-line calibration: {a['key']} keeps "
                        f"{a['shrink']:.0%} of a disagreement with the close "
                        f"(slope {a['slope']:+.3f} ± {a['se']:.3f} on "
                        f"{a['n']:,} games)")
            except Exception as exc:  # noqa: BLE001
                log(f"  ⚠️  game-line calibration skipped: {exc}")
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
                # Same discipline as the deep refit: the lab replays
                # whole seasons in memory and its own "done" stamp is
                # written only when it finishes, so a killed run would
                # be due again on the next cycle. Attempted once a day,
                # and out of process.
                if lab._due(Path(lab.LAB_PATH), today) \
                        and state.get("lab_attempted") != today.isoformat():
                    state["lab_attempted"] = today.isoformat()
                    _save_state(state_path, state)
                    for line in _run_lab(log):
                        log(f"  {line}")
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


#: How long a weekly fitter may run before it is cut off. The deep refit
#: was measured in minutes per season on the droplet; an hour is room,
#: not a target, and a job that needs more than that is a job to split.
WEEKLY_JOB_TIMEOUT_S = 3600

#: The weekly children this process has started and not yet reaped:
#: ``{module: {"proc", "started", "log"}}``. Module-level on purpose —
#: the refresh loop calls `run_if_due` every cycle, and the reaping has
#: to see the children an earlier cycle spawned.
_CHILDREN: dict = {}


def _child_log_path(module: str) -> Path:
    return ROOT / "data" / "cache" / f"weekly_{module.rsplit('.', 1)[-1]}.log"


def _spawn_module(module: str, log, args: tuple = ()) -> list[str]:
    """Start ``python3 -m module`` as a niced, DETACHED child.

    Detached, and that word is the fix. The first version of this ran the
    child with `subprocess.run` and waited — and the refresh loop calls
    the daily chores BEFORE it rebuilds a single board, so on the
    fitters' day every board on the site stood still until the refit
    and then the lab had finished, up to an hour each. A weekly job that
    freezes the day's boards is the outage in a different coat. Now the
    child is started and left; its output goes to a log file under
    data/cache; and `reap_children` — called every cycle — logs its exit
    when it lands, and cuts it off past WEEKLY_JOB_TIMEOUT_S.

    Everything the child loads is freed when it exits, and if the box
    cannot afford the job it is the child the OOM killer takes; the
    unit's OOMPolicy=continue is what lets the server survive that.
    Never raises: a fitter that cannot start is a logged line.
    """
    import subprocess
    import sys
    import time as _time
    if module in _CHILDREN:
        return [f"{module}: still running from an earlier cycle — not started again"]
    cmd = [sys.executable, "-m", module, *args]
    nicer = (lambda: os.nice(10)) if hasattr(os, "nice") else None
    path = _child_log_path(module)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(path, "w", encoding="utf-8")
        proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=fh, stderr=subprocess.STDOUT,
                                preexec_fn=nicer, start_new_session=True)
    except Exception as exc:  # noqa: BLE001
        return [f"⚠️  {module}: could not start — {exc}"]
    _CHILDREN[module] = {"proc": proc, "started": _time.time(), "log": path, "fh": fh}
    return [f"{module}: started in the background (pid {proc.pid}), "
            f"output in {path.relative_to(ROOT)}"]


def reap_children(log=print, now: float | None = None) -> list[str]:
    """Log every weekly child that has finished since the last cycle, and
    cut off any that has run past its ceiling. Called every cycle."""
    import time as _time
    now = _time.time() if now is None else now
    out = []
    for module, c in list(_CHILDREN.items()):
        proc = c["proc"]
        code = proc.poll()
        if code is None and now - c["started"] > WEEKLY_JOB_TIMEOUT_S:
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass
            code = proc.wait() if hasattr(proc, "wait") else -9
            out.append(f"⚠️  {module}: cut off after {WEEKLY_JOB_TIMEOUT_S}s")
        if code is None:
            continue
        try:
            c["fh"].close()
        except Exception:  # noqa: BLE001
            pass
        try:
            tail = [ln for ln in c["log"].read_text(encoding="utf-8").splitlines()
                    if ln.strip()][-12:]
        except Exception:  # noqa: BLE001
            tail = []
        mins = (now - c["started"]) / 60.0
        out.append(f"{module}: finished in {mins:.0f} min with exit {code}"
                   + ("" if code == 0 else " ⚠️"))
        out.extend(f"  {ln}" for ln in tail)
        del _CHILDREN[module]
    for line in out:
        log(f"  {line}")
    return out


def _run_deep_refit(log) -> list[str]:
    """The Wednesday deep fitters, out of process and detached.
    Injectable for tests, which must never spawn the real fitters."""
    return _spawn_module("engine.deepfit", log)


def _run_lab(log) -> list[str]:
    """The weekly backtest lab, out of process and detached."""
    return _spawn_module("engine.lab", log, args=("--auto",))


def game_rank_boot_due(store: dict, state: dict, today: _dt.date,
                       sport: str = "mlb") -> bool:
    """Should this pass measure ``sport``'s GAME markets now, not Wednesday?

    Yes when the rank store holds no game-market entry for the sport
    (``kind == "game"`` — a prop entry does not count, the prop
    bootstrap has its own test) and this box has not already tried
    today. Once a day, not once a pass: `gamerank.measure` walks every
    scored game the box holds, and a box whose closes cannot yet clear
    `gamerank.MIN_GAMES` would otherwise walk them every forty-five
    minutes for nothing. Pure, so it can be tested without a database.
    """
    for k, v in (store or {}).items():
        if k.startswith(f"{sport}:") and isinstance(v, dict) and v.get("kind") == "game":
            return False
    tried = (state or {}).get("game_rank_boot") or {}
    return tried.get(sport) != today.isoformat()


def run_if_due(force: bool = False, harvest: bool = True, log=print,
               state_path: Path | None = None, today: _dt.date | None = None) -> bool:
    """Run the daily chores if they haven't run yet today.

    Returns True when the chores ran (successfully or not), False when they
    were already done today. A failed results ingest leaves the day unmarked
    so the next cycle retries; everything else is best-effort.
    """
    state_path = state_path or STATE_PATH
    today = today or _dt.date.today()
    # Every cycle, before the once-a-day gate: the weekly children an
    # earlier cycle started are logged when they finish, or cut off.
    reap_children(log)
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

        # The same idea for college football, and a bigger hole. The CFB
        # model fits its own scoring baseline, home-field edge and
        # margin/total spread from finished games — and this database
        # held ONE, so every college board was priced from a prior and
        # sat on probation: journaled and graded, never staked. ESPN's
        # scoreboard cannot fix that (it answers one day at a time, and
        # a standard egress policy refuses it); whole finished seasons
        # come down the same raw.githubusercontent.com path the NFL
        # schedules use. Guarded on the game count, so it runs on a box
        # that needs it and skips silently on one that does not.
        try:
            from . import db as _cdb
            from .ingest import ingest_cfb_history
            from .cfb.ratings import MIN_GAMES as _CFB_MIN
            _cconn = _cdb.connect()
            have = _cconn.execute(
                "SELECT COUNT(*) FROM games WHERE sport='cfb' "
                "AND home_score IS NOT NULL").fetchone()[0]
            # AND THE SEASON BEING PLAYED, EVERY NIGHT. The guard above
            # was the whole condition until 2026-09-06: once the backfill
            # had landed its four seasons, `have` sat far above the bar
            # and this block never ran again — so no 2026 college result
            # ever reached the games table. Nothing else writes one.
            #
            # What that cost, exactly (measured in tests/test_cfb_settles.py):
            # `settle_from_history` grades a game bet — moneyline, spread,
            # total, team total — only from a `games` row on the bet's own
            # date. With none, every college game bet stayed OPEN for ever,
            # while the props settled on the Monday player-log refresh. So
            # the record page showed a college book that had recommended
            # dozens of bets and settled a handful. Ethan, 2026-09-06:
            # "CFB doesn't seem to have settled its bets."
            #
            # Its two siblings below — the closes and the player logs —
            # already had an in-season refresh; the results, which are what
            # actually settle money, were the one that did not. Daily
            # rather than their Monday, because a Saturday bet should
            # settle on Sunday, and cheap: one cached CSV off the same
            # mirror. `parse_schedule` writes only games with a final
            # score and `upsert_games` merges with COALESCE, so a refresh
            # can neither invent a scoreless row nor erase the closing
            # lines the lines pass attached.
            season = today.year if today.month >= 8 else today.year - 1
            in_season = today.month >= 8 or today.month <= 1
            backfill = have < _CFB_MIN
            seasons = ([today.year - n for n in (4, 3, 2, 1)] if backfill
                       else ([season] if in_season else []))
            # The stored rows first, or the refresh writes correct keys
            # beside three thousand unjoinable ones. Idempotent and cheap
            # once done: the scan finds nothing on the next night.
            from .ingest import remap_cfb_game_ids
            _fix = remap_cfb_game_ids(_cconn)
            if _fix["renamed"] or _fix["merged"]:
                log(f"  cfb keys: {_fix['renamed']:,} game(s) rekeyed to "
                    f"away@home, {_fix['merged']:,} duplicate(s) merged — "
                    f"college totals can be graded now")
            if seasons:
                res = ingest_cfb_history(
                    _cconn, seasons, quiet=True,
                    ttl=None if backfill else CFB_RESULTS_TTL)
                log(f"  cfb backfill: {res['games']:,} FBS games ingested "
                    f"across {len(res['seasons'])} season(s) — the model's "
                    f"variance is now measured, not assumed" if backfill else
                    f"  cfb results: {res['games']:,} finished {season} game(s) "
                    f"on file — college game bets settle from these")
                for s_ in res["skipped"]:
                    log(f"  ⚠️  {s_}")
        except Exception as exc:  # noqa: BLE001
            log(f"  ⚠️  cfb history backfill failed: {exc}")

        # THE CLOSING NUMBERS, which the results backfill deliberately
        # left NULL. Without them `engine.gamecal` cannot measure college
        # football's market haircut and the board prices spreads and
        # totals against a flat guess — the standing item on this site's
        # own doctor. Guarded on the count, then refreshed weekly in
        # season so the current year's closes keep arriving.
        try:
            from . import db as _ldb
            from .ingest import ingest_cfb_lines
            _lconn = _ldb.connect()
            have = _lconn.execute(
                "SELECT COUNT(*) FROM games WHERE sport='cfb' "
                "AND spread IS NOT NULL").fetchone()[0]
            season = today.year if today.month >= 8 else today.year - 1
            seasons = None
            if have < CFB_MIN_CLOSES:
                seasons = [today.year - n for n in (4, 3, 2, 1)]
            elif today.weekday() == 0:
                seasons = [season]
            if seasons is not None:
                res = ingest_cfb_lines(_lconn, seasons, quiet=True)
                log(f"  cfb closes: {res['spread']:,} spread(s) and "
                    f"{res['total']:,} total(s) attached — the college "
                    f"board can be graded against the market now")
                for s_ in res["skipped"]:
                    log(f"  ⚠️  {s_}")
        except Exception as exc:  # noqa: BLE001
            log(f"  ⚠️  cfb closing lines failed: {exc}")

        # THE PLAYER HALF, AND THE ONE THE BOARD ACTUALLY SHOWS. Results
        # let the CFB model measure its own variance; player rows are
        # what engine/cfb/tds.py needs to name a scorer at all — its
        # first rule is that a quoted player with no ingested usage gets
        # no pick. This database held TEN CFB player rows, so the college
        # touchdown board could price nobody. Guarded on the count and
        # refreshed weekly in season: the mirror publishes finished
        # weeks, so Monday (after the weekend, and after any Sunday
        # correction) is when a new week is there to read.
        try:
            from . import db as _pcdb
            from .ingest import ingest_cfb_player_history
            _pconn = _pcdb.connect()
            have = _pconn.execute(
                "SELECT COUNT(*) FROM player_game_logs WHERE sport='cfb' "
                "AND market='anytime_td'").fetchone()[0]
            season = today.year if today.month >= 8 else today.year - 1
            seasons = cfb_player_seasons(today, have)
            if seasons:
                res = ingest_cfb_player_history(_pconn, seasons, quiet=True,
                                                fresh=season)
                log(f"  cfb players: {res['rows']:,} log rows across "
                    f"{len(res['seasons'])} season(s), "
                    f"{res['assets']:,} identities — the touchdown board "
                    f"now has usage to price")
                for s_ in res["skipped"]:
                    log(f"  ⚠️  {s_}")
                # AND FIT IT NOW, NOT ON WEDNESDAY. The deep refit that
                # owns `cfb:anytime_td` runs weekly; college football
                # plays on Saturday. On a box that has just ingested its
                # first four seasons, waiting for the next deep-refit day
                # means the first weekend of the season is priced on the
                # neutral correction the board has carried since it
                # shipped — while the measurement says the model is
                # conservative by five points in the longshot band. The
                # guard above only lets the backfill run once, so this
                # runs once with it.
                if have < CFB_MIN_PLAYER_ROWS and res["rows"]:
                    from .deepfit import refit_cfb_touchdowns
                    for line in refit_cfb_touchdowns():
                        log(f"  {line}")
                # AND RANK THE YARDAGE MARKETS ON THE SAME LOGS, for the
                # same reason and on the same schedule. College's four
                # yardage/reception markets have a model (the shared
                # football chain) and, until this box walks them, no
                # measurement — so `likely.rank_auc("cfb", "rush_yds")`
                # is None and the shelf stays shut. That is correct and
                # it is also not a state to leave a season sitting in:
                # the logs that answer the question have just landed on
                # this disk. `rankfit.measure` is idempotent and writes
                # only what MIN_PAIRS supports, so running it beside the
                # backfill costs one walk and can only ever turn a shelf
                # on with evidence behind it.
                if res["rows"]:
                    try:
                        from .rankfit import measure as _cfb_rank
                        for line in _cfb_rank(_pconn, "cfb", log=lambda _s: None):
                            log(f"  {line}")
                    except Exception as _rexc:  # noqa: BLE001
                        log(f"  ⚠️  cfb rank fit skipped: {_rexc}")
        except Exception as exc:  # noqa: BLE001
            log(f"  ⚠️  cfb player backfill failed: {exc}")

        # Play-by-play refresh — the measured red-zone roles. The file is
        # ~100MB, so once a week (Tuesdays, after Monday night) is the
        # right cadence, not daily…
        #
        # …UNLESS THE UNIT RATINGS ARE BEHIND THE LAST WEEK PLAYED, and
        # then every night until they are not (engine/freshness). One
        # failed Tuesday used to leave the matchup tape a week behind with
        # nothing to retry it — found 2026-09-25, when the tape was read
        # as stale ("we are pulling ... 2025 information").
        _units_behind = False
        try:
            from . import db as _fdb, freshness as _fresh
            _units_behind = "unit ratings" in _fresh.football_weeks(_fdb.connect(), "nfl", today)["behind"]
        except Exception:                                       # noqa: BLE001
            _units_behind = False
        if today.weekday() == 1 or _units_behind:
            try:
                from . import db as _pdb
                from .sources.nflpbp import (load_pbp_rows, aggregate_pbp,
                                             xfp_player_rows)
                from .sources.nflunits import Units, UNIT_COLS
                season = today.year if today.month >= 8 else today.year - 1
                # The unit ratings the matchup scan ranks (engine/gamescan)
                # ride the same read of the file.
                units = Units()
                agg = aggregate_pbp(load_pbp_rows(season, columns=UNIT_COLS),
                                    also=units.add)
                _pc = _pdb.connect()
                n = _pdb.upsert_player_logs(_pc, xfp_player_rows(agg, season))
                n_u = _pdb.upsert_team_units(_pc, units.rows(season))
                if n or n_u:
                    log(f"  nfl pbp: {n:,} xFP/red-zone rows, {n_u:,} unit rows refreshed")
            except Exception as exc:  # noqa: BLE001
                log(f"  ⚠️  nfl pbp refresh failed: {exc}")

    # The DEEP fitters, weekly. `engine.journalfit` already refits every
    # sport off the journal on every settle pass — that is the universal
    # rung and it is not what this is. These three walk the HISTORY DB
    # through the sport's own engine, which is the stronger fit and the
    # slow one (one walk-forward per grid point, 21 per market), and
    # they were CLI-only: `--sport` defaults to mlb, so unless somebody
    # typed the flag only baseball had ever been deep-fitted. launch.py
    # flagged that on 2026-08-16 and it stayed true.
    #
    # It is worth automating because it is not a formality. Run against
    # the NFL's 329,434 ingested log rows for the first time on
    # 2026-08-27, the recency dial moved three of four markets on 20,000+
    # settled predictions each. Every fitter here has its own adoption
    # gate (MIN_SAMPLES, a Brier margin, a plateau check), so a sport
    # without the sample simply declines — the schedule can be generous
    # because the fitters are not.
    #
    # Wednesdays, and ORDER MATTERS: dial, then memory, then temperature
    # last, because the first two move the model the third is calibrating.
    # `refit_order` is the same sequence launch.py's command runs.
    # `today`, not the wall clock: every other weekday gate in this
    # function reads the parameter, and this one alone read the real
    # date — so on a Wednesday the test suite's fake July Saturdays
    # launched the REAL fitters against the box's history.db and hung
    # for 15 minutes (found 2026-09-02, a Wednesday).
    if today.weekday() == 2 and state.get("deep_attempted") != today.isoformat():
        # THE MARKER IS WRITTEN BEFORE THE WORK, and that is the whole
        # fix. On Wednesday 2026-09-02 the deep refit ran here, IN THE
        # SERVER PROCESS, for the first time in production. It loads
        # every ingested season and replays every prop week by week; the
        # process passed the unit's 1600 MB cap and the OOM killer took
        # it — the server, port and all. `last_done` is written at the
        # END of this function, so the day was never marked, systemd
        # restarted the unit three seconds later, the first cycle ran
        # the chores again, and the site cycled up-for-two-minutes,
        # dead-for-three from 01:24 to the afternoon: 223 kills, and the
        # StartLimit guard never fired because it counts restarts per
        # minute and this loop was slower than that.
        #
        # Two things follow. The attempt is recorded before it starts,
        # so a job that dies takes one day off rather than every cycle
        # of it. And the fitters run in a CHILD process (below), so if
        # the box cannot afford them the child is what the kernel
        # takes, and the site keeps serving.
        state["deep_attempted"] = today.isoformat()
        _save_state(state_path, state)
        try:
            for line in _run_deep_refit(log):
                log(f"  {line}")
        except Exception as exc:  # noqa: BLE001
            log(f"  ⚠️  deep refit skipped: {exc}")
        # #77, answered on the box that can: does the market shrink help
        # or hurt the top of the likelihood board? The replay says the
        # top still underclaims after the fitted temperature (top-1 60.0%
        # claimed, 67.4% landed) while the page prints a number shrunk
        # halfway to the book — and only a join to HARVESTED CLOSES can
        # say whether that shrink is closing the gap or dragging good
        # numbers toward a lazy consensus. The dev box has no
        # odds_history, so the report refuses there and answers here,
        # weekly, in this log — where the question was going to be asked
        # anyway the next time the board had a big Sunday.
        try:
            from . import db as _sdb
            from .tdbook import board_priced, shrink_report
            _sc = _sdb.connect()
            try:
                for line in shrink_report(board_priced(_sc)):
                    log(f"  {line}")
            finally:
                _sc.close()
        except Exception as exc:  # noqa: BLE001
            log(f"  ⚠️  shrink check skipped: {exc}")
        # #65's tracker, on the same weekly clock. devigfit measures how
        # the touchdown market's vig is SHARED OUT across prices — its
        # band table is where "the +455 to +800 band charges double" was
        # found — and it was CLI-only, so the finding could never
        # re-measure as closes accrued. It needs odds_history, refuses
        # thin splits itself, and answers on the box that harvests.
        try:
            from . import db as _vdb
            from .devigfit import collected, report_lines
            _vc = _vdb.connect()
            try:
                for _sp in ("nfl", "cfb"):
                    rows = collected(_vc, sport=_sp)
                    if not rows:
                        log(f"  devig bands ({_sp}): no joined closes on "
                            f"this box — the question stays open")
                        continue
                    log(f"  devig bands ({_sp}): {len(rows):,} player-weeks "
                        f"with a real close")
                    for line in report_lines(rows):
                        log(f"  {line}")
            finally:
                _vc.close()
        except Exception as exc:  # noqa: BLE001
            log(f"  ⚠️  devig band check skipped: {exc}")
        # The ranking fitter behind every likelihood board that is not
        # running on a hand-measured constant: measures each market's
        # walk-forward AUC on this box's own logs and stores what the
        # sample supports. likely.rank_auc reads the store, so an MLB
        # shelf turns on HERE, where the logs are — the dev box has no
        # MLB logs at all and can never claim one.
        #
        # CFB joined the list on 2026-09-03. Its four yardage markets
        # walk the SHARED football chain and are measured on COLLEGE
        # logs, which is the whole discipline: the touchdown board once
        # wore the NFL's 0.721 because nobody had measured college, and
        # a yardage board shipped on the NFL's 0.761 would be the same
        # mistake with a different number.
        try:
            from . import db as _rkdb
            from .rankfit import context_report as _rank_ctx
            from .rankfit import measure as _rank_measure
            _rkc = _rkdb.connect()
            try:
                # ONE SPORT'S FAILURE IS ONE SPORT'S. Until 2026-09-15
                # the four measurements, the park report and the game
                # markets below shared one try: a walk that raised for
                # any sport skipped every sport after it AND the game
                # markets, and the log said "rank fit skipped" once. The
                # MLB moneyline shelf depends on the last thing in this
                # block running, so it has to run whatever came before.
                for _sp in ("mlb", "wnba", "nba", "cfb"):
                    try:
                        _rank_measure(_rkc, _sp, log=log)
                    except Exception as _rexc:  # noqa: BLE001
                        log(f"  ⚠️  rank fit {_sp} skipped: {_rexc}")
                # THE PARK A/B, ANSWERED WHERE THE LOGS ARE. The standing
                # finding (2026-08-31): the walk replays history in a
                # NEUTRAL stadium, so the venue layer the MLB handicapping
                # script wired in is invisible to the store's AUCs. The
                # one-liner that measures it was never pasted on the
                # droplet, so the question sat unanswered — now the weekly
                # log answers it by itself. It still WRITES NOTHING:
                # adoption is a decision for whoever reads the deltas.
                try:
                    _rank_ctx(_rkc, "mlb", log=log)
                except Exception as _cexc:  # noqa: BLE001
                    log(f"  ⚠️  park A/B report skipped: {_cexc}")
                # GAME MARKETS, the same discipline. engine.gamerank
                # replays each league's stored closes and writes the
                # moneyline / spread / total ranking into the same
                # store, so an MLB moneyline can earn its shelf on the
                # one box that holds the MLB games (Ethan, 2026-09-02:
                # "we have no money lines or spreads or totals").
                from .gamerank import measure_and_store as _game_rank
                for _sp in ("mlb", "nfl", "cfb"):
                    try:
                        _game_rank(_rkc, _sp, log=log)
                    except Exception as _gexc:  # noqa: BLE001
                        log(f"  ⚠️  game rank {_sp} skipped: {_gexc}")
            finally:
                _rkc.close()
        except Exception as exc:  # noqa: BLE001
            log(f"  ⚠️  rank fit skipped: {exc}")
        # WHEN we bet, graded against the close — the cut that turns
        # "bet early" from folklore into this book's own instruction.
        try:
            from . import ledger as _clvled
            from .clvboard import leadtime_lines
            _cc = _clvled.connect()
            try:
                for line in leadtime_lines(_cc):
                    log(line)
            finally:
                _cc.close()
        except Exception as exc:  # noqa: BLE001
            log(f"  ⚠️  lead-time CLV skipped: {exc}")

        # The per-sport Most Likely scoreboard — the standing order
        # ("don't stop testing each sport until the most likely for
        # each sport is making money") run as an instrument. One line
        # per sport, every week: calibration gap, ROI, and either a
        # verdict-eligible sample or the honest distance to one.
        try:
            from . import ledger as _lkled
            _lc = _lkled.connect()
            try:
                _rep = _lkled.likely_report(_lc)
                for _sp, _e in sorted((_rep.get("by_sport") or {}).items()):
                    line = (f"  likely book {_sp}: {_e['n']} settled, "
                            f"claimed {(_e['claimed'] or 0) * 100:.0f}% → "
                            f"landed {(_e['actual'] or 0) * 100:.0f}%, "
                            f"ROI {_e['roi'] * 100:+.1f}%")
                    log(line + ("" if _e.get("enough")
                                else f" ({_e.get('note', '')})"))
                    # The game rows, per market, under their sport —
                    # so a lean shelf that drags the book is named
                    # rather than averaged away.
                    for _mk, _g in sorted(
                            ((_rep.get("by_sport_market") or {})
                             .get(_sp) or {}).items()):
                        log(f"    {_mk}: {_g['n']} settled, claimed "
                            f"{(_g['claimed'] or 0) * 100:.0f}% → landed "
                            f"{(_g['actual'] or 0) * 100:.0f}%, ROI "
                            f"{_g['roi'] * 100:+.1f}%")
            finally:
                _lc.close()
        except Exception as exc:  # noqa: BLE001
            log(f"  ⚠️  likely scoreboard skipped: {exc}")

    # BOOTSTRAP: a box holding a sport's logs with an EMPTY rank store
    # measures now rather than waiting for Wednesday — the same "fit it
    # now, not on Wednesday" precedent the CFB touchdown backfill set.
    # Without this, "most likely for MLB" ships and then sits dark for
    # up to a week on the one box that could light it.
    try:
        from . import db as _rbdb
        from .rankfit import load as _rank_load, measure as _rank_boot
        _rbs = _rank_load()
        _rbc = _rbdb.connect()
        try:
            for _sp in ("mlb", "wnba", "nba"):
                if any(k.startswith(f"{_sp}:") for k in _rbs):
                    continue
                have = _rbc.execute(
                    "SELECT COUNT(*) FROM player_game_logs WHERE sport=?",
                    (_sp,)).fetchone()[0]
                if have:
                    log(f"  rank store has no {_sp} entry and {have:,} "
                        f"log rows exist — measuring now, not Wednesday")
                    _rank_boot(_rbc, _sp, log=log)
        finally:
            _rbc.close()
    except Exception as exc:  # noqa: BLE001
        log(f"  ⚠️  rank bootstrap skipped: {exc}")

    # THE GAME MARKETS BOOTSTRAP, same precedent. Ethan, 2026-09-15: "MLB
    # most likely bets are only showing hits and total bases. There is
    # no money lines ... or game totals or anything like that." An MLB
    # moneyline reaches the board only once `gamerank` has written a
    # figure into the rank store, and the only thing that wrote one was
    # the Wednesday block above — so a box that missed a Wednesday, or
    # whose Wednesday block raised before it got there, showed no game
    # line for a week at a time. The prop shelves have bootstrapped since
    # 2026-08-31; the game shelf did not, and this is it catching up.
    # The marker is written BEFORE the work (the deep-refit rule) and
    # once a day (`game_rank_boot_due`), so a box whose closes cannot yet
    # clear the sample floor tries tomorrow rather than every pass.
    try:
        from . import db as _gbdb
        from .gamerank import measure_and_store as _game_boot
        from .rankfit import load as _grank_load
        if game_rank_boot_due(_grank_load(), state, today):
            _gbc = _gbdb.connect()
            try:
                have = _gbc.execute(
                    "SELECT COUNT(*) FROM games WHERE sport='mlb' "
                    "AND home_score IS NOT NULL").fetchone()[0]
                if have:
                    state.setdefault("game_rank_boot", {})["mlb"] = today.isoformat()
                    _save_state(state_path, state)
                    log(f"  rank store has no mlb game market and {have:,} "
                        f"scored games exist — measuring now, not Wednesday")
                    _game_boot(_gbc, "mlb", log=log)
            finally:
                _gbc.close()
    except Exception as exc:  # noqa: BLE001
        log(f"  ⚠️  game rank bootstrap skipped: {exc}")

    # Settle the one-sided quote journals against whatever stat rows the
    # ingests above just wrote, and refit each market's measured hold
    # once its sample clears the gate (engine/holdwatch — the number
    # that retires "vig assumed at 6%").
    #
    # OUTSIDE the NFL-season guard on purpose: it lived inside it at
    # first, which was fine while touchdowns were the only market and
    # became wrong the moment MLB home runs joined — baseball settles
    # from April, and a journal that only settles Aug-Feb would have
    # thrown a summer of quotes away. The pass is a handful of indexed
    # queries and a no-op when nothing is waiting, so running it daily
    # costs nothing.
    for _hsport, _hmarket in HOLD_MARKETS:
        try:
            from . import db as _qdb
            from . import holdwatch as _hw
            _qconn = _qdb.connect()
            _ns = _hw.settle(_qconn, sport=_hsport, market=_hmarket)
            if _ns:
                log(f"  hold journal ({_hsport} {_hmarket}): {_ns} quote(s) settled")
            _fit = _hw.fit(_qconn, sport=_hsport, market=_hmarket)
            if _fit:
                log(f"  hold measured ({_hsport} {_hmarket}): "
                    f"{_fit['hold'] - 1:.1%} off {_fit['n']:,} settled quotes")
        except Exception as exc:  # noqa: BLE001
            log(f"  ⚠️  hold journal ({_hsport} {_hmarket}) skipped: {exc}")

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

    # PLAYER FACES, EVERY SPORT. Ethan, 2026-09-04: "I see some players
    # on nfl don't have any."
    #
    # `facesfill` has existed since 2026-08-18 and had NEVER RUN ON A
    # SCHEDULE — no caller in launch.py, no line in any deploy script,
    # only a human typing it. Its own docstring explains why nothing else
    # can do this job: the photo URL is captured DURING ingest, and
    # ingest skips days it has already stored, so a player whose days
    # were all stored before faces existed can never pick one up. That is
    # a one-way ratchet, and the only thing that releases it is this,
    # running.
    #
    # Measured in this checkout: `player_assets` held 5,766 college rows
    # and NOT ONE for nfl, mlb, nba or wnba — which is exactly what the
    # facesfill header predicts ("NOTHING has ever written NFL rows to
    # that table"). The fantasy player profile reads that table for its
    # face, so those cards drew initials while the identifiers to build a
    # URL sat in the same database.
    #
    # HERE RATHER THAN IN THE NIGHTLY, because this function is the
    # once-a-day hook BOTH paths call — `nightly_run`'s first step and
    # the server's own `_startup_chores`/`_background_refresher`. Wiring
    # it to the nightly alone would leave it unrun on any box where the
    # nightly is the thing that broke, which is the failure mode this
    # module's docstring is about.
    #
    # Never fatal and safe to repeat: `upsert_player_assets` keys on
    # (sport, player) and an empty value never clobbers a stored one, so
    # the worst case of a bad day is the faces it already had.
    try:
        import facesfill
        from . import db as _fdb
        _fconn = _fdb.connect()
        _filled = []
        for _sport in ("nfl", "mlb", "nba", "wnba"):
            try:
                _n, _before, _after = facesfill.fill(_fconn, _sport)
            except Exception as exc:                          # noqa: BLE001
                log(f"  ⚠️  faces ({_sport}) skipped: {exc}")
                continue
            if _after > _before:
                _filled.append(f"{_sport} {_before}->{_after}")
        log("  faces: " + (", ".join(_filled) if _filled
                           else "nothing new to fill"))
    except Exception as exc:                                  # noqa: BLE001
        log(f"  ⚠️  faces backfill skipped: {exc}")

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
