#!/usr/bin/env python3
"""The NBA lab's two changes, measured on the box's own games and lines.
Read-only: it replays the board, it writes nothing.

    cd /srv/qellys && sudo -u qellys nice -n 19 python3 nbalabcheck.py

Ethan, 2026-11-04: "work on the nba most likely and edge bets ... find and
invent more tools and data ... make better picks." The lab (docs/NBA_LAB.md)
measured two changes on two full seasons of the league's play-by-play:

* SHOOTING, LUCK TAKEN OUT (engine/nba/shooting, ON since this commit):
  points and threes rebuilt from shot volume at long-run percentages.
* THE SPREAD THAT FOLLOWS THE PROJECTION (`hoops.NBA.sd_power`, OFF until
  ``QB_NBA_SPREAD=1``): variance = a × projection^c instead of one CV.

This replays every stored NBA player-game through the board's own pricer
(engine/hoopsreplay — the twenty games before it, the production
projection, the spreads the build fits from the box's logs, the calibration
as stored), once with each change off and once on, and prints per market, over the props BOTH runs priced: how far the
projections land from what happened (RMSE) and how good the chances were
(Brier); and each run's recommended bets on the games priced against a
harvested closing line, with their record and return.

THE BRIER IS READ ON HALF-POINT LINES ONLY (2026-11-04). The replay's own
line, where no closing line was stored, was his recent average rounded, a
whole number half the time. A rebound or assist count lands exactly on a
whole number about one time in five, the push is dropped from the score,
and the board's chance never counts a push (a real prop line is a half
point). On the lab's two seasons replayed that way, that alone made the
spread look 2.5% worse for rebounds and assists on whole-number lines and
about even on half-point ones. The replay's line is always a half point
now (`hoopsreplay._naive_line`); the filter stays for any closing line
that is whole. A closing line is scored on its own too.

THE LADDER (Most Likely's kind of bet). Near the line is only half of it:
Most Likely bets overs on lines well under a player, where one CV per stat
was wrong the most. Every game the fitters' walk projects (the board's own
projection, no gate in the way) is priced as an over at lines 0.5, 0.65 and
0.8 of his projection, with the spread off and on: the Brier, and the overs
each spread calls 80% or more, with how often they hit. Not the average of
what was said against the average hit: on the lab's two seasons replayed at
the board's fitted spreads, one wide CV said 68.4% for points overs that
hit 68.3% on average while calling a few 82% that hit 60% and never finding
the 18,600 the new spread called 84-93% and that hit 84-92%. An average can
be right while both ends are wrong.

Both spread reads come twice: through today's stored calibration (what
switching it on tonight would do) and raw (what it does once the NBA refit
learns on it). The last line says whether the spread is ready for that
refit (the runbook's step JY has the refit and the switch).
"""

from __future__ import annotations

import argparse
import math
import os
import sys

SHOOT = ("pts", "fg3m", "pra", "pts_reb", "pts_ast")
SPREAD = ("pts", "reb", "ast", "pra", "pts_reb", "pts_ast", "reb_ast")

#: Most Likely's kind of over: lines at these fractions of his projection.
LADDER = (0.5, 0.65, 0.8)

#: The spread is ready for the refit when, raw: the ladder's Brier is lower
#: in at least READY_LADDER of the seven markets; its overs called TOP or
#: more hit within HONEST of what it called (on at least MIN_TOP of them)
#: in as many; and no market's Brier near the line (half-point lines) is
#: worse by more than NEAR_SLACK of itself.
READY_LADDER = 5
TOP = 0.80
HONEST = 0.03
MIN_TOP = 100
NEAR_SLACK = 0.005

#: A closing-line comparison is printed once both runs priced this many.
MIN_BOOK = 30


def board_tune(conn):
    """The NBA's tuning as the live build prices with it
    (`hoops_fit.fitted_tuning`: the spreads fitted from the box's own
    logs), or the inherited numbers if the fit fails, as the build does.
    The replay's own default is the inherited numbers, which are not the
    spread the board uses: the comparison has to be against the real one."""
    from engine.hoops import NBA
    try:
        from engine.hoops_fit import fitted_tuning
        return fitted_tuning(conn, "nba")[0]
    except Exception:                                        # noqa: BLE001
        return NBA


