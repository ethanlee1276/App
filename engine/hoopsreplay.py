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

THE FITTERS' WALK (`walk`, 2026-10-14). Ethan: "Ya do the self tuneung."
The three self-tuning fits — the temperatures (calibrate.py), the player
memory (playerfit.py) and the rank store (engine/rankfit) — walk a sport
through `logwalk.walk`, and until this day that handed basketball to the
FOOTBALL chain (`projection.build_projection` + `betting.evaluate_prop`),
which has no minutes model at all. The NBA board then applied what those
fits learned — the temperature through `calibrated(tune.key, …)`, the
memory through `pf_mult` — to its own minutes × rate projection: a
correction measured on one model, applied to another. `walk` is the same
window as the replay above through the board's own `project` and
`p_over`, at the naive -110/-110 line, with no gate in the way: a fit
learns from every game the model priced, not only the ones the humility
clamp let through. The recency dial (formfit.py) has nothing to turn here
— the projection is minutes × a per-minute rate over his last twenty
games, with no blend of windows — so formfit.py leaves basketball alone.

Standard library only; reads the tables the ingest already fills.
"""

from __future__ import annotations

from .backtest import SettledProp, evaluate, BacktestReport
from .hoops import COMBOS, COUNTS, carried

#: The markets the basketball boards price — steals, blocks and turnovers
#: since 2026-10-14 (`hoops.COUNTS`).
MARKETS = ("pts", "reb", "ast", "fg3m", "pra", "pts_reb", "pts_ast", "reb_ast", "stl", "blk", "tov")

#: The live build keeps a player's last twenty games; so does the replay.
WINDOW = 20

#: Games of history before a prediction counts — the Lab's bar.
MIN_HISTORY = 8

#: A season of NBA props is ~125,000 player-market-games. The replay grades
#: the most recent ones up to this cap per market, so a weekly run stays in
#: minutes on the droplet rather than an hour.
MAX_PER_MARKET = 20000

#: The fitters' walk prices up to this many of a market's most recent
#: player-games — a season and a bit of the NBA's. Each deep fitter has
#: fifteen minutes per sport on the droplet (`deepfit.TIMEOUT_S`) for all
#: eleven markets; the player memory walks each twice, and the temperature
#: fit costs more than its walk (timed 2026-10-14: about 4 s to walk and
#: 15 s to fit 38,000 games of one market here).
FIT_CAP = 30000


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
                for combo, (a, b) in COMBOS.items():
                    g[combo] = round(g[a] + g[b], 1)
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


def _entries(hist: dict, market: str) -> list:
    """`histories` in the walk's entry shape (`db.hoops_entries`): one
    entry per player, oldest first, None where the box stored no row."""
    return [{"name": player,
             "dates": [day for day, _, _ in rows],
             "starters": [bool(s) for _, s, _ in rows],
             "minutes": [float(g.get("min", 0.0)) for _, _, g in rows],
             "values": [g.get(market) for _, _, g in rows]}
            for player, rows in hist.items()]


def _todo(entries: list, min_history: int, cap: int) -> list:
    """Every gradeable game, ``(day, player, entry index, game index)``,
    oldest first and capped to the most recent ``cap``: a game with a
    stored value that he played in (a book voids a prop he sat out)."""
    todo = []
    for n, e in enumerate(entries):
        vals, mins, days = e.get("values") or [], e.get("minutes") or [], e.get("dates") or []
        for i in range(min_history, len(vals)):
            if vals[i] is None or float(mins[i] or 0.0) <= 0:
                continue
            todo.append((str(days[i]), str(e["name"]), n, i))
    todo.sort()
    return todo[-cap:] if cap else todo


def _window(e: dict, i: int, market: str) -> tuple[list, list, bool]:
    """``(minutes, values, starter)`` for game ``i`` exactly as the live
    build hands them to the board (`nba_build.player_history`): his twenty
    games before it, newest first. The minutes keep every one of them; a
    count (`hoops.COUNTS`) keeps only the run of newest games whose box
    stored it — a missing row is not a zero — and the rate pairs the two
    game for game from the newest. Starter is his newest game's flag."""
    lo = max(0, i - WINDOW)
    minutes = [float(m or 0.0) for m in (e.get("minutes") or [])[lo:i]][::-1]
    values = list((e.get("values") or [])[lo:i])[::-1]
    if market in COUNTS:
        run = carried([{} if v is None else {market: v} for v in values], market)
        values = [float(v) for v in values[:run]]
    else:
        values = [0.0 if v is None else float(v) for v in values]
    starters = e.get("starters") or []
    return minutes, values, bool(starters[i - 1]) if 0 < i <= len(starters) else False


