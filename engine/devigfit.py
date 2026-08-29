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
        rows.append({"season": r["season"], "week": str(period),
                     "market": market,
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


def split(rows: list) -> tuple[list, list]:
    """Earlier seasons train, the latest season scores.

    Split by SEASON, not at random. A random split leaves the same game's
    other players in both halves, and players in one game share a
    scoreboard — so the test half would be partly memorised rather than
    predicted, and the more flexible transform would win on that alone.
    """
    seasons = sorted({r["season"] for r in rows})
    if len(seasons) < 2:
        return [], []
    last = seasons[-1]
    return ([r for r in rows if r["season"] != last],
            [r for r in rows if r["season"] == last])


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


def band_lines(rows: list, m: float, k: float, min_band: int = 40) -> list:
    """Per raw-price band: what each method says, and what happened.

    The summary loss is one number over a whole board; this is where the
    two methods are supposed to differ, so it is where the claim has to
    be checked. A method that wins overall while being wrong at the short
    end has not earned the short end.
    """
    lines = ["  raw band      n   raw   prop  power  actual   nearer"]
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
        nearer = "power" if abs(pw - act) < abs(pr - act) else "prop"
        if abs(abs(pw - act) - abs(pr - act)) < 0.002:
            nearer = "tie"
        lines.append(f"  {lo:.2f}-{hi:.2f} {len(got):>6} {raw:5.3f} "
                     f"{pr:6.3f} {pw:6.3f} {act:7.3f}   {nearer}")
    return lines


def report_lines(rows: list, min_split: int = MIN_SPLIT) -> list:
    got = compare(rows, min_split)
    if got.get("thin"):
        return [f"  too thin to split: {got['train']} train / {got['test']} test "
                f"player-weeks, need {min_split} each",
                "  harvest more anytime_td closes, or ingest another season"]
    lines = [
        f"  fitted on {got['train']:,} player-weeks, scored on {got['test']:,} "
        f"held out",
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
    lines += ["",
              "  A margin under 0.0005 is not a result — the two methods "
              "agree and the default stands on its reasoning."]
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
