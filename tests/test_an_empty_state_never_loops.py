"""Empty states: a door never opens onto another empty page, one empty
state speaks per view, the demo banner folds to a line, and a single
sentence is never folded mid-word.

Audit 2026-09-30, V-17 and remove/merge #2 (roadmap #48). Every empty
view ended in the same Tonight / Live / Record trio (twice on Edge); on an
empty night "Tonight's picks" led to Tonight saying the same sentence; the
demo banner (~110px) had no way to put it away; and the two-line clamp cut
an empty state's only sentence mid-word. These run the shipped functions.
"""

import json
import os
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


def _const(name):
    i = APP.index(f"const {name} = ")
    return APP[i:APP.index(";\n", i) + 2]


def _node(body):
    node = shutil.which("node")
    if not node:
        return None
    prog = "\n".join([
        "let state = { data: null };",
        "let _tonight = { n: 0, shots: [], ml: [] };",
        "function tonightPick() { return _tonight; }",
        _const("EMPTY_DOORS"), _fn("emptyDoorOpen"), _fn("boardEmptyDoors"), body])
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        r = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_doors_skip_pages_that_are_empty_too():
    got = _node("""
      const out = {};
      state.data = { games: [{ live: { state: "scheduled" } }] };
      out.quiet = boardEmptyDoors("edge");
      _tonight = { n: 3, shots: [], ml: [] };
      state.data = { games: [{ live: { state: "in" } }] };
      out.busy = boardEmptyDoors("edge");
      state.data = null; out.unknown = boardEmptyDoors("edge");
      console.log(JSON.stringify(out));""")
    if got is None:
        print("  SKIP node not installed"); return
    assert 'data-es-view="tonight"' not in got["quiet"] and 'data-es-view="live"' not in got["quiet"]
    assert 'data-es-tool="record"' in got["quiet"], "the record is never empty"
    assert 'data-es-view="tonight"' in got["busy"] and 'data-es-view="live"' in got["busy"]
    assert got["unknown"].count('class="btn es-door"') == 3, "an unloaded board is not an empty one"


def test_one_empty_state_speaks_per_view():
    body = _fn("enhanceEmpties")
    assert 'const first = view && view.querySelector(".empty-slate");' in body
    assert 'if (first && first !== es) { es.classList.add("es-also"); return; }' in body
    assert body.index("es-also") < body.index("boardEmptyDoors(key)"), "a second state never gets doors"
    assert ".empty-slate.es-also > :not(.es-title):not(h3) { display: none; }" in CSS


def test_the_demo_banner_folds_to_a_line_that_still_says_demo():
    body = _fn("slateNoticeHTML")
    assert "function slateNoticeHTML(n, compact)" in body
    i = body.index("compact) {")
    chip = body[i:body.index('if (n.kind === "demo") {', i)]
    assert "Demo board." in chip and "not today’s slate" in chip and "nothing here is a pick" in chip
    assert 'data-act="demoAck">Got it</button>' in body
    assert "slateNoticeHTML(notice, demoAcked())" in APP
    assert 'sessionStorage.setItem(DEMO_ACK_KEY, "1")' in APP, "for the session, not forever"


def test_a_single_sentence_is_never_folded():
    body = _fn("enhanceNotes")
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed"); return
    test = """
      const one = (text) => !/[.!?](\\s|$)/.test(text.replace(/[.!?]["’”)]*\\s*$/, ""));
      console.log(JSON.stringify([
        one("Nothing cleared the bar tonight because every market tonight missed the tier's edge bar, failed a gate or graded below seventy and the board below names each."),
        one("Nothing cleared the bar tonight. The board below names each one, and why it was held.")]));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(test); path = fh.name
    try:
        r = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert json.loads(r.stdout) == [True, False]
    assert '.replace(/[.!?]["’”)]*\\s*$/, ""))) return;' in body


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
