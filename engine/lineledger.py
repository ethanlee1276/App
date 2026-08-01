"""Keep the game lines the build already paid for.

The daily build asks the odds API for ``h2h, spreads, totals`` on every
game, attaches all three to the slate, prices bets off them — and then
throws two of the three away. Player props and moneylines were journaled to
``odds_history``; spreads and totals were not stored anywhere.

That is why the spread/total model has never been graded. A backtest needs
the number the market actually closed at, and there wasn't one: the
database held six seasons of props and not a single stored game total. The
model could be argued about but not measured, which is the state every
other layer in this project has been dragged out of.

Nothing here costs an API credit. The prices are already in memory when
this runs; the only thing that was missing was writing them down.

Snapshots are keyed by (sport, taken_at, event_id, player, market, book),
so a build every 60 seconds does NOT write 1,440 rows a day per game — it
writes one row per distinct minute the number was observed, and the
backtest takes the last snapshot before first pitch as the close. Storing
the movement is a feature: it is the same table the CLV tracking reads.
"""

from __future__ import annotations

import datetime as _dt

#: Markets written here. `player` carries the side's identity — the team for
#: a spread, the literal "TOTAL" for a game total — so one table shape
#: serves props, moneylines and game lines alike.
TOTAL_KEY = "TOTAL"


def _stamp(now: _dt.datetime | None = None) -> str:
    """Minute resolution. Second resolution would make every build a new
    primary key and turn a season of one game into a million rows."""
    n = now or _dt.datetime.now(_dt.timezone.utc)
    return n.strftime("%Y-%m-%dT%H:%M:00Z")


def rows_for_games(sport: str, games, now: _dt.datetime | None = None) -> list[dict]:
    """``odds_history`` rows for every game carrying a real book number.

    A game with no attached price contributes nothing — writing a row of
    Nones would make "we never saw a line" and "the line was even" the same
    stored fact, which is the exact confusion this table exists to prevent.
    """
    taken = _stamp(now)
    out: list[dict] = []
    for g in games:
        home = getattr(g, "home", "") or ""
        away = getattr(g, "away", "") or ""
        if not home or not away:
            continue
        date = str(getattr(g, "date", "") or "")[:10]
        event_id = f"{date}-{away}@{home}"
        base = {"sport": sport, "taken_at": taken, "event_id": event_id,
                "home": home, "away": away, "book": "best"}

        total = getattr(g, "total", None)
        if total is not None:
            out.append({**base, "player": TOTAL_KEY, "market": "total",
                        "line": float(total),
                        "over_odds": getattr(g, "total_over_odds", None),
                        "under_odds": getattr(g, "total_under_odds", None)})

        spread = getattr(g, "spread", None)
        # 0.0 is a real pick'em line, so test for None rather than falsiness.
        if spread is not None:
            out.append({**base, "player": home, "market": "spread",
                        "line": float(spread),
                        "over_odds": getattr(g, "spread_home_odds", None),
                        "under_odds": getattr(g, "spread_away_odds", None)})

        home_ml, away_ml = getattr(g, "home_ml", None), getattr(g, "away_ml", None)
        if home_ml and away_ml:
            for team, price in ((home, home_ml), (away, away_ml)):
                out.append({**base, "player": team, "market": "moneyline",
                            "line": 0.0, "over_odds": int(price),
                            "under_odds": None})
    return out


def record(conn, sport: str, games, now: _dt.datetime | None = None) -> int:
    """Write today's game lines. Returns rows stored.

    Never raises into a build: a betting board that fails because its
    telemetry could not write is a board that goes dark for the least
    important reason available.
    """
    try:
        from . import db
        rows = rows_for_games(sport, games, now)
        if not rows:
            return 0
        return db.upsert_odds_history(conn, rows)
    except Exception:
        return 0
