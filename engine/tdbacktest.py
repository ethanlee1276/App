"""Grade the touchdown model against four seasons of who actually scored.

THE GAP THIS CLOSES. `engine.touchdowns` is the model behind every
anytime-TD pick and every longshot on both football boards — the picks
Ethan cares most about — and on 2026-08-27 it had never been measured.
`backtest.py` walks the yardage and reception markets; `anytime_td`
appears nowhere in it. The touchdown board shipped, graded itself
against results, and no one had ever asked whether its probabilities
were true.

They have to be true in a specific place. A longshot lives in the TAIL:
a +450 anytime-TD price is asking whether an 18% shot is really 18%, and
a model that is beautifully calibrated at 40% and quietly overconfident
at 15% will look healthy in aggregate while losing money on every
longshot it publishes. So this reports by PROBABILITY BAND, and the
bands at the bottom are the ones that matter.

WHAT IS REPLAYED. The production `td_probability`, with production
inputs, walked forward one week at a time:

  * opportunity share, red-zone usage and touchdown history from weeks
    STRICTLY BEFORE the week being graded;
  * the team's implied total from the schedule's own closing spread and
    total — the real market number the live board reads, not a proxy;
  * the same position baselines, blends and clamps the board ships.

The defence and weather multipliers are left neutral. Both need a
`Team`/`Weather` the history rows cannot reconstruct faithfully, and a
guessed multiplier would be measuring a model nobody runs. The result is
therefore a floor: the shipped model has strictly more information than
this replay does.

Standard library only.
"""

from __future__ import annotations

import math

from .fantasy import _short_key
from .models import Game, Prop, Team, DefenseProfile, Weather, GameLog, ANYTIME_TD
from .touchdowns import RedZoneUsage, td_probability

#: Weeks of prior form behind an opportunity share, matching the live
#: usage maps rather than inventing a second window.
FORM_WEEKS = 6

#: Player-weeks before a player is graded at all. Below this his history
#: is thinner than the model's own blend expects and the row says more
#: about the sample than the model.
MIN_PRIOR_WEEKS = 3

#: The probability bands the report splits on. Deliberately finer at the
#: BOTTOM: that is where longshots live and where a few points of
#: overconfidence is the whole margin.
BANDS = ((0.00, 0.10), (0.10, 0.18), (0.18, 0.28),
         (0.28, 0.40), (0.40, 0.60), (0.60, 1.01))


def _neutral_opponent(abbr: str) -> Team:
    """A league-average defence — see the module docstring on why."""
    return Team(abbr=abbr, name=abbr, defense=DefenseProfile(team=abbr))


def implied_total(total, spread, is_home: bool) -> float | None:
    """The team's own implied points from the game's closing numbers.

    ``spread`` is the HOME team's number (negative = home favoured), the
    convention `engine.ingest` stores and `engine.gamebacktest` relies
    on. Home points are ``(total - spread) / 2``: a home team laying 7 in
    a 47 game is implied for 27.
    """
    try:
        t, s = float(total), float(spread)
    except (TypeError, ValueError):
        return None
    if t <= 0:
        return None
    home = (t - s) / 2.0
    return home if is_home else t - home


