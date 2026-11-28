"""The Most Likely board's chances, made honest by its own record.

    sudo -u qellys python3 -m engine.likelycal fit --sport nfl      # measure; save only if it holds
    sudo -u qellys python3 -m engine.likelycal fit --sport nfl --dry-run
    sudo -u qellys python3 -m engine.likelycal show
    sudo -u qellys python3 -m engine.likelycal fit --sport nba --dry-run   # + when ours and the price agree

Ethan, 2026-10-03, after the box's record check: "I don't want to really
get rid of any most likely bets ... I just want to use the everything we've
collected ... make the picks better, make what we recommend better."

WHAT THE RECORD SAID (2026-10-03, the NFL board, 300 settled):
  * the Most Likely list's own picks hold up — said 65%, hit 65% over 372;
  * the board's other picks do not: the matchup picks went 18-43 and the
    "bolder than the books" picks 23-38, while claiming the list's kind of
    number, and the board's unders claimed 63% and hit 49% (every sport);
  * the record check vouched for them anyway, because it reads the list's
    record for the same market, side and band — the honest picks' record,
    lent to picks from somewhere else.

WHAT THIS DOES. Nothing is removed. Each board pick's chance is pulled
toward the price's own chance by as much as picks LIKE IT — the same sport,
the same maker (the list, the matchup picks, the touchdown scenarios, the
bold rows) and the same side — have earned in the journal:

    shown = price's chance + k × (our chance − price's chance),  0 ≤ k ≤ 1

k = 1 leaves a group's number alone (its record backs it); k = 0 says its
record is no better than the price. A chance is only ever lowered, never
raised, except in the NBA and the NHL since 21 November, where a pick priced
above our number may rise toward the price (`RAISE_SPORTS`, Ethan: "8. Yes").
The tiers, the ranking and the card then read the honest number, so
a pick that hit 30% stops wearing "Top pick" and one that holds up rises.
The price's chance is the American price's implied chance with an average
4.5% two-way hold taken out (DEVIG).

HOW IT IS KEPT FROM FITTING NOISE. k is chosen per group by log loss, and
only for groups of MIN_GROUP settled picks. Before anything is saved the
whole correction is scored on picks it was not fitted on: five folds split
by game (day and team), each fold's k fitted on the other four. The NFL
board is one week old, so a split by date would leave a few dozen picks to
judge; a split by game keeps every slate's picks on one side. THE BAR,
WRITTEN BEFORE ANY RUN: the held-out log loss must improve, at the bottom
of its 95% interval (a bootstrap over games). Pass → the k's fitted on
every pick are saved to the store the board reads on its next build. Fail
→ nothing is saved and the board keeps its own numbers. The record keeps
the board's raw chance beside the shown one (`raw_prob`), so the next fit
reads the raw claim and never compounds its own correction.

BY MARKET TOO (Ethan, 2026-11-03, "2, yes"). A maker's side is a wide
group: the record's own cuts found college receiving-yards unders hitting
50% where we said 70% inside a list whose unders as a whole did far better.
So a maker's side on one market (``list|under|rec_yds``) is a group of its
own once it has MIN_GROUP settled picks, fitted on those picks; the rest of
the maker's side is fitted on what the market groups leave. It is kept
only if it earns it, on the same held-out folds: the market-level
correction must beat the raw chance at the bottom of its 95% interval, and,
where the maker-level one passes too, must beat THAT at the bottom of its
interval. Otherwise the maker-level fit is what is saved, as before. The
rule is Ethan's either way: a chance is only ever lowered, and a pick is
never taken off the board for its record.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import os
import random
import sys
from pathlib import Path

DEVIG = 1.045
MIN_GROUP = 40
FOLDS = 5
BOOT = 2000
SEED = 20261003
K_GRID = tuple(round(i * 0.05, 2) for i in range(21))
def _store() -> Path:
    """data/models/likely_calibration.json (engine/modelstate: a fit belongs
    to the box that measured it, and the suite sandboxes the directory —
    engine/boardlearn refits this nightly, so a test must never reach the
    real one). Read at call time, so the sandbox is honoured."""
    from . import modelstate
    return Path(os.environ.get("QB_LIKELY_CAL", "").strip() or modelstate.path("likely_calibration.json"))
#: The other books a board pick can also sit in, asked in this order.
SOURCE_BOOKS = (("bold", ("bold",)), ("matchup", ("matchup_td", "matchup_prop")),
                ("scenario", ("td_scenario",)))
SOURCE_WORDS = {"list": "Most Likely list", "matchup": "matchup picks",
                "scenario": "touchdown scenarios", "bold": "bolder-than-the-books picks"}


def price_chance(odds) -> float | None:
    """The price's own chance, the average hold taken out."""
    try:
        o = int(float(odds))
    except (TypeError, ValueError):
        return None
    if abs(o) < 100:
        return None
    p = ((-o) / ((-o) + 100.0) if o < 0 else 100.0 / (o + 100.0)) / DEVIG
    return min(0.98, max(0.02, p))