def _run(conn, markets, shooting: bool, spread: bool, calib: bool = True, tune=None) -> dict:
    from engine import calibrate, hoopsreplay
    os.environ["QB_NBA_SHOOTING"] = "1" if shooting else "0"
    os.environ["QB_NBA_SPREAD"] = "1" if spread else "0"
    if calib:
        out = hoopsreplay.replay(conn, "nba", markets, tune=tune)
    else:
        with calibrate.disabled():
            out = hoopsreplay.replay(conn, "nba", markets, tune=tune)
    return {m: (rep, counts) for m, rep, counts in out}


def _book(rep) -> str:
    g = (rep.segments or {}).get("book") or {}
    n = int(g.get("n_bets") or 0)
    if not n:
        return "no book-priced bets"
    return f"{n} book bets {g.get('win_rate', 0):.1%}, ROI {g.get('roi', 0):+.1%}"


def _brier(S, keys):
    tot = n = 0
    for k in keys:
        s = S[k]
        won = (s.actual > s.line) if s.side == "OVER" else (s.actual < s.line)
        tot += (s.hit_prob - (1.0 if won else 0.0)) ** 2
        n += 1
    return tot / n if n else None


def _paired(ra, rb) -> dict:
    """Over the props BOTH runs priced — a change that makes the board
    refuse more props must not be scored on a different set from the one
    it replaced: ``n``, the two RMSEs over all of them, the two Briers over
    the half-point lines (``n_half``; ``n_whole`` left out), and the two
    Briers over those priced at a closing line in both (``n_book``)."""
    A = {s.key: s for s in ra.settled if getattr(s, "key", "")}
    B = {s.key: s for s in rb.settled if getattr(s, "key", "")}
    keys = [k for k in A if k in B]
    out = {"n": len(keys)}
    if not keys:
        return out

    def rmse(S):
        return (sum((S[k].projection - S[k].actual) ** 2 for k in keys) / len(keys)) ** 0.5

    half = [k for k in keys if A[k].line % 1 and B[k].line % 1]
    book = [k for k in half if A[k].basis == "book" and B[k].basis == "book"]
    out.update(rmse=(rmse(A), rmse(B)), n_half=len(half), n_whole=len(keys) - len(half),
               brier=(_brier(A, half), _brier(B, half)), n_book=len(book),
               book=(_brier(A, book), _brier(B, book)))
    return out


def _compare(title: str, markets, off: dict, on: dict, show_rmse: bool) -> dict:
    """Prints each market; returns ``{market: paired}`` for the verdicts."""
    print(f"\n{title}")
    got = {}
    for m in markets:
        a, b = off.get(m), on.get(m)
        if not a or not b:
            print(f"  {m:8s} nothing to replay")
            continue
        ra, rb = a[0], b[0]
        p = _paired(ra, rb)
        if not p.get("n") or None in p.get("brier", (None,)):
            print(f"  {m:8s} no half-point prop priced both ways")
            continue
        got[m] = p
        line = (f"  {m:8s} {p['n']:>6} priced both ways (off {ra.total_priced}, on {rb.total_priced}; "
                f"{a[1].get('book', 0)} at a closing line)")
        if show_rmse:
            line += f"  RMSE {p['rmse'][0]:.3f} → {p['rmse'][1]:.3f}"
        line += (f"  Brier {p['brier'][0]:.4f} → {p['brier'][1]:.4f} on {p['n_half']} half-point lines"
                 f" ({p['n_whole']} whole-number lines left out: they can push)")
        print(line)
        if p["n_book"] >= MIN_BOOK:
            print(f"  {'':8s} at a closing line: Brier {p['book'][0]:.4f} → {p['book'][1]:.4f} "
                  f"over {p['n_book']}")
        print(f"  {'':8s} off: {_book(ra)}  |  on: {_book(rb)}")
    return got


