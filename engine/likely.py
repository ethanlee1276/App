"""The board that answers "who will actually hit", not "where is the edge".

Ethan, 2026-08-30: "we need to focus more on using the data to figure out
who will score each game, not who has the best edge... a page for EDGE
picks that give the best EDGE, then a separate page which will be the
main page for bets, that will show who we genuinely think will score or
hit the over."

THE MEASUREMENTS SAY HE IS RIGHT, AND THEY SAY IT LOUDLY. The model ranks
outcomes well and prices them badly, and those are separate abilities:

    what it is asked          how well it does it
    who scores a touchdown    AUC 0.721 (22,099 graded NFL player-weeks)
    who clears their line     AUC 0.76 rushing, 0.77 receptions,
                              0.73 receiving, 0.69 passing
    where the market is wrong AUC 0.468 — noise (the site's settle pass)

So the edge board is built on the model's weakest ability and the
likelihood board on its strongest, and until now only the weak one had a
page.

GAME LINES, MEASURED THE SAME WAY. Ethan, 2026-09-02: "all I see us is
doing overs, but we have no unders, and we also have no money lines or
spreads or totals ... there is more bets that we can salvage." Measured
by `engine.gamerank` — the ratings-only replay `engine.gamebacktest`
runs over the stored closes, keeping for EVERY quoted game the
probability the pricer put on its side and whether that side won:

    who wins the game (moneyline)   AUC 0.677 NFL (1,356 games)
                                    AUC 0.752 CFB (2,729 games)
    …and the market's own number    AUC 0.722 NFL · 0.791 CFB — better
                                    in both, so game rows rank on it
                                    (GAME_RANK_MARKET, 2026-09-07), and
                                    the model's disagreement with it
                                    does not bar a row (engine_credible,
                                    measured 2026-09-08)
    who covers the spread           0.491 NFL · 0.496 CFB — a coin flip
    over or under the total         0.497 NFL · 0.503 CFB — a coin flip
    a team over its own number      0.513 NFL · 0.492 CFB — a coin flip

(The college walk rebuilds the production opponent-adjusted ratings
before every date — `gamerank.measure_cfb`; the plain-ratings floor
had said 0.708 for the moneyline and the same coin flips elsewhere.)

The model can say who WINS and cannot say who COVERS. That is not a
surprise — the close already holds the ratings, and the market's own
de-vigged moneyline ranks the winner at 0.714 — and it is what decides
the board: moneylines are ranked here, spreads and totals are not, and
they stay off until a measurement says otherwise. The MLB figures can
only be measured where the MLB history is (`gamerank --save` on the
droplet writes them into the store `rank_auc` reads first).

WHY A SHUT MARKET STILL BELONGS HERE, which looks wrong and is not.
`calibrate.is_reliable` closes rush_yds and rec_yds for BETTING because
their probability is wrong in ABSOLUTE terms — it cannot be compared to a
price. Ranking needs it right only in RELATIVE terms, and those are
different tests: rushing yards rank at 0.7605 while being unbettable.
Ordering barely moves when the calibration is stripped out entirely
(0.7605 against 0.7627 for the raw projection), because a monotone error
does not reorder a list.

A market therefore appears on this board when it can RANK, and carries an
honest flag saying whether it can also be BET. Nothing here is a
recommendation to stake; that is what the edge board is for.

WHAT THESE NUMBERS ARE NOT. The yardage figures are scored at synthetic
lines on a grid. A real book hangs its line at its own number, which
already contains most of the signal, so the achievable AUC against a live
board is lower — probably by a lot. Nothing on the page may quote these
as though they were the live figure until `engine.yardagefit --real` has
measured the same thing at real closes.

Standard library only.
"""

from __future__ import annotations

from .yardagefit import display_prob

#: Markets this board will rank, and whether the model has been shown to
#: rank them. Measured 2026-08-30 at synthetic lines over 2021-25 NFL
#: logs; `anytime_td` comes from `engine.tdbacktest` against outcomes.
#:
#: A market with no measurement does not appear. That is the whole
#: discipline: "we think he will hit" is a claim, and an unmeasured claim
#: on the main board is exactly what this product is trying to stop
#: being.
RANK_AUC = {
    "anytime_td": 0.721,
    #: PASSING touchdowns, measured 2026-09-10 on this box's own
    #: `player_game_logs`: the blend in `engine/passtd` fitted on
    #: 2021-2024 and scored on HELD-OUT 2025 sorts a quarterback who
    #: throws at least one from one who does not at 0.687 over 647
    #: games. The in-sample figure was 0.715 and this is deliberately
    #: not that one — the whole point of holding a season back is to
    #: publish the number that survived it.
    #:
    #: Sits just under the scorers' 0.721, which is the right
    #: neighbourhood: it is the same kind of question about the same
    #: kind of event, asked of the man who throws it.
    "pass_td": 0.687,
    "receptions": 0.770,
    "rush_yds": 0.761,
    "rec_yds": 0.733,
    "pass_yds": 0.691,
}

#: The game markets a card can carry (`gamebets._game_bet` bet_type).
GAME_MARKETS = ("moneyline", "spread", "total", "team_total")

#: Game markets shown to rank, per sport — measured 2026-09-02 by
#: `engine.gamerank` (see the header). ONLY the markets that cleared
#: MIN_RANK_AUC are listed, because an entry here is what puts a market
#: on the board; the ones that tested as a coin flip are written out in
#: the header so nobody re-measures them by accident and nobody quietly
#: adds them. A sport with no entry ranks no game market until the
#: store on its own box says so.
GAME_RANK_AUC = {
    "nfl": {"moneyline": 0.677},
    "cfb": {"moneyline": 0.752},
}

#: EVERY game-market figure that was measured, floor or not — the same
#: run, the whole table. Ethan, 2026-09-02, after the first cut shipped
#: moneylines alone: "I only see money lines in the best bets. I don't
#: see team totals over or unders ... I don't see spread bets, I don't
#: see anything like that I just asked you to do." His call: the
#: spreads, totals and team totals go on the board. The measurement's
#: job is then to be PRINTED on each of them — a row from a market that
#: sorts games at 0.49 says so on its face, carries `ranked` False, and
#: is shown as the model's lean at that number rather than as a claim to
#: rank. A market with NO figure at all still has nothing to say and
#: stays off.
#:
#: BASEBALL'S MONEYLINE ARRIVED 2026-09-16 (#257) — the walk could only
#: ever run where the MLB history is, and Ethan ran it on the droplet.
#: The model ranks winners at 0.5596 on 1,088 quoted games, which is
#: close enough to a coin flip to be worth stating plainly: baseball's
#: game rows were being ordered on very little. Its other three markets
#: were not measured and so are still absent, which keeps them off the
#: board exactly as before.
GAME_RANK_MEASURED = {
    "nfl": {"moneyline": 0.677, "spread": 0.504, "total": 0.496, "team_total": 0.500},
    "cfb": {"moneyline": 0.752, "spread": 0.496, "total": 0.503, "team_total": 0.492},
    "mlb": {"moneyline": 0.5596},
}

#: THE MARKET'S OWN RANKING, and why the board ranks on it where it can.
#: Ethan, 2026-09-07: "you worked on the NFL and CFB Most Likely model
#: and made it better." The one thing measured to rank winners better
#: than the model is the closing market itself. Measured 2026-09-07 on
#: this box's stored closes — the schedule's de-vigged moneyline against
#: the result, every scored game with a price, ties out:
#:
#:     nfl  market 0.722 on 1,420 games (2021-26)   model 0.677
#:     cfb  market 0.791 on 3,011 games (2022-26)   model 0.752
#:
#: BASEBALL JOINED ON 2026-09-16 (#257). It could only ever be measured
#: where the MLB history lives, so Ethan ran the same walk on the droplet
#: and it came back with the widest gap of the three:
#:
#:     mlb  market 0.6727 on 1,088 games            model 0.5596
#:
#: 1,088 quoted games is well past the 400-game floor the walk refuses
#: below, and the same run re-measured the NFL as a control: 0.7236
#: against the 0.722 stored here, so the harvest has not drifted under
#: the table. The model at 0.5596 is close enough to a coin flip that
#: baseball's game rows were being ordered on very little; this is the
#: measurement #257 was opened to get.
#:
#: So a game row on the NFL or college board ranks on the book's
#: de-vigged number for its side — `fair_prob` on the card — rather
#: than on the model's, whenever the market's measured figure beats the
#: model's (`ranking_number`). The model's number stays on the row and
#: on the card; only the ORDER changes, and the row says which number
#: ordered it (`prob_source`). A sharp-anchored card ranks on its own
#: `win_prob`, which IS a market number — the sharp book's fair. Spreads,
#: totals and team totals have no market figure here and rank (or are
#: shown as leans) exactly as before. A market with no entry ranks on
#: the model, so nothing changes for a sport that has not been measured.
GAME_RANK_MARKET = {
    "nfl": {"moneyline": 0.722},
    "cfb": {"moneyline": 0.7905},
    "mlb": {"moneyline": 0.6727},
}


def ranking_number(sport: str, market: str, row: dict, model_auc):
    """``(probability, source, auc)`` a game row ranks on.

    ``source`` is "sharp" (the card's own probability is the sharp
    book's fair), "market" (the book's de-vigged number, because it
    measures better than the model here), or "model".
    """
    prob = row.get("win_prob")
    fair = row.get("fair_prob")
    market_auc = GAME_RANK_MARKET.get(sport, {}).get(market)
    if row.get("sharp_anchored") and prob is not None and market_auc is not None:
        return float(prob), "sharp", float(market_auc)
    if (market_auc is not None and fair is not None
            and (model_auc is None or float(market_auc) > float(model_auc))):
        return float(fair), "market", float(market_auc)
    return (None if prob is None else float(prob)), "model", model_auc


#: EVERY MARKET KEEPS ITS BEST ROWS. Ethan, 2026-09-07: "for some reason
#: its only displaying tight ends for reciving props and thats it. that
#: seems strang and wrong." The board kept the forty highest
#: probabilities across every player market in one list, and the
#: highest probabilities belong to the lowest lines — a tight end or a
#: back over 2.5 receptions at 68% — so the forty filled with those and
#: a receiver's 58% over on 64.5 yards, ranked just as honestly, never
#: reached the receiving shelf. A shelf that shows one position is a
#: shelf that shows one kind of line.
#:
#: So the cut is in two passes: first up to PER_MARKET rows from each
#: player market in probability order, then the remaining seats filled
#: from whatever is left, by probability. The floor, the price cap and
#: the credibility bar are untouched — a market whose every row sits
#: under 55% still shows nothing, and the census says so.
PER_MARKET = 8

#: THE HOLD. Ethan, 2026-09-24: "for the most likely bets they seem too
#: change alot so it's hard too judge what picks the models are
#: comfortable with."
#:
#: The board had no memory. Every refresh rebuilt it from nothing, and
#: two things in that rebuild move on a price tick rather than on
#: anything the model thinks:
#:
#:   * THE NUMBER. `_best_rung` takes the likeliest rung at no heavier
#:     than -250, which is the rung sitting nearest the cap — so over
#:     34.5 at -245 is the pick until the book moves it to -255, then
#:     over 39.5 is, then 34.5 again. The player's projection never
#:     moved; the row's line, price and percent did.
#:   * THE SEAT. A rung near the cap is priced near 71%, and the
#:     credibility bar keeps the model within ten points of it, so the
#:     rows fighting for a market's eight seats sit a point or two apart.
#:     A hop on one row reorders the seats for all of them.
#:
#: So a pick on the board keeps its number while that number still
#: clears every bar at its own price (`from_prop`'s `prefer`), and keeps
#: its seat unless a newcomer is likelier by HOLD_MARGIN. NO BAR MOVES:
#: the floor, the -250 cap, the credibility bar and the injury holds are
#: asked of a held pick exactly as of a new one, and a held pick that
#: fails one leaves. What the hold decides is only which of several rows
#: that ALL clear the bars is shown — the question a price tick used to
#: answer.
#:
#: WHAT IT BOUGHT, REPLAYED BEFORE IT SHIPPED (tests/test_most_likely_
#: holds_its_picks.py builds the replay; there was no board history on
#: any box to measure instead — the board never kept one). Seventy-two
#: props on alternate ladders at three books, rebuilt every fifteen
#: minutes for six hours with every rung's price ticking; picks that
#: differ between two looks at a forty-pick board:
#:
#:                       15 min apart   1 hour   3 hours
#:     prices jitter     5.4 -> 2.4     5.1 -> 2.9   5.3 -> 4.3
#:     prices drift      5.5 -> 2.6     6.5 -> 4.0   8.0 -> 6.9
#:
#: THE HELD NUMBER DID NEARLY ALL OF IT. The margin moved nothing in the
#: replay (0.00 against 0.05: 4.1 against 3.9 at an hour), because there a
#: pick's probability at a fixed number never moves — the mixture reads
#: the projection, not the price. On the box it does move: passing yards
#: price on a mean anchored to the book (`_anchored_mean`), and a
#: projection moves on news. THREE POINTS is one step of the ladder near
#: the cap (-220 against -250 is 68.8% against 71.4%), and each build
#: reports how many held rows the margin alone kept (`kept_by_margin` in
#: `turnover`): a margin that never decides a seat is doing nothing, and
#: one deciding most of them is too wide.
HOLD_MARGIN = 0.03

#: HOW LONG A PICK THAT LEFT IS STILL THE SAME PICK, in minutes. Found in
#: the replay above: a held rung whose price ticks past -250 for one
#: refresh drops the pick to a weaker number, the pick loses its seat, and
#: by the next refresh — the price back at -245 — the board had forgotten
#: it and the row that took its seat was the incumbent. So a pick that
#: left for any reason but its game starting is remembered for an hour
#: (`turnover["held_out"]`): if it clears every bar again inside that, it
#: returns at its own number, with its seat margin and its `since`. In
#: the replay that took the changes between looks an hour apart from 4.4
#: to 4.0 of forty — small, and the rest of those are the ticks the cap
#: really did refuse. An hour is four refreshes on the slowest board:
#: long enough to ride out a tick, short enough that a pick the model
#: really dropped is gone by the next time anyone looks.
HOLD_GRACE_MIN = 60


def hold_key(r: dict) -> tuple:
    """Which pick a row IS, across refreshes: the player and market (the
    number may move), or the game, market and side."""
    kind = r.get("kind") or "prop"
    if kind == "game":
        return ("game", r.get("matchup") or "", r.get("market") or "",
                r.get("team") or "", str(r.get("side") or "").lower())
    return (kind, r.get("player") or "", r.get("team") or "",
            r.get("market") or "")


def _seat(r: dict, held) -> float:
    """What a row competes for a seat on: its probability, plus the hold's
    margin when it was on the board last time."""
    p = float(r.get("model_prob") or 0.0)
    return p + HOLD_MARGIN if held and hold_key(r) in held else p


#: A POSTED PICK KEEPS ITS SEAT. Ethan, 2026-09-24, the evening after
#: the hold shipped: "we still have most likely and edge bets
#: dissaperring from the board. there was most likley bets i saw for the
#: packers game yesterday that are no where to be found."
#:
#: The seats are slate-wide: eight a market across a whole NFL week. On
#: Wednesday the books had priced Thursday's game and little else, so the
#: Packers picks held the seats; on Thursday the Sunday props arrived,
#: every one three points likelier took a seat (HOLD_MARGIN), and
#: tonight's picks were gone from the board, the shelf and their own game
#: page hours before kickoff. Nothing about those picks had changed.
#:
#: So a pick that was on the board last build keeps its seat while it
#: clears every bar, however many likelier picks arrive; a newcomer that
#: beats it is added beside it, not swapped in. A pick still leaves for
#: anything about ITSELF — an injury designation, the price past the cap,
#: the model under the floor, the book no longer offering it, its game
#: starting — and those are listed until kickoff (`_earlier`). The market
#: may grow to HELD_SEATS times its seats; past that the weakest posted
#: pick gives way, and says so.
HELD_SEATS = 2


#: A POSTED PICK IS LOCKED UNTIL KICKOFF. Ethan, 2026-09-25, the day
#: after HELD_SEATS shipped: "it still seems like picks on the most likley
#: board and page are dissapearing and new props are replacing them. we
#: cant let that be a plroblem ever ever ever."
#:
#: The seat hold stopped newcomers pushing a pick off; a posted pick still
#: left the moment it failed ANY bar on a later build. And this board picks
#: its numbers near the bars on purpose — the likeliest rung no heavier
#: than -250 is the one nearest -250 — so the commonest exit was a price
#: tick: -245 to -255 and the pick was gone, when the market moving toward
#: it is the book agreeing with it. The model easing a point under the
#: floor, one refresh with no book quoting it, a Questionable tag, the
#: market's seat ceiling: all of them took a pick a reader had seen.
#:
#: Now only a HARD exit removes a posted pick: its game started, or the
#: player is ruled Out / Doubtful / inactive — the bet cannot be made as
#: posted. Anything else (`lock_note` names each) keeps it on the board
#: exactly as it went up — its number, its price, its chance — with a line
#: saying what has changed since. The bars decide what is POSTED; nothing
#: but the game and the player's availability decides what is TAKEN DOWN.
#: The journal already holds the posted row (`ledger.log_most_likely`), so
#: the board and the record now say the same thing until the game.
PLAYABLE_STATUSES = ("questionable", "probable", "day-to-day", "day to day", "gtd")


