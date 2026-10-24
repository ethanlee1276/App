"""Which books copy which — and the consensus that counts each opinion once.

Ethan, 2026-10-16: "add everything now. 1-13" — idea 4. Several of the
books we read hang the same number at the same price night after night,
because they buy it from the same supplier or follow the same leader. A
"consensus" that counts nine books where there are four opinions is the
loudest supplier's number with extra weight, and it is what every no-vig
"fair price" on the site averages over today.

THREE MEASUREMENTS, all on data the box already keeps:

  * AGREEMENT (every stored close, every season). For each pair of books,
    on every player-date both priced: how often the two hung the identical
    line, and how far apart their over prices were when they did. Books
    that agree far more than chance are one opinion. Average-linkage
    clustering on 1 − (identical-line rate) groups them; a pair inside
    SAME_FEED of each other ends up in one group.
  * LEAD AND LAG (the prop tape, every book's number when it changes, kept
    since September). When a book moves a line and another in its group
    moves the same way within LAG_WINDOW minutes, the first led. The book
    that leads its group most is its leader, with the median lag.
  * THE CONSENSUS TEST, written before its first run. On held-out seasons,
    at every close where at least MIN_GROUPS groups quote the same line, the
    fair over chance two ways: the plain mean over books, and the mean over
    groups (each group's books averaged first). The group-weighted one must
    have the lower log loss, with a paired t ≥ MIN_T, over at least
    MIN_PROPS props. Until it does, nothing on any board reads it.

WHAT THE PAGE SAYS. For a pick: how many books price him, and how many
opinions that is; the fair chance counted by book and by opinion; and any
group whose leader has moved while its copies still show the old number
(stale, with the usual lag). A reading.

Standard library only.
"""

from __future__ import annotations

import datetime as _dt
import json
import math

from .models import PASS_YDS, RUSH_YDS, REC_YDS, RECEPTIONS

MARKETS = (PASS_YDS, RUSH_YDS, REC_YDS, RECEPTIONS)
#: Two books whose lines are identical at least this often are one feed.
SAME_FEED = 0.25                  # on the distance 1 − identical rate
#: A pair needs this many shared closes before its rate means anything.
MIN_SHARED = 200
#: A copy follows within this many minutes, or it did not follow.
LAG_WINDOW = 90
#: The consensus test.
MIN_GROUPS = 3
MIN_T = 2.0
MIN_PROPS = 2000
STORE = "bookclusters.json"


def _implied(o):
    try:
        o = float(o)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(o) or -100 < o < 100:
        return None
    return 100.0 / (o + 100.0) if o > 0 else -o / (-o + 100.0)


def fair_over(over, under):
    a, b = _implied(over), _implied(under)
    if a is None or b is None or a + b <= 0:
        return None
    return a / (a + b)


# ---- agreement and the groups ---------------------------------------------------

def _as_quotes(books: dict) -> list:
    """A compact close (`bookmenu.closes_compact`: {book: (line, over,
    under)}) as the quote dicts the rest of this module reads."""
    return [{"book": b, "line": q[0], "over_odds": q[1], "under_odds": q[2]} for b, q in books.items()]


def tally(acc: dict, quotes) -> None:
    """Add one key's quotes to the running pair counts."""
    q = {}
    for x in quotes:
        b = str(x.get("book") or "")
        try:
            q[b] = (float(x["line"]), _implied(x.get("over_odds")))
        except (KeyError, TypeError, ValueError):
            continue
    books = sorted(q)
    for i, a in enumerate(books):
        for b in books[i + 1:]:
            s = acc.setdefault((a, b), [0, 0, 0.0, 0])
            s[0] += 1
            if q[a][0] == q[b][0]:
                s[1] += 1
                if q[a][1] is not None and q[b][1] is not None:
                    s[2] += abs(q[a][1] - q[b][1])
                    s[3] += 1


def finish(acc: dict) -> dict:
    return {k: {"shared": s[0], "same": round(s[1] / s[0], 4),
                "gap": round(s[2] / s[3], 4) if s[3] else None}
            for k, s in acc.items()}


def pair_agreement(closes_by_key) -> dict:
    """``{(a, b): {"shared", "same", "gap"}}`` over every key both books
    priced: shared closes, identical-line rate, mean |over chance| apart
    when the line matched."""
    acc: dict = {}
    for quotes in closes_by_key:
        tally(acc, quotes)
    return finish(acc)


