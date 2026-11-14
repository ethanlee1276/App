"""Shooting regressed: points and threes rebuilt from shot volume.

Ethan, 2026-11-04: "work on the nba most likely and edge bets ... find and
invent more tools and data ... to make better picks."

THE MEASUREMENT (2026-11-04, the NBA lab). Two full seasons of the league's
own play-by-play (2024-25 and 2025-26, every game; engine/nba/stints rebuilt
each and its box scores matched every final), every player-game with 10+
minutes and 5+ earlier games for his club: his rate times the minutes he
actually played, against what he did. The constants were chosen on 2024-25
and judged on 2025-26, which they never saw:

* **Threes** as his three-point ATTEMPTS a minute over the same games as
  his rate, times a 3P% read over his last 60 games and shrunk toward the
  league's by 250 attempts: error 1.68% lower than threes a minute
  (16,248 player-games; this module itself, judged the same way).
* **Points** as twos, threes and free throws a minute, each make rate
  shrunk the same way (twos by 150 attempts, threes by 250, free throws by
  50): error 0.99% lower than points a minute. A simple "he's shooting
  above his norm" discount managed 0.47%.

WHY IT WORKS. Attempts are a player's role and his coach's choice; makes
are that plus luck. Twenty games is about 100 threes for a starter, and a
3P% over 100 attempts swings ±5 points on luck alone, so a rate that counts
makes carries last month's luck straight into tonight's number. The
attempts carry over; the luck regresses. A board priced on raw makes calls
a hot shooter's over an edge the market has already discounted.

Pure functions plus two reads of `player_game_logs` (the columns the
ingest has stored since 2026-10-20). Anything missing returns None, and the
projection keeps its raw rate: no claim beats a guessed one.
"""

from __future__ import annotations

import os

#: The box-score columns a shot read needs, per game.
SHOT_KEYS = ("fgm", "fga", "fg3m", "fg3a", "ftm", "fta")

#: Attempts of the league's percentage a player's own record is shrunk
#: toward (measured, 2024-25 fit, 2025-26 test).
K2, K3, KF = 150.0, 250.0, 50.0
#: His long-run record: his last this-many games, any club, any season.
LONG_GAMES = 60
#: The league's own percentages over both lab seasons, used when the logs
#: cannot give a current one (2024-25 / 2025-26: 36.0% and 36.0% from
#: three, 54.5% and 55.0% on twos, 78.0% and 78.3% at the line).
LEAGUE_FALLBACK = {"p3": 0.360, "p2": 0.548, "pf": 0.781}
#: College's, 2025-26's Division I box scores: a shorter three, and fewer
#: of everything made, than the NBA's.
LEAGUE_FALLBACK_BY = {"nba": LEAGUE_FALLBACK, "cbb": {"p3": 0.338, "p2": 0.519, "pf": 0.722}}
#: A recent window where fewer of his minutes than this carry shot
#: columns is too thin a volume read; the raw rate stands.
MIN_SHOT_SHARE = 0.8
#: The markets whose projection the read moves: points and threes, and
#: the combos that hold points (only their points part moves).
POINTS_COMBOS = ("pra", "pts_reb", "pts_ast")
MOVED = ("pts", "fg3m") + POINTS_COMBOS
#: Leagues measured. The WNBA was not (its own percentages, its own lab).
#: College basketball was, on its own five seasons (2026-11-13,
#: docs/CBB_LAB.md: points 0.4-0.5% closer, threes 1.2-1.3%, every judged
#: season), against its own percentages (`LEAGUE_FALLBACK_BY` until the
#: box's logs can say).
LEAGUES = ("nba", "cbb")
#: What each league's read says it was measured to do, on the pick.
MEASURED = {"nba": {"fg3m": "1.68%", "pts": "0.99%"}, "cbb": {"fg3m": "1.2%", "pts": "0.5%"}}


def enabled() -> bool:
    """On unless ``QB_NBA_SHOOTING=0`` — the switch the box's replay uses to
    measure the board with and without it (`nbashootfit.py`)."""
    return os.environ.get("QB_NBA_SHOOTING", "1").strip() not in ("0", "off", "false", "no")


