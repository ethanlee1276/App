"""The draft, round by round, from YOUR seat — before it starts and while it runs.

Ethan, 2026-09-02: "add like a list for best draft orders of players or
something so users can see who they should draft in what round and shit
like that. We need a tool to help users in their draft while they are
doing it. Make sure we use all our data available."

Two things the draft kit did not answer, built from the same numbers:

WHO TO TAKE IN WHICH ROUND. The kit ranks by VORP and the pick-by-pick
advice says who will still be there at your NEXT pick. Neither says, in
advance, "your seat is 7 of 12: rounds one and two are backs, the third
is the last tier-two receiver, the tight end goes in five, the
quarterback in eight". That is the plan a person actually walks into a
room with, and it is a function of three things this repo already
holds: the board's value over replacement, the market's draft order
(the consensus ranks, which carry Sleeper's own board), and the seat's
pick numbers. For each of your picks the plan asks, of every player
still available, "how likely is he to survive until this pick" — the
same `fantasy_pick.survival` the live advice uses, with the room's
measured reach when there are picks to measure it from and the stated
prior when there are not — and takes the most valuable player who is
likely to be there, filling starting slots before bench, never a third
quarterback. Greedy, one round at a time, and it says so: a plan is a
list of intentions, and every row carries the fallback for when the
room disagrees.

A DRAFT ON ANY PLATFORM. The live advice reads Sleeper's pick feed;
ESPN, Yahoo, and the kitchen-table draft have no feed to read. So the
same function accepts the picks a person marks by hand — who is gone,
who is theirs — and returns the advice for the pick on the clock plus
the plan for every pick after it. Nothing here fetches; the server
hands in the board and ranks it already publishes.

WHAT THE DATA IS AND IS NOT. Projections are the kit's: last season's
expected points from volume, run forward. Rookies and anyone who missed
the year sit at the market's rank with the board's points at that rank
(`source="market"`), and every row that reaches the page says so. The
plan cannot see camp news, a Friday injury, or that seat 4 only drafts
his own team; the note on every response says that too.

Standard library only.
"""

from __future__ import annotations

import math

from .fantasy_pick import (DEFAULT_WINDOW, LIKELY, UNLIKELY, pick_numbers,
                           reach_window, survival, verdict)

#: Starting slots when a caller does not say. FLEX is a starter that
#: either a back or a receiver can fill, and it is counted as one.
DEFAULT_SLOTS = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1}

#: The most of one position a plan will draft. A third quarterback or
#: tight end is a roster spot that never starts; a seventh back is a
#: lottery ticket the waiver wire sells for free.
MAX_AT_POSITION = {"QB": 2, "RB": 6, "WR": 6, "TE": 2}

#: How much a starting-slot need is worth beside VORP when the plan
#: chooses. In points per game — the unit VORP is in — so "he fills my
#: RB2" is worth about two points of value, not a veto.
NEED_BONUS = 2.0

#: Positions eligible for the flex slot.
FLEX_POSITIONS = ("RB", "WR", "TE")

#: A candidate this unlikely to be there is not a target for this pick;
#: he is a target for the pick before it.
MIN_TARGET_P = UNLIKELY

#: Below this a player is not a reach either — he is simply gone, and
#: naming him in every later round would be listing the first overall
#: pick as a "reach" in round nine. One in seven is the floor: a reach
#: is a bet you could defend, not a lottery ticket.
MIN_REACH_P = 0.15

#: Targets listed per pick, fallbacks per pick.
TARGETS_PER_PICK = 5
FALLBACKS_PER_PICK = 2


def _pos(r: dict) -> str:
    return str(r.get("position") or "").upper()


