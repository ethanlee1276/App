"""The league you are actually in, and the team you are actually playing.

IDEAS #7. The League Desk already reads a Sleeper league — your roster,
your rivals', the optimal lineup, the trades — and answers every question
as though you were playing the field. You are not. You are playing one
specific team this week, and that changes the answer.

WHY A MEAN IS NOT ENOUGH, and it is the whole reason this module exists
rather than a sort on the lineup card. Two flex plays projected at 11.0
are the same start until you know that one has never scored under 8 and
the other alternates 2 and 20. Which one you want depends entirely on
the scoreboard: four points down with one player left you need the
20, four points up you need the 8. The optimiser cannot see that,
because it is maximising a total against nobody.

So the unit here is the MARGIN, not the total: your starters' points
minus theirs, with a spread around it measured from both sides' own
week-to-week scoring (`fantasy_lineup.per_game` now carries `_sd`). Win
probability is that margin read against zero.

THE TWO ASSUMPTIONS, said out loud because they are the only things here
that are not counted:

  * A NORMAL MARGIN. Individual weekly scores are right-skewed; a sum of
    nine starters is close enough to symmetric that the central limit
    theorem carries it, and this is the standard approximation. It will
    be worst in the tail of a lineup with one enormous long-shot leg.
  * INDEPENDENCE between the two lineups. When your quarterback is
    throwing to their receiver the two totals are correlated, and that
    narrows the real spread. We do not measure game-level fantasy
    correlation, so we do not pretend to: the number is flagged, not
    fudged. `engine/parlays.py` is where correlation IS measured, and it
    is measured, not assumed, which is the bar this would have to clear.

WHAT FALLS OUT FOR FREE is the part worth reading. Ranking bench swaps by
their effect on WIN PROBABILITY rather than on points reproduces the
advice every fantasy column gives — favourites want floors, underdogs
want ceilings — without anybody writing that rule down. A swap that
costs half a point but halves your variance is correct at +9 and wrong
at −9, and the arithmetic says which without being told.

Standard library, no I/O: the caller hands in what Sleeper returned.
"""

from __future__ import annotations

import math

from .fantasy_lineup import _eligible, assign, league_points, starting_slots

#: A margin this far inside a rounding error is a coin flip, and saying
#: "51%" about it implies a precision the inputs do not have.
COINFLIP = 0.5

#: Below this the spread is unusable and the module answers with a margin
#: and no probability — see `head_to_head`.
MIN_SD = 1.0


