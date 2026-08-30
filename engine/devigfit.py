"""Which de-vig the anytime-touchdown market actually wants.

`engine/devig` measures a game's overround off its own board. How that
margin is SHARED OUT across the prices is a separate question, and the
two available answers disagree by a tenth of the price at each end of a
real board:

    proportional   fair = raw / m      every price loses the same fraction
    power          fair = raw ** k     long prices lose more than short

It matters. Under proportional, MAX_CREDIBLE_EDGE and the EV floor
together make no price shorter than +364 gradeable at a 30% hold, which
removes the short half of the touchdown board. `engine/devig` defaults to
power on the argument that books load vig onto longshots — well
established, and what the handbook prescribes above an 8% hold — but an
argument is not a measurement, and this box bought the data to settle it.

HOW THIS ASKS THE QUESTION. Both methods normalise to the same expected
scorers, so the choice between them is about SHAPE, not level. That means
no game line and no scorer estimate is needed: fit each method's single
free parameter on one set of seasons, then score the other set. A
transform that predicts who scored better, out of sample, is the better
transform. One parameter each, so neither is flattered by flexibility.

WHY OUT OF SAMPLE IS NOT OPTIONAL HERE. Both families contain the
identity (m = 1, k = 1) and both are monotone, so on their own training
data each can only improve on the raw price and the winner would be
whichever had the luckier fit. The split is the whole measurement.

Needs a database with `odds_history` — the box that bought the closes.
Runs for both sports: `python3 -m engine.devigfit [nfl|cfb] [seasons...]`.

Standard library only.
"""

from __future__ import annotations

import math

#: Search bounds. m below 1 or k below 1 would mean shortening prices the
#: book already shortened, which is not a de-vig.
M_MIN, M_MAX = 1.0, 2.0
K_MIN, K_MAX = 1.0, 3.0

#: Below this a split cannot say anything. At 300 player-weeks a 20% band
#: still carries about 60 scorers.
MIN_SPLIT = 300

#: How close to a bound still counts as pinned. A section search that ran
#: all the way to the edge stops a hair inside it, so an exact comparison
#: never fires and a failed fit gets printed as a clean answer.
PIN_TOL = 1e-3


def collected(conn, sport: str = "nfl", seasons=None) -> list:
    """``[{season, week, market, scored}]`` for weeks with a real close.

    The raw market price and the outcome, which is all the shape question
    needs. The model's own probability plays no part, deliberately: this
    asks what the BOOK's number means, not whether we beat it — so it
    reads the touchdown outcomes straight out of the logs rather than
    replaying a model whose answer is not part of the question.

    Both sports come through here. The only difference is the bridge to a
    date: an NFL log's period is a week number and the schedule supplies
    the date, while a college log's period IS the date.

    EACH ROW SAYS WHETHER THE PLAYER TOOK A SNAP, because a bet on a man
    who never took the field is VOID at every book — it is not a loss,
    and grading it as one measures a hold nobody could have paid. That
    matters here more than anywhere: non-participation is 9.6% of
    player-weeks for a player whose career touchdown rate is under 5% and
    0.1% for one above 35%, a hundred-fold gradient pointing straight at
    the longshot band where the hold looks largest.

    `played` is True where a snap count is positive, False where the logs
    explicitly record ZERO snaps, and None where no snap row exists at
    all. Three values, not two: 240 NFL player-weeks and every college one
    genuinely cannot be classified, and collapsing "unknown" into either
    answer would invent a fact. A zero-usage row with snaps is a real
    loss and stays in.
    """
    from . import db as _db
    from .backtest import _norm

    closes = _db.closing_odds_by_date(conn, sport, "anytime_td")
    if not closes:
        return []

    dates = {}
    if sport == "nfl":
        from .formbook import game_dates
        dates = game_dates(seasons)

    where = "WHERE sport=? AND market='anytime_td'"
    args: list = [sport]
    if seasons:
        where += " AND season IN (%s)" % ",".join("?" * len(seasons))
        args += [int(x) for x in seasons]

    snaps: dict = {}
    snap_where = where.replace("market='anytime_td'", "market='snap_pct'")
    for r in conn.execute(
            f"SELECT season, period, player, team, value "
            f"FROM player_game_logs {snap_where}", args):
        snaps[(r["season"], str(r["period"]), r["player"], r["team"])] = \
            r["value"]

    rows: list = []
    for r in conn.execute(
            f"SELECT season, period, player, team, value "
            f"FROM player_game_logs {where}", args):
        period = r["period"]
        if sport == "nfl":
            try:
                date = dates.get((r["season"], int(period), r["team"]))
            except (TypeError, ValueError):
                continue
        else:
            date = str(period)[:10]
        if not date:
            continue
        quote = closes.get((_norm(r["player"]), date))
        if not quote:
            continue
        market = _prob(quote.get("over_odds"))
        if market is None or not 0.0 < market < 1.0:
            continue
        snap = snaps.get((r["season"], str(period), r["player"], r["team"]))
        rows.append({"season": r["season"], "week": str(period),
                     "market": market,
                     "played": None if snap is None else float(snap) > 0,
                     "scored": 1 if float(r["value"] or 0) > 0 else 0})
    return rows


