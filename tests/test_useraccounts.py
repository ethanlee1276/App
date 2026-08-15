"""Real accounts: email, password, and the properties that make that safe.

Ethan, 2026-08-15: *"we will be storing user information and passwords and
logins ... make a feature where you can make an account on our website
with email and password so we can store peoples bets and fantasy leauges
and search history."*

THIS FILE EXISTS BECAUSE A RULE CHANGED. The site used to have no login
at all, and several tests said so out loud. Those are updated rather than
deleted — a rule that gets quietly dropped is one nobody can tell was ever
considered. What replaced it is narrower and, I think, the part that was
always doing the work: **we hold our own credential, never somebody
else's.** A Qellys password can be scoped, rotated and deleted by us. A
DraftKings password cannot.

Holding real passwords is a promise about handling, so the handling is
what gets pinned here — not that the feature "works", but that the four
things which quietly go wrong in every homemade auth system do not:

  * the password is not recoverable from what we store;
  * a stolen database does not hand over live sessions;
  * the login form is not an account-enumeration oracle;
  * a session cookie is not readable by page scripts.

The last one is the difference between an XSS bug and an XSS bug that is
also a session theft.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine import accounts as A                                # noqa: E402


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


SERVER = _read("server.py")
APP = _read("web", "js", "app.js")
GOOD = "correct-horse-battery"


def _db():
    d = tempfile.mkdtemp()
    return A.connect(os.path.join(d, "acc.db")), os.path.join(d, "acc.db")


# --- what is on disk ---------------------------------------------------------
def test_the_password_is_not_in_the_database_in_any_readable_form():
    """THE ONE THAT MATTERS. "Storing a password" means storing a one-way
    function of it; anything else means a copy of this file is a copy of
    everybody's password, including the one they also used on their bank."""
    conn, path = _db()
    A.create_user(conn, "ethan@example.com", GOOD)
    conn.commit()
    raw = open(path, "rb").read()
    assert GOOD.encode() not in raw
    assert GOOD.encode("utf-16-le") not in raw


def test_the_verifier_carries_its_own_parameters():
    """A stored hash that does not say how it was made can never be
    upgraded without asking everyone to reset. This one is self-describing,
    so the work factor can be raised later on next sign-in."""
    v = A.hash_password(GOOD)
    algo, n, r, p, salt, digest = v.split("$")
    assert algo == "scrypt"
    assert int(n) >= 1 << 14 and int(r) >= 8 and int(p) >= 1
    assert len(bytes.fromhex(salt)) >= 16
    assert len(bytes.fromhex(digest)) >= 32


def test_two_identical_passwords_get_different_verifiers():
    """Per-user salt. Without it, one rainbow table cracks every account
    that chose the same password, and equal hashes reveal who they are."""
    assert A.hash_password(GOOD) != A.hash_password(GOOD)
    assert A.verify_password(A.hash_password(GOOD), GOOD)


def test_verification_is_constant_time():
    """`==` on a digest leaks its prefix through timing. There is a right
    function for this and it costs nothing to use it."""
    src = _read("engine", "accounts.py")
    body = src[src.index("def verify_password("):]
    body = body[:body.index("\n\n\n")]
    assert "hmac.compare_digest" in body
    assert "==" not in body.split("return")[-1]


def test_a_wrong_password_fails_and_a_right_one_does_not():
    assert A.verify_password(A.hash_password(GOOD), GOOD) is True
    assert A.verify_password(A.hash_password(GOOD), GOOD + "x") is False
    assert A.verify_password("not-even-a-verifier", GOOD) is False
    assert A.verify_password("", "") is False


def test_the_database_file_is_owner_only():
    """It holds every user's email and verifier — the single worst file in
    this repo to leave world-readable on a shared box."""
    _conn, path = _db()
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"


# --- the login form is not an oracle -----------------------------------------
def test_an_unknown_email_and_a_wrong_password_say_the_same_thing():
    """Told apart, they turn the login form into a way to check whether an
    address is registered here — which is worth money to whoever is
    building a list of people who bet."""
    conn, _ = _db()
    A.create_user(conn, "ethan@example.com", GOOD)
    a = A.authenticate(conn, "ethan@example.com", "wrong-password-here")
    b = A.authenticate(conn, "ghost@example.com", "wrong-password-here")
    assert a[0] == b[0] == 403
    assert a[1] == b[1]


