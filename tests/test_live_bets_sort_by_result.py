"""The Live page's open bets: cashed on top, running in the middle, dead
at the bottom.

Ethan, 2026-09-27, the 1pm games in the third quarter: "push all under
bets that end up going over to the bottom of the page … all bets that
have an over that hit and that are green shoot to the top. And then
everything that's still open stays in the middle."

Run directly: `python3 tests/test_live_bets_sort_by_result.py`
"""

import os
import shutil
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _band_src():
    i = JS.index("  const band = (r) =>")
    return JS[i:JS.index(";", JS.index(": 2);", i)) + 1]


def test_the_panel_sorts_its_running_list_by_band():
    i = JS.index("  const panel = (list, title, sub, empty, foot) => {")
    body = JS[i:i + 600]
    assert "active.sort((a, b) => band(a) - band(b));" in body


def test_cashed_then_running_then_upcoming_then_dead():
    if not shutil.which("node"):
        print("  SKIP node is not installed")
        return
    prog = _band_src().replace("  const band", "const band") + """
const rows = [
  {id: "under busted", status: "busted", phase: "live"},
  {id: "lawrence", status: "tracking", phase: "live"},
  {id: "aaron jones", status: "upcoming", phase: "upcoming"},
  {id: "over cleared", status: "cleared", phase: "live"},
  {id: "marks", status: "tracking", phase: "live"},
  {id: "no chances left", status: "dead", phase: "live"},
  {id: "won pending", status: "won_pending", phase: "live"},
];
const got = rows.slice().sort((a, b) => band(a) - band(b)).map((x) => x.id);
console.log(JSON.stringify(got));
"""
    out = subprocess.run(["node", "-e", prog], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-400:]
    assert out.stdout.strip() == ('["over cleared","won pending","lawrence","marks",'
                                  '"aaron jones","under busted","no chances left"]'), out.stdout


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
