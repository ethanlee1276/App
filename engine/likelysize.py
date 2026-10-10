"""What to stake on the likelihood board, read off the board's own record.

Ethan, 2026-09-21: *"I wanna raise stake and put real money on the most
likely paper bets and add all that to the record and we need to figure
out what unit sizes and money sizes makes the most sense and make the
most money and highest roi on the most likley bets."*

THE ONE ANSWER THAT HAS TO COME FIRST: **a flat stake cannot change
ROI.** ROI is net units over units staked, so doubling every stake
doubles both and lands on the same percentage. Staking 5u a row instead
of 0.25u on a board returning +9.5% returns +9.5% on twenty times the
money — twenty times the profit, twenty times the drawdown, the same
number on the page. "Most money" and "highest ROI" are therefore two
different requests, and only the first is a sizing question. `replay`
prints both columns side by side so that is visible rather than argued.

The ROI levers are which rows get taken and which get a bigger share —
`live_verdict` already stops a band that is not paying, and that is the
lever that moves the percentage.

SIZED ON THE LOWER BOUND, NOT THE POINT ESTIMATE. The measured edge is
an estimate with a standard error, and Kelly on an over-estimated edge
is how bankrolls die: the penalty for staking twice the optimum is
worse than for staking half of it, and the optimum itself is uncertain.
So the edge is taken `EDGE_Z` standard errors BELOW what the record
says. A board whose advantage is real grows into a bigger stake as the
sample grows and the bound tightens. A board that was lucky shrinks
back down on its own, without anyone having to notice.

QUARTER KELLY, THEN DIVIDED BY THE MEASURED CORRELATION. Kelly assumes
one bet at a time. This board puts ten or twenty rows on one slate, and
same-slate props are not independent — a game that goes under drags
every receiving line with it. Rather than assume a correlation, this
MEASURES one: the variance of the board's per-slate results against what
independence would have predicted. That ratio is how many bets this
board is really making at once, and the stake is divided by it. With too
few slates to measure, it falls back to the whole slate — the fully
correlated assumption, which is the safe direction to be wrong in.

CAPPED BELOW THE EDGE BOOK'S OWN CEILING. `staking.MAX_PRICED_U` is
1.25u for the book with the most evidence behind it. A board still
inside its own noise band does not out-stake it.
"""

from __future__ import annotations

#: How much of Kelly. A quarter is the standard practical answer: it
#: gives about 94% of the growth rate for about a quarter of the
#: variance, and it is forgiving of an edge that turns out smaller than
#: measured — which is the error this book is most likely to be making.
KELLY_FRACTION = 0.25

#: How many standard errors BELOW the measured ROI the stake is sized
#: on. One, not two: two is the bar for calling an edge real and would
#: hold the stake at the floor for years, and this is a sizing decision
#: rather than a publication. The asymmetry is the argument — being
#: half-sized costs a little growth, being double-sized can cost the
#: bankroll.
EDGE_Z = 1.0

#: Never smaller than the board has been staking since 2026-09-19.
#: Below this the measurement stops being worth its own bookkeeping, and
#: the demotion that matters is `live_verdict`'s stop, which is zero.
FLOOR_U = 0.25

#: And never above the Edge book's own ceiling — see the module note.
CAP_U = 1.0

#: THE MOST THIS BOARD MAY HAVE RIDING ON ONE SLATE, in units — 12% of
#: bankroll at a 1u = 1% ruler.
#:
#: The correlation divisor above is an ESTIMATE, and the failure it
#: cannot protect against is the one where it is wrong: forty props on
#: one Sunday, priced off one model, losing together because the model
#: was wrong about that Sunday rather than about football. Kelly sizes
#: for the average day. This is the cap for the bad one, and it is a
#: flat rule rather than a measured one on purpose — the whole point of
#: it is to hold when the measurement is mistaken.
MAX_SLATE_U = 12.0

#: Settled rows before the stake moves off the floor at all.
#:
#: THE SAME BAR THE BOARD ALREADY SET FOR ITSELF. `ledger.LIKELY_VERDICT_N`
#: is 100, and below it the Record page refuses to offer a verdict
#: because "a ten-point miss and a run of luck look identical". A stake
#: is a stronger statement than a verdict, so it cannot move on less.
#:
#: Without this the lower bound alone let a twenty-row board at +16%
#: size up, because a point estimate that high keeps its bound positive
#: even when the bound is enormous. A small sample read as a result is
#: the error this repo has made more than any other.
MIN_N = 100