def groups(pairs: dict, cut: float = SAME_FEED) -> list:
    """Average-linkage clustering on 1 − identical rate, merging while the
    closest two groups sit under `cut`. Pairs under MIN_SHARED count as far
    apart: too little evidence to call two books one feed."""
    books = sorted({b for k in pairs for b in k})
    dist = {}
    for (a, b), s in pairs.items():
        dist[(a, b)] = dist[(b, a)] = (1.0 - s["same"]) if s["shared"] >= MIN_SHARED else 1.0
    cl = [[b] for b in books]

    def d(x, y):
        ds = [dist.get((a, b), 1.0) for a in x for b in y]
        return sum(ds) / len(ds)
    while len(cl) > 1:
        best = None
        for i in range(len(cl)):
            for j in range(i + 1, len(cl)):
                v = d(cl[i], cl[j])
                if best is None or v < best[0]:
                    best = (v, i, j)
        if best[0] >= cut:
            break
        _v, i, j = best
        cl[i] = sorted(cl[i] + cl[j])
        del cl[j]
    return sorted(cl, key=lambda g: (-len(g), g))


def group_of(fitted_groups: list) -> dict:
    return {b: i for i, g in enumerate(fitted_groups or []) for b in g}


# ---- lead and lag -----------------------------------------------------------------

def moves(rows) -> list:
    """``rows``: [(taken_at, instrument, book, line)] in time order →
    [(t, instrument, book, sign)] wherever a book's line changed."""
    last: dict = {}
    out = []
    for at, inst, book, line in rows:
        k = (inst, book)
        prev = last.get(k)
        last[k] = line
        if prev is not None and line is not None and line != prev:
            out.append((at, inst, book, 1 if line > prev else -1))
    return out


def _minutes(a, b):
    def t(s):
        return _dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return (t(b) - t(a)).total_seconds() / 60.0


