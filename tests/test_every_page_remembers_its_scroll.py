"""Every page remembers how far down you were, and Back returns there.

Ethan, 2026-09-28: "There is other pages I scroll then click and go back and
it shoots you back to the top … every page [should] remember how far down
you scrolled and which page you left." Pinned: the offset of every page as
it is left; a back (Back buttons, the browser's own back/forward) restores
it; a plain tab tap still lands at the top; a detail page opened by a tap is
a history entry, so the phone's back-swipe returns to the page it came from;
and the landing retries while the page draws but never fights the reader.

Run directly: `python3 tests/test_every_page_remembers_its_scroll.py`
"""
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


def test_every_page_left_is_remembered():
    body = _fn("_switchViewNow")
    assert "if (leaving) _scrollMemo[leaving] = window.scrollY;" in body


def test_a_back_restores_it_and_a_tab_tap_does_not():
    land = _fn("_landScroll")
    assert "const back = Date.now() - _backNavAt < 2000;" in land
    assert "} else if (back && _scrollMemo[name] != null) {" in land
    assert 'window.addEventListener("popstate", () => { _backNavAt = Date.now();' in APP
    assert "markBackNav(); switchView(detailBackView());" in APP
    assert "{ markBackNav(); switchView(way.view); }" in APP, "the play-by-play's Back too"


def test_the_landing_retries_but_never_fights_a_thumb():
    land = _fn("_landScroll")
    assert "if (_touchedAt > landed || state.view !== name || tries++ > 24) return;" in land
    for ev in ('"touchstart"', '"wheel"', '"keydown"'):
        assert ev in APP


def test_a_detail_opened_by_a_tap_is_a_history_entry():
    body = _fn("_switchViewNow")
    assert "const openedByTap = name !== leaving && Date.now() - _routerNavAt > 1500;" in body
    for url in ("writeDetail(shareable", "writeDetail(teamHref(", "writeDetail(`#game/",
                "writeDetail(`#pbp/", "writeDetail(`#player/"):
        assert url in body, url
    # the router's own switches never stack entries
    assert "_routerNavAt = Date.now();\n    const h = (location.hash" in APP
    assert "function initialView() {\n  _routerNavAt = Date.now();" in APP


def test_the_globals_cannot_be_read_before_they_exist():
    """`var`, not `let`: a switch that runs before these lines at load must
    not hit the temporal dead zone and take the page down."""
    for name in ("_scrollMemo", "_backNavAt", "_routerNavAt", "_touchedAt"):
        assert f"var {name} = " in APP, name


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
