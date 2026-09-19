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
#: The whole refusal message, from its assignment to the closing paren.
_INSECURE = SERVER[SERVER.index("_INSECURE_LOGIN = ("):]
_INSECURE = _INSECURE[:_INSECURE.index('before starting the server.)"') + 30]


def _db():
    d = tempfile.mkdtemp()
    return A.connect(os.path.join(d, "acc.db")), os.path.join(d, "acc.db")


# --- what is on disk ---------------------------------------------------------
def test_the_password_is_not_in_the_database_in_any_readable_form():
    """THE ONE THAT MATTERS. "Storing a password" means storing a one-way
    function of it; anything else means a copy of this file is a copy of
    everybody's password, including the one they also used on their bank."""
    conn, path = _db()
    A.create_user(conn, "ethan@example.com", GOOD, confirmed=True)
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
    A.create_user(conn, "ethan@example.com", GOOD, confirmed=True)
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
    A.create_user(conn, "ethan@example.com", GOOD, confirmed=True)

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
    A.create_user(conn, "ethan@example.com", GOOD, confirmed=True)
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
    A.create_user(conn, "ethan@example.com", GOOD, confirmed=True)
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
    _, who = A.create_user(conn, "ethan@example.com", GOOD, confirmed=True)
    token = A.start_session(conn, who["id"])
    conn.commit()
    assert token.encode() not in open(path, "rb").read()
    assert A.session_user(conn, token)["email"] == "ethan@example.com"


def test_a_token_nobody_issued_is_not_a_session():
    conn, _ = _db()
    _, who = A.create_user(conn, "ethan@example.com", GOOD, confirmed=True)
    A.start_session(conn, who["id"])
    assert A.session_user(conn, "made-up") is None
    assert A.session_user(conn, "") is None
    assert A.session_user(conn, None) is None


def test_an_expired_session_stops_working():
    conn, _ = _db()
    _, who = A.create_user(conn, "ethan@example.com", GOOD, confirmed=True)
    token = A.start_session(conn, who["id"])
    conn.execute("UPDATE sessions SET expires_at=?", (time.time() - 1,))
    conn.commit()
    assert A.session_user(conn, token) is None


def test_signing_out_ends_it_on_the_server():
    """Forgetting a cookie locally is not signing out — the session is
    still valid for whoever else has it."""
    conn, _ = _db()
    _, who = A.create_user(conn, "ethan@example.com", GOOD, confirmed=True)
    token = A.start_session(conn, who["id"])
    A.end_session(conn, token)
    assert A.session_user(conn, token) is None


def test_changing_the_password_signs_out_every_device():
    """A password change is usually an answer to "somebody else may have
    this". Leaving their session alive answers it with nothing."""
    conn, _ = _db()
    _, who = A.create_user(conn, "ethan@example.com", GOOD, confirmed=True)
    theirs = A.start_session(conn, who["id"])
    assert A.change_password(conn, who["id"], GOOD, "a-brand-new-passphrase")[0] == 200
    assert A.session_user(conn, theirs) is None
    assert A.authenticate(conn, "ethan@example.com", "a-brand-new-passphrase")[0] == 200
    assert A.authenticate(conn, "ethan@example.com", GOOD)[0] == 403


def test_the_old_password_is_required_to_change_it():
    conn, _ = _db()
    _, who = A.create_user(conn, "ethan@example.com", GOOD, confirmed=True)
    assert A.change_password(conn, who["id"], "not-it-at-all", "x" * 12)[0] == 403


# --- the two strings we accept -----------------------------------------------
def test_email_case_does_not_create_a_second_account():
    conn, _ = _db()
    assert A.create_user(conn, "Ethan@Example.COM", GOOD, confirmed=True)[0] == 200
    assert A.create_user(conn, "ethan@example.com", GOOD, confirmed=True)[0] == 409
    assert A.authenticate(conn, "  ETHAN@example.com ", GOOD)[0] == 200


