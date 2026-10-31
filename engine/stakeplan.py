"""WHICH PICKS CARRY A STAKE — one rule, read by the record and by every new bet.

Ethan, 2026-10-31: "I feel like we're winning a lot of bets, but not winning
money. And we're still down ROI. We're still down units ... We need to find
what bets and what unit bets ... works best for our ROI to be positive and
our units to be positive, and then we need to implement that, and then also
update our current record on the site and the current ROI and units on the
site with the respected units and ROI ... we're going to use for our new
bets."

WHAT THE RECORD SAYS (tools/stake_study.py reruns every number from the
public receipts, /api/record/receipts.csv; docs/STAKES.md has the tables).
Every graded pick of the headline record, 2026-08-06 to 2026-10-31:

  * THE MOST LIKELY HALF WINS BETS AND LOSES MONEY. 4,582-2,953 (60.8%) and
    −17.4 units (−1.4%), because it paid −162 on average, where 61.8% only
    breaks even. Its chances are honest — it said 61.8% and hit 60.8% — but
    they do not beat the price: at flat stakes the picks we called 5-10%
    better than the price made −3.8%, the ones we called worse −2.0%. A
    board chosen for how LIKELY a pick is pays the juice on every pick.
  * THE EDGE HALF MAKES MONEY ON ITS LADDER. 691-723 and +13.9 units
    (+1.85%) at the price ladder's stakes; flat 1u on the same picks makes
    +0.15%, because the ladder puts less on the long prices that lost. The
    NFL's Edge picks made +16.1u (+5.1%) and were positive in both halves of
    the sample.
  * NOTHING ADAPTIVE HELD UP. Walked forward one day at a time — each day's
    rule read only from the days before it — staking the segments that had
    been winning, sizing up the leagues with the best record, or dropping
    the markets that had been losing all did WORSE than flat stakes (−1.5% to
    −5.0% against −2.3%): the winners of one fortnight were not the winners
    of the next. What held up is structural, so the rule below is structural.

THE RULE (v4, from 2026-10-31), per league:

  * EDGE PICKS ARE STAKED on the price ladder (engine/staking: −110 is 1u,
    −200 1.25u, +200 0.64u, never under 0.35u). A league's Edge book stops
    being staked when it is clearly losing — EDGE_STOP: 100 graded at
    z ≤ −2.0, the bar `ledger.LIVE_STOP_*` already held the staked Most
    Likely board to — and is staked again once it climbs back above z −1.0.
  * MOST LIKELY PICKS ARE TRACKED, NOT STAKED: every pick still posts, is
    graded and counts toward the board's hit rate. A league's Most Likely
    book is staked once it proves it beats the price — LIKELY_GO: 200 graded
    at z ≥ +2.0, the bar the stale-line book had to clear before it risked a
    penny — and goes back to paper at z ≤ 0.

THE RECORD AT THESE STAKES is `staked_reports`: every graded pick of the
headline record, at the stake it carried if this rule had it staked on the
day it was made, and at nothing if not — each day's decision read only from
the days before it, so nothing in it knows what happened next. It is the
record the site leads with from 2026-10-31. The picks themselves are the
same picks, made in public at the time; only which of them carried units is
decided by today's rule, and the record as placed (every pick at the stake
it carried, Most Likely included) stays beside it on the page.

Standard library only.
"""
from __future__ import annotations

import datetime as _dt
import math
import re

#: The rule's name and the day it took over the record.
VERSION = "v4"
SINCE = "2026-10-31"
LABEL = "Staked picks — Edge on the price ladder, Most Likely tracked"

EDGE_CATS = ("main", "paper")
LIKELY_CATS = ("likely", "likely_live", "board")

#: A league's Edge book stops at `z` once it has `n` graded, and comes back
#: above `back`.
EDGE_STOP = {"n": 100, "z": -2.0, "back": -1.0}
#: A league's Most Likely book is staked once it has `n` graded at `z`, and
#: goes back to paper at `off`.
LIKELY_GO = {"n": 200, "z": 2.0, "off": 0.0}

#: How many of the record's newest staked picks ride with the report, and
#: with each league's (the first screen downloads them all).
RECENT = 60
RECENT_SPORT = 30


def half_of(category) -> str | None:
    """"edge", "likely", or None for a book outside the headline."""
    c = str(category or "")
    if c in EDGE_CATS:
        return "edge"
    if c in LIKELY_CATS:
        return "likely"
    return None


