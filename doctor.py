#!/usr/bin/env python3
"""One command that answers "is anything wrong?" — and exits nonzero if so.

The diagnostics already existed, scattered across nine launcher flags:
--check, --stuck, --data-audit, --odds-doctor, --coverage, --why-empty.
Each answers one question well, and running all nine by hand every morning
is a thing nobody does. So they were only ever run AFTER something looked
broken — which is the one time a health check is too late to help.

This composes them into a single pass with a verdict. Every check is
independent and wrapped: a check that throws reports itself as a failed
check rather than taking the run down with it, because a health monitor
that goes silent when it breaks is worse than no monitor at all.

    python3 doctor.py              # full pass, human-readable
    python3 doctor.py --quiet      # findings only — nothing if all clear
    python3 doctor.py --json       # machine-readable, for an agent
    python3 doctor.py --skip-tests # the slow one, when iterating
    python3 doctor.py --code-only  # for CI: skip everything needing the laptop

Exit codes: 0 all clear · 1 warnings only · 2 something needs a human.
"""

from __future__ import annotations

import datetime as _dt
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

OK, WARN, FAIL = "ok", "warn", "fail"
_RANK = {OK: 0, WARN: 1, FAIL: 2}

# A slate JSON older than this means the launcher is not running. Six hours
# clears an overnight gap on a laptop that was closed, without letting a
# genuinely dead refresh loop hide for a full day.
STALE_SLATE_H = 6
# Player logs this far behind for a sport with recent games means the
# ingest is not keeping up. Two days survives a normal off-day.
STALE_LOGS_D = 2
# Below this many credits, a busy evening can run the month dry.
LOW_CREDITS = 2000


def _no_data(what: str) -> str:
    return (f"no {what} on this machine — this check needs the machine that "
            f"runs the builds")


def has_history() -> bool:
    """Is there a real stats DB here, or would connect() invent an empty one?

    This matters more than it looks. The databases are gitignored, so a
    fresh clone — a CI box, a scheduled cloud session — has neither. Every
    data check would then run against a database sqlite creates on the spot
    and report "0 open bets, no problems found", which is not a pass. It is
    a health monitor confidently describing a machine it cannot see.
    """
    from engine import db
    p = Path(db.DEFAULT_DB)
    return p.exists() and p.stat().st_size > 1_000_000


def has_journal() -> bool:
    from engine import ledger
    p = Path(ledger.DEFAULT_DB)
    if not p.exists():
        return False
    try:
        from engine import ledger as _l
        return _l.connect().execute(
            "SELECT COUNT(*) FROM bets").fetchone()[0] > 0
    except Exception:
        return False


class Report:
    def __init__(self):
        self.checks: list[dict] = []

    def add(self, name, status, detail, fix=""):
        self.checks.append({"check": name, "status": status,
                            "detail": detail, "fix": fix})

    @property
    def verdict(self):
        return max((_RANK[c["status"]] for c in self.checks), default=0)


def _check(rep, name):
    """Decorator-ish helper: run a check, and turn a crash INTO a finding.

    A bare try/except that swallows would make a broken check look healthy,
    which is the specific failure mode that makes monitoring worthless."""
    def run(fn):
        try:
            fn()
        except Exception as exc:
            rep.add(name, FAIL, f"the check itself failed: {exc!r}",
                    "this is a bug in doctor.py, not necessarily in the app")
    return run


# --- checks -----------------------------------------------------------------
def check_tests(rep):
    @_check(rep, "test suite")
    def _():
        p = subprocess.run([sys.executable, "run_tests.py"], cwd=ROOT,
                           capture_output=True, text=True, timeout=900)
        tail = (p.stdout or "").strip().splitlines()
        last = tail[-1] if tail else "(no output)"
        if p.returncode == 0:
            rep.add("test suite", OK, last)
        else:
            bad = [l.strip() for l in tail if "❌" in l or "FAIL" in l]
            rep.add("test suite", FAIL,
                    f"{last} · {len(bad)} failing file(s): {', '.join(bad[:5])}",
                    "python3 run_tests.py")