def shrunk(made: float, att: float, k: float, league: float) -> float:
    """His make rate with ``k`` attempts of the league's added."""
    return (made + k * league) / (att + k)


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def game_shots(g: dict) -> dict | None:
    """One stored game's shot columns, or None when any is missing."""
    out = {}
    for k in SHOT_KEYS:
        v = _num((g or {}).get(k))
        if v is None:
            return None
        out[k] = v
    return out


def sums(games: list) -> dict:
    """Totals over games that carry their shot columns, with the minutes
    and points of exactly those games."""
    tot = dict.fromkeys(SHOT_KEYS + ("min", "pts"), 0.0)
    tot["games"] = 0
    for g in games or []:
        s = game_shots(g)
        if s is None:
            continue
        for k, v in s.items():
            tot[k] += v
        tot["min"] += float(_num(g.get("min")) or 0.0)
        tot["pts"] += float(_num(g.get("pts")) or 0.0)
        tot["games"] += 1
    return tot


def bundle(recent: list, longrun: list, league: dict | None = None, league_key: str = "nba") -> dict | None:
    """What a prop carries for the read: ``{"recent": sums, "long": sums,
    "league": pcts}`` — ``recent`` the games his rate is read from (his
    newest first, each a stored game ``{market: value}``), ``longrun`` his
    last LONG_GAMES games any club. None when there is nothing to read."""
    if not recent:
        return None
    r = sums(recent)
    mins = sum(float(_num((g or {}).get("min")) or 0.0) for g in recent)
    if r["games"] == 0 or mins <= 0 or r["min"] < MIN_SHOT_SHARE * mins:
        return None
    lg = dict(LEAGUE_FALLBACK_BY.get(league_key, LEAGUE_FALLBACK))
    lg.update({k: v for k, v in (league or {}).items() if k in lg and v})
    return {"recent": r, "long": sums(longrun or recent), "league": lg}


def structural(read: dict) -> dict | None:
    """Per-minute points and threes rebuilt from volume and shrunk makes:
    ``{"pts", "fg3m", "p2", "p3", "pf", "p3_recent"}``, or None."""
    if not read:
        return None
    r, lr, lg = read["recent"], read["long"], read["league"]
    if r["min"] <= 0:
        return None
    a2 = (r["fga"] - r["fg3a"]) / r["min"]
    a3 = r["fg3a"] / r["min"]
    af = r["fta"] / r["min"]
    p3 = shrunk(lr["fg3m"], lr["fg3a"], K3, lg["p3"])
    p2 = shrunk(lr["fgm"] - lr["fg3m"], lr["fga"] - lr["fg3a"], K2, lg["p2"])
    pf = shrunk(lr["ftm"], lr["fta"], KF, lg["pf"])
    return {"pts": 2 * a2 * p2 + 3 * a3 * p3 + af * pf, "fg3m": a3 * p3,
            "p2": p2, "p3": p3, "pf": pf,
            "p3_recent": (r["fg3m"] / r["fg3a"]) if r["fg3a"] else None,
            "pts_raw": r["pts"] / r["min"], "fg3m_raw": r["fg3m"] / r["min"]}


