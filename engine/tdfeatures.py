"""Does a candidate feature add anything to the touchdown model?

WHERE THIS SITS. `engine.scriptfit` closed the team-level question: the
implied total is the whole between-game signal, and the spread and the
opponent's defensive record add nothing on top of it in either sport. So
every remaining improvement to a touchdown pick has to come from WITHIN a
team — who on this roster gets them — because the team number is already
as good as the market's.

And the current within-team feature set is spent. The shipped chain
scores AUC 0.7210 over 22,099 graded NFL player-weeks; an unconstrained
logistic over everything the model already knows scores 0.7225. There is
nothing left to rearrange. The only thing that moves it now is a feature
that is not in there yet.

HOW A CANDIDATE IS JUDGED. On top of the model, never beside it. Each
candidate is added as a single term to a logistic whose only other input
is the shipped probability's own logit, and the pair is scored
LEAVE-ONE-SEASON-OUT. A feature that merely restates the model's opinion
scores well on its own and adds nothing here, which is the entire point:

    baseline      logit(shipped prob)
    candidate     logit(shipped prob) + b * x

Reported as change in AUC and in log-loss. AUC answers the question the
product actually asks — can it RANK who scores — and log-loss guards
against a term that reorders well while wrecking the probabilities the
prices are compared against.

EVERY FEATURE IS BUILT FROM WEEKS STRICTLY BEFORE THE GRADED ONE, on the
same walked-forward window `engine.tdbacktest` used for the probability
it is being added to. Two different histories compared against each other
will show a difference that is about the windows, not the feature.

BOTH SPORTS, EACH ON ITS OWN CHAIN. The probability a candidate is
judged against has to come from the model that actually ships for that
sport: `engine.tdbacktest` replays `engine.touchdowns` for the NFL,
`engine.cfbtdfit` replays `engine.cfb.tds` for college. Running one
against the other's logs grades a model nobody runs — done once, on
2026-08-30, producing a confident table showing the college calibration
failing badly when on the real college chain the same bands are sound.
`graded_rows` routes by sport and `tdbacktest.run` still refuses `cfb`
rather than answering the wrong question quietly.

College was blocked until 2026-08-30 on `cfbtdfit.Sample` carrying no
player identity — its slots stopped at the team, and every within-team
question is a question about a person. The name was in scope in
`samples` the whole time and simply never stored.

THE TWO FEEDS DO NOT CARRY THE SAME COLUMNS, and that is the trap this
extension had to avoid. The NFL logs a target and an inside-five carry;
college logs neither, and logs receptions instead. Reading the NFL names
against college rows does not raise — every lookup returns 0.0, the
candidate takes a share of nothing, and the harness reports a flat AUC
as though the feature had been measured. A negative result nobody can
tell apart from a wiring fault is worse than no result, so the column
names are declared per sport (`TOUCH_MARKETS`, `GOAL_LINE_MARKET`) and a
candidate whose input this feed does not publish is REFUSED and printed
as "not in this feed" rather than scored on zeros.

Standard library only.

    python3 -m engine.tdfeatures
"""

from __future__ import annotations

import math
import sys
from collections import defaultdict

from . import db as _db
from . import tdbacktest as B
from .fantasy import _short_key

#: A candidate needs this many graded player-weeks before its number
#: means anything. Below it the leave-one-season-out fit is describing a
#: handful of players.
MIN_ROWS = 2000

#: Seasons with fewer graded rows than this cannot be held out.
MIN_TEST = 400

#: Newton steps for the logistic. It has two or three parameters and
#: converges in a handful; the cap is here so a separable fixture cannot
#: spin forever.
MAX_STEPS = 40
TOL = 1e-9

#: Ridge on the coefficients. Small enough not to shrink a real effect,
#: large enough that a candidate which perfectly separates some season
#: returns a number instead of an overflow.
RIDGE = 1e-4

#: Recent form window for a trend feature — three weeks against the rest
#: of the walked-forward window, which is what "he is being used more
#: lately" means.
TREND_WEEKS = 3


