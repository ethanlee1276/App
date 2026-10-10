"""Does anything we can compute carry information the NFL close does not?

Ethan, 2026-09-07: "start working on what u think we should put effort
into. I just want a wining nfl model for our best bets AND edge models."

WHAT WAS ALREADY KNOWN. The shipped rating — a team's shrunk scoring
margin through a normal curve — ranks NFL winners at 0.683 against the
closing moneyline's 0.724, and where it disagrees with the close the
disagreement carries nothing (slope −0.06 ± 0.14). Opponent adjustment
and a fitted home field move it by two thousandths
(docs/NFL_MONEYLINE_ARITHMETIC.md). More arithmetic on points scored and
allowed is a closed road.

WHAT THIS ASKS. The method of docs/THE_INFORMATION_TEST.md, pointed at
new INPUTS instead of new curves: walk every game with the closing
number as a FIXED offset and ask whether a candidate feature, computed
from strictly earlier weeks, still predicts the outcome once the close
has had its say. A feature that does is information the market did not
price; one that does not is priced already, or noise. Fitted on
2021-2023, judged on 2024-2025 — never the same seasons — because a
coefficient scored on the games it was fitted to is scored on its own
memory (`engine.nflfit` set that rule for props).

THE CANDIDATES, and where each comes from:

  * EPA per play, offence minus defence (`team_weeks`, from nflverse
    play-by-play) — the standard upgrade over points, less noisy per
    game; the market uses it too.
  * The starting quarterback (`player_game_logs`: the passer with the
    most attempts that week): whether he is the team's usual starter,
    how many starts he has, and his yards-per-attempt against the usual
    starter's. The one known single factor that moves a line by several
    points and is invisible to any function of past scores.
  * Wind, temperature and a roof, on the TOTAL.
  * A bye the week before.
  * A division game.
  * Form drift: the last three weeks' EPA against the season's.

Each is tested on the moneyline (logistic, market log-odds as offset),
and the point-market ones on the spread and the total (least squares of
actual − close on the feature). Then all of them together, fitted on the
train seasons, are turned into a BET RULE and settled at the close on
the test seasons — because a significant coefficient that cannot pay
the vig is a finding, not a model.

    python3 -m engine.nflinfo            # the whole table
    python3 -m engine.nflinfo --wind     # the wind bands, by season

MEASURED 2026-09-07, 854 train games and 570 test games. Nothing holds.

  Moneyline, each feature alone on top of the close (log-odds):
    pts_gap          train −0.26 ± 0.18   test +0.10 ± 0.18
    epa_diff         train −0.97 ± 0.72   test +1.37 ± 0.84   (sign flips)
    qb_change_diff   train −0.16 ± 0.14   test −0.25 ± 0.16
    qb_new_diff      train −0.25 ± 0.16   test −0.14 ± 0.20
    qb_ypa_diff      train +0.08 ± 0.16   test −0.10 ± 0.14
    bye_diff         train +0.32 ± 0.25   test −0.20 ± 0.28
    div_game         train −0.00 ± 0.13   test +0.05 ± 0.16
    drift_diff       train +0.69 ± 0.49   test +0.77 ± 0.57
  All together, fitted on train and applied to test: log-loss WORSE
  than the market alone by 0.011, AUC 0.772 → 0.755, and the bet rule
  (EV > 2% at the close) went 108 for 253, ROI −13.2%.

  Spread: epa_diff +10.2 ± 4.2 on test but −3.2 on train — a flip.
  qb_change −1.9 ± 0.9 on test, −0.2 on train; a side starting a
  non-usual passer with under three starts is −0.8 ± 0.7 against the
  close over 382 games and covers 50.0%. The joint rule: 49.5%, −5.4%.

  Total: the one consistent sign was WIND — −0.25 ± 0.09 a mph on train
  (2.9σ), −0.09 ± 0.11 on test. So the spec's own bands were tested:
  12–18 mph, 166 games, unders 59.5% and +13.6% pooled — and by season
  27/43, 21/28, 21/29, then 16/35 and 12/28. Sixty-eight per cent of
  unders in 2021–23 and forty-seven in 2024–25. The market priced wind
  in, or the first three seasons were the fluke; on the held-out
  seasons the rule loses either way, and it is not shipped.

  WHY THE BACKTEST WOULD FLATTER IT ANYWAY: `games.wind` is the wind
  RECORDED at the game, from the box score. The close only knew the
  forecast, and so would we (`engine.nflwx`). A total-vs-recorded-wind
  edge is partly forecast error that nobody could bet.

What this leaves is the finding the moneyline table already gave and
this extends to every input on disk: for NFL game markets, the closing
line contains what we can compute and more. The remaining honest
sources of edge are prices — a sharp book's number against a soft one's
(`gamebets.price_moneyline_sharp` and kin), and the opening line
against the close — and neither is a better equation.

Standard library only. Nothing here is read by a build; a survivor gets
wired in by its own commit, behind `engine.gamecal`'s guards.
"""