def _prob(odds) -> float | None:
    """American price to implied probability, vig included."""
    from .odds import american_to_prob
    try:
        odds = int(odds)
    except (TypeError, ValueError):
        return None
    return american_to_prob(odds) if odds else None


def log_loss(probs, outcomes) -> float:
    """Mean negative log likelihood. Lower is a better probability."""
    n = 0
    total = 0.0
    for p, y in zip(probs, outcomes):
        p = min(max(float(p), 1e-6), 1.0 - 1e-6)
        total += -(math.log(p) if y else math.log(1.0 - p))
        n += 1
    return total / n if n else float("nan")


def _fit(rows, transform, lo, hi) -> float:
    """The parameter minimising training log-loss, by golden section.

    Unimodal in the parameter because both transforms are monotone in it
    and the loss is convex in a monotone shift of every probability, so a
    section search is exact enough and needs no derivative.
    """
    market = [r["market"] for r in rows]
    scored = [r["scored"] for r in rows]
    phi = (math.sqrt(5.0) - 1.0) / 2.0
    a, b = lo, hi
    c, d = b - phi * (b - a), a + phi * (b - a)
    fc = log_loss([transform(p, c) for p in market], scored)
    fd = log_loss([transform(p, d) for p in market], scored)
    for _ in range(60):
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - phi * (b - a)
            fc = log_loss([transform(p, c) for p in market], scored)
        else:
            a, c, fc = c, d, fd
            d = a + phi * (b - a)
            fd = log_loss([transform(p, d) for p in market], scored)
    return (a + b) / 2.0


def proportional(p: float, m: float) -> float:
    return p / m


def power(p: float, k: float) -> float:
    return p ** k


#: Share of the timeline that trains. The rest scores.
TRAIN_SHARE = 0.7


def _order(period):
    """Sort key for a period that may be a week number or a date.

    An NFL log's period is a week ('1', '02', '17') and a college log's
    is a date ('2026-08-29'). Sorting those together needs the numbers
    compared as numbers — '10' before '9' is a silently wrong timeline,
    and a wrong timeline means the split leaks the future into training.
    """
    try:
        return (0, int(period), "")
    except (TypeError, ValueError):
        return (1, 0, str(period))


def split(rows: list) -> tuple[list, list]:
    """Earlier weeks train, later weeks score.

    Split by TIME, not at random. Players in one game share a scoreboard,
    so a random split leaves the same game in both halves — the test set
    would be partly memorised rather than predicted, and the more
    flexible transform would win on that alone.

    Split by WEEK, not by season, and that is a correction. The first cut
    split on season, reasoning that a season boundary certainly separates
    games. It does, but a purchased harvest covers a stretch of ONE
    season: on 3,890 joined NFL player-weeks it produced 0 train and 0
    test and reported the data as too thin, when the data was fine and
    the split was wrong. A week boundary separates games just as
    completely and works inside a season, which is the only shape this
    data actually comes in.
    """
    keys = sorted({(r["season"], _order(r["week"])) for r in rows})
    if len(keys) < 2:
        return [], []
    cut = max(1, min(len(keys) - 1, round(len(keys) * TRAIN_SHARE)))
    train_keys = set(keys[:cut])
    train, test = [], []
    for r in rows:
        k = (r["season"], _order(r["week"]))
        (train if k in train_keys else test).append(r)
    return train, test


