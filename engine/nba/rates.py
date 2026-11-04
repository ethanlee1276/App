"""Rates, luck taken out: each per-minute rate read past his last twenty games.

Ethan, 2026-11-04: "We want to make our NBA model as proficient as
possible ... I don't want to have to specifically ask you for certain
tools ... I want you to just do it."

The board reads every rate from his last twenty games for the club. Twenty
games is about 600 minutes for a starter: some 20 blocks for a forward, 15
steals for a guard, so a hot fortnight moves the number as much as a real
change does. THE READ: his older games (his last LONG_GAMES any club, past
the twenty) join it at a weight ``w`` a minute, and ``kappa`` minutes of
the league's rate for his role (starter or bench) are added:

    rate = (V20 + w * V_old + kappa * league) / (M20 + w * M_old + kappa)

V the stat's total and M the minutes over the games that stored it. It
reads rebounds, assists, steals, blocks and turnovers, and the rebounds and
assists inside every combo. Points and threes stay as the shooting read
has them (engine/nba/shooting): their shots a game read the same way came
out closer as numbers but no better as chances (below).

THE MEASUREMENT (2026-11-04, the NBA lab: the league's own play-by-play for
2024-25 and 2025-26, every player-game of 10+ minutes with 5+ earlier games
for his club, his rate times the minutes he actually played against what he
did). ``w`` and ``kappa`` were fitted on one season and judged on the other,
both ways; the constants below were fitted on both. The squared error the
read takes off, season held out 2024-25 / 2025-26:

    steals 4.5% / 4.4%   turnovers 3.3% / 3.4%   blocks 2.7% / 4.0%
    rebounds 2.0% / 3.2% assists 1.6% / 2.4%
    rebounds + assists 1.9% / 2.8%

and through the board's own minutes, on the players it prices (15+ a
game), a little over half of it: steals 3.3% / 3.3%, blocks 2.2% / 3.3%,
turnovers 2.3% / 2.4%, rebounds 1.3% / 2.1%, assists 1.0% / 1.7%. Most of
it is in the men with a thin twenty (under 400 minutes): 3-7%.

AS CHANCES. Through the fitters' own walk (`hoopsreplay.walk`: the board's
projection, priced at a half point under his last eight games' average),
Brier with a temperature fitted on one half of the games and judged on the
other, both ways: steals 0.7-1.3% better, blocks 1.1-1.5%, turnovers
0.9-1.2%, rebounds 0.7%, assists 0.6%, rebounds + assists 0.5%, the
combos with points 0.0-0.1% (their points untouched) — and as
much with the temperature fitted before the read as after it, so the board
gains from the first build, not only after the weekly refit. Points read
the same way (his shots a game past the twenty) landed 0.8-1.4% closer as a
number (0.5% through the walk) and 0.1% WORSE as a chance, so points and
threes are left alone.

Off with ``QB_NBA_RATES=0`` (engine/nba/switches ``rates``), and the box's
own check (`nbarates.py --save`, run by the weekly deep refit) turns it off
when the box's stored seasons do not bear it out. The WNBA was not measured
and is not moved. Pure functions plus one read of `player_game_logs`.
"""
from __future__ import annotations

#: Leagues measured.
LEAGUES = ("nba",)
#: His long-run read: his last this-many games, any club, any season — the
#: twenty and the older games past them (the shooting read's sixty).
LONG_GAMES = 60
#: The board's own window, which the older games are read past.
WINDOW = 20
#: ``(w, kappa)`` per stat, fitted on both lab seasons: the weight a minute
#: of an older game carries, and the minutes of the league's rate added.
PARAMS = {"reb": (0.5, 25.0), "ast": (0.3, 25.0), "stl": (0.75, 400.0),
          "blk": (0.5, 100.0), "tov": (0.3, 100.0)}
#: The league's rate a minute for a starter and for a bench player, both lab
#: seasons (the starters' own five at the opening tip).
LEAGUE = {True: {"reb": 0.18576, "ast": 0.12008, "stl": 0.03411, "blk": 0.02068, "tov": 0.06080},
          False: {"reb": 0.17466, "ast": 0.09553, "stl": 0.03528, "blk": 0.01936, "tov": 0.04962}}
#: The stats read, and the columns each needs.
KEYS = tuple(PARAMS)
#: The parts of each market this step reads. Points, threes and the points
#: in a combo stay the shooting read's (engine/nba/shooting).
PARTS = {"reb": ("reb",), "ast": ("ast",), "stl": ("stl",), "blk": ("blk",), "tov": ("tov",),
         "reb_ast": ("reb", "ast"), "pra": ("reb", "ast"), "pts_reb": ("reb",),
         "pts_ast": ("ast",)}
LABEL = {"reb": "rebounds", "ast": "assists", "stl": "steals", "blk": "blocks", "tov": "turnovers"}


