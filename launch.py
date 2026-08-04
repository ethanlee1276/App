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
WNBA_OUT = "web/data/wnba.json"
UFC_OUT = "web/data/ufc.json"
CFB_OUT = "web/data/cfb.json"
# One bulk request covers h2h + spreads + totals for the whole
# board, so the cost is per-market, not per-game.
CFB_ODDS_COST = 3


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
    live = sum(1 for p in (MLB_OUT, NFL_OUT, NBA_OUT, WNBA_OUT, CFB_OUT)
               if _slate_games(p) > 0)
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


def _odds_affordable(out_path: str, quiet: bool, sport: str | None = None,
                     cost: int | None = None) -> bool:
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
    # Cost is normally one request per game (player props are event-scoped).
    # A sport that pulls its whole board in one call passes its real cost
    # instead — charging CFB sixty credits for a three-credit request would
    # mean the pacer never authorised a single Saturday.
    ok, reason = should_refresh(cost if cost is not None
                                else _games_on_slate(out_path) + 1,
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
    # --injuries was never passed here, so §7's ripple model — the layer
    # that holds a clouded player's props and boosts the beneficiaries —
    # sat unfetched with the coverage scan promising it "refreshes with
    # the launcher". It does now. The feed is free and cached, and
    # nfl_build already degrades to a warning when it cannot be reached,
    # so this cannot cost a build.
    args = ["nfl_build.py", str(season), str(week), "--out", out, "--injuries"]
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


def refresh_sport_rosters(quiet: bool = False) -> bool:
    """Per-sport roster tabs. Zero network — reads our own game logs.

    The NFL's rosters come off the players feed inside `fantasy_build`;
    everything else is built from who actually appeared for a team, which
    is a second reading of history the nightly ingest already stores.
    """
    ok, tail = _run_build(["rosters_build.py"])
    if not quiet:
        print(f"  ROS  rosters: {'refreshed' if ok else 'unavailable'}"
              + (f"  ({tail})" if not ok and tail else ""))
    return ok


def refresh_standings(quiet: bool = False) -> bool:
    """Standings and the postseason bracket. Zero network — both are
    counted from the same finished games every other board reads, so they
    cannot disagree with the records shown beside them."""
    ok, tail = _run_build(["standings_build.py"])
    if not quiet:
        print(f"  STD  standings: {'refreshed' if ok else 'unavailable'}"
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


def refresh_wnba(quiet: bool = False) -> bool:
    """WNBA slate — the same Scalpy build with --league wnba.

    Paced exactly like NBA, including the games>0 gate: the schedule comes
    from a free keyless CDN, so "is there a slate tonight" is answerable
    before spending anything. The season runs May-September, so this is the
    one board that is live while the NBA's is dark."""
    args = ["nba_build.py", _slate_date(), "--league", "wnba",
            "--out", WNBA_OUT]
    spend = _slate_games(WNBA_OUT) > 0 and _odds_affordable(WNBA_OUT, quiet,
                                                            sport="wnba")
    before_seen = _paid_pull_baseline() if spend else ""
    if spend:
        args.append("--odds")
    elif _with_odds():
        args.append("--cached-odds")
    ok, tail = _run_build(args)
    _finish_paid_pull(spend, before_seen, ok, tail, "WNBA", sport="wnba")
    if not quiet:
        print(f"  WNBA {_slate_date()}: {'refreshed' if ok else 'unavailable'}"
              + (f"  ({tail})" if not ok and tail else ""))
    return ok


def refresh_cfb(quiet: bool = False) -> bool:
    """College football — one bulk odds request for the whole board.

    Everything except the prices is keyless (ESPN), so the schedule,
    conferences, rankings and results refresh on every cycle for free; only
    the lines are metered. And they are metered CHEAPLY here: full-game
    markets come back for the entire slate in a single call, so a 60-game
    Saturday costs the same three credits as a four-game Tuesday. That is
    why this passes an explicit cost instead of the games-on-slate default.
    """
    args = ["cfb_build.py", _slate_date(), "--out", CFB_OUT]
    spend = _slate_games(CFB_OUT) > 0 and _odds_affordable(
        CFB_OUT, quiet, sport="cfb", cost=CFB_ODDS_COST)
    before_seen = _paid_pull_baseline() if spend else ""
    if spend:
        args.append("--odds")
    elif _with_odds():
        args.append("--cached-odds")
    ok, tail = _run_build(args)
    _finish_paid_pull(spend, before_seen, ok, tail, "CFB", sport="cfb")
    if not quiet:
        print(f"  CFB  {_slate_date()}: {'refreshed' if ok else 'unavailable'}"
              + (f"  ({tail})" if not ok and tail else ""))
    return ok


# A fighter is ~50 small cached requests, about half a minute cold. The
# refresh loop runs every 60s, so drafting a few per tick lets a 34-bout
# card fill itself in over a few minutes instead of stalling one refresh
# for half an hour. Progress is saved as it goes.
DOSSIERS_PER_TICK = 4


def _auto_dossiers(quiet: bool = False) -> None:
    """Draft the upcoming card's missing fighter dossiers, unprompted.

    "No dossier, no bet" is the right rule and it was also, in practice,
    the reason most of a card never got modelled: drafting was a command
    you had to remember to run. A card the site knows about is a card the
    site can look up on its own. Hand-written dossiers are never touched.
    """
    try:
        import ufc_dossiers as UD
        _label, names = UD.card_fighters()
        if not names:
            return
        book = UD.load_book()
        todo = [n for n in names if UD.needs_draft(book, n)]
        if not todo:
            return
        _b, drafted, _kept, missing = UD.draft(todo,
                                               limit=DOSSIERS_PER_TICK)
        left = len(todo) - len(drafted) - len(missing)
        if not quiet and (drafted or left):
            note = f"  UFC  dossiers: drafted {len(drafted)}"
            if left:
                note += f", {left} still to draft (a few per refresh)"
            if missing:
                note += (f", {len(missing)} not on ESPN (debut/spelling) — "
                         f"skipped for a day so they stop crowding out the "
                         f"fighters that can be drafted")
            print(note)
    except Exception as exc:  # noqa: BLE001 — never let this stop the card
        if not quiet:
            print(f"  UFC  dossiers: auto-draft unavailable ({exc})")


def _auto_weighins(quiet: bool = False) -> None:
    """Pull official weigh-in results for the upcoming card, unprompted.

    Recording these by hand was the one place this system still asked a
    person to type in data, and `--weigh-in` stays available for exactly
    the case a feed cannot cover: you watched the scale on the broadcast
    before anyone published it.
    """
    try:
        from engine.ufc import weighin_feed
        res = weighin_feed.refresh()
        if not quiet and res.get("recorded"):
            print(f"  UFC  weigh-ins: recorded {res['recorded']} "
                  f"({res['made']} made, {res['missed']} missed) "
                  f"from {res['source']}")
        elif not quiet and res.get("note"):
            print(f"  UFC  weigh-ins: {res['note']}")
    except Exception as exc:  # noqa: BLE001
        if not quiet:
            print(f"  UFC  weigh-ins: auto-pull unavailable ({exc})")


def refresh_ufc(quiet: bool = False) -> bool:
    """UFC card (Scalpy MMA) — a real member of the paid-pull rotation.

    It was cached-ONLY, which is precisely the bug NBA had and had fixed:
    with every call reading cache and nothing ever writing it, the event
    list came back empty forever, ``select_card`` found no bouts, and the
    page said "no card" straight through fight night. A card that can only
    be read from a cache nothing seeds is a card that never appears.

    It now paces on its own clock like the others. There is deliberately
    no games>0 gate — for UFC the card only EXISTS in the payload once a
    pull has happened, so gating the pull on the card is circular, which
    is the same knot in a different rope.
    """
    _auto_dossiers(quiet)
    _auto_weighins(quiet)
    args = ["ufc_build.py", "--out", UFC_OUT]
    spend = _odds_affordable(UFC_OUT, quiet, sport="ufc")
    before_seen = _paid_pull_baseline() if spend else ""
    if spend:
        args.append("--odds")
    elif _with_odds():
        args.append("--cached-odds")
    ok, tail = _run_build(args)
    _finish_paid_pull(spend, before_seen, ok, tail, "UFC", sport="ufc")
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
    refresh_wnba(quiet=quiet)
    refresh_cfb(quiet=quiet)
    refresh_ufc(quiet=quiet)
    refresh_sport_rosters(quiet=quiet)
    refresh_standings(quiet=quiet)
    _arbitrate_parlays(quiet=quiet)
    _journal_parlays(quiet=quiet)
    _seal_forecasts(quiet=quiet)
    _run_futures(quiet=quiet)


def _seal_forecasts(quiet: bool = False) -> None:
    """Chain tonight's picks into the forecast log — LAST, after everything
    that journals a bet has run.

    A sweep rather than a hook on each INSERT. Eight-plus places write a
    bet and a new one appears every time a sport does; a per-site hook is
    one somebody forgets, and a forecast log with a hole in it is worse
    than none, because it still looks complete. This cannot be forgotten
    and it is idempotent.
    """
    try:
        from engine import ledger as _led
        conn = _led.connect()
        n = _led.seal_forecasts(conn)
        v = _led.verify_forecast_log(conn)
        conn.close()
        if not quiet and n:
            print(f"  forecast log   : +{n} sealed, {v['n']} total, "
                  f"head {(v['head'] or '')[:12]}")
        if not v["ok"]:
            # Loud regardless of quiet: this is the one failure on the site
            # that means a published claim is no longer provable.
            print(f"  ⚠️  FORECAST LOG BROKEN at #{v['broken_at']} — "
                  f"verified through #{v.get('verified_through')}")
    except Exception as exc:                           # noqa: BLE001
        if not quiet:
            print(f"  ⚠️  forecast log seal failed: {exc}")


def _journal_parlays(quiet: bool = False) -> None:
    """§11: log tonight's tickets. Runs after the arbitration, not before.

    The arbitration is what decides which single ticket §10.2 would have
    allowed, and it can only run once every board exists — so journaling
    ahead of it would record every night's play as "not the play".

    Re-entrant by design: this fires on every 60s refresh, and log_board
    keys on the legs themselves, so a ticket journals once per slate no
    matter how many times the board is rebuilt around it.
    """
    try:
        from engine import ledger as _led, parlayledger
        conn = _led.connect()
        r = parlayledger.journal_built_boards(conn, ROOT)
        conn.close()
        if not quiet and r["journaled"]:
            print(f"  Parlay journal: {r['journaled']} new ticket(s) tracked "
                  f"(graded, never staked).")
        if not quiet:
            for s in r["skipped"]:
                print(f"  ⚠️  parlay journal skipped {s}")
    except Exception as exc:  # noqa: BLE001 — never take the site down
        if not quiet:
            print(f"  ⚠️  parlay journal skipped: {exc}")


def _arbitrate_parlays(quiet: bool = False) -> None:
    """§10.2: one parlay per slate ACROSS ALL SPORTS.

    Each league screens its own board and cannot see the others, so six
    leagues can each publish a play and the operation ends up holding six
    against a rule that permits one. This runs once all the boards exist and
    leaves the single best number standing; the rest keep their cards and
    their ranking and lose only their status as the play.
    """
    try:
        from engine.parlays import arbitrate_slate
        r = arbitrate_slate(ROOT)
        if not quiet and r["boards"]:
            if r["play"]:
                print(f"  Parlay slate cap: {r['play'].upper()} takes the one "
                      f"play; {r['demoted']} other(s) demoted.")
            elif not quiet:
                print("  Parlay slate cap: nothing qualified on any board.")
    except Exception as exc:  # noqa: BLE001 — never take the site down
        if not quiet:
            print(f"  ⚠️  parlay slate cap skipped: {exc}")


def _run_maintenance() -> None:
    """Daily chores (results ingest, journal settle, closing-odds harvest).
    First call of each day does the work; the rest are no-ops."""
    try:
        from engine.maintenance import run_if_due
        run_if_due()
    except Exception as exc:  # noqa: BLE001 — chores must never take the site down
        print(f"  ⚠️  daily maintenance failed: {exc}")


#: Futures move over weeks, and a full MLB season at 20,000 trials takes
#: 3.6 seconds. Four sports on the 60-second loop would burn fourteen
#: seconds of every minute re-answering a question whose answer barely
#: changes. Once a day is generous.
FUTURES_EVERY_HOURS = 24


def _run_futures(quiet: bool = False) -> None:
    """Rebuild the futures boards, at most once a day.

    Free: the simulation reads the history DB and the schedule feeds, all
    of them keyless. Prices are NOT pulled here — futures_build.py --odds
    does that, one credit per sport, and its cache TTL is a week. A page
    rebuild must never be able to spend.
    """
    import time
    stamp = ROOT / "web" / "data" / ".futures_built"
    try:
        if stamp.exists() and (time.time() - stamp.stat().st_mtime) < \
                FUTURES_EVERY_HOURS * 3600:
            return
        import futures_build
        from engine import db as _hdb
        conn = _hdb.connect()
        try:
            for sport in futures_build.SPORTS:
                try:
                    data = futures_build.build(sport, conn, live_odds=False)
                except Exception:                   # noqa: BLE001
                    continue
                (futures_build.OUT / f"futures_{sport}.json").write_text(
                    json.dumps(data, indent=2))
        finally:
            conn.close()
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(time.strftime("%Y-%m-%dT%H:%M:%S"))
        if not quiet:
            print("  Futures: season projections rebuilt (free).")
    except Exception as exc:  # noqa: BLE001 — never take the site down
        if not quiet:
            print(f"  ⚠️  futures rebuild skipped: {exc}")


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


def why_live(sport: str = "mlb") -> None:
    """Account for every open bet: shown on the Live tab, or why not.

    "we are only showing live longshots and not the actual recommended
    player props" is a claim about a difference between two sets, and the
    only way to answer it without guessing is to print both sets and the
    decision made about each row.

    This reads the board the site is ALREADY serving rather than rebuilding
    it, so it costs nothing and describes exactly what you are looking at.
    """
    import json as _json
    from engine import ledger as _led
    from engine.livepicks import assemble_live_picks
    from engine.sources.oddsapi import normalize_name

    path = {"mlb": MLB_OUT, "nfl": NFL_OUT, "nba": NBA_OUT,
            "wnba": WNBA_OUT, "cfb": CFB_OUT}.get(sport, MLB_OUT)
    try:
        d = _json.loads(Path(path).read_text())
    except Exception as exc:
        print(f"can't read {path}: {exc}")
        return

    date = d.get("date", "")
    games = d.get("games") or []
    recs = d.get("recommendations") or []
    shots = d.get("long_shots") or []
    live = d.get("live_picks") or []
    print(f"Live tab — {sport.upper()} slate {date}")
    print(f"  built with {len(games)} game(s), {len(recs)} analyzed prop(s), "
          f"{len(shots)} long shot(s)")
    if d.get("live_picks_error"):
        print(f"  ⚠️  the tracker errored this build: {d['live_picks_error']}")
    n_live_games = sum(1 for g in games
                       if ((g.get("live") or {}).get("state")) == "live")
    print(f"  {n_live_games} game(s) live right now\n")

    conn = _led.connect()
    rows = [dict(r) for r in conn.execute(
        "SELECT player, market, side, line, odds, stake_units, date, category "
        "FROM bets WHERE status='open' AND sport=? ORDER BY date, category",
        (sport,))]
    if not rows:
        print("  The journal has NO open bets for this sport. Nothing to show "
              "is the correct output — check the Record page: they may have "
              "already settled.")
        return

    # The same index the tracker builds, so this cannot drift from it.
    idx = {(normalize_name(r.get("player", "")), r.get("market", "")): "main"
           for r in recs}
    for r in shots:
        idx.setdefault((normalize_name(r.get("player", "")), r.get("market", "")),
                       "long shots")
    # Keyed on the BUCKET too. The same player can hold a bet in two
    # buckets at once — a long shot and a stale-line flag on the same
    # homer — and matching on name+market alone reported the excluded one
    # as shown, which is the exact kind of confident wrong line this
    # report exists to prevent.
    def _key(r):
        return (normalize_name(r.get("player", "")), r.get("market", ""),
                r.get("category", "main"))
    shown = {_key(r) for r in live}
    # If the payload has no live_picks KEY at all, it was written by a build
    # that predates the tracker. Every "not shown" below would then be this
    # one fact wearing five different explanations — so say it once and stop.
    if "live_picks" not in d:
        print("  ⚠️  This slate was built before the open-bet tracker ran.\n"
              "      Nothing below is a verdict about your bets — rebuild "
              "first (the launcher does it on its next cycle), then re-run "
              "this.\n")

    by_cat: dict = {}
    for b in rows:
        by_cat.setdefault(b["category"], []).append(b)
    print(f"  {len(rows)} open bet(s) in the journal, by bucket:")
    for cat, bs in sorted(by_cat.items()):
        n_shown = sum(1 for b in bs if _key(b) in shown)
        flag = "" if cat in ("main", "longshot") else \
            "   ← not eligible for the Live tab by design"
        print(f"    {cat:<16} {len(bs):>4} open · {n_shown} on the Live tab{flag}")

    print("\n  Every open bet, and what happened to it:")
    hdr = (f"    {'player':<22} {'market':<13} {'bucket':<15} "
           f"{'date':<11} verdict")
    print(hdr)
    print("    " + "-" * (len(hdr) - 4))
    for b in rows:
        key = _key(b)
        idx_key = key[:2]
        if key in shown:
            row = next(r for r in live if _key(r) == key)
            verdict = f"SHOWN — {row['status']} ({row['phase']})"
        elif b["category"] not in ("main", "longshot"):
            verdict = "excluded — bucket is not tracked live"
        elif b["date"] != date and b["date"] not in _near_dates(date):
            verdict = f"excluded — journaled {b['date']}, slate is {date}"
        elif idx_key not in idx:
            verdict = ("NOT ON EITHER BOARD — the build no longer carries this "
                       "player+market, so it can't be placed on a game")
        else:
            verdict = (f"on the {idx[idx_key]} board but not tracked — no game "
                       f"matched (team/opponent, or the doubleheader leg)")
        print(f"    {str(b['player'])[:21]:<22} {b['market'][:12]:<13} "
              f"{b['category'][:14]:<15} {b['date']:<11} {verdict}")

    main_open = len(by_cat.get("main", []))
    main_shown = sum(1 for b in by_cat.get("main", []) if _key(b) in shown)
    print(f"\n  Player props (category 'main'): {main_open} open, "
          f"{main_shown} on the Live tab.")
    if main_open == 0:
        print("  There are none to show. The main board journals a prop only "
              "when it is RECOMMENDED and staked above zero — on a thin night "
              "that is one or two picks, and they leave this list the moment "
              "they settle.")


def _live_status(live: list, market: str, rows: list) -> None:
    """Say why this bet is or is not on the Live tab.

    The first version told a SETTLED bet to "run --why-live for the mapping
    reason". There is nothing to map: the Live tab shows open bets, the bet
    had already graded, and it left by design. Sending someone to hunt a
    mapping bug for a bet that simply won is the same confidently-wrong
    answer this whole family of reports exists to stop producing.
    """
    shown = [x for x in live if x.get("market") == market]
    if shown:
        x = shown[0]
        print(f"     ✓ ON THE LIVE TAB — {x.get('status')} ({x.get('phase')})")
        return
    graded = [b for b in rows if b["status"] in ("won", "lost", "push")]
    if graded and not any(b["status"] == "open" for b in rows):
        last = graded[-1]
        print(f"     — SETTLED ({last['status']}) on {last['date']}, so it "
              f"left the Live tab by design.\n       It is on the Record "
              f"page. The Live tab only ever holds OPEN bets.")
        return
    if any(b["status"] == "open" for b in rows):
        print("     ✗ open in the journal but NOT on the Live tab — run "
              "`--why-live` for the\n       mapping reason (team, opponent "
              "or doubleheader leg).")
        return
    print("     ✗ no journal row in any bucket.")


def repair_premature_cli(argv: list) -> None:
    """List — and optionally undo — bets graded before their game ended.

        python3 launch.py --repair-premature            # dry run, lists only
        python3 launch.py --repair-premature --apply    # actually repairs

    Dry by default and loudly so. This edits a betting record: it reopens
    bets, reverses the bankroll those bets moved, and deletes the partial
    stat rows they were graded against. None of that is recoverable from
    the app, so --apply takes a backup first.
    """
    from engine import db as _db, ledger as _led
    lconn, hconn = _led.connect(), _db.connect()
    apply = "--apply" in argv

    plan = _led.repair_premature(lconn, hconn, apply=False)
    rows = plan["suspect"]
    if not rows:
        print("\nNo prematurely graded bets found.\n"
              "  Every settled bet's game has a final score stored for that "
              "day.\n")
        return

    print(f"\n{len(rows)} bet(s) graded against a game with no final score "
          f"that day:\n")
    hdr = (f"  {'date':<12}{'player':<22}{'market':<13}{'side':<6}"
           f"{'line':>6}{'graded':>8}{'$':>9}  bucket")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for r in rows:
        print(f"  {str(r['date']):<12}{str(r['player'])[:21]:<22}"
              f"{str(r['market'])[:12]:<13}{str(r['side']):<6}"
              f"{r['line']:>6}{r['status']:>8}{r['pnl_dollars']:>9.2f}"
              f"  {r['category']}")

    unders = [r for r in rows if str(r["side"]).upper() == "UNDER"]
    print(f"\n  {len(unders)} of these are UNDERs — the ones most likely to "
          f"be flatly WRONG.\n  An over already past its line grades early "
          f"but correctly; an under graded\n  in the fourth inning is a "
          f"result that had not happened yet.")
    print(f"\n  Bankroll now      ${plan['bankroll_before']:,.2f}")
    print(f"  Would reverse     ${plan['dollars_reversed']:,.2f}")
    print(f"  Bankroll after    ${plan['bankroll_after']:,.2f}")

    if not apply:
        print("\n  DRY RUN — nothing was changed.\n"
              "  Re-run with --apply to reopen these bets, reverse that "
              "bankroll, and delete\n  the partial stat rows they graded "
              "against. They will settle normally once\n  the games finish "
              "and the results are ingested.\n")
        return

    backup = _backup_before_repair()
    print(f"\n  Backup written: {backup}" if backup else
          "\n  ⚠️  Backup FAILED — stopping rather than editing the journal "
          "with no way back.")
    if not backup:
        return
    done = _led.repair_premature(lconn, hconn, apply=True)
    print(f"  Reopened {len(done['suspect'])} bet(s), deleted "
          f"{done['logs_deleted']} partial stat row(s).")
    print(f"  Bankroll ${done['bankroll_before']:,.2f} → "
          f"${done['bankroll_after']:,.2f}")
    print("\n  Re-ingest once tonight's games are final, then settle:\n"
          "    python3 ingest.py mlb --seasons "
          f"{_dt.date.today().year}\n"
          "    python3 launch.py --settle all\n")


def _backup_before_repair():
    """Copy both databases somewhere safe. Returns the directory or None."""
    import shutil
    from engine import db as _db, ledger as _led
    try:
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = ROOT / "data" / "backups" / f"pre-repair-{stamp}"
        dest.mkdir(parents=True, exist_ok=True)
        for src in (Path(_led.DEFAULT_DB), Path(_db.DEFAULT_DB)):
            if src.is_file():
                shutil.copy2(src, dest / src.name)
        return dest
    except Exception as exc:  # noqa: BLE001
        print(f"  backup failed: {exc}")
        return None


def _goes_nowhere(skip: str) -> bool:
    """Does this skip mean the pick lands in NO bucket at all?

    Two of the four skips route the bet elsewhere rather than dropping it:
    a long shot goes to its own journal, and a non-recommended prop may be
    picked up by the near-miss sampler. Only a zero stake or a proxy price
    means nothing anywhere will ever hold it — and that is the only case
    worth shouting about."""
    return "stake is 0.00u" in skip or "no real book price" in skip


def why_pick(name: str, sport: str = "mlb") -> None:
    """Trace ONE pick from the board to the Live tab, naming every gate.

        python3 launch.py --why-pick "Carter Jensen"

    "we still have props recommended from earlier that are live right now
    but not showing on the live page" is two different failures wearing one
    symptom, and --why-live can only see the second:

      * the pick is on the board but never reached the JOURNAL — in which
        case nothing downstream will ever show it, and the Live tab is
        behaving correctly
      * the pick is in the journal but did not map to a game

    Reading the code to guess between those is how the last three rounds
    went. This walks the actual row.
    """
    import json as _json
    from engine import ledger as _led
    from engine.ledger import journal_skip_reason
    from engine.sources.oddsapi import normalize_name

    path = {"mlb": MLB_OUT, "nfl": NFL_OUT, "nba": NBA_OUT,
            "wnba": WNBA_OUT, "cfb": CFB_OUT}.get(sport, MLB_OUT)
    try:
        d = _json.loads(Path(path).read_text())
    except Exception as exc:
        print(f"can't read {path}: {exc}")
        return

    want = normalize_name(name)
    recs = [r for r in (d.get("recommendations") or [])
            if normalize_name(r.get("player", "")) == want]
    shots = [r for r in (d.get("long_shots") or [])
             if normalize_name(r.get("player", "")) == want]
    live = [r for r in (d.get("live_picks") or [])
            if normalize_name(r.get("player", "")) == want]

    print(f"\nTracing “{name}” · {sport.upper()} slate {d.get('date', '?')}\n")
    if not recs and not shots:
        print(f"  NOT ON THE BUILT BOARD at all ({len(d.get('recommendations') or [])} "
              f"analyzed prop(s) tonight).\n"
              f"  Either the name is spelled differently in the feed, or his "
              f"game is not on\n  this slate, or the board has rebuilt since "
              f"you saw him. Check the spelling\n  the site shows and try "
              f"again.")
        return

    conn = _led.connect()
    for r in recs + shots:
        mkt = r.get("market", "?")
        print(f"  ── {r.get('market_label') or mkt} · "
              f"{r.get('side', '?')} {r.get('line', '?')} ──")
        print(f"     grade {r.get('grade', '?')} · confidence "
              f"{r.get('confidence', 0)} · edge "
              f"{float(r.get('edge') or 0) * 100:.2f}% · stake "
              f"{r.get('stake_units', 0)}u · odds {r.get('odds', '?')}")
        rec_flag = r.get("recommended")
        print(f"     recommended on the board: {bool(rec_flag)}")

        rows = [dict(x) for x in conn.execute(
            "SELECT date, category, status, stake_units FROM bets "
            "WHERE sport=? AND player=? AND market=?",
            (sport, r.get("player"), mkt))]

        skip = journal_skip_reason(r)
        if skip:
            print(f"     ✗ not on the MAIN board's journal — {skip}")
            # A long shot is not missing; it is filed elsewhere, by
            # log_longshots. Saying "the journal has no row for it" here
            # would be a confident wrong answer about a bet sitting in the
            # journal two lines below.
            if rows:
                for b in rows:
                    print(f"     journal: {b['category']} · {b['date']} · "
                          f"{b['status']} · {b['stake_units']}u")
                _live_status(live, mkt, rows)
            elif rec_flag and _goes_nowhere(skip):
                print(f"       THIS IS THE GAP: the board shows it as a pick, "
                      f"no bucket holds it,\n       so it can never appear on "
                      f"the Live tab or the Record page.")
            continue
        print("     ✓ passes every journal gate")
        if not rows:
            print("     ✗ but there is NO journal row — the build that "
                  "recommended it has not\n       journaled yet (journaling "
                  "runs after the tracker in the same pass,\n       so a "
                  "brand-new pick appears on the Live tab one cycle later).")
            continue
        for b in rows:
            print(f"     journal: {b['category']} · {b['date']} · "
                  f"{b['status']} · {b['stake_units']}u")
        _live_status(live, mkt, rows)
    print()


def _near_dates(date: str) -> set:
    """The neighbouring days the tracker also considers, so this report and
    the tracker agree about what 'today' means."""
    try:
        d = _dt.date.fromisoformat(date)
    except ValueError:
        return set()
    return {(d + _dt.timedelta(days=n)).isoformat() for n in (-1, 1)}


def _run_doctor(force: bool = False) -> int:
    """Once a day, say out loud whether anything is wrong.

    The health check has to run HERE, on the laptop, and not in a scheduled
    cloud session — because the databases are gitignored. A fresh clone has
    no journal and no stats, so a remote check would be reporting on a
    machine it cannot see. This is the machine with the data.

    Once per calendar day, printed into the terminal that is already open,
    and silent when everything is fine. A daily line that says "all clear"
    every morning trains you to stop reading it."""
    try:
        import doctor
        from engine.maintenance import STATE_PATH, _load_state, _save_state
        today = _dt.date.today().isoformat()
        state = _load_state(STATE_PATH)
        if not force and state.get("last_doctor_day") == today:
            return 0
        # The suite takes minutes and the refresh loop is on a 60s cycle;
        # a nightly `run_tests.py` here would stall the site's data.
        rep = doctor.run(skip_tests=True)
        state["last_doctor_day"] = today
        _save_state(STATE_PATH, state)
        bad = [c for c in rep.checks if c["status"] != "ok"]
        if bad:
            mark = {"warn": "⚠️ ", "fail": "❌"}
            print(f"\n  Health check — {len(bad)} thing(s) need attention:")
            for c in bad:
                print(f"    {mark[c['status']]} {c['check']}: {c['detail']}")
                if c["fix"]:
                    print(f"       ↳ {c['fix']}")
            print("    (full report: python3 doctor.py)\n")
        return rep.verdict
    except Exception as exc:  # noqa: BLE001 — a check must never stop the site
        print(f"  ⚠️  health check failed: {exc}")
        return 0


def weigh_in_cli(argv: list) -> None:
    """Record a weigh-in, or show what the current card is missing.

        python3 launch.py --weigh-in "Fighter Name" 155.5
        python3 launch.py --weigh-in "Champ Name" 155 --title
        python3 launch.py --weigh-in                 (just show the card)

    The division comes from the fighter's dossier, so the limit — and the
    one-pound non-title allowance — are worked out rather than typed.
    """
    import json as _json
    from engine.ufc import weighin

    args = [a for a in argv[argv.index("--weigh-in") + 1:]
            if not a.startswith("--")]
    title = "--title" in argv
    store = weighin.load_store()

    if len(args) >= 2:
        name, raw = " ".join(args[:-1]), args[-1]
        try:
            weight = float(raw)
        except ValueError:
            print(f"'{raw}' isn't a weight. Usage: --weigh-in \"Name\" 155.5")
            return
        # The division is the dossier's, not something to retype wrong.
        try:
            dossiers = _json.loads(Path("data/ufc_dossiers.json").read_text())
        except (OSError, ValueError):
            dossiers = {}
        from engine.sources.oddsapi import normalize_name
        d = dossiers.get(normalize_name(name)) or {}
        division = d.get("division", "")
        if not division:
            print(f"No dossier for '{name}', so there's no division to check "
                  f"{weight} against. Add the dossier first — this engine "
                  f"doesn't bet fighters it has no dossier for anyway.")
            return
        res = weighin.record(name, weight, division, title_fight=title)
        limit = res.get("limit")
        if res["state"] == "missed":
            print(f"⛔ {name}: {weight} vs {limit} limit — MISSED by "
                  f"{res['over']:g} lb ({division}"
                  f"{', title' if title else ''}).")
            print("   Recorded as a red flag: every bet on this fight is now "
                  "gated off the card, which is what `kill_if` always said.")
        else:
            print(f"✅ {name}: {weight} vs {limit} limit — made weight "
                  f"({division}{', title' if title else ''}).")

    # Always finish by showing what the card still needs.
    path = ROOT / UFC_OUT
    try:
        card = _json.loads(path.read_text())
    except (OSError, ValueError):
        print("\nNo UFC card built yet — run the launcher once.")
        return
    rows = list(card.get("picks") or []) + list(card.get("pass_list") or [])
    if not rows:
        print(f"\nNo bouts on the built card ({card.get('status', '?')}).")
        return
    print(f"\nCard {card.get('event_date', '')} — weigh-in status:")
    for row in rows:
        wi = row.get("weigh_in") or {}
        bits = []
        for side in ("a", "b"):
            st = wi.get(side) or {}
            nm = st.get("name", "?")
            s = st.get("state")
            bits.append(f"{nm}: " + (
                f"{st.get('weight')} ✅" if s == "made" else
                f"{st.get('weight')} ⛔ +{st.get('over'):g}" if s == "missed"
                else "— not recorded"))
        print(f"  {row.get('fight', '?')}\n      " + "   |   ".join(bits))
    summary = card.get("weigh_ins") or {}
    if summary:
        print(f"\n  {summary.get('made', 0)} made · {summary.get('missed', 0)} "
              f"missed · {summary.get('unrecorded', 0)} not recorded")


def card_venue_cli(argv: list) -> None:
    """Record where this card is being held, or show what's set.

        python3 launch.py --card-venue "UFC Apex" "Las Vegas"
        python3 launch.py --card-venue          (show the current card)

    §8 of the MMA spec calls cage size the input almost nobody prices: the
    promotion's own facility uses a 25-foot cage and arenas use 30, and
    less space means pressure fighters and wrestlers gain while finishes
    go up. Altitude is the other half — Mexico City and Denver impose a
    real cardio tax that pushes finishes later.

    Neither rides in the odds feed, and both are one fact per card rather
    than one per fight, so they are typed in the same way weigh-ins are.
    """
    import json as _json
    from engine.ufc import environment as env

    args = [a for a in argv[argv.index("--card-venue") + 1:]
            if not a.startswith("--")]
    try:
        board = _json.loads((ROOT / UFC_OUT).read_text())
    except (OSError, ValueError):
        board = {}
    event_date = board.get("event_date") or _slate_date()

    if args:
        venue = args[0]
        city = args[1] if len(args) > 1 else ""
        env.record_card(event_date, venue, city)
        cage = env.cage_size(venue)
        alt = env.altitude(city)
        print(f"✅ {event_date}: {venue}" + (f", {city}" if city else ""))
        print(f"   cage — {cage['note']}")
        print(f"   altitude — {alt['note']}")
        print("   Rebuild to apply it: python3 ufc_build.py --cached-odds")
        return

    rec = env.card_for(event_date, env.load_cards())
    if rec.get("venue"):
        print(f"{event_date}: {rec['venue']}"
              + (f", {rec['city']}" if rec.get("city") else ""))
        print(f"  cage — {env.cage_size(rec['venue'])['note']}")
        print(f"  altitude — {env.altitude(rec.get('city', ''))['note']}")
    else:
        print(f"{event_date}: no venue recorded. Cage size and altitude are "
              f"unchecked, which the grade scores as neutral rather than "
              f"good.")
        print('  Set it:  python3 launch.py --card-venue "UFC Apex" "Las Vegas"')


def confirm_qb_cli(argv: list) -> None:
    """Confirm a starting quarterback, or list what the board is waiting on.

        python3 launch.py --confirm-qb "TOL" --starter "Tucker Gleason"
        python3 launch.py --confirm-qb "TOL" --out          (starter is OUT)
        python3 launch.py --confirm-qb                      (just show me)

    College football has no league-mandated injury report, so this is the
    one fact the engine cannot fetch. §2.3 makes it a gate: until both
    sidelines are confirmed, every play in the game publishes as a
    conditional with its number and its edge but no stake. This command is
    how a conditional becomes a bet.

    Confirmations are scoped to the slate date, so last week's answer can
    never authorise this week's bet.
    """
    import json as _json
    from engine.cfb import status as qb

    args = [a for a in argv[argv.index("--confirm-qb") + 1:]
            if not a.startswith("--")]
    try:
        board = _json.loads((ROOT / CFB_OUT).read_text())
    except (OSError, ValueError):
        board = {}

    if args:
        team = " ".join(args).strip()
        # Date the confirmation against the game this team is ACTUALLY
        # playing, not against today. Weeknight college games are on the
        # board days before Saturday, and a confirmation stamped with the
        # wrong date is worse than none — it reports success and authorises
        # nothing.
        date = next((g.get("date") for g in board.get("games", [])
                     if team.upper() in (g.get("home", "").upper(),
                                         g.get("away", "").upper())
                     and g.get("date")), None)
        if not date:
            date = _slate_date()
            print(f"⚠️  {team.upper()} isn't on the built board — recording "
                  f"against {date}. If their game is another day, rebuild "
                  f"first so this lands on the right one.")
        starter = ""
        if "--starter" in argv:
            i = argv.index("--starter")
            starter = " ".join(a for a in argv[i + 1:]
                               if not a.startswith("--")).strip()
        state = qb.BACKUP if "--out" in argv else qb.CONFIRMED
        qb.record(team, date, state=state, starter=starter)
        if state == qb.BACKUP:
            print(f"⚠️  {team.upper()} — starter reported OUT for {date}"
                  f"{f' (backup: {starter})' if starter else ''}.")
            print("   That's information, not a hold: the market underprices "
                  "this more often in college than anywhere else.")
        else:
            print(f"✅ {team.upper()} — starter confirmed for {date}"
                  f"{f' ({starter})' if starter else ''}.")
        print("   Rebuild the board to promote its conditionals: "
              "python3 cfb_build.py --cached-odds")

    # Always finish by showing what the board is still waiting on.
    if not board:
        print("\nNo CFB board built yet — run the launcher once.")
        return
    pending = [g for g in board.get("games", []) if not g.get("qb_confirmed")]
    conditionals = [b for b in board.get("game_bets", []) if b.get("conditional")]
    print(f"\nCFB {board.get('date', '')}: {len(board.get('games', []))} game(s), "
          f"{len(pending)} awaiting a QB confirmation.")
    if conditionals:
        print("  Conditionals — these are bets the moment the starter is confirmed:")
        for b in conditionals[:12]:
            print(f"    {b.get('matchup', ''):16} {b.get('pick_label', ''):22} "
                  f"{b.get('odds', 0):+5}  edge {b.get('edge', 0):+.1%}  "
                  f"{b.get('stake_if_confirmed_units', 0):.2f}u if confirmed")
    else:
        print("  Nothing is waiting on a quarterback right now.")


def refresh_rosters(name: str | None = None) -> None:
    """Re-pull the roster feed now, and say what it knows about a player.

    Team moves come from Sleeper's player file, which is cached for hours
    and — when the fetch fails — falls back to the last good copy for as
    long as it takes. Either way a trade from yesterday can be invisible
    with nothing on screen admitting it. This forces the pull and prints
    the feed's own answer, so "why isn't this trade showing" stops being a
    guess about caches.
    """
    import datetime as _d
    from engine import offseason
    from engine.sources.fetch import CACHE_DIR

    cached = Path(CACHE_DIR) / offseason.SLEEPER_CACHE
    if cached.exists():
        age_h = (time.time() - cached.stat().st_mtime) / 3600
        print(f"Cached roster file: {age_h:.1f} h old — deleting it so the "
              f"next read has to go to the wire.")
        try:
            cached.unlink()
        except OSError as exc:
            print(f"  ⚠️  couldn't delete it: {exc}")

    blob = offseason.load_sleeper_players(max_age_s=0)
    if not blob:
        print("⚠️  Roster feed unreachable and no cached copy — team moves "
              "cannot update until api.sleeper.app is reachable.")
        return
    fresh = cached.exists()
    print(f"Roster feed: {len(blob):,} players "
          f"({'fetched just now' if fresh else 'served from cache — the pull failed'})")
    if fresh:
        print(f"  synced {_d.datetime.fromtimestamp(cached.stat().st_mtime):%Y-%m-%d %H:%M}")

    if name:
        from engine.sources.oddsapi import normalize_name
        want = normalize_name(name)
        hits = []
        for p in blob.values():
            if not isinstance(p, dict):
                continue
            full = (p.get("full_name")
                    or f"{p.get('first_name', '')} {p.get('last_name', '')}").strip()
            if full and normalize_name(full) == want:
                hits.append((full, p))
        if not hits:
            print(f"\n  '{name}' is not in the roster feed under that name. "
                  f"The feed's spelling is what the board matches on.")
        for full, p in hits:
            print(f"\n  roster feed: {full} — {p.get('position')} · team "
                  f"{p.get('team') or '(free agent)'} · "
                  f"{'active' if p.get('active') else 'inactive'}"
                  f" · depth {p.get('depth_chart_position')}"
                  f"{p.get('depth_chart_order')}")

        # Knowing the feed is right only gets you halfway. A move is only
        # ever REPORTED for players who are on one of the fantasy boards —
        # so a correct feed plus an absent player still looks like a bug,
        # and the answer is "he was never checked", which nothing on the
        # page says out loud.
        _where_on_board(name)

    print("\nRebuild the fantasy page to apply it:  python3 fantasy_build.py")


def _where_on_board(name: str) -> None:
    """Which fantasy boards carry this player, and with what team.

    Team moves are stamped onto board rows; a player on none of them is
    never examined, which is indistinguishable on screen from a player the
    feed got wrong."""
    from engine.sources.oddsapi import normalize_name
    want = normalize_name(name)
    path = ROOT / "web" / "data" / "fantasy.json"
    if not path.is_file():
        print(f"\n  board: {path.name} not built yet — run python3 fantasy_build.py")
        return
    try:
        d = json.loads(path.read_text())
    except Exception as exc:
        print(f"\n  board: unreadable ({exc})")
        return
    kit = d.get("draft_kit") or {}
    groups = {
        "draft kit board": kit.get("board") or [],
        "usage movers": d.get("usage") or [],
        "buy low": (d.get("buy_sell") or {}).get("buy_low") or [],
        "sell high": (d.get("buy_sell") or {}).get("sell_high") or [],
    }
    for pos_rows in (kit.get("tiers") or {}).values():
        groups.setdefault("draft kit tiers", []).extend(pos_rows)

    found = False
    print()
    for label, rows in groups.items():
        for r in rows:
            if normalize_name(r.get("player", "")) != want:
                continue
            found = True
            moved = (f" (was {r['moved_from']})" if r.get("moved_from") else "")
            flag = f" · {r['roster_flag']}" if r.get("roster_flag") else ""
            print(f"  board: on '{label}' as {r.get('team')}{moved}{flag}")
            break
    if not found:
        print(f"  board: '{name}' is on NONE of the fantasy boards, so a trade "
              f"for him is never looked for.")
        print(f"         The boards are built from last season's volume — a "
              f"player who didn't play, or ranks outside the kit, simply has "
              f"no row to stamp. That is why he is absent rather than wrong.")
    moves = ((d.get("offseason") or {}).get("moves") or [])
    hit = [m for m in moves if normalize_name(m.get("player", "")) == want]
    if hit:
        m = hit[0]
        print(f"  moves list: reported {m['from']} → {m['to']}")
    elif found:
        print("  moves list: not reported — the feed's team matches the "
              "board's, so nothing has changed as far as the data knows.")


def odds_doctor() -> None:
    """Why does the board say N props have no book price?

    Written after guessing wrong about it twice. "753 unpriced" has at
    least three unrelated causes that look identical on the phone — the
    board is frozen, the board is fresh but re-applying a stale cached
    price snapshot, or the books genuinely have not posted those lines —
    and the difference is entirely in numbers that live on this machine.
    So print them instead of reasoning about them.
    """
    import datetime as _d

    def ago(ts):
        """A timestamp with its distance from now — in either direction, so
        the same helper reads correctly for a pull that happened and a first
        pitch that hasn't."""
        if not ts:
            return "never"
        mins = (time.time() - float(ts)) / 60
        when = _d.datetime.fromtimestamp(float(ts)).strftime("%a %H:%M")
        gap = abs(mins)
        span = f"{gap:.0f} min" if gap < 180 else f"{gap / 60:.1f} h"
        return f"{when} ({span} {'ago' if mins >= 0 else 'from now'})"

    print("Odds doctor — why the board is priced the way it is\n")

    # 1. Is this machine even running the code I think it is?
    ok, head = _git("log", "-1", "--format=%h %s")
    if ok:
        print(f"  code      {head[:72]}")
        _git("fetch", "-q", "origin")
        ok2, behind = _git("rev-list", "--count", "HEAD..@{u}")
        if ok2 and behind.isdigit() and int(behind):
            print(f"            ⚠️  {behind} commit(s) BEHIND origin — "
                  f"you have not pulled. `git pull` first; everything below "
                  f"is the old code's behaviour.")
        elif ok2:
            print("            up to date with origin")

    # 2. The board file itself: how old, and what it says about its prices.
    path = ROOT / MLB_OUT
    if not path.is_file():
        print(f"\n  board     {MLB_OUT} does not exist — nothing has built.")
        return
    age_min = (time.time() - path.stat().st_mtime) / 60
    try:
        board = json.loads(path.read_text())
    except Exception as exc:
        print(f"\n  board     unreadable: {exc}")
        return
    props = board.get("recommendations", []) or []
    priced = sum(1 for r in props if r.get("has_market"))
    census = board.get("gate_census", {}) or {}
    os_ = board.get("odds_status", {}) or {}
    print(f"\n  board     rebuilt {age_min:.0f} min ago · slate {board.get('date')}"
          f" · {len(board.get('games', []))} game(s)")
    if census:
        print(f"            {len(props)} prop(s): {priced} with a real book "
              f"price, {census.get('no_real_price', 0)} without")
    else:
        print(f"            {len(props)} prop(s): {priced} with a real book "
              f"price (this build recorded no gate census)")
    if age_min > 5:
        print(f"            ⚠️  a running launcher rebuilds this every 60s. "
              f"{age_min:.0f} minutes means it is NOT running (or is failing).")

    # 3. What the last build did about odds. `source` is the key field:
    #    "cache" means it re-applied the last PAID pull's snapshot, so a
    #    board can be seconds old and its prices hours old.
    if not os_:
        print("\n  odds      the build recorded nothing — it ran without "
              "--odds/--cached-odds (no ODDS_API_KEY?)")
    else:
        src = os_.get("source")
        print(f"\n  odds      last build used: "
              f"{'FRESH paid pull' if src == 'fresh' else 'CACHED prices' if src == 'cache' else src}")
        print(f"            matched {os_.get('matched', 0)} prop price(s) "
              f"across {os_.get('events', 0)} game(s)")
        if os_.get("priced_at"):
            print(f"            those prices were pulled {ago(os_['priced_at'])}")
        if os_.get("error"):
            print(f"            ⚠️  {os_['error']}")
        if os_.get("name_misses"):
            print(f"            ⚠️  {os_['name_misses']} price(s) nearly matched "
                  f"a prop but didn't join — that part IS a bug:")
            for m in os_.get("name_miss_examples", [])[:8]:
                print(f"                 ours '{m.get('prop')}' vs book "
                      f"'{m.get('book')}' ({m.get('market')})")
            if not os_.get("name_miss_examples"):
                print("                 (rebuild once on the new code to see "
                      "which names)")

    # 4. The budget's own books, and what the pacer would decide right now.
    try:
        from engine import oddsbudget
        st = oddsbudget.load()
        print(f"\n  budget    {oddsbudget.summary()}")
        print(f"            last paid MLB pull: "
              f"{ago(st.sport_ts('mlb') or st.last_refresh_ts)}")
        kicks = _slate_kickoffs(str(path))
        if kicks:
            print(f"            first pitch {ago(min(kicks))} · pre-game window "
                  f"opens {ago(min(kicks) - oddsbudget.PRIME_BEFORE_S)}")
        ok3, why = oddsbudget.should_refresh(
            _games_on_slate(str(path)) + 1, kickoffs=kicks, sport="mlb",
            share=_budget_share())
        print(f"\n  right now {'WOULD pull' if ok3 else 'would NOT pull'}: {why}")
    except Exception as exc:                       # noqa: BLE001
        print(f"\n  budget    unreadable: {exc}")

    if not _with_odds():
        print("\n  ⚠️  ODDS_API_KEY is not set in this shell — every build is "
              "running on proxy lines. Check secrets.local.")


AUTO_UPDATE_EVERY_S = 300


def _git(*args, timeout: int = 60):
    """Run a git command in the repo. Returns (ok, output)."""
    import subprocess
    try:
        p = subprocess.run(("git", "-C", str(ROOT)) + args, capture_output=True,
                           text=True, timeout=timeout)
        return p.returncode == 0, (p.stdout + p.stderr).strip()
    except Exception as exc:                       # git missing, hung, offline
        return False, str(exc)


def _auto_update() -> bool:
    """Fast-forward to whatever has been pushed. True if new code arrived.

    The point is a laptop that is at home while you are not: a fix gets
    pushed, and the machine picks it up without anyone typing `git pull`.

    Deliberately timid, because this ends in running code:

    * ``--ff-only`` — it will never merge, rebase, or resolve anything. If
      the branch has diverged it stops and says so.
    * a dirty working tree is left completely alone. Uncommitted work on
      the laptop is someone's work in progress, not an obstacle.
    * it stays on the branch already checked out; it never switches.
    """
    ok, dirty = _git("status", "--porcelain")
    if not ok:
        return False
    if dirty:
        print("  ⚠️  auto-update skipped: uncommitted changes in the working "
              "tree. Commit or stash them and it resumes on its own.")
        return False
    ok, branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    if not ok or not branch or branch == "HEAD":
        return False
    ok, before = _git("rev-parse", "HEAD")
    if not ok:
        return False
    ok, out = _git("pull", "--ff-only", "origin", branch)
    if not ok:
        # Offline is the common case and not worth shouting about; a real
        # divergence is, because it means auto-update has stopped working.
        if "diverge" in out.lower() or "non-fast-forward" in out.lower():
            print(f"  ⚠️  auto-update stopped: {branch} has diverged from "
                  f"origin. Sort it out by hand — nothing was changed.")
        return False
    ok, after = _git("rev-parse", "HEAD")
    return bool(ok and after != before)


def _restart_into_new_code() -> None:
    """Replace this process with a fresh one running the code just pulled.

    Python has already imported the old modules, so a pull alone changes
    nothing that matters — the engine in memory is still yesterday's. execv
    keeps the same PID and terminal, so the launcher simply reappears with
    the new code and the phone reconnects on its next poll.
    """
    import os
    print("  ↻ new code pulled — restarting the launcher into it…\n")
    sys.stdout.flush()
    try:
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as exc:                       # noqa: BLE001
        print(f"  ⚠️  restart failed ({exc}) — the new code is on disk; "
              f"Ctrl+C and start it again to pick it up.")


def _auto_updater() -> None:
    """Check for pushed code every few minutes, and restart when it lands."""
    while True:
        time.sleep(AUTO_UPDATE_EVERY_S)
        try:
            if _auto_update():
                _restart_into_new_code()
        except Exception as exc:                   # noqa: BLE001
            print(f"  ⚠️  auto-update error: {exc}")


def _background_refresher(interval: int) -> None:
    """Keep the served data fresh while the server runs (quiet after startup)."""
    while True:
        time.sleep(interval)
        # Catches the date rolling over while the server runs overnight.
        _run_maintenance()
        # Closes out tonight's games as they end, rather than tomorrow.
        _run_autosettle()
        # Once a day, and only when something is wrong.
        _run_doctor()
        refresh_all(quiet=True)


# A fight moves in seconds, so the live card cannot ride the 60-second
# cycle the rest of the site uses. This runs on its own clock, and it
# BACKS OFF to the slow tick when nothing is in progress — polling a free
# feed every 12 seconds around the clock to watch an empty octagon is
# rude and pointless.
LIVE_FAST_S = 12
LIVE_IDLE_S = 180


def _live_ufc_refresher() -> None:
    """Poll the live fight feed fast while a bout is on, slowly otherwise."""
    import json as _json
    while True:
        wait = LIVE_IDLE_S
        try:
            ok, _tail = _run_build(["ufc_live_build.py"])
            if ok:
                blob = _json.loads((ROOT / "web" / "data" /
                                    "ufc_live.json").read_text())
                if blob.get("status") == "live":
                    wait = LIVE_FAST_S
        except Exception:      # noqa: BLE001 — never let this stop the site
            pass
        time.sleep(wait)


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
    # Port 0 lets the OS pick a free one. A fixed port here meant two
    # --check runs at once — or one left half-finished — failed on
    # "address already in use" during a HEALTH CHECK, which is the worst
    # possible moment to hand somebody an error about our own plumbing.
    port = 0
    server = None
    try:
        # The sweep's own server must not narrate every asset fetch into
        # the middle of the checklist.
        class _Quiet(Handler):
            def log_message(self, *a, **kw):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", port), _Quiet)
        port = server.server_address[1]        # whatever the OS handed us
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


def _reachable(url: str, timeout: int = 6, ua: str = "qellys-book/preflight") -> bool:
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
    print("Qellys Book — preflight check\n")

    v = sys.version_info
    print(f"{ok if v >= (3, 9) else warn} Python {v.major}.{v.minor}"
          + ("" if v >= (3, 9) else "  → need 3.9+"))

    # Team ratings (needed for moneyline / spread / totals to have an edge).
    try:
        from engine.db import connect
        conn = connect()
        for sport in ("nfl", "mlb", "cfb"):
            n = conn.execute("SELECT COUNT(*) FROM games WHERE sport=?", (sport,)).fetchone()[0]
            if n:
                print(f"{ok} Team ratings ({sport.upper()}): {n} games ingested")
            else:
                # College football fills its own table from the ESPN feed;
                # ingest.py has no cfb mode, so pointing at it would send
                # you to a command that doesn't exist.
                how = ("python3 cfb_build.py --backfill 2025-08-24:2026-01-20"
                       if sport == "cfb" else f"python3 ingest.py {sport}")
                print(f"{warn} Team ratings ({sport.upper()}): none — run "
                      f"`{how}` so game bets have an edge")
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
        ("College football (ESPN)", "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard"),
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

        open_days = ledger.open_by_day(lconn, today)
        # More than one night stuck is a launcher that was off, not a
        # one-off — say so once here rather than making someone read eight
        # lines and run --settle eight times.
        stale_days = [d for d in open_days
                      if d["stale"] and "-W" not in (d["date"] or "")]
        if len(stale_days) > 1:
            print(f"{warn}   {len(stale_days)} finished days still have picks "
                  f"open. Settle them all in one go: "
                  f"python3 launch.py --settle all")
        for day in open_days[:8]:
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


def why_ufc(argv: list | None = None) -> None:
    """Explain a UFC card with no picks — which gate stopped each fight.

        python3 launch.py --why-ufc

    "No qualifying plays on this card" is a valid and common output for
    this model, but valid is not the same as understood. This walks the
    built card and, for every bout, says exactly what stopped it: no
    dossier, no tracked stats, no posted price, the humility clamp, the
    edge bar, or the 0-100 grade — and when it is the grade, which of the
    six components was short and by how much.
    """
    import json as _json
    from engine.ufc import grade as G

    try:
        card = _json.loads((ROOT / UFC_OUT).read_text())
    except (OSError, ValueError):
        print("No UFC card built yet — run the launcher once.")
        return
    if card.get("status") != "card":
        print(f"No card in the window ({card.get('status')}). "
              f"{card.get('note', '')}")
        return

    picks = card.get("picks") or []
    passes = card.get("pass_list") or []
    print(f"UFC {card.get('event_date', '')}: {len(picks)} pick(s), "
          f"{len(passes)} pass(es), {card.get('dossiers_loaded', 0)} dossier(s) "
          f"loaded\n")

    # Weigh-ins first, because that is the usual suspicion — and usually
    # not the culprit. An UNRECORDED weigh-in is not a red flag; only a
    # MISSED weight blocks a bet outright.
    wi = card.get("weigh_ins") or {}
    if wi:
        print(f"Weigh-ins: {wi.get('made', 0)} made · {wi.get('missed', 0)} "
              f"missed · {wi.get('unrecorded', 0)} not recorded")
        if wi.get("missed"):
            print("  A missed weight is a hard red flag and blocks that fight.")
        if wi.get("unrecorded"):
            print("  Unrecorded does NOT block a bet and no longer costs "
                  "grade points either. The fight-week component drops out "
                  "of the scorecard entirely and the remaining components "
                  "are renormalised, so an un-weighed fight is graded on "
                  "what we DO know rather than marked down for a Friday "
                  "that has not happened. Results are pulled automatically "
                  "once they publish — see --probe-weighins.")
        print()

    buckets: dict = {}
    for row in passes:
        buckets.setdefault(row.get("reason_code", "other"), []).append(row)
    LABEL = {
        "no_dossier": "no dossier for a corner — the engine will not bet a "
                      "fighter it has never measured",
        "no_data": "no fight-by-fight stats (regional/uncovered record)",
        "no_price": "no two-sided price posted yet — books open MMA late",
        "clamp_kill": "model and market disagree too far — treated as our "
                      "input being wrong, not as a goldmine",
        "gate": "priced and modelled, but failed the edge bar or the grade",
        "card_cap": "trimmed by the card exposure cap",
    }
    for code, rows in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
        print(f"{len(rows):>3} × {LABEL.get(code, code)}")
        for r in rows[:4]:
            print(f"      {r.get('fight', '')}")
        if len(rows) > 4:
            print(f"      … and {len(rows) - 4} more")
    print()

    # The gated fights are the interesting ones: they had everything and
    # still did not clear. Show the grade arithmetic.
    gated = buckets.get("gate", [])
    if not gated:
        print("Nothing reached the grade — the blockers above are upstream "
              "of it. Fix those first.")
        return
    print("Fights that were priced and modelled — how close each came:\n")
    for r in sorted(gated, key=lambda x: -(x.get("grade_score") or 0)):
        best = r.get("best_market") or {}
        print(f"  {r.get('fight', '')}")
        print(f"    would bet: {r.get('selection', r.get('pick', ''))} "
              f"{best.get('odds', r.get('odds', ''))}  "
              f"edge {(best.get('edge') or 0):+.1%} vs bar "
              f"{(r.get('required_edge') or 0):.1%}")
        print(f"    grade {r.get('grade_score', 0)}/{G.MIN_GRADE} needed"
              f"  ({r.get('why', '')})")
        parts = r.get("grade_parts") or {}
        for key, weight in G.GRADE_WEIGHTS.items():
            if key == "edge":
                continue
            got = (parts.get({"data_quality": "data", "camp_info": "camp",
                              "style_clarity": "style",
                              "environment": "env"}.get(key, key)) or {})
            sc = got.get("score")
            if sc is None:
                print(f"      {key:14}  —   no feed: dropped from the "
                      f"scorecard, not scored against this fight")
                continue
            print(f"      {key:14} {sc:.2f} → {sc * weight:4.1f} of {weight}")
        cov = r.get("grade_coverage")
        if cov is not None:
            print(f"      graded on {cov:.0%} of the scorecard"
                  + ("  (capped — an incomplete scorecard cannot earn top "
                     "marks)" if r.get("grade_capped") else ""))
        print()
    print("Components with no feed score NOTHING rather than a fixed "
          "neutral: they leave the scorecard and the rest is renormalised, "
          "so the grade answers 'how good is this bet on what we can "
          "actually see'. Market movement has no UFC line history yet and "
          "is always one of them; fight-week info joins it until the scale "
          "happens. A fight that fails now fails on its own merits.")


def odds_audit() -> None:
    """Where did the credits go?

    Ethan's 20,000-credit plan emptied and the only evidence was a cumulative
    counter that says how much is gone and nothing about what took it. That is
    not a question anyone should have to reason about — it should be a
    receipt.

    Two sources, in order of trust. The spend ledger records every paid call
    with its own billed cost and is exact from the moment it exists. Before
    it existed there is only the cache directory: every successful paid call
    wrote a file there, so the filenames say what KIND of call it was and the
    modification times say when. That reconstruction cannot see the price, so
    it prices each class at the documented rate and says it is estimating.
    """
    from engine import oddsbudget as ob
    from engine.sources.fetch import CACHE_DIR
    import datetime as _dt

    print("\nWHERE THE ODDS CREDITS WENT\n")
    st = ob.load()
    ring = []
    try:
        from engine.sources.oddsapi import api_keys
        ring = api_keys()
    except Exception:
        pass
    print(f"  Pool now: {st.remaining:,} credit(s) across "
          f"{len(ring) or 1} key(s) · {st.used:,} used on the last key seen")
    if ring:
        for k in ring:
            ks = ob.key_state(k)
            mark = "spent" if ob.key_is_spent(k) else "live "
            rem = ks.get("remaining")
            print(f"    {mark}  key {ob.fingerprint(k)}  "
                  f"{'never called' if rem is None else f'{int(rem):,} left'}")

    ledger = ob.spend_by_day()
    if ledger:
        print("\n  From the spend ledger (exact, per call):")
        for day in sorted(ledger):
            kinds = ledger[day]
            total = sum(v[1] for v in kinds.values())
            print(f"    {day}   {total:>6,} credit(s)")
            for kind, (n, c) in sorted(kinds.items(), key=lambda t: -t[1][1]):
                print(f"        {kind:<14} {n:>5} call(s)  {c:>6,} credit(s)")
    else:
        print("\n  The spend ledger is empty — it only records calls made "
              "since it was added, so anything before that is below.")

    # Reconstruction from the cache, for spend the ledger never saw.
    buckets: dict = {}
    try:
        files = list(CACHE_DIR.glob("odds_*.json"))
    except Exception:
        files = []
    for f in files:
        day = _dt.date.fromtimestamp(f.stat().st_mtime).isoformat()
        name = f.name
        if name.startswith("odds_hist_event_"):
            kind, cost = "hist_event", ob.CREDIT_COST["hist_event"]
        elif name.startswith("odds_hist_events_"):
            kind, cost = "hist_events", ob.CREDIT_COST["hist_events"]
        elif name.startswith("odds_board_"):
            kind, cost = "live_board", ob.CREDIT_COST["live_board"]
        elif name.startswith("odds_events_"):
            kind, cost = "live_events", ob.CREDIT_COST["live_events"]
        else:
            kind, cost = "live_event", ob.CREDIT_COST["live_event"]
        cell = buckets.setdefault(day, {}).setdefault(kind, [0, 0])
        cell[0] += 1
        cell[1] += cost
    if buckets:
        print(f"\n  Reconstructed from {len(files):,} cache file(s) — a cache "
              f"file is what a paid call leaves behind, so this counts CALLS\n"
              f"  exactly and prices them at the documented rate. One cached\n"
              f"  file can also stand for several re-reads that cost nothing.")
        grand = 0
        for day in sorted(buckets):
            kinds = buckets[day]
            total = sum(v[1] for v in kinds.values())
            grand += total
            print(f"    {day}   ~{total:>6,} credit(s)")
            for kind, (n, c) in sorted(kinds.items(), key=lambda t: -t[1][1]):
                print(f"        {kind:<14} {n:>5} call(s)  ~{c:>6,} credit(s)")
        print(f"\n    Estimated total across the cache: ~{grand:,} credit(s)")
        hist = sum(v.get("hist_event", [0, 0])[1] + v.get("hist_events", [0, 0])[1]
                   for v in buckets.values())
        if hist and grand:
            print(f"    Historical harvesting accounts for ~{hist:,} of that "
                  f"({hist / grand:.0%}).")
            print("    A historical call is billed several times a live one, so "
                  "a harvest\n    over a long date range empties a plan far "
                  "faster than a season of\n    nightly builds. Cap it with "
                  "`--budget N` on harvest_odds.py.")
    else:
        print("\n  No odds cache on this machine — nothing to reconstruct.")


def why_many(sport: str = "mlb", days: int = 21) -> None:
    """The inverse of --why-empty: why is tonight's board BIGGER than usual?

    "We normally recommend about four a night" is a memory, and a memory is
    not a baseline. This measures the nightly count from the journal itself,
    so tonight's number gets compared against what actually happened rather
    than against an impression — and then walks the gates to say which one
    stopped holding.

    The gate that swings an MLB count hardest is the lineup hold: hitter
    props are blocked until the card is posted, so the board is quiet in the
    morning and fills in the moment lineups drop. A count taken at 11am and
    a count taken at 6pm are not the same measurement.
    """
    import json as _json
    from collections import Counter
    from engine import ledger

    rel = ("web/data/mlb_recommendations.json" if sport == "mlb"
           else "web/data/recommendations.json")
    p = ROOT / rel
    if not p.is_file():
        print(f"No board built yet at {rel} — start the launcher first.")
        return
    board = _json.loads(p.read_text())
    recs = board.get("recommendations", [])
    live = [r for r in recs if r.get("recommended")]
    print(f"\n  TONIGHT ({board.get('date', '?')})")
    print(f"  {len(recs)} prop(s) priced · {len(live)} recommended\n")

    # --- the baseline, measured ------------------------------------------
    with ledger.connect() as conn:
        rows = conn.execute(
            "SELECT date, COUNT(*) n FROM bets WHERE sport=? AND category='main' "
            "GROUP BY date ORDER BY date DESC LIMIT ?", (sport, days)).fetchall()
    if rows:
        counts = [r["n"] for r in rows]
        counts_sorted = sorted(counts)
        med = counts_sorted[len(counts_sorted) // 2]
        print(f"  JOURNALLED PER NIGHT, last {len(counts)} slate(s) with picks")
        print(f"  median {med} · min {min(counts)} · max {max(counts)}")
        for r in rows[:8]:
            bar = "#" * min(r["n"], 40)
            print(f"    {r['date']}  {r['n']:>3}  {bar}")
        if live and med:
            print(f"\n  tonight is {len(live) / med:.1f}x the median night")
        print()
    else:
        print(f"  No {sport} picks journalled yet — no baseline to compare "
              f"against, so tonight's count cannot be called unusual.\n")

    # --- what cleared, and what it cleared BY -----------------------------
    if not live:
        print("  Nothing recommended — run --why-empty instead.")
        return
    edges = sorted(r.get("edge", 0) for r in live)
    confs = sorted(r.get("confidence", 0) for r in live)
    stakes = [r.get("stake_units", 0) or 0 for r in live]
    mid = len(edges) // 2
    print("  WHAT CLEARED")
    print(f"  edge        min {edges[0]:+.1%}  median {edges[mid]:+.1%}  max {edges[-1]:+.1%}")
    print(f"  confidence  min {confs[0]:.1f}   median {confs[mid]:.1f}   max {confs[-1]:.1f}")
    print(f"  exposure    {sum(stakes):.2f}u across {len(live)} pick(s)")
    by_market = Counter(r.get("market_label") or r.get("market") for r in live)
    by_grade = Counter(r.get("grade") for r in live)
    by_game = Counter(f"{r.get('opponent','?')}" for r in live)
    print(f"  markets     " + ", ".join(f"{k} {v}" for k, v in by_market.most_common()))
    print(f"  grades      " + ", ".join(f"{k} {v}" for k, v in by_grade.most_common()))
    print(f"  spread over {len(by_game)} matchup(s)\n")

    # A board that is big because it is CONCENTRATED is a different problem
    # from one that is big because the slate is big. Say which.
    top_game, top_n = by_game.most_common(1)[0]
    if top_n > max(3, len(live) * 0.4):
        print(f"  ! {top_n} of {len(live)} picks come from one matchup ({top_game}).")
        print(f"    Correlated exposure — check the correlation flags before "
              f"treating these as {top_n} independent bets.\n")

    # --- the gates, and how much room each pick had -----------------------
    thin = [r for r in live if (r.get("stake_units") or 0) < 0.10]
    if thin:
        print(f"  {len(thin)} of {len(live)} size under 0.10u — they cleared "
              f"the edge bar but Kelly barely wants them.\n")
    print("  Run --why-pick \"<player>\" for the gate-by-gate on any one of "
          "them.\n")


def why_empty(sport: str = "mlb", min_conf: float = 6.0,
              min_edge: float = 0.02, max_juice: int = -350) -> None:
    """Explain an empty board: which gate is actually filtering everything.

    Reads the board the site is already serving and walks every prop
    through the four independent gates a recommendation must clear, so
    "0 recommended" stops being a mystery and becomes a number you can
    point at."""
    import json as _json
    from engine.betting import BASE_THRESHOLDS, favourite_surcharge, net_edge
    _GRADE_FLOOR = min(net_min for _, _, net_min in BASE_THRESHOLDS)
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
    # Home runs (Tier 3) are quarantined on the Long Shots board BY DESIGN
    # — engine/mlb/pipeline.py skips them for the main board and counts
    # them under census["longshot_board"]. Walking them through this funnel
    # made 15 props that can never be main-board picks appear "in the
    # recommendable window", and then manufactured a binding gate to
    # explain why they were not picked. A report about the main board has
    # to be about the main board.
    def _is_longshot(r):
        return r.get("tier") == 3 or r.get("market") in ("home_runs",
                                                         "anytime_td")
    shots = [r for r in real if _is_longshot(r)]
    real = [r for r in real if not _is_longshot(r)]
    print(f"{sport.upper()} board: {len(recs)} analyzed, "
          f"{len(real) + len(shots)} with a real price\n")
    if shots:
        print(f"🎯 {len(shots)} of those are home runs — the Long Shots board "
              f"owns those by design, and they are\n   excluded from "
              f"everything below. See the Long Shots page for that funnel.\n")
    if not real:
        print("Every real-priced prop tonight is a long shot. The main board "
              "has nothing to explain.")
        return

    rows = []
    for r in real:
        odds = int(r.get("odds") or -110)
        hit = float(r.get("hit_prob") or 0)
        rows.append({
            "label": f"{r.get('player','?')} {r.get('side','')} {r.get('line','')} "
                     f"{r.get('market','')}",
            "odds": odds, "net": net_edge(hit, odds),
            # The grader's real floor, not a looser number of this
            # report's own invention. It was hardcoded at 0.003 while
            # _grade's lowest threshold ("Play") needs 0.010 — so the
            # funnel cleared props at a bar the engine would reject, and
            # then blamed "engine graded it" for killing them. A report
            # that disagrees with the code it explains sends you hunting
            # for a bug that is not there.
            "need": _GRADE_FLOOR + favourite_surcharge(odds),
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
        (f"clears the graded bar (net ≥ {_GRADE_FLOOR*100:.1f}pt "
         f"+ chalk surcharge)", lambda x: x["net"] >= x["need"]),
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


def side_bias(sport: str = "mlb") -> None:
    """Is the model's disagreement with the market ONE-SIDED?

    On a 591-prop card every one of the five biggest edges was an UNDER,
    at 20-25%. Five is not a sample, so this counts the whole board.

    The distinction matters because the two cases need opposite fixes. If
    OVERs and UNDERs disagree with the market symmetrically, the model is
    noisy and the credibility ceiling is doing its job catching outliers.
    If the disagreement is one-sided, the model is BIASED — it is
    systematically projecting low — and every "edge too big to believe" is
    the same error appearing hundreds of times. A ceiling cannot fix that;
    it just hides it, and hides it most on the props where the error is
    largest.

    Long shots are excluded, as everywhere else: they are their own board
    with their own model.
    """
    import json as _json
    from engine.betting import MARKET_SHRINK, MAX_CREDIBLE_EDGE
    rel = {"mlb": MLB_OUT, "nfl": NFL_OUT, "nba": NBA_OUT,
           "wnba": WNBA_OUT, "cfb": CFB_OUT}.get(sport, MLB_OUT)
    try:
        recs = _json.loads((ROOT / rel).read_text()).get("recommendations", [])
    except (OSError, ValueError):
        print(f"No board built yet at {rel} — start the launcher first.")
        return
    real = [r for r in recs if r.get("has_market") is not False
            and r.get("tier") != 3
            and r.get("market") not in ("home_runs", "anytime_td")]
    if not real:
        print("No real-priced main-board props on this card.")
        return
    ceiling = MAX_CREDIBLE_EDGE * MARKET_SHRINK

    by: dict = {}
    per_market: dict = {}
    for r in real:
        side = (r.get("side") or "?").upper()
        e = float(r.get("edge") or 0)
        d = by.setdefault(side, {"n": 0, "sum": 0.0, "over": 0})
        d["n"] += 1
        d["sum"] += e
        if e > ceiling:
            d["over"] += 1
        m = per_market.setdefault(r.get("market", "?"),
                                  {"OVER": 0, "UNDER": 0})
        if side in m:
            m[side] += 1

    print(f"{sport.upper()} — model vs market, by side")
    print(f"  {len(real)} real-priced main-board prop(s) · "
          f"credibility ceiling {ceiling:.1%}\n")
    print(f"  {'side':<8}{'n':>6}{'mean edge':>12}{'over ceiling':>15}{'rate':>8}")
    for side, d in sorted(by.items()):
        print(f"  {side:<8}{d['n']:>6}{d['sum'] / d['n'] * 100:>11.2f}%"
              f"{d['over']:>15}{d['over'] / d['n']:>7.0%}")

    o, u = by.get("OVER"), by.get("UNDER")
    if not (o and u and o["n"] >= 30 and u["n"] >= 30):
        print("\n  Too few on one side to call. This needs a full slate — "
              "run it again on a night with a real board.")
        return
    ro, ru = o["over"] / o["n"], u["over"] / u["n"]
    gap = abs(ro - ru)
    print(f"\n  Unbiased, those two rates would be about equal. "
          f"They are {ro:.0%} and {ru:.0%}.")
    if gap < 0.10:
        print("  → Symmetric. The ceiling is catching noise, which is its "
              "job. No side bias to chase.")
    else:
        heavy = "UNDER" if ru > ro else "OVER"
        print(f"  → ONE-SIDED, by {gap:.0%}. The model systematically favours "
              f"{heavy}.\n"
              f"    That is a projection error, not a market inefficiency, "
              f"and the credibility\n"
              f"    ceiling is hiding it — worst on exactly the props where "
              f"it is largest.\n"
              f"    Fix the projection; do not loosen the ceiling.")
        print("\n  By market (where the skew lives):")
        for m, c in sorted(per_market.items(),
                           key=lambda kv: -(kv[1]["OVER"] + kv[1]["UNDER"])):
            tot = c["OVER"] + c["UNDER"]
            if tot < 10:
                continue
            print(f"    {m:<16} {c['OVER']:>4} over · {c['UNDER']:>4} under"
                  f"   ({c['UNDER'] / tot:.0%} under)")


def _settleable_days(open_days) -> list[str]:
    """Which open-pick dates a per-date settle pass can actually grade.

    NFL journals under week labels ("2026-W1") rather than ISO days, and
    grades off weekly stats — feeding one to the MLB per-date results
    ingest looks like a night whose results never arrived. Oldest first,
    so each pass builds on the history the previous one stored."""
    return sorted(d["date"] for d in open_days
                  if d.get("date") and "-W" not in d["date"])


def show_stuck() -> None:
    """Which open bets can never settle, and why.

    `--settle all` reaching back weeks is the tell: those dates keep coming
    back because something on them cannot grade, and the sweep has no way
    to say which. It re-ingests, matches nothing new, reports zero, and
    leaves them to be swept again tomorrow — forever.
    """
    from engine import db, ledger
    lconn = ledger.connect()
    hconn = db.connect()
    try:
        rows = ledger.why_open(lconn, hconn, _slate_date())
    finally:
        lconn.close(); hconn.close()
    if not rows:
        print("Nothing stuck — every open pick is from a day still in play.")
        return

    by_reason: dict = {}
    for r in rows:
        by_reason.setdefault(r["reason"], []).append(r)
    print(f"{len(rows)} open pick(s) on days that are already over:\n")
    for reason in sorted(by_reason, key=lambda k: -len(by_reason[k])):
        group = by_reason[reason]
        print(f"  {len(group):>4}  {reason}")
        for r in sorted(group, key=lambda x: x["date"])[:6]:
            near = (f"  → logged on {r['logged_on']}" if r.get("logged_on")
                    else f"  ~ feed has {r['closest']!r}" if r.get("closest")
                    else "")
            print(f"          {r['date']}  {r['sport']:<5} "
                  f"{(r['player'] or '')[:26]:<26} {r['market']} "
                  f"({r['age_days']}d){near}")
            # The settler repairs the one-day drift on its own; a bet still
            # here means a guard refused, and the row must say which.
            if r.get("repair"):
                print(f"              ↳ {r['repair']}")
        if len(group) > 6:
            print(f"          … and {len(group) - 6} more")
        # How much of each day IS stored. A date with 30 players in it is a
        # partial ingest and every "missing" player on it is a symptom of
        # that, not 30 separate name problems.
        days = {}
        for r in group:
            if r.get("day_players") is not None:
                days[r["date"]] = (r["day_players"], r.get("day_games", 0))
        for d, (players, games) in sorted(days.items()):
            print(f"          {d}: {players} player(s), {games} game(s) "
                  f"stored for that date")
        print()

    # What to do about each, in the order they are worth doing.
    tips = {
        "no results ingested":
            "the games were never stored. Ingest that date's results "
            "(python3 ingest.py <sport> …) and they grade on the next pass.",
        "gradeable now":
            "results ARE there and these match — run `python3 launch.py "
            "--settle all`; if they survive it, tell me.",
        "player has no log":
            "that day IS ingested and this player is not in it: a scratch or "
            "a DNP (correct to void), or the journal spells his name "
            "differently from the feed (a name-map fix — the line shows the "
            "closest name the feed has, when there is one).",
        "logged under the next day":
            "the player IS in the results, on the date beside this one — a "
            "late first pitch that is already tomorrow in UTC. The settler "
            "repairs that drift automatically, so a bet still sitting here "
            "means one of the repair's guards refused — the ↳ line under "
            "each bet names which one, and the command that clears it.",
        "day barely ingested":
            "the date has far too few players stored to conclude anything "
            "about one of them — the ingest for that day did not finish. "
            "Re-run it (python3 ingest.py <sport> --dates <date>) and settle "
            "again.",
        "market not ingested":
            "he played, but this stat was never stored for him — the ingest "
            "for that sport does not carry this market.",
        "game not found":
            "a game-level bet whose game is not in the results: usually a "
            "postponement, which should be voided rather than graded.",
    }
    print("What each means:")
    for reason in sorted(by_reason, key=lambda k: -len(by_reason[k])):
        print(f"  {reason} — {tips.get(reason, 'unknown')}")


def settle_all() -> None:
    """Grade every day that still has picks open, oldest first.

    "Some bets aren't settled" is usually more than one night — a laptop
    that slept, a crashed pass, a west-coast game that ended after the
    launcher was closed. Finding each date by hand off the --check output
    and running --settle once per day is busywork the machine can do."""
    from engine import ledger
    lconn = ledger.connect()
    try:
        days = _settleable_days(ledger.open_by_day(lconn, _slate_date()))
    finally:
        lconn.close()
    if not days:
        print("Nothing open to settle.")
        return
    print(f"{len(days)} day(s) with open picks: {', '.join(sorted(days))}\n")
    for day in sorted(days):        # oldest first, so history builds forward
        settle_now(day)
        print()


def settle_now(day: str | None = None) -> None:
    """Ingest a day's results and grade the journal against them, now.

    The daily chores only run on the first refresh cycle of a new day, so
    a night's picks normally grade tomorrow morning. This does it on
    demand — run it after the games end to see tonight's board settle,
    and it prints the open/settled counts per bucket either side of the
    run so nothing has to be taken on faith.

    Pass "all" to sweep every day that still has something open."""
    import datetime as _dt
    if day == "all":
        return settle_all()
    # _slate_date(), not date.today(): the baseball day rolls at 5 AM, so
    # between midnight and 5 the picks you are looking at are journaled
    # under YESTERDAY's date. Defaulting to the calendar date meant that a
    # bare `--settle` at 4 AM — exactly when you'd reach for it, with the
    # west-coast games just finished — ingested an empty date and reported
    # settling nothing, while last night's board sat open.
    day = day or _slate_date()
    try:
        _dt.date.fromisoformat(day)
    except ValueError:
        print(f"--settle takes a date like 2026-07-26, or 'all' (got {day!r}).")
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
    # A hoops bet filed under the wrong league can never meet its results.
    # Re-file the unambiguous ones FIRST — the ingest below decides which
    # sports to fetch from the bets' own labels, so relabeling after it
    # would leave the right league un-ingested for another pass.
    try:
        moved = ledger.relabel_cross_league(lconn, hconn)
        if moved:
            print(f"  re-filed {moved} hoops bet(s) under the league that "
                  f"actually played them")
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠️  league relabel skipped: {exc}")
    # Long-shot markets may never sit in the headline record — re-file any
    # stray so the main record only describes picks the model stands behind.
    try:
        strays = ledger.move_longshots_out_of_main(lconn)
        if strays:
            print(f"  re-filed {strays} long-shot bet(s) out of the "
                  f"headline record into their own bucket")
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠️  long-shot re-file skipped: {exc}")
    try:
        # Every sport with an open pick that day, not just baseball. This
        # ingested MLB alone, so a WNBA or UFC pick had no stat line to be
        # graded against and stayed open — which is why `--settle all` began
        # at the same old date every night and reported nothing settled.
        from engine.maintenance import ingest_for_open_bets
        res = ingest_for_open_bets(lconn, hconn, [day], print)
        print(f"  results: {res.get('games', 0)} game(s), "
              f"{res.get('player_logs', 0):,} player log rows")
        # A called-off game is the usual reason a night refuses to grade:
        # it sits in the DB scoreless, looking exactly like a game still in
        # progress, and holds every pick on both teams open. Name it.
        for a in res.get("abandoned", []):
            print(f"  ⛔ {a}")
        for s in res.get("skipped", []):
            print(f"  ⚠️  {s}")
        if not res["games"]:
            print("  (no finished games ingested for that date yet — if "
                  "tonight's games are still in progress, run this again "
                  "after they end)")
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠️  results ingest failed: {exc}")
    n = ledger.settle_from_history(lconn, hconn)
    # Parlay tickets grade off their legs' verdicts in the singles journal,
    # so this has to run AFTER the settle above or every ticket would find
    # its legs still open and wait another day for no reason.
    try:
        from engine import parlayledger
        pr = parlayledger.settle(lconn)
        if pr["settled"] or pr["waiting"]:
            print(f"  parlays: graded {pr['settled']}, "
                  f"{pr['waiting']} waiting on legs")
        # And the mirror of resettle_mismatches: when a single moved (a
        # partial-data grade healed, or repair-premature reopened it), any
        # settled ticket resting on it re-grades or reopens with it.
        rp = parlayledger.resettle(lconn)
        if rp["fixed"] or rp["reopened"]:
            print(f"  ⚠️  parlays re-audited: {len(rp['fixed'])} re-graded, "
                  f"{rp['reopened']} reopened with their legs")
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠️  parlay settle skipped: {exc}")
    # The learning step: fresh grades re-mine the journal for loss
    # patterns, so a slice that just crossed the evidence bar vetoes
    # picks on the next build.
    try:
        from engine import losspatterns
        lp = losspatterns.refresh(lconn)
        if lp["closed"]:
            print(f"  loss patterns: {len(lp['closed'])} slice(s) "
                  "self-closed — see the Record page")
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠️  loss-pattern mining skipped: {exc}")
    try:
        from engine import journalfit
        jf = journalfit.refresh(lconn)
        for f in jf["temperatures"]["fitted"]:
            print(f"  journal fit: {f['key']} temperature "
                  f"T={f['temperature']} on {f['n']} settled bets")
        for f in jf["memory"]["fitted"]:
            if f["adopted"]:
                print(f"  journal fit: {f['key']} player memory on "
                      f"({f['players']} corrected)")
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠️  journal fit skipped: {exc}")
    try:
        from engine import hypotheses
        hs = hypotheses.retest(lconn)
        closed_h = [h for h in hs.get("hypotheses") or []
                    if h.get("action") == "close"]
        if closed_h:
            print(f"  hypotheses: {len(closed_h)} confirmed closure(s) "
                  "enforcing — see the Record page")
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠️  hypothesis retest skipped: {exc}")
    # The prose lanes (nightly postmortem, weekly brief): pennies per
    # call, so they guard themselves — no key = silent skip, one entry
    # per night/week, and they stand down once the monthly cap is spent.
    try:
        from engine import prose
        prose.nightly(lconn, print)
        prose.weekly(lconn, print)
        prose.weekly_lab(lconn, print)
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠️  prose lanes skipped: {exc}")
    ledger.export_json(lconn, ROOT / "web" / "data" / "record.json")
    after = counts(lconn)
    print(f"  journal: settled {n} pick(s)")
    # Every bucket that has (or had) something open, not just main/longshot.
    # Most open picks live in longshot_watch and the samplers; reporting two
    # buckets made a pass that cleared 40 watch rows look like it did nothing.
    cats = sorted({c for (c, s) in list(before) + list(after) if s == "open"}
                  | {"main", "longshot"})
    for cat in cats:
        b_open, a_open = before.get((cat, "open"), 0), after.get((cat, "open"), 0)
        if not (b_open or a_open):
            continue
        graded = sum(v for (c, s), v in after.items()
                     if c == cat and s in ("won", "lost", "push"))
        moved = "" if b_open == a_open else "  ←"
        print(f"  {cat:>15}: open {b_open} → {a_open}"
              f"   ({graded} graded total){moved}")
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
    if "--doctor" in argv:
        import doctor
        sys.exit(doctor.main([a for a in argv if a != "--doctor"]))
    if "--weigh-in" in argv:
        weigh_in_cli(argv)
        return
    if "--confirm-qb" in argv:
        confirm_qb_cli(argv)
        return
    if "--card-venue" in argv:
        card_venue_cli(argv)
        return
    if "--refresh-rosters" in argv:
        i = argv.index("--refresh-rosters")
        who = " ".join(a for a in argv[i + 1:] if not a.startswith("-")) or None
        refresh_rosters(who)
        return
    if "--odds-doctor" in argv:
        odds_doctor()
        return
    if "--coverage" in argv:
        from engine.coverage import report
        i = argv.index("--coverage")
        want = [a.lower() for a in argv[i + 1:] if not a.startswith("-")]
        print(report(want or None))
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
    if "--why-ufc" in argv:
        why_ufc(argv)
        return
    if "--probe-live" in argv:
        from engine.ufc import live as _live
        i = argv.index("--probe-live")
        day = (argv[i + 1] if len(argv) > i + 1
               and not argv[i + 1].startswith("-") else None)
        for line in _live.probe(day):
            print(line)
        return
    if "--probe-weighins" in argv:
        from engine.ufc import weighin_feed
        i = argv.index("--probe-weighins")
        day = (argv[i + 1] if len(argv) > i + 1
               and not argv[i + 1].startswith("-") else None)
        for line in weighin_feed.probe(day):
            print(line)
        return
    if "--side-bias" in argv:
        i = argv.index("--side-bias")
        who = next((a.lower() for a in argv[i + 1:]
                    if not a.startswith("-")), "mlb")
        side_bias(who)
        return
    if "--repair-premature" in argv:
        repair_premature_cli(argv)
        return
    if "--why-pick" in argv:
        i = argv.index("--why-pick")
        rest = [a for a in argv[i + 1:] if not a.startswith("-")]
        if not rest:
            print('usage: python3 launch.py --why-pick "Player Name" [sport]')
            return
        sport = rest[-1].lower() if rest[-1].lower() in (
            "mlb", "nfl", "nba", "wnba", "cfb") else "mlb"
        who = " ".join(rest[:-1] if sport == rest[-1].lower() else rest)
        why_pick(who, sport)
        return
    if "--why-live" in argv:
        i = argv.index("--why-live")
        who = next((a.lower() for a in argv[i + 1:]
                    if not a.startswith("-")), "mlb")
        why_live(who)
        return
    if "--odds-audit" in argv:
        odds_audit()
        raise SystemExit(0)
    if "--why-many" in argv:
        i = argv.index("--why-many")
        sp = argv[i + 1] if len(argv) > i + 1 and not argv[i + 1].startswith("-") else "mlb"
        why_many(sp)
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
    if "--stuck" in argv:
        show_stuck()
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

    print("Qellys Book — grabbing the newest live data for both leagues…")
    if not _with_odds():
        print("  (no ODDS_API_KEY set — using model/proxy lines; live scores still update)")
    refresh_all()

    try:
        server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    except OSError as exc:
        # "Address already in use" is not a crash, it is the single most
        # ordinary thing that can happen: the site is already running in
        # another window. A traceback for that teaches somebody to be
        # afraid of their own tool.
        if getattr(exc, "errno", None) not in (48, 98, 10048):
            raise
        print(f"\n  ⚠️  Port {port} is already in use — Qellys Book is almost "
              f"certainly already running.\n"
              f"\n  Open it:            http://localhost:{port}\n"
              f"  Or use another port: python3 launch.py {port + 1}\n"
              f"\n  If you want to restart it, close the other Terminal "
              f"window (Ctrl+C in it) and run this again. To find it:\n"
              f"      lsof -ti :{port}          ← the process id\n"
              f"      kill $(lsof -ti :{port})  ← stop it\n")
        return
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

    if "--auto-update" in argv:
        # Opt-in, every run: this pulls code and executes it, so it should
        # be a thing you asked for this morning, not a setting you forgot.
        if _auto_update():
            _restart_into_new_code()
        threading.Thread(target=_auto_updater, daemon=True).start()
        print(f"Auto-update ON — pulling pushed fixes every "
              f"{AUTO_UPDATE_EVERY_S // 60} min and restarting into them.")

    if interval > 0:
        t = threading.Thread(target=_background_refresher, args=(interval,), daemon=True)
        t.start()
        print(f"Auto-refresh every {interval}s (scores free; odds budgeted).")
        # Its own clock: a fight moves in seconds, and this feed is free.
        threading.Thread(target=_live_ufc_refresher, daemon=True).start()
        print(f"  UFC live fights: every {LIVE_FAST_S}s while a bout is on, "
              f"{LIVE_IDLE_S}s otherwise.")
        try:
            from engine.oddsbudget import summary as _bsum
            if _with_odds():
                print("  " + _bsum())
        except Exception:
            pass

    print(f"\nQellys Book running (LIVE data) → http://localhost:{port}")
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
