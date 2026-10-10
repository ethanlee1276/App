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
    """The opportunity the depth order is ranked on: his offensive snap share
    when the game carries one (`games_from_snaps`), else targets, and
    carries for a back.

    SNAPS FIRST since 2026-09-27. Mason Taylor, the Jets' TE1 on 66% and
    46% of the snaps, drew 0 targets in week 2 — so the box scores had no
    row for him and the target order made Kenyon Sadiq (36% of the snaps)
    the starter, and Taylor's absence a backup's. Ranked on snaps, every
    "above" effect measured at least as strong on 2022-2025 and one the
    target order never found appeared (a TE's receiving yards with the TE
    above him just out, ×1.75 ± .25, every season)."""
    if "_snap" in r:
        return float(r["_snap"])
    return _f(r, "targets") + (_f(r, "carries") if pos == "RB" else 0.0)


def games_from_snaps(stat_rows: list[dict], snap_rows: list[dict]) -> tuple[dict, dict]:
    """(games, team_weeks) for one season with every game a WR/TE/RB took
    an offensive snap in — his box-score row where he has one, zeros where
    he played and recorded nothing — each carrying its snap share as
    ``_snap``. The shape `samples` and engine/teammates.depth_table read."""
    stat = {}
    for r in stat_rows:
        if str(r.get("season_type") or "REG") not in ("REG", ""):
            continue
        stat[(str(r.get("team") or r.get("recent_team") or ""), int(_f(r, "week")),
              str(r.get("player_display_name") or ""))] = r
    games: dict = defaultdict(dict)
    team_weeks: dict = defaultdict(set)
    for r in snap_rows:
        if str(r.get("game_type") or "REG") not in ("REG", ""):
            continue
        team, wk = str(r.get("team") or ""), int(_f(r, "week"))
        if not team or wk <= 0:
            continue
        team_weeks[team].add(wk)
        pos = str(r.get("position") or "").upper()
        if pos not in GROUPS or _f(r, "offense_snaps") <= 0:
            continue
        name = str(r.get("player") or "")
        row = dict(stat.get((team, wk, name)) or {})
        pct = _f(r, "offense_pct")
        row["_snap"] = pct / 100.0 if pct > 1.0 else pct
        games[(team, pos, name)][wk] = row
    return games, team_weeks


def early_min_games(week: int) -> int:
    """How many games a player needs before ``week`` to be ranked: MIN_GAMES,
    or every game played so far in weeks 2-3 — the early season the rule
    used to skip (see `early_samples`)."""
    return max(1, min(MIN_GAMES, int(week) - 1))


def ranked(games: dict, team: str, pos: str, week: int,
           min_games: int | None = None) -> list[tuple]:
    """[(name, per-game volume, games, last week played)] best first — players
    at this position with ``min_games`` (default MIN_GAMES) before ``week``,
    top TOP."""
    need = MIN_GAMES if min_games is None else min_games
    out = []
    for (t, p, name), g in games.items():
        if t != team or p != pos:
            continue
        prev = [w for w in g if w < week]
        if len(prev) < need:
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


def samples(seasons: dict, snaps: dict | None = None) -> list[dict]:
    """``snaps`` ({season: snap-count rows}) ranks the depth order on snap
    share (`games_from_snaps`); without it, on targets as first measured."""
    from .form import compute_form
    from .models import GameLog
    out = []
    for season, rows in sorted(seasons.items()):
        if snaps and snaps.get(season):
            games, team_weeks = games_from_snaps(rows, snaps[season])
        else:
            games, team_weeks = _games_from_stats(rows)
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


def _games_from_stats(rows: list[dict]) -> tuple[dict, dict]:
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
    return games, team_weeks


