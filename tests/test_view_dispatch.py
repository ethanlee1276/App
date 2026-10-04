"""A page that draws itself only when a data load happens to be passing.

Ethan has now found this twice. The first time it was the paywall and
checkout screens, and the comment left in _switchViewNow says what the
symptom was: "THESE TWO WERE MISSING, and the symptom was a blank page…
Found by Ethan doing exactly that on the live site."

Futures was the third, found 2026-08-25, and it hid for most of a night
behind its own intermittency. Checked on its own it drew fine; checked
after walking three other pages it drew nothing at all — not an empty
state, not a loading line, an empty <section>. I wrote it off as a probe
artifact twice before measuring it properly.

THE INVARIANT, which is narrower than "every view is dispatched".
renderAll() holds two kinds of renderer:

  * UNCONDITIONAL — renderScanner, renderTrending, renderPlayers and the
    rest run on every load whatever view you are on, so their hosts are
    already filled by the time you navigate. They need no dispatch and
    must not be required to have one.

  * CONDITIONAL — `if (state.view === "x") renderX()`. These run ONLY
    when a load lands while you are already standing on that page. A
    load is not navigation, so a conditional renderer with no entry in
    _switchViewNow can only draw by luck.

So: every conditional renderer in renderAll must also be dispatched from
_switchViewNow. That is the rule futures broke, it is the rule paywall
and checkout broke before it, and it is checkable from the source.

Run directly: `python3 tests/test_view_dispatch.py`
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _body(name):
    """A function's own body, brace-matched from the BODY brace.

    Counting from the first `{` after the name lands inside a default
    argument like `opts = {}` and truncates the function there.
    """
    i = APP.index(f"function {name}(")
    j = APP.index(") {", i) + 2
    depth = 0
    for k in range(j, len(APP)):
        if APP[k] == "{":
            depth += 1
        elif APP[k] == "}":
            depth -= 1
            if depth == 0:
                return APP[i:k + 1]
    raise AssertionError(f"unbalanced braces reading {name}")


def _conditional_renderers():
    """{view: renderFn} for every `if (state.view === "x") renderX();`."""
    body = _body("renderAll")
    return dict(re.findall(
        r'if \(state\.view === "([a-z]+)"\) (render\w+)\(\)', body))


def test_renderall_still_has_conditional_renderers():
    """If this ever finds none, the shape of renderAll changed and the
    check below is passing because it is looking at nothing."""
    found = _conditional_renderers()
    assert len(found) >= 4, \
        f"only found {found} — the reader, not the code, is probably wrong"


def test_every_conditional_renderer_is_also_dispatched_on_navigation():
    """The rule. A load is not navigation."""
    sw = _body("_switchViewNow")
    missing = []
    for view, fn in sorted(_conditional_renderers().items()):
        # `then(renderAccount)` counts: dispatched, just not called here.
        if fn not in sw:
            missing.append(f"{view} ({fn})")
    assert not missing, (
        "these views are drawn only when a data load lands while you are "
        "already on them, so navigating to them shows a blank page: "
        + ", ".join(missing)
        + ". Add `if (name === \"<view>\") <renderFn>();` to _switchViewNow.")


def test_futures_specifically():
    """The one that was missing, pinned by name — it is the third page to
    go blank this way and the first two are already commented in place."""
    sw = _body("_switchViewNow")
    assert 'if (name === "futures") renderFutures();' in sw, \
        "futures is back to drawing only when a load passes by"


def test_the_two_that_taught_this_lesson_are_still_dispatched():
    sw = _body("_switchViewNow")
    for line in ('if (name === "paywall") renderPaywall();',
                 'if (name === "checkout") renderCheckout();'):
        assert line in sw, f"regressed: {line}"


def test_the_unconditional_renderers_are_not_required_to_be_dispatched():
    """Guards the OTHER half of the rule. renderScanner and friends run
    on every load whatever view is showing, so their hosts are already
    filled — demanding a dispatch for them would be noise, and a test
    that demands noise gets relaxed until it means nothing."""
    body = _body("renderAll")
    conditional = set(_conditional_renderers().values())
    for fn in ("renderScanner", "renderTrending", "renderPlayers",
               "renderRecommended"):
        assert f"{fn}()" in body, f"{fn} left renderAll"
        assert fn not in conditional, \
            f"{fn} became conditional — it now needs a dispatch too"


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
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
