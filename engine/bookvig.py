"""What each book charges, and how much the de-vig assumption is worth.

Ethan, 2026-09-15: "all the us books your using and shit, is that able
too be used for all sports if it makes sense and can save us api key
credits?" They can, and they are — the book list is a filter on a
response already paid for, so the seventeen books cost exactly what ten
did. That left a question nobody could answer from the board: WHICH of
the seventeen actually came back, and what does each one charge.

NOTHING HERE COSTS A CREDIT. Every number is arithmetic on a payload the
build already has in memory, in the same loop that already walks it
(`oddsapi.apply_odds_to_slate` iterates `parse_event_h2h_by_book` and
keeps one book out of seventeen).

────────────────────────────────────────────────────────────────────
WHY THIS EXISTS RATHER THAN THE FEATURE IT WAS SUPPOSED TO BE
────────────────────────────────────────────────────────────────────

The intended build was an exchange DETECTOR: measure each book's
overround, and treat a near-zero-vig two-way quote as an exchange fair —
auto-promoting Novig and ProphetX to the top of `potd.EVIDENCE` without
naming them, which is the discipline `booksharp` already follows.

The premise was that de-vigging a book means ASSUMING how its margin is
shared across the two sides (`odds.devig_two_way` divides it
proportionally; the favourite-longshot literature says books do not
price that way), so a book with no margin would need no assumption.

That premise was measured before it was built, and it does not hold at
the sizes this feature works at. `assumption_points` below computes the
gap between the three standard de-vigs — proportional, additive and
power — on a real pair. Worst case inside the Pick of the Day price
band (`potd.MIN_ODDS` -142 to `potd.MAX_ODDS` +190, so a price implying
0.345 to 0.587), and inside the narrower range the side actually TAKEN
can sit in (`potd.MIN_FAIR` 0.50 upward):

    book overround   whole band   side taken   vs potd.MIN_EV (2 pts)
      1.00 exchange     0.00 pts     0.00 pts            0%
      1.01              0.24         0.13               12%
      1.02              0.48         0.26               24%
      1.03 Pinnacle     0.70         0.39               35%
      1.04              0.94         0.52               47%
      1.05 soft book    1.18         0.66               59%

BOTH COLUMNS ARE HERE BECAUSE THE FIRST DRAFT QUOTED ONLY THE SECOND.
Measuring over 0.50-0.587 alone gave 0.39 points for a sharp book and
read as an emphatic answer; the band's plus-money end reaches 0.345,
where the same pair moves 0.70. The conclusion below survives either
number, but the smaller one was quoted as though it covered the band
and it did not.

So a sharp book's pair carries about SEVEN TENTHS OF A POINT of method
risk at the worst point of this band — a third of the smallest edge the
selector will act on. Two things follow, and they point opposite ways:

  THE DE-VIG IS NOT A REASON TO PROMOTE A BOOK A WHOLE TIER. Jumping
  Novig above Pinnacle buys at most 0.70 points of arithmetic certainty
  and costs the thing that actually ranks a price — whether it predicts.
  So this module measures and stores; it does not promote. Whether a
  no-margin venue's number beats a sharp book's is `booksharp`'s
  question, and it needs a tape that does not exist yet.

  THE MARKET TIER IS ARITHMETICALLY SOUND, which is the more useful half.
  `likely.GAME_RANK_MARKET` ranks NFL and CFB moneylines on a de-vigged
  book fair (0.722 and 0.7905 AUC), and "we de-vigged on an assumption"
  was a standing caveat on that number. Measured, the assumption is worth
  1.18 points at the very worst corner of this band and a fifth of that
  at even money. Small, and now a figure rather than an adjective —
  which is the difference between a caveat somebody can weigh and one
  that just sits there.

WHY THE GAP VANISHES AT EVEN MONEY, since it is the whole shape of the
table above and it is not obvious. All three methods must return two
numbers summing to one, and at a true 50/50 the only such answer is
50/50 — so they cannot disagree, whatever the margin. The disagreement
is driven by DISTANCE FROM EVEN MONEY, not by the size of the vig, and
the Pick of the Day band is pinned near even money by construction
(no in-band price can imply more than 58.7%). A board pricing +900
touchdown longshots is a different question with a different answer, and
`engine/devig` is where that one is already asked.
"""

from __future__ import annotations

#: A pair whose two sides sum to less than this is not a book's quote.
#: One book quoting an arbitrage against itself is a data error — a
#: mis-posted price, a stale side, or two different lines parsed as one —
#: and de-vig arithmetic on it returns confident nonsense rather than
#: failing. `odds.pair_is_sane` refuses the same shape one level up.
MIN_OVERROUND = 0.90

#: …and a two-way game market this wide is not one either. The widest
#: real h2h hold in this repository's tape is under 8%; 25% is a market
#: with a suspended side or an alternate line mixed in.
MAX_OVERROUND = 1.25