class TDBacktest:
    """What the touchdown model claimed, and what actually happened."""

    def __init__(self, label: str = "NFL"):
        #: What the summary calls itself. The class is sport-agnostic —
        #: `engine.cfbtdfit` grades college football through it — and a
        #: report headed "NFL" over college rows is the kind of label
        #: nobody re-reads once it has scrolled past.
        self.label = label
        self.n = 0
        self.scored = 0
        self.claimed = 0.0
        self.bands: dict = {}
        self.brier = 0.0
        self._sq = 0.0
        #: (claimed probability, did he score) — exactly the shape
        #: `engine.calibrate.fit` takes, which is the whole point: the
        #: touchdown market has no LINE, so `calibrate.fit_market` (which
        #: walks over/under props) can never fit it, and (nfl,
        #: anytime_td) has therefore sat on a neutral correction since the
        #: board shipped. These pairs are the missing input.
        self.pairs: list = []

    def add(self, prob: float, scored: int) -> None:
        self.n += 1
        self.scored += scored
        self.claimed += prob
        self._sq += (prob - scored) ** 2
        self.pairs.append((prob, scored))
        for lo, hi in BANDS:
            if lo <= prob < hi:
                b = self.bands.setdefault((lo, hi),
                                          {"n": 0, "claimed": 0.0, "scored": 0})
                b["n"] += 1
                b["claimed"] += prob
                b["scored"] += scored
                break

    def finish(self) -> "TDBacktest":
        if self.n:
            self.brier = self._sq / self.n
        for b in self.bands.values():
            b["claimed"] = b["claimed"] / b["n"] if b["n"] else 0.0
            b["landed"] = b["scored"] / b["n"] if b["n"] else 0.0
            b["gap"] = b["landed"] - b["claimed"]
        return self

    @property
    def base_rate(self) -> float:
        return (self.scored / self.n) if self.n else 0.0

    def summary(self, min_band_n: int = 40) -> str:
        if not self.n:
            return ("No touchdown rows to grade. Needs ingested anytime_td "
                    "logs plus schedule spreads and totals.")
        lines = [
            f"{self.label} anytime-TD backtest · {self.n:,} player-weeks",
            f"  Claimed     {self.claimed / self.n:.1%} on average, "
            f"{self.base_rate:.1%} actually scored",
            f"  Brier       {self.brier:.4f}  (always-guess "
            f"{self.base_rate * (1 - self.base_rate):.4f})",
            "  By band     claimed vs landed — the bottom rows are the "
            "longshots",
        ]
        for lo, hi in BANDS:
            b = self.bands.get((lo, hi))
            if not b or b["n"] < min_band_n:
                continue
            flag = ""
            if b["gap"] <= -0.03:
                flag = "  ⚠️  overconfident"
            elif b["gap"] >= 0.03:
                flag = "  (conservative)"
            lines.append(
                f"    {lo:.0%}-{hi:.0%}".ljust(16)
                + f"{b['n']:>6} bets   claimed {b['claimed']:.1%} → landed "
                  f"{b['landed']:.1%}   {b['gap']:+.1%}{flag}")
        return "\n".join(lines)


#: Player-weeks behind a touchdown calibration before it may be adopted.
#: `calibrate.fit` runs its own bake-off on a held-out slice, so this is
#: only the floor below which the split itself is noise.
MIN_FIT_PAIRS = 2_000


def fit_calibration(conn, sport: str = "nfl", seasons=None, path=None):
    """Fit and persist the touchdown market's temperature. Returns the fit.

    THE HOLE THIS FILLS. `calibrate.SPORT_MARKETS["nfl"]` lists
    pass_yds, rush_yds, rec_yds and receptions — `anytime_td` is absent,
    and not by the deliberate reasoning the module gives for leaving CFB
    and UFC out. It cannot simply be added: `fit_market` walks
    over/under props and a touchdown has no LINE, so there is nothing
    for it to compare a projection against. The consequence was that
    `correction_for("nfl", "anytime_td")` has returned the neutral
    (1.0, 0.0) since the touchdown board shipped, while
    `longshots.calibrated_prob` faithfully applied it to every pick.

    A walk-forward replay produces exactly what `calibrate.fit` wants —
    (claimed probability, did he score) — so the market can be fitted
    through the front door after all. The model is CONSERVATIVE, and in
    one direction at every level: over five seasons and 22,099
    player-weeks it claims 15.5% on average where 20.0% actually score,
    and every band lands high — 5.9% claiming against 8.4% landing at the
    bottom, 46.1% against 55.3% at the top.

    That direction matters for the reason this was worth doing at all.
    Under-rating the bottom band is under-rating LONGSHOTS — the model
    was quietly passing over the very picks it exists to find.

    HOW WELL THE CORRECTION HOLDS UP, measured leave-one-season-out so
    the answer is not read off the data it was fitted on: every fold
    lands on the same shape (T 1.10-1.14, intercept +0.16 to +0.24), and
    on the held-out seasons the worst band gap falls from 9.2 points to
    1.4 with the aggregate at 20.3% claimed against 20.0% landed.
    """
    from . import calibrate
    report = run(conn, sport=sport, seasons=seasons)
    if len(report.pairs) < MIN_FIT_PAIRS:
        return None, report
    fit = calibrate.fit(report.pairs, sport=sport, market="anytime_td")
    fit.basis = calibrate.BASIS_HISTORY
    import datetime as _dt
    fit.fitted_at = _dt.date.today().isoformat()
    calibrate.save({f"{sport}:anytime_td": fit},
                   path or calibrate.DEFAULT_PATH)
    calibrate.reset_cache()
    return fit, report


