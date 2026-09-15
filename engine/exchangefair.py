"""The exchange's own number, hung on the rows that can use it.

Ethan, 2026-09-15: "I want to make sure that we're using every single
piece of data. If there's any data that we're not pulling that we need
to pull ... we need to start doing that."

WE WERE ALREADY PULLING THE BEST ONE AND NOT USING IT. `engine/sources
/kalshi` fetches a CFTC-regulated exchange, keyless, in all fifty
states. It already parses the order book, already matches a market to
one of our games (`match_game`), and already knows which side the YES
contract is (`yes_team`). It fed the Prediction Desk and nothing else —
so the Pick of the Day, a feature built entirely around finding a
trustworthy fair and comparing it to a soft price, never saw it.

WHY AN EXCHANGE MID BEATS A SHARP BOOK'S DE-VIG, which is the whole
argument for ranking it first. `kalshi.parse_markets` says it plainly:

    an exchange's mid IS the market's probability, where a sportsbook's
    line has the book's margin baked in and has to be de-vigged on an
    assumption.

De-vigging Pinnacle means assuming HOW its margin is spread across the
two sides — `odds.devig_two_way` divides it proportionally, and the
favourite-longshot literature says books do not actually price that way.
An exchange has no margin to strip: two people take opposite sides at a
price they both chose. There is nothing to assume.

HOW BIG THAT ASSUMPTION IS, MEASURED. This paragraph used to say the
assumption was "small in the even-money band this feature lives in",
which was true and carried no number, so it could neither be checked nor
argued with. `bookvig.assumption_points` is the number: the gap between
the three standard de-vigs — proportional, additive and power — on one
real pair. Worst case anywhere in this feature's price band (a price
implying 0.345 at +190 up to 0.587 at -142):

    Pinnacle's ~3% hold       0.70 points     a third of `potd.MIN_EV`
    a soft book's ~5%         1.18 points     three fifths of it
    an exchange's 0%          0.00 points

Nearer even money it is half that — 0.39 and 0.66 over the narrower
range the side actually taken sits in. `engine/bookvig` carries the full
table and the note on why quoting only that narrower one was misleading.

AND IT IS SMALLER THAN THE ARGUMENT NEEDED. Seven tenths of a point of
arithmetic certainty does not justify ranking a venue above a sharp book
on its own, so the ladder's ordering does NOT rest on this paragraph.
What it rests on is the second sentence up top: an exchange mid is a
price two people chose, where a book's line is one firm's opinion with a
business model attached. That is a claim about whose number it is, not
about how the margin comes off, and `booksharp` is where it gets tested.

WHY THE GAP IS SO SMALL HERE and would not be elsewhere: all three
methods must return two numbers summing to one, so at a true 50/50 they
cannot disagree at all, whatever the margin. The disagreement grows with
DISTANCE FROM EVEN MONEY, and `potd.MIN_ODDS`/`MAX_ODDS` pin this board
near even money by construction. On a +900 touchdown longshot the same
arithmetic moves 3.66 points, which is why `engine/devig` exists and
takes the question seriously one board over.

THREE GUARDS, AND THEY MATTER MORE THAN THE SOURCE DOES. A number from
an exchange is only better than a book's if the book behind it is real:

  A TWO-SIDED BOOK, never a last trade. `parse_markets` already reports
  which it is (`price_basis`), and says why: "a fair value with no book
  behind it is a weaker claim". One stale print at 62c on a market
  nobody has touched since Tuesday is not the market's opinion.

  A TIGHT BOOK. The mid of a quote 10 cents wide carries five points of
  slop in either direction, and `potd.MIN_EV` is two. A wide book cannot
  settle a question this fine, so it does not get to.

  LIQUIDITY, because a two-sided book with four contracts behind it is
  two people, not a market.

NOTHING HERE PRICES A BET. It hangs `exchange_fair` on rows it can
match, with the evidence of its own quality beside it, and
`potd.evidence` decides what to do with that. A row it cannot match is
left exactly as it was.
"""