def logit(p: float) -> float:
    p = min(max(float(p), 1e-6), 1.0 - 1e-6)
    return math.log(p / (1.0 - p))


def sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def fit_logistic(xs, ys):
    """Newton-Raphson with a ridge. Returns coefficients, or None."""
    if not xs:
        return None
    k = len(xs[0])
    beta = [0.0] * k
    for _ in range(MAX_STEPS):
        grad = [0.0] * k
        hess = [[RIDGE if i == j else 0.0 for j in range(k)] for i in range(k)]
        for i in range(k):
            grad[i] -= RIDGE * beta[i]
        for x, y in zip(xs, ys):
            p = sigmoid(sum(b * v for b, v in zip(beta, x)))
            w = max(p * (1.0 - p), 1e-9)
            r = y - p
            for i in range(k):
                grad[i] += x[i] * r
                for j in range(k):
                    hess[i][j] += w * x[i] * x[j]
        step = _solve(hess, grad)
        if step is None:
            return None
        beta = [b + s for b, s in zip(beta, step)]
        if max(abs(s) for s in step) < TOL:
            break
    return beta


def _solve(A, b):
    k = len(b)
    A = [row[:] for row in A]
    b = b[:]
    for i in range(k):
        p = max(range(i, k), key=lambda t: abs(A[t][i]))
        A[i], A[p] = A[p], A[i]
        b[i], b[p] = b[p], b[i]
        if abs(A[i][i]) < 1e-12:
            return None
        for t in range(i + 1, k):
            f = A[t][i] / A[i][i]
            for c in range(i, k):
                A[t][c] -= f * A[i][c]
            b[t] -= f * b[i]
    out = [0.0] * k
    for i in range(k - 1, -1, -1):
        out[i] = (b[i] - sum(A[i][j] * out[j] for j in range(i + 1, k))) / A[i][i]
    return out


def auc(pairs) -> float:
    """Rank AUC with ties shared, which matters: a feature that is zero
    for most of the board produces a lot of them."""
    ranked = sorted(pairs, key=lambda t: t[0])
    n = len(ranked)
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and ranked[j + 1][0] == ranked[i][0]:
            j += 1
        r = (i + j) / 2.0 + 1.0
        for t in range(i, j + 1):
            ranks[t] = r
        i = j + 1
    pos = sum(1 for _s, y in ranked if y)
    neg = n - pos
    if not pos or not neg:
        return 0.5
    s = sum(r for r, (_sc, y) in zip(ranks, ranked) if y)
    return (s - pos * (pos + 1) / 2.0) / (pos * neg)


def log_loss(pairs) -> float:
    if not pairs:
        return float("nan")
    total = 0.0
    for p, y in pairs:
        p = min(max(p, 1e-9), 1.0 - 1e-9)
        total -= math.log(p) if y else math.log(1.0 - p)
    return total / len(pairs)


# --- the candidate features -----------------------------------------------
#: WHAT COUNTS AS A TOUCH, PER SPORT. The NFL logs carry `targets`;
#: the college feed does not and carries `receptions` instead. Reading
#: the NFL name against college rows returns zeros from every lookup —
#: which is not an error, it is a feature that silently measures nothing
#: and reports a flat AUC as if it had been tested.
TOUCH_MARKETS = {"nfl": ("targets", "carries"),
                 "cfb": ("receptions", "carries")}

#: The inside-five column, which only the NFL feed has. A candidate that
#: needs it is REFUSED for college rather than run against zeros.
GOAL_LINE_MARKET = {"nfl": "i5_car", "cfb": None}

#: The red-zone columns each feed actually publishes.
RZ_MARKETS = {"nfl": ("rz_car", "rz_tgt"), "cfb": ("rz_car", "rz_rec")}


def touch_markets(sport: str) -> tuple:
    return TOUCH_MARKETS.get((sport or "").lower(), TOUCH_MARKETS["nfl"])


