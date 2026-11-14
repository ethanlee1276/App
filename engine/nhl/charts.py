"""Every shot a skater took and every shot a goalie faced: hockey's two charts.

Ethan, 2026-10-13: "Yes do all of them and don't stop till they are all
done, then make sure they are all routed correctly like nfl." The list he
said yes to had the NHL's shot map and the goalie's save map on it.

NOTHING NEW TO FETCH. The expected-goals work (engine/sources/nhlpbp,
2026-10-03) already stores every attempt of every game in `nhl_shots`:
where it was taken (feet from centre ice), what it became (a goal, a shot
on goal, a miss or a block), the shooter, the goalie in net, the shot
type, the strength, and whether it came off a rebound or the rush. These
charts read that table.

ONE END OF THE RINK. The league's coordinates put a shot at either end;
the row's distance was measured to the net the shooter attacked, so each
attempt is turned to face the same net (a half turn, never a mirror: the
shooter's left stays his left).

THE SKATER'S SHOT MAP (kind "shotmap"): every attempt, on goal, missed or
blocked, and the goals, with each unblocked attempt's expected goals from
the site's own model (engine/nhl/xg, fitted on every stored shot; said
as ours wherever it is shown).

THE GOALIE'S SAVE MAP (kind "saves"): every shot on goal he faced, saved
or scored, with goals saved above expected the way the board already
counts it (xg.summaries: shots on goal and goals, no empty nets).
"""

from __future__ import annotations

import math

#: The net each attempt is turned to face, in feet from centre ice.
NET_X = 89.0
#: Distance bands for the splits and the pills, in feet from the net.
BANDS = ((0, 10, "crease", "In the crease"), (10, 20, "slot", "The slot"),
         (20, 35, "high", "High slot and circles"), (35, 200, "point", "The point"))
STRENGTH = {"EV": "Even strength", "PP": "Power play", "SH": "Shorthanded"}


def band(dist) -> str:
    if dist is None:
        return ""
    return next((k for lo, hi, k, _n in BANDS if lo <= dist < hi), "point")


def facing(x, y, dist) -> tuple:
    """The attempt turned to face the net at +89: the stored distance says
    which net he attacked."""
    if x is None or y is None:
        return None, None
    if dist is not None:
        right = math.hypot(NET_X - x, y)
        left = math.hypot(-NET_X - x, y)
        if abs(left - dist) < abs(right - dist):
            return -x, -y
    elif x < 0:
        return -x, -y
    return x, y


def season_label(season: int) -> str:
    return f"{int(season)}-{(int(season) + 1) % 100:02d}"


def _resolve(conn, player: str, col: str) -> str:
    """The stored spelling of a shooter's or goalie's name, or ""."""
    from ..carries import _fold
    q = (player or "").strip()
    if not q:
        return ""
    row = conn.execute(f"SELECT {col} FROM nhl_shots WHERE {col}=? LIMIT 1", (q,)).fetchone()
    if row:
        return row[0]
    want = _fold(q)
    hits = {name for (name,) in conn.execute(f"SELECT DISTINCT {col} FROM nhl_shots WHERE {col} != ''")
            if _fold(name) == want}
    return next(iter(hits)) if len(hits) == 1 else ""


def _model():
    from . import xg as X
    try:
        return X.load()
    except Exception:                                              # noqa: BLE001
        return None


def _shot(r: dict, model) -> dict:
    from . import xg as X
    x, y = facing(r["x"], r["y"], r["dist"])
    out = {"i": r["event_id"], "x": round(x, 1) if x is not None else None,
           "y": round(y, 1) if y is not None else None, "k": r["kind"], "g": int(r["is_goal"] or 0),
           "t": r["shot_type"] or "", "st": r["strength"] or "", "p": r["period"], "d": r["dist"],
           "reb": int(r["rebound"] or 0), "rush": int(r["rush"] or 0), "en": int(r["empty_net"] or 0),
           "z": band(r["dist"])}
    if model is not None and r["kind"] in X.UNBLOCKED:
        out["xg"] = round(X.xg(model, r), 3)
    return out


def _games(rows: list, model, who: str) -> list:
    games: dict = {}
    for r in rows:
        g = games.setdefault(r["game_id"], {"id": r["game_id"], "date": r["date"], "season": r["season"],
                                            "team": r["team"] if who == "shooter" else r["opponent"],
                                            "opp": r["opponent"] if who == "shooter" else r["team"],
                                            "shots": []})
        s = _shot(r, model)
        if who == "shooter":
            s["vs"] = r["goalie"] or ""
            if r["is_goal"]:
                s["a"] = [a for a in (r["assist1"], r["assist2"]) if a]
        else:
            s["by"] = r["shooter"] or ""
        g["shots"].append(s)
    return sorted(games.values(), key=lambda g: (g["date"], g["id"]), reverse=True)


def _homes(conn, games: list) -> None:
    """Which side was home, off the games table (keyed AWAY@HOME by date);
    a game it does not have says neither."""
    for g in games:
        row = conn.execute("SELECT home FROM games WHERE sport='nhl' AND period=? AND (home=? OR away=?) LIMIT 1",
                           (g["date"], g["team"], g["team"])).fetchone()
        g["home"] = None if row is None else row[0] == g["team"]


