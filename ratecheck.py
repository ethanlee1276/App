#!/usr/bin/env python3
"""Should a pitcher prop be projected as a TOTAL, or as a rate times length?

    python3 ratecheck.py                        # strikeouts, from data/history.db
    python3 ratecheck.py --from-db data/history.db --min-history 6
    python3 ratecheck.py --market outs          # the length half on its own

THE QUESTION

A strikeout prop is two predictions wearing one number:

    strikeouts  =  strikeouts per out  x  outs recorded

The first is stuff — how often he misses a bat — and it is a property of
the pitcher, stable across starts. The second is length, and it is a
MANAGER'S DECISION: bullpen state, pitch count, score, how the third time
through is going. Those two have nothing to do with each other and they
are not equally predictable.

The engine projects the total directly. engine/mlb/projection.py blends
his recent strikeout TOTALS (engine/form.compute_form) and multiplies by
park, weather, umpire and matchup — so a pitcher whose recent starts ran
seven innings projects high, and when tonight's start runs five the over
dies whether or not his stuff was fine. Nothing in that path knows how
long the start is expected to be.

The data to do it the other way is already there and already ingested:
MARKET_STAT maps OUTS to the API's own `outs` field, and history stores
strikeouts and outs for the same start under the same game_id.

WHAT THIS MEASURES

A walk-forward, per pitcher-start, projecting two ways from earlier starts
only:

    direct       blend of past strikeout totals            (what ships)
    decomposed   blend of past K-per-out  x  blend of past outs

scored by mean absolute error against what actually happened. Same blend,
same windows, same games — the only difference is whether rate and length
are estimated apart or together.

WHAT IT WILL NOT DO

Change the projection. If the decomposition wins it is worth building; if
it does not, that is the more useful answer, and either way the number
belongs on the table before anyone rewrites a pricing path.
"""

from __future__ import annotations

import argparse
import math
import sys

from engine.form import MLB_WINDOW_WEIGHTS, compute_form
from engine.mlb.models import MLBGameLog

#: Starts a pitcher needs before his next one is scored — the same shape
#: of floor the deep fitters use, so a thin log is not counted as evidence
#: for either method.
MIN_HISTORY = 5
#: A start with no outs recorded is a pitcher who never got anyone out;
#: the ratio is undefined and it is not a start to learn a rate from.
MIN_OUTS = 3


def load_starts(conn, market: str = "strikeouts") -> dict:
    """{player: [(period, value, outs) …]} in chronological order.

    Joined on game_id, so the value and the length come from the same
    start rather than from two averages that never met.
    """
    # `b.sport` is not decoration. Without it the join matches an outs row
    # from ANY sport that shares a game_id and player, and it also leaves
    # the inner lookup with no usable index — every index on this table
    # leads with (sport, market), so omitting the sport means none of them
    # can be used and SQLite falls back to scanning the whole table once
    # per outer row. On a real history that is the difference between a
    # second and never finishing.
    rows = conn.execute(
        "SELECT a.player, a.period, a.game_id, a.value AS v, b.value AS outs "
        "FROM player_game_logs a "
        "JOIN player_game_logs b "
        "  ON b.sport = a.sport AND b.market = 'outs' "
        " AND b.game_id = a.game_id AND b.player = a.player "
        "WHERE a.sport='mlb' AND a.market=? "
        "ORDER BY a.player, a.period, a.game_id", (market,)).fetchall()
    out: dict = {}
    for r in rows:
        out.setdefault(r["player"], []).append(
            (r["period"], float(r["v"] or 0), float(r["outs"] or 0)))
    return out


def _blend(values: list[float]) -> float | None:
    """The engine's own recency blend over a most-recent-first series."""
    if not values:
        return None
    logs = [MLBGameLog(game=i, opponent="", value=v)
            for i, v in enumerate(values)]
    career = sum(values) / len(values)
    return compute_form(logs, career, None,
                        weights=MLB_WINDOW_WEIGHTS).mean


def walk(starts: dict, min_history: int = MIN_HISTORY) -> dict:
    """Score both methods on every start that has enough history."""
    n = 0
    err_direct = err_decomp = err_oracle = 0.0
    paired: list[float] = []
    players = 0
    for player, series in starts.items():
        usable = [(v, o) for _p, v, o in series if o >= MIN_OUTS]
        if len(usable) <= min_history:
            continue
        players += 1
        for i in range(min_history, len(usable)):
            past = usable[:i]
            actual, actual_outs = usable[i]
            # Most-recent-first, which is what compute_form expects.
            vals = [v for v, _o in reversed(past)]
            outs = [o for _v, o in reversed(past)]
            rates = [v / o for v, o in reversed(past)]

            direct = _blend(vals)
            r, length = _blend(rates), _blend(outs)
            if direct is None or r is None or length is None:
                continue
            decomp = r * length
            # The ORACLE: the same rate blend times the length the start
            # actually ran. It cheats, deliberately. Decomposing only pays
            # if tonight's length can be predicted better than a pitcher's
            # own average, so this is the ceiling on what ANY leash model
            # could ever buy — bullpen state, pitch counts, all of it. If
            # the oracle barely beats projecting the total, the whole idea
            # is not worth building however good the story sounds.
            oracle = r * actual_outs
            ed, ec = abs(direct - actual), abs(decomp - actual)
            err_direct += ed
            err_decomp += ec
            err_oracle += abs(oracle - actual)
            paired.append(ed - ec)
            n += 1
    if not n:
        return {"n": 0, "players": players}
    mae_d, mae_c = err_direct / n, err_decomp / n
    mean = sum(paired) / n
    var = sum((d - mean) ** 2 for d in paired) / n
    se = math.sqrt(var / n) if var > 0 else 0.0
    return {"n": n, "players": players, "mae_direct": mae_d,
            "mae_decomposed": mae_c, "mae_oracle": err_oracle / n,
            "gain": mae_d - mae_c, "headroom": mae_d - err_oracle / n,
            "se": se, "z": (mean / se) if se else 0.0}