def _phi(z: float) -> float:
    """The standard normal CDF, from the stdlib's error function."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def opponent_roster_id(matchups, roster_id) -> int | None:
    """Whose roster you are playing this week, from Sleeper's own board.

    ``matchups`` is ``league/{id}/matchups/{week}``: one row per roster
    carrying a shared ``matchup_id``. A bye week, a league that has not
    scheduled yet, or a roster id that is not in the list all answer
    None rather than picking somebody at random.
    """
    try:
        rid = int(roster_id)
    except (TypeError, ValueError):
        return None
    mine = None
    for m in matchups or []:
        if int(m.get("roster_id") or -1) == rid:
            mine = m.get("matchup_id")
            break
    if mine is None:
        return None
    for m in matchups or []:
        if (m.get("matchup_id") == mine
                and int(m.get("roster_id") or -1) != rid):
            return int(m["roster_id"])
    return None


def _pts(settings: dict, key: str) -> float:
    """Sleeper splits a team's points across two fields — `fpts` and
    `fpts_decimal` — and reading only the first loses the tenths that
    decide half the leagues in the country."""
    whole = float((settings or {}).get(key) or 0)
    frac = float((settings or {}).get(f"{key}_decimal") or 0)
    return round(whole + frac / 100.0, 2)


def standings(rosters, owners=None) -> list[dict]:
    """The table, straight off the league. Facts only — nothing modelled.

    Sorted the way a league sorts: wins, then points for, which is the
    default tiebreak in every Sleeper league and the one people argue
    about in the others.
    """
    owners = owners or {}
    out = []
    for r in rosters or []:
        st = r.get("settings") or {}
        rid = r.get("roster_id")
        out.append({
            "roster_id": int(rid) if rid is not None else None,
            "owner_id": str(r.get("owner_id") or ""),
            "team": owners.get(str(r.get("owner_id") or ""))
                    or f"Team {rid}",
            "wins": int(st.get("wins") or 0),
            "losses": int(st.get("losses") or 0),
            "ties": int(st.get("ties") or 0),
            "points_for": _pts(st, "fpts"),
            "points_against": _pts(st, "fpts_against"),
        })
    out.sort(key=lambda t: (-t["wins"], -t["points_for"]))
    for i, t in enumerate(out, 1):
        t["rank"] = i
    return out


def team_total(roster_rows, slots, scoring: dict, means: dict) -> dict:
    """One team's optimal starting lineup: its points and its spread.

    The spread is the root of the summed variances, because that is what
    a sum of independent weekly scores has. A starter we have no spread
    for contributes his points and no variance, which understates the
    swing — flagged in ``unmeasured`` rather than filled in.
    """
    rows = []
    for r in roster_rows or []:
        name = r.get("player")
        m = (means or {}).get(name) or {}
        pos = (r.get("position") or m.get("position") or "").upper()
        scored = league_points({**m, "position": pos}, scoring)
        sd = m.get("_sd")
        # THE LEAGUE'S SCALE, NOT PPR'S. `_sd` is measured on PPR points;
        # a league that pays half a point per reception scores this
        # player lower, and his week-to-week swing scales with him.
        # First-order and said so: the shape of his distribution is
        # assumed unchanged, only its size.
        base = float(scored.get("base_ppr") or 0.0)
        if sd is not None and base > 0:
            sd = float(sd) * (float(scored["points"]) / base)
        rows.append({
            "player": name, "position": pos,
            "points": scored["points"], "sd": None if sd is None else round(sd, 2),
            "sd_basis": m.get("_sd_basis") or "none",
        })
    seated = assign(rows, list(slots or []))
    starters = [dict(seated[i], slot=s) for i, s in enumerate(slots or [])
                if i in seated]
    started = {p["player"] for p in seated.values()}
    bench = sorted((r for r in rows if r["player"] not in started),
                   key=lambda r: -r["points"])
    points = round(sum(float(p["points"] or 0) for p in starters), 2)
    var = sum(float(p["sd"] or 0) ** 2 for p in starters)
    unmeasured = [p["player"] for p in starters if not p.get("sd")]
    return {"points": points, "sd": round(var ** 0.5, 2), "variance": var,
            "starters": starters, "bench": bench, "unmeasured": unmeasured}


def win_probability(margin: float, sd: float) -> float | None:
    """P(the margin lands above zero). None when the spread is unusable."""
    if sd is None or sd < MIN_SD:
        return None
    return round(_phi(float(margin) / float(sd)), 4)


def head_to_head(mine, theirs, roster_positions, scoring: dict,
                 means: dict) -> dict:
    """This week's game: both optimal lineups, the margin, the odds.

    ``theirs`` None — a bye, or an unscheduled league — returns your side
    alone with ``opponent: None``, because half a matchup is still worth
    seeing and inventing the other half is not.
    """
    slots = starting_slots(roster_positions)
    me = team_total(mine, slots, scoring, means)
    if not theirs:
        return {"me": me, "them": None, "margin": None, "win_prob": None,
                "slots": slots}
    them = team_total(theirs, slots, scoring, means)
    margin = round(me["points"] - them["points"], 2)
    sd = round((me["variance"] + them["variance"]) ** 0.5, 2)
    return {
        "me": me, "them": them, "slots": slots,
        "margin": margin, "sd": sd,
        "win_prob": win_probability(margin, sd),
        "coinflip": abs(margin) <= COINFLIP,
        # Every starter on either side whose swing we could not measure.
        # A margin built on these is a mean with no spread under it.
        "unmeasured": sorted(set(me["unmeasured"]) | set(them["unmeasured"])),
    }


def swings(h2h: dict, limit: int = 5) -> list[dict]:
    """Bench decisions ranked by what they do to WIN PROBABILITY.

    This is the head-to-head answer and it is not the lineup card's.
    The optimiser maximises points; against a specific opponent the
    right play is whichever start makes you likeliest to win, and those
    differ exactly when variance matters — which is to say whenever the
    game is not close. A swap that costs half a point and halves your
    swing is correct at +9 and wrong at −9, and nothing here had to be
    told that.

    Only swaps that BEAT the seated lineup on win probability are
    returned: an optimiser's own starter is the baseline, so a list that
    included the losers would be a list of things not to do.
    """
    me, them = h2h.get("me") or {}, h2h.get("them") or {}
    if not them or h2h.get("win_prob") is None:
        return []
    base_p = float(h2h["win_prob"])
    their_var = float(them.get("variance") or 0.0)
    out = []
    for s in me.get("starters") or []:
        if not s.get("player"):
            continue
        for b in me.get("bench") or []:
            if not _eligible(s.get("slot") or "", b.get("position") or ""):
                continue
            d_pts = float(b["points"] or 0) - float(s["points"] or 0)
            d_var = (float(b["sd"] or 0) ** 2) - (float(s["sd"] or 0) ** 2)
            var = max(0.0, float(me.get("variance") or 0.0) + d_var) + their_var
            p = win_probability(float(h2h["margin"]) + d_pts, var ** 0.5)
            if p is None or p <= base_p:
                continue
            out.append({
                "start": b["player"], "sit": s["player"], "slot": s["slot"],
                "points": round(d_pts, 2),
                "win_prob": p, "gain": round(p - base_p, 4),
                # The reason, in the vocabulary a reader already has.
                "why": ("more ceiling, and you need it" if d_var > 0
                        else "safer, and you are ahead"),
            })
    out.sort(key=lambda r: -r["gain"])
    return out[:limit]
