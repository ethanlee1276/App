"""Calibrate the game-line model against its own record.

THE MEASUREMENT THAT MOTIVATED THIS, run 2026-08-27 over 899 NFL games
from four ingested seasons — the first time the spread/total model had
ever been graded against a closing number, because until this week no
closing numbers were stored:

    nfl total    slope +0.030 ± 0.113   nfl spread   slope +0.006 ± 0.085

That slope is the whole question. Regress the market's own error
(``actual − close``) on the model's disagreement (``projection − close``)
and the coefficient says what fraction of a disagreement is real. A
slope of 1.0 would mean the model is right and the close is wrong by
exactly the amount claimed. A slope of 0.0 means the disagreement is
noise: when this model says a total is four points too low, the game
lands on the market's side as often as ours.

Both NFL slopes are indistinguishable from zero. Betting the side the
model preferred beat the close on 51.2% of totals and 50.7% of spreads,
against the 52.4% a −110 line needs. The model is not beaten because it
is badly built; it is beaten because a closing NFL spread is the
aggregate of everyone who bet it, and a team's points-for/points-against
average is a thin thing to bring to that fight.

WHAT THIS MODULE DOES ABOUT IT. `engine.betting.temper_edge` already
shrinks every raw disagreement toward the market and already takes the
shrink as a parameter — the flat ``MARKET_SHRINK = 0.5`` is only a
default, and 0.5 was a reasonable guess made before anyone could measure
the real number. This measures it and passes it, per sport and per
market. Where the model has demonstrated nothing, the shrink collapses
toward zero and the edges go quiet, which is the correct output of an
honest model with no edge. Where it demonstrates something, the
measurement raises the shrink and the board says so.

The guards are corrfit's, for corrfit's reasons: a minimum sample, a
standard error small enough to act on, and a refusal to adopt a slope
that is merely a small number with a large error bar. A fit that
declines to adopt records WHY.

Deliberately NOT done here: nudging the projection itself with a fitted
intercept. The measured bias is +0.27 points on a total whose actual
scores scatter with a 13-point SD — a rounding error dressed as a
correction, and one that would need refitting every season.

Standard library only.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import time

from . import feedstate as _feedstate

#: Games behind a slope before it may be adopted. Deliberately large: a
#: slope fitted on a hundred games has an error bar wide enough to
#: contain both "the model is perfect" and "the model is noise".
MIN_N = 400
#: …and the slope must be pinned tightly enough that the adoption means
#: something. ±0.11 on the NFL total fit is wide, and it is exactly why
#: the honest reading of that fit is "no measured edge" rather than
#: "3% edge" — a shrink of 0.03 and a shrink of 0.14 are the same
#: statement about our knowledge, not two different numbers.
MAX_SE = 0.25
#: A shrink is a fraction of a disagreement kept, so it lives in [0, 1].
#: A negative fitted slope means the model was worse than useless on this
#: market; the floor reads that as zero rather than inverting the model,
#: because "bet the opposite of our own projection" is a claim that needs
#: far more than one fit behind it.
FLOOR, CEIL = 0.0, 1.0
#: Never trust more of a disagreement than the flat prior did on the
#: strength of one fit. The measurement is allowed to make the model
#: quieter; making it louder is a bigger claim and needs a season of
#: forward results, not a backfit.
MAX_ADOPTED = 0.5
#: Team games of prior history before a game is priced in the fit — the
#: same walk-forward warmup `backtest_game_lines` uses, so the fit and
#: the backtest are measuring the same population.
MIN_TEAM_GAMES = 15

STATE_PATH = _feedstate.path("gamecal.json")

_cache: dict = {}


class Fit:
    """One market's calibration slope, with everything needed to judge it."""

    __slots__ = ("sport", "market", "n", "slope", "se", "hit", "decided",
                 "bias", "resid_sd", "missing")

    def __init__(self, sport, market, n=0, slope=float("nan"),
                 se=float("nan"), hit=0, decided=0, bias=float("nan"),
                 resid_sd=float("nan"), missing=""):
        self.sport, self.market = sport, market
        self.n, self.slope, self.se = n, slope, se
        self.hit, self.decided = hit, decided
        self.bias, self.resid_sd, self.missing = bias, resid_sd, missing

    @property
    def hit_rate(self) -> float:
        return (self.hit / self.decided) if self.decided else 0.0

    def summary(self) -> str:
        if self.missing:
            return f"{self.sport} {self.market}: {self.missing}"
        head = (f"{self.sport} {self.market}: slope {self.slope:+.3f} ± "
                f"{self.se:.3f} on {self.n} games")
        if self.market == "moneyline":
            # NOT a hit rate. On a two-way points market the model's side
            # wins about half the time and anything above 52.4% is money;
            # on a moneyline the model mostly disagrees toward the
            # underdog, so its side wins well under half the time and is
            # still profitable at the price. Quoting a raw hit rate here
            # would read as a catastrophe and mean nothing. The slope is
            # the measurement.
            return head
        return (head + f"; the model's side beat the close {self.hit}/"
                       f"{self.decided} = {self.hit_rate:.1%}")