def early_samples(seasons: dict, weeks=(2, 3)) -> list[dict]:
    """The same measurement in WEEKS 2-3, which `samples` skips.

    Ethan, 2026-09-27, comparing us with another model on Jets @ Lions in
    week 3: Mason Taylor out, Kenyon Sadiq the obvious beneficiary, and our
    teammate step never ran — the depth order needs MIN_GAMES this season,
    so every team's was empty until week 4. Here the order ranks on every
    game played so far (`early_min_games`) and the form is carried from
    last season as the live early-season board's is (engine/carry).
    ``seasons`` is {season: rows} and must hold each season's previous one.

    On 2022-2025 every "above" cell came out above 1.0 and within its
    error of the week-4+ multiplier — TE receptions ×1.24 ± .31 (n 13)
    against ×1.45, WR receptions ×1.29 ± .18 (n 39) against ×1.18, RB
    rushing ×1.96 ± .59 (n 9) against ×1.65 — too thin to ship numbers
    of their own, consistent enough that the measured ones apply from
    week 2."""
    from .form import compute_form
    from .models import GameLog
    out = []
    for season in sorted(s for s in seasons if s - 1 in seasons):
        rows = [r for r in seasons[season] if str(r.get("season_type") or "REG") in ("REG", "")]
        prior: dict = defaultdict(list)
        for r in seasons[season - 1]:
            if str(r.get("season_type") or "REG") in ("REG", ""):
                prior[r["player_display_name"]].append(r)
        games: dict = defaultdict(dict)
        team_weeks: dict = defaultdict(set)
        for r in rows:
            pos = str(r.get("position") or "").upper()
            team = str(r.get("team") or r.get("recent_team") or "")
            wk = int(_f(r, "week"))
            team_weeks[team].add(wk)
            if pos in GROUPS:
                games[(team, pos, r["player_display_name"])][wk] = r
        for team, tw in team_weeks.items():
            for wk in sorted(tw):
                if wk not in weeks:
                    continue
                last = max((w for w in tw if w < wk), default=0)
                for pos in GROUPS:
                    order = ranked(games, team, pos, wk, early_min_games(wk))
                    playing = {o[0] for o in order if wk in games[(team, pos, o[0])]}
                    for name, _v, _n, _l in order:
                        g = games[(team, pos, name)]
                        if wk not in g:
                            continue
                        case = case_for(order, name, playing, last)
                        before = sorted(prior[name], key=lambda r: _f(r, "week"))
                        now = [g[w] for w in sorted(g) if w < wk]
                        for m, cols, floor in MARKETS[pos]:
                            vals = [sum(_f(p, c) for c in cols) for p in before + now]
                            if len(vals) < 3:
                                continue
                            logs = [GameLog(week=len(vals) - j, opponent="", value=v)
                                    for j, v in enumerate(reversed(vals))]
                            e = compute_form(logs, sum(vals) / len(vals), None).mean
                            if e < floor or e <= 0:
                                continue
                            out.append({"season": season, "m": m, "g": pos, "e": e,
                                        "y": sum(_f(g[wk], c) for c in cols), "tier": case})
    return out


# ═══ ACROSS POSITIONS ════════════════════════════════════════════════════
#
# Ethan, 2026-09-27: the other model "finds where other players are out
# and other players could step up" — a wide receiver out lifting the tight
# end and the back, not only the next receiver. `samples` measures the
# same position only. This measures the rest: when one of a team's two
# leading target-getters (LEADER_SHARE of the targets or more, any of WR,
# TE, RB) does not play, what the players at the OTHER positions do
# against their own form. Only games with nobody out at the player's own
# position count, so the effect is not the same-position one again.

