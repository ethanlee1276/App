"""A Most Likely card prints the model's number beside the tier's real rate.

Audit 2026-09-30, V-10 (roadmap #12): where the ring shows the tier's
measured hit rate, the model's own probability lived only in a tooltip.
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def test_both_numbers_print_when_the_tier_rate_leads():
    if not shutil.which("node"):
        return
    p = os.path.join(tempfile.mkdtemp(), "b.js")
    Path(p).write_text(_fn("obBothHTML") + "\nprocess.stdout.write(JSON.stringify(["
                       "obBothHTML({model_prob:0.59,tier_rate:0.48,tier_n:210}),"
                       "obBothHTML({model_prob:0.59}), obBothHTML({tier_rate:0.48})]));")
    out = subprocess.run(["node", p], capture_output=True, text=True, timeout=60)
    got = json.loads(out.stdout)
    assert "model 59% · tier hits 48% (n=210)" in got[0]
    assert got[1] == "" and got[2] == ""


def test_the_card_places_it_under_the_ring():
    assert "</span>${obBothHTML(r)}</span>" in APP


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