def test_dots_and_plus_tags_are_left_alone():
    """Gmail treats them as noise; most providers do not. An app that
    "helpfully" strips them decides two different people are one account,
    which is a worse failure than a duplicate signup."""
    conn, _ = _db()
    assert A.create_user(conn, "a.b@example.com", GOOD, confirmed=True)[0] == 200
    assert A.create_user(conn, "ab@example.com", GOOD, confirmed=True)[0] == 200
    assert A.create_user(conn, "a.b+tag@example.com", GOOD, confirmed=True)[0] == 200


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
    assert A.create_user(conn, "e@example.com", "x" * 10_000, confirmed=True)[0] == 400


# --- the data an account holds -----------------------------------------------
def test_the_four_sections_round_trip():
    conn, _ = _db()
    _, who = A.create_user(conn, "ethan@example.com", GOOD, confirmed=True)
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
    _, who = A.create_user(conn, "ethan@example.com", GOOD, confirmed=True)
    A.save_sections(conn, who["id"], {"whatever": {"ts": 1, "data": "x"}})
    assert A.get_sections(conn, who["id"]) == {}


def test_search_history_is_a_section_because_ethan_asked_for_it():
    assert "search" in A.SECTIONS
    assert '"search"' in SERVER or "'search'" in SERVER


def test_deleting_an_account_removes_everything():
    conn, _ = _db()
    _, who = A.create_user(conn, "ethan@example.com", GOOD, confirmed=True)
    A.start_session(conn, who["id"])
    A.save_sections(conn, who["id"], {"search": {"ts": 1, "data": ["x"]}})
    A.delete_user(conn, who["id"])
    assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM user_data").fetchone()[0] == 0


def test_the_database_path_does_not_follow_the_working_directory():
    """Where the accounts live must not depend on where you stood.

    `DB_PATH` was `Path("data") / "accounts.db"` — relative. Start the
    server from anywhere but the repo root and SQLite happily creates a
    second, empty accounts database: every user apparently gone, new
    signups landing in a file that is on no backup list and that nobody
    would think to look for. Found by doing exactly that from a scratch
    directory while testing something else. ledger.py and db.py both
    anchor to the repo; this was the one that did not.
    """
    from pathlib import Path
    assert A.DB_PATH.is_absolute()
    assert A.DB_PATH == Path(ROOT) / "data" / "accounts.db"

    # And prove it, rather than trusting the constant: resolve it from a
    # directory that is not the repo.
    cwd = os.getcwd()
    try:
        os.chdir(tempfile.mkdtemp())
        assert str(A.DB_PATH).startswith(ROOT)
        assert not os.path.exists(os.path.join(os.getcwd(), "data"))
    finally:
        os.chdir(cwd)


def test_deleting_an_account_takes_the_stripe_link_with_it():
    """"Delete everything" has to include the billing row.

    `subscriptions.user_id` carries ON DELETE CASCADE, so with
    `PRAGMA foreign_keys=ON` — which `connect()` sets — this already
    worked. The pragma is per-connection and off by default, though, and
    the row holds a Stripe customer_id: a pointer to a real person's name
    and card, sitting in our database after they asked to be forgotten.
    So the delete names the table instead of trusting the pragma, and this
    proves it by deleting through a connection that never set it.
    """
    import sqlite3
    from pathlib import Path
    from engine import billing as B
    path = Path(tempfile.mkdtemp()) / "acc.db"
    conn = A.connect(path)
    B.init(conn)
    _, who = A.create_user(conn, "ethan@example.com", GOOD, confirmed=True)
    conn.execute("INSERT INTO subscriptions (user_id, customer_id, "
                 "subscription_id, status, period_end, updated_at) "
                 "VALUES (?,?,?,?,?,?)",
                 (who["id"], "cus_live", "sub_live", "active", 4e9, 1.0))
    conn.commit()
    conn.close()

    raw = sqlite3.connect(str(path))          # deliberately no pragma
    assert raw.execute("PRAGMA foreign_keys").fetchone()[0] == 0
    A.delete_user(raw, who["id"])
    assert raw.execute("SELECT COUNT(*) FROM subscriptions").fetchone()[0] == 0
    assert raw.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0


def test_deleting_works_on_a_database_billing_never_touched():
    """Most installs never run Stripe, so `subscriptions` does not exist.
    Naming a missing table in a DELETE is a hard error, which would break
    deletion for everyone to protect a table nobody has."""
    conn, _ = _db()
    _, who = A.create_user(conn, "ethan@example.com", GOOD, confirmed=True)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "subscriptions" not in tables
    A.delete_user(conn, who["id"])
    assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0