def _prior_form(weeks: dict, upto: list, market: str) -> float:
    """Per-game average of ``market`` over the most recent prior weeks."""
    vals = [weeks[w].get(market, 0.0) for w in upto]
    return (sum(vals) / len(vals)) if vals else 0.0


#: THE ONLY SPORT THIS REPLAYS. `run` calls `touchdowns.td_probability`,
#: which IS the NFL model — its own baselines, its own script curve, its
#: own red-zone blend. College football ships `engine.cfb.tds`, a
#: different chain with different constants, and its replay is
#: `engine.cfbtdfit.run`.
#:
#: The `sport` argument names which LOGS to read, and nothing stopped it
#: reading college ones. Doing that on 2026-08-30 produced a confident
#: table showing the college calibration failing badly — 8% claimed
#: against 15.7% landed AFTER correction — and it was the NFL model being
#: graded on college data. On the real college chain the same bands come
#: out at 1.25 and 1.05 and the stored fit is sound. Nothing was wrong
#: except the question.
#:
#: So the guard is here rather than in a docstring nobody reads at the
#: call site. Pass `allow_any_sport=True` to grade the NFL model on
#: another sport's logs ON PURPOSE — that is a comparison between chains,
#: not a measurement of that sport's board, and it must not be reported
#: as one.
NFL_ONLY = "nfl"


