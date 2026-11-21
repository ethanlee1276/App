"""Rookies and transfers, translated from our own college data.

Ethan, 2026-10-16: "add everything now. 1-13" — idea 8. A rookie's first
NFL month is priced off almost nothing: a handful of pro games, or none,
shrunk toward his position. But the box holds his whole college career
(the college board's own logs), and the draft says how highly the league
rated him. Those two numbers are a projection the thin-history shrink
throws away.

THE ROOKIE TRANSLATOR, per market (receiving yards, catches, rushing
yards), one least-squares fit:

    his NFL per-game in weeks 1-4  ~  a + b · his last college season's per-game
                                       + c · log(where he was drafted)

on every rookie class the box can read (nflverse rosters name each man's
rookie year, draft slot and college). An undrafted man is pick 260.

THE TRANSFER TABLE, for college: a player whose school changed between
seasons, his first four games at the new school against his last season
at the old one, per market. How much of a transfer's production comes
with him is a ratio, measured.

THE BAR, WRITTEN BEFORE ITS FIRST RUN. Rookies: fitted on every class but
the last two, scored on those two by absolute error against two simpler
guesses — draft slot alone, and the position's rookie mean. The translator
earns a reading only if it beats both, paired, with t ≥ MIN_T over at
least MIN_ROOKIES rookie-markets. Until then the pick page shows his
college line and the translation and says it is not yet measured; nothing
on the board reads it.

Standard library only.
"""

from __future__ import annotations

import json
import math

MARKETS = ("rec_yds", "receptions", "rush_yds")
POSITIONS = ("WR", "TE", "RB")
UNDRAFTED = 260
#: College games a last season needs; NFL games a first month needs.
MIN_COLLEGE_GAMES = 6
MIN_NFL_GAMES = 2
FIRST_WEEKS = 4
#: The bar.
MIN_T = 2.0
MIN_ROOKIES = 60
STORE = "rookies.json"


def _norm(name):
    from .backtest import _norm as n
    return n(name)


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def college_lines(conn, season: int, market: str) -> dict:
    """``{norm name: (school, per-game, games)}`` for one college season —
    names that two schools share are left out rather than guessed."""
    acc: dict = {}
    for r in conn.execute("SELECT player, team, value FROM player_game_logs WHERE sport='cfb' AND season=? "
                          "AND market=? AND value IS NOT NULL", (season, market)):
        acc.setdefault(_norm(r[0]), {}).setdefault(r[1], []).append(float(r[2]))
    out = {}
    for name, by_team in acc.items():
        if len(by_team) != 1:
            continue
        team, vals = next(iter(by_team.items()))
        if len(vals) >= MIN_COLLEGE_GAMES:
            out[name] = (team, sum(vals) / len(vals), len(vals))
    return out


def nfl_first_month(conn, season: int, market: str) -> dict:
    """``{norm name: (per-game, games)}`` over weeks 1-4 of an NFL season."""
    acc: dict = {}
    for r in conn.execute("SELECT player, period, value FROM player_game_logs WHERE sport='nfl' AND season=? "
                          "AND market=? AND value IS NOT NULL", (season, market)):
        try:
            if int(r[1]) <= FIRST_WEEKS:
                acc.setdefault(_norm(r[0]), []).append(float(r[2]))
        except (TypeError, ValueError):
            continue
    return {n: (sum(v) / len(v), len(v)) for n, v in acc.items() if len(v) >= MIN_NFL_GAMES}