def observations(conn, sport: str, market: str,
                 min_team_games: int = MIN_TEAM_GAMES) -> list[tuple]:
    """``[(model − close, actual − close)]``, walked forward in time.

    Ratings for each game come from games strictly BEFORE it, through the
    same `_split` the backtest and `engine.teamrates` share, so this
    measures the model as it would actually have been run — not a model
    fitted on the games it is being graded against.
    """
    from .gamebacktest import schedule_closes, game_line_closes, _split
    from .gamebets import project_total, game_margin, SCORING_BASELINE, _sd

    if market == "moneyline":
        return _moneyline_observations(conn, sport, min_team_games)
    if market not in ("total", "spread"):
        raise ValueError(
            f"market must be 'total', 'spread' or 'moneyline', got {market!r}")
    if sport not in SCORING_BASELINE:
        # A sport can register its own constants at import time — CFB's
        # ratings module installs a measured prior as a side effect of
        # being imported. Give it that chance before concluding the sport
        # has no variance registered, but do not invent one if it hasn't:
        # `_sd` refusing is the right outcome, and `fit_one` turns the
        # refusal into a recorded hold rather than a crash.
        try:                                              # pragma: no cover
            import importlib
            importlib.import_module(f".{sport}.ratings", __package__)
        except Exception:                                 # noqa: BLE001
            pass
    baseline = _sd(SCORING_BASELINE, sport, "scoring baseline")
    closes = game_line_closes(conn, sport, market) or schedule_closes(
        conn, sport, market)
    if not closes:
        return []
    rows = conn.execute(
        "SELECT period, home, away, home_score, away_score FROM games "
        "WHERE sport=? AND home_score IS NOT NULL AND away_score IS NOT NULL "
        "ORDER BY period", (sport,)).fetchall()
    agg: dict = {}
    out: list[tuple] = []
    for row in rows:
        date, home, away = row["period"], row["home"], row["away"]
        hs, as_ = float(row["home_score"]), float(row["away_score"])
        quote = closes.get((str(date), home, away))
        enough = (agg.get(home, (0, 0, 0))[2] >= min_team_games
                  and agg.get(away, (0, 0, 0))[2] >= min_team_games)
        if quote and enough:
            h_off, h_def = _split(agg, home, baseline)
            a_off, a_def = _split(agg, away, baseline)
            line = quote[0]
            if market == "total":
                proj = project_total(sport, h_off, h_def, a_off, a_def)
                out.append((proj - line, (hs + as_) - line))
            else:
                # `line` is the HOME number; the home margin the market
                # implies is its negation, which is what the projection
                # has to be compared against.
                proj = game_margin(sport, h_off - h_def, a_off - a_def)
                out.append((proj + line, (hs - as_) + line))
        pf, pa, n = agg.get(home, (0.0, 0.0, 0))
        agg[home] = (pf + hs, pa + as_, n + 1)
        pf, pa, n = agg.get(away, (0.0, 0.0, 0))
        agg[away] = (pf + as_, pa + hs, n + 1)
    return out


