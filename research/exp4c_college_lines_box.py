#!/usr/bin/env python3
"""EXP-004c — EXP-004's college results priced at REAL college lines, against the books.

    cd /srv/qellys && sudo -u qellys nice -n 19 python3 research/exp4c_college_lines_box.py

EXP-004 (research/exp4_college_two_stage.py) advanced two college results
on CRPS: B, the two-stage model, on receptions, and H — the direct model's
centre with B's shape — on rushing yards. Neither moves a pick until it
holds where a bet is made, at the books' own line. This is EXP-001c's test
(research/exp1_lines_box.py) for college. Registry EXP-004c.

THE LINES, from two stores the box already keeps, so no credits are spent:
the line snapshots (data/cache/line_history.jsonl — college since
2026-09-30, every book's main line on each paid pull, with the game's
start) and odds_history (sport 'cfb'). For each player, game and market,
each book's LAST two-sided quote before kickoff — never at or after it,
never more than LOOKAHEAD before it; the line most books hang (ties to the
lower); the market's chance for the over the median de-vigged fair of the
books quoting both sides at that line (engine/odds.consensus_fair, with its
own minimum of books; exp1_lines_box.consensus). A quote is placed by the
start it carries (a snapshot's start_ts, an odds_history row's
commence_time) on the game of his that kicks off within NEAR of it, or,
carrying none, on his next kickoff; a quote two same-named players' games
could both claim is dropped. Kickoffs come from the season's schedule
(data/cache/cfb_schedules_2026.csv, which the nightly college ingest
keeps); without it the script says so and stops.

THE PLAYER-GAMES are EXP-004's (exp4_college_two_stage.rows_for,
unchanged): the 2026 regular season from week 4, three games behind him, a
receiver or a back by roster or his own games. A prop joins one by name
and game. A push is left out of scoring.

THE FORECASTS of "over", all from information before the game:
  A, B, H    EXP-004's models, all fitted on FIT (2025: the season before,
             which the live college model's priors already read, and whose
             target counts are the nearest to 2026's; one season also keeps
             the run inside the box's memory)
  A*, B*, H* each recalibrated (a logistic on its logit) at the proxy line
             — the half below A's median — on the same 2025 games, as
             EXP-001c recalibrates on its training seasons
  C          the books' de-vigged consensus
  D          the average of logit(C) and logit(B*) on receptions, of
             logit(H*) on rushing yards — description only

THE DECISION, WRITTEN BEFORE ANY RUN (2026-10-19), on games after
2026-10-17 (EXP-004's freeze) only:
  Q1  B* beats A* in log loss on receptions
  Q2  H* beats A* in log loss on rushing yards
each PASSES when the game-week-clustered bootstrap's upper bound is under
zero at 97.5% (0.05 / 2); right direction otherwise INCONCLUSIVE; wrong
direction FAILS. ONE READ (EXP-001c's AMENDMENT 2, written in from the
start): each question is decided on the first complete weeks after the
freeze, in order, at which its market reaches MIN_DECIDE rows — fixed from
then on, the same on every later run; rows from later weeks are printed
beneath as description. A week is complete when the schedule marks every
one of its games with a major-college (FBS) side completed and the play
file holds at least COMPLETE of them (2025's file held 886 of 888); an
incomplete week stops the count.
If every week after the freeze is complete and a market is still short, it
is decided on all of them when they hold MIN_FLOOR rows, and is otherwise
NO DECISION. Everything up to the freeze is development: it says where
things stand and decides nothing. D against C, flat-stake ROI and anything
else printed is description.

Read-only on every database and file.
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pricetrust as PT                                           # noqa: E402
from research import exp1_lines_box as EL                        # noqa: E402
from research import exp1_two_stage as E1                        # noqa: E402
from research import exp4_college_two_stage as E4                # noqa: E402

FREEZE = E4.FREEZE
SEASON = 2026
FIT = 2025
MARKETS = ("receptions", "rush_yds")
#: The forecast each question tries against A*, by market.
SHAPE = {"receptions": "B*", "rush_yds": "H*"}
MIN_DECIDE = EL.MIN_DECIDE
MIN_FLOOR = 100
COMPLETE = 0.95
LOOKAHEAD = EL.LOOKAHEAD
#: How far a quote's own start may sit from the schedule's kickoff and
#: still name that game. Tight on purpose: the snapshots carry no sport,
#: and an NFL player who shares a college player's name plays a day
#: apart. (Every completed 2025 game in the mirror's schedule has its
#: real kickoff; none is still marked "time TBD".)
NEAR = _dt.timedelta(hours=6)
KEYS = ("A", "A*", "B", "B*", "H", "H*", "C", "D")

_NAMES: dict = {}


def _norm(name: str) -> str:
    n = _NAMES.get(name)
    if n is None:
        from engine.sources.oddsapi import normalize_name
        n = _NAMES[name] = normalize_name(name)
    return n


def schedule(path) -> dict:
    """``{game_id: {"week", "kick" (UTC), "day" (US date), "done", "fbs"}}``
    for the regular season's games in a cfbfastR schedule file."""
    out = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if (r.get("season_type") or "regular") != "regular":
                continue
            try:
                kick = EL._utc(r["start_date"])
                week = int(float(r.get("week") or 0))
            except (KeyError, TypeError, ValueError):
                continue
            out[str(r["game_id"])] = {
                "week": week, "kick": kick, "day": EL.et_date(r["start_date"]),
                "done": str(r.get("completed") or "").strip().upper() == "TRUE",
                "fbs": "fbs" in (r.get("home_division"), r.get("away_division"))}
    return out


