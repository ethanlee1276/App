"""Run the deep fitters for every sport that has the history to support it.

Three rungs walk the HISTORY DB through a sport's own engine rather than
through the journal: the recency dial (`formfit`), the per-player memory
(`playerfit`) and the probability temperatures (`calibrate`). They are
the strongest fits this project has, and until now they were the only
learning on the site a human had to remember to run.

The gap, quoting launch.py's own note from 2026-08-16 — Ethan: *"i wanna
make sure the self learning and all of that shit is wrapped into nfl
too."* — was never the code. All three take ``--sport`` and all three
DEFAULT TO MLB, so unless somebody typed the flag, only baseball had
ever been deep-fitted. `engine.journalfit` covers every sport off the
journal and runs nightly; that is the universal rung, and it is a
different and weaker thing than this.

It was worth automating because it is not a formality. Run against the
NFL's 329,434 ingested log rows for the first time on 2026-08-27, the
recency dial moved three of its four markets, each on more than twenty
thousand settled predictions.

ORDER IS LOAD-BEARING and is the one launch.py's refit command uses:
dial, then memory, then temperature LAST — the first two move the model
the third is calibrating, and a temperature fitted before them describes
a model that no longer exists.

Each fitter carries its own adoption gate (a minimum sample, a Brier
margin, a plateau check), so a sport without the history declines on its
own. That is why this can be scheduled generously: the schedule does not
decide what gets adopted, the evidence does.

Standard library only.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: dial → memory → temperature. Do not reorder; see the docstring.
REFIT_ORDER = (("recency dial", "formfit.py"),
               ("player memory", "playerfit.py"),
               ("temperatures", "calibrate.py"))

#: Log rows a sport needs before a deep fit is even attempted. Well below
#: any fitter's own adoption bar — this only avoids spending minutes of a
#: 1-vCPU box's night walking an empty table.
MIN_LOG_ROWS = 2_000

#: A fitter that has not finished in this long has found something
#: pathological. Bounded so a weekly job cannot become a permanent one.
#: Forty-five minutes since 2026-10-14: the NBA's temperature fit, on
#: twice the history it had (last season's box scores read again with
#: steals, blocks and turnovers), ran past the old fifteen and was skipped;
#: run by hand without a limit on the box it took 17 minutes, niced, beside
#: the board sweep. The refit is a detached child, outside the chores'
#: hour, so the longer bound costs the site nothing.
TIMEOUT_S = 2700


def sports_with_history(db: str = "data/history.db") -> list[str]:
    """Which supported sports actually have enough logs to fit."""
    return list(_row_counts(db))


def _row_counts(db: str = "data/history.db") -> dict:
    """{sport: its player_game_logs rows} for every supported sport with
    enough of them to fit, in sport order. The round reads the count as
    "has anything new landed since this sport's last full fit"."""
    import sqlite3
    try:
        from formfit import SPORT_MARKETS          # noqa: PLC0415
    except Exception:                              # noqa: BLE001
        sys.path.insert(0, ROOT)
        from formfit import SPORT_MARKETS          # noqa: PLC0415
    path = db if os.path.isabs(db) else os.path.join(ROOT, db)
    if not os.path.isfile(path):
        return {}
    conn = sqlite3.connect(path)
    try:
        out = {}
        for sport in sorted(SPORT_MARKETS):
            n = conn.execute(
                "SELECT COUNT(*) FROM player_game_logs WHERE sport=?",
                (sport,)).fetchone()[0]
            if n >= MIN_LOG_ROWS:
                out[sport] = n
        return out
    finally:
        conn.close()


def refit_sport(sport: str, db: str = "data/history.db", say=None) -> list[str]:
    """Run all three fitters for one sport. Returns log lines.

    Invokes the real CLIs rather than reimplementing them, so there is
    exactly one definition of each fit and this cannot drift from the
    thing it runs — the same reasoning launch.py's refit command gives.

    ``say``, when given, hears each fitter start and finish as it happens
    (`python3 -m engine.deepfit nba` passes print). The lines alone come
    back only at the end — the runbook's step AI printed nothing for 25
    minutes on 2026-10-17 and was stopped, when the temperature fit on its
    own had taken 17 the run before.
    """
    return _refit_sport(sport, db, say)[0]


def _refit_sport(sport: str, db: str = "data/history.db", say=None,
                 deadline: float | None = None, skip=(), on_done=None,
                 clean_before: bool = True, last: str | None = None,
                 round_of: str | None = None) -> tuple[list[str], bool]:
    """`refit_sport`, and whether all three fitters ran to an answer.

    ``deadline`` (a time.monotonic() reading) bounds every fitter by what
    is left of the weekly job's budget as well as by TIMEOUT_S, so a piece
    stops itself before the chores' reaper stops the whole job. A fitter
    cut off by either bound leaves the sport unfinished: the round keeps
    it, and the next run tries it again.

    RESUMED INSIDE THE SPORT (2026-11-05). The live heartbeat that morning:
    the round ran 68 minutes and finished nothing, the NFL first in line,
    its fits still dated late August. A sport's three fitters were one
    piece, so a run that finished the recency dial and was cut off in the
    player memory threw the dial's work away and began again at the dial:
    a sport whose three fitters outgrow one run could never finish.
    ``skip`` names the fitters already done this round, which are not run
    again; ``on_done(label, seconds, status)`` hears each fitter as it ends
    ("ok", "failed" or "cut_off"), so the round writes it down at once (the
    reaper may stop the job before this returns). ``clean_before`` is
    False when a fitter failed in an earlier run of the round, so the
    NBA's switch still waits for a clean refit. ``last`` is a fitter cut
    off earlier in the round: it goes last, so one fitter that outgrows a
    run cannot keep the other two from theirs (the board keeps reading its
    previous fit meanwhile).

    ``round_of`` is the round's first day. The recency dial is handed it
    (``--resume-after``): the dial writes each market as it is fitted and
    keeps the ones fitted since then, so a run cut off inside the dial
    loses only the market it was walking."""
    import time as _time
    lines = []
    finished = True
    clean = clean_before
    tell = on_done or (lambda *_a: None)
    note = say or (lambda _l: None)
    # THE NBA FITS ON WHAT ITS OWN CHECK DECIDED (engine/nba/switches): the
    # spread its verdict asks for, so the calibration is fitted on the board
    # as it will price — and the switch is thrown only after this refit has
    # run clean, the runbook's order. A setting on the box decides outright:
    # then there is no target, and the fitters read the box's setting.
    env = None
    if sport == "nba":
        from .nba import switches
        want = switches.target("spread")
        if want is not None:
            env = dict(os.environ, QB_NBA_SPREAD="1" if want else "0")
            lines.append(f"deep refit: nba fits with the spread that follows the projection "
                         f"{'ON' if want else 'OFF'}, as the box's own check asks")
    order = [f for f in REFIT_ORDER if f[0] != last] + [f for f in REFIT_ORDER if f[0] == last]
    for label, script in order:
        if label in skip:
            lines.append(f"deep refit: {sport} {label} — done earlier this round")
            continue
        cmd = [sys.executable, script, "--from-db", db, "--sport", sport]
        if round_of and script == "formfit.py":
            cmd += ["--resume-after", round_of]
        t0 = _time.monotonic()
        bound = TIMEOUT_S if deadline is None else min(TIMEOUT_S, deadline - t0)
        if bound < 1:
            lines.append(f"⚠️  {sport} {label}: no time left in this run — left for the next")
            note(lines[-1])
            finished = False
            break
        note(f"  {sport} {label}: running {script} (up to {bound / 60:.0f} min)…")
        kept_before = _dial_kept(sport, round_of) if label in RESUMES else None
        try:
            r = subprocess.run(cmd, cwd=ROOT, capture_output=True,
                               text=True, timeout=bound, env=env)
        except subprocess.TimeoutExpired as exc:
            ran = _time.monotonic() - t0
            whole = bound >= TOO_LONG_SHARE * TIMEOUT_S and ran >= TOO_LONG_SHARE * TIMEOUT_S
            kept_after = _dial_kept(sport, round_of) if label in RESUMES else None
            if label in RESUMES:
                # How far it got before the cut, in its own words (formfit.py
                # says each setting as it is kept, flushed): the log then
                # shows how long one setting takes on the box.
                said = [ln.strip() for ln in _timed_out_text(exc).splitlines() if " scored — " in ln]
                if said:
                    lines.append(f"deep refit: {sport} {label} — {len(said)} setting(s) scored before "
                                 f"the cut; the last: {said[-1]}")
                    note(lines[-1])
            if label in RESUMES and whole and kept_before is not None \
                    and (kept_after is None or kept_after <= kept_before):
                # Its whole time, and not one setting more kept (a market's
                # grid it had to start afresh counts as none): it did not
                # move. The round counts the stall (STALLS_TO_SET_ASIDE).
                lines.append(f"⚠️  {sport} {label}: ran the whole {bound / 60:.0f} min a fitter may "
                             f"have and kept no market it had not kept before — stalled")
                note(lines[-1])
                finished = False
                tell(label, ran, "stalled")
                continue
            if (label not in RESUMES and bound >= TOO_LONG_SHARE * TIMEOUT_S
                    and ran >= TOO_LONG_SHARE * TIMEOUT_S):
                # The whole of a fitter's time, and still not done: no run
                # can finish it. Set aside for the round so the sport's
                # other fitters, and what waits on the sport, go ahead; the
                # store keeps its last fit, and the NBA's switch is not
                # thrown on a refit missing one.
                lines.append(f"⚠️  {sport} {label}: ran the whole {bound / 60:.0f} min a fitter "
                             f"may have and did not finish — too long for a run; set aside for this "
                             f"round, its last fit stands")
                note(lines[-1])
                clean = False
                tell(label, ran, "too_long")
                continue
            lines.append(f"⚠️  {sport} {label}: still running after "
                         f"{bound:.0f}s — skipped")
            note(lines[-1])
            finished = False
            tell(label, _time.monotonic() - t0, "cut_off")
            continue
        note(f"  {sport} {label}: done in {_time.monotonic() - t0:.0f}s")
        if r.returncode != 0:
            tail = ((r.stderr or r.stdout or "").strip().splitlines()
                    or ["no output"])[-1]
            lines.append(f"⚠️  {sport} {label} failed: {tail}")
            clean = False
            tell(label, _time.monotonic() - t0, "failed")
            continue
        tell(label, _time.monotonic() - t0, "ok")
        # A fit the sport's board has nothing for (formfit.NO_DIAL: the
        # basketball projection has no recency dial) says so, not "nothing
        # adopted" as if the record had been asked and said no.
        declined = [ln.split(": not fitted — ", 1)[1].strip() for ln in (r.stdout or "").splitlines()
                    if ": not fitted — " in ln]
        if declined:
            lines.append(f"deep refit: {sport} {label} — not fitted: {declined[0]}")
            continue
        # ADOPTIONS ONLY. These CLIs print a paragraph per market; a
        # nightly log that reprints all of it teaches you to skip the
        # nightly log. What matters is which markets MOVED.
        moved = [ln.strip() for ln in (r.stdout or "").splitlines()
                 if "the record moved" in ln or "adopted" in ln.lower()]
        # The dial's markets fitted in an earlier run of the round, kept.
        kept = [ln for ln in (r.stdout or "").splitlines() if " kept — fitted " in ln]
        fitted_now = [ln for ln in (r.stdout or "").splitlines() if " settled " in ln and "Brier" in ln]
        if kept:
            lines.append(f"deep refit: {sport} {label} — {len(kept)} market(s) fitted earlier "
                         f"this round, kept")
        if moved:
            lines.append(f"deep refit: {sport} {label} — {len(moved)} "
                         f"market(s) moved")
            for m in moved[:4]:
                lines.append(f"    {m}")
        elif fitted_now or not kept:
            lines.append(f"deep refit: {sport} {label} — nothing adopted "
                         f"(the record did not beat the default)")
    if env is not None and finished and clean:
        thrown = switches.apply_target("spread")
        if thrown:
            lines.append(thrown)
    return lines, finished


def refit_nfl_props(db: str = "data/history.db") -> list[str]:
    """The yardage and reception markets, against REAL book lines.

    `calibrate.py` fits these through `engine.logwalk`, which prices
    every game against a trailing-average proxy. The correction it learns
    is about that proxy and is applied live against a book — and on
    2026-08-28 two of the four markets had been fitted into corrections
    that could never output more than 0.470, so rushing and receiving
    yards could only ever be bet UNDER, for any player, in any game.

    `engine.propcal` refits them on the book-priced subset of the
    walk-forward, and refuses a market that has too little of it rather
    than accepting one fitted against the wrong opponent.
    """
    try:
        from . import db as _db
        from . import propcal
        path = db if os.path.isabs(db) else os.path.join(ROOT, db)
        if not os.path.isfile(path):
            return []
        conn = _db.connect(path)
        try:
            out = propcal.fit(conn, log=lambda *a: None)
        finally:
            conn.close()
    except Exception as exc:                              # noqa: BLE001
        return [f"⚠️  nfl prop calibration skipped: {exc}"]
    return propcal.report_lines(out)


def refit_td_scale(db: str = "data/history.db") -> list[str]:
    """engine/tdscale: how hard a scorer's chance follows his team's
    expected points, per position, adopted only on held-out seasons —
    the NFL on its replay, college on its own."""
    try:
        import sqlite3
        from .tdscale import refit
        path = db if os.path.isabs(db) else os.path.join(ROOT, db)
        if not os.path.isfile(path):
            return []
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        out = []
        try:
            for sport in ("nfl", "cfb"):
                try:
                    out += [f"deep refit:{line}" for line in refit(conn, sport=sport)]
                except Exception as exc:                  # noqa: BLE001
                    out.append(f"⚠️  {sport} touchdown team-total fit skipped: {exc}")
            return out
        finally:
            conn.close()
    except Exception as exc:                              # noqa: BLE001
        return [f"⚠️  touchdown team-total fit skipped: {exc}"]


def refit_touchdowns(db: str = "data/history.db") -> list[str]:
    """The touchdown market, which no other fitter can reach.

    `calibrate.SPORT_MARKETS["nfl"]` lists the yardage and reception
    props; `anytime_td` is absent because `fit_market` walks over/under
    props and a touchdown has no LINE to compare a projection against.
    So the market that drives every longshot on the board carried a
    neutral correction from the day it shipped, while
    `longshots.calibrated_prob` faithfully applied it to every pick.

    `engine.tdbacktest` replays the model forward and produces the
    (claimed, scored) pairs `calibrate.fit` wants, which is the front
    door after all.
    """
    try:
        import sqlite3
        from .tdbacktest import fit_calibration, MIN_FIT_PAIRS
        path = db if os.path.isabs(db) else os.path.join(ROOT, db)
        if not os.path.isfile(path):
            return []
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            fit, report = fit_calibration(conn)
        finally:
            conn.close()
    except Exception as exc:                              # noqa: BLE001
        return [f"⚠️  touchdown calibration skipped: {exc}"]
    if fit is None:
        return [f"deep refit: touchdowns — {report.n:,} graded player-weeks, "
                f"needs {MIN_FIT_PAIRS:,}"]
    return [f"deep refit: touchdowns refit on {report.n:,} player-weeks — "
            f"T={fit.temperature} bias={fit.intercept:+.2f}, Brier "
            f"{fit.brier_before:.4f} → {fit.brier_after:.4f}"]


def refit_cfb_touchdowns(db: str = "data/history.db") -> list[str]:
    """The college touchdown market, for the same reason the NFL's is here.

    `calibrate.SPORT_MARKETS` leaves CFB out entirely and `fit_market`
    could not fit a touchdown anyway — there is no line to compare a
    projection against. So `correction_for("cfb", "anytime_td")` returned
    the neutral (1.0, 0.0) from the day the college longshot board
    shipped, while `longshots.calibrated_prob` faithfully applied it.

    `engine.cfbtdfit` replays the model's role chain over every ingested
    college season and produces the (claimed, scored) pairs
    `calibrate.fit` wants. It is a prior, not the final word — the
    journal fitter replaces this key once 200 college touchdown picks
    have settled — and it is a prior the measurement says the board
    needs: conservative by five points in the band the longshots live
    in.
    """
    try:
        import sqlite3
        from .cfbtdfit import fit_calibration, MIN_FIT_PAIRS
        path = db if os.path.isabs(db) else os.path.join(ROOT, db)
        if not os.path.isfile(path):
            return []
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            fit, report = fit_calibration(conn)
        finally:
            conn.close()
    except Exception as exc:                              # noqa: BLE001
        return [f"⚠️  cfb touchdown calibration skipped: {exc}"]
    if fit is None:
        return [f"deep refit: cfb touchdowns — {report.n:,} graded "
                f"player-games, needs {MIN_FIT_PAIRS:,}"]
    return [f"deep refit: cfb touchdowns refit on {report.n:,} "
            f"player-games — T={fit.temperature} bias={fit.intercept:+.2f}, "
            f"Brier {fit.brier_before:.4f} → {fit.brier_after:.4f}"]


def refit_yardage_mixture(db: str = "data/history.db") -> list[str]:
    """Refit the zero-inflated mixture the LIKELIHOOD board displays.

    Not the betting path — that still asks `statmath.prob_over`, because
    against real closes the mixture makes no money the normal was not
    already making. This is the number the Most Likely page quotes, and
    there it is measurably closer to what lands: it halves the miss in
    both markets big enough to score.

    It matters most where the calibration store cannot help at all.
    `calibrate.correction_for` discards a boundary fit rather than
    applying it, so rush_yds and rec_yds — whose fitted temperatures both
    ran to the grid cap — were displayed with NO correction whatsoever.
    """
    try:
        import sqlite3
        from .yardagefit import save_fits
        path = db if os.path.isabs(db) else os.path.join(ROOT, db)
        if not os.path.isfile(path):
            return []
        conn = sqlite3.connect(path)
        try:
            wrote = save_fits(conn)
        finally:
            conn.close()
    except Exception as exc:                              # noqa: BLE001
        return [f"⚠️  yardage mixture skipped: {exc}"]
    if not wrote:
        return ["deep refit: yardage mixture — not enough logged rows yet"]
    bits = ", ".join(f"{m} sigma {g['sigma']:.2f}"
                     for m, g in sorted(wrote.items()))
    return [f"deep refit: yardage mixture for the likelihood board — {bits}"]


def refit_all(db: str = "data/history.db") -> list[str]:
    """Every sport with the history for it. Returns log lines."""
    sports = sports_with_history(db)
    if not sports:
        return ["deep refit: no sport has enough ingested logs yet"]
    lines = []
    for sport in sports:
        lines.extend(refit_sport(sport, db))
    # Outside the per-sport loop: both touchdown fits are driven by their
    # own replays rather than by the three CLIs above, because a
    # touchdown has no line for `calibrate.fit_market` to walk.
    lines.extend(refit_yardage_mixture(db))
    # The team-total exponent FIRST (engine/tdscale), so the temperature
    # below is always fitted on top of it.
    lines.extend(refit_td_scale(db))
    lines.extend(refit_touchdowns(db))
    lines.extend(refit_cfb_touchdowns(db))
    # AFTER the three CLIs above, deliberately. `calibrate.py` fits these
    # same markets against a trailing-average proxy; this refits them
    # against real book lines and must therefore be the last word, not
    # the first. It refuses a market with too little book-priced history
    # rather than leaving the proxy fit in place unremarked.
    lines.extend(refit_nfl_props(db))
    # The conviction ladder, re-measured against the ingested seasons.
    # Weekly and not nightly on purpose: it replays every prop week by
    # week and a season is minutes, not seconds.
    try:
        from .ladder import refresh as _ladder_refresh
        lines.extend(_ladder_refresh())
    except Exception as exc:                              # noqa: BLE001
        lines.append(f"⚠️  grade ladder skipped: {exc}")
    return lines


# --- THE WEEKLY JOB FINISHES IN PIECES (2026-11-03) ------------------------
#
# `refit_all` walked every sport and then the extras in one child, and the
# chores' reaper kills a weekly child past the hour
# (maintenance.WEEKLY_JOB_TIMEOUT_S, since 2026-09-02). College goes first
# and finished; MLB's fits ran into the hour and the child died there, every
# Wednesday, so the NFL (fourth), the WNBA, the touchdown fits, the NFL
# props' refit against book lines and the conviction ladder stopped running.
# On 3 November the Record page's own dates said so: the NFL's recency dial
# last fitted 25 August and its player memory 29 August, MLB's dial
# 1 September, college's memory 28 October. A cut-off child also printed
# nothing, because `refit_all` returns its lines at the end. And the journal
# fitter fits a market's FIRST temperature only, leaving refits to this job
# (journalfit's docstring), so the NFL's temperatures had stopped moving too.
#
# So the weekly job is a ROUND of pieces (each sport's three fitters, and
# each extra), begun every Wednesday and continued day by day until every
# piece in it has run, each run stopping itself inside a budget under the
# reaper's hour. A piece is marked attempted before it starts and done when
# it finishes; the order is stalest first, so a piece that was cut off goes
# to the back of the line instead of starving the rest. A sport whose
# history has not grown since its last full fit is left out of the round:
# refitting it would measure the same rows again (MLB and the WNBA out of
# season). Every piece says when it starts and ends, flushed, so the
# reaper's last line names where the time went.

#: The round's state, beside the chores' own (maintenance.STATE_PATH).
STATE_PATH = os.path.join(ROOT, "data", "cache", "deepfit_state.json")

#: How long one run may work: under maintenance.WEEKLY_JOB_TIMEOUT_S (an
#: hour), with room for the last piece to write its stores.
DEEP_BUDGET_S = 50 * 60

#: A piece is not started with less than this left, or less than a fifth
#: over its own last running time, unless it is the first piece of a run.
MIN_PIECE_LEFT_S = 5 * 60

#: THE NBA'S OWN CHECKS (2026-11-04; Ethan: "I don't want to have to
#: specifically ask you for certain tools ... I want you to just do it").
#: Three changes the NBA lab measured waited on a command typed on the box
#: (runbook JY and JZ). Each is a piece of the round now, run before the
#: NBA's fitters so its calibration is fitted on the board as it will price:
#: the rotation's three rules (on or off by the box's own seasons), the
#: minutes a fresh absence opens (its held-out verdict saved, which the board
#: reads only when it holds), and the spread that follows the projection
#: (its verdict filed; the NBA's refit then fits on it and only then throws
#: the switch — engine/nba/switches). A fourth joined the same day: the
#: rates read past his last twenty games, on or off by the box's own
#: seasons (`nbarates.py`). Each script and its arguments.
NBA_CHECKS = {"nba_rules": ("nbarules.py", ("--save",)),
              "nba_vacancy": ("nbavacancy.py", ("nba", "--heldout", "--save")),
              # The rates read past his last twenty games (engine/nba/rates,
              # 2026-11-04): on or off by the box's own seasons, as the rules.
              "nba_rates": ("nbarates.py", ("--save",)),
              "nba_spread": ("nbalabcheck.py", ("--part", "spread", "--save-verdict"))}
#: The time a check is given before its own first run has said how long it
#: takes: the spread's replay reads every stored NBA game four times over and
#: prices a ladder twice (the lab's two seasons took seven minutes on a fast
#: machine; the box is one niced vCPU beside the boards).
NBA_CHECK_GUESS_S = {"nba_rules": 10 * 60, "nba_vacancy": 35 * 60, "nba_rates": 10 * 60,
                     "nba_spread": 45 * 60}
# The box's own times, 5 November: the rotation's rules 30 minutes (1,823 s)
# and the rates 11; the teammate-out minutes replay the same games as the
# rules and were started on the old ten-minute guess with half an hour left,
# so they were cut off and owed again every run. Their guess is the rules'
# time now, and the spread's (the heaviest: four replays) a whole run.

#: TOO LONG FOR A RUN (2026-11-06). A piece or a fitter that was given this
#: share of the most a run can give and still did not finish cannot finish
#: in any run: it is set aside for the round, its last result stands, and
#: what waited on it goes ahead. Until then one stuck NBA check kept the
#: NBA's own fitters waiting all week (their alternate-line correction was
#: still dated 17 October on 6 November).
TOO_LONG_SHARE = 0.9

#: Fitters that keep what they fitted when they are cut off (the recency
#: dial writes each market as it goes, ``--resume-after``): one cut off by
#: its whole time has still moved, so it is tried again. The others start
#: over each time and are the ones a run can be too short for.
RESUMES = ("recency dial",)

#: A RESUMING FITTER THAT KEEPS NOTHING HAS STALLED (2026-11-06). The dial is
#: tried again after a cut on the belief that a cut-off run "has still
#: moved": it writes each market as it finishes. That is checked now. A run
#: that gave the dial its whole time and left no more of the sport's markets
#: kept this round than it found (`_dial_kept`) is a stall; the round's
#: second stall sets the dial aside like a fitter no run can finish (its last
#: fit stands), so one market that outgrows a run cannot keep the sport's
#: other two fitters, and with them the round, waiting for ever. One stall
#: alone is a busy night and is tried again.
STALLS_TO_SET_ASIDE = 2

#: AN UNFINISHED ROUND CARRIES OVER (2026-11-06). Each Wednesday began a new
#: round whatever the last one still owed, and with it went the dial's kept
#: markets (`formfit.py --resume-after` the round's first day) and each
#: sport's fitters done. The round of 4 November still owed nine pieces after
#: three runs; with one run a night, stalest first, the NFL's turn came about
#: once a week, so a sport whose three fitters need two of its turns could
#: never finish. Now a round runs to its end before the next begins (the run
#: after it ends). Past this many days a new round begins anyway, so nothing
#: owed for ever can hold every other fit back.
ROUND_CARRY_MAX_DAYS = 21


def _carries(start: str, today: _dt.date) -> bool:
    """Does the round begun ``start`` carry on past its own week (it owes
    pieces)? Not once it is older than ROUND_CARRY_MAX_DAYS, nor when its
    date will not read."""
    try:
        return (today - _dt.date.fromisoformat(str(start)[:10])).days <= ROUND_CARRY_MAX_DAYS
    except ValueError:
        return False


def _timed_out_text(exc) -> str:
    """What a fitter the refit cut off had printed, as text (``run`` hands it
    back as bytes whatever ``text`` was asked)."""
    out = getattr(exc, "stdout", None) or getattr(exc, "output", None) or ""
    return out.decode("utf-8", "replace") if isinstance(out, (bytes, bytearray)) else str(out)


def _dial_kept(sport: str, round_of: str | None, path=None) -> int | None:
    """How far ``sport``'s recency dial has got this round, in settings
    scored: each market the store holds fitted on or after ``round_of``
    (what `formfit.py --resume-after` keeps) counts its whole grid, and a
    market part-way the settings it has kept (`formfit.GridCheckpoint`,
    2026-11-06: one NFL market alone outgrew a run, so a run that scored
    settings without finishing a market has still moved). None when there
    is no round or the store cannot be read."""
    if not round_of:
        return None
    try:
        from . import formfit as ff
        stored = ff._load(ff.DEFAULT_PATH if path is None else path)
        part = ff.partial_counts(sport)
    except Exception:                                     # noqa: BLE001
        return None
    done = {str(k).partition(":")[2] for k, v in (stored or {}).items()
            if str(k).partition(":")[0] == sport and isinstance(v, dict)
            and str(v.get("fitted") or "") >= round_of}
    return len(ff.GRID) * len(done) + sum(n for m, n in part.items() if m not in done)

#: Every piece, in the order a round takes them when they are equally
#: stale: the sports first (football leads in the autumn; the NBA's checks
#: right before its fitters), then the extras in the order refit_all always
#: ran them.
PIECE_ORDER = ("nfl", "cfb", *NBA_CHECKS, "nba", "mlb", "wnba",
               "yardage_mixture", "td_scale", "touchdowns", "cfb_touchdowns",
               "nfl_props", "ladder")

#: A piece waits while a piece it builds on is still owed this round: the
#: touchdown temperatures sit on the team-total exponent, the NFL props'
#: book-line fit must be the last word over the NFL's own temperatures, and
#: the NBA's fitters fit on what the NBA's checks decided.
PREREQS = {"touchdowns": ("td_scale",), "cfb_touchdowns": ("td_scale",),
           "nfl_props": ("nfl",), "nba": tuple(NBA_CHECKS)}


def _ladder(db: str = "data/history.db") -> list[str]:
    """The conviction ladder, as refit_all runs it."""
    try:
        from .ladder import refresh as _ladder_refresh
        return list(_ladder_refresh())
    except Exception as exc:                              # noqa: BLE001
        return [f"⚠️  grade ladder skipped: {exc}"]


#: The pieces that are not a sport, each taking the history path.
EXTRAS = {"yardage_mixture": refit_yardage_mixture, "td_scale": refit_td_scale,
          "touchdowns": refit_touchdowns, "cfb_touchdowns": refit_cfb_touchdowns,
          "nfl_props": refit_nfl_props, "ladder": _ladder}


def _read_state(path) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            st = json.load(fh)
    except (OSError, ValueError):
        return {}
    return st if isinstance(st, dict) else {}


def _write_state(path, st: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(st, fh, indent=1, sort_keys=True)
    os.replace(tmp, path)


def round_start(today: _dt.date) -> _dt.date:
    """The Wednesday a round belongs to: today's, or the last one."""
    return today - _dt.timedelta(days=(today.weekday() - 2) % 7)