def leaders(mv: list, fitted_groups: list) -> dict:
    """Per group: which book's moves its group-mates follow most, and the
    median minutes until they do."""
    gid = group_of(fitted_groups)
    by_inst: dict = {}
    for m in mv:
        by_inst.setdefault(m[1], []).append(m)
    led: dict = {}
    lags: dict = {}
    for ms in by_inst.values():
        ms.sort()
        for i, (t0, _inst, b0, s0) in enumerate(ms):
            g = gid.get(b0)
            if g is None:
                continue
            for t1, _i, b1, s1 in ms[i + 1:]:
                gap = _minutes(t0, t1)
                if gap > LAG_WINDOW:
                    break
                if b1 != b0 and gid.get(b1) == g and s1 == s0:
                    led[(g, b0)] = led.get((g, b0), 0) + 1
                    lags.setdefault((g, b0), []).append(gap)
    out = {}
    for (g, b), n in led.items():
        if g not in out or n > out[g]["follows"]:
            ls = sorted(lags[(g, b)])
            out[g] = {"leader": b, "follows": n, "lag_min": round(ls[len(ls) // 2], 1)}
    return {str(k): v for k, v in out.items()}


# ---- the consensus, two ways --------------------------------------------------------

def consensus(quotes, fitted_groups: list, line=None) -> dict | None:
    """The fair over chance at one line (the modal line by default),
    counted by book and by group. None under two books."""
    by_line: dict = {}
    for q in quotes or []:
        get = (lambda k, q=q: q.get(k)) if isinstance(q, dict) else (lambda k, q=q: getattr(q, k, None))
        try:
            ln = float(get("line"))
        except (TypeError, ValueError):
            continue
        p = fair_over(get("over_odds"), get("under_odds"))
        if p is not None:
            by_line.setdefault(ln, []).append((str(get("book") or ""), p))
    if not by_line:
        return None
    if line is None:
        line = max(by_line, key=lambda ln: len(by_line[ln]))
    rows = by_line.get(float(line)) or []
    if len(rows) < 2:
        return None
    gid = group_of(fitted_groups)
    per: dict = {}
    for b, p in rows:
        per.setdefault(gid.get(b, f"solo:{b}"), []).append(p)
    by_book = sum(p for _b, p in rows) / len(rows)
    by_group = sum(sum(v) / len(v) for v in per.values()) / len(per)
    return {"line": float(line), "books": len(rows), "opinions": len(per),
            "by_book": round(by_book, 4), "by_group": round(by_group, 4)}


def stale(quotes, fitted_groups: list, leads: dict) -> list:
    """A group whose leader's line differs from its copies' right now: the
    copies are showing the number the leader has left."""
    line_of = {}
    for q in quotes or []:
        get = (lambda k, q=q: q.get(k)) if isinstance(q, dict) else (lambda k, q=q: getattr(q, k, None))
        try:
            line_of[str(get("book") or "")] = float(get("line"))
        except (TypeError, ValueError):
            continue
    out = []
    for gi, g in enumerate(fitted_groups or []):
        lead = (leads or {}).get(str(gi))
        if not lead or lead["leader"] not in line_of:
            continue
        lv = line_of[lead["leader"]]
        behind = [b for b in g if b != lead["leader"] and b in line_of and line_of[b] != lv]
        if behind:
            out.append({"leader": lead["leader"], "line": lv, "behind": {b: line_of[b] for b in behind},
                        "lag_min": lead["lag_min"]})
    return out


# ---- the measurement (the box) ---------------------------------------------------------

def _logloss(p, y):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return -(math.log(p) if y else math.log(1 - p))


def consensus_test(cases, fitted_groups) -> dict:
    """``cases``: [(quotes, actual)] → paired log-loss difference (by book
    minus by group; positive favours the groups) over props where at least
    MIN_GROUPS groups quote the modal line."""
    diffs = []
    for quotes, actual in cases:
        c = consensus(quotes, fitted_groups)
        if not c or c["opinions"] < MIN_GROUPS or actual == c["line"]:
            continue
        y = int(actual > c["line"])
        diffs.append(_logloss(c["by_book"], y) - _logloss(c["by_group"], y))
    n = len(diffs)
    if n < 2:
        return {"n": n, "gain": None, "t": None, "holds": False}
    m = sum(diffs) / n
    var = sum((d - m) ** 2 for d in diffs) / (n - 1)
    t = m / math.sqrt(var / n) if var > 0 else None
    return {"n": n, "gain": round(m, 5), "t": None if t is None else round(t, 2),
            "holds": bool(n >= MIN_PROPS and m > 0 and (t or 0) >= MIN_T)}


#: The prop tape (every book's number when it changes) began here; the
#: seasons before it are one harvested snapshot a day, which carry no
#: order of moves, and reading them all at once would not fit the box.
TAPE_SINCE = "2026-09-01"


def _tape_rows(conn, sport, since: str = TAPE_SINCE):
    """Every per-book number the prop tape kept, in time order."""
    return [(r[0], (r[1], r[2], r[3]), r[4], r[5]) for r in conn.execute(
        "SELECT taken_at, event_id, player, market, book, line FROM odds_history "
        "WHERE sport=? AND line IS NOT NULL AND taken_at >= ? ORDER BY taken_at", (sport, since))]


def measure(conn, sport: str = "nfl") -> dict:
    """Agreement → groups → leaders → the held-out consensus test."""
    from .backtest import _norm
    from .bookmenu import closes_compact
    actual: dict = {}
    from .formbook import game_dates
    dates = game_dates()
    for r in conn.execute("SELECT season, period, player, team, market, value FROM player_game_logs "
                          "WHERE sport=? AND value IS NOT NULL AND market IN (%s)" % ",".join("?" * len(MARKETS)),
                          (sport, *MARKETS)):
        try:
            d = dates.get((int(r["season"]), int(r["period"]), r["team"]))
        except (TypeError, ValueError):
            continue
        if d:
            actual[(r["market"], _norm(r["player"]), d)] = (int(r["season"]), float(r["value"]))
    seasons = sorted({s for s, _v in actual.values()})
    test = set(seasons[-2:]) if len(seasons) >= 3 else set(seasons)
    # ONE MARKET AT A TIME, counted into the pairs as it goes and kept only
    # where the held-out test needs it: six seasons of closes at every book
    # do not fit the box at once.
    acc: dict = {}
    held: list = []
    for m in MARKETS:
        closes = closes_compact(conn, sport, m)
        for (name, date), books in closes.items():
            quotes = _as_quotes(books)
            tally(acc, quotes)
            a = actual.get((m, name, date))
            if a and a[0] in test:
                held.append((quotes, a[1]))
        del closes
    pairs = finish(acc)
    grp = groups(pairs)
    leads = leaders(moves(_tape_rows(conn, sport)), grp)
    cases = held
    return {"sport": sport, "books": sorted({b for k in pairs for b in k}), "pairs": len(pairs),
            "groups": grp, "leaders": leads, "test_seasons": sorted(test),
            "consensus": consensus_test(cases, grp),
            "closest": sorted(({"a": a, "b": b, **s} for (a, b), s in pairs.items() if s["shared"] >= MIN_SHARED),
                              key=lambda x: -x["same"])[:12]}


def save(res: dict) -> str:
    from . import modelstate
    import os
    p = modelstate.path(STORE)
    try:
        with open(p) as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        d = {}
    d[res["sport"]] = {k: res[k] for k in ("groups", "leaders", "consensus", "test_seasons")}
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w") as fh:
        json.dump(d, fh, indent=1)
    return p


def load(sport: str) -> dict:
    from . import modelstate
    try:
        with open(modelstate.path(STORE)) as fh:
            return json.load(fh).get(sport) or {}
    except (OSError, ValueError):
        return {}


def report_lines(res: dict) -> list:
    out = [f"Which books copy which — {res['sport'].upper()}: {len(res['books'])} books, {res['pairs']} pairs"]
    out.append("  closest pairs (identical line rate · over-price gap when identical · shared closes):")
    for p in res["closest"]:
        out.append(f"    {p['a'][:14]:14s} {p['b'][:14]:14s} {p['same']:.0%} · {p['gap'] if p['gap'] is not None else '—'} · {p['shared']}")
    out.append(f"  groups (one opinion each, cut at {1 - SAME_FEED:.0%} identical):")
    for i, g in enumerate(res["groups"]):
        lead = res["leaders"].get(str(i))
        out.append(f"    {i}: {', '.join(g)}" + (f"  — leader {lead['leader']}, copies follow in ~{lead['lag_min']} min "
                                                 f"({lead['follows']} times)" if lead else ""))
    c = res["consensus"]
    out.append(f"  consensus test {res['test_seasons']}: n {c['n']}, log loss by book − by group {c['gain']} "
               f"(t {c['t']}) — {'HOLDS' if c['holds'] else 'does not hold'}")
    out.append(f"  THE BAR: group-weighted fair beats book-weighted on log loss, t ≥ {MIN_T}, ≥ {MIN_PROPS} props "
               f"with {MIN_GROUPS}+ groups on the line")
    return out


# ---- the ideas file ------------------------------------------------------------------

def ideas_section(props, games, board, sport):
    fit = load(sport)
    grp, leads = fit.get("groups") or [], fit.get("leaders") or {}
    rows = {}
    for row in (board or {}).get("recommendations") or []:
        quotes = row.get("all_lines") or []
        if not row.get("player") or len(quotes) < 2:
            continue
        c = consensus(quotes, grp)
        if not c:
            continue
        rows[f"{row['player']}|{row.get('market')}"] = {**c, "stale": stale(quotes, grp, leads)}
    return {"rows": rows, "groups": grp, "measured": bool(grp), "consensus": fit.get("consensus") or {}}


def pick_view(sec, player, market, side="", line=None):
    r = (sec.get("rows") or {}).get(f"{player}|{market}")
    if not r:
        return None
    return {**r, "measured": sec.get("measured"), "consensus": sec.get("consensus") or {},
            "groups": [g for g in sec.get("groups") or [] if len(g) > 1]}


def game_view(sec, home, away):
    return None


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Which books copy which, and the consensus that counts each opinion once")
    ap.add_argument("--sport", default="nfl")
    ap.add_argument("--save", action="store_true", help="keep the groups and leaders where the pick page reads them")
    a = ap.parse_args(argv)
    from . import db as _db
    conn = _db.connect()
    try:
        res = measure(conn, a.sport)
    finally:
        conn.close()
    print("\n".join(report_lines(res)))
    if a.save:
        print(f"  saved → {save(res)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