from __future__ import annotations

import argparse
import math
import sqlite3
from dataclasses import dataclass, field

from .divisions import group_of
from .gamebacktest import close_for, schedule_closes, schedule_moneylines
from .gamebets import NFL_HOME_FIELD, NFL_MARGIN_SD, nfl_win_prob
from .gamecal import _logit
from .nflfit import _solve
from .odds import american_to_decimal, devig_two_way
from .rankfit import auc
from .statmath import clamp, normal_cdf
from . import teamrates

TRAIN = (2021, 2022, 2023)
TEST = (2024, 2025)

#: Prior starts before a passer's own yards-per-attempt is a number
#: rather than a coin; below it the gap feature is zero, not a guess.
QB_MIN_ATT = 60
#: Prior weeks this season before a "usual starter" exists.
QB_MIN_WEEKS = 3
#: Weeks of EPA before form drift means anything.
DRIFT_MIN_WEEKS = 5
DRIFT_WINDOW = 3
#: The edge a rule needs before it bets, in expected value at the close.
BET_EV = 0.02
#: …and in points, on the spread and the total.
BET_POINTS = 1.0

COLS = "sport, season, period, home, away, home_score, away_score, extra"


@dataclass
class Row:
    season: int
    period: str
    home: str
    away: str
    hs: float
    as_: float
    fair_home: float | None
    home_ml: int | None
    away_ml: int | None
    spread: float | None            # the home number, as the book writes it
    total: float | None
    f: dict = field(default_factory=dict)   # feature name -> value


# ------------------------------------------------------------ the walk ----
def _prior_table(mem, rows, before: tuple, seasons) -> None:
    """Only the past, by season then week — see `gamerank._prior_table`."""
    mem.execute("DELETE FROM games")
    mem.executemany(
        "INSERT INTO games VALUES (?,?,?,?,?,?,?,?)",
        [tuple(r)[:8] for r in rows
         if (r["season"], r["period"]) < before and r["season"] in seasons])
    mem.commit()


def _qb_weeks(conn) -> dict:
    """{(season, period, team): (passer, attempts, yards)} — the starter
    is whoever threw the most that week."""
    att: dict = {}
    yds: dict = {}
    for r in conn.execute(
            "SELECT season, period, team, player, market, value FROM player_game_logs "
            "WHERE sport='nfl' AND market IN ('pass_att', 'pass_yds')"):
        key = (r["season"], r["period"], r["team"], r["player"])
        (att if r["market"] == "pass_att" else yds)[key] = float(r["value"] or 0)
    best: dict = {}
    for (season, period, team, player), a in att.items():
        cur = best.get((season, period, team))
        if cur is None or a > cur[1]:
            best[(season, period, team)] = (player, a, yds.get((season, period, team, player), 0.0))
    return best


def _epa_weeks(conn) -> dict:
    """{(season, period, team): row} from team_weeks."""
    return {(r["season"], r["period"], r["team"]): r for r in conn.execute(
        "SELECT season, period, team, plays, proe, off_epa, def_epa, pace "
        "FROM team_weeks WHERE sport='nfl'")}


