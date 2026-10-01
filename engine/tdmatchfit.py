"""Does a bad defence raise a receiver's touchdown chance beyond the model's
own number? Measured, walk-forward, on five seasons of who actually scored.

Ethan, 2026-09-25: "The Detroit Lions secondary and defense and corners
and all that shit is completely ass right now ... I bet on Chris Olave to
get a touchdown ... I bet on Dalton Kincaid to get a touchdown ... and
they all did. So you need to think like that too."

The touchdown model (engine/touchdowns.td_probability) gives backs a
measured defence multiplier and receivers none, because engine/defensefit
found no defence-vs-position TOUCHDOWN number that predicted a receiver's
touchdowns. This asks the question the other way round, on the model's
own graded rows: take every player-week engine/tdbacktest replays
(22,168 of them), keep its probability as the model's number, join the
OPPONENT'S defence as of the weeks before that game, and fit

    scored ≈ prob · (1 + a + b · x)

with the same least squares, the same season-held-out gain and the same
bar engine/scanfit admits a signal on: held-out gain positive on average
and in all but one season, b at least MIN_T standard errors from zero.

Two readings of "bad defence", each centred on the league so 0 is average:

  defense_epa   the opponent's EPA allowed per play, season to date,
                blended with last season by games / (games + PRIOR_GAMES)
                (engine/db team_weeks, 2021–2025 on the box);
  td_allowed    touchdowns the opponent has allowed per game to this
                player's position group, season to date, the same blend —
                receiving for WR/TE, receiving plus rushing for RB.

And two readings of the RED ZONE (#168, Ethan's "how the defenses guards
the offense in the red zone"), the half of the other model's touchdown
method still unmeasured here:

  rz_allowed     how often the opponent lets offences inside its 20 —
                 engine/redzone.team_rates' `def_rel`, opponent-adjusted,
                 exactly the number the touchdown scenarios read today;
  rz_td_allowed  once an offence is there, how often it scores against
                 this defence: touchdowns allowed per red-zone play
                 allowed, season to date (ratio of sums), the same blend.

THE RED-ZONE READINGS CARRY A STRICTER, PRE-REGISTERED RULE (2026-10-01,
before any real run). A defence's number is the same for every player who
faces it, so the shared fit's t treats one opponent-season as dozens of
independent results; on synthetic noise the shared bar passed 4 tests in
60, and four readings by three groups would make a fluke likely. So each
red-zone reading is ONE test, pooled over WR, TE and RB (group "ALL"):
the shared season rule, plus a cluster-robust t (clusters = opponent
season) of at least RZ_MIN_T. Noise passed that 2 times in 180; a 9%-per-
SD effect still passes. The per-group rows are printed for reading only.

Receivers (WR, TE) are scored apart from backs (RB), since the model
already gives backs a defence term. Run on the box:

    python3 -m engine.tdmatchfit                 # every season on file
    python3 -m engine.tdmatchfit --seasons 2023 2024 2025

Standard library only. Nothing here moves a number; the verdict says
whether one should.
"""
from __future__ import annotations

from engine import scanfit as S

#: Games of this season a defence's number leans on before it stands alone.
PRIOR_GAMES = 4.0
#: Position groups scored, and the touchdown markets that count against a
#: defence for each.
GROUPS = {"WR": ("rec_td",), "TE": ("rec_td",), "RB": ("rec_td", "rush_td")}
SIGNALS = ("defense_epa", "td_allowed", "rz_allowed", "rz_td_allowed")
#: The red-zone readings, judged pooled ("ALL") on a cluster-robust t.
RZ_SIGNALS = ("rz_allowed", "rz_td_allowed")
RZ_MIN_T = 2.5
#: The markets a red-zone play is counted from (engine/redzone's own).
RZ_MARKETS = ("rz_tgt", "rz_car")
TD_MARKETS = ("rec_td", "rush_td")


