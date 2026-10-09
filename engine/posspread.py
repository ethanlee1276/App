"""How wide a player's outcomes really are, by position.

    sudo -u qellys python3 -m engine.posspread            # measure 2021+, every league, save what holds
    sudo -u qellys python3 -m engine.posspread --dry-run
    sudo -u qellys python3 -m engine.posspread --sport cfb --dry-run

COLLEGE (2026-10-09, Ethan: "add it for college football"): the same
measurement on college's stored player-weeks, its own store
(cfb_position_spread.json), its own record veto (college's position-by-
side slices), and the same bar — unchanged, written for the NFL before any
run. A college width is used only on college props.

THE FINDING THAT ASKED FOR IT. The NFL Most Likely record, 2026-10-04:
tight ends over-claimed on BOTH sides — overs hit 47% where we said 64%
(53 picks), unders 41% where we said 65% (22). A model that misses in
both directions is not leaning the wrong way; it is too SURE. The width
it gives a player's outcome comes from his own games and a per-MARKET
floor (projection.CV_FLOOR: receptions 0.34, rec_yds 0.48) — the same
floor for a tight end as for a WR1, though a tight end's targets come in
lumps.

WHAT THIS MEASURES. Every 2021+ player-week with four earlier games that
season (yardagefit's rows: the shipped window blend as the mean, his own
spread, the market floor), split by position, priced the way the board
prices it — Normal(mean, max(own sd, floor × mean)) — at the lines a book
would hang near him (yardagefit.MARKETS, inside LINE_LO..LINE_HI of the
mean). For each position and market, one width multiplier m (WIDTH_GRID)
is chosen by log loss on the over/under outcome.

THE RECORD CAN VETO (record_veto, added 2026-10-04): a position whose
graded Most Likely picks already hit at or above their claim on a side
(VETO_N or more) is not widened, whatever history says.

THE BAR, WRITTEN BEFORE ANY BOX RUN. Leave one season out: m fitted on
the other seasons, scored on the held-out one, against m = 1. A position
and market adopts its m only if held-out log loss improves POOLED and in
at least MIN_SEASONS_BETTER of the held-out seasons, on MIN_ROWS rows or
more. The m saved is the one fitted on every season. Anything else stays
at 1 — the shipped width.

WHAT IT CHANGES. engine/projection multiplies the projection's spread by
the stored m for the player's position and market (`width_mult`). The
mean does not move. A wider spread pulls every chance toward 50%, so a
too-sure tight end shows less certainty on both sides — which is the
error the record showed.

Runs weekly with the deep fitters (engine/maintenance). Standard library only.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

from . import modelstate

MARKETS = ("receptions", "rec_yds", "rush_yds")
POSITIONS = ("RB", "WR", "TE")
WIDTH_GRID = tuple(round(0.80 + 0.05 * i, 2) for i in range(17))      # 0.80 .. 1.60
MIN_ROWS = 2000
MIN_SEASONS_BETTER = 4
#: WHERE A BOOK HANGS THE LINE: within this band of his projection. The
#: first box run (2026-10-04) scored lines from 0.4x to 3x his average —
#: yardagefit's band — and adopted x1.20-x1.40 for every position. Most of
#: that gain lives in the far tails, where the normal curve is already known
#: to be the wrong shape (the zero-yard spike; engine/yardagefit), not
#: around the line a pick is made at. The record disagreed where it can
#: speak: receiver overs hit 67% where we said 63%, and widening them would
#: have made a well-calibrated group worse. So the width is judged only on
#: lines near the projection. Written before the re-run.
NEAR_LO, NEAR_HI = 0.75, 1.33
#: Stores written before the record could veto (versions 1-2) are never read.
STORE_VERSION = 3


#: Leagues measured. Each reads only widths measured on its own games.
SPORTS = ("nfl", "cfb")
#: Games of form behind a row, by league: about one season.
CARRY_BY = {"nfl": 17, "cfb": 12}


def _store(sport: str = "nfl") -> Path:
    """The NFL's store keeps its original name, so the box's file is read
    as it is; every other league has its own."""
    return Path(modelstate.path("position_spread.json" if sport == "nfl" else f"{sport}_position_spread.json"))


def load(path=None) -> dict:
    try:
        return json.loads(Path(path or _store()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


_CACHE: dict = {}


def width_mult(position: str, market: str, sport: str = "nfl") -> float:
    """The adopted spread multiplier for this position and market in this
    league, 1.0 where nothing was adopted. Re-read when the store changes —
    the launcher is long-lived and the weekly refit writes from a child."""
    if sport not in SPORTS:
        return 1.0
    p = _store(sport)
    try:
        stamp = (str(p), p.stat().st_mtime)
    except OSError:
        stamp = (str(p), None)
    cell = _CACHE.setdefault(sport, {})
    if cell.get("stamp") != stamp:
        store = load(p)
        cell["stamp"] = stamp
        cell["w"] = (store.get("widths") or {}) if store.get("version") == STORE_VERSION else {}
    return float((cell["w"].get(f"{str(position or '').upper()}|{market}") or {}).get("m", 1.0))


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _ll(p: float, hit: bool) -> float:
    p = min(0.999, max(0.001, p))
    return -math.log(p if hit else 1.0 - p)


def positions_of(conn, sport: str = "nfl") -> dict:
    """{(season, player, team): position} off the box-score rows."""
    out = {}
    for season, player, team, pos in conn.execute(
            "SELECT season, player, team, MAX(position) FROM player_game_logs WHERE sport=? "
            "AND position IN ('QB','RB','WR','TE') GROUP BY season, player, team", (sport,)):
        out[(season, player, team)] = pos
    return out


def samples(rows: list, market: str) -> list:
    """(season, base_sd, mu, line, hit) for every row at every line near
    his projection (NEAR_LO..NEAR_HI), where a book would hang it."""
    from .projection import CV_FLOOR
    from .yardagefit import MARKETS as LINES
    cv = CV_FLOOR.get(market, 0.35)
    out = []
    for r in rows:
        sd = max(r["form_sd"], cv * max(r["mu"], 1.0))
        for line in LINES.get(market, ()):
            if NEAR_LO * r["mu"] <= line <= NEAR_HI * r["mu"]:
                out.append((r["season"], sd, r["mu"], line, r["actual"] > line))
    return out


def loss(data: list, m: float) -> float:
    return sum(_ll(1.0 - _phi((line - mu) / max(sd * m, 1e-6)), hit) for _s, sd, mu, line, hit in data)


def best_m(data: list) -> float:
    return min(WIDTH_GRID, key=lambda m: loss(data, m))


def judge(data: list) -> dict:
    """Leave-one-season-out: is a fitted width better than the shipped one?"""
    seasons = sorted({d[0] for d in data})
    per, better, pooled_raw, pooled_fit = {}, 0, 0.0, 0.0
    for s in seasons:
        train = [d for d in data if d[0] != s]
        test = [d for d in data if d[0] == s]
        if not train or not test:
            continue
        m = best_m(train)
        raw, fit = loss(test, 1.0), loss(test, m)
        per[s] = {"m": m, "n": len(test), "gain": round((raw - fit) / len(test), 5)}
        better += fit < raw
        pooled_raw += raw
        pooled_fit += fit
    n = len(data)
    m_all = best_m(data) if data else 1.0
    passed = bool(n >= MIN_ROWS and pooled_fit < pooled_raw and better >= MIN_SEASONS_BETTER
                  and m_all != 1.0)
    return {"m": m_all, "n": n, "seasons": per, "better": better,
            "gain": round((pooled_raw - pooled_fit) / n, 5) if n else 0.0, "passed": passed}


#: A side of the record this deep that already hits at or above its claim
#: vetoes widening that position (`record_veto`).
VETO_N = 30


def record_veto(position: str, report: dict | None = None, sport: str = "nfl") -> str | None:
    """Why the board's own record forbids widening this position, or None.

    Written 2026-10-04, after the near-line re-run adopted x1.25-x1.50 for
    receivers while their overs were hitting 67% where we said 63% (94
    picks). Widening pulls every chance toward 50%; the record's correction
    (engine/likelycal) can only ever LOWER a chance, never raise it — so a
    width that makes an honest group shy is a mistake nothing downstream can
    undo. History proposes; the record of the picks we actually make can
    say no. It reads engine/boardlearn's last report (position by side)."""
    if report is None:
        from . import boardlearn
        report = boardlearn.report()
    for s in ((report.get(sport) or {}).get("slices") or {}).get("position") or []:
        pos, _, side = str(s.get("key", "")).partition(" · ")
        if pos == position and s.get("n", 0) >= VETO_N and s.get("hit", 0) >= s.get("said", 1):
            return (f"the record's {position} {side}s hit {s['hit']:.0%} of {s['n']} where we said "
                    f"{s['said']:.0%} — not over-sure, so not widened")
    return None