def sort_day(day) -> str:
    """A day that sorts: an NFL week label ("2026-W08") becomes that week's
    Sunday. Week 1's Thursday is the first Thursday after Labor Day."""
    d = str(day or "")
    m = re.fullmatch(r"(\d{4})-W(\d{1,2})", d)
    if not m:
        return d[:10]
    y, w = int(m.group(1)), int(m.group(2))
    sept1 = _dt.date(y, 9, 1)
    labor = sept1 + _dt.timedelta(days=(0 - sept1.weekday()) % 7)
    return (labor + _dt.timedelta(days=6 + 7 * (w - 1))).isoformat()


def _decimal(odds) -> float:
    o = int(odds)
    return 1.0 + (o / 100.0 if o > 0 else 100.0 / abs(o))


def flat_return(odds, status) -> float | None:
    """One unit's profit: won, lost, push (0), or None for anything else."""
    s = str(status or "")
    if s == "push":
        return 0.0
    try:
        d = _decimal(odds)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if s == "won":
        return d - 1.0
    if s == "lost":
        return -1.0
    return None


class Book:
    """One league's half of the record, at flat stakes: the evidence the rule
    reads. Pushes are not decisions and are not counted."""
    __slots__ = ("n", "s", "ss")

    def __init__(self):
        self.n, self.s, self.ss = 0, 0.0, 0.0

    def add(self, x: float) -> None:
        self.n += 1
        self.s += x
        self.ss += x * x

    def roi(self) -> float:
        return self.s / self.n if self.n else 0.0

    def z(self) -> float:
        if self.n < 2:
            return 0.0
        m = self.s / self.n
        var = (self.ss - self.n * m * m) / (self.n - 1)
        return m / math.sqrt(var / self.n) if var > 0 else 0.0


def decide(half: str, staked: bool | None, book: Book) -> bool:
    """Is this half of this league staked on the next day, given yesterday's
    answer (None before the first) and its record so far?"""
    if half == "edge":
        on = True if staked is None else staked
        if book.n >= EDGE_STOP["n"]:
            z = book.z()
            if on and z <= EDGE_STOP["z"]:
                return False
            if not on and z > EDGE_STOP["back"]:
                return True
        return on
    on = False if staked is None else staked
    if book.n >= LIKELY_GO["n"]:
        z = book.z()
        if not on and z >= LIKELY_GO["z"]:
            return True
        if on and z <= LIKELY_GO["off"]:
            return False
    return on


def why(half: str, staked: bool, book: Book) -> str:
    """The reader's sentence for one league's half, as it stands."""
    rec = (f"{book.n} graded, {book.roi():+.1%} at flat stakes (z {book.z():+.2f})"
           if book.n else "nothing graded yet")
    if half == "edge":
        if staked:
            return f"staked on the price ladder — {rec}"
        return (f"tracked, not staked — clearly losing ({rec}); staked again above "
                f"z {EDGE_STOP['back']:+.1f}")
    if staked:
        return f"staked — it has beaten the price: {rec}"
    need = (f"{LIKELY_GO['n'] - book.n} more graded" if book.n < LIKELY_GO["n"]
            else f"z {LIKELY_GO['z']:+.1f}")
    return (f"tracked for its hit rate, not staked — {rec}; staked once it beats the "
            f"price ({need})")


def replay(rows: list) -> tuple[list, dict]:
    """Walk the record forward a day at a time.

    ``rows`` are dicts with ``day``, ``sport``, ``category``, ``odds`` and
    ``status``, in any order. Returns ``(flags, state)``: ``flags[i]`` is
    whether rows[i]'s half of its league was staked on its day, decided from
    the days before it only; ``state`` is {(half, sport): {"staked", "book"}}
    after the last day — what the rule says for the next pick."""
    order = sorted(range(len(rows)), key=lambda i: (sort_day(rows[i].get("day")),))
    flags = [False] * len(rows)
    staked: dict = {}
    books: dict = {}
    i = 0
    while i < len(order):
        d = sort_day(rows[order[i]].get("day"))
        j = i
        while j < len(order) and sort_day(rows[order[j]].get("day")) == d:
            j += 1
        day = order[i:j]
        for k in day:
            r = rows[k]
            h = half_of(r.get("category"))
            if h is None:
                continue
            key = (h, str(r.get("sport") or "").lower())
            if key not in staked or staked[key] is None:
                staked[key] = decide(h, None, books.setdefault(key, Book()))
            flags[k] = bool(staked[key])
        for k in day:
            r = rows[k]
            h = half_of(r.get("category"))
            if h is None:
                continue
            x = flat_return(r.get("odds"), r.get("status"))
            if x is None or str(r.get("status")) == "push":
                continue
            books.setdefault((h, str(r.get("sport") or "").lower()), Book()).add(x)
        # The next day's answer, from everything graded up to tonight.
        for key, book in books.items():
            staked[key] = decide(key[0], staked.get(key), book)
        i = j
    state = {key: {"staked": bool(staked.get(key, key[0] == "edge")), "book": book}
             for key, book in books.items()}
    return flags, state


