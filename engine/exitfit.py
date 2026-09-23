"""Games a player left early, in every sport: measured, then ruled.

Ethan, 2026-09-23, after Garrett Wilson's 0 against Cleveland (a knee, 39%
of the snaps) sat in his chart as a full game: "make sure that Wilson 0
yard game issue doesn't affect any other players or picks or sports and
that all gets sorted out so it's no an issue."

WHAT A LEFT-EARLY GAME IS, in every sport the same way: a game in which
his usage was under half of his own usual — the median over the games the
projection reads — for a player whose usual is a real role. Usage is the
thing the sport counts: snaps (NFL), minutes (NBA, WNBA), outs (an MLB
starter), plate appearances (an MLB hitter). A player whose usual is under
the floor has no role to leave early from.

THE QUESTION is never "does it look wrong" — it is whether the NEXT game
is better predicted with that game in the projection's history or out of
it: the share of later outcomes above the projection (0.50 is centred),
the mean miss, and the root-mean-square miss, split by where the early
exit sits (in his last five games, or only older).

WHAT THE GAMES SAID:

  * NFL, 2022-2025 snap counts (engine/sources/nflverse.stamp_snaps): IN.
    Receiving yards .50 above with the partial game in, .46 without — a
    game he left hurt predicts a quieter stretch. Named on the chart, the
    log and the cooling-off line; kept in the number.
  * WNBA and NBA, 2022-2025 box scores (sportsdataverse, ESPN's feed):
    a player who left a game early in his LAST FIVE is still limited —
    keep everything (dropping it leaves his minutes 3 too high, .34-.36
    above). One whose only early exits are OLDER is not — those games
    only drag his minutes down (.56 above with them, .49 without, both
    leagues, every season). engine/nba/minutes.role_minutes.
  * MLB: measured on the box's own history (`python3 exitfit.py mlb` —
    starters' strikeouts and outs by outs recorded, hitters' hits and
    total bases by plate appearances) before any rule; until then every
    start and game stays in, the NFL's answer.
  * College football publishes no snap counts, so a game he left and a
    quiet game cannot be told apart; every game stays in, the NFL's
    measured answer.

Standard library only.
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict

#: Under this share of his own median usage is a game he left early.
EXIT_SHARE = 0.5
#: "Recent" is the last this many games.
RECENT = 5
#: Games of history before a game is predicted at all.
MIN_PRIOR = 3


def exits(usage: list[float], min_median: float, share: float = EXIT_SHARE) -> list[int]:
    """Indexes into ``usage`` (newest first) of the games he left early —
    none when his median is under ``min_median`` (no role to leave)."""
    vals = [float(u) for u in usage if u is not None]
    if len(vals) < MIN_PRIOR:
        return []
    med = statistics.median(vals)
    if med < min_median:
        return []
    return [i for i, u in enumerate(usage) if u is not None and float(u) < share * med]


def keep_rule(usage: list[float], min_median: float, rule: str) -> list[int]:
    """Indexes kept under ``rule``: "all"; "old" — drop early exits older
    than the last RECENT games when none is recent (the hoops rule);
    "none" — drop every early exit."""
    ex = exits(usage, min_median)
    n = len(usage)
    if rule == "all" or not ex:
        return list(range(n))
    if rule == "old":
        if any(i < RECENT for i in ex):
            return list(range(n))
        return [i for i in range(n) if i not in ex]
    return [i for i in range(n) if i not in ex]


RULES = ("all", "old", "none")


def measure(series: dict, project, min_median: float, window: int = 20) -> dict:
    """``series`` is ``{player: [(season, period, usage, value), ...]}`` in
    date order; ``project(values, usage)`` gives the projection from
    newest-first lists. Returns ``{(cell, rule): {n, above, bias, rmse,
    per}}`` with cell "clean", "old" (early exits only past the last
    RECENT) or "recent"."""
    acc: dict = defaultdict(lambda: {"err": [], "season": []})
    for games in series.values():
        for i in range(len(games)):
            season = games[i][0]
            prior = [g for g in games[:i] if g[0] == season][-window:][::-1]
            if len(prior) < MIN_PRIOR or games[i][2] is None:
                continue
            usage = [g[2] for g in prior]
            values = [g[3] for g in prior]
            ex = exits(usage, min_median)
            cell = ("recent" if any(j < RECENT for j in ex) else "old") if ex else "clean"
            for rule in RULES:
                keep = keep_rule(usage, min_median, rule)
                if len(keep) < MIN_PRIOR:
                    keep = list(range(len(usage)))
                proj = project([values[j] for j in keep], [usage[j] for j in keep])
                if proj is None:
                    continue
                a = acc[(cell, rule)]
                a["err"].append(games[i][3] - proj)
                a["season"].append(season)
    out = {}
    for key, a in acc.items():
        e = a["err"]
        per: dict = defaultdict(list)
        for x, s in zip(e, a["season"]):
            per[s].append(x)
        out[key] = {"n": len(e),
                    "above": round(sum(1 for x in e if x > 0) / len(e), 3),
                    "bias": round(sum(e) / len(e), 3),
                    "rmse": round(math.sqrt(sum(x * x for x in e) / len(e)), 3),
                    "per": {s: round(sum(1 for x in v if x > 0) / len(v), 3)
                            for s, v in sorted(per.items())}}
    return out


def form_projection(weights=None, prior_games: float = 0.0):
    """The projection's own form base (engine/form.compute_form) over the
    kept games, anchored to their mean — what the MLB and football boards
    start from."""
    from .form import compute_form
    from .models import GameLog

    def project(values, _usage):
        if not values:
            return None
        logs = [GameLog(week=len(values) - j, opponent="", value=float(v))
                for j, v in enumerate(values)]
        mean = sum(values) / len(values)
        kw = {"weights": weights} if weights else {}
        if prior_games:
            kw.update(prior=mean, prior_n=len(values), prior_games=prior_games)
        return compute_form(logs, mean, None, **kw).mean
    return project


def minutes_projection(tune):
    """The hoops minutes base (engine/nba/minutes.base_minutes)."""
    from .nba.minutes import base_minutes

    def project(values, _usage):
        return base_minutes(values, tune)
    return project


def lines(title: str, result: dict) -> list[str]:
    out = [title]
    for cell in ("clean", "old", "recent"):
        for rule in RULES:
            r = result.get((cell, rule))
            if not r or (cell == "clean" and rule != "all"):
                continue
            out.append(f"  {cell:<7}{rule:<5} n {r['n']:<6} above {r['above']:.3f}  "
                       f"bias {r['bias']:+.2f}  rmse {r['rmse']:.2f}  "
                       + " ".join(f"{s}:{x:.2f}" for s, x in r["per"].items()))
    return out