def kickoffs(rows: list[dict], sched: dict) -> dict:
    """``{normalized name: sorted [(kickoff, game id)]}`` for the scored rows."""
    out: dict = defaultdict(set)
    for x in rows:
        g = sched.get(str(x.get("gid") or ""))
        if g:
            out[_norm(x["name"])].add((g["kick"], str(x["gid"])))
    return {n: sorted(v) for n, v in out.items()}


def place(games: list, start: _dt.datetime) -> str | None:
    """The one game of his whose kickoff is within NEAR of a quote's own
    start; None for none, or for two (same-named players the same day)."""
    hits = [gid for kick, gid in games if abs(kick - start) <= NEAR]
    return hits[0] if len(hits) == 1 else None


def next_game(games: list, taken: _dt.datetime) -> tuple | None:
    """(kickoff, game id) of his next game within LOOKAHEAD of ``taken``."""
    for kick, gid in games:
        if kick > taken:
            return (kick, gid) if kick - taken <= LOOKAHEAD else None
    return None


def gather(kicks: dict, snapshots=(), history=(), funnel: Counter | None = None) -> dict:
    """``{(name, game id, market): {book: (line, over, under)}}`` — each
    book's last quote before kickoff, from snapshot rows (dicts as
    line_history.jsonl writes them) and odds_history rows (taken_at,
    player, market, book, line, over, under, commence_time)."""
    funnel = funnel if funnel is not None else Counter()
    last: dict = {}

    def keep(name, gid, market, book, taken, line, over, under):
        k = (name, gid, market, str(book or "").lower())
        if k not in last or taken > last[k][0]:
            last[k] = (taken, line, over, under)

    def game_of(games, taken, start):
        if start is None:
            got = next_game(games, taken)
            return got[1] if got else None
        if taken >= start or start - taken > LOOKAHEAD:
            return None
        return place(games, start)

    for r in snapshots:
        funnel["snapshot quotes on a scored player"] += 1
        name = _norm(r.get("player") or "")
        try:
            taken = _dt.datetime.fromtimestamp(float(r["ts"]), _dt.timezone.utc)
            start = (_dt.datetime.fromtimestamp(float(r["start_ts"]), _dt.timezone.utc)
                     if r.get("start_ts") is not None else None)
            line = float(r["line"])
        except (KeyError, TypeError, ValueError):
            continue
        gid = game_of(kicks.get(name) or [], taken, start)
        if gid is None:
            continue
        funnel["snapshot quotes placed before a kickoff"] += 1
        keep(name, gid, r.get("market"), r.get("book"), taken, line, r.get("over_odds"), r.get("under_odds"))
    for taken_at, player, market, book, line, over, under, commence in history:
        funnel["odds_history quotes read"] += 1
        name = _norm(player or "")
        games = kicks.get(name)
        if not games or line is None or not taken_at:
            continue
        try:
            taken = EL._utc(taken_at)
            start = EL._utc(commence) if commence else None
        except ValueError:
            continue
        gid = game_of(games, taken, start)
        if gid is None:
            continue
        funnel["odds_history quotes placed before a kickoff"] += 1
        keep(name, gid, market, book, taken, float(line), over, under)
    per: dict = defaultdict(dict)
    for (name, gid, market, book), (_t, line, over, under) in last.items():
        per[(name, gid, market)][book] = (line, over, under)
    funnel["props (player, game, market)"] += len(per)
    return dict(per)


