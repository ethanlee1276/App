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

#: The shopped field, as one row. Every book that quoted the side went into
#: choosing it, and which book won is not recoverable from the number.
BEST_BOOK = "best"

#: THE SHARP BOOK, WRITTEN DOWN. Every measured edge in this repository is a
#: comparison of two prices — the sharp anchor (+13.5% on the MLB replay) and
#: the stale-line flag (64.8% CLV on 30,448 quotes) are both "this book
#: against that book" — and the second half of both comparisons was being
#: discarded on every build. `apply_odds_to_slate` and
#: `apply_board_lines_to_slate` each parse the sharp book's own two-sided
#: pair and hang it on the game (`sharp_home_ml`, `sharp_total`,
#: `sharp_spread` and their prices); cfb_build parses the same pair into its
#: entry's `sharp` key. All of it was in memory and none of it was stored,
#: so the tape held one shopped number per game per minute and nothing to
#: compare it against.
#:
#: Spelled as the API's DISPLAY title because that is what the historical
#: harvest writes (`oddshistory.to_rows` stores `SportsbookLine.book`, which
#: `_parse_lines` fills from `BOOK_TITLES`). A build row and a harvest row
#: for the same book must carry the same spelling or the two halves of the
#: tape never join — tests/test_sharp_price_tape.py pins them equal.
SHARP_BOOK = "Pinnacle"


def _stamp(now: _dt.datetime | None = None) -> str:
    """Minute resolution. Second resolution would make every build a new
    primary key and turn a season of one game into a million rows."""
    n = now or _dt.datetime.now(_dt.timezone.utc)
    return n.strftime("%Y-%m-%dT%H:%M:00Z")


def _f(g, name, default=None):
    """One field off a game, whether it is an object or a mapping.

    MLB and NFL hand over Game dataclasses; CFB's board is plain dicts
    with its prices in a side map. Reading both here beats a per-sport
    copy of this whole function — the ROWS are identical either way.
    """
    if isinstance(g, dict):
        v = g.get(name, default)
    else:
        v = getattr(g, name, default)
    return default if v is None else v


def rows_for_games(sport: str, games, now: _dt.datetime | None = None) -> list[dict]:
    """``odds_history`` rows for every game carrying a real book number.

    A game with no attached price contributes nothing — writing a row of
    Nones would make "we never saw a line" and "the line was even" the same
    stored fact, which is the exact confusion this table exists to prevent.
    """
    taken = _stamp(now)
    out: list[dict] = []
    for g in games:
        home = _f(g, "home", "") or ""
        away = _f(g, "away", "") or ""
        if not home or not away:
            continue
        date = str(_f(g, "date", "") or "")[:10]
        event_id = f"{date}-{away}@{home}"
        base = {"sport": sport, "taken_at": taken, "event_id": event_id,
                "home": home, "away": away, "book": BEST_BOOK}

        total = _f(g, "total")
        if total is not None:
            out.append({**base, "player": TOTAL_KEY, "market": "total",
                        "line": float(total),
                        "over_odds": _f(g, "total_over_odds"),
                        "under_odds": _f(g, "total_under_odds")})

        spread = _f(g, "spread")
        # 0.0 is a real pick'em line, so test for None rather than falsiness.
        if spread is not None:
            out.append({**base, "player": home, "market": "spread",
                        "line": float(spread),
                        "over_odds": _f(g, "spread_home_odds"),
                        "under_odds": _f(g, "spread_away_odds")})

        home_ml, away_ml = _f(g, "home_ml"), _f(g, "away_ml")
        if home_ml and away_ml:
            for team, price in ((home, home_ml), (away, away_ml)):
                out.append({**base, "player": team, "market": "moneyline",
                            "line": 0.0, "over_odds": int(price),
                            "under_odds": None})

        # THE SHARP BOOK'S OWN PAIR, beside the shopped field. Same rows,
        # same event key, a different `book` — so the tape reads back as two
        # series a comparison can be drawn between.
        #
        # A PRICE IS THE EVIDENCE A BOOK POSTED THE NUMBER, which is the
        # `Game.total_is_posted` rule applied here. The sharp fields default
        # to 0.0 and a real pick'em spread is also 0.0, so the LINE cannot
        # say whether anyone quoted it; the two-sided pair can, and a
        # one-sided quote is not a number this table should carry.
        s_total = _f(g, "sharp_total")
        s_over, s_under = (_f(g, "sharp_total_over_odds"),
                           _f(g, "sharp_total_under_odds"))
        if s_total and s_over and s_under:
            out.append({**base, "book": SHARP_BOOK, "player": TOTAL_KEY,
                        "market": "total", "line": float(s_total),
                        "over_odds": int(s_over), "under_odds": int(s_under)})

        s_spread = _f(g, "sharp_spread")
        s_home, s_away = (_f(g, "sharp_spread_home_odds"),
                          _f(g, "sharp_spread_away_odds"))
        if s_spread is not None and s_home and s_away:
            out.append({**base, "book": SHARP_BOOK, "player": home,
                        "market": "spread", "line": float(s_spread),
                        "over_odds": int(s_home), "under_odds": int(s_away)})

        s_hml, s_aml = _f(g, "sharp_home_ml"), _f(g, "sharp_away_ml")
        if s_hml and s_aml:
            for team, price in ((home, s_hml), (away, s_aml)):
                out.append({**base, "book": SHARP_BOOK, "player": team,
                            "market": "moneyline", "line": 0.0,
                            "over_odds": int(price), "under_odds": None})
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
