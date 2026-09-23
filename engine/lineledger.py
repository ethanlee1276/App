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

    PREFER `record_note` IN A BUILD. This returns 0 both when there was
    nothing to write and when the write threw, and those are opposite
    facts — see that function's docstring for what that cost.
    """
    return _write(conn, sport, games, now)[0]


def _write(conn, sport: str, games, now=None) -> tuple:
    """``(rows_stored, books, error)`` — the whole truth, once, so
    `record` and `record_note` can never disagree about what happened."""
    try:
        from . import db
        rows = rows_for_games(sport, games, now)
        if not rows:
            return 0, {}, ""
        books: dict = {}
        for r in rows:
            books[r["book"]] = books.get(r["book"], 0) + 1
        return db.upsert_odds_history(conn, rows), books, ""
    except Exception as exc:                                  # noqa: BLE001
        return 0, {}, f"{type(exc).__name__}: {exc}"


def record_note(conn, sport: str, games, now: _dt.datetime | None = None) -> str:
    """`record`, plus the sentence the build prints. Never raises.

    THE HOLE THIS CLOSES, and it is the one this repository keeps
    digging. `record` returns 0 when the write threw and 0 when there
    was simply nothing to write, and two of the three builds then wrapped
    the call in `except Exception: pass` and printed nothing at all — a
    DOUBLE silence. A harvest broken on the day it shipped would have
    looked exactly like a quiet Tuesday for as long as nobody went
    looking, which is the same failure shape as the rankings section that
    returned "" for a month (tests/test_rankings_never_silent.py) and the
    Live tab that could not tell "nothing on" from "the feed failed".
    Ethan, 2026-09-15, on the sharp closes this table is supposed to be
    collecting: "is there anything else you can work on for this". This.

    THE SHARP BOOK IS NAMED SEPARATELY on purpose. Rows stored is not the
    number that matters — `SHARP_BOOK` rows are, because the whole
    sharp-anchor measurement is the comparison between those and the
    shopped field (engine/gamebacktest.backtest_sharp_anchor). A build
    writing 40 rows of which zero are Pinnacle's is a build that looks
    healthy and collects nothing we can measure with.
    """
    n, books, error = _write(conn, sport, games, now)
    league = sport.upper()
    if error:
        return f"  ⚠️  {league} line ledger FAILED — nothing stored: {error}"
    if not n:
        return (f"  {league} line ledger: nothing to store — no game on the "
                f"slate carried a book price")
    sharp = books.get(SHARP_BOOK, 0)
    shopped = books.get(BEST_BOOK, 0)
    tail = (f"{sharp} from {SHARP_BOOK}" if sharp else
            f"NONE from {SHARP_BOOK} — the sharp pair is not reaching the "
            f"games, so the anchor cannot be measured")
    return (f"  {league} line ledger: {n} row(s) stored free — "
            f"{shopped} shopped, {tail}.")


def closes_into_games(conn, sport: str, games) -> dict:
    """Write each FINISHED game's last pre-kickoff line from this tape into
    the games table, where the models and the grading read closes.

    WHY (Ethan's droplet, 2026-09-23): college closes read
    ``[(2022, 951), (2023, 939), (2024, 861), (2025, 860), (2026, 0)]``.
    Every past season comes from cfbfastR's cfb_line_odds.csv, whose newest
    row is 2026-01-20 — it publishes after a season, not during one. The
    2026 closes were never missing; `record` has written every college game
    line the build paid for since this module shipped. Nothing copied them
    to where `gamecal`, `cfbtdfit` and the settle read.

    Only snapshots taken BEFORE kickoff count (a line priced during the game
    is not a close), only the shopped field (`BEST_BOOK`), and only where
    the game has no close yet — a published close beats our own tape.
    ``games`` are the build's own dicts: ``completed``, ``kickoff`` (ISO),
    ``date``, ``home``, ``away``, ``game_id``, ``season``.
    Returns {"games", "spread", "total", "ml"}.
    """
    import json as _json
    out = {"games": 0, "spread": 0, "total": 0, "ml": 0}
    for g in games or []:
        if not g.get("completed") or not g.get("kickoff"):
            continue
        try:
            kick = _dt.datetime.fromisoformat(str(g["kickoff"]).replace("Z", "+00:00"))
        except ValueError:
            continue
        if kick.tzinfo is None:
            continue
        cut = kick.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:00Z")
        home, away = g.get("home") or "", g.get("away") or ""
        event_id = f"{str(g.get('date') or '')[:10]}-{away}@{home}"
        last: dict = {}
        for r in conn.execute(
                "SELECT market, player, line, over_odds FROM odds_history WHERE sport=? AND "
                "event_id=? AND book=? AND market IN ('spread','total','moneyline') AND taken_at<? "
                "ORDER BY taken_at", (sport, event_id, BEST_BOOK, cut)):
            last[(r[0], r[1])] = (r[2], r[3])
        if not last:
            continue
        key = (sport, g.get("season") or 0, g.get("date") or "", g["game_id"])
        wrote = False
        for market, player, column in (("spread", home, "spread"), ("total", TOTAL_KEY, "total")):
            got = last.get((market, player))
            if got is None or got[0] is None:
                continue
            cur = conn.execute(
                f"UPDATE games SET {column}=? WHERE sport=? AND season=? AND period=? AND game_id=? "
                f"AND {column} IS NULL", (float(got[0]), *key))
            out[column] += cur.rowcount
            wrote = wrote or cur.rowcount > 0
        hm, am = last.get(("moneyline", home)), last.get(("moneyline", away))
        if hm and am and hm[1] and am[1]:
            row = conn.execute("SELECT extra FROM games WHERE sport=? AND season=? AND period=? "
                               "AND game_id=?", key).fetchone()
            if row is not None:
                try:
                    extra = _json.loads(row[0] or "{}") or {}
                except ValueError:
                    extra = {}
                if "ml" not in extra:
                    extra["ml"] = [int(hm[1]), int(am[1])]
                    extra["ml_source"] = "tape"
                    conn.execute("UPDATE games SET extra=? WHERE sport=? AND season=? AND period=? "
                                 "AND game_id=?", (_json.dumps(extra, separators=(",", ":")), *key))
                    out["ml"] += 1
                    wrote = True
        out["games"] += int(wrote)
    conn.commit()
    return out
