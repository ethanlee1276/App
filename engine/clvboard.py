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
    q = ("SELECT sport, market, side, line, closing_line, odds, "
         "closing_odds, status "
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
    from .ledger import _bet_clv, _bet_price_clv, CLV_MIN_N

    by: dict = {}
    for b in _rows(conn, category, since):
        key = (b["sport"] or "?", b["market"] or "?")
        d = by.setdefault(key, {"settled": 0, "clvs": [], "pclvs": []})
        d["settled"] += 1
        c = _bet_clv(b)
        if c is not None:
            d["clvs"].append(c)
        # PRICE CLV BESIDE LINE CLV, since 2026-09-02. Ethan's droplet
        # run of the MLB readiness audit: "The scoreboard measures line
        # movement in prop-line points. Its query does not select the
        # price columns at all, so it structurally cannot measure price
        # movement. On a hits or total-bases prop the line barely moves,
        # so it reports near zero and a 9% beat rate." A 0.5 line closes
        # at 0.5; the price is the instrument that can see those markets.
        pc = _bet_price_clv(b)
        if pc is not None:
            d["pclvs"].append(pc)

    rows = []
    for (sport, market), d in by.items():
        label = _label(market)
        clvs, settled, pclvs = d["clvs"], d["settled"], d["pclvs"]
        n, pn = len(clvs), len(pclvs)
        rows.append({
            "sport": sport, "market": market, "market_label": label,
            "settled": settled, "with_close": n,
            "coverage": round(n / settled, 3) if settled else 0.0,
            "avg_clv": round(sum(clvs) / n, 3) if n else None,
            "beat_rate": (round(sum(1 for c in clvs if c > 0) / n, 3)
                          if n else None),
            # Price CLV in PROBABILITY POINTS (x100), the unit every
            # other CLV readout in this repo prints.
            "with_price_close": pn,
            "avg_price_clv_pts": (round(100.0 * sum(pclvs) / pn, 2)
                                  if pn else None),
            "price_beat_rate": (round(sum(1 for c in pclvs if c > 0) / pn, 3)
                                if pn else None),
            "price_ready": pn >= CLV_MIN_N,
            # The verdict is a SEPARATE field from the number, so a page
            # can print the average honestly while refusing to call it.
            "ready": n >= CLV_MIN_N,
            "thin": settled < MIN_ROW_N,
        })
    rows.sort(key=lambda r: (-r["with_close"], -r["settled"],
                             r["sport"], r["market"]))

    all_clv = [c for d in by.values() for c in d["clvs"]]
    all_pclv = [c for d in by.values() for c in d["pclvs"]]
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
            "with_price_close": len(all_pclv),
            "avg_price_clv_pts": (round(100.0 * sum(all_pclv) / len(all_pclv), 2)
                                  if all_pclv else None),
            "price_beat_rate": (round(sum(1 for c in all_pclv if c > 0)
                                      / len(all_pclv), 3) if all_pclv else None),
            "price_ready": len(all_pclv) >= CLV_MIN_N,
        },
        "min_n": CLV_MIN_N,
        "min_row_n": MIN_ROW_N,
    }


#: Lead-time buckets, in minutes before kickoff. The split is where the
#: market's week actually bends: prices are softest when menus post,
#: firm through the middle, and sharpest in the final hours.
LEAD_BUCKETS = ((2880, None, "2+ days out"),
                (720, 2880, "12–48 hours"),
                (120, 720, "2–12 hours"),
                (0, 120, "under 2 hours"))


def leadtime(conn, category: str = "main", since: str | None = None) -> dict:
    """Price CLV by HOW EARLY the pick was journaled.

    THE ACTIONABLE CUT. Ethan, 2026-08-31: "make the model better…
    making more money and winning more." The models rank well and show
    no edge against the CLOSE — but nobody bets the close. Every
    journaled pick carries `lead_min` (minutes to kickoff when it was
    made) and, once settled, the closing price beside the price taken.
    If picks made days out consistently beat the close and picks made
    hours out do not, "bet Tuesday, not Sunday" stops being folklore
    and becomes the book's own measured instruction — the one kind of
    edge a small operation can actually keep, because it comes from
    WHEN, not from out-modelling the market.

    Price CLV (probability points, `_bet_price_clv`), not line CLV — a
    touchdown line cannot move, and the touchdown board is the point.
    Gated at ``ledger.CLV_MIN_N`` per bucket like every CLV verdict:
    below it the counts print and the call is refused.
    """
    from .ledger import _bet_price_clv, CLV_MIN_N

    rows = conn.execute(
        "SELECT sport, market, side, line, odds, closing_line, "
        "closing_odds, lead_min, status FROM bets "
        "WHERE status IN ('won','lost','push') AND category=? "
        "AND lead_min IS NOT NULL"
        + (" AND date >= ?" if since else ""),
        ([category, since] if since else [category])).fetchall()

    buckets = []
    for lo, hi, label in LEAD_BUCKETS:
        clvs, settled = [], 0
        for b in rows:
            lead = b["lead_min"]
            if lead is None or lead < lo or (hi is not None and lead >= hi):
                continue
            settled += 1
            c = _bet_price_clv(b)
            if c is not None:
                clvs.append(c)
        n = len(clvs)
        buckets.append({
            "label": label, "settled": settled, "with_close": n,
            "avg_clv": round(sum(clvs) / n, 4) if n else None,
            # The same number in the unit the record tool prints —
            # probability POINTS. This view printed the raw fraction as
            # "+0.02pt" while engine/mlbrecord printed "+2.17pts" for the
            # same bets (Ethan's droplet run, 2026-09-02).
            "avg_clv_pts": round(100.0 * sum(clvs) / n, 2) if n else None,
            "beat_close": round(sum(1 for c in clvs if c > 0) / n, 4)
            if n else None,
            "verdict": (None if n < CLV_MIN_N else
                        "beats the close" if sum(clvs) / n > 0 else
                        "loses to the close"),
        })
    return {"category": category, "buckets": buckets,
            "min_n": CLV_MIN_N,
            "note": ("Positive means the market moved toward our side "
                     "after we bet — we got the better number. avg_clv is "
                     "a probability fraction; avg_clv_pts is the same "
                     "number in points (x100), which is what prints.")}


