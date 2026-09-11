"""When a player is out, where does his usage actually go?

NFL_MODEL §7's injury ripple, and the half that was never built:

    | §7 Injury ripple | 🟡 | … full redistribution model 📋 |

What exists today is `engine/injuries.py`, and it is worth being exact
about what that is: a table of INVENTED multipliers. Opponent's CB1 out
multiplies a receiving projection by 1.09. Interior DT out, 1.06. Own left
tackle out, 0.95. Nobody measured those numbers — they are plausible, they
are round, and they are the same for every team and every player.

A redistribution model is the opposite claim: not "receivers do about 9%
better", but "when THIS player misses, THESE teammates absorb his targets,
by this much, over this many games." That is answerable from the weekly
stats already on disk. It is a comparison of the same teammates in the
games he played against the games he missed.

TWO THINGS MAKE THIS HONEST AND BOTH ARE EASY TO SKIP.

**Share, not volume.** A teammate's raw targets rise in a game the team
threw 45 times and fall in one it threw 22, and neither has anything to do
with who was absent. The measure is share of the team's targets, so game
script cancels.

**The absence sample is tiny and must say so.** A player who missed three
games gives a three-game sample; the difference between 18% and 24% target
share over three games is nothing at all. Every row carries `n_out`, and
`MIN_OUT_GAMES` is the floor below which the answer is "not enough games",
which is the true answer for most players in most seasons.

NOTHING HERE PRICES ANYTHING. It measures. Replacing `injuries.py`'s 1.09
with a measured share is a PRICING change, and `docs/THE_INFORMATION_TEST.md`
is why it waits — the claimed edge measures AUC 0.479, so a new input into
the grade is the exact move that finding rules out until something moves
that number. What this closes is that we had never looked.
"""

from __future__ import annotations

#: Below this many missed games the honest answer is "cannot say". Three
#: is not a power calculation — it is the point below which a difference
#: in share is a rounding artefact of one busy afternoon.
MIN_OUT_GAMES = 3
#: A teammate needs this many games in BOTH states to be compared at all.
MIN_BOTH = 2

#: Which weekly-stats column carries each usage kind, with the fallbacks
#: nflverse's schema has used over the years.
USAGE = {
    "targets": ("targets", "tgt"),
    "carries": ("carries", "rushing_attempts", "rush_att"),
}


def _f(row, keys) -> float:
    for k in keys:
        v = row.get(k)
        if v not in (None, "", "NA"):
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return 0.0


def _name(row) -> str:
    for k in ("player_display_name", "player_name", "player"):
        v = row.get(k)
        if v:
            return str(v)
    return ""


def _week(row):
    try:
        return int(float(row.get("week")))
    except (TypeError, ValueError):
        return None


def team_weeks(rows, team: str) -> dict:
    """`{week: [row, ...]}` for one team's players, regular season only."""
    out: dict = {}
    for r in rows:
        if str(r.get("recent_team") or r.get("team") or "").upper() != team:
            continue
        if str(r.get("season_type") or "REG").upper() not in ("REG", ""):
            continue
        w = _week(r)
        if w is None:
            continue
        out.setdefault(w, []).append(r)
    return out


def shares(week_rows, kind: str) -> dict:
    """`{player: share of the team's targets/carries}` for one week."""
    keys = USAGE[kind]
    tot = sum(_f(r, keys) for r in week_rows)
    if tot <= 0:
        return {}
    return {_name(r): _f(r, keys) / tot for r in week_rows if _name(r)}


def redistribution(rows, team: str, player: str, kind: str = "targets"
                   ) -> dict:
    """How teammates' usage share changed in the weeks `player` was absent.

    Absence is read from the stats themselves — a week where the team
    played and this player has no row, or a row with no usage at all. That
    is deliberately not an injury report: a report says who was listed,
    the stats say who actually did not play, and only the second is what a
    redistribution is about.
    """
    weeks = team_weeks(rows, team)
    played, missed = [], []
    for w, wk in sorted(weeks.items()):
        s = shares(wk, kind)
        if not s:
            continue
        (played if s.get(player, 0.0) > 0 else missed).append(s)

    who = {}
    for name in {n for s in played + missed for n in s}:
        if name == player:
            continue
        a = [s[name] for s in played if name in s]
        b = [s[name] for s in missed if name in s]
        if len(a) < MIN_BOTH or len(b) < MIN_BOTH:
            continue
        with_, without = sum(a) / len(a), sum(b) / len(b)
        who[name] = {
            "with": round(with_, 4),
            "without": round(without, 4),
            "delta": round(without - with_, 4),
            "n_with": len(a), "n_without": len(b),
        }
    return {
        "team": team, "player": player, "kind": kind,
        "n_played": len(played), "n_out": len(missed),
        # THE GUARD, not a decoration. Below the floor every delta below is
        # noise, and a caller that reads the deltas without reading this
        # is reading a three-game accident as a role change.
        "enough": len(missed) >= MIN_OUT_GAMES,
        "beneficiaries": dict(sorted(who.items(),
                                     key=lambda kv: -kv[1]["delta"])),
    }


def report(res: dict, limit: int = 6) -> str:
    lines = ["", "=" * 70,
             f"  WHERE {res['player'].upper()}'S {res['kind'].upper()} GO "
             f"WHEN HE IS OUT", "=" * 70,
             f"  {res['team']} · {res['n_played']} game(s) with him, "
             f"{res['n_out']} without"]
    if not res["enough"]:
        lines += [
            "",
            f"  NOT ENOUGH GAMES — {res['n_out']} missed, and the floor is "
            f"{MIN_OUT_GAMES}.",
            "  The numbers below are printed so you can see the shape, and",
            "  they are not evidence of anything: a six-point move in share",
            "  over two games is one busy afternoon.",
        ]
    if not res["beneficiaries"]:
        lines += ["", "  No teammate appears in enough games on both sides "
                      "to compare.", ""]
        return "\n".join(lines)
    lines += ["", f"  {'teammate':<24} {'with':>7} {'without':>8} "
                  f"{'delta':>7}   games"]
    for name, v in list(res["beneficiaries"].items())[:limit]:
        lines.append(f"  {name[:24]:<24} {v['with']:>6.1%} {v['without']:>8.1%}"
                     f" {v['delta']:>+7.1%}   {v['n_with']}/{v['n_without']}")
    lines += [
        "",
        "  Share of the team's total, not raw volume: a teammate's targets",
        "  rise when the team throws 45 times and fall when it throws 22,",
        "  and neither has anything to do with who was absent.",
        "",
        "  Measurement only. engine/injuries.py still prices injuries with",
        "  invented multipliers (1.09 for a CB1, 1.06 for a DT); replacing",
        "  those with measured shares is a PRICING change — see",
        "  docs/THE_INFORMATION_TEST.md.",
        ""]
    return "\n".join(lines)
