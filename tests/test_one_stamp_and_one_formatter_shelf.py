"""Formatters and tokens: one formatStamp() that honours the Times
setting, one `fmt` shelf, spacing tokens, and the row templates' inline
styles moved to classes so the phone rules lose their !importants.

Audit 2026-09-30, V-24 / D-1 / D-2 (roadmap #50). Build times printed raw
ISO, ISO with the T swapped out, or the UTC hour sliced out of the string
— "Updated 23:41" at 7:41pm Eastern — in no zone the reader chose.
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


def test_the_stamp_reads_in_the_chosen_zone_and_says_which():
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed"); return
    prog = ("let _tz = 'America/New_York'; const settings = () => ({ tz: _tz });\n"
            + _fn("tzOpts") + _fn("formatStamp") + """
      const iso = "2026-09-30T23:41:00Z";
      const out = { ny: formatStamp(iso), nyTime: formatStamp(iso, "time") };
      _tz = "America/Los_Angeles"; out.la = formatStamp(iso, "time");
      out.bad = formatStamp(""); out.junk = formatStamp("not a date");
      out.day = formatStamp("2026-09-30");
      console.log(JSON.stringify(out));""")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    try:
        r = subprocess.run([node, path], capture_output=True, text=True, timeout=30,
                           env={**os.environ, "TZ": "UTC", "LANG": "en_US.UTF-8"})
    finally:
        os.unlink(path)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    assert "7:41" in got["nyTime"] and re.search(r"E[DS]T", got["nyTime"]), got
    assert "4:41" in got["la"] and re.search(r"P[DS]T", got["la"]), got
    assert "Sep 30" in got["ny"] and "7:41" in got["ny"]
    assert got["bad"] == "—" and got["junk"] == "—"
    assert "Sep 30" in got["day"] and "2026" in got["day"], "a bare day is that day, not the evening before"


def test_no_build_stamp_prints_raw_iso_or_the_utc_hour():
    assert "(d.generated_at || \"\").slice(11, 16)" not in APP
    assert "((d || {}).generated_at || \"\").slice(11, 16)" not in APP
    assert 'escapeHtml((d.generated_at || "").replace("T", " "))' not in APP
    assert APP.count("formatStamp(d.generated_at") >= 5


def test_one_shelf_of_formatters():
    i = APP.index("const fmt = Object.freeze({")
    shelf = APP[i:APP.index("});", i)]
    for k in ("odds", "pct", "money", "stamp", "time", "date"):
        assert re.search(rf"get {k}\(\)", shelf), k
    assert "get stamp() { return formatStamp; }" in shelf


def test_spacing_tokens_exist():
    for n, px in ((1, 4), (2, 8), (3, 12), (4, 16), (5, 24), (6, 32)):
        assert f"--sp-{n}: {px}px;" in CSS


def test_the_row_templates_use_classes_and_the_importants_are_gone():
    for name in ("renderSleeperPanel", "renderUFC"):
        body = _fn(name)
        assert 'style="flex:1' not in body, name
    assert '<span class="drow-label">' in _fn("renderSleeperPanel")
    assert '<span class="ufc-verdict ${r._pick ? "bet" : "pass"}">' in _fn("renderUFC")
    assert '[style*="flex:1"]' not in CSS and 'span[style*="text-align:right"]' not in CSS
    for sel in (".drow >", ".ufc-edge-row"):
        lines = [l for l in CSS.splitlines() if l.strip().startswith(sel)]
        assert lines and not any("!important" in l for l in lines), sel


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
