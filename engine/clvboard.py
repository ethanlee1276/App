"""Does this thing beat the closing line? Cut by sport and by market.

THE MOST PERSUASIVE THING A PAID PRODUCT CAN SHOW, and persuasive
exactly because it can come out badly. A win-loss record over a few
hundred bets is mostly variance wearing a percentage sign. Closing-line
value is not: it grades the DECISION the moment the game starts, it
accrues on every settled bet rather than only the ones that won, and a
model that beats the close persistently is picking up something the
market had not priced yet. If ours does not, this page says so.

WHAT A ROW IS. One sport-and-market pair: how many settled picks it
holds, how many of those have a real closing line stored beside them,
the average line movement in our favour, and how often the market moved
our way at all. The SAMPLE SIZE sits beside every number, because a
+0.4 average over nine bets is not a finding and printing it next to a
+0.4 over four hundred would be the most flattering lie available.

THE VERDICT IS GATED, THE NUMBERS ARE NOT. Below ``ledger.CLV_MIN_N``
captured closes a row shows its counts and says "not enough yet" where
the verdict would be. It does not hide the average — hiding a number
until it looks good is the failure mode this whole page exists to
refuse — it declines to CALL it.

COVERAGE IS PART OF THE ANSWER. A market with 200 settled picks and 12
closes is not a market with a good CLV number; it is a market we cannot
grade, and the row says which of the two it is. That is why a harvest
gap (CFB before 2026-08-26, and NFL touchdowns before the same day)
shows here as missing coverage rather than as a silently absent row.

Standard library only; every input is already in the journal.
"""

from __future__ import annotations

#: Rows thinner than this are pooled into their sport's "other markets"
#: line rather than printed one-by-one. A page of nine-bet rows is a
#: list, not a scoreboard.
MIN_ROW_N = 5


def _label(market: str) -> str:
    """Words for a market key. The shared map first (it covers the
    football markets), then a plain de-underscoring — a market with no
    entry reads as itself rather than disappearing behind a "?"."""
    try:
        from .models import MARKET_LABELS
        if market in MARKET_LABELS:
            return MARKET_LABELS[market]
    except Exception:                                        # noqa: BLE001
        pass
    words = str(market or "").replace("_", " ").strip()
    return words.title() if words else "?"


def _rows(conn, category: str, since: str | None):
    q = ("SELECT sport, market, side, line, closing_line, status "
         "FROM bets WHERE status IN ('won','lost','push') "
         "AND category=? AND stake_units > 0")
    args: list = [category]
    if since:
        q += " AND date >= ?"
        args.append(since)
    return conn.execute(q, args).fetchall()


def scoreboard(conn, category: str = "main",
               since: str | None = None) -> dict:
    """``{"rows": [...], "totals": {...}, "min_n": n}``.

    Rows are sorted by sample size — the thing a reader should weigh
    first — not by how good the number looks.
    """
    from .ledger import _bet_clv, CLV_MIN_N

    by: dict = {}
    for b in _rows(conn, category, since):
        key = (b["sport"] or "?", b["market"] or "?")
        d = by.setdefault(key, {"settled": 0, "clvs": []})
        d["settled"] += 1
        c = _bet_clv(b)
        if c is not None:
            d["clvs"].append(c)

    rows = []
    for (sport, market), d in by.items():
        label = _label(market)
        clvs, settled = d["clvs"], d["settled"]
        n = len(clvs)
        rows.append({
            "sport": sport, "market": market, "market_label": label,
            "settled": settled, "with_close": n,
            "coverage": round(n / settled, 3) if settled else 0.0,
            "avg_clv": round(sum(clvs) / n, 3) if n else None,
            "beat_rate": (round(sum(1 for c in clvs if c > 0) / n, 3)
                          if n else None),
            # The verdict is a SEPARATE field from the number, so a page
            # can print the average honestly while refusing to call it.
            "ready": n >= CLV_MIN_N,
            "thin": settled < MIN_ROW_N,
        })
    rows.sort(key=lambda r: (-r["with_close"], -r["settled"],
                             r["sport"], r["market"]))

    all_clv = [c for d in by.values() for c in d["clvs"]]
    settled = sum(d["settled"] for d in by.values())
    return {
        "rows": rows,
        "totals": {
            "settled": settled,
            "with_close": len(all_clv),
            "coverage": (round(len(all_clv) / settled, 3) if settled else 0.0),
            "avg_clv": (round(sum(all_clv) / len(all_clv), 3)
                        if all_clv else None),
            "beat_rate": (round(sum(1 for c in all_clv if c > 0)
                                / len(all_clv), 3) if all_clv else None),
            "ready": len(all_clv) >= CLV_MIN_N,
        },
        "min_n": CLV_MIN_N,
        "min_row_n": MIN_ROW_N,
    }
