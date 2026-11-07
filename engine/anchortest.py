"""Would Caesars make a backup sharp book? Every book tried as the anchor.

Ethan, 2026-11-03, "5, yes": test Caesars as a backup reference for where
Pinnacle has no price, and change nothing unless it wins. Caesars measures
among the most accurate books against the close (engine/booksharp, 11,920
lines), but accuracy against the close is not the job. The job is the one
Pinnacle does on the NBA and NHL boards and the football cards: its
de-vigged pair is the fair chance, the best price a reader can take at
another book is held against it, and a gap of SHARP_MIN_EV to SHARP_MAX_EV
is a bet (`betting.sharp_anchor_for`, `sharpvalue.sharp_value`).

WHAT THE BOX CAN ANSWER. Pinnacle's prop pairs were never stored: the
harvest and the tapes keep the books a reader can bet
(`oddsapi.parse_event_lines`). So this cannot put Caesars beside Pinnacle
on the same props. It asks the question that decides a backup instead:
used as the anchor the same way, do Caesars' prices find bets that win at
the other books, and do they do it better than every other book would?

For every stored pre-game close (each book's last quote of the day before
its game) with a result in player_game_logs:

  ANCHOR BETS   each book in turn is the anchor: its two-way pair at a
                line, de-vigged; the best price at any OTHER book on each
                side of that line (the anchor itself and the sharp book
                never count as the price to take); one unit when the EV is
                inside the bands. Graded on the result; a push is no bet.
  CALIBRATION   where the anchor and at least two other books quote both
                sides of the same line: the anchor's fair against the other
                books' average fair, log loss on the same results, paired.

Both t-statistics are taken across DAYS, not bets: a day's props share its
games, so bets on one day are not independent draws.

THE BAR, WRITTEN BEFORE ITS FIRST RUN. Caesars "holds as a backup" in a
sport when, on that sport's anchor bets:
  1. it made at least MIN_BETS bets,
  2. their ROI is above zero with t >= MIN_T,
  3. its fair beats the other books' average on log loss with t >= MIN_T,
  4. and no book tried has a higher ROI on at least MIN_BETS bets.
Otherwise it "does not hold". READ-ONLY: it opens history.db read-only and
writes nothing; wiring a backup anchor into pricing waits on Ethan's yes.

    python3 -m engine.anchortest              # every sport with stored closes
    python3 -m engine.anchortest nba nhl      # just these

Standard library only.
"""

from __future__ import annotations

import datetime as _dt
import math
import re

MIN_BETS = 200
MIN_T = 2.0
#: Books under this many anchor bets in a sport are listed, not ranked.
MIN_RANKED = MIN_BETS

#: The book this test is about, by every name a stored row has carried.
CANDIDATE = "caesars"
ALIASES = {"williamhillus": "caesars", "williamhill": "caesars",
           "espnbet": "thescorebet", "thescore": "thescorebet"}
#: Game markets and anything not a player's stat line: not this test's.
SKIP_MARKETS = {"moneyline", "spread", "total", "spreads", "totals", "h2h"}


def book_key(name) -> str:
    """One key per book whatever the row called it ("Caesars",
    "William Hill (US)", "williamhill_us" are one book)."""
    k = re.sub(r"[^a-z0-9]", "", str(name or "").lower())
    return ALIASES.get(k, k)


def _eastern_date(stamp) -> str | None:
    """The calendar day in New York of an ISO UTC stamp: the day the game
    is listed under, which a UTC date is not for a late tip."""
    if not stamp:
        return None
    try:
        t = _dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=_dt.timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        return t.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    except Exception:                                     # noqa: BLE001
        return (t - _dt.timedelta(hours=5)).date().isoformat()


def closes(conn, sport: str, market: str) -> dict:
    """``{(norm player, date): {line: {book: (over, under)}}}``: each book's
    last pre-game two-way quote of the day, keyed by the game's own day.

    The day is the game's start in New York when the row carries it, and
    the snapshot's date otherwise. Only rows with both sides quoted and a
    book that is not our own placeholder ("proxy") are kept."""
    from . import db as _db
    from .backtest import _norm
    # BY PLAYER, THEN TIME: the order of idx_odds_hist_lookup (sport, market,
    # player, taken_at), so SQLite walks the index instead of sorting a
    # season of quotes into a temp file on a disk that has filled before.
    # A later quote still replaces an earlier one, which is all the order
    # is for.
    rows = conn.execute(
        "SELECT player, book, line, over_odds, under_odds, taken_at"
        f"{_db._commence_sql(conn)} FROM odds_history WHERE sport=? AND market=? "
        "ORDER BY player, taken_at", (sport, market))
    out: dict = {}
    names: dict = {}
    for r in rows:
        if _db._in_play(r):
            continue
        book = book_key(r["book"])
        if not book or book in ("proxy", "best"):
            continue
        try:
            line = float(r["line"])
            over, under = int(r["over_odds"] or 0), int(r["under_odds"] or 0)
        except (TypeError, ValueError):
            continue
        if not over or not under:
            continue
        day = _eastern_date(_db._commence_of(r)) or str(r["taken_at"])[:10]
        raw = r["player"]
        player = names.get(raw)
        if player is None:
            player = names[raw] = _norm(raw)
        # Ordered by taken_at: a later quote of the same day replaces it.
        # Nested rather than one flat key: one market of a season is
        # hundreds of thousands of quotes on a box with a gigabyte.
        out.setdefault((player, day), {}).setdefault(line, {})[book] = (over, under)
    return out