def hard_exit(why: str) -> bool:
    """Is this a reason a POSTED pick may leave the board? Its game has
    started, or its player is ruled out (not merely questionable)."""
    lw = str(why or "").strip().lower()
    if "under way" in lw or "already been played" in lw or "game started" in lw:
        return True
    if lw.startswith("listed "):
        status = lw[len("listed "):].split(" —")[0].split(" -")[0].strip()
        return status not in PLAYABLE_STATUSES
    return False


def lock_note(why: str, now=None, then=None) -> str:
    """What has changed since a locked pick went up, in the reader's words.

    ``now`` and ``then`` are the model's chance at the posted number today
    and when it went up (`_prob_at`); with them the note says the numbers
    rather than "eased under 55%" beside a tile still reading the old one
    (Ethan, 2026-09-25: "How can we display our model is saying this has
    a 71% chance too hit but then say it went under 55% in the other spot.
    Which number do I trust?")."""
    lw = str(why or "").strip().lower()
    # TODAY'S CHANCE UNDER THE BAR IS THE NEWS, whatever refusal the build
    # recorded for the prop (which can be about another number).
    if now is not None and then is not None and float(now) < MIN_PROB:
        return (f"Our chance at this number is now {round(float(now) * 100)}%, down from "
                f"{round(float(then) * 100)}% when it went up — under the "
                f"{round(MIN_PROB * 100)}% a new pick needs. It stays tracked and graded as posted, "
                "in “Our chance has dropped” below the board.")
    if "floor" in lw or lw == "no probability":
        if now is not None and then is not None:
            return ("The books now hang this stat at another number; this is the one we posted, "
                    "and its chance is as shown.")
        return (f"Our chance has eased under {round(MIN_PROB * 100)}% since this went up. "
                "It stays on the board as posted.")
    if lw.startswith("heavier than"):
        return (f"The price has moved past −{abs(HEAVIEST_PRICE)} since this went up — "
                "the books like it more now. Shown at the price we posted.")
    if lw.startswith("listed "):
        return f"Now {why.split(' —')[0].lower()} — check his status before kickoff."
    if ("no real" in lw or "no book" in lw or "no longer offered" in lw
            or "could not have posted" in lw or "could post" in lw or "price is missing" in lw):
        return "No book is quoting this number right now. Shown at the price we posted."
    if "disagrees with" in lw:
        return "The market has moved away from our number since this went up."
    if "number moved" in lw:
        return "The books have moved the line since this went up. This is the number we posted."
    if "likelier pick" in lw:
        return ""
    return f"Changed since this went up: {reader_reason(why)}."


def _prob_at(row: dict | None, market: str, side, line, fits=None):
    """The model's chance for (side, line) off a prop's CURRENT row — the
    derivation `rungs` prices a ladder number with — or None."""
    if not row or line is None:
        return None
    try:
        line = float(line)
    except (TypeError, ValueError):
        return None
    pre = (row.get("rung_probs") or {}).get(f"{line:g}")
    if pre is not None:
        p_over = float(pre)
    else:
        p_over = display_prob(market, row.get("projection"), line,
                              row.get("recent_values"), fits=fits)
        if p_over is None:
            try:
                mu, sd = float(row.get("projection")), float(row.get("proj_std") or 0)
            except (TypeError, ValueError):
                return None
            if sd <= 0:
                return None
            from .statmath import prob_over
            anchored = _anchored_mean(row, sd)
            p_over = prob_over(line, anchored if anchored is not None else mu, sd)
    p = 1.0 - float(p_over) if _side(side) == "under" else float(p_over)
    return round(p, 4)


def _locked(h: dict, why: str, stamp: str, now_prob=None) -> dict:
    """A posted pick carried forward as it went up — at TODAY's chance.

    The number, the price and the book stay as posted; the chance does
    not. ``now_prob`` is the model's chance at the posted number off this
    build (`_prob_at`), and it replaces the posted one on the row so every
    reader of `model_prob` — the tile, the tier, the order, the note —
    says today's number; `first_prob` keeps the one it went up at."""
    r = dict(h)
    r.pop("out_at", None)
    r.pop("out_why", None)
    then = h.get("first_prob", h.get("model_prob"))
    if now_prob is not None:
        r["first_prob"] = then
        r["model_prob"] = round(float(now_prob), 4)
    r["locked"] = True
    r["lock_why"] = why
    r["lock_note"] = lock_note(why, now=now_prob, then=then if now_prob is not None else None)
    r["locked_at"] = h.get("locked_at") or stamp
    return r


def _posted(r: dict, held) -> bool:
    """Was this pick on the board last build (not a ghost held out)?"""
    if not held:
        return False
    h = held.get(hold_key(r))
    return h is not None and not h.get("out_at")


def _same_number(side, line, prefer) -> bool:
    """Is (side, line) the number ``prefer`` — one (side, line) — names?"""
    if not prefer:
        return False
    try:
        return (str(side or "").lower() == str(prefer[0] or "").lower()
                and abs(float(line) - float(prefer[1])) < 1e-9)
    except (TypeError, ValueError):
        return False


def _cut_players(rows: list, limit: int, per_market: int = PER_MARKET,
                 held=None) -> list:
    """The player rows the board keeps: each market's best `per_market`
    — seats no other market can take — then the best of the rest up to
    `limit`, probability order.

    ONE MARKET NEVER COSTS ANOTHER (Ethan, 2026-09-14: "If I'm having an
    issue seeing a certain category of props, to make those props show
    you should not be affecting another category of props"). Until today
    the kept rows were cut back to `limit` in probability order ACROSS
    markets. With five NFL markets at eight seats that never bound; the
    sixth market (passing touchdowns) joined the board this morning, and
    the cut would have taken the eight seats back from whichever market
    priced lowest — passing yards, the one Ethan had just asked for. The
    per-market seats are guaranteed; `limit` is the back-fill target.
    See docs/ONE_MARKET_NEVER_COSTS_ANOTHER.md.

    ``held`` is the hold's index of last build's rows: a row in it
    competes for its seat at HOLD_MARGIN over its probability.
    """
    rows = sorted(rows, key=lambda r: -_seat(r, held))
    kept, taken = [], {}
    for r in rows:
        m = r.get("market") or ""
        if taken.get(m, 0) < per_market:
            taken[m] = taken.get(m, 0) + 1
            kept.append(r)
    # A POSTED PICK KEEPS ITS SEAT (HELD_SEATS): the ones the seats above
    # did not reach come back beside them, strongest first, up to the
    # market's ceiling.
    if held:
        chosen = {id(r) for r in kept}
        for r in rows:
            m = r.get("market") or ""
            if (id(r) not in chosen and _posted(r, held)
                    and taken.get(m, 0) < per_market * HELD_SEATS):
                taken[m] = taken.get(m, 0) + 1
                kept.append(r)
                chosen.add(id(r))
    if len(kept) < limit:
        chosen = {id(r) for r in kept}
        kept += [r for r in rows if id(r) not in chosen][:limit - len(kept)]
    return sorted(kept, key=lambda r: -float(r.get("model_prob") or 0.0))


#: Game rows the board carries per sport, beside LIMIT player rows.
#: Five cards a game across a sixteen-game Sunday is eighty rows of
#: 50-60% leans, which would push every player row off a board capped
#: at forty; the two kinds are capped apart so neither crowds the other.
GAME_LIMIT = 20

#: SHOULD THIS BOARD GET REAL MONEY? Ethan, 2026-08-30: "we need to
#: figure out if we are gonna put real money on these bets and record
#: them and if so we need them to be in the recommended bets."
#:
#: Measured rather than argued. Both orderings bet the TOP QUARTER of the
#: same qualifying pool — same rows available, same stakes, same prices,
#: same vig — so the only difference is which of them get the money:
#:
#:     market      picked by     bets   hit      ROI    95% interval
#:     receptions  likelihood      76  65.8%   +11.7%   [-8.7%, +32.1%]
#:     receptions  edge            76  53.9%    +2.4%   [-19.0%, +23.8%]
#:     rec_yds     likelihood      86  54.7%    +3.2%   [-16.9%, +23.3%]
#:     rec_yds     edge            86  54.7%    +3.9%   [-16.2%, +24.0%]
#:
#: The receptions result is the best evidence this thesis has, and it is
#: not proof: the hit-rate gap is +11.9 points at z = +1.5, and every ROI
#: above carries about ten points of standard error on 76-86 bets. One
#: market suggests likelihood-ranking is better, one shows no difference
#: at all, and both sit on fourteen weeks of a single season.
#:
#: SO THIS BOARD IS NOT JOURNALED, and the reason is specific rather than
#: cautious. Ranking says who hits; it does not say whether the price is
#: worth taking. A -260 near-lock can be correctly ranked first and still
#: lose money, because being right 70% of the time at a price that needs
#: 72% is a losing bet made confidently. This board deliberately ignores
#: EV when ordering, so wiring it to the journal as it stands would stake
#: negative-EV locks with conviction.
#:
#: What would settle it: the same table on two or three more seasons of
#: closes, and on more than one market. `engine.yardagefit --real` prints
#: it, and the harvest is the binding constraint, not the code.

#: Below this a market cannot sort its own board and has no business
#: claiming who will hit. 0.5 is a coin flip; this is the floor at which
#: an ordering is worth showing a reader.
MIN_RANK_AUC = 0.60

#: A price outside this is a stale quote or a market we have mis-keyed,
#: not a likelihood — the same guard the touchdown watch uses.
SANE_ODDS = (-100000, 2000)

#: How far a game's MONEYLINE and its own SPREAD may disagree about who
#: wins before the pair is not a price any book has posted.
#:
#: Ethan, 2026-09-08, with two screenshots side by side — his book and
#: our page: "Also the money lines we are showing on the most likley
#: page is completely wrong." His book had DAL -3 and DAL -162 at the
#: Giants; our board had NYG ML -218 as a 66% favourite. The two numbers
#: on OUR OWN card disagreed about which team was going to win, and
#: nothing looked at them together. It is the third report of this class
#: (2026-09-03, twice: "The lines on the most likely best bet page ...
#: are completely wrong so we are giving bad bets" and "A lot of the
#: money lines and shit are wrong"), and the first two were answered
#: with freshness stamps — which say a price is OLD and cannot say a
#: price is WRONG.
#:
#: MEASURED, on this box's 1,424 stored NFL closes with both a closing
#: moneyline and a spread (2026-09-08). For each, the book's de-vigged
#: P(home) against the same book's spread read through the sport's own
#: win curve (`gamebets.spread_win_prob`):
#:
#:     median gap  0.036      99th  0.102      99.9th  0.113
#:     the largest disagreement in five seasons          0.118
#:     games where the two named a different favourite   0 of 1,424
#:
#: A real book keeps its two markets within about a tenth of each other
#: and never crosses over. So 0.15 is above every disagreement five
#: seasons of closes contain, and a pair past it is not a price — it is
#: two snapshots of different games, or one market read against the
#: wrong side. Ethan's Giants card scores 0.199 and is refused; his
#: Vikings card scores 0.083 and is NOT — that one is a price that is
#: merely old, which this bar cannot see and does not pretend to.
SPREAD_COHERENCE = 0.15

#: The heaviest price the board will show. Ethan, 2026-09-01, reading
#: the likely book's first settled night (52/73 won, ROI -11.2%, rows
#: at -800/-1200/-1800): "i dont wanna be betting on -1200 or -1800
#: bets. the point of the most likley page is to push bets based of
#: game data, game script, weather, offense, defense... not just
#: grabbing random -1200 props. and thats for every sport." The model
#: WAS using all of that — the probabilities were calibrated (claimed
#: 75%, landed 71%) — but the gate never asked whether a row was a bet
#: a human would want, and baseball's most-likely outcomes are mostly
#: heavy-juice failures to do things. At -250 a bet needs 71.4% to
#: break even; past it, "most likely" stops being a pick and becomes
#: chalk.
HEAVIEST_PRICE = -250

#: How many player rows the board back-fills to per sport before it
#: stops being a ranking and starts being a dump. Not a cap on the
#: per-market seats: a sport that ranks more than LIMIT / PER_MARKET
#: markets shows every market's PER_MARKET (see `_cut_players`).
LIMIT = 40

#: A model probability below this is not "likely" by any reading, whatever
#: it is ranked against.
#:
#: RAISED FROM 0.30 ON 2026-09-06, Ethan's call, after the paper book's
#: first honest scoreboard. 402 settled rows, and the 45-60% band was
#: 184 of them at -7.68%:
#:
#:     band        n    said     hit      roi
#:     45%-60%    184   53.3%   49.5%   -7.68%
#:     60%-75%    154   66.1%   71.4%   +3.91%
#:     75%-101%    64   84.8%   76.6%   -6.00%
#:
#: THE ARITHMETIC THAT DOES NOT DEPEND ON THE SAMPLE. A 53.3% pick at
#: -110 needs 52.4% to break even. The margin is nine tenths of a point,
#: which is inside every error bar this model has — `selectionfit`
#: measures a 9-10 point over-claim on the bets we choose. A band that
#: thin cannot be bet into a vig, and a 45-60% row is not "most likely"
#: by any reading of the words on the page.
#:
#: WHAT THE SAMPLE DOES NOT SAY, recorded because it was nearly quoted as
#: if it did. Dropping that band takes the settled record to +1.00%, at
#: +/-9.5%. Cutting the SAME 402 rows by market instead of by band gives
#: -2.15% for the ranked shelves against -3.90% for the unranked ones.
#: Two cuts of one sample, disagreeing in sign, both inside noise. The
#: ROI evidence establishes nothing; the naming argument above is the
#: whole case.
#:
#: WHAT IT COSTS, PUT TO ETHAN BEFORE IT SHIPPED AND ACCEPTED. The
#: 45-60% band IS the game-lines shelf: spread (84 rows, said 55.0%),
#: total (71, 55.1%) and team_total (35, 54.7%) are 190 rows against the
#: band's 184. So this floor removes about half of the shelf he asked
#: for on 2026-09-02 — "I don't see spread bets, I don't see anything
#: like that I just asked you to do" — and shipped as labelled leans.
#: Those three are also exactly the markets `GAME_RANK_MEASURED` puts at
#: 0.49, a coin flip: the record and the ranking measurement agree about
#: which shelves these are. He was shown the collision and chose 0.55
#: everywhere rather than scoping it to props.
MIN_PROB = 0.55

#: THE FLOOR WHEN THE ALTERNATIVE IS AN EMPTY PAGE. Ethan, 2026-09-08:
#: "Also I don't want an empty boar either we need to have picks period."
#:
#: He set MIN_PROB to 0.55 himself two days earlier, knowing it costs
#: about half the game-lines shelf (see above). Both instructions stand,
#: and they only look contradictory if the board has one bar. It has two
#: now: 0.55 is still what it takes to be called a pick, and this is the
#: floor for the rows shown when NOTHING clears that — labelled as below
#: the bar, ordered by probability, never journalled and never staked.
#:
#: WHAT THIS DOES NOT RELAX, deliberately, because the difference is the
#: whole design. A refusal on this board is one of two kinds:
#:
#:   * the number is WRONG or unknown — a proxy price, a price no book
#:     could post, a stale quote, a probability that disagrees with the
#:     market past MAX_CREDIBLE_EDGE, a moneyline that contradicts its
#:     own spread, a player held for injury. Those stay. Showing a row
#:     we believe is mispriced is how the last three weeks of wrong
#:     lines happened, and "we need picks" is not a reason to publish a
#:     number we think is false.
#:   * the bet is not ATTRACTIVE enough — this floor, and HEAVIEST_PRICE.
#:     Those are product judgements, and a product judgement that empties
#:     the page is his call to overrule.
#:
#: HEAVIEST_PRICE IS NOT RELAXED EITHER, even though it is the second
#: kind. The -250 cap exists because Ethan complained about exactly this
#: on 2026-09-01 — "just grabbing random -1200 props" — so widening it to
#: fill a quiet night would answer today's instruction by re-creating the
#: bug he reported. The floor is what empties a board; the cap is what he
#: asked for.
#:
#: 0.40 rather than lower: below it "most likely" is not a caveat away
#: from honest, it is the wrong words on the page. And the band this
#: admits is measured at a loss (45-60% went -7.68% over 184 settled
#: rows) — which is precisely why these rows ship labelled, unstaked and
#: out of the book.
RESERVE_MIN_PROB = 0.40

#: How many reserve rows ship PER EMPTY SHELF. A page that normally
#: carries forty and falls back to forty looks like an ordinary night; a
#: handful reads as what it is — the closest things to the bar on a
#: shelf that cleared it with nothing.
#:
#: Per shelf rather than per board, since 2026-09-08. The reserve fired
#: only when the WHOLE board came out empty, and Ethan's report was not
#: that — "We have barely any moneylines show and barley and touchdowns
#: shown" is a board carrying player props with two of its three shelves
#: bare. A shelf with nothing on it is the empty page, for anyone who
#: came to the board for that shelf.
RESERVE_LIMIT = 12

