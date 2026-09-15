"""Creating an account is its own page.

Ethan, 2026-08-22: *"on the login page, the sign up button should link to
a new page to sign up. its confusing to someone to type in there email and
password into a login section to signup for an account."*

He is right, and it was worse than confusing. One card carried one set of
fields and two buttons, so the same two boxes meant "the password I
already have" under Log in and "a password I am choosing now" under Sign
up — and the markup told the browser `autocomplete="current-password"`
either way, which is the wrong hint for half the people using it. That
hint is what decides whether a password manager offers to FILL or offers
to SAVE. The 21-and-over checkbox sat under both buttons and applied to
one of them.

    python3 tests/test_signup_page.py
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "web", "js", "app.js")
HTML = os.path.join(ROOT, "web", "index.html")


def _read(p):
    return open(p, encoding="utf-8").read()


def _code():
    s = re.sub(r"/\*.*?\*/", " ", _read(APP), flags=re.S)
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


# --- it is a page -----------------------------------------------------------
def test_there_is_a_signup_view():
    assert 'id="view-signup"' in _read(HTML)
    code = _code()
    order = code[code.index("const VIEW_ORDER"):]
    assert '"signup"' in order[:order.index("\n")], (
        "a routable view missing from VIEW_ORDER animates backwards")


def test_the_router_draws_it():
    body = _fn(_code(), "_switchViewNow")
    assert 'if (name === "signup") renderSignup();' in body, (
        "switching to a view nobody renders is a blank section")


def test_it_is_reachable_from_behind_the_wall():
    """Somebody who has not paid has, by definition, not signed up."""
    code = _code()
    m = re.search(r"const WALL_OPEN = \[([^\]]*)\]", code)
    assert '"signup"' in m.group(1), (
        "the wall blocks the page where an account is created")


def test_the_login_card_links_to_it():
    card = _fn(_code(), "acctSignInHTML")
    assert "acctGoSignup()" in card, "no way through to the sign-up page"


def test_the_signup_page_links_back():
    page = _fn(_code(), "signupHTML")
    assert "acctGoLogin()" in page, (
        "somebody who already has an account is stranded")


# --- one page asks one question ---------------------------------------------
def test_the_login_card_no_longer_creates_accounts():
    card = _fn(_code(), "acctSignInHTML")
    assert "'signup'" not in card, (
        "the sign-in card still has a sign-up button — this is the whole "
        "complaint")
    assert "acct-age" not in card, (
        "the 21-and-over checkbox is on the sign-in card, where it applies "
        "to nothing")


def test_the_signup_page_asks_for_the_confirmation():
    page = _fn(_code(), "signupHTML")
    assert "acct-age" in page, "nothing asks whether they are 21"
    assert "terms.html" in page and "privacy.html" in page, (
        "the box says they accept terms it does not link to")


def test_the_password_hint_follows_the_page():
    """`current-password` on a sign-up form asks a password manager to
    fill a password that does not exist yet; `new-password` is what makes
    it offer to generate and save one."""
    fields = _fn(_code(), "acctFieldsHTML")
    assert "new-password" in fields and "current-password" in fields
    assert "isNew" in fields, "both pages send the same hint"


def test_both_pages_build_their_fields_from_one_place():
    """Two copies of an email field and a password field is two places
    for the autocomplete hint, the maxlength and the eye toggle to
    drift."""
    code = _code()
    assert code.count('class="acct-email"') == 1, (
        "the email field is written out more than once")
    assert code.count("acctFieldsHTML(") >= 3, (
        "the shared builder exists but both pages do not use it")


# --- the details ------------------------------------------------------------
def test_somebody_already_signed_in_is_not_offered_a_second_account():
    body = _fn(_code(), "renderSignup")
    assert "signed_in" in body and 'switchView("account"' in body


def test_the_note_is_cleared_when_moving_between_them():
    """`_acctNote` is the line under the button. Carrying "Email and
    password, both." from the sign-in card onto the sign-up page reads as
    an error about something the reader has not done yet."""
    code = _code()
    for fn in ("acctGoSignup", "acctGoLogin"):
        i = code.index("window." + fn + " = function")
        body = code[i:code.index("\n};", i)]
        assert "_acctNote" in body, "%s does not clear the note" % fn


def test_the_signup_page_says_it_takes_no_card():
    page = _fn(_code(), "signupHTML")
    assert "takes no card" in page or "no card" in page, (
        "a sign-up form on a paid site has to say whether it charges")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("  ok  %s" % fn.__name__)
    print()
    print("%d tests passed." % len(fns))