def _blank() -> dict:
    return {"settled": 0, "wins": 0, "losses": 0, "pushes": 0, "units_staked": 0.0,
            "net_units": 0.0, "_be": 0.0, "_be_n": 0, "_price": 0.0, "tracked": 0}


def _add(t: dict, r: dict, stake: float) -> None:
    status = str(r.get("status") or "")
    t["settled"] += 1
    t["wins"] += status == "won"
    t["losses"] += status == "lost"
    t["pushes"] += status == "push"
    if status != "push":
        t["units_staked"] += stake
        try:
            d = _decimal(r.get("odds"))
            t["_be"] += 1.0 / d
            t["_be_n"] += 1
            t["_price"] += float(r.get("odds"))
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    t["net_units"] += float(r.get("pnl_units") or 0.0) * (1.0 if stake else 0.0)


def _finish(t: dict) -> dict:
    out = {k: v for k, v in t.items() if not k.startswith("_")}
    dec = t["wins"] + t["losses"]
    out["units_staked"] = round(t["units_staked"], 2)
    out["net_units"] = round(t["net_units"], 2)
    out["roi"] = (t["net_units"] / t["units_staked"]) if t["units_staked"] else None
    out["win_rate"] = (t["wins"] / dec) if dec else None
    out["breakeven"] = (t["_be"] / t["_be_n"]) if t["_be_n"] else None
    out["avg_price"] = round(t["_price"] / t["_be_n"]) if t["_be_n"] else None
    return out


def report(rows: list, sport: str | None = None, recent: int = RECENT,
           replayed: tuple | None = None) -> dict:
    """The record at the rule's stakes, from settled headline rows.

    ``rows`` carry ``day``, ``sport``, ``category``, ``odds``, ``status``,
    ``stake_units`` and ``pnl_units`` (and whatever a recent row should
    show). The replay always runs over every league — each league's rule is
    its own, but the same walk serves every page — and ``sport`` narrows the
    totals. ``replayed`` is a `replay` already run over these rows."""
    flags, state = replayed if replayed is not None else replay(rows)
    tot, halves, curve, staked_rows = _blank(), {"edge": _blank(), "likely": _blank()}, {}, []
    placed = _blank()
    sp = str(sport or "").lower()
    for r, on in zip(rows, flags):
        if sp and str(r.get("sport") or "").lower() != sp:
            continue
        h = half_of(r.get("category"))
        if h is None:
            continue
        stake = float(r.get("stake_units") or 0.0) if on else 0.0
        _add(placed, r, float(r.get("stake_units") or 0.0))
        if not on:
            tot["tracked"] += 1
            halves[h]["tracked"] += 1
            continue
        _add(tot, r, stake)
        _add(halves[h], r, stake)
        d = sort_day(r.get("day"))
        c = curve.setdefault(d, {"date": d, "day_u": 0.0, "n": 0, "w": 0, "l": 0, "staked": 0.0})
        c["day_u"] += float(r.get("pnl_units") or 0.0)
        c["n"] += 1
        c["w"] += r.get("status") == "won"
        c["l"] += r.get("status") == "lost"
        if r.get("status") != "push":
            c["staked"] += stake
        staked_rows.append(r)
    cum, pts = 0.0, []
    for d in sorted(curve):
        c = curve[d]
        cum += c["day_u"]
        pts.append({**c, "day_u": round(c["day_u"], 2), "cum_u": round(cum, 2),
                    "staked": round(c["staked"], 2)})
    staked_rows.sort(key=lambda r: (sort_day(r.get("day")), r.get("id") or 0), reverse=True)
    out = _finish(tot)
    out.update({"rule": VERSION, "since": SINCE, "label": LABEL,
                "by_half": {h: _finish(t) for h, t in halves.items()},
                "as_placed": {k: v for k, v in _finish(placed).items()
                              if k in ("settled", "wins", "losses", "pushes", "units_staked",
                                       "net_units", "roi", "win_rate")}})
    return {"overall": out, "curve": pts,
            "recent": [_recent(r) for r in staked_rows[:max(0, int(recent))]],
            "plan": plan_from(state, sport)}