def _num(x, default=0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def others_before(pick_no: int, made: int, mine: list[int]) -> int:
    """How many picks that are NOT yours land between now and ``pick_no``.

    ``made`` picks have already happened. Between them and ``pick_no``
    every pick is somebody else's except your own earlier ones, which
    the plan has already spent."""
    if pick_no <= made:
        return 0
    own_between = sum(1 for p in mine if made < p < pick_no)
    return max(0, pick_no - 1 - made - own_between)


def starter_needs(counts: dict, slots: dict | None) -> dict:
    """``{position: starters still unfilled}`` with the flex handled.

    The flex counts against whichever flex-eligible position the roster
    is thinnest at, relative to its own starters, so a plan holding two
    backs and one receiver reads the flex as a receiver need."""
    slots = dict(slots or DEFAULT_SLOTS)
    flex = int(slots.pop("FLEX", 0) or 0)
    need: dict = {}
    for pos, want in slots.items():
        short = int(want) - int(counts.get(pos, 0))
        if short > 0:
            need[pos] = short
    for _ in range(flex):
        # Spare bodies beyond the fixed starters, per flex position.
        spare = {p: int(counts.get(p, 0)) - int(slots.get(p, 0))
                 for p in FLEX_POSITIONS}
        if any(v > 0 for v in spare.values()):
            continue                       # something already fills it
        # Nobody spare: the flex is a need at the thinnest position.
        pos = min(FLEX_POSITIONS, key=lambda p: (spare[p], p != "RB"))
        need[pos] = need.get(pos, 0) + 1
    return need


def score(c: dict, need: dict) -> float:
    """What a candidate is worth to THIS pick: his value over replacement
    (plus the starting-slot bonus) weighted by the chance he is there.

    Value alone chose the earliest still-plausible player every round —
    a plan made entirely of 40% shots. Weighting by survival trades a
    little value for a lot of certainty, which is what a person walking
    into a room wants a plan to do."""
    p = _num(c.get("survives"), 0.0)
    return (_num(c.get("vorp")) + (NEED_BONUS if need.get(c["position"]) else 0.0)) * p


def _choose(cands: list[dict], counts: dict, slots: dict | None) -> dict | None:
    """The plan's pick from the targets: expected value first, starting
    need second, position caps always."""
    need = starter_needs(counts, slots)
    best, best_score = None, None
    for c in cands:
        pos = c["position"]
        if counts.get(pos, 0) >= MAX_AT_POSITION.get(pos, 6):
            continue
        sc = score(c, need)
        if best is None or sc > best_score:
            best, best_score = c, sc
    return best


def build(board: list[dict], ranks: dict, teams: int, slot: int,
          rounds: int = 15, kind: str = "snake", slots: dict | None = None,
          taken=(), mine=(), picks: list | None = None,
          window: float | None = None) -> dict:
    """The plan for one seat, from wherever the draft stands.

    ``board`` rows carry ``key``, ``player``, ``position``, ``vorp``,
    ``proj``, ``tier`` (the kit's board, keyed). ``ranks`` is the
    consensus map ``{key: rank}`` — the draft order the room is expected
    to follow. ``taken`` are keys drafted by other seats, ``mine`` the
    keys you hold; ``picks`` (optional) are the normalised pick rows in
    order, used only to measure the room's reach.
    """
    teams, slot, rounds = int(teams), int(slot), int(rounds)
    my_picks = pick_numbers(slot, teams, rounds, kind)
    taken, mine = set(taken or ()), list(mine or ())
    mine_set = set(mine)
    made = len(taken) + len(mine_set)
    win = float(window) if window else (
        reach_window(picks, ranks) if picks else DEFAULT_WINDOW)

    by_key = {r.get("key"): r for r in board or [] if r.get("key")}
    counts: dict = {}
    for k in mine_set:
        pos = _pos(by_key.get(k) or {})
        if pos:
            counts[pos] = counts.get(pos, 0) + 1

    planned: list[str] = []
    rounds_out = []
    for pick_no in my_picks:
        if pick_no <= made:
            continue
        gone = taken | mine_set | set(planned)
        # The room's order, minus everyone gone: depth is the position in
        # THIS list, which is what survival is a function of.
        avail = [k for k in sorted((k for k in ranks if ranks[k] is not None),
                                   key=lambda k: ranks[k]) if k not in gone]
        depth = {k: i + 1 for i, k in enumerate(avail)}
        k_before = others_before(pick_no, made, my_picks)
        cands = []
        for key in avail:
            r = by_key.get(key)
            if not r:
                continue
            p = survival(depth[key], k_before, win)
            cands.append({
                "key": key, "player": r.get("player") or key.title(),
                "position": _pos(r), "team": r.get("team", ""),
                "vorp": r.get("vorp"), "proj": r.get("proj"),
                "tier": r.get("tier"), "bye": r.get("bye"),
                "rank": ranks.get(key), "depth": depth[key],
                "survives": round(p, 3), "verdict": verdict(p),
                "market": r.get("source") == "market",
            })
        need_now = starter_needs(counts, slots)
        likely = [c for c in cands if c["survives"] >= MIN_TARGET_P]
        likely.sort(key=lambda c: -score(c, need_now))
        choice = _choose(likely, counts, slots)
        targets = [c for c in likely if c is not choice][:TARGETS_PER_PICK]
        # The stretch: the most valuable toss-up — worth a look if the
        # room lets him fall, not the plan.
        stretch = max((c for c in likely if c["verdict"] == "toss-up"),
                      key=lambda c: _num(c.get("vorp")), default=None)
        # Players worth more than the pick who will probably not be
        # there: the reason to have taken them a round earlier. Not the
        # ones who are simply gone.
        reach = sorted((c for c in cands
                        if MIN_REACH_P < c["survives"] < MIN_TARGET_P
                        and choice is not None
                        and _num(c.get("vorp")) > _num(choice.get("vorp"))),
                       key=lambda c: -_num(c.get("vorp")))[:3]
        if choice:
            planned.append(choice["key"])
            counts[choice["position"]] = counts.get(choice["position"], 0) + 1
        rnd = (pick_no - 1) // teams + 1
        rounds_out.append({
            "round": rnd, "pick": pick_no, "others_before": k_before,
            "plan": choice,
            "targets": targets,
            "fallbacks": targets[:FALLBACKS_PER_PICK],
            "stretch": stretch if stretch is not choice else None,
            "reach": reach,
            "needs_before": need_now,
            "needs_after": starter_needs(counts, slots),
            "empty": choice is None,
        })

    return {
        "teams": teams, "slot": slot, "n_rounds": rounds, "type": kind,
        "picks_made": made, "my_picks": my_picks,
        "window": round(win, 2), "window_fitted": bool(picks) and len(picks or []) >= 8,
        "have": counts_before(mine_set, by_key),
        "rounds": rounds_out,
        "summary": summary(rounds_out, by_key, mine_set, slots),
        "note": ("A plan, not a promise: each round takes the most valuable "
                 "player likely to be there from this seat, filling starting "
                 "slots first and never a third quarterback. Survival is the "
                 "consensus draft order run through the room's reach — the "
                 "stated prior until the room has made enough picks to "
                 "measure. It does not know camp news, a Friday injury, or "
                 "that seat 4 only drafts his own team."),
    }


def counts_before(mine: set, by_key: dict) -> dict:
    out: dict = {}
    for k in mine:
        pos = _pos(by_key.get(k) or {})
        if pos:
            out[pos] = out.get(pos, 0) + 1
    return out


def summary(rounds_out: list[dict], by_key: dict, mine: set,
            slots: dict | None) -> dict:
    """What the plan adds up to: the planned roster, its starting lineup
    under the slots, and the round each position is taken in."""
    roster = [by_key[k] for k in mine if k in by_key]
    roster += [r["plan"] for r in rounds_out if r.get("plan")]
    lineup = best_lineup(roster, slots)
    order = " · ".join(f"R{r['round']} {r['plan']['position']}"
                       for r in rounds_out if r.get("plan"))
    first_at: dict = {}
    for r in rounds_out:
        if r.get("plan") and r["plan"]["position"] not in first_at:
            first_at[r["plan"]["position"]] = r["round"]
    return {
        "starters_proj": round(sum(_num(p.get("proj")) for p in lineup), 1),
        "starters": [{"player": p.get("player"), "position": _pos(p),
                      "proj": p.get("proj")} for p in lineup],
        "shape": order,
        "first_round_at": first_at,
        "planned": sum(1 for r in rounds_out if r.get("plan")),
        "empty_rounds": sum(1 for r in rounds_out if r.get("empty")),
    }


def best_lineup(roster: list[dict], slots: dict | None) -> list[dict]:
    """The starting lineup the slots allow, best projection first, flex
    filled from whatever is left among flex-eligible positions."""
    slots = dict(slots or DEFAULT_SLOTS)
    flex = int(slots.pop("FLEX", 0) or 0)
    pool = sorted(roster, key=lambda p: -_num(p.get("proj")))
    used: list[dict] = []
    for pos, n in slots.items():
        got = [p for p in pool if _pos(p) == pos and p not in used][:int(n)]
        used.extend(got)
    for _ in range(flex):
        rest = [p for p in pool if p not in used and _pos(p) in FLEX_POSITIONS]
        if rest:
            used.append(rest[0])
    return used


def annotate_rounds(board: list[dict], ranks: dict, teams: int) -> list[dict]:
    """The board with the round each side would take a player in.

    ``our_round`` is where VORP order puts him; ``market_round`` is where
    the consensus draft order does. A player the market takes a round or
    more later than we would is a VALUE (he should be there when we want
    him); one it takes a round or more earlier is a REACH (we would have
    to overpay to get him, and the board says let him go)."""
    teams = max(1, int(teams))
    out = []
    for i, r in enumerate(board or []):
        key = r.get("key")
        ours = i + 1
        mkt = ranks.get(key) if key else None
        our_round = math.ceil(ours / teams)
        mkt_round = math.ceil(_num(mkt) / teams) if mkt else None
        if mkt_round is None:
            tag = "unranked"
        elif mkt_round - our_round >= 1:
            tag = "value"
        elif our_round - mkt_round >= 1:
            tag = "reach"
        else:
            tag = "fair"
        out.append({**r, "our_rank": ours, "our_round": our_round,
                    "market_rank": mkt, "market_round": mkt_round, "tag": tag})
    return out


def draft_state(draft: dict | None = None, teams: int = 12, slot: int = 1,
                rounds: int = 15, kind: str = "snake") -> dict:
    """A `fantasy_pick.advice`-shaped draft dict for a hand-marked draft,
    so the live advice code runs unchanged for a room with no feed."""
    d = dict(draft or {})
    d.setdefault("settings", {})
    d["settings"] = {**d["settings"], "teams": int(teams), "rounds": int(rounds)}
    d["type"] = kind
    d["draft_order"] = {"me": int(slot)}
    return d
