"""The walkthrough's "Never show again", and never over the paywall.

Ethan, 2026-09-05: "The 3 things that we show on the website first that
tells new people what's what, we should put a 'never show again' button,
and also don't show it on the paywall screen."

Every card carries the button. It, or finishing the three cards, is
what remembers "done" for good; ×, the backdrop and Escape are "not
now" — away for the rest of the visit, back on the next one. The tour
never opens over the paywall, sign-up or checkout views: pending, it is
cancelled; open, it is taken down without deciding anything. The
decision runs for real in node (skipped without it).

Run directly: `python3 tests/test_tour_never.py`
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ", "\n(function")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return APP[i:min(ends)]


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""
      {_fn("tourDue")}
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


def test_it_never_opens_on_the_wall_and_not_now_holds_for_the_visit():
    got = _node("""
      const base = { stored: "", hash: "", isStatic: false, view: "recommended",
                     standalone: ["about"], wall: ["paywall", "signup", "checkout"] };
      const d = (o) => tourDue({ ...base, ...o });
      return { plain: d({}), paywall: d({ view: "paywall" }), signup: d({ view: "signup" }),
               checkout: d({ view: "checkout" }), later: d({ stored: "later" }),
               done: d({ stored: "done" }), noWallList: d({ view: "paywall", wall: undefined }) };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["plain"] is True
    for k in ("paywall", "signup", "checkout", "later", "done"):
        assert got[k] is False, k
    assert got["noWallList"] is True, "the list is the caller's; the function adds no view of its own"


def test_every_card_carries_never_show_again_and_only_it_or_done_remembers():
    op = _fn("tourOpen")
    assert '<button type="button" class="tour-never">Never show again</button>' in op
    assert op.index('class="tour-never"') > op.index('class="tour-nav"'), "under the Back/Next row, on every step"
    assert 'ov.querySelector(".tour-never").addEventListener("click", () => tourClose(true));' in op
    assert 'if (done) done.addEventListener("click", () => tourClose(true));' in op
    assert 'if (e.target === ov || e.target.closest(".tour-close")) tourClose(false);' in op
    assert 'if (e.key === "Escape") tourClose(false);' in _fn("tourKey")
    cl = _fn("tourClose")
    assert cl.startswith("function tourClose(forever) {\n  tourHide();")
    assert 'if (forever) {\n    try { localStorage.setItem(TOUR_KEY, "done"); }' in cl
    assert 'else {\n    try { sessionStorage.setItem(TOUR_KEY, "later"); }' in cl
    mb = _fn("tourMaybe")
    assert 'if (stored !== "done" && sessionStorage.getItem(TOUR_KEY) === "later") stored = "later";' in mb
    assert "wall: NO_TOUR_VIEWS" in mb
    assert 'const NO_TOUR_VIEWS = ["paywall", "signup", "checkout"];' in APP


def test_the_wall_cancels_a_pending_tour_and_takes_an_open_one_down():
    mb = _fn("tourMaybe")
    assert "if (!NO_TOUR_VIEWS.includes(state.view)) tourOpen(0);" in mb, "checked when the timer fires, not when it was set"
    assert "clearTimeout(_tourTimer);" in mb
    hd = _fn("tourHide")
    assert "clearTimeout(_tourTimer);" in hd and "ov.remove();" in hd and "lockScroll(false);" in hd
    assert "localStorage" not in hd and "sessionStorage" not in hd, "taking it down decides nothing"
    sw = _fn("_switchViewNow")
    assert 'if (wallBlocked(name)) { name = "paywall"; dir = 0; }\n  if (NO_TOUR_VIEWS.includes(name) && typeof tourHide === "function") tourHide();' in sw
    assert ".tour-never {" in CSS and ".tour-never:hover, .tour-never:focus-visible" in CSS


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
