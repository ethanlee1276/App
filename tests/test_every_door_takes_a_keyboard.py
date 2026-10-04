"""Accessibility floor: every clickable row is a keyboard stop, icon-only
buttons are named, control chips are 28px, the smallest type steps rise
on a phone, the Ask composer keeps a focus mark, and the light theme
clears WCAG AA on its secondary and brand text.

Audit 2026-09-30, V-21 (roadmap #49). The doors run in node over a tiny
DOM double, so the net is tested as it ships.
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


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def _const(name):
    i = APP.index(f"const {name} = ")
    return APP[i:APP.index(";\n", i) + 2]


def test_rows_get_a_stop_and_a_role_once():
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed"); return
    prog = """
      function el(tag, attrs, text) {
        const a = Object.assign({}, attrs);
        return { tag, a, dataset: {}, textContent: text || "",
          hasAttribute: (k) => k in a, getAttribute: (k) => a[k],
          setAttribute: (k, v) => { a[k] = String(v); },
          matches(sel) { return sel.split(",").some((s) => {
            s = s.trim(); if (/^[a-z]+$/.test(s)) return s === tag;
            const m = s.match(/^\\[([a-z-]+)\\]$/); return m ? m[1] in a : false; }); } };
      }
      const rows = [el("div", {"data-team-open": "KC"}), el("td", {"data-gid": "1"}),
                    el("button", {"data-open": "x"}), el("div", {"data-gs-toggle": "", "role": "tab"}),
                    el("span", {"data-prop": "p", "tabindex": "-1"})];
      const btns = [el("button", {"title": "Delete this bet"}, ""), el("button", {"title": "Copy"}, "Copy"),
                    el("button", {"title": "Bell", "aria-label": "Injuries"}, "")];
      const root = { querySelectorAll: (sel) => sel.startsWith("button[title]")
        ? btns.filter((b) => !("aria-label" in b.a))      // :not([aria-label])
        : rows };
    """ + _const("DOOR_SELECTORS") + _fn("enhanceDoors") + """
      enhanceDoors(root); enhanceDoors(root);
      console.log(JSON.stringify({ rows: rows.map((r) => [r.a.tabindex, r.a.role, r.dataset.doorKb || ""]),
                                   btns: btns.map((b) => b.a["aria-label"] || "") }));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    try:
        r = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    assert got["rows"] == [["0", "link", "1"], ["0", "link", "1"], [None, None, ""],
                           ["0", "tab", "1"], ["-1", "link", "1"]], got["rows"]
    assert got["btns"] == ["Delete this bet", "", "Injuries"], got["btns"]


def test_enter_and_space_click_the_row_unless_it_has_its_own_keys():
    i = APP.index("const DOOR_OWN_KEYS")
    block = APP[i:APP.index("function enhanceSectionSubs(", i)]
    assert 'e.target.closest("[data-door-kb]")' in block and "el.matches(DOOR_OWN_KEYS)" in block
    assert "el.click();" in block and "el !== e.target" in block, "an inner control's key is its own"
    assert "enhanceDoors(root);" in _fn("enhanceSectionSubs"), "runs on every render"
    assert _fn("doorAttrs").count('tabindex="0"') == 1


def test_chips_type_and_the_composer_ring():
    assert 'button.chip, a.chip, .chip[role="button"], .chip[tabindex] { min-height: 28px; }' in CSS
    m = re.search(r"@media \(max-width: 760px\) \{\s*:root \{ --fs-2xs: ([0-9.]+)px; --fs-xs: ([0-9.]+)px; \}", CSS)
    assert m and float(m.group(1)) >= 11 and float(m.group(2)) >= 12
    assert ".ask-form:focus-within { box-shadow: var(--glow); }" in CSS
    assert ".ask-form:focus-within { border-color: var(--gold); }" in CSS


def _lum(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _cr(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def test_the_light_theme_clears_wcag_aa_on_secondary_text():
    blocks = re.findall(r':root\[data-theme="light"\] \{(.*?)\n\}', CSS, flags=re.S)
    tokens = {}
    for b in blocks:                       # later blocks win, as in the cascade
        for k, v in re.findall(r"--([a-z0-9-]+):\s*(#[0-9A-Fa-f]{6})\b", b):
            tokens[k] = v
    for fg in ("text-mute", "brand", "warn"):
        for bg in ("bg", "panel", "panel-2", "panel-3"):
            assert _cr(tokens[fg], tokens[bg]) >= 4.5, (fg, bg, tokens[fg], tokens[bg], round(_cr(tokens[fg], tokens[bg]), 2))


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