def check_stuck_bets(rep):
    @_check(rep, "stuck bets")
    def _():
        if not (has_journal() and has_history()):
            rep.add("stuck bets", WARN, _no_data("bet journal"))
            return
        from engine import db, ledger
        today = _dt.date.today().isoformat()
        rows = ledger.why_open(ledger.connect(), db.connect(), today)
        if not rows:
            rep.add("stuck bets", OK,
                    "no open pick is older than the settle window")
            return
        by = {}
        for r in rows:
            by[r["reason"]] = by.get(r["reason"], 0) + 1
        why = " · ".join(f"{n} {k}" for k, n in
                         sorted(by.items(), key=lambda x: -x[1]))
        # "no results ingested" is fixable by a command; the rest usually
        # mean a scratch or a name mismatch and need eyes.
        only_ingest = set(by) == {"no results ingested"}
        rep.add("stuck bets", WARN if only_ingest else FAIL,
                f"{len(rows)} open pick(s) whose day is done — {why}",
                "python3 launch.py --stuck")


def check_slate_freshness(rep):
    @_check(rep, "site data")
    def _():
        if not (ROOT / "web" / "data").is_dir():
            rep.add("site data", WARN, _no_data("built slates"))
            return
        now = time.time()
        stale, missing = [], []
        wanted = {"mlb_recommendations.json": "MLB",
                  "recommendations.json": "NFL",
                  "nba.json": "NBA", "wnba.json": "WNBA",
                  "cfb.json": "CFB", "ufc.json": "UFC"}
        for fn, label in wanted.items():
            p = ROOT / "web" / "data" / fn
            if not p.exists():
                missing.append(label)
                continue
            age_h = (now - p.stat().st_mtime) / 3600
            if age_h > STALE_SLATE_H:
                stale.append(f"{label} {age_h:.0f}h")
        if not stale and not missing:
            rep.add("site data", OK, "every slate rebuilt within "
                                     f"{STALE_SLATE_H}h")
            return
        bits = []
        if stale:
            bits.append("stale: " + ", ".join(stale))
        if missing:
            bits.append("never built: " + ", ".join(missing))
        # Missing is normal out of season; stale means the loop stopped.
        rep.add("site data", WARN if not stale else FAIL, " · ".join(bits),
                "is `python3 launch.py` still running?")


def check_ingest_freshness(rep):
    @_check(rep, "results ingest")
    def _():
        if not has_history():
            rep.add("results ingest", WARN, _no_data("stats database"))
            return
        from engine import db
        h = db.connect()
        today = _dt.date.today()
        behind = []
        # The column is `period`, not `date` — for MLB/NBA it holds the game
        # date, for NFL a week label like "2026-W1". Anything that is not a
        # calendar date is skipped rather than string-compared, which is the
        # mistake that once made --stuck hide every football bet.
        for r in h.execute(
                "SELECT sport, MAX(period) d FROM games "
                "WHERE home_score IS NOT NULL GROUP BY sport"):
            try:
                last = _dt.date.fromisoformat(r["d"])
            except (ValueError, TypeError):
                continue
            gap = (today - last).days
            # Only a complaint if that sport has games scheduled since the
            # last stored final — otherwise it is simply the off-season.
            since = h.execute(
                "SELECT COUNT(*) FROM games WHERE sport=? AND period>? "
                "AND period<=?",
                (r["sport"], r["d"], today.isoformat())).fetchone()[0]
            if gap > STALE_LOGS_D and since:
                behind.append(f"{r['sport'].upper()} last final {r['d']} "
                              f"({gap}d ago, {since} game(s) since)")
        if behind:
            rep.add("results ingest", FAIL, " · ".join(behind),
                    "python3 ingest.py <sport> --seasons <yr>")
        else:
            rep.add("results ingest", OK,
                    "every in-season sport has finals through its last game")


def check_odds_budget(rep):
    @_check(rep, "odds budget")
    def _():
        from engine import oddsbudget as ob
        # No state file means no paid pull has ever run HERE, and load()
        # falls back to ASSUMED_MONTHLY. Reporting that as "500 credits
        # left" is the same lie as reporting an empty journal as clean.
        if not Path(ob.STATE_PATH).exists():
            rep.add("odds budget", WARN, _no_data("odds-budget state"))
            return
        st = ob.load()
        # Recomputed at read time, not the stored headline: the headline is
        # whatever the LAST paid pull summed, and after a key rotation it
        # keeps counting the dead key's ghost until some pull rewrites it.
        remaining = ob.pool_remaining()
        days = ob.days_left_in_month()
        if remaining is None:
            rep.add("odds budget", WARN, "no quota recorded yet — the next "
                    "paid pull will read it", "python3 launch.py --odds-doctor")
            return
        per_day = remaining / max(1, days)
        status = OK if remaining > LOW_CREDITS else WARN
        # With a key ring attached, "how many credits" is a property of the
        # POOL and the interesting detail is how many plans are still alive.
        # One empty key beside a full one is a healthy operation, and a
        # headline that only reported the empty one sent the last reader
        # looking for a second computer.
        try:
            from engine.sources.oddsapi import api_keys
            ring = api_keys()
        except Exception:
            ring = []
        ringnote = ""
        if len(ring) > 1:
            live = sum(1 for k in ring if not ob.key_is_spent(k))
            ringnote = f" · {live} of {len(ring)} key(s) still have credits"
            if live:
                status = OK if remaining > LOW_CREDITS else status
        rep.add("odds budget", status,
                f"{remaining:,} credit(s) left · {days} day(s) in the month "
                f"· {per_day:,.0f}/day available{ringnote}",
                "python3 launch.py --odds-doctor" if status != OK else "")


