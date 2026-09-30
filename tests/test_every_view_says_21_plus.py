"""21+ and 1-800-GAMBLER on every view, in the first screen; zoom allowed.

Audit 2026-09-30, P1-8 / V-1 / V-4 (roadmap #7). The full notice lives in
the footer, which goes quiet on reference pages (Ethan, 2026-09-24) and on
every page sits below hundreds of rows. One line now sits above every
view in the shell, outside any view's section, so no route can drop it.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "web" / "index.html").read_text()
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def test_the_line_is_in_the_shell_above_every_view():
    i = HTML.index('<p class="rg-line"')
    main = HTML.index("<main>")
    first_view = HTML.index('<section class="view')
    assert main < i < first_view, "inside <main>, above the first view"
    line = HTML[i:HTML.index("</p>", i)]
    assert "21+" in line and "1-800-GAMBLER" in line


def test_no_view_or_mode_hides_it():
    for m in re.finditer(r"\.rg-line[^{]*\{([^}]*)\}", CSS):
        assert "display: none" not in m.group(1) and "visibility: hidden" not in m.group(1)
    assert not re.search(r"body\.[\w-]+ \.rg-line\s*\{[^}]*display:\s*none", CSS)
    assert "rg-line" not in APP or "rg-line\").hidden" not in APP


def test_the_viewport_allows_zoom():
    vp = HTML[HTML.index('name="viewport"'):]
    vp = vp[:vp.index(">")]
    assert "user-scalable=no" not in vp and "maximum-scale" not in vp


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
