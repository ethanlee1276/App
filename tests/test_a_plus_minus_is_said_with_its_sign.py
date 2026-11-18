"""A plus-minus is said with its sign (USEREYES1, 18 November 2026).

Connor McDavid's player page carried the season's counts as small pills
(PLRPILLS1), and a +28 skater's read "28 plus-minus": a plus-minus is
written with its sign. What these hold:

  * a positive plus-minus pill reads "+28 plus-minus", a negative one
    "−5 plus-minus" with a true minus, and an even one "0 plus-minus";
  * every other count is said as before ("9 games", "91 targets").

    python3 tests/test_a_plus_minus_is_said_with_its_sign.py
"""
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLR = (ROOT / "web" / "js" / "playerpage.js").read_text(encoding="utf-8")

STUBS = r"""
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => '&#' + c.charCodeAt(0) + ';');
const escapeHtml = esc, escapeAttr = esc;
const MINUS = "−";
const RE_SIGN = /(^|[^\w])-(?=[\d.])/g;
const trueMinus = (s) => String(s).replace(RE_SIGN, `$1${MINUS}`);
"""


def _fn(src, name):
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 3]


def _pills(pm):
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        return None
    i = PLR.index("const PLR_PILL_SKIP")
    js = STUBS + PLR[i:PLR.index(";\n", i) + 2] + _fn(PLR, "plrSeasonPills")
    d = {"season": 2026, "role": "skater", "career": {
        "groups": [{"key": "skater", "cols": [{"key": "g", "label": "G", "title": "Goals"},
                                              {"key": "pm", "label": "+/-", "title": "Plus-minus"},
                                              {"key": "pim", "label": "PIM", "title": "Penalty minutes"}]}],
        "rows": [{"season": 2026, "gp": 20, "values": {"skater.g": 14, "skater.pm": pm, "skater.pim": 6}}]}}
    nums = [{"key": "g"}]
    out = subprocess.run([node, "-e", js + f"\nprocess.stdout.write(JSON.stringify(plrSeasonPills({json.dumps(d)}, "
                          f"{json.dumps(nums)})));"], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    return json.loads(out.stdout)


def test_a_plus_minus_pill_carries_its_sign():
    got = _pills(28)
    if got is None:
        return
    assert got == ('<div class="plr-pills"><span class="plr-pill">20 games</span>'
                   '<span class="plr-pill">+28 plus-minus</span>'
                   '<span class="plr-pill">6 penalty minutes</span></div>'), got
    assert '<span class="plr-pill">−5 plus-minus</span>' in _pills(-5)
    assert '<span class="plr-pill">0 plus-minus</span>' in _pills(0)


def test_the_page_signs_by_the_columns_label():
    assert 'col.label === "+/-" && Number(v) > 0 ? "+" : ""' in PLR


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
