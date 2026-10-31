#!/usr/bin/env python3
"""Are our carry projections right? — every running back's game, replayed from the weeks before it.

    cd /srv/qellys && sudo -u qellys nice -n 19 python3 carrycheck.py                    # this season
    sudo -u qellys nice -n 19 python3 carrycheck.py --seasons 2025-2026                  # and last
    python3 carrycheck.py --db PATH --seasons 2026 --weeks 3-7                           # another history

Ethan, 2026-10-23, after Patriots at Bears (D'Andre Swift: 15 carries
projected, 22 carried): "yes do the carry projection check". The loss
autopsy (engine/autopsy) already names volume the step most often wrong.

HOW. engine/backtest.backtest_from_stats rebuilds each week's slate the way
the live board does (the season prior, `--carry`; the usage bridge as of
that week, from this history) from the weeks before it only, and hands back
every settled prop. This keeps the running backs' carries (rush_att) and
grades the projection four ways: by the role it projected (lead 14+, share
9-14, change of pace under 9), against a plain average of his last three
games, by the spread before the game, and by how the game went. Bias is
carried minus projected: plus means we projected too few.

WHAT IT CAN AND CANNOT SAY. A bias by the SPREAD is one the board could
have known before kickoff, and is fixable. A bias by the FINAL MARGIN is
game flow — a team that leads runs the ball — and a projection made before
the game cannot see it; it explains misses without being one.

THE ANSWER, 2026-10-24, 2025 and 2026 from week 3 (1,625 running-back
games, replayed in the sandbox off nflverse's files, rebuilt as the box
stores them):

                          games  projected  carried   bias   miss  off 5+
    every running back     1625      8.0      8.2     +0.2    3.4    24%
    lead (14+)              340     16.4     16.0     -0.4    4.2    34%
    share (9-14)            347     11.4     11.7     +0.3    4.3    37%
    change of pace (<9)     938      3.7      4.0     +0.4    2.7    16%
    last-three average                                       3.4    26%
                                                    (ours:   3.3    23%)
    lead, favoured by 3+    144                       -0.3
    lead, underdog by 3+    117                       -0.7
    lead, won by 7+         103                       +1.2
    lead, lost by 7+         97                       -3.4

NO BIAS TO FIX. A lead back is not under-projected (-0.4, within its
error); the projection beats a plain three-game average; and nothing is
left in the spread, so the board's game-script step is the right size. The
misses are game flow: a lead back on a team that trails by a score or
more loses 3.4 carries, one that leads gains 1.2, and no number made
before kickoff can know which. Swift's 22 (Bears by 6) is that. The only
flag is the change-of-pace backs, 0.4 a game light, too small to move a
line. The biggest misses are backups starting for an injured lead back,
which this replay cannot see and the live board's injury step can.

Reads the history and nflverse's files in data/cache; writes nothing.
"""
from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

#: Projected carries that make a lead back, and a share of the work.
LEAD, SHARE = 14.0, 9.0
#: A miss this many carries or more is a miss a bettor feels.
BIG_MISS = 5.0
#: A game this close (points, either way) is "within a score".
CLOSE = 7.0
#: Favoured or an underdog by this much or more before the game.
SPREAD = 3.0


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _span(text: str) -> list[int]:
    lo, _, hi = str(text).partition("-")
    return list(range(int(lo), int(hi or lo) + 1))


def last_three(stats: list[dict]) -> dict:
    """{(player, week): his average carries over his last three games
    before that week} — the plain baseline, from the box scores alone."""
    by = defaultdict(list)
    for r in stats:
        w = _num(r.get("week"))
        if w is None or str(r.get("season_type") or "REG").upper() not in ("REG", ""):
            continue
        by[r.get("player_display_name") or r.get("player_name") or ""].append((int(w), _num(r.get("carries")) or 0.0))
    out = {}
    for name, games in by.items():
        games.sort()
        for i, (w, _c) in enumerate(games):
            prior = [c for _w, c in games[:i]][-3:]
            if prior:
                out[(name, w)] = sum(prior) / len(prior)
    return out


def game_lines(games: list[dict], season: int) -> dict:
    """{(team, week): (spread for the team, final margin for the team)} from
    nflverse's games.csv: the spread signed so plus is favoured."""
    out = {}
    for g in games:
        if str(g.get("season")) != str(season):
            continue
        w = _num(g.get("week"))
        line = _num(g.get("spread_line"))
        hs, as_ = _num(g.get("home_score")), _num(g.get("away_score"))
        if w is None:
            continue
        home, away = g.get("home_team") or "", g.get("away_team") or ""
        margin = (hs - as_) if hs is not None and as_ is not None else None
        out[(home, int(w))] = (line, margin)
        out[(away, int(w))] = (-line if line is not None else None, -margin if margin is not None else None)
    return out


def tier(projection: float) -> str:
    return "lead (14+)" if projection >= LEAD else "share (9-14)" if projection >= SHARE else "change of pace (<9)"


