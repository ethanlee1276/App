"""THE ROOM: when a team's receivers sit, what the ones left get (step AHW, 26 November 2026).

Ethan, 26 November, after Packers at Rams with Puka Nacua and Davante Adams on injured reserve: "when there is alot
of players out we dont reccomend any props for the backups ... or how there usage could step up in the game
reports". The projection already lifts a receiver whose teammate ranked AHEAD of him at his own position is out
(engine/teammates, the top three at each position). It added nothing for the rest of the room.

MEASURED (roomfit.py, 2016-2025 weekly box scores, held out by season). A team's regulars are its receivers, tight
ends and backs with three or more of its games this season; a regular SITS when he took 10%+ of the targets in the
games he played and played in one of the team's last two; the VACATED share is the sum of those shares. Each regular
who plays is ranked among those left by his own share. Against his form times the lift we already apply, and against
the same rank in games where nobody sat (the box score files no row for a game with no catch, which flatters small
roles everywhere), the share of games he beat our number rose:

  * the fourth man on, 20-35% of the targets out: 48% against 42% (targets), 49% against 43% (catches), 46% against
    40% (yards), above the normal rate in every season for targets and catches and in 9 of 10 for yards;
  * the fourth man on, 35% or more out: 53%, 51% and 49% against the same 42%, 43% and 40%, above it in 9, 10 and
    10 seasons of 10;
  * the top three left moved too, but by season it came and went (the 35%-plus second man: 1 season of 10 closer).

The multiplier that brings his over rate back to the normal game's, fitted on nine seasons and scored on the tenth:
catches x1.16 and yards x1.24 at 20-35% (the gap 6.4 to 3.2 points and 5.9 to 3.0, closer in 7 and 8 seasons of
10), catches x1.32 and yards x1.42 at 35% or more (8.9 to 5.9 and 9.8 to 3.4, 8 and 9 seasons of 10). Only those
cells ship (`ROOM`); the rest are said, never priced. The yards are what a team without its main receivers has to
throw somewhere; the team's own targets fell about 4% in those games (x0.96), so it is not more passing.

Standard library only; nothing here raises into a build.
"""
from __future__ import annotations

#: A regular: this many of his team's games this season (roomfit.MIN_PRIOR).
MIN_GAMES = 3
#: A share worth counting when he sits, and how fresh the absence must be (in the team's last this-many games).
SIT_SHARE, FRESH = 0.10, 2
#: The cells that ship: {(market, bucket): multiplier} for the regulars ranked FROM_RANK or lower among those left.
FROM_RANK = 4
BUCKETS = ((0.20, 0.35, "20"), (0.35, 1.01, "35"))
ROOM = {
    ("receptions", "20"): 1.16, ("rec_yds", "20"): 1.24,
    ("receptions", "35"): 1.32, ("rec_yds", "35"): 1.42,
}
#: The words for each cell, on the card and in the report.
MEASURED = "over ten seasons (2016-2025)"
#: The floor a regular's own targets a game must clear to be lifted (roomfit's samples).
MIN_TARGETS_PG = 1.0
#: Who is LEFT: a regular not ruled out who played in one of the team's last this-many games. The measurement ranked
#: the men who played; a build knows only who is ruled out, and a tight end unseen since week 3 (Terrance Ferguson,
#: the Rams, 2026) is not in tonight's room whatever the report says.
ACTIVE = 3
POSITIONS = ("WR", "TE", "RB", "FB")


def _f(r, k) -> float:
    try:
        return float(r.get(k) or 0.0)
    except (TypeError, ValueError, AttributeError):
        return 0.0


def table(stats, teams, upto_week: int) -> dict:
    """{team: {"players": {name: [share, games, last week, targets a game, position]}, "weeks": [weeks played]}}
    from this season's weekly rows before ``upto_week``: each receiver's, tight end's and back's share of his team's
    targets over the games he played. {} on nothing."""
    from .sources.nflverse import _regular_season, _s
    weeks: dict = {}
    for r in _regular_season(stats or []):
        try:
            wk = int(_f(r, "week"))
        except (TypeError, ValueError):
            continue
        if wk <= 0 or wk >= int(upto_week):
            continue
        team = _s(r, "recent_team", "team")
        if not team or (teams and team not in teams):
            continue
        tw = weeks.setdefault(team, {}).setdefault(wk, {})
        pos = _s(r, "position", "position_group").upper()
        if pos in POSITIONS:
            name = _s(r, "player_display_name", "player_name", "full_name")
            if name:
                tw[name] = (pos, _f(r, "targets"))
    out: dict = {}
    for team, ws in weeks.items():
        team_t = {w: sum(t for _p, t in ps.values()) for w, ps in ws.items()}
        acc: dict = {}
        for w, ps in ws.items():
            for name, (pos, t) in ps.items():
                a = acc.setdefault(name, [0.0, 0.0, 0, 0, pos])
                a[0] += t
                a[1] += team_t[w]
                a[2] += 1
                a[3] = max(a[3], w)
        players = {n: [round(a[0] / a[1], 4) if a[1] else 0.0, a[2], a[3], round(a[0] / a[2], 2), a[4]]
                   for n, a in acc.items()}
        out[team] = {"players": players, "weeks": sorted(ws)}
    return out


