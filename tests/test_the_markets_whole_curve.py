"""The market's whole curve from the alternate ladders, and ours beside it.

Ethan, 2026-10-16: "add everything now. 1-13" — idea 2: every rung of a
ladder, priced both ways, is a point on the market's curve of "chance he
goes over this number"; laid beside our own chance at the same rungs, the
two can agree in the middle and part at the ends.

What these hold: only rungs a book prices BOTH ways are used, each
de-vigged on its own two prices, the median taken across books; the curve
is made to fall as the number rises (pool-adjacent-violators, weighted by
books); the market's middle and spread are read off where the curve
crosses 75%, 50% and 25%; a prop needs three rungs; "ends disagree" needs
the middle within 3 points and an end 6 or more apart; the ideas section
keys each curve by player and market with its game's date; the journal
keeps one row per player, market and date, the latest replacing the
earlier, and writes nothing from `ideas.build`; the score counts a prop
once (its parted rungs averaged), our side against the market's fair
chance and our log score against the market's; the bar needs 150 props;
and the pick page draws both curves and the rung table, labelled.

Run directly: `python3 tests/test_the_markets_whole_curve.py`
"""
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import altcurve as A                                 # noqa: E402
from engine import ideas as ID                                   # noqa: E402
from engine.statmath import prob_over                            # noqa: E402

LAB = ROOT / "web" / "js" / "lab.js"


def _q(book, line, o, u):
    return {"book": book, "line": line, "over_odds": o, "under_odds": u}


def _row():
    return {"player": "X", "team": "KC", "market": "rec_yds", "projection": 60.0, "proj_std": 20.0,
            "all_lines": [_q("dk", 55.5, -115, -105)],
            "alt_lines": [_q("dk", 39.5, -300, 220), _q("dk", 69.5, 150, -190), _q("fd", 69.5, 160, -200),
                          _q("dk", 89.5, 450, -700), _q("dk", 99.5, 700, None)]}


def test_two_sided_rungs_only_median_across_books_and_falling():
    mk = A.market_curve(_row()["all_lines"] + _row()["alt_lines"])
    assert [ln for ln, _p, _b in mk] == [39.5, 55.5, 69.5, 89.5], "99.5 is quoted one way only"
    assert dict((ln, b) for ln, _p, b in mk)[69.5] == 2
    dk = (100 / 250) / (100 / 250 + 190 / 290)
    fd = (100 / 260) / (100 / 260 + 200 / 300)
    assert abs(dict((ln, p) for ln, p, _b in mk)[69.5] - round((dk + fd) / 2, 4)) < 1e-4, "the median of two books"
    assert all(a[1] >= b[1] for a, b in zip(mk, mk[1:])), "the curve falls as the number rises"
    bumpy = A.market_curve([_q("a", 10.5, -150, 120), _q("a", 12.5, -200, 160), _q("a", 14.5, 200, -250)])
    assert bumpy[0][1] == bumpy[1][1], "a rise between rungs is pooled flat"
    pooled = A.decreasing([(1, 0.6, 1), (2, 0.7, 3), (3, 0.2, 1)])
    assert [ln for ln, _p in pooled] == [1, 2, 3] and abs(pooled[0][1] - 0.675) < 1e-9 and pooled[0][1] == pooled[1][1], \
        "pooled by the books behind each point"


def test_the_middle_and_spread_come_off_the_market_curve():
    curve = [(40, 0.9), (50, 0.75), (60, 0.5), (70, 0.25), (80, 0.1)]
    assert A.crossing(curve, 0.5) == 60 and A.crossing(curve, 0.75) == 50 and A.crossing(curve, 0.25) == 70
    assert A.crossing([(40, 0.4), (50, 0.3)], 0.5) is None, "rungs that do not straddle say nothing"


def test_ends_disagree_needs_an_agreeing_middle_and_a_parted_end():
    mu = lambda r, m, s, l: prob_over(l, 60, 20)                # noqa: E731
    c = A.compare(_row(), "rec_yds", prob_at=mu)
    assert len(c["rungs"]) == 4 and c["tail_line"] == 39.5 and c["tail_side"] == "over"
    assert not c["ends_disagree"], "the middle is 8 points apart here"
    mk = {ln: p for ln, p, _b in A.market_curve(_row()["all_lines"] + _row()["alt_lines"])}
    shaped = lambda r, m, s, l: mk[l] + (0.10 if l == 89.5 else 0.0)    # noqa: E731
    c2 = A.compare(_row(), "rec_yds", prob_at=shaped)
    assert c2["ends_disagree"] and c2["tail_side"] == "over" and c2["tail_line"] == 89.5
    assert abs(c2["mid_gap"]) < 1e-9
    thin = {**_row(), "alt_lines": [_q("dk", 69.5, 150, -190)]}
    assert A.compare(thin, "rec_yds", prob_at=mu) is None, "two rungs are not a curve"