def _epa_rating(hist: list, season: int) -> tuple[float, float, float, float] | None:
    """(net EPA/play, plays/game, proe, pace) on the same pooling rule the
    shipped points rating uses: this season alone once it has four weeks,
    pooled with the prior season until then. Shrunk toward zero by
    n/(n+6) like the points rating, so the two are on one footing."""
    this = [w for w in hist if w["season"] == season]
    use = this if len(this) >= teamrates.MIN_GAMES_PER_TEAM else [
        w for w in hist if w["season"] in (season - 1, season)]
    # A week can carry no neutral pace (no snaps with the game in the
    # balance) and, rarely, no EPA; each number averages what is there
    # and a rating with no EPA weeks at all is no rating.
    ep = [w for w in use if w["off_epa"] is not None and w["def_epa"] is not None]
    if not ep:
        return None
    n = len(ep)
    k = n / (n + 6.0)
    net = sum(w["off_epa"] - w["def_epa"] for w in ep) / n * k
    plays = sum(w["plays"] or 0 for w in ep) / n
    pr = [w["proe"] for w in ep if w["proe"] is not None]
    proe = (sum(pr) / len(pr) * k) if pr else 0.0
    pc = [w["pace"] for w in use if w["pace"] is not None]
    pace = (sum(pc) / len(pc)) if pc else None
    return net, plays, proe, pace