def test_an_export_carries_no_secret():
    """An export is a file people mail around. It must not carry the two
    things that would let somebody else be them."""
    conn, _ = _db()
    _, who = A.create_user(conn, "ethan@example.com", GOOD, confirmed=True)
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
    # THE FUNCTION, not everything between it and the next one with a
    # similar name. That slice ran 60,000 characters and swept in whatever
    # happened to be declared in between, so the first unrelated
    # localStorage write to land there failed a test about passwords.
    i = APP.index("window.acctAuth")
    depth, seen, body = 0, False, None
    for j in range(APP.index("{", i), len(APP)):
        if APP[j] == "{":
            depth += 1
            seen = True
        elif APP[j] == "}":
            depth -= 1
            if seen and depth == 0:
                body = APP[i:j + 1]
                break
    assert body and len(body) < 6000, "acctAuth was not bracketed correctly"
    assert "localStorage" not in body
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


# --- the transport ----------------------------------------------------------
#
# THE HASHING DOES NOTHING FOR THIS, which is the whole reason it needed a
# guard of its own. scrypt protects the password at rest; a password typed
# into a plain-HTTP page has already crossed the network readable before it
# ever reaches the hash, and anyone on that Wi-Fi has it — for this site
# and for wherever else it was reused.
def test_a_password_cannot_cross_a_cleartext_network_by_default():
    i = SERVER.index("def _password_transport_ok(")
    body = SERVER[i:SERVER.index("\n    def ", i + 1)]
    assert "_transport_is_cleartext()" in body
    j = SERVER.index("PASSWORD_PATHS = ")
    paths = SERVER[j:j + 200]
    for p in ("signup", "login", "password", "delete"):
        assert p in paths, p
    k = SERVER.index("def _account_post(")
    post = SERVER[k:SERVER.index("\n    def ", k + 1)]
    assert "self.PASSWORD_PATHS" in post and "_password_transport_ok()" in post


def test_loopback_is_not_treated_as_a_network():
    """http://localhost crosses nothing. Refusing it would break the way
    this app is actually used and buy exactly no safety."""
    i = SERVER.index("def _transport_is_cleartext(")
    body = SERVER[i:SERVER.index("\n    def ", i + 1)]
    assert "_local_only()" in body and "_is_https()" in body


def test_a_tailnet_is_not_treated_as_cleartext():
    """Ethan, 2026-08-15, uses `http://100.87.149.86:8000` from his phone.

    `http://` OVER A TAILNET IS NOT CLEARTEXT. Tailscale is WireGuard —
    packets are encrypted device-to-device before they touch any network,
    so the scheme in the address bar describes the last inch rather than
    the wire. The first cut of this guard refused that connection, which
    was a false positive on a genuinely private link and worse than
    useless in practice: the way round it is QB_ALLOW_INSECURE_LOGIN=1,
    which disables the check EVERYWHERE, including the coffee shop.

    BOTH ENDS have to be in the range. `100.64.0.0/10` is RFC 6598 shared
    space — Tailscale uses it and so do some ISPs for carrier-grade NAT —
    so a client address there proves nothing alone. Requiring our own
    socket to be a tailnet address too means the packet arrived on the
    tailnet interface."""
    import ipaddress
    i = SERVER.index("def _via_tailnet(")
    body = SERVER[i:SERVER.index("\n    def ", i + 1)]
    assert "100.64.0.0/10" in body
    assert "fd7a:115c:a1e0::/48" in body, "IPv6 tailnet addresses are missed"
    assert "getsockname()" in body, "only the client end is being checked"
    assert "inside(peer) and inside(mine)" in body
    # The address Ethan actually uses.
    assert (ipaddress.ip_address("100.87.149.86")
            in ipaddress.ip_network("100.64.0.0/10"))
    # …and it feeds the cleartext decision.
    j = SERVER.index("def _transport_is_cleartext(")
    ct = SERVER[j:SERVER.index("\n    def ", j + 1)]
    assert "_via_tailnet()" in ct


