#!/usr/bin/env python3
"""Measure this week's fantasy projection against the season average.

    python3 fantasyweekfit.py                       # 2023-2025, weeks 4-17
    python3 fantasyweekfit.py --seasons 2024 --weeks 4-10
    python3 fantasyweekfit.py --save                # keep the measured spread and play chances
    python3 fantasyweekfit.py --from-rows rows.json # re-score a run's rows (no slates)

THE QUESTION (engine/fantasyweek, 2026-10-22). The league desks valued
every player at his season-to-date average. Does the NFL board's chain
(form, usage, the defence against his position, the game script, the
weather, the touchdown model) put players in a better order, and closer
to what they scored, than that average? Walked forward: each week's
slate is built from the weeks before it (sources/nflverse.build_slate),
priced (pipeline.price_props), its touchdown chances taken
(pipeline.td_chances), added up in PPR (fantasyweek.project_players),
and scored against nflverse's own `fantasy_points_ppr` for that week. The
baseline is the same player's PPR average over his games so far that
season: what `fantasy_lineup.per_game` hands the desks.

SCORED ON THE SAME PLAYERS: everyone the slate built who played that
week and had at least one earlier game that season. A player who sat
scores neither way, so availability (which only the weekly projection
reads) is left out of this comparison, not credited to it.

THE NUMBERS:
  rank      Spearman correlation with what they scored, per week and
            position, averaged over weeks (the start/sit ordering);
  pairs     of every two players at one position in one week, how often
            the higher number scored more: the start/sit call itself;
  MAE       mean absolute error, points;
  bias      mean of (scored − projected).
A paired t over weeks says whether the pairs gain is noise.

ALSO MEASURED, for the card and the head-to-head:
  range     where eight weeks in ten land: the 10th and 90th percentile
            of what players scored, by projection band, as two lines on
            the projection per position. Fantasy points lean high (a
            touchdown is six at once), so a normal band around the
            projection is the wrong shape: it missed high 12-14% of the
            time for backs, receivers and tight ends and low 1-4%. Checked
            on each season held out of its own fit;
  spread    the residual's standard deviation by projection band, fit as
            a + b × projection: what the head-to-head's win chance adds
            up (fantasy_h2h), where a sum of a lineup is close to normal;
  play      how often a listed player plays (nflverse's injury reports
            against its snap counts), by designation and practice;
  fill      the projection with and without the season-average fill for
            the parts the board has no line for (fantasyweek.fill_missing);
  td        the touchdown model's expected count against what was scored,
            by position, and a scale kept only where it beat no scale on
            every season held out of its own fit (fantasyweek.TD_SCALE).

USAGE MAPS. Where the history database holds NFL usage (the box), the
maps are replayed as of each week (nflusage.build_usage_maps, as the
backtest does) and handed to the projections and the touchdown model,
which is what the live build runs. Without them the touchdown model sees
no expected-points share, and its counts are not the live model's.

Reads nflverse's weekly stats, schedules, rosters, snap counts and injury
reports into data/cache on first use. Run it off the site's clock: it
builds one slate per week.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

from engine import fantasyweek as FW
from engine.backtest import _norm
from engine.pipeline import price_props, td_chances
from engine.rules import RuleConfig
from engine.sources import nflverse as N

ROOT = Path(__file__).resolve().parent
POSITIONS = ("QB", "RB", "WR", "TE")
#: Projection bands for the residual's spread.
BANDS = ((0, 5), (5, 10), (10, 15), (15, 20), (20, 25), (25, 60))


def _rng(text: str) -> list:
    a, _, b = str(text).partition("-")
    return list(range(int(a), int(b or a) + 1))


#: nflverse's columns for the parts a season average can fill, as the
#: desks name them (fantasy_lineup.SCORING_MARKET's values).
STAT_COLS = {"receptions": ("receptions",), "rec_yds": ("receiving_yards",),
             "rush_yds": ("rushing_yards",), "pass_yds": ("passing_yards",),
             "pass_td": ("passing_tds",), "pass_int": ("passing_interceptions", "interceptions"),
             "rush_td": ("rushing_tds",), "rec_td": ("receiving_tds",)}


def _col(r: dict, names) -> float | None:
    for n in names:
        v = r.get(n)
        if v not in (None, ""):
            try:
                return float(v)
            except ValueError:
                return None
    return None


def _usage_conn():
    """The history database when it holds NFL usage (the box), else None:
    the maps are then replayed as of each week, as the backtest does."""
    try:
        from engine.db import connect
        conn = connect()
        if conn.execute("SELECT 1 FROM player_game_logs WHERE sport='nfl' LIMIT 1").fetchone():
            return conn
        conn.close()
    except Exception:                                        # noqa: BLE001
        pass
    return None


def week_rows(season: int, weeks, log=print, usage_conn=None) -> list:
    """[(season, week, position, player, projection, season average, scored,
    model touchdowns, touchdowns scored, projection before the fill)].

    The model's touchdowns are his chance turned back into a count, unscaled
    (fantasyweek.td_lambda); scored ones are rushing and receiving, a
    quarterback's rushing alone, as the touchdown model counts them."""
    from engine.nflusage import build_usage_maps
    stats = N.load_weekly_stats(season)
    ppr: dict = {}
    lines: dict = {}
    for r in stats:
        if (r.get("season_type") or "REG") != "REG":
            continue
        try:
            wk = int(float(r.get("week") or 0))
            pts = float(r.get("fantasy_points_ppr") or 0.0)
        except ValueError:
            continue
        name = r.get("player_display_name") or r.get("player_name") or ""
        if name:
            ppr[(_norm(name), wk)] = pts
            lines[(_norm(name), wk)] = {k: _col(r, cols) for k, cols in STAT_COLS.items()}
    out = []
    started = time.monotonic()
    for w in weeks:
        try:
            slate = N.build_slate(season, w, upto_week=w, carry=True)
        except Exception as exc:                             # noqa: BLE001
            log(f"  {season} week {w}: no slate ({exc})")
            continue
        usage = build_usage_maps(usage_conn, season, upto_week=w) if usage_conn is not None else None
        rows = price_props(slate, RuleConfig(), allow_synthetic_line=True, nfl_usage=usage)
        players = FW.project_players(rows, td_chances(slate, usage))
        before_fill = {(p["team"], p["player"]): p["ppr"] for p in players}
        # His season to date, as the desks' per_game would have it that week.
        means: dict = {}
        for (key, k), st in lines.items():
            if k < w:
                acc = means.setdefault(key, {})
                for m, v in st.items():
                    if v is not None:
                        acc.setdefault(m, []).append(v)
        means = {key: {m: sum(v) / len(v) for m, v in acc.items()} for key, acc in means.items()}
        players = FW.fill_missing(players, {p["player"]: means.get(_norm(p["player"]), {})
                                            for p in players})
        n = 0
        for p in players:
            pos = p["position"]
            if pos not in POSITIONS:
                continue
            key = _norm(p["player"])
            scored = ppr.get((key, w))
            if scored is None:
                continue
            before = [ppr[(key, k)] for k in range(1, w) if (key, k) in ppr]
            if not before:
                continue
            got = lines.get((key, w)) or {}
            tds = (got.get("rush_td") or 0.0) + (0.0 if pos == "QB" else (got.get("rec_td") or 0.0))
            lam = FW.td_lambda(p["td_prob"]) if p.get("td_prob") is not None else None
            out.append((season, w, pos, p["player"], p["ppr"],
                        sum(before) / len(before), scored, lam, tds,
                        before_fill.get((p["team"], p["player"]), p["ppr"])))
            n += 1
        log(f"  {season} week {w}: {n} players scored · {time.monotonic() - started:.0f}s")
    return out