#: Slates needed before the correlation is measured at all. Below this
#: the whole slate is assumed to move as one.
#:
#: THERE IS NO CLIFF ABOVE IT. A hard "20 slates or assume the worst"
#: was the first cut and it was wrong in a way worth writing down: an
#: NFL Sunday is forty props across thirteen different games, and
#: calling that ONE bet is not caution, it is a claim about football
#: that is plainly false. It held the stake at the floor for a league
#: whose measured edge supported four times it, on the strength of an
#: assumption nobody had checked. So the correlation is estimated from
#: whatever slates exist and then inflated by ITS own uncertainty — see
#: `measure`. Few slates means a big inflation rather than a pretence.
MIN_SLATES = 5

#: How many standard errors the correlation estimate is inflated by
#: before the stake is divided by it. Same asymmetry as `EDGE_Z`: an
#: under-estimated correlation over-stakes a whole slate at once.
CORR_Z = 1.0


def _decimal_profit(odds) -> float | None:
    """American price to profit per unit staked."""
    try:
        o = int(odds)
    except (TypeError, ValueError):
        return None
    if o >= 100:
        return o / 100.0
    if o <= -100:
        return 100.0 / -o
    return None


#: THE EVIDENCE IS BOTH BOOKS, and it has to be.
#:
#: `likely_live` only exists from 2026-09-19, so sizing on it alone
#: would read a fortnight of rows and hold every league at the floor
#: forever — while the answer sat in `likely`, which is the SAME
#: selection at a smaller stake. ROI does not care what a row was
#: staked at (see the module note), so a paper row is evidence about
#: the edge on exactly the same terms as a staked one. That is what the
#: paper book was kept for.
EVIDENCE_BOOKS = ("likely", "likely_live")


def _rows(conn, sport, category=EVIDENCE_BOOKS, since=None):
    # THE SLATE IS A CALENDAR DAY, NOT A LABEL. The NFL journals its
    # `date` as a week ("2026-W3"), so grouping on it would call a
    # whole week one slate — and the correlation divisor below is the
    # slate's row count, which would have read 53 bets riding at once
    # for a league that actually spreads them over Thursday, Sunday and
    # Monday. `game_day` is the calendar day every row is stamped with
    # for exactly this class of question.
    cats = (category,) if isinstance(category, str) else tuple(category)
    marks = ",".join("?" * len(cats))
    q = ("SELECT COALESCE(game_day, date) AS date, status, odds FROM bets "
         "WHERE status IN ('won','lost') AND stake_units > 0 "
         f"AND category IN ({marks})")
    args: list = list(cats)
    if sport:
        q += " AND sport=?"
        args.append(sport)
    if since:
        q += " AND date >= ?"
        args.append(since)
    return conn.execute(q, args).fetchall()


