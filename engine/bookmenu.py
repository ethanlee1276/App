"""Does a book's own menu add up? — the books checked against themselves.

Ethan, 2026-10-16: "add everything now. 1-13 and dont stop till everything
is done." The first idea on the list: a book prices a quarterback's yards
and, separately, every receiver he throws to. Those numbers are hung by
different traders off different feeds, and nothing forces them to agree.
When one book's own menu does not add up, one side of it is probably
wrong — and no model is needed to see it, only arithmetic on prices we
already buy.

THE CHECKS. Each compares a PARENT number with the PARTS it is made of, at
ONE book, before kickoff:

    pass_rec   a quarterback's passing yards   vs   his team's receiving yards
    cmp_rec    a quarterback's completions     vs   his team's catches
    rush_rec   a back's rush + rec yards       vs   his rushing and receiving apart
    pass_rush  a passer's pass + rush yards    vs   his passing and rushing apart
    td_total   a team's touchdown prices       vs   the touchdowns its points imply

The statistic is one number, x = log(parts / parent). The parts never
cover the parent exactly — a book prices four or five receivers, not
every man who catches a ball — so x is never 0, and what "normal" looks
like is MEASURED, per check and per count of parts, on this box's own
stored closes (`measure`). A menu is flagged only against that measured
normal: z = (x − typical) / spread, and |z| ≥ FLAG_Z. Before the fit
exists the page shows the arithmetic and says the normal is not measured
yet; it never invents one.

WHICH SIDE A GAP POINTS TO. x above normal means the parts are priced high
against the parent: the parent's over and the parts' unders are the cheap
sides. Below normal, the reverse. That is a reading, and it is shown as
one. Nothing on any board reads it until the bar below is cleared.

THE BAR, WRITTEN BEFORE ITS FIRST RUN. Train on every season but the last
two; test on those two. A check's side (parent or parts) earns a "holds"
when, over the held-out flagged menus:
  1. it beats its own de-vigged chance by at least MIN_EXCESS on average,
  2. with a t of at least MIN_T across MENUS (a menu's parts move together,
     so the menu, not the leg, is the unit),
  3. on at least MIN_CASES flagged menus,
  4. and with the excess above zero in EACH test season on its own.
A check that holds is saved as such; one that does not is saved as
"does not hold" and the page keeps calling its flags readings. Nothing is
promoted to a price without Ethan's yes.

Standard library only.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from .models import (PASS_YDS, REC_YDS, PASS_CMP, RECEPTIONS, RUSH_YDS,
                     RUSH_REC_YDS, PASS_RUSH_YDS, ANYTIME_TD)

ROOT = Path(__file__).resolve().parents[1]

CHECKS = {
    "pass_rec": {"label": "Passing yards against his receivers' yards",
                 "kind": "team", "parent": PASS_YDS, "part": REC_YDS, "unit": "yds"},
    "cmp_rec": {"label": "Completions against his receivers' catches",
                "kind": "team", "parent": PASS_CMP, "part": RECEPTIONS, "unit": "catches"},
    "rush_rec": {"label": "Rush + rec yards against the two apart",
                 "kind": "player", "parent": RUSH_REC_YDS, "parts": (RUSH_YDS, REC_YDS), "unit": "yds"},
    "pass_rush": {"label": "Pass + rush yards against the two apart",
                  "kind": "player", "parent": PASS_RUSH_YDS, "parts": (PASS_YDS, RUSH_YDS), "unit": "yds"},
    "td_total": {"label": "Touchdown prices against the team's points",
                 "kind": "td", "unit": "TDs"},
}

#: Fewer priced parts than this and a team menu is not a menu.
MIN_PARTS = 3
#: Count-of-parts buckets for the team checks: 3, 4, 5, 6 and 7-or-more.
#: Six receivers priced leaves less of the quarterback uncovered than three.
MAX_BUCKET = 7
#: A bucket fitted on fewer training menus than this has no normal.
MIN_FIT = 100
#: How far from normal a menu must sit to be flagged.
FLAG_Z = 2.0
#: The bar (module docstring).
MIN_EXCESS = 0.03
MIN_T = 2.0
MIN_CASES = 150

FIT_FILE = "bookmenu_fit.json"


def _fit_path() -> Path:
    from . import modelstate
    return Path(modelstate.path(FIT_FILE))


# ---- the arithmetic --------------------------------------------------------

def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _implied(odds):
    o = _num(odds)
    if o is None or -100 < o < 100:
        return None
    return 100.0 / (o + 100.0) if o > 0 else -o / (-o + 100.0)


def fair_pair(over, under):
    """De-vigged (over, under) chances from one book's own two prices, or
    None when either side is missing — a one-sided price carries its hold
    in it, and this module does not assume one."""
    a, b = _implied(over), _implied(under)
    if a is None or b is None or a + b <= 0:
        return None
    return a / (a + b), b / (a + b)


def td_rate(yes, no):
    """Expected touchdowns one man's Yes/No prices imply: the Poisson rate
    whose chance of at least one is his de-vigged Yes. Both sides needed."""
    fp = fair_pair(yes, no)
    if fp is None or not (0.0 < fp[0] < 0.999):
        return None
    return -math.log(1.0 - fp[0])


def team_points(spread, total, home: bool):
    """Points a team is expected to score from the game's spread (home
    line, negative = home favoured) and total."""
    s, t = _num(spread), _num(total)
    if s is None or t is None or t <= 0:
        return None
    return t / 2.0 - s / 2.0 if home else t / 2.0 + s / 2.0


def tds_from_points(points):
    """The touchdowns a team total implies, on the shape the touchdown
    board already measured (`devig.expected_tds_affine`)."""
    if points is None:
        return None
    from .devig import expected_tds_affine
    v = expected_tds_affine(points)
    return v if v > 0 else None


def statistic(parts_sum, parent):
    p, s = _num(parent), _num(parts_sum)
    if p is None or s is None or p <= 0 or s <= 0:
        return None
    return math.log(s / p)


def bucket(check: str, n: int) -> str:
    if CHECKS[check]["kind"] != "team":
        return "all"
    return str(min(int(n), MAX_BUCKET))


# ---- the fit ---------------------------------------------------------------

def _median(xs):
    s = sorted(xs)
    n = len(s)
    if not n:
        return None
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def fit(cases) -> dict:
    """``{check: {bucket: {"mu", "sd", "n"}}}`` from training cases.

    Median and 1.4826 × MAD, not mean and standard deviation: a single
    bad quote (a line hung on the wrong man) is a giant x, and one of them
    should not move what normal is."""
    groups: dict = {}
    for c in cases:
        groups.setdefault((c["check"], c["bucket"]), []).append(c["x"])
    out: dict = {}
    for (check, b), xs in groups.items():
        if len(xs) < MIN_FIT:
            continue
        mu = _median(xs)
        mad = _median([abs(x - mu) for x in xs])
        sd = 1.4826 * mad if mad else None
        if not sd:
            continue
        out.setdefault(check, {})[b] = {"mu": round(mu, 5), "sd": round(sd, 5), "n": len(xs)}
    return out


def z_of(fitted: dict, check: str, b: str, x):
    f = ((fitted or {}).get(check) or {}).get(b)
    if not f or x is None:
        return None
    return (x - f["mu"]) / f["sd"]


def load_fit(sport: str) -> dict:
    try:
        d = json.loads(_fit_path().read_text())
    except (OSError, ValueError):
        return {}
    return (d.get(sport) or {}).get("fit") or {}


def load_verdict(sport: str) -> dict:
    try:
        d = json.loads(_fit_path().read_text())
    except (OSError, ValueError):
        return {}
    return (d.get(sport) or {}).get("verdict") or {}


# ---- one slate's menus (the live read) -------------------------------------

def _book_lines(prop) -> dict:
    """``{book: (line, over, under)}`` off a priced prop or a row dict."""
    out = {}
    for ln in (getattr(prop, "lines", None) or (prop.get("lines") if isinstance(prop, dict) else None) or []):
        get = (lambda k, ln=ln: ln.get(k)) if isinstance(ln, dict) else (lambda k, ln=ln: getattr(ln, k, None))
        book, line = get("book"), _num(get("line"))
        if book and line is not None:
            out[str(book)] = (line, get("over_odds"), get("under_odds"))
    return out


def _attr(p, k, default=""):
    return p.get(k, default) if isinstance(p, dict) else getattr(p, k, default)


def menus(props, games, sport: str = "nfl", fitted: dict | None = None) -> list[dict]:
    """Every menu one slate's books hang, checked.

    ``props`` are priced props (or dicts with player, team, position,
    market and per-book ``lines``); ``games`` the board's games (home,
    away, spread, total). One row per (check, book, team or player).
    Rows carry ``z`` and ``lean`` only when a fit exists for their
    bucket."""
    fitted = load_fit(sport) if fitted is None else fitted
    by = {}
    for p in props or []:
        m = _attr(p, "market")
        team = _attr(p, "team")
        if not m or not team:
            continue
        by.setdefault((team, m), []).append(p)
    opp_game = {}
    for g in games or []:
        h, a = _attr(g, "home"), _attr(g, "away")
        if h and a:
            opp_game[h] = (g, True)
            opp_game[a] = (g, False)
    rows: list[dict] = []
    teams = sorted({t for t, _m in by})
    for team in teams:
        g, is_home = opp_game.get(team, (None, None))
        game = f"{_attr(g, 'away')} @ {_attr(g, 'home')}" if g is not None else ""
        for check, spec in CHECKS.items():
            if spec["kind"] == "team":
                rows += _team_menus(check, spec, team, game, by, fitted)
            elif spec["kind"] == "player":
                rows += _player_menus(check, spec, team, game, by, fitted)
            elif g is not None:
                rows += _td_menus(team, game, g, is_home, by, fitted)
    return rows


def _lean(z):
    if z is None or abs(z) < FLAG_Z:
        return None
    return "parent over, parts under" if z > 0 else "parent under, parts over"


def _row(check, team, game, book, parent, parts, x, n, fitted, extra=None):
    b = bucket(check, n)
    z = z_of(fitted, check, b, x)
    row = {"check": check, "label": CHECKS[check]["label"], "unit": CHECKS[check]["unit"],
           "team": team, "game": game, "book": book, "parent": parent, "parts": parts,
           "sum": round(sum(p["line"] for p in parts), 2), "x": round(x, 4), "n": n,
           "bucket": b, "z": None if z is None else round(z, 2), "lean": _lean(z),
           "players": sorted({parent.get("player", "")} | {p["player"] for p in parts} - {""})}
    if extra:
        row.update(extra)
    return row


def _team_menus(check, spec, team, game, by, fitted):
    out = []
    parents = [p for p in by.get((team, spec["parent"]), [])
               if str(_attr(p, "position")).upper() in ("QB", "")]
    parts = [p for p in by.get((team, spec["part"]), [])]
    if not parents or len(parts) < MIN_PARTS:
        return out
    books = set()
    for p in parents:
        books |= set(_book_lines(p))
    for book in sorted(books):
        # The starter is the passer this book prices highest.
        best = None
        for p in parents:
            q = _book_lines(p).get(book)
            if q and (best is None or q[0] > best[1][0]):
                best = (p, q)
        if best is None:
            continue
        pp, pq = best
        legs = []
        for p in parts:
            if _attr(p, "player") == _attr(pp, "player"):
                continue
            q = _book_lines(p).get(book)
            if q:
                legs.append({"player": _attr(p, "player"), "line": q[0]})
        if len(legs) < MIN_PARTS:
            continue
        x = statistic(sum(l["line"] for l in legs), pq[0])
        if x is None:
            continue
        out.append(_row(check, team, game, book, {"player": _attr(pp, "player"), "line": pq[0]},
                        sorted(legs, key=lambda l: -l["line"]), x, len(legs), fitted))
    return out


def _player_menus(check, spec, team, game, by, fitted):
    out = []
    a_m, b_m = spec["parts"]
    combos = by.get((team, spec["parent"]), [])
    if not combos:
        return out
    a_of = {_attr(p, "player"): p for p in by.get((team, a_m), [])}
    b_of = {_attr(p, "player"): p for p in by.get((team, b_m), [])}
    for c in combos:
        name = _attr(c, "player")
        pa, pb = a_of.get(name), b_of.get(name)
        if pa is None or pb is None:
            continue
        la, lb = _book_lines(pa), _book_lines(pb)
        for book, cq in sorted(_book_lines(c).items()):
            qa, qb = la.get(book), lb.get(book)
            if not qa or not qb:
                continue
            x = statistic(qa[0] + qb[0], cq[0])
            if x is None:
                continue
            legs = [{"player": name, "line": qa[0], "market": a_m},
                    {"player": name, "line": qb[0], "market": b_m}]
            out.append(_row(check, team, game, book, {"player": name, "line": cq[0]}, legs, x, 2, fitted))
    return out


def _td_menus(team, game, g, is_home, by, fitted):
    out = []
    pts = team_points(_attr(g, "spread", None), _attr(g, "total", None), bool(is_home))
    want = tds_from_points(pts)
    if want is None:
        return out
    scorers = by.get((team, ANYTIME_TD), [])
    per_book: dict = {}
    for p in scorers:
        for book, (_line, yes, no) in _book_lines(p).items():
            lam = td_rate(yes, no)
            if lam is not None:
                per_book.setdefault(book, []).append({"player": _attr(p, "player"), "line": round(lam, 3)})
    for book, legs in sorted(per_book.items()):
        if len(legs) < MIN_PARTS:
            continue
        x = statistic(sum(l["line"] for l in legs), want)
        if x is None:
            continue
        out.append(_row("td_total", team, game, book,
                        {"player": f"{team} points", "line": round(want, 3)},
                        sorted(legs, key=lambda l: -l["line"]), x, len(legs), fitted,
                        {"points": round(pts, 1)}))
    return out


def flagged(rows) -> list[dict]:
    return sorted((r for r in rows if r.get("lean")), key=lambda r: -abs(r["z"]))


def for_player(rows, player: str) -> list[dict]:
    return [r for r in rows if player in (r.get("players") or [])]


def summary(rows) -> dict:
    """What the page says over the whole slate: how many menus were
    checked, how many have a measured normal, how many are flagged."""
    return {"checked": len(rows), "measured": sum(1 for r in rows if r.get("z") is not None),
            "flagged": sum(1 for r in rows if r.get("lean"))}


# ---- the measurement (the box) ---------------------------------------------

def _season_week_dates(seasons=None) -> dict:
    from .formbook import game_dates
    return game_dates(seasons)


def history_cases(conn, sport: str = "nfl", seasons=None) -> list[dict]:
    """Every stored pre-game menu, with what happened.

    Closes are the last snapshot per player-date at each book
    (`db.closing_odds_all_books`); who a man played for, and what he did,
    come from `player_game_logs`, dated by the schedule. One case per
    (check, book, team-or-player, date)."""
    from . import db as _db
    from .backtest import _norm
    dates = _season_week_dates(seasons)
    who: dict = {}
    actual: dict = {}
    for r in conn.execute(
            "SELECT season, period, player, team, position, market, value FROM player_game_logs "
            "WHERE sport=? AND market IN (?,?,?,?,?,?)",
            (sport, PASS_YDS, REC_YDS, PASS_CMP, RECEPTIONS, RUSH_YDS, ANYTIME_TD)):
        try:
            season, week = int(r["season"]), int(r["period"])
        except (TypeError, ValueError):
            continue
        if seasons and season not in seasons:
            continue
        date = dates.get((season, week, r["team"]))
        if not date or r["value"] is None:
            continue
        k = (_norm(r["player"]), date)
        who[k] = (r["team"], (r["position"] or "").upper(), season)
        actual[k + (r["market"],)] = float(r["value"])
    for (n, d, m) in list(actual):
        if m in (RUSH_YDS, REC_YDS):
            a, b = actual.get((n, d, RUSH_YDS)), actual.get((n, d, REC_YDS))
            if a is not None and b is not None:
                actual[(n, d, RUSH_REC_YDS)] = a + b
        if m in (PASS_YDS, RUSH_YDS):
            a, b = actual.get((n, d, PASS_YDS)), actual.get((n, d, RUSH_YDS))
            if a is not None and b is not None:
                actual[(n, d, PASS_RUSH_YDS)] = a + b
    closes = {m: _db.closing_odds_all_books(conn, sport, m)
              for m in (PASS_YDS, REC_YDS, PASS_CMP, RECEPTIONS, RUSH_YDS,
                        RUSH_REC_YDS, PASS_RUSH_YDS, ANYTIME_TD)}
    games = _game_points(conn, sport, seasons)
    cases: list[dict] = []
    for check, spec in CHECKS.items():
        if spec["kind"] == "team":
            cases += _hist_team(check, spec, closes, who, actual)
        elif spec["kind"] == "player":
            cases += _hist_player(check, spec, closes, who, actual)
        else:
            cases += _hist_td(closes, who, actual, games, dates)
    return cases


def _quotes_by(closes_m, who):
    """``{(team, date, book): [(name, quote)]}`` for one market."""
    out: dict = {}
    for (name, date), quotes in (closes_m or {}).items():
        w = who.get((name, date))
        if not w:
            continue
        for q in quotes:
            if _num(q.get("line")) is None or not q.get("book"):
                continue
            out.setdefault((w[0], date, q["book"]), []).append((name, q))
    return out


def _leg(name, q, market, actual, date):
    a = actual.get((name, date, market))
    fp = fair_pair(q.get("over_odds"), q.get("under_odds"))
    line = _num(q.get("line"))
    if a is None or fp is None or line is None or a == line:
        return None
    return {"player": name, "line": line, "over": int(a > line), "p_over": fp[0]}


def _hist_team(check, spec, closes, who, actual):
    par = _quotes_by(closes.get(spec["parent"]), who)
    prt = _quotes_by(closes.get(spec["part"]), who)
    out = []
    for key, plist in par.items():
        team, date, book = key
        qbs = [(n, q) for n, q in plist if who.get((n, date), ("", ""))[1] in ("QB", "")]
        if not qbs:
            continue
        name, q = max(qbs, key=lambda nq: _num(nq[1]["line"]))
        legs = [(n, pq) for n, pq in prt.get(key, []) if n != name]
        if len(legs) < MIN_PARTS:
            continue
        x = statistic(sum(_num(pq["line"]) for _n, pq in legs), q["line"])
        if x is None:
            continue
        out.append({"check": check, "bucket": bucket(check, len(legs)), "x": x, "season": who[(name, date)][2],
                    "date": date, "book": book, "team": team,
                    "parent": _leg(name, q, spec["parent"], actual, date),
                    "parts": [l for l in (_leg(n, pq, spec["part"], actual, date) for n, pq in legs) if l]})
    return out


def _hist_player(check, spec, closes, who, actual):
    a_m, b_m = spec["parts"]
    out = []
    ca, cb = closes.get(a_m) or {}, closes.get(b_m) or {}
    for (name, date), quotes in (closes.get(spec["parent"]) or {}).items():
        w = who.get((name, date))
        if not w:
            continue
        qa = {q["book"]: q for q in ca.get((name, date), [])}
        qb = {q["book"]: q for q in cb.get((name, date), [])}
        for q in quotes:
            book = q.get("book")
            if book not in qa or book not in qb:
                continue
            x = statistic(_num(qa[book]["line"]) + _num(qb[book]["line"]), q.get("line"))
            if x is None:
                continue
            out.append({"check": check, "bucket": "all", "x": x, "season": w[2], "date": date, "book": book,
                        "team": w[0], "parent": _leg(name, q, spec["parent"], actual, date),
                        "parts": [l for l in (_leg(name, qa[book], a_m, actual, date),
                                              _leg(name, qb[book], b_m, actual, date)) if l]})
    return out


def _game_points(conn, sport, seasons=None) -> dict:
    """``{(season, week, team): (points, is_home)}`` from stored closes."""
    out: dict = {}
    for r in conn.execute("SELECT season, period, home, away, spread, total FROM games WHERE sport=?", (sport,)):
        try:
            season, week = int(r["season"]), int(r["period"])
        except (TypeError, ValueError):
            continue
        if seasons and season not in seasons:
            continue
        for team, home in ((r["home"], True), (r["away"], False)):
            pts = team_points(r["spread"], r["total"], home)
            if team and pts is not None:
                out[(season, week, team)] = pts
    return out


def _hist_td(closes, who, actual, games, dates):
    by: dict = {}
    for (name, date), quotes in (closes.get(ANYTIME_TD) or {}).items():
        w = who.get((name, date))
        if not w:
            continue
        for q in quotes:
            lam = td_rate(q.get("over_odds"), q.get("under_odds"))
            if lam is None or not q.get("book"):
                continue
            by.setdefault((w[0], date, q["book"]), []).append((name, q, lam))
    when = {(t, d): (s, wk) for (s, wk, t), d in dates.items()}
    out = []
    for (team, date, book), legs in by.items():
        sw = when.get((team, date))
        pts = games.get((sw[0], sw[1], team)) if sw else None
        want = tds_from_points(pts)
        if want is None or len(legs) < MIN_PARTS:
            continue
        x = statistic(sum(l for _n, _q, l in legs), want)
        if x is None:
            continue
        parts = []
        for name, q, _lam in legs:
            a = actual.get((name, date, ANYTIME_TD))
            fp = fair_pair(q.get("over_odds"), q.get("under_odds"))
            if a is None or fp is None:
                continue
            parts.append({"player": name, "line": 0.5, "over": int(a > 0.5), "p_over": fp[0]})
        out.append({"check": "td_total", "bucket": bucket("td_total", len(legs)), "x": x, "season": sw[0],
                    "date": date, "book": book, "team": team, "parent": None, "parts": parts})
    return out


def score(cases, fitted) -> dict:
    """Per check and side: how the leaned side did against its own fair
    chance on the flagged menus, overall and per season."""
    out: dict = {}
    for c in cases:
        z = z_of(fitted, c["check"], c["bucket"], c["x"])
        if z is None or abs(z) < FLAG_Z:
            continue
        sign = 1 if z > 0 else -1
        sides = []
        p = c.get("parent")
        if p:
            hit = p["over"] if sign > 0 else 1 - p["over"]
            fair = p["p_over"] if sign > 0 else 1 - p["p_over"]
            sides.append(("parent", hit - fair))
        parts = c.get("parts") or []
        if parts:
            ex = [((1 - l["over"]) - (1 - l["p_over"])) if sign > 0 else (l["over"] - l["p_over"]) for l in parts]
            sides.append(("parts", sum(ex) / len(ex)))
        for side, ex in sides:
            s = out.setdefault(c["check"], {}).setdefault(side, {"all": [], "by_season": {}})
            s["all"].append(ex)
            s["by_season"].setdefault(c["season"], []).append(ex)
    return out


def _stats(xs):
    n = len(xs)
    if n < 2:
        return {"n": n, "excess": (xs[0] if xs else None), "t": None}
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    t = m / math.sqrt(var / n) if var > 0 else None
    return {"n": n, "excess": round(m, 4), "t": None if t is None else round(t, 2)}


def verdict(scored) -> dict:
    """The bar, applied (module docstring)."""
    out: dict = {}
    for check, sides in scored.items():
        for side, s in sides.items():
            st = _stats(s["all"])
            per = {str(k): _stats(v) for k, v in sorted(s["by_season"].items())}
            holds = (st["n"] >= MIN_CASES and (st["excess"] or 0) >= MIN_EXCESS
                     and (st["t"] or 0) >= MIN_T
                     and all((v["excess"] or 0) > 0 for v in per.values()))
            out.setdefault(check, {})[side] = {**st, "by_season": per, "holds": bool(holds)}
    return out


def measure(conn, sport: str = "nfl", seasons=None) -> dict:
    cases = history_cases(conn, sport, seasons)
    years = sorted({c["season"] for c in cases})
    if len(years) < 3:
        return {"sport": sport, "cases": len(cases), "seasons": years,
                "note": "fewer than three seasons of stored closes — nothing to hold out"}
    test = set(years[-2:])
    train = [c for c in cases if c["season"] not in test]
    held = [c for c in cases if c["season"] in test]
    f_train = fit(train)
    v = verdict(score(held, f_train))
    return {"sport": sport, "cases": len(cases), "seasons": years, "train": sorted(set(years) - test),
            "test": sorted(test), "fit_train": f_train, "fit_all": fit(cases), "verdict": v,
            "counts": {k: sum(1 for c in cases if c["check"] == k) for k in CHECKS}}


def save(result: dict) -> Path:
    path = _fit_path()
    try:
        d = json.loads(path.read_text())
    except (OSError, ValueError):
        d = {}
    d[result["sport"]] = {"fit": result.get("fit_all") or {}, "verdict": result.get("verdict") or {},
                          "seasons": result.get("seasons"), "test": result.get("test")}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(d, indent=1, sort_keys=True))
    return path


def report_lines(result: dict) -> list[str]:
    out = [f"Book menus — {result['sport'].upper()}: {result['cases']} stored menu(s), seasons {result.get('seasons')}"]
    if result.get("note"):
        return out + ["  " + result["note"]]
    out.append(f"  train {result['train']} · test {result['test']} · flag at |z| ≥ {FLAG_Z}")
    for check, n in result["counts"].items():
        out.append(f"  {check:10s} {n:6d} menus · normal by bucket: "
                   + (", ".join(f"{b}: x̃ {f['mu']:+.3f} ±{f['sd']:.3f} (n {f['n']})"
                                for b, f in sorted((result['fit_all'].get(check) or {}).items())) or "none fitted"))
    out.append(f"  THE BAR: excess ≥ {MIN_EXCESS:+.2f} over the fair chance, t ≥ {MIN_T}, ≥ {MIN_CASES} flagged "
               f"menus, above zero in each test season")
    for check, sides in result["verdict"].items():
        for side, s in sides.items():
            per = " · ".join(f"{k}: {v['excess']:+.3f} (n {v['n']})" for k, v in s["by_season"].items()
                             if v["excess"] is not None)
            out.append(f"  {check:10s} {side:6s} n {s['n']:5d} excess {s['excess'] if s['excess'] is not None else '—'}"
                       f" t {s['t'] if s['t'] is not None else '—'}  {'HOLDS' if s['holds'] else 'does not hold'}  [{per}]")
    if not result["verdict"]:
        out.append("  no held-out menu was flagged")
    return out


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Does a book's own menu add up? (measured on stored closes)")
    ap.add_argument("--sport", default="nfl")
    ap.add_argument("--save", action="store_true", help="write the fit and verdict for the builds to read")
    a = ap.parse_args(argv)
    from . import db as _db
    conn = _db.connect()
    try:
        res = measure(conn, a.sport)
    finally:
        conn.close()
    print("\n".join(report_lines(res)))
    if a.save and not res.get("note"):
        print(f"  saved → {save(res)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ---- the ideas file (engine/ideas) ------------------------------------------

def ideas_section(props, games, board, sport):
    """The slate's menus for the ideas file: every row, the summary, and
    whether the normal has been measured and the bar cleared."""
    rows = menus(props, games, sport)
    return {"rows": rows, "summary": summary(rows), "verdict": load_verdict(sport),
            "flag_z": FLAG_Z}


def pick_view(sec, player, market, side="", line=None):
    rows = for_player(sec.get("rows") or [], player)
    if not rows:
        return None
    rows = sorted(rows, key=lambda r: (r.get("lean") is None, -abs(r.get("z") or 0), r["check"], r["book"]))
    return {"rows": rows[:12], "summary": sec.get("summary"), "verdict": sec.get("verdict") or {},
            "flag_z": sec.get("flag_z", FLAG_Z)}


def game_view(sec, home, away):
    game = f"{away} @ {home}"
    rows = [r for r in sec.get("rows") or [] if r.get("game") == game]
    if not rows:
        return None
    flag = flagged(rows)
    if not flag:
        return None              # a game with nothing flagged has nothing to show
    return {"rows": flag[:12], "summary": summary(rows), "verdict": sec.get("verdict") or {},
            "flag_z": sec.get("flag_z", FLAG_Z)}
