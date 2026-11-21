"""Which books are actually sharp — measured, not asserted.

NFL_MODEL §4 wants a sharp-book hierarchy and the row has read the same
way for months:

    | §4 Sharp-book hierarchy | 🟡 | … per-book sharpness weights 📋 |

Today the hierarchy is a LIST. `linemoves._is_sharp` asks
`oddsapi.SHARP_BOOKS`, which is a hand-written set — Pinnacle, Circa —
and everything in it counts equally while everything outside it counts for
nothing. That is received wisdom, and received wisdom about which book is
sharp is the single most repeated claim in this industry and the least
often checked.

We do not need to trust it. Every snapshot the movement engine has ever
written is a record of what each book said and when, and the closing
consensus is the nearest thing to truth anyone has. So sharpness becomes
arithmetic:

  LEAD      how often this book moved BEFORE the market did, and by how
            long. A book that consistently moves first is doing the
            pricing rather than copying it.
  ACCURACY  how close this book's early price sat to where the market
            eventually closed, in implied-probability points. A book that
            is already at the closing number when everyone else is 3
            points away knows something.

ACCURACY IS THE ONE THAT MATTERS and lead is the one that flatters. A book
can move first every single time by being twitchy — reacting to noise,
then reverting — and a hierarchy built on lead alone would rank the
jumpiest book top. Ranking is therefore on accuracy, with lead reported
beside it, and a book has to clear `MIN_SERIES` before it is ranked at
all.

NOTHING HERE PRICES ANYTHING. It reports weights; wiring them into the
consensus is a pricing change and `docs/THE_INFORMATION_TEST.md` is why
that waits: the claimed edge measures AUC 0.479, so a new input into the
pricing path is the exact move that finding rules out until something
moves that number. What this closes is the "we never measured it" half.
"""

from __future__ import annotations

#: A book judged on fewer series than this is not judged. Ten is not a
#: statistical bar, it is a floor against a book that quoted three props
#: once and ranked first on all of them.
MIN_SERIES = 10

#: How near the close a snapshot must be to count as "early" rather than
#: as the close itself. A book quoted only in the last minutes is not
#: predicting anything — it is reading the same screen as everyone else.
EARLY_FRACTION = 0.5


def _implied(odds) -> float | None:
    """American odds → implied probability, vig included.

    Vig included ON PURPOSE. The comparison here is book-to-book on the
    same side of the same market, so the hold cancels out of the
    DIFFERENCE, and de-vigging would need the other side which many of
    these snapshots do not carry.
    """
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return None
    if not o or abs(o) < 100:
        return None                     # an impossible price, not a price
    from .odds import american_to_prob
    return american_to_prob(o)


#: The card is cut from the last four weeks of snapshots. It is a weekly
#: ranking (roadmap #7), the books a bettor meets this month are the books
#: this month measures, and the daily chores read four weeks of the journal
#: rather than every line it has ever held.
WINDOW_DAYS = 28

#: How long before its game a prop's first price can sit: an NFL line opens
#: the week before. The read starts this much before the window, so a series
#: that closes inside the window is measured from its open rather than from
#: the window's edge; a series that closed before the window is not scored.
RUN_IN_DAYS = 7

#: A snapshot with no game start belongs to that day's series, complete once
#: the stream is this far past midnight UTC. The journal is appended in real
#: time, so an hour covers a writer that ran late.
DAY_GRACE_S = 3600.0


def _blank() -> dict:
    return {"n": 0, "err": 0.0, "led": 0, "moved": 0, "series": 0}


def _start(row: dict) -> float | None:
    """The game's start stamped on a snapshot, or None."""
    try:
        got = row.get("start_ts")
        return float(got) if got is not None else None
    except (TypeError, ValueError):
        return None


