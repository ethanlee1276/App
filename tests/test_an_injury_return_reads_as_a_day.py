"""An injury's return reads as a day (USEREYES1, 18 November 2026).

The NHL injuries page listed Zemgus Girgensons "Day-To-Day · return
2026-11-19": the feed's date as it comes, under a page that says every
other date as "Thu, Nov 19". The same date rode the injury tag's title and
the dossier's injury line. What these hold:

  * the injuries page's rows, the tag beside a name and the dossier's line
    all say "return Thu, Nov 19", through one helper (`injRet`);
  * a date the formatter cannot read is said as it came, and no date says
    nothing.

    python3 tests/test_an_injury_return_reads_as_a_day.py
"""
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 3]


def test_every_injury_line_says_the_day():
    i = APP.index("const injRet = (r) =>")
    helper = APP[i:APP.index("\n", i)]
    assert "formatGameDate(r.return_date) || r.return_date" in helper, helper
    assert "`return ${r.return_date}`" not in APP and "return ${escapeHtml(r.return_date)}" not in APP
    assert "injRet(r)" in _fn("injTag") and "injRet(r)" in _fn("injLineHTML") and "injRet(r)" in _fn("injRow")


def test_the_day_reads_as_the_site_says_dates():
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        return
    i = APP.index("const injRet = (r) =>")
    js = (_fn("formatGameDate") + APP[i:APP.index("\n", i) + 1]
          + "process.stdout.write(JSON.stringify([injRet({return_date: '2026-11-19'}), "
            "injRet({return_date: 'soon'}), injRet({})]));")
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=60,
                         env={"LANG": "en_US.UTF-8", "TZ": "America/New_York", "PATH": "/usr/bin:/bin"})
    assert out.returncode == 0, out.stderr[-800:]
    day, odd, none = json.loads(out.stdout)
    assert day == "return Thu, Nov 19", day
    assert odd == "return soon" and none == "", (odd, none)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
