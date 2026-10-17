"""Dollars group their thousands everywhere a person's book is printed.

Zeno's ribbon read "$2140.00 risked" and My Bets would have read the
same once a season's stakes added up: four digits with no comma read
as a typo on a page whose job is to be trusted. Both formatters group the
same way, the count-up keeps the comma where it finds one, and a
number under a thousand is untouched.
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


def _fn(name):
    i = APP.index(f"function {name}(")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return re.sub(r"/\*.*?\*/", "", APP[i:min(ends)], flags=re.S)


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""
      const MINUS = "\\u2212";
      {_fn("zenoMoney")}
      {_fn("mbMoney")}
      {_fn("countAt")}
      console.log(JSON.stringify((() => {{ {js} }})()));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_both_money_formatters_group_and_agree():
    got = _node("""return { z: zenoMoney(2140), zneg: zenoMoney(-1234567.5), zsmall: zenoMoney(85), zzero: zenoMoney(0),
                           m: mbMoney(2140), msign: mbMoney(-2140, true), mpos: mbMoney(12000.4, true), msmall: mbMoney(999.99),
                           count: countAt("$2,140.00 risked", 0.5), end: countAt("$2,140.00 risked", 1) };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["z"] == "$2,140.00" and got["m"] == "$2,140.00", "one formatter, two books"
    assert got["zneg"] == "−$1,234,567.50" and got["msign"] == "−$2,140.00"
    assert got["mpos"] == "+$12,000.40"
    assert got["zsmall"] == "$85.00" and got["msmall"] == "$999.99" and got["zzero"] == "$0.00", "under a thousand, untouched"
    assert got["end"] == "$2,140.00 risked" and "," in got["count"], "the count-up keeps the comma"
    for name in ("zenoMoney", "mbMoney"):
        assert '.toFixed(2).replace(/\\B(?=(\\d{3})+(?!\\d))/g, ",")' in _fn(name), f"{name} lost its grouping"


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