def check_llm_spend(rep):
    """What the hypothesis lab has actually cost, from its own ledger.

    Never a FAIL — money already spent is a fact to display, not a fault to
    fix. The line exists so the bill is read in the same place as every
    other operational number instead of being remembered."""
    @_check(rep, "llm spend")
    def _():
        from engine import hypotheses as hyp
        from engine import prose
        r = hyp.llm_spend_report()
        cap = prose.cap_usd()
        if not r["runs"]:
            rep.add("llm spend", OK, "no paid Anthropic calls logged — "
                    f"the prose lanes and the lab record themselves, "
                    f"capped at ${cap:.2f}/month")
            return
        capnote = (" · CAPPED — automatic prose paused for the month"
                   if not prose.under_cap() else "")
        rep.add("llm spend", OK,
                f"${r['month_usd']:.2f} of ${cap:.2f}/month across "
                f"{r['month_runs']} run(s) · ${r['total_usd']:.2f} all-time "
                f"({r['runs']} run(s)) · `python3 hypotheses.py --spend`"
                + capnote)


def check_journal_sanity(rep):
    @_check(rep, "bet journal")
    def _():
        if not has_journal():
            rep.add("bet journal", WARN, _no_data("bet journal"))
            return
        from engine import ledger
        c = ledger.connect()
        problems = []
        n_open = c.execute(
            "SELECT COUNT(*) FROM bets WHERE status='open'").fetchone()[0]
        neg = c.execute(
            "SELECT COUNT(*) FROM bets WHERE stake_units < 0").fetchone()[0]
        if neg:
            problems.append(f"{neg} bet(s) with a negative stake")
        noodds = c.execute(
            "SELECT COUNT(*) FROM bets WHERE odds IS NULL "
            "AND status!='open'").fetchone()[0]
        if noodds:
            problems.append(f"{noodds} settled bet(s) with no price — "
                            "their P&L is guesswork")
        bank = ledger.bankroll(c)
        if bank <= 0:
            problems.append(f"bankroll is ${bank:,.2f}")
        if problems:
            rep.add("bet journal", FAIL, " · ".join(problems),
                    "python3 launch.py --data-audit")
        else:
            rep.add("bet journal", OK,
                    f"{n_open} open · bankroll ${bank:,.2f} · no bad rows")


def check_record_page(rep):
    @_check(rep, "record page")
    def _():
        if not has_journal():
            rep.add("record page", WARN, _no_data("bet journal"))
            return
        from engine import ledger
        p = ROOT / "web" / "data" / "record.json"
        if not p.exists():
            rep.add("record page", FAIL, "record.json has never been written",
                    "python3 launch.py --settle all")
            return
        d = json.loads(p.read_text(encoding="utf-8"))
        c = ledger.connect()
        # Compare against the SAME number the page computes, not a private
        # re-count. The page excludes zero-staked graded rows (they were
        # never bets anyone could win a unit on — performance() reports
        # them separately as "unstaked"), and a raw COUNT here read those
        # 181 rows as "the export is behind" and prescribed a settle sweep
        # that could re-run forever without reconciling anything.
        settled = ledger.performance(c)["settled"]
        unstaked = c.execute(
            "SELECT COUNT(*) FROM bets WHERE status IN ('won','lost','push') "
            "AND category='main' AND (stake_units IS NULL OR stake_units <= 0)"
        ).fetchone()[0]
        shown = ((d.get("overall") or {}).get("settled")
                 or (d.get("performance") or {}).get("settled"))
        age_h = (time.time() - p.stat().st_mtime) / 3600
        if shown is not None and shown != settled:
            rep.add("record page", FAIL,
                    f"the page shows {shown} settled bet(s), the journal has "
                    f"{settled} — the export is behind",
                    "python3 launch.py --settle all")
        else:
            note = (f" (+{unstaked} graded-but-unstaked, reported separately"
                    f" — `--resize-unstaked` counts them at 0.1u)"
                    if unstaked else "")
            rep.add("record page", OK,
                    f"{settled} settled bet(s), written {age_h:.0f}h ago"
                    + note)


