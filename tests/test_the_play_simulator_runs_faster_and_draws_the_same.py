"""The play simulator draws the same games, faster (engine/playsim.simulate,
_pair_corr, ideas_section).

The NFL build's readings spent 12.2 seconds in the simulator at 07:49 on 9
November. Its trials re-read the same dicts and recomputed the same
exponential on every throw, and the board section compared every leg with
every other twice, working out each leg's over flags and length again for
each partner. Now each is worked out once. What these hold:

  * every trial comes out the same to the digit as the loop it replaced
    (kept here as the reference), with the random draws in the same order;
  * a pair's correlation is `scores_corr`'s float exactly, either way round;
  * the board section's numbers are the same as one built the old way.

Run directly: `python3 tests/test_the_play_simulator_runs_faster_and_draws_the_same.py`
"""
import bisect
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import playsim as P                                   # noqa: E402


def _reference(prof, trials, rng, shocks=None):
    """`simulate` as it was before 9 November, line for line."""
    sh = {**P.DEFAULT_SHOCKS, **(shocks or {})}
    qb = prof["qb"]
    rnames, rcum = P._picker(prof["receivers"], True)
    cnames, ccum = P._picker(prof["rushers"], False)
    out: dict = {}

    def slot(p, m):
        return out.setdefault(p, {}).setdefault(m, [0.0] * trials)
    for p in prof["receivers"]:
        for m in ("targets", "receptions", "rec_yds"):
            slot(p, m)
    for p in prof["rushers"]:
        for m in ("rush_att", "rush_yds"):
            slot(p, m)
    for m in ("pass_att", "pass_cmp", "pass_yds"):
        slot(qb, m)
    kr, kq = sh["k_rec"], sh["k_rush"]
    rtop, ctop = rcum[-1], (ccum[-1] if ccum else 0.0)
    for t in range(trials):
        v, s, e = rng.gauss(0, sh["vol_sd"]), rng.gauss(0, sh["script_sd"]), rng.gauss(0, sh["eff_sd"])
        n_pass = P._count(rng, prof["pass_att"] * math.exp(v + s))
        n_rush = P._count(rng, prof["rush_att"] * math.exp(v - s))
        cmp_ = yds = 0.0
        boost = math.exp(e)
        for _ in range(n_pass):
            who = rnames[min(bisect.bisect_right(rcum, rng.random() * rtop), len(rnames) - 1)]
            if who is None:
                c, ypc = P.OTHER_CATCH, P.OTHER_YPC
            else:
                st = prof["receivers"][who]
                c, ypc = st["catch"], st["ypc"]
                out[who]["targets"][t] += 1
            c = 1.0 / (1.0 + (1.0 / c - 1.0) * math.exp(-e))
            if rng.random() < c:
                y = rng.gammavariate(kr, ypc * boost / kr)
                cmp_ += 1
                yds += y
                if who is not None:
                    out[who]["receptions"][t] += 1
                    out[who]["rec_yds"][t] += y
        out[qb]["pass_att"][t] = n_pass
        out[qb]["pass_cmp"][t] = cmp_
        out[qb]["pass_yds"][t] = yds
        if not ctop:
            continue
        for _ in range(n_rush):
            i = bisect.bisect_right(ccum, rng.random() * ctop)
            if i >= len(cnames):
                continue
            who = cnames[i]
            ypr = prof["rushers"][who]["ypr"]
            out[who]["rush_att"][t] += 1
            out[who]["rush_yds"][t] += rng.gammavariate(kq, (ypr + P.RUSH_SHIFT) / kq) - P.RUSH_SHIFT
    return out


