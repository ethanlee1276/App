"""How each book sets a line — and how the line SHOULD have been set.

Ethan, 2026-10-16: "add everything now. 1-13" — idea 3. Every book turns
the same public numbers (his last game, his last three, his season, his
career) into a line. Fit that recipe from the lines it actually hung, fit
the recipe that actually predicted what happened, and the difference is
the book's habit: a book that leans 40% on last week when the results say
15% will hang a number too high after every big game. That turns "find
the books' biases" into a measurement instead of a guess.

THE TWO RECIPES, one least-squares fit each, on the same four features
(plus a constant), per market and per book:

    book recipe      line   ~ a + b1·last game + b2·last three + b3·season + b4·career
    outcome recipe   result ~ a + b1·last game + b2·last three + b3·season + b4·career

"Weight on last game" is b1 over the four slopes' sum, so the two recipes
compare on the same scale.

WHAT THE PAGE SAYS. For a pick: each book's recipe applied to his numbers
(what that book "would" hang), the line it did hang, and what the outcome
recipe expects — plus how much each leans on his last game. A reading.

THE BAR, WRITTEN BEFORE ITS FIRST RUN. Fit on every season but the last
two; on those two, take the closes where the outcome recipe sits FLAG_SD
or more of its own residual spread away from the line. The side it points
to must beat the close's own fair chance by MIN_EXCESS on average, with
t ≥ MIN_T, over at least MIN_CASES closes, and above zero in each test
season. Until then nothing reads it.

Standard library only.
"""

from __future__ import annotations

import json
import math

from .models import PASS_YDS, RUSH_YDS, REC_YDS, RECEPTIONS

MARKETS = (PASS_YDS, RUSH_YDS, REC_YDS, RECEPTIONS)
FEATURES = ("last1", "last3", "season", "career")
#: Prior games a close needs before its features mean anything.
MIN_PRIOR = 3
#: Closes a recipe needs before it is fitted.
MIN_FIT = 200
#: The bar.
FLAG_SD = 0.75
MIN_EXCESS = 0.03
MIN_T = 2.0
MIN_CASES = 300
STORE = "bookrecipe_fit.json"


def features_from(prior: list) -> dict | None:
    """``prior``: his earlier games, newest first, as (season, value).
    Last game, mean of the last three, this season's mean (his career
    mean when the season has none yet), career mean."""
    if len(prior) < MIN_PRIOR:
        return None
    vals = [v for _s, v in prior]
    season_now = prior[0][0]
    this = [v for s, v in prior if s == season_now]
    career = sum(vals) / len(vals)
    return {"last1": vals[0], "last3": sum(vals[:3]) / 3.0,
            "season": (sum(this) / len(this)) if this else career, "career": career}


def features_from_row(row: dict) -> dict | None:
    """The same four off a priced board row's own `form` block."""
    f = row.get("form") or {}
    try:
        out = {"last1": float(f["last1"]), "last3": float(f["last3"]),
               "season": float(f.get("season") if f.get("season") is not None else f["career"]),
               "career": float(f["career"] if f.get("career") is not None else f["season"])}
    except (KeyError, TypeError, ValueError):
        return None
    return out if all(math.isfinite(v) for v in out.values()) else None


def _solve(a, b):
    """Gaussian elimination with partial pivoting; None when singular."""
    n = len(a)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        if abs(m[p][c]) < 1e-12:
            return None
        m[c], m[p] = m[p], m[c]
        for r in range(n):
            if r != c:
                f = m[r][c] / m[c][c]
                for k in range(c, n + 1):
                    m[r][k] -= f * m[c][k]
    return [m[i][n] / m[i][i] for i in range(n)]


def fit(xs: list, ys: list, ridge: float = 1e-6) -> dict | None:
    """Least squares on [1, last1, last3, season, career] → y, with a
    whisper of ridge so near-collinear features (last three and season
    move together) do not blow the slopes up."""
    if len(xs) < MIN_FIT:
        return None
    k = len(FEATURES) + 1
    ata = [[0.0] * k for _ in range(k)]
    aty = [0.0] * k
    for x, y in zip(xs, ys):
        v = [1.0] + [x[f] for f in FEATURES]
        for i in range(k):
            aty[i] += v[i] * y
            for j in range(k):
                ata[i][j] += v[i] * v[j]
    for i in range(1, k):
        ata[i][i] += ridge * len(xs)
    w = _solve(ata, aty)
    if w is None:
        return None
    res = [y - predict({"w": w}, x) for x, y in zip(xs, ys)]
    sd = math.sqrt(sum(r * r for r in res) / max(1, len(res) - k))
    slopes = w[1:]
    tot = sum(abs(s) for s in slopes) or 1.0
    return {"w": [round(c, 5) for c in w], "sd": round(sd, 4), "n": len(xs),
            "weights": {f: round(abs(s) / tot, 3) for f, s in zip(FEATURES, slopes)}}