def measure(rows) -> dict:
    """The board's record as the sizing rule needs it.

    ``{n, wins, hit, roi, b, var, slates, slate_n, corr, corr_measured}``
    — every input the recommendation uses, returned rather than kept, so
    a number on the page can be traced back to the row count behind it.
    """
    profits, by_slate = [], {}

    for r in rows:
        b = _decimal_profit(r["odds"])
        if b is None:
            continue
        p = b if r["status"] == "won" else -1.0
        profits.append(p)
        by_slate.setdefault(str(r["date"]), []).append(p)
    n = len(profits)
    out = {"n": n, "wins": 0, "hit": None, "roi": None, "b": None,
           "var": None, "slates": len(by_slate), "slate_n": None,
           "corr": None, "corr_measured": False, "corr_raw": None,
           "corr_se_rel": None, "slate_max": 0}
    if not n:
        return out
    out["wins"] = sum(1 for p in profits if p > 0)
    out["hit"] = out["wins"] / n
    out["roi"] = sum(profits) / n          # flat stake: mean profit per unit
    wins = [p for p in profits if p > 0]
    out["b"] = (sum(wins) / len(wins)) if wins else None
    mean = out["roi"]
    out["var"] = sum((p - mean) ** 2 for p in profits) / n

    # HOW MANY BETS THIS BOARD IS REALLY MAKING AT ONCE. Independence
    # predicts a slate's variance is its row count times one row's. The
    # ratio of what actually happened to that is the correlation, and
    # dividing the stake by it is the whole of the adjustment.
    sizes = [len(v) for v in by_slate.values()]
    out["slate_n"] = (sum(sizes) / len(sizes)) if sizes else None
    # The BIGGEST one, not the average: the exposure cap is about the
    # worst night this board has, and an average night cannot describe it.
    out["slate_max"] = max(sizes) if sizes else 0
    k = len(by_slate)
    if k >= MIN_SLATES and out["var"] and out["slate_n"]:
        tot = [sum(v) - len(v) * mean for v in by_slate.values()]
        tvar = sum(t * t for t in tot) / k
        ratio = tvar / (out["slate_n"] * out["var"])
        # INFLATED BY ITS OWN UNCERTAINTY. A variance estimated from k
        # samples carries a relative standard error of about
        # sqrt(2/(k-1)), so nine slates means this ratio could honestly
        # be half again what it looks like. Erring high here costs a
        # smaller stake; erring low over-bets a whole slate at once.
        out["corr_se_rel"] = (2.0 / (k - 1)) ** 0.5 if k > 1 else None
        infl = ratio * (1.0 + CORR_Z * (out["corr_se_rel"] or 0.0))
        # Between one bet's worth of risk and the whole slate's: below 1
        # is sampling noise, not anti-correlation worth staking on.
        out["corr_raw"] = ratio
        out["corr"] = max(1.0, min(float(out["slate_n"]), infl))
        out["corr_measured"] = True
    else:
        # Too few slates to say anything: assume the slate moves as one.
        out["corr"] = float(out["slate_n"] or 1.0)
    return out


def roi_stderr(m: dict) -> float | None:
    """The standard error of the measured ROI, from the results
    themselves rather than from an assumed distribution."""
    if not m.get("n") or m.get("var") is None:
        return None
    return (m["var"] / m["n"]) ** 0.5


def recommend(m: dict) -> dict:
    """``{units, why, ...}`` — the stake, and every step that set it."""
    out = dict(m)
    se = roi_stderr(m)
    out["roi_se"] = se
    out["roi_lb"] = None
    out["kelly_full"] = None
    out["units"] = FLOOR_U
    out["over_exposed"] = False
    if not m.get("n") or se is None or not m.get("b"):
        out["why"] = ("nothing settled to size on — holding at the floor "
                      f"of {FLOOR_U}u")
        return out
    lb = m["roi"] - EDGE_Z * se
    out["roi_lb"] = lb
    if m["n"] < MIN_N:
        out["why"] = (
            f"{m['n']} settled, {MIN_N} needed before the stake moves — "
            f"the same bar the board's own verdict waits for, and a "
            f"stake says more than a verdict does. Holding at "
            f"{FLOOR_U}u")
        return out
    if lb <= 0:
        out["why"] = (
            f"measured {m['roi']:+.1%} on {m['n']} settled, but one "
            f"standard error below that is {lb:+.1%} — not yet an edge "
            f"anything should be sized on, so the stake holds at the "
            f"floor of {FLOOR_U}u")
        return out
    full = lb / m["b"]
    out["kelly_full"] = full
    raw = KELLY_FRACTION * full * 100.0 / (m["corr"] or 1.0)
    # AND THE CAP FOR THE BAD NIGHT, which Kelly does not price.
    slate_cap = (MAX_SLATE_U / m["slate_max"]) if m.get("slate_max") else CAP_U
    out["slate_cap_u"] = round(slate_cap, 3)
    units = round(min(CAP_U, slate_cap, max(FLOOR_U, raw)), 2)
    # …but never below the floor, which is what the board already stakes.
    # WHEN THE FLOOR WINS THAT IS A FINDING, NOT A ROUNDING. It means the
    # board is too wide to stake at this bankroll even at its smallest
    # size, and saying so is more use than quietly staking anyway.
    units = max(FLOOR_U, units)
    out["over_exposed"] = units > slate_cap + 1e-9
    out["units"] = units
    how = (f"measured {m['corr_raw']:.1f}, inflated for "
           f"{m['slates']} slates" if m["corr_measured"]
           else f"assumed — only {m['slates']} slates, too few to measure")
    out["why"] = (
        f"measured {m['roi']:+.1%} on {m['n']} settled; one standard "
        f"error below is {lb:+.1%}; full Kelly on that at an average "
        f"{m['b']:.2f} payout is {full:.1%} of bankroll; a quarter of it "
        f"is {KELLY_FRACTION * full * 100:.2f}u, divided by "
        f"{m['corr']:.1f} bets riding at once ({how}) = {raw:.2f}u"
        + (f"; held to {slate_cap:.2f}u so the biggest slate seen "
           f"({m['slate_max']} rows) cannot put more than {MAX_SLATE_U:.0f}u "
           f"at risk in one night" if slate_cap < min(CAP_U, raw) else "")
        + (f", capped at {CAP_U}u" if raw > CAP_U and slate_cap >= CAP_U
           else "")
        + (f", floored at {FLOOR_U}u" if units <= FLOOR_U < raw else "")
        + (f". NOTE: even at the {FLOOR_U}u floor the biggest slate "
           f"({m['slate_max']} rows) risks {units * m['slate_max']:.1f}u in "
           f"one night, over the {MAX_SLATE_U:.0f}u this book is meant to "
           f"put up — the board is wide for this bankroll"
           if out["over_exposed"] else ""))
    return out