def side_of(side) -> str:
    s = str(side or "").lower()
    return "under" if s in ("under", "no") else "over"


def source_of_row(r: dict) -> str:
    """A board row's maker, as the build sees it (r["sources"], r["bold"])."""
    src = r.get("sources") or []
    if r.get("bold"):
        return "bold"
    if "likely" in src:
        return "list"
    if "matchup" in src:
        return "matchup"
    if "scenario" in src:
        return "scenario"
    return "list"


#: WHERE THE RECORD MAY RAISE A CHANCE (Ethan, 21 November: "8. Yes"). Their
#: rule since 3 October was that the record only ever lowers one. The NBA's and
#: hockey's picks are where that cost: the NBA's picks priced above our number
#: at 50-60% hit 66.9% where we said 57.3% (614 picks), so the price was right
#: and our number low. In these leagues the correction may pull a chance UP to
#: the price's own chance (never above it, and never past our number when ours
#: is the higher), by as much as the group's record has earned on the same
#: held-out folds and the same bar as a lowering. Everywhere else a chance is
#: only lowered, as before. `QB_RECORD_RAISES=off` holds every league to lowering.
RAISE_SPORTS = ("nba", "nhl")


def raises(sport: str) -> bool:
    """May the record raise a chance in ``sport`` (RAISE_SPORTS, unless switched off)?"""
    return (str(sport or "").lower() in RAISE_SPORTS
            and os.environ.get("QB_RECORD_RAISES", "").strip().lower() != "off")


#: WHEN OUR NUMBER AND THE PRICE AGREE (decision 19; Ethan, 23 November: "do
#: whatever you think. All I want is picks that win the most on there, and we
#: need to be truthful about our shit"). The NBA's Most Likely picks won more
#: than they said: 3,371 graded picks said 61.2% and won 64.2%. The list's
#: overs said 61.3%, the price 63.0%, and won 65.5% (1,375); its unders said
#: 61.8%, the price 59.4%, and won 64.3% (1,711). Its Edge bets, where our
#: number and the price DISAGREE, said 51.2% and won 48.3% (451). Two reads
#: that are partly separate and land on the same side are stronger together
#: than either alone, and the k above can only put a chance somewhere between
#: ours and the price's, so it could never show those picks what they win.
#:
#: WHAT THIS DOES, WRITTEN BEFORE ANY RUN. In a league where the record may
#: raise a chance (`raises`), a pick whose raw number AND price's chance are
#: both above AGREE_FLOOR on its side shows
#:
#:     shown = σ(a + b·logit(ours) + c·logit(price))
#:
#: with a, b and c fitted for its maker (the list, the matchup picks, the
#: bold picks), overs and unders together, on that maker's settled picks
#: where the two agreed, by log loss, held gently (RIDGE) toward the plain
#: average of the two (a = 0, b = c = ½) so two numbers that move together
#: cannot send the weights wild. A maker needs AGREE_MIN such picks. It can
#: put a chance above both numbers, and lower one where agreeing picks at
#: that level said too much. Picks where the two disagree keep the k above.
#:
#: OVERS AND UNDERS TOGETHER, chosen before any run on the NBA's own counts:
#: one fit with the same weights on both numbers matches both sides (the
#: overs, where the price says more than we do, and the unders, where we
#: say more than the price: σ(0.66·(logit ours + logit price)) at each
#: side's average numbers gives 65.8% and 63.8% where they won 65.4% and
#: 64.2%, the Record of 23 November), and three weights fitted on
#: twice the picks are judged far more surely than six on half. On a
#: made-up record the NBA's size (3,450 picks over 468 games) whose picks
#: win their own number, it passed in none of eight tries either way.
#:
#: THE BAR is every correction's here: scored on the same five game folds
#: (each fold's fit made on the other four) against what the board shows
#: WITHOUT it (the k's own held-out correction where that one is saved, else
#: our raw number), the held-out log loss must improve at the bottom of its
#: 95% interval (a bootstrap over games). Pass → saved to its own store and
#: read on the next build; fail → nothing saved, and a saved one that stops
#: passing is removed. Each league is judged on its own picks: the NBA
#: first, hockey only if its own record passes. It changes the chance shown,
#: the tier a pick earns and the order, never which picks the list carries.
#: Off without a deploy: `QB_RECORD_AGREE=off`.
AGREE_FLOOR = 0.5
AGREE_MIN = 200
RIDGE = 2.0
AGREE_PRIOR = (0.0, 0.5, 0.5)