def predict(model: dict, x: dict) -> float:
    w = model["w"]
    return w[0] + sum(c * x[f] for c, f in zip(w[1:], FEATURES))


# ---- the measurement (the box) -------------------------------------------------

def _implied(o):
    try:
        o = float(o)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(o) or -100 < o < 100:
        return None
    return 100.0 / (o + 100.0) if o > 0 else -o / (-o + 100.0)


def _fair_over(q):
    a, b = _implied(q.get("over_odds")), _implied(q.get("under_odds"))
    if a is None or b is None or a + b <= 0:
        return None
    return a / (a + b)


def history(conn, sport: str = "nfl", market: str = REC_YDS, dates=None) -> list:
    """Every stored close with his features as they stood before the game
    and what he did: [(season, book, line, fair_over, x, actual)]."""
    from . import db as _db
    from .backtest import _norm
    if dates is None:
        from .formbook import game_dates
        dates = game_dates()
    seq: dict = {}
    for r in conn.execute("SELECT season, period, player, team, value FROM player_game_logs "
                          "WHERE sport=? AND market=? AND value IS NOT NULL ORDER BY season, period", (sport, market)):
        try:
            season, week = int(r["season"]), int(r["period"])
        except (TypeError, ValueError):
            continue
        seq.setdefault(_norm(r["player"]), []).append((season, week, r["team"], float(r["value"])))
    closes = _db.closing_odds_all_books(conn, sport, market)
    out = []
    for name, games in seq.items():
        prior: list = []
        for season, week, team, value in games:
            x = features_from(prior)
            date = dates.get((season, week, team))
            if x is not None and date:
                for q in closes.get((name, date), []):
                    try:
                        line = float(q["line"])
                    except (TypeError, ValueError, KeyError):
                        continue
                    out.append((season, str(q.get("book") or ""), line, _fair_over(q), x, value))
            prior.insert(0, (season, value))
    return out


def fit_all(rows: list) -> dict:
    """``{"outcome": recipe, "books": {book: recipe}}`` for one market."""
    seen: dict = {}
    for season, book, line, _f, x, actual in rows:
        seen.setdefault(("_o", season, id(x)), (x, actual))
    oxs = [x for x, _a in seen.values()]
    oys = [a for _x, a in seen.values()]
    books: dict = {}
    for _season, book, line, _f, x, _a in rows:
        books.setdefault(book, ([], []))
        books[book][0].append(x)
        books[book][1].append(line)
    return {"outcome": fit(oxs, oys),
            "books": {b: m for b, (xs, ys) in sorted(books.items()) if (m := fit(xs, ys))}}


def score(rows: list, outcome: dict) -> dict:
    """On the closes where the outcome recipe sits FLAG_SD of its own
    spread away from the line, the side it points to against the close's
    fair chance, overall and per season."""
    if not outcome:
        return {"all": [], "by_season": {}}
    out = {"all": [], "by_season": {}}
    for season, _book, line, fair, x, actual in rows:
        if fair is None or actual == line:
            continue
        gap = predict(outcome, x) - line
        if abs(gap) < FLAG_SD * outcome["sd"]:
            continue
        over = gap > 0
        hit = int(actual > line) if over else int(actual < line)
        ex = hit - (fair if over else 1 - fair)
        out["all"].append(ex)
        out["by_season"].setdefault(season, []).append(ex)
    return out


def _stats(xs):
    n = len(xs)
    if n < 2:
        return {"n": n, "excess": xs[0] if xs else None, "t": None}
    m = sum(xs) / n
    var = sum((v - m) ** 2 for v in xs) / (n - 1)
    return {"n": n, "excess": round(m, 4), "t": round(m / math.sqrt(var / n), 2) if var > 0 else None}


