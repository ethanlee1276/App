"""The stale bar must not evict the sidebar.

Found 2026-08-19 while rendering the new memecoin record and noticing its
table was 150px wide. Walking up the DOM said why: `<main>` was **240px
inside a 1280px shell**, and the sidebar had taken main's 1040px track.

`.shell` is a two-column grid — `240px minmax(0, 1fr)`, three with the
rail. `#stalebar` is a direct child of it, and a grid item with no
placement takes a cell. It took column one, the sidebar's; the sidebar
slid into column two; `<main>` wrapped to the next row and got the 240px
stub.

THE REASON IT SURVIVED IS THE PART WORTH REMEMBERING. The bar is
`hidden` on a fresh board and `#stalebar[hidden]` is correctly
`display: none`, so it is not a grid item at all — the layout is perfect
on every healthy page, and every screenshot anyone had taken was of a
healthy page. It broke only when the bar was SHOWING, which is to say
exactly when the site had something important to tell the reader.

`grid-column: 1 / -1` covers both the two-column and the has-rail
three-column shapes.

Run directly: `python3 tests/test_shell_grid.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
HTML = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()


def _rule(sel):
    """The declarations of the first rule whose selector list starts with
    `sel`, comments stripped."""
    body = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    m = re.search(re.escape(sel) + r"\s*\{([^}]*)\}", body)
    assert m, f"no rule for {sel}"
    return m.group(1)


def test_the_shell_is_still_a_two_track_grid():
    """If this ever stops being true the finding below changes shape and
    the fix wants re-reading rather than trusting."""
    r = _rule(".shell")
    assert "display: grid" in r
    assert "grid-template-columns: 240px" in r


def test_every_direct_child_of_the_shell_is_placed_or_hidden():
    """The general form of the bug. Any element parked inside `.shell`
    that is neither positioned out of flow, hidden by default, nor given
    an explicit span, silently eats a column."""
    i = HTML.index('<div class="shell">')
    seg = HTML[i:i + 12000]
    depth, kids = 0, []
    for m in re.finditer(r"<(/?)([a-zA-Z][\w-]*)([^>]*)>", seg):
        close, tag, attrs = m.group(1), m.group(2), m.group(3)
        if tag in ("br", "img", "input", "meta", "link", "path", "circle", "use"):
            continue
        if not close:
            if depth == 1:
                kids.append((tag, attrs))
            depth += 1
        else:
            depth -= 1
            if depth <= 0:
                break
    assert kids, "could not read the shell's children"
    known = {"scrim", "stalebar", "sidebar", "rail"}
    for tag, attrs in kids:
        ident = re.search(r'(?:id|class)="([\w -]+)"', attrs)
        name = (ident.group(1).split()[0] if ident else tag)
        assert name in known or tag == "main", \
            (f"<{tag} {name}> is a new direct child of .shell — give it "
             f"grid-column or hide it, or it takes the sidebar's column")


def test_the_stale_bar_spans_instead_of_taking_a_column():
    r = _rule("#stalebar")
    assert "grid-column: 1 / -1" in r, \
        "the stale bar is a plain grid item again — it will evict the sidebar"


def test_it_is_still_display_none_when_hidden():
    """The guard that made the bug intermittent. Keep it: without it the
    bar is a grid item on every page, all the time."""
    assert "#stalebar[hidden] { display: none; }" in CSS


def test_the_rail_variant_is_covered_too():
    """`1 / -1` has to span three columns as well as two, which is the
    whole reason it is written as -1 rather than 3."""
    body = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    m = re.search(r"body\.has-rail \.shell\s*\{([^}]*)\}", body)
    assert m, "the has-rail shell variant is gone"
    assert m.group(1).count("px") >= 2, m.group(1)
    assert "grid-column: 1 / -1" in _rule("#stalebar")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