def _logit(p: float) -> float:
    p = min(max(float(p), 1e-6), 1.0 - 1e-6)
    return math.log(p / (1.0 - p))


def _moneyline_observations(conn, sport: str, min_team_games: int) -> list[tuple]:
    """``[(model − market, in LOG-ODDS, home won)]``, walked forward.

    A moneyline is a probability, not a number of points, so the
    disagreement that means anything is the log-odds gap between our
    win probability and the market's de-vigged fair — which is also the
    space `engine.betting.temper_edge` shrinks in for a two-way market.
    Fitting here and shrinking there therefore measure the same quantity,
    which is the whole point of doing it this way rather than regressing
    points and hoping the mapping holds.
    """
    from .gamebacktest import moneyline_closes, schedule_moneylines, _rating
    from .gamebets import SCORING_BASELINE, mlb_win_prob, nfl_win_prob
    from .odds import devig_two_way

    CURVES = {"mlb": mlb_win_prob, "nfl": nfl_win_prob}
    if sport not in CURVES:
        raise ValueError(
            f"no win-probability curve registered for {sport!r} — fitting a "
            f"shrink through another league's curve would calibrate the wrong "
            f"model")
    win_prob = CURVES[sport]
    baseline = SCORING_BASELINE.get(sport, 0.0)
    closes = moneyline_closes(conn, sport)
    if not closes:
        closes = {k: {k[1]: h, k[2]: a}
                  for k, (h, a) in schedule_moneylines(conn, sport).items()}
    if not closes:
        return []
    rows = conn.execute(
        "SELECT period, home, away, home_score, away_score FROM games "
        "WHERE sport=? AND home_score IS NOT NULL AND away_score IS NOT NULL "
        "ORDER BY period", (sport,)).fetchall()
    agg: dict = {}
    out: list[tuple] = []
    for row in rows:
        date, home, away = row["period"], row["home"], row["away"]
        hs, as_ = float(row["home_score"]), float(row["away_score"])
        quote = closes.get((str(date), home, away)) or {}
        enough = (agg.get(home, (0, 0, 0))[2] >= min_team_games
                  and agg.get(away, (0, 0, 0))[2] >= min_team_games)
        h_ml, a_ml = quote.get(home), quote.get(away)
        if enough and h_ml is not None and a_ml is not None and hs != as_:
            fair_home, _ = devig_two_way(int(h_ml), int(a_ml))
            wp = win_prob(_rating(agg, home, baseline),
                          _rating(agg, away, baseline))
            out.append((_logit(wp) - _logit(fair_home),
                        _logit(fair_home), 1.0 if hs > as_ else 0.0))
        pf, pa, n = agg.get(home, (0.0, 0.0, 0))
        agg[home] = (pf + hs, pa + as_, n + 1)
        pf, pa, n = agg.get(away, (0.0, 0.0, 0))
        agg[away] = (pf + as_, pa + hs, n + 1)
    return out


def _fit_logistic(obs: list[tuple]) -> tuple[float, float]:
    """``(slope, se)`` for P(home) = sigmoid(market_logodds + slope · gap).

    One free parameter, the market's own log-odds carried as a fixed
    offset, so the slope answers exactly one question: how much of our
    disagreement with the market should be believed. Newton–Raphson;
    the log-likelihood is concave in a single parameter so it converges
    in a handful of steps from zero, and zero — "believe the market" —
    is the right place to start from.
    """
    b = 0.0
    for _ in range(60):
        g = h = 0.0
        for x, offset, y in obs:
            p = 1.0 / (1.0 + math.exp(-max(min(offset + b * x, 40.0), -40.0)))
            g += x * (y - p)
            h += x * x * p * (1.0 - p)
        if h <= 1e-12:
            return float("nan"), float("nan")
        step = g / h
        b += step
        if abs(step) < 1e-9:
            break
    else:
        return float("nan"), float("nan")
    return b, math.sqrt(1.0 / h) if h > 0 else float("nan")


