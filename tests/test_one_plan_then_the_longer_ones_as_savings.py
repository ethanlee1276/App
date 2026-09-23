"""Audit items 11-12: one plan, then the longer ones as savings.

Ethan's product audit, 2026-09-23: "Instead of three giant equal cards:
QELLYS BOOK, $25/month, Everything included. Then: Save with longer
plans — 6 months $125, save $25; year $225, save $75 — $18.75/month
equivalent." The 6-month card wore "Most popular", which nothing
measured; the badge now goes to the cheapest plan per month and says
"Best value", which is arithmetic.
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
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def test_best_value_is_the_cheapest_month_not_a_claim():
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed"); return
    i = APP.index("const PLANS = [")
    plans = APP[i:APP.index("];", i) + 2]
    prog = plans + _fn("planPerMonth") + _fn("bestValuePlanId") + """
      console.log(JSON.stringify({ best: bestValuePlanId(PLANS),
        per: PLANS.map((p) => [p.id, planPerMonth(p).toFixed(2)]),
        swapped: bestValuePlanId([{ id: "a", price: 10, months: 1 }, { id: "b", price: 120, months: 6 }]) }));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    try:
        r = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    assert got["best"] == "yearly"
    assert got["per"] == [["monthly", "25.00"], ["sixmonth", "20.83"], ["yearly", "18.75"]]
    assert got["swapped"] == "a", "computed, not hard-wired to the yearly plan"
    assert "popular" not in plans and ">Most popular<" not in APP, "an unmeasured badge"


def test_one_card_then_the_longer_plans_as_rows():
    body = _fn("paywallHTML")
    shape = body[body.index('<div class="pw-plans" data-shape="one">'):]
    shape = shape[:shape.index("</div>\n    </div>")]
    assert '${plan(PLANS.find((p) => p.id === "monthly") || PLANS[0])}' in shape, "the one main card"
    assert '<div class="pw-longer-h">Save with a longer plan</div>' in shape
    assert '${PLANS.filter((p) => p.id !== "monthly").map(longer).join("")}' in shape
    assert "PLANS.map(plan)" not in body, "three equal cards again"
    assert '"Qellys Book"' in body and "Everything included" in body
    assert '<span class="pw-long-price">$${pl.price} · $${planPerMonth(pl).toFixed(2)} a month</span>' in body
    assert '<span class="pw-best">Best value</span>' in body
    assert "const bestId = bestValuePlanId(PLANS);" in body and "const best = pl.id === bestId;" in body, \
        "the badge is computed, never assigned"
    assert 'data-plan="${escapeAttr(pl.id)}"' in body and "coStart(this)" in body, "each row still checks out"
    assert "Card required. Becomes $${pl.price} a month on day ${" in body, "the trial terms stay on the card"
    for rule in ('.pw-plans[data-shape="one"] { max-width: 900px;', ".pw-long { display: flex;",
                 ".pw-buy.pw-buy-sm { width: auto;"):
        assert rule in CSS, rule


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
