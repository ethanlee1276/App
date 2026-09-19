"""Discount codes — access granted without a payment.

Ethan, 2026-08-20: *"i also want a spot for discount codes. i want code
'USFARATHANE' to give you 100% off 1 year."*

A hundred-percent-off code means THERE IS NO PAYMENT, so it does not go
through the payment processor. Routing a zero-dollar transaction through
a merchant of record needs a live Paddle account (there is not one), a
price, a coupon and a webhook whose signature verifier is still flagged
UNVERIFIED — four ways for a free grant to fail in production for a
reason nobody can see. A grant involving no money writes an entitlement
directly, and Paddle stays what it is: the thing that handles money.

The useful consequence, and the reason this unblocks Ethan today: the
paywall can be switched ON before Paddle is live. Comp addresses and
codes are the two ways in, both under his hand.

What is defended here is mostly the abuse surface, because a code system
is a free-subscription generator with a lock on it and the lock is the
whole feature.

    python3 tests/test_redeem.py
"""

import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import redeem as RD

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = {"QB_CODES": "USFARATHANE:12:100, FRIENDS:1:2, SOLO:3:1"}


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _code_only(src: str) -> str:
    """Source with comments removed.

    Four tests across three files hit the same shape on 2026-08-20: a
    check for a mistake failing on the COMMENT that warns against the
    mistake. A rule that names what it forbids is the normal way to
    write one, so the scanner has to be the thing that adapts.
    """
    import re
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", " ", src)


def _db(users=6):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("CREATE TABLE users(id INTEGER PRIMARY KEY, email TEXT);")
    conn.executemany("INSERT INTO users(id,email) VALUES(?,?)",
                     [(i, f"u{i}@x.io") for i in range(1, users + 1)])
    RD.init(conn)
    return conn


# --- the code Ethan asked for -------------------------------------------------
def test_usfarathane_grants_a_full_year():
    conn = _db()
    got = RD.redeem(conn, 1, "USFARATHANE", env=ENV)
    assert got["months"] == 12
    days = (got["granted_to"] - time.time()) / 86400
    assert 360 <= days <= 370, f"a 12-month grant landed {days:.0f} days out"
    assert RD.active(conn, 1)


def test_the_code_is_typed_by_a_human_so_case_and_space_do_not_matter():
    conn = _db()
    RD.redeem(conn, 1, "  usfarathane  ", env=ENV)
    assert RD.active(conn, 1)


