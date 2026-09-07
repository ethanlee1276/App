"""Does anything we can compute carry information the COLLEGE close does not?

Ethan, 2026-09-07: "make sure you do the same exact work to make CFB
just as good."

WHAT WAS ALREADY KNOWN. The shipped college rating — opponent-adjusted
scoring margin with a fitted home field, walked forward the way the
board builds it — ranks winners at 0.752 (`gamerank.measure_cfb`), and
where it disagrees with the close the disagreement carries nothing:
`engine.gamecal --sport cfb` measures the moneyline at −0.079 ± 0.067,
the spread at −0.037 ± 0.040 and the total at +0.115 ± 0.060 with the
model's side beating the close 52.4% of the time — the break-even at
−110. The rating is priced already.

WHAT THIS ASKS. `engine.nflinfo`'s question, pointed at college: walk
every game with the closing number as a FIXED offset and ask whether a
candidate input, computed from strictly earlier games, still predicts
the outcome once the close has had its say. Fitted on 2022-2023,
judged on 2024-2025, never the same seasons.

THE CANDIDATES, and where each comes from — what the database holds
for college, which is less than it holds for the NFL: no play-by-play
efficiency, no weather, no conference map on disk.

  * The rating's own disagreement with the close (`pts_gap`), the
    production walk (`teamrates.adjusted_ratings_for_season` rebuilt
    before every date, FCS buy games excluded as the build excludes
    them) — the control, so the new inputs are read against it.
  * The starting quarterback (`player_game_logs`: the passer with the
    most yards that game): whether he is the team's usual starter, how
    many starts he has, and his yards per game against the usual
    starter's. College's is the sharper version of the NFL's question —
    a transfer or an injury turns over a college depth chart every
    other week and the books price it from beat reporters.
  * Rest: days since the team's last game, and a bye (twelve days or
    more) — a college schedule has open dates the NFL's does not.
  * A neutral site, from the schedule.
  * Form drift: the last three margins against the season's.

Each is tested on the moneyline (logistic, market log-odds as offset)
and on the spread and the total (least squares of actual − close), then
all together, fitted on the train seasons and settled as a bet rule on
the test seasons at the close.

    python3 -m engine.cfbinfo

MEASURED 2026-09-07, 1,526 train games and 1,606 test games, on a box
where every team key is the `espn:` fallback (so no FCS exclusion, as
`gamerank.measure_cfb` rules) and the 2025 logs cover 35 dates.
Nothing holds at the bar. One input comes closer than anything the NFL
test found, and it is written down here so it is measured again and
not rediscovered.

  Moneyline, each feature alone on top of the close (log-odds):
    pts_gap          train −0.108 ± 0.112   test −0.038 ± 0.093
    qb_change_diff   train −0.392 ± 0.114** test −0.172 ± 0.114
    qb_new_diff      train −0.476 ± 0.122** test −0.167 ± 0.117
    qb_ypg_diff      train −0.004 ± 0.003   test −0.003 ± 0.003
    bye_diff         train +0.201 ± 0.144   test −0.118 ± 0.119   (sign flips)
    rest_diff        train +0.028 ± 0.019   test −0.019 ± 0.015   (sign flips)
    neutral          train +0.219 ± 0.249   test +0.023 ± 0.184
    drift_diff       train +0.001 ± 0.007   test +0.005 ± 0.007
  All together, fitted on train and applied to test (534 games):
    log-loss WORSE by 0.0141; AUC 0.7895 market alone, 0.7760 with
    features; the EV > 2% rule 370 bets, 198 won, ROI +1.7%.
  Spread (points of actual − close per unit):
    qb_change_diff   train −2.35 ± 0.73**   test −0.19 ± 0.73
    qb_new_diff      train −2.37 ± 0.77**   test −0.44 ± 0.75
    everything else within one standard error of zero on test; the
    1-point rule 294 settled, 53.7%, ROI +2.6% — half a standard error
    over the 52.4% it needs.
  Total: pts_tot_edge train −0.054 ± 0.093, test +0.165 ± 0.098 (sign
    flips); the 1-point rule 238 settled, 52.1%, ROI −0.5%.

THE QUARTERBACK. A team starting someone other than its usual passer
does WORSE than the close says: 3.4σ on the fit seasons, and on the
held-out seasons the same sign at half the size, 1.5σ — the only
feature in either league's table to keep its sign and half its size
out of sample (the NFL's held-out reading was −0.25 ± 0.16, the same
sign again). Not a finding: the rule is that the held-out seasons hold
on their own, and 1.5σ is what noise looks like a third of the time.
Not nothing either. It is the one input on this list worth a
pre-registered re-read, and the number that decides is written on
`QB_CHANGE_WATCH` below: when the 2026 season has been ingested, this
command's test-seasons coefficient for `qb_change_diff`, and nothing
pooled, nothing re-fitted. Beyond two standard errors and it becomes a
term in the college moneyline's pricing — fitted, not typed. Short of
it and this paragraph stays as the record of a near miss.

Nothing here is shipped.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sqlite3

from .cfb import ratings as cfbratings
from .gamebacktest import close_for, schedule_closes, schedule_moneylines
from .gamebets import project_total
from .nflinfo import Row, _prior_table, report_for
from .odds import devig_two_way
from . import teamrates

TRAIN = (2022, 2023)
TEST = (2024, 2025)

#: Games on both sides before the production walk prices a matchup —
#: `gamerank.measure_cfb`'s floor, four because a college season is
#: twelve games.
MIN_TEAM_GAMES = 4
#: Prior games this season before a "usual starter" exists.
QB_MIN_GAMES = 3
#: Games a passer needs before his yards per game is a number, not a coin.
QB_YPG_MIN_GAMES = 3
#: Games before form drift means anything, and the window it reads.
DRIFT_MIN_GAMES = 5
DRIFT_WINDOW = 3
#: Days off that count as a bye.
BYE_DAYS = 12
#: Rest is capped so one August opener does not become a fifty-day feature.
REST_CAP = 21

COLS = "sport, season, period, home, away, home_score, away_score, extra"

#: The pre-registered re-read of the quarterback finding — see the
#: module note. Read by nothing; a number written down before the data
#: it will be judged on exists, so the judgment cannot move.
QB_CHANGE_WATCH = {
    "feature": "qb_change_diff",
    "market": "moneyline",
    "measured": {"train": (-0.392, 0.114), "test": (-0.172, 0.114)},
    "re_read_after": "the 2026 season is ingested",
    "test_seasons": (2024, 2025, 2026),
    "decides": "test coefficient beyond two standard errors, alone, unpooled",
    "if_it_holds": "a fitted qb-change term in the college moneyline pricing",
}

ML_FEATURES = ("pts_gap", "qb_change_diff", "qb_new_diff", "qb_ypg_diff",
               "bye_diff", "rest_diff", "neutral", "drift_diff")
SPREAD_FEATURES = ("pts_edge", "qb_change_diff", "qb_new_diff", "qb_ypg_diff",
                   "bye_diff", "rest_diff", "neutral", "drift_diff")
TOTAL_FEATURES = ("pts_tot_edge", "qb_change_sum", "neutral", "drift_sum")


def _qb_games(conn) -> dict:
    """{(season, date, team): (passer, yards)} — the starter is whoever
    threw for the most yards that game. College logs carry no attempts."""
    best: dict = {}
    for r in conn.execute(
            "SELECT season, period, team, player, value FROM player_game_logs "
            "WHERE sport='cfb' AND market='pass_yds'"):
        key = (r["season"], r["period"], r["team"])
        yds = float(r["value"] or 0)
        cur = best.get(key)
        if cur is None or yds > cur[1]:
            best[key] = (r["player"], yds)
    return best


def _day(s: str) -> datetime.date:
    return datetime.date.fromisoformat(str(s)[:10])


def _exclusion(rows) -> str | None:
    """`gamerank.measure_cfb`'s rule: the FCS exclusion only where the
    team map loaded — on a box where every key is the `espn:` fallback,
    excluding it would drop the league."""
    espn = sum(1 for r in rows if str(r["home"]).startswith("espn:")
               or str(r["away"]).startswith("espn:"))
    return "espn:" if rows and espn / len(rows) < 0.5 else None


def build_rows(conn) -> list[Row]:
    """Every scored college game with a close, features from earlier games only."""
    games = conn.execute(
        f"SELECT {COLS} FROM games WHERE sport='cfb' "
        "AND home_score IS NOT NULL AND away_score IS NOT NULL "
        "ORDER BY season, period").fetchall()
    exclude = _exclusion(games)
    plain = teamrates.compute_team_ratings(conn, "cfb", shrink=8.0)
    fit = cfbratings.fit_from_history(conn, plain)
    mls = {k: {k[2]: h, k[3]: a} for k, (h, a) in schedule_moneylines(conn, "cfb").items()}
    sps = schedule_closes(conn, "cfb", "spread", require_prices=False)
    tts = schedule_closes(conn, "cfb", "total", require_prices=False)
    qb = _qb_games(conn)
    mem = sqlite3.connect(":memory:")
    mem.row_factory = sqlite3.Row
    mem.execute(f"CREATE TABLE games ({COLS})")
    by_date: dict = {}
    for g in games:
        by_date.setdefault((g["season"], g["period"]), []).append(g)
    last_played: dict = {}   # team -> (season, date)
    margins: dict = {}       # team -> list of (season, margin)
    qb_hist: dict = {}       # team -> list of (season, date, passer, yards)
    out: list[Row] = []
    for key in sorted(by_date):
        season, date = key
        _prior_table(mem, games, key, (season - 1, season))
        ratings, _ = teamrates.adjusted_ratings_for_season(
            mem, "cfb", season, shrink=8.0, exclude_prefix=exclude,
            home_field=fit.home_field)
        for g in by_date[key]:
            h, a = g["home"], g["away"]
            hs, as_ = float(g["home_score"]), float(g["away_score"])
            try:
                neutral = bool((json.loads(g["extra"] or "{}") or {}).get("neutral"))
            except (TypeError, ValueError):
                neutral = False
            q = close_for({}, mls, season, date, h, a) or {}
            sq = close_for({}, sps, season, date, h, a)
            tq = close_for({}, tts, season, date, h, a)
            fair = None
            if q.get(h) is not None and q.get(a) is not None:
                fair, _ = devig_two_way(int(q[h]), int(q[a]))
            row = Row(season, date, h, a, hs, as_, fair, q.get(h), q.get(a),
                      sq[0] if sq else None, tq[0] if tq else None)
            f = row.f
            hr, ar = ratings.get(h), ratings.get(a)
            if (hr and ar and hr.games >= MIN_TEAM_GAMES and ar.games >= MIN_TEAM_GAMES):
                f["pts_margin"] = (hr.net - ar.net) + (0.0 if neutral else fit.home_field)
                f["pts_wp"] = cfbratings.win_prob(f["pts_margin"], fit)
                f["pts_total"] = project_total("cfb", hr.off, hr.def_, ar.off, ar.def_)
            f["neutral"] = 1.0 if neutral else 0.0
            for side, team in (("h", h), ("a", a)):
                # Quarterback.
                this = qb.get((season, date, team))
                hist = qb_hist.get(team, [])
                mine = [w for w in hist if w[0] == season]
                usual = None
                pool = mine if len(mine) >= QB_MIN_GAMES else [w for w in hist if w[0] == season - 1]
                if pool:
                    counts: dict = {}
                    for w in pool:
                        counts[w[2]] = counts.get(w[2], 0) + 1
                    usual = max(counts, key=counts.get)
                if this and usual is not None:
                    f[f"qb_change_{side}"] = 0.0 if this[0] == usual else 1.0
                    f[f"qb_starts_{side}"] = float(sum(1 for w in hist if w[2] == this[0]))

                    def ypg(name):
                        ws = [w for w in hist if w[2] == name and w[0] in (season - 1, season)]
                        return (sum(w[3] for w in ws) / len(ws)) if len(ws) >= QB_YPG_MIN_GAMES else None
                    mine_ypg, usual_ypg = ypg(this[0]), ypg(usual)
                    f[f"qb_ypg_{side}"] = ((mine_ypg - usual_ypg)
                                           if (mine_ypg is not None and usual_ypg is not None
                                               and this[0] != usual) else 0.0)
                # Rest and the bye: only once the team has played this season.
                prev = last_played.get(team)
                if prev and prev[0] == season:
                    rest = min((_day(date) - _day(prev[1])).days, REST_CAP)
                    f[f"rest_{side}"] = float(rest)
                    f[f"bye_{side}"] = 1.0 if rest >= BYE_DAYS else 0.0
                # Drift: the last three margins against the season's.
                ms = [m for s_, m in margins.get(team, []) if s_ == season]
                if len(ms) >= DRIFT_MIN_GAMES:
                    f[f"drift_{side}"] = (sum(ms[-DRIFT_WINDOW:]) / DRIFT_WINDOW
                                          - sum(ms) / len(ms))
            for name, kind in (("qb_change", "diff"), ("qb_ypg", "diff"), ("bye", "diff"),
                               ("rest", "diff"), ("drift", "diff"),
                               ("qb_change", "sum"), ("drift", "sum")):
                if f"{name}_h" in f and f"{name}_a" in f:
                    f[f"{name}_{kind}"] = (f[f"{name}_h"] - f[f"{name}_a"] if kind == "diff"
                                           else f[f"{name}_h"] + f[f"{name}_a"])
            if "qb_starts_h" in f and "qb_starts_a" in f:
                f["qb_new_diff"] = float(f["qb_starts_h"] < 3) - float(f["qb_starts_a"] < 3)
            out.append(row)
        # Then the date becomes history.
        for g in by_date[key]:
            hs, as_ = float(g["home_score"]), float(g["away_score"])
            for team, margin in ((g["home"], hs - as_), (g["away"], as_ - hs)):
                last_played[team] = (season, date)
                margins.setdefault(team, []).append((season, margin))
                w = qb.get((season, date, team))
                if w:
                    qb_hist.setdefault(team, []).append((season, date, w[0], w[1]))
    mem.close()
    return out


def report(rows: list[Row], train=TRAIN, test=TEST) -> list[str]:
    return report_for(rows, "CFB", ML_FEATURES, SPREAD_FEATURES, TOTAL_FEATURES,
                      train=train, test=test)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None)
    args = ap.parse_args()
    from . import db
    conn = db.connect(args.db) if args.db else db.connect()
    conn.row_factory = sqlite3.Row
    for line in report(build_rows(conn)):
        print(line)


if __name__ == "__main__":
    main()