def _by_player(conn, sport: str, markets):
    """``{(season, short_key): {week: {market: value}}}``.

    KEYED THE WAY THE LIVE PATH KEYS — `_short_key`, first initial plus
    last name plus team. Play-by-play rows spell a man "E.Higgins" and
    stat rows spell him "Elijah Higgins"; keyed raw they are two people,
    and a feature built that way is measured against somebody else's
    touchdowns. This has already cost this codebase one whole round of
    conclusions, when every play-by-play signal came back under 0.5 AUC.
    """
    out: dict = {}
    q = ("SELECT season, period, player, team, position, market, value "
         "FROM player_game_logs WHERE sport=? AND market IN (%s)"
         % ",".join("?" * len(markets)))
    for (season, period, player, team, pos, market, value) in conn.execute(
            q, (sport, *markets)):
        key = (season, _short_key(player, team))
        wk = out.setdefault(key, {}).setdefault(period, {})
        wk[market] = float(value or 0.0)
        if pos:
            wk["_pos"] = pos
    return out


def _team_week(conn, sport: str, markets):
    """``{(season, week, team): {market: total}}`` — the denominators."""
    out: dict = defaultdict(lambda: defaultdict(float))
    q = ("SELECT season, period, team, market, SUM(value) "
         "FROM player_game_logs WHERE sport=? AND market IN (%s) "
         "GROUP BY 1, 2, 3, 4" % ",".join("?" * len(markets)))
    for (season, period, team, market, value) in conn.execute(
            q, (sport, *markets)):
        out[(season, period, team)][market] = float(value or 0.0)
    return out


def _mean(weeks, prior, market):
    vals = [weeks.get(w, {}).get(market, 0.0) for w in prior]
    return sum(vals) / len(vals) if vals else 0.0


def red_zone_over_overall(row, ctx):
    """Red-zone share MINUS overall opportunity share.

    The model already carries both, but as separate multiplicative terms.
    What it never asks is whether a player is used MORE heavily near the
    goal line than his general workload implies — the difference between
    a back who gets 20% of the touches everywhere and one who gets 20%
    everywhere and 45% inside the ten. If that gap carries information
    the shipped chain has not already spent, this is where it shows.
    """
    if not row["rz_share"]:
        return None
    return row["rz_share"] - row["opp_share"]


def usage_trend(row, ctx):
    """Recent opportunity share against the rest of the prior window.

    "He is being used more lately" — a role that is climbing, measured
    only on weeks already played. A snap-count version would be better
    and the NFL has the column; college has none, so this uses touches,
    which both sports carry.
    """
    prior = row["prior_weeks"]
    if len(prior) < TREND_WEEKS + 1:
        return None
    recent, older = prior[-TREND_WEEKS:], prior[:-TREND_WEEKS]
    weeks = ctx["form"].get((row["season"], row["short"]))
    if not weeks:
        return None
    tw = ctx["team_week"]

    touches = ctx["touch_markets"]

    def share(window):
        own = sum(sum(_mean(weeks, [w], m) for m in touches)
                  for w in window) / len(window)
        team = sum(sum(tw.get((row["season"], w, row["team"]), {}).get(m, 0.0)
                       for m in touches)
                   for w in window) / len(window)
        return (own / team) if team > 0 else None

    a, b = share(recent), share(older)
    if a is None or b is None:
        return None
    return a - b


def quarterback_goal_line(row, ctx):
    """The share of the team's inside-5 carries its QUARTERBACK takes.

    The handbook proposes this as a RULE — cap the back once the
    quarterback passes 40% — and as a rule it separates almost nothing
    (0.250 against 0.238 over 2,203 lead-back games, z = +0.74). The
    reason given at the time was that the red-zone denominator counts
    every player, so a rushing quarterback already dilutes the back
    without anyone adding a term. This is that claim's actual test: if
    the dilution is complete, the number adds nothing HERE.
    """
    # REFUSED, NOT ZEROED. The college feed publishes no inside-five
    # column, and reading `i5_car` against it returns 0.0 from every
    # lookup — a candidate that measures nothing and reports a flat AUC
    # as though it had been tested. `evaluate` treats None as "no cover".
    i5 = ctx.get("goal_line_market")
    if not i5:
        return None
    prior = row["prior_weeks"]
    weeks_by_team = ctx["qb_i5"].get((row["season"], row["team"]))
    team_i5 = ctx["team_week"]
    if not weeks_by_team:
        return None
    qb = sum(weeks_by_team.get(w, 0.0) for w in prior)
    tot = sum(team_i5.get((row["season"], w, row["team"]), {}).get(i5, 0.0)
              for w in prior)
    if tot <= 0:
        return None
    return qb / tot