def due(path, today: _dt.date) -> bool:
    """Should the chores start the job on a day that is not Wednesday?
    When this week's round still has pieces left, or this week's round never
    began (a Wednesday the box was down). With no state at all it waits for
    a Wednesday, as the first round always has."""
    st = _read_state(path)
    if not st:
        return False
    if st.get("left"):
        return True
    return str(st.get("round") or "") < round_start(today).isoformat()


def round_pieces(state: dict, rows: dict) -> list[str]:
    """What a new round owes: every sport with history whose rows have grown
    since its last full fit, and every extra (they read the same history).

    The sports are whatever `_row_counts` found — formfit's own table, the
    one list (tests/test_cfb_calibration.py) — in PIECE_ORDER where it names
    them and after them where it does not, so a sport added to the fitters'
    table joins the round without a second list to remember."""
    done = state.get("pieces") or {}
    rank = {p: i for i, p in enumerate(PIECE_ORDER)}
    out = []
    for sp in sorted(rows, key=lambda s: (rank.get(s, len(PIECE_ORDER)), s)):
        last = done.get(sp) or {}
        if last.get("done") and last.get("rows") == rows[sp]:
            continue
        out.append(sp)
    if "nba" in out:
        # The NBA's checks come with its fitters, right before them.
        i = out.index("nba")
        out[i:i] = list(NBA_CHECKS)
    if rows:
        out.extend(EXTRAS)
    return out


