"""Desktop line-shopping basics: "/" searches, tables sort, the menu's
groups are legible and open, and the other books are printed.

Audit 2026-09-30, V-13 / V-14 / V-23 / O26 (roadmap #42).
"""

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()
HTML = (ROOT / "web" / "index.html").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 3]


def test_sort_keys_read_numbers_through_signs_and_units():
    js = _fn("sortKey") + """
console.log(JSON.stringify(["+1.25u", "\\u22120.40", "52.4%", "$1,200", "Josh Allen", "-110", ""].map(sortKey)));"""
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout)
    assert got[:4] == [1.25, -0.4, 52.4, 1200] and got[4] == "josh allen" and got[5] == -110


def test_a_header_click_sorts_the_rows_both_ways():
    js = ("const SORTABLE_TABLES = 'table';\n" + _fn("sortKey") + _fn("sortTableBy") + """
const rows = [["A", "+1.2u"], ["B", "\\u22120.5u"], ["C", "+3.0u"]];
const cell = (t) => ({ textContent: t });
const body = { rows: rows.map((r) => ({ cells: r.map(cell), id: r[0] })), appendChild(r) {
  this.rows = this.rows.filter((x) => x !== r).concat([r]); } };
const ths = [0, 1].map(() => ({ attrs: {}, getAttribute(k) { return this.attrs[k]; },
  setAttribute(k, v) { this.attrs[k] = v; } }));
const tr = { children: ths, querySelectorAll: () => ths };
ths.forEach((t) => { t.parentElement = tr; t.closest = () => ({ tBodies: [body] }); t.attrs["aria-sort"] = "none"; });
sortTableBy(ths[1]); const first = body.rows.map((r) => r.id).join("") + ths[1].attrs["aria-sort"];
sortTableBy(ths[1]); const second = body.rows.map((r) => r.id).join("") + ths[1].attrs["aria-sort"];
console.log(JSON.stringify([first, second]));""")
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == ["CABdescending", "BACascending"]


def test_sortable_headers_are_announced_and_reachable():
    assert 'th.setAttribute("aria-sort", "none");' in _fn("armSortable") and "th.tabIndex = 0;" in _fn("armSortable")
    assert 'const SORTABLE_TABLES = "table.log-table, table.kx-table, table.sortable";' in APP
    assert 'th[aria-sort="ascending"]::after' in CSS and "th[aria-sort]:focus-visible" in CSS


def test_slash_focuses_the_player_search_unless_you_are_typing():
    i = APP.index('// "/" SEARCHES (audit V-14)')
    blk = APP[i:i + 700]
    assert 'if (e.key !== "/" || e.metaKey || e.ctrlKey || e.altKey) return;' in blk
    assert "/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)" in blk and 'getElementById("player-search")' in blk


def test_the_menu_groups_are_legible_open_and_counted():
    for fold in ("research", "library"):
        m = re.search(rf'data-fold="{fold}"\s+type="button" aria-expanded="(\w+)"', HTML)
        assert m and m.group(1) == "true", fold
        assert f'<div class="sb-group" data-group="{fold}">' in HTML, fold
    i = CSS.index(".sb-fold { display: flex;")
    rule = CSS[i:CSS.index("}", i)]
    assert "font-size: var(--fs-xs); min-height: 24px;" in rule
    assert 'c.className = "sb-count";' in APP and "c.textContent = `(${n})`;" in APP


def test_the_other_books_are_printed_not_hidden_in_a_tooltip():
    strip = _fn("booksStripHTML")
    assert "+ at other lines:" in strip and 'class="bs-more" title=' not in strip


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