def agree_on(sport: str) -> bool:
    """Does the agreement correction run in ``sport`` (a raise league, unless switched off)?"""
    return raises(sport) and os.environ.get("QB_RECORD_AGREE", "").strip().lower() != "off"


def agrees(p, q) -> bool:
    """Our number and the price's chance both above AGREE_FLOOR on the pick's side."""
    return p is not None and q is not None and float(p) > AGREE_FLOOR and float(q) > AGREE_FLOOR


def shrink(p: float, q: float, k: float, up: bool = False) -> float:
    """Our chance ``p`` pulled toward the price's ``q`` by ``1 - k``: only ever lowered, unless ``up``
    (`raises`), when a pick priced above our number may rise toward the price."""
    adj = max(0.02, min(0.98, q + k * (p - q)))
    return adj if up else min(p, adj)


def _ll(p: float, won: bool) -> float:
    p = min(0.999, max(0.001, p))
    return -math.log(p if won else 1 - p)


# --- the journal ----------------------------------------------------------
def journal_rows(conn, sport: str) -> list[dict]:
    """Settled Most Likely picks, each ONCE, tagged with the maker the board
    credits it to (bold first, then the list, the matchup picks, the
    scenarios — `source_of_row`'s order), at the raw claim.

    It reads the journal through engine/likelyctx.journal, the same reading
    nflaudit.py reports from. Until 2026-10-04 it matched a board row to the
    other books on the `date` column, and the box's first fit (494 NFL
    picks) printed no bold group at all while the audit, keyed on the game
    day, found 61 bold picks hitting 38% where we said 75%: the worst maker
    on the board was invisible to the one correction built for it."""
    from .likelyctx import journal, maker
    out = []
    for r in journal(conn, sport):
        row = _row(r, maker(r["sources"]))
        if row is not None:
            out.append(row)
    return out


def _row(r, source):
    q = price_chance(r["odds"])
    if q is None:
        return None
    return {"group": f"{source}|{side_of(r['side'])}", "p": float(r["p"]), "q": q,
            "won": bool(r["won"]), "market": market_of(r.get("market")),
            "game": f"{r['day']}|{r.get('team') or r['player']}"}


def market_of(market) -> str:
    """A market's key as the groups write it: lower case, no spaces."""
    return str(market or "").strip().lower().replace(" ", "_")


# --- the fit ----------------------------------------------------------------
#: A maker's overs and unders together — read only when its own side is
#: too small to fit (`k_for`).
BOTH = "both"


def k_for(groups: dict, group: str, market: str | None = None) -> dict | None:
    """The fitted group a pick reads: its maker on its side on its market
    (when the market level was saved, see the module's BY MARKET TOO),
    else its maker on its side, else — when that side has too few settled
    picks to fit — its maker on both sides.

    Added 2026-10-04 after the box's run: the bold picks went 13-20 on
    unders and 17-25 on overs while claiming 71-74%, and neither side alone
    reached MIN_GROUP inside a training fold, so the held-out test never
    saw a bold correction at all. Same bar, same held-out test; the group
    is just the maker when the side cannot carry one."""
    m = market_of(market) if market else ""
    return ((m and groups.get(f"{group}|{m}")) or groups.get(group)
            or groups.get(f"{group.split('|')[0]}|{BOTH}"))


def _fit_one(rs: list[dict], up: bool = False) -> dict:
    best = min(K_GRID, key=lambda k: sum(_ll(shrink(x["p"], x["q"], k, up), x["won"]) for x in rs))
    return {"k": best, "n": len(rs),
            "hit": round(sum(x["won"] for x in rs) / len(rs), 4),
            "claimed": round(sum(x["p"] for x in rs) / len(rs), 4),
            "price": round(sum(x["q"] for x in rs) / len(rs), 4)}


