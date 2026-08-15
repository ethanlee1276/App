"""Pick-by-pick advice: not who is best, but who will not be there later.

Ethan, 2026-08-15: "We need to show pick by pick advice."

THE QUESTION AT A DRAFT TABLE IS NOT "WHO IS BEST AVAILABLE". The board
already answers that and it is the easy half. The question that actually
decides a pick is:

    of the players I want, which ones will still be here at my NEXT pick?

Taking the best available when he would have lasted another round, and
passing on the man who will not, is how a good board produces a bad team.
So every recommendation here carries a survival probability, and the
advice is phrased against it: take him NOW, or take someone else and get
him next time.

HOW SURVIVAL IS ESTIMATED, AND WHY IT IS NOT A GUESS.

Nothing here uses national ADP. The room you are in is the sample: every
pick already made says how far off consensus THIS set of twelve people
drafts. `reach_window` measures it — for each pick, how deep into the
then-available consensus list that player was. A chalk room runs a depth
of two or three; a room full of homers and hype runs ten. That measured
depth is the whole model's one parameter, and it updates on every pick.

Given a window ``w`` and ``k`` picks before your next turn, a player
sitting at depth ``d`` in the available list is exposed once the queue
reaches him, which takes ``d - w`` picks, and is then taken with
probability ``1/w`` per pick:

    P(survive) = (1 - 1/w) ** max(0, k - max(0, d - w))

Monotone in every argument, exact at the boundaries (k = 0 is certain
survival; a huge window makes everyone a coin toss), and every input is
counted rather than assumed.

WHAT THIS CANNOT SEE, said plainly because it changes how much to trust
it: it does not know that the guy in seat 4 only drafts his own team's
players, that someone has already announced he is taking a quarterback,
or that a player was ruled out an hour ago. It models the room as
consensus-plus-noise, and the noise is measured, not the intent.

Read-only and pure — every input is handed in, nothing is fetched.
"""

from __future__ import annotations

#: A room needs to have drafted at least this many players before its
#: reach can be measured. Below it the prior is used, because a window
#: fitted on three picks is one loud homer away from nonsense.
MIN_PICKS_TO_FIT = 8
#: The prior window, in players. Roughly "the room takes one of the top
#: half-dozen available", which is what a normal draft looks like before
#: anyone has shown you otherwise.
DEFAULT_WINDOW = 6.0
#: Clamps. A window under 1 makes the arithmetic meaningless; over 40 is
#: not a draft, it is a raffle, and the survival numbers stop being worth
#: printing.
WINDOW_FLOOR, WINDOW_CEILING = 1.5, 40.0
#: Above this, "he'll be there" — below it, "he won't". Two thresholds
#: rather than one so the middle can honestly say it does not know.
LIKELY, UNLIKELY = 0.70, 0.35


# --- where your picks are ---------------------------------------------------
def pick_numbers(slot: int, teams: int, rounds: int,
                 kind: str = "snake") -> list[int]:
    """Every overall pick number belonging to one draft slot.

    Snake reverses on even rounds, which is the entire reason the wait
    between your picks is uneven — slot 1 waits 22 picks in a 12-team
    league and slot 12 waits 2. Getting this wrong does not produce a
    small error in the advice, it produces advice for someone else's
    seat.
    """
    slot, teams, rounds = int(slot), int(teams), int(rounds)
    if slot < 1 or teams < 1 or rounds < 1 or slot > teams:
        return []
    out = []
    for r in range(1, rounds + 1):
        if kind == "snake" and r % 2 == 0:
            out.append((r - 1) * teams + (teams - slot + 1))
        else:
            out.append((r - 1) * teams + slot)
    return out


def my_slot(draft: dict, user_id: str) -> int | None:
    """Which seat is yours, from Sleeper's ``draft_order``. None if absent.

    None matters: a draft you are only watching has no seat for you, and
    inventing one would produce confident advice for a team that is not
    yours.
    """
    order = (draft or {}).get("draft_order") or {}
    slot = order.get(str(user_id))
    return int(slot) if isinstance(slot, (int, float)) and slot > 0 else None


def next_pick(made: int, mine: list[int]) -> int | None:
    """Your next pick number given how many picks have been made."""
    for p in sorted(mine or []):
        if p > made:
            return p
    return None


def picks_until(made: int, mine: list[int]) -> int | None:
    """How many other people pick before you do again."""
    nxt = next_pick(made, mine)
    return None if nxt is None else max(0, nxt - made - 1)


# --- how this room drafts ---------------------------------------------------
def _depths(picks: list, ranks: dict) -> list[int]:
    """For each pick, how deep into the then-available list it reached.

    1 means "took the consensus best available". The sequence of these is
    the room's behaviour, and it is all the model needs.
    """
    order = sorted((k for k in ranks if ranks[k] is not None),
                   key=lambda k: ranks[k])
    gone: set = set()
    out = []
    for p in picks or []:
        key = (p or {}).get("key")
        if not key or key not in ranks:
            continue
        depth = 0
        for k in order:
            if k in gone:
                continue
            depth += 1
            if k == key:
                out.append(depth)
                break
        gone.add(key)
    return out


def reach_window(picks: list, ranks: dict) -> float:
    """The room's measured reach, in players. Falls back to the prior.

    The MEAN depth rather than the median, on purpose: one drafter who
    reaches forty spots for his own quarterback genuinely does change how
    safe everyone else is, and a median would discard exactly the
    behaviour that makes a room unpredictable.
    """
    d = _depths(picks, ranks)
    if len(d) < MIN_PICKS_TO_FIT:
        return DEFAULT_WINDOW
    return max(WINDOW_FLOOR, min(WINDOW_CEILING, sum(d) / len(d)))