def leadtime_lines(conn, since: str | None = None) -> list[str]:
    """The weekly-log rendering, both books side by side."""
    out = []
    for cat, name in (("main", "staked book"), ("likely", "likely book")):
        got = leadtime(conn, category=cat, since=since)
        live = [b for b in got["buckets"] if b["settled"]]
        if not live:
            out.append(f"  when we bet ({name}): no settled picks carry "
                       f"a lead time yet")
            continue
        out.append(f"  when we bet ({name}) — price CLV by lead time:")
        for b in got["buckets"]:
            if not b["settled"]:
                continue
            word = (b["verdict"] or
                    f"needs {got['min_n']} closes, has {b['with_close']}")
            avg = ("—" if b["avg_clv_pts"] is None
                   else f"{b['avg_clv_pts']:+.2f}pts")
            beat = ("" if b["beat_close"] is None
                    else f", beat the close {b['beat_close']:.0%}")
            out.append(f"    {b['label']:<14} {b['settled']:4d} settled, "
                       f"{b['with_close']:4d} closed   {avg}{beat}   "
                       f"{word}")
    return out


# --- runnable ---------------------------------------------------------------
def scoreboard_lines(conn, category: str = "main",
                     since: str | None = None) -> list[str]:
    """The scoreboard as text: line CLV and price CLV side by side, each
    with its own count, so a market whose line cannot move (a 0.5 home
    run or hits line) is graded by the instrument that can see it."""
    got = scoreboard(conn, category, since)
    out = [f"  CLV scoreboard ({category} book"
           + (f", since {since}" if since else "") + ") — "
           f"line CLV in line points, price CLV in probability points; "
           f"verdicts need {got['min_n']} closes"]
    if not got["rows"]:
        out.append("    no settled bets")
        return out
    out.append(f"    {'sport':<5} {'market':<16} {'settled':>7} | "
               f"{'line: n':>8} {'avg':>7} {'beat':>5} | "
               f"{'price: n':>9} {'avg pts':>8} {'beat':>5}")
    for r in got["rows"]:
        la = "—" if r["avg_clv"] is None else f"{r['avg_clv']:+.2f}"
        lb = "—" if r["beat_rate"] is None else f"{r['beat_rate']:.0%}"
        pa = ("—" if r["avg_price_clv_pts"] is None
              else f"{r['avg_price_clv_pts']:+.2f}")
        pb = ("—" if r["price_beat_rate"] is None
              else f"{r['price_beat_rate']:.0%}")
        out.append(f"    {r['sport']:<5} {r['market']:<16} {r['settled']:>7} | "
                   f"{r['with_close']:>8} {la:>7} {lb:>5} | "
                   f"{r['with_price_close']:>9} {pa:>8} {pb:>5}"
                   + ("" if r["price_ready"] else "   (price verdict: not enough yet)"))
    t = got["totals"]
    pa = "—" if t["avg_price_clv_pts"] is None else f"{t['avg_price_clv_pts']:+.2f}"
    out.append(f"    all   {'':<16} {t['settled']:>7} | {t['with_close']:>8} "
               f"{'':>7} {'':>5} | {t['with_price_close']:>9} {pa:>8}")
    return out


def main(argv=None) -> int:
    """``python3 -m engine.clvboard`` — the command MLB_READINESS.md told
    Ethan to run, which on 2026-09-02 printed nothing: this module had
    no entry point, so importing it as a module exited zero in silence."""
    import argparse
    import os
    import sys
    ap = argparse.ArgumentParser(description="CLV scoreboard and lead-time cut")
    ap.add_argument("--db", default=None, help="ledger path (default: data/ledger.db)")
    ap.add_argument("--category", default="main")
    ap.add_argument("--since", default=None)
    a = ap.parse_args(argv)
    from . import ledger as _ledger
    path = a.db or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "ledger.db")
    if not os.path.exists(path):
        print(f"no ledger at {path}", file=sys.stderr)
        return 2
    conn = _ledger.connect(path)
    try:
        for line in scoreboard_lines(conn, a.category, a.since):
            print(line)
        print()
        for line in leadtime_lines(conn, a.since):
            print(line)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