def teammate_vacancy(row, ctx):
    """How much of the team's prior opportunity belongs to players who
    are NOT playing this week.

    The one genuinely new kind of information here: everything else
    describes the player, this describes the room around him. A back
    whose share was 22% behind a starter who is out this week is not a
    22% back today, and nothing in the shipped chain knows that.

    Absence is inferred from the log table — a player with prior-window
    usage and no row this week did not play — which is what the live
    board can also see on a Sunday, so it is not hindsight.

    MEASURED AND NOT ADOPTED, 2026-08-30, and the way it failed is worth
    keeping. It was the only candidate to move both metrics the right
    way (+0.0005 AUC, -0.0004 log-loss over 22,099 rows), and a band
    table looked like it had found something real: the model came in 25%
    low on settled teams and 59% low on the most depleted ones.

    But high-vacancy rows are mostly BACKUPS, and backups sit at low
    model probabilities, so a general low-probability miss produces that
    exact picture with nothing to do with the room. Holding the model's
    own opinion fixed inside narrow probability bands, the gradient does
    not survive — it is not monotone in the NFL (1.34 / 1.27 / 1.62 at
    5-10%, but 1.27 / 1.32 / 1.29 at 15-22%) and it is flat everywhere in
    college. The confound was the whole effect.

    Kept in the list because it is the right IDEA — nothing else here
    describes the room rather than the player — and because a future
    version with real inactives, rather than absence inferred after the
    fact from a log table, is a different and better feature than this
    one. What is settled is that THIS proxy does not carry it.
    """
    season, week, team = row["season"], row["week"], row["team"]
    prior = row["prior_weeks"]
    roster = ctx["roster"].get((season, team))
    playing = ctx["played"].get((season, week, team))
    if not roster or not playing:
        return None
    gone, total = 0.0, 0.0
    for short, weeks in roster.items():
        own = sum(weeks.get(w, 0.0) for w in prior)
        if own <= 0:
            continue
        total += own
        if short not in playing and short != row["short"]:
            gone += own
    if total <= 0:
        return None
    return gone / total


#: WHAT THE FOUR CANDIDATES MEASURED, 2026-08-30, over 22,099 graded NFL
#: player-weeks, leave-one-season-out:
#:
#:     candidate                      cover        AUC          log-loss
#:     red-zone share over overall      84%   0.7002 -> 0.7002  0.4882 -> 0.4882
#:     usage trend, last 3 weeks        89%   0.7203 -> 0.7203  0.4555 -> 0.4555
#:     QB share of inside-5 work        99%   0.7213 -> 0.7212  0.4507 -> 0.4507
#:     teammate vacancy this week      100%   0.7212 -> 0.7217  0.4505 -> 0.4501
#:
#: NONE OF THEM ADD ANYTHING. Three are flat to four decimal places and
#: the fourth is a confound (see `teammate_vacancy`). That is a real
#: answer, not a failed search: it says the within-team allocation the
#: model already does is as good as these inputs can make it, and the
#: next gain has to come from information this database does not hold —
#: injury designations before kickoff, depth charts, personnel packages —
#: rather than from another arrangement of touches and red-zone counts.
#:
#: The QB result is the one that confirms something. The handbook wanted
#: a rule capping a back once his quarterback passes 40% of inside-5
#: carries; as a rule it separated almost nothing (z = +0.74), and the
#: explanation offered then was that the red-zone denominator counts
#: every player, so the dilution already happens. -0.0001 AUC over 21,885
#: rows is that explanation being right.
#:
#: AND THE SAME ANSWER IN COLLEGE, 2026-08-30, over 29,047 graded
#: player-weeks across 2022-2025 on the college chain:
#:
#:     candidate                      cover        AUC          log-loss
#:     red-zone share over overall      84%   0.6704 -> 0.6703  0.5656 -> 0.5655
#:     usage trend, last 3 weeks        79%   0.6738 -> 0.6739  0.5575 -> 0.5574
#:     QB share of inside-5 work         —    not in this feed
#:     teammate vacancy this week      100%   0.6749 -> 0.6756  0.5486 -> 0.5484
#:
#: Two leagues, two chains, two independent samples, one answer: the
#: within-team allocation is spent. That is worth more than either table
#: alone — a null in one sport is a null that might be about that sport,
#: and the college numbers were measured against a DIFFERENT model with
#: DIFFERENT columns and land in the same place.
#:
#: The college baseline sits ~0.67 against the NFL's ~0.72, which is the
#: model being genuinely worse at ranking college players and not a
#: defect in this harness — `cfbtdfit` reports the same figure.
#:
#: The vacancy term is again the largest mover and again the confound
#: (+0.0007 here, +0.0005 there); `teammate_vacancy`'s own note already
#: recorded that its band gradient is flat in college, and this is that
#: observation arriving from the other direction.
CANDIDATES = (
    ("red-zone share over overall", red_zone_over_overall),
    ("usage trend, last 3 weeks", usage_trend),
    ("QB share of inside-5 work", quarterback_goal_line),
    ("teammate vacancy this week", teammate_vacancy),
)