def _blend(now_vals: list, prior_mean: float | None) -> float | None:
    """Season-to-date mean, leaning on last season's until PRIOR_GAMES."""
    if not now_vals and prior_mean is None:
        return None
    if not now_vals:
        return prior_mean
    now = sum(now_vals) / len(now_vals)
    if prior_mean is None:
        return now
    w = len(now_vals) / (len(now_vals) + PRIOR_GAMES)
    return w * now + (1 - w) * prior_mean


def defense_epa_table(rows: list) -> dict:
    """{(season, week, team): opponent-facing defensive EPA as of that week,
    centred on the league that week} from team_weeks rows
    (season, period, team, def_epa)."""
    by: dict = {}
    for r in rows:
        try:
            by.setdefault((int(r["season"]), str(r["team"])), {})[int(r["period"])] = float(r["def_epa"])
        except (TypeError, ValueError, KeyError):
            continue
    season_mean: dict = {}
    for (season, team), weeks in by.items():
        season_mean.setdefault(season, {})[team] = sum(weeks.values()) / len(weeks)
    out: dict = {}
    seasons = sorted({s for s, _t in by})
    for season in seasons:
        teams = [t for s, t in by if s == season]
        weeks_all = sorted({w for (s, t), ws in by.items() if s == season for w in ws})
        for wk in weeks_all:
            vals = {}
            for t in teams:
                now = [v for w, v in by[(season, t)].items() if w < wk]
                vals[t] = _blend(now, (season_mean.get(season - 1) or {}).get(t))
            have = [v for v in vals.values() if v is not None]
            if not have:
                continue
            league = sum(have) / len(have)
            for t, v in vals.items():
                if v is not None:
                    out[(season, wk, t)] = v - league
    return out


def td_allowed_table(rows: list) -> dict:
    """{(season, week, opponent, group): touchdowns allowed per game to the
    group as of that week, centred on the league} from player_game_logs
    rows (season, period, opponent, position, market, value)."""
    per_game: dict = {}
    for r in rows:
        try:
            season, wk = int(r["season"]), int(r["period"])
            pos = str(r["position"] or "").upper()
            opp, mk, v = str(r["opponent"] or ""), str(r["market"]), float(r["value"] or 0.0)
        except (TypeError, ValueError, KeyError):
            continue
        for grp, markets in GROUPS.items():
            if pos == grp and mk in markets and opp:
                per_game[(season, wk, opp, grp)] = per_game.get((season, wk, opp, grp), 0.0) + v
    out: dict = {}
    seasons = sorted({k[0] for k in per_game})
    for grp in GROUPS:
        prior_mean: dict = {}
        for season in seasons:
            weeks = sorted({k[1] for k in per_game if k[0] == season and k[3] == grp})
            teams = sorted({k[2] for k in per_game if k[0] == season and k[3] == grp})
            for wk in weeks:
                vals = {}
                for t in teams:
                    now = [per_game.get((season, w, t, grp), 0.0) for w in weeks if w < wk
                           and (season, w, t, grp) in per_game]
                    vals[t] = _blend(now, prior_mean.get(t))
                have = [v for v in vals.values() if v is not None]
                if not have:
                    continue
                league = sum(have) / len(have)
                for t, v in vals.items():
                    if v is not None:
                        out[(season, wk, t, grp)] = v - league
            prior_mean = {t: sum(per_game.get((season, w, t, grp), 0.0) for w in weeks) / len(weeks)
                          for t in teams if weeks}
    return out


def rz_allowed_table(conn, keys) -> dict:
    """{(season, week, team): the defence's red-zone plays allowed per game
    before that week, relative to the league} — engine/redzone.team_rates'
    `def_rel`, so the study scores the very number the scenarios show.
    ``keys`` is the (season, week) pairs the graded rows need."""
    from . import redzone
    out: dict = {}
    for season, wk in sorted(set(keys)):
        for team, r in redzone.team_rates(conn, season, before_week=wk).items():
            v = r.get("def_rel")
            if v is not None:
                out[(season, wk, team)] = float(v)
    return out


