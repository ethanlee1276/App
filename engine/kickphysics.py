"""Kick physics — the air a field goal flies through, not just the wind speed.

Ethan, 2026-10-16: "add everything now. 1-13" — idea 7. A kicked ball is
slowed by drag, and drag is proportional to the density of the air. Air
is thinner when it is warm and when it is high: Denver's mile is the
famous case, but a 90-degree September afternoon thins the air too, and a
20-degree December night thickens it. Every weather read on the board
today uses wind speed alone; none of them knows how thick the air is.

THE PHYSICS. Air density from the ideal gas law: pressure from the
stadium's altitude (the standard atmosphere) or a measured pressure when
one is given, temperature from the game-time forecast, and water vapour
when the humidity is known (moist air is lighter). Sea level at 59°F is
1.225 kg/m³; Denver on a 70°F day is about 0.98, a fifth thinner.

THE WIND, ALONG THE FIELD. A wind's speed says little until you know its
angle to the uprights: ten miles an hour straight down the field helps one
end and hurts the other; across it, it pushes the ball sideways. That needs
each stadium's bearing (the compass direction of its long axis), which is a
fact about a building and has to come from a source, so the table starts
empty and is filled one stadium at a time with `--bearing TEAM DEGREES
--source URL`. Until a stadium has one, its wind is a speed and nothing
more.

THE MEASUREMENT, WRITTEN BEFORE ITS FIRST RUN. Every field goal the box
holds (`kicks`), the make chance fitted by logistic regression on distance
(and distance squared, and wind × distance outdoors), with and without one
more term: distance × the air's density against sea level. Fitted on every
season but the last two, scored on those two by log loss, kick by kick. The
density term earns a place only if it improves the held-out log loss with
t ≥ MIN_T over at least MIN_KICKS kicks AND its sign is the physics' (denser
air, fewer makes). If it holds, the pick page says what a 50-yard try plays
like tonight; until then it shows the air and the wind and says the effect
is not yet measured. Nothing on the board reads it either way without
Ethan's yes.

Standard library only.
"""

from __future__ import annotations

import json
import math

R_DRY = 287.05          # J/(kg·K), dry air
R_VAP = 461.495         # J/(kg·K), water vapour
RHO_SEA = 1.225         # kg/m³ at sea level, 15 °C (59 °F), dry
COMPASS = {d: i * 22.5 for i, d in enumerate(
    ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"))}
#: Indoors the air is the building's: a dome is kept near this.
DOME_F = 70.0
#: The bar.
MIN_T = 2.0
MIN_KICKS = 2000
STORE = "kickphysics.json"
BEARINGS_STORE = "stadium_bearings.json"


def pressure_pa(altitude_ft: float) -> float:
    """The standard atmosphere's pressure at an altitude."""
    h = max(0.0, float(altitude_ft or 0)) * 0.3048
    return 101325.0 * (1.0 - 2.25577e-5 * h) ** 5.25588


def air_density(temp_f, altitude_ft=0.0, humidity=None, pressure_hpa=None) -> float | None:
    """kg/m³. ``humidity`` is relative humidity 0-1 (or 0-100); vapour
    pressure from the Tetens formula. None without a temperature."""
    try:
        tf = float(temp_f)
    except (TypeError, ValueError):
        return None
    tc = (tf - 32.0) * 5.0 / 9.0
    t = tc + 273.15
    p = float(pressure_hpa) * 100.0 if pressure_hpa else pressure_pa(altitude_ft)
    rh = None
    if humidity is not None:
        try:
            rh = float(humidity)
            rh = rh / 100.0 if rh > 1.0 else rh
        except (TypeError, ValueError):
            rh = None
    if rh:
        es = 610.78 * 10 ** (7.5 * tc / (tc + 237.3))
        pv = rh * es
        return (p - pv) / (R_DRY * t) + pv / (R_VAP * t)
    return p / (R_DRY * t)


def density_dev(rho) -> float | None:
    """The air against sea level, as a fraction (−0.2 is a fifth thinner)."""
    return None if rho is None else rho / RHO_SEA - 1.0


def wind_parts(speed, direction, bearing):
    """A wind's component along the field (toward the end the bearing
    points at: positive pushes a kick toward that end) and across it.
    ``direction`` is where the wind blows FROM, compass or degrees; the
    wind blows toward direction + 180. None without all three."""
    try:
        s = float(speed)
        b = float(bearing)
    except (TypeError, ValueError):
        return None
    if isinstance(direction, str):
        d = COMPASS.get(direction.strip().upper())
    else:
        d = direction
    if d is None:
        return None
    toward = (float(d) + 180.0) % 360.0
    ang = math.radians(toward - b)
    return {"along": round(s * math.cos(ang), 1), "across": round(abs(s * math.sin(ang)), 1)}


# ---- the fit -------------------------------------------------------------------------

def _sig(z):
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))


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


