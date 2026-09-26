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
SIGNALS = ("defense_epa", "td_allowed")


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


def points(graded: list, epa: dict, allowed: dict) -> dict:
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
    return out


def study(pts: dict) -> dict:
    """scanfit's fit, held-out gain and bar, on these points."""
    return S.study(pts)


def report(res: dict) -> str:
    lines = ["Touchdowns: the opponent's defence on top of the model's own number "
             "(held out a season at a time; PASSES = worth putting in the number)"]
    for (name, _mk, grp), r in sorted(res.items()):
        se = f" ± {r['se']:.3f}" if r.get("se") is not None else ""
        held = "  ".join(f"{s} {100 * v:+.2f}%" for s, v in r["held_out"].items() if v is not None)
        lines.append(f"  {name:<12} {grp:<3} b = {r['b']:+.3f}{se} (t {r['t']:.1f})  n {r['n']:>6}   "
                     f"1 SD of defence moves his chance {100 * r['per_sd']:+.1f}%   held out {held}   "
                     f"mean {100 * r['mean_gain']:+.3f}%   {'PASSES' if r['passes'] else 'fails'}")
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
    pts = points(graded, defense_epa_table(epa_rows), td_allowed_table(allowed_rows))
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
