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
    return (-o) / ((-o) + 100.0) if o < 0 else 100.0 / (o + 100.0)


def _blank() -> dict:
    return {"n": 0, "err": 0.0, "led": 0, "moved": 0, "series": 0}


def _series(rows) -> dict:
    """Snapshots grouped by (player, market, side), each sorted by time."""
    out: dict = {}
    for r in rows:
        try:
            ts = float(r["ts"])
        except (KeyError, TypeError, ValueError):
            continue
        key = (r.get("player"), r.get("market"), r.get("side") or "over")
        out.setdefault(key, []).append((ts, r))
    for k in out:
        out[k].sort(key=lambda x: x[0])
    return out


def _book_prices(snap: dict, side: str) -> dict:
    """`{book: odds}` from one snapshot row, for the side we are measuring."""
    field = "under_odds" if str(side).lower().startswith("u") else "odds"
    books = snap.get("books")
    if isinstance(books, dict):
        return {str(b): v.get(field) if isinstance(v, dict) else v
                for b, v in books.items()}
    b = snap.get("book")
    return {str(b): snap.get(field)} if b else {}


def measure(rows) -> dict:
    """Per-book accuracy against the close, and how often it led.

    Returns `{book: {n, mae_pts, lead_rate, weight}}`. `mae_pts` is mean
    absolute error in implied-probability POINTS against that series'
    closing consensus — lower is sharper.
    """
    acc: dict = {}
    for (_p, _m, side), items in _series(rows).items():
        if len(items) < 2:
            continue
        t0, t1 = items[0][0], items[-1][0]
        if t1 <= t0:
            continue
        # The close: the median implied probability across books in the
        # LAST snapshot. A single book cannot define the truth it is then
        # graded against.
        last = _book_prices(items[-1][1], side)
        closes = sorted(p for p in (_implied(o) for o in last.values())
                        if p is not None)
        if not closes:
            continue
        close = closes[len(closes) // 2]

        cutoff = t0 + (t1 - t0) * EARLY_FRACTION
        first_move: dict = {}
        prev: dict = {}
        present: set = set()
        for ts, snap in items:
            for book, odds in _book_prices(snap, side).items():
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
    """
    try:
        from .sources.oddsapi import SHARP_BOOKS
    except Exception:                                       # noqa: BLE001
        SHARP_BOOKS = {"pinnacle"}
    named = {str(s).lower().replace(" ", "") for s in SHARP_BOOKS if s}

    def is_named(book: str) -> bool:
        b = str(book).lower().replace(" ", "")
        return any(s in b for s in named)

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


def payload(rows=None) -> dict:
    """The public report card (roadmap #7: "which book is slowest to
    react per market. Weekly rankings are shareable content").

    Facts about BOOKS, not about games: per book, how far its early
    prices sat from the closing consensus and how often it moved a
    number first, measured on our own snapshot history. No pick, no
    line, no model probability is in it — which is why it publishes
    free. A book below MIN_SERIES is listed unranked rather than
    dropped, so a thin sample reads as thin instead of as absent.
    """
    import datetime as _dt
    if rows is None:
        from .linemoves import load_history
        rows = load_history()
    measured = measure(rows)
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