def test_an_unknown_email_costs_the_same_time_as_a_known_one():
    """The message being identical is worthless if the CLOCK is not: a
    missing user that skips the hash answers ten times faster, and that is
    the same oracle by another channel. Measured, not asserted by reading
    the code."""
    conn, _ = _db()
    A.create_user(conn, "ethan@example.com", GOOD)

    def timed(email):
        best = 9e9
        for _ in range(3):                     # min: least affected by noise
            t0 = time.perf_counter()
            A.authenticate(conn, email, "wrong-password-here")
            A._fails.clear()                   # not what is under test here
            best = min(best, time.perf_counter() - t0)
        return best

    known, unknown = timed("ethan@example.com"), timed("ghost@example.com")
    ratio = max(known, unknown) / max(1e-6, min(known, unknown))
    assert ratio < 3.0, f"timing differs {ratio:.1f}x — that is an oracle"


def test_repeated_wrong_passwords_get_throttled():
    conn, _ = _db()
    A.create_user(conn, "ethan@example.com", GOOD)
    A._fails.clear()
    codes = [A.authenticate(conn, "ethan@example.com", "nope-nope-nope")[0]
             for _ in range(A.MAX_FAILS + 1)]
    assert codes[-1] == 429, "a guesser gets unlimited attempts"
    assert codes[0] == 403
    A._fails.clear()


def test_a_correct_password_clears_the_throttle():
    """Otherwise a stranger can lock a real user out of their own account
    by guessing wrong at them eight times."""
    conn, _ = _db()
    A.create_user(conn, "ethan@example.com", GOOD)
    A._fails.clear()
    for _ in range(A.MAX_FAILS - 1):
        A.authenticate(conn, "ethan@example.com", "nope-nope-nope")
    assert A.authenticate(conn, "ethan@example.com", GOOD)[0] == 200
    assert A.authenticate(conn, "ethan@example.com", "nope-nope-nope")[0] == 403
    A._fails.clear()


# --- sessions ----------------------------------------------------------------
def test_the_session_token_is_hashed_at_rest():
    """The one people skip. A token stored in the clear is a live session
    for anyone who reads the database — same argument as the password, and
    it is a session rather than a guess, so it is worse."""
    conn, path = _db()
    _, who = A.create_user(conn, "ethan@example.com", GOOD)
    token = A.start_session(conn, who["id"])
    conn.commit()
    assert token.encode() not in open(path, "rb").read()
    assert A.session_user(conn, token)["email"] == "ethan@example.com"


def test_a_token_nobody_issued_is_not_a_session():
    conn, _ = _db()
    _, who = A.create_user(conn, "ethan@example.com", GOOD)
    A.start_session(conn, who["id"])
    assert A.session_user(conn, "made-up") is None
    assert A.session_user(conn, "") is None
    assert A.session_user(conn, None) is None


def test_an_expired_session_stops_working():
    conn, _ = _db()
    _, who = A.create_user(conn, "ethan@example.com", GOOD)
    token = A.start_session(conn, who["id"])
    conn.execute("UPDATE sessions SET expires_at=?", (time.time() - 1,))
    conn.commit()
    assert A.session_user(conn, token) is None


def test_signing_out_ends_it_on_the_server():
    """Forgetting a cookie locally is not signing out — the session is
    still valid for whoever else has it."""
    conn, _ = _db()
    _, who = A.create_user(conn, "ethan@example.com", GOOD)
    token = A.start_session(conn, who["id"])
    A.end_session(conn, token)
    assert A.session_user(conn, token) is None


def test_changing_the_password_signs_out_every_device():
    """A password change is usually an answer to "somebody else may have
    this". Leaving their session alive answers it with nothing."""
    conn, _ = _db()
    _, who = A.create_user(conn, "ethan@example.com", GOOD)
    theirs = A.start_session(conn, who["id"])
    assert A.change_password(conn, who["id"], GOOD, "a-brand-new-passphrase")[0] == 200
    assert A.session_user(conn, theirs) is None
    assert A.authenticate(conn, "ethan@example.com", "a-brand-new-passphrase")[0] == 200
    assert A.authenticate(conn, "ethan@example.com", GOOD)[0] == 403


def test_the_old_password_is_required_to_change_it():
    conn, _ = _db()
    _, who = A.create_user(conn, "ethan@example.com", GOOD)
    assert A.change_password(conn, who["id"], "not-it-at-all", "x" * 12)[0] == 403