def context(conn, sport: str) -> dict:
    """Everything the candidates need, keyed the way the replay keys.

    PER SPORT, because the two feeds do not carry the same columns. The
    NFL logs a target and an inside-five carry; the college feed logs
    neither and logs receptions instead. Reading the NFL names against
    college rows does not fail — every lookup returns 0.0, the candidate
    computes a share of nothing, and the harness reports a flat AUC as
    though the feature had been tested and found wanting. That is the
    worst outcome available: a negative result nobody can distinguish
    from a wiring fault.
    """
    sport = (sport or "nfl").lower()
    touches = touch_markets(sport)
    i5 = GOAL_LINE_MARKET.get(sport)
    rz = RZ_MARKETS.get(sport, RZ_MARKETS["nfl"])
    wanted = tuple(dict.fromkeys(touches + rz + ((i5,) if i5 else ())))
    form = _by_player(conn, sport, wanted)
    team_week = _team_week(conn, sport, tuple(dict.fromkeys(
        touches + ((i5,) if i5 else ()))))
    qb_i5: dict = defaultdict(dict)
    roster: dict = defaultdict(dict)
    played: dict = defaultdict(set)
    for (season, short), weeks in form.items():
        team = short[2]
        for wk, marks in weeks.items():
            touch = sum(marks.get(m, 0.0) for m in touches)
            roster[(season, team)].setdefault(short, {})[wk] = touch
            if touch > 0:
                played[(season, wk, team)].add(short)
            if i5 and (marks.get("_pos") or "").upper() == "QB":
                qb_i5[(season, team)][wk] = marks.get(i5, 0.0)
    return {"form": form, "team_week": team_week, "qb_i5": qb_i5,
            "roster": roster, "played": played,
            "sport": sport, "touch_markets": touches,
            "goal_line_market": i5}


def graded_rows(conn, sport: str) -> list:
    """One row per graded player-week, with that sport's replay's inputs.

    ROUTED BY SPORT, and this is the whole of what kept the file NFL-only.
    `tdbacktest` replays `engine.touchdowns`; college ships a different
    chain in `engine.cfb.tds`, replayed by `engine.cfbtdfit`. Running one
    against the other's logs grades a model nobody runs — done once on
    2026-08-30, and it produced a confident table showing the college
    calibration failing badly when on the real chain the same bands are
    sound.
    """
    rows: list = []
    if (sport or "").lower() == "cfb":
        from . import cfbtdfit
        cfbtdfit.run(conn, collect=rows.append)
    else:
        B.run(conn, sport, collect=rows.append)
    for r in rows:
        r["short"] = _short_key(r["player"], r["team"]) if r["player"] \
            else ("", "", r["team"])
    return rows