def _ladder(conn, markets, tune) -> tuple[dict, dict]:
    """``(through today's calibration, raw)``, each ``{market: {"n", "hit",
    "off": read, "on": read}}`` with a read ``{"brier", "said", "top": (n,
    said, hit)}``: overs at lines LADDER × his projection over every game
    the fitters' walk projects, priced with the spread off and on; ``top``
    is the overs that spread called TOP or more. One walk per market feeds
    both: the projection does not depend on the spread or the calibration."""
    from engine import calibrate, hoopsreplay as HR
    from engine.nba.prob import p_over
    hist = HR.histories(conn, "nba")
    cal, raw = {}, {}
    for m in markets:
        rep = HR.walk(HR._entries(hist, m), m, "nba", tune=tune)
        rows = []
        for s in rep.settled:
            for k in LADDER:
                line = math.floor(k * s.projection) + 0.5
                if 0 < line < s.projection:
                    rows.append((s.projection, line, 1.0 if s.actual > line else 0.0))
        if not rows:
            continue
        outs = [o for *_, o in rows]
        base = {"n": len(rows), "hit": sum(outs) / len(rows)}
        cal[m], raw[m] = dict(base), dict(base)
        for on in (False, True):
            os.environ["QB_NBA_SPREAD"] = "1" if on else "0"
            ps = [p_over(m, mu, line, tune) for mu, line, _ in rows]
            for got, use in ((raw[m], ps), (cal[m], [calibrate.calibrated(tune.key, m, p) for p in ps])):
                top = [(p, o) for p, o in zip(use, outs) if p >= TOP]
                got["on" if on else "off"] = {
                    "brier": sum((p - o) ** 2 for p, o in zip(use, outs)) / len(rows),
                    "said": sum(use) / len(use),
                    "top": (len(top), sum(p for p, _ in top) / len(top) if top else None,
                            sum(o for _, o in top) / len(top) if top else None)}
    return cal, raw


def _top(t) -> str:
    n, said, hit = t
    return f"{n:,} at {said:.0%}, hit {hit:.0%}" if n else "none"


def _honest(t) -> bool:
    n, said, hit = t
    return n >= MIN_TOP and abs(said - hit) <= HONEST


def _print_ladder(title: str, lad: dict) -> dict:
    """Prints each market; returns ``{market: (Brier lower, top honest)}``."""
    print(f"\n{title}")
    out = {}
    for m, g in lad.items():
        a, b = g["off"], g["on"]
        print(f"  {m:8s} {g['n']:>6} overs, {g['hit']:.1%} hit: Brier {a['brier']:.4f} → {b['brier']:.4f}; "
              f"called {TOP:.0%} or more: {_top(a['top'])} → {_top(b['top'])}")
        out[m] = (b["brier"] < a["brier"], _honest(b["top"]))
    return out


