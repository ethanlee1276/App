"""Walk-forward replay of the NBA / WNBA prop pricer over stored game logs.

Audit 2026-09-30, B1-1 (roadmap #34). The basketball boards priced props
every night and nothing replayed them: the Lab's coverage matrix said "no
walk-forward prop harness yet — projections ship unreplayed", and the
only calibration evidence for those two leagues was the forward journal
whose headline it was meant to check.

THE WALK. For every player-game in the history database, game i is priced
from games [:i] only — the twenty before it, newest first, the window the
live build reads (`nba_build.player_history`) — through the PRODUCTION
`engine.nba.pipeline.evaluate_prop`, and graded against what he did in
game i. Nothing is re-implemented here: the minutes model, the rate, the
calibration, the side choice and the gates are the board's own, so a
change to the pricer changes this replay the same day.

NEUTRAL CONTEXT, like its MLB and NFL siblings (`engine/mlb/backtest.py`,
`engine/logwalk.py`): no spread, no game total, no layoff, no defence
rating, rest "1day". This measures the form-and-minutes model and its
calibration, not the context layer.

THE PRICE. A harvested close for that player on that day where one
exists ("book" basis — the only rows that speak to beating a book), and a
trailing-average naive line at -110/-110 otherwise ("naive" basis —
predictive skill only). A game he did not play (0 minutes) is not graded:
a book voids that prop.

Standard library only; reads the tables the ingest already fills.
"""

from __future__ import annotations

from .backtest import SettledProp, evaluate, BacktestReport

#: The markets the basketball boards price.
MARKETS = ("pts", "reb", "ast", "fg3m", "pra")

#: The live build keeps a player's last twenty games; so does the replay.
WINDOW = 20

#: Games of history before a prediction counts — the Lab's bar.
MIN_HISTORY = 8

#: A season of NBA props is ~125,000 player-market-games. The replay grades
#: the most recent ones up to this cap per market, so a weekly run stays in
#: minutes on the droplet rather than an hour.
MAX_PER_MARKET = 20000


def _tune(sport: str):
    from .hoops import NBA, WNBA
    return WNBA if sport == "wnba" else NBA


def _norm(name: str) -> str:
    from .sources.oddsapi import normalize_name
    return normalize_name(name or "")


def histories(conn, sport: str, seasons: list | None = None) -> dict:
    """``{player: [(date, starter, {market: value}), ...]}`` oldest first."""
    q = ("SELECT player, position, period, market, value FROM player_game_logs "
         "WHERE sport=?")
    args: list = [sport]
    if seasons:
        q += " AND season IN (%s)" % ",".join("?" * len(seasons))
        args += list(seasons)
    games: dict = {}
    for r in conn.execute(q, args):
        g = games.setdefault(r[0], {}).setdefault(str(r[2]), {"_s": None})
        g[r[3]] = float(r[4] or 0.0)
        if r[3] == "min":
            g["_s"] = r[1] == "S"
    out = {}
    for player, by_day in games.items():
        rows = []
        for day in sorted(by_day):
            g = by_day[day]
            if "pts" in g and "reb" in g and "ast" in g:
                g["pra"] = round(g["pts"] + g["reb"] + g["ast"], 1)
            rows.append((day, bool(g.pop("_s")), g))
        out[player] = rows
    return out


def _naive_line(prior: list) -> float:
    base = sum(prior) / len(prior)
    return max(0.5, round(base * 2) / 2.0 - 0.5)


def _quotes(conn, sport: str, market: str) -> dict:
    """``{(normalised player, day): quote}`` from the harvested closes."""
    try:
        from .db import closing_odds_by_date
        raw = closing_odds_by_date(conn, sport, market)
    except Exception:                                        # noqa: BLE001
        return {}
    return {(_norm(p), d): q for (p, d), q in raw.items()}


def settled_props(hist: dict, market: str, sport: str = "nba",
                  quotes: dict | None = None,
                  min_history: int = MIN_HISTORY,
                  cap: int = MAX_PER_MARKET) -> tuple[list, dict]:
    """Price every eligible player-game; ``(settled, counts)``."""
    from .nba.pipeline import evaluate_prop
    tune = _tune(sport)
    quotes = quotes or {}
    todo = []
    for player, rows in hist.items():
        for i in range(min_history, len(rows)):
            day, _starter, g = rows[i]
            if market not in g or g.get("min", 0.0) <= 0:
                continue                           # did not play: voided
            todo.append((day, player, i))
    todo.sort()
    todo = todo[-cap:] if cap else todo
    settled, counts = [], {"priced": 0, "skipped": 0, "book": 0, "naive": 0}
    for day, player, i in todo:
        rows = hist[player]
        prior = rows[max(0, i - WINDOW):i][::-1]         # newest first
        minutes = [g.get("min", 0.0) for _, _, g in prior]
        values = [g.get(market, 0.0) for _, _, g in prior]
        actual = float(rows[i][2][market])
        q = quotes.get((_norm(player), day))
        over = int((q or {}).get("over_odds") or 0)
        under = int((q or {}).get("under_odds") or 0)
        if q and over and under and q.get("line") is not None:
            line, basis = float(q["line"]), "book"
        else:
            played = [v for v, m in zip(values, minutes) if m > 0][:8] or values[:8]
            line, over, under, basis = _naive_line(played), -110, -110, "naive"
        prop = {"player": player, "market": market, "minutes": minutes,
                "values": values, "line": line, "over_odds": over,
                "under_odds": under, "is_starter": prior[0][1],
                "spread": 0.0, "rest": "1day", "book": "replay"}
        try:
            out = evaluate_prop(prop, tune)
        except Exception:                                    # noqa: BLE001
            out = {"kind": "skip"}
        if out.get("kind") == "skip" or out.get("p_model") is None:
            counts["skipped"] += 1
            continue
        counts["priced"] += 1
        counts[basis] += 1
        settled.append(SettledProp(
            player=player, market=market, line=line, odds=int(out["odds"]),
            hit_prob=float(out["p_model"]), projection=float(out["projection"]),
            actual=actual, recommended=out.get("kind") == "pick",
            stake_units=float(out.get("stake_units") or 0.0),
            side=out["side"], basis=basis))
    return settled, counts


def replay(conn, sport: str = "nba", markets=MARKETS,
           seasons: list | None = None,
           min_history: int = MIN_HISTORY) -> list:
    """``[(market, BacktestReport, counts), ...]`` for every market that
    priced anything."""
    hist = histories(conn, sport, seasons)
    out = []
    for market in markets:
        settled, counts = settled_props(hist, market, sport,
                                        _quotes(conn, sport, market),
                                        min_history=min_history)
        if not settled:
            continue
        rep: BacktestReport = evaluate(settled)
        rep.total_priced = len(settled)
        rep.used_real_lines = counts["book"]
        out.append((market, rep, counts))
    return out