def _profiles():
    yield {"qb": "QB", "pass_att": 34.0, "rush_att": 27.0,
           "receivers": {"WR1": {"share": 0.27, "catch": 0.66, "ypc": 12.1},
                         "WR2": {"share": 0.21, "catch": 0.62, "ypc": 13.4},
                         "TE": {"share": 0.17, "catch": 0.72, "ypc": 9.8},
                         "RB": {"share": 0.11, "catch": 0.8, "ypc": 7.4}},
           "rushers": {"RB": {"share": 0.62, "ypr": 4.4}, "RB2": {"share": 0.21, "ypr": 4.1},
                       "QB": {"share": 0.12, "ypr": 5.2}}}
    yield {"qb": "QB", "pass_att": 41.0, "rush_att": 19.0,           # a pass-heavy side, no rushers
           "receivers": {"X": {"share": 0.4, "catch": 0.6, "ypc": 14.0}}, "rushers": {}}
    yield {"qb": "QB", "pass_att": 12.0, "rush_att": 45.0,            # an option offence
           "receivers": {"A": {"share": 0.5, "catch": 0.5, "ypc": 18.0},
                         "B": {"share": 0.6, "catch": 0.55, "ypc": 15.0}},
           "rushers": {"FB": {"share": 0.5, "ypr": 4.0}, "QB": {"share": 0.5, "ypr": 5.5}}}


def test_every_trial_is_drawn_the_same_as_before():
    for i, prof in enumerate(_profiles()):
        for shocks in (None, {"vol_sd": 0.3, "script_sd": 0.2, "eff_sd": 0.25, "k_rec": 1.6}):
            want = _reference(prof, 400, random.Random(100 + i), shocks)
            got = P.simulate(prof, 400, random.Random(100 + i), shocks)
            assert got == want, (i, shocks)


def test_a_pairs_correlation_is_scores_corr_either_way_round():
    rnd = random.Random(4)
    ns = {k: P.normal_scores([rnd.gauss(0, 1) + j * rnd.random() for j in range(300)]) for k in "abcd"}
    ns["short"] = ns["a"][:10]
    norm = {k: math.sqrt(sum(x * x for x in v)) for k, v in ns.items()}
    dots: dict = {}
    for a in "abcd":
        for b in "abcd":
            if a != b:
                assert P._pair_corr(ns, norm, dots, a, b) == P.scores_corr(ns[a], ns[b]), (a, b)
    assert P._pair_corr(ns, norm, dots, "a", "short") is None


def test_the_board_section_reads_the_same_as_one_built_the_old_way():
    rnd = random.Random(2)
    rows, board = [], {"recommendations": []}
    for team, opp in (("AAA", "BBB"), ("BBB", "AAA")):
        for wk in range(1, 7):
            rows.append((2026, wk, team, f"{team} QB", "pass_att", 30 + rnd.randint(0, 10)))
            for r in range(3):
                t = rnd.randint(2, 10)
                c = min(t, rnd.randint(1, 8))
                rows += [(2026, wk, team, f"{team} WR{r}", "targets", t),
                         (2026, wk, team, f"{team} WR{r}", "receptions", c),
                         (2026, wk, team, f"{team} WR{r}", "rec_yds", c * 11.0)]
            rows += [(2026, wk, team, f"{team} RB", "rush_att", rnd.randint(8, 20)),
                     (2026, wk, team, f"{team} RB", "rush_yds", rnd.randint(30, 110))]
        for p, m, ln in ((f"{team} QB", "pass_yds", 230.5), (f"{team} WR0", "rec_yds", 55.5),
                         (f"{team} WR1", "receptions", 3.5), (f"{team} RB", "rush_yds", 62.5)):
            board["recommendations"].append({"team": team, "opponent": opp, "player": p,
                                             "market": m, "line": ln})

    class _Conn:
        def execute(self, *a, **k):
            class R:
                def fetchone(self):
                    return (2026,)
            return R()

    keep = (P.load_rows, P.simulate, P.BUILD_SECONDS, P.load)
    try:
        P.load_rows = lambda conn, sport, seasons=None, teams=None: [r for r in rows if not teams or r[2] in teams]
        P.load = lambda: {}
        P.BUILD_SECONDS = 10_000
        new = P.ideas_section(None, None, board, "nfl", conn=_Conn())
        P.simulate = _reference
        old = P.ideas_section(None, None, board, "nfl", conn=_Conn())
    finally:
        P.load_rows, P.simulate, P.BUILD_SECONDS, P.load = keep
    assert new["players"] and new == old


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
