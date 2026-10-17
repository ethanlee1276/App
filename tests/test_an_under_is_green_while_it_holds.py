"""An under's progress bar is green while it holds, red once it goes over.

Ethan, 2026-09-26, a live Emmett Mosley UNDER 3.5 Receptions at 1 so far
with an orange bar: "for under bets, can we show a green line instead of a
orange line since technically the bet is winning till it goes over, then
once it's over the line will go red".
"""
import json
import os
import shutil
import subprocess
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _bar_fn():
    i = APP.index("  const progressBar = (r) => {")
    return APP[i:APP.index("\n  };\n", i) + 5]


def _colors(rows):
    if not shutil.which("node"):
        return None
    prog = _bar_fn() + ("\nconst rows = %s;\nconsole.log(JSON.stringify(rows.map((r) => "
                        "(progressBar(r).match(/background:(var\\(--[a-z]+\\))/) || [])[1] || null)));" % json.dumps(rows))
    path = os.path.join(tempfile.mkdtemp(), "b.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(prog)
    return json.loads(subprocess.run(["node", path], capture_output=True, text=True, check=True).stdout)


def test_an_under_is_green_until_it_goes_over_then_red():
    got = _colors([
        {"side": "UNDER", "line": 3.5, "current": 1, "status": "live"},        # holding
        {"side": "UNDER", "line": 3.5, "current": 3, "status": "live"},        # still holding at 3
        {"side": "UNDER", "line": 3.5, "current": 4, "status": "live"},        # over, grader not yet told
        {"side": "UNDER", "line": 3.5, "current": 5, "status": "busted"},
        {"side": "UNDER", "line": 3.5, "current": 2, "status": "won_pending"},
        {"side": "UNDER", "line": 3.0, "current": 3, "status": "push_pending"},
    ])
    if got is None:
        return
    assert got == ["var(--good)", "var(--good)", "var(--bad)", "var(--bad)", "var(--good)", "var(--brand)"], got


def test_an_over_is_unchanged():
    got = _colors([
        {"side": "OVER", "line": 219.5, "current": 150, "status": "live"},     # climbing: neutral
        {"side": "OVER", "line": 2.5, "current": 3, "status": "cleared"},
        {"side": "OVER", "line": 6.5, "current": 5, "status": "lost_pending"},
    ])
    if got is None:
        return
    assert got == ["var(--brand)", "var(--good)", "var(--bad)"], got


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
