"""The matchup card under a hockey pick, in the shape every league's takes.

Ethan, 2026-10-14: "make sure all sports have the same most likely screens
with same type of info and info is being used how it should be." The NFL,
college and NBA picks each carried a card saying what tonight's opponent
gives up — per game, against the league, where that ranks — and what the
model did with it. A hockey pick had none, though the model reads exactly
that (engine/nhl/model.opp_factor) off the team profiles it builds.

WHAT IT SAYS. A skater's shots on goal: the shots tonight's opponent allows
a game. His goals, assists, points or anytime goal: the goals it allows a
game. His blocked shots: the shots it takes a game. A goalie's saves: the
shots tonight's opponent takes a game. Each beside the league's rate and
its rank among the clubs (1st allows, or takes, the most), off the same
decay-weighted team profiles the projection reads (engine/nhl/model.
team_profiles) — last season's while this one has under SEASON_MIN_GAMES.

WHAT THE MODEL DID, said under it: how far its opponent factor moved this
projection, and that the factor is a written prior (shrunk toward the
league, capped at ±OPP_CAP), not a measured transfer — the hockey model's
own docstring says nothing in it is fitted to a backtest.

Standard library only.
"""

from __future__ import annotations

from . import model as M

#: market → (the profile number, the words on the card)
MARKETS = {"sog": ("sog_against", "shots allowed"), "blocks": ("sog_for", "shots taken"),
           "goals": ("ga", "goals allowed"), "assists": ("ga", "goals allowed"),
           "points": ("ga", "goals allowed"), "anytime_goal": ("ga", "goals allowed"),
           "saves": ("sog_for", "shots taken")}
#: Fewer games than this this season and the profile is mostly last season's.
SEASON_MIN_GAMES = 3


def note(market: str, opponent: str, teams: dict, proj: dict | None) -> str:
    """What the projection did with tonight's opponent."""
    p = proj or {}
    if market == "saves":
        mult = M.opp_factor(teams, opponent, "sog_for")
        what = "their shot volume moves his shots against"
    else:
        mult = float(p.get("opp") or 1.0) / float(p.get("pp_factor") or 1.0)
        what = ("the chances they allow at five-on-five and their starter against chances move it"
                if p.get("shot_model") == "xg" and market in ("goals", "anytime_goal", "points", "assists")
                else "their shots allowed and their starter's save rate move it"
                if market in ("goals", "anytime_goal", "points", "assists")
                else "their shot volume moves it" if market == "blocks"
                else "their shots allowed moves it")
    pct = round((mult - 1) * 100)
    moved = f"{'+' if pct > 0 else ''}{pct}%" if pct else "not at all"
    return (f"Read into the projection: {what} {moved} — a written prior, shrunk toward the league and "
            f"capped at ±{M.OPP_CAP:.0%}, not a measured transfer.")


def card(market: str, opponent: str, teams: dict, proj: dict | None = None) -> dict | None:
    """The card for one pick, or None without a number for this market or
    this club."""
    if market not in MARKETS or not opponent:
        return None
    key, words = MARKETS[market]
    pool = {t: v[key] for t, v in (teams or {}).items() if isinstance(v, dict) and v.get(key) is not None}
    if opponent not in pool:
        return None
    order = sorted(pool, key=lambda t: -pool[t])
    league = sum(pool.values()) / len(pool)
    t = teams[opponent]
    gp = int(t.get("gp_season") or 0)
    last = gp < SEASON_MIN_GAMES
    games = gp if gp else int(t.get("n") or 0)
    per = pool[opponent]
    out = {"opponent": opponent, "stat": words, "per_game": round(per, 1), "league": round(league, 1),
           "rank": order.index(opponent) + 1, "of": len(order), "games": games,
           "text": (f"{opponent}: {per:.1f} {words} a game, the {order.index(opponent) + 1}"
                    f"{_suffix(order.index(opponent) + 1)}-most of {len(order)} (league {league:.1f})"),
           "note": note(market, opponent, teams, proj)}
    if last:
        out["last_season"] = True
    return out


def _suffix(n: int) -> str:
    return "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
