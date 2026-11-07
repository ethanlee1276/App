"""A role change spotted early — Bayesian changepoint detection on each man's share of the work.

Ethan, 2026-10-16: "add everything now. 1-13" — idea 10. A player's role
does not drift; it jumps. A receiver moves into the slot, a back takes the
starting job, a tight end's snaps double when the man ahead of him goes on
injured reserve. The board reads volume as the average of his last four
weeks (`nflusage.VOL_WEEKS`), which takes four weeks to fully believe a
jump that happened in one, and keeps the old role in the number for three
games after the new one is plain.

ONLINE BAYESIAN CHANGEPOINT DETECTION (Adams & MacKay, 2007). For each
share series — his targets over his team's, his carries over his team's,
his snap share — the run-length posterior: after every game, the chance
his current role began 0, 1, 2 … games ago. Each candidate role is a
normal with unknown mean and spread (Normal-Gamma conjugate, so the
forecast is a Student t), and a new role starts with chance 1/HAZARD each
game. The forecast for next game is each candidate role's mean weighted
by its chance, so a role that changed two games ago is believed as soon
as the data say so, and not before.

THE BAR, WRITTEN BEFORE ITS FIRST RUN. Each player-season's next-game
share, forecast from the games before it (four at least), by the detector
and by the board's four-week average. The detector's two settings (how
often a role changes, how noisy a share is) are chosen from a fixed grid
on the training seasons only; the two newest seasons are scored by
absolute error, paired, averaged within each player-season first. Each
share earns a reading only if it beats the four-week average with t ≥
MIN_T over MIN_SERIES player-seasons and MIN_FORECASTS forecasts, and in
each test season. Until then the pick page shows his shares game by game,
where the detector puts the change and how sure it is, labelled; the
board's volume is unchanged.

Standard library only.
"""

from __future__ import annotations

import json
import math

#: share key -> (what it is, the log market on top, the team total it is a share of)
SHARES = {"tgt": ("Target share", "targets"), "car": ("Carry share", "carries"), "snap": ("Snap share", "snap_pct")}
#: The share each priced market rides on.
BY_MARKET = {"rec_yds": "tgt", "receptions": "tgt", "rush_yds": "car", "rush_att": "car", "rush_rec_yds": "car"}
BASELINE_WEEKS = 4
MIN_PRIOR = 4
MAX_RUN = 40
PRIOR_WEIGHT = 0.1
#: The grid the training seasons choose from (games between changes, a share's spread).
HAZARDS = (8.0, 15.0, 30.0)
SPREADS = (0.04, 0.07, 0.10)
DEFAULT = {"hazard": 15.0, "spread": 0.07}
#: "Changed" on the pick page: this sure that the role began within RECENT games.
RECENT = 3
FLAG_AT = 0.6
#: The bar.
MIN_T = 2.0
MIN_SERIES = 300
MIN_FORECASTS = 2000
STORE = "rolechange.json"


def _t_pdf(x, mu, scale, df):
    z = (x - mu) / scale
    return math.exp(math.lgamma((df + 1) / 2) - math.lgamma(df / 2) - 0.5 * math.log(df * math.pi)
                    - math.log(scale) - (df + 1) / 2 * math.log1p(z * z / df))


def detect(xs: list, hazard: float = DEFAULT["hazard"], spread: float = DEFAULT["spread"], prior_mean=None) -> dict:
    """Run the detector over a share series. Returns the forecast made
    BEFORE each game (None before the first), and after the last game the
    run-length posterior: ``run[i]`` = chance the current role holds the
    last i+1 games."""
    h = 1.0 / hazard
    # The prior a new role starts from: centred on his first game (never a
    # later one, so no game reaches a forecast made before it) and worth a
    # tenth of a game, so a new role is read off its own games.
    mu0 = (xs[0] if xs else 0.0) if prior_mean is None else prior_mean
    k0, a0 = PRIOR_WEIGHT, 2.0
    b0 = a0 * spread * spread
    run = [1.0]
    mus, ks, as_, bs = [mu0], [k0], [a0], [b0]
    forecasts = []
    started = False
    for x in xs:
        forecasts.append(sum(r * m for r, m in zip(run, mus)) if started else None)
        pred = [_t_pdf(x, m, math.sqrt(b * (k + 1) / (a * k)), 2 * a) for m, k, a, b in zip(mus, ks, as_, bs)]
        grow = [r * p * (1 - h) for r, p in zip(run, pred)]
        # A role that begins with this game is judged on what a new role
        # would predict for it (the prior's forecast), not the old one's.
        cp = h * _t_pdf(x, mu0, math.sqrt(b0 * (k0 + 1) / (a0 * k0)), 2 * a0)
        new = [cp] + grow
        tot = sum(new) or 1.0
        run = [v / tot for v in new]
        # every run, including the one that starts now, absorbs x
        prev = list(zip([mu0] + mus, [k0] + ks, [a0] + as_, [b0] + bs))
        mus, ks, as_, bs = [], [], [], []
        for m, k, a, b in prev:
            mus.append((k * m + x) / (k + 1))
            ks.append(k + 1)
            as_.append(a + 0.5)
            bs.append(b + k * (x - m) ** 2 / (2 * (k + 1)))
        if len(run) > MAX_RUN:
            run[MAX_RUN - 1] += sum(run[MAX_RUN:])
            run, mus, ks, as_, bs = run[:MAX_RUN], mus[:MAX_RUN], ks[:MAX_RUN], as_[:MAX_RUN], bs[:MAX_RUN]
        started = True
    nxt = sum(r * m for r, m in zip(run, mus)) if started else None
    return {"forecasts": forecasts, "next": nxt, "run": run, "means": mus}


