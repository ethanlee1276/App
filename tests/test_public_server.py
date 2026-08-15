"""What changes when the door is open to everyone.

Ethan, 2026-08-15: *"a dedicated server for anyone and everyone to use."*

A LAN server and a public one are different programs wearing the same
code. Most of this repo's assumptions were fine for one person on their
own Wi-Fi and stop being fine the moment a stranger can reach the port.
Two were found by audit rather than by reading — measured against a
running server, which is the only way this class of thing shows up:

  * **`/api/profile/<name>` created accounts with no credential.** Three
    were made from curl in a second. On a LAN that was the feature; public
    it is free disk for whoever finds the path.
  * **No security headers at all.** Not one.

Both are fixed and pinned here. The plan they came out of is
docs/LAUNCH.md, and the thing worth keeping from it is the order: the
questions that can invalidate the work go before the work.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


SERVER = _read("server.py")
APP = _read("web", "js", "app.js")
PLAN = _read("docs", "LAUNCH.md")


# --- the open write endpoint -------------------------------------------------
def test_a_stranger_cannot_create_a_profile():
    """The one an audit found. Anyone could POST a name that did not
    exist and get a 1MB store, with no credential of any kind."""
    i = SERVER.index('if not parsed.path.startswith("/api/profile/")')
    body = SERVER[i:i + 2000]
    assert "_load_profile(_name) is None" in body
    assert "_local_only()" in body and "_via_tailnet()" in body
    assert "_PROFILE_LOCAL_ONLY" in body


def test_syncing_an_existing_profile_still_works_from_anywhere():
    """The fix must not break the phone that already has one. Creation is
    the privileged act; syncing is not, and gating both would have broken
    the feature to secure it."""
    i = SERVER.index('if not parsed.path.startswith("/api/profile/")')
    body = SERVER[i:i + 2000]
    guard = body[body.index("_load_profile(_name) is None"):]
    guard = guard[:guard.index("code, out = profile_sync")]
    # The refusal is conditional on the profile being ABSENT.
    assert "is None" in guard
    assert "403" in guard


def test_the_refusal_points_at_the_thing_that_replaced_it():
    """A closed door with no sign on it is a bug report."""
    i = SERVER.index("_PROFILE_LOCAL_ONLY = (")
    msg = SERVER[i:i + 500]
    assert "email and password" in msg


# --- security headers --------------------------------------------------------
def test_every_response_carries_the_basic_headers():
    assert "SECURITY_HEADERS = (" in SERVER
    i = SERVER.index("SECURITY_HEADERS = (")
    block = SERVER[i:SERVER.index("\n)", i)]
    for name in ("X-Content-Type-Options", "Referrer-Policy",
                 "X-Frame-Options", "Content-Security-Policy"):
        assert name in block, name
    assert "nosniff" in block
    # …and they are sent from the one place every response goes through.
    j = SERVER.index("def _send(")
    send = SERVER[j:j + 1400]
    assert "for name, value in SECURITY_HEADERS" in send


def test_hsts_is_sent_only_over_https():
    """On a plain-HTTP LAN address it does nothing at best; announced from
    a name that later has to serve HTTP it is a self-inflicted outage
    browsers remember for months."""
    j = SERVER.index("def _send(")
    send = SERVER[j:j + 1400]
    i = send.index("Strict-Transport-Security")
    assert "self._is_https()" in send[:i], "HSTS is sent unconditionally"
    # And it is NOT in the always-sent tuple, which is the other way the
    # same mistake gets made.
    k = SERVER.index("SECURITY_HEADERS = (")
    always = SERVER[k:SERVER.index("\n)", k)]
    assert "Strict-Transport-Security" not in always


def test_connect_src_is_self_and_that_is_a_real_restriction():
    """Not decoration. The page makes NO browser-side request to any
    external host — Sleeper, ESPN, Yahoo and Stripe are all reached by the
    server — so an injected script has nowhere to send what it steals.
    Checked against the page rather than asserted."""
    k = SERVER.index("SECURITY_HEADERS = (")
    csp = SERVER[k:SERVER.index("\n)", k)]
    assert "connect-src 'self'" in csp
    external = re.findall(r'fetch\(\s*[`"\']https?://', APP)
    assert not external, f"the page now fetches externally: {external[:3]}"


def test_the_inline_script_weakness_is_written_down_not_hidden():
    """`script-src` still needs 'unsafe-inline' because the page carries
    inline onclick handlers. That is a real weakness in the policy, and an
    exception nobody wrote down gets mistaken for a considered choice."""
    k = SERVER.index("SECURITY_HEADERS = (")
    block = SERVER[max(0, k - 1400):SERVER.index("\n)", k)]
    assert "unsafe-inline" in block
    assert "onclick" in block, "the reason for the weakness is not recorded"
    assert APP.count('onclick="') > 0, \
        "the handlers are gone — tighten script-src and update this test"


def test_clickjacking_is_refused_twice():
    """`X-Frame-Options` for old browsers, `frame-ancestors` for the rest.
    A betting page framed inside somebody else's site is a phishing page
    wearing our numbers."""
    k = SERVER.index("SECURITY_HEADERS = (")
    block = SERVER[k:SERVER.index("\n)", k)]
    assert "DENY" in block and "frame-ancestors 'none'" in block


# --- the plan ----------------------------------------------------------------
def test_the_plan_puts_the_killable_questions_first():
    """Standing up a server before checking whether Stripe will process
    this business, or whether the feeds permit commercial use, is how
    three weeks get spent on something that has to be rebuilt."""
    assert "Phase 0" in PLAN
    assert PLAN.index("Phase 0") < PLAN.index("Phase 2 — the server")
    for must in ("restricted-business", "commercial use", "not a lawyer"):
        assert must in PLAN, must


def test_the_plan_is_honest_about_what_it_cannot_answer():
    assert "**I am not a lawyer.**" in PLAN
    assert "Only you can" in PLAN


def test_the_plan_names_the_audit_findings_rather_than_generalities():
    assert "no credential" in PLAN
    assert "No security headers" in PLAN
    # …and the things that were ALREADY right are recorded as such, so
    # nobody re-does them.
    assert "already correct" in PLAN


def test_the_undocumented_feed_risk_is_called_out():
    """The finding most likely to be missed, because nothing breaks when
    you get it wrong — it just becomes somebody else's decision later."""
    assert "Undocumented endpoints" in PLAN
    assert "ESPN" in PLAN


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
