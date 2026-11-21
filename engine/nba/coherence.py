"""The two accounting identities a hoops prop menu must satisfy — §1.3.

The football and baseball boards devig their longshot menus with the
market-sum method. Basketball has no distinct-scorer market, but the
script hands it "something better: two accounting identities the book's
menu must satisfy, and frequently doesn't":

THE POINTS-SUM CHECK. A WNBA rotation is short enough that the listed
players on a points menu carry ~90-95% of team scoring. Invert each
listed line and its juice into an implied projection, sum them, and
compare against the team total the game line implies. When they
diverge, one side is wrong — and the team total is the sharper market,
so it's the props.

THE 200-MINUTE CHECK. Every team plays exactly 200 player-minutes.
Divide each listed player's implied points by her own measured
points-per-minute and the menu confesses its implied minutes. When news
breaks, books race to move the obvious names and the updated menu's
minutes routinely sum short — the missing minutes are real, they will
be played, and they are sitting unpriced on whoever didn't move.

Both are published as a per-team audit rather than silently consumed:
a diagnosis a reader can check beats a multiplier nobody can see.

Standard library only.
"""

from __future__ import annotations

from statistics import NormalDist

from .prob import devig, sd_for
from ..hoops import LeagueTuning, NBA

#: §1.3 — the listed players' typical share of team scoring, the middle
#: of the script's 90-95% band.
LISTED_COVERAGE = 0.925
#: A points-sum gap under this many points is menu noise, not a signal.
POINTS_GAP = 6.0
#: The share of 200 minutes the listed players typically hold, and the
#: shortfall (in minutes) that flags a menu as underpriced.
MINUTES_COVERAGE = 0.80
MINUTES_SHORT = 8.0
#: Fewer listed players than this and neither identity has the coverage
#: to say anything.
MIN_LISTED = 5

_ND = NormalDist()


def team_totals(total, spread) -> tuple[float, float] | None:
    """§1.1: ``(favorite total, underdog total)`` from the game line."""
    try:
        t, s = float(total), abs(float(spread))
    except (TypeError, ValueError):
        return None
    if t <= 0:
        return None
    return (t + s) / 2.0, (t - s) / 2.0


def implied_projection(line, over_odds, under_odds, stat: str = "pts",
                       tune: LeagueTuning = NBA) -> float | None:
    """The projection a two-way price is really stating.

    Devig the pair, then invert the same normal the model prices with:
    a -130/+100 pair on 18.5 is not saying 18.5, it is saying ~19.3,
    and the juice is where the statement lives.
    """
    try:
        line = float(line)
        p_over, _ = devig(int(over_odds), int(under_odds))
    except (TypeError, ValueError):
        return None
    p_over = max(0.02, min(0.98, p_over))
    return line + _ND.inv_cdf(p_over) * sd_for(stat, max(line, 1.0), tune)


def points_sum_check(rows: list[dict], team_total,
                     tune: LeagueTuning = NBA) -> dict | None:
    """One team's menu against its own team total.

    ``rows`` are pts-market entries: ``{player, line, over_odds,
    under_odds}``. Returns the audit dict, or None when the menu is too
    thin to speak.
    """
    try:
        tt = float(team_total)
    except (TypeError, ValueError):
        return None
    if tt <= 0 or len(rows) < MIN_LISTED:
        return None
    implied = []
    for r in rows:
        got = implied_projection(r.get("line"), r.get("over_odds"),
                                 r.get("under_odds"), "pts", tune)
        if got is not None:
            implied.append((r.get("player", ""), got))
    if len(implied) < MIN_LISTED:
        return None
    menu = sum(p for _, p in implied)
    expected = tt * LISTED_COVERAGE
    gap = menu - expected
    verdict = None
    if abs(gap) >= POINTS_GAP:
        # The team total is the sharper market — the MENU is the side
        # that's wrong, and the sign says which way.
        verdict = ("menu prices MORE scoring than the team total supports "
                   "— the listed overs are collectively taxed"
                   if gap > 0 else
                   "menu prices LESS scoring than the team total supports "
                   "— the listed lines are collectively cheap")
    return {"listed": len(implied), "menu_pts": round(menu, 1),
            "team_total": round(tt, 1), "expected_pts": round(expected, 1),
            "gap": round(gap, 1), "verdict": verdict}