def test_the_tailnet_carve_out_states_its_own_limit():
    """A network that really did put both machines inside 100.64.0.0/10
    would read as a tailnet here. Narrow, but real, and an exception
    nobody wrote down gets "fixed" later by someone who does not know it
    was a choice."""
    i = SERVER.index("def _via_tailnet(")
    body = SERVER[i:SERVER.index("\n    def ", i + 1)]
    assert "carrier-grade NAT" in body
    assert "narrow shape" in body or "narrow" in body


def test_the_refusal_names_the_fix():
    """"Insecure connection" on its own leaves someone with nowhere to go."""
    assert "tailscale serve" in _INSECURE
    assert "QB_ALLOW_INSECURE_LOGIN" in _INSECURE
    assert "computer running the server" in _INSECURE


def test_the_override_removes_the_refusal_and_not_the_risk():
    """`insecure` is a fact about the wire and stays true under the
    override. Reporting a private connection because somebody set an
    environment variable would be the page telling a comfortable lie."""
    i = SERVER.index("def _transport_is_cleartext(")
    body = SERVER[i:SERVER.index("\n    def ", i + 1)]
    assert "QB_ALLOW_INSECURE_LOGIN" not in body, \
        "the override leaked into the statement of fact"
    j = SERVER.index('if path == "me"')
    me = SERVER[j:j + 500]
    assert '"insecure": self._transport_is_cleartext()' in me
    assert '"allowed": self._password_transport_ok()' in me


def test_the_page_warns_before_the_password_is_typed():
    """A refusal arrives too late to help: by then it is in the box, and
    on a phone it is already in the keyboard's suggestion history."""
    i = APP.index("function acctSignInHTML")
    body = APP[i:APP.index("\nwindow.acctAuth", i)]
    assert "_acctUser.insecure" in body or "insecure" in body
    # It used to assert the copy printed `tailscale serve --bg 8000`,
    # which is an instruction only the operator can act on and came off
    # the public site on 2026-08-23. What a reader needs is the same
    # thing it was there to give them: somewhere safe to sign in instead
    # of a dead end.
    assert "https" in body, "the warning refuses without offering a way through"
    assert "tailscale" not in body and "python3" not in body
    # And the warning still shows when the override is on, worded for it.
    assert "_acctUser.allowed" in body
    assert "not the risk" in body


def test_the_card_repaints_once_the_server_has_answered():
    """THE TIMING BUG THIS FILE ALMOST MISSED.

    `_acctUser` arrives 1.5s after the card first draws, so the warning
    cannot be in the first paint — the card has to be redrawn when the
    answer lands. The first cut redrew only when signed IN, which left the
    signed-OUT card exactly as it was: and the signed-out card is the one
    carrying the warning. The warning was invisible in precisely the case
    it exists for.

    Every source-level check above passed the whole time, because the
    string was present and only the ORDER was wrong. It was found by
    opening the LAN address in a browser. This test pins the repaint as
    unconditional; the browser check is what pins the result."""
    i = APP.index("await acctWho(true)")
    body = APP[i:i + 900]
    repaint = body.index("renderMyBets()")
    guard = body.find("signed_in")
    assert guard == -1 or guard > repaint, \
        "the repaint is behind a signed-in check again"


def test_reads_are_not_blocked_by_the_guard():
    """Only the password paths are refused. Blocking reads would break a
    phone on the LAN for no gain — the session cookie is a different and
    smaller exposure than a reused password, and that is Ethan's call to
    make with the override."""
    i = SERVER.index("def _account_post(")
    post = SERVER[i:SERVER.index("\n    def ", i + 1)]
    guard = post[post.index("PASSWORD_PATHS") if "PASSWORD_PATHS" in post else 0:]
    assert '"data"' not in guard.split("\n")[0]
    j = SERVER.index("PASSWORD_PATHS = ")
    assert '"data"' not in SERVER[j:j + 200]
    assert '"logout"' not in SERVER[j:j + 200]


def test_the_tls_gap_is_written_down_rather_than_left_to_be_discovered():
    """The server speaks plain HTTP. That was fine for a PIN on a LAN and
    is not fine for real passwords on the open internet, and the honest
    place for that is the doc rather than a surprise."""
    d = _read("docs", "ACCOUNTS.md")
    assert "cleartext" in d and "tailscale serve" in d.lower()