def _spearman(xs, ys) -> float | None:
    n = len(xs)
    if n < 3:
        return None

    def ranks(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2.0
            i = j + 1
        return r
    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    return sxy / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else None


def _pairs(xs, ys) -> tuple[int, int]:
    """(right, called) over every pair with a strict order both ways."""
    right = called = 0
    n = len(xs)
    for i in range(n):
        for j in range(i + 1, n):
            if xs[i] == xs[j] or ys[i] == ys[j]:
                continue
            called += 1
            right += (xs[i] > xs[j]) == (ys[i] > ys[j])
    return right, called


def _t(diffs) -> float | None:
    n = len(diffs)
    if n < 2:
        return None
    m = sum(diffs) / n
    var = sum((d - m) ** 2 for d in diffs) / (n - 1)
    return m / math.sqrt(var / n) if var > 0 else None


def score(rows) -> dict:
    """Per position: rank, pairs, MAE, bias for both numbers, and the
    paired t of the weekly gain in pairs."""
    out = {}
    for pos in POSITIONS + ("ALL",):
        sel = [r for r in rows if pos == "ALL" or r[2] == pos]
        if not sel:
            continue
        groups: dict = {}
        for r in sel:
            groups.setdefault((r[0], r[1], r[2]), []).append(r)
        rk = {"week": [], "season": []}
        pr = {"week": [0, 0], "season": [0, 0]}
        gains = []
        for g in groups.values():
            proj, base, act = [x[4] for x in g], [x[5] for x in g], [x[6] for x in g]
            a, b = _spearman(proj, act), _spearman(base, act)
            if a is not None and b is not None:
                rk["week"].append(a)
                rk["season"].append(b)
            r1, c1 = _pairs(proj, act)
            r2, c2 = _pairs(base, act)
            pr["week"][0] += r1
            pr["week"][1] += c1
            pr["season"][0] += r2
            pr["season"][1] += c2
            if c1 and c2:
                gains.append(r1 / c1 - r2 / c2)
        n = len(sel)
        out[pos] = {
            "n": n, "weeks": len(groups),
            "rank_week": round(sum(rk["week"]) / len(rk["week"]), 4) if rk["week"] else None,
            "rank_season": round(sum(rk["season"]) / len(rk["season"]), 4) if rk["season"] else None,
            "pairs_week": round(pr["week"][0] / pr["week"][1], 4) if pr["week"][1] else None,
            "pairs_season": round(pr["season"][0] / pr["season"][1], 4) if pr["season"][1] else None,
            "pairs_gain_t": (round(_t(gains), 2) if _t(gains) is not None else None),
            "mae_week": round(sum(abs(x[6] - x[4]) for x in sel) / n, 3),
            "mae_season": round(sum(abs(x[6] - x[5]) for x in sel) / n, 3),
            "bias_week": round(sum(x[6] - x[4] for x in sel) / n, 3),
            "bias_season": round(sum(x[6] - x[5] for x in sel) / n, 3),
        }
    return out


def residual_fit(rows) -> dict:
    """{position: (a, b, bands)}: the spread of (scored − projection) by
    projection band, and the weighted least-squares line through it."""
    out = {}
    for pos in POSITIONS:
        bands = []
        for lo, hi in BANDS:
            res = [r[6] - r[4] for r in rows if r[2] == pos and lo <= r[4] < hi]
            if len(res) < 30:
                continue
            m = sum(res) / len(res)
            sd = math.sqrt(sum((x - m) ** 2 for x in res) / (len(res) - 1))
            mid = sum(r[4] for r in rows if r[2] == pos and lo <= r[4] < hi) / len(res)
            bands.append((round(mid, 2), round(sd, 3), len(res)))
        if len(bands) < 2:
            continue
        w = [n for _x, _s, n in bands]
        sw = sum(w)
        mx = sum(x * n for x, _s, n in bands) / sw
        my = sum(s * n for _x, s, n in bands) / sw
        sxx = sum(n * (x - mx) ** 2 for x, _s, n in bands)
        sxy = sum(n * (x - mx) * (s - my) for x, s, n in bands)
        b = sxy / sxx if sxx > 0 else 0.0
        out[pos] = (round(my - b * mx, 3), round(b, 4), bands)
    return out


def _q(values, p: float) -> float:
    v = sorted(values)
    i = p * (len(v) - 1)
    lo = int(i)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)


