"""Does the off-board read tell the truth? Measured on seasons already played.

Ethan, 2026-10-13, after the read shipped (engine/slipread): a number such
as "ours 88%" on a leg no board carries is only worth printing if 88% is
what such legs do. This replays the read on finished seasons and reports
whether its numbers hit. It is a report and never a change: nothing here
writes a parameter, and the history database is read, not written.

THE REPLAY, football (NFL and college). Every player-game in the seasons
asked for, in the seven markets a book hangs most, where the player had a
prop-sized role going in (his trailing average over FLOORS, the line
engine/proplivefit draws): the SHIPPING ARITHMETIC — slipread.football,
then slipgrade.prob_at_line, the two calls the parlay checker makes — is
asked AS OF that game: his games before it, the defence rated on the weeks
before it, last season as the anchor, the game's own spread, total and
weather off the games table. What the replay leaves out that the checker
does: resolving the slip's spelling of his name (the stored name is used),
the injury list (none is kept for past games, so no teammate or
quarterback is ever out in a replay; the depth order and his measured
volume role are read as of the week), and holding the number to the
Most Likely list's record (slipgrade._honest is the journal's live
correction; this measures the raw model).

THE LINES. No book's prop lines are kept for past games, so each
player-game is priced at a BOOK-LIKE line — his trailing average to the
half below, where a book hangs it — and at a LADDER of four more around
the read's own projection (half and one spread either side), so every
band of the scale gets its turn: a read that says 75% should land 75%
whether the 75% came from a soft number or a hard one.

WHAT IT REPORTS, per market: how many player-games, the over rate, Brier
and log loss for the read ("ours") against a stand-in any bettor could
make — his last eight games' average and spread as a normal ("last8") —
and the read's calibration: of the times it said 60-70%, how often the
over landed. "ours" beating "last8" on Brier is the read earning its
place; a calibration row where "said" and "landed" part by more than the
noise is the finding to put in front of Ethan, not a change this makes.

    python3 -m engine.slipreadfit --sport nfl --seasons 2023 2024 2025
    python3 -m engine.slipreadfit --sport cfb --seasons 2024 2025 --limit 3000
    python3 -m engine.slipreadfit --json data/slipreadfit.json

Standard library only.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import sys
from collections import defaultdict

from .proplivefit import FLOORS, _stand_in, calibration, _clamp

#: The markets a book hangs most, and the read prices as the board does.
MARKETS = ("rec_yds", "receptions", "rush_yds", "rush_att", "pass_yds", "pass_att", "pass_cmp")
#: The ladder around the read's projection, in spreads.
LADDER = (-1.0, -0.5, 0.5, 1.0)
ARMS = ("ours", "last8")


def _half(x: float) -> float:
    """A number a push cannot land on: the half below."""
    return math.floor(x) + 0.5


def _normal_over(line: float, mean: float, sd: float) -> float:
    """The stand-in's chance of the over: a normal on his last games."""
    sd = max(float(sd), 1e-6)
    return _clamp(0.5 * math.erfc((float(line) - float(mean)) / (sd * math.sqrt(2.0))))


# ---- the history, as the read stores it ----------------------------------------
def _logs(conn, sport: str, seasons, market: str) -> dict:
    """{player: [his games in the market, oldest first]} over the seasons
    replayed and the one before them (the stand-in's history). The first
    stored alternative with rows wins, as slipread.games reads him; a sum
    adds what each game stored."""
    from .slipread import FOOTBALL_LOGS, _pkey
    look = sorted(set(int(s) for s in seasons) | {min(int(s) for s in seasons) - 1})
    for alt in FOOTBALL_LOGS[market]:
        marks = ",".join("?" * len(alt))
        sm = ",".join("?" * len(look))
        rows = conn.execute(
            f"SELECT season, period, game_id, player, team, opponent, position, home, value "
            f"FROM player_game_logs WHERE sport=? AND market IN ({marks}) AND season IN ({sm})",
            (sport, *alt, *look)).fetchall()
        if not rows:
            continue
        by: dict = {}
        for r in rows:
            k = (str(r[3]), int(r[0] or 0), str(r[1] or ""), str(r[2] or ""))
            g = by.get(k)
            if g is None:
                g = by[k] = {"player": k[0], "season": k[1], "period": k[2], "game_id": k[3],
                             "team": str(r[4] or ""), "opponent": str(r[5] or ""),
                             "position": str(r[6] or "").upper(), "home": bool(r[7]), "value": 0.0}
            g["value"] += float(r[8] or 0.0)
        out: dict = defaultdict(list)
        for g in by.values():
            out[g["player"]].append(g)
        for seq in out.values():
            seq.sort(key=lambda g: _pkey(g["season"], g["period"]))
        return dict(out)
    return {}