# --- the age and terms acknowledgment ----------------------------------------
def test_signup_requires_the_age_and_terms_confirmation():
    """Recorded SERVER-SIDE with a timestamp, not trusted to a
    localStorage flag. A flag in the browser proves nothing later, and
    "did this person agree" is exactly the question that gets asked when
    it matters."""
    conn, _ = _db()
    code, out = A.create_user(conn, "new@example.com", GOOD)
    assert code == 400 and "21 or older" in out["error"]
    code, who = A.create_user(conn, "new@example.com", GOOD, confirmed=True)
    assert code == 200
    row = conn.execute("SELECT age_confirmed, terms_accepted_at FROM users "
                       "WHERE id=?", (who["id"],)).fetchone()
    assert row["age_confirmed"] == 1
    assert row["terms_accepted_at"] and row["terms_accepted_at"] > 0


def test_the_migration_adds_columns_to_a_database_that_predates_them():
    """THE FIRST REAL MIGRATION, and the pattern matters more than these
    two columns. `CREATE TABLE IF NOT EXISTS` covers a new TABLE and does
    nothing for a new COLUMN — so a deployed accounts.db would keep its
    old shape while the code expected the new one, and the failure lands
    on a live account rather than in a test."""
    import sqlite3, tempfile, os
    p = os.path.join(tempfile.mkdtemp(), "old.db")
    c = sqlite3.connect(p)
    c.executescript(
        "CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT NOT NULL "
        "UNIQUE, verifier TEXT NOT NULL, created_at REAL NOT NULL, "
        "last_seen REAL);")
    c.execute("INSERT INTO users (email, verifier, created_at) "
              "VALUES ('old@x.com','scrypt$x',1)")
    c.commit(); c.close()
    conn = A.connect(p)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    assert {"age_confirmed", "terms_accepted_at"} <= cols
    # …and the row that was already there is untouched.
    assert conn.execute("SELECT email FROM users").fetchone()[0] == "old@x.com"


def test_the_migration_is_additive_only():
    """Once other people's data is in here, a destructive migration needs
    a written plan and a fresh backup — not a line in this function."""
    src = _read("engine", "accounts.py")
    body = src[src.index("def _migrate("):]
    body = body[:body.index("\n\n\n")]
    for destructive in ("DROP ", "DELETE FROM", "TRUNCATE", "ALTER TABLE users RENAME"):
        assert destructive not in body.upper().replace("DROPPING", ""), destructive
    assert "ADD COLUMN" in body


def test_the_sign_in_form_does_not_re_ask_returning_users():
    """Asking somebody to re-tick an acknowledgment every time they sign
    in trains them to tick it without reading, which is the opposite of
    what an acknowledgment is for."""
    i = APP.index("window.acctAuth")
    body = APP[i:APP.index("\nwindow.acctChangePassword", i)]
    assert 'mode === "signup" && !confirmed' in body


def test_the_documents_exist_and_are_no_longer_drafts():
    """They carried a DRAFT banner while the counterparty and the contact
    address were blank, which was right at the time: publishing an
    unfinished contract as finished would have been the worse error.

    COMPLETED 2026-08-22, once Ethan supplied both. The banner went with
    them, and not as tidying: a live binding contract headed "DRAFT — not
    yet reviewed by a lawyer" invites the argument that nothing on the
    page was meant to bind anybody, on the one page whose whole job is to
    bind. That an attorney has still not read the judgement clauses is
    true and is tracked in `--todo`, where an internal action item
    belongs.

    tests/test_legal_pages.py owns the detail — what each document has to
    cover, who the counterparty is, and that the addresses are real. This
    only checks the pages exist and are not calling themselves drafts."""
    for page in ("terms.html", "privacy.html"):
        doc = _read("web", page)
        assert "Last updated" in doc, "%s is not a dated document" % page
        assert "DRAFT" not in doc, "%s still calls itself a draft" % page
        assert "not yet reviewed by a lawyer" not in doc


