"""Waivers for YOUR roster: who to pick up, what to bid, whom to drop.

Ethan, 2026-10-27: "make sure … the fantasy room is actually a useful tool
and doing what it's supposed to be". The league desk already listed this
week's best free agents (engine/fantasyweek.free_agents), but the best free
agent in the league is not the best pickup for a team: a fourth quarterback
adds nothing to a roster that starts one, and the twentieth-best receiver
is a starter for the team whose WR2 is on a bye. FantasyPros' waiver
assistant answers it for your roster, with a FAAB bid (docs/FANTASY.md).

WHAT A PICKUP IS WORTH HERE is what he adds to YOUR best legal lineup this
week, under your league's scoring and slots: the lineup is solved again with
him on the roster (`fantasy_lineup.lineup`, the same optimiser the desk's
lineup uses) and the gain is the difference. Who he would push out of the
lineup is named, and so is his season average, because a waiver claim
lasts longer than a week.

THE BID, where the league bids blind from a budget (FAAB). There is no
fitted answer to "how much": no league here has ever shared its bids with
us, and the guides disagree. What this does is a stated rule of thumb, in
the shape the guides agree on (4for4, Fantasy Index): a bid scales with what
he adds a week and how many weeks are left before the playoffs, a one-week
stream (a kicker, a defense) is worth a dollar, and nothing past a quarter
of what is left. The card says it is a rule of thumb.

THE DROP is the bench player worth least over the season (his season
average), never a starter in the best lineup, never one on injured reserve
(an IR slot costs no roster spot), and never the only player at a position
the league must start.

Standard library only. Pure: every input is handed in.
"""
from __future__ import annotations

from . import fantasy_lineup as FL

#: A pickup worth naming adds at least this to the best lineup.
MIN_GAIN = 0.5
#: How many free agents per position are tried (by this week's points).
TRY_PER_POS = 8
#: The bid's tiers, by what he adds this week: (at least, share of the
#: budget left at the low end, at the high end).
BID_TIERS = ((6.0, 0.15, 0.25), (3.0, 0.08, 0.15), (1.0, 0.02, 0.06), (0.0, 0.0, 0.01))
#: Positions a team streams a week at a time: a dollar, not a share.
STREAM = ("K", "DEF")
#: Weeks before the playoffs at which a bid stops shrinking.
FULL_WEEKS = 8
#: IR on every platform's roster, by name: costs no roster spot.
IR_STATUSES = {"IR", "INJURED RESERVE", "PUP"}


def _weeks_left(week: int | None, playoff_start: int | None) -> int | None:
    if not week or not playoff_start:
        return None
    return max(0, int(playoff_start) - int(week))


def bid(gain: float, position: str, budget_left: float | None, weeks_left: int | None) -> dict | None:
    """A FAAB bid range ``{low, high, of}`` in the league's dollars, or None
    where the league bids no budget. The rule of thumb in the docstring."""
    if budget_left is None:
        return None
    left = max(0.0, float(budget_left))
    if position in STREAM:
        return {"low": 0, "high": min(1, int(left)), "of": int(left), "rule": "stream"}
    lo_share, hi_share = next((lo, hi) for floor, lo, hi in BID_TIERS if gain >= floor)
    scale = 1.0 if weeks_left is None else min(1.0, max(0.25, weeks_left / FULL_WEEKS))
    low = int(round(left * lo_share * scale))
    high = int(round(left * hi_share * scale))
    return {"low": max(0, min(low, high)), "high": max(0, high), "of": int(left), "rule": "thumb"}