from __future__ import annotations

#: The widest two-sided book whose mid is still worth trusting, in cents
#: of probability. Read this against `potd.MIN_EV` (0.02): a book 10
#: cents wide puts the true number anywhere in a five-point range on
#: either side of the mid, which is more slop than the entire edge this
#: feature asks for. Four cents leaves two, which is the most that can
#: be tolerated before the guard stops meaning anything.
MAX_SPREAD_CENTS = 4.0

#: A two-sided book with almost nothing behind it is two people, not a
#: market. NOT A MEASURED FIGURE — it is a floor against the obviously
#: thin, chosen before there was any tape to fit it on, and the honest
#: thing is to say so on the constant rather than to imply it was
#: derived. `kalshi.price_series` is the store that will eventually
#: answer what this should be.
MIN_LIQUIDITY = 250.0

#: Markets this can speak to. A game-winner contract is a moneyline and
#: nothing else — Kalshi does not list our spread or total, and pretending
#: a win probability settles a run line is the kind of silent coercion
#: this codebase keeps finding in its own history.
MARKETS = ("moneyline",)


def quality(row: dict) -> str:
    """"" if this exchange market's price is worth using, else why not."""
    if str(row.get("price_basis") or "") != "book":
        return "no two-sided book — only a last trade"
    spread = row.get("spread_cents")
    if spread is None:
        return "no quoted spread"
    try:
        if float(spread) > MAX_SPREAD_CENTS:
            return f"book is {float(spread):.0f}c wide"
    except (TypeError, ValueError):
        return "unreadable spread"
    liq = max(float(row.get("volume_24h") or 0.0),
              float(row.get("open_interest") or 0.0))
    if liq < MIN_LIQUIDITY:
        return f"thin — {liq:.0f} against a {MIN_LIQUIDITY:.0f} floor"
    return ""


def fair_for_team(market: dict, team: str, game: dict) -> float | None:
    """P(this team wins) off the exchange, or None.

    The YES side is one team; the other team's probability is one minus
    it. `kalshi.yes_team` is what knows which, and it is asked rather
    than guessed at — a side error here would not look like a bug, it
    would look like a confident pick on the wrong team.
    """
    from .sources import kalshi
    prob = market.get("prob")
    if prob is None:
        return None
    try:
        p = float(prob)
    except (TypeError, ValueError):
        return None
    if not (0.0 < p < 1.0):
        return None
    # `yes_team` NAMES A ROLE, NOT A CLUB — it returns "home" or "away"
    # (see its docstring: four deciders, each resolving to a side of the
    # matched game). The first draft here compared that string to a team
    # ABBREVIATION, which never matches, so BOTH teams fell through to
    # the 1-p branch and each side of every game was priced at the other
    # side's number. Caught by
    # `test_the_yes_side_and_the_other_side_are_not_confused`, which is
    # the test written precisely because this failure does not look like
    # a bug — it looks like a confident pick on the wrong team.
    yes = kalshi.yes_team(market, game)
    if yes not in ("home", "away"):
        return None
    t = str(team or "").strip().upper()
    if not t:
        return None
    yes_code = str(game.get(yes) or "").strip().upper()
    other = "away" if yes == "home" else "home"
    other_code = str(game.get(other) or "").strip().upper()
    if not yes_code or not other_code:
        return None
    if t == yes_code:
        return round(p, 4)
    if t == other_code:
        # The other side of a two-outcome market. Only safe BECAUSE the
        # market is two-outcome: a game-winner contract has no draw.
        return round(1.0 - p, 4)
    # NOT A SIDE OF THIS GAME AT ALL. Returning either number here would
    # be inventing a price for a team the contract says nothing about.
    return None