def minutes_sum_check(rows: list[dict],
                      tune: LeagueTuning = NBA) -> dict | None:
    """The 200-minute audit: the menu's implied minutes, summed.

    ``rows`` add ``rate`` (the player's own measured points per minute)
    and optionally ``recent_min`` (her recent minutes norm). The output
    names the players whose implied minutes sit furthest under their
    norm — after injury news, that's where the unpriced production is.
    """
    if len(rows) < MIN_LISTED:
        return None
    implied = []
    for r in rows:
        rate = r.get("rate")
        if not rate or rate <= 0:
            continue
        proj = implied_projection(r.get("line"), r.get("over_odds"),
                                  r.get("under_odds"), "pts", tune)
        if proj is None:
            continue
        mins = proj / rate
        implied.append({"player": r.get("player", ""),
                        "implied_min": round(mins, 1),
                        "recent_min": r.get("recent_min"),
                        "short_by": (round(r["recent_min"] - mins, 1)
                                     if r.get("recent_min") else None)})
    if len(implied) < MIN_LISTED:
        return None
    total = sum(x["implied_min"] for x in implied)
    expected = 200.0 * MINUTES_COVERAGE
    missing = expected - total
    unmoved = sorted((x for x in implied
                      if x["short_by"] and x["short_by"] > 2.0),
                     key=lambda x: -x["short_by"])[:3]
    return {"listed": len(implied), "implied_minutes": round(total, 1),
            "expected_minutes": round(expected, 1),
            "missing_minutes": round(missing, 1) if missing > 0 else 0.0,
            "flag": missing >= MINUTES_SHORT,
            "unmoved": [x["player"] for x in unmoved],
            "detail": implied}


def menu_audit(props: list[dict], games: list[dict],
               tune: LeagueTuning = NBA) -> list[dict]:
    """Both checks, per team, from the build's own prop rows.

    ``props`` are the pipeline's prop dicts (pts rows are used);
    ``games`` carry home/away/total/spread. Teams whose menus are too
    thin are simply absent — an audit that can't measure says nothing.
    """
    by_team: dict[str, list[dict]] = {}
    for p in props:
        if p.get("market") != "pts":
            continue
        minutes = [m for m in (p.get("minutes") or []) if m > 0]
        values = p.get("values") or []
        pairs = [(m, v) for m, v in zip(p.get("minutes") or [], values)
                 if m > 0]
        rate = (sum(v for _, v in pairs) / sum(m for m, _ in pairs)
                if pairs and sum(m for m, _ in pairs) > 0 else None)
        by_team.setdefault(p.get("team", ""), []).append({
            "player": p.get("player", ""), "line": p.get("line"),
            "over_odds": p.get("over_odds"), "under_odds": p.get("under_odds"),
            "rate": rate,
            "recent_min": (sum(minutes[:5]) / min(5, len(minutes))
                           if minutes else None)})
    out: list[dict] = []
    for g in games:
        total, spread = g.get("total"), g.get("spread")
        tt = team_totals(total, spread)
        for team, is_fav in ((g.get("home", ""), (spread or 0) < 0),
                             (g.get("away", ""), (spread or 0) > 0)):
            rows = by_team.get(team)
            if not rows:
                continue
            team_tt = None
            if tt:
                team_tt = tt[0] if is_fav else tt[1]
            pts = points_sum_check(rows, team_tt, tune)
            mins = minutes_sum_check(rows, tune)
            if not pts and not mins:
                continue
            out.append({"team": team, "opponent": (g.get("away", "")
                                                   if team == g.get("home")
                                                   else g.get("home", "")),
                        "points_sum": pts, "minutes_sum": mins})
    return out