def build_rows(conn) -> list[Row]:
    """Every scored NFL game with a close, features from earlier weeks only."""
    games = conn.execute(
        f"SELECT {COLS}, roof, temp, wind FROM games WHERE sport='nfl' "
        "AND home_score IS NOT NULL AND away_score IS NOT NULL "
        "ORDER BY season, period").fetchall()
    mls = {k: {k[2]: h, k[3]: a} for k, (h, a) in schedule_moneylines(conn, "nfl").items()}
    sps = schedule_closes(conn, "nfl", "spread", require_prices=False)
    tts = schedule_closes(conn, "nfl", "total", require_prices=False)
    qb = _qb_weeks(conn)
    epa = _epa_weeks(conn)
    mem = sqlite3.connect(":memory:")
    mem.row_factory = sqlite3.Row
    mem.execute(f"CREATE TABLE games ({COLS})")
    by_week: dict = {}
    for g in games:
        by_week.setdefault((g["season"], g["period"]), []).append(g)
    played: dict = {}        # team -> list of (season, period)
    qb_hist: dict = {}       # team -> list of (season, period, passer, att, yds)
    epa_hist: dict = {}      # team -> list of team_weeks rows, in order
    out: list[Row] = []
    for week in sorted(by_week):
        season, period = week
        _prior_table(mem, games, week, (season - 1, season))
        ratings, _ = teamrates.ratings_for_season(mem, "nfl", season)
        for g in by_week[week]:
            h, a = g["home"], g["away"]
            hs, as_ = float(g["home_score"]), float(g["away_score"])
            q = close_for({}, mls, season, period, h, a) or {}
            sq = close_for({}, sps, season, period, h, a)
            tq = close_for({}, tts, season, period, h, a)
            fair = None
            if q.get(h) is not None and q.get(a) is not None:
                fair, _ = devig_two_way(int(q[h]), int(q[a]))
            row = Row(season, period, h, a, hs, as_, fair,
                      q.get(h), q.get(a),
                      sq[0] if sq else None, tq[0] if tq else None)
            f = row.f
            hr, ar = ratings.get(h), ratings.get(a)
            eh = _epa_rating(epa_hist.get(h, []), season)
            ea = _epa_rating(epa_hist.get(a, []), season)
            ok = (hr and ar and hr.games >= teamrates.MIN_GAMES_PER_TEAM
                  and ar.games >= teamrates.MIN_GAMES_PER_TEAM and eh and ea)
            if ok:
                f["pts_margin"] = (hr.net - ar.net) + NFL_HOME_FIELD
                f["pts_wp"] = nfl_win_prob(hr.net, ar.net)
                f["pts_total"] = 2 * 22.6 + hr.off + hr.def_ + ar.off + ar.def_
                f["epa_diff"] = eh[0] - ea[0]
                f["epa_total"] = (eh[0] + ea[0])          # both offences net of defences
                if eh[3] is not None and ea[3] is not None:
                    f["pace_sum"] = eh[3] + ea[3]
                f["proe_sum"] = eh[2] + ea[2]
            # Quarterback.
            for side, team in (("h", h), ("a", a)):
                this = qb.get((season, period, team))
                hist = qb_hist.get(team, [])
                mine = [w for w in hist if w[0] == season]
                usual = None
                if len(mine) >= QB_MIN_WEEKS:
                    counts: dict = {}
                    for w in mine:
                        counts[w[2]] = counts.get(w[2], 0) + 1
                    usual = max(counts, key=counts.get)
                elif hist:
                    prev = [w for w in hist if w[0] == season - 1]
                    if prev:
                        counts = {}
                        for w in prev:
                            counts[w[2]] = counts.get(w[2], 0) + 1
                        usual = max(counts, key=counts.get)
                if this and usual is not None:
                    f[f"qb_change_{side}"] = 0.0 if this[0] == usual else 1.0
                    starts = [w for w in hist if w[2] == this[0]]
                    f[f"qb_starts_{side}"] = float(len(starts))
                    def ypa(name):
                        ws = [w for w in hist if w[2] == name and w[0] in (season - 1, season)]
                        att_ = sum(w[3] for w in ws); yd = sum(w[4] for w in ws)
                        return (yd / att_) if att_ >= QB_MIN_ATT else None
                    mine_ypa, usual_ypa = ypa(this[0]), ypa(usual)
                    f[f"qb_ypa_gap_{side}"] = ((mine_ypa - usual_ypa)
                                               if (mine_ypa is not None and usual_ypa is not None
                                                   and this[0] != usual) else 0.0)
                # Bye: did not play last week (week > 1).
                if int(period) > 1:
                    f[f"bye_{side}"] = 0.0 if (season, f"{int(period) - 1:03d}") in played.get(team, set()) else 1.0
                # Drift: last three weeks' net EPA against the season's.
                mine_epa = [w for w in epa_hist.get(team, []) if w["season"] == season]
                if len(mine_epa) >= DRIFT_MIN_WEEKS:
                    net = [w["off_epa"] - w["def_epa"] for w in mine_epa]
                    f[f"drift_{side}"] = (sum(net[-DRIFT_WINDOW:]) / DRIFT_WINDOW
                                          - sum(net) / len(net))
            if "qb_change_h" in f and "qb_change_a" in f:
                f["qb_change_diff"] = f["qb_change_h"] - f["qb_change_a"]
                f["qb_ypa_diff"] = f["qb_ypa_gap_h"] - f["qb_ypa_gap_a"]
                f["qb_new_diff"] = (float(f["qb_starts_h"] < 3) - float(f["qb_starts_a"] < 3))
            if "bye_h" in f and "bye_a" in f:
                f["bye_diff"] = f["bye_h"] - f["bye_a"]
            if "drift_h" in f and "drift_a" in f:
                f["drift_diff"] = f["drift_h"] - f["drift_a"]
            gh, ga = group_of("nfl", h), group_of("nfl", a)
            f["div_game"] = 1.0 if (gh[1] and gh == ga) else 0.0
            roof = (g["roof"] or "").lower()
            indoor = roof in ("dome", "closed")
            f["indoor"] = 1.0 if indoor else 0.0
            if indoor:
                f["wind"] = 0.0
                f["cold"] = 0.0
            elif g["wind"] is not None:
                f["wind"] = float(g["wind"])
                f["cold"] = 1.0 if (g["temp"] is not None and float(g["temp"]) < 32) else 0.0
            out.append(row)
        # Then the week becomes history.
        for g in by_week[week]:
            for team in (g["home"], g["away"]):
                played.setdefault(team, set()).add((season, period))
                w = qb.get((season, period, team))
                if w:
                    qb_hist.setdefault(team, []).append((season, period, w[0], w[1], w[2]))
                e = epa.get((season, period, team))
                if e:
                    epa_hist.setdefault(team, []).append(e)
    mem.close()
    return out


# ------------------------------------------------------------- the fits ---
def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(min(z, 40.0), -40.0)))


