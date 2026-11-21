"""One odds printer: every price honours the reader's American/decimal setting.

Audit 2026-09-30, V-3 (roadmap #11). `oddsTxt` honoured the setting and
`american` — 83 call sites — did not, so a decimal reader saw both formats
on one card, and a missing price printed "null".
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


def _line(prefix):
    i = APP.index(prefix)
    return APP[i:APP.index(";\n", i) + 2]


def test_american_goes_through_the_setting():
    if not shutil.which("node"):
        return
    i = APP.index("const american = ")
    decl = APP[i:APP.index("\n", i) + 1]
    js = ("const MINUS='\\u2212';" + _line("const RE_SIGN") + _line("const trueMinus")
          + "let MODE='american';const settings=()=>({odds: MODE});\n" + _fn("oddsTxt") + decl
          + "\nconst a=[american(-110), american(150), american(null)];MODE='decimal';"
          "a.push(american(-110), american(150));process.stdout.write(JSON.stringify(a));")
    p = os.path.join(tempfile.mkdtemp(), "o.js")
    Path(p).write_text(js)
    out = subprocess.run(["node", p], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-400:]
    got = json.loads(out.stdout)
    assert got[0] == "−110" and got[1] == "+150" and got[2] == "—"
    assert got[3] == "1.91" and got[4] == "2.50", got


def test_american_is_defined_through_odds_txt():
    i = APP.index("const american = ")
    assert "oddsTxt(o)" in APP[i:i + 200]


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