def survival(depth: int, k: int, window: float) -> float:
    """P(a player at ``depth`` is still there after ``k`` more picks).

    See the module docstring for the derivation. Returns 1.0 when nobody
    picks before you, which is the correct answer rather than a modelled
    approximation of it.
    """
    if k is None or k <= 0:
        return 1.0
    w = max(WINDOW_FLOOR, float(window or DEFAULT_WINDOW))
    exposed = max(0, int(k) - max(0, int(depth) - int(round(w))))
    if exposed <= 0:
        return 1.0
    return max(0.0, min(1.0, (1.0 - 1.0 / w) ** exposed))


def verdict(p: float) -> str:
    """"gone" / "toss-up" / "safe" — three states, because two would lie.

    A single threshold forces every 50/50 into a confident word. The
    middle band exists so the board can say it does not know, which at a
    draft is a useful thing to be told.
    """
    if p >= LIKELY:
        return "safe"
    return "gone" if p <= UNLIKELY else "toss-up"


# --- what you already have --------------------------------------------------
def roster_counts(picks: list, user_id: str, positions: dict) -> dict:
    """``{position: how many you have}`` from the picks you have made."""
    out: dict = {}
    for p in picks or []:
        if str((p or {}).get("picked_by") or "") != str(user_id):
            continue
        pos = (positions or {}).get(p.get("key")) or p.get("position")
        if pos:
            out[str(pos).upper()] = out.get(str(pos).upper(), 0) + 1
    return out


def needs(counts: dict, slots: dict) -> dict:
    """``{position: how many starters you still have to fill}``.

    Only STARTERS count as need. A bench body is not a need, and treating
    it as one is what makes a draft board tell you to take a fourth tight
    end in the eighth round.
    """
    out = {}
    for pos, want in (slots or {}).items():
        short = int(want) - int((counts or {}).get(pos, 0))
        if short > 0:
            out[pos] = short
    return out


# --- the advice -------------------------------------------------------------
def advice(draft: dict, picks: list, ranks: dict, board: list,
           user_id: str, slots: dict | None = None,
           limit: int = 6) -> dict:
    """Everything the board needs to tell you what to do with this pick.

    ``picks`` are normalised rows carrying at least ``key`` (the join key)
    and ``picked_by``. ``board`` is our draft kit's rows, which supply
    position and VORP. ``ranks`` is the consensus map from
    `fantasy_ranks` — the ordering the survival model reads.
    """
    settings = (draft or {}).get("settings") or {}
    teams = int(settings.get("teams") or 12)
    rounds = int(settings.get("rounds") or 15)
    kind = str((draft or {}).get("type") or "snake").lower()
    made = len([p for p in picks or [] if (p or {}).get("key")])

    slot = my_slot(draft, user_id)
    mine = pick_numbers(slot, teams, rounds, kind) if slot else []
    nxt = next_pick(made, mine)
    wait = picks_until(made, mine)
    window = reach_window(picks, ranks)

    positions = {r.get("key"): (r.get("position") or "").upper()
                 for r in board or [] if r.get("key")}
    vorp = {r.get("key"): r.get("vorp") for r in board or [] if r.get("key")}
    names = {r.get("key"): r.get("player") for r in board or [] if r.get("key")}
    for p in picks or []:
        if p.get("key") and p.get("player"):
            names.setdefault(p["key"], p["player"])

    gone = {p["key"] for p in picks or [] if (p or {}).get("key")}
    avail = sorted((k for k in ranks
                    if k not in gone and ranks.get(k) is not None),
                   key=lambda k: ranks[k])

    counts = roster_counts(picks, user_id, positions)
    short = needs(counts, slots or {})

    rows = []
    for depth, key in enumerate(avail[:60], start=1):
        p = survival(depth, wait, window)
        rows.append({
            "key": key,
            "player": names.get(key) or key.title(),
            "position": positions.get(key) or "",
            "rank": ranks.get(key),
            "depth": depth,
            "vorp": vorp.get(key),
            "survives": round(p, 3),
            "verdict": verdict(p),
            "fills_need": bool(short.get(positions.get(key) or "")),
        })

    # THE ONE THAT CANNOT WAIT. Among the players worth taking at all,
    # the recommendation is the best one who will not survive the round
    # trip — that is the pick a later round cannot give back. If everyone
    # in range is safe, the honest advice is simply the best available.
    pool = rows[:limit * 3]
    urgent = [r for r in pool if r["verdict"] == "gone"]
    take = (urgent or pool)[:1]
    return {
        "slot": slot, "teams": teams, "rounds": rounds, "type": kind,
        "picks_made": made, "next_pick": nxt, "picks_until": wait,
        "window": round(window, 2),
        "window_fitted": len(_depths(picks, ranks)) >= MIN_PICKS_TO_FIT,
        "on_the_clock": bool(slot and wait == 0),
        "needs": short, "have": counts,
        "take": take[0] if take else None,
        "board": rows[:limit],
        "can_wait": [r for r in rows[:limit * 3] if r["verdict"] == "safe"][:limit],
        "note": ("Survival is measured from THIS room — how far off "
                 "consensus its picks have actually reached — not from a "
                 "national average. It does not know who is about to be "
                 "ruled out, or that seat 4 only drafts his own team."),
    }