def line(label: str, rows: list[dict], key: str = "projection") -> str:
    """One row of the table: games, mean projected, mean carried, bias with
    its two standard errors, the average miss and the share off by 5+."""
    n = len(rows)
    if not n:
        return f"  {label:<26}{'-':>6}"
    errs = [r["actual"] - r[key] for r in rows]
    bias = sum(errs) / n
    sd = math.sqrt(sum((e - bias) ** 2 for e in errs) / (n - 1)) if n > 1 else 0.0
    se2 = 2 * sd / math.sqrt(n) if n > 1 else 0.0
    mae = sum(abs(e) for e in errs) / n
    big = sum(1 for e in errs if abs(e) >= BIG_MISS) / n
    flag = "  <-- off" if n >= 20 and abs(bias) > se2 else ""
    return (f"  {label:<26}{n:>6}{sum(r[key] for r in rows) / n:>10.1f}{sum(r['actual'] for r in rows) / n:>9.1f}"
            f"{bias:>+8.1f} ±{se2:<4.1f}{mae:>8.1f}{big:>9.0%}{flag}")


HEAD = (f"  {'':<26}{'games':>6}{'projected':>10}{'carried':>9}{'bias':>8}{'':6}{'miss':>8}{'off 5+':>9}")


def report(rows: list[dict], label: str) -> list[str]:
    out = [f"=== Running backs' carries, {label}: {len(rows):,} games, each projected from the weeks before it",
           "  bias = carried minus projected (plus: we projected too few), ± two standard errors;",
           "  <-- off marks a bias bigger than that, on 20 games or more", HEAD]
    out.append(line("every running back", rows))
    for t in ("lead (14+)", "share (9-14)", "change of pace (<9)"):
        out.append(line(t, [r for r in rows if tier(r["projection"]) == t]))
    based = [r for r in rows if r.get("naive") is not None]
    out.append("  the same games, scored against a plain average of his last three:")
    out.append(line("  our projection", based))
    out.append(line("  last-three average", based, key="naive"))
    lead = [r for r in rows if r["projection"] >= LEAD]
    out.append(f"  lead backs by the spread before the game (could have been known):")
    out.append(line(f"  favoured by {SPREAD:g}+", [r for r in lead if (r.get("spread") or 0) >= SPREAD]))
    out.append(line(f"  within {SPREAD:g}", [r for r in lead if r.get("spread") is not None and abs(r["spread"]) < SPREAD]))
    out.append(line(f"  underdog by {SPREAD:g}+", [r for r in lead if (r.get("spread") or 0) <= -SPREAD]))
    out.append(f"  lead backs by how the game went (game flow, not knowable before):")
    out.append(line(f"  won by {CLOSE:g}+", [r for r in lead if (r.get("margin") or 0) >= CLOSE]))
    out.append(line(f"  within {CLOSE:g}", [r for r in lead if r.get("margin") is not None and abs(r["margin"]) < CLOSE]))
    out.append(line(f"  lost by {CLOSE:g}+", [r for r in lead if (r.get("margin") or 0) <= -CLOSE]))
    out.append("  the biggest misses:")
    for r in sorted(rows, key=lambda r: -abs(r["actual"] - r["projection"]))[:10]:
        m = r.get("margin")
        out.append(f"    week {r['week']:>2} {r['team']:<4}{r['player'][:22]:<23}projected {r['projection']:>5.1f}"
                   f"  carried {r['actual']:>4.0f}" + (f"  ({'won' if m > 0 else 'lost' if m < 0 else 'tied'} by {abs(m):.0f})" if m is not None else ""))
    return out


def collect(season: int, weeks: list[int], conn, say=print) -> list[dict]:
    """The running backs' carry rows for one season, joined to the baseline,
    the spread and the result."""
    from engine.backtest import backtest_from_stats
    from engine.sources.nflverse import load_schedules, load_weekly_stats
    stats = load_weekly_stats(season)
    played = {int(w) for w in (_num(r.get("week")) for r in stats) if w is not None}
    weeks = [w for w in weeks if w in played]
    if not weeks:
        say(f"  {season}: no week in range has box scores yet")
        return []
    rows: list[dict] = []
    backtest_from_stats(season, weeks, carry=True, usage_conn=conn, log=say, rows_out=rows)
    naive = last_three(stats)
    lines = game_lines(load_schedules(), season)
    out = []
    for r in rows:
        if r["market"] != "rush_att" or str(r.get("position") or "").upper() != "RB":
            continue
        spread, margin = lines.get((r["team"], int(r["week"])), (None, None))
        out.append(dict(r, season=season, naive=naive.get((r["player"], int(r["week"]))),
                        spread=spread, margin=margin))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seasons", default="", help="e.g. 2026 or 2025-2026 (default: the history's latest)")
    ap.add_argument("--weeks", default="3-22", help="weeks to replay; ones without box scores are skipped")
    ap.add_argument("--db", default="", help="the history to read (default: the box's)")
    args = ap.parse_args(argv)
    from engine import db
    conn = db.connect(args.db) if args.db else db.connect()
    seasons = _span(args.seasons) if args.seasons else [
        int(conn.execute("SELECT MAX(season) FROM player_game_logs WHERE sport='nfl'").fetchone()[0])]
    weeks = _span(args.weeks)
    rows = []
    for season in seasons:
        print(f"{season}: replaying weeks {weeks[0]}-{weeks[-1]} (a few seconds a week here, longer on the box)")
        rows += collect(season, weeks, conn)
    if not rows:
        print("nothing to grade")
        return 1
    label = ", ".join(str(s) for s in seasons)
    for text in report(rows, label):
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