def test_no_money_is_involved_anywhere_in_the_grant():
    """The whole design claim. If this module ever imports the processor,
    a free grant has acquired a dependency on a live Paddle account and
    on a signature verifier flagged UNVERIFIED.

    CHECKED AS IMPORTS, not as text: the module's own docstring explains
    at length why it does not use Paddle, and a substring search fails on
    the explanation rather than on the mistake. (Third time this shape has
    bitten a test today; imports are the thing that actually matters.)
    """
    import ast
    tree = ast.parse(_read("engine", "redeem.py"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
            names.update(a.name for a in node.names)
    for bad in ("paddle", "stripe", "billing", "requests", "urllib", "http"):
        assert bad not in names, f"the redemption path imports {bad!r}"
    # Standard library only, as the module claims.
    assert names <= {"os", "re", "time", "annotations", "__future__"}, \
        f"unexpected dependencies: {sorted(names)}"


# --- the four abuses ----------------------------------------------------------
def test_a_code_cannot_be_redeemed_twice_by_one_account():
    """Otherwise a twelve-month code is an infinite-year code, typed
    repeatedly. Enforced by a PRIMARY KEY rather than a check, because a
    check races with itself under two simultaneous requests."""
    conn = _db()
    RD.redeem(conn, 1, "USFARATHANE", env=ENV)
    try:
        RD.redeem(conn, 1, "USFARATHANE", env=ENV)
        assert False, "redeemed the same code twice"
    except RD.RedeemError as exc:
        assert "already" in str(exc).lower()
    src = _read("engine", "redeem.py")
    assert "PRIMARY KEY (code, user_id)" in src, \
        "the one-per-account rule is a check that can be raced"


def test_a_shared_code_stops_at_its_cap():
    conn = _db()
    RD.redeem(conn, 1, "FRIENDS", env=ENV)
    RD.redeem(conn, 2, "FRIENDS", env=ENV)          # cap is 2
    try:
        RD.redeem(conn, 3, "FRIENDS", env=ENV)
        assert False, "the third redemption walked past a cap of two"
    except RD.RedeemError:
        pass


def test_guessing_is_rate_limited_and_answers_are_indistinguishable():
    """A fast "no such code" and a slow "used up" together enumerate live
    codes. Both get the same sentence, and the guesses run out."""
    conn = _db()
    RD.redeem(conn, 1, "SOLO", env=ENV)             # cap is 1, now spent
    spent = used = None
    try:
        RD.redeem(conn, 2, "SOLO", env=ENV)
    except RD.RedeemError as exc:
        spent = str(exc)
    try:
        RD.redeem(conn, 2, "NOSUCHCODE", env=ENV)
    except RD.RedeemError as exc:
        used = str(exc)
    assert spent == used, \
        f"a used-up code and an unknown code are told apart: {spent!r} vs {used!r}"
    last = ""
    for i in range(RD.MAX_ATTEMPTS + 4):
        try:
            RD.redeem(conn, 4, f"WRONG{i}", env=ENV)
        except RD.RedeemError as exc:
            last = str(exc)
    assert "Too many" in last, "a code can be brute-forced without limit"


def test_a_lapsed_grant_cannot_be_renewed_by_retyping_the_code():
    """The grant is an absolute date, and re-redeeming is refused whether
    or not it has run out — otherwise one code is a subscription that
    renews itself forever."""
    conn = _db()
    RD.redeem(conn, 1, "SOLO", env=ENV)
    conn.execute("UPDATE code_redemptions SET granted_to=? WHERE user_id=1",
                 (time.time() - 10,))
    conn.commit()
    assert not RD.active(conn, 1), "an expired grant still reads as active"
    try:
        RD.redeem(conn, 1, "SOLO", env=ENV)
        assert False, "an expired code was renewed by retyping it"
    except RD.RedeemError:
        pass


def test_two_codes_are_the_furthest_date_not_the_sum():
    """"You hold a grant to March and a grant to June" reads as covered
    until June. Summing them would let a pile of one-month codes stack
    into years."""
    conn = _db()
    a = RD.redeem(conn, 1, "FRIENDS", env=ENV)      # 1 month
    b = RD.redeem(conn, 1, "USFARATHANE", env=ENV)  # 12 months
    assert RD.granted_until(conn, 1) == max(a["granted_to"], b["granted_to"])


# --- where codes come from ----------------------------------------------------
def test_codes_are_defined_in_the_environment_not_the_database():
    """Nothing reachable from the web may mint access. A table of codes
    with an admin endpoint is one authentication bug away from an
    unlimited free-subscription generator; an environment variable cannot
    be written by an HTTP request at all — the same reasoning that put
    the comp list in QB_COMP_EMAILS."""
    src = _read("engine", "redeem.py")
    assert 'ENV_CODES = "QB_CODES"' in src
    for bad in ("INSERT INTO codes", "CREATE TABLE IF NOT EXISTS codes"):
        assert bad not in src, "codes are stored somewhere writable"
    server = _read("server.py")
    assert "QB_CODES" not in server, \
        "the server writes or reads the catalogue directly instead of via redeem"


def test_a_malformed_entry_drops_itself_and_not_the_endpoint():
    """Parsed per request off a hand-typed list. One typo must not take
    redemption down for every other code in it."""
    got = RD.catalogue({"QB_CODES": "GOOD:6:5, ,BAD, WORSE:x:1, "
                                    "TOOLONG:999:1, OK2:1"})
    assert set(got) == {"GOOD", "OK2"}, got
    assert got["OK2"]["max_uses"] == 0          # no cap given means no cap


# --- the wiring ---------------------------------------------------------------
def test_a_redeemed_code_entitles_without_the_processor():
    server = _read("server.py")
    body = server[server.index("def _entitled"):][:2200]
    assert "RD.active(" in body, "a redeemed code does not grant access"
    assert body.index("RD.active(") < body.index("BI.status_for"), \
        "codes are checked after the processor, so they need it to be up"


def test_the_code_box_survives_an_unconfigured_processor():
    """The old panel returned early when Paddle was unconfigured and took
    everything with it. Codes involve no processor, and while Paddle is
    still being set up they are the ONLY way in — which is exactly the
    state the site is in today."""
    app = _read("web", "js", "app.js")
    fn = app[app.index("async function renderBilling("):]
    fn = fn[:fn.index("\n/* \"Have a code?\"")]
    assert "codeBoxHTML(" in fn
    head = fn[:fn.index("codeBoxHTML(")]
    # THE PROPERTY IS NOT "no early returns" — three are correct and
    # necessary (no slot, the fetch failed, nobody is signed in). It is
    # that none of them is conditioned on the PROCESSOR being set up,
    # which is what the removed one did.
    for line in _code_only(head).splitlines():
        if "return" not in line:
            continue
        assert "configured" not in line, \
            f"an unconfigured processor still short-circuits the panel: {line.strip()[:70]}"
    assert "s.configured ?" in head, \
        "the subscribe controls no longer depend on the processor either, " \
        "which means they render pointing at nothing"


def test_redemption_requires_an_account():
    """A grant has to attach to somebody, one-per-account needs an
    account to be per, and the rate limiter needs a subject to count. An
    anonymous redemption is an unlimited redemption."""
    server = _read("server.py")
    fn = server[server.index("def _billing_redeem"):]
    fn = fn[:fn.index("\n    def _billing_post")]
    assert "401" in fn and "if not who" in fn


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
