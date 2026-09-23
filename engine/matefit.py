"""A teammate out at his position: what it does to the player, measured.

Ethan, 2026-09-23: "make sure everything we pull, all the data we use is
actually being projected to the pick ... if we need to say it under the
card ... but we also need our model to adjust accordingly."

The board has SHOWN this since 2026-09-14 — engine/redistribute's usage
ripple ("Pacheco out — Hunt absorbed +11% of the carries") — and moved
nothing, because engine/ripplefit asks whether the ripple beats the
CLOSING LINE. That is the edge board's question. The Most Likely board's
question is whether it predicts what the player DOES, and it does, by more
than anything else this model reads.

For every top-three WR, TE and RB by volume a game (three or more earlier
games) from week 4 on:

    expected = the projection's own starting point: engine/form
               .compute_form over his earlier games (the live base)
    case     = "above" when a teammate ranked ABOVE him at his position
               did not play, "below" when only one ranked below him did;
               "new" when that teammate played the team's previous week
               (the player's recent games do not know yet), "cont" when he
               was already out (they partly do)

and the multiplier is actual/expected in that case over actual/expected
in games with all three playing. The rule is engine/qbfit.shipped's: two
standard errors from 1.0 and three seasons of four. Standard library only.
"""
from __future__ import annotations

from collections import defaultdict

from .qbfit import measure, shipped   # noqa: F401  (same measurement, same rule)

GROUPS = ("WR", "TE", "RB")
#: position -> [(market, column(s), form floor)]
MARKETS = {
    "WR": [("rec_yds", ("receiving_yards",), 15.0), ("receptions", ("receptions",), 1.5),
           ("anytime_td", ("receiving_tds", "rushing_tds"), 0.0)],
    "TE": [("rec_yds", ("receiving_yards",), 15.0), ("receptions", ("receptions",), 1.5),
           ("anytime_td", ("receiving_tds", "rushing_tds"), 0.0)],
    "RB": [("rush_yds", ("rushing_yards",), 15.0), ("receptions", ("receptions",), 1.5),
           ("rec_yds", ("receiving_yards",), 12.0), ("anytime_td", ("receiving_tds", "rushing_tds"), 0.0)],
}
FIRST_WEEK = 4
MIN_GAMES = 3
TOP = 3


def _f(r: dict, k: str) -> float:
    try:
        return float(r.get(k) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def volume(r: dict, pos: str) -> float:
    """The opportunity the depth order is ranked on: targets, and carries for a back."""
    return _f(r, "targets") + (_f(r, "carries") if pos == "RB" else 0.0)


def ranked(games: dict, team: str, pos: str, week: int) -> list[tuple]:
    """[(name, per-game volume, games, last week played)] best first — players
    at this position with MIN_GAMES before ``week``, top TOP."""
    out = []
    for (t, p, name), g in games.items():
        if t != team or p != pos:
            continue
        prev = [w for w in g if w < week]
        if len(prev) < MIN_GAMES:
            continue
        out.append((name, sum(volume(g[w], pos) for w in prev) / len(prev), len(prev), max(prev)))
    out.sort(key=lambda x: -x[1])
    return out[:TOP]


def case_for(order: list[tuple], me: str, playing: set, last_team_week: int) -> str | None:
    """"above_new" / "above_cont" / "below_new" / "below_cont", or None with all playing."""
    names = [o[0] for o in order]
    if me not in names:
        return None
    i = names.index(me)
    for side, group in (("above", order[:i]), ("below", order[i + 1:])):
        out = [o for o in group if o[0] not in playing]
        if out:
            fresh = any(o[3] >= last_team_week for o in out)
            return f"{side}_{'new' if fresh else 'cont'}"
    return None


def samples(seasons: dict) -> list[dict]:
    from .form import compute_form
    from .models import GameLog
    out = []
    for season, rows in sorted(seasons.items()):
        rows = [r for r in rows if str(r.get("season_type") or "REG") in ("REG", "")]
        games: dict = defaultdict(dict)
        team_weeks: dict = defaultdict(set)
        for r in rows:
            pos = str(r.get("position") or "").upper()
            team = str(r.get("team") or r.get("recent_team") or "")
            wk = int(_f(r, "week"))
            team_weeks[team].add(wk)
            if pos in GROUPS:
                games[(team, pos, r["player_display_name"])][wk] = r
        for team, weeks in team_weeks.items():
            for wk in sorted(weeks):
                if wk < FIRST_WEEK:
                    continue
                last = max((w for w in weeks if w < wk), default=0)
                for pos in GROUPS:
                    order = ranked(games, team, pos, wk)
                    playing = {o[0] for o in order if wk in games[(team, pos, o[0])]}
                    for name, _v, _n, _l in order:
                        g = games[(team, pos, name)]
                        if wk not in g:
                            continue
                        case = case_for(order, name, playing, last)
                        prev = [g[w] for w in sorted(g) if w < wk]
                        for m, cols, floor in MARKETS[pos]:
                            vals = [sum(_f(p, c) for c in cols) for p in prev]
                            logs = [GameLog(week=len(vals) - j, opponent="", value=v)
                                    for j, v in enumerate(reversed(vals))]
                            e = compute_form(logs, sum(vals) / len(vals), None).mean
                            if e < floor or e <= 0:
                                continue
                            out.append({"season": season, "m": m, "g": pos, "e": e,
                                        "y": sum(_f(g[wk], c) for c in cols), "tier": case})
    return out
