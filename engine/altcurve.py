"""The market's whole curve, from the alternate ladders — and ours beside it.

Ethan, 2026-10-16: "add everything now. 1-13" — idea 2. A main line tells
you where the book thinks the middle is. The alternate ladder (49.5,
59.5, 69.5 …) tells you how likely the book thinks EVERY outcome is: each
rung, priced both ways, is one point on the market's curve of "chance he
goes over this number". Laid beside our own chance at the same rungs, the
two curves can agree in the middle and part at the ends — the market
pricing his big day as rarer (or commoner) than we do. That is a SHAPE
disagreement, and a main-line comparison can never see it.

THE MARKET'S CURVE. At each rung, every book quoting BOTH sides is
de-vigged on its own two prices and the median taken; one-sided rungs are
left out rather than given an assumed hold. The points are then made to
fall as the number rises (pool-adjacent-violators), because a chance of
going over 69.5 above the chance of going over 59.5 is two books
disagreeing, not a curve.

OURS, at the same rungs, is `likely._prob_at` — the derivation the Most
Likely board already prices every rung with. Nothing new is modelled.

WHAT THE PAGE SAYS. Both curves, the gap at every rung, and the market's
implied middle and spread. "Ends disagree" is said when the middle agrees
within MID_AGREE and an end rung parts by TAIL_GAP or more. It is a
reading, and labelled one.

THE MEASUREMENT. The ladders were never stored, so there is no history to
replay — the curves are kept from today (`journal`, one row per player,
market and date, the last pre-kickoff curve wins) and scored as games
settle (`measure`). THE BAR, written before the first row: on rungs where
the two curves part by TAIL_GAP or more, the side our curve favours must
beat the market's fair chance by MIN_EXCESS on average, with t ≥ MIN_T,
across at least MIN_PROPS props (a prop's rungs move together, so the prop
is the unit), and our log score must beat the market's on those rungs.
Until then nothing reads it.

Standard library only.
"""

from __future__ import annotations

import datetime as _dt
import json
import math

#: Rungs a curve needs before it is a curve.
MIN_RUNGS = 3
#: "The middle agrees" and "an end parts", in chance.
MID_AGREE = 0.03
TAIL_GAP = 0.06
#: The bar (module docstring).
MIN_EXCESS = 0.03
MIN_T = 2.0
MIN_PROPS = 150

TABLE = """
CREATE TABLE IF NOT EXISTS alt_curves (
    sport TEXT, date TEXT, player TEXT, market TEXT, taken_at TEXT,
    rungs TEXT, PRIMARY KEY (sport, date, player, market)
);
"""


def _implied(o):
    try:
        o = float(o)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(o) or -100 < o < 100:
        return None
    return 100.0 / (o + 100.0) if o > 0 else -o / (-o + 100.0)


def _median(xs):
    s = sorted(xs)
    n = len(s)
    return None if not n else (s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2]))


def decreasing(points):
    """Pool-adjacent-violators: the closest non-increasing sequence to the
    points' chances, weighted by how many books stood behind each."""
    blocks = []                                   # [line_list, mean, weight]
    for line, p, w in points:
        blocks.append([[line], p, w])
        while len(blocks) > 1 and blocks[-2][1] < blocks[-1][1]:
            a, b = blocks[-2], blocks.pop()
            tot = a[2] + b[2]
            a[1] = (a[1] * a[2] + b[1] * b[2]) / tot
            a[2] = tot
            a[0] += b[0]
    out = []
    for lines, p, _w in blocks:
        out += [(ln, p) for ln in lines]
    return out


def market_curve(quotes) -> list:
    """``[(line, p_over, books)]`` from every quote of one prop (main and
    alternate), two-sided quotes only, median across books, made to fall."""
    by: dict = {}
    for q in quotes or []:
        get = (lambda k, q=q: q.get(k)) if isinstance(q, dict) else (lambda k, q=q: getattr(q, k, None))
        try:
            line = float(get("line"))
        except (TypeError, ValueError):
            continue
        a, b = _implied(get("over_odds")), _implied(get("under_odds"))
        if a is None or b is None or a + b <= 0:
            continue
        by.setdefault(line, {})[str(get("book") or "")] = a / (a + b)
    pts = [(ln, _median(list(bk.values())), len(bk)) for ln, bk in sorted(by.items())]
    fixed = decreasing(pts)
    books = {ln: n for ln, _p, n in pts}
    return [(ln, round(p, 4), books[ln]) for ln, p in fixed]