def _card(conn, sport: str, g: dict, cache: dict) -> dict | None:
    """The game's card as the board would carry it, off the games table:
    spread (home, negative when home is favoured — the engine's sign, as
    the ingest stores it), total, roof and weather. None when the table
    has no row for it; the read then prices as it does for a game no
    board has posted."""
    k = (g["season"], g["period"], g["game_id"])
    if k in cache:
        return cache[k]
    r = conn.execute("SELECT home, away, spread, total, roof, surface, temp, wind, date FROM games "
                     "WHERE sport=? AND season=? AND period=? AND game_id=?",
                     (sport, g["season"], g["period"], g["game_id"])).fetchone()
    card = None
    if r:
        roof = str(r[4] or "").lower()
        card = {"home": str(r[0] or ""), "away": str(r[1] or ""), "date": str(r[8] or ""), "roof": roof,
                "surface": str(r[5] or "grass"), "spread": r[2], "total": r[3],
                "total_measured": r[3] is not None, "spread_measured": r[2] is not None,
                "weather": {"dome": roof in ("dome", "closed"), "temp_f": r[6], "wind_mph": r[7],
                            "measured": r[6] is not None or r[7] is not None}}
    cache[k] = card
    return card


# ---- the replay -----------------------------------------------------------------
def replay(conn, sport: str, seasons, markets=MARKETS, limit: int | None = None, progress=None) -> list[dict]:
    """One row per player-game, market and line: the read's chance for
    the over ("ours"), the stand-in's ("last8") and whether it landed.
    ``limit`` caps the reads made (a quick look); ``progress(n)`` is
    called every 500."""
    from . import slipread as SR
    from . import slipgrade as SG
    seasons = [int(s) for s in seasons]
    out: list[dict] = []
    cards: dict = {}
    reads = errors = 0
    for market in markets:
        for player, seq in _logs(conn, sport, seasons, market).items():
            history: list[float] = []
            for g in seq:
                final = float(g["value"])
                if g["season"] in seasons:
                    got = _stand_in(history)
                    if got is not None:
                        mean, sd = got
                        if mean >= FLOORS.get(market, 0.0) and mean > 0:
                            if limit is not None and reads >= limit:
                                return out
                            card = _card(conn, sport, g, cards)
                            board = {"date": (card or {}).get("date") or "", "games": [card] if card else []}
                            home = (card or {}).get("home") or (g["team"] if g["home"] else g["opponent"])
                            away = (card or {}).get("away") or (g["opponent"] if g["home"] else g["team"])
                            book = _half(mean)
                            leg = {"sport": sport, "player": player, "team": g["team"], "market": market,
                                   "side": "over", "line": book, "odds": -110, "game": f"{away} @ {home}"}
                            who = {"player": player, "team": g["team"], "position": g["position"]}
                            reads += 1
                            if progress and reads % 500 == 0:
                                progress(reads)
                            try:
                                row = SR.football(conn, board, sport, leg, who, asof=(g["season"], g["period"]))
                            except Exception:                              # noqa: BLE001
                                errors += 1
                                row = None
                            if row and row.get("projection") is not None:
                                proj = float(row["projection"])
                                spread = float(row.get("proj_std") or 0.0) or sd
                                lines = [("book", book)] + [("ladder", _half(proj + k * spread)) for k in LADDER]
                                seen = set()
                                for arm, line in lines:
                                    if line < 0.5 or line in seen or final == line:
                                        continue
                                    seen.add(line)
                                    p = SG.prob_at_line(row, market, "over", line)
                                    if p is None:
                                        continue
                                    out.append({"market": market, "player": player, "season": g["season"],
                                                "period": g["period"], "arm": arm, "line": line,
                                                "ours": _clamp(p), "last8": _normal_over(line, mean, sd),
                                                "hit": 1 if final > line else 0,
                                                "games": len(row.get("logs") or []),
                                                "posted": bool(card and card.get("total") is not None)})
                history.append(final)
    out_errors = errors
    if out_errors and progress:
        progress(-out_errors)
    return out


# ---- the score ------------------------------------------------------------------
def _score_rows(rs: list[dict]) -> dict:
    n = len(rs)
    brier = {a: round(sum((r[a] - r["hit"]) ** 2 for r in rs) / n, 4) for a in ARMS}
    ll = -sum(math.log(_clamp(r["ours"])) if r["hit"] else math.log(1.0 - _clamp(r["ours"])) for r in rs) / n
    return {"n": n, "rate": round(sum(r["hit"] for r in rs) / n, 4), "brier": brier,
            "logloss": round(ll, 4), "calibration": calibration(rs, "ours")}