def pair_overround(a_odds, b_odds) -> float | None:
    """What the two sides sum to. 1.00 is no margin; 1.045 is a soft book.

    `None` rather than a number when the pair cannot be read, because a
    census that silently scores an unreadable quote as 1.0 would report
    the broken books as the tightest ones on the board.
    """
    from .odds import american_to_prob
    try:
        a, b = int(a_odds), int(b_odds)
    except (TypeError, ValueError):
        return None
    if not a or not b:
        return None
    try:
        total = american_to_prob(a) + american_to_prob(b)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if not (MIN_OVERROUND <= total <= MAX_OVERROUND):
        return None
    return round(total, 4)


def _power_fair(ra: float, rb: float) -> float | None:
    """The power de-vig: the k making ``ra**k + rb**k == 1``, then ``ra**k``.

    Bisection rather than a solver so this carries no new dependency.
    The function is strictly decreasing in k for probabilities under one,
    so a sign change across the bracket is a single root.
    """
    if not (0.0 < ra < 1.0 and 0.0 < rb < 1.0):
        return None
    lo, hi = 0.05, 20.0

    def f(k: float) -> float:
        return ra ** k + rb ** k - 1.0

    flo, fhi = f(lo), f(hi)
    if flo * fhi > 0:
        return None
    for _ in range(80):
        mid = (lo + hi) / 2.0
        fm = f(mid)
        if flo * fm <= 0:
            hi = mid
        else:
            lo, flo = mid, fm
    return ra ** ((lo + hi) / 2.0)


def devig_methods(a_odds, b_odds) -> dict:
    """The three standard de-vigs of one pair, as fairs for the FIRST side.

    ``{"proportional": p, "additive": p, "power": p}``, any of which may
    be absent if that method cannot be applied. Proportional is what
    `odds.devig_two_way` uses; the other two are here to measure it
    against, not to replace it.
    """
    from .odds import american_to_prob
    try:
        a, b = int(a_odds), int(b_odds)
    except (TypeError, ValueError):
        return {}
    if not a or not b:
        return {}
    ra, rb = american_to_prob(a), american_to_prob(b)
    total = ra + rb
    if not (MIN_OVERROUND <= total <= MAX_OVERROUND):
        return {}
    out: dict = {"proportional": ra / total,
                 "additive": ra - (total - 1.0) / 2.0}
    pw = _power_fair(ra, rb)
    if pw is not None:
        out["power"] = pw
    # EVERY VALUE HERE IS ALREADY A PROBABILITY, and the first draft
    # filtered for that on a scenario that cannot occur. The worry was
    # that an additive de-vig walks a lopsided pair off the number line,
    # since it subtracts the SAME margin from both sides. It cannot,
    # with S = ra + rb:
    #
    #   additive < 0  needs  ra < (S-1)/2  <=>  ra + 1 < rb, and rb < 1
    #   additive > 1  needs  ra - (S-1)/2 > 1  <=>  ra - rb > 1, ra < 1
    #
    # Both are impossible for two raw implied probabilities. Proportional
    # is ra/S with S > ra > 0, and power is ra**k with 0 < ra < 1 — so
    # neither can escape either. Swept over 260,900 pairs clearing the
    # band guard: the widest range any method returned was 0.0020 to
    # 0.9980. The filter was removed rather than kept "just in case",
    # because a guard whose justification is false is worse than none —
    # it is a claim about the arithmetic that a reader would believe.
    return out


def assumption_points(a_odds, b_odds) -> float | None:
    """How far apart the de-vigs land, in probability POINTS.

    This is the size of the thing the exchange tier was built to avoid.
    See the module docstring for what it measures out at: four tenths of
    a point at a sharp book's margin, inside this feature's price band.

    `None` when fewer than two methods apply, because the spread of one
    number is zero and reporting that as agreement would be a lie about
    a pair nothing could be computed for.
    """
    ms = devig_methods(a_odds, b_odds)
    if len(ms) < 2:
        return None
    return round((max(ms.values()) - min(ms.values())) * 100.0, 4)


