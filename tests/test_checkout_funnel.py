"""Somebody who picked a plan does not get asked to pick it again.

Ethan, 2026-09-09, after two customers went through it: *"it let them
make an account. It was a little confusing."*

THE LOOP THEY WALKED. Read the plans, pick one, read the checkout, press
the big button — and only THEN get told a subscription needs an account.
Bounced to the sign-up form with "come back here when you are in", where
"here" was a page they had to find again. They make the account, and
`acctLandAfterAuth` sees a signed-in reader with no plan and does the
sensible-looking thing: shows them the plans. Which they had already
chosen from, two minutes earlier.

So the choice appeared not to register, and the account step arrived as
an ambush at the last possible moment. Two changes, and they are
different halves of the same problem:

  * the checkout SAYS an account is part of this, above the button,
    before anybody commits to anything;
  * the chosen plan is remembered across the bounce and the reader comes
    back to that plan's checkout rather than to the list.

The second one copies `acceptPendingInvite` deliberately — same shape,
and its comment already states the principle: the link is why this
person just signed in, and forgetting it is a funnel with a hole in the
bottom. A chosen plan is why this person just signed UP.

    python3 tests/test_checkout_funnel.py
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


APP = _read("web", "js", "app.js")


def _fn(sig, end="\n}"):
    i = APP.index(sig)
    return APP[i:APP.index(end, i)]


def test_the_checkout_says_an_account_is_part_of_this_before_the_button():
    """Above the button, not after it. Discovering the requirement by
    pressing Pay is the ambush."""
    body = APP[APP.index("function checkoutHTML("):]
    body = body[:body.index("\nfunction renderCheckout(")]
    needle = "attaches to an\n              account"
    # Asserted before it is used: a bare `.index` on a line somebody
    # removed raises ValueError, and the runner reports that as noise
    # rather than as the sentence explaining what broke.
    assert needle in body, \
        "the checkout no longer mentions that an account is part of this"
    assert body.index(needle) < body.index("coPay(this)"), \
        "the account line is below the button it is warning about"


def test_the_plan_is_remembered_when_the_wall_interrupts_the_purchase():
    body = _fn("window.coPay = async function (btn) {", "\n};")
    assert "rememberPendingPlan(plan)" in body, \
        "the plan is dropped on the floor at the one moment it is needed"
    i = body.index("rememberPendingPlan(plan)")
    j = body.index('_switchViewNow("account"')
    assert i < j, "the bounce happens before the plan is kept"


def test_signing_up_comes_back_to_that_plan_and_not_to_the_list():
    body = _fn("async function acctLandAfterAuth(")
    assert "takePendingPlan()" in body, \
        "a reader who chose a plan is still sent back to choose one"
    i = body.index("takePendingPlan()")
    j = body.index("renderPaywall()")
    assert i < j, \
        "the plans page is drawn before the pending plan is even looked at"
    resume = body[i:j]
    assert "_switchViewNow(\"checkout\"" in resume, \
        "the plan is read and then not used to go anywhere"


def test_the_plan_is_read_once_and_cleared():
    """A plan left in storage would hijack the NEXT sign-in on the
    device — somebody else's, on a shared phone."""
    body = _fn("function takePendingPlan()")
    assert "removeItem(PENDING_PLAN_KEY)" in body, \
        "the pending plan outlives the sign-in that consumed it"
    land = _fn("async function acctLandAfterAuth(")
    assert land.count("takePendingPlan()") == 2, \
        "the already-paid branch does not clear it, so it ambushes a later sign-in"


def test_it_survives_the_reload_that_one_sign_in_branch_does():
    """`acctLandAfterAuth` reloads the page when the wall state changes.
    A plan held in a variable would not live through that, which is why
    this is storage and not a `let`."""
    body = _fn("function rememberPendingPlan(id)")
    assert "localStorage.setItem" in body, "an in-memory plan dies on the reload"
    assert "try {" in body, \
        "a browser with storage blocked would throw on the way to checkout"


def test_the_bounce_message_no_longer_sends_them_looking():
    """"Come back here when you are in" named a place the reader was
    about to be moved away from."""
    body = _fn("window.coPay = async function (btn) {", "\n};")
    # The comment above the fix QUOTES the old line to say what it
    # replaced, and a grep that reads comments would be satisfied by the
    # comment. Code only — the same trap as the Record page's chips.
    code = re.sub(r"//[^\n]*", "", re.sub(r"/\*.*?\*/", "", body, flags=re.S))
    assert "come back here when you are in" not in code.lower(), \
        "still telling them to find their own way back"
    assert "straight back" in body, \
        "nothing tells them the plan is kept"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