def _late_checks(st: dict, start: str) -> bool:
    """A round already under way when the NBA's checks joined (4 November
    2026) still owes them before its NBA fitters, so the switches do not
    wait a week. True when the round's list changed."""
    left = st.get("left") or []
    if "nba" not in left:
        return False
    pieces = st.get("pieces") or {}
    # A check set aside this round as too long for a run is not owed again.
    missing = [c for c in NBA_CHECKS
               if c not in left and str((pieces.get(c) or {}).get("done") or "") < start
               and ((pieces.get(c) or {}).get("too_long") or {}).get("round") != start]
    if not missing:
        return False
    i = left.index("nba")
    st["left"] = left[:i] + missing + left[i:]
    return True


def _stalest_first(left: list[str], state: dict) -> list[str]:
    pieces = state.get("pieces") or {}

    def key(p):
        e = pieces.get(p) or {}
        return (max(str(e.get("done") or ""), str(e.get("attempted") or "")),
                PIECE_ORDER.index(p) if p in PIECE_ORDER else len(PIECE_ORDER))
    return sorted(left, key=key)


def _run_check(piece: str, deadline: float | None = None, say=None) -> tuple[list[str], bool]:
    """One of the NBA's checks, as a child like the fitters: (its lines,
    whether it ran to an answer). Bounded by what is left of the run; a
    check that has not answered in time stays owed. Only its verdict lines
    come back — the tables are for a person running it by hand."""
    import time as _time
    script, args = NBA_CHECKS[piece]
    note = say or (lambda _l: None)
    t0 = _time.monotonic()
    bound = TIMEOUT_S if deadline is None else min(TIMEOUT_S, deadline - t0)
    if bound < 1:
        return [f"⚠️  {piece}: no time left in this run — left for the next"], False
    note(f"  {piece}: running {script} (up to {bound / 60:.0f} min)…")
    try:
        r = subprocess.run([sys.executable, script, *args], cwd=ROOT, capture_output=True,
                           text=True, timeout=bound)
    except subprocess.TimeoutExpired:
        return [f"⚠️  {piece}: still running after {bound:.0f}s — left for the next run"], False
    note(f"  {piece}: done in {_time.monotonic() - t0:.0f}s")
    out = (r.stdout or "").splitlines()
    if r.returncode != 0:
        tail = ((r.stderr or r.stdout or "").strip().splitlines() or ["no output"])[-1]
        return [f"⚠️  {piece} failed: {tail}"], True
    keep = [ln.strip() for ln in out
            if any(w in ln for w in ("HOLDS", "DOES NOT HOLD", "verdict filed", "verdict not filed",
                                     "saved:", "spread: ready", "spread: not yet", "No NBA logs",
                                     "No nba logs"))]
    return [f"{piece}: {ln}" for ln in keep] or [f"{piece}: ran (no verdict line printed)"], True