def enabled() -> bool:
    """On unless ``QB_NBA_RATES`` says off or the box's own check filed a
    verdict that did not hold (engine/nba/switches)."""
    try:
        from .switches import is_on
        return is_on("rates")
    except Exception:                                       # noqa: BLE001
        return True


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def sums(games) -> dict:
    """``{stat: (total, minutes)}`` over the games that stored the stat — a
    missing row is not a zero."""
    out = {}
    for k in KEYS:
        v_tot = m_tot = 0.0
        for g in games or []:
            v = _num((g or {}).get(k))
            m = _num((g or {}).get("min"))
            if v is None or m is None or m <= 0:
                continue
            v_tot += v
            m_tot += m
        out[k] = (v_tot, m_tot)
    return out


def bundle(recent, recent_dates, longrun, starter) -> dict | None:
    """What a prop carries for the read: ``{"recent", "older", "starter"}``.

    ``recent`` the games his rate is read from (newest first, each a stored
    game ``{market: value}``) on ``recent_dates``; ``longrun`` his last
    LONG_GAMES games any club, newest first, as ``(date, game)``; the older
    games are those of it not among the recent. None when nothing to read."""
    if not recent:
        return None
    seen = {str(d) for d in (recent_dates or [])}
    older = [g for d, g in (longrun or []) if str(d) not in seen]
    return {"recent": sums(recent), "older": sums(older), "starter": bool(starter)}


def blended(stat: str, read: dict | None):
    """``(raw, read)`` rates a minute for one stat, or None when the recent
    games never stored it."""
    if not read or stat not in PARAMS:
        return None
    v_r, m_r = (read.get("recent") or {}).get(stat) or (0.0, 0.0)
    if m_r <= 0:
        return None
    v_o, m_o = (read.get("older") or {}).get(stat) or (0.0, 0.0)
    w, kappa = PARAMS[stat]
    prior = LEAGUE[bool(read.get("starter"))][stat]
    den = m_r + w * m_o + kappa
    return v_r / m_r, (v_r + w * v_o + kappa * prior) / den


def projection_mult(stat: str, rate: float, read: dict | None,
                    league_key: str = "nba") -> tuple[float, str]:
    """``(multiplier, note)`` on a projection whose rate a minute is
    ``rate`` (after the shooting read): the parts this step reads swapped
    from his twenty games' rate to the read past them. (1.0, "") when off,
    unmeasured, or nothing to read."""
    parts = PARTS.get(stat)
    if (not parts or league_key not in LEAGUES or not read or not rate
            or rate <= 0 or not enabled()):
        return 1.0, ""
    raw = new = 0.0
    shown = []
    for p in parts:
        b = blended(p, read)
        if b is None:
            return 1.0, ""
        raw += b[0]
        new += b[1]
        shown.append((p, b))
    rate_new = rate - raw + new
    if rate_new <= 0:
        return 1.0, ""
    m = rate_new / rate
    tail = ("his older games and his role's league rate in it "
            "(measured: closer on a season it never saw)")
    if len(shown) == 1:
        p, (r0, r1) = shown[0]
        note = (f"His {LABEL[p]} read past his last {WINDOW} games: {r1 * 36:.1f} a 36 minutes, "
                f"not {r0 * 36:.1f} — {tail}")
    else:
        note = (f"His {' and '.join(LABEL[p] for p, _b in shown)} read past his last {WINDOW} games — "
                f"{tail}")
    return m, note


def lift_zero(stat: str, read: dict | None, league_key: str = "nba") -> tuple:
    """``(rate, note)`` for a single stat his twenty games never once
    recorded — a guard's blocks, a bench man's steals — or ``(None, "")``.
    A multiplier cannot lift a zero, and a rate of nothing calls the under a
    certainty the longer read says it is not; the lab's measurement counted
    these men too."""
    parts = PARTS.get(stat)
    if (not parts or len(parts) != 1 or league_key not in LEAGUES or not read
            or not enabled()):
        return None, ""
    b = blended(parts[0], read)
    if b is None or b[0] > 0 or b[1] <= 0:
        return None, ""
    return b[1], (f"No {LABEL[parts[0]]} in his last {WINDOW} games: read past them at "
                  f"{b[1] * 36:.2f} a 36 minutes, his older games and his role's league rate in it "
                  f"(measured: closer on a season it never saw)")


def longrun(conn, sport: str, players, n: int = LONG_GAMES, before: str | None = None) -> dict:
    """``{player: [(date, stored game), ...] newest first}`` — his last ``n``
    games, any club, any season (``before`` an ISO date to read history as
    of then). One query for every name asked."""
    names = sorted({p for p in players if p})
    if not names:
        return {}
    cols = ("min",) + KEYS
    q = ("SELECT player, period, market, value FROM player_game_logs WHERE sport=? "
         "AND market IN (%s) AND player IN (%s)" % (",".join("?" * len(cols)), ",".join("?" * len(names))))
    args = [sport, *cols, *names]
    if before:
        q += " AND period < ?"
        args.append(before)
    games: dict = {}
    for r in conn.execute(q, args):
        games.setdefault(r[0], {}).setdefault(str(r[1]), {})[r[2]] = r[3]
    out = {}
    for p, by_day in games.items():
        days = [d for d in sorted(by_day, reverse=True) if float(by_day[d].get("min") or 0.0) > 0][:n]
        out[p] = [(d, by_day[d]) for d in days]
    return out