def check_premature_evidence(rep):
    """Settled game bets must have a FINAL games row behind them.

    The August premature-settle bug's fingerprint: the NBA schedule parser
    passed live in-progress scores into the games table, game bets graded
    against them, and nothing ever re-checked. The parser is fixed and the
    repair pass now audits team markets — this is the tripwire that fires
    if any future feed reintroduces the leak. A settled game bet whose
    games row is scoreless (or missing) was graded on evidence that no
    longer exists.
    """
    @_check(rep, "grade evidence")
    def _():
        if not (has_journal() and has_history()):
            rep.add("grade evidence", WARN, _no_data("journal + history"))
            return
        from engine import db, ledger
        c = ledger.connect()
        h = db.connect()
        marks = ", ".join("?" for _ in ledger.GAME_MARKETS)
        bad = 0
        for b in c.execute(
                f"SELECT * FROM bets WHERE status IN ('won','lost','push') "
                f"AND market IN ({marks})", ledger.GAME_MARKETS).fetchall():
            where, wargs = ledger._hist_where(b)
            rows, actual_fn = ledger._game_bet_evidence(h, b, where, wargs)
            finals = [g for g in rows if g["home_score"] is not None]
            if not finals:
                bad += 1
        if bad:
            rep.add("grade evidence", FAIL,
                    f"{bad} settled game bet(s) have no final score behind "
                    f"them — graded off a partial or vanished games row",
                    "python3 launch.py --settle all   (the repair pass "
                    "re-audits team markets)")
        else:
            rep.add("grade evidence", OK,
                    "every settled game bet has a final games row")


def check_parlay_agreement(rep):
    """The parlay record may never disagree with the singles its legs are in.

    settle() promises it, resettle() now enforces it — this checks it, so a
    regression in either shows up here rather than as a quietly wrong
    Record page. A settled ticket whose stored leg verdicts differ from the
    singles journal's current ones is exactly the healed-leg/dead-ticket
    bug coming back.
    """
    @_check(rep, "parlay agreement")
    def _():
        if not has_journal():
            rep.add("parlay agreement", WARN, _no_data("bet journal"))
            return
        from engine import ledger, parlayledger
        c = ledger.connect()
        parlayledger.ensure_schema(c)
        stale = 0
        for p in c.execute("SELECT * FROM parlays WHERE status IN "
                           "('won','lost','void')").fetchall():
            for leg in c.execute("SELECT * FROM parlay_legs WHERE parlay_id=?",
                                 (p["id"],)).fetchall():
                b = parlayledger._matching_bet(c, p, leg)
                if b is not None and (leg["status"] or "open") != b["status"]:
                    stale += 1
                    break
        if stale:
            rep.add("parlay agreement", FAIL,
                    f"{stale} settled ticket(s) disagree with the singles "
                    f"journal their legs live in",
                    "python3 launch.py --settle all   (runs the parlay "
                    "re-audit)")
        else:
            rep.add("parlay agreement", OK,
                    "every settled ticket matches its legs' singles verdicts")


def check_forecast_log(rep):
    """The hash chain must verify end to end.

    A tamper-evident log that nobody verifies is decoration. A break means
    a past forecast was edited or deleted — the one thing the transparency
    pillar promises cannot happen silently.
    """
    @_check(rep, "forecast log")
    def _():
        if not has_journal():
            rep.add("forecast log", WARN, _no_data("bet journal"))
            return
        from engine import ledger
        c = ledger.connect()
        v = ledger.verify_forecast_log(c)
        if not v["n"]:
            rep.add("forecast log", OK, "empty — seals on the next refresh")
        elif v["ok"]:
            rep.add("forecast log", OK,
                    f"{v['n']:,} forecast(s) sealed · chain verifies · "
                    f"head {(v['head'] or '')[:12]}")
        else:
            rep.add("forecast log", FAIL,
                    f"chain BROKEN at #{v['broken_at']} — entries after "
                    f"#{v.get('verified_through')} are no longer provable",
                    "the log is append-only by design; a break means a row "
                    "was edited or deleted underneath it")


