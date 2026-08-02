"""Walk-forward backtest for the HOME-RUN LONG SHOT model.

The per-market calibration sweep has a "Home Runs" row, and it is not this
model. That row runs the generic prop model over home runs — a market it
never bets, which is why it reports 0 bets. The model that actually
produces the Long Shots board is ``engine.mlb.homeruns.hr_probability``,
and until this file nothing measured it against a single real outcome.

That mattered more than a gap usually does: on a summer night the Long
Shots board is often the ONLY board holding open bets, so the one model
taking money was the one model nobody had scored.

What this can and cannot reconstruct
------------------------------------
The model multiplies a baseline rate by contact quality, the pitcher, and
the park/weather environment. Only some of that survives in the history DB,
so rather than quietly substituting defaults and reporting a clean number,
every run states its input coverage:

  * game logs      — stored, and walked forward properly (game i is
                     projected from games [:i] only)
  * park           — resolved from the home team, so the HR factor is real
  * weather        — from the stored game row where it exists
  * Statcast       — NOT stored historically. The model falls back to
                     season rate alone, which is the same fallback it uses
                     live for a hitter with no profile, and it is honest
                     about it on the pick. This backtest therefore measures
                     the FALLBACK path, and says so.
  * lineup spot    — not stored; plate appearances default to 4.0

A number produced with half the inputs missing is still worth having —
it bounds the model from below, and a model that is badly calibrated on
its baseline is not rescued by contact quality. But it is not the same
number the live board computes, and the report must never imply it is.

Everything here calls the production ``hr_probability``. Reimplementing it
would measure a copy.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .homeruns import hr_probability
from .models import HOME_RUNS, MLBGame, MLBGameLog, MLBProp, MLBWeather
from .parks import PARKS, GENERIC_PARK
from ..backtest import SettledProp, evaluate

# The Long Shots board only ever backs the OVER — "does he hit one" — so
# hit_prob is always P(over) and the calibration bins cannot be inverted by
# a side flip. Home runs are the one market where that inversion silently
# grades everything backwards (see engine/backtest.py:evaluate).
HR_LINE = 0.5

_TEAM_PARK = {p.team: key for key, p in PARKS.items() if getattr(p, "team", "")}


@dataclass
class HRCoverage:
    """Which inputs were real, so the headline number can be read honestly."""
    props: int = 0
    with_park: int = 0
    with_weather: int = 0
    with_statcast: int = 0
    with_lineup_spot: int = 0
    with_book_line: int = 0

    def lines(self) -> list[str]:
        def pc(n):
            return f"{n / self.props:.0%}" if self.props else "—"
        return [
            f"  Inputs      park {pc(self.with_park)} · weather "
            f"{pc(self.with_weather)} · Statcast {pc(self.with_statcast)} · "
            f"lineup spot {pc(self.with_lineup_spot)}",
            f"  Priced      {self.with_book_line} of {self.props} against a "
            f"real harvested book line",
        ]


def hr_entries(conn, seasons: list[int] | None = None,
               min_games: int = 20) -> list[dict]:
    """Chronological home-run games per player, WITH the context the model
    needs. ``entries_for_market`` drops team/opponent, and without the home
    team there is no park, and without the park the environment multiplier
    is a constant."""
    q = ("SELECT player, team, opponent, home, value, period "
         "FROM player_game_logs WHERE sport='mlb' AND market=?")
    args: list = [HOME_RUNS]
    if seasons:
        q += " AND season IN (%s)" % ",".join("?" * len(seasons))
        args += list(seasons)
    q += " ORDER BY player, season, period, game_id"

    grouped: dict[str, dict] = {}
    for r in conn.execute(q, args):
        e = grouped.setdefault(r["player"], {"name": r["player"], "values": [],
                                             "dates": [], "teams": [],
                                             "opps": [], "homes": []})
        e["values"].append(float(r["value"]))
        e["dates"].append(str(r["period"]))
        e["teams"].append(str(r["team"] or ""))
        e["opps"].append(str(r["opponent"] or ""))
        e["homes"].append(bool(r["home"]))
    return [e for e in grouped.values() if len(e["values"]) >= min_games]


def game_context(conn) -> dict:
    """(date, home, away) → stored conditions, where the ingest captured
    them. Missing rows are not an error; they are a coverage number."""
    out: dict = {}
    try:
        rows = conn.execute(
            "SELECT period, home, away, roof, temp, wind FROM games "
            "WHERE sport='mlb'")
    except Exception:
        return out
    for r in rows:
        out[(str(r["period"]), str(r["home"]), str(r["away"]))] = {
            "roof": (r["roof"] or ""), "temp": r["temp"], "wind": r["wind"]}
    return out


def _build_game(date: str, team: str, opp: str, at_home: bool,
                ctx: dict) -> tuple[MLBGame, bool, bool]:
    home, away = (team, opp) if at_home else (opp, team)
    park_key = _TEAM_PARK.get(home, "")
    c = ctx.get((date, home, away)) or {}
    w = MLBWeather()
    got_weather = False
    if c.get("temp") is not None:
        w.temp_f = float(c["temp"])
        got_weather = True
    if c.get("wind") is not None:
        w.wind_mph = float(c["wind"])
        got_weather = True
    if str(c.get("roof", "")).lower() in ("closed", "dome", "indoor"):
        w.roof_closed = True
        got_weather = True
    g = MLBGame(home=home, away=away, park=park_key or GENERIC_PARK.key,
                date=date, weather=w)
    return g, bool(park_key), got_weather


def settled_hr(entries: list[dict], ctx: dict, min_history: int = 20,
               limit: int = 40, real_lines: dict | None = None
               ) -> tuple[list[SettledProp], HRCoverage]:
    """One SettledProp per player-game, scored by the production model."""
    from ..sources.oddsapi import normalize_name
    real_lines = real_lines or {}
    out: list[SettledProp] = []
    cov = HRCoverage()

    for e in entries:
        vals, dates = e["values"], e["dates"]
        teams, opps, homes = e["teams"], e["opps"], e["homes"]
        for i in range(min_history, len(vals)):
            prior = vals[:i][::-1][:limit]           # most-recent-first
            date = dates[i] if i < len(dates) else ""
            team = teams[i] if i < len(teams) else ""
            opp = opps[i] if i < len(opps) else ""
            at_home = homes[i] if i < len(homes) else True
            game, got_park, got_weather = _build_game(date, team, opp,
                                                      at_home, ctx)
            prop = MLBProp(
                player=e["name"], team=team, opponent=opp, position="",
                market=HOME_RUNS,
                logs=[MLBGameLog(game=len(prior) - j, opponent="",
                                 value=float(v))
                      for j, v in enumerate(prior)],
                career_avg=sum(vals[:i]) / i,
                vs_pitcher_avg=None, lines=[],
                # Not stored historically. Left at the model's own defaults
                # rather than invented, which is what makes this the
                # fallback path and why the report says so.
                lineup_spot=0, statcast=None)
            prob, _meta = hr_probability(prop, game)

            quote = real_lines.get((normalize_name(e["name"]), date))
            over_odds = int((quote or {}).get("over_odds") or 0)
            basis, odds = "naive", 0
            if over_odds:
                basis, odds = "book", over_odds
                cov.with_book_line += 1

            cov.props += 1
            cov.with_park += 1 if got_park else 0
            cov.with_weather += 1 if got_weather else 0
            out.append(SettledProp(
                player=e["name"], market=HOME_RUNS, line=HR_LINE, odds=odds,
                hit_prob=prob, projection=prob, actual=float(vals[i]),
                recommended=False, side="OVER", basis=basis))
    return out, cov


def lift(settled: list[SettledProp], buckets: int = 5) -> list[dict]:
    """Do the hitters the model likes MOST actually homer more?

    For this board, ranking beats calibration and it is not close. The Long
    Shots page picks three names a night off the top of the list; it never
    bets the population. So the question is not "is 11% right on average"
    but "do the names at the top go deep more often than the names at the
    bottom" — and Brier cannot answer that.

    Brier is actively misleading on a rare event. Home runs land ~10% of
    the time, so predicting 10% for everybody scores about 0.09, and even
    perfect knowledge of each hitter's true rate only improves it to ~0.091
    — a skill score of a couple of percent. A model with NO discrimination
    and a model with all of it are separated by a rounding error in that
    number, while the thing the board actually does with the model lives
    entirely in the gap this function measures.
    """
    rows = [s for s in settled if s.hit_prob is not None]
    if len(rows) < buckets * 50:
        return []
    rows.sort(key=lambda s: s.hit_prob)
    out, size = [], len(rows) // buckets
    for b in range(buckets):
        lo = b * size
        hi = len(rows) if b == buckets - 1 else (b + 1) * size
        chunk = rows[lo:hi]
        if not chunk:
            continue
        out.append({
            "bucket": b + 1,
            "n": len(chunk),
            "said": sum(s.hit_prob for s in chunk) / len(chunk),
            "actual": sum(1 for s in chunk if s.actual > 0) / len(chunk),
        })
    return out


def backtest_hr(conn, min_history: int = 20, limit: int = 40,
                seasons: list[int] | None = None, use_real_lines: bool = True):
    """The whole thing: entries → settled → report, plus input coverage."""
    from .. import db as _db
    real_lines: dict = {}
    if use_real_lines:
        from ..sources.oddsapi import normalize_name
        try:
            for (player, date), q in _db.closing_odds_by_date(
                    conn, "mlb", HOME_RUNS).items():
                real_lines[(normalize_name(player), date)] = q
        except Exception:
            real_lines = {}
    entries = hr_entries(conn, seasons=seasons, min_games=min_history + 1)
    settled, cov = settled_hr(entries, game_context(conn),
                              min_history=min_history, limit=limit,
                              real_lines=real_lines)
    return evaluate(settled), cov, settled