def rz_td_rate_table(rows: list) -> dict:
    """{(season, week, opponent): touchdowns allowed per red-zone play
    allowed before that week, centred on the league} from player_game_logs
    rows (season, period, opponent, market, value). A ratio of season sums,
    leaning on last season's ratio until PRIOR_GAMES."""
    td: dict = {}
    rz: dict = {}
    for r in rows:
        try:
            season, wk = int(r["season"]), int(r["period"])
            opp, mk, v = str(r["opponent"] or ""), str(r["market"]), float(r["value"] or 0.0)
        except (TypeError, ValueError, KeyError):
            continue
        if not opp:
            continue
        if mk in TD_MARKETS:
            td[(season, wk, opp)] = td.get((season, wk, opp), 0.0) + v
        elif mk in RZ_MARKETS:
            rz[(season, wk, opp)] = rz.get((season, wk, opp), 0.0) + v
    keys = set(td) | set(rz)
    out: dict = {}
    prior: dict = {}
    for season in sorted({k[0] for k in keys}):
        weeks = sorted({k[1] for k in keys if k[0] == season})
        teams = sorted({k[2] for k in keys if k[0] == season})
        for wk in weeks:
            vals = {}
            for t in teams:
                played = [w for w in weeks if w < wk and (season, w, t) in rz]
                plays = sum(rz.get((season, w, t), 0.0) for w in played)
                tds = sum(td.get((season, w, t), 0.0) for w in played)
                now = (tds / plays) if plays > 0 else None
                pri = prior.get(t)
                if now is None:
                    vals[t] = pri
                elif pri is None:
                    vals[t] = now
                else:
                    w8 = len(played) / (len(played) + PRIOR_GAMES)
                    vals[t] = w8 * now + (1 - w8) * pri
            have = [v for v in vals.values() if v is not None]
            if not have:
                continue
            league = sum(have) / len(have)
            for t, v in vals.items():
                if v is not None:
                    out[(season, wk, t)] = v - league
        prior = {}
        for t in teams:
            plays = sum(rz.get((season, w, t), 0.0) for w in weeks)
            if plays > 0:
                prior[t] = sum(td.get((season, w, t), 0.0) for w in weeks) / plays
    return out


def points(graded: list, epa: dict, allowed: dict, rz_allowed: dict | None = None,
           rz_rate: dict | None = None) -> dict:
    """{(signal, "anytime_td", group): [(prob, x, scored, season)]} from the
    backtest's collected rows."""
    out: dict = {}
    for r in graded:
        grp = str(r.get("position") or "").upper()
        if grp not in GROUPS:
            continue
        season, wk, opp = int(r["season"]), int(r["week"]), str(r.get("opponent") or "")
        e, y = float(r["prob"]), int(r["scored"])
        if e <= 0 or not opp:
            continue
        x = epa.get((season, wk, opp))
        if x is not None:
            out.setdefault(("defense_epa", "anytime_td", grp), []).append((e, x, y, season))
        x = allowed.get((season, wk, opp, grp))
        if x is not None:
            out.setdefault(("td_allowed", "anytime_td", grp), []).append((e, x, y, season))
        for name, tab in (("rz_allowed", rz_allowed), ("rz_td_allowed", rz_rate)):
            x = (tab or {}).get((season, wk, opp))
            if x is None:
                continue
            # The fifth element is the cluster: one opponent-season.
            pt = (e, x, y, season, (season, opp))
            out.setdefault((name, "anytime_td", grp), []).append(pt)
            out.setdefault((name, "anytime_td", "ALL"), []).append(pt)
    return out