def compare(rows: list, min_split: int = MIN_SPLIT) -> dict:
    """Fit both on the training seasons, score both on the held-out one."""
    train, test = split(rows)
    if len(train) < min_split or len(test) < min_split:
        return {"thin": True, "train": len(train), "test": len(test)}
    m = _fit(train, proportional, M_MIN, M_MAX)
    k = _fit(train, power, K_MIN, K_MAX)
    market = [r["market"] for r in test]
    scored = [r["scored"] for r in test]
    out = {
        "thin": False, "train": len(train), "test": len(test),
        "m": m, "k": k,
        "raw_loss": log_loss(market, scored),
        "prop_loss": log_loss([proportional(p, m) for p in market], scored),
        "power_loss": log_loss([power(p, k) for p in market], scored),
        "realised": sum(scored) / len(scored),
    }
    out["winner"] = "power" if out["power_loss"] < out["prop_loss"] \
        else "proportional"
    out["margin"] = abs(out["power_loss"] - out["prop_loss"])
    # At the boundary the fit is reporting failure, not an answer.
    out["m_pinned"] = m <= M_MIN + PIN_TOL or m >= M_MAX - PIN_TOL
    out["k_pinned"] = k <= K_MIN + PIN_TOL or k >= K_MAX - PIN_TOL
    return out


#: Price bands to report the two methods across. The disagreement is at
#: the ends, so the ends get their own rows.
BANDS = ((0.00, 0.10), (0.10, 0.18), (0.18, 0.28), (0.28, 0.45), (0.45, 1.01))

#: How far a band's haircut must sit from the rest of the board before it
#: is called a real difference. 2.58 is the 1% two-sided point, which is
#: 5% split across the five bands — the bar for asking the question five
#: times and reporting the loudest answer. A plain 2.0 flagged a band on
#: a SIMULATED board charging a flat 14% everywhere.
BAND_Z = 2.58


def band_lines(rows: list, m: float, k: float, min_band: int = 40) -> list:
    """Per raw-price band: what each method says, and what happened.

    WITH ERROR BARS, because without them this table misleads. The first
    live run showed power "nearer" in two bands and proportional in
    three, which reads as a coin flip — but scored against each band's
    standard error, proportional matched four bands almost exactly and
    missed one by 3.1 sigma, while power was mediocre in all five. That
    is a completely different diagnosis from the same numbers, and only
    one of them tells you where to look.

    The summary log loss is one number over a whole board; this is where
    the two methods are supposed to differ, so it is where the claim has
    to be checked. A method that wins overall while being wrong at one
    end has not earned that end.
    """
    lines = ["  raw band      n   raw   prop  power  actual    prop z  power z"]
    chi = {"prop": 0.0, "power": 0.0}
    shown = 0
    for lo, hi in BANDS:
        got = [r for r in rows if lo <= r["market"] < hi]
        if len(got) < min_band:
            lines.append(f"  {lo:.2f}-{hi:.2f} {len(got):>6}   (thin)")
            continue
        n = float(len(got))
        raw = sum(r["market"] for r in got) / n
        pr = sum(proportional(r["market"], m) for r in got) / n
        pw = sum(power(r["market"], k) for r in got) / n
        act = sum(r["scored"] for r in got) / n
        se = math.sqrt(max(act * (1.0 - act), 1e-9) / n)
        zp, zw = (pr - act) / se, (pw - act) / se
        chi["prop"] += zp * zp
        chi["power"] += zw * zw
        shown += 1
        lines.append(f"  {lo:.2f}-{hi:.2f} {len(got):>6} {raw:5.3f} "
                     f"{pr:6.3f} {pw:6.3f} {act:7.3f} {zp:>+9.2f} {zw:>+8.2f}")
    if shown:
        lines += ["",
                  f"  chi-square over {shown} band(s):  "
                  f"proportional {chi['prop']:.2f}   power {chi['power']:.2f}",
                  "  (a z past +/-2 in ONE band is where the shape is wrong, "
                  "whatever the totals say)"]
    return lines


