"""Trades worth proposing, and an honest answer about acceptance.

Ethan, 2026-08-15: "Have a trade generator to generate trades and know if
they will m be accepted or not."

THE FIRST HALF IS BUILDABLE AND IS BUILT. THE SECOND HALF IS NOT, YET,
and the difference matters enough to put at the top of the file.

WHAT A TRADE IS WORTH IS A REAL QUESTION WITH A REAL ANSWER. A player's
value to a team is not his ranking — it is what he adds to that team's
best legal STARTING LINEUP. A third good tight end is worth almost
nothing to a roster that starts one, and the same man is worth ten points
a week to the team with a hole there. So every trade here is scored by
re-optimising BOTH lineups with the players swapped and taking the
difference. That is why it can find the deal where each side genuinely
improves: not because value was invented, but because the same player is
worth different amounts to different rosters.

"WILL THEY ACCEPT" IS NOT FITTABLE TODAY, and any percentage this file
printed would be invented. Acceptance is a fact about a person — whether
they read their messages, whether they like the player, whether they are
tanking — and this repo has never stored a single proposed trade, let
alone an accepted or rejected one. There is nothing to fit on.

What CAN be said, and is:

  * whether the deal improves THEIR starting lineup, computed the same
    way as ours. A trade that helps only one side is not a trade, it is a
    request;
  * how lopsided it is, so a proposal that wins by thirty points a week
    can be labelled as the insult it will be received as;
  * whether it fills a hole they actually have.

Those three are what actually decide a real-life accept, and they are
measured rather than guessed. `acceptance_odds` deliberately does not
exist. `log_proposal` does — every proposal written down, so that after a
season of them the question becomes answerable from evidence instead of
from a plausible-sounding number.

Read-only over its inputs; the proposal log is one append per proposal.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from . import fantasy_lineup as fl

#: Weekly starting-lineup points a side must GAIN for the deal to be worth
#: proposing at all. Below this it is noise dressed as a trade, and
#: sending it costs goodwill you will want later.
MIN_GAIN = 0.75
#: Above this gap between the two sides' gains, the deal reads as a
#: fleece however politely it is worded. Not a rule against proposing it —
#: a label, so it is sent knowingly.
LOPSIDED = 4.0
#: How many players may move each way. Three-for-three trades are mostly
#: a way to launder one bad player, and the search space explodes.
MAX_PER_SIDE = 2
#: Proposals kept per rival, best first.
PER_TEAM = 3

LOG_PATH = Path("data") / "fantasy_trades.jsonl"


def _lineup_value(roster: list[dict], slots, scoring: dict,
                  means: dict) -> float:
    """One roster's best legal starting total. The unit of value here."""
    return fl.lineup(roster, slots, scoring, means)["total"]


def _combos(roster: list[dict], k: int) -> list[tuple]:
    """Every k-sized bundle from a roster, as tuples of rows.

    General rather than hand-unrolled for k of 1 and 2 — the first cut
    was, and it returned an empty list for k of 3 instead of failing,
    which would have made `MAX_PER_SIDE = 3` look like "no trades exist".
    """
    from itertools import combinations
    return list(combinations(roster or [], k))


def evaluate(mine: list[dict], theirs: list[dict], give: tuple, get: tuple,
             slots, scoring: dict, means: dict) -> dict:
    """Score one specific swap for BOTH sides.

    Both lineups are re-optimised from scratch after the swap, which is
    the only way to see that the same player is worth ten points to one
    roster and nothing to the other.
    """
    give_names = {r["player"] for r in give}
    get_names = {r["player"] for r in get}
    my_after = [r for r in mine if r["player"] not in give_names] + list(get)
    their_after = [r for r in theirs if r["player"] not in get_names] + list(give)
    my_before = _lineup_value(mine, slots, scoring, means)
    their_before = _lineup_value(theirs, slots, scoring, means)
    my_gain = _lineup_value(my_after, slots, scoring, means) - my_before
    their_gain = _lineup_value(their_after, slots, scoring, means) - their_before
    return {
        "give": [r["player"] for r in give],
        "get": [r["player"] for r in get],
        "my_gain": round(my_gain, 2),
        "their_gain": round(their_gain, 2),
        "both_gain": my_gain >= MIN_GAIN and their_gain >= MIN_GAIN,
        # NOT a probability. The size of the imbalance, named so a
        # proposal that will read as an insult can be sent knowingly.
        "gap": round(abs(my_gain - their_gain), 2),
        "lopsided": abs(my_gain - their_gain) >= LOPSIDED,
        "favours": ("me" if my_gain > their_gain else
                    "them" if their_gain > my_gain else "even"),
    }