def _run_piece(piece: str, db: str, deadline: float, say=None, skip=(), on_done=None,
               clean_before: bool = True, last: str | None = None,
               round_of: str | None = None) -> tuple[list[str], bool]:
    """One piece: (its log lines, whether it ran to an answer). ``skip``,
    ``on_done``, ``clean_before``, ``last`` and ``round_of`` reach a sport's
    fitters (`_refit_sport`)."""
    if piece in NBA_CHECKS:
        return _run_check(piece, deadline, say)
    if piece in EXTRAS:
        try:
            return list(EXTRAS[piece](db) or []), True
        except Exception as exc:                          # noqa: BLE001
            return [f"⚠️  {piece} failed: {type(exc).__name__}: {exc}"], True
    return _refit_sport(piece, db, say=say, deadline=deadline, skip=skip, on_done=on_done,
                        clean_before=clean_before, last=last, round_of=round_of)


def _part_way(pieces: dict, left: list, start: str, today: str) -> list[str]:
    """``["nfl (recency dial done; player memory cut off after 45 min)"]``:
    each owed sport that is part-way through this round, and where this
    run's time ran out in it."""
    out = []
    for p in left:
        e = pieces.get(p) or {}
        fd = e.get("fitters_done") or {}
        mine = fd.get("round") == start
        aside = list(fd.get("too_long") or []) if mine else []
        done = [f for f in (fd.get("done") or []) if f not in aside] if mine else []
        cut = e.get("cut_off") or {}
        bits = [f"{', '.join(done)} done"] if done else []
        if aside:
            bits.append(f"{', '.join(aside)} set aside")
        if cut.get("on") == today and cut.get("fitter"):
            stall = e.get("stalled") or {}
            stalled = (stall.get("round") == start and stall.get("on") == today
                       and stall.get("fitter") == cut["fitter"])
            bits.append(f"{cut['fitter']} cut off after {max(1, round(cut.get('after_s', 0) / 60))} min"
                        + (f", nothing new kept (stall {stall.get('n')} of {STALLS_TO_SET_ASIDE})"
                           if stalled else ""))
        if bits:
            out.append(f"{p} ({'; '.join(bits)})")
    return out