def rookie_rows(roster: list) -> list:
    """The rookies on an nflverse roster: [(norm name, name, position, pick,
    college)], one row a man even when a trade lists him twice."""
    out, seen = [], set()
    for r in roster:
        try:
            season = int(r.get("season") or 0)
            rookie = int(r.get("rookie_year") or r.get("entry_year") or 0)
        except (TypeError, ValueError):
            continue
        pos = str(r.get("position") or "").upper()
        if not season or rookie != season or pos not in POSITIONS:
            continue
        name = r.get("full_name") or r.get("player_name") or ""
        try:
            pick = int(float(r.get("draft_number"))) if r.get("draft_number") not in (None, "", "NA") else UNDRAFTED
        except (TypeError, ValueError):
            pick = UNDRAFTED
        if not name or _norm(name) in seen:
            continue
        seen.add(_norm(name))
        out.append((_norm(name), name, pos, pick, r.get("college") or ""))
    return out


def examples(conn, rosters: dict, market: str) -> list:
    """``rosters``: {NFL season: roster rows}. → [(season, pos, pick,
    college per-game, NFL first-month per-game)]."""
    out = []
    for season, roster in sorted(rosters.items()):
        col = college_lines(conn, season - 1, market)
        pro = nfl_first_month(conn, season, market)
        for key, _name, pos, pick, _college in rookie_rows(roster):
            if key in col and key in pro:
                out.append((season, pos, pick, col[key][1], pro[key][0]))
    return out


def _solve(a, b):
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


def _ols(xs, ys):
    k = len(xs[0])
    ata = [[sum(x[i] * x[j] for x in xs) for j in range(k)] for i in range(k)]
    aty = [sum(x[i] * y for x, y in zip(xs, ys)) for i in range(k)]
    return _solve(ata, aty)


def fit(rows) -> dict | None:
    """The translator [a, b, c] and the two simpler guesses: draft slot
    alone, and each position's rookie mean."""
    if len(rows) < 10:
        return None
    full = _ols([[1.0, r[3], math.log(r[2])] for r in rows], [r[4] for r in rows])
    slot = _ols([[1.0, math.log(r[2])] for r in rows], [r[4] for r in rows])
    pos: dict = {}
    for r in rows:
        pos.setdefault(r[1], []).append(r[4])
    if full is None or slot is None:
        return None
    return {"w": [round(x, 5) for x in full], "slot": [round(x, 5) for x in slot],
            "pos_mean": {p: round(sum(v) / len(v), 3) for p, v in pos.items()}, "n": len(rows)}


def translate(model: dict, college_pg: float, pick: int) -> float | None:
    if not model:
        return None
    a, b, c = model["w"]
    return max(0.0, a + b * float(college_pg) + c * math.log(max(1, int(pick))))


def held_out(rows) -> dict:
    seasons = sorted({r[0] for r in rows})
    if len(seasons) < 3:
        return {"n": 0, "holds": False, "note": "fewer than three rookie classes"}
    test = set(seasons[-2:])
    m = fit([r for r in rows if r[0] not in test])
    if not m:
        return {"n": 0, "holds": False, "note": "too few rookies to fit"}
    d_slot, d_pos = [], []
    for _season, pos, pick, col, actual in (r for r in rows if r[0] in test):
        e_t = abs(translate(m, col, pick) - actual)
        e_s = abs(max(0.0, m["slot"][0] + m["slot"][1] * math.log(pick)) - actual)
        e_p = abs(m["pos_mean"].get(pos, actual) - actual)
        d_slot.append(e_s - e_t)
        d_pos.append(e_p - e_t)

    def st(xs):
        n = len(xs)
        if n < 2:
            return {"n": n, "gain": None, "t": None}
        mu = sum(xs) / n
        var = sum((x - mu) ** 2 for x in xs) / (n - 1)
        return {"n": n, "gain": round(mu, 3), "t": round(mu / math.sqrt(var / n), 2) if var > 0 else None}
    a, b = st(d_slot), st(d_pos)
    holds = all(s["n"] >= MIN_ROOKIES and (s["gain"] or 0) > 0 and (s["t"] or 0) >= MIN_T for s in (a, b))
    return {"n": a["n"], "test": sorted(test), "vs_slot": a, "vs_position": b, "holds": bool(holds)}