def _iso(s) -> bool:
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", str(s or "")[:10])) and len(str(s)) >= 10


def results(conn, sport: str, market: str, nfl_dates=None) -> dict:
    """``{(norm player, date): value}`` from player_game_logs, dated by
    the games table, the period itself for the daily sports, or the NFL
    schedule (``nfl_dates``: {(season, week, team): date}, read lazily)."""
    from .backtest import _norm
    out: dict = {}
    q = ("SELECT l.player, l.value, l.season, l.period, l.team, g.date "
         "FROM player_game_logs l LEFT JOIN games g ON g.sport = l.sport "
         "AND g.season = l.season AND g.period = l.period AND g.game_id = l.game_id "
         "WHERE l.sport=? AND l.market=?")
    for player, value, season, period, team, gdate in conn.execute(q, (sport, market)):
        if value is None:
            continue
        day = None
        if _iso(gdate):
            day = str(gdate)[:10]
        elif _iso(period):
            day = str(period)[:10]
        elif sport == "nfl" and nfl_dates is not None:
            try:
                day = nfl_dates().get((int(season), int(period), team))
            except (TypeError, ValueError):
                day = None
        if day:
            out[(_norm(player), day)] = float(value)
    return out


def _quotable(o) -> bool:
    from .odds import is_quotable
    return bool(o) and is_quotable(o)


def _blank() -> dict:
    return {"bets": 0, "won": 0, "units": 0.0, "by_day": {},
            "ll_n": 0, "ll_diff": 0.0, "ll_by_day": {}}


def score_case(acc: dict, line: float, books: dict, value: float, day: str,
               sharp=None) -> None:
    """Every book at one (player, day, line) tried as the anchor, into
    ``acc`` ({book: tallies}). ``books``: {book: (over, under)}."""
    from .gamebets import SHARP_MAX_EV, SHARP_MIN_EV
    from .odds import american_to_decimal, devig_two_way, is_sharp_book
    sharp = sharp or is_sharp_book
    if value == line:
        return                                    # a push: no bet, no score
    over_won = value > line
    pairs = {b: q for b, q in books.items() if _quotable(q[0]) and _quotable(q[1])}
    fairs = {b: devig_two_way(int(q[0]), int(q[1]))[0] for b, q in pairs.items()}
    for anchor, fo in fairs.items():
        if sharp(anchor) or not 0.0 < fo < 1.0:
            continue
        t = acc.setdefault(anchor, _blank())
        # The price to take: the best at any other bettable book.
        best = {}
        for side, idx in (("over", 0), ("under", 1)):
            prices = [int(q[idx]) for b, q in books.items()
                      if b != anchor and not sharp(b) and _quotable(q[idx])]
            if prices:
                best[side] = max(prices)
        pick = None
        for side, fair in (("over", fo), ("under", 1.0 - fo)):
            if side not in best:
                continue
            ev = fair * american_to_decimal(best[side]) - 1.0
            if SHARP_MIN_EV <= ev <= SHARP_MAX_EV and (pick is None or ev > pick[2]):
                pick = (side, best[side], ev)
        if pick is not None:
            won = (pick[0] == "over") == over_won
            pnl = american_to_decimal(pick[1]) - 1.0 if won else -1.0
            t["bets"] += 1
            t["won"] += int(won)
            t["units"] += pnl
            d = t["by_day"].setdefault(day, [0, 0.0])
            d[0] += 1
            d[1] += pnl
        # Calibration: this book's fair against the others' average, paired.
        others = [f for b, f in fairs.items() if b != anchor and not sharp(b) and 0.0 < f < 1.0]
        if len(others) >= 2:
            mean = sum(others) / len(others)
            eps = 1e-6

            def ll(p):
                p = min(1 - eps, max(eps, p))
                return -math.log(p if over_won else 1.0 - p)
            diff = ll(fo) - ll(mean)
            t["ll_n"] += 1
            t["ll_diff"] += diff
            d = t["ll_by_day"].setdefault(day, [0, 0.0])
            d[0] += 1
            d[1] += diff


def _day_t(by_day: dict) -> float | None:
    """t of the per-day mean (units per bet, or log-loss gap per line)
    across days: mean / (sd / sqrt(days))."""
    xs = [s / n for n, s in by_day.values() if n]
    if len(xs) < 3:
        return None
    m = sum(xs) / len(xs)
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    if var <= 0:
        return None
    return m / math.sqrt(var / len(xs))