#: What a reserve row says about itself, on the row and on the card.
#:
#: The sentence names the SHELF the row is filling, because the reserve
#: is per shelf: a board carrying twenty player props and a reserve
#: moneyline cannot truthfully say "nothing on this slate cleared it",
#: and the label is the entire reason these rows are allowed to ship.
RESERVE_SHELF_WORD = {"td": "touchdown row", "prop": "player prop",
                      "game": "game line"}


def reserve_note(kind: str = "", seated: int = 0) -> str:
    """The label a reserve row carries, naming its own shelf.

    TWO SENTENCES, because the shelf is topped up rather than only
    filled. "No touchdown row on this slate cleared it" is false the
    moment one did — and a shelf holding one real row plus eleven
    reserve rows is exactly that case. The label is the entire reason
    these rows are allowed to ship, so it does not get to overstate by
    one row any more than by a whole board.
    """
    what = RESERVE_SHELF_WORD.get(kind or "", "")
    if not what:
        return ("Below the board’s usual bar — shown because nothing on "
                "this slate cleared it. Ranked, not recommended.")
    if seated:
        return (f"Below the board’s usual bar — shown because only "
                f"{seated} {what}{'' if seated == 1 else 's'} on this slate "
                f"cleared it. Ranked, not recommended.")
    return (f"Below the board’s usual bar — shown because no "
            f"{what} on this slate cleared it. Ranked, not recommended.")


#: The board-wide wording, kept as the name the page and the tests knew.
RESERVE_NOTE = reserve_note()


def _floor(override) -> float:
    """The likelihood floor in force: MIN_PROB, or a reserve override."""
    return MIN_PROB if override is None else float(override)

#: How far the displayed probability may sit from the book's own de-vigged
#: number before the row is refused — the same bar `engine.betting` uses,
#: for the same reason.
from .betting import MAX_CREDIBLE_EDGE                     # noqa: E402


def _credible(prob, fair) -> bool:
    """Is this probability defensible against the book's own number?"""
    if fair is None or prob is None:
        return True
    try:
        return abs(float(prob) - float(fair)) <= MAX_CREDIBLE_EDGE
    except (TypeError, ValueError):
        return True


def engine_credible(row: dict) -> bool:
    """The ENGINE's own credibility test, on the engine's own numbers.

    THE CHECK ABOVE CANNOT CATCH WHAT THIS CATCHES, and the reason is
    arithmetic rather than an oversight. `betting.temper_edge` shrinks
    the published claim toward the market:

        hit = fair + shrink x (raw - fair)

    so `hit - fair` is at most `shrink x (raw - fair)`, and with shrink
    at or below 0.5 a row needs a RAW disagreement above 20 points
    before the shrunk gap can exceed the 10-point cap. Every row with a
    raw gap between 10 and 20 points — exactly the band the engine
    calls a modelling or data error — sails through a check made on the
    shrunk number. The check looked like a guard and could not fire on
    the rows it existed for.

    Ethan found one on a phone, 2026-09-02: Zack Gelof, UNDER 4.5 total
    bases at -200, "MODEL 73%", projection 1.7, none of his last ten
    games clearing 4.5 — sitting on the Most Likely board while its own
    card printed `betting.IMPLAUSIBLE_EDGE_REASON` in red. The model was
    RIGHT: P(under 4.5) on a 1.7 projection is about 96%, and 73% is
    what 96% becomes after being shrunk toward a market number that
    cannot be a real price for that line. The board then ranked the
    shrink artefact as a top pick.

    So this asks what the engine asked: is the RAW claim within
    MAX_CREDIBLE_EDGE of the book's de-vigged number? A row that has no
    raw claim (the touchdown chain, game cards) answers True and is
    judged by `_credible` on what it does carry.
    """
    # NOT ON A ROW RANKED ON THE MARKET'S NUMBER. Ethan, 2026-09-08:
    # "we have player props just barely any money lines." A football
    # moneyline row ranks on the book's de-vigged number (GAME_RANK_MARKET)
    # because that number sorts winners better than the model's; the
    # row's claim IS the market's, and this bar was still refusing it
    # whenever the model's own rating sat more than ten points away.
    # Measured 2026-09-08 on this box's NFL closes (`gamerank
    # --raw-bar`, 1,356 quoted games on the ratings the build ships):
    #
    #     favourites the board could carry (fair >= 55%, price >= -250)   681
    #     …refused here for the model's raw disagreement                   207   30%
    #     the market's number on the rows kept:     claimed 61.4%  landed 64.3%
    #     the market's number on the rows refused:  claimed 61.4%  landed 62.3%
    #     refused minus kept, 95% by game                        [-9.8%, +5.7%]
    #     by size of the disagreement: 10-15 pts +2.2 · 15-20 -0.6 · 20-30 -1.9
    #
    # and college the same day (2,729 games): 1,066 eligible, 401 refused
    # (38%); kept claimed 62.2% landed 60.2%; refused claimed 64.0%
    # landed 63.8%; 95% [-4.3%, +7.8%].
    #
    # The market lands where it claims on the games the model disputes,
    # at every size of dispute — which is what `gamecal` had already
    # said of the same model from the other side (the slope of its
    # disagreement against the close, -0.057 +/- 0.135: nothing). A bar
    # that removes three rows in ten and changes nothing measurable is
    # not a bar; it is a shelf a third empty. The model's own rating
    # stays on the row (`engine_raw_prob`) and the note prints it.
    if row.get("prob_source") == "market":
        return True
    # NOR ON A RUNG THAT CARRIES THE MARKET'S CLAIM. A rung priced from
    # the sharp book's own pair, or on the market's centre with the
    # model's width (`_anchored_mean`), is not the raw model's claim at
    # the main line — that claim is exactly what the anchor set aside.
    # Ethan, 2026-09-15: one passing-yards prop; the raw passing model
    # sat 15-35 points above the book for most quarterbacks, so this bar
    # refused the row before any rung could be read.
    if row.get("rung") == "alt" and row.get("prob_source") in ("sharp", "anchored"):
        return True
    # ONLY the engine's pre-shrink claim. This board's own `raw_prob` is
    # the display number before the mixture, which is a different
    # quantity measured against a different thing — falling back to it
    # would refuse honest rows for a disagreement the engine never had.
    raw, fair = row.get("engine_raw_prob"), row.get("fair_prob")
    if raw is None or fair is None:
        return True
    try:
        return abs(float(raw) - float(fair)) <= MAX_CREDIBLE_EDGE
    except (TypeError, ValueError):
        return True


#: The college touchdown ranking, measured by engine.cfbtdfit over
#: 29,047 player-weeks. Shipped like the NFL constants because it was
#: measured the same way — by a person, against this repo's own replay —
#: and previously the CFB board wore the NFL's 0.721 by accident:
#: `from_watch` read RANK_AUC["anytime_td"] with no idea whose chain
#: built the row.
CFB_TD_AUC = 0.675


def rank_auc(sport: str, market: str):
    """The measured ranking AUC for this market, or None.

    THREE SOURCES, IN TRUST ORDER. The fitted store first — written by
    engine.rankfit on the box whose logs it walked, which is the only
    number that can exist for MLB at all (its logs never leave the
    droplet). Then the shipped constants: NFL's hand-measured five and
    the college touchdown figure. A market in none of them has no
    measurement, and no measurement means no shelf — the founding rule
    of this board, now enforced per sport instead of assuming every
    caller was the NFL.
    """
    from .rankfit import rank_auc as _fitted
    got = _fitted(sport, market)
    if got is not None:
        return got
    if market in GAME_MARKETS:
        return GAME_RANK_AUC.get(sport, {}).get(market)
    if sport == "nfl":
        return RANK_AUC.get(market)
    if sport == "cfb" and market == "anytime_td":
        return CFB_TD_AUC
    return None


def rankable(market: str, sport: str = "nfl") -> bool:
    """Has this market been SHOWN to rank, not merely modelled?"""
    return (rank_auc(sport, market) or 0.0) >= MIN_RANK_AUC


def measured_auc(sport: str, market: str):
    """The measured figure for a GAME market whether or not it cleared
    the floor: the box's own store first (gamerank --save writes
    sub-floor numbers too), then the shipped table. None = never
    measured, which is a different fact from measured-and-failed."""
    from .rankfit import rank_auc as _fitted
    got = _fitted(sport, market)
    if got is not None:
        return got
    return GAME_RANK_MEASURED.get(sport, {}).get(market)


#: The word a lean note uses for each market, plural.
_GAME_WORDS = {"spread": "spreads", "total": "totals",
               "team_total": "team totals", "moneyline": "moneylines"}


def _sane(odds) -> bool:
    """In range for this board AND a price a book could have posted.

    SANE_ODDS bounds the outside; it says nothing about the dead zone in
    the middle, so -97 used to pass — and then win the shop, because it
    pays better than the -105 it was corrupting. See odds.is_quotable.
    """
    from .odds import is_quotable
    try:
        o = int(odds)
    except (TypeError, ValueError):
        return False
    return SANE_ODDS[0] <= o <= SANE_ODDS[1] and is_quotable(o)


#: Game markets a sportsbook actually posts a two-sided price for, and
#: therefore the ones that must be able to name the book posting the side
#: taken. `team_total` is deliberately absent: it is derived from the
#: game total and the spread, so no book quotes it and none can be named
#: — `pipeline._finish_bet` says exactly that in its own comment.
BOOK_POSTED_GAME_MARKETS = ("moneyline", "spread", "total")

#: Sports whose game cards are KNOWN to name the book posting each side,
#: and therefore the ones where a missing name is a defect rather than a
#: feature that has not been built.
#:
#: `pipeline._finish_bet` fills `home_ml_book`/`away_ml_book` and their
#: spread and total twins off the `Game`, and `cfb_build._book_for_side`
#: does the same for college. `engine.mlb.models.MLBGame` carries no such
#: field at all, so an MLB game card has never had a book to give — and
#: holding it to this bar tonight would empty a shelf that is in season,
#: on the strength of a defect I have not measured there. It is the same
#: defect and it deserves the same fix; it does not deserve to be
#: discovered by Ethan on a live board. Task #206.
BOOK_NAMED_SPORTS = ("nfl", "cfb")

def admissible(row: dict, floor=None) -> str:
    """"" if this row belongs on the board, else why it does not.

    ``floor`` overrides MIN_PROB for the reserve pass and NOTHING else —
    see RESERVE_MIN_PROB for why exactly one of these refusals is allowed
    to move and the rest are not.

    ONE BAR, APPLIED TO EVERY ROW, WHATEVER BUILT IT. `build` takes rows
    from two makers — `from_prop` for the priced prop board and
    `from_watch` for the touchdown chain — and only the first one
    enforced anything. `build`'s own comment claimed "one board means one
    bar" while applying that bar on one of its two paths, which is this
    codebase's most-repeated bug: a rule announced in prose and enforced
    in one place.

    IT MATTERED MOST WHERE IT WAS CHECKED LEAST. When this was written,
    college football's entire likelihood board was watch rows — cfb_build
    called `build([], rows, watch)` with no props at all — so every
    refusal added to this module protected the NFL prop board and left
    the whole college board ungated. Measured 2026-08-30, all of these
    published: an 8% row on a board whose floor is 30%, a -97 price no
    book can post, and a `proxy` quote the model invented.

    THAT SENTENCE IS NO LONGER TRUE, and it is left standing above with
    its tense corrected rather than deleted, because it is the reason
    this function exists. cfb_build passes its props and its game cards
    now, so college answers to all three makers. What has not changed is
    the lesson: a bar applied on one of several paths is not a bar.

    THE FLOOR IS ABOUT THE WORD, NOT THE SPORT. MIN_PROB says a
    probability below it "is not likely by any reading" — that is a claim
    about what the page is called, so a college board that empties under
    it is a board honestly reporting it has nothing likely tonight,
    rather than one relabelling 8% as likely.
    """
    prob = row.get("model_prob")
    if prob is None:
        return "no probability"
    if float(prob) < _floor(floor):
        return "under the likelihood floor"
    if (row.get("book") or "").lower() == "proxy":
        # A fabricated price. `from_prop` catches this as `has_market`;
        # watch rows carry no such key and the book name is the tell.
        return "no real market price"
    if not _sane(row.get("odds")):
        return "price a book could not have posted"
    # THE PRODUCT REFUSAL (Ethan, 2026-09-01 — see HEAVIEST_PRICE): the
    # board shows who's most likely to DO something, priced like a bet.
    #
    # AN UNDER IS ADMITTED AGAIN, and the history is worth keeping. The
    # ban went in on 09-01 beside the price cap, aimed at the first MLB
    # night's rows — unders at -300 to -1800, "the most likely outcome
    # of most baseball nights" — and the CAP is what answered that
    # complaint: every one of those rows is heavier than -250. The
    # under rule swept the rest out with them, and a day later Ethan,
    # 2026-09-02: "all I see us is doing overs, but we have no unders
    # ... there is more bets that we can salvage." The measurement
    # agrees with him: an AUC is symmetric, so a market whose over
    # ranks at 0.77 ranks its under at 0.77 — 1 - P(over) is the same
    # ordering read from the other end (pinned in
    # tests/test_likely_gamelines.py). `from_prop` shows the under's
    # own probability; this bar holds it to the same cap, floor and
    # credibility as an over.
    if int(row["odds"]) < HEAVIEST_PRICE:
        return f"heavier than {HEAVIEST_PRICE} — chalk, not a pick"
    if not _credible(prob, row.get("implied_prob")):
        return "the shown probability disagrees with the market by more than we credit"
    # EACH REFUSAL NAMES ITS OWN NUMBER. Three different questions are
    # asked of three different probabilities here, and until 2026-09-08
    # two of them answered in sentences a reader could not tell apart —
    # "disagrees with the market by more than we credit" and "the model
    # and the market disagree by more than we credit", the same words in
    # a different order. On the droplet's census they printed as two
    # lines splitting 98 refused rows between them, and the one thing a
    # census exists to say — WHICH bar killed the board — was the one
    # thing those two lines could not. They say which number now: the
    # SHOWN probability, the model's OWN READ, the RAW claim.
    #
    # A row that RANKS on a market number still carries the model's own
    # read as its card, and a model that disagrees with the book by more
    # than we credit is our error wherever the row is sorted — the
    # Gelof guard, asked of the number the card prints.
    if (row.get("prob_source") in ("market", "sharp") and row.get("win_prob") is not None
            and not _credible(float(row["win_prob"]), row.get("implied_prob"))):
        return "the model's own read disagrees with the market by more than we credit"
    # …and the same question asked of the claim BEFORE the shrink, which
    # is the only place a big disagreement is still visible. See
    # `engine_credible`.
    if not engine_credible(row):
        return "the raw model claim, before the shrink, disagrees with the market by more than we credit"
    # THE INJURY HOLD, WHICH THIS BOARD NEVER HAD. `rules.apply_rules`
    # holds a Questionable / Doubtful / Out player "until inactives
    # confirm status" — and only the edge board read that decision. This
    # page took the same evaluated row, ignored `recommended`, and had
    # no field carrying the designation at all, so a player ruled out
    # on Friday could top "who is most likely to hit" on Sunday. Ethan,
    # 2026-09-02: "some of them seem weird ... especially the most likely
    # bets." A hold that applies to one board and not the other is not a
    # hold; it is the announced-in-prose, enforced-in-one-place bug this
    # module's own docstring names.
    status = str(row.get("injury_status") or "").strip()
    if status:
        return f"listed {status} — held until inactives confirm"
    return ""


def _spread_disagrees(row: dict, sport: str) -> bool:
    """Does this moneyline contradict its own game's posted spread?

    Both numbers are read for the HOME side, so the comparison does not
    depend on which side the card took. False whenever either number is
    missing, or the sport has no registered win curve — an unmeasurable
    row is not a refused one.
    """
    from .gamebets import spread_win_prob
    spread = row.get("game_spread")
    fair = row.get("fair_prob")
    if spread is None or fair is None:
        return False
    from_spread = spread_win_prob(sport, spread)
    if from_spread is None:
        return False
    try:
        fair = float(fair)
        # `fair_prob` is the de-vigged number for the side the CARD took.
        home = row.get("home") or ""
        took = row.get("team") or row.get("pick") or ""
        is_home = row.get("pick_is_home")
        if is_home is None:
            is_home = bool(home) and took == home
        from_price = fair if is_home else 1.0 - fair
    except (TypeError, ValueError):
        return False
    return abs(from_price - float(from_spread)) > SPREAD_COHERENCE


def _refuse(census, why: str):
    """Count a maker's refusal and return None.

    THE HALF OF THE FUNNEL THAT WAS NEVER COUNTED. `build`'s census fills
    from `keep`, which only sees rows a maker has already agreed to
    build. Everything the makers themselves turn away — an unmeasured
    market, a proxy price, a conditional, a live game — returned a bare
    None and left no trace, so a board that came out empty because its
    makers refused every row looked exactly like a board with nothing to
    say. On the college card of 2026-09-03 that was 440 prop rows
    refused before the counter could see one of them, and a census that
    reported {}.

    The census is the answer to "why is this board short tonight", and it
    could only ever answer for the rows that got far enough to be asked.
    """
    if census is not None:
        census[why] = census.get(why, 0) + 1
    return None


