#!/usr/bin/env python3
"""Should a college receiver's thrown-at-and-caught-nothing game be on his record? — measured.

    python3 cfbtargetfit.py                      # 2025 and 2026
    python3 cfbtargetfit.py --seasons 2024-2026

Ethan, 2026-10-13: "We worked so hard on nfl so ik CFB and mlb and nba and
ufc is missing stuff." One thing college was missing is in its own feed.
The play file names the intended receiver on 78% of 2025's incompletions
and 92% of 2026's — 21% of 2024's, the year the parser was written and
decided college has no targets. engine/sources/cfbstats now counts a
named target as a receiver's opportunity (ZERO_WHEN): thrown at, caught
none, and the game is a zero — receptions 0, receiving yards 0. Before,
the game was not in his log at all, so his history was "games in which he
caught one".

Both arms come off the SAME parser; ``parse_player_stats(..., targets=False)``
is the logs as they were:

  * THE POPULATION IS THE BOARD'S. A player-game where, on the OLD logs, he
    has MIN_LOGS games in his last LOG_LIMIT — this season's first, then
    last season's, as engine/cfb/props reads them — at a per-game mean over
    the board's floor (engine/cfb/props._MIN_MEAN): the props the board
    would have priced.
  * THE FORECAST IS THE BOARD'S FORM, engine/form.compute_form over those
    logs, newest first, last season's games marked carried.
  * THE TRUTH IS WHAT THE BOOK GRADES: his catches or yards that game, 0
    when he was thrown at and caught none. A game he was not thrown at is
    invisible to both arms and is not scored.

THE BAR, set before the first run: the new logs ship if the squared error
falls in BOTH 2025 and 2026 for BOTH receptions and receiving yards — the
two seasons whose files name most targets.

THE RESULT, 2026-10-13, run in the cloud sandbox off the mirror's files:

    season  market           n    old MSE   new MSE  change   bias old -> new  thrown-at zeros
    2025    receptions  14,234      3.775     3.765   -0.3%    +0.14 ->  +0.08    1063
    2025    rec_yds     14,461    927.959   925.318   -0.3%    +2.19 ->  +1.53    1070
    2026    receptions   4,209      3.729     3.663   -1.8%    +0.13 ->  -0.00     471
    2026    rec_yds      4,329    996.424   986.159   -1.0%    +0.61 ->  -0.91     489
    THE BAR: squared error falls in every season for both markets — MET

The old logs ran high in every cell — a log of "games he caught one" —
and the new ones take most of that out; 2026's yards now sit a touch
under, at a lower error. "thrown-at zeros" counts the scored games that
were a thrown-at zero: games a sportsbook grades (an over lost, an under
won) that the old history could not see at all.

THE TOUCHDOWN SIDE, checked the same day: a thrown-at receiver's game
now also files an anytime-TD 0. A per-game scoring rate over the last 20
games, scored by Brier on the next game for every player with a scoring
history: 2025 0.1584 -> 0.1583, 2026 0.2345 -> 0.2346. Unchanged within
a ten-thousandth either way, so the zeros cost the touchdown board nothing.

Reads the mirror's files (cached under data/cache); writes nothing.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

#: The two receiving markets the board prices off these logs.
MEASURED = ("receptions", "rec_yds")
DEFAULT_SEASONS = (2025, 2026)


def _rows(season: int):
    from engine.sources import cfbstats as C
    return C._stream(C.STATS_URL.format(season=int(season)),
                     f"cfb_player_stats_{int(season)}.csv", 86400 * 7)


def games_of(season: int) -> dict:
    """``{game_id: {"period", "home", "away", "home_name", "away_name"}}``
    off the file itself — the shape engine/sources/cfbfastr stores, with the
    week as the period (it orders a season the way the date does)."""
    out: dict = {}
    for r in _rows(season):
        gid = (r.get("game_id") or "").strip()
        team, opp = (r.get("team") or "").strip(), (r.get("opponent") or "").strip()
        if not gid or not team or not opp or gid in out:
            continue
        try:
            week = int(float(r.get("week") or 0))
        except ValueError:
            week = 0
        out[gid] = {"period": f"{int(season)}-W{week:02d}", "home": team, "away": opp,
                    "home_name": team, "away_name": opp}
    return out


def logs(season: int, games: dict, targets: bool) -> dict:
    """``{(player, team): {market: {period: value}}}`` for one arm."""
    from engine.sources import cfbstats as C
    out: dict = defaultdict(lambda: defaultdict(dict))
    for row in C.parse_player_stats(_rows(season), season, games, targets=targets)["rows"]:
        if row["market"] in MEASURED:
            out[(row["player"], row["team"])][row["market"]][row["period"]] = float(row["value"])
    return out


def _carried(prior: dict, shared: set) -> dict:
    """``{player: {market: [values newest first]}}`` from last season — by
    name, any school (a transfer's production is filed under the one he
    left), and dropped when two players share the name (``shared``, the
    same set for both arms, so each arm reads the same players)."""
    out: dict = {}
    for (player, _team), mk in prior.items():
        if player in shared:
            continue
        out[player] = {m: [v for _p, v in sorted(by.items(), reverse=True)] for m, by in mk.items()}
    return out


def _shared_names(*arms: dict) -> set:
    teams: dict = defaultdict(set)
    for arm in arms:
        for (player, team) in arm:
            teams[player].add(team)
    return {p for p, t in teams.items() if len(t) > 1}


def points(now_old: dict, now_new: dict, prior_old: dict, prior_new: dict) -> dict:
    """``{market: [(old_forecast, new_forecast, truth, thrown_at_zero)]}``."""
    from engine.cfb.props import LOG_LIMIT, MIN_LOGS, _MIN_MEAN
    from engine.form import compute_form
    from engine.formfit import weights_for
    from engine.models import GameLog
    shared = _shared_names(prior_old, prior_new)
    carried_old, carried_new = _carried(prior_old, shared), _carried(prior_new, shared)
    out: dict = defaultdict(list)

    def history(cur: dict, carried: list, before: str) -> list:
        mine = [(p, v, False) for p, v in sorted(cur.items(), reverse=True) if p < before]
        return (mine + [(None, v, True) for v in carried])[:LOG_LIMIT]

    def form(hist: list, market: str) -> float:
        vals = [v for _p, v, _c in hist]
        gl = [GameLog(week=len(hist) - i, opponent="", value=v, prior=c)
              for i, (_p, v, c) in enumerate(hist)]
        return compute_form(gl, sum(vals) / len(vals), None,
                            weights=weights_for("cfb", market)).mean

    for key, mk_new in now_new.items():
        player = key[0]
        mk_old = now_old.get(key, {})
        for market in MEASURED:
            new_games = mk_new.get(market) or {}
            old_games = mk_old.get(market) or {}
            for period, truth in new_games.items():
                old_hist = history(old_games, (carried_old.get(player) or {}).get(market, []), period)
                if len(old_hist) < MIN_LOGS:
                    continue
                if sum(v for _p, v, _c in old_hist) / len(old_hist) < _MIN_MEAN[market]:
                    continue
                new_hist = history(new_games, (carried_new.get(player) or {}).get(market, []), period)
                out[market].append((form(old_hist, market), form(new_hist, market), truth,
                                    period not in old_games))
    return out


def table(seasons) -> list[str]:
    lines = [f"{'season':<7} {'market':<11} {'n':>6}  {'old MSE':>9} {'new MSE':>9} {'change':>7}  "
             f"{'bias old -> new':>16}  thrown-at zeros"]
    verdicts = []
    for s in seasons:
        g_now, g_prior = games_of(s), games_of(s - 1)
        pts = points(logs(s, g_now, False), logs(s, g_now, True),
                     logs(s - 1, g_prior, False), logs(s - 1, g_prior, True))
        for market in MEASURED:
            rows = pts.get(market) or []
            if not rows:
                lines.append(f"{s:<7} {market:<11} {0:>6}  (nothing to score)")
                verdicts.append(False)
                continue
            n = len(rows)
            mse_o = sum((o - y) ** 2 for o, _n, y, _z in rows) / n
            mse_n = sum((nw - y) ** 2 for _o, nw, y, _z in rows) / n
            b_o = sum(o - y for o, _n, y, _z in rows) / n
            b_n = sum(nw - y for _o, nw, y, _z in rows) / n
            zeros = sum(1 for *_x, z in rows if z)
            lines.append(f"{s:<7} {market:<11} {n:>6,}  {mse_o:>9.3f} {mse_n:>9.3f} "
                         f"{(mse_n / mse_o - 1) * 100:>+6.1f}%  {b_o:>+7.2f} -> {b_n:>+6.2f}  {zeros:>6}")
            verdicts.append(mse_n < mse_o)
    lines.append("THE BAR: squared error falls in every season for both markets — "
                 + ("MET" if verdicts and all(verdicts) else "NOT MET"))
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seasons", default="", help="e.g. 2024-2026 (default 2025,2026)")
    a = ap.parse_args(argv)
    seasons = DEFAULT_SEASONS
    if a.seasons:
        from engine.seasons import parse_seasons
        seasons = tuple(parse_seasons(a.seasons))
    for line in table(seasons):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
