"""THE WALL HAS TO REFUSE IN ONE PLACE, and that place is `_switchViewNow`.

THE BUG THIS REPLACED. Enforcement lived in a `hashchange` listener
installed at boot, and it read `state.view` to decide whether a correction
was needed:

    if (state.view !== "paywall") { renderPaywall(); _switchViewNow(...); }

That listener could not win. The router's own hashchange handler is
registered during setup, so it is registered FIRST and runs FIRST, and it
hands the switch to `document.startViewTransition` — which defers it.
`state.view` therefore still read "paywall" when the guard ran, so the
guard did nothing, and the deferred switch then put the reader on the
board. Typing `#recommended` from the wall walked straight onto the site
on every browser with View Transitions, which is all of them.

Found by driving it: `location.hash = '#recommended'` while walled left
`view-recommended` on screen and the URL agreeing with it.

WHAT IS BEING PROTECTED. Not the picks — those are redacted by
`gate.redact()` before the JSON is written and by `_entitled` on the
server, and a reader who defeats every line of app.js finds the same
empty lists. This protects the CHROME from lying: Ethan asked that
"no one can bypass the stripe paywall to get on the site", and a board
that renders its own furniture around nothing is both that, and a support
email from somebody who thinks their payment broke.

    python3 tests/test_wall_routing.py
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "web", "js", "app.js")


def _src():
    return open(APP, encoding="utf-8").read()


def _code():
    """Comments in this file quote the bugs they prevent, so every check
    below reads code only. Learned repeatedly, the same way each time."""
    s = re.sub(r"/\*.*?\*/", " ", _src(), flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", s)


def _fn(src, name):
    start = src.index("function " + name + "(")
    depth, seen = 0, False
    for j in range(src.index("(", start), len(src)):
        if src[j] == "{":
            depth += 1
            seen = True
        elif src[j] == "}":
            depth -= 1
            if seen and depth == 0:
                return src[start:j + 1]
    raise AssertionError(name + " never closes")


def test_the_refusal_lives_in_the_function_every_route_change_ends_in():
    body = _fn(_code(), "_switchViewNow")
    assert "wallBlocked" in body, (
        "_switchViewNow does not check the wall, so any caller that "
        "reaches it directly — a deferred view transition, openGame, the "
        "boot router — walks past it")


def test_the_refusal_lands_on_the_paywall():
    body = _fn(_code(), "_switchViewNow")
    m = re.search(r"if \(wallBlocked\(name\)\) \{[^}]*name = \"paywall\"", body)
    assert m, "blocked, but not redirected anywhere"


def test_switch_view_redirects_before_it_measures_the_direction():
    """VIEW_ORDER.indexOf runs on the name, so rewriting the name after
    that leaves the slide animating between two pages that are not the
    ones on screen."""
    body = _fn(_code(), "switchView")
    i = body.index("wallBlocked")
    j = body.index("VIEW_ORDER.indexOf")
    assert i < j, "the wall check runs after the direction is computed"


def test_nothing_decides_the_wall_from_state_view():
    """The stale read that caused the bypass. `state.view` is whatever the
    last COMPLETED transition set, which during a hashchange is the page
    the reader is leaving."""
    code = _code()
    for m in re.finditer(r'state\.view [!=]==? "paywall"', code):
        raise AssertionError(
            "wall logic reading state.view at offset %d: %r — this is the "
            "race that let #recommended through"
            % (m.start(), code[m.start() - 60:m.start() + 40]))


def test_the_pages_that_stay_open_are_named_once():
    code = _code()
    m = re.search(r"const WALL_OPEN = \[([^\]]*)\]", code)
    assert m, "no single list of what stays open behind the wall"
    open_ = re.findall(r'"([a-z]+)"', m.group(1))
    # Record is the evidence the subscription is sold on. Account is where
    # signing in happens — without it the wall has no door. Discord is a
    # sales page for anyone who has not paid, and the invite on it is
    # sent by the server only to those who have. Paywall and checkout are
    # the wall itself.
    # Signup joined the list 2026-08-22: creating an account is its own
    # page now, and somebody who has not paid has by definition not
    # signed up. Verified in a browser that #wall-back reaches it.
    # Streak joined 2026-08-24: the free daily game is the acquisition
    # funnel — it exists to build the audience the paywall converts, so
    # walling it would defeat it. It publishes no model output (see
    # tests/test_streak.py's key census), and #wall-back verified visible
    # on it with body.walled set.
    # Messages joined 2026-08-25: an invited friend must be able to SEE
    # what was sent — the friends layer is session-gated on purpose,
    # never entitlement-gated (a share is a pointer; the recipient's own
    # board answers it under their own entitlement), so the page leaks
    # nothing and exists to pull people in. #wall-back reaches it
    # through the same generic branch as Record and the streak.
    assert set(open_) == {"paywall", "checkout", "record", "account",
                          "discord", "signup", "streak", "messages"}, open_


def test_every_open_page_is_a_real_view():
    code = _code()
    order = code[code.index("const VIEW_ORDER"):]
    names = re.findall(r'"([a-z]+)"', order[:order.index("\n")])
    open_ = re.findall(r'"([a-z]+)"',
                       re.search(r"const WALL_OPEN = \[([^\]]*)\]",
                                 code).group(1))
    for n in open_:
        assert n in names, "WALL_OPEN names #%s, which is not a view" % n


def test_the_boot_listener_still_draws_the_plans():
    """`_switchViewNow` refuses and switches to #paywall. If nothing ever
    rendered into that section the reader gets a blank page — which is
    exactly what Ethan hit typing /#paywall by hand."""
    code = _code()
    # The LAST one: the router owns the first, and the boot wall listener
    # is installed after it (which is the whole reason it lost the race).
    i = code.rindex('addEventListener("hashchange"')
    tail = code[i:i + 400]
    assert "renderPaywall" in tail, (
        "the wall is enforced but never drawn on a hash hop")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("  ok  %s" % fn.__name__)
    print()
    print("%d tests passed." % len(fns))