def fit_groups(rows: list[dict], by_market: bool = False, up: bool = False) -> dict:
    """{group: {"k", "n", "hit", "claimed", "price"}} for groups of
    MIN_GROUP or more; smaller groups are left alone (absent). Each maker
    is also fitted on both sides together (``maker|both``), read only where
    its side has no fit of its own.

    ``by_market``: a maker's side on one market (``maker|side|market``)
    with MIN_GROUP picks is fitted on its own picks, and the maker-level
    groups on the picks no market group took, so each pick is fitted in
    exactly the group it reads (`k_for`)."""
    out = {}
    rest = rows
    if by_market:
        mk: dict = {}
        for r in rows:
            if r.get("market"):
                mk.setdefault(f"{r['group']}|{r['market']}", []).append(r)
        taken = set()
        for g, rs in mk.items():
            if len(rs) >= MIN_GROUP:
                out[g] = _fit_one(rs, up)
                taken.update(id(x) for x in rs)
        rest = [r for r in rows if id(r) not in taken]
    by: dict = {}
    for r in rest:
        by.setdefault(r["group"], []).append(r)
        by.setdefault(f"{r['group'].split('|')[0]}|{BOTH}", []).append(r)
    for g, rs in by.items():
        if len(rs) >= MIN_GROUP:
            out[g] = _fit_one(rs, up)
    return out


def held_out(rows: list[dict], folds=FOLDS, seed=SEED, up: bool = False) -> dict:
    """Out-of-fold log loss, raw against corrected, games kept whole."""
    games = sorted({r["game"] for r in rows})
    rng = random.Random(seed)
    rng.shuffle(games)
    fold_of = {g: i % folds for i, g in enumerate(games)}
    per_game: dict = {}
    for f in range(folds):
        train = [r for r in rows if fold_of[r["game"]] != f]
        ks = fit_groups(train, up=up)
        km = fit_groups(train, by_market=True, up=up)
        for r in rows:
            if fold_of[r["game"]] != f:
                continue
            k = (k_for(ks, r["group"]) or {}).get("k", 1.0)
            k2 = (k_for(km, r["group"], r.get("market")) or {}).get("k", 1.0)
            raw, adj = _ll(r["p"], r["won"]), _ll(shrink(r["p"], r["q"], k, up), r["won"])
            adj2 = _ll(shrink(r["p"], r["q"], k2, up), r["won"])
            cell = per_game.setdefault(r["game"], [0.0, 0.0, 0, 0.0])
            cell[0] += raw
            cell[1] += adj
            cell[2] += 1
            cell[3] += adj2
    cells = list(per_game.values())
    n = sum(c[2] for c in cells)
    if not n:
        return {"n": 0}
    gain = (sum(c[0] for c in cells) - sum(c[1] for c in cells)) / n
    # One set of draws for all three comparisons: the maker level against
    # the raw chance (the bar as it always was), and the market level
    # against the raw chance and against the maker level.
    boots, b_raw, b_mk = [], [], []
    for _ in range(BOOT):
        pick = [cells[rng.randrange(len(cells))] for _ in cells]
        m = sum(c[2] for c in pick)
        boots.append((sum(c[0] for c in pick) - sum(c[1] for c in pick)) / m if m else 0.0)
        b_raw.append((sum(c[0] for c in pick) - sum(c[3] for c in pick)) / m if m else 0.0)
        b_mk.append((sum(c[1] for c in pick) - sum(c[3] for c in pick)) / m if m else 0.0)
    for b in (boots, b_raw, b_mk):
        b.sort()
    lo_i, hi_i = int(0.025 * BOOT), int(0.975 * BOOT) - 1
    market = {"corrected": round(sum(c[3] for c in cells) / n, 4),
              "gain_vs_raw": round((sum(c[0] for c in cells) - sum(c[3] for c in cells)) / n, 5),
              "lo_vs_raw": round(b_raw[lo_i], 5),
              "gain": round((sum(c[1] for c in cells) - sum(c[3] for c in cells)) / n, 5),
              "lo": round(b_mk[lo_i], 5), "hi": round(b_mk[hi_i], 5)}
    return {"n": n, "games": len(cells), "raw": round(sum(c[0] for c in cells) / n, 4),
            "corrected": round(sum(c[1] for c in cells) / n, 4), "gain": round(gain, 5),
            "lo": round(boots[lo_i], 5), "hi": round(boots[hi_i], 5), "market": market}


def choose_level(ho: dict) -> tuple[bool, bool]:
    """``(passed, by_market)`` from a held-out report: the maker level
    passes on the bar as it always was; the market level passes against the
    raw chance and, where the maker level passes too, against that, each at
    the bottom of its 95% interval."""
    if not ho.get("n"):
        return False, False
    maker_ok = ho.get("lo", 0) > 0
    mk = ho.get("market") or {}
    market_ok = mk.get("lo_vs_raw", 0) > 0 and (not maker_ok or mk.get("lo", 0) > 0)
    return bool(maker_ok or market_ok), bool(market_ok)