def logistic(xs: list, ys: list, iters: int = 25, ridge: float = 1e-6) -> list | None:
    """Newton–Raphson on the log likelihood; a whisper of ridge keeps the
    Hessian invertible when a column is all zeros (no wind indoors)."""
    k = len(xs[0])
    w = [0.0] * k
    for _ in range(iters):
        g = [0.0] * k
        h = [[0.0] * k for _ in range(k)]
        for x, y in zip(xs, ys):
            p = _sig(sum(a * b for a, b in zip(w, x)))
            for i in range(k):
                g[i] += (y - p) * x[i]
                for j in range(k):
                    h[i][j] += p * (1 - p) * x[i] * x[j]
        for i in range(k):
            h[i][i] += ridge * len(xs)
            g[i] -= ridge * len(xs) * w[i]
        step = _solve(h, g)
        if step is None:
            return None
        w = [a + b for a, b in zip(w, step)]
        if max(abs(s) for s in step) < 1e-8:
            break
    return w


def features(k: dict, with_density: bool) -> list:
    """[1, d/10, (d/10)², wind×d/100 outdoors, (density dev × d/10)]."""
    d = float(k["distance"]) / 10.0
    wind = float(k.get("wind") or 0.0) if k.get("outdoors") else 0.0
    x = [1.0, d, d * d, wind * d / 10.0]
    if with_density:
        x.append((k.get("dens_dev") or 0.0) * d)
    return x


def prob(w: list, k: dict) -> float:
    return _sig(sum(a * b for a, b in zip(w, features(k, len(w) == 5))))


def _ll(p, y):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return -(math.log(p) if y else math.log(1 - p))


def held_seasons(kicks: list, seasons: list) -> set:
    """The newest seasons, as many as it takes to score MIN_KICKS kicks,
    always leaving at least two seasons to fit on (and never fewer than the
    newest two held out). A season holds about a thousand field goals, so
    the newest two — one of them in progress — could not reach the bar's
    count until December (box run, 2026-10-17: 1,467 kicks in all)."""
    per = {s: 0 for s in seasons}
    for k in kicks:
        per[k["season"]] += 1
    test: list = []
    for s in reversed(seasons):
        if len(seasons) - len(test) <= 2:
            break
        test.append(s)
        if len(test) >= 2 and sum(per[x] for x in test) >= MIN_KICKS:
            break
    return set(test)


def held_out(kicks: list) -> dict:
    seasons = sorted({k["season"] for k in kicks})
    if len(seasons) < 3:
        return {"n": 0, "gain": None, "t": None, "holds": False, "note": "fewer than three seasons"}
    test = held_seasons(kicks, seasons)
    tr = [k for k in kicks if k["season"] not in test]
    te = [k for k in kicks if k["season"] in test]
    base = logistic([features(k, False) for k in tr], [k["made"] for k in tr])
    full = logistic([features(k, True) for k in tr], [k["made"] for k in tr])
    if base is None or full is None:
        return {"n": 0, "gain": None, "t": None, "holds": False, "note": "the fit did not converge"}
    diffs = [_ll(prob(base, k), k["made"]) - _ll(prob(full, k), k["made"]) for k in te]
    n = len(diffs)
    m = sum(diffs) / n if n else 0.0
    var = sum((x - m) ** 2 for x in diffs) / (n - 1) if n > 1 else 0.0
    t = m / math.sqrt(var / n) if var > 0 else None
    sign_ok = full[4] < 0
    devs = [k["dens_dev"] for k in kicks if k.get("dens_dev") is not None]
    return {"n": n, "gain": round(m, 6), "t": None if t is None else round(t, 2), "test": sorted(test),
            # The air the league's kicks usually fly through — what a
            # kicker's own average was built in (engine/ideagate.kick_factor).
            "mean_dev": round(sum(devs) / len(devs), 4) if devs else 0.0,
            "density_coef": round(full[4], 4), "distance_coef": round(full[1], 4), "sign_ok": sign_ok,
            "holds": bool(n >= MIN_KICKS and m > 0 and (t or 0) >= MIN_T and sign_ok),
            "base": [round(x, 5) for x in base], "full": [round(x, 5) for x in full]}