def summary(xs: list, settings: dict | None = None) -> dict | None:
    """What the pick page says: how sure the detector is that his role
    began within the last RECENT games, where (the likeliest start), his
    share before and since, and the forecast beside the four-week average."""
    if len(xs) < MIN_PRIOR:
        return None
    s = {**DEFAULT, **(settings or {})}
    d = detect(xs, s["hazard"], s["spread"])
    n = len(xs)
    recent = sum(p for i, p in enumerate(d["run"]) if i + 1 <= RECENT and i + 1 < n)
    best = max(range(len(d["run"])), key=lambda i: d["run"][i])
    since = best + 1
    out = {"changed": round(recent, 3), "flag": recent >= FLAG_AT, "forecast": round(d["next"], 4),
           "four_week": round(sum(xs[-BASELINE_WEEKS:]) / len(xs[-BASELINE_WEEKS:]), 4)}
    if since < n:
        out.update({"games_ago": since, "before": round(sum(xs[:-since]) / (n - since), 4),
                    "after": round(sum(xs[-since:]) / since, 4)})
    return out


# ---- the held-out test ----------------------------------------------------------------

def series_from(rows) -> dict:
    """rows: (season, week, team, player, market, value) → ``{(key,
    season, player): [(week, share)]}``: targets and carries over his team's
    that week, snap share as stored."""
    tot: dict = {}
    mine: dict = {}
    for season, week, team, player, market, value in rows:
        if value is None:
            continue
        mine.setdefault((season, player), {}).setdefault(week, {})[market] = (team, float(value))
        if market in ("targets", "carries"):
            tot[(season, week, team, market)] = tot.get((season, week, team, market), 0.0) + float(value)
    out: dict = {}
    for (season, player), weeks in mine.items():
        for key, (_name, market) in SHARES.items():
            pts = []
            for week in sorted(weeks):
                got = weeks[week].get(market)
                if got is None:
                    continue
                team, v = got
                if market == "snap_pct":
                    pts.append((week, v))
                else:
                    t = tot.get((season, week, team, market))
                    if t:
                        pts.append((week, v / t))
            if pts:
                out[(key, season, player)] = pts
    return out


def errors(series: dict, key: str, seasons, settings: dict) -> list:
    """[(season, series id, |detector − actual|, |four-week − actual|)]."""
    out = []
    for (k, season, player), pts in series.items():
        if k != key or season not in seasons or len(pts) <= MIN_PRIOR:
            continue
        xs = [v for _w, v in pts]
        d = detect(xs, settings["hazard"], settings["spread"])
        for i in range(MIN_PRIOR, len(xs)):
            base = sum(xs[i - BASELINE_WEEKS:i]) / BASELINE_WEEKS
            out.append((season, f"{player}|{season}", abs(d["forecasts"][i] - xs[i]), abs(base - xs[i])))
    return out


def choose(series: dict, key: str, train) -> dict:
    """The grid point with the lowest mean absolute error on the training seasons."""
    best, best_err = dict(DEFAULT), None
    for hz in HAZARDS:
        for sp in SPREADS:
            e = errors(series, key, train, {"hazard": hz, "spread": sp})
            if not e:
                continue
            m = sum(x[2] for x in e) / len(e)
            if best_err is None or m < best_err:
                best, best_err = {"hazard": hz, "spread": sp}, m
    return best


def verdict(errs: list) -> dict:
    by: dict = {}
    for season, sid, det, base in errs:
        by.setdefault(sid, (season, []))[1].append(base - det)
    g = [sum(v) / len(v) for _s, v in by.values()]
    n = len(g)
    if n < 2:
        return {"series": n, "forecasts": len(errs), "gain": None, "t": None, "holds": False}
    m = sum(g) / n
    var = sum((x - m) ** 2 for x in g) / (n - 1)
    t = m / math.sqrt(var / n) if var > 0 else None
    seasons = sorted({s for s, _v in by.values()})
    per = {}
    for s in seasons:
        sub = [sum(v) / len(v) for ss, v in by.values() if ss == s]
        per[str(s)] = round(sum(sub) / len(sub), 5)
    holds = (n >= MIN_SERIES and len(errs) >= MIN_FORECASTS and m > 0 and (t or 0) >= MIN_T
             and len(seasons) >= 2 and all(v > 0 for v in per.values()))
    return {"series": n, "forecasts": len(errs), "gain": round(m, 5), "t": None if t is None else round(t, 2),
            "by_season": per, "holds": bool(holds)}