def fit(conn, sport: str) -> dict:
    rows = journal_rows(conn, sport)
    up = raises(sport)
    ho = held_out(rows, up=up) if rows else {"n": 0}
    passed, by_market = choose_level(ho)
    groups = fit_groups(rows, by_market=by_market, up=up)
    return {"sport": sport, "n": len(rows), "held_out": ho, "groups": groups, "passed": passed,
            "by_market": by_market,
            "fitted_at": _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")}


# --- the agreement fit (decision 19) ----------------------------------------
def _logit(p: float) -> float:
    p = min(0.98, max(0.02, float(p)))
    return math.log(p / (1.0 - p))


def _sig(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def agree_chance(p: float, q: float, w) -> float:
    """σ(a + b·logit(p) + c·logit(q)), kept inside 2-98%."""
    a, b, c = (float(x) for x in w)
    return max(0.02, min(0.98, _sig(a + b * _logit(p) + c * _logit(q))))


def _solve3(m: list, v: list) -> list:
    """m⁻¹·v for a 3×3 system (Gaussian elimination, partial pivoting)."""
    a = [row[:] + [v[i]] for i, row in enumerate(m)]
    for col in range(3):
        piv = max(range(col, 3), key=lambda r: abs(a[r][col]))
        a[col], a[piv] = a[piv], a[col]
        if abs(a[col][col]) < 1e-12:
            return [0.0, 0.0, 0.0]
        for r in range(3):
            if r != col:
                f = a[r][col] / a[col][col]
                for c in range(col, 4):
                    a[r][c] -= f * a[col][c]
    return [a[i][3] / a[i][i] for i in range(3)]


def _newton(xs: list, ys: list, free: tuple) -> list[float]:
    """Penalised log loss (RIDGE toward AGREE_PRIOR) minimised over the
    weights in ``free``; the others stay at zero. Newton's method: the
    penalised loss has one minimum."""
    th = [AGREE_PRIOR[i] if i in free else 0.0 for i in range(3)]
    for _ in range(60):
        g = [RIDGE * (th[i] - AGREE_PRIOR[i]) if i in free else 0.0 for i in range(3)]
        h = [[(RIDGE if i == j else 0.0) if i in free and j in free else (1.0 if i == j else 0.0)
              for j in range(3)] for i in range(3)]
        for x, y in zip(xs, ys):
            m = _sig(th[0] * x[0] + th[1] * x[1] + th[2] * x[2])
            d, wt = m - y, m * (1.0 - m)
            for i in free:
                g[i] += d * x[i]
                for j in free:
                    h[i][j] += wt * x[i] * x[j]
        step = _solve3(h, g)
        th = [th[i] - step[i] if i in free else 0.0 for i in range(3)]
        if max(abs(s) for s in step) < 1e-9:
            break
    return th


def fit_agree_one(rs: list[dict]) -> list[float]:
    """(a, b, c) by log loss with RIDGE toward AGREE_PRIOR. A higher chance
    from either number never lowers ours: a weight that comes out below
    zero is held at zero and the others are fitted again without it (set to
    zero and left there, the rest would no longer fit — the first cut did
    that, and on a made-up record where only our number mattered it scored
    worse than our raw number)."""
    xs = [(1.0, _logit(r["p"]), _logit(r["q"])) for r in rs]
    ys = [1.0 if r["won"] else 0.0 for r in rs]
    free = (0, 1, 2)
    th = _newton(xs, ys, free)
    while any(th[i] < 0 for i in free if i):
        free = tuple(i for i in free if not (i and th[i] < 0))
        th = _newton(xs, ys, free)
    return [th[0], max(0.0, th[1]), max(0.0, th[2])]


def agree_group(group: str) -> str:
    """The agreement correction's group for a pick's k group: its maker,
    overs and unders together (``list|both``)."""
    return f"{str(group).split('|')[0]}|{BOTH}"


def agree_groups(rows: list[dict]) -> dict:
    """{maker|both: {"w", "n", "hit", "claimed", "price", "shown"}} for each
    maker with AGREE_MIN settled picks where our number and the price agreed."""
    by: dict = {}
    for r in rows:
        if agrees(r["p"], r["q"]):
            by.setdefault(agree_group(r["group"]), []).append(r)
    out = {}
    for g, rs in by.items():
        if len(rs) < AGREE_MIN:
            continue
        w = fit_agree_one(rs)
        n = len(rs)
        out[g] = {"w": [round(x, 5) for x in w], "n": n,
                  "hit": round(sum(x["won"] for x in rs) / n, 4),
                  "claimed": round(sum(x["p"] for x in rs) / n, 4),
                  "price": round(sum(x["q"] for x in rs) / n, 4),
                  "shown": round(sum(agree_chance(x["p"], x["q"], w) for x in rs) / n, 4)}
    return out


def held_out_agree(rows: list[dict], base_level=None, up: bool = False,
                   folds=FOLDS, seed=SEED) -> dict:
    """Out-of-fold log loss on the agreeing picks, the board without this
    against the board with it, games kept whole. ``base_level`` is how the
    k above was saved (False: by maker and side, True: by market too) and
    the board's number without this is that k's fit on the other four
    folds; None (no k saved) means our raw number."""
    games = sorted({r["game"] for r in rows})
    rng = random.Random(seed)
    rng.shuffle(games)
    fold_of = {g: i % folds for i, g in enumerate(games)}
    per_game: dict = {}
    for f in range(folds):
        train = [r for r in rows if fold_of[r["game"]] != f]
        ks = fit_groups(train, by_market=bool(base_level), up=up) if base_level is not None else {}
        ag = agree_groups(train)
        if not ag:
            continue
        for r in rows:
            if fold_of[r["game"]] != f or not agrees(r["p"], r["q"]):
                continue
            g = ag.get(agree_group(r["group"]))
            if not g:
                continue
            k = (k_for(ks, r["group"], r.get("market")) or {}).get("k", 1.0)
            base = shrink(r["p"], r["q"], k, up) if k < 1.0 else r["p"]
            cell = per_game.setdefault(r["game"], [0.0, 0.0, 0])
            cell[0] += _ll(base, r["won"])
            cell[1] += _ll(agree_chance(r["p"], r["q"], g["w"]), r["won"])
            cell[2] += 1
    cells = list(per_game.values())
    n = sum(c[2] for c in cells)
    if not n:
        return {"n": 0}
    boots = []
    for _ in range(BOOT):
        pick = [cells[rng.randrange(len(cells))] for _ in cells]
        m = sum(c[2] for c in pick)
        boots.append((sum(c[0] for c in pick) - sum(c[1] for c in pick)) / m if m else 0.0)
    boots.sort()
    return {"n": n, "games": len(cells), "raw": round(sum(c[0] for c in cells) / n, 4),
            "corrected": round(sum(c[1] for c in cells) / n, 4),
            "gain": round((sum(c[0] for c in cells) - sum(c[1] for c in cells)) / n, 5),
            "lo": round(boots[int(0.025 * BOOT)], 5), "hi": round(boots[int(0.975 * BOOT) - 1], 5)}


def fit_agree(conn, sport: str, cal: dict | None = None, rows: list | None = None) -> dict:
    """The agreement correction for ``sport``, measured on its own graded
    picks. ``cal`` is this run's k fit (`fit`): where it passed, the board's
    number without this is that k's; else our raw number."""
    rows = journal_rows(conn, sport) if rows is None else rows
    on = agree_on(sport)
    level = bool(cal.get("by_market")) if cal and cal.get("passed") else None
    ho = held_out_agree(rows, level, raises(sport)) if (rows and on) else {"n": 0}
    return {"sport": sport, "n": len(rows), "agreeing": sum(1 for r in rows if agrees(r["p"], r["q"])),
            "held_out": ho, "groups": agree_groups(rows) if on else {}, "on": on,
            "passed": bool(on and ho.get("n") and ho.get("lo", 0) > 0),
            "fitted_at": _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")}


def _agree_store() -> Path:
    """data/models/likely_agree.json, beside the k's store (see `_store`)."""
    from . import modelstate
    return Path(os.environ.get("QB_LIKELY_AGREE", "").strip() or modelstate.path("likely_agree.json"))


def load_agree(path=None) -> dict:
    try:
        return json.loads((Path(path) if path else _agree_store()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_agree(res: dict, path=None) -> None:
    p = Path(path) if path else _agree_store()
    p.parent.mkdir(parents=True, exist_ok=True)
    store = load_agree(p)
    store[res["sport"]] = {"groups": res["groups"], "held_out": res["held_out"], "fitted_at": res["fitted_at"]}
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(store, indent=1), encoding="utf-8")
    tmp.replace(p)


def drop_agree(sport: str, path=None) -> bool:
    """Remove a league's agreement correction; True if it had one."""
    p = Path(path) if path else _agree_store()
    store = load_agree(p)
    if sport not in store:
        return False
    del store[sport]
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(store, indent=1), encoding="utf-8")
    tmp.replace(p)
    return True


#: A maker's picks as the card names them.
AGREE_WORDS = {"list": "Most Likely list picks", "matchup": "Matchup picks", "scenario": "Touchdown scenario picks",
               "bold": "Bolder-than-the-books picks"}


def agree_note(src: str, g: dict, shown: float, raw: float, q: float) -> str:
    """The card's sentence: what agreeing picks of this maker have done, and the number it shows."""
    return (f"{AGREE_WORDS.get(src, src)} where our number and the price agree have hit "
            f"{g['hit']:.0%} of {g['n']:,} where we said {g['claimed']:.0%} and the price (its cut "
            f"taken out) {g['price']:.0%}, so this shows {shown:.0%} (our number {raw:.0%}, its price {q:.0%})")


# --- the store and the board -----------------------------------------------
def load(path=None) -> dict:
    p = Path(path) if path else _store()
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(res: dict, path=None) -> None:
    p = Path(path) if path else _store()
    p.parent.mkdir(parents=True, exist_ok=True)
    store = load(p)
    store[res["sport"]] = {"groups": {g: {"k": v["k"], "n": v["n"], "hit": v["hit"], "claimed": v["claimed"]}
                                      for g, v in res["groups"].items()},
                           "by_market": bool(res.get("by_market")),
                           "held_out": res["held_out"], "fitted_at": res["fitted_at"]}
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(store, indent=1), encoding="utf-8")
    tmp.replace(p)


def apply(rows: list[dict], sport: str, store: dict | None = None, agree: dict | None = None) -> int:
    """Correct each board row's chance in place, before its checks; returns
    how many moved. The raw chance rides along as ``board_raw_prob`` (the
    journal keeps it as ``raw_prob``) and the reason as ``cal_note``.

    A pick where our number and the price agree, in a league whose
    agreement correction is saved (`agree_on`, `fit_agree`), shows that
    correction's number instead of the k's; ``agree_from`` keeps what the k
    alone would have shown. ``cal_raised`` says the number shown is above
    our raw one: the record found picks like it win MORE than we said, so
    nothing reads it as a proven over-claim (likelyboard.held_reason).
    ``agree`` is that store (default: its file; none when the caller hands
    its own k ``store``, so a caller's store is all that moves its rows)."""
    groups = ((store if store is not None else load()).get(sport) or {}).get("groups") or {}
    up = raises(sport)
    if agree is None:
        agree = load_agree() if store is None else {}
    ag = ((agree.get(sport) or {}).get("groups") or {}) if agree_on(sport) else {}
    moved = 0
    for r in rows:
        r.pop("agree_from", None)
        r.pop("cal_raised", None)
        if r.get("model_prob") is None:
            continue
        src = source_of_row(r)
        side = side_of(r.get("side"))
        market = market_of(r.get("market"))
        g = k_for(groups, f"{src}|{side}", market)
        q = price_chance(r.get("odds"))
        raw = float(r["model_prob"])
        a = ag.get(f"{src}|{BOTH}") if (ag and agrees(raw, q)) else None
        if a:
            k = g["k"] if g else 1.0
            shown = round(agree_chance(raw, q, a["w"]), 4)
            if abs(shown - raw) < 5e-5:
                continue
            r["board_raw_prob"] = raw
            r["model_prob"] = shown
            r["agree_from"] = round(shrink(raw, q, k, up), 4) if k < 1.0 else raw
            r["cal_raised"] = shown > raw
            r["cal_note"] = agree_note(src, a, shown, raw, q)
            moved += 1
            continue
        if not g or q is None or g["k"] >= 1.0:
            continue
        adj = round(shrink(raw, q, g["k"], up), 4)
        # Lowered, or in a league where the record may raise one (`raises`), raised; never moved by nothing.
        if adj >= raw and not (up and adj > raw + 1e-9):
            continue
        r["board_raw_prob"] = raw
        r["model_prob"] = adj
        r["cal_raised"] = adj > raw
        if market and groups.get(f"{src}|{side}|{market}") is g:
            from .livepicks import market_label
            on = f"on the {side} on {market_label(market, sport).lower()}"
        else:
            on = f"on the {side}" if groups.get(f"{src}|{side}") else "(overs and unders together)"
        r["cal_note"] = (f"{SOURCE_WORDS.get(src, src)} {on} have hit "
                         f"{g['hit']:.0%} of {g['n']} where we said {g['claimed']:.0%}, so this shows "
                         f"{adj:.0%} (our raw number was {raw:.0%})")
        moved += 1
    return moved


# --- the command ------------------------------------------------------------
def _report(res: dict) -> None:
    ho = res["held_out"]
    print(f"\n=== {res['sport'].upper()}: {res['n']} settled picks the correction can learn from")
    for g, v in sorted(res["groups"].items(), key=lambda kv: -kv[1]["n"]):
        src, side, *mkt = g.split("|")
        what = "left alone" if v["k"] >= 1.0 else f"pulled {1 - v['k']:.0%} of the way to the price"
        print(f"    {SOURCE_WORDS.get(src, src):28} {side:5} {(mkt[0] if mkt else ''):12} n {v['n']:4}  "
              f"said {v['claimed']:.0%}  price {v['price']:.0%}  hit {v['hit']:.0%}  → {what}")
    if not ho.get("n"):
        print("    nothing to judge yet.")
        return
    print(f"    held out (5 folds by game, {ho['games']} games): log loss {ho['raw']} raw → "
          f"{ho['corrected']} corrected; gain {ho['gain']:+.4f}, 95% {ho['lo']:+.4f} to {ho['hi']:+.4f}")
    mk = ho.get("market") or {}
    if mk:
        print(f"    by market too: {mk['corrected']} held out; against the maker level "
              f"{mk['gain']:+.4f}, 95% {mk['lo']:+.4f} to {mk['hi']:+.4f} → "
              + ("kept: the board reads each market's own record"
                 if res.get("by_market") else "not kept: the maker level stands"))
    print("    PASSES — " + ("saved; the board reads it on its next build." if res["passed"] else "")
          if res["passed"] else "    NOT PROVEN — nothing saved; the board keeps its own numbers.")


def _report_agree(res: dict) -> None:
    ho = res["held_out"]
    print(f"\n    WHEN OUR NUMBER AND THE PRICE AGREE ({res['agreeing']} of {res['n']} picks):")
    if not res.get("on"):
        print("    not run in this league (the record may not raise a chance here).")
        return
    for g, v in sorted(res["groups"].items(), key=lambda kv: -kv[1]["n"]):
        src = g.split("|")[0]
        a, b, c = v["w"]
        print(f"    {SOURCE_WORDS.get(src, src):28} both  n {v['n']:4}  said {v['claimed']:.1%}  "
              f"price {v['price']:.1%}  hit {v['hit']:.1%}  → shows {v['shown']:.1%} "
              f"(σ({a:+.3f} {b:+.3f}·ours {c:+.3f}·price))")
    if not ho.get("n"):
        print("    nothing to judge yet.")
        return
    print(f"    held out (5 folds by game, {ho['games']} games, {ho['n']} picks): log loss {ho['raw']} as the "
          f"board shows them now → {ho['corrected']}; gain {ho['gain']:+.4f}, 95% {ho['lo']:+.4f} to {ho['hi']:+.4f}")
    print("    PASSES — saved; the board reads it on its next build." if res["passed"]
          else "    NOT PROVEN — nothing saved; agreeing picks keep the numbers above.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m engine.likelycal")
    ap.add_argument("cmd", choices=("fit", "show"), help="fit: measure and save if it holds; show: the store")
    ap.add_argument("--sport", default="nfl", help="the league to fit (default nfl)")
    ap.add_argument("--db", default="", help="ledger path (default data/ledger.db)")
    ap.add_argument("--dry-run", action="store_true", help="measure and report, save nothing")
    a = ap.parse_args(argv)
    if a.cmd == "show":
        print(json.dumps(load(), indent=1) or "{}")
        print(json.dumps({"when our number and the price agree": load_agree()}, indent=1))
        return 0
    import sqlite3
    from . import ledger
    path = a.db or str(ledger.DEFAULT_DB)
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    res = fit(conn, a.sport.lower())
    if res["passed"] and not a.dry_run:
        save(res)
    elif res["passed"]:
        print("(dry run: it would be saved)")
    _report(res)
    if raises(a.sport.lower()):
        ag = fit_agree(conn, a.sport.lower(), res)
        if ag["passed"] and not a.dry_run:
            save_agree(ag)
        _report_agree(ag)
    return 0


if __name__ == "__main__":
    sys.exit(main())