RECENT_KEYS = ("date", "sport", "player", "market", "side", "line", "odds", "grade",
               "status", "pnl_units", "hit_prob", "stake_units", "book", "category")


def _recent(r: dict) -> dict:
    out = {k: r.get(k) for k in RECENT_KEYS if k in r}
    out["date"] = r.get("day") or r.get("date")
    return out


def plan_from(state: dict, sport: str | None = None) -> dict:
    """{sport: {"edge": {...}, "likely": {...}}} — what the rule stakes next."""
    out: dict = {}
    sp = str(sport or "").lower()
    for (h, s), v in sorted(state.items()):
        if sp and s != sp:
            continue
        b = v["book"]
        out.setdefault(s, {})[h] = {"staked": v["staked"], "n": b.n,
                                    "roi": round(b.roi(), 4), "z": round(b.z(), 2),
                                    "why": why(h, v["staked"], b)}
    return out


# --- the journal (engine/ledger) ---------------------------------------------------
def headline_rows(conn, since: str | None = None) -> list:
    """Every settled, staked row of the headline record (the books
    `ledger.POOLED_BOOKS` names, each pick once), oldest first, benched
    leagues out — the rows `ledger.lab_rows` serves the strategy lab."""
    from . import ledger as L
    books, bargs = L.books_sql(L.POOLED_BOOKS)
    q = (f"SELECT id, {L.day_expr()} AS day, date, sport, category, player, market, side, "
         "line, odds, grade, status, pnl_units, stake_units, hit_prob, book FROM bets "
         f"WHERE status IN ('won','lost','push') AND stake_units > 0 AND {books}")
    args: list = list(bargs)
    if since:
        q += f" AND {L.day_expr()} >= ?"
        args.append(since)
    ex = tuple(str(x).lower() for x in L.BENCHED_SPORTS)
    if ex:
        q += f" AND LOWER(sport) NOT IN ({','.join('?' * len(ex))})"
        args += list(ex)
    q += " ORDER BY id"
    return [dict(r) for r in conn.execute(q, args)]


#: The temp table the staked picks' ids go into, for `ledger.performance`,
#: `pnl_curve` and `recent_settled` (their ``only_ids``).
IDS_TABLE = "temp.staked_ids"


def _open_staked(conn, state: dict, sport: str | None = None) -> int:
    """Open picks whose half of their league the rule stakes now."""
    from . import ledger as L
    books, bargs = L.books_sql(L.POOLED_BOOKS)
    q = (f"SELECT LOWER(sport) AS sp, category, COUNT(*) AS n FROM bets WHERE status='open' "
         f"AND stake_units > 0 AND {books}")
    args: list = list(bargs)
    if sport:
        q += " AND LOWER(sport)=?"
        args.append(str(sport).lower())
    n = 0
    for r in conn.execute(q + " GROUP BY LOWER(sport), category", args):
        h = half_of(r["category"])
        if h is None or L.is_benched(r["sp"]):
            continue
        v = state.get((h, r["sp"]))
        if (v["staked"] if v else h == "edge"):
            n += int(r["n"] or 0)
    return n