def test_the_section_keys_curves_and_the_journal_keeps_one_per_day():
    real = A.compare
    A.compare = lambda row, market, quotes=None, prob_at=None: real(row, market, quotes,
                                                                   prob_at=lambda r, m, s, l: prob_over(l, 60, 20))
    try:
        sec = A.ideas_section([], [{"home": "KC", "away": "BUF", "date": "2026-10-19"}],
                              {"date": "2026-W07", "recommendations": [_row(), {"player": "Y", "market": "rec_yds"}]}, "nfl")
        bare = A.ideas_section([], [{"home": "KC", "away": "BUF", "date": "2026-10-19"}],
                               {"recommendations": [_row()]}, "nfl")
    finally:
        A.compare = real
    assert list(sec["curves"]) == ["X|rec_yds"] and sec["curves"]["X|rec_yds"]["date"] == "2026-W07", \
        "kept under the board's own settle key, the one the ledger looks results up by"
    assert bare["curves"]["X|rec_yds"]["date"] == "2026-10-19", "the game's date when the board names none"
    assert A.pick_view(sec, "X", "rec_yds")["rungs"] and A.pick_view(sec, "Z", "rec_yds") is None
    conn = sqlite3.connect(":memory:")
    assert A.journal("nfl", sec, conn=conn) == 1
    sec["curves"]["X|rec_yds"]["rungs"][0]["ours"] = 0.99
    A.journal("nfl", sec, conn=conn)
    rows = conn.execute("SELECT player, market, date, rungs FROM alt_curves").fetchall()
    assert len(rows) == 1 and json.loads(rows[0][3])[0][2] == 0.99, "the later curve replaces the earlier"
    assert ID.SECTIONS["curve"] == "altcurve"
    src = (ROOT / "engine" / "ideas.py").read_text(encoding="utf-8")
    assert "fn(sport, sec)" in src[src.index("def attach("):], "journals run from a build only"


def test_a_prop_is_scored_once_against_the_markets_fair_chance():
    rungs = [[40.5, 0.80, 0.90], [60.5, 0.50, 0.51], [80.5, 0.20, 0.10]]
    sc = A.score([(rungs, 70.0)])
    # 40.5: we lean over (0.90 vs 0.80), he went over: 1 - 0.80 = +0.20.
    # 80.5: we lean under (0.10 vs 0.20), he stayed under: 1 - 0.80 = +0.20. 60.5 is not parted.
    assert sc["excess"]["n"] == 1 and abs(sc["excess"]["mean"] - 0.20) < 1e-9
    assert sc["logscore"]["mean"] > 0
    assert A.score([([[50.5, 0.5, 0.52]], 70.0)])["excess"]["n"] == 0, "no parted rung, no prop"
    many = [(rungs, 70.0 if i % 3 else 30.0) for i in range(200)]
    v = A.verdict(A.score(many))
    assert v["excess"]["n"] == 200 and isinstance(v["holds"], bool)
    assert not A.verdict(A.score(many[:100]))["holds"], "under 150 props the bar is not met"


def test_the_pick_page_draws_both_curves_and_the_rungs():
    node = shutil.which("node")
    if not node:
        print("      (skipped: no Node)")
        return
    c = A.compare(_row(), "rec_yds", prob_at=lambda r, m, s, l: prob_over(l, 60, 20))
    slice_ = {"sections": {"curve": {**c, "verdict": {}}}}
    script = ("const vm = require('vm'); const fs = require('fs'); const ctx = { window: {} }; vm.createContext(ctx);"
              f"vm.runInContext(fs.readFileSync({json.dumps(str(LAB))}, 'utf8'), ctx); const L = ctx.window.QBLab;"
              f"process.stdout.write(JSON.stringify({{h: L.pickHTML({json.dumps(slice_)})}}));")
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1200:]
    h = json.loads(out.stdout)["h"]
    assert "The market’s whole curve" in h and 'class="lb-mk"' in h and 'class="lb-us"' in h
    assert h.count("<tr><td>Over ") == 4 and "Reading · not measured yet" in h
    assert "The market’s middle sits at" in h


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
