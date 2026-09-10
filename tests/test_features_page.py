"""A features list nobody can click is how a features list starts lying.

Ethan, 2026-09-10: "add a features page so new users can go and look at
every single feature the site offers. i want you to go in depth and tell
EVERY feature we offer. down to the draft simulator and being able too
look up past player or team stats vs specific teams and litterally
everything."

The page is rendered from `FEATURES` in app.js rather than written into
the shell, so it can be checked. TWO DIRECTIONS, and both matter:

  · every `view` a row names must be a real destination, or the page
    advertises a screen that does not exist and the arrow goes nowhere;
  · every destination the SIDEBAR offers must appear somewhere on the
    page, or a feature shipped later quietly goes undocumented and the
    list is out of date the first week nobody re-reads it.

The second is the one that rots on its own. The first fails loudly the
moment somebody clicks; the second fails silently forever.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APP = (ROOT / "web" / "js" / "app.js").read_text()
HTML = (ROOT / "web" / "index.html").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _table():
    """`FEATURES` as [(section, blurb, [(title, desc, view|None)])]."""
    i = APP.index("const FEATURES = [")
    src = APP[i:APP.index("\n];", i)]
    # Sections open at indent 2 with a name and a blurb and nothing else
    # on the line; rows are the triples, wherever they sit. Two passes
    # rather than one alternation — the first draft of this used one and
    # the `[[` that opens each section's row list ate that section's
    # FIRST row, which is a parser that silently under-reports and a
    # test that then passes for the wrong reason.
    heads = [(m.start(), m.group(1), m.group(2))
             for m in re.finditer(r'^  \["([^"]+)", "([^"]*)",$', src, re.M)]
    assert heads, "no sections parsed"
    out = []
    for n, (at, name, blurb) in enumerate(heads):
        end = heads[n + 1][0] if n + 1 < len(heads) else len(src)
        rows = [(t, d, None if v == "null" else v.strip('"'))
                for t, d, v in re.findall(r'\["([^"]+)", "(.*?)", (null|"[a-z]+")\]',
                                          src[at + len(name) + len(blurb):end])]
        out.append([name, blurb, rows])
    return out


def _views():
    return set(re.findall(r'id="view-([a-z-]+)"', HTML))


def test_the_table_parses_into_something_worth_checking():
    """If the shape drifts, every assertion below passes vacuously."""
    t = _table()
    assert len(t) >= 6, f"only {len(t)} sections"
    rows = [r for _, _, rs in t for r in rs]
    assert len(rows) >= 50, f"only {len(rows)} features listed — 'EVERY feature' was the ask"
    assert any(v for _, _, v in rows), "no row opens anything"
    assert any(v is None for _, _, v in rows), "no row is a part-of-a-screen entry"


def test_every_arrow_goes_somewhere_real():
    views = _views()
    for section, _, rows in _table():
        for title, _, view in rows:
            if view:
                assert view in views, f"{section} / {title} opens #{view}, which is not a view"


def test_every_sidebar_destination_is_described():
    """THE ONE THAT ROTS QUIETLY. A page added later and not written up
    here leaves the list wrong with nothing to notice it."""
    listed = {v for _, _, rows in _table() for _, _, v in rows if v}
    nav = set(re.findall(r'data-view="([a-z-]+)"', HTML))
    nav |= {m for m in re.findall(r'data-sport="([a-z]+)" data-kind="tool"', HTML)}
    # The shell's own plumbing is not a feature: sign-up, the wall, the
    # checkout and the account screen are how you buy it, not what it does.
    plumbing = {"account", "signup", "paywall", "checkout", "discord", "features"}
    missing = sorted(nav - listed - plumbing)
    assert not missing, f"destinations the features page never mentions: {missing}"


def test_the_two_things_he_named_are_actually_on_it():
    """He named the draft simulator and the past-stats-versus-a-team
    lookup by hand, which makes them the test everybody else's page
    would have failed."""
    rows = [(t, d) for _, _, rs in _table() for t, d, _ in rs]
    blob = " ".join(f"{t} {d}" for t, d in rows).lower()
    assert "mock draft simulator" in blob, "the draft simulator is not listed"
    assert "against tonight’s opponent" in blob or "against a specific team" in blob, \
        "the versus lookup is not listed"
    assert "head-to-head" in blob, "the team-vs-team history is not listed"


def test_the_page_is_free_to_read():
    """Somebody deciding whether to pay has to be able to read what they
    would be paying for."""
    i = APP.index("const REFERENCE_VIEWS = ")
    assert '"features"' in APP[i:APP.index("]", i)], \
        "the features page is not a free reference view"


def test_the_page_is_wired_and_styled():
    assert 'id="view-features"' in HTML
    assert 'id="features-body"' in HTML
    assert 'data-sport="features"' in HTML, "no way in from the nav"
    assert 'if (name === "features") renderFeatures();' in APP, "nothing renders it"
    assert '"features"' in APP[APP.index("const VIEW_ORDER"):APP.index("const VIEW_ORDER") + 900], \
        "the router does not know the view"
    assert ".ft-row {" in CSS and ".ft-jump {" in CSS


def test_a_row_without_a_door_does_not_draw_an_arrow():
    """An arrow that does nothing is worse than no arrow."""
    body = APP[APP.index("function renderFeatures()"):APP.index("const REFERENCE_VIEWS = ")]
    assert 'view ? "button" : "div"' in body, "every row is a button, door or not"
    assert '${view ? `<span class="ft-go"' in body, "the arrow is unconditional"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