def plays_like(fit: dict, distance: float, dens_dev: float) -> float | None:
    """The distance at sea-level air with the same make chance — only from
    a fit that held. With logit = … + b·d + c·dev·d (d in tens of yards),
    the same logit at dev 0 is reached at d·(1 + c·dev / b) to first order."""
    if not fit or not fit.get("holds"):
        return None
    b, c = fit["distance_coef"], fit["density_coef"]
    if not b:
        return None
    return round(distance * (1.0 + c * dens_dev / b), 1)


# ---- every stored field goal (the box) -----------------------------------------------

def _altitude(team: str) -> float:
    from .stadiums import STADIUMS
    s = STADIUMS.get(str(team or "").upper())
    return float(s.altitude_ft) if s else 0.0


def load_kicks(conn, sport: str = "nfl") -> list:
    """Every field goal with the air it flew through: [{season, distance,
    made, outdoors, wind, dens_dev}]. Indoors the building's air (DOME_F)."""
    out = []
    for r in conn.execute("SELECT season, game_id, distance, result, roof, temp, wind FROM kicks "
                          "WHERE sport=? AND kind='fg' AND distance IS NOT NULL", (sport,)):
        res = str(r[3] or "").lower()
        if res not in ("made", "missed", "blocked"):
            continue
        home = str(r[1] or "").split("@")[-1]
        outdoors = str(r[4] or "").lower() in ("outdoors", "open")
        temp = r[5] if (outdoors and r[5] is not None) else DOME_F
        rho = air_density(temp, _altitude(home))
        out.append({"season": int(r[0]), "distance": int(r[2]), "made": int(res == "made"),
                    "outdoors": outdoors, "wind": float(r[6] or 0.0) if outdoors else 0.0,
                    "dens_dev": density_dev(rho)})
    return out


def save(res: dict, sport: str = "nfl") -> str:
    from . import modelstate
    import os
    p = modelstate.path(STORE)
    try:
        with open(p) as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        d = {}
    d[sport] = res
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w") as fh:
        json.dump(d, fh, indent=1)
    return p


def load(sport: str = "nfl") -> dict:
    from . import modelstate
    try:
        with open(modelstate.path(STORE)) as fh:
            return json.load(fh).get(sport) or {}
    except (OSError, ValueError):
        return {}


def bearings() -> dict:
    """``{TEAM: {"deg", "source"}}`` — only stadiums someone recorded."""
    from . import modelstate
    try:
        with open(modelstate.path(BEARINGS_STORE)) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def set_bearing(team: str, deg: float, source: str) -> str:
    """Record a stadium's bearing — the compass direction its field's long
    axis points, toward either end (0-180; the other end is +180). A
    source is required: a bearing is a fact about a building."""
    from . import modelstate
    import os
    if not str(source or "").startswith(("http://", "https://")):
        raise ValueError("a bearing needs a source link")
    d = bearings()
    d[str(team).upper()] = {"deg": float(deg) % 180.0, "source": source}
    p = modelstate.path(BEARINGS_STORE)
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w") as fh:
        json.dump(d, fh, indent=1, sort_keys=True)
    return p


# ---- the ideas file ------------------------------------------------------------------------