def _quotes(row: dict):
    """``(side, {book: odds})`` for each side one journal row prices.

    A row is one book's line, as `linemoves.record_snapshots` writes it:
    ``"book"``, ``"line"``, ``"over_odds"``, ``"under_odds"``. A fight is
    written once per fighter with the opponent's price as the under
    (`record_fight_snapshots`), so a fight's under is the other fighter's
    over — read once, not twice.
    """
    import sys as _sys
    book = row.get("book")
    if not book or book == "proxy":
        return
    book = _sys.intern(str(book))
    if row.get("over_odds") is not None:
        yield "over", {book: row["over_odds"]}
    if row.get("under_odds") is not None and row.get("market") != "moneyline":
        yield "under", {book: row["under_odds"]}


def _closed_series(rows, since: float | None = None):
    """Each series — one side of one line of one player's market in one
    game — as ``[(ts, {book: odds}), ...]`` in time order, handed over as
    soon as the stream has passed its game's start, then forgotten.

    THE SHAPE THE JOURNAL WRITES (the 2026-10-30 audit). This read a
    ``"books"`` map and an ``"odds"`` price that no writer has ever
    produced: `linemoves.record_snapshots` has written one row per book
    with ``"over_odds"`` and ``"under_odds"`` since 2026-07-22, before this
    module existed. Every row read as no price, `measure` came back empty,
    and the chores never wrote bookreport.json — the Line Shopping page has
    said "Not ranked yet" since the card shipped on 25 August, its tests
    green on a row shape of their own. Read as written now: one snapshot's
    books merged into one moment; the series keyed on the line (a price at
    24.5 says nothing about one at 25.5) and on the game (the same line
    next week is another market); both sides; and nothing at or after the
    start, because an in-play price is not a close.

    NEVER THE WHOLE JOURNAL AT ONCE (2026-10-07). Holding every series to
    the end holds every price the read has seen, and the daily chores were
    killed at ~1.15 GB under the unit's 1600M when that was whole rows. The
    journal is appended in time order, so a series is complete once the
    stream passes its game's start: it is handed over then and dropped,
    and memory holds only the games not yet played.

    ``since``: a series whose last pre-game price is older than this is
    read, to keep the stream whole, and not handed over.
    """
    import heapq
    live: dict = {}
    due: list = []                  # (complete at, n, key), soonest first
    n = 0

    def done(items) -> bool:
        items.sort(key=lambda x: x[0])
        return since is None or items[-1][0] >= since

    for r in rows:
        try:
            ts = float(r["ts"])
        except (KeyError, TypeError, ValueError):
            continue
        while due and due[0][0] <= ts:
            items = live.pop(heapq.heappop(due)[2], None)
            if items and done(items):
                yield items
        start = _start(r)
        if start is not None and ts >= start:
            continue                # in play: never a close
        day = int(ts // 86400)
        game = start if start is not None else ("day", day)
        for side, prices in _quotes(r):
            key = (r.get("player"), r.get("market"), side, r.get("line"), game)
            items = live.get(key)
            if items is None:
                items = live[key] = []
                n += 1
                heapq.heappush(due, (start if start is not None
                                     else (day + 1) * 86400 + DAY_GRACE_S, n, key))
            if items and items[-1][0] == ts:
                items[-1][1].update(prices)     # the same snapshot, another book
            else:
                items.append((ts, prices))
    for items in live.values():
        if items and done(items):
            yield items


def _score(items: list, acc: dict) -> None:
    """One series into the per-book tallies: each book's early error
    against the close, and who moved first."""
    if len(items) < 2:
        return
    t0, t1 = items[0][0], items[-1][0]
    if t1 <= t0:
        return
    # The close: the median implied probability across books in the LAST
    # snapshot. A single book cannot define the truth it is then graded
    # against, so a line only one book still quoted at the end has none.
    closes = sorted(p for p in (_implied(o) for o in items[-1][1].values())
                    if p is not None)
    if len(closes) < 2:
        return
    close = closes[len(closes) // 2]

    cutoff = t0 + (t1 - t0) * EARLY_FRACTION
    first_move: dict = {}
    prev: dict = {}
    present: set = set()
    for ts, prices in items:
        for book, odds in prices.items():
            p = _implied(odds)
            if p is None:
                continue
            present.add(book)
            # ACCURACY, from early snapshots only.
            if ts <= cutoff:
                a = acc.setdefault(book, _blank())
                a["n"] += 1
                a["err"] += abs(p - close) * 100.0
            # LEAD: the first time this book's price moved at all.
            if book in prev and abs(p - prev[book]) > 1e-9:
                first_move.setdefault(book, ts)
            prev[book] = p
    # SERIES COUNTS BEING QUOTED, NOT MOVING, and the first cut had it
    # the other way. A book that sits at the right number and never
    # moves recorded zero series, fell under MIN_SERIES and came back
    # unranked — the most accurate book on the board excluded for being
    # steady, which is the behaviour sharpness is supposed to reward.
    for book in present:
        acc.setdefault(book, _blank())["series"] += 1
    if first_move:
        earliest = min(first_move.values())
        for book, ts in first_move.items():
            a = acc.setdefault(book, _blank())
            a["moved"] += 1
            if ts <= earliest:
                a["led"] += 1


def measure(rows, since: float | None = None) -> dict:
    """Per-book accuracy against the close, and how often it led.

    Returns `{book: {n, series, mae_pts, lead_rate, weight}}`. `mae_pts` is
    mean absolute error in implied-probability POINTS against that series'
    closing consensus — lower is sharper. ``rows`` are journal rows, read
    once, in time order (see `_closed_series`).
    """
    acc: dict = {}
    for items in _closed_series(rows, since):
        _score(items, acc)

    out: dict = {}
    for book, a in acc.items():
        if not a["n"]:
            continue
        out[book] = {
            "n": a["n"],
            "series": a["series"],
            "mae_pts": round(a["err"] / a["n"], 3),
            # Lead rate is over series where this book MOVED: a book that
            # never moved led nothing, and dividing by every series it was
            # quoted in would report it as a follower rather than as
            # something the measure does not apply to.
            "lead_rate": (round(a["led"] / a["moved"], 3)
                          if a["moved"] else None),
        }
    # WEIGHTS FROM ACCURACY, NOT FROM LEAD. A twitchy book moves first by
    # reacting to noise and then reverting; ranking on lead would put it
    # top. Inverse error, normalised over the books that cleared the
    # floor, so the weights sum to 1 and a book nobody measured gets none.
    ranked = {b: v for b, v in out.items() if v["series"] >= MIN_SERIES}
    total = sum(1.0 / max(v["mae_pts"], 0.01) for v in ranked.values())
    for b, v in out.items():
        v["weight"] = (round((1.0 / max(v["mae_pts"], 0.01)) / total, 4)
                       if b in ranked and total else None)
    return out


def compare_to_the_list(measured: dict) -> dict:
    """What we ASSERT is sharp against what the snapshots say.

    The point of the whole module. `SHARP_BOOKS` is hand-written; this
    reports which of its members actually price better than the field, and
    which books outside it do.

    THE SAME PREDICATE THE SHOP USES. `engine.odds.is_sharp_book` is
    what `best_over_line` and `best_scorer_price` consult before they
    refuse to quote a price, so "asserted sharp" here and "not shopped"
    there cannot mean two different sets of books.
    """
    from .odds import is_sharp_book as is_named

    ranked = [(b, v) for b, v in measured.items()
              if v.get("weight") is not None]
    ranked.sort(key=lambda kv: kv[1]["mae_pts"])
    return {
        "ranked": [b for b, _ in ranked],
        "asserted_sharp": sorted(b for b, _ in ranked if is_named(b)),
        "measured_sharpest": [b for b, _ in ranked[:3]],
        # Named sharp and pricing worse than the median book: the finding
        # that would actually change something.
        "asserted_but_not": sorted(
            b for i, (b, _) in enumerate(ranked)
            if is_named(b) and i >= len(ranked) / 2),
        "sharp_but_unnamed": sorted(
            b for i, (b, _) in enumerate(ranked[:3]) if not is_named(b)),
        "n_ranked": len(ranked),
    }


def payload(rows=None, now: float | None = None) -> dict:
    """The public report card (roadmap #7: "which book is slowest to
    react per market. Weekly rankings are shareable content").

    Facts about BOOKS, not about games: per book, how far its early
    prices sat from the closing consensus and how often it moved a
    number first, measured on our own snapshot history. No pick, no
    line, no model probability is in it — which is why it publishes
    free. A book below MIN_SERIES is listed unranked rather than
    dropped, so a thin sample reads as thin instead of as absent.

    The last WINDOW_DAYS of the journal, read from RUN_IN_DAYS before
    them, one snapshot at a time: this runs in the daily chores (see
    `_closed_series`). ``rows`` given (the tests) are measured whole.
    """
    import datetime as _dt
    import time as _time
    since = None
    if rows is None:
        from .linemoves import stream_since
        since = (_time.time() if now is None else now) - WINDOW_DAYS * 86400
        rows = stream_since(since - RUN_IN_DAYS * 86400)
    measured = measure(rows, since)
    ranked = sorted(
        ({"book": b, "n": v["n"], "mae_pts": v["mae_pts"],
          "lead_rate": v["lead_rate"], "ranked": v.get("weight") is not None}
         for b, v in measured.items()),
        key=lambda r: (not r["ranked"],
                       r["mae_pts"] if r["mae_pts"] is not None else 99))
    return {
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "books": ranked,
        "min_series": MIN_SERIES,
        "window_days": WINDOW_DAYS,
        "vs_list": compare_to_the_list(measured),
        "note": ("Measured from our own line-history snapshots: each "
                 "book's early prices against that market's closing "
                 "consensus. Lower error = sharper; a high lead rate "
                 "with a high error is a book that moves first and "
                 "wrong."),
    }


def report(rows) -> str:
    m = measure(rows)
    c = compare_to_the_list(m)
    lines = ["", "=" * 70, "  WHICH BOOKS ARE ACTUALLY SHARP", "=" * 70]
    if not m:
        return "\n".join(lines + [
            "", "  No snapshot history yet. The movement engine writes it on",
            "  every build; this needs a few days of them.", ""])
    if not c["n_ranked"]:
        lines += ["", f"  {len(m)} book(s) seen, none with {MIN_SERIES}+ "
                      f"series yet — too early to rank.", ""]
    lines.append("")
    lines.append(f"  {'book':<22} {'MAE pts':>8} {'lead':>7} {'series':>7}"
                 f" {'weight':>8}")
    for b, v in sorted(m.items(), key=lambda kv: kv[1]["mae_pts"]):
        lead = f"{v['lead_rate']:.0%}" if v["lead_rate"] is not None else "—"
        w = f"{v['weight']:.3f}" if v.get("weight") is not None else "—"
        lines.append(f"  {b[:22]:<22} {v['mae_pts']:>8.3f} {lead:>7} "
                     f"{v['series']:>7} {w:>8}")
    lines += [
        "",
        "  MAE = mean distance from the closing consensus, in implied-",
        "  probability points, measured on the EARLY half of each series.",
        "  Lower is sharper. Ranked on accuracy and not on lead: a twitchy",
        "  book moves first by reacting to noise and reverting, and a",
        "  hierarchy built on lead would put it top.",
        ""]
    if c["asserted_but_not"]:
        lines += ["  NAMED SHARP, PRICING BELOW THE MEDIAN BOOK: "
                  + ", ".join(c["asserted_but_not"]), ""]
    if c["sharp_but_unnamed"]:
        lines += ["  SHARPEST THREE, NOT ON THE LIST: "
                  + ", ".join(c["sharp_but_unnamed"]), ""]
    lines += [
        "  Nothing prices from this. Wiring these weights into the",
        "  consensus is a pricing change, and the claimed edge measures",
        "  AUC 0.479 — see docs/THE_INFORMATION_TEST.md.",
        ""]
    return "\n".join(lines)
