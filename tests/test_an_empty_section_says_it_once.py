"""v4: an empty section says it once.

On a quiet board every one of the scanner's six sections drew a head,
its sub, and a card holding one sentence saying there was nothing in
it — six heads and six boxes around nothing. Without rows a section is
one row: its name and the reason, in the empty-panel voice, no box.
With rows, nothing changes.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    return re.sub(r"^\s*//.*$", "", APP[i:APP.index("\n}\n", i)], flags=re.M)


def test_without_rows_a_section_is_one_row():
    body = _fn("scanSection")
    assert "if (!rows.length) {" in body
    # The branch ends where the full head begins; the first "}" after the
    # `if` is a template placeholder's, not the block's.
    i = body.index("if (!rows.length) {")
    empty = body[i:body.index('return `<div class="section-title">', i)]
    assert '<div class="scan-empty" title="${escapeAttr(sub)}"><b>${title}</b>' in empty, "the name, and the sub kept as its title"
    assert '<span class="panel-empty">${escapeHtml(emptyText)}</span>' in empty, "the reason, in the empty-panel voice"
    assert "section-title" not in empty and "card" not in empty, "a head and a box around nothing"


def test_with_rows_nothing_changes():
    body = _fn("scanSection")
    after = body[body.index("return `<div class=\"section-title\">"):]
    assert '<span class="sub">— ${sub}</span></div>' in after
    assert '<div class="card" style="padding:0">' in after and "rows.map(rowFn).join" in after
    assert "panelEmpty(" not in body, "the empty branch is the row now, not a panel inside a card"


def test_the_row_is_styled_without_a_box():
    i = CSS.index(".scan-empty {")
    rule = CSS[i:CSS.index("}", i)]
    assert "display: flex" in rule and "border-bottom: var(--hairline)" in rule
    assert "background" not in rule and "border-radius" not in rule
    assert ".scan-empty .panel-empty { flex: 1 1 240px; padding: 0; }" in CSS


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