# ---- transfers (college) ---------------------------------------------------------------

def transfer_ratios(conn, season: int, market: str) -> list:
    """Every player whose school changed into `season`: (old per-game,
    new first-four per-game)."""
    old = college_lines(conn, season - 1, market)
    new: dict = {}
    for r in conn.execute("SELECT player, team, period, value FROM player_game_logs WHERE sport='cfb' AND season=? "
                          "AND market=? AND value IS NOT NULL ORDER BY period", (season, market)):
        new.setdefault(_norm(r[0]), {}).setdefault(r[1], []).append(float(r[3]))
    out = []
    for name, by_team in new.items():
        if name not in old or len(by_team) != 1:
            continue
        team, vals = next(iter(by_team.items()))
        if team == old[name][0] or len(vals) < MIN_NFL_GAMES:
            continue
        out.append((old[name][1], sum(vals[:FIRST_WEEKS]) / len(vals[:FIRST_WEEKS])))
    return out


def transfer_table(pairs) -> dict | None:
    """How much a transfer keeps: the ratio of sums (robust to a zero
    season), and the count."""
    olds = sum(o for o, _n in pairs)
    if len(pairs) < 10 or olds <= 0:
        return None
    return {"keep": round(sum(n for _o, n in pairs) / olds, 3), "n": len(pairs)}


# ---- storage, the box, the ideas file ----------------------------------------------------

def save(res: dict) -> str:
    from . import modelstate
    import os
    p = modelstate.path(STORE)
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w") as fh:
        json.dump(res, fh, indent=1)
    return p


def load() -> dict:
    from . import modelstate
    try:
        with open(modelstate.path(STORE)) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def measure(conn, seasons) -> dict:
    from .sources.nflverse import load_rosters
    rosters = {}
    for s in seasons:
        try:
            rosters[s] = [{**r, "season": r.get("season") or s} for r in load_rosters(s)]
        except Exception as exc:                              # noqa: BLE001
            print(f"  ⚠️  {s} roster unavailable: {exc}")
    res = {"rookies": {}, "transfers": {}}
    for m in MARKETS:
        rows = examples(conn, rosters, m)
        res["rookies"][m] = {"fit": fit(rows), "held_out": held_out(rows), "examples": len(rows)}
        pairs = []
        for s in seasons:
            pairs += transfer_ratios(conn, s, m)
        res["transfers"][m] = transfer_table(pairs)
    return res


def ideas_section(props, games, board, sport):
    saved = load()
    if not saved:
        return {"rows": {}, "measured": False}
    rows = {}
    if sport == "nfl":
        rk = saved.get("rookie_index") or {}
        for row in (board or {}).get("recommendations") or []:
            info = rk.get(_norm(row.get("player") or ""))
            m = ((saved.get("rookies") or {}).get(row.get("market")) or {})
            if not info or not m.get("fit") or row.get("market") not in MARKETS:
                continue
            col = (info.get("college") or {}).get(row["market"])
            if not col:
                continue
            rows[f"{row['player']}|{row['market']}"] = {
                "kind": "rookie", "school": col["school"], "college_pg": col["pg"], "college_games": col["games"],
                "pick": info.get("pick"), "translated": round(translate(m["fit"], col["pg"], info.get("pick") or UNDRAFTED), 1),
                "held_out": m.get("held_out") or {}}
    elif sport == "cfb":
        tr = saved.get("transfer_index") or {}
        for row in (board or {}).get("recommendations") or []:
            info = tr.get(_norm(row.get("player") or ""))
            t = ((saved.get("transfers") or {}).get(row.get("market")) or {})
            if not info or not t or row.get("market") not in MARKETS:
                continue
            old = (info.get("old") or {}).get(row["market"])
            if not old:
                continue
            rows[f"{row['player']}|{row['market']}"] = {
                "kind": "transfer", "school": old["school"], "college_pg": old["pg"], "college_games": old["games"],
                "keep": t["keep"], "keep_n": t["n"], "translated": round(old["pg"] * t["keep"], 1)}
    return {"rows": rows, "measured": True}