def crossing(curve, target: float):
    """The line where a falling curve passes `target`, interpolated, or
    None when the rungs do not straddle it."""
    for (l0, p0, *_), (l1, p1, *_r) in zip(curve, curve[1:]):
        if p0 >= target >= p1 and p0 != p1:
            return round(l0 + (p0 - target) * (l1 - l0) / (p0 - p1), 2)
    return None


def compare(row: dict, market: str, quotes=None, prob_at=None) -> dict | None:
    """One prop's two curves, rung by rung. ``prob_at(row, market, side,
    line)`` defaults to the Most Likely board's own derivation."""
    quotes = quotes if quotes is not None else (row.get("all_lines") or []) + (row.get("alt_lines") or [])
    mk = market_curve(quotes)
    if len(mk) < MIN_RUNGS:
        return None
    if prob_at is None:
        from .likely import _prob_at as prob_at
    rungs = []
    for line, p_mkt, books in mk:
        ours = prob_at(row, market, "over", line)
        if ours is None:
            continue
        rungs.append({"line": line, "market": p_mkt, "ours": round(float(ours), 4),
                      "gap": round(float(ours) - p_mkt, 4), "books": books})
    if len(rungs) < MIN_RUNGS:
        return None
    mid = min(rungs, key=lambda r: abs(r["market"] - 0.5))
    ends = (rungs[0], rungs[-1])
    tail = max(ends, key=lambda r: abs(r["gap"]))
    shape = (abs(mid["gap"]) <= MID_AGREE and abs(tail["gap"]) >= TAIL_GAP)
    curve = [(r["line"], r["market"]) for r in rungs]
    q25, q50, q75 = crossing(curve, 0.75), crossing(curve, 0.5), crossing(curve, 0.25)
    return {"rungs": rungs, "mid_gap": mid["gap"], "tail_gap": tail["gap"], "tail_line": tail["line"],
            "ends_disagree": bool(shape),
            "tail_side": ("over" if tail["gap"] > 0 else "under") if abs(tail["gap"]) >= TAIL_GAP else None,
            "market_median": q50,
            "market_spread": round((q25 - q75) / 1.349, 2) if q25 is not None and q75 is not None and q25 < q75 else None}


# ---- the ideas file ----------------------------------------------------------

def _game_dates(games) -> dict:
    out = {}
    for g in games or []:
        get = g.get if isinstance(g, dict) else (lambda k, g=g: getattr(g, k, None))
        for t in (get("home"), get("away")):
            if t:
                out[t] = str(get("date") or "")[:10]
    return out


def ideas_section(props, games, board, sport):
    # THE SETTLE KEY IS THE BOARD'S OWN DATE, the one its bets are journaled
    # under ("2026-W07" for an NFL week, the day for the daily sports), so
    # the ledger's own lookup finds the result; the game's calendar date
    # is the fallback for a board that carries none.
    dates = _game_dates(games)
    key = str((board or {}).get("date") or "")
    out = {}
    for row in (board or {}).get("recommendations") or []:
        player, market = row.get("player"), row.get("market")
        if not player or not market or not row.get("alt_lines"):
            continue
        try:
            c = compare(row, market)
        except Exception:                                     # noqa: BLE001
            c = None
        if c:
            c["date"] = key or dates.get(row.get("team"), "")
            out[f"{player}|{market}"] = c
    return {"curves": out, "verdict": load_verdict(sport)}


def pick_view(sec, player, market, side="", line=None):
    c = (sec.get("curves") or {}).get(f"{player}|{market}")
    if not c:
        return None
    return {**c, "verdict": sec.get("verdict") or {}}


def game_view(sec, home, away):
    return None


# ---- the journal and the measurement -------------------------------------------

def ensure_table(conn) -> None:
    conn.executescript(TABLE)


def journal(sport: str, section: dict, conn=None, now=None) -> int:
    """Keep today's curves: one row per (player, market, date), the latest
    build's curve replacing the earlier one until the game starts (a build
    after kickoff does not price, so the last write is the pre-game one)."""
    curves = (section or {}).get("curves") or {}
    if not curves:
        return 0
    own = conn is None
    if own:
        from . import db as _db
        conn = _db.connect()
    try:
        ensure_table(conn)
        stamp = (now or _dt.datetime.now(_dt.timezone.utc)).strftime("%Y-%m-%dT%H:%M:00Z")
        n = 0
        for key, c in curves.items():
            player, market = key.split("|", 1)
            if not c.get("date"):
                continue
            conn.execute("INSERT OR REPLACE INTO alt_curves VALUES (?,?,?,?,?,?)",
                         (sport, c["date"], player, market, stamp,
                          json.dumps([[r["line"], r["market"], r["ours"]] for r in c["rungs"]])))
            n += 1
        conn.commit()
        return n
    finally:
        if own:
            conn.close()