def summarize(acc: dict) -> list[dict]:
    rows = []
    for book, t in acc.items():
        n = t["bets"]
        rows.append({
            "book": book, "bets": n, "won": t["won"], "lost": n - t["won"],
            "units": round(t["units"], 2),
            "roi": round(t["units"] / n, 4) if n else None,
            "roi_t": _day_t(t["by_day"]),
            "ll_lines": t["ll_n"],
            "ll_gap": round(1000 * t["ll_diff"] / t["ll_n"], 2) if t["ll_n"] else None,
            "ll_t": _day_t(t["ll_by_day"]),
        })
    rows.sort(key=lambda r: (-(r["bets"] >= MIN_RANKED), -(r["roi"] or -9), r["book"]))
    return rows


def verdict(rows: list[dict], candidate: str = CANDIDATE) -> tuple[bool, str]:
    """The bar in the module docstring, for one sport's rows."""
    me = next((r for r in rows if r["book"] == candidate), None)
    if me is None or not me["bets"]:
        return False, f"{candidate} made no anchor bets"
    why = []
    if me["bets"] < MIN_BETS:
        why.append(f"{me['bets']} bets, under {MIN_BETS}")
    if not (me["roi"] or 0) > 0 or (me["roi_t"] or 0) < MIN_T:
        why.append(f"ROI {(me['roi'] or 0):+.1%} at t {(me['roi_t'] or 0):.1f} (needs > 0 at t ≥ {MIN_T:g})")
    if me["ll_gap"] is None or me["ll_gap"] >= 0 or -(me["ll_t"] or 0) < MIN_T:
        why.append("its fair does not beat the other books' average "
                   f"(log loss {me['ll_gap'] if me['ll_gap'] is not None else '—'} per 1,000 lines, "
                   f"t {(me['ll_t'] or 0):.1f})")
    better = [r["book"] for r in rows if r["book"] != candidate and r["bets"] >= MIN_RANKED
              and (r["roi"] or -9) > (me["roi"] or -9)]
    if better:
        why.append("a higher ROI as the anchor: " + ", ".join(better))
    return (not why), ("holds" if not why else "does not hold: " + "; ".join(why))


def run(conn, sports=None, say=print) -> dict:
    """Every sport's stored prop closes, every book as the anchor."""
    from functools import lru_cache
    have = conn.execute("SELECT DISTINCT sport, market FROM odds_history").fetchall()
    by_sport: dict = {}
    for sport, market in have:
        if sports and sport not in sports:
            continue
        if not market or str(market).lower() in SKIP_MARKETS:
            continue
        by_sport.setdefault(sport, []).append(market)

    @lru_cache(maxsize=1)
    def nfl_dates():
        from .formbook import game_dates
        return game_dates()
    report: dict = {}
    for sport in sorted(by_sport):
        acc: dict = {}
        lines = 0
        for market in sorted(by_sport[sport]):
            res = results(conn, sport, market, nfl_dates=nfl_dates)
            if not res:
                continue
            for (player, day), at in closes(conn, sport, market).items():
                value = res.get((player, day))
                if value is None:
                    continue
                for line, books in at.items():
                    if len(books) < 2:
                        continue
                    lines += 1
                    score_case(acc, line, books, value, day)
        rows = summarize(acc)
        ok, why = verdict(rows)
        report[sport] = {"lines": lines, "rows": rows, "holds": ok, "verdict": why}
        for ln in _lines(sport, report[sport]):
            say(ln)
    return report


def _lines(sport: str, rep: dict) -> list[str]:
    out = [f"{sport}: {rep['lines']:,} lines with two or more books and a result",
           f"    {'anchor':14} {'bets':>6} {'won-lost':>11} {'units':>8} {'ROI':>7} {'t':>5}"
           f"   {'log loss vs the rest':>21} {'t':>5}"]
    for r in rep["rows"]:
        roi = f"{r['roi']:+.1%}" if r["roi"] is not None else "—"
        rt = f"{r['roi_t']:.1f}" if r["roi_t"] is not None else "—"
        gap = f"{r['ll_gap']:+.1f}/1k on {r['ll_lines']:,}" if r["ll_gap"] is not None else "—"
        lt = f"{r['ll_t']:.1f}" if r["ll_t"] is not None else "—"
        mark = "  <-" if r["book"] == CANDIDATE else ""
        out.append(f"    {r['book']:14} {r['bets']:>6} {r['won']:>5}-{r['lost']:<5} "
                   f"{r['units']:>+8.2f} {roi:>7} {rt:>5}   {gap:>21} {lt:>5}{mark}")
    out.append(f"  Caesars as a backup anchor in {sport}: {rep['verdict']}")
    return out


def main(argv=None) -> int:
    import sqlite3
    import sys
    from . import db as _db
    from .gamebets import SHARP_MAX_EV, SHARP_MIN_EV
    argv = sys.argv[1:] if argv is None else argv
    conn = sqlite3.connect(f"file:{_db.DEFAULT_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    print("Anchor test: each book's de-vigged pair as the fair price, the best price "
          f"at another book bet at {SHARP_MIN_EV:.0%} to {SHARP_MAX_EV:.0%} EV, graded "
          "on the result. Read-only.")
    run(conn, sports=set(argv) or None)
    return 0


if __name__ == "__main__":                       # pragma: no cover
    raise SystemExit(main())
