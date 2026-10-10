"""When a WNBA/NBA player sits, whose usage inherits her share?

WNBA_MODEL §6: "Injury ripple — minutes redistribution is modelled;
on/off usage inheritance 📋".

The hoops twin of `engine/redistribute.py`, and it follows the same three
rules for the same reasons:

SHARE, NOT VOLUME. A teammate's raw points rise in a 90-possession game
and fall in a 74-possession one, and neither has anything to do with who
was absent. The measure is her share of the TEAM's total that night, so
pace cancels the way game script cancels in the NFL version.

ABSENCE IS READ FROM THE STATS, not from an injury report. A report says
who was listed; the box score says who did not play, and only the second
is what an inheritance is about.

THE ABSENCE SAMPLE IS TINY AND MUST SAY SO. `MIN_OUT_GAMES` is the floor,
and below it the report prints the shape and says outright that it is not
evidence — a six-point share move over two games is one hot quarter.

EVIDENCE ONLY. Nothing prices from this: replacing the minutes model's
redistribution with measured inheritance is a pricing change, and the
claimed edge measures AUC 0.479 (docs/THE_INFORMATION_TEST.md).
"""

from __future__ import annotations

#: Same floors as the NFL version, same reasons.
MIN_OUT_GAMES = 3
MIN_BOTH = 2

#: The stats a share can be computed over. `pts` is the usage proxy the
#: §6 row asks about; `min` is the floor-time inheritance.
STATS = ("pts", "min", "reb", "ast", "fg3m")


def team_games(rows, team: str) -> dict:
    """`{date: {player: {stat: value}}}` for one team's logs."""
    out: dict = {}
    for r in rows:
        if str(r.get("team") or "").upper() != team:
            continue
        stat = r.get("market")
        if stat not in STATS:
            continue
        d = str(r.get("period") or "")
        p = str(r.get("player") or "")
        if not d or not p:
            continue
        try:
            v = float(r.get("value") or 0)
        except (TypeError, ValueError):
            continue
        out.setdefault(d, {}).setdefault(p, {})[stat] = v
    return out


def shares(game: dict, stat: str) -> dict:
    """`{player: share of the team's `stat` that night}`."""
    tot = sum(p.get(stat, 0.0) for p in game.values())
    if tot <= 0:
        return {}
    return {name: p.get(stat, 0.0) / tot for name, p in game.items()}


def inheritance(rows, team: str, player: str, stat: str = "pts") -> dict:
    """Teammates' share of `stat` in the games `player` sat, vs played.

    Played = she recorded MINUTES that night, whatever the target stat —
    a scoreless game is still a played game, and judging presence by the
    stat being shared would call a 0-point night an absence.
    """
    games = team_games(rows, team)
    played, missed = [], []
    for d in sorted(games):
        g = games[d]
        s = shares(g, stat)
        if not s:
            continue
        on = g.get(player, {}).get("min", 0.0) > 0 or \
            g.get(player, {}).get(stat, 0.0) > 0
        (played if on else missed).append(s)

    who: dict = {}
    for name in {n for s in played + missed for n in s}:
        if name == player:
            continue
        a = [s[name] for s in played if name in s]
        b = [s[name] for s in missed if name in s]
        if len(a) < MIN_BOTH or len(b) < MIN_BOTH:
            continue
        w, wo = sum(a) / len(a), sum(b) / len(b)
        who[name] = {"with": round(w, 4), "without": round(wo, 4),
                     "delta": round(wo - w, 4),
                     "n_with": len(a), "n_without": len(b)}
    return {
        "team": team, "player": player, "stat": stat,
        "n_played": len(played), "n_out": len(missed),
        "enough": len(missed) >= MIN_OUT_GAMES,
        "beneficiaries": dict(sorted(who.items(),
                                     key=lambda kv: -kv[1]["delta"])),
    }


def report(res: dict, limit: int = 6) -> str:
    lines = ["", "=" * 70,
             f"  WHO INHERITS {res['player'].upper()}'S "
             f"{res['stat'].upper()} SHARE WHEN SHE SITS", "=" * 70,
             f"  {res['team']} · {res['n_played']} game(s) with her, "
             f"{res['n_out']} without"]
    if not res["enough"]:
        lines += ["",
                  f"  NOT ENOUGH GAMES — {res['n_out']} missed, floor is "
                  f"{MIN_OUT_GAMES}. The shape below is printed and it is "
                  f"not evidence:",
                  "  a six-point share move over two games is one hot "
                  "quarter."]
    if not res["beneficiaries"]:
        lines += ["", "  No teammate appears in enough games on both sides "
                      "to compare.", ""]
        return "\n".join(lines)
    lines += ["", f"  {'teammate':<24} {'with':>7} {'without':>8} "
                  f"{'delta':>7}   games"]
    for name, v in list(res["beneficiaries"].items())[:limit]:
        lines.append(f"  {name[:24]:<24} {v['with']:>6.1%} "
                     f"{v['without']:>8.1%} {v['delta']:>+7.1%}   "
                     f"{v['n_with']}/{v['n_without']}")
    lines += ["",
              "  Share of the team's total, not raw volume — pace cancels.",
              "  Evidence only; the minutes model still owns redistribution.",
              ""]
    return "\n".join(lines)