def _anchored_mean(row: dict, sd: float) -> float | None:
    """The model's width hung on the MARKET's centre, for a sharp-anchored row.

    Ethan, 2026-09-10 and again 2026-09-15: one passing-yards prop on the
    Most Likely board. Measured on the local board: the raw passing model
    ran well above the book (Brissett 0.67, Shough 0.87, Jackson 0.75
    against a −110 main line) — so the main line failed the credibility
    bar, every over rung on the ladder failed it by the same margin, and
    every under rung fell under the floor. One quarterback in a week
    happened to land in the narrow band between the floor and the bar,
    and that was the board.

    The edge board already answers this for the main line: where a sharp
    book quotes, `hit_prob` is the sharp-anchored number and `raw_prob`
    the model's own. The ladder now prices from the same anchor: the
    main line's anchored P(over) fixes where the distribution's centre
    is, the model keeps its width, and each rung is read off that curve.
    Rows the edge board did not anchor keep the model's own centre.
    """
    if not row.get("sharp_anchored") or sd <= 0:
        return None
    try:
        p_side = float(row.get("hit_prob"))
        main = float(row.get("line"))
    except (TypeError, ValueError):
        return None
    if not (0.0 < p_side < 1.0):
        return None
    p_over = p_side if str(row.get("side") or "over").lower() != "under" else 1.0 - p_side
    p_over = min(max(p_over, 0.02), 0.98)
    from statistics import NormalDist
    return main + sd * NormalDist().inv_cdf(p_over)


def _tally(ladder, why: str) -> None:
    """Count a rung's fate for the funnel — see `build`'s per-market ledger."""
    if ladder is not None:
        ladder[why] = ladder.get(why, 0) + 1


def _best_rung(row: dict, market: str, fits=None, floor=None,
               ladder: dict | None = None, prefer=None, lean=None) -> dict | None:
    """The likeliest priced number on the prop's alternate ladder, or None.

    THE CHOICE, over `rungs` below, which is the derivation. This board
    asks "what is most likely", so it takes the highest probability. The
    Pick of the Day asks a different question of the same ladder — what
    clears an EV floor at a price inside an even-money band — and a
    second walk of the ladder to answer it would be a second set of
    probabilities to keep honest. One derivation, two views.

    ``prefer`` lists the (side, line) numbers the board held for this
    prop, in order (see `_held_choice`): while one of them is still among
    the rungs clearing every bar, it is the answer, whatever its
    neighbour did to its price.
    """
    got = rungs(row, market, fits, floor=floor, ladder=ladder)
    if not got:
        return None
    held = _held_choice(row, got, prefer, main_ok=False)
    if held is not None:
        return held
    leaned = _lean_choice(row, got, False, 0.0, lean)
    return leaned if isinstance(leaned, dict) else max(got, key=lambda c: c["prob"])


#: THE MATCHUP READ PICKS THE SIDE, NEVER THE CHANCE. Ethan, 2026-09-25,
#: with the dashboard's "Who could shine" open: "how do we show dalton
#: kincaid, garret willson, and Adonia Mitchell all as breakout candidates
#: but then don't have any most likely bets for them? It doesn't make any
#: sense." Two reasons it happened, both in this module: a prop's row is
#: the likeliest number on EITHER side of its ladder, so a receiver the
#: scan calls a breakout could come out as an under; and the seats are
#: eight a market across a whole NFL week, so his over, clearing every
#: bar, lost its seat to other players' overs.
#:
#: A LEAN (engine/gamescan.leans_from_reads — "over" for a player who
#: could shine, "under" for one who could struggle, in the markets his
#: read points at) chooses among the numbers that ALREADY clear every
#: bar here: the likeliest one on the lean side, when there is one. The
#: probability, the 55% floor, the -250 cap and the credibility bar are
#: untouched — the scan's signals measured no lift over the model
#: (engine/scanfit), so they never move a number. A row that agrees with
#: its read is marked (`scan_read`) and keeps a seat past the caps
#: (`build`, READ_SEATS). A read with nothing on its side that clears
#: says so on its card, with our best number there (`lean_report`).
READ_SEATS = 1


def _side(x) -> str:
    """A row's side as over/under ("yes" is a scorer's over)."""
    s = str(x or "").lower()
    return "over" if s in ("over", "yes") else "under" if s in ("under", "no") else s


def _lean_choice(row: dict, got: list, main_ok: bool, shown: float, lean):
    """The likeliest number on the lean side that clears: a rung, "main",
    or None when the lean side has nothing."""
    if not lean:
        return None
    mine = [c for c in got if _side(c["side"]) == lean]
    main = main_ok and _side(row.get("side")) == lean
    best = max(mine, key=lambda c: c["prob"]) if mine else None
    if best is not None and (not main or best["prob"] > shown):
        return best
    return "main" if main else None


def _pick_brief(r: dict) -> dict:
    """What a read's card says about one board row."""
    return {k: r.get(k) for k in ("player", "team", "market", "market_label", "side", "line",
                                  "odds", "book", "model_prob")}


#: The least chance a no-pick card will call "his likeliest" number —
#: `boardtruth.LONGSHOT_PROB`, the self-check's own bar.
LEAN_BEST_MIN_PROB = 0.20


def _main_candidate(row: dict, side, fits=None):
    """The prop's main number on ``side`` as a rung-shaped candidate —
    {side, line, odds, book, prob} — or None when no bettable book prices
    that side at −250 or better, or the model cannot price the number."""
    line = row.get("line")
    got = _price_at(row, side, line)
    if got is None or got[0] < HEAVIEST_PRICE:
        return None
    p = _prob_at(row, row.get("market") or "", side, line, fits)
    if p is None:
        return None
    return {"side": _side(side), "line": float(line), "odds": got[0], "book": got[1], "prob": p}


def _lean_report(board: list, leans: dict, lean_props: dict, fits=None,
                 why: dict | None = None) -> dict:
    """{(player, team): what his read got} — see `build`'s ``lean_report``.

    "pick": a board row on the read's side (the likeliest, if several).
    "other_side": the board carries him only on the other side — the
      model's likeliest number disagrees with the read, and the card says
      so rather than hiding either.
    "none": nothing of his on the board; ``best`` is our likeliest number
      on the read's side at a price the board would take (−250 or better),
      under the floor — or None when not one of his numbers is priced.
    """
    want: dict = {}
    for (player, team, _market), lean in leans.items():
        want.setdefault((player, team), lean)
    rows: dict = {}
    for r in board:
        if r.get("kind") == "game":
            continue
        rows.setdefault((r.get("player"), r.get("team")), []).append(r)
    out = {}
    for k, lean in want.items():
        mine = [r for r in rows.get(k, []) if (k[0], k[1], r.get("market") or "") in leans]
        agree = [r for r in mine if _side(r.get("side")) == lean.get("side")]
        if agree:
            out[k] = {"status": "pick", "pick": _pick_brief(
                max(agree, key=lambda r: float(r.get("model_prob") or 0)))}
            continue
        if mine:
            out[k] = {"status": "other_side", "pick": _pick_brief(
                max(mine, key=lambda r: float(r.get("model_prob") or 0)))}
            continue
        best = None
        # WHY THE BOARD SAID NO, in the board's own words (`build`'s
        # why_left). Without it a card read "no Most Likely pick" beside a
        # 72% over — Jahmyr Gibbs, 2026-09-25 — and the reader could not
        # tell which bar the number failed.
        refused = ("no book has a main line on it to price against"
                   if lean_props.get(k) and not any(r.get("has_market") for r in lean_props[k])
                   else next((reader_reason(w) for w in (
                       (why or {}).get(("prop", k[0], k[1], row.get("market") or ""))
                       for row in lean_props.get(k, [])) if w), ""))
        for row in lean_props.get(k, []):
            # The same gate `from_prop` puts on the ladder: a prop with no
            # real main-line price never reaches its rungs.
            if not row.get("has_market"):
                continue
            # HIS MAIN LINE IS A CANDIDATE TOO. Only the alternate rungs were
            # read here, and the rungs that survive the credibility bar can
            # be only the far ones — Ladd McConkey, 2026-09-25, "his likeliest
            # over … is Over 109.5 Receiving Yards · +700 · 4%" beside a main
            # line near 45. Ethan: "Why is it talking about a plus 700 … and
            # over 109 yards? Are we pulling this correct line that is
            # actually reasonable?" The line was real (an alt rung); calling
            # it his likeliest was not.
            cands = list(rungs(row, row.get("market") or "", fits, floor=0.0))
            main = _main_candidate(row, lean.get("side"), fits)
            if main is not None:
                cands.append(main)
            for c in cands:
                # A LONGSHOT IS NOBODY'S LIKELIEST. The main line above did
                # not stop it on the droplet (2026-09-25 self-check:
                # "Judkins over 109.5 +900 at 1%", Montgomery at 0%): under
                # LEAN_BEST_MIN_PROB the card says none of his numbers is
                # one we would stand behind, which is the true sentence.
                if float(c["prob"]) < LEAN_BEST_MIN_PROB:
                    continue
                if _side(c["side"]) == lean.get("side") and (best is None or c["prob"] > best["prob"]):
                    best = dict(c, market=row.get("market"),
                                market_label=row.get("market_label") or row.get("market"))
        out[k] = {"status": "none", "priced": bool(lean_props.get(k)), "refused": refused,
                  "best": None if best is None else {
            "market": best["market"], "market_label": best["market_label"], "side": best["side"],
            "line": best["line"], "odds": best["odds"], "book": best["book"],
            "model_prob": round(float(best["prob"]), 4)}}
    return out


def _held_choice(row: dict, got: list, prefer, main_ok: bool):
    """"main", a rung from ``got``, or None: the first of the numbers the
    board held (``prefer``, in order — the number the pick went up at,
    then the one it showed last) that still clears every bar.

    THE NUMBER IT WENT UP AT COMES FIRST. A held pick whose number ticks
    past a bar falls back to another rung; when the first number clears
    again the pick returns to it rather than staying wherever the tick
    left it — the pick is the one that was posted."""
    for p in prefer or ():
        if main_ok and _same_number(row.get("side"), row.get("line"), p):
            return "main"
        for c in got:
            if _same_number(c["side"], c["line"], p):
                return c
    return None


def rungs(row: dict, market: str, fits=None, floor=None,
          ladder: dict | None = None) -> list:
    """EVERY priced number on the prop's alternate ladder that clears the
    floor and its own credibility bar, best price per (line, side).

    THE LADDER IS WHERE "MOST LIKELY" IS FOR SALE. A main line is hung
    where the book thinks the coin is fair, so the calibrated number at
    it sits near 50% and a board asking for 55% at no heavier than -250
    had nothing to show (2026-09-07: 303 rows, 215 under the floor,
    none shown). The same books hang the same stat at other numbers —
    a back over 40.5 at -220 rather than over 62.5 at -110 — and those
    are the rows Ethan asked for: "whatever gives us props and picks
    every single day".

    Every rung is held to the bars the main line is held to, at the
    rung's own numbers: the mixture's probability AT THAT LINE (or the
    sharp book's de-vigged fair there when the market has no fit), the
    55% floor, the -250 cap, a price a book could post, and the
    credibility bar against the rung's own de-vigged price. The best
    price per (line, side) across the bettable books is what is shown,
    exactly as the main line is shopped. Sharp-book rungs are never
    shown (nobody here can bet them) and only ever price. Highest
    probability wins.
    """
    from .odds import devig_two_way, is_sharp_book
    alts = row.get("alt_lines") or []
    if not alts:
        return []
    sharp: dict[float, tuple[float, float]] = {}
    for ln in row.get("alt_sharp_lines") or []:
        try:
            if ln.get("over_odds") and ln.get("under_odds"):
                sharp[float(ln["line"])] = devig_two_way(int(ln["over_odds"]),
                                                         int(ln["under_odds"]))
        except (TypeError, ValueError):
            continue
    best_price: dict[tuple[float, str], tuple[int, str, dict]] = {}
    for ln in alts:
        try:
            line = float(ln.get("line"))
        except (TypeError, ValueError):
            continue
        book = str(ln.get("book") or "")
        if not book or book.lower() == "proxy" or is_sharp_book(book):
            continue
        for side, key in (("over", "over_odds"), ("under", "under_odds")):
            try:
                odds = int(ln.get(key) or 0)
            except (TypeError, ValueError):
                continue
            if not odds or not _sane(odds) or odds < HEAVIEST_PRICE:
                if odds and odds < HEAVIEST_PRICE:
                    _tally(ladder, "heavier than the cap")
                continue
            prev = best_price.get((line, side))
            if prev is None or odds > prev[0]:
                best_price[(line, side)] = (odds, book, ln)
    out: list = []
    priced = row.get("rung_probs") or {}
    for (line, side), (odds, book, ln) in best_price.items():
        # A RUNG THE MAKER PRICED ITSELF COMES FIRST. Baseball rows carry
        # `rung_probs` (engine/mlb/betting.rung_probs): P(over) at each
        # rung from the same curve that priced the main line — the only
        # curve that knows a hitter records zero total bases in 40% of
        # games. The mixture and the normal below are football's, and
        # neither is the right shape for a count of one or two.
        pre = priced.get(f"{line:g}")
        if pre is not None:
            p_over, source = float(pre), "model"
        else:
            p_over = display_prob(market, row.get("projection"), line,
                                  row.get("recent_values"), fits=fits)
            source = "mixture"
        if p_over is None:
            # NO MIXTURE FOR THIS MARKET — passing yards, which the
            # yardage fit declined — so price the rung the way the main
            # line was priced: the projection's own normal. Ethan,
            # 2026-09-15: "I didn't see any passing yard props." A
            # quarterback's ladder could only be priced where a sharp
            # book happened to hang the same number, which is almost
            # never, so the market that most needed the ladder was the
            # one the ladder could not read. Same bars as every rung:
            # the floor, the cap, the credibility of the number against
            # the rung's own de-vigged price.
            try:
                mu, sd = float(row.get("projection")), float(row.get("proj_std") or 0)
            except (TypeError, ValueError):
                mu, sd = 0.0, 0.0
            if sd > 0:
                from .statmath import prob_over
                anchored = _anchored_mean(row, sd)
                if anchored is not None:
                    mu = anchored
                p_over = prob_over(line, mu, sd)
                source = "anchored" if anchored is not None else "model"
        if p_over is None:
            pair = sharp.get(line)
            if pair is None:
                _tally(ladder, "no number to price the rung")
                continue
            p_over, source = pair[0], "sharp"
        p = 1.0 - float(p_over) if side == "under" else float(p_over)
        if p < _floor(floor):
            _tally(ladder, "under the floor")
            continue
        fair_over, fair_under = devig_two_way(int(ln.get("over_odds") or 0),
                                              int(ln.get("under_odds") or 0))
        fair = fair_under if side == "under" else fair_over
        if not _credible(p, fair):
            _tally(ladder, "disagrees with the rung’s own price")
            continue
        _tally(ladder, "priced")
        out.append({"line": line, "side": side, "book": book, "odds": odds,
                    "prob": p, "fair": fair, "source": source})
    # Highest probability first, so a caller that wants one can take the
    # head and a caller with its own bars walks a sensible order.
    out.sort(key=lambda c: -c["prob"])
    return out


