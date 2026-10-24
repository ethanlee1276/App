"""A record too young to judge reads in one screen, not fourteen panels.

Audit 2026-09-30, V-22 / V-5 (roadmap #38). At one settled bet the Record
page drew two ribbons, the calendar, four Most Likely tiles, six verdict
cells, books, splits and the settled list — 3,700 px to say "1-0, too
early". Under `min_graded` the page now shows the calendar, the verdict,
a "this month" card and the settled list, and folds the rest behind three
summaries that say why. A window chip the record cannot fill yet is shown
greyed with the reason instead of silently missing, and the settled list
never reads as fewer bets than the verdict.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 3]


STUBS = """
const MINUS = '\\u2212';
const escapeHtml = (s) => String(s); const escapeAttr = (s) => String(s);
const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;
const fmtRoi = (x) => `${x >= 0 ? '+' : '\\u2212'}${Math.abs(x * 100).toFixed(1)}%`;
const panelEmpty = (t) => `<p class="empty">${t}</p>`;
const recSettledRow = (r) => `<div class="row">${r.player}</div>`;
const icon = () => '';
let _recAllPicks = false;
let _recRange = 'all';
"""


def _run(expr):
    js = (STUBS + "".join(_fn(n) for n in ("recRanges", "recRangesFor", "recRangesClosed",
                                           "recordWindowHTML", "recMonthCard", "recRecentSection"))
          + f"\nconsole.log(JSON.stringify({expr}));")
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_month_card_says_this_month_in_one_card():
    src = {"curve": [{"date": "2026-08-30", "w": 3, "l": 1, "n": 4, "staked": 4, "day_u": 1.5},
                     {"date": "2026-09-02", "w": 1, "l": 0, "n": 1, "staked": 1, "day_u": 0.91},
                     {"date": "2026-09-20", "w": 0, "l": 1, "n": 1, "staked": 1, "day_u": -1}],
           "overall": {"clv_n": 12, "avg_clv": 0.42},
           "calibration": {"brier_model": 0.2391, "brier_market": 0.2402,
                           "buckets": [{"predicted": 0.6, "actual": 0.5, "n": 10}]}}
    html = _run(f"recMonthCard({json.dumps(src)}, 'NFL')")
    assert "September, NFL" in html
    assert ">1-1<" in html and "2 settled bets" in html, "September only — August is not this month"
    assert "−0.09u" in html and "ROI −4.5%" in html
    assert "+0.42" in html and "on 12 bets, whole record" in html
    assert "60% → 50%" in html and "0.239" in html and "market 0.240" in html
    assert _run("recMonthCard({curve: []}, 'NFL')") == ""


def test_a_window_the_record_cannot_fill_is_greyed_with_the_reason():
    curve = [{"date": "2026-09-10"}, {"date": "2026-09-20"}]
    got = _run(f"recordWindowHTML(recRangesFor({json.dumps(curve)}), 'all', recRangesClosed({json.dumps(curve)}))")
    assert re.findall(r'data-win="([^"]+)"', got) == ["all", "1w"], "the open chips still work"
    assert got.count("rec-win off") == 2 and got.count('aria-disabled="true"') == 2
    assert "The record covers 10 days so far — a 30-day window would be the whole record." in got
    one = _run("recordWindowHTML(recRangesFor([]), 'all', recRangesClosed([]))")
    assert "Not enough settled days for a window yet." in one


def test_the_settled_list_never_counts_below_the_verdict():
    html = _run("recRecentSection([], 1)")
    assert "Nothing settled yet" not in html and "1 settled bet" in html
    assert "Nothing settled yet" in _run("recRecentSection([], 0)")


def test_under_the_floor_the_rest_folds_behind_three_summaries():
    i = APP.index("  const receipts = calendar\n")
    body = APP[i:APP.index("\n  `;", i)]
    assert body.count("foldOpen(") == 3 and body.count("foldClose") == 3
    assert "+ verdict + ridingNote + unstaked + small + monthCard" in body
    assert body.index("${foldClose}\n    ${recRecentSection(") < body.index("recRecentSection(") + 1
    assert "const underFloor = (o.settled || 0) < recNeed;" in APP
    assert 'const foldOpen = (what) => !underFloor ? "" :' in APP
    assert "recordWindowHTML(avail, rk, recRangesClosed(src.curve))" in APP


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