def _line(pts) -> tuple[float, float]:
    """Weighted least squares through [(x, y, n)]: (intercept, slope)."""
    sw = sum(n for _x, _y, n in pts)
    mx = sum(x * n for x, _y, n in pts) / sw
    my = sum(y * n for _x, y, n in pts) / sw
    sxx = sum(n * (x - mx) ** 2 for x, _y, n in pts)
    sxy = sum(n * (x - mx) * (y - my) for x, y, n in pts)
    b = sxy / sxx if sxx > 0 else 0.0
    return my - b * mx, b


def range_fit(rows) -> dict:
    """{position: (lo_a, lo_b, hi_a, hi_b)}: the 10th and 90th percentile
    of what players scored, by projection band, as lines on the projection
    — where eight weeks in ten land (fantasyweek.range_for)."""
    out = {}
    for pos in POSITIONS:
        lo_pts, hi_pts = [], []
        for lo, hi in BANDS:
            sel = [r for r in rows if r[2] == pos and lo <= r[4] < hi]
            if len(sel) < 30:
                continue
            mid = sum(r[4] for r in sel) / len(sel)
            lo_pts.append((mid, _q([r[6] for r in sel], 0.1), len(sel)))
            hi_pts.append((mid, _q([r[6] for r in sel], 0.9), len(sel)))
        if len(lo_pts) < 2:
            continue
        out[pos] = tuple(round(x, 3) for x in _line(lo_pts) + _line(hi_pts))
    return out