def history_rows(conn) -> list:
    """odds_history's college rows of the two markets (commence_time NULL
    on a table older than that column)."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(odds_history)")}
    start = "commence_time" if "commence_time" in cols else "NULL"
    q = (f"SELECT taken_at, player, market, book, line, over_odds, under_odds, {start} FROM odds_history "
         f"WHERE sport='cfb' AND market IN ({','.join('?' * len(MARKETS))})")
    return conn.execute(q, MARKETS).fetchall()


def chances(fit, x: dict, line: float) -> dict:
    """A's, B's and H's chance of the over at ``line``."""
    mb = fit.mean_b(x)
    h = fit.cdf_b(x, [line], scale=x["mu_a"] / mb)[0] if mb > 0 else fit.cdf_b(x, [line])[0]
    return {"A": 1.0 - fit.cdf_a(x, line), "B": 1.0 - fit.cdf_b(x, [line])[0], "H": 1.0 - h}


def calibrators(fit, rows: list[dict]) -> dict:
    """``{(market, model): Calibrator}`` fitted at the proxy line."""
    pairs: dict = defaultdict(list)
    for x in rows:
        line = EL.proxy_line(fit, x)
        if x["y"] == line:
            continue
        y = 1.0 if x["y"] > line else 0.0
        for k, p in chances(fit, x, line).items():
            pairs[(x["m"], k)].append((p, y))
    return {k: EL.Calibrator(v) for k, v in pairs.items()}


def scored(fit, cals: dict, props: dict, rows: list[dict], sched: dict, funnel: Counter | None = None) -> list[dict]:
    funnel = funnel if funnel is not None else Counter()
    out = []
    for x in rows:
        g = sched.get(str(x.get("gid") or ""))
        p = props.get((_norm(x["name"]), str(x.get("gid") or ""), x["m"])) if g else None
        if not p:
            continue
        c = EL.consensus(p)
        if not c:
            continue
        line, fair, books, price = c
        funnel["props joined to a scored player-game"] += 1
        if x["y"] == line:
            funnel["pushes left out"] += 1
            continue
        raw = chances(fit, x, line)
        row = {"m": x["m"], "day": g["day"], "wk": f"{x['s']}-{x['week']:02d}", "week": x["week"],
               "after": g["day"] > FREEZE, "y": 1.0 if x["y"] > line else 0.0, "line": line, "books": books,
               "price": price, "C": fair, **raw}
        for k in ("A", "B", "H"):
            row[k + "*"] = cals[(x["m"], k)](raw[k])
        row["D"] = EL._sig(0.5 * EL._logit(row[SHAPE[x["m"]]]) + 0.5 * EL._logit(fair))
        out.append(row)
    return out


def complete_weeks(sched: dict, played: set, after: str = FREEZE) -> tuple[list[int], bool]:
    """(the weeks after ``after`` that are complete, in order, up to the
    first that is not; whether every week after it is complete). Only
    games with an FBS side count: no other game carries a prop."""
    by: dict = defaultdict(list)
    for gid, g in sched.items():
        if g["fbs"] and g["day"] > after:
            by[g["week"]].append((gid, g))
    out = []
    for wk in sorted(by):
        games = by[wk]
        if not all(g["done"] for _gid, g in games):
            break
        if sum(1 for gid, _g in games if gid in played) < COMPLETE * len(games):
            break
        out.append(wk)
    return out, bool(by) and len(out) == len(by)


def decision_weeks(post: list[dict], weeks: list[int], market: str, season_over: bool) -> tuple:
    """(the weeks that decide ``market``, how) — ONE READ: the first
    complete weeks whose rows reach MIN_DECIDE; at the season's end every
    complete week if they reach MIN_FLOOR; else ((), why not)."""
    n, chosen = 0, []
    for wk in weeks:
        chosen.append(wk)
        n += sum(1 for r in post if r["week"] == wk and r["m"] == market)
        if n >= MIN_DECIDE:
            return tuple(chosen), f"the first complete weeks to reach {MIN_DECIDE} rows"
    if season_over:
        if n >= MIN_FLOOR:
            return tuple(chosen), f"every week after the freeze ({n} rows, under {MIN_DECIDE})"
        return (), f"NO DECISION: the season's {n} rows are under {MIN_FLOOR}"
    return (), f"NOT YET: {n} rows in complete weeks, {MIN_DECIDE} needed"