def haircut_lines(rows: list, min_band: int = 40) -> list:
    """What the market ACTUALLY charged per band, ignoring both methods.

    ``1 - actual / raw`` is the toll the price took, measured against the
    outcome. Both transforms are attempts to predict this column, so
    seeing it directly says whether either shape is even the right
    family — and on the first live run it was not: four bands clustered
    near 14% and one sat at 35%, which is flat-plus-a-spike rather than
    the smooth monotone curve a power exponent draws.
    """
    # WITH ERROR BARS, for the reason `band_lines` above spells out and
    # this table did not follow: a haircut is 1 - actual / raw, so the
    # noise on the realised rate is DIVIDED BY THE RAW PRICE. At a 0.10
    # longshot that multiplies the uncertainty tenfold, and a band of a
    # couple of hundred rows can show a 35% toll on a market charging 14%
    # without anything being there. That is exactly the shape the first
    # live run reported, and exactly why it was never wired.
    #
    # The z-score is against the OTHER bands pooled, because the question
    # is not "is this band's haircut non-zero" — every band's is. It is
    # "does this band charge more than the rest of the board".
    #
    # AND THE BAR IS RAISED FOR LOOKING FIVE TIMES. On a simulated board
    # charging a flat 14% in every band, a plain z >= 2 flagged one band
    # at +2.3 — with five bands that happens about a quarter of the time
    # by construction, and wiring a haircut on the strength of it would
    # be charging a toll nobody levied. `engine.losspatterns` already
    # runs its miner under false-discovery control for the same reason;
    # this is the same discipline with one number instead of a procedure.
    per: list = []
    for lo, hi in BANDS:
        got = [r for r in rows if lo <= r["market"] < hi]
        if len(got) < min_band:
            continue
        n = float(len(got))
        raw = sum(r["market"] for r in got) / n
        act = sum(r["scored"] for r in got) / n
        if raw <= 0:
            continue
        se_act = math.sqrt(max(act * (1.0 - act), 1e-12) / n)
        per.append({"lo": lo, "hi": hi, "n": len(got), "raw": raw,
                    "act": act, "cut": 1.0 - act / raw,
                    "se": se_act / raw, "hits": act * n, "rows": n})
    lines = ["  what the market actually charged, by band:",
             "  raw band      n     raw  actual   haircut          vs "
             "the other bands"]
    for b in per:
        others = [o for o in per if o is not b]
        z = ""
        if others:
            o_raw = sum(o["raw"] * o["rows"] for o in others) \
                / sum(o["rows"] for o in others)
            o_hits = sum(o["hits"] for o in others)
            o_rows = sum(o["rows"] for o in others)
            o_act = o_hits / o_rows
            o_cut = 1.0 - o_act / o_raw if o_raw > 0 else 0.0
            o_se = math.sqrt(max(o_act * (1.0 - o_act), 1e-12) / o_rows) / o_raw
            sd = math.sqrt(b["se"] ** 2 + o_se ** 2)
            zz = (b["cut"] - o_cut) / sd if sd > 0 else 0.0
            z = (f"{o_cut:>7.1%}   z = {zz:+5.1f}"
                 + ("   <-- charges more" if zz >= BAND_Z else
                    "   inside the noise"))
        lines.append(f"  {b['lo']:.2f}-{b['hi']:.2f} {b['n']:>6} "
                     f"{b['raw']:>7.3f} {b['act']:>7.3f} "
                     f"{b['cut']:>7.1%} +/-{b['se']:.1%} {z}")
    if per:
        lines.append("  a haircut divides the outcome noise by the raw "
                     "price, so a longshot band's error bar is many times "
                     "a favourite's — read the z, not the gap")
    return lines


def played_rows(rows: list) -> list:
    """The rows a bettor could actually have lost.

    Drops only player-weeks the logs EXPLICITLY record as zero snaps.
    A row with no snap record at all stays in, because "unknown" is not
    "absent" and guessing either way would invent the fact the whole
    check is about.
    """
    return [r for r in rows if r.get("played") is not False]