def fit_one(conn, sport: str, market: str) -> Fit:
    """Least squares of ``actual − close`` on ``model − close``.

    For the moneyline, the logistic equivalent — see
    `_moneyline_observations` for why that is the same measurement.
    """
    try:
        pairs = observations(conn, sport, market)
    except ValueError as exc:
        # No registered variance for this sport. Held, not crashed — a
        # refresh over every sport in the DB must not be taken down by
        # the one league nobody has fitted yet.
        return Fit(sport, market, missing=str(exc).split(" — ")[0])
    n = len(pairs)
    if n < 3:
        return Fit(sport, market, n=n,
                   missing=f"{n} graded games with a close")
    if market == "moneyline":
        slope, se = _fit_logistic(pairs)
        if slope != slope:
            return Fit(sport, market, n=n,
                       missing="the logistic fit did not converge")
        hit = sum(1 for x, _o, y in pairs if x and (y > 0.5) == (x > 0))
        decided = sum(1 for x, _o, _y in pairs if x)
        return Fit(sport, market, n=n, slope=slope, se=se, hit=hit,
                   decided=decided,
                   bias=sum(p[0] for p in pairs) / n)
    mx = sum(p[0] for p in pairs) / n
    my = sum(p[1] for p in pairs) / n
    sxx = sum((p[0] - mx) ** 2 for p in pairs)
    if sxx <= 0:
        return Fit(sport, market, n=n,
                   missing="the model never disagreed with the close")
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pairs)
    slope = sxy / sxx
    intercept = my - slope * mx
    resid = [p[1] - (intercept + slope * p[0]) for p in pairs]
    dof = n - 2
    rvar = sum(r * r for r in resid) / dof if dof > 0 else float("nan")
    se = math.sqrt(rvar / sxx) if rvar == rvar and rvar >= 0 else float("nan")
    hit = sum(1 for p in pairs if p[0] and p[1] and (p[1] > 0) == (p[0] > 0))
    decided = sum(1 for p in pairs if p[0] and p[1])
    return Fit(sport, market, n=n, slope=slope, se=se, hit=hit,
               decided=decided, bias=mx,
               resid_sd=math.sqrt(rvar) if rvar == rvar else float("nan"))


def _adopted_shrink(f: Fit) -> float:
    """The slope, clamped into the range a shrink is allowed to occupy."""
    return min(max(f.slope, FLOOR), min(CEIL, MAX_ADOPTED))


def refresh(db="data/history.db", sport: str | None = None,
            markets=("total", "spread", "moneyline")) -> dict:
    """Fit every game market and persist the fits that earned adoption.

    Returns ``{"adopted": [...], "held": [...]}``; a held fit carries the
    reason, because a calibration that quietly declines to adopt is the
    same invisibility this module exists to remove.
    """
    conn = db if hasattr(db, "execute") else sqlite3.connect(db)
    own = conn is not db
    try:
        conn.row_factory = sqlite3.Row
        sports = ([sport] if sport else
                  [r[0] for r in conn.execute(
                      "SELECT DISTINCT sport FROM games "
                      "WHERE home_score IS NOT NULL")])
        fits = [fit_one(conn, s, m) for s in sports for m in markets]
    finally:
        if own:
            conn.close()
    state = _read_state()
    adopted, held = [], []
    for f in fits:
        key = f"{f.sport}:{f.market}"
        if f.missing:
            held.append({"key": key, "why": f.missing})
            continue
        if f.slope != f.slope or f.se != f.se:
            held.append({"key": key, "why": "unusable fit"})
            continue
        if f.n < MIN_N:
            held.append({"key": key, "why": f"{f.n} games, needs {MIN_N}"})
            continue
        if f.se > MAX_SE:
            held.append({"key": key,
                         "why": f"slope ±{f.se:.3f} is looser than the "
                                f"±{MAX_SE} needed to act on"})
            continue
        state[key] = {"shrink": round(_adopted_shrink(f), 4),
                      "slope": round(f.slope, 4), "se": round(f.se, 4),
                      "n": int(f.n), "hit_rate": round(f.hit_rate, 4),
                      "sport": f.sport, "market": f.market,
                      "fit_at": time.time()}
        adopted.append({"key": key, **state[key]})
    if adopted:
        _write_state(state)
        _cache.clear()
    return {"adopted": adopted, "held": held}