def apply_vetoes(res: dict, report: dict | None = None, sport: str = "nfl") -> dict:
    """Mark every passing width the record vetoes as not passed, with why."""
    for k, v in res.items():
        why = record_veto(k.split("|")[0], report, sport) if v.get("passed") else None
        if why:
            v["passed"], v["veto"] = False, why
    return res


#: Games of form behind a row, reaching back across seasons: about one season.
CARRY_GAMES = 17


def carried_rows(conn, market: str, sport: str = "nfl") -> list:
    """yardagefit.rows, but his form reaches back into last season.

    Ethan, 2026-10-04: "make sure ur using 2026 data too." Keyed by season,
    a row needed four earlier games THAT season, so with four 2026 weeks
    played no 2026 row existed. Keyed by player and team across seasons —
    his last CARRY_GAMES games, as the live model carries a season over in
    its first weeks — the current season counts from week 2."""
    from .yardagefit import MIN_PRIOR, MIN_PROJECTION, blended
    carry = CARRY_BY.get(sport, CARRY_GAMES)
    by: dict = defaultdict(list)
    for season, period, player, team, value in conn.execute(
            "SELECT season, period, player, team, value FROM player_game_logs "
            "WHERE sport=? AND market=?", (sport, market)):
        by[(player, team)].append((season, str(period), float(value or 0.0)))
    out = []
    for (player, team), games in by.items():
        # By week, not by text: college's periods are "1".."15", and "10"
        # sorts before "2" as a string.
        games.sort(key=lambda g: (g[0], _week(g[1])))
        for i in range(MIN_PRIOR, len(games)):
            vals = [v for _s, _p, v in games[max(0, i - carry):i]]
            mean = sum(vals) / len(vals)
            sd = math.sqrt(sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)) if len(vals) > 1 else 0.0
            mu = blended(vals)
            if mu > MIN_PROJECTION:
                season, period, actual = games[i]
                out.append({"season": season, "mu": mu, "form_sd": sd, "actual": max(actual, 0.0),
                            "player": player, "team": team, "period": period})
    return out