def from_prop(row: dict, bettable, fits=None, sport: str = "nfl",
              census: dict | None = None, floor=None,
              ladder: dict | None = None, prefer=None, lean=None) -> dict | None:
    """One likelihood row from a published prop row, or None.

    `row` is what `pipeline._rec_to_dict` already produces for EVERY
    prop, recommended or not — the likelihood board is a different cut of
    the same evaluation, not a second model. Building it any other way
    would let the two pages disagree about the same player.

    ``census`` counts each refusal by reason — see `_refuse`.

    ``prefer`` lists the (side, line) numbers this board held for the
    prop — the one it went up at, then the one it showed last. The first
    still clearing every bar, main line or rung, is the row, so a price
    tick on a neighbouring rung does not move the pick (HOLD_MARGIN).
    """
    market = row.get("market") or ""
    if not rankable(market, sport):
        return _refuse(census, "no measured ranking for this market yet")
    prob = row.get("hit_prob")
    # A SHARP-ANCHORED CARD'S `hit_prob` IS THE SHARP BOOK'S FAIR, and
    # a sharp line is hung where that book thinks the coin is fair, so
    # the number sits at 50-53% for every prop it quotes. Judged on it,
    # every such prop is "under the likelihood floor" before the model
    # is consulted, and the board shows only what the sharp book did
    # not quote. Ethan, 2026-09-07: "it just shows 2 tight end reception
    # props. there is no rushing props for running backs or any
    # recieving props for wr." This board asks the MODEL who is likely
    # to hit — `raw_prob` is the model's own read of the side on an
    # anchored card (see `betting.Recommendation.raw_prob`) — and the
    # mixture below recomputes the shown number from the projection
    # either way. The sharp fair stays on the row as `sharp_fair`.
    if row.get("sharp_anchored") and row.get("raw_prob") is not None:
        prob = row.get("raw_prob")
    if prob is None or float(prob) < _floor(floor):
        # THE LADDER BEFORE THE FLOOR. A main line is hung where the book
        # thinks the coin is fair, so its number sits near 50% — and this
        # refusal fired on that number before `_best_rung` below was
        # ever consulted. The ladders (2026-09-07) exist for exactly the
        # row this turned away: the same stat at a lower number, priced
        # heavier, where "most likely" is actually for sale. Ethan,
        # 2026-09-08, off the droplet's census: 363 rows, 212 of them
        # here, none on the board, none on a rung — the ladders were
        # bought, carried, and never looked at, because every rung test
        # fixture started at 0.56. A main line under the floor asks its
        # ladder first; the floor's refusal is for a row whose every
        # number is under it. `has_market` still gates the ladder, since
        # a proxy-priced row has no real rungs to show.
        # With or without a model number on the main line: a rung priced
        # by the model's own curve, or by a sharp book hanging the same
        # alternate, needs neither (2026-09-15).
        rung = (_best_rung(row, market, fits, floor=floor, ladder=ladder,
                           prefer=prefer, lean=lean)
                if row.get("has_market") else None)
        if rung is not None:
            return _row_from(row, market, sport, bettable, prob, rung=rung)
        return _refuse(census, "under the likelihood floor")
    if not row.get("has_market"):
        return _refuse(census, "no real book price")
    if not _sane(row.get("odds")):
        return _refuse(census, "not a price a book could post")
    # CALIBRATED FOR DISPLAY, and this is the fix for a real defect.
    # `calibrate.correction_for` DISCARDS a boundary fit rather than
    # applying it — right for betting, since a capped temperature is the
    # search failing — so rush_yds and rec_yds, the two markets whose fits
    # ran to the cap, reached this page with NO correction at all. The
    # likelihood board was quoting the raw number from the two markets
    # measured most overconfident.
    #
    # `yardagefit`'s mixture halves the miss between what is claimed and
    # what lands (rec_yds 0.1137 -> 0.0709, receptions 0.0610 -> 0.0285).
    # It was declined for BETTING because it makes no money the normal was
    # not already making; this page's objective is calibration, not ROI,
    # and there it is measurably the better number.
    shown = float(prob)
    source = "model"
    # `fits` is INJECTABLE for the same reason `nflready`'s shrink lookup
    # is: the suite points QB_MODELS_DIR at an empty sandbox, so a test
    # reading the ambient store asserts about whether THIS box has been
    # fitted rather than about the code.
    fitted = display_prob(market, row.get("projection"), row.get("line"),
                          row.get("recent_values"), fits=fits)
    if fitted is not None:
        # The mixture is P(over); an UNDER row shows its complement.
        # Every yardage line a book hangs is a half-number, so there
        # is no push to subtract — the same convention `hit_prob`
        # already arrived with (betting.choose_side: under_win =
        # 1 - p_over_at_under).
        under = str(row.get("side") or "").lower() == "under"
        shown = 1.0 - float(fitted) if under else float(fitted)
        source = "mixture"
    # COUNTED, LIKE EVERY OTHER REFUSAL. These two were bare `return
    # None`s, and they are the two the mixture creates: a row that
    # cleared the floor on its raw claim and fell under it once
    # calibrated, and a row the calibration walked away from the book.
    # On a night the board came out empty the census said "under the
    # likelihood floor: 4" and the other hundred refusals were invisible
    # — the half of the funnel `_refuse` exists to count, uncounted
    # again one function later. Ethan, 2026-09-07: "so what changed."
    # The census has to be able to answer that.
    # THE LADDER, judged beside the main line. A rung that is likelier
    # than the main number — or the only one of the two to clear the
    # bars — is what the row shows; the main number stays on the row
    # as `main_line` so the card can say which book number the rung
    # stands beside. See `_best_rung`.
    got = rungs(row, market, fits, floor=floor, ladder=ladder)
    main_ok = shown >= _floor(floor) and _credible(shown, row.get("fair_prob"))
    # THE HELD NUMBER FIRST (HOLD_MARGIN, `_held_choice`): the main line or
    # the rung the board held, while it still clears; only then the
    # likeliest of the two.
    held = _held_choice(row, got, prefer, main_ok)
    if isinstance(held, dict):
        return _row_from(row, market, sport, bettable, prob, rung=held)
    # THE READ'S SIDE, among the numbers that clear (READ_SEATS).
    leaned = _lean_choice(row, got, main_ok, shown, lean) if held is None else None
    if isinstance(leaned, dict):
        return _row_from(row, market, sport, bettable, prob, rung=leaned)
    rung = max(got, key=lambda c: c["prob"]) if got else None
    if rung is not None and held != "main" and leaned != "main" and (
            not main_ok or rung["prob"] > shown):
        return _row_from(row, market, sport, bettable, prob, rung=rung)
    if shown < _floor(floor):
        return _refuse(census, "under the likelihood floor after calibration")
    # CREDIBILITY, AND THIS BOARD HAD NONE. Every other pick path refuses
    # a probability that disagrees with the market past
    # MAX_CREDIBLE_EDGE — `betting.evaluate_prop`, `longshots`,
    # `gamebets.temper` all carry it — because a 20-point disagreement in
    # a heavily bet market is our error far more often than a discovery.
    # This page does not grade or stake, so nothing ever forced the
    # question; it still makes the claim, and the claim is the product.
    #
    # CHECKED AFTER THE MIXTURE, not before. The mixture recomputes from
    # the projection and therefore discards the market shrink `hit_prob`
    # already carried, so the rows most able to run away from the book
    # are exactly the ones this page calibrated. Checking the input would
    # pass precisely what this exists to catch.
    #
    # REFUSED, NOT SHRUNK: a likelihood board that quietly moves its
    # number toward the market has stopped saying what it believes.
    if not _credible(shown, row.get("fair_prob")):
        return _refuse(census, "the shown probability disagrees with the market by more than we credit")
    return _row_from(row, market, sport, bettable, prob, shown=shown, source=source)


def _row_from(row: dict, market: str, sport: str, bettable, prob,
              shown: float | None = None, source: str = "model",
              rung: dict | None = None) -> dict:
    """The likelihood row, from the main line or from a rung of the ladder."""
    if rung is not None:
        side, line, book, odds = rung["side"], rung["line"], rung["book"], rung["odds"]
        shown, source = rung["prob"], rung["source"]
        # The rung's own de-vigged price is what the shown number is
        # judged against (`admissible`'s credibility bar reads
        # `implied_prob`); the engine's pre-shrink claim is still judged
        # against the MAIN line's fair, where it was made.
        implied = round(float(rung["fair"]), 4)
        ev = None
    else:
        side, line, book, odds = (row.get("side", ""), row.get("line"),
                                  row.get("book", ""), row.get("odds"))
        implied = row.get("fair_prob")
        ev = row.get("ev_per_unit")
    return {
        # WHICH MAKER BUILT IT — "prop", "td" or "game" — so the page,
        # the journal and the lint branch on a flag rather than on the
        # absence of a position or a line.
        "kind": "prop",
        "player": row.get("player", ""), "team": row.get("team", ""),
        "opponent": row.get("opponent", ""),
        "market": market, "market_label": row.get("market_label", market),
        "side": side, "line": line,
        "book": book, "odds": odds,
        # HOW OLD THIS PRICE IS (pipeline stamps it off the event payload),
        # which the prop rows never carried — so no Most Likely prop card
        # could say its price's age. 2026-09-25, the stale-data pass.
        "price_age_s": row.get("price_age_s"),
        "priced_from": row.get("priced_from") or "",
        "model_prob": round(float(shown), 4),
        # WHICH NUMBER THE READER IS LOOKING AT. A page that silently
        # swapped its probability source would be the opposite of the
        # point.
        "prob_source": source,
        # WHICH NUMBER ON THE BOOK'S LADDER. "alt" rows carry the main
        # line beside them so the card can say what the rung stands
        # next to; the journal and the grader read `line`/`side`/`odds`
        # and so grade the rung itself.
        "rung": "alt" if rung is not None else "main",
        "main_line": row.get("line"), "main_odds": row.get("odds"),
        "main_book": row.get("book", ""), "main_side": row.get("side", ""),
        "raw_prob": round(float(prob), 4) if prob is not None else None,
        # THE PRE-SHRINK CLAIM AND THE BOOK'S OWN NUMBER, carried so the
        # one bar can ask the engine's question (see `engine_credible`).
        # `raw_prob` above is this board's own raw display number, which
        # is a different thing from the engine's pre-shrink claim, so
        # the engine's travels under its own name.
        "engine_raw_prob": row.get("raw_prob"),
        # THE SHARP BOOK'S OWN NUMBER, beside the model's, when the card
        # was priced from a sharp pair. The floor above was asked of the
        # model; a reader deserves to see the number it was not asked of.
        "sharp_anchored": bool(row.get("sharp_anchored")),
        "sharp_fair": row.get("sharp_fair"),
        "fair_prob": row.get("fair_prob"),
        "implied_prob": implied,
        "projection": row.get("projection"),
        "ev_per_unit": ev,
        # THE FLAG THAT KEEPS THIS HONEST. A market can rank without
        # being bettable, and a reader deserves to know which they are
        # looking at rather than inferring it from the absence of a
        # stake.
        "bettable": bool(bettable(market)),
        "rank_auc": rank_auc(sport, market),
        "reasons": row.get("reasons") or [],
        # What the defence gives up to his position (engine/defensevs).
        "matchup_card": row.get("matchup_card"),
        "qb_card": row.get("qb_card"),
        "mate_card": row.get("mate_card"),
        "game_script": row.get("game_script"),
        "ripples": row.get("ripples") or [],
        "recent_values": row.get("recent_values") or [],
        # THE GAME'S OWN DAY, READ FROM THE FIELD THAT HOLDS IT. This
        # said `row.get("date")`, and a prop row has no `date` at all —
        # `pipeline._rec_to_dict` writes the kickoff day to `game_date`
        # (2026-09-13) and leaves `date` unset. So every prop-derived
        # likelihood row carried an EMPTY game_date, and `ledger.
        # game_day_for` then had nothing to stamp a calendar day from.
        # Football settles on a week label, so the empty field was the
        # difference between a row that can be graded and one that sits
        # in a bucket called "2026-W01" forever (134 of them on
        # 2026-09-11). Game rows were unaffected: a game bet's `date` IS
        # its day, which is why this only ever bit the player rows.
        "game_date": row.get("game_date") or row.get("date", ""),
        "kickoff": row.get("kickoff", ""),
        "headshot": row.get("headshot", ""),
        "position": row.get("position", ""),
        "usage_role": row.get("usage_role", ""),
        # Carried so `admissible` can refuse on it and a lint can see it.
        "injury_status": row.get("injury_status", "") or "",
        # A BASEBALL HITTER ON A PROJECTED LINEUP (engine/mlb/pipeline
        # stamps it; None where a sport has no lineup card). The board
        # shows him with the caveat; the journal waits for the card
        # (`ledger.log_most_likely`) — found by the site audit, 2026-09-24:
        # this row dropped the flag, so the staked book could take a
        # hitter who then sat, and baseball has no absent-player grade.
        "lineup_confirmed": row.get("lineup_confirmed"),
        "warnings": list(row.get("warnings") or []),
    }


def from_watch(row: dict, sport: str = "nfl") -> dict:
    """A touchdown watch row, in the same shape.

    The most-likely-scorers list was already this board for one market;
    it keeps its own builder because it prices through the long-shot
    chain, and is merged here rather than rebuilt.
    """
    return {
        "kind": "td",
        "player": row.get("player", ""), "team": row.get("team", ""),
        "opponent": row.get("opponent", ""),
        "market": "anytime_td", "market_label": "Anytime TD",
        "side": "yes", "line": None,
        "book": row.get("book", ""), "odds": row.get("odds"),
        "price_age_s": row.get("price_age_s"),
        "priced_from": row.get("priced_from") or "",
        "model_prob": row.get("model_prob"),
        "implied_prob": row.get("implied_prob"),
        "projection": None,
        "ev_per_unit": row.get("ev_per_unit"),
        "bettable": True,
        "rank_auc": rank_auc(sport, "anytime_td"),
        "reasons": row.get("reasons") or [],
        "matchup_card": row.get("matchup_card"),
        "qb_card": row.get("qb_card"),
        "mate_card": row.get("mate_card"),
        "game_script": row.get("game_script"),
        "ripples": row.get("ripples") or [],
        "recent_values": row.get("recent_values") or [],
        "game_date": row.get("game_date", ""),
        "kickoff": row.get("kickoff", ""),
        "headshot": row.get("headshot", ""),
        "position": row.get("position", ""),
        "injury_status": row.get("injury_status", "") or "",
        "warnings": list(row.get("caveats") or []),
    }