def pick_view(sec, player, market, side="", line=None):
    return (sec.get("rows") or {}).get(f"{player}|{market}")


def game_view(sec, home, away):
    return None


def indexes(conn, nfl_season: int, roster: list, cfb_season: int) -> dict:
    """What the builds look up: this season's NFL rookies with their last
    college line, and this college season's transfers with their old one."""
    rk = {}
    last = {m: college_lines(conn, nfl_season - 1, m) for m in MARKETS}
    for key, name, pos, pick, _college in rookie_rows([{**r, "season": r.get("season") or nfl_season} for r in roster]):
        lines = {m: last[m][key] for m in MARKETS if key in last[m]}
        lines = {m: {"school": v[0], "pg": round(v[1], 1), "games": v[2]} for m, v in lines.items()}
        if lines:
            rk[key] = {"name": name, "pos": pos, "pick": pick, "college": lines}
    tr = {}
    for m in MARKETS:
        old = college_lines(conn, cfb_season - 1, m)
        now = {}
        for r in conn.execute("SELECT player, team FROM player_game_logs WHERE sport='cfb' AND season=? AND market=?",
                              (cfb_season, m)):
            now.setdefault(_norm(r[0]), set()).add(r[1])
        for key, teams in now.items():
            if key in old and len(teams) == 1 and old[key][0] not in teams:
                tr.setdefault(key, {"old": {}})["old"][m] = {"school": old[key][0], "pg": round(old[key][1], 1),
                                                              "games": old[key][2]}
    return {"rookie_index": rk, "transfer_index": tr}


def main(argv=None) -> int:
    import argparse
    import datetime as _dt
    ap = argparse.ArgumentParser(description="Rookies from their college line and draft slot; transfers' carryover")
    ap.add_argument("--seasons", type=int, nargs="*", help="NFL rookie classes to read (default: the last six, this season included)")
    ap.add_argument("--save", action="store_true", help="keep the fits and this season's lookups for the pick page")
    a = ap.parse_args(argv)
    year = _dt.date.today().year
    seasons = a.seasons or list(range(year - 5, year + 1))
    from . import db as _db
    from .sources.nflverse import load_rosters
    conn = _db.connect()
    try:
        res = measure(conn, seasons)
        try:
            res.update(indexes(conn, year, load_rosters(year), year))
        except Exception as exc:                              # noqa: BLE001
            print(f"  ⚠️  this season's lookups unavailable: {exc}")
    finally:
        conn.close()
    print(f"Rookies and transfers, rookie classes {seasons}")
    for m, r in res["rookies"].items():
        h, f = r["held_out"], r["fit"] or {}
        print(f"  {m}: {r['examples']} rookies with a college line and a first month; "
              f"fit {f.get('w')} (a, college per-game, log pick)")
        if h.get("n"):
            print(f"    held out {h['test']}: beats draft slot by {h['vs_slot']['gain']} (t {h['vs_slot']['t']}), "
                  f"beats the position mean by {h['vs_position']['gain']} (t {h['vs_position']['t']}), n {h['n']} — "
                  f"{'HOLDS' if h['holds'] else 'does not hold'}")
        else:
            print(f"    {h.get('note')}")
        t = res["transfers"].get(m)
        print(f"    transfers keep {t['keep']:.0%} in their first four games (n {t['n']})" if t else "    transfers: too few")
    print(f"  THE BAR: the translator beats draft slot AND the position mean, paired, t ≥ {MIN_T}, ≥ {MIN_ROOKIES} rookies")
    print(f"  this season: {len(res.get('rookie_index') or {})} rookies, {len(res.get('transfer_index') or {})} transfers indexed")
    if a.save:
        print(f"  saved → {save(res)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
