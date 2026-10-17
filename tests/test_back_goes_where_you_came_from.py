"""A detail page's Back returns to the page it was opened from.

Ethan, 2026-09-28, on a pick page opened from the Most Likely page: "Back to
the board … will just take me back to the home screen. It should take me
back to the page I was previously on." The pick page and the game page
switched to Home by name; they now return to `_boardReturn` (recorded when a
detail opens from a non-detail page, with the scroll it restores) and say
which page that is. Cold landings still go Home.

Run directly: `python3 tests/test_back_goes_where_you_came_from.py`
"""
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")


def _fn(name):
    i = APP.index(f"function {name}(")
    depth, j = 0, APP.index("{", i)
    for k in range(j, len(APP)):
        depth += {"{": 1, "}": -1}.get(APP[k], 0)
        if depth == 0:
            return APP[i:k + 1]


def test_no_back_button_hard_codes_home():
    assert not re.search(r'(bk|b0|b|back)\.addEventListener\("click", \(\) => switchView\("recommended"\)\)', APP)
    assert len(re.findall(r'addEventListener\("click", detailBack\)', APP)) >= 5
    assert "← Back to the board</button>" not in APP, "the label names the page it goes back to"
    assert APP.count("${escapeHtml(detailBackLabel())}") >= 5


def test_the_return_point_is_the_page_left_for_the_detail():
    assert "if (DETAIL_VIEWS.includes(name) && !DETAIL_VIEWS.includes(leaving))\n    _boardReturn = { view: leaving, y: window.scrollY };" in APP


def test_back_names_and_goes_to_the_page():
    if not shutil.which("node"):
        print("  SKIP node is not installed")
        return
    i = APP.index("const BACK_NAMES = ")
    prog = "let _boardReturn = null; const DETAIL_VIEWS = [\"prop\", \"game\", \"pbp\"];\n" + \
        APP[i:APP.index("function detailBack() {", i)] + """
const out = [];
out.push(detailBackView(), detailBackLabel());
_boardReturn = {view: "likely", y: 900};
out.push(detailBackView(), detailBackLabel());
_boardReturn = {view: "game", y: 0};
out.push(detailBackView());
console.log(JSON.stringify(out));
"""
    got = subprocess.run(["node", "-e", prog], capture_output=True, text=True, timeout=60)
    assert got.returncode == 0, got.stderr[-400:]
    assert got.stdout.strip() == ('["recommended","← Back to the board","likely",'
                                  '"← Back to Most Likely","recommended"]'), got.stdout


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