# --- the two strings we accept -----------------------------------------------
def test_email_case_does_not_create_a_second_account():
    conn, _ = _db()
    assert A.create_user(conn, "Ethan@Example.COM", GOOD)[0] == 200
    assert A.create_user(conn, "ethan@example.com", GOOD)[0] == 409
    assert A.authenticate(conn, "  ETHAN@example.com ", GOOD)[0] == 200


def test_dots_and_plus_tags_are_left_alone():
    """Gmail treats them as noise; most providers do not. An app that
    "helpfully" strips them decides two different people are one account,
    which is a worse failure than a duplicate signup."""
    conn, _ = _db()
    assert A.create_user(conn, "a.b@example.com", GOOD)[0] == 200
    assert A.create_user(conn, "ab@example.com", GOOD)[0] == 200
    assert A.create_user(conn, "a.b+tag@example.com", GOOD)[0] == 200


def test_an_address_that_is_not_one_is_refused():
    for bad in ("", "nope", "a@b", "a b@c.com", "@example.com",
                "a@@example.com", "a@example..com", "x" * 250 + "@e.com"):
        assert not A.email_ok(bad), bad
    for ok in ("a@b.co", "ethan.lee@sub.example.com", "a+b@example.co.uk"):
        assert A.email_ok(ok), ok


def test_the_password_rule_says_which_rule_failed():
    """"Invalid password" tells someone nothing about what to type next."""
    assert "10 characters" in (A.password_problem("short") or "")
    assert A.password_problem("password1!") is not None      # on every list
    assert A.password_problem("aaaaaaaaaaaa") is not None    # too few distinct
    assert A.password_problem(GOOD) is None
    assert A.password_problem("x" * 500) is not None         # scrypt DoS


def test_a_giant_password_cannot_be_used_as_a_cpu_bomb():
    """scrypt on a 10MB string is free denial of service, one request."""
    assert A.MAX_PASSWORD <= 1000
    conn, _ = _db()
    assert A.create_user(conn, "e@example.com", "x" * 10_000)[0] == 400


# --- the data an account holds -----------------------------------------------
def test_the_four_sections_round_trip():
    conn, _ = _db()
    _, who = A.create_user(conn, "ethan@example.com", GOOD)
    A.save_sections(conn, who["id"], {
        "mybets": {"ts": 3, "data": {"rows": [], "deleted": []}},
        "fantasy": {"ts": 4, "data": {"user": "ethan"}},
        "bankroll": {"ts": 5, "data": {"bankroll": "500"}},
        "search": {"ts": 6, "data": [{"q": "mahomes", "ts": 1}]},
    })
    got = A.get_sections(conn, who["id"])
    assert set(got) == {"mybets", "fantasy", "bankroll", "search"}
    assert got["search"]["data"][0]["q"] == "mahomes"


def test_a_section_we_do_not_know_is_dropped_not_stored():
    """The section list is the schema. Letting a client invent names makes
    this table a free key-value store for anything anyone POSTs."""
    conn, _ = _db()
    _, who = A.create_user(conn, "ethan@example.com", GOOD)
    A.save_sections(conn, who["id"], {"whatever": {"ts": 1, "data": "x"}})
    assert A.get_sections(conn, who["id"]) == {}


def test_search_history_is_a_section_because_ethan_asked_for_it():
    assert "search" in A.SECTIONS
    assert '"search"' in SERVER or "'search'" in SERVER


def test_deleting_an_account_removes_everything():
    conn, _ = _db()
    _, who = A.create_user(conn, "ethan@example.com", GOOD)
    A.start_session(conn, who["id"])
    A.save_sections(conn, who["id"], {"search": {"ts": 1, "data": ["x"]}})
    A.delete_user(conn, who["id"])
    assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM user_data").fetchone()[0] == 0


def test_an_export_carries_no_secret():
    """An export is a file people mail around. It must not carry the two
    things that would let somebody else be them."""
    conn, _ = _db()
    _, who = A.create_user(conn, "ethan@example.com", GOOD)
    A.start_session(conn, who["id"])
    blob = json.dumps(A.export_user(conn, who["id"]))
    assert "verifier" not in blob and "scrypt$" not in blob
    assert "token" not in blob
    assert "ethan@example.com" in blob


# --- the wiring --------------------------------------------------------------
def test_the_cookie_is_httponly_and_samesite():
    """HttpOnly is what stops a page script — ours or an injected one —
    from reading the session. Without it an XSS bug is also a session
    theft."""
    i = SERVER.index("def _session_cookie(")
    body = SERVER[i:SERVER.index("\n    def ", i + 1)]
    assert "HttpOnly" in body and "SameSite=Lax" in body


