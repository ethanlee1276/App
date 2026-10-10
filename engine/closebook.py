"""Each book's own pre-game close: the price a bet is fairly compared with.

Ethan, 2026-10-04 ("yes do it"): the journal banked ONE book's close
beside the BEST price on the screen — from the purchased history, whichever
book SQLite handed back last; from our own snapshots, the median across
books. Best-of-six against one book, or against the middle, reads as the
market "moving toward us" when nothing moved: NFL Most Likely read +1.7
points that way and −2.0 against its own books.

THE RULE: the close of the SAME book the bet was posted at; when that book
quoted nothing at the bet's line before kickoff, the BEST close across the
books (the price a line-shopper could still get), never the middle or an
arbitrary one. Pre-game rows only, same line, same side.

TWO STORES, in settling's order: the purchased odds history
(db.closing_odds_all_books, one row per book) and our own line snapshots
(engine/linemoves, one row per book per pull — kept apart here). The
snapshot file is streamed once and only rows for the bets in hand are
kept, so the 1 GB box never holds the history. Standard library only.
"""
from __future__ import annotations

import re
import sqlite3


def implied(o) -> float | None:
    try:
        o = float(o)
    except (TypeError, ValueError):
        return None
    if not o:
        return None
    return 100.0 / (o + 100.0) if o > 0 else -o / (100.0 - o)


def _bookkey(b) -> str:
    from .sources.oddsapi import BOOK_TITLES
    b = str(b or "")
    return re.sub(r"[^a-z0-9]", "", BOOK_TITLES.get(b, b).lower())


def _price(v) -> int | None:
    try:
        v = int(float(v))
    except (TypeError, ValueError):
        return None
    return v if abs(v) >= 100 else None


class SameBookCloses:
    """Each book's own pre-game close, for the same-book and best-book CLV.

    TWO STORES, the ones settling reads, in its order: the purchased odds
    history (db.closing_odds_all_books, one row per book) and our own line
    snapshots (engine/linemoves, one row per book per pull — settling
    medians them; this keeps each book apart). NFL closes are almost all
    in the snapshots. The snapshot file is streamed once and only rows for
    a bet in hand are kept, so the 1 GB box does not hold the history."""

    def __init__(self, hist, snapshots=None):
        self.hist = hist                     # the history DB connection, or None
        self._cache: dict = {}
        self._snap_rows = snapshots          # an iterable of snapshot rows, or None = the file
        self._snap: dict | None = None
        self._stamped_keys: set = set()

    def close_for(self, b: dict, dates: list | None = None, stamped=None):
        """The price to bank: the same book's close, else the best one."""
        same, best = self.same_and_best(b, dates, stamped)
        return same if same is not None else best

    def prepare(self, bets: list[dict]) -> None:
        """One pass over the snapshot file, keeping only rows for these bets.

        CHEAP ON PURPOSE (Ethan's first repair run, 2026-10-05, still going
        at four minutes): the market is checked before the name, and each
        raw name is normalised once, not once per row — the file holds
        every sport's every pull. The keys whose game start was recorded
        are kept as well, so the proven-close rule needs no second pass."""
        from . import linemoves
        from .sources.oddsapi import normalize_name
        names: dict = {}

        def norm(x):
            v = names.get(x)
            if v is None:
                v = names[x] = normalize_name(x or "")
            return v
        want = set()
        for b in bets:
            if b.get("player") and b.get("market") and b.get("line") is not None:
                want.add((norm(b["player"]), b["market"], round(float(b["line"]), 1)))
        markets = {k[1] for k in want}
        grouped: dict = {}
        rows = self._snap_rows if self._snap_rows is not None else linemoves.stream_history()
        for r in rows:
            try:
                if r.get("market") not in markets:
                    continue
                k = (norm(r["player"]), r["market"], round(float(r["line"]), 1))
                if k not in want:
                    continue
                float(r["ts"])
                grouped.setdefault((k[0], k[1], linemoves._slate_day(r), k[2]), []).append(r)
            except (KeyError, TypeError, ValueError, AttributeError):
                continue
        out, stamped = {}, set()
        for key, items in grouped.items():
            legs = linemoves._pregame_legs(items)
            if not legs or not legs[0][1]:
                continue
            if legs[0][0] is not None:
                stamped.add(key[:3])
            last: dict = {}
            for r in legs[0][1]:
                bk = _bookkey(r.get("book"))
                if bk and (bk not in last or float(r["ts"]) >= float(last[bk]["ts"])):
                    last[bk] = r
            out[key] = {bk: {"over": _price(r.get("over_odds")), "under": _price(r.get("under_odds"))}
                        for bk, r in last.items()}
        self._snap = out
        self._stamped_keys = stamped

    def _harvested(self, b: dict, dates: list, stamped=None) -> list:
        from . import db, ledger
        from .sources.oddsapi import normalize_name
        ck = (b["sport"], b["market"])
        if ck not in self._cache:
            try:
                self._cache[ck] = db.closing_odds_all_books(self.hist, *ck) if self.hist is not None else {}
            except sqlite3.Error:
                self._cache[ck] = {}
        who = normalize_name(b["player"])
        got = ledger.close_at(self._cache[ck], who, dates) or []
        out = []
        for q in got:
            if ledger._pregame_close(q, b) is None:
                continue
            # Settling's rule (`ledger.settle_from_history`): a harvested
            # row nothing proves pre-game loses to a snapshot close cut at
            # a recorded start — the keys this object's own snapshot pass
            # saw stamped, plus any set the caller already holds.
            if not ledger._close_proven(q, b):
                keys = self._stamped_keys | set(stamped or ())
                if any((who, b["market"], d) in keys for d in dates):
                    continue
            price = ledger._close_odds_from(q, b["line"], b["side"])
            if price is not None:
                out.append((_bookkey(q.get("book")), price))
        return out

    def quotes(self, b: dict, dates: list | None = None, stamped=None) -> list:
        if not b.get("player") or not b.get("market"):
            return []
        from . import ledger
        from .sources.oddsapi import normalize_name
        if dates is None:
            try:
                dates = ledger.close_dates(self.hist, b) if self.hist is not None else []
            except Exception:                               # noqa: BLE001
                dates = []
        dates = list(dates or []) or [str(b.get("game_day") or b.get("date") or "")[:10]]
        got = self._harvested(b, dates, stamped)
        if got or self._snap is None or b.get("line") is None:
            return got
        side = "under" if str(b.get("side") or "OVER").upper() == "UNDER" else "over"
        who, ln = normalize_name(b["player"]), round(float(b["line"]), 1)
        for d in dates:
            books = self._snap.get((who, b["market"], d, ln))
            if books:
                return [(bk, px[side]) for bk, px in books.items() if px[side] is not None]
        return []

    def same_and_best(self, b: dict, dates: list | None = None, stamped=None):
        """(the same book's close, the best close across books) — either None."""
        if self._snap is None and self._snap_rows is not None:
            self.prepare([b])
        qs = self.quotes(b, dates, stamped)
        if not qs:
            return None, None
        mine = _bookkey(b.get("book"))
        same = next((p for k, p in qs if k and k == mine), None)
        best = min((p for _k, p in qs), key=lambda p: implied(p))   # longest price = least implied
        return same, best
