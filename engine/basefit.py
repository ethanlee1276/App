"""AN ORDINARY GAME, FOR EVERY LEAGUE (step AIL, 27 November 2026).

The Record says how often each kind of read was right, graded as engine/reportgrade grades it: the player's stat
that game against the average of the player's previous games (at most 10, at least 2). "Beat the average" is not a
coin flip: the stats are skewed, so most of a player's games sit under the average. The NFL's record says what an
ordinary game does beside it (reportrecord.BASE_RATES, step AIB: a key player beats that average 42% of the time
and falls short 57%). The other leagues said nothing, so hockey's fades read "right 47 of 104 (45%)" with no way to
tell that an ordinary game falls short of a shooter's average more than half the time, which would make 45% worse
than doing nothing.

This measures each league's ordinary game the same way, on the history database's own game logs: for every key
player (a volume floor over the player's previous games, below), the share of games where the stat the league's
reads are graded on beat, fell short of, or equalled the average of the player's previous games. It runs with the
Wednesday deep refit (engine/maintenance._run_deep_refit), writes BASE_PATH, and its last line is the job's word
on the heartbeat. engine/reportrecord reads the file for every league but the NFL, whose measurement on nflverse
(25,403 games, 2017-2025) stays as it is.

Nothing here moves a number. Standard library only; never raises out of `refresh`.

    python3 -m engine.basefit            # measure, write data/base_rates.json, print each league
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path

#: Where the measurement is kept (engine/reportrecord.base_rates reads it).
BASE_PATH = Path(__file__).resolve().parents[1] / "data" / "base_rates.json"
#: The previous games a read is graded against (engine/reportgrade.LAST_N, MIN_N).
LAST_N, MIN_N = 10, 2
#: How many of the newest seasons in the logs are measured.
SEASONS = 3
#: A league is said only on this many graded games.
MIN_GAMES = 500
#: Each league's ordinary game, by position ("" for every position): (the stat its reads are graded on, the volume
#: market, the average of it over the player's previous games that makes a key player). Basketball's reads are graded
#: on points (reportgrade.DEFAULT_STAT), hockey's skaters on shots on goal (nhl/scan SKATER_LEANS starts with them),
#: college football's as the NFL's are, by position.
SPEC = {
    "nba": {"": ("pts", "min", 24.0)},
    "wnba": {"": ("pts", "min", 24.0)},
    "cbb": {"": ("pts", "min", 24.0)},
    "nhl": {"": ("sog", "toi", 15.0)},
    "cfb": {"QB": ("pass_yds", "pass_att", 20.0), "RB": ("rush_yds", "rush_att", 10.0),
            "WR": ("rec_yds", "receptions", 3.0), "TE": ("rec_yds", "receptions", 3.0)},
}
#: Positions never measured: a goalie is graded on saves, not shots.
SKIP_POS = {"nhl": ("G",)}


def _f(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def measure(conn, sport: str, seasons: int = SEASONS) -> dict | None:
    """{"over", "under", "even", "n", "seasons"} for ``sport``'s key players over its newest ``seasons`` seasons in
    the logs, or None with too few games (MIN_GAMES) or no logs."""
    spec = SPEC.get(sport)
    if not spec:
        return None
    markets = sorted({m for st, vol, _floor in spec.values() for m in (st, vol)})
    try:
        newest = conn.execute("SELECT MAX(season) FROM player_game_logs WHERE sport=?", (sport,)).fetchone()[0]
        if newest is None:
            return None
        first = int(newest) - seasons + 1
        rows = conn.execute(
            "SELECT season, period, game_id, player, team, position, market, value FROM player_game_logs "
            f"WHERE sport=? AND season>=? AND market IN ({','.join('?' * len(markets))})",
            (sport, first - 1, *markets)).fetchall()
    except Exception:                                        # noqa: BLE001
        return None
    games: dict = defaultdict(dict)        # ((player, team), season, period, game_id) -> {market: value, "_pos": pos}
    for r in rows:
        r = tuple(r)
        # One man to a name and club: two college players can share a name, and a trade starts a new history.
        k = ((r[3], r[4]), int(r[0]), str(r[1] or ""), str(r[2] or ""))
        g = games[k]
        v = _f(r[7])
        if v is not None:
            g[r[6]] = v
        if r[5]:
            g["_pos"] = str(r[5]).upper()
    by_player: dict = defaultdict(list)
    for (p, season, period, gid), g in games.items():
        by_player[p].append((season, period, gid, g))
    over = under = even = 0
    skip = SKIP_POS.get(sport, ())
    for p, gl in by_player.items():
        gl.sort(key=lambda x: (x[0], x[1], x[2]))
        for i, (season, _period, _gid, g) in enumerate(gl):
            if season < first:
                continue                                     # the season before is history, not measured
            pos = g.get("_pos") or ""
            if pos in skip:
                continue
            st, vol, floor = spec.get(pos) or spec.get("") or (None, None, None)
            if st is None or g.get(st) is None:
                continue
            past = [x[3] for x in gl[max(0, i - LAST_N):i] if x[0] >= season - 1]
            vals = [x[st] for x in past if x.get(st) is not None]
            vols = [x[vol] for x in past if x.get(vol) is not None]
            if len(vals) < MIN_N or len(vols) < MIN_N or sum(vols) / len(vols) < floor:
                continue
            avg = sum(vals) / len(vals)
            if g[st] > avg:
                over += 1
            elif g[st] < avg:
                under += 1
            else:
                even += 1
    n = over + under + even
    if n < MIN_GAMES:
        return None
    return {"over": round(over / n, 3), "under": round(under / n, 3), "even": round(even / n, 3), "n": n,
            "seasons": f"{first}–{int(newest)}"}


def refresh(conn=None, path: Path = BASE_PATH, leagues=None) -> dict:
    """Measure every league in SPEC (or ``leagues``) and write ``path``: {"at", "leagues": {league: measure}}.
    Returns what it wrote; never raises (a league that cannot be read is left out)."""
    import datetime as _dt
    out = {"at": _dt.datetime.now().isoformat(timespec="seconds"), "leagues": {}}
    own = conn is None
    try:
        if own:
            from . import db
            conn = db.connect()
        for lg in leagues or SPEC:
            try:
                m = measure(conn, lg)
            except Exception:                                # noqa: BLE001
                m = None
            if m:
                out["leagues"][lg] = m
        tmp = Path(str(path) + ".tmp")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(out, indent=1), encoding="utf-8")
        os.replace(tmp, path)
    except Exception as exc:                                 # noqa: BLE001
        out["error"] = str(exc).split("\n")[0][:200]
    finally:
        if own and conn is not None:
            try:
                conn.close()
            except Exception:                                # noqa: BLE001
                pass
    return out


def summary_line(res: dict) -> str:
    """The job's last line on the heartbeat: "base rates: nba 46.1% over / 52.7% under (31,204 games, 2024–2026);
    ..." or why there is none."""
    if res.get("error"):
        return f"base rates: not written ({res['error']})"
    parts = [f"{lg} {m['over']:.1%} over / {m['under']:.1%} under ({m['n']:,} games, {m['seasons']})"
             for lg, m in (res.get("leagues") or {}).items()]
    return "base rates: " + ("; ".join(parts) if parts else "no league had enough games")


def main(argv=None) -> int:
    res = refresh()
    print(summary_line(res))
    return 0 if not res.get("error") else 1


if __name__ == "__main__":
    raise SystemExit(main())