def conditions(game: dict, fit: dict | None = None, bears: dict | None = None) -> dict | None:
    """One game's kicking air: temperature, altitude, density against sea
    level, the wind and (with a recorded bearing) its parts along and
    across the field, and — from a fit that held — what a 50 plays like."""
    home = str(game.get("home") or "")
    w = game.get("weather") or {}
    dome = bool(w.get("dome")) or str(game.get("roof") or "").lower() in ("dome", "closed")
    temp = DOME_F if dome else w.get("temp_f")
    alt = _altitude(home)
    rho = air_density(temp, alt)
    if rho is None:
        return None
    dev = density_dev(rho)
    out = {"home": home, "away": game.get("away"), "dome": dome, "temp_f": temp, "altitude_ft": alt,
           "density": round(rho, 4), "density_dev": round(dev, 4),
           "measured_weather": bool(w.get("measured")) or dome,
           "wind_mph": None if dome else w.get("wind_mph"), "wind_dir": None if dome else (w.get("wind_dir") or None)}
    b = (bears or {}).get(home.upper())
    if b and not dome:
        parts = wind_parts(w.get("wind_mph"), w.get("wind_dir"), b["deg"])
        if parts:
            out["wind_parts"] = {**parts, "bearing": b["deg"]}
    pl = plays_like(fit or {}, 50.0, dev)
    if pl is not None:
        out["plays_like_50"] = pl
    return out


KICK_MARKETS = ("kick_pts", "fg_made")


def ideas_section(props, games, board, sport):
    if sport not in ("nfl", "cfb"):
        return None
    fit, bears = load(sport), bearings()
    by_game = {}
    for g in games or []:
        if not isinstance(g, dict):
            continue
        c = conditions(g, fit, bears)
        if c:
            by_game[f"{g.get('away')}@{g.get('home')}"] = c
    team_game = {}
    for key, c in by_game.items():
        team_game[c["home"]] = key
        team_game[str(c["away"])] = key
    kickers = {}
    for row in (board or {}).get("recommendations") or []:
        if row.get("market") in KICK_MARKETS and row.get("team") in team_game:
            kickers[row["player"]] = team_game[row["team"]]
    return {"games": by_game, "kickers": kickers, "fit": {k: fit.get(k) for k in ("holds", "n", "gain", "t")} if fit else {}}


def pick_view(sec, player, market, side="", line=None):
    key = (sec.get("kickers") or {}).get(player)
    if not key:
        return None
    return {**(sec.get("games") or {}).get(key, {}), "fit": sec.get("fit") or {}}


def game_view(sec, home, away):
    c = (sec.get("games") or {}).get(f"{away}@{home}")
    if not c:
        return None
    return {**c, "fit": sec.get("fit") or {}}


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Air density and field goals, measured on every stored kick")
    ap.add_argument("--sport", default="nfl", help="nfl or cfb (default nfl)")
    ap.add_argument("--save", action="store_true", help="keep the fit where the pick and game pages read it")
    ap.add_argument("--bearing", nargs=2, metavar=("TEAM", "DEGREES"),
                    help="record a stadium's field bearing (needs --source)")
    ap.add_argument("--source", default="", help="the link a --bearing came from")
    a = ap.parse_args(argv)
    if a.bearing:
        print(f"saved → {set_bearing(a.bearing[0], float(a.bearing[1]), a.source)}")
        return 0
    from . import db as _db
    conn = _db.connect()
    try:
        kicks = load_kicks(conn, a.sport)
    finally:
        conn.close()
    res = held_out(kicks)
    devs = sorted(k["dens_dev"] for k in kicks if k["dens_dev"] is not None)
    print(f"Kick physics — {a.sport.upper()}: {len(kicks)} field goals; air against sea level from "
          f"{devs[0]:+.1%} to {devs[-1]:+.1%}" if devs else "no kicks stored")
    print(f"  held out {res.get('test')}: log loss gain with the air {res['gain']} (t {res['t']}, n {res['n']}); "
          f"density coefficient {res.get('density_coef')} (the physics wants it negative)")
    print(f"  THE BAR: gain > 0, t ≥ {MIN_T}, ≥ {MIN_KICKS} kicks, the physics' sign — "
          f"{'HOLDS' if res['holds'] else 'does not hold'}")
    if res.get("holds"):
        for dev in (-0.2, -0.1, 0.1):
            print(f"    a 50-yard try in air {dev:+.0%} against sea level plays like {plays_like(res, 50, dev)}")
    if a.save:
        print(f"  saved → {save(res, a.sport)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