# ---- storage, the box, the ideas file -------------------------------------------------

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


def load_rows(conn, sport: str, seasons=None) -> list:
    markets = ("targets", "carries", "snap_pct")
    q = ("SELECT season, period, team, player, market, value FROM player_game_logs WHERE sport=? AND market IN (?,?,?)")
    args = [sport, *markets]
    if seasons:
        q += " AND season IN (%s)" % ",".join("?" * len(seasons))
        args += list(seasons)
    out = []
    for r in conn.execute(q, args):
        try:
            out.append((int(r[0]), int(r[1]), r[2], r[3], r[4], r[5]))
        except (TypeError, ValueError):
            continue
    return out


def measure(conn, sport: str = "nfl") -> dict:
    series = series_from(load_rows(conn, sport))
    seasons = sorted({s for (_k, s, _p) in series})
    if len(seasons) < 3:
        return {"note": "fewer than three seasons of logs"}
    test, train = set(seasons[-2:]), set(seasons[:-2])
    res = {"test": sorted(test), "train": sorted(train), "shares": {}}
    for key in SHARES:
        settings = choose(series, key, train)
        res["shares"][key] = {"settings": settings, "verdict": verdict(errors(series, key, test, settings))}
    return res


def ideas_section(props, games, board, sport, conn=None):
    if sport != "nfl":
        return None
    rows = [r for r in (board or {}).get("recommendations") or [] if r.get("player")]
    if not rows:
        return {"players": {}}
    saved = load()
    own = conn is None
    if own:
        from . import db as _db
        conn = _db.connect()
    import sqlite3
    try:
        try:
            latest = conn.execute("SELECT MAX(season) FROM player_game_logs WHERE sport=? AND market='targets'",
                                  (sport,)).fetchone()[0]
        except sqlite3.OperationalError:
            latest = None                                     # a database with no logs table reads empty
        if latest is None:
            return {"players": {}}
        series = series_from(load_rows(conn, sport, (int(latest),)))
    finally:
        if own:
            conn.close()
    out = {}
    for r in rows:
        name = r["player"]
        if name in out:
            continue
        reads = {}
        for key in SHARES:
            pts = series.get((key, int(latest), name))
            if not pts:
                continue
            sh = (saved.get("shares") or {}).get(key) or {}
            s = summary([v for _w, v in pts], sh.get("settings"))
            if s:
                reads[key] = {**s, "weeks": [w for w, _v in pts], "values": [round(v, 4) for _w, v in pts],
                              "verdict": sh.get("verdict") or {}}
        if reads:
            out[name] = {"team": r.get("team"), "opponent": r.get("opponent"), "reads": reads}
    return {"players": out}


def pick_view(sec, player, market, side="", line=None):
    p = (sec.get("players") or {}).get(player)
    if not p:
        return None
    lead = BY_MARKET.get(market) or "snap"
    order = [lead] + [k for k in ("snap", "tgt", "car") if k != lead]
    return {"lead": lead, "reads": {k: p["reads"][k] for k in order if k in p["reads"]}}


def game_view(sec, home, away):
    flagged = []
    for name, p in (sec.get("players") or {}).items():
        if {p.get("team"), p.get("opponent")} != {home, away}:
            continue
        for key, rd in p["reads"].items():
            if rd.get("flag") and rd.get("games_ago"):
                flagged.append({"player": name, "team": p.get("team"), "share": key, "label": SHARES[key][0],
                                "before": rd.get("before"), "after": rd.get("after"), "games_ago": rd["games_ago"],
                                "changed": rd["changed"]})
    flagged.sort(key=lambda x: -x["changed"])
    return {"rows": flagged[:10]} if flagged else None


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Role changes spotted by Bayesian changepoint detection, against the four-week average")
    ap.add_argument("--save", action="store_true", help="keep the chosen settings and the verdicts for the pick page")
    a = ap.parse_args(argv)
    from . import db as _db
    conn = _db.connect()
    try:
        res = measure(conn, "nfl")
    finally:
        conn.close()
    print("Role changes — the detector against the board's four-week average")
    if res.get("note"):
        print(f"  {res['note']}")
        return 0
    print(f"  settings chosen on {res['train']}, scored on {res['test']}")
    for key, r in res["shares"].items():
        v, s = r["verdict"], r["settings"]
        print(f"  {SHARES[key][0]}: a role lasts ~{s['hazard']:.0f} games, a share's spread {s['spread']}")
        print(f"    {v['forecasts']} forecasts over {v['series']} player-seasons: closer by {v['gain']} a game "
              f"(t {v['t']}), by season {v.get('by_season')} — {'HOLDS' if v['holds'] else 'does not hold'}")
    print(f"  THE BAR: closer than the four-week average, t ≥ {MIN_T}, ≥ {MIN_SERIES} player-seasons and "
          f"{MIN_FORECASTS} forecasts, each test season above zero")
    if a.save:
        print(f"  saved → {save(res)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