def _actual(hconn, sport, player, market, date):
    """What he did that day, by the ledger's own lookup. None only when no
    result is stored yet; a lookup that breaks raises, so a broken join can
    never read as a week of unsettled games."""
    from .ledger import _hist_where
    where, args = _hist_where({"sport": sport, "date": date, "game_day": date})
    r = hconn.execute(f"SELECT value FROM player_game_logs WHERE {where} AND market=? AND player=?",
                      (*args, market, player)).fetchone()
    return None if r is None or r[0] is None else float(r[0])


def score(rows) -> dict:
    """``rows``: [(rungs, actual)] — per prop, on the rungs where the
    curves part by TAIL_GAP or more: our side's excess over the market's
    fair chance, and the log-score difference (ours − market)."""
    ex, ll = [], []
    for rungs, actual in rows:
        e, d = [], []
        for line, p_m, p_o in rungs:
            if actual == line or abs(p_o - p_m) < TAIL_GAP:
                continue
            y = 1 if actual > line else 0
            side_over = p_o > p_m
            hit = y if side_over else 1 - y
            fair = p_m if side_over else 1 - p_m
            e.append(hit - fair)
            pm, po = min(max(p_m, 1e-4), 1 - 1e-4), min(max(p_o, 1e-4), 1 - 1e-4)
            d.append((math.log(po) if y else math.log(1 - po)) - (math.log(pm) if y else math.log(1 - pm)))
        if e:
            ex.append(sum(e) / len(e))
            ll.append(sum(d) / len(d))
    return {"excess": _stats(ex), "logscore": _stats(ll)}


def _stats(xs):
    n = len(xs)
    if n < 2:
        return {"n": n, "mean": xs[0] if xs else None, "t": None}
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    return {"n": n, "mean": round(m, 4), "t": round(m / math.sqrt(var / n), 2) if var > 0 else None}


def verdict(sc) -> dict:
    e, l = sc["excess"], sc["logscore"]
    holds = (e["n"] >= MIN_PROPS and (e["mean"] or 0) >= MIN_EXCESS and (e["t"] or 0) >= MIN_T
             and (l["mean"] or 0) > 0)
    return {**sc, "holds": bool(holds)}


def measure(conn, hconn=None, sport: str = "nfl") -> dict:
    ensure_table(conn)
    hconn = hconn or conn
    rows = []
    for r in conn.execute("SELECT player, market, date, rungs FROM alt_curves WHERE sport=?", (sport,)):
        actual = _actual(hconn, sport, r[0], r[1], r[2])
        if actual is None:
            continue
        rows.append((json.loads(r[3]), actual))
    return {"sport": sport, "settled": len(rows), **verdict(score(rows))}


STORE = "altcurve_verdict.json"


def load_verdict(sport: str) -> dict:
    from . import modelstate
    try:
        with open(modelstate.path(STORE)) as fh:
            return json.load(fh).get(sport) or {}
    except (OSError, ValueError):
        return {}


def save_verdict(res: dict) -> str:
    from . import modelstate
    import os
    p = modelstate.path(STORE)
    try:
        with open(p) as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        d = {}
    d[res["sport"]] = {k: res[k] for k in ("settled", "excess", "logscore", "holds")}
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w") as fh:
        json.dump(d, fh, indent=1)
    return p


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="The market's curve against ours, scored on settled games")
    ap.add_argument("--sport", default="nfl")
    ap.add_argument("--save", action="store_true", help="keep the verdict where the page reads it")
    a = ap.parse_args(argv)
    from . import db as _db
    conn = _db.connect()
    try:
        res = measure(conn, sport=a.sport)
    finally:
        conn.close()
    e, l = res["excess"], res["logscore"]
    print(f"Alt-ladder curves — {a.sport.upper()}: {res['settled']} settled prop curve(s) kept")
    print(f"  where the curves part by ≥ {TAIL_GAP:.2f}: our side vs the market's fair chance "
          f"{e['mean'] if e['mean'] is not None else '—'} (t {e['t'] if e['t'] is not None else '—'}, n {e['n']}); "
          f"log score ours − market {l['mean'] if l['mean'] is not None else '—'} (t {l['t'] if l['t'] is not None else '—'})")
    print(f"  THE BAR: ≥ {MIN_EXCESS:+.2f}, t ≥ {MIN_T}, ≥ {MIN_PROPS} props, log score above the market's — "
          f"{'HOLDS' if res['holds'] else 'does not hold (yet)'}")
    if a.save:
        print(f"  saved → {save_verdict(res)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
