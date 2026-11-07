"""Every book's line on one market over time, and the steam marks: where the books moved together.

Ethan, 2026-10-15, from the brainstorm he asked to have built: a line
movement chart with every book on it and the steam marked. The pick page
already draws one line (engine/linetape: the best number a bettor could
have taken, minute by minute). This reads the same table, `odds_history`,
one series per book instead, so a reader can see who moved first and who
was left behind.

WHAT IS STORED. Game lines: the best price and the sharp book's, every
build (engine/lineledger). Player props: every book's number for the men
the builds watch — anyone on an injury report, and since 2026-10-15
anyone with an open pick on the board (engine/proptape) — written only
when it changes. A market nobody watched has no per-book history, and the
chart says so rather than drawing one line and calling it the market.

STEAM, WRITTEN NOT MEASURED. A mark where, within STEAM_MIN minutes, at
least STEAM_BOOKS different books (and at least half of the books quoting
it then) moved the same way: the line itself, or with the line unchanged
the over's price by at least STEAM_PROB of implied chance. That is the
shape a sharp bet leaves on a market. It has not been scored against
results, so the page calls it a mark, not a signal, and nothing on the
board reads it. A market with fewer than STEAM_BOOKS books can carry none.

Read-only.
"""

from __future__ import annotations

import datetime as _dt
import math

#: How far back the chart reaches by default.
HOURS = 48
#: The window books must move together inside.
STEAM_MIN = 15
#: Books that must move together.
STEAM_BOOKS = 3
#: A price move (line unchanged) that counts: implied chance of the over.
STEAM_PROB = 0.03
#: Books drawn, most quotes first; the rest are named but not drawn.
MAX_BOOKS = 10


def _implied(odds) -> float | None:
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return None
    if o == 0:
        return None
    return 100.0 / (o + 100.0) if o > 0 else -o / (-o + 100.0)


def _when(at: str) -> _dt.datetime | None:
    try:
        return _dt.datetime.strptime(str(at)[:16], "%Y-%m-%dT%H:%M").replace(tzinfo=_dt.timezone.utc)
    except ValueError:
        return None


def series(conn, sport: str, player: str, market: str, hours: int = HOURS,
           now: _dt.datetime | None = None) -> dict:
    """``{book: [{"at", "line", "over", "under"}]}``, oldest first, each
    book's own quotes. Several names for the player are tried (the books'
    folded spelling and the one given), the first that has rows wins."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    since = (now - _dt.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:00Z")
    names = [player]
    try:
        from .sources.oddsapi import normalize_name
        folded = normalize_name(player)
        if folded and folded not in names:
            names.insert(0, folded)
    except Exception:                                         # noqa: BLE001
        pass
    for name in names:
        rows = conn.execute(
            "SELECT taken_at, book, line, over_odds, under_odds FROM odds_history "
            "WHERE sport=? AND player=? AND market=? AND taken_at >= ? ORDER BY taken_at",
            (sport, name, market, since)).fetchall()
        if rows:
            out: dict = {}
            for at, book, line, over, under in rows:
                pts = out.setdefault(str(book or ""), [])
                pt = {"at": at, "line": line, "over": over, "under": under}
                # One point per distinct number: the tape writes on change,
                # the ledger every build, and a repeat is not a move.
                if not pts or (pts[-1]["line"], pts[-1]["over"], pts[-1]["under"]) != (line, over, under):
                    pts.append(pt)
            return out
    return {}


def moves(books: dict) -> list[dict]:
    """Every change a book made: ``{"at", "book", "sign", "kind", "from",
    "to"}``. ``sign`` +1 is pressure on the over (the line up, or the
    over dearer at the same line), -1 the under."""
    out = []
    for book, pts in books.items():
        for a, b in zip(pts, pts[1:]):
            if a["line"] is not None and b["line"] is not None and b["line"] != a["line"]:
                out.append({"at": b["at"], "book": book, "sign": 1 if b["line"] > a["line"] else -1,
                            "kind": "line", "from": a["line"], "to": b["line"]})
                continue
            pa, pb = _implied(a["over"]), _implied(b["over"])
            if pa is not None and pb is not None and abs(pb - pa) >= STEAM_PROB:
                out.append({"at": b["at"], "book": book, "sign": 1 if pb > pa else -1,
                            "kind": "price", "from": a["over"], "to": b["over"]})
    return sorted(out, key=lambda m: m["at"])


def steam(books: dict) -> list[dict]:
    """The marks: ``{"at", "sign", "books", "kind"}``, each move used once."""
    ms = moves(books)
    first = {b: _when(p[0]["at"]) for b, p in books.items() if p}
    used: set = set()
    out = []
    for i, m in enumerate(ms):
        if i in used:
            continue
        t0 = _when(m["at"])
        if t0 is None:
            continue
        end = t0 + _dt.timedelta(minutes=STEAM_MIN)
        group = {m["book"]: i}
        for j in range(i + 1, len(ms)):
            n = ms[j]
            tj = _when(n["at"])
            if tj is None or tj > end:
                break
            if j not in used and n["sign"] == m["sign"] and n["book"] not in group:
                group[n["book"]] = j
        quoting = sum(1 for t in first.values() if t is not None and t <= end)
        if len(group) >= max(STEAM_BOOKS, math.ceil(quoting / 2)):
            used.update(group.values())
            kinds = {ms[k]["kind"] for k in group.values()}
            out.append({"at": m["at"], "sign": m["sign"], "books": sorted(group),
                        "kind": "line" if "line" in kinds else "price"})
    return out


def chart(conn, sport: str, player: str, market: str, hours: int = HOURS,
          now: _dt.datetime | None = None) -> dict:
    """The page's payload: the books drawn (most quotes first), any left
    off, the steam marks and the window."""
    books = series(conn, sport, player, market, hours, now)
    order = sorted(books, key=lambda b: (-len(books[b]), b))
    drawn = {b: books[b] for b in order[:MAX_BOOKS]}
    return {"sport": sport, "player": player, "market": market, "hours": hours,
            "books": drawn, "more": order[MAX_BOOKS:], "steam": steam(books),
            "n_books": len(books), "rule": {"minutes": STEAM_MIN, "books": STEAM_BOOKS, "prob": STEAM_PROB}}
