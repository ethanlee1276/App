"""The closing numbers college football is graded against.

    https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/
        main/betting/csv/cfb_line_odds.csv.gz

WHAT WAS MISSING AND WHAT IT COST. `engine.sources.cfbfastr` backfilled
3,132 FBS games and stored ``spread=None, total=None`` on every one of
them, with a comment saying so: that feed carries scores and Elo, not
betting lines, and writing a 0.0 would have been a fake number reading as
a pick'em on three thousand games. The consequences ran everywhere:

  * `engine.gamecal` could not measure college football's market
    haircut, so the CFB board priced spreads and totals against a flat
    0.5 guess — the one thing the site's own doctor kept flagging as
    "staking on the unmeasured guess";
  * `engine.cfbtdfit` had no historical implied total, so the college
    touchdown model could only be graded on its role chain with the
    market's own inputs held neutral;
  * nothing on the college board had ever been compared with the number
    a bettor could actually have taken.

The file was in the same repository the whole time, under a name three
guesses missed. 1,183,530 rows, seven megabytes gzipped, every season
back to 2006 — and it joins on ``game_id``, which is ESPN's, which is
what our games table already keys on.

THE SHAPE, AND THE THREE THINGS THAT WILL BITE. One row per game per
market per side per book.

**``abbr`` is not an abbreviation on modern rows.** It holds the school
name ("Penn State"), and on TOTAL rows it holds "over" or "under". Older
seasons really do use abbreviations ("UTH" for Utah), which is why the
home side is resolved by matching ``abbr`` against the school name the
schedule already stored for THAT GAME rather than through any table. A
game where neither side matches is skipped, so the pre-2010 rows this
project does not ingest simply never join.

**A spread is one team's number, and both are present.** The row for the
home school is the one our ``games.spread`` column wants — negative when
the home side is favoured, the same convention nflverse uses. Verified
rather than assumed, twice: within a book the two sides must sum to zero
or that quote is dropped, and across 3,126 graded games the team with
the negative number won 72.7%, which is what a real spread does. The
residual is unbiased — margin plus spread averages +0.20 points.

**``lines`` is the close and ``opening_lines`` is the opener.** A book
with no ``lines`` value has no close, and its opener is NOT substituted:
an opener in a column labelled "close" is exactly the kind of number
that reads as measured and is not.

Books disagree, so the stored number is the MEDIAN across every book
that quoted the game. Median, not mean: one book leaving a stale number
up moves a mean and cannot move a median past its neighbours.

Standard library only.
"""

from __future__ import annotations

import csv
import io

from .fetch import fetch_text, DataUnavailable

LINES_URL = ("https://raw.githubusercontent.com/sportsdataverse/"
             "cfbfastR-data/main/betting/csv/cfb_line_odds.csv.gz")

#: The values this feed uses for "no value".
BLANK = ("", "NA", "NULL", "None", "nan")

#: How far the two sides of one book's spread may miss cancelling before
#: the quote is dropped. They are the same number with opposite signs;
#: anything else means the row pair is not what it claims to be.
PAIR_TOLERANCE = 0.11

#: A spread this big is not a spread. College football's widest real
#: numbers sit around 60 in an FBS-vs-FCS mismatch; this project only
#: ingests FBS vs FBS, where the record high is nearer 50.
MAX_SPREAD = 80.0

#: Totals outside this are a data error, not a shootout.
MIN_TOTAL, MAX_TOTAL = 20.0, 110.0

#: How the total's two rows identify themselves.
OVER, UNDER = "over", "under"

#: A moneyline outside this is not a price anyone offered. College has
#: genuine 10,000-to-1 mismatches in September; beyond that the cell is
#: a data error, and a five-figure favourite prices to a certainty the
#: de-vig cannot do anything sensible with.
MIN_MONEYLINE, MAX_MONEYLINE = -50_000, 50_000


def _blank(value) -> bool:
    return str(value).strip() in BLANK