def range_cover(rows, fit: dict) -> dict:
    """{position: (below, inside, above)}: shares of weeks against the range."""
    out = {}
    for pos, f in fit.items():
        sel = [r for r in rows if r[2] == pos]
        if not sel:
            continue
        below = above = 0
        for r in sel:
            lo, hi = FW.range_for(pos, r[4], fit=f)
            below += r[6] < lo
            above += r[6] > hi
        n = len(sel)
        out[pos] = (round(below / n, 4), round((n - below - above) / n, 4), round(above / n, 4))
    return out


#: Positions whose touchdowns the model prices.
TD_POS = POSITIONS


def td_report(rows) -> dict:
    """{position: (model touchdowns a game, scored a game, n)} over rows
    the touchdown model priced."""
    out = {}
    for pos in TD_POS:
        sel = [r for r in rows if len(r) > 8 and r[2] == pos and r[7] is not None]
        if sel:
            out[pos] = (round(sum(r[7] for r in sel) / len(sel), 3),
                        round(sum(r[8] for r in sel) / len(sel), 3), len(sel))
    return out


def td_scale_fit(rows) -> dict:
    """{position: scale} kept only where it held: the ratio of scored to
    the model's touchdowns, fitted with each season held out and scored on
    it by squared error of the touchdown count — kept when the scaled
    count beat the model's in EVERY held-out season, then refitted on all
    of them. A ratio, because fantasy points need the expected count."""
    seasons = sorted({r[0] for r in rows})
    out = {}
    for pos in TD_POS:
        sel = [r for r in rows if len(r) > 8 and r[2] == pos and r[7] is not None]
        if len(seasons) < 2 or len(sel) < 200:
            continue
        held = True
        for s_ in seasons:
            fit = [r for r in sel if r[0] != s_]
            test = [r for r in sel if r[0] == s_]
            lam = sum(r[7] for r in fit)
            if not test or lam <= 0:
                held = False
                break
            k = sum(r[8] for r in fit) / lam
            raw = sum((r[8] - r[7]) ** 2 for r in test)
            scaled = sum((r[8] - k * r[7]) ** 2 for r in test)
            if scaled >= raw:
                held = False
                break
        if held:
            lam = sum(r[7] for r in sel)
            out[pos] = round(sum(r[8] for r in sel) / lam, 3)
    return out


def with_td_scale(rows, scale: dict) -> list:
    """The rows re-scored with a touchdown scale: six points a touchdown
    either way (a quarterback's are rushing ones)."""
    out = []
    for r in rows:
        k = scale.get(r[2])
        if k and len(r) > 8 and r[7] is not None:
            r = (*r[:4], r[4] + 6.0 * r[7] * (k - 1.0), *r[5:])
        out.append(r)
    return out