def projection_mult(stat: str, rate: float, read: dict | None,
                    league_key: str = "nba") -> tuple[float, str]:
    """``(multiplier, note)`` on a projection whose per-minute rate is
    ``rate``: the rebuilt rate over the raw one, from the same games. For
    a combo only its points part is rebuilt. (1.0, "") when the read is
    off, unmeasured for this league or market, or missing."""
    if (stat not in MOVED or league_key not in LEAGUES or not enabled()
            or not rate or rate <= 0):
        return 1.0, ""
    s = structural(read)
    if not s:
        return 1.0, ""
    if stat == "fg3m":
        if s["fg3m_raw"] <= 0 and s["fg3m"] <= 0:
            return 1.0, ""
        new = s["fg3m"]
        raw = s["fg3m_raw"]
        if raw <= 0:
            return 1.0, ""
        m = new / raw
        lately = s["p3_recent"]
        note = (f"Threes read as his attempts times his 3P% over his last {LONG_GAMES} games "
                f"({s['p3']:.1%} shrunk toward the league's), not his makes"
                + (f" — {lately:.1%} lately" if lately is not None else "")
                + f" (measured: {MEASURED.get(league_key, MEASURED['nba'])['fg3m']} closer on a season it never saw)")
    else:
        if s["pts_raw"] <= 0:
            return 1.0, ""
        # Swap the points part of the rate: raw points out, rebuilt in.
        new_rate = rate - s["pts_raw"] + s["pts"] if stat != "pts" else s["pts"]
        base_rate = rate if stat != "pts" else s["pts_raw"]
        if base_rate <= 0 or new_rate <= 0:
            return 1.0, ""
        m = new_rate / base_rate
        note = (f"Points read from his shot volume at his long-run percentages "
                f"(2s {s['p2']:.1%}, 3s {s['p3']:.1%}, FTs {s['pf']:.1%}, shrunk toward the league's), "
                f"not his recent makes (measured: {MEASURED.get(league_key, MEASURED['nba'])['pts']} closer on a "
                f"season it never saw)")
    m = round(m, 4)
    if abs(m - 1.0) < 0.005:
        return 1.0, ""
    return m, note


def longrun(conn, sport: str, players, n: int = LONG_GAMES, before: str | None = None) -> dict:
    """`_longrun`, kept between builds while the league's logs and the
    slate's names hold (engine/logcache, 2026-11-09): every priced player's
    last games for his shot columns, 4.4 seconds of the NBA build's context
    reads at 09:34 on 9 November, read again on every build of the same
    slate. Keyed on every season of the league, the names asked for (a
    digest) and ``before``."""
    names = sorted({p for p in players if p})
    if not names:
        return {}
    import hashlib
    from .. import logcache
    return logcache.memo(conn, f"nba_shooting_long{int(n)}", sport, None,
                         lambda: _longrun(conn, sport, names, n, before), code=__file__,
                         extra={"names": hashlib.sha1("\n".join(names).encode()).hexdigest(),
                                "before": before})


def _longrun(conn, sport: str, players, n: int = LONG_GAMES, before: str | None = None) -> dict:
    """``{player: [stored games, newest first]}`` — his last ``n`` games with
    shot columns, any club, any season (``before`` an ISO date to read
    history as of then). One query for every name asked."""
    names = sorted({p for p in players if p})
    if not names:
        return {}
    out: dict = {}
    q = ("SELECT player, period, market, value FROM player_game_logs WHERE sport=? "
         "AND market IN (%s) AND player IN (%s)" % (",".join("?" * (len(SHOT_KEYS) + 2)),
                                                     ",".join("?" * len(names))))
    args = [sport, *SHOT_KEYS, "min", "pts", *names]
    if before:
        q += " AND period < ?"
        args.append(before)
    games: dict = {}
    for r in conn.execute(q, args):
        games.setdefault(r[0], {}).setdefault(str(r[1]), {})[r[2]] = r[3]
    for p, by_day in games.items():
        days = sorted(by_day, reverse=True)
        out[p] = [by_day[d] for d in days if game_shots(by_day[d]) is not None][:n]
    return out


def league_pcts(conn, sport: str, since: str | None = None) -> dict:
    """The league's 2P%, 3P% and FT% from the stored logs (``since`` an ISO
    date), or {} when there are too few shots to say."""
    q = ("SELECT market, SUM(value) FROM player_game_logs WHERE sport=? "
         "AND market IN (%s)" % ",".join("?" * len(SHOT_KEYS)))
    args: list = [sport, *SHOT_KEYS]
    if since:
        q += " AND period >= ?"
        args.append(since)
    tot = {r[0]: float(r[1] or 0.0) for r in conn.execute(q + " GROUP BY market", args)}
    if tot.get("fg3a", 0) < 5000 or tot.get("fga", 0) < 20000 or tot.get("fta", 0) < 5000:
        return {}
    return {"p3": tot["fg3m"] / tot["fg3a"],
            "p2": (tot["fgm"] - tot["fg3m"]) / (tot["fga"] - tot["fg3a"]),
            "pf": tot["ftm"] / tot["fta"]}