def _norm(name) -> str:
    try:
        from .teammates import _norm as n
        return n(str(name or ""))
    except Exception:                                        # noqa: BLE001
        return str(name or "").lower().strip()


def vacated(room: dict | None, out) -> tuple:
    """(the share of the team's targets that sits tonight, [(name, share)] of the regulars who left it, best first):
    regulars ruled out who took SIT_SHARE or more and played in one of the team's last FRESH games."""
    players = (room or {}).get("players") or {}
    fresh = set(((room or {}).get("weeks") or [])[-FRESH:])
    gone = {_norm(o) for o in out or ()}
    sat = [(n, p[0]) for n, p in players.items()
           if _norm(n) in gone and p[1] >= MIN_GAMES and p[0] >= SIT_SHARE and p[2] in fresh]
    sat.sort(key=lambda x: -x[1])
    return min(0.8, sum(s for _n, s in sat)), sat


def rank_left(room: dict | None, out, me: str) -> int | None:
    """His rank by share among the regulars left tonight (1 = the biggest share left), or None when he is not a
    regular here."""
    players = (room or {}).get("players") or {}
    gone = {_norm(o) for o in out or ()}
    mine = next((p for n, p in players.items() if _norm(n) == _norm(me)), None)
    if not mine or mine[1] < MIN_GAMES:
        return None
    active = set(((room or {}).get("weeks") or [])[-ACTIVE:])
    left = [p[0] for n, p in players.items()
            if _norm(n) not in gone and p[1] >= MIN_GAMES and (not active or p[2] in active)]
    return 1 + sum(1 for s in left if s > mine[0])


def bucket(share: float) -> str | None:
    return next((b for lo, hi, b in BUCKETS if lo <= share < hi), None)


def lift(room: dict | None, out, me: str, market: str) -> tuple:
    """(multiplier, info) for one player's market: ROOM's cell when 20%+ of the targets sit and he ranks FROM_RANK
    or lower among the regulars left, with his own targets a game over MIN_TARGETS_PG; (1.0, info or None) else.
    ``info`` is {"vacated", "sat": [(name, share)], "rank", "bucket", "applied"} whenever a share sits."""
    share, sat = vacated(room, out)
    if not sat:
        return 1.0, None
    rank = rank_left(room, out, me)
    b = bucket(share)
    info = {"vacated": round(share, 3), "sat": [(n, round(s, 3)) for n, s in sat], "rank": rank, "bucket": b,
            "applied": 1.0}
    players = (room or {}).get("players") or {}
    mine = next((p for n, p in players.items() if _norm(n) == _norm(me)), None)
    if (b is None or rank is None or rank < FROM_RANK or not mine or mine[3] < MIN_TARGETS_PG
            or str(mine[4]).upper() not in POSITIONS or _norm(me) in {_norm(o) for o in out or ()}):
        return 1.0, info
    mult = ROOM.get((market, b), 1.0)
    info["applied"] = mult
    return mult, info


def words(info: dict, team: str, market: str) -> str:
    """The card's note for a room lift that applied."""
    who = " and ".join(n for n, _s in info.get("sat") or [])
    lo = next((lo for lo, hi, b in BUCKETS if b == info.get("bucket")), 0.2)
    hi = next((hi for lo_, hi, b in BUCKETS if b == info.get("bucket")), 1.0)
    span = f"{lo:.0%} to {hi:.0%}" if hi <= 1 else f"{lo:.0%} or more"
    what = {"receptions": "catches", "rec_yds": "receiving yards"}.get(market, "numbers")
    return (f"{who} out: {info['vacated']:.0%} of {team}'s targets sit. Measured {MEASURED}: when {span} of a "
            f"team's targets sat, the receivers left beyond its top three beat their usual {what} more often than "
            f"in other games, and this is the lift that measured — applied (×{info['applied']:.2f})")