def staked_reports(conn, sports=(), since: str | None = None) -> dict:
    """{"overall", "curve", "recent", "plan", "by_sport": {sport: the same}}
    — one read of the journal and one walk for the whole export.

    The totals are `ledger.performance` over the picks the rule staked —
    every field the Record page reads (CLV, streak, the splits), the same
    arithmetic as every other record on the page — with the rule's own
    counts beside them: how many picks were tracked and not staked, each
    half's share, and the record as placed."""
    from . import ledger as L
    rows = headline_rows(conn, since)
    replayed = replay(rows)
    flags, state = replayed
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS staked_ids (id INTEGER PRIMARY KEY)")
    conn.execute(f"DELETE FROM {IDS_TABLE}")
    conn.executemany(f"INSERT OR IGNORE INTO {IDS_TABLE} (id) VALUES (?)",
                     [(r["id"],) for r, on in zip(rows, flags) if on and r.get("id") is not None])

    def one(sport=None) -> dict:
        light = report(rows, sport, recent=0, replayed=replayed)
        perf = L.performance(conn, sport, category=L.POOLED_BOOKS, since=since,
                             only_ids=IDS_TABLE)
        lo = light["overall"]
        perf.update({"rule": VERSION, "since": SINCE, "label": LABEL,
                     "tracked": lo["tracked"], "by_half": lo["by_half"],
                     "as_placed": lo["as_placed"],
                     "open": _open_staked(conn, state, sport)})
        return {"overall": perf,
                "curve": L.pnl_curve(conn, sport, since=since, category=L.POOLED_BOOKS,
                                     only_ids=IDS_TABLE),
                "recent": L.recent_settled(conn, L.RECENT_LIMIT if sport is None else RECENT_SPORT,
                                           category=L.POOLED_BOOKS, sport=sport, since=since,
                                           only_ids=IDS_TABLE),
                "plan": light["plan"]}

    out = one()
    out["by_sport"] = {sp: one(sp) for sp in sports}
    return out


def plan(conn=None) -> dict:
    """What the rule stakes next, per league — {sport: {"edge", "likely"}}.

    Read from the whole headline record (`headline_rows` since the record's
    epoch), so the answer is the record's own. A journal that cannot be read
    answers {} and every caller treats that as "the defaults": Edge staked,
    Most Likely tracked."""
    own = conn is None
    try:
        if own:
            from . import ledger as L
            conn = L.connect()
        from . import ledger as L
        _flags, state = replay(headline_rows(conn, getattr(L, "RECORD_EPOCH", None)))
        return plan_from(state)
    except Exception:                                         # noqa: BLE001
        return {}
    finally:
        if own and conn is not None:
            try:
                conn.close()
            except Exception:                                 # noqa: BLE001
                pass


def promoted(*sports) -> dict:
    """A plan with these leagues' Most Likely books staked (and their Edge
    books, as by default) — the shape `plan` returns, for a caller that sets
    the answer rather than reading it off the record: a test, or
    `python3 -m engine.stakeplan --promote nba`."""
    return {str(s).lower(): {"edge": {"staked": True}, "likely": {"staked": True}}
            for s in sports}


def store(conn, plan_: dict) -> None:
    """Keep ``plan_`` where the journal reads it (ledger.STAKE_PLAN_KEY)."""
    import json as _json
    from . import ledger as L
    L.set_cfg(conn, L.STAKE_PLAN_KEY, _json.dumps(plan_ or {}, sort_keys=True))


def likely_staked(sport, conn=None, _plan: dict | None = None) -> bool:
    """Does this league's Most Likely book carry stakes now? False until it
    clears LIKELY_GO."""
    p = _plan if _plan is not None else plan(conn)
    return bool(((p.get(str(sport or "").lower()) or {}).get("likely") or {}).get("staked"))


def edge_staked(sport, conn=None, _plan: dict | None = None) -> bool:
    """Does this league's Edge book carry stakes now? True unless EDGE_STOP."""
    p = _plan if _plan is not None else plan(conn)
    e = (p.get(str(sport or "").lower()) or {}).get("edge")
    return True if e is None else bool(e.get("staked"))


def main(argv=None) -> int:
    """Print what the rule stakes next, per league, from the journal."""
    import argparse
    import json as _json
    ap = argparse.ArgumentParser(description="The stake rule's answer per league (v4).")
    ap.add_argument("--json", action="store_true", help="print the plan as JSON")
    a = ap.parse_args(argv)
    p = plan()
    if a.json:
        print(_json.dumps(p, indent=2, sort_keys=True))
        return 0
    if not p:
        print("no graded picks on the record yet — Edge staked, Most Likely tracked")
        return 0
    for sport, halves in sorted(p.items()):
        for h in ("edge", "likely"):
            if h in halves:
                print(f"  {sport.upper():5s} {'Edge' if h == 'edge' else 'Most Likely':12s} "
                      f"{halves[h].get('why', '')}")
    return 0


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(main())