def report(label: str, rows: list[dict]) -> None:
    print(f"\n{label}")
    for m in MARKETS:
        t = [r for r in rows if r["m"] == m]
        if not t:
            print(f"  {m:<10} no rows")
            continue
        ll = {k: sum(EL._ll(r[k], r["y"]) for r in t) / len(t) for k in KEYS}
        hit = sum(r["y"] for r in t) / len(t)
        print(f"  {m:<10} n={len(t):,}  over hit {hit:.3f}  log loss " + "  ".join(f"{k} {v:.4f}" for k, v in ll.items()))
        n, r_ = EL.roi(t, SHAPE[m])
        print(f"  {'':<10} secondary: {SHAPE[m]} off the market by >{EL.EDGE:.0%} on {n:,} props, flat ROI {r_:+.3f}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=str(ROOT / "data" / "history.db"))
    ap.add_argument("--snapshots", help="the line snapshots (default data/cache/line_history.jsonl)")
    ap.add_argument("--schedule", default=str(E4.CACHE / f"cfb_schedules_{SEASON}.csv"))
    a = ap.parse_args(argv)
    print("EXP-004c — EXP-004's college models at the books' own lines (receptions, rush_yds)")
    need = [p for p in (Path(a.schedule), E4.CACHE / f"cfb_player_stats_{SEASON}.csv",
                        E4.CACHE / f"cfb_player_stats_{FIT}.csv") if not p.exists()]
    if need:
        print("  NOT YET: missing " + ", ".join(str(p) for p in need)
              + " (the nightly college ingest writes them)")
        return 0
    sched = schedule(a.schedule)
    targets = E4.rows_for(SEASON, MARKETS)
    kicks = kickoffs(targets, sched)
    funnel: Counter = Counter()
    conn = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    hist = history_rows(conn)
    conn.close()
    snaps = PT._snapshot_rows(a.snapshots, set(MARKETS), set(kicks), _norm)
    props = gather(kicks, snaps, hist, funnel)
    hist = snaps = None
    have = [s for s in (FIT - 1, FIT, SEASON) if (E4.CACHE / f"cfb_player_stats_{s}.csv").exists()]
    print(f"  play files on this box: {', '.join(map(str, have))} ({FIT - 1}'s only anchors {FIT}'s early weeks)")
    fit_rows = E4.rows_for(FIT, MARKETS)
    fit = E1.Fit(fit_rows)
    cals = calibrators(fit, fit_rows)
    print(f"  fitted and recalibrated on {FIT}: {len(fit_rows):,} player-games; scored 2026 player-games "
          f"{len(targets):,} ({len(kicks):,} players with a kickoff)")
    for (m, k), c in sorted(cals.items()):
        print(f"  calibration {m:<10} {k}*: a {c.a:+.3f} b {c.b:.3f}")
    rows = scored(fit, cals, props, targets, sched, funnel)
    print("  funnel: " + " → ".join(f"{k} {v:,}" for k, v in funnel.items()))
    dev = [r for r in rows if not r["after"]]
    post = [r for r in rows if r["after"]]
    print(f"  scored {len(rows):,} props ({len(dev):,} development, {len(post):,} after {FREEZE})")
    report(f"DEVELOPMENT (2026 through {FREEZE}) — decides nothing", dev)
    played = {g["gid"] for gs in E4._season(SEASON).values() for g in gs}
    weeks, over = complete_weeks(sched, played)
    print(f"\nDECISION (games after {FREEZE}; one read per question)")
    print(f"  complete weeks after the freeze: {', '.join(map(str, weeks)) or 'none yet'}"
          + ("; the regular season is complete" if over else ""))
    decided: set = set()
    for m, key, name in (("receptions", "B*", "Q1 two-stage beats direct, receptions"),
                         ("rush_yds", "H*", "Q2 hybrid beats direct, rushing yards")):
        chosen, how = decision_weeks(post, weeks, m, over)
        if not chosen:
            pace = Counter(r["week"] for r in dev if r["m"] == m)
            per = sum(pace.values()) / len(pace) if pace else 0.0
            print(f"  {name:<40} {how}" + (f" (development weeks averaged {per:.0f} rows)" if pace else ""))
            continue
        decided |= set(chosen)
        t = [r for r in post if r["m"] == m and r["week"] in set(chosen)]
        mean, lo, hi = EL.compare(t, key, "A*")
        verdict = "PASSES" if hi < 0 else ("INCONCLUSIVE" if mean < 0 else "FAILS")
        print(f"  {name:<40} weeks {chosen[0]}-{chosen[-1]}, {how}: {len(t):,} rows  "
              f"{mean:+.5f} [{lo:+.5f}, {hi:+.5f}]  {verdict}")
    if decided:
        report("decision weeks, both markets", [r for r in post if r["week"] in decided])
    later = [r for r in post if r["week"] not in decided]
    if later:
        report("AFTER THE FREEZE, OUTSIDE A DECISION — description, decides nothing", later)
    return 0


if __name__ == "__main__":
    sys.exit(main())