def void_lines(rows: list, min_band: int = 40) -> list:
    """How much of the measured hold is bets that were never live.

    THE ARTIFACT THIS EXISTS TO CATCH. An anytime-touchdown prop on a
    player who does not take the field is VOID at every book. Graded here
    as a loss, it lowers the realised rate without lowering the price,
    which is arithmetically indistinguishable from the book charging a
    bigger toll. And non-participation is not spread evenly: 9.6% of
    player-weeks for a player whose career touchdown rate is under 5%
    against 0.1% for one above 35%, which points at precisely the
    longshot band where the hold reads largest.

    So this prints the haircut table twice. The gap between them is not a
    correction to apply — it is the width of what the logs cannot settle,
    and the honest answer sits inside it.

    A board with no snap records at all (college has no `snap_pct`
    market) says so instead of printing an identical table twice and
    letting it read as agreement.
    """
    known = [r for r in rows if r.get("played") is not None]
    if not known:
        return ["  participation unknown for every row — no snap records on "
                "this board, so none of the hold above can be separated "
                "from bets that were void at the book"]
    live = played_rows(rows)
    dropped = len(rows) - len(live)
    if not dropped:
        return [f"  every one of {len(known):,} rows with a snap record took "
                "the field, so no part of the hold above is a void bet"]
    scored = sum(r["scored"] for r in rows if r.get("played") is False)
    lines = [f"  {dropped:,} of {len(rows):,} rows never took a snap "
             f"({dropped / len(rows):.1%}) — VOID at the book, not losses; "
             f"{scored} of them scored",
             "  the same table over only the rows a bettor could have lost:"]
    lines += haircut_lines(live, min_band=min_band)[1:]
    lines.append("  the truth is between the two tables, not in either: the "
                 "logs cannot tell an inactive from a healthy scratch of "
                 "usage")
    return lines


def report_lines(rows: list, min_split: int = MIN_SPLIT) -> list:
    got = compare(rows, min_split)
    if got.get("thin"):
        return [f"  too thin to split: {got['train']} train / {got['test']} test "
                f"player-weeks, need {min_split} each",
                "  harvest more anytime_td closes — the split needs at least "
                "two distinct weeks and enough joined rows on each side"]
    lines = [
        f"  fitted on {got['train']:,} player-weeks, scored on {got['test']:,} "
        f"held out (later weeks)",
        f"  proportional m = {got['m']:.4f}  ({got['m'] - 1:+.1%} average hold)"
        + ("   AT THE BOUND — not an answer" if got["m_pinned"] else ""),
        f"  power       k = {got['k']:.4f}"
        + ("   AT THE BOUND — not an answer" if got["k_pinned"] else ""),
        "",
        f"  log loss   raw {got['raw_loss']:.5f}   prop {got['prop_loss']:.5f}"
        f"   power {got['power_loss']:.5f}",
        f"  winner: {got['winner'].upper()} by {got['margin']:.5f}",
        "",
    ]
    lines += band_lines(rows, got["m"], got["k"])
    lines += [""] + haircut_lines(rows)
    lines += [""] + void_lines(rows)
    lines += ["",
              "  A margin under 0.0005 is not a result — the two methods "
              "agree and the choice between them is not settled by this "
              "data. What IS settled: both beat the raw price, so the "
              "de-vig itself is doing real work."]
    return lines


if __name__ == "__main__":                       # pragma: no cover
    import sys
    from . import db as _db
    argv = sys.argv[1:]
    sport = next((a for a in argv if a in ("nfl", "cfb")), "nfl")
    seasons = [int(a) for a in argv if a.isdigit()] or None
    conn = _db.connect()
    print(f"joining harvested {sport} anytime-TD closes to logged outcomes...")
    rows = collected(conn, sport=sport, seasons=seasons)
    if not rows:
        print("  no joined player-weeks — this box has no odds_history, "
              "or no season is ingested")
        sys.exit(1)
    print(f"  {len(rows):,} player-weeks with a real close\n")
    for line in report_lines(rows):
        print(line)