def test_the_privacy_policy_matches_what_is_actually_stored():
    """Most privacy policies are wrong because nobody asks the engineers.
    Every section this app stores has to appear, and the two things it
    deliberately does NOT hold have to be stated."""
    doc = _read("web", "privacy.html")
    for section in ("bet log", "fantasy", "bankroll", "search"):
        assert section in doc.lower(), section
    assert "one-way scramble" in doc or "scrypt" in doc
    assert "sportsbook password" in doc.lower()
    assert "Card numbers" in doc
    # AND THE CONTROLS IT PROMISES ARE ONES THAT EXIST — checked against
    # app.js rather than against a list typed here, because that is the
    # failure mode: the policy names a button, the button gets renamed,
    # and the policy keeps promising a control nobody can find. This test
    # itself named "Download everything" and "Delete everything" for
    # weeks after the buttons became "Download my data" and "Delete my
    # account", and passed the whole time, because it only ever compared
    # the policy against itself.
    app = _read("web", "js", "app.js")
    for control in ("Download my data", "Clear search history"):
        assert control in app, \
            f"the policy names a control that is not in the app: {control}"
        assert control in doc, \
            f"the app has a {control!r} button the policy does not mention"


def test_a_subscribed_account_is_asked_to_cancel_before_it_can_be_deleted():
    """Deletion is the one action that can cost somebody money afterwards.

    `delete_user` clears our `subscriptions` row; Stripe never hears about
    it. The card keeps being charged on schedule and the row that said
    whose card it was is gone — a charge the person cannot place and a
    payment we cannot refund to an account. So the server refuses with 409
    while the subscription is live, and says why.

    Refused states are the entitled ones, `past_due` and `trialing`
    included: both still have something live at Stripe. Nobody is trapped
    — cancelling is a button on the same card, and it flips the status
    through the webhook.
    """
    src = SERVER[SERVER.index("def _live_subscription("):]
    src = src[:src.index("\n    # --- billing")]
    assert "entitled" in src
    block = SERVER[SERVER.index('if path == "delete"'):]
    block = block[:block.index("A.delete_user(")]
    assert "409" in block and "_live_subscription" in block
    # It must not be able to block deletion by throwing: a bug in code
    # that is switched off would otherwise hold somebody's data hostage.
    assert "except Exception" in src and 'return ""' in src


def test_the_delete_button_stops_claiming_every_failure_is_a_bad_password():
    """The client turned any non-200 from /api/account/delete into "Wrong
    password." — a guess dressed as a diagnosis. A subscribed account is
    refused for an entirely different reason and the person has to be told
    which one, or they retype a correct password until they give up."""
    body = APP[APP.index("window.acctDelete ="):]
    body = body[:body.index("\n};")]
    # Comments out: this function explains the old behaviour in prose, and
    # a grep that matches its own explanation proves nothing.
    code = "\n".join(l for l in body.splitlines()
                     if not l.strip().startswith(("//", "*", "/*")))
    assert "j.error" in code, "the server's message is not surfaced"
    assert code.count('"Wrong password."') == 1, "still hardcoding the reason"
    # The fallback has to sit BEFORE the server's message wins, not after.
    assert code.index('"Wrong password."') < code.index("j.error")


def test_the_privacy_policy_admits_that_backups_outlive_deletion():
    """"Delete everything" is true of the live site and not of the archives.

    The weekly backup now includes accounts.db — it has to, or one failed
    disk erases the records of every user who did NOT ask to be deleted.
    The cost is that a deleted account survives in up to BACKUP_KEEP
    weekly archives, and a policy that says "gone" while six copies sit in
    data/backups/ is the same kind of false claim Ethan told us to go
    find and fix.

    The number is pinned to the constant, so raising the retention makes
    this fail rather than making the policy quietly wrong.
    """
    from engine import maintenance
    doc = _read("web", "privacy.html")
    assert "backup" in doc.lower()
    weeks = maintenance.BACKUP_KEEP * maintenance.BACKUP_EVERY_DAYS / 7
    assert weeks == 6, "retention changed — the privacy page says six weeks"
    assert "six weeks" in doc.lower()


def test_the_terms_say_the_thing_that_makes_this_lawful_to_run():
    doc = _read("web", "terms.html")
    assert "We do not take bets" in doc
    assert "1-800-GAMBLER" in doc
    assert "21" in doc


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