def overrounds(event_json: dict, team_map: dict) -> dict:
    """``{book title: overround}`` for every book quoting BOTH sides.

    A one-sided quote contributes nothing — there is no margin to measure
    without the other half, and assuming one is the move this whole
    module exists to put a number on.

    AN UNMAPPED TEAM NAME IS KEPT, which is the one place this parses
    more loosely than `consensus_h2h_fair` beside it, and deliberately.
    That function hangs a fair on a NAMED side, so a name it cannot
    resolve is a number it must not use. This one never names a side —
    it measures the distance between two prices — so an unrecognised
    club costs nothing, and refusing it would silently exclude exactly
    the leagues whose team map is built at runtime (college football)
    or is the identity (UFC), which are the leagues nobody has ever
    measured a book's margin on.

    The two-outcome check is what keeps that safe: a market with a draw
    or an alternate line mixed in has three prices and is skipped, so
    the loose key can only ever pair the two sides of a two-way market.
    """
    out: dict = {}
    for bm in (event_json or {}).get("bookmakers", []):
        from .sources.oddsapi import BOOK_TITLES
        book = BOOK_TITLES.get(bm.get("key", ""), bm.get("key", ""))
        if not book:
            continue
        for mkt in bm.get("markets", []):
            if mkt.get("key") != "h2h":
                continue
            priced: dict = {}
            for o in mkt.get("outcomes", []):
                name = o.get("name", "")
                abbr = (team_map or {}).get(name, name)
                price = o.get("price")
                if abbr and price is not None:
                    priced[abbr] = price
            if len(priced) != 2:
                continue
            (_a, oa), (_b, ob) = sorted(priced.items())
            orr = pair_overround(oa, ob)
            if orr is not None:
                out[book] = orr
    return out


class Census:
    """Every book's margin over a slate, accumulated one game at a time.

    A plain object rather than a dict-of-lists on the caller because
    three builds accumulate this and a fourth will; the shape of the
    summary is the thing they must agree on.
    """

    def __init__(self, seen: dict | None = None) -> None:
        # ADOPTS the dict it is handed rather than copying it, so a caller
        # holding a plain dict on a dataclass can wrap it per event and
        # still be accumulating into the one store. A census that copied
        # would count every game and report none of them.
        self.seen: dict = {} if seen is None else seen

    def add(self, book: str, overround) -> None:
        if not book or overround is None:
            return
        try:
            v = float(overround)
        except (TypeError, ValueError):
            return
        self.seen.setdefault(str(book), []).append(v)

    def add_event(self, event_json: dict, team_map: dict) -> int:
        """Every book on one event. Returns how many books were read."""
        got = overrounds(event_json, team_map)
        for book, orr in got.items():
            self.add(book, orr)
        return len(got)

    def summary(self) -> dict:
        """``{book: {"games", "median", "min", "max"}}``, median-sorted.

        THE MEDIAN, not the mean, for the reason `consensus_h2h_fair`
        gives one level up: one suspended market quoted at a 20% hold
        should not be able to describe a book's whole slate.
        """
        import statistics
        out: dict = {}
        for book, vals in self.seen.items():
            if not vals:
                continue
            out[book] = {"games": len(vals),
                         "median": round(statistics.median(vals), 4),
                         "min": round(min(vals), 4),
                         "max": round(max(vals), 4)}
        return dict(sorted(out.items(), key=lambda kv: kv[1]["median"]))

    def missing(self, wanted) -> list:
        """Books we ASKED FOR that never quoted a two-way game price.

        The point of the whole census. Seven books were added to
        `oddsapi.DEFAULT_BOOKS` on the argument that they are free, and
        a book key that does not resolve on the live API is free in
        exactly the same way and worth nothing — indistinguishable from
        a book that resolved, from the board, until somebody counted.
        """
        from .sources.oddsapi import BOOK_TITLES
        have = {b.strip().lower() for b in self.seen}
        # BY TITLE, DEDUPED, because the book list is keyed by API key and
        # three of its keys — espnbet, thescorebet, thescore — are the
        # same book renamed twice. Listing it three times would read as
        # three missing books, and asking for all three aliases is the
        # right thing to do (they cost nothing and one of them resolves).
        out = set()
        for key in wanted or ():
            title = BOOK_TITLES.get(key, key)
            if title.strip().lower() not in have:
                out.add(title)
        return sorted(out)


def report(census: "Census", sport: str = "", wanted=None) -> str:
    """The build-log lines. Never raises, never returns "".

    A census that prints nothing on a day it read nothing is the failure
    shape this repository keeps finding in itself — `lineledger.
    record_note` and `rankings` were both dragged out of it. So the
    empty case gets a sentence naming the likely cause instead.
    """
    try:
        summ = census.summary()
    except Exception as exc:                                  # noqa: BLE001
        return f"  ⚠️  {sport.upper()} book margins: {type(exc).__name__} — {exc}"
    tag = f"{sport.upper()} " if sport else ""
    if not summ:
        return (f"  {tag}book margins: no book quoted both sides of any "
                f"game — either no odds pull reached this build, or the "
                f"payload carried one-sided prices only")
    lines = [f"  {tag}book margins, tightest first "
             f"({len(summ)} book(s) quoting both sides):"]
    for book, s in summ.items():
        lines.append(f"    {book:<22} {s['median']:.4f} median over "
                     f"{s['games']} game(s)  [{s['min']:.4f}-{s['max']:.4f}]")
    if wanted:
        gone = census.missing(wanted)
        if gone:
            # NAMED, not counted. "3 books missing" sends somebody to the
            # source to find out which; the names are the whole answer.
            lines.append(f"    asked for and never seen: {', '.join(gone)}")
    return "\n".join(lines)