def drop_candidate(mine: list, best: dict, season_means: dict, slots: list, statuses: dict | None = None) -> dict | None:
    """The bench player worth least over the season, or None. Never a
    starter in ``best`` (the solved lineup), never one on IR, never the last
    player at a position a slot only he can fill."""
    started = {s.get("player") for s in (best or {}).get("starters") or [] if s.get("player")}
    by_pos: dict = {}
    for r in mine or []:
        by_pos.setdefault(r.get("position"), []).append(r)
    needs = {s for s in slots or [] if s in ("QB", "RB", "WR", "TE", "K", "DEF")}
    out = None
    for r in mine or []:
        name, pos = r.get("player"), r.get("position")
        if name in started:
            continue
        if str((statuses or {}).get(name) or "").upper() in IR_STATUSES:
            continue
        if pos in needs and len(by_pos.get(pos) or []) <= 1:
            continue
        ppg = float(((season_means or {}).get(name) or {}).get("fp_ppr") or 0.0)
        if out is None or ppg < out["ppg"]:
            out = {"player": name, "position": pos, "ppg": round(ppg, 1)}
    return out


def for_roster(mine: list, slots: list, scoring: dict, means: dict, week_doc: dict,
               rostered: list, *, season_means: dict | None = None, statuses: dict | None = None,
               budget_left: float | None = None, week: int | None = None,
               playoff_start: int | None = None, dst_scoring: dict | None = None,
               limit: int = 5) -> dict:
    """The pickups for this roster, best first: ``{pickups, drop, base}``.

    ``means`` are the desk's this-week means (fantasyweek.with_week);
    ``week_doc`` the week's file; ``rostered`` every name on every roster
    in the league. Each pickup: player, position, team, this week's points,
    the gain to the best lineup, whom he replaces, his season average, the
    bid."""
    from . import fantasyweek as FW
    if not mine or not week_doc:
        return {"pickups": [], "drop": None, "base": None}
    base = FL.lineup(mine, slots, scoring, means)
    base_total = float(base.get("total") or 0.0)
    started = {s.get("player"): s for s in base.get("starters") or [] if s.get("player")}
    idx = FW.index(week_doc)
    fa = FW.free_agents(week_doc, rostered, limit_per_pos=TRY_PER_POS)
    weeks_left = _weeks_left(week, playoff_start)
    found = []
    for pos, rows in fa.items():
        for r in rows:
            name = r.get("player")
            full = idx.get(_key(name)) or r
            if pos == "DEF":
                from . import dstproj
                full = dstproj.with_scoring(full, dst_scoring)
            trial = dict(means)
            trial[name] = FW.week_entry(full, {"position": pos})
            after = FL.lineup(list(mine) + [{"player": name, "position": pos}], slots, scoring, trial)
            gain = round(float(after.get("total") or 0.0) - base_total, 2)
            if gain < MIN_GAIN:
                continue
            now = {s.get("player") for s in after.get("starters") or [] if s.get("player")}
            out_of = sorted((p for p in started if p not in now),
                            key=lambda p: float(started[p].get("points") or 0))
            found.append({
                "player": name, "position": pos, "team": r.get("team"), "opponent": r.get("opponent"),
                "expected": full.get("expected", r.get("expected")), "gain": gain,
                "replaces": out_of[0] if out_of else None,
                "season_ppg": round(float(((season_means or {}).get(name) or {}).get("fp_ppr") or 0.0), 1) or None,
                "bid": bid(gain, pos, budget_left, weeks_left),
                "card": r.get("card"),
            })
    found.sort(key=lambda p: -p["gain"])
    drop = drop_candidate(mine, base, season_means or {}, slots, statuses)
    # A STREAM REPLACES, it does not add: a defense or a kicker picked up
    # for this week goes in for the one he starts over, and that one is the
    # drop. Anyone else costs the roster's least valuable bench spot.
    for f in found:
        if f["position"] in STREAM and f.get("replaces"):
            f["drop"] = {"player": f["replaces"], "position": f["position"], "ppg": None, "why": "stream"}
        else:
            f["drop"] = drop
    return {"pickups": found[:limit], "drop": drop,
            "base": round(base_total, 2), "weeks_left": weeks_left,
            "faab": None if budget_left is None else {"left": int(max(0.0, float(budget_left)))}}


def _key(name) -> str:
    from .backtest import _norm
    return _norm(name or "")