def attach(rows, markets, games, sport: str = "") -> dict:
    """Hang `exchange_fair` on every row an exchange market can price.

    Returns a census of what happened, in the shape every other funnel in
    this codebase keeps: a day where nothing attached should say which
    step lost the rows rather than leaving a caller to guess.
    """
    from .sources import kalshi
    census: dict = {"rows": 0, "attached": 0}

    def _tally(why: str) -> None:
        census[why] = census.get(why, 0) + 1

    usable = []
    for m in markets or []:
        if sport and kalshi.sport_of(m) not in (None, sport):
            continue
        why = quality(m)
        if why:
            _tally(why)
            continue
        usable.append(m)
    census["usable markets"] = len(usable)
    if not usable:
        return census

    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("market") or "") not in MARKETS:
            continue
        census["rows"] += 1
        team = row.get("team") or row.get("player") or ""
        hit = None
        for m in usable:
            g = kalshi.match_game(m, games or [])
            if not g:
                continue
            fair = fair_for_team(m, team, g)
            if fair is not None:
                hit = (fair, m)
                break
        if hit is None:
            _tally("no exchange market for this game")
            continue
        fair, m = hit
        row["exchange_fair"] = fair
        row["exchange_ticker"] = m.get("ticker", "")
        row["exchange_spread_cents"] = m.get("spread_cents")
        census["attached"] += 1
    return census


def attach_to_board(result: dict, sport: str) -> str:
    """Hang the exchange's fair on a finished board. Returns a log line.

    ONE HOOK, CALLED FROM EVERY BUILD, for the reason `potd.attach` and
    `livepicks.attach_tracker` each exist: four builds assembling this
    inline is four chances for one to drift, and the drift shows up as a
    sport whose Pick of the Day quietly has a worse fair than the others.

    NEVER RAISES, and it fetches from a live venue, so that promise is
    doing real work: an exchange having a bad morning must cost us the
    exchange tier for one build and nothing else. The failure lands in
    the JSON where the page and `potd_report` can see it, rather than
    only in a log the launcher swallows.

    ORDERED BEFORE `potd.attach` BY THE CALLER, necessarily — the fair
    has to be on the row before the selector reads the row. A build that
    calls them the other way round gets a board with exchange fairs on
    it and a pick chosen without them, which would look like nothing at
    all going wrong.
    """
    rows = result.get("most_likely") or []
    if not rows:
        return f"  {sport.upper()} exchange fair: no board rows to price"
    try:
        from .sources import kalshi
        markets, meta = kalshi.fetch_sports_markets(kalshi.parse_markets)
    except Exception as exc:                                  # noqa: BLE001
        result["exchange_fair_error"] = f"{type(exc).__name__}: {exc}"
        return f"  ⚠️  {sport.upper()} exchange fair: feed unavailable — {exc}"
    try:
        census = attach(rows, markets, result.get("games") or [], sport)
    except Exception as exc:                                  # noqa: BLE001
        result["exchange_fair_error"] = f"{type(exc).__name__}: {exc}"
        return f"  ⚠️  {sport.upper()} exchange fair: {type(exc).__name__} — {exc}"
    result["exchange_fair_census"] = census
    got, seen = census.get("attached", 0), census.get("rows", 0)
    if not seen:
        return (f"  {sport.upper()} exchange fair: no moneyline rows on the "
                f"board to price")
    if not got:
        # WHY NOTHING LANDED, not just that nothing did. The census keys
        # are the quality reasons from `quality()`, so this names the
        # book that was too wide or too thin rather than shrugging.
        why = ", ".join(f"{n} {k}" for k, n in sorted(census.items())
                        if k not in ("rows", "attached", "usable markets"))
        return (f"  {sport.upper()} exchange fair: 0 of {seen} row(s) priced"
                + (f" — {why}" if why else ""))
    return (f"  {sport.upper()} exchange fair: {got} of {seen} moneyline "
            f"row(s) carry an exchange number "
            f"({census.get('usable markets', 0)} usable market(s))")