#: MEASURED 2026-09-27 (`python3 matefit.py --cross`, 2022-2025, week 4+):
#: small and not significant — nothing ships. A TE's receiving yards with
#: the WR leader out ×1.13 ± .13 (n 66), a WR's catches with the TE leader
#: out ×1.12 ± .11 (n 27); in TARGETS, WRs +11% ± 9% (n 30, up all four
#: seasons) and the TE +7% ± 7% (n 68) — against +19% to +75% for the
#: same-position cases engine/teammates applies. A back's carries and
#: targets do not move when a receiver sits. The two cells the plain rule
#: would pass rest on two games each, hence MIN_CROSS_N.
#: The fewest games a cross-position cell needs before the rule is asked.
MIN_CROSS_N = 20
#: A target leader: one of the team's top two by targets a game, at this
#: share of the team's targets or more over his earlier games.
LEADER_SHARE = 0.18
LEADERS = 2
#: The markets measured across positions (a touchdown is too rare to).
CROSS_MARKETS = {
    "WR": [("rec_yds", ("receiving_yards",), 15.0), ("receptions", ("receptions",), 1.5)],
    "TE": [("rec_yds", ("receiving_yards",), 15.0), ("receptions", ("receptions",), 1.5)],
    "RB": [("rush_yds", ("rushing_yards",), 15.0), ("receptions", ("receptions",), 1.5),
           ("rec_yds", ("receiving_yards",), 12.0)],
}


def target_leaders(games: dict, team: str, week: int) -> list[tuple]:
    """[(name, position, targets a game, last week played)] — the team's
    top LEADERS target-getters before ``week`` with MIN_GAMES games and
    LEADER_SHARE of the team's targets."""
    per: list = []
    team_tgt = 0.0
    for (t, p, name), g in games.items():
        if t != team:
            continue
        prev = [w for w in g if w < week]
        tg = sum(_f(g[w], "targets") for w in prev)
        team_tgt += tg
        if len(prev) >= MIN_GAMES:
            per.append((name, p, tg / len(prev), max(prev), tg))
    if team_tgt <= 0:
        return []
    per.sort(key=lambda x: -x[2])
    return [(n, p, tpg, last) for n, p, tpg, last, tg in per[:LEADERS] if tg / team_tgt >= LEADER_SHARE]


def cross_case(leaders: list, me: str, my_pos: str, played: set, last_team_week: int) -> str | None:
    """"x{POS}_new" / "x{POS}_cont" when a target leader at another
    position did not play (the first such, by targets), else None."""
    for name, pos, _tpg, last in leaders:
        if name == me or pos == my_pos or name in played:
            continue
        return f"x{pos}_{'new' if last >= last_team_week else 'cont'}"
    return None


def cross_samples(seasons: dict) -> list[dict]:
    """Points for `measure`: tier = cross_case, None when every target
    leader played; skipped when anyone is out at the player's own
    position (that is `samples`' question)."""
    from .form import compute_form
    from .models import GameLog
    out = []
    for season, rows in sorted(seasons.items()):
        games, team_weeks = _games_from_stats(rows)
        for team, weeks in team_weeks.items():
            for wk in sorted(weeks):
                if wk < FIRST_WEEK:
                    continue
                last = max((w for w in weeks if w < wk), default=0)
                played = {name for (t, _p, name), g in games.items() if t == team and wk in g}
                leaders = target_leaders(games, team, wk)
                for pos in GROUPS:
                    order = ranked(games, team, pos, wk)
                    if any(o[0] not in played for o in order):
                        continue                      # someone out at his own position
                    for name, _v, _n, _l in order:
                        g = games[(team, pos, name)]
                        if wk not in g:
                            continue
                        case = cross_case(leaders, name, pos, played, last)
                        prev = [g[w] for w in sorted(g) if w < wk]
                        for m, cols, floor in CROSS_MARKETS[pos]:
                            vals = [sum(_f(p, c) for c in cols) for p in prev]
                            logs = [GameLog(week=len(vals) - j, opponent="", value=v)
                                    for j, v in enumerate(reversed(vals))]
                            e = compute_form(logs, sum(vals) / len(vals), None).mean
                            if e < floor or e <= 0:
                                continue
                            out.append({"season": season, "m": m, "g": pos, "e": e,
                                        "y": sum(_f(g[wk], c) for c in cols), "tier": case})
    return out
