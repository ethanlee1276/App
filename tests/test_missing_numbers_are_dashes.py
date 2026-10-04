"""A number the engine did not compute prints as a dash, never as a claim.

Audit 2026-09-30, P1-9 / P1-10 / V-6 / V-7 (roadmap #8):

  * `roi || 0` printed "+0.0% ROI" in the positive colour where the engine
    had refused to compute one; `model_prob || 0` printed "0%" and "hits
    about 1 in 10"; a missing edge printed "+undefined pts";
  * `whyNotStaked` said "Graded 71/100 — under the 70 a pick needs";
  * the hero said "Real data. Real edges. Real results." under the demo
    banner — a results promise the site otherwise refuses to make;
  * the Health tab said it scored "your" action; it scores our picks;
  * "Avg edge" was green whatever its sign.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
APP = (ROOT / "web" / "js" / "app.js").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def _node(body, expr):
    if not shutil.which("node"):
        return None
    p = os.path.join(tempfile.mkdtemp(), "h.js")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("const MINUS='\\u2212';const trueMinus=(s)=>String(s).replace(/^-/, MINUS);\n"
                 + body + f"\nprocess.stdout.write(JSON.stringify({expr}));")
    out = subprocess.run(["node", p], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-500:]
    return json.loads(out.stdout)


def test_a_missing_roi_is_a_dash():
    i = APP.index("const signedPct = ")
    got = _node(APP[i:APP.index("\n", i)] + "\n" + _fn("fmtRoi"), "[fmtRoi(null), fmtRoi(undefined), fmtRoi(0), fmtRoi(0.051), fmtRoi(-0.12), fmtRoi('x')]")
    if got is None:
        return
    assert got[0] == "—" and got[1] == "—" and got[5] == "—"
    assert got[2] == "+0.0%" and got[3] == "+5.1%" and got[4] == "−12.0%"


def test_no_roi_is_read_as_zero_on_the_page():
    left = re.findall(r"\broi \|\| 0\b", APP)
    assert not left, f"{len(left)} site(s) still print a missing ROI as +0.0%"


def test_a_missing_probability_never_prints_as_a_number():
    assert "Number(r.model_prob || 0) * 100).toFixed(0)" not in APP
    assert "Math.round(Number(r.model_prob || 0) * 10)" not in APP
    assert "our model said ${Math.round(Number(r.model_prob || 0) * 100)}%" not in APP


def test_a_missing_edge_never_prints_undefined():
    assert '${(r.edge || 0) >= 0 ? "+" : ""}${r.edge} pts' not in APP


def test_the_grade_sentence_is_true_when_it_prints():
    body = _fn("whyNotStaked")
    got = _node(body, "[whyNotStaked({quality: 71}), whyNotStaked({quality: 64}), whyNotStaked({})]")
    if got is None:
        return
    assert "under the 70" not in got[0], got[0]
    assert "64/100" in got[1] and "under the 70" in got[1]


def test_the_hero_makes_no_results_promise():
    assert "Real data. Real edges. Real results." not in APP
    assert "Journaled at the price we found. Graded in public." in APP


def test_the_health_tab_says_whose_picks_it_scores():
    assert "limit-prone your action" not in APP and "whether this account survives being right" not in APP
    assert "our picks" in _fn("recHealthSection")
    led = (ROOT / "engine" / "ledger.py").read_text()
    assert "Inferred from your own journaled" not in led


def test_the_average_edge_is_coloured_by_its_sign():
    assert 'pre: avgEdge >= 0 ? "+" : "", cls: "pos" }' not in APP
    assert 'cls: avgEdge >= 0 ? "pos" : "neg"' in APP


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
