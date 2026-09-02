"""The MLB record, scored the way the readiness brief asks for it.

Ethan's MLB readiness brief (2026-09-01), Phase 4, "the main event":

    Number of bets — the first number in the report, not the last.
    Hit rate vs. breakeven at the average price.
    ROI at bet price and ROI at closing price. The gap is your CLV and
    it is the number that matters most.
    Average CLV in points of implied probability, and share of bets
    beating the close.
    Calibration by probability bucket, with a Brier score. Do this
    separately for HR props, where the model must be well calibrated
    in the 5–15% range.
    Max drawdown in units and longest losing streak.
    Flat stakes vs. Kelly-sized.
    Parlays scored separately from straight bets.
    ... and a month-by-month trend.

Every one of those is a function of columns the journal already holds
(`bets`: odds, closing_odds, hit_prob, stake_units, pnl_units, status,
date, market, category; `parlays`: status, stake_units, pnl_units,
singles_pnl_units). Nothing here is estimated, fitted, or filled in —
a bet with no closing price contributes to the price-side numbers and
is COUNTED OUT of the close-side ones, and the count of such bets is
printed beside every close-side number so a reader can see how much of
the record the CLV verdict rests on.

WHAT A BET IS. The same population the Record page and `stakecheck.py`
score: ``category IN ('main','paper') AND stake_units > 0``, settled.
The home-run board journals hundreds of rows a night at a flat
measurement stake under `longshot` / `longshot_watch`; those are not
bets and never enter an ROI here. They ARE the best available sample
for HR calibration, so the calibration section scores them too — on a
separate line that says "measurement, not money" in as many words.

WHY THIS IS ITS OWN MODULE rather than a flag on `stakecheck.py`:
stakecheck answers one question (did the sizing path shrink stakes?)
and this answers a different one (is the model profitable, and is it
decaying?). The two share a population and nothing else.

READ-ONLY. Opens the ledger in immutable mode; writes nothing.

    python3 -m engine.mlbrecord                    # data/ledger.db, all of 2026
    python3 -m engine.mlbrecord --since 2026-08-04 # post-rescale only
    python3 -m engine.mlbrecord --json             # the same numbers, as JSON
    python3 -m engine.mlbrecord --sport nfl        # works for any sport

Standard library only.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import sys

from .odds import american_to_decimal, american_to_prob

#: How the brief wants markets grouped. Anything not listed is
#: "other player props" — the MLB prop menu is hits / total bases /
#: strikeouts / outs, and an F5 or run-line market would land in the
#: sides/totals buckets by its market key when the odds feed carries it.
MARKET_TYPE = {
    "home_runs": "HR props",
    "moneyline": "sides", "spread": "sides", "run_line": "sides",
    "total": "totals", "team_total": "totals",
    "f5_moneyline": "F5", "f5_total": "F5", "f5_spread": "F5",
}

#: HR calibration buckets, in probability points. The brief singles out
#: 5–15% as "where the money is and where miscalibration is easiest to
#: hide", so that band is split in two rather than pooled.
HR_BUCKETS = ((0.0, 0.05), (0.05, 0.10), (0.10, 0.15), (0.15, 0.20),
              (0.20, 1.01))
#: Everything else: ten-point buckets.
PROB_BUCKETS = tuple((k / 10.0, (k + 1) / 10.0) for k in range(10))

#: Under this many settled bets a headline ROI is variance wearing a
#: percentage sign; the report prints the number and refuses the verdict.
MIN_N_FOR_VERDICT = 100

MONEY = "category IN ('main','paper') AND stake_units > 0"
MEASUREMENT = "category IN ('longshot','longshot_watch')"


def market_type(market: str | None) -> str:
    return MARKET_TYPE.get(str(market or ""), "other player props")


# --- loading -----------------------------------------------------------------
def _open(db: str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_bets(conn, sport: str = "mlb", since: str | None = None,
              where: str = MONEY) -> list[dict]:
    """Settled rows, oldest first. ``where`` picks the population."""
    q = ("SELECT id, date, sport, player, market, side, line, odds, book, "
         "hit_prob, edge, grade, stake_units, pnl_units, status, category, "
         "closing_odds, closing_line, fair_consensus FROM bets "
         "WHERE status IN ('won','lost','push') AND sport=? AND " + where)
    args: list = [sport]
    if since:
        q += " AND date >= ?"
        args.append(since)
    q += " ORDER BY date, id"
    return [dict(r) for r in conn.execute(q, args)]


def load_parlays(conn, sport: str = "mlb", since: str | None = None) -> list[dict]:
    q = ("SELECT id, date, n_legs, status, stake_units, notional_units, "
         "pnl_units, singles_pnl_units FROM parlays "
         "WHERE status IN ('won','lost','void') AND sport=?")
    args: list = [sport]
    if since:
        q += " AND date >= ?"
        args.append(since)
    q += " ORDER BY date, id"
    try:
        return [dict(r) for r in conn.execute(q, args)]
    except sqlite3.OperationalError:          # a ledger from before parlays
        return []


# --- per-bet arithmetic ------------------------------------------------------
def outcome(b: dict) -> int | None:
    """1 won, 0 lost, None push (a push is not evidence either way)."""
    s = (b.get("status") or "").lower()
    if s == "won":
        return 1
    if s == "lost":
        return 0
    return None


def pnl_at(b: dict, odds, stake: float) -> float:
    """What this bet's result pays at ``odds`` for ``stake`` units.

    The result is the result; only the price changes. This is how "ROI
    at the close" is computed — the same wins and losses, paid at the
    closing price instead of the one we took."""
    o = outcome(b)
    if o is None or odds is None:
        return 0.0
    try:
        dec = american_to_decimal(int(odds))
    except (TypeError, ValueError):
        return 0.0
    return stake * (dec - 1.0) if o else -stake


def price_clv(b: dict) -> float | None:
    """CLV in implied-probability points: close minus taken, both raw
    implied. Positive = the market moved toward our side. Same sign and
    units as `ledger._bet_price_clv`, restated here so this module has
    no import of the write-side ledger."""
    close, took = b.get("closing_odds"), b.get("odds")
    if close is None or took is None:
        return None
    try:
        return american_to_prob(int(close)) - american_to_prob(int(took))
    except (TypeError, ValueError):
        return None


# --- scoring one population --------------------------------------------------
def _roi(net: float, staked: float) -> float | None:
    return (net / staked) if staked > 0 else None


def score(rows: list[dict]) -> dict:
    """Every Phase 4 number for one population of settled bets."""
    live = [b for b in rows if outcome(b) is not None]
    n, wins = len(live), sum(outcome(b) for b in live)
    staked = sum(float(b.get("stake_units") or 0.0) for b in live)
    net = sum(float(b.get("pnl_units") or 0.0) for b in live)

    # Breakeven at the average price taken: the mean implied probability
    # of the prices we paid is the hit rate that returns exactly zero.
    implied = []
    for b in live:
        try:
            implied.append(american_to_prob(int(b["odds"])))
        except (TypeError, ValueError, KeyError):
            pass
    breakeven = (sum(implied) / len(implied)) if implied else None

    # At the close: same results, the closing price, the same stakes.
    with_close = [b for b in live if b.get("closing_odds") is not None]
    close_staked = sum(float(b.get("stake_units") or 0.0) for b in with_close)
    close_net_at_price = sum(float(b.get("pnl_units") or 0.0) for b in with_close)
    close_net = sum(pnl_at(b, b["closing_odds"], float(b.get("stake_units") or 0.0))
                    for b in with_close)
    clvs = [c for c in (price_clv(b) for b in with_close) if c is not None]

    # Flat 1u vs the stakes actually used. Flat is the control: same
    # bets, same results, sizing removed.
    flat_net = sum(pnl_at(b, b.get("odds"), 1.0) for b in live)

    # Drawdown and streak, in the order the bets settled (date, id).
    peak = cum = dd = 0.0
    streak = worst = 0
    for b in live:
        cum += float(b.get("pnl_units") or 0.0)
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
        if outcome(b) == 0:
            streak += 1
            worst = max(worst, streak)
        else:
            streak = 0

    # Is the edge distinguishable from zero? Per-bet flat returns, their
    # mean and a normal-approximation 95% interval. Reported as an
    # interval, not a verdict — a reader can see whether zero is inside.
    rets = [pnl_at(b, b.get("odds"), 1.0) for b in live]
    ci = None
    if len(rets) >= 2:
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
        se = math.sqrt(var / len(rets))
        ci = (round(mean - 1.96 * se, 4), round(mean + 1.96 * se, 4))

    return {
        "n": n, "wins": wins, "losses": n - wins,
        "pushes": sum(1 for b in rows if outcome(b) is None),
        "hit_rate": round(wins / n, 4) if n else None,
        "breakeven": round(breakeven, 4) if breakeven is not None else None,
        "staked": round(staked, 2), "net": round(net, 3),
        "roi_at_price": _r(_roi(net, staked)),
        "n_with_close": len(with_close),
        "roi_at_price_closed_subset": _r(_roi(close_net_at_price, close_staked)),
        "roi_at_close": _r(_roi(close_net, close_staked)),
        "clv_mean_pts": round(sum(clvs) / len(clvs), 4) if clvs else None,
        "clv_beat_share": round(sum(1 for c in clvs if c > 0) / len(clvs), 4) if clvs else None,
        "flat_roi": _r(_roi(flat_net, float(n))),
        "flat_roi_ci95": ci,
        "max_drawdown_u": round(dd, 3),
        "longest_losing_streak": worst,
    }


def _r(x):
    return None if x is None else round(x, 4)


def calibration(rows: list[dict], buckets=PROB_BUCKETS) -> dict:
    """Brier score and per-bucket predicted-vs-actual on `hit_prob`.

    A row with no stored probability is counted out (and counted), never
    given one."""
    scored = [(float(b["hit_prob"]), outcome(b)) for b in rows
              if b.get("hit_prob") is not None and outcome(b) is not None]
    out: dict = {"n": len(scored),
                 "n_without_prob": sum(1 for b in rows if b.get("hit_prob") is None
                                       and outcome(b) is not None),
                 "brier": None, "buckets": []}
    if not scored:
        return out
    out["brier"] = round(sum((p - y) ** 2 for p, y in scored) / len(scored), 4)
    for lo, hi in buckets:
        inb = [(p, y) for p, y in scored if lo <= p < hi]
        if not inb:
            continue
        out["buckets"].append({
            "range": f"{lo:.0%}–{min(hi, 1.0):.0%}", "n": len(inb),
            "predicted": round(sum(p for p, _ in inb) / len(inb), 4),
            "actual": round(sum(y for _, y in inb) / len(inb), 4),
        })
    return out


def score_parlays(rows: list[dict]) -> dict:
    """Parlays on their own, against the singles alternative the journal
    stores beside each ticket (`singles_pnl_units`: the same legs bet
    flat and separately)."""
    live = [p for p in rows if p.get("status") in ("won", "lost")]
    staked = sum(float(p.get("stake_units") or 0.0) for p in live)
    net = sum(float(p.get("pnl_units") or 0.0) for p in live)
    # Notional-basis ROI so a paper ticket (stake 0) still scores.
    notional = sum(float(p.get("notional_units") or 1.0) for p in live)
    net_notional = sum(float(p.get("pnl_units") or 0.0) for p in live)
    singles = [p for p in live if p.get("singles_pnl_units") is not None]
    singles_net = sum(float(p["singles_pnl_units"]) for p in singles)
    singles_legs = sum(int(p.get("n_legs") or 0) for p in singles)
    return {
        "n": len(live), "won": sum(1 for p in live if p["status"] == "won"),
        "voided": sum(1 for p in rows if p.get("status") == "void"),
        "staked": round(staked, 2), "net": round(net, 3),
        "roi_at_price": _r(_roi(net, staked)),
        "roi_notional": _r(_roi(net_notional, notional)),
        "singles_n_legs": singles_legs,
        "singles_net_flat": round(singles_net, 3),
        "singles_roi_flat": _r(_roi(singles_net, float(singles_legs))),
        "with_money": sum(1 for p in live if float(p.get("stake_units") or 0) > 0),
    }


# --- the report --------------------------------------------------------------
def _group(rows, key):
    by: dict = {}
    for b in rows:
        by.setdefault(key(b), []).append(b)
    return by


def report(conn, sport: str = "mlb", since: str | None = None) -> dict:
    bets = load_bets(conn, sport, since)
    hr_measure = [b for b in load_bets(conn, sport, since, MEASUREMENT)
                  if b.get("market") == "home_runs"]
    parlays = load_parlays(conn, sport, since)
    by_type = _group(bets, lambda b: market_type(b.get("market")))
    by_month = _group(bets, lambda b: str(b.get("date") or "")[:7])
    by_market = _group(bets, lambda b: str(b.get("market") or "?"))
    hr_money = by_type.get("HR props", [])
    return {
        "sport": sport, "since": since,
        "population": MONEY,
        "overall": score(bets),
        "by_type": {k: score(v) for k, v in sorted(by_type.items())},
        "by_market": {k: score(v) for k, v in sorted(by_market.items())},
        "by_month": {k: score(v) for k, v in sorted(by_month.items())},
        "by_type_month": {t: {m: score(v) for m, v in sorted(
            _group(rows, lambda b: str(b.get("date") or "")[:7]).items())}
            for t, rows in sorted(by_type.items())},
        "calibration": calibration(bets),
        "hr_calibration_money": calibration(hr_money, HR_BUCKETS),
        "hr_calibration_measurement": calibration(hr_measure, HR_BUCKETS),
        "hr_measurement_rows": len(hr_measure),
        "parlays": score_parlays(parlays),
        "min_n_for_verdict": MIN_N_FOR_VERDICT,
        "verdict": verdict(score(bets)),
    }


def verdict(s: dict) -> str:
    """The sentence the brief wants first, written from the numbers and
    refusing to be written at all under the sample floor."""
    n = s.get("n") or 0
    if n == 0:
        return "profitability is unverified — no settled bets in this population"
    if n < MIN_N_FOR_VERDICT:
        return (f"profitability is unverified — {n} settled bets is under the "
                f"{MIN_N_FOR_VERDICT}-bet floor for a verdict")
    ci = s.get("flat_roi_ci95")
    roi = s.get("roi_at_price")
    close = s.get("roi_at_close")
    clv = s.get("clv_mean_pts")
    nclose = s.get("n_with_close") or 0
    parts = [f"{n} bets, ROI at price {roi:+.1%}"]
    if close is not None:
        parts.append(f"ROI at close {close:+.1%} on the {nclose} with a close")
    if clv is not None:
        parts.append(f"mean CLV {clv * 100:+.2f} pts")
    if ci:
        lo, hi = ci
        if lo > 0:
            parts.append("flat-ROI 95% interval is above zero: edge distinguishable from zero")
        elif hi < 0:
            parts.append("flat-ROI 95% interval is below zero: losing, distinguishably")
        else:
            parts.append(f"flat-ROI 95% interval {lo:+.1%}..{hi:+.1%} spans zero: "
                         "not distinguishable from zero at this sample")
    if roi is not None and roi > 0.10:
        parts.append("ABOVE 10% — treat as a bug until proven otherwise (brief rule 5)")
    return "; ".join(parts)


# --- text --------------------------------------------------------------------
def _pct(x, digits=1):
    return "—" if x is None else f"{x:+.{digits}%}"


def _fmt(x, kind: str) -> str:
    """One formatter for the optional numbers a line carries."""
    if x is None:
        return "—"
    if kind == "pct":
        return f"{x:.1%}"
    if kind == "pts":
        return f"{x * 100:+.2f}pts"
    if kind == "share":
        return f"{x:.0%}"
    return str(x)


def _line(name: str, s: dict) -> str:
    hit = _fmt(s["hit_rate"], "pct")
    be = _fmt(s["breakeven"], "pct")
    clv = _fmt(s["clv_mean_pts"], "pts")
    beat = _fmt(s["clv_beat_share"], "share")
    return (f"{name:<22} n={s['n']:<5} hit {hit:>6} vs BE {be:>6} | "
            f"ROI@price {_pct(s['roi_at_price'])} "
            f"| close: n={s['n_with_close']} ROI@close {_pct(s['roi_at_close'])} "
            f"CLV {clv} beat {beat} "
            f"| flat {_pct(s['flat_roi'])} | DD {s['max_drawdown_u']:.1f}u "
            f"| L-streak {s['longest_losing_streak']}")


def _cal_lines(name: str, c: dict, indent="    ") -> list[str]:
    brier = "—" if c["brier"] is None else str(c["brier"])
    out = [f"{indent}{name}: n={c['n']} (no stored probability: "
           f"{c['n_without_prob']}), Brier {brier}"]
    for b in c["buckets"]:
        out.append(f"{indent}  {b['range']:>9}  n={b['n']:<5} said {b['predicted']:.1%}"
                   f"  hit {b['actual']:.1%}")
    return out


def render(r: dict) -> str:
    o = r["overall"]
    lines = [f"Record — {r['sport']}, population: {r['population']}"
             + (f", since {r['since']}" if r["since"] else ""),
             "",
             f"VERDICT: {r['verdict']}",
             "",
             f"Bets: {o['n']} settled ({o['wins']}–{o['losses']}, {o['pushes']} pushes)",
             _line("all", o),
             "",
             "By market type:"]
    for k, s in r["by_type"].items():
        lines.append("  " + _line(k, s))
    lines += ["", "By market:"]
    for k, s in r["by_market"].items():
        lines.append("  " + _line(k, s))
    lines += ["", "Month by month (the trend the brief asks for first):"]
    for k, s in r["by_month"].items():
        lines.append("  " + _line(k, s))
    for t, months in r["by_type_month"].items():
        if len(months) > 1:
            lines.append(f"  {t}:")
            for m, s in months.items():
                lines.append("    " + _line(m, s))
    lines += ["", "Calibration (hit_prob vs outcome):"]
    lines += _cal_lines("all bets", r["calibration"])
    lines += _cal_lines("HR props, money", r["hr_calibration_money"])
    lines += _cal_lines(f"HR board, measurement rows (NOT money, flat journal stake)",
                        r["hr_calibration_measurement"])
    p = r["parlays"]
    lines += ["", "Parlays (scored apart from straights):",
              f"    n={p['n']} settled, won {p['won']}, voided {p['voided']}, "
              f"with real money {p['with_money']}",
              f"    staked {p['staked']}u net {p['net']:+.3f}u ROI@price {_pct(p['roi_at_price'])} "
              f"(notional basis {_pct(p['roi_notional'])})",
              f"    the same legs as flat singles: {p['singles_n_legs']} legs, "
              f"net {p['singles_net_flat']:+.3f}u, ROI {_pct(p['singles_roi_flat'])}"]
    lines += ["", f"Verdict floor: {r['min_n_for_verdict']} settled bets. "
              "Close-side numbers use only the bets that carry a closing price; "
              "the count is printed beside each."]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "ledger.db"))
    ap.add_argument("--sport", default="mlb")
    ap.add_argument("--since", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if not os.path.exists(a.db):
        print(f"no ledger at {a.db}", file=sys.stderr)
        return 2
    conn = _open(a.db)
    try:
        r = report(conn, a.sport, a.since)
    finally:
        conn.close()
    print(json.dumps(r, indent=1) if a.json else render(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