def from_game_bet(row: dict, sport: str = "nfl",
                  census: dict | None = None, floor=None) -> dict | None:
    """One likelihood row from a priced game bet, or None.

    `row` is the card the edge board already built — `gamebets._game_bet`,
    `gamebets.moneyline_to_dict`, cfb_build.to_game_bet — so this is, once
    more, a different cut of the same evaluation and not a second model.
    `win_prob` is the model's probability of the side the card took and
    `fair_prob` the book's de-vigged number for that side; both are on
    the card, and `admissible` holds them to the same cap, floor and
    credibility bar as every player row.

    THE MARKET HAS TO HAVE RANKED. `GAME_RANK_AUC` (or the box's own
    store) says which game markets the model has been shown to sort;
    today that is the moneyline and nothing else, because spreads and
    totals measured as a coin flip against the close. A spread card
    handed in here comes back None, and that is the board working.

    THE LIKELY SIDE, NOT THE PRICED SIDE. The edge card backs whichever
    side has the edge, and on a moneyline that is the dog more often
    than not — the first end-to-end run put "CHI ML +190, 37%" on a
    board called Most Likely, with the 63% favourite nowhere on it. A
    moneyline is two-way with no push, so the other side's probability
    is on the card already (1 - win_prob, 1 - fair_prob); its price is
    now too (`MoneylineRec.home_odds` / `away_odds`). When the card's
    pick sits under 50% the row is built for the favourite. A dog card
    without the other price (a stale payload) is refused rather than
    shown as "likely". Spreads and totals would need the same flip the
    day they rank, and their cards do not carry the other price yet —
    noted here so it is not rediscovered.

    HOLDS, NOT PICKS: a card on an in-play market a pre-game model
    cannot price (`live`), and a college conditional waiting on a
    starter (`conditional`) — the same reading the injury hold gives a
    listed player. A card the edge board refused as not credible still
    arrives here with `credible` False and a Pass grade; `admissible`
    refuses it again on the numbers, which is the one bar doing its job.

    THE ROW WEARS THE CARD'S SHAPE (win_prob, fair_prob, edge, grade,
    headline, matchup …) beside the board's own keys, so the game-bet
    page can draw a flipped row it will not find among the edge cards.
    """
    from .gamebets import expected_value
    market = row.get("bet_type") or row.get("market") or ""
    if market not in GAME_MARKETS:
        return _refuse(census, "not a game market this board carries")
    # AN UNATTRIBUTABLE PRICE IS NOT A PRICE.
    #
    # Ethan, 2026-09-09, with FanDuel and DraftKings open beside our
    # board: his books had GB +105 / MIN -125 and DAL -162 / NYG +136;
    # ours showed MIN ML -220 and NYG ML -218, both captioned "Moneyline
    # · best". "That's wrong and needs to be fixed now."
    #
    # "best" was this function's own doing — `row.get("book") or "best"`,
    # under a comment saying game cards carry no book name, which stopped
    # being true when the moneyline, the spread and the total each
    # learned to name their side's book. The fallback outlived the
    # comment, so a card that arrived with no book printed one anyway. A
    # made-up name is worse than none: it tells a reader the number was
    # checked against a book when nothing checked it.
    #
    # A TRUTH BAR, so the reserve pass does not relax it (see
    # RESERVE_MIN_PROB) — "we need picks" is not a reason to publish a
    # price no book is posting. A shelf that empties here is a shelf
    # reporting that its prices could not be sourced, which is honest and
    # is a diagnosis; the alternative is a moneyline wrong by ninety-five
    # cents on the dollar.
    if (sport in BOOK_NAMED_SPORTS
            and market in BOOK_POSTED_GAME_MARKETS
            and not (row.get("book") or "").strip()
            and not (row.get("home_book") or "").strip()
            and not (row.get("away_book") or "").strip()):
        # EITHER SIDE NAMING A BOOK IS ENOUGH TO PASS HERE. The flip to
        # the favourite below rewrites `row["book"]` on its way past — a
        # dog at FanDuel becomes a favourite at DraftKings — so the
        # question this guard asks is whether ANY book is posting this
        # game, not which one the row will end up showing.
        return _refuse(census, "no book is posting this price")
    # MEASURED IS THE BAR FOR A GAME MARKET, not ranked (see
    # GAME_RANK_MEASURED). A market with a figure is shown with it; a
    # market with none is not shown at all.
    model_auc = measured_auc(sport, market)
    if model_auc is None:
        return _refuse(census, "this game market has never been measured")
    if row.get("has_market") is False:
        return _refuse(census, "no real book price")
    if row.get("live"):
        return _refuse(census, "the game is already under way")
    # …AND ONE THAT HAS FINISHED, which `live` says nothing about. Every
    # producer sets `live` as `state == "live"`, so a FINAL game answers
    # False to it and sailed onto a board called Most Likely To Hit with
    # a settled result and a pre-game probability. `rules.game_has_started`
    # is the wider fact — live OR final, "once a pre-game projection is
    # stale" — and it was computed in every `_finish_bet` and thrown away.
    # Counted separately from `live` because "still playing" and "already
    # over" are different answers to "why is this not on the board".
    if row.get("started"):
        return _refuse(census, "the game has already been played")
    if row.get("conditional"):
        return _refuse(census, "a conditional, which is a hold and not a pick")
    # THE CARD'S TWO NUMBERS, READ TOGETHER (see SPREAD_COHERENCE). A
    # moneyline is checked against the same game's posted spread, because
    # a book prices both off one opinion and ours came from two feeds.
    if market == "moneyline" and _spread_disagrees(row, sport):
        # ONE LINE, ONE LITERAL, deliberately: a census label split
        # across two source lines is one that neither a reader nor this
        # module's own label linter (tests/test_census_labels.py) can
        # find whole.
        return _refuse(census, "the moneyline disagrees with this game’s own spread by more than any book has")
    # WHICH NUMBER ORDERS THE ROW — see `ranking_number`. `prob` is the
    # ranking number from here on; `prob_model` is the model's own read
    # for the same side, kept on the row and the card as the model's.
    prob, source, auc = ranking_number(sport, market, row, model_auc)
    if prob is None:
        return _refuse(census, "no probability")
    ranked = float(auc) >= MIN_RANK_AUC
    fair = row.get("fair_prob")
    prob_model = row.get("win_prob")
    prob_model = prob if prob_model is None else float(prob_model)
    home, away = row.get("home", "") or "", row.get("away", "") or ""
    team = row.get("team") or ""
    side = row.get("side", "") or ""
    line = row.get("line")
    odds = row.get("odds")
    label = row.get("pick_label") or row.get("headline") or ""
    # The model's own claim before the market haircut, when the maker
    # carries one. See MoneylineRec.raw_win_prob.
    raw_claim = row.get("engine_raw_prob")
    try:
        raw_claim = None if raw_claim is None else float(raw_claim)
    except (TypeError, ValueError):
        raw_claim = None
    flipped, backed, backed_odds = False, label, odds
    if prob < 0.5:
        # THE LIKELY SIDE. Every game market here is two-way, so the
        # other side is 1 - p at the other side's price (`other_odds`
        # on every card since 2026-09-02; the moneyline also carries
        # both prices by name). A card without it is refused rather
        # than shown as "likely" from the wrong end.
        if market == "moneyline":
            other_odds = row.get("away_odds") if team == home else row.get("home_odds")
            other_odds = row.get("other_odds") if other_odds is None else other_odds
            # THE BOOK FLIPS WITH THE PRICE. The two sides' best prices
            # can be at different books, so a flipped row that kept the
            # card's book would name a book that is not posting the
            # number beside it — worse than naming none.
            other_book = (row.get("away_book") if team == home
                          else row.get("home_book"))
            if other_book:
                row = dict(row, book=other_book)
            team = away if team == home else home
            label = f"{team} ML"
        elif market == "spread":
            other_odds = row.get("other_odds")
            team = away if team == home else home
            line = None if line is None else -float(line)
            label = f"{team} {line:+g}" if line is not None else f"{team}"
        else:                                   # total, team_total
            other_odds = row.get("other_odds")
            side = "Under" if str(side).lower().startswith("o") else "Over"
            label = (f"{side} {line:g}" if market == "total"
                     else f"{team} {side} {line:g}") if line is not None else side
        if not team and market != "total":
            return _refuse(census, "the likely side has no team on the card")
        if other_odds is None or fair is None:
            return _refuse(census, "the other side's price is missing")
        odds, prob, fair, flipped = other_odds, 1.0 - prob, 1.0 - float(fair), True
        prob_model = 1.0 - prob_model
        # THE PRE-SHRINK CLAIM FLIPS WITH THE SIDE. Every market here is
        # two-way, so the model's raw number for the other side is
        # 1 - raw. Left unflipped it would be compared against the OTHER
        # side's fair by `engine_credible`, which is a guard reading two
        # numbers about different teams.
        if raw_claim is not None:
            raw_claim = 1.0 - raw_claim
    if prob < _floor(floor):
        return _refuse(census, "under the likelihood floor")
    # The card's edge and EV are the MODEL's, as on every card: the
    # ranking number is what orders the board, not what the card claims.
    edge = None if fair is None else round(prob_model - float(fair), 4)
    try:
        ev = round(expected_value(prob_model, int(odds)), 4)
    except (TypeError, ValueError):
        ev = None
    reasons = list(row.get("reasons") or [])
    # THE EDGE BOARD'S REFUSAL IS NOT THIS BOARD'S. Ethan, 2026-09-08,
    # with the Vikings card on screen: a green "67% · the likely side"
    # headline sitting over a red "Model disagrees with the market by
    # more than 10% — a rating error, not an edge". Both sentences were
    # true of their own board and the card carried them together, which
    # is the same self-contradiction the Gelof card had in reverse.
    #
    # A row that ranks on the MARKET's number is not staking our rating,
    # and the disagreement it names was measured to carry nothing
    # against the close (`engine_credible`, `gamerank --raw-bar`). The
    # row says what it IS doing in `rank_note`, which prints the model's
    # own number and why it does not bar the row. So the staking
    # refusal comes off, by name rather than by matching text.
    if source == "market":
        from .gamebets import RATING_ERROR_REASON, RATING_ERROR_REASON_EFFICIENT
        gone = {RATING_ERROR_REASON, RATING_ERROR_REASON_EFFICIENT}
        reasons = [r for r in reasons if r not in gone]
    if flipped:
        try:
            at = f" at {int(backed_odds):+d}"
        except (TypeError, ValueError):
            at = ""
        reasons.insert(0, f"The likely side. The edge board backed {backed}{at} "
                          f"on price; this is the side the same numbers say "
                          f"lands more often ({prob:.0%}).")
    # WHAT THE FIGURE MEANS, on the row. A ranked market's number is a
    # ranking; a measured-below-floor market's number is the model's
    # lean at this line, and the row says which it is rather than
    # letting a shelf header speak for it.
    if not ranked:
        rank_note = (
            f"Shown as the model’s lean at this number. Sorting "
            f"{_GAME_WORDS.get(market, market)} across games measured at "
            f"{float(auc):.2f} against the close — a coin flip — so the "
            f"percentage is a read on this game, not a ranking.")
    elif source == "market":
        # THE MODEL'S OWN NUMBER, not the book's under the word "model".
        # `prob_model` is the card's `win_prob`, and on a football
        # moneyline the measured haircut prices that AT the market
        # (gamecal: the disagreement carries nothing), so it is the
        # market's number twice over. The pre-shrink claim is the
        # model's own read, and it is what a reader means by "the
        # model" (tests/test_game_claim.py, the MIN -220 card).
        own = prob_model if raw_claim is None else raw_claim
        rank_note = (
            f"Ranked on the market’s number, {prob:.0%}: the book’s de-vigged "
            f"price sorts {sport.upper()} winners at {float(auc):.2f} measured, "
            f"against {float(model_auc):.2f} for the model’s own. The model’s "
            f"own rating has this side at {own:.0%}.")
        if (raw_claim is not None and fair is not None
                and abs(raw_claim - float(fair)) > MAX_CREDIBLE_EDGE):
            rank_note += (
                " That disagreement does not bar the row: measured against "
                "the close, the market’s number lands the same on the games "
                "the model disputes as on the ones it agrees with, and the "
                "model’s disagreement with the close carries no information "
                "(engine.gamecal, engine.gamerank --raw-bar).")
    elif source == "sharp":
        rank_note = (
            f"Ranked on the sharp book’s fair, {prob:.0%} — a market number, "
            f"which sorts {sport.upper()} winners at {float(auc):.2f} measured.")
    else:
        rank_note = ""
    return {
        # WHAT KIND OF ROW THIS IS, said once, so the page, the journal
        # and the lint branch on a flag rather than on the absence of a
        # position. `player` carries the pick label because every reader
        # of this board keys on it; the journal re-derives the team or
        # matchup it needs from the fields below.
        "kind": "game",
        "player": label, "team": team or home,
        "opponent": (away if (team or home) == home else home),
        "home": home, "away": away,
        "matchup": row.get("matchup", "") or f"{away} @ {home}",
        "pick_label": label, "pick": team or "",
        "pick_is_home": (team == home) if team else None,
        "headline": label,
        "bet_type": market, "market": market,
        "market_label": row.get("market_label", market),
        # THE ENGINE'S OWN NUMBER, for the engine's own question. Without
        # it `engine_credible` answered True for every game row — the
        # Gelof guard was blind to this whole board (Ethan, 2026-09-03:
        # "none of these teams are favored to win on any sports book").
        #
        # ONLY ON A MARKET THAT CLAIMS A RANKING, and that is a product
        # decision, not a technicality. The bar exists to stop a row
        # being presented as a LIKELIHOOD RANKING while the engine does
        # not credit its own number. An unranked spread or total makes
        # no such claim — it ships labelled "the model's lean at this
        # number" because Ethan asked to see those (2026-09-02), and the
        # model there disagrees with the close by 30 points as a matter
        # of course. Feeding those to this bar would empty both shelves
        # and silently reverse his call.
        "engine_raw_prob": raw_claim if ranked else None,
        "side": side, "line": line,
        # THE BOOK POSTING THIS PRICE, or nothing at all.
        #
        # This read `row.get("book") or "best"`. The comment above it
        # said "a game card carries no book name on the NFL path", which
        # stopped being true when the moneyline, the spread and the
        # total each learned to name their side's book — and the
        # fallback outlived it, so a card with no book printed a book
        # called "best" beside a real-looking price.
        #
        # Ethan, 2026-09-09, with his sportsbook open next to ours:
        # "FanDuel and draft kings show the lines in the screenshot yet
        # we show a different line. That's wrong." Both cards in that
        # screenshot read "Moneyline · best". A name we made up is worse
        # than no name: it tells a reader the number was checked against
        # a book when nothing checked it. `admissible` refuses the row
        # instead — see "no book is posting this price".
        # READ HERE, NOT AT THE GUARD ABOVE. The flip to the favourite
        # rewrites `row["book"]` on its way past — a dog at FanDuel
        # becomes a favourite at DraftKings — so the name this card
        # ends up showing is only settled by this point.
        "book": row.get("book") or "", "odds": odds,
        # HOW OLD THIS PRICE IS, carried to the card. A row that cannot
        # date its own number is how three wrong-moneyline reports in a
        # week could not be told apart from three stale ones.
        "price_age_s": row.get("price_age_s"),
        "priced_from": row.get("priced_from") or "",
        "model_prob": round(prob, 4),
        "prob_source": source,
        "raw_prob": round(prob, 4),
        "implied_prob": None if fair is None else round(float(fair), 4),
        "projection": None,
        "ev_per_unit": ev,
        "bettable": True,
        "rank_auc": round(float(auc), 4),
        "ranked": ranked,
        "rank_note": rank_note,
        "reasons": reasons,
        "game_script": row.get("game_script"),
        "recent_values": [],
        "game_date": row.get("date", "") or "", "kickoff": row.get("kickoff", "") or "",
        "date": row.get("date", "") or "",
        "headshot": "", "position": "", "usage_role": "",
        "injury_status": "",
        "warnings": list(row.get("warnings") or []),
        # The card shape, for the game-bet page. NOT a stake: this board
        # ranks and never sizes, and a flipped row is not on the edge
        # board at all.
        "win_prob": round(prob_model, 4),
        # WHOSE NUMBER THIS IS, carried rather than inferred.
        #
        # Ethan, 2026-09-16, on the Pick of the Day being moneylines in
        # practice when he had asked for spreads and totals too. The
        # cause was here: a sharp-anchored SPREAD card arrives with
        # `win_prob` already set to the sharp book's de-vigged fair
        # (`gamebets._sharpify`, the same rewrite `price_moneyline_sharp`
        # does), and this row dropped the fact on the floor. Downstream,
        # `potd.evidence` found no `sharp_anchored`, read `prob_source`
        # — which `ranking_number` sets to "model" for any market with no
        # GAME_RANK_MARKET entry, i.e. every spread and total — and
        # refused the row as "only our own model disputes this price".
        #
        # THAT SENTENCE WAS FALSE ABOUT THE ROW. The number disputing
        # the price was Pinnacle's. The evidence was not weighed and
        # found wanting, it was discarded on the way here.
        #
        # `ranking_number` is deliberately NOT changed: which number the
        # board RANKS on, and whether a spread ships labelled a lean, is
        # Ethan's 2026-09-02 call and this does not touch it. These two
        # fields only record where the probability came from.
        #
        # FLIP-SAFE BY CONSTRUCTION: `prob_model` is flipped above with
        # the side, so the fair recorded here is the fair for the side
        # this row actually takes — which is why it reuses the very
        # number published as `win_prob` one line up rather than reading
        # the card again.
        "sharp_anchored": bool(row.get("sharp_anchored")),
        "sharp_fair": (round(prob_model, 4)
                       if row.get("sharp_anchored") else None),
        "fair_prob": None if fair is None else round(float(fair), 4),
        "edge": edge,
        "has_market": True, "live": False, "credible": True,
        "grade": "Likely", "quality": None, "confidence": None,
        "stake_units": 0.0, "recommended": False,
        "flipped": flipped,
    }


#: The kinds of row the board is built from, in the order the makers run.
def _now() -> str:
    """This build's stamp: UTC to the second, one format, so stamps sort."""
    import datetime as _dt
    return (_dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
            .replace("+00:00", "Z"))