def _read_state() -> dict:
    try:
        with open(STATE_PATH, encoding="utf-8") as fh:
            return json.load(fh) or {}
    except (OSError, ValueError):
        return {}


def _write_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)
    os.replace(tmp, STATE_PATH)


def measured(sport: str, market: str) -> dict | None:
    """The persisted fit for one sport+market, or None.

    Never raises. This is read on the pricing path for every game bet on
    every board, and a half-written state file must cost the calibration,
    not the board.
    """
    key = f"{sport}:{market}"
    if key in _cache:
        return _cache[key]
    entry = _read_state().get(key)
    if entry is not None:
        try:
            ok = (FLOOR <= float(entry["shrink"]) <= CEIL
                  and int(entry["n"]) >= MIN_N
                  and float(entry["se"]) <= MAX_SE)
        except (KeyError, TypeError, ValueError):
            ok = False
        if not ok:
            entry = None
    _cache[key] = entry
    return entry


def shrink_for(sport: str, market: str) -> float | None:
    """How much of a raw disagreement to keep, or None if never measured."""
    entry = measured(sport, market)
    if entry is None:
        return None
    try:
        return float(entry["shrink"])
    except (KeyError, TypeError, ValueError):
        return None


def note_for(sport: str, market: str) -> str | None:
    """One line for the card explaining a measured haircut, or None.

    Only speaks when the measurement actually changed something. A fit
    that landed on the flat prior has nothing to add to a card.
    """
    entry = measured(sport, market)
    if entry is None:
        return None
    try:
        shrink, n = float(entry["shrink"]), int(entry["n"])
        hit = float(entry.get("hit_rate") or 0.0)
    except (TypeError, ValueError):
        return None
    if shrink <= 0.02:
        note = (f"Measured on our own record: over {n} graded games this "
                f"model's disagreements with the closing number carried no "
                f"information")
        if market != "moneyline" and hit:
            note += f" — its side beat the close {hit:.1%} of the time"
        return note + ". Priced at the market until that changes"
    if shrink < 0.45:
        return (f"Measured on our own record: {shrink:.0%} of a "
                f"disagreement with the close has held up over {n} graded "
                f"games, so that is all this price keeps")
    return None


if __name__ == "__main__":                       # pragma: no cover
    import sys
    argv = sys.argv[1:]
    sport = argv[argv.index("--sport") + 1] if "--sport" in argv else None
    db = argv[argv.index("--db") + 1] if "--db" in argv else "data/history.db"
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    sports = ([sport] if sport else
              [r[0] for r in conn.execute("SELECT DISTINCT sport FROM games "
                                          "WHERE home_score IS NOT NULL")])
    for s in sports:
        for m in ("total", "spread", "moneyline"):
            print(fit_one(conn, s, m).summary())
    conn.close()
    out = refresh(db=db, sport=sport)
    for a in out["adopted"]:
        print(f"  adopted {a['key']}: shrink {a['shrink']}  (slope "
              f"{a['slope']:+.3f} ± {a['se']:.3f}, n={a['n']})")
    for h in out["held"]:
        print(f"  held    {h['key']}: {h['why']}")