def replay(rows, sizes) -> list:
    """What each flat size WOULD have returned on these rows.

    THE ROI COLUMN IS THE POINT, and it is the same in every row of this
    table. That is not a bug in the replay; it is the answer to half the
    question. What changes with size is the money and the drawdown.
    """
    seq, by_slate = [], {}
    for r in rows:
        b = _decimal_profit(r["odds"])
        if b is None:
            continue
        p = b if r["status"] == "won" else -1.0
        seq.append((str(r["date"]), p))
        by_slate.setdefault(str(r["date"]), []).append(p)
    seq.sort(key=lambda x: x[0])
    out = []
    for s in sizes:
        net = run = peak = dd = 0.0
        for _d, p in seq:
            run += s * p
            peak = max(peak, run)
            dd = min(dd, run - peak)
        net = run
        staked = s * len(seq)
        worst = min((s * sum(v) for v in by_slate.values()), default=0.0)
        # THE NUMBER THAT DECIDES THIS, and it is not on the ROI line.
        # A slate is bet all at once, so if the model is wrong in a
        # correlated way the whole slate goes down together. That is the
        # loss to size against, and it is the one a per-bet ROI hides.
        biggest = max((len(v) for v in by_slate.values()), default=0)
        out.append({
            "units": s, "net_units": round(net, 2),
            "units_staked": round(staked, 1),
            "roi": (net / staked) if staked else None,
            "max_drawdown_u": round(dd, 2),
            "worst_slate_u": round(worst, 2),
            "biggest_slate_rows": biggest,
            "if_a_slate_all_lost_u": round(-s * biggest, 2)})
    return out


def for_sport(conn, sport, category=EVIDENCE_BOOKS, since=None) -> dict:
    """The recommendation for one league's staked likelihood board."""
    return recommend(measure(_rows(conn, sport, category, since)))


#: One measurement per league per process. `log_most_likely` asks for
#: every row it journals, and the scan behind this reads the whole book;
#: doing it per row would put a full table scan inside a nightly loop.
#: A process here is one build, so the stake is re-derived every run
#: rather than pinned — which is the point of deriving it at all.
_CACHE: dict = {}


def staked_units(conn, sport, category=EVIDENCE_BOOKS) -> float:
    """The stake this league's board should be taking, in units.

    Cached per league per process — see `_CACHE`. Never raises into the
    journaling path: a sizing rule that can stop the night's bets being
    recorded is worse than a stake that is briefly the old constant.
    """
    key = (id(conn), str(sport or ""), tuple(category))
    if key not in _CACHE:
        try:
            _CACHE[key] = float(for_sport(conn, sport, category)["units"])
        except Exception:                                     # noqa: BLE001
            _CACHE[key] = FLOOR_U
    return _CACHE[key]
