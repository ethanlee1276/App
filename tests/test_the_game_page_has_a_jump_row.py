"""The game page carries a chip row that jumps to each of its sections.

Every book's event page segments its markets (Popular / Game lines /
Player props). Ours is one long page, and stays one — the research
brief was ease of use "without losing information" — so the segments
are a row of chips under the hero that scroll to a section, drawn only
for sections the page actually has. One section, no row. It stays under
the hero (Ethan, 2026-09-23: "fix how this bar follows the page when you
scroll down") — it used to be sticky.
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
VIS = (ROOT / "web" / "js" / "visuals.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _strip(src):
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


def _fn(name):
    i = APP.index(f"function {name}(")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return _strip(APP[i:min(ends)])


def _vfn(name):
    i = VIS.index(f"function {name}(")
    return VIS[i:VIS.index("\n}\n", i) + 3]


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""
      {_fn("escapeHtml")}
      {_vfn("escapeAttr")}
      {_fn("gpJumpHTML")}
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


def test_only_sections_the_page_drew_get_a_chip_and_one_section_gets_no_row():
    got = _node("""
      const full = gpJumpHTML([["gp-sec-lines", "Lines & insights"], null, ["gp-sec-props", "Props · 4"], ["gp-sec-shots", "Long shots · 2"]]);
      const one = gpJumpHTML([null, ["gp-sec-props", "Props"], null]);
      const none = gpJumpHTML([]);
      return { chips: [...full.matchAll(/data-jump="([^"]+)"/g)].map((m) => m[1]),
               labels: [...full.matchAll(/>([^<]+)<\\/button>/g)].map((m) => m[1]),
               sticky: full.includes('class="std-chips gp-jump"'), one, none };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["chips"] == ["gp-sec-lines", "gp-sec-props", "gp-sec-shots"]
    assert got["labels"] == ["Lines &amp; insights", "Props · 4", "Long shots · 2"]
    assert got["sticky"]
    assert got["one"] == "" and got["none"] == ""


def test_every_section_the_row_names_exists_on_the_page_and_the_chips_scroll():
    page = _fn("renderGamePage")
    for sec in ("gp-sec-lines", "gp-sec-replay", "gp-sec-shapes", "gp-sec-likely", "gp-sec-bets", "gp-sec-props", "gp-sec-shots"):
        assert f'id="{sec}"' in page, sec
        assert f'["{sec}",' in page, f"{sec} is offered as a jump"
    assert 'simCard ? ["gp-sec-replay", "Replay"] : null' in page, "no chip for a section that did not draw"
    assert 'host.querySelectorAll(".gp-jump [data-jump]")' in page
    assert 'el.scrollIntoView({ behavior: state.quiet ? "auto" : "smooth", block: "start" });' in page
    rule = re.search(r"\.gp-jump \{([^}]*)\}", _strip(CSS)).group(1)
    assert "sticky" not in rule and "fixed" not in rule, \
        "the row stays under the hero — pinned, it rode down over every card (Ethan, 2026-09-23)"
    assert not re.search(r"\.gp-jump[^{]*\{[^}]*position:\s*(sticky|fixed)", _strip(CSS)), \
        "and no later rule pins it again"
    assert '[id^="gp-sec-"] { scroll-margin-top: calc(var(--topbar-h) + 12px); }' in CSS, \
        "a section lands just under the top bar"


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
