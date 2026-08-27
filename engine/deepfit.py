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
TIMEOUT_S = 900


def sports_with_history(db: str = "data/history.db") -> list[str]:
    """Which supported sports actually have enough logs to fit."""
    import sqlite3
    try:
        from formfit import SPORT_MARKETS          # noqa: PLC0415
    except Exception:                              # noqa: BLE001
        sys.path.insert(0, ROOT)
        from formfit import SPORT_MARKETS          # noqa: PLC0415
    path = db if os.path.isabs(db) else os.path.join(ROOT, db)
    if not os.path.isfile(path):
        return []
    conn = sqlite3.connect(path)
    try:
        out = []
        for sport in sorted(SPORT_MARKETS):
            n = conn.execute(
                "SELECT COUNT(*) FROM player_game_logs WHERE sport=?",
                (sport,)).fetchone()[0]
            if n >= MIN_LOG_ROWS:
                out.append(sport)
        return out
    finally:
        conn.close()


def refit_sport(sport: str, db: str = "data/history.db") -> list[str]:
    """Run all three fitters for one sport. Returns log lines.

    Invokes the real CLIs rather than reimplementing them, so there is
    exactly one definition of each fit and this cannot drift from the
    thing it runs — the same reasoning launch.py's refit command gives.
    """
    lines = []
    for label, script in REFIT_ORDER:
        cmd = [sys.executable, script, "--from-db", db, "--sport", sport]
        try:
            r = subprocess.run(cmd, cwd=ROOT, capture_output=True,
                               text=True, timeout=TIMEOUT_S)
        except subprocess.TimeoutExpired:
            lines.append(f"⚠️  {sport} {label}: still running after "
                         f"{TIMEOUT_S}s — skipped")
            continue
        if r.returncode != 0:
            tail = ((r.stderr or r.stdout or "").strip().splitlines()
                    or ["no output"])[-1]
            lines.append(f"⚠️  {sport} {label} failed: {tail}")
            continue
        # ADOPTIONS ONLY. These CLIs print a paragraph per market; a
        # nightly log that reprints all of it teaches you to skip the
        # nightly log. What matters is which markets MOVED.
        moved = [ln.strip() for ln in (r.stdout or "").splitlines()
                 if "the record moved" in ln or "adopted" in ln.lower()]
        if moved:
            lines.append(f"deep refit: {sport} {label} — {len(moved)} "
                         f"market(s) moved")
            for m in moved[:4]:
                lines.append(f"    {m}")
        else:
            lines.append(f"deep refit: {sport} {label} — nothing adopted "
                         f"(the record did not beat the default)")
    return lines


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
    lines.extend(refit_touchdowns(db))
    lines.extend(refit_cfb_touchdowns(db))
    return lines


if __name__ == "__main__":                       # pragma: no cover
    for _line in refit_all():
        print(_line)