def _ready(near_raw: dict, ladder_raw: dict) -> tuple[bool, str]:
    """The spread's verdict from the raw reads: (ready, why)."""
    n = len(ladder_raw)
    lower = sum(1 for b, _ in ladder_raw.values() if b)
    honest = sum(1 for _, h in ladder_raw.values() if h)
    worse = [m for m, p in near_raw.items()
             if p["brier"][1] > p["brier"][0] * (1 + NEAR_SLACK)]
    if lower < READY_LADDER:
        return False, f"its Brier on Most Likely's kind of over is lower in {lower} of {n} markets, under {READY_LADDER}"
    if honest < READY_LADDER:
        return False, (f"its overs called {TOP:.0%} or more hit within {HONEST:.0%} of that in {honest} "
                       f"of {n} markets, under {READY_LADDER}")
    if worse:
        return False, f"near the line it is worse in {', '.join(worse)}"
    return True, (f"Brier lower on Most Likely's kind of over in {lower} of {n} markets, its "
                  f"{TOP:.0%}-and-up overs honest in {honest} of {n}, and no market worse near the line")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--part", choices=("all", "shooting", "spread"), default="all")
    ap.add_argument("--save-verdict", action="store_true",
                    help="file the spread's verdict for the NBA refit to act on (engine/nba/switches); "
                         "the weekly deep refit runs it this way")
    args = ap.parse_args(argv)
    from engine import calibrate
    from engine.db import connect
    saved = {k: os.environ.get(k) for k in ("QB_NBA_SHOOTING", "QB_NBA_SPREAD")}
    conn = connect()
    try:
        n = conn.execute("SELECT COUNT(DISTINCT period) FROM player_game_logs WHERE sport='nba'").fetchone()[0]
        span = conn.execute("SELECT MIN(period), MAX(period) FROM player_game_logs WHERE sport='nba'").fetchone()
        print(f"NBA logs: {n} game dates, {span[0]} to {span[1]}")
        if not n:
            print("No NBA logs stored: nothing to replay.")
            return 1
        tune = board_tune(conn)
        print("The board's spreads (one CV per stat, as the build fits them): "
              + ", ".join(f"{m} {tune.sd_cv.get(m, 0):.3f}" for m in SPREAD + ("fg3m",)))
        verdicts = []
        if args.part in ("all", "shooting"):
            off = _run(conn, SHOOT, shooting=False, spread=False, tune=tune)
            on = _run(conn, SHOOT, shooting=True, spread=False, tune=tune)
            got = _compare("SHOOTING, LUCK TAKEN OUT (on in the board since this commit)",
                           SHOOT, off, on, show_rmse=True)
            closer = sum(1 for p in got.values() if p["rmse"][1] < p["rmse"][0])
            verdicts.append(f"shooting: projections closer in {closer} of {len(got)} markets")
        if args.part in ("all", "spread"):
            off = _run(conn, SPREAD, shooting=True, spread=False, tune=tune)
            on = _run(conn, SPREAD, shooting=True, spread=True, tune=tune)
            near_cal = _compare("THE SPREAD THAT FOLLOWS THE PROJECTION, near the line — through today's "
                                "stored calibration", SPREAD, off, on, show_rmse=False)
            off_r = _run(conn, SPREAD, shooting=True, spread=False, calib=False, tune=tune)
            on_r = _run(conn, SPREAD, shooting=True, spread=True, calib=False, tune=tune)
            near_raw = _compare("THE SPREAD THAT FOLLOWS THE PROJECTION, near the line — raw, before any "
                                "calibration", SPREAD, off_r, on_r, show_rmse=False)
            os.environ["QB_NBA_SHOOTING"] = "1"
            cal, raw = _ladder(conn, SPREAD, tune=tune)
            lad_cal = _print_ladder("MOST LIKELY'S KIND OF OVER (lines at 0.5, 0.65 and 0.8 of his "
                                    "projection) — through today's stored calibration", cal)
            lad_raw = _print_ladder("MOST LIKELY'S KIND OF OVER — raw, before any calibration", raw)

            def lower(got):
                return sum(1 for p in got.values() if p["brier"][1] < p["brier"][0])

            verdicts.append(f"spread near the line: Brier lower in {lower(near_cal)} of {len(near_cal)} "
                            f"markets through today's calibration, {lower(near_raw)} of {len(near_raw)} raw")
            verdicts.append(f"spread on Most Likely's kind of over: Brier lower in "
                            f"{sum(1 for b, _ in lad_cal.values() if b)} of {len(lad_cal)} through today's "
                            f"calibration, {sum(1 for b, _ in lad_raw.values() if b)} of {len(lad_raw)} raw; "
                            f"its {TOP:.0%}-and-up overs honest in "
                            f"{sum(1 for _, h in lad_raw.values() if h)} of {len(lad_raw)} raw")
            ready, why = _ready(near_raw, lad_raw)
            verdicts.append(("spread: ready for the refit — " if ready else "spread: not yet — ") + why)
            if args.save_verdict:
                # The verdict only: the switch follows once the NBA refit has
                # fitted its calibration on it (engine/deepfit, the runbook's
                # order — the refit and then the switch).
                from engine.nba import switches
                verdicts.append(f"spread verdict filed: {switches.record_check('spread', ready, why)}")
        print("\n" + "\n".join(verdicts))
        return 0
    finally:
        conn.close()
        # The switches as they were: this measured, it changed nothing.
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


if __name__ == "__main__":
    sys.exit(main())