def fit_logistic(obs: list[tuple]) -> tuple[list[float], list[float]] | None:
    """``(coefs, ses)`` for P = sigmoid(offset + Σ b·x). ``obs`` is
    ``[(xs, offset, y)]``. Newton–Raphson; the market's own log-odds
    ride as the offset with a fixed coefficient of one, so every b is
    'how much of this, on top of the close'."""
    if not obs:
        return None
    k = len(obs[0][0])
    b = [0.0] * k
    for _ in range(50):
        g = [0.0] * k
        H = [[0.0] * k for _ in range(k)]
        for xs, off, y in obs:
            p = _sigmoid(off + sum(bi * xi for bi, xi in zip(b, xs)))
            w = p * (1 - p)
            for i in range(k):
                g[i] += xs[i] * (y - p)
                for j in range(k):
                    H[i][j] += xs[i] * xs[j] * w
        step = _solve(H, g)
        if step is None:
            return None
        b = [bi + si for bi, si in zip(b, step)]
        if max(abs(s) for s in step) < 1e-8:
            break
    ses = []
    for i in range(k):
        e = [0.0] * k; e[i] = 1.0
        col = _solve(H, e)
        ses.append(math.sqrt(col[i]) if col and col[i] > 0 else float("nan"))
    return b, ses


def fit_ols(obs: list[tuple]) -> tuple[list[float], list[float]] | None:
    """``(coefs, ses)`` for y = a + Σ b·x, with the intercept first."""
    if len(obs) < 3:
        return None
    k = len(obs[0][0]) + 1
    X = [[1.0] + list(xs) for xs, y in obs]
    Y = [y for _, y in obs]
    XtX = [[sum(r[i] * r[j] for r in X) for j in range(k)] for i in range(k)]
    XtY = [sum(r[i] * y for r, y in zip(X, Y)) for i in range(k)]
    b = _solve(XtX, XtY)
    if b is None:
        return None
    resid = sum((y - sum(bi * xi for bi, xi in zip(b, r))) ** 2 for r, y in zip(X, Y))
    s2 = resid / max(len(obs) - k, 1)
    ses = []
    for i in range(k):
        e = [0.0] * k; e[i] = 1.0
        col = _solve(XtX, e)
        ses.append(math.sqrt(s2 * col[i]) if col and col[i] > 0 else float("nan"))
    return b, ses


ML_FEATURES = ("pts_gap", "epa_diff", "qb_change_diff", "qb_new_diff",
               "qb_ypa_diff", "bye_diff", "div_game", "drift_diff")
SPREAD_FEATURES = ("pts_edge", "epa_diff", "qb_change_diff", "qb_new_diff",
                   "qb_ypa_diff", "bye_diff", "div_game", "drift_diff")
TOTAL_FEATURES = ("pts_tot_edge", "epa_total", "pace_sum", "proe_sum",
                  "wind", "cold", "indoor", "div_game")


def _ml_obs(rows, feats, seasons):
    obs = []
    for r in rows:
        if r.season not in seasons or r.fair_home is None or r.hs == r.as_:
            continue
        f = dict(r.f)
        if "pts_wp" in f:
            f["pts_gap"] = _logit(f["pts_wp"]) - _logit(r.fair_home)
        if any(k not in f for k in feats):
            continue
        obs.append(([f[k] for k in feats], _logit(r.fair_home), 1.0 if r.hs > r.as_ else 0.0, r))
    return obs


def _pts_obs(rows, feats, seasons, market):
    obs = []
    for r in rows:
        if r.season not in seasons:
            continue
        f = dict(r.f)
        if market == "spread":
            if r.spread is None or "pts_margin" not in f:
                continue
            f["pts_edge"] = f["pts_margin"] + r.spread      # model margin − market margin
            y = (r.hs - r.as_) + r.spread
        else:
            if r.total is None or "pts_total" not in f:
                continue
            f["pts_tot_edge"] = f["pts_total"] - r.total
            y = (r.hs + r.as_) - r.total
        if any(k not in f for k in feats):
            continue
        obs.append(([f[k] for k in feats], y, r))
    return obs