def _priced_at(stamp: str, age_s) -> str | None:
    """When a price was pulled: this build's stamp less the price's age.

    A CLOCK TIME, NOT AN AGE. `price_age_s` is the price's age when the
    build ran, and a page read an hour later printed it unchanged — "priced
    4m ago" beside a number an hour old. Ethan, 2026-09-25: "We shouldn't
    be showing stale shit to a user looking for up-to-date information."
    With the pull's own time on the row the page ages it to the second,
    and a locked pick carries the time its posted price was pulled."""
    import datetime as _dt
    if age_s is None:
        return None
    try:
        t = _dt.datetime.fromisoformat(str(stamp).strip().replace("Z", "+00:00"))
        t = t if t.tzinfo else t.replace(tzinfo=_dt.timezone.utc)
        at = t - _dt.timedelta(seconds=float(age_s))
    except (TypeError, ValueError):
        return None
    return at.astimezone(_dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _price_at(row: dict | None, side, line):
    """The best bettable price a book lists TODAY for (side, line) on a
    prop's current row — (odds, book) — or None when no book lists it.

    Read off every quote on the row: the alternate ladder, each book's main
    number (both sides), and the row's own price; sharp and proxy books
    excluded (nobody here can bet them)."""
    from .odds import is_sharp_book
    if not row or line is None:
        return None
    try:
        line = float(line)
    except (TypeError, ValueError):
        return None
    want = _side(side)
    key = "under_odds" if want == "under" else "over_odds"
    best = None
    quotes = [(ln.get("line"), ln.get(key), ln.get("book"))
              for ln in (row.get("alt_lines") or []) + (row.get("all_lines") or [])]
    if _side(row.get("side")) == want:
        quotes.append((row.get("line"), row.get("odds"), row.get("book")))
    for q_line, q_odds, q_book in quotes:
        try:
            if abs(float(q_line) - line) > 1e-9:
                continue
            odds = int(q_odds or 0)
        except (TypeError, ValueError):
            continue
        book = str(q_book or "")
        if not odds or not _sane(odds) or not book or book.lower() == "proxy" or is_sharp_book(book):
            continue
        if best is None or odds > best[0]:
            best = (odds, book)
    return best


def _started(row: dict, stamp: str) -> bool:
    """Had this row's game kicked off by `stamp`? False when either is unreadable."""
    import datetime as _dt

    def parse(x):
        t = _dt.datetime.fromisoformat(str(x).strip().replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=_dt.timezone.utc)
    try:
        return bool(row.get("kickoff")) and parse(row["kickoff"]) <= parse(stamp)
    except (TypeError, ValueError):
        return False


def _kicked_off(row: dict, stamp: str) -> bool:
    """Had this row's game started by `stamp`, read the way the boards
    actually write it: `kickoff` is an ISO time on some boards and a bare
    local "20:15" on the NFL's (nflverse's `gametime`, Eastern), beside
    `game_date`. `_started` only reads the first, so on the NFL board a
    pick whose game had kicked off never read as one.

    A game dated before `stamp`'s day (Eastern) has started; one dated
    that day has once its clock time has passed; anything unreadable has
    not, so a pick is never dropped on a guess."""
    if _started(row, stamp):
        return True
    import datetime as _dt
    import re as _re
    try:
        from zoneinfo import ZoneInfo
        et = ZoneInfo("America/New_York")
        now = _dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        now = (now if now.tzinfo else now.replace(tzinfo=_dt.timezone.utc)).astimezone(et)
        day = _dt.date.fromisoformat(str(row.get("game_date") or row.get("date") or "")[:10])
    except (TypeError, ValueError, KeyError):
        return False
    if day < now.date():
        return True
    if day > now.date():
        return False
    m = _re.match(r"^\s*(\d{1,2}):(\d{2})\s*([AaPp][Mm])?", str(row.get("kickoff") or ""))
    if not m:
        return False
    hh, mm = int(m.group(1)), int(m.group(2))
    if m.group(3):
        hh = hh % 12 + (12 if m.group(3).lower() == "pm" else 0)
    return (now.hour, now.minute) >= (hh, mm)


def _stamp_hold(rows: list, held: dict, stamp: str) -> None:
    """`since`, `first_prob` and (when the number has moved) `first_line`
    on every row: carried from last build's row for the same pick on the
    same side, or this build's for a pick that has just gone up.

    CONTINUOUS, NOT CUMULATIVE. Only last build's board is consulted, so a
    pick that left and came back went up again when it came back — "on
    the board since 9:12" means through every refresh since 9:12."""
    for r in rows:
        h = held.get(hold_key(r))
        if h is not None and (str(h.get("side") or "").lower()
                              == str(r.get("side") or "").lower()):
            r["since"] = h.get("since") or stamp
            r["first_prob"] = h.get("first_prob", h.get("model_prob"))
            first = h.get("first_line", h.get("line"))
            if (first is not None and r.get("line") is not None
                    and not _same_number(r.get("side"), r.get("line"),
                                         (r.get("side"), first))):
                r["first_line"] = first
        else:
            r["since"] = stamp
            r["first_prob"] = r.get("model_prob")


def _minutes(since: str, stamp: str) -> float:
    """Minutes from `since` to `stamp`; 0 when either is unreadable."""
    import datetime as _dt

    def parse(x):
        t = _dt.datetime.fromisoformat(str(x).strip().replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=_dt.timezone.utc)
    try:
        return (parse(stamp) - parse(since)).total_seconds() / 60.0
    except (TypeError, ValueError):
        return 0.0


#: What a pick held out of the board keeps (HOLD_GRACE_MIN): enough to
#: key it, hold its number, and give it back its `since` if it returns.
_HELD_OUT_FIELDS = ("kind", "player", "team", "market", "matchup", "side",
                    "line", "model_prob", "since", "first_prob", "first_line",
                    "kickoff",
                    # …and enough to DRAW it where it is listed as pulled
                    # (`_earlier`): the reader saw this row, so the list
                    # shows the same bet, at the price it last showed.
                    "game_date", "opponent", "market_label", "book", "odds",
                    "headshot", "position", "pick_label", "home", "away")


def _turnover(rows: list, held: dict, why_left: dict, outranked: set,
              stamp: str, by_margin: int) -> dict:
    """What changed against last build's board, why each pick left, and
    the picks still held out for the next build.

    The measurement behind the hold (HOLD_MARGIN): on the box, each build
    says how many picks it kept on the same number, how many moved number
    or side, how many are new, how many came back inside the grace
    (HOLD_GRACE_MIN), and for each that left the reason — its game
    started, a bar turned it away (the census's own words), a likelier
    pick took its seat, or the books stopped offering it.

    `held_out` is what the next build reads back (`previous_board`). It
    names picks, so it rides in a paid key (`gate.PAID_KEYS`).
    """
    now = {hold_key(r): r for r in rows}
    kept = moved = flipped = back = 0
    for k, r in now.items():
        h = held.get(k)
        if h is None:
            continue
        if h.get("out_at"):
            back += 1
        elif str(h.get("side") or "").lower() != str(r.get("side") or "").lower():
            flipped += 1
        elif (h.get("line") is not None and r.get("line") is not None
              and not _same_number(r.get("side"), r.get("line"),
                                   (h.get("side"), h.get("line")))):
            moved += 1
        else:
            kept += 1
    left: dict = {}
    held_out: list = []
    for k, h in held.items():
        if k in now:
            continue
        started = _kicked_off(h, stamp)
        if h.get("out_at"):
            if not started:
                held_out.append(h)
            continue
        why = ("its game started" if started
               else why_left.get(k) or ("a likelier pick took its seat"
                                        if k in outranked else "no longer offered"))
        left[why] = left.get(why, 0) + 1
        if not started:
            ghost = {f: h.get(f) for f in _HELD_OUT_FIELDS if h.get(f) is not None}
            ghost.update(since=h.get("since") or stamp, out_at=stamp, out_why=why)
            held_out.append(ghost)
    return {"at": stamp,
            "previous": sum(1 for h in held.values() if not h.get("out_at")),
            "rows": len(rows), "held": kept, "number_moved": moved,
            "side_flipped": flipped, "came_back": back,
            "new": sum(1 for k in now if k not in held), "left": left,
            "kept_by_margin": by_margin, "held_out": held_out}


#: The counts `_day_tally` adds up across a slate's builds.
_DAY_COUNTS = ("held", "number_moved", "side_flipped", "came_back", "new",
               "kept_by_margin")


def _day_tally(day: dict, turn: dict, fresh: bool) -> dict:
    """The slate's running tally: this build's turnover added to the last
    one's. One build's turnover says what the last refresh did; the tally
    says what a whole day of them did, and which reason dominates — the
    number `homecheck.py hold` prints. The first build of a slate starts
    it, and does not count its every row as new."""
    out = {"builds": int(day.get("builds") or 0) + 1,
           "since": day.get("since") or turn.get("at")}
    for k in _DAY_COUNTS:
        out[k] = int(day.get(k) or 0) + (0 if fresh and k == "new" else int(turn.get(k) or 0))
    left = dict(day.get("left") or {})
    for why, n in (turn.get("left") or {}).items():
        left[why] = int(left.get(why) or 0) + int(n)
    out["left"] = left
    return out


#: How many pulled picks a board carries at most — newest first. A week
#: of NFL refreshes will not come near it; it is a bound, not a policy.
EARLIER_MAX = 60


def reader_reason(why: str) -> str:
    """Why a pick left, in the words the page prints. The census's own
    wording (`admissible`, `from_prop`, `from_game_bet`) is written for
    the droplet's reports; a reader needs the fact about the bet."""
    w = str(why or "").strip()
    lw = w.lower()
    if "floor" in lw or lw == "no probability":
        return "the model’s chance for it fell under our bar"
    if lw.startswith("heavier than"):
        return f"the price moved past −{abs(HEAVIEST_PRICE)}, too heavy to call a pick"
    if lw.startswith("listed "):
        return w
    if ("no real" in lw or "no book" in lw or "no longer offered" in lw
            or "could not have posted" in lw or "could post" in lw
            or "price is missing" in lw):
        return "the books stopped offering it"
    if "disagrees with" in lw:
        return "the market moved away from our number"
    if "likelier pick" in lw:
        return "the board filled with likelier picks"
    if "under way" in lw or "already been played" in lw or "game started" in lw:
        return "its game started"
    return w or "it no longer cleared the board"


def _earlier(prev: list, held_out: list, rows: list, stamp: str) -> list:
    """Every pick that went up and has since come off, until its game
    starts — the answer to "the picks I saw yesterday are nowhere to be
    found" (Ethan, 2026-09-24). `held_out` keeps a pick for the hour it
    may come back as the same pick (HOLD_GRACE_MIN); this keeps it for
    the READER until kickoff, with when it went up, when it came off and
    why. A pick back on the board is dropped from here; so is one whose
    game has started. Newest departure first."""
    now = {hold_key(r) for r in rows}
    out: dict = {}
    for g in list(prev or []) + list(held_out or []):
        if not isinstance(g, dict) or not g.get("out_at"):
            continue
        k = hold_key(g)
        if k in now or _kicked_off(g, stamp):
            continue
        e = dict(g)
        e["out_note"] = reader_reason(e.get("out_why"))
        out[k] = e
    return sorted(out.values(), key=lambda e: str(e.get("out_at") or ""),
                  reverse=True)[:EARLIER_MAX]


def previous_board(public_path, date) -> dict:
    """What this board published last, for the hold: {"rows": its
    `most_likely` rows and the picks it was holding out, "day": the
    slate's running tally} — empty when there is no board yet, it is
    another slate's, or it cannot be read.

    Read from the private copies (`gate.board_source`): with the paywall
    on, the public file has the picks taken out, and a hold reading it
    would find nothing to hold and quietly turn itself off. THE LIGHT COPY
    FIRST (`engine/lightboard`), written by the same build a moment after
    the full one: it carries every Most Likely row and `likely_turnover`
    without each row's chain and comps, and the full MLB board is 8 MB to
    parse on every refresh of a one-gigabyte box to read forty rows.
    """
    import json
    from .gate import board_source
    from .lightboard import light_path
    doc = None
    for path in (light_path(public_path), public_path):
        try:
            with open(board_source(path), encoding="utf-8") as fh:
                doc = json.load(fh)
            break
        except (OSError, ValueError, TypeError):
            continue
    if doc is None:
        return {"rows": [], "day": {}, "earlier": []}
    if not isinstance(doc, dict) or str(doc.get("date") or "") != str(date or ""):
        return {"rows": [], "day": {}, "earlier": []}
    # The board's rows, then the picks it was holding out (HOLD_GRACE_MIN);
    # `build` drops a ghost whose hour has run and prefers a row to its ghost.
    turn = doc.get("likely_turnover") or {}
    rows = [r for r in doc.get("most_likely") or [] if isinstance(r, dict)]
    rows += [r for r in turn.get("held_out") or []
             if isinstance(r, dict) and r.get("out_at")]
    return {"rows": rows, "day": turn.get("day") or {},
            "earlier": [r for r in turn.get("earlier") or [] if isinstance(r, dict)]}


def hold_report(sport: str, board: dict) -> list:
    """How steady one published Most Likely board is — `homecheck.py hold`.

    Three readings, each answering part of Ethan's "it's hard too judge
    what picks the models are comfortable with" (2026-09-24): how long
    the picks on the board now have been up, what a day of refreshes did
    to the board (`likely_turnover.day`), and why the picks that left,
    left. Ages are measured at the board's own last build, so a stale
    board does not read as a steady one.
    """
    rows = [r for r in (board or {}).get("most_likely") or [] if isinstance(r, dict)]
    turn = (board or {}).get("likely_turnover") or {}
    head = f"  {sport} {board.get('date', '')} · {len(rows)} pick{'' if len(rows) == 1 else 's'}"
    if not rows and not turn:
        return [head + " · no Most Likely board"]
    at = turn.get("at")
    if not at:
        return [head + " · built before the hold (no `likely_turnover`) — "
                "rebuild on a box running it"]
    ages = [_minutes(r["since"], at) for r in rows if r.get("since")]
    day = turn.get("day") or {}
    out = [head + f" · {day.get('builds', 1)} build(s) since {day.get('since') or at}",
           f"    up 3h+: {sum(1 for a in ages if a >= 180)}   1-3h: "
           f"{sum(1 for a in ages if 60 <= a < 180)}   under 1h: "
           f"{sum(1 for a in ages if a < 60)}"]
    out.append("    today: " + " · ".join(
        f"{k.replace('_', ' ')} {int(day.get(k) or 0)}" for k in _DAY_COUNTS))
    left = sorted((day.get("left") or {}).items(), key=lambda kv: -kv[1])
    out.append("    left: " + (" · ".join(f"{why} {n}" for why, n in left) or "none"))
    out.append(f"    last build: kept {turn.get('held', 0)}, new {turn.get('new', 0)}, "
               f"held out {len(turn.get('held_out') or [])}")
    # Every pick listed as pulled, with why — what a reader sees in the
    # "Pulled since they went up" fold (`_earlier`).
    pulled = [e for e in turn.get("earlier") or [] if isinstance(e, dict)]
    out.append(f"    pulled, listed until kickoff: {len(pulled)}")
    for e in pulled[:20]:
        bet = e.get("pick_label") or " ".join(
            str(x) for x in (e.get("player"), e.get("side"), e.get("line"), e.get("market")) if x not in (None, ""))
        out.append(f"      {bet} ({e.get('team') or ''}) · up {e.get('since') or '?'} · "
                   f"off {e.get('out_at') or '?'} · {e.get('out_note') or e.get('out_why') or ''}")
    return out


KINDS = ("td", "prop", "game")


def _funnel() -> dict:
    return {"offered": 0, "kept": 0, "duplicate": 0, "shown": 0, "refused": {}}


def build(props: list, td_picks=None, td_watch=None, sport: str = "nfl",
          limit: int = LIMIT, fits=None, census: dict | None = None,
          game_bets=None, census_by_kind: dict | None = None,
          cut: list | None = None, previous=None,
          turnover: dict | None = None, now: str | None = None,
          leans: dict | None = None, lean_report: dict | None = None) -> list:
    """The likelihood board: every rankable market, ordered by probability.

    ``leans`` maps (player, team, market) to the matchup read's side —
    {"side": "over"|"under", "read": key, "label": words} — see READ_SEATS.
    ``lean_report`` is filled in place with what each leaned player got:
    {(player, team): {"status": "pick"|"other_side"|"none", ...}}.

    ORDERED BY PROBABILITY AND NOTHING ELSE. Sorting by EV, or breaking
    ties on it, would quietly rebuild the edge board under a different
    name — which is the exact failure this page exists to correct.

    `census` is filled with {reason: count} across every row the board
    turned away, as before. `census_by_kind` is filled with the same
    refusals split by the kind of row — "td", "prop", "game" — each
    with how many rows were OFFERED, how many the bar KEPT, how many
    were a DUPLICATE of a row already seated, how many were SHOWN once
    the caps ran, and the refusals by reason. Ethan, 2026-09-08: "we
    have player props just barely any money lines or touchdown." The
    flat census could not say where the moneylines and the scorers
    went: "under the likelihood floor: 212" is one line for three
    different shelves, and a shelf whose rows were never offered at all
    prints nothing. Offered / kept / shown per kind is the funnel that
    answers him — a "td" line reading offered 0 is an empty feed, one
    reading offered 40 and refused 40 under the floor is the floor.

    ``previous`` is the board this one replaces — the same slate's last
    published `most_likely` (`previous_board`) — and turns on the hold
    (HOLD_MARGIN): a pick keeps its number and its seat while it still
    clears every bar, and carries `since` (when it went up) and
    `first_prob` forward. ``turnover`` is filled with what changed
    against it and why (`_turnover`). With no previous board every row
    is new and the order is exactly the probability order it always was.
    """
    from .calibrate import is_reliable

    stamp = now or _now()
    # `previous_board` hands back {"rows", "day"}; a bare list of rows is
    # the same board with no running tally.
    prev_day: dict = {}
    prev_earlier: list = []
    if isinstance(previous, dict):
        prev_earlier = previous.get("earlier") or []
        previous, prev_day = previous.get("rows") or [], previous.get("day") or {}
    # Last build's rows first, then the picks it was still holding out
    # (HOLD_GRACE_MIN) — a pick on the board wins over its own ghost.
    held: dict = {}
    for r in previous or []:
        if isinstance(r, dict) and not (
                r.get("out_at") and _minutes(r["out_at"], stamp) > HOLD_GRACE_MIN):
            held.setdefault(hold_key(r), r)
    # WHY EACH HELD PICK LEFT, when it did: its key -> the refusal. Filled
    # by the standard pass only; the reserve's lower floor is not a reason
    # a pick left the real board.
    why_left: dict = {}

    def prefer_for(row) -> list | None:
        """The numbers held for this prop: the one it went up at, then the
        one it showed last (`_held_choice`)."""
        h = held.get(("prop", row.get("player") or "", row.get("team") or "",
                      row.get("market") or ""))
        if not h:
            return None
        return [(h.get("side"), ln) for ln in (h.get("first_line"), h.get("line"))
                if ln is not None] or None

    def bettable(market):
        return is_reliable(sport, market)

    funnel = {k: _funnel() for k in KINDS}
    # The prop rows a matchup read leaned, by player — what `lean_report`
    # prices when none of them came out on the read's side.
    lean_props: dict = {}

    def one_pass(floor, funnel, seen=None, why=None):
        """Every maker, every row, at one floor. Returns the rows kept.

        Lifted out of `build` so the reserve can ask the same question
        with the same bar in every respect but one (see
        RESERVE_MIN_PROB). Running it twice is cheap next to the risk of
        a second, drifting copy of the admission logic — this module's
        own docstring calls a rule enforced in one of several places
        "this codebase's most-repeated bug", and two passes over one
        function cannot disagree with each other.
        """
        out = []
        # THE CALLER MAY HAND IN WHAT IS ALREADY SEATED. The top-up pass
        # re-offers every row the standard pass took, so it has to know
        # them — and it has to know them by the SAME key this function
        # builds, or the dedupe is a second, drifting copy of the rule.
        # Passing the set in is how that is guaranteed.
        seen = set() if seen is None else seen

        def keep(got, kind: str, market_funnel: dict | None = None) -> bool:
            """The one gate. Every row passes through here or does not ship.

            ``market_funnel`` is the prop row's own market's tally, kept
            beside the kind's — the same verdict written twice, never a
            second judgement."""
            no = admissible(got, floor=floor)
            if no:
                _refuse(funnel[kind]["refused"], no)
                if market_funnel is not None:
                    _refuse(market_funnel["refused"], no)
                if why is not None:
                    why.setdefault(hold_key(got), no)
                return False
            funnel[kind]["kept"] += 1
            if market_funnel is not None:
                market_funnel["kept"] += 1
            return True

        funnel["td"]["offered"] = len(td_picks or []) + len(td_watch or [])
        for row in (td_picks or []) + (td_watch or []):
            got = from_watch(row, sport=sport)
            key = (got["player"], got["team"], "anytime_td")
            if key in seen:
                funnel["td"]["duplicate"] += 1
                continue
            if not keep(got, "td"):
                continue
            seen.add(key)
            out.append(got)
        funnel["prop"]["offered"] = len(props or [])
        # PER MARKET, because "the board is short" is not a question
        # anyone asks. Ethan, 2026-09-15: "some days we'd be showing
        # four or five passing props, and then the next day they'd all
        # be gone ... I didn't see any passing yard props." A census by
        # reason across the whole board cannot say which market lost its
        # rows or to which bar; this can, and the page prints it.
        markets_f = funnel["prop"].setdefault("markets", {})
        for row in props or []:
            mk = str(row.get("market") or "")
            mf = markets_f.setdefault(mk, {"offered": 0, "priced": 0, "kept": 0,
                                           "shown": 0, "refused": {},
                                           # THE LADDER'S OWN LEDGER: how
                                           # many rows carried one and
                                           # what became of each rung —
                                           # "one passing prop: supply or
                                           # refusal?" could not be
                                           # answered without it
                                           # (2026-09-15).
                                           "laddered": 0, "ladder": {}})
            mf["offered"] += 1
            if row.get("has_market"):
                mf["priced"] += 1
            if row.get("alt_lines"):
                mf["laddered"] += 1
            local: dict = {}
            rungs: dict = {}
            lean = (leans or {}).get((row.get("player") or "", row.get("team") or "", mk))
            if lean:
                lean_props.setdefault((row.get("player") or "", row.get("team") or ""), []).append(row)
            got = from_prop(row, bettable, fits=fits, sport=sport,
                            census=local, floor=floor, ladder=rungs,
                            prefer=prefer_for(row), lean=(lean or {}).get("side"))
            for no, n in local.items():
                funnel["prop"]["refused"][no] = funnel["prop"]["refused"].get(no, 0) + n
                mf["refused"][no] = mf["refused"].get(no, 0) + n
            for no, n in rungs.items():
                mf["ladder"][no] = mf["ladder"].get(no, 0) + n
            if got is None and local and why is not None:
                why.setdefault(("prop", row.get("player") or "",
                                row.get("team") or "", mk), next(iter(local)))
        # `from_prop` already refuses on the same grounds and returns
        # None; it stays as a cheap pre-filter because the mixture work
        # below it is not cheap. `keep` is what actually decides — but
        # the pre-filter now counts what it turned away into the same
        # census, so the funnel adds up whichever of the two said no.
            if got is None:
                continue
            key = (got["player"], got["team"], got["market"])
            if key in seen:
                funnel["prop"]["duplicate"] += 1
                continue
            if not keep(got, "prop", mf):
                continue
            seen.add(key)
            out.append(got)
        # THE THIRD MAKER, same bar. Game cards arrive from the edge
        # board's own pricing (`pipeline._game_bets`,
        # `mlb.pipeline._game_bets`, cfb_build.build_plays); a market the
        # model has not been shown to rank never leaves `from_game_bet`,
        # and everything that does answers to `keep` like every other row.
        funnel["game"]["offered"] = len(game_bets or [])
        for row in game_bets or []:
            got = from_game_bet(row, sport=sport,
                                census=funnel["game"]["refused"], floor=floor)
            if got is None:
                continue
            key = ("game", got["matchup"], got["market"], got["team"], got["side"])
            if key in seen:
                funnel["game"]["duplicate"] += 1
                continue
            if not keep(got, "game"):
                continue
            seen.add(key)
            out.append(got)
        return out

    seated_keys: set = set()
    out = one_pass(None, funnel, seated_keys, why_left)
    # NO SHELF GOES BLANK. Ethan, 2026-09-08: "Also I don't want an empty
    # boar either we need to have picks period", and then, the night
    # before the opener: "We have barely any moneylines show and barley
    # and touchdowns shown." The second report is the one that moved this
    # from a board-wide fallback to a per-shelf one. A board carrying
    # twenty player props and nothing under Touchdowns is not an empty
    # board by this function's arithmetic, and it is exactly an empty
    # page to the person who opened it for the touchdowns.
    #
    # So the bar is asked again one notch lower for each shelf that came
    # out with nothing on it — the FLOOR only. Every refusal that means
    # "this number is wrong" is asked exactly as it was, which is why
    # this can be done at all (see RESERVE_MIN_PROB). The standard pass
    # keeps the census: the honest answer to "why is the board short" is
    # what the real bar turned away, not what the fallback did.
    #
    # THIN COUNTS AS EMPTY, and that is the second correction this
    # fallback has needed. It first fired only on a wholly empty board;
    # then only on a wholly empty SHELF. Ethan, 2026-09-09, looking at a
    # board whose Touchdown shelf held exactly one row and whose Rushing
    # shelf held five, against 390 rows refused under the floor: "Still
    # showing no touchdown props or rushing props."
    #
    # He is right, and the arithmetic says why. `MIN_PROB` is 0.55, and
    # anytime-touchdown probabilities cluster between 20% and 45% — only
    # a bell cow in a good spot clears 55%. So that shelf is near-empty
    # BY CONSTRUCTION, not because the slate is quiet, and a rule that
    # waits for it to reach exactly zero will wait forever while showing
    # one row.
    #
    # So each shelf is topped up to RESERVE_LIMIT rather than filled only
    # when bare. Rows that cleared the real bar keep their places and
    # their absence of a label; the reserve fills what is left.
    #
    # `seated_keys` is what makes that safe. The reserve pass re-offers
    # every row the standard pass already took, and a shelf that is being
    # topped up has taken some — so without it, the same touchdown would
    # appear twice, once labelled. Seeding the pass with the keys it
    # already issued means the dedupe uses one definition of "the same
    # row" rather than two.
    seated = {k: 0 for k in KINDS}
    for r in out:
        seated[r.get("kind") or "prop"] = seated.get(r.get("kind") or "prop", 0) + 1
    thin = [k for k in KINDS if seated.get(k, 0) < RESERVE_LIMIT]
    if thin:
        spare = one_pass(RESERVE_MIN_PROB, {k: _funnel() for k in KINDS},
                         seated_keys)
        spare.sort(key=lambda r: -_seat(r, held))
        taken = {k: 0 for k in thin}
        for r in spare:
            kind = r.get("kind") or "prop"
            if (kind not in taken
                    or seated.get(kind, 0) + taken[kind] >= RESERVE_LIMIT):
                continue
            taken[kind] += 1
            r["reserve"] = True
            r["reserve_note"] = reserve_note(kind, seated.get(kind, 0))
            # `bettable` IS DELIBERATELY LEFT ALONE. It was set False here
            # first, on the reasoning that a reserve row is not a
            # recommendation — which is true, and the wrong field to say
            # it with. On this board `bettable` means the MARKET has a
            # price worth staking against, and the card renders it as
            # "No bettable price here — this market's fit against the
            # book ran off the end of its range". On a reserve row that
            # is a false statement about a real quoted price, in service
            # of a true one about the probability: exactly the kind of
            # small lie the rest of this work is removing. The row says
            # what it is through `reserve` and its note; the book is kept
            # clean by `ledger.log_most_likely`, which refuses it.
            out.append(r)
    out.sort(key=lambda r: -float(r["model_prob"] or 0.0))
    # TWO CAPS, ONE ORDER. Player rows keep LIMIT; game rows keep
    # GAME_LIMIT; the survivors are one list in probability order, so a
    # 63% favourite still sits above a 55% catch and a Sunday's eighty
    # game leans cannot push the player rows off (see GAME_LIMIT).
    # The reserve needs no exemption here and must not be given one:
    # RESERVE_LIMIT is below both caps, and `_cut_players` back-fills to
    # `limit`, so a reserve of that size passes through untouched. A
    # guard for it would be a branch no test could ever reach. See
    # `test_the_reserve_cap_stays_under_the_board_caps` for the invariant
    # that keeps this true if someone raises RESERVE_LIMIT.
    # THE READ, ON THE ROWS THAT AGREE WITH IT (READ_SEATS): marked, so
    # the card can say it and the seat below can find them.
    for r in out:
        lean = (leans or {}).get((r.get("player") or "", r.get("team") or "",
                                  r.get("market") or ""))
        if lean and _side(r.get("side")) == lean.get("side"):
            r["scan_read"], r["scan_label"] = lean.get("read"), lean.get("label")
    players = _cut_players([r for r in out if r.get("kind") != "game"], limit,
                           held=held)
    # …AND ITS PICK KEEPS A SEAT PAST THE CAPS: the likeliest agreeing row
    # of each read player the cut left off, READ_SEATS a player. Every one
    # cleared every bar; what it lacked was a seat, which is a layout fact
    # (see `cut` below), and a card calling him a breakout beside a board
    # without him is the contradiction Ethan asked about.
    if leans:
        on = {id(r) for r in players}
        have: dict = {}
        for r in players:
            if r.get("scan_read"):
                k = (r.get("player"), r.get("team"))
                have[k] = have.get(k, 0) + 1
        for r in sorted((r for r in out if r.get("kind") != "game" and r.get("scan_read")
                         and id(r) not in on), key=lambda r: -float(r.get("model_prob") or 0)):
            k = (r.get("player"), r.get("team"))
            if have.get(k, 0) < READ_SEATS:
                players.append(r)
                have[k] = have.get(k, 0) + 1
    game_rows = sorted((r for r in out if r.get("kind") == "game"),
                       key=lambda r: -_seat(r, held))
    games = game_rows[:GAME_LIMIT]
    # The same rule for the game shelf (HELD_SEATS).
    games += [r for r in game_rows[GAME_LIMIT:] if _posted(r, held)][
        :GAME_LIMIT * (HELD_SEATS - 1)]
    # WHAT THE MARGIN ALONE DECIDED: held rows seated here that the same
    # cut without it would have dropped. Counted so the margin is judged
    # on the box, not argued (HOLD_MARGIN).
    by_margin = 0
    if held:
        plain = {id(r) for r in _cut_players(
            [r for r in out if r.get("kind") != "game"], limit)}
        plain |= {id(r) for r in [r for r in out if r.get("kind") == "game"][:GAME_LIMIT]}
        by_margin = sum(1 for r in players + games if id(r) not in plain)
    # WHAT THE DISPLAY CAPS DROPPED, HANDED BACK TO A CALLER THAT ASKED.
    #
    # Ethan, 2026-09-16: "I think the selector should see the full game
    # list so no prop or game is left unscanned." He is right, and the
    # reason is that the two rankings pull opposite ways. The cut above
    # keeps the LIKELIEST rows; `potd`'s band (-142 to +190) exists to
    # throw the likeliest rows away, because a -300 favourite pays too
    # little to be the day's pick. So the rows this cap discards are
    # exactly the rows the Pick of the Day is shopping for — a
    # sharp-anchored +130 dog with a real edge sits at position 21 on a
    # probability ranking and never reached the selector at all.
    #
    # THESE ARE CUT ROWS, NOT RAW ONES, and that distinction is the whole
    # safety of it. Every row here already cleared `admissible` and every
    # refusal in `from_prop` / `from_game_bet` — the price cap, the
    # credibility bar, an injury designation, a game under way, a
    # moneyline that contradicts its own spread. What it failed is a
    # SEAT, which is a page-layout fact and not a judgement about the
    # bet. Handing a caller the rows the model refused would be a
    # different and much worse change.
    #
    # THE BOARD ITSELF IS UNCHANGED. `GAME_LIMIT` and `limit` still say
    # what the page draws and the payload carries (the MLB board is
    # already 8 MB); this is a second, in-memory view for a caller whose
    # question the caps were never about. Filled in place, like
    # `census_by_kind`, so no existing caller has to change.
    seated = {id(r) for r in players} | {id(r) for r in games}
    if cut is not None:
        cut.extend(r for r in out if id(r) not in seated)
    outranked = {hold_key(r) for r in out if id(r) not in seated}
    out = players + games
    # THE LOCK (PLAYABLE_STATUSES above): every pick posted last build is
    # on this board until its game or its player's status takes it down.
    locked_n: dict = {}
    # THE PROP ROWS THIS BUILD PRICED, for a locked pick's chance TODAY at
    # the number it went up at (`_locked`, `_prob_at`).
    prop_now = {("prop", r.get("player") or "", r.get("team") or "", r.get("market") or ""): r
                for r in props or []}

    def now_prob(h):
        if (h.get("kind") or "prop") != "prop":
            return None
        return _prob_at(prop_now.get(hold_key(h)), h.get("market") or "",
                        h.get("side"), h.get("line"), fits)

    def lock(h, why):
        """`_locked` at today's chance, with today's projection and today's
        price at the posted number beside it."""
        r = _locked(h, why, stamp, now_prob(h))
        prop = (h.get("kind") or "prop") == "prop"
        cur = prop_now.get(hold_key(h)) if prop else None
        if cur and cur.get("projection") is not None:
            r["projection"] = cur["projection"]
        if prop:
            # THE PRICE AS IT STANDS. The posted price stays on the row —
            # it is the one journaled and graded — and today's best price
            # at the same number sits beside it, or the fact that no book
            # lists that number any more.
            got = _price_at(cur, h.get("side"), h.get("line"))
            r["now_listed"] = got is not None
            r["now_odds"], r["now_book"] = got if got else (None, "")
            r["now_priced_at"] = _priced_at(stamp, cur.get("price_age_s")) if got and cur else None
        if not r.get("priced_at"):
            # A pick posted before rows carried their pull time: its age at
            # the build that posted it, counted from when it went up.
            r["priced_at"] = _priced_at(r.get("since") or stamp, h.get("price_age_s"))
        return r
    if held:
        for i, r in enumerate(out):
            h = held.get(hold_key(r))
            if (h is not None and not h.get("out_at") and h.get("line") is not None
                    and r.get("line") is not None
                    and not _same_number(r.get("side"), r.get("line"),
                                         (h.get("side"), h.get("line")))):
                out[i] = lock(h, "number moved")
                locked_n["number moved"] = locked_n.get("number moved", 0) + 1
        present = {hold_key(r) for r in out}
        for k, h in held.items():
            if k in present or h.get("out_at") or _kicked_off(h, stamp):
                continue
            why = why_left.get(k) or ("a likelier pick took its seat"
                                      if k in outranked else "no longer offered")
            if hard_exit(why):
                continue
            out.append(lock(h, why))
            locked_n[why] = locked_n.get(why, 0) + 1
    _stamp_hold(out, held, stamp)
    for r in out:
        if not r.get("locked") and r.get("price_age_s") is not None:
            r["priced_at"] = _priced_at(stamp, r.get("price_age_s"))
    # PROBABILITY ORDER, AS PRINTED. Rows the page shows at the same whole
    # percent sit longest-held first, so two picks a tenth of a point apart
    # stop trading places on every refresh; rows at different percents are
    # in probability order exactly as before, and with no previous board
    # every `since` is this build's and the order is the exact one.
    out.sort(key=lambda r: (-round(float(r["model_prob"] or 0.0), 2),
                            0 if hold_key(r) in held else 1,
                            str(r.get("since") or ""),
                            -float(r["model_prob"] or 0.0)))
    if lean_report is not None and leans:
        lean_report.update(_lean_report(out, leans, lean_props, fits, why_left))
    if turnover is not None:
        turnover.update(_turnover(out, held, why_left, outranked, stamp,
                                  by_margin))
        # How many posted picks the lock alone kept up, and why each
        # would otherwise have left.
        turnover["locked"] = locked_n
        turnover["day"] = _day_tally(prev_day, turnover, fresh=not held)
        turnover["earlier"] = _earlier(prev_earlier, turnover.get("held_out"),
                                       out, stamp)
    # WHY THE BOARD IS THE SIZE IT IS, handed back to a caller that asked
    # for it. An empty college Saturday has several causes and a census
    # that only reaches stdout is one nobody has the morning they need
    # it. Filled in place rather than returned, so no existing caller
    # has to change and no row carries metadata that would follow it
    # into the journal.
    for r in out:
        funnel[r.get("kind") or "prop"]["shown"] += 1
        if (r.get("kind") or "prop") == "prop":
            mf = funnel["prop"].setdefault("markets", {}).get(str(r.get("market") or ""))
            if mf is not None:
                mf["shown"] += 1
    refused: dict = {}
    for kind in KINDS:
        for why, n in funnel[kind]["refused"].items():
            refused[why] = refused.get(why, 0) + n
    # THE RESERVE IS NOT COUNTED HERE, and the first version of this got
    # it wrong. A "reserve ran" key was written into `census`, which broke
    # the invariant `test_likely_census_by_kind` holds — the flat census
    # is exactly the per-kind refusals summed — and, worse, the page's
    # `likelyRefusedNote` totals these values as "N turned down". A row
    # the board SHOWED would have been counted as a row it refused, on
    # exactly the nights the number matters. The rows say it themselves:
    # every reserve row carries `reserve`, so nothing here has to.
    if census is not None:
        census.update(refused)
    if census_by_kind is not None:
        census_by_kind.update(funnel)
    return out


def summary(board: list, refused: int = 0) -> dict:
    """What the page says about itself, counted rather than asserted.

    `refused` carries the rows the credibility bar dropped, so a board
    that came out short can say WHY rather than looking like a quiet
    slate — the same census discipline the pick funnel uses.
    """
    by_market: dict = {}
    for r in board:
        by_market[r["market"]] = by_market.get(r["market"], 0) + 1
    return {
        "rows": len(board),
        "by_market": by_market,
        "bettable": sum(1 for r in board if r.get("bettable")),
        "rank_only": sum(1 for r in board if not r.get("bettable")),
        "refused_incredible": refused,
    }