def play_table(seasons) -> dict:
    """{"designation|practice": {"n", "played"}}, and "designation|*":
    listed players who took a snap, by how they practised that week."""
    from engine.practice import designation_of, practice_of
    from engine.sources.injuries import load_injuries
    acc: dict = {}
    for s in seasons:
        try:
            reports = load_injuries(s)
            snaps = N.load_snap_counts(s)
        except Exception as exc:                             # noqa: BLE001
            print(f"  {s}: no injury reports or snap counts ({exc})")
            continue
        took: set = set()
        for r in snaps:
            try:
                total = sum(float(r.get(k) or 0) for k in ("offense_snaps", "defense_snaps", "st_snaps"))
                wk = int(float(r.get("week") or 0))
            except ValueError:
                continue
            if total > 0 and (r.get("game_type") or "REG") == "REG":
                took.add((_norm(r.get("player") or ""), wk))
        for r in reports:
            if (r.get("game_type") or "REG") != "REG":
                continue
            d = designation_of(r.get("report_status"))
            if d not in ("Questionable", "Doubtful", "Out"):
                continue
            try:
                wk = int(float(r.get("week") or 0))
            except ValueError:
                continue
            name = _norm(r.get("full_name") or "")
            if not name:
                continue
            p = practice_of(r.get("practice_status"))
            for key in (f"{d}|{p}", f"{d}|*"):
                a = acc.setdefault(key, [0, 0])
                a[0] += 1
                a[1] += int((name, wk) in took)
    return {d: {"n": n, "played": round(k / n, 4)} for d, (n, k) in sorted(acc.items()) if n}