def check_clv_capture(rep):
    """Are closing lines actually being captured, and are they pre-game?

    CLV grades the decision the moment a game starts, which makes it the
    fastest evidence the journal has — but only if the closes are real.
    Two ways they aren't: no snapshot near first pitch (nothing captured)
    or a snapshot taken DURING the game (the odds endpoint returns
    in-play prices, so a late pull on a staggered slate re-prices games
    already running). The second is silently worse — it doesn't leave a
    gap, it fills one with fiction.
    """
    @_check(rep, "clv capture")
    def _():
        if not has_journal():
            rep.add("clv capture", WARN, _no_data("bet journal"))
            return
        from engine import ledger
        cov = ledger.clv_coverage(ledger.connect())
        if not cov["settled"]:
            rep.add("clv capture", OK, "no settled picks yet")
            return
        pct = cov["coverage"] * 100
        ready = cov["ready_sports"]
        detail = (f"{cov['with_close']:,} of {cov['settled']:,} settled picks "
                  f"have a close ({pct:.0f}%)")
        if ready:
            detail += " · sized-on-CLV ready: " + ", ".join(ready)
        if pct < 25:
            rep.add("clv capture", WARN, detail,
                    "closes come from the last PRE-GAME odds snapshot; if the "
                    "pacer's pull lands before the pre-game window opens there "
                    "is nothing near first pitch to capture")
        else:
            rep.add("clv capture", OK, detail)


def check_learning(rep):
    """Is the learning ladder actually recording, and has it learned anything?

    Four rungs run off the journal — the blind-spot miner, the recency
    dial, the per-player memory and the hypothesis lab — and every one of
    them is silent when it has nothing. Silence is indistinguishable from
    "not wired up", which is the whole problem: a ladder that quietly
    stopped feeding would look exactly like a ladder with no findings yet.

    So this reports the two things separately. INPUT is whether the
    journal is carrying the circumstance dimensions the rungs mine — a bet
    logged without them can never be convicted of anything. OUTPUT is
    whether any rung has produced a fitted number or a finding. Input
    without output is normal and early. Output without input is impossible,
    and input going to zero after it was non-zero is the failure worth
    catching.
    """
    @_check(rep, "learning ladder")
    def _():
        if not has_journal():
            rep.add("learning ladder", WARN, _no_data("bet journal"))
            return
        from engine import ledger
        conn = ledger.connect()
        # The dimensions the miner bands. Each is journaled by a different
        # part of the board, so a column that is entirely NULL points at
        # one pipeline rather than at the ladder.
        dims = ("lead_min", "park_hr", "wind_out", "lineup_slot",
                "rest_days", "body_clock", "pen_own", "pen_opp", "loss_cause")
        have = {c[1] for c in conn.execute("PRAGMA table_info(bets)")}
        total = conn.execute("SELECT COUNT(*) FROM bets").fetchone()[0]
        if not total:
            rep.add("learning ladder", OK, "journal is empty — nothing to learn from yet")
            return
        filled, missing_col = {}, []
        for d in dims:
            if d not in have:
                missing_col.append(d)
                continue
            n = conn.execute(
                f"SELECT COUNT(*) FROM bets WHERE {d} IS NOT NULL").fetchone()[0]
            filled[d] = n
        live = [d for d, n in filled.items() if n]
        dead = [d for d, n in filled.items() if not n]

        # OUTPUT: anything any rung has actually fitted or found.
        #
        # A store that cannot be READ is reported, never swallowed. The
        # first version of this check called `load` on every rung; formfit
        # and playerfit expose `_load`, so the getattr raised, a bare
        # except ate it, and the check announced "no rung has convicted
        # anything yet" on a machine where two rungs were full. That is
        # precisely the silence-looks-like-health failure this exists to
        # catch, built into the thing catching it.
        found, unreadable = [], []

        def _rung(label, fn):
            try:
                return fn()
            except Exception as exc:                       # noqa: BLE001
                unreadable.append(f"{label} ({type(exc).__name__})")
                return None

        store = _rung("blind-spot miner",
                      lambda: __import__("engine.losspatterns",
                                         fromlist=["load"]).load())
        if store is not None:
            f = len(store.get("findings") or [])
            c = len(store.get("closed") or [])
            if f or c:
                found.append(f"miner: {f} open, {c} convicted")

        for label, mod in (("recency dial", "engine.formfit"),
                           ("player memory", "engine.playerfit")):
            store = _rung(label, lambda m=mod: __import__(
                m, fromlist=["_load"])._load())
            if isinstance(store, dict) and store:
                n = sum(len(v) if isinstance(v, dict) else 1
                        for v in store.values())
                found.append(f"{label}: {n} fitted")

        store = _rung("hypothesis lab",
                      lambda: __import__("engine.hypotheses",
                                         fromlist=["load"]).load())
        if isinstance(store, dict):
            n_live = len(store.get("hypotheses") or [])
            n_watch = len(store.get("watchlist") or [])
            if n_live or n_watch:
                found.append(f"hypothesis lab: {n_live} live, "
                             f"{n_watch} watched")

        detail = (f"{total:,} journaled picks · {len(live)}/{len(dims)} "
                  f"mineable dimensions carrying data")
        if found:
            detail += " · " + "; ".join(found)
        else:
            detail += " · no rung has convicted anything yet"

        if unreadable:
            rep.add("learning ladder", WARN, detail,
                    "could not read: " + ", ".join(unreadable)
                    + " — the rung may be full and reporting as empty, which "
                      "is the one thing this check must never do quietly")
        elif missing_col:
            rep.add("learning ladder", WARN, detail,
                    "missing column(s): " + ", ".join(missing_col)
                    + " — run any build once; ledger.connect() migrates")
        elif dead:
            rep.add("learning ladder", WARN, detail,
                    "always-NULL: " + ", ".join(dead)
                    + " — those pipelines are not journaling their dimension, "
                      "so the miner can never convict on it")
        else:
            rep.add("learning ladder", OK, detail)