def _num(value):
    if _blank(value):
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _median(values: list) -> float:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def parse_lines(rows, games: dict, seasons=None) -> dict:
    """Closing spread and total per game, from every book that quoted it.

    ``games`` maps game id → ``{"home_name", "away_name"}`` — what
    `engine.sources.cfbfastr` already stored — so the home side of a
    spread is identified per game and never through a name table.

    Returns ``{"lines": {game_id: {"spread", "total", "ml",
    "spread_books", "total_books", "ml_books"}}, "skipped": {reason: n}}``.
    A game reaches ``lines`` only for the markets it actually has; a
    spread with no usable pair does not borrow the total's game.

    ``ml`` is ``[home price, away price]`` in American odds, the shape
    `gamebacktest.schedule_moneylines` reads. Unlike the spread and the
    total it needs BOTH sides — a moneyline is only usable de-vigged,
    and one price alone cannot be de-vigged.
    """
    want = {int(s) for s in seasons} if seasons else None
    pairs: dict = {}          # (game, book) -> {"home": x, "away": y}
    totals: dict = {}         # game -> [values]
    prices: dict = {}         # (game, book) -> {"home": p, "away": p}
    skipped: dict[str, int] = {}

    def skip(reason):
        skipped[reason] = skipped.get(reason, 0) + 1

    for r in rows or []:
        gid = str(r.get("game_id") or "").strip()
        game = games.get(gid)
        if not game:
            skip("game not ingested")
            continue
        season = _num(r.get("season"))
        if want is not None and (season is None or int(season) not in want):
            skip("season not requested")
            continue
        market = str(r.get("market_type") or "").strip().lower()
        side = str(r.get("abbr") or "").strip()
        value = _num(r.get("lines"))
        book = str(r.get("book") or "").strip()
        # A MONEYLINE LIVES IN A DIFFERENT COLUMN. Its price is in
        # ``odds`` and its ``lines`` cell is empty, so the missing-close
        # guard below would throw away every moneyline row in the file.
        if market == "money_line":
            price = _num(r.get("odds"))
            if price is None:
                skip("no moneyline price from this book")
            elif side == game.get("home_name"):
                prices.setdefault((gid, book), {})["home"] = price
            elif side == game.get("away_name"):
                prices.setdefault((gid, book), {})["away"] = price
            else:
                skip("moneyline side matched neither school")
            continue
        if value is None:
            # No close from this book. Its opener is not a close and is
            # deliberately not substituted.
            skip("no closing number from this book")
            continue
        if market == "spread":
            slot = pairs.setdefault((gid, book), {})
            if side == game.get("home_name"):
                slot["home"] = value
            elif side == game.get("away_name"):
                slot["away"] = value
            else:
                skip("spread side matched neither school")
        elif market == "total":
            lowered = side.lower()
            if lowered == OVER:
                totals.setdefault(gid, []).append(value)
            elif lowered != UNDER:
                skip("total side was neither over nor under")

    spreads: dict = {}
    for (gid, _book), slot in pairs.items():
        home, away = slot.get("home"), slot.get("away")
        if home is None:
            skip("no home-side spread from this book")
            continue
        if away is not None and abs(home + away) > PAIR_TOLERANCE:
            # The two sides of one book's spread are the same number with
            # opposite signs. When they are not, the pair is not what it
            # claims and the quote is dropped rather than half-read.
            skip("the two sides of the spread did not cancel")
            continue
        if abs(home) > MAX_SPREAD:
            skip("spread outside any plausible range")
            continue
        spreads.setdefault(gid, []).append(home)

    #: A moneyline needs BOTH sides, so books are combined in
    #: PROBABILITY space rather than on the American numbers: the median
    #: of -110 and +105 is not a price, and averaging across the
    #: ±100 discontinuity is worse. Each book's pair is de-vigged to a
    #: fair home probability, those are combined, and the consensus is
    #: written back out as a fair two-way pair.
    consensus: dict = {}
    for (gid, _book), slot in prices.items():
        home, away = slot.get("home"), slot.get("away")
        if home is None or away is None:
            skip("only one side of the moneyline from this book")
            continue
        if not (MIN_MONEYLINE <= home <= MAX_MONEYLINE
                and MIN_MONEYLINE <= away <= MAX_MONEYLINE):
            skip("moneyline outside any plausible range")
            continue
        fair = _fair_home(home, away)
        if fair is None:
            skip("moneyline pair did not de-vig")
            continue
        consensus.setdefault(gid, []).append(fair)

    out: dict = {}
    for gid, values in spreads.items():
        out.setdefault(gid, {})["spread"] = round(_median(values), 2)
        out[gid]["spread_books"] = len(values)
    for gid, values in totals.items():
        usable = [v for v in values if MIN_TOTAL <= v <= MAX_TOTAL]
        if not usable:
            skip("total outside any plausible range")
            continue
        out.setdefault(gid, {})["total"] = round(_median(usable), 2)
        out[gid]["total_books"] = len(usable)
    for gid, values in consensus.items():
        fair = _median(values)
        out.setdefault(gid, {})["ml"] = [_american(fair), _american(1.0 - fair)]
        out[gid]["ml_books"] = len(values)
    return {"lines": out, "skipped": skipped}


def _implied(american: float) -> float:
    """An American price as its implied probability, vig included."""
    return (-american) / (-american + 100.0) if american < 0 \
        else 100.0 / (american + 100.0)


def _fair_home(home: float, away: float):
    """The home side's de-vigged probability, or None."""
    total = _implied(home) + _implied(away)
    if total <= 0:
        return None
    fair = _implied(home) / total
    return fair if 0.0 < fair < 1.0 else None


def _american(p: float) -> int:
    """A fair probability back as an American price.

    Written out as a PAIR of fair prices rather than kept as a
    probability because that is the shape every consumer already reads —
    `gamebacktest.schedule_moneylines` hands two American numbers to
    `odds.devig_two_way`, which will find no vig in them and return the
    same probability back. Storing the consensus any other way would
    mean teaching four call sites a second format.
    """
    p = min(max(float(p), 1e-4), 1.0 - 1e-4)
    if p >= 0.5:
        return int(round(-100.0 * p / (1.0 - p)))
    return int(round(100.0 * (1.0 - p) / p))


def _stream(url: str, cache_name: str, ttl: int):
    """Rows of the cached CSV without materialising it as dicts.

    `fetch_text` gunzips a ``.gz`` body itself, so this reads the
    seven-megabyte download as one string and hands the reader on.
    """
    return csv.DictReader(io.StringIO(fetch_text(url, cache_name, ttl=ttl)))


def fetch_lines(games: dict, seasons=None, ttl: int = 86400 * 3) -> dict:
    """Closing numbers straight off the mirror.

    A three-day cache: the file is rebuilt during the season as games
    finish, and a stale copy costs the most recent week's closes.
    """
    return parse_lines(_stream(LINES_URL, "cfb_line_odds.csv", ttl),
                       games, seasons)


def load_lines(path, games: dict, seasons=None) -> dict:
    """The same, from a file already on disk — for an offline backfill."""
    with open(path, encoding="utf-8", errors="replace", newline="") as fh:
        return parse_lines(csv.DictReader(fh), games, seasons)


__all__ = ["LINES_URL", "PAIR_TOLERANCE", "MAX_SPREAD", "MIN_TOTAL",
           "MAX_TOTAL", "MIN_MONEYLINE", "MAX_MONEYLINE", "DataUnavailable",
           "fetch_lines", "load_lines", "parse_lines"]