def _line(name, tr, te):
    def cell(fit):
        if not fit:
            return "        —        "
        (b, s) = fit
        stars = "**" if abs(b) > 2 * s else (" *" if abs(b) > 1.65 * s else "  ")
        return f"{b:+8.3f} ± {s:5.3f}{stars}"
    return f"  {name:<16} train {cell(tr)}   test {cell(te)}"


def report(rows: list[Row], train=TRAIN, test=TEST) -> list[str]:
    return report_for(rows, "NFL", ML_FEATURES, SPREAD_FEATURES, TOTAL_FEATURES,
                      train=train, test=test)


def report_for(rows: list[Row], label: str, ml_features, spread_features,
               total_features, train, test) -> list[str]:
    """The whole table for one league. `engine.cfbinfo` calls this with
    college's feature lists and seasons; the arithmetic — each feature
    alone on top of the close, all of them together as a bet rule on the
    held-out seasons — is the same question in both leagues, and one
    copy of it means one copy to be wrong."""
    out = []
    n_tr = sum(1 for r in rows if r.season in train)
    n_te = sum(1 for r in rows if r.season in test)
    out.append(f"{label} information test · train {train} ({n_tr} games) · test {test} ({n_te} games)")
    out.append("  ** = beyond two standard errors, * = beyond 1.65; a feature has to hold on TEST to count")

    # --- moneyline, each feature alone ---------------------------------
    out.append("\nMONEYLINE — each feature alone, on top of the close's log-odds")
    for name in ml_features:
        tr = _ml_obs(rows, (name,), train)
        te = _ml_obs(rows, (name,), test)
        ftr = fit_logistic([(xs, off, y) for xs, off, y, _ in tr])
        fte = fit_logistic([(xs, off, y) for xs, off, y, _ in te])
        out.append(_line(name, (ftr[0][0], ftr[1][0]) if ftr else None,
                         (fte[0][0], fte[1][0]) if fte else None)
                   + f"   n {len(tr)}/{len(te)}")
    # --- moneyline, all together, fitted on train, bet on test ----------
    feats = [k for k in ml_features if k != "pts_gap"] + ["pts_gap"]
    tr = _ml_obs(rows, feats, train)
    te = _ml_obs(rows, feats, test)
    joint = fit_logistic([(xs, off, y) for xs, off, y, _ in tr])
    if joint and te:
        b = joint[0]
        ll_m = ll_j = 0.0
        pairs_m, pairs_j = [], []
        bets = wins = 0; staked = net = 0.0
        for xs, off, y, r in te:
            pm = _sigmoid(off)
            pj = _sigmoid(off + sum(bi * xi for bi, xi in zip(b, xs)))
            ll_m -= y * math.log(pm) + (1 - y) * math.log(1 - pm)
            ll_j -= y * math.log(pj) + (1 - y) * math.log(1 - pj)
            pairs_m.append((pm, y == 1.0)); pairs_j.append((pj, y == 1.0))
            ev_h = pj * american_to_decimal(r.home_ml) - 1
            ev_a = (1 - pj) * american_to_decimal(r.away_ml) - 1
            side = None
            if ev_h > BET_EV and ev_h >= ev_a:
                side, dec, won = "h", american_to_decimal(r.home_ml), y == 1.0
            elif ev_a > BET_EV:
                side, dec, won = "a", american_to_decimal(r.away_ml), y == 0.0
            if side:
                bets += 1; staked += 1.0
                net += (dec - 1.0) if won else -1.0
                wins += won
        n = len(te)
        out.append(f"\nMONEYLINE — all features fitted on train, applied to test ({n} games)")
        out.append(f"  log-loss   market alone {ll_m / n:.4f}   with features {ll_j / n:.4f}   "
                   f"({'better' if ll_j < ll_m else 'WORSE'} by {abs(ll_j - ll_m) / n:.4f})")
        out.append(f"  AUC        market alone {auc(pairs_m):.4f}   with features {auc(pairs_j):.4f}")
        roi = net / staked if staked else 0.0
        out.append(f"  bet rule   EV > {BET_EV:.0%} at the close: {bets} bets, {wins} won, ROI {roi:+.1%}")
        out.append("  coefficients (train): " + ", ".join(f"{k} {bi:+.3f}" for k, bi in zip(feats, b)))

    # --- spread and total ------------------------------------------------
    for market, feats_all in (("spread", spread_features), ("total", total_features)):
        out.append(f"\n{market.upper()} — each feature alone, least squares of (actual − close)")
        for name in feats_all:
            tr = _pts_obs(rows, (name,), train, market)
            te = _pts_obs(rows, (name,), test, market)
            ftr = fit_ols([(xs, y) for xs, y, _ in tr])
            fte = fit_ols([(xs, y) for xs, y, _ in te])
            out.append(_line(name, (ftr[0][1], ftr[1][1]) if ftr else None,
                             (fte[0][1], fte[1][1]) if fte else None)
                       + f"   n {len(tr)}/{len(te)}")
        tr = _pts_obs(rows, feats_all, train, market)
        te = _pts_obs(rows, feats_all, test, market)
        joint = fit_ols([(xs, y) for xs, y, _ in tr])
        if joint and te:
            b = joint[0]
            bets = wins = pushes = 0; net = 0.0
            for xs, y, r in te:
                pred = b[0] + sum(bi * xi for bi, xi in zip(b[1:], xs))
                if abs(pred) < BET_POINTS:
                    continue
                bets += 1
                if y == 0:
                    pushes += 1; continue
                won = (y > 0) == (pred > 0)
                wins += won
                net += (100 / 110) if won else -1.0
            settled = bets - pushes
            out.append(f"  bet rule   |predicted edge| > {BET_POINTS:.0f} pt, at −110: {bets} bets, "
                       f"{wins} won of {settled} settled ({(wins / settled if settled else 0):.1%}), "
                       f"ROI {(net / settled if settled else 0):+.1%}  (needs 52.4%)")
            out.append("  coefficients (train): " + ", ".join(
                f"{k} {bi:+.3f}" for k, bi in zip(("intercept",) + tuple(feats_all), b)))
    return out