def measure(conn, sport: str = "nfl", markets=MARKETS) -> dict:
    from .formbook import game_dates
    dates = game_dates()
    res = {"sport": sport, "markets": {}}
    for market in markets:
        rows = history(conn, sport, market, dates)
        years = sorted({r[0] for r in rows})
        entry: dict = {"closes": len(rows), "seasons": years}
        if len(years) >= 3:
            test = set(years[-2:])
            train = [r for r in rows if r[0] not in test]
            held = [r for r in rows if r[0] in test]
            ft = fit_all(train)
            sc = score(held, ft["outcome"])
            st = _stats(sc["all"])
            per = {str(k): _stats(v) for k, v in sorted(sc["by_season"].items())}
            entry["verdict"] = {**st, "by_season": per,
                                "holds": bool(st["n"] >= MIN_CASES and (st["excess"] or 0) >= MIN_EXCESS
                                              and (st["t"] or 0) >= MIN_T
                                              and all((v["excess"] or 0) > 0 for v in per.values()))}
        entry["fit"] = fit_all(rows)
        res["markets"][market] = entry
    return res


def save(res: dict) -> str:
    from . import modelstate
    import os
    p = modelstate.path(STORE)
    try:
        with open(p) as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        d = {}
    d[res["sport"]] = res["markets"]
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
    out = [f"Book recipes — {res['sport'].upper()}"]
    for market, e in res["markets"].items():
        f = e.get("fit") or {}
        o = f.get("outcome")
        out.append(f"  {market}: {e['closes']} closes, seasons {e['seasons']}")
        if o:
            out.append(f"    results:    last game {o['weights']['last1']:.0%} · last three {o['weights']['last3']:.0%} · "
                       f"season {o['weights']['season']:.0%} · career {o['weights']['career']:.0%}  (n {o['n']}, ±{o['sd']})")
        for b, m in (f.get("books") or {}).items():
            out.append(f"    {b[:12]:12s} last game {m['weights']['last1']:.0%} · last three {m['weights']['last3']:.0%} · "
                       f"season {m['weights']['season']:.0%} · career {m['weights']['career']:.0%}  (n {m['n']})")
        v = e.get("verdict")
        if v:
            per = " · ".join(f"{k}: {s['excess']:+.3f} (n {s['n']})" for k, s in v["by_season"].items() if s["excess"] is not None)
            out.append(f"    held out: n {v['n']} excess {v['excess']} t {v['t']} — {'HOLDS' if v['holds'] else 'does not hold'} [{per}]")
    out.append(f"  THE BAR: outcome recipe ≥ {FLAG_SD} of its spread from the line; its side beats the close's fair chance "
               f"by ≥ {MIN_EXCESS:+.2f}, t ≥ {MIN_T}, ≥ {MIN_CASES} closes, above zero in each test season")
    return out


# ---- the ideas file ----------------------------------------------------------------

def ideas_section(props, games, board, sport):
    fitted = load(sport)
    if not fitted:
        return {"rows": {}, "fitted": False}
    rows = {}
    for row in (board or {}).get("recommendations") or []:
        m = row.get("market")
        e = (fitted.get(m) or {}).get("fit") or {}
        o = e.get("outcome")
        x = features_from_row(row)
        if not o or x is None or not row.get("player"):
            continue
        books = []
        for q in row.get("all_lines") or []:
            rec = (e.get("books") or {}).get(str(q.get("book") or ""))
            if not rec or q.get("line") is None:
                continue
            books.append({"book": q["book"], "line": q["line"], "recipe": round(predict(rec, x), 1),
                          "last1": rec["weights"]["last1"]})
        exp = predict(o, x)
        rows[f"{row['player']}|{m}"] = {"expect": round(exp, 1), "sd": o["sd"], "last1": o["weights"]["last1"],
                                        "books": books, "form": {k: round(v, 1) for k, v in x.items()},
                                        "verdict": (fitted.get(m) or {}).get("verdict") or {}}
    return {"rows": rows, "fitted": True}


def pick_view(sec, player, market, side="", line=None):
    r = (sec.get("rows") or {}).get(f"{player}|{market}")
    if not r or not r.get("books"):
        return None
    return r


def game_view(sec, home, away):
    return None


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Fit how each book sets a line, and how it should have")
    ap.add_argument("--sport", default="nfl")
    ap.add_argument("--save", action="store_true", help="keep the recipes where the pick page reads them")
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
