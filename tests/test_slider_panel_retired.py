"""The board’s slider panel is gone, and nothing points at it.

Ethan, 2026-09-14, with the panel on screen above an empty board:
"Can you remove this circled section as it seems like it’s not working
and also it’s not needed."

Both were true. Min confidence, Min edge and Max juice defaulted to the
engine’s OWN bars, so the only thing moving one could do was hide picks
the model had already approved — and the empty state the panel produced
("No props clear your filters — loosen the sliders") sent a reader to
knobs that were never the reason a board was empty. The bars are
constants now (`BARS`), the board draws what cleared them, and the
funnel under the board says what held each prop.

What this pins: the controls are gone from the markup and the wiring;
no rendered sentence sends a reader to one; the bars still match the
engine’s; and the one reveal that survives — the game page’s "show
everything analyzed" — is reversible, because the checkbox that used to
undo it is gone.

Run directly: `python3 tests/test_slider_panel_retired.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


APP = _read("web", "js", "app.js")
HTML = _read("web", "index.html")


def test_the_controls_are_gone_from_the_markup():
    for dead in ('id="rec-controls"', 'id="min-conf"', 'id="min-edge"',
                 'id="max-juice"', 'id="show-all"', "Show non-recommended props",
                 "Min confidence", "Min edge", "Max juice"):
        assert dead not in HTML, dead


def test_nothing_is_wired_to_a_control_that_does_not_exist():
    """A listener on a removed element throws on load and takes every
    later listener in the same function with it."""
    for dead in ('getElementById("min-conf")', 'getElementById("min-edge")',
                 'getElementById("max-juice")', 'getElementById("show-all")',
                 "state.showAll"):
        assert dead not in APP, dead


def test_no_sentence_on_screen_sends_a_reader_to_a_slider():
    """The dead end Ethan was looking at. Comments may still explain the
    history; rendered copy may not point at a control that is gone."""
    code = re.sub(r"/\*.*?\*/", "", APP, flags=re.S)          # block comments
    code = "\n".join(ln for ln in code.splitlines()
                     if not ln.lstrip().startswith("//"))      # line comments
    body = code + HTML
    for phrase in ("Loosen the sliders", "loosen the sliders",
                   "show non-recommended", "No props clear your filters",
                   "no slider changes that", "sliders have nothing to filter"):
        assert phrase not in body, phrase


def test_the_bars_are_constants_and_still_the_engines_own():
    """The panel defaulted to the engine's numbers; removing it must not
    change what the board draws. `server.py` defaults the same three."""
    assert "const BARS = Object.freeze({ conf: 6.0, edge: 2.0, juice: -350 });" in APP
    assert "minConf: BARS.conf, minEdge: BARS.edge, maxJuice: BARS.juice" in APP
    srv = _read("server.py")
    assert 'qf("min_confidence", 6.0)' in srv
    assert 'qf("max_juice", -350)' in srv
    assert 'qf("min_edge", 2.0)' in srv
    # The board's own gate reads them, so a row still has to clear all three.
    fn = APP[APP.index("function passesFilters"):]
    fn = fn[:fn.index("\n}\n")]
    for bar in ("state.minConf", "state.minEdge", "state.maxJuice"):
        assert bar in fn, bar


def test_the_game_pages_reveal_is_reversible():
    """It was one-way while the board had a checkbox to undo it. Scoped
    to the game page and given its own way back, or a reader who clicks
    it once sees rows the model passed on from then on."""
    assert "state.showAll" not in APP and "gameShowAll" in APP
    # Shown only when the reveal is on, and wired.
    assert "state.gameShowAll && props.length" in APP
    assert 'id="gp-hideall"' in APP
    # The exact lookup, so a guard that can never be true ("null &&
    # host.querySelector(...)") is a change to this line and fails here
    # rather than passing a substring check on a button nothing listens to.
    at = APP.index('const hideAll = host.querySelector("#gp-hideall");')
    wiring = APP[at:at + 220]
    assert 'if (hideAll) hideAll.addEventListener("click"' in wiring, wiring
    assert "state.gameShowAll = false" in wiring and "renderGamePage()" in wiring
    # The board does not read it: turning it on inside one game can never
    # change what the Recommended board draws.
    fn = APP[APP.index("function renderRecommended"):]
    fn = fn[:fn.index("\nfunction ")]
    assert "gameShowAll" not in fn, "the board reads the game page's reveal"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