#: NFL_MODEL.md §7's own wind bands, so the test is the spec's and not a
#: cut chosen after looking.
WIND_BANDS = ((0, 8), (8, 12), (12, 18), (18, 25), (25, 99))


def wind_report(rows: list[Row]) -> list[str]:
    """The total against the close by wind band, outdoor games only —
    pooled, and BY SEASON, because that is where the answer was."""
    out = ["TOTAL vs close by wind band · outdoor games with a recorded wind",
           f"  {'band':>8} {'n':>5} {'actual−close':>16} {'under':>7} {'ROI −110':>9}   under-rate by season"]
    for lo, hi in WIND_BANDS:
        xs = [(r.hs + r.as_ - r.total, r.season) for r in rows
              if r.total is not None and r.f.get("indoor") == 0.0
              and "wind" in r.f and lo <= r.f["wind"] < hi]
        if not xs:
            continue
        n = len(xs)
        m = sum(x for x, _ in xs) / n
        sd = math.sqrt(sum((x - m) ** 2 for x, _ in xs) / max(n - 1, 1))
        unders = sum(1 for x, _ in xs if x < 0)
        settled = sum(1 for x, _ in xs if x != 0)
        roi = (unders * (100 / 110) - (settled - unders)) / settled if settled else 0.0
        by: dict = {}
        for x, sn in xs:
            by.setdefault(sn, [0, 0])
            by[sn][1] += (x != 0)
            by[sn][0] += (x < 0)
        per = " ".join(f"{sn}:{a}/{b}" for sn, (a, b) in sorted(by.items()))
        out.append(f"  {lo:>3}-{hi:<4} {n:>5} {m:>+8.2f} ± {sd / math.sqrt(n):4.2f} "
                   f"{(unders / settled if settled else 0):>6.1%} {roi:>+8.1%}   {per}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None)
    ap.add_argument("--wind", action="store_true", help="the wind-band table only")
    args = ap.parse_args()
    from . import db
    conn = db.connect(args.db) if args.db else db.connect()
    conn.row_factory = sqlite3.Row
    rows = build_rows(conn)
    for line in (wind_report(rows) if args.wind else report(rows)):
        print(line)


if __name__ == "__main__":
    main()