def stability(starts: dict) -> dict:
    """How much of the variance in the total is rate, and how much length?

    The reason to expect the decomposition to help, stated as a number: if
    length swings far more than rate does, projecting the product hides a
    volatile term inside a stable-looking one.
    """
    cv_rate, cv_len, cv_tot = [], [], []
    for _p, series in starts.items():
        u = [(v, o) for _pp, v, o in series if o >= MIN_OUTS]
        if len(u) < 6:
            continue
        for name, vals in (("rate", [v / o for v, o in u]),
                           ("len", [o for _v, o in u]),
                           ("tot", [v for v, _o in u])):
            m = sum(vals) / len(vals)
            if m <= 0:
                continue
            sd = math.sqrt(sum((x - m) ** 2 for x in vals) / len(vals))
            {"rate": cv_rate, "len": cv_len, "tot": cv_tot}[name].append(sd / m)
    avg = lambda xs: (sum(xs) / len(xs)) if xs else None    # noqa: E731
    return {"rate": avg(cv_rate), "length": avg(cv_len),
            "total": avg(cv_tot), "pitchers": len(cv_rate)}


def report(starts: dict, market: str, min_history: int = MIN_HISTORY) -> int:
    if not starts:
        print("No pitcher starts found with both the stat and its outs.")
        print("Ingest has to carry the 'outs' market for the same games.")
        return 0

    s = stability(starts)
    print("=" * 74)
    print("WHERE THE VARIANCE LIVES")
    print("=" * 74)
    if s["pitchers"]:
        print(f"  across {s['pitchers']} pitchers with 6+ starts, "
              f"coefficient of variation:")
        print(f"    {market} per out   {s['rate']:.1%}   ← stuff")
        print(f"    outs recorded      {s['length']:.1%}   ← the manager")
        print(f"    {market} total     {s['total']:.1%}   ← what we project")
        print()
        if s["length"] > s["rate"]:
            print("  Length swings more than rate does. Projecting the product")
            print("  puts the volatile term inside the stable-looking one.")
        else:
            print("  Rate swings at least as much as length here, which is an")
            print("  argument AGAINST bothering to separate them.")
    else:
        print("  Not enough pitchers with 6+ starts to say.")

    w = walk(starts, min_history)
    print()
    print("=" * 74)
    print("WALK-FORWARD — same blend, same games, estimated apart or together")
    print("=" * 74)
    if not w["n"]:
        print(f"  Nothing scoreable: {w['players']} pitcher(s) cleared the "
              f"{min_history}-start floor.")
        return 0
    print(f"  {w['n']:,} starts scored across {w['players']} pitchers")
    print(f"    direct      (blend of totals)        MAE {w['mae_direct']:.3f}")
    print(f"    decomposed  (rate blend × length)    MAE {w['mae_decomposed']:.3f}")
    print(f"    difference  {w['gain']:+.3f}   z {w['z']:+.2f}")
    print()
    print(f"    ORACLE      (rate blend × the length it ACTUALLY ran)")
    print(f"                                         MAE {w['mae_oracle']:.3f}")
    print(f"    headroom    {w['headroom']:+.3f}  ← the most any leash model")
    print(f"                could ever buy, since it is what a PERFECT")
    print(f"                length prediction is worth on these starts")
    print()
    if w["headroom"] < 0.05:
        print("  ⚠  The oracle barely beats projecting the total. Predicting")
        print("     length better cannot pay for itself here whatever the")
        print("     story sounds like — the error is in the RATE, not the")
        print("     leash, and a bullpen model would be work spent on the")
        print("     wrong half.")
    else:
        print(f"  The oracle is {w['headroom']:.3f} MAE better than what ships,")
        print("  so length prediction is where the money is IF it can be")
        print("  predicted at all. Decomposing on past length alone captures")
        print(f"  {(w['gain'] / w['headroom'] * 100) if w['headroom'] else 0:.0f}%"
              f" of that.")
    print()
    if w["z"] > 2:
        print("  → DECOMPOSING WINS, and the record can show it. Projecting")
        print(f"    {market} as rate × expected length beats projecting the")
        print("    total on the same games with the same blend.")
        print()
        print("    That is a projection change, not a gate change: it moves")
        print("    every pitcher number on the board. Worth building; worth")
        print("    building deliberately.")
    elif w["z"] < -2:
        print("  → DECOMPOSING LOSES. The total is the better thing to")
        print("    project, and the two-part story — however sensible it")
        print("    sounds — does not survive its own walk-forward.")
    else:
        print("  → NO DIFFERENCE THE RECORD CAN SEE. Both methods land within")
        print("    each other's error on these starts. The mechanism may")
        print("    still be real; this sample cannot pay for the rewrite.")
    return 0


def main(argv: list) -> int:
    p = argparse.ArgumentParser(
        description="Total, or rate × length? Ask the game logs.")
    p.add_argument("--from-db", dest="db", default="data/history.db")
    p.add_argument("--market", default="strikeouts",
                   help="the stat to decompose (default strikeouts)")
    p.add_argument("--min-history", type=int, default=MIN_HISTORY)
    a = p.parse_args(argv)
    from engine import db
    conn = db.connect(a.db)
    return report(load_starts(conn, a.market), a.market, a.min_history)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
