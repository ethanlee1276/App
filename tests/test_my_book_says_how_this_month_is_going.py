"""My Book says how this month is going, with last month beside it.

Ethan's product audit, 2026-09-23, item 16: My Book as a retention
engine — "this month, best markets, biggest leak". The leak and the
sport carrying you were already takeaways (mbTakeaways), and the sport
and price tables are the best markets. "This month" was the missing
read: one line under your ribbon.
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


def _strip(src):
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


def _fn(name):
    i = APP.index(f"function {name}(")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ", "\nwindow.")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return _strip(APP[i:min(ends)])


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""
      const MINUS = "−";
      const plural = (n, w) => `${{n}} ${{w}}${{n === 1 ? "" : "s"}}`;
      {_fn("mbDecimal")}
      {_fn("mbProfit")}
      {_fn("mbStats")}
      {_fn("mbMoney")}
      {_fn("mbMonth")}
      {_fn("mbMonthName")}
      {_fn("mbMonthHTML")}
      const bet = (date, result, stake, odds) => ({{ date, result, stake, odds, book: "DK" }});
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


def test_the_month_is_the_bets_own_month_and_last_month_sits_beside_it():
    got = _node("""
      const bets = [bet("2026-09-02", "win", 100, 100), bet("2026-09-10", "loss", 50, -110),
                    bet("2026-09-20", "push", 20, -110), bet("2026-09-21", "pending", 30, 150),
                    bet("2026-08-30", "loss", 40, -110), bet("2026-07-01", "win", 999, 100)];
      const m = mbMonth(bets, "2026-09-23");
      return { ym: m.ym, prev: m.prev, cur: [m.cur.wins, m.cur.losses, m.cur.pushes, m.cur.pending, m.cur.profit, m.cur.staked],
               last: [m.last.settled, m.last.profit], html: mbMonthHTML(bets, "2026-09-23") };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert (got["ym"], got["prev"]) == ("2026-09", "2026-08")
    assert got["cur"] == [1, 1, 1, 1, 50, 170], got["cur"]
    assert got["last"] == [1, -40], "July's big win is neither month"
    h = got["html"]
    assert h.startswith('<p class="mb-month"><span class="hd-eyebrow">September</span> <b>1-1-1</b>')
    assert '<b class="good">+$50.00</b>' in h and "+29.4% ROI" in h
    assert "open bet" not in h, "the at-risk line above already says what is open"
    assert '<span class="mb-month-prev">August −$40.00</span>' in h


def test_january_looks_back_at_last_december():
    got = _node("""
      const bets = [bet("2027-01-03", "loss", 10, -110), bet("2026-12-28", "win", 10, 100)];
      const m = mbMonth(bets, "2027-01-05");
      return { prev: m.prev, html: mbMonthHTML(bets, "2027-01-05") };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["prev"] == "2026-12"
    assert "January" in got["html"] and '<b class="bad">−$10.00</b>' in got["html"] \
        and "December +$10.00" in got["html"]


def test_a_quiet_month_says_so_and_no_history_says_nothing():
    got = _node("""
      return { quiet: mbMonthHTML([bet("2026-09-21", "pending", 30, 150), bet("2026-08-02", "win", 10, 100)], "2026-09-23"),
               lastOnly: mbMonthHTML([bet("2026-08-02", "win", 10, 100)], "2026-09-23"),
               none: mbMonthHTML([], "2026-09-23"), old: mbMonthHTML([bet("2025-01-02", "win", 5, 100)], "2026-09-23") };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert "September</span> nothing settled yet<span" in got["quiet"] and "August +$10.00" in got["quiet"]
    assert "September</span> nothing settled yet" in got["lastOnly"], "a new month still names itself"
    assert got["none"] == "" and got["old"] == "", "nothing this month or last, no line"


def test_the_line_sits_under_your_ribbon():
    body = APP[APP.index("function renderMyBets("):]
    body = body[:body.index("\n}\n")]
    assert "    ${ribbon}\n    ${mbMonthHTML(bets, today)}\n" in body
    assert body.index("const today = ") < body.index("${mbMonthHTML(bets, today)}")
    assert ".mb-month { margin: -2px 0 14px;" in CSS and ".mb-month b.bad { color: var(--bad); }" in CSS


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