def _skater_line(shots: list) -> dict:
    sog = [s for s in shots if s["k"] in ("sog", "goal")]
    unb = [s for s in shots if s["k"] in ("sog", "goal", "miss")]
    goals = sum(s["g"] for s in shots)
    xg = [s["xg"] for s in unb if "xg" in s]
    return {"n": len(shots), "att": len(shots), "sog": len(sog), "goals": goals,
            "miss": sum(1 for s in shots if s["k"] == "miss"), "blocked": sum(1 for s in shots if s["k"] == "block"),
            "pp": sum(1 for s in shots if s["st"] == "PP"), "rebounds": sum(1 for s in shots if s["reb"]),
            "rush": sum(1 for s in shots if s["rush"]),
            "ixg": round(sum(xg), 2) if xg else None,
            "sh_pct": round(goals / len(sog), 3) if sog else None}


def _goalie_line(shots: list) -> dict:
    faced = [s for s in shots if s["k"] in ("sog", "goal") and not s["en"]]
    ga = sum(s["g"] for s in faced)
    xga = [s["xg"] for s in faced if "xg" in s]
    return {"n": len(faced), "shots": len(faced), "saves": len(faced) - ga, "ga": ga,
            "sv_pct": round((len(faced) - ga) / len(faced), 3) if faced else None,
            "xga": round(sum(xga), 2) if xga else None,
            "gsax": round(sum(xga) - ga, 2) if xga else None,
            "pp": sum(1 for s in faced if s["st"] == "PP"), "rebounds": sum(1 for s in faced if s["reb"])}


def _split(shots: list, key, order) -> list:
    out = []
    for k, name in order:
        xs = [s for s in shots if key(s) == k]
        if not xs:
            continue
        g = sum(s["g"] for s in xs)
        on = [s for s in xs if s["k"] in ("sog", "goal")]
        out.append({"key": k, "name": name, "n": len(xs), "on": len(on), "goals": g,
                    "pct": round(g / len(on), 3) if on else None})
    return out


def _chart(conn, player: str, season, who: str) -> dict:
    col = "shooter" if who == "shooter" else "goalie"
    name = _resolve(conn, player, col)
    if not name:
        return {}
    seasons = [int(s) for (s,) in conn.execute(
        f"SELECT DISTINCT season FROM nhl_shots WHERE {col}=? AND season IS NOT NULL ORDER BY season DESC",
        (name,))]
    if not seasons:
        return {}
    pick = int(season) if season and int(season) in seasons else seasons[0]
    cur = conn.execute(
        f"SELECT game_id, event_id, date, season, team, opponent, shooter, goalie, kind, x, y, dist, angle, "
        f"shot_type, strength, empty_net, rebound, rush, is_goal, period, assist1, assist2 FROM nhl_shots "
        f"WHERE {col}=? AND season=? ORDER BY date, game_id, event_id", (name, pick))
    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, r)) for r in cur]
    if who == "goalie":
        # His shots: on goal, never into an empty net (xg.summaries' rule).
        rows = [r for r in rows if r["kind"] in ("sog", "goal") and not r["empty_net"]]
    if not rows:
        return {}
    model = _model()
    games = _games(rows, model, who)
    _homes(conn, games)
    # The final over the game's rink (the chart's frame, 2026-10-14).
    from ..carries import scoreboard
    scoreboard(conn, "nhl", pick, games)
    line = _skater_line if who == "shooter" else _goalie_line
    every = []
    for g in games:
        g["line"] = line(g["shots"])
        every += g["shots"]
    total = line(every)
    n = len(games)
    total["games"] = n
    if who == "shooter":
        total["sog_pg"] = round(total["sog"] / n, 2) if n else None
    else:
        total["shots_pg"] = round(total["shots"] / n, 1) if n else None
    bands = [(k, label) for _lo, _hi, k, label in BANDS]
    kind = lambda s: (s["t"] or "other").lower()  # noqa: E731
    types = sorted({kind(s) for s in every}, key=lambda t: -sum(1 for s in every if kind(s) == t))
    by_zone = _split(every, lambda s: s["z"], bands)
    by_type = _split(every, kind, [(t, t.replace("-", " ").capitalize()) for t in types])
    by_strength = _split(every, lambda s: s["st"], list(STRENGTH.items()))
    latest = games[0] if games else {}
    return {"player": name, "sport": "nhl", "role": "skater" if who == "shooter" else "goalie",
            "seasons": seasons, "season": pick, "season_label": season_label(pick),
            "team": latest.get("team", ""), "games": games, "season_line": total, "zones": by_zone,
            "by_type": by_type, "by_strength": by_strength, "xg_model": model is not None}


def shot_map(conn, player: str, season: int | None = None) -> dict:
    """Everything the skater's shot map draws for one player-season:
    ``{player, sport, role, seasons, season, season_label, team, games:
    [{id, date, opp, team, line, shots}], season_line, zones, by_type,
    by_strength, xg_model}``, games newest first, each attempt ``{i, x, y,
    k, g, t, st, p, d, reb, rush, en, z, xg?, vs, a?}`` turned to face the
    net at +89."""
    return _chart(conn, player, season, "shooter")


def save_map(conn, player: str, season: int | None = None) -> dict:
    """The goalie's save map: every shot on goal he faced, the same shape,
    each shot ``by`` its shooter."""
    return _chart(conn, player, season, "goalie")