def score(rows: list[dict]) -> dict:
    """{market: {"book": …, "ladder": …, "all": …, "seasons": {season: …}}},
    each a {n, rate, brier: {ours, last8}, logloss, calibration}."""
    groups: dict = defaultdict(list)
    for r in rows:
        groups[r["market"]].append(r)
    out: dict = {}
    for market, rs in groups.items():
        cell: dict = {}
        for arm in ("book", "ladder"):
            sub = [r for r in rs if r["arm"] == arm]
            if sub:
                cell[arm] = _score_rows(sub)
        cell["all"] = _score_rows(rs)
        cell["seasons"] = {}
        for season in sorted({r["season"] for r in rs}):
            sub = [r for r in rs if r["season"] == season and r["arm"] == "book"]
            if sub:
                cell["seasons"][str(season)] = _score_rows(sub)
        out[market] = cell
    return out


def report(scored: dict, title: str) -> str:
    """The table a person reads."""
    lines = [title, ""]
    for market in sorted(scored):
        cell = scored[market]
        lines.append(f"{market}  ({cell['all']['n']:,} priced lines over {cell.get('book', cell['all'])['n']:,} "
                     f"player-games)")
        lines.append("  lines      n       over%   Brier: ours   last8    log loss")
        for arm in ("book", "ladder", "all"):
            v = cell.get(arm)
            if not v:
                continue
            b = v["brier"]
            lines.append(f"  {arm:<8}{v['n']:>7,}   {v['rate']:>6.1%}   {b['ours']:>10.4f}   {b['last8']:.4f}   "
                         f"{v['logloss']:.4f}")
        for arm in ("book", "all"):
            v = cell.get(arm)
            if not v:
                continue
            cal = " · ".join(f"{c['from']:.0%}-{c['to']:.0%}: said {c['said']:.0%}, landed {c['landed']:.0%} of {c['n']}"
                             for c in v["calibration"] if c["n"] >= 20)
            if cal:
                lines.append(f"  calibration, {arm}: {cal}")
        by_season = cell.get("seasons") or {}
        if len(by_season) > 1:
            lines.append("  by season, book lines: " + " · ".join(
                f"{s}: n {v['n']:,}, Brier ours {v['brier']['ours']:.4f} / last8 {v['brier']['last8']:.4f}"
                for s, v in by_season.items()))
        lines.append("")
    lines.append("Brier and log loss: lower is better. 'ours' is the read the parlay checker prints for a leg no")
    lines.append("board carries; 'last8' is his last eight games' average and spread as a normal. 'book' prices")
    lines.append("each player-game at his trailing average to the half below; 'ladder' at four numbers around")
    lines.append("the read's projection. Calibration: of the times we said that range, how often the over")
    lines.append("landed. Nothing here changes the model.")
    return "\n".join(lines)


# ---- the box command -------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Replay the off-board read on finished seasons; a report, never a change.")
    ap.add_argument("--sport", default="nfl", choices=("nfl", "cfb"))
    ap.add_argument("--seasons", nargs="+", type=int, default=[2023, 2024, 2025])
    ap.add_argument("--markets", nargs="+", default=list(MARKETS))
    ap.add_argument("--limit", type=int, default=None, help="cap the reads (a quick look)")
    ap.add_argument("--json", default=None, help="also write the rows and the tables here")
    ap.add_argument("--db", default=None, help="the history database (the box's by default)")
    a = ap.parse_args(argv)
    from . import db as DB
    from . import slipread as SR
    conn = DB.connect(a.db) if a.db else DB.connect()
    try:
        SR.clear_cache()
        rows = replay(conn, a.sport, a.seasons, tuple(a.markets), limit=a.limit,
                      progress=lambda n: print(f"  {n:,} reads…" if n > 0 else f"  {-n:,} read(s) failed and were skipped",
                                               file=sys.stderr))
    finally:
        conn.close()
    reads = len({(r["market"], r["player"], r["season"], r["period"]) for r in rows})
    scored = score(rows)
    title = (f"The off-board read replayed: {a.sport.upper()} {min(a.seasons)}-{max(a.seasons)}, "
             f"{reads:,} player-game reads, {len(rows):,} priced lines")
    print(report(scored, title) if rows else f"{title}\n\nnothing to replay: no games stored for those seasons")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump({"sport": a.sport, "seasons": sorted(a.seasons), "markets": list(a.markets),
                       "reads": reads, "rows": rows, "scored": scored,
                       "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")},
                      fh, indent=1)
        print(f"\nwritten: {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
