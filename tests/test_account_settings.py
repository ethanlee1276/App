"""What the account page tells you, and what it lets you do.

Ethan, 2026-08-22: *"On the account page make sure we should exactly what
plan they are subscribed too. Also we need to add settings a normal
website would have for an account?"*

THE PLAN. It said "Subscribed — renews 21 Sep 2026." and stopped. That is
a status, not an answer: it does not say monthly or yearly, what it costs,
or what the next charge will be. Somebody who bought six months and sees a
date four weeks out has no way to tell whether they are on the plan they
think they are, and the place they go next is a chargeback.

THE SETTINGS. Change your password, download everything held about you,
clear the search history, delete the account — those were already here,
and they are the four that matter. What was missing is the one you need
when you cannot reach a device: sign out everywhere. Without it the only
way to revoke a session on a laptop you left somewhere is to change a
password you had no other reason to change.

    python3 tests/test_account_settings.py
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "web", "js", "app.js")
SERVER = os.path.join(ROOT, "server.py")
ACCOUNTS = os.path.join(ROOT, "engine", "accounts.py")


def _read(p):
    return open(p, encoding="utf-8").read()


def _code(p=APP):
    s = re.sub(r"/\*.*?\*/", " ", _read(p), flags=re.S)
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


# --- exactly what plan ------------------------------------------------------
def test_the_panel_names_the_plan():
    body = _fn(_code(), "planPanelHTML")
    assert "PLANS.find" in body, (
        "nothing looks the plan up, so the page cannot name it")
    assert "plan.name" in body


def test_it_states_the_price_and_the_cadence():
    body = _fn(_code(), "planPanelHTML")
    assert "plan.price" in body and "plan.per" in body, (
        "the page says which plan without saying what it costs")


def test_it_states_when_the_next_charge_lands():
    body = _fn(_code(), "planPanelHTML")
    assert "period_end" in body, "no renewal date"


def test_a_trial_is_labelled_as_one_and_says_what_follows():
    body = _fn(_code(), "planPanelHTML")
    assert '"trialing"' in body, "a trial reads as an ordinary subscription"
    assert "Then" in body, (
        "the trial does not say what it becomes, which is the part that "
        "surprises people")


def test_a_cancelled_subscription_says_when_access_ends():
    body = _fn(_code(), "planPanelHTML")
    assert '"canceled"' in body
    assert "Access until" in body or "Ends " in body


def test_a_comped_account_is_not_offered_a_subscription_to_manage():
    body = _fn(_code(), "planPanelHTML")
    assert "comped" in body, (
        "an account given access directly reads as a paying one, and the "
        "page offers it a portal for a customer that does not exist")


def test_nothing_is_invented_when_the_server_does_not_know():
    """An account page that guesses is worse than one that is quiet."""
    body = _fn(_code(), "planPanelHTML")
    assert "if (!s || !s.entitled) return \"\"" in body, (
        "the panel draws for somebody with no subscription")
    # Every row is conditional on its value.
    assert re.search(r"const row = \([^)]*\) => v\s*\n?\s*\?", body), (
        "rows are drawn whether or not there is anything to put in them")


def test_the_panel_is_actually_mounted():
    body = _fn(_code(), "renderBilling")
    assert "planPanelHTML(s)" in body, "the panel exists and is never drawn"


# --- sign out everywhere ----------------------------------------------------
def test_the_endpoint_exists_and_needs_an_account():
    src = _read(SERVER)
    assert '"signout-all"' in src
    i = src.index('if path == "signout-all"')
    before = src[:i]
    j = before.rindex('return self._send(401')
    assert "sign in first" in before[j:j + 90], (
        "the 401 guard does not cover it")


def test_it_ends_every_session_including_this_one():
    src = _code(ACCOUNTS)
    body = src[src.index("def end_all_sessions("):]
    body = body[:body.index("\ndef ")]
    assert "DELETE FROM sessions WHERE user_id=?" in body, (
        "it ends one session, not all of them")
    assert "commit()" in body


def test_the_browser_stops_believing_it_is_signed_in():
    """This session went with the rest. A page still showing an account
    for a session that no longer exists is the confusing half."""
    code = _code()
    i = code.index("window.acctSignOutAll = async function")
    body = code[i:code.index("\n};", i)]
    assert "location.reload()" in body
    assert "signed_in: false" in body


def test_the_cookie_is_cleared_by_the_server_too():
    src = _read(SERVER)
    i = src.index('if path == "signout-all"')
    body = src[i:i + 600]
    assert "clear=True" in body, (
        "the session rows are gone and the browser still holds the cookie")


def test_the_button_is_on_the_page():
    card = _fn(_code(), "acctSignedInHTML")
    assert "acctSignOutAll" in card


# --- the settings that were already right -----------------------------------
def test_the_four_that_matter_are_still_there():
    card = _fn(_code(), "acctSignedInHTML")
    for fn, what in (("acctChangePassword", "change a password"),
                     ("acctExport", "download what is held about you"),
                     ("acctSearchClear", "clear the search history"),
                     ("acctDelete", "delete the account")):
        assert fn in card, "no way to %s" % what


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("  ok  %s" % fn.__name__)
    print()
    print("%d tests passed." % len(fns))
