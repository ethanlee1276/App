"""Auction values — the same projections, denominated in dollars.

A large minority of leagues do not snake. They put every player on the
block and hand each manager a budget, and for those rooms the draft kit
was useless: a tier board answers "who is next" and an auction never
asks that question. It asks one question, over and over, with a clock
running: *is he worth this much of my money?*

THE ARITHMETIC, AND EVERY TERM IS OURS. The money in the room is
``teams x budget``. Every roster spot must be filled and the minimum bid
is a dollar, so ``teams x slots`` of those dollars are already spoken
for. What is left is discretionary, and the only thing this board has to
divide it by is value over replacement — points above the best man you
could have had for nothing. So:

    per_vorp = teams x (budget - slots) / (sum of positive VORP)
    value    = $1 + VORP x per_vorp

and a player at or below replacement is worth exactly the minimum,
because that is what replacing him costs.

THE BASELINE IS DEEPER HERE THAN ON THE SNAKE BOARD, and that is the
one number in this file worth arguing about. The kit measures a player
against the best free STARTER at his position, which is right for a
snake: you draft a starter early and stream the rest off a waiver wire
that is genuinely free. An auction has no such wire on draft day —
every roster spot in the room is bought, bench included — so the real
alternative to paying up for a back is the LAST back anybody drafts,
not the twenty-sixth. Using the snake baseline here priced the top pick
at $136 of a $200 budget, which no auction in history has paid, and the
reason was structural: a shallow baseline concentrates all the money in
the starters. So this module computes its own replacement level at the
depth an auction actually drafts to, and the sheet publishes it.

THE SHEET BALANCES TO THE DOLLAR. Whole-dollar rounding is done by
largest remainder, not by rounding each row on its own: the floors are
taken first and the leftover dollars go to the biggest fractions. So the
priced players plus a dollar for every remaining roster spot sum to
exactly the money in the room — which is the property that makes the
sheet usable at the table. If your values total more than the league can
spend, every one of them is a lie by however much they overshoot, and
you find that out in the last three rounds.

WHAT THIS IS NOT: a prediction of what he will GO for. Real rooms
overpay at the top and leave dollars unspent at the bottom, and the gap
between the value and the price is exactly where an auction is won. We
have never logged a single auction, so there is nothing here to fit an
inflation curve to, and inventing one would be a number nobody measured
wearing a decimal point. The sheet says what he is worth. The room says
what he costs. Comparing them is the reader's job and the whole game.

The projections behind it are last season's volume run forward, with the
same blind spots the rest of the kit declares.

Standard library only; no I/O — this is arithmetic over rows the kit has
already built.
"""

from __future__ import annotations

#: A standard room: $200 a team, 15 roster spots. Both are inputs on the
#: page; these are only the defaults the payload is built at.
DEFAULT_BUDGET = 200
DEFAULT_SLOTS = 15

#: Kicker and defence. They each take a roster spot — and therefore a
#: dollar — but this board has no projection for either, so they are
#: subtracted from the spots the sheet can fill rather than pretended
#: at. Their dollars stay reserved: the money is spent whether or not we
#: have an opinion about who spends it.
NON_SKILL_SLOTS = 2

#: How a thirteen-man skill roster actually gets filled, per team — the
#: shape of a drafted bench, not of a starting lineup. Sums to
#: ``DEFAULT_SLOTS - NON_SKILL_SLOTS``, and scales with both league size
#: and roster size, so the baseline follows the room instead of assuming
#: one. Fractions are deliberate: most teams carry one quarterback and
#: some carry two, and rounding that to either integer before
#: multiplying by twelve moves the baseline by a whole draft round.
DRAFTED_PER_TEAM = {"QB": 1.5, "RB": 4.5, "WR": 5.5, "TE": 1.5}

#: Rails on the budget input. Below the roster size there is no
#: discretionary money at all and every player is a dollar, which is
#: arithmetic rather than a failure; the floor is here so the page
#: cannot be typed into nonsense. The page clamps to the same pair and
#: a test pins that it does.
MIN_BUDGET = 20
MAX_BUDGET = 1000