def clustered_t(pts: list, a: float, b: float) -> float:
    """|b| over its cluster-robust standard error for ``y − e = a·e + b·e·x``
    (clusters = the fifth element of each point; a sandwich estimator with
    the G/(G−1) correction). 0 when it cannot be computed."""
    import math
    suu = sum(e * e for e, *_ in pts)
    svv = sum((e * x) ** 2 for e, x, *_ in pts)
    suv = sum(e * e * x for e, x, *_ in pts)
    det = suu * svv - suv * suv
    if det <= 0:
        return 0.0
    i01, i11 = -suv / det, suu / det
    sums: dict = {}
    for pt in pts:
        e, x, y = pt[0], pt[1], pt[2]
        c = pt[4] if len(pt) > 4 else id(pt)
        r = y - e * (1 + a + b * x)
        acc = sums.setdefault(c, [0.0, 0.0])
        acc[0] += e * r
        acc[1] += e * x * r
    g = len(sums)
    if g < 2:
        return 0.0
    m00 = sum(s0 * s0 for s0, _ in sums.values())
    m01 = sum(s0 * s1 for s0, s1 in sums.values())
    m11 = sum(s1 * s1 for _, s1 in sums.values())
    # V[1][1] of inv · meat · inv, inv symmetric.
    v11 = (i01 * i01 * m00 + 2 * i01 * i11 * m01 + i11 * i11 * m11) * g / (g - 1)
    return abs(b) / math.sqrt(v11) if v11 > 0 else 0.0


def study(pts: dict) -> dict:
    """scanfit's fit, held-out gain and bar, on these points; the red-zone
    readings are then judged by the pre-registered rule above, pooled."""
    res = S.study(pts)
    for key, r in res.items():
        name, _mk, grp = key
        if name not in RZ_SIGNALS:
            continue
        r["t_cluster"] = round(clustered_t(pts[key], r["a"], r["b"]), 2)
        vals = [v for v in r["held_out"].values() if v is not None]
        season_rule = (len(vals) >= 3 and sum(vals) / len(vals) > 0
                       and sum(v > 0 for v in vals) >= len(vals) - 1)
        r["decides"] = grp == "ALL"
        r["passes"] = bool(r["decides"] and season_rule and r["t_cluster"] >= RZ_MIN_T)
    return res


def report(res: dict) -> str:
    lines = ["Touchdowns: the opponent's defence on top of the model's own number "
             "(held out a season at a time; PASSES = worth putting in the number)"]
    for (name, _mk, grp), r in sorted(res.items()):
        se = f" ± {r['se']:.3f}" if r.get("se") is not None else ""
        held = "  ".join(f"{s} {100 * v:+.2f}%" for s, v in r["held_out"].items() if v is not None)
        tc = f", clustered {r['t_cluster']:.1f}" if r.get("t_cluster") is not None else ""
        verdict = ("PASSES" if r["passes"] else "fails") if r.get("decides", True) else "(by group, reading only)"
        lines.append(f"  {name:<14} {grp:<3} b = {r['b']:+.3f}{se} (t {r['t']:.1f}{tc})  n {r['n']:>6}   "
                     f"1 SD of defence moves his chance {100 * r['per_sd']:+.1f}%   held out {held}   "
                     f"mean {100 * r['mean_gain']:+.3f}%   {verdict}")
    return "\n".join(lines)


def run(conn, seasons=None) -> dict:
    """Collect the backtest's rows and score both defence readings."""
    from . import tdbacktest
    graded: list = []
    tdbacktest.run(conn, seasons=seasons, collect=graded.append)
    epa_rows = conn.execute("SELECT season, period, team, def_epa FROM team_weeks "
                            "WHERE sport='nfl' AND def_epa IS NOT NULL").fetchall()
    allowed_rows = conn.execute(
        "SELECT season, period, opponent, position, market, value FROM player_game_logs "
        "WHERE sport='nfl' AND market IN ('rec_td','rush_td')").fetchall()
    rz_rows = conn.execute(
        "SELECT season, period, opponent, market, value FROM player_game_logs "
        "WHERE sport='nfl' AND market IN ('rec_td','rush_td','rz_tgt','rz_car')").fetchall()
    keys = {(int(r["season"]), int(r["week"])) for r in graded}
    pts = points(graded, defense_epa_table(epa_rows), td_allowed_table(allowed_rows),
                 rz_allowed_table(conn, keys), rz_td_rate_table(rz_rows))
    return study(pts)


def main(argv=None) -> int:
    import argparse
    from . import db
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seasons", nargs="*", type=int, default=None)
    args = ap.parse_args(argv)
    res = run(db.connect(), seasons=args.seasons)
    print(report(res) if res else "  no graded rows carried a defence reading")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