def save(res: dict) -> str:
    from engine import modelstate
    path = modelstate.path(FW.STORE)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        json.dump(res, fh, indent=1, sort_keys=True)
    return str(path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seasons", default="2023-2025")
    ap.add_argument("--weeks", default="4-17")
    ap.add_argument("--save", action="store_true", help="keep the spread and play chances where the board reads them")
    ap.add_argument("--rows", default="", help="write the scored rows to this JSON (for re-scoring)")
    ap.add_argument("--from-rows", default="", help="re-score the rows a run wrote, building no slates")
    a = ap.parse_args(argv)
    seasons, weeks = _rng(a.seasons), _rng(a.weeks)
    rows: list = []
    if a.from_rows:
        rows = [tuple(r) for r in json.loads(Path(a.from_rows).read_text())]
        seasons = sorted({r[0] for r in rows}) or seasons
        weeks = sorted({r[1] for r in rows}) or weeks
    else:
        # The measurement is of the model as it stands, never of a scale a
        # previous --save already applied.
        FW._SAVED["fit"] = {k: v for k, v in FW.saved_fit().items() if k != "td_scale"}
        usage_conn = _usage_conn()
        print("Usage maps: " + ("replayed as of each week from the history database"
                                if usage_conn is not None else
                                "none (no NFL usage in the history database) — the touchdown "
                                "model runs without its expected-points share, unlike live"), flush=True)
        for s in seasons:
            print(f"Season {s}:", flush=True)
            rows += week_rows(s, weeks, log=lambda m: print(m, flush=True), usage_conn=usage_conn)
    if a.rows:
        Path(a.rows).write_text(json.dumps(rows))
    if not rows:
        print("No player-weeks scored.")
        return 1
    res = score(rows)
    print(f"\nTHIS WEEK'S PROJECTION vs THE SEASON AVERAGE — {seasons[0]}-{seasons[-1]}, weeks {weeks[0]}-{weeks[-1]}")
    print("  pos     n   rank wk/szn    pairs wk/szn  (t)    MAE wk/szn    bias wk/szn")
    for pos, v in res.items():
        print(f"  {pos:4s} {v['n']:6,d}  {v['rank_week']}/{v['rank_season']}"
              f"   {v['pairs_week']}/{v['pairs_season']} ({v['pairs_gain_t']})"
              f"   {v['mae_week']}/{v['mae_season']}   {v['bias_week']}/{v['bias_season']}")
    if rows and len(rows[0]) > 9:
        nofill = [(*r[:4], r[9], *r[5:]) for r in rows]
        was, now = score(nofill)["ALL"], res["ALL"]
        print("\nTHE SEASON-AVERAGE FILL (parts the board does not project): without → with")
        print(f"  pairs {was['pairs_week']} → {now['pairs_week']}   MAE {was['mae_week']} → {now['mae_week']}   "
              f"bias {was['bias_week']} → {now['bias_week']}")
        for pos in POSITIONS:
            x, y = score([r for r in nofill if r[2] == pos])[pos], res[pos]
            print(f"  {pos}: pairs {x['pairs_week']} → {y['pairs_week']}, MAE {x['mae_week']} → "
                  f"{y['mae_week']}, bias {x['bias_week']} → {y['bias_week']}")
    tdr = td_report(rows)
    td_scale = {}
    if tdr:
        print("\nTOUCHDOWNS: the model's expected count a game against what was scored "
              "(a quarterback's: rushing)")
        for pos, (m, a_, n) in tdr.items():
            print(f"  {pos}: model {m} · scored {a_} (×{a_ / m if m else 0:.2f}, n {n:,})")
        td_scale = td_scale_fit(rows)
        print("  scale kept (beat the model on every held-out season): "
              + (", ".join(f"{p} ×{k}" for p, k in td_scale.items()) or "none"))
        if td_scale:
            scaled = score(with_td_scale(rows, td_scale))
            for pos in td_scale:
                x, y = res[pos], scaled[pos]
                print(f"    {pos}: pairs {x['pairs_week']} → {y['pairs_week']}, MAE {x['mae_week']} → "
                      f"{y['mae_week']}, bias {x['bias_week']} → {y['bias_week']}")
    # WHAT LIVE WILL RUN: the scale, where one was kept, is in every
    # projection the box publishes, so the range, the spread and the
    # quoted score are fitted on the projection with it.
    final = with_td_scale(rows, td_scale) if td_scale else rows
    if td_scale:
        res = score(final)
    rng = range_fit(final)
    print("\nWHERE EIGHT WEEKS IN TEN LAND (10th / 90th percentile of scored, as lines on the projection):")
    for pos, (la, lb, ha, hb) in rng.items():
        print(f"  {pos}: low ≈ {la} + {lb} × projection, high ≈ {ha} + {hb} × projection")
    held = sorted({r[0] for r in final})
    if len(held) > 1:
        print("  held out (fit on the other seasons, scored on this one): below / inside / above")
        for s in held:
            fit = range_fit([r for r in final if r[0] != s])
            cov = range_cover([r for r in final if r[0] == s], fit)
            print(f"    {s}: " + "  ".join(f"{p} {b:.1%}/{i:.1%}/{o:.1%}" for p, (b, i, o) in cov.items()))
    fit = residual_fit(final)
    print("\nHOW WIDE A WEEK LANDS around its projection (sd of scored − projected):")
    for pos, (a_, b_, bands) in fit.items():
        print(f"  {pos}: sd ≈ {a_} + {b_} × projection   bands " +
              ", ".join(f"{x:g}→{s:g} (n {n})" for x, s, n in bands))
    plays = play_table(seasons)
    print("\nLISTED PLAYERS WHO PLAYED (nflverse injury reports against snap counts):")
    for d, v in plays.items():
        print(f"  {d:24s} {v['played']:.1%} of {v['n']:,}")
    if a.save:
        out = {"measured": time.strftime("%Y-%m-%d"), "seasons": f"{seasons[0]}-{seasons[-1]}",
               "weeks": f"{weeks[0]}-{weeks[-1]}", "score": res,
               "residual": {p: [a_, b_] for p, (a_, b_, _bands) in fit.items()},
               "td_scale": td_scale,
               "range": {p: list(v) for p, v in rng.items()},
               "play": {d: v["played"] for d, v in plays.items()
                        if not d.startswith("Out") and v["n"] >= FW.PLAY_MIN_N}}
        print(f"\n  saved → {save(out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