def generate(mine: list[dict], rosters: dict, slots, scoring: dict,
             means: dict, max_per_side: int = MAX_PER_SIDE,
             per_team: int = PER_TEAM) -> list[dict]:
    """Every trade worth proposing, best first, across every rival roster.

    ``rosters`` is ``{team label: [{player, position}]}``. Only deals
    where BOTH starting lineups improve are returned — a trade that helps
    one side is a request, and sending those is how a league stops
    reading your messages.
    """
    out = []
    for label, theirs in (rosters or {}).items():
        found = []
        for k in range(1, max_per_side + 1):
            for j in range(1, max_per_side + 1):
                for give in _combos(mine or [], k):
                    for get in _combos(theirs or [], j):
                        ev = evaluate(mine, theirs, give, get, slots,
                                      scoring, means)
                        if ev["both_gain"]:
                            found.append({**ev, "with": label})
        found.sort(key=lambda t: (-(t["my_gain"] + t["their_gain"]),
                                  t["gap"]))
        out.extend(found[:per_team])
    out.sort(key=lambda t: -(t["my_gain"] + t["their_gain"]))
    return out


def summary(trades: list[dict]) -> dict:
    """What the page prints above the list, including what it cannot say."""
    return {
        "count": len(trades or []),
        "best": (trades or [None])[0],
        "acceptance_note": (
            "There is no acceptance probability here and will not be one "
            "until it can be measured. Whether a manager says yes is a "
            "fact about a person, and this app has never stored a single "
            "proposed trade — so a percentage would be invented. What is "
            "shown instead is measured: whether THEIR starting lineup "
            "improves too, by how much, and whether the deal is lopsided "
            "enough to read as an insult. Log the ones you send and the "
            "question becomes answerable from evidence."),
    }


def log_proposal(trade: dict, sent: bool = False, outcome: str = "",
                 path: str | Path | None = None) -> bool:
    """Write one proposal down. This is what makes acceptance fittable.

    ``outcome`` is free text the user fills in later — "accepted",
    "rejected", "countered", "ignored". Nothing here interprets it yet,
    on purpose: the first job is to HAVE the rows, and a scoring rule
    invented before the data exists is the thing this file refuses to do.
    """
    if not trade:
        return False
    f = Path(path or LOG_PATH)
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        row = {"ts": round(time.time(), 3), "sent": bool(sent),
               "outcome": str(outcome or ""),
               "with": trade.get("with"), "give": trade.get("give"),
               "get": trade.get("get"), "my_gain": trade.get("my_gain"),
               "their_gain": trade.get("their_gain")}
        with f.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")
        return True
    except OSError:
        return False


def load_proposals(path: str | Path | None = None) -> list[dict]:
    """Every logged proposal, oldest first. Bad lines are skipped."""
    f = Path(path or LOG_PATH)
    if not f.exists():
        return []
    out = []
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def acceptance_evidence(path: str | Path | None = None) -> dict:
    """What the log can support SO FAR. Usually: not enough to say anything.

    Deliberately reports the count first and a rate only when there is
    enough of one to mean something. The bar is stated here rather than
    chosen later, for the same reason the preseason fit's bar is.
    """
    rows = [r for r in load_proposals(path) if r.get("sent")]
    graded = [r for r in rows if r.get("outcome") in
              ("accepted", "rejected", "countered", "ignored")]
    yes = sum(1 for r in graded if r.get("outcome") == "accepted")
    enough = len(graded) >= 20
    return {
        "sent": len(rows), "graded": len(graded), "accepted": yes,
        "enough": enough,
        "rate": round(yes / len(graded), 3) if enough and graded else None,
        "note": ("A rate needs at least 20 graded proposals; below that it "
                 "is a number about four people's moods."
                 if not enough else
                 "Measured from proposals you logged and graded yourself."),
    }