def settled_props(hist: dict, market: str, sport: str = "nba",
                  quotes: dict | None = None,
                  min_history: int = MIN_HISTORY,
                  cap: int = MAX_PER_MARKET) -> tuple[list, dict]:
    """Price every eligible player-game; ``(settled, counts)``."""
    from .nba.pipeline import evaluate_prop
    tune = _tune(sport)
    quotes = quotes or {}
    entries = _entries(hist, market)
    settled, counts = [], {"priced": 0, "skipped": 0, "book": 0, "naive": 0}
    for day, player, n, i in _todo(entries, min_history, cap):
        minutes, values, starter = _window(entries[n], i, market)
        if len(values) < 3:
            # Under three games of the stat is no rate — the floor every
            # prop has (a count read before its box stored it, mostly).
            counts["skipped"] += 1
            continue
        actual = float(entries[n]["values"][i])
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
                "under_odds": under, "is_starter": starter,
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


def walk(entries: list, market: str, sport: str = "nba",
         min_history: int | None = None, tune=None,
         player_adjust=None, player_record=None,
         form_weights=None, cap: int = FIT_CAP, **_other) -> BacktestReport:
    """The self-tuning fitters' walk for basketball — see the module
    docstring. ``entries`` are `db.hoops_entries` rows (`logwalk.load_entries`
    loads them, with the league's fitted tuning as ``tune``).

    Every gradeable game is projected by the board's own `project` from
    the twenty before it and priced by its own `p_over` at the naive line
    off his last eight played games, -110 both ways; the side is the one
    the (calibrated) probability favours, as `evaluate_prop` takes it, and
    ``raw_prob`` keeps the untempered number the temperature fit learns on.
    Oldest first, so `calibrate.bake_off`'s held-out slice is the latest.

    The memory hooks are logwalk's: ``player_adjust(name)`` stands in for
    the store (1.0 = no memory), and ``player_record(name, projected,
    actual)`` gets the projection before that multiplier. ``form_weights``
    has nothing to act on here and is ignored (formfit.py skips
    basketball); so is anything else a football walk takes."""
    from .calibrate import calibrated
    from .nba.pipeline import project
    from .nba.prob import p_over
    tune = tune or _tune(sport)
    settled = []
    for _day, player, n, i in _todo(entries, MIN_HISTORY if min_history is None else min_history, cap):
        minutes, values, starter = _window(entries[n], i, market)
        if len(values) < 3:
            continue
        played = [v for v, m in zip(values, minutes) if m > 0][:8] or values[:8]
        line = _naive_line(played)
        mult = float(player_adjust(player)) if player_adjust else None
        prop = {"player": player, "market": market, "minutes": minutes, "values": values,
                "is_starter": starter, "spread": 0.0, "rest": "1day"}
        if mult is not None:
            prop["player_mult"] = mult
        try:
            pj = project(prop, tune)
        except Exception:                                    # noqa: BLE001
            continue
        if "skip" in pj:
            continue
        proj, actual = float(pj["projection"]), float(entries[n]["values"][i])
        if player_record is not None:
            player_record(player, proj / (mult or 1.0), actual)
        raw = p_over(market, proj, line, tune)
        over = calibrated(tune.key, market, raw)
        side = "OVER" if over >= 0.5 else "UNDER"
        settled.append(SettledProp(
            player=player, market=market, line=line, odds=-110,
            hit_prob=over if side == "OVER" else 1.0 - over,
            raw_prob=raw if side == "OVER" else 1.0 - raw,
            projection=proj, actual=actual, recommended=False, stake_units=0.0,
            side=side, basis="naive"))
    report = evaluate(settled)
    report.total_priced = len(settled)
    return report


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