def check_git(rep):
    @_check(rep, "git")
    def _():
        p = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                           capture_output=True, text=True, timeout=60)
        dirty = [l for l in p.stdout.splitlines() if l.strip()]
        # Data files change every build; they are not "uncommitted work".
        code = [l for l in dirty if not l.split()[-1].startswith("web/data/")
                and not l.split()[-1].startswith("data/")]
        if code:
            rep.add("git", WARN, f"{len(code)} uncommitted code file(s): "
                    + ", ".join(l.split()[-1] for l in code[:4]),
                    "git status")
        else:
            rep.add("git", OK, "no uncommitted code changes")


CHECKS = [check_tests, check_stuck_bets, check_slate_freshness,
          check_ingest_freshness, check_odds_budget, check_llm_spend,
          check_journal_sanity, check_record_page, check_premature_evidence,
          check_parlay_agreement, check_forecast_log, check_clv_capture,
          check_learning, check_git]

# The checks that need the laptop's databases, budget state and built
# slates. On a machine that has none of those — CI, a fresh clone — they
# correctly report "not my machine", and six such warnings every night is
# noise that teaches you to ignore the run. --code-only drops them, so a
# red CI run means something is actually red.
DATA_CHECKS = (check_stuck_bets, check_slate_freshness,
               check_ingest_freshness, check_odds_budget, check_llm_spend,
               check_journal_sanity, check_record_page,
               check_premature_evidence, check_parlay_agreement,
               check_forecast_log, check_clv_capture, check_learning)


def run(skip_tests: bool = False, code_only: bool = False) -> Report:
    rep = Report()
    for fn in CHECKS:
        if skip_tests and fn is check_tests:
            continue
        if code_only and fn in DATA_CHECKS:
            continue
        fn(rep)
    return rep


def main(argv: list[str]) -> int:
    rep = run(skip_tests="--skip-tests" in argv,
              code_only="--code-only" in argv)
    if "--json" in argv:
        print(json.dumps({"verdict": ["ok", "warn", "fail"][rep.verdict],
                          "checks": rep.checks}, indent=2))
        return rep.verdict

    quiet = "--quiet" in argv
    mark = {OK: "✅", WARN: "⚠️ ", FAIL: "❌"}
    rows = [c for c in rep.checks if not quiet or c["status"] != OK]
    if not quiet:
        print(f"Qellys Book — health check · "
              f"{_dt.datetime.now():%a %b %-d, %-I:%M %p}\n")
    for c in rows:
        print(f"{mark[c['status']]} {c['check']:<16} {c['detail']}")
        if c["fix"] and c["status"] != OK:
            print(f"   ↳ {c['fix']}")
    if rep.verdict == 0:
        if not quiet:
            print("\nAll clear.")
    else:
        n = sum(1 for c in rep.checks if c["status"] != OK)
        print(f"\n{n} thing(s) need attention.")
    return rep.verdict


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