def run_round(db: str = "data/history.db", state_path=None, today: _dt.date | None = None,
              budget_s: float = DEEP_BUDGET_S, clock=None, run_piece=None, say=None) -> list[str]:
    """The weekly job: begin this week's round if it has not begun, then run
    its pieces, stalest first, until the round is done or the budget is
    spent. Returns every line it said."""
    import time as _time
    clock = clock or _time.monotonic
    today = today or _dt.date.today()
    path = state_path or STATE_PATH
    custom = run_piece
    out: list[str] = []

    def emit(line: str) -> None:
        out.append(line)
        if say:
            say(line)

    rows = _row_counts(db)
    if not rows:
        emit("deep refit: no sport has enough ingested logs yet")
        return out
    st = _read_state(path)
    pieces = st.setdefault("pieces", {})
    week = round_start(today).isoformat()
    start = str(st.get("round") or "")
    if start and start != week and st.get("left") and _carries(start, today):
        # Last week's round still owes pieces: it runs to its end first,
        # keeping what each sport has done in it (ROUND_CARRY_MAX_DAYS).
        emit(f"deep refit: the round of {start} carries on — {len(st['left'])} piece(s) still owed "
             f"({', '.join(st['left'])}); this week's begins when it is done")
        if _late_checks(st, start):
            _write_state(path, st)
    elif start != week:
        start = week
        st["round"] = start
        st["left"] = round_pieces(st, rows)
        _write_state(path, st)
        emit(f"deep refit: the round of {start} owes {len(st['left'])} piece(s): "
             f"{', '.join(st['left']) or 'none'}")
    elif _late_checks(st, start):
        _write_state(path, st)
        emit(f"deep refit: the NBA's own checks join this round before its fitters: "
             f"{', '.join(st['left'])}")
    left = list(st.get("left") or [])
    deadline = clock() + budget_s
    done_now: list[str] = []
    set_aside: list[str] = []
    started = 0

    def run_piece(p, db_, deadline_, say_):
        """The piece, resumed where this round left it (`_refit_sport`):
        each fitter written down the moment it ends."""
        if custom is not None:
            return custom(p, db_, deadline_, say_)
        e = pieces.setdefault(p, {})
        fd = e.get("fitters_done") or {}
        mine = fd.get("round") == start
        skip = set(fd.get("done") or []) if mine else set()

        def on_done(label, secs, status):
            cur = e.get("fitters_done") or {}
            if cur.get("round") != start:
                cur = {"round": start, "done": []}
            e.setdefault("fitter_seconds", {})[label] = round(secs)
            s = e.get("stalled") or {}
            if status == "stalled":
                # A dial run that kept nothing new in its whole time: counted
                # for the round, in a row; the STALLS_TO_SET_ASIDE-th sets it
                # aside (its last fit stands), the ones before are a cut.
                n = (int(s.get("n") or 0) if s.get("round") == start and s.get("fitter") == label else 0) + 1
                e["stalled"] = {"round": start, "n": n, "fitter": label, "on": today.isoformat()}
                status = "too_long" if n >= STALLS_TO_SET_ASIDE else "cut_off"
            elif s.get("fitter") == label:
                e.pop("stalled", None)        # it moved, or finished: the count starts again
            if status == "cut_off":
                # The longest cut today names the fitter that outgrew the
                # run; one cut a few minutes later, only because the run's
                # time was nearly gone, must not take its place.
                was = e.get("cut_off") or {}
                if not (was.get("round") == start and was.get("on") == today.isoformat()
                        and float(was.get("after_s") or 0) >= secs):
                    e["cut_off"] = {"fitter": label, "after_s": round(secs), "on": today.isoformat(),
                                    "round": start}
            else:
                if label not in cur["done"]:
                    cur["done"].append(label)
                if status == "failed" and label not in cur.setdefault("failed", []):
                    cur["failed"].append(label)
                if status == "too_long" and label not in cur.setdefault("too_long", []):
                    # Skipped by the rest of the round like a done fitter,
                    # and named, so the round's line and the desk say so.
                    cur["too_long"].append(label)
                    cur.setdefault("failed", []).append(label)
            e["fitters_done"] = cur
            _write_state(path, st)
        cut = e.get("cut_off") or {}
        return _run_piece(p, db_, deadline_, say_, skip=skip, on_done=on_done,
                          clean_before=not (mine and fd.get("failed")),
                          last=cut.get("fitter") if cut.get("round") == start else None,
                          round_of=start)
    while left:
        # Chosen afresh after every piece: one that waited on another
        # (PREREQS) may run as soon as that one is done.
        runnable = [p for p in _stalest_first(left, st)
                    if not any(q in left for q in PREREQS.get(p, ()))]
        if not runnable:
            break
        p = runnable[0]
        e0 = pieces.get(p) or {}
        # ITS OWN TIME (2026-11-06): its last full run, its guess before it
        # has one, and never less than it has already been seen to run
        # without finishing (``min_s``).
        took = max(float(e0.get("seconds") or 0) or float(NBA_CHECK_GUESS_S.get(p, 0)),
                   float(e0.get("min_s") or 0))
        need = min(budget_s * 0.9, max(MIN_PIECE_LEFT_S, 1.2 * took))
        if started and deadline - clock() < need:
            break
        started += 1
        entry = pieces.setdefault(p, {})
        entry["attempted"] = today.isoformat()
        _write_state(path, st)
        emit(f"deep refit: {p} — starting ({len(left)} left in this round)")
        t0 = clock()
        lines, finished = run_piece(p, db, deadline, say)
        for ln in lines:
            emit(f"  {ln}")
        if not finished:
            ran = clock() - t0
            if p not in rows:
                # A check or an extra is all or nothing: what it ran is the
                # least it needs, so it is not started again with less.
                entry["min_s"] = max(int(entry.get("min_s") or 0), int(round(ran)))
                if ran >= TOO_LONG_SHARE * min(TIMEOUT_S, budget_s):
                    entry["too_long"] = {"round": start, "after_s": int(round(ran)),
                                         "on": today.isoformat()}
                    left.remove(p)
                    st["left"] = left
                    _write_state(path, st)
                    set_aside.append(p)
                    emit(f"deep refit: {p} ran {ran / 60:.0f} min, the most a run can give, and did "
                         f"not finish — too long for a run; set aside for this round (its last result "
                         f"stands) and what waited on it goes ahead")
                    continue
            emit(f"deep refit: {p} did not finish in this run — it goes to the back of the line")
            break
        entry.update({"done": today.isoformat(), "seconds": round(clock() - t0),
                      "rows": rows.get(p)})
        entry.pop("fitters_done", None)
        entry.pop("cut_off", None)
        entry.pop("min_s", None)
        entry.pop("too_long", None)
        entry.pop("stalled", None)
        left.remove(p)
        st["left"] = left
        _write_state(path, st)
        done_now.append(p)
    st["left"] = left
    _write_state(path, st)
    aside = f"; set aside as too long for a run: {', '.join(set_aside)}" if set_aside else ""
    if left:
        part = _part_way(pieces, left, start, today.isoformat())
        emit(f"deep refit: round of {start}: {', '.join(done_now) or 'nothing'} done this run; "
             f"left for the next: {', '.join(left)}"
             + (f"; part-way: {', '.join(part)}" if part else "") + aside)
    else:
        emit(f"deep refit: round of {start} complete"
             + (f" — {', '.join(done_now)} this run" if done_now else "") + aside)
    return out


if __name__ == "__main__":                       # pragma: no cover
    # `python3 -m engine.deepfit nba` refits one sport and says each step as
    # it goes; `--all` runs every sport and extra in one go (by hand only:
    # it outlasts the chores' hour); with nothing, this week's round, as the
    # chores start it.
    if len(sys.argv) > 1 and sys.argv[1] == "--all":
        for _line in refit_all():
            print(_line, flush=True)
    elif len(sys.argv) > 1:
        for _line in refit_sport(sys.argv[1].lower(), say=lambda l: print(l, flush=True)):
            print(_line, flush=True)
    else:
        run_round(say=lambda l: print(l, flush=True))
