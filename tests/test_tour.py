"""The first-visit walkthrough: three cards, once, never on a deep link.

Ethan, 2026-09-05: "a first visit walk through". What a pick card is,
what RIDING means, why the Record keeps two books. Shown once per
viewer on a plain landing, never to someone who arrived at a pick or a
game by link, never on a static host; the account page's Settings can
show it again. The decision runs for real in node (skipped without it).
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
      {_fn("tourSteps")}
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


def test_three_cards_say_the_three_things():
    got = _node("return tourSteps();")
    if got is None:
        print("  SKIP node not installed"); return
    assert len(got) == 3
    assert [s["title"] for s in got] == ["A pick card is one bet", "RIDING means we already hold it", "Two books, kept apart"]
    assert "70 or better" in got[0]["body"] and "edge" in got[0]["body"]
    assert "earlier pull" in got[1]["body"] and "Don’t add more" in got[1]["body"]
    assert "separate books" in got[2]["body"] and "only ones we stake" in got[2]["body"]
    for s in got:
        assert s["icon"] and 120 < len(s["body"]) < 420, "a card, not an essay"


def test_it_shows_once_on_a_plain_landing_and_never_on_a_deep_link():
    got = _node("""
      const base = { stored: "", hash: "", isStatic: false, view: "recommended", standalone: ["about", "why"] };
      const d = (o) => tourDue({ ...base, ...o });
      return {
        plain: d({}), hashOnly: d({ hash: "#" }), home: d({ hash: "#recommended" }),
        done: d({ stored: "done" }), static: d({ isStatic: true }),
        pick: d({ hash: "#pick/juan-soto-home-runs" }), game: d({ hash: "#game/2026-09-05_NE@SEA" }),
        pbp: d({ hash: "#pbp/mlb/777" }), about: d({ view: "about" }), why: d({ view: "why" }),
      };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["plain"] and got["hashOnly"] and got["home"]
    for k in ("done", "static", "pick", "game", "pbp", "about", "why"):
        assert got[k] is False, k


def test_the_dialog_is_a_dialog_that_closes_every_way_and_remembers():
    op = _fn("tourOpen")
    assert 'role="dialog" aria-modal="true"' in op
    assert 'if (e.target === ov || e.target.closest(".tour-close")) tourClose(false);' in op, "backdrop and × close it"
    assert 'document.addEventListener("keydown", tourKey);' in op and "lockScroll(true);" in op
    assert 'data-tour-step="${i - 1}">Back' in op and 'data-tour-step="${i + 1}">Next' in op
    assert 'class="btn tour-done">Done' in op
    assert "Math.max(0, Math.min(steps.length - 1, step || 0))" in op, "a step past the end is the last card"
    cl = _fn("tourClose")
    assert 'localStorage.setItem(TOUR_KEY, "done")' in cl and cl.startswith("function tourClose(forever) {\n  tourHide();")
    hd = _fn("tourHide")
    assert "lockScroll(false);" in hd and 'document.removeEventListener("keydown", tourKey);' in hd
    assert 'if (e.key === "Escape") tourClose(false);' in _fn("tourKey")
    mb = _fn("tourMaybe")
    assert "tourDue({ stored, hash: location.hash, isStatic: state.static," in mb
    assert "}, 900);" in mb and "tourOpen(0);" in mb, "after the board has drawn, not over a skeleton"


def test_it_boots_after_the_slip_and_settings_can_show_it_again():
    i = APP.index("(function initNewLook() {")
    boot = APP[i:APP.index("\n})();", i)]
    assert "slipRender();\n  tourMaybe();" in boot
    sh = _fn("settingsHTML")
    assert 'data-set-tour="1">Show me around</button>' in sh
    assert 'host.querySelectorAll("[data-set-tour]").forEach((b) =>\n    b.addEventListener("click", () => tourOpen(0)));' in APP
    for sel in ("#tour-overlay", ".tour-card", ".tour-dots i.on", ".tour-nav"):
        assert sel in CSS, sel


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
