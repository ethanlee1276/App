"""The browser's resize notice never puts the apology on the page.

Ethan, 2026-10-14, with a screenshot of the banner over a Most Likely
pick: "Every time I click on a player page, for the most likely bets, it
shows this" — "Sorry — part of this page failed to draw … (ResizeObserver
loop completed with undelivered notifications.)".

That message is not a throw. The spec has the browser report it when one
frame's resize notices spill over into the next, and they are delivered
there; nothing failed to draw. The page-wide `error` listener apologised
for it because the browser delivers it as an error event with a message,
the shape of a script error. Pinned here:

  * the listener lets both wordings of the notice go (Safari's and
    today's Chrome's, and Chrome's older "limit exceeded");
  * a real throw — "ResizeObserver is not defined" included — still gets
    the apology, once, and a missing image still does not.

Run directly: `python3 tests/test_a_resize_notice_is_not_a_broken_page.py`
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")


def _listener() -> str:
    i = APP.index('addEventListener("error", (e) => {')
    return APP[i:APP.index("\n});", i) + 4]


def test_the_listener_lets_the_resize_notice_go():
    src = _listener()
    assert "!/ResizeObserver loop/.test(e.message)" in src
    assert "e.target && e.target.tagName" in src, "a missing image is still not a broken page"
    assert "crashNote(e.message)" in src


def test_only_a_real_throw_gets_the_apology():
    if not shutil.which("node"):
        return
    cases = [
        ("ResizeObserver loop completed with undelivered notifications.", None, False),
        ("ResizeObserver loop limit exceeded", None, False),
        ("TypeError: Cannot read properties of undefined (reading 'line')", None, True),
        ("ReferenceError: ResizeObserver is not defined", None, True),
        ("", "IMG", False),
        ("Script error.", "IMG", False),
    ]
    # The listener also reports a real crash to the box (engine/bugscan,
    # app.js reportCrash): a notice that is not an apology is not a report.
    prog = ("const said = [], sent = []; const crashNote = (m) => said.push(m);"
            "const reportCrash = (m) => sent.push(m); let handler = null;"
            "const addEventListener = (type, fn) => { if (type === 'error') handler = fn; };\n"
            + _listener() + "\n"
            + "const out = " + json.dumps(cases) + ".map(([message, tag]) => {"
            "  said.length = 0; sent.length = 0; handler({ message, target: tag ? { tagName: tag } : null });"
            "  return [said.length, sent.length]; });"
            "process.stdout.write(JSON.stringify(out));")
    got = subprocess.run(["node", "-e", prog], capture_output=True, text=True, timeout=30)
    assert got.returncode == 0, got.stderr
    said = json.loads(got.stdout)
    for (message, tag, want), (n, sent) in zip(cases, said):
        assert (n == 1) == want, (message, tag, n)
        assert sent == n, (message, "reported exactly when apologised for")


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