def run(conn, sport: str = NFL_ONLY, seasons=None,
        min_prior: int = MIN_PRIOR_WEEKS, collect=None,
        allow_any_sport: bool = False) -> TDBacktest:
    """Walk forward through every ingested week and grade the model.

    NFL ONLY unless ``allow_any_sport`` — see :data:`NFL_ONLY` for what
    happened the one time that was ignored.

    ``collect(row)`` optionally receives one dict per graded player-week,
    carrying the identity the grading itself does not need — player,
    team, season, week — so a caller can join these probabilities to
    something else. `engine.tdbook` joins them to the harvested closing
    price, which is the only way to ask where the model disagrees with
    the market rather than only where it disagrees with the outcome.
    """
    if sport != NFL_ONLY and not allow_any_sport:
        raise ValueError(
            f"tdbacktest replays the NFL touchdown model; grading it on "
            f"{sport!r} logs measures a chain that sport does not ship. "
            f"College football is engine.cfbtdfit.run. Pass "
            f"allow_any_sport=True only for a deliberate cross-chain "
            f"comparison.")
    where = "WHERE sport=?"
    args: list = [sport]
    if seasons:
        where += " AND season IN (%s)" % ",".join("?" * len(seasons))
        args += list(seasons)

    # Every player-week's raw markets, keyed so a week can look backwards.
    rows = conn.execute(
        f"SELECT season, period, player, team, opponent, position, home, "
        f"market, value FROM player_game_logs {where} AND market IN "
        f"('anytime_td','targets','carries','rz_tgt','rz_car','i5_car',"
        f"'xfp')",
        args).fetchall()
    # KEYED THE WAY THE LIVE PATH KEYS, and this is not a detail. The
    # red-zone rows come from play-by-play and spell a player
    # "E.Higgins"; the stat rows spell him "Elijah Higgins". Keyed on the
    # raw name they are two different people, so no row ever carries both
    # a touchdown outcome and a red-zone history — which is exactly what
    # the first cut of this module did, silently, and it measured the
    # model with its single best predictor switched off. `_short_key`
    # (first initial, last name, team) is what `engine.nflusage` joins on
    # for the same reason; using anything else here measures a model
    # nobody runs.
    form: dict = {}
    display: dict = {}
    for r in rows:
        key = (r["season"], _short_key(r["player"], r["team"]))
        wk = form.setdefault(key, {}).setdefault(r["period"], {})
        wk[r["market"]] = float(r["value"] or 0.0)
        # Play-by-play rows carry no position or opponent; keep whatever
        # the stat rows said rather than letting a pbp row blank it.
        if r["position"]:
            wk["_pos"] = r["position"]
        if r["opponent"]:
            wk["_opp"] = r["opponent"]
        wk.setdefault("_pos", "")
        wk.setdefault("_opp", "")
        wk["_home"] = bool(r["home"])
        if len(str(r["player"])) > len(display.get(key, "")):
            display[key] = str(r["player"])

    # The game numbers, by (season, week, team) — the real closing market.
    games: dict = {}
    for g in conn.execute(
            "SELECT season, period, home, away, spread, total FROM games "
            "WHERE sport=? AND total IS NOT NULL", (sport,)):
        games[(g["season"], g["period"], g["home"])] = (g["total"], g["spread"], True)
        games[(g["season"], g["period"], g["away"])] = (g["total"], g["spread"], False)

    # Team totals per week, so an opportunity share has a denominator.
    team_week: dict = {}
    for (season, short), weeks in form.items():
        team = short[2]
        for wk, marks in weeks.items():
            t = team_week.setdefault((season, wk, team),
                                     {"opp": 0.0, "xfp": 0.0})
            t["opp"] += marks.get("targets", 0.0) + marks.get("carries", 0.0)
            t["xfp"] += marks.get("xfp", 0.0)

    # IN TIME ORDER, AND THAT IS NOT COSMETIC. `calibrate.bake_off`
    # holds out "the later part of the sample" and judges a fitted
    # correction on it. Built the obvious way — a loop over players, each
    # walked forward — these pairs come out grouped by PLAYER, so the
    # judge was scoring the correction on an arbitrary subset of the
    # league rather than on its future, and its held-out Brier (0.125
    # against 0.170 over the whole sample) says how unrepresentative that
    # slice can be. Graded rows are collected and sorted before they are
    # added, so the held-out slice is the later weeks, which is what the
    # bake-off's own docstring promises.
    graded: list = []
    out = TDBacktest()
    for (season, short), weeks in form.items():
        team = short[2]
        player = display.get((season, short), short[1])
        ordered = sorted(weeks)
        for idx, wk in enumerate(ordered):
            prior = ordered[max(0, idx - FORM_WEEKS):idx]
            if len(prior) < min_prior:
                continue
            marks = weeks[wk]
            if "anytime_td" not in marks:
                continue
            game = games.get((season, wk, team))
            if not game:
                continue
            total, spread, is_home = game
            implied = implied_total(total, spread, is_home)
            if implied is None:
                continue

            opp_own = _prior_form(weeks, prior, "targets") \
                + _prior_form(weeks, prior, "carries")
            team_opp = sum(team_week.get((season, w, team), {}).get("opp", 0.0)
                           for w in prior) / len(prior)
            share = (opp_own / team_opp) if team_opp > 0 else 0.0

            rz_tgt = _prior_form(weeks, prior, "rz_tgt")
            rz_car = max(_prior_form(weeks, prior, "rz_car"),
                         _prior_form(weeks, prior, "i5_car"))
            i5 = _prior_form(weeks, prior, "i5_car")
            rz_share = 0.0
            if team_opp > 0:
                rz_share = min((rz_tgt + rz_car) / max(team_opp * 0.12, 0.1), 1.0)
            rz = RedZoneUsage(carries_inside_5=i5, carries_inside_10=rz_car,
                              targets_inside_10=rz_tgt,
                              rz_touch_share=round(rz_share, 3),
                              measured=bool(rz_tgt or rz_car))

            logs = [GameLog(week=i, opponent="", value=weeks[w].get("anytime_td", 0.0))
                    for i, w in enumerate(prior)]
            prop = Prop(player=player, team=team, opponent=marks.get("_opp", ""),
                        position=marks.get("_pos", ""), market=ANYTIME_TD,
                        logs=logs, career_avg=0.0, vs_opponent_avg=None, lines=[])
            gm = Game(home=team if is_home else marks.get("_opp", ""),
                      away=marks.get("_opp", "") if is_home else team,
                      weather=Weather(dome=True, measured=True),
                      total=float(total), spread=float(spread))
            # THE xFP SHARE, as of the weeks already played. The board
            # blends its touchdown share toward this (touchdowns.
            # XFP_SHARE_WEIGHT); a replay that leaves it out fits a
            # calibration for a model nobody runs — the same fault the
            # usage bridge had in engine/backtest, and the reason
            # `nflusage.xfp_roles` exists.
            own_xfp = _prior_form(weeks, prior, "xfp")
            team_xfp = sum(team_week.get((season, w, team), {}).get("xfp", 0.0)
                           for w in prior) / len(prior)
            xfp = ({"xfp_share": own_xfp / team_xfp}
                   if team_xfp > 0 and own_xfp > 0 else None)
            prob, _why = td_probability(
                prop, gm, _neutral_opponent(marks.get("_opp", "") or "OPP"),
                share, red_zone=rz, xfp=xfp)
            scored = 1 if marks.get("anytime_td", 0.0) > 0 else 0
            graded.append((season, wk, float(prob), scored))
            if collect is not None:
                # THE PRIOR-WINDOW INPUTS TRAVEL WITH THE ROW. Anything
                # asking "does feature X add to this model" has to be
                # built on the same walked-forward window this used, or
                # it is comparing two different histories and calling the
                # difference a signal. Recomputing them in the caller is
                # how that goes wrong quietly.
                collect({"season": season, "week": wk,
                         "player": display.get((season, short), ""),
                         "team": team, "prob": float(prob), "scored": scored,
                         "xfp_share": (xfp or {}).get("xfp_share"),
                         "position": marks.get("_pos", ""),
                         "opponent": marks.get("_opp", ""),
                         "implied": implied, "spread": float(spread),
                         "is_home": is_home,
                         "opp_share": share, "team_opp": team_opp,
                         "own_opp": opp_own, "rz_share": rz_share,
                         "rz_car": rz_car, "i5_car": i5, "rz_tgt": rz_tgt,
                         "prior_weeks": list(prior)})
    for _season, _wk, prob, scored in sorted(graded, key=lambda g: g[:2]):
        out.add(prob, scored)
    return out.finish()


if __name__ == "__main__":                       # pragma: no cover
    import sys
    from . import db as _db
    argv = sys.argv[1:]
    conn = _db.connect()
    if "--fit" in argv:
        fit, report = fit_calibration(conn)
        print(report.summary())
        if fit is None:
            print(f"\n  Not fitted — under {MIN_FIT_PAIRS:,} graded "
                  f"player-weeks.")
        else:
            print(f"\n  Fitted and saved: T = {fit.temperature}  "
                  f"bias = {fit.intercept:+.3f}")
            print(f"  Brier {fit.brier_before:.4f} → {fit.brier_after:.4f}")
            print(f"  {fit.verdict}")
    else:
        print(run(conn).summary())
        print("\n  --fit to fit and save the correction the board reads.")
    conn.close()