def test_secure_is_set_when_and_only_when_the_request_was_https():
    """Unconditionally would make sign-in silently impossible over the
    plain-HTTP LAN address; never would let the cookie ride a cleartext
    request when there IS a TLS front."""
    i = SERVER.index("def _session_cookie(")
    body = SERVER[i:SERVER.index("\n    def ", i + 1)]
    assert "self._is_https()" in body and '"Secure"' in body
    j = SERVER.index("def _is_https(")
    assert "X-Forwarded-Proto" in SERVER[j:j + 900]


def test_the_token_is_never_put_in_a_response_body():
    """It goes in the cookie and nowhere else. HttpOnly is only a promise
    if we do not also hand the token to the page in JSON."""
    i = SERVER.index("def _account_post(")
    body = SERVER[i:SERVER.index("\n    def ", i + 1)]
    for line in body.splitlines():
        if "json.dumps" in line:
            assert "token" not in line, line


def test_the_browser_never_stores_the_password():
    """Typed, POSTed, cleared. A password in localStorage is a password on
    disk in the clear, which is the thing this whole file is about."""
    i = APP.index("window.acctAuth")
    body = APP[i:APP.index("\nwindow.acctChangePassword", i)]
    assert "localStorage.setItem" not in body
    assert '.value = ""' in body


def test_signing_out_calls_the_server():
    i = APP.index("window.acctSignOut")
    body = APP[i:APP.index("\n/* Boot", i)]
    assert "/api/account/logout" in body


def test_the_merge_is_shared_with_the_older_store_not_reimplemented():
    """Union by bet signature, tombstones, and a graded bet never
    un-settled by a stale pending copy. Two implementations of "never lose
    a logged bet" is one too many, and the second one is always the one
    that is wrong."""
    i = SERVER.index("def _account_post(")
    body = SERVER[i:SERVER.index("\n    def ", i + 1)]
    assert "merge_sections(" in body
    src = _read("engine", "accounts.py")
    assert "def _merge_mybets" not in src and "bet_sig" not in src


def test_an_anonymous_request_cannot_read_anybody_s_data():
    for path in ("data", "export"):
        i = SERVER.index("def _account_get(")
        body = SERVER[i:SERVER.index("\n    def ", i + 1)]
        assert 'sign in first' in body
    i = SERVER.index("def _account_post(")
    body = SERVER[i:SERVER.index("\n    def ", i + 1)]
    assert "sign in first" in body


def test_deleting_needs_the_password_again():
    i = SERVER.index("def _account_post(")
    body = SERVER[i:SERVER.index("\n    def ", i + 1)]
    d = body[body.index('if path == "delete"'):]
    assert "A.authenticate(" in d


# --- the rule that survived --------------------------------------------------
def test_we_still_do_not_ask_for_a_third_party_password():
    """The distinction the whole change turns on. Our own credential is
    scopable, rotatable and deletable by us; a DraftKings or ESPN one is
    none of those, which is why Yahoo went through OAuth and a private
    ESPN league is still refused."""
    for mod in ("espnfantasy.py", "yahoofantasy.py"):
        src = _read("engine", "sources", mod)
        for bad in ("Cookie:", "cookies=", "espn_s2=", '"password"'):
            assert bad not in src, f"{mod} reached for {bad!r}"


def test_the_docs_no_longer_claim_we_never_take_a_login():
    """Ethan: "go into our docs and shit where it say we will never store
    passwords ... because that is not true." A doc that states a rule the
    code broke is worse than no doc."""
    plat = _read("docs", "FANTASY_PLATFORMS.md")
    assert "the site never takes a login" not in plat
    assert "no longer true" in plat
    red = _read("docs", "REDESIGN_DECISIONS.md")
    assert "This site never holds money" not in red
    assert "will charge for access" in red


def test_the_docs_say_what_is_true_now():
    d = _read("docs", "ACCOUNTS.md")
    for must in ("scrypt", "email + password", "still never asked for",
                 "TLS", "Stripe"):
        assert must in d, must


def test_the_tls_gap_is_written_down_rather_than_left_to_be_discovered():
    """The server speaks plain HTTP. That was fine for a PIN on a LAN and
    is not fine for real passwords on the open internet, and the honest
    place for that is the doc rather than a surprise."""
    d = _read("docs", "ACCOUNTS.md")
    assert "cleartext" in d and "tailscale serve" in d.lower()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
