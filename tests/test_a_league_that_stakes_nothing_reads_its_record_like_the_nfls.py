"""A league that stakes nothing yet reads its Record like the NFL's (step ABN, 22 November 2026).

Ethan, the Sunday morning: "the record pages to match each other. Not numbers wise but visual wise ... NFL is kind
of like the one we want to go off of." Hockey and college basketball stake nothing yet (their edge picks wait on
paper; their Most Likely picks are tracked for their hit rate), so their Record leads with the Most Likely record,
each pick once: hockey's tile read 1958-1024 over 2,982 graded picks. Everything under it read the empty staked
record instead: the 90, 30 and 7-day windows sat greyed, "Not enough settled days for a window yet"; the verdict
read "0-0-0 ... Too early to call. 0 graded picks against the 30"; the running P&L, the books and the splits sat
folded, "too early to read (0 of the 30 settled bets the record needs)"; and the running P&L drew nothing. What
these hold:

  * such a league's window and running P&L read the pooled journal's days, which are that record's own
    (`recPageCurve`), and a window's ribbon says whose record it is;
  * its verdict reads that record, its claimed and landed off the Most Likely book's own bands;
  * its floor is that record's count, so a league past it unfolds as the NFL's does, and one under it says its
    real count;
  * a league with a staked record reads as it did.

    python3 tests/test_a_league_that_stakes_nothing_reads_its_record_like_the_nfls.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from _app import app_js  # noqa: E402

APP = app_js()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 3]


STUBS = """
const MINUS = '\\u2212';
const escapeHtml = (s) => String(s); const escapeAttr = (s) => String(s);
const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;
const icon = () => '';
const trueMinus = (s) => String(s);
const signedPct = (x) => `${x >= 0 ? "+" : ""}${(x * 100).toFixed(1)}%`;
let _recRange = 'all';
"""
FNS = ("sameTally", "fmtRoi", "recRanges", "recRangesFor", "recRangesClosed", "recordWindowHTML", "recRangeKey",
       "recRangeFrom", "recRangeTotals", "recPageCurve", "recLikelyBuckets", "reliabilityDiagram", "moneySplitHTML",
       "combinedLineHTML", "verdictBooksHTML", "recordVerdictHTML")


def _run(expr):
    if not shutil.which("node"):
        return None
    js = STUBS + "".join(_fn(n) for n in FNS) + f"\nconsole.log(JSON.stringify({expr}));"
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _days(start_day, n, per=80):
    out, cum = [], 0.0
    for i in range(n):
        cum += 0.05
        out.append({"date": f"2026-10-{start_day + i:02d}" if start_day + i <= 31 else f"2026-11-{start_day + i - 31:02d}",
                    "day_u": 0.05, "cum_u": round(cum, 2), "n": per, "w": 53, "l": 27, "staked": per * 0.1})
    return out


LIKELY = {"settled": 2982, "wins": 1958, "losses": 1024, "pushes": 0, "win_rate": 0.6566, "breakeven": 0.6536,
          "units_staked": 298.2, "net_units": 2.11, "roi": 0.0071, "money_bets": 0, "paper_bets": 2982,
          "avg_price": -189, "returned_units": 300.31, "best_streak": 17, "open": 49, "avg_clv": 0.25, "clv_n": 2982}
EMPTY = {"settled": 0, "wins": 0, "losses": 0, "pushes": 0, "win_rate": 0.0, "units_staked": 0, "net_units": 0,
         "roi": 0.0, "money_bets": 0, "paper_bets": 0, "best_streak": 0}
HOCKEY = {"overall": EMPTY, "curve": [], "recent": [], "likely_overall": LIKELY, "pooled_overall": LIKELY,
          "edge": {"overall": EMPTY}, "edge_board": EMPTY, "min_graded": 30,
          "pooled": {"overall": LIKELY, "likely": LIKELY, "edge": EMPTY, "curve": _days(13, 40)}}
LK = {"settled": 2737, "verdict": "We said 64%, they hit 66% over 2737 settled.",
      "bands": [{"lo": 0.45, "hi": 0.6, "n": 685, "claimed": 0.5748, "actual": 0.6175},
                {"lo": 0.6, "hi": 0.75, "n": 2045, "claimed": 0.6643, "actual": 0.668}]}


def test_its_window_and_running_pnl_read_the_record_it_leads_with():
    got = _run(f"(() => {{ const pc = recPageCurve({json.dumps(HOCKEY)});"
               " return [pc.likely, pc.curve.length, pc.o.settled,"
               " recordWindowHTML(recRangesFor(pc.curve), 'all', recRangesClosed(pc.curve))]; })()")
    if got is None:
        print("  SKIP node not installed"); return
    likely, n, settled, bar = got
    assert likely and n == 40 and settled == 2982
    assert 'data-win="30d"' in bar or "30 days" in bar, bar
    assert "Not enough settled days" not in bar
    assert "a 90-day window would be the whole record" in bar, bar
    # The windowed totals are that record's own days.
    tot = _run(f"recRangeTotals({json.dumps(HOCKEY['pooled']['curve'])}, '2026-11-15')")
    assert tot and tot["settled"] == 7 * 80 and tot["wins"] == 7 * 53, tot


def test_a_league_with_a_staked_record_or_another_book_in_its_pool_reads_as_it_did():
    nfl = dict(HOCKEY, overall=dict(LIKELY, settled=571, rule="v4"), curve=_days(1, 20))
    got = _run(f"[recPageCurve({json.dumps(nfl)}).likely, recPageCurve({json.dumps(nfl)}).curve.length]")
    if got is None:
        return
    assert got == [False, 20]
    mixed = json.loads(json.dumps(HOCKEY))
    mixed["pooled"]["overall"] = dict(LIKELY, wins=1990, settled=3010)        # edge rows in the pool too
    assert _run(f"recPageCurve({json.dumps(mixed)}).likely") is False
    assert _run(f"recPageCurve({json.dumps(dict(HOCKEY, likely_overall=EMPTY))}).likely") is False


def test_its_verdict_reads_that_record():
    src = dict(HOCKEY, overall=LIKELY)
    html = _run(f"recordVerdictHTML({json.dumps(src)}, 'Hockey', {json.dumps(LK)},"
                " { likelyLed: true, likelySaid: true, combinedShown: true })")
    if html is None:
        return
    assert "1958‑1024‑0" in html and "49 open · 2982 settled" in html, html[:600]
    assert "Too early to call" not in html
    assert "its Most Likely picks, each counted once (none staked here yet)" in html
    assert "the Most Likely list’s chance, 2730 graded" in html and "how often those picks hit" in html
    assert "<svg" in html, "its picture, off the Most Likely bands"
    assert "Edge bets" not in html, "no empty edge book beside it"
    # The staked leagues' verdict is as it was.
    old = _run(f"recordVerdictHTML({json.dumps(HOCKEY)}, 'Hockey', {json.dumps(LK)}, {{}})")
    assert "Too early to call" in old and "0‑0‑0" in old


def test_the_page_reads_one_record_for_its_window_floor_verdict_pnl_and_splits():
    i = APP.index("async function renderRecord(")
    page = APP[i:APP.index("\n}\n", i)]
    assert "const pc = recPageCurve(src);" in page
    assert page.index("const pc = recPageCurve(src);") < page.index("const winAvail = recRangesFor(pc.curve)")
    for s in ("const underFloor = (pc.o.settled || 0) < recNeed;",
              "to read (${pc.o.settled || 0} of the ${recNeed} settled bets the record needs)",
              "${recAnalytics(pc.curve, pc.o, ((d.model_eras || {}).eras) || [])}",
              "${recSplitsSection(pc.o, !!scoped)}",
              "const avail = recRangesFor(pc.curve);",
              "const winO = from ? recRangeTotals(pc.curve, from) : null;",
              "const winBar = recordWindowHTML(avail, rk, recRangesClosed(pc.curve));",
              'pc.likely ? "Most Likely · every pick once"',
              "recordVerdictHTML(pc.likely ? { ...src, overall: pc.o } : src,",
              "likelyLed: pc.likely });"):
        assert s in page, s
    assert "src.curve" not in page[:page.index("const calCurve")], "the calendar keeps its own books"


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    fails = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as exc:                              # noqa: BLE001
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed.")
    sys.exit(1 if fails else 0)