def _week(period) -> tuple:
    try:
        return (0, int(str(period).strip()))
    except (TypeError, ValueError):
        return (1, str(period))


def measure(conn, sport: str = "nfl") -> dict:
    """{"POS|market": judge(...)} for every position and market."""
    yrows = lambda c, m: carried_rows(c, m, sport)                   # noqa: E731
    pos = positions_of(conn, sport)
    out = {}
    for market in MARKETS:
        by = defaultdict(list)
        for r in yrows(conn, market):
            p = pos.get((r["season"], r["player"], r["team"]))
            if p in POSITIONS:
                by[p].append(r)
        for p, rs in by.items():
            out[f"{p}|{market}"] = judge(samples(rs, market))
    return apply_vetoes(out, sport=sport)


def save(res: dict, path=None, sport: str = "nfl") -> None:
    import datetime as _dt
    p = Path(path or _store(sport))
    p.parent.mkdir(parents=True, exist_ok=True)
    widths = {k: {"m": v["m"], "n": v["n"], "gain": v["gain"]} for k, v in res.items() if v["passed"]}
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps({"version": STORE_VERSION, "widths": widths, "at": _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
                               .isoformat(timespec="seconds")}, indent=1), encoding="utf-8")
    tmp.replace(p)
    _CACHE.clear()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m engine.posspread")
    ap.add_argument("--dry-run", action="store_true", help="measure and report, save nothing")
    ap.add_argument("--sport", default="", help="one league (default: every league measured)")
    a = ap.parse_args(argv)
    from . import db
    conn = db.connect()
    for sport in ([a.sport.lower()] if a.sport else list(SPORTS)):
        print(f"=== {sport.upper()}")
        res = measure(conn, sport)
        for k, v in sorted(res.items()):
            verdict = (f"ADOPT ×{v['m']:.2f}" if v["passed"] else
                       f"keep ×1.00 ({v['veto']})" if v.get("veto") else "keep ×1.00")
            print(f"  {k:16} n {v['n']:6}  fitted ×{v['m']:.2f}  held-out gain {v['gain']:+.5f}  "
                  f"better in {v['better']}/{len(v['seasons'])} seasons  → {verdict}")
        if not res:
            print("  no rows to measure")
        if not a.dry_run:
            save(res, sport=sport)
            print("saved; the next build reads it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