def evaluate(rows, feature, ctx) -> dict | None:
    """Leave-one-season-out AUC and log-loss, with and without the term."""
    usable = []
    for r in rows:
        x = feature(r, ctx)
        if x is None or not math.isfinite(x):
            continue
        usable.append((r, float(x)))
    if not usable:
        # NOT THE SAME AS THIN, and the difference is the whole answer.
        # Zero rows means the feature could not be BUILT here — a column
        # this feed does not publish — not that it was measured and found
        # small. Reporting both as "too thin" invites the reader to treat
        # an untested candidate as a tested one.
        return {"rows": 0, "unavailable": True}
    if len(usable) < MIN_ROWS:
        return {"rows": len(usable), "thin": True}

    base_pairs, cand_pairs = [], []
    seasons = sorted({r["season"] for r, _x in usable})
    for season in seasons:
        train = [(r, x) for r, x in usable if r["season"] != season]
        test = [(r, x) for r, x in usable if r["season"] == season]
        if len(train) < MIN_ROWS or len(test) < MIN_TEST:
            continue
        ys = [r["scored"] for r, _x in train]
        b0 = fit_logistic([[1.0, logit(r["prob"])] for r, _x in train], ys)
        b1 = fit_logistic([[1.0, logit(r["prob"]), x] for r, x in train], ys)
        if b0 is None or b1 is None:
            continue
        for r, x in test:
            z = logit(r["prob"])
            base_pairs.append((sigmoid(b0[0] + b0[1] * z), r["scored"]))
            cand_pairs.append((sigmoid(b1[0] + b1[1] * z + b1[2] * x),
                               r["scored"]))
    if not base_pairs:
        return {"rows": len(usable), "thin": True}
    return {"rows": len(usable),
            "auc_base": auc(base_pairs), "auc_cand": auc(cand_pairs),
            "ll_base": log_loss(base_pairs), "ll_cand": log_loss(cand_pairs),
            "coverage": len(usable) / len(rows)}


def report(sport: str = B.NFL_ONLY, conn=None) -> list:
    close = conn is None
    conn = conn or _db.connect()
    try:
        rows = graded_rows(conn, sport)
        out = [f"=== {sport.upper()} — {len(rows):,} graded player-weeks"]
        if len(rows) < MIN_ROWS:
            return out + ["  too few graded player-weeks to measure"]
        scored = sum(r["scored"] for r in rows)
        out.append(f"  {scored:,} scored ({scored / len(rows):.1%}), "
                   f"seasons {min(r['season'] for r in rows)}-"
                   f"{max(r['season'] for r in rows)}")
        ctx = context(conn, sport)
        out.append(f"  {'candidate':<30} {'rows':>7} {'cover':>6} "
                   f"{'AUC':>16} {'log-loss':>16}")
        for label, feature in CANDIDATES:
            got = evaluate(rows, feature, ctx)
            if got is not None and got.get("unavailable"):
                out.append(f"    {label:<28} {'—':>7}   not in this feed — "
                           f"refused rather than scored on zeros")
                continue
            if got is None or got.get("thin"):
                n = 0 if got is None else got["rows"]
                out.append(f"    {label:<28} {n:>7}   too thin to score")
                continue
            d_auc = got["auc_cand"] - got["auc_base"]
            d_ll = got["ll_cand"] - got["ll_base"]
            # A term has to help BOTH: reordering while wrecking the
            # probabilities is worse than useless on a board that
            # compares them to prices.
            verdict = "  <-- adds" if d_auc > 0.002 and d_ll < 0 else ""
            out.append(
                f"    {label:<28} {got['rows']:>7} {got['coverage']:>6.0%} "
                f"{got['auc_base']:.4f}->{got['auc_cand']:.4f} "
                f"{got['ll_base']:.4f}->{got['ll_cand']:.4f}{verdict}")
        return out
    finally:
        if close:
            conn.close()


def main(argv=None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    for i, sport in enumerate(args or [B.NFL_ONLY]):
        if i:
            print()
        for line in report(sport):
            print(line)
    return 0


if __name__ == "__main__":                                # pragma: no cover
    raise SystemExit(main())