def baselines(rows, teams: int, skill_slots: int) -> tuple[dict, dict]:
    """Replacement projection per position, at auction depth.

    Returns ``({position: baseline PPG}, {position: rank used})`` — both
    published, because a value nobody can check the baseline of is a
    number to be taken on faith.
    """
    shape = sum(DRAFTED_PER_TEAM.values())
    scale = (skill_slots / shape) if shape else 1.0
    base: dict[str, float] = {}
    ranks: dict[str, int] = {}
    for pos, per in DRAFTED_PER_TEAM.items():
        projs = sorted((float(r.get("proj") or 0.0) for r in rows
                        if str(r.get("position") or "").upper() == pos),
                       reverse=True)
        rank = max(1, int(round(teams * per * scale)))
        ranks[pos] = rank
        # Shallower than the rank means the last man on the list is the
        # baseline — the same rule the kit's own replacement level uses.
        base[pos] = projs[min(rank, len(projs)) - 1] if projs else 0.0
    return base, ranks


def _allocate(pool: list[dict], vorps: list[float], per_vorp: float,
              target: int) -> None:
    """Whole dollars by largest remainder, summing to exactly ``target``.

    Rounding each row independently would drift — a hundred rows each
    rounded up by a third of a dollar is thirty dollars the league does
    not have. Floors first, then the leftover goes to the largest
    fractional parts, ties broken by value so the same board always
    prices the same way.
    """
    raws = [1.0 + v * per_vorp for v in vorps]
    for r, raw in zip(pool, raws):
        r["auction"] = int(raw)
    short = target - sum(int(raw) for raw in raws)
    if short <= 0:
        return
    order = sorted(range(len(pool)),
                   key=lambda i: (raws[i] - int(raws[i]), raws[i]),
                   reverse=True)
    for i in order[:short]:
        pool[i]["auction"] += 1


def attach(rows, teams: int = 12, budget: int = DEFAULT_BUDGET,
           slots: int = DEFAULT_SLOTS,
           non_skill: int = NON_SKILL_SLOTS) -> dict:
    """Stamp ``auction`` on every row; return what the sheet spent.

    Mutates, like the tier and bye passes it runs beside — the kit's
    board, tiers and mock-draft pool are the same row objects, so one
    pass prices all three. Every row gets the key, so a missing dollar
    figure on the page means the pass did not run rather than that the
    player was skipped.
    """
    rows = list(rows or [])
    teams = max(2, int(teams))
    budget = max(1, int(budget))
    slots = max(1, int(slots))
    non_skill = max(0, int(non_skill))
    for r in rows:
        r["auction"] = 1

    skill_slots = max(1, slots - non_skill)
    base, ranks = baselines(rows, teams, skill_slots)
    # The board can only fill the spots it has players for; a kicker's
    # dollar is reserved below but never priced here.
    cap = teams * skill_slots
    priced = []
    for r in rows:
        v = float(r.get("proj") or 0.0) - base.get(
            str(r.get("position") or "").upper(), 0.0)
        if v > 0:
            priced.append((v, r))
    priced.sort(key=lambda vr: vr[0], reverse=True)
    priced = priced[:cap]
    pool = [r for _, r in priced]
    vorps = [v for v, _ in priced]

    total = teams * budget
    # Every roster spot this sheet does not price still costs a dollar.
    dollar_spots = max(0, teams * slots - len(pool))
    purse = total - dollar_spots - len(pool)
    sum_vorp = sum(vorps)
    per_vorp = purse / sum_vorp if (pool and purse > 0 and sum_vorp > 0) else 0.0
    if per_vorp:
        _allocate(pool, vorps, per_vorp, purse + len(pool))

    by_pos: dict[str, dict] = {}
    for r in pool:
        b = by_pos.setdefault(str(r.get("position") or "?"),
                              {"n": 0, "dollars": 0})
        b["n"] += 1
        b["dollars"] += int(r["auction"])
    for b in by_pos.values():
        b["share"] = round(b["dollars"] / total, 3) if total else 0.0

    return {
        "teams": teams, "budget": budget, "slots": slots,
        "non_skill": non_skill,
        "total": total,
        "priced": len(pool),
        "dollar_spots": dollar_spots,
        # Priced players plus a dollar apiece for the rest. Equal to
        # `total` by construction — if it ever is not, the largest
        # remainder pass is broken and the sheet is over the room's
        # money, which a test refuses to let ship.
        "allocated": sum(int(r["auction"]) for r in pool) + dollar_spots,
        "per_vorp": round(per_vorp, 3),
        "max": max((int(r["auction"]) for r in pool), default=1),
        "replacement": {k: round(v, 1) for k, v in sorted(base.items())},
        "ranks": {k: ranks[k] for k in sorted(ranks)},
        "by_position": {k: by_pos[k] for k in sorted(by_pos)},
    }
