"""Signing in has to END SOMEWHERE, and where depends on the plan.

Ethan, 2026-08-21, with a screenshot of the sign-in card: "it doesn't tell
you it logged you in and then take you to the main website pages, it just
says 'synced'. So we need too change that. If you have a plan already
bought, when you login, it should take you too the main page like mlb or
sum. If you don't have a plan paid for, it should obv take you too the
paywall page since no one should ever get on the Main page without
paying."

The old flow authenticated, synced, wrote "synced 6:18 PM" into the note
under the button, and stopped. Everything had worked and nothing said so.

WHAT THIS PINS

1.  `acctAuth` ends by calling the lander. Without that call the rest of
    the function is unreachable in practice, and the symptom is exactly
    the one Ethan reported.
2.  The lander asks the SERVER. A client-side guess at entitlement is the
    one thing that must not decide this — `paywallCheck` hits
    /api/billing/status with the session cookie.
3.  A failed status request does not fall through to "come in".
    `paywallCheck` swallows its own errors and returns false, and false
    means the board. The lander has to tell the two apart.
4.  A CHANGE in wall state reloads. Boards already in this tab were
    fetched as the previous visitor: for someone signing in from behind
    the wall those copies are the redacted ones, and re-rendering would
    show a paying subscriber the free version of what they just bought.
    The reverse direction has to reload too, because the hashchange guard
    that stops the wall being hash-hopped is only installed at boot.

    python3 tests/test_login_landing.py
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "web", "js", "app.js")


def _src():
    return open(APP, encoding="utf-8").read()


def _body(src, name):
    """The text of one function declaration, brace-matched.

    The parameter list is stepped over first. `say = () => {}` is a
    default value containing braces, and starting the brace match at the
    first `{` after the name stops one character into the signature."""
    m = re.search(r"(?:function %s\s*\(|%s\s*=\s*(?:async\s+)?function\s*\()"
                  % (name, re.escape(name)), src)
    assert m, name + " is not in app.js at all"
    start = m.start()
    depth, i = 0, src.index("(", m.end() - 1)
    for j in range(i, len(src)):
        if src[j] == "(":
            depth += 1
        elif src[j] == ")":
            depth -= 1
            if depth == 0:
                i = src.index("{", j)
                break
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[start:j + 1]
    raise AssertionError(name + " never closes")


def _decomment(text):
    """Comments in this file describe the bugs they prevent, so every check
    below reads code only. Learned the hard way, repeatedly."""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", text)


def test_signing_in_calls_the_lander():
    body = _decomment(_body(_src(), "acctAuth"))
    assert "acctLandAfterAuth" in body, (
        "acctAuth ends without going anywhere — this is the 'synced' bug")


def test_the_lander_asks_the_server_which_page_you_get():
    body = _decomment(_body(_src(), "acctLandAfterAuth"))
    assert "paywallCheck" in body, (
        "entitlement decided client-side; it has to come from "
        "/api/billing/status")


def test_an_unreachable_server_does_not_mean_come_in():
    body = _decomment(_body(_src(), "acctLandAfterAuth"))
    assert "_pwStatus = null" in body, (
        "without clearing it first, a failed request is indistinguishable "
        "from a cached answer")
    assert re.search(r"if \(!_pwStatus\)", body), (
        "nothing checks whether the status request actually landed")


def test_a_change_in_wall_state_reloads():
    body = _decomment(_body(_src(), "acctLandAfterAuth"))
    assert "location.reload()" in body, (
        "no reload: a subscriber would be shown the redacted boards this "
        "tab fetched before they signed in")
    assert "walled !== was" in body or "was !== walled" in body, (
        "the reload has to be conditional on the state CHANGING, not on "
        "being walled")


def test_the_paid_landing_is_a_real_view():
    body = _decomment(_body(_src(), "acctLandAfterAuth"))
    src = _src()
    order = src[src.index("const VIEW_ORDER"):]
    order = order[:order.index("\n")]
    names = re.findall(r'"([a-z]+)"', order)
    landed = (re.findall(r'switchView\(\s*"([a-z]+)"', body)
              + re.findall(r'"#([a-z]+)"', body))
    assert landed, "the lander never navigates anywhere"
    for name in landed:
        assert name in names, (
            "lands on #%s, which is not in VIEW_ORDER" % name)


def test_the_unpaid_landing_is_the_paywall():
    body = _decomment(_body(_src(), "acctLandAfterAuth"))
    assert "paywall" in body, "an unpaid sign-in has to end on the plans"
    assert "renderPaywall" in body, (
        "switching to #paywall without rendering it shows a blank section "
        "— the exact bug Ethan hit typing the URL by hand")


def test_the_lander_survives_being_called_without_a_note_to_write_to():
    body = _decomment(_body(_src(), "acctLandAfterAuth"))
    assert re.search(r"function acctLandAfterAuth\(say\s*=", body), (
        "say has no default, so any future caller without one throws "
        "mid-redirect and strands the user on the form")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("  ok  %s" % fn.__name__)
    print()
    print("%d tests passed." % len(fns))
