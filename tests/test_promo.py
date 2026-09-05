"""Checkout discount codes.

A percentage off a real subscription cannot be expressed by the grants in
`engine/redeem.py` — those hand out free months with no payment, which is
why they never touch a processor. So a discount is a Stripe Coupon plus a
Promotion Code, typed into Stripe's own checkout box.

TWO THINGS THESE TESTS EXIST FOR.

*The codes are secrets and this repository is public.* Ethan, 2026-08-22:
"we do not want to display to people that code is a thing. its a secret
promo code i will only be givving my friends." A code in a source file, a
docstring, a test fixture or a commit message is a code on the open
internet — so they live in the environment, and nothing the site serves
ever names one. No real code appears in this file either; every test
below builds its own.

*A discount offered on the wrong plan is worth real money.* All three
plans are Prices on one Stripe Product, so a coupon offered at checkout
applies to whatever is in the cart, and a 2-month discount against the
yearly price is 75% off a whole year.

Run directly: `python3 tests/test_promo.py`
"""

import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import billing as BI
from engine import redeem as RD

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: A fixture, not a real code. Named so that finding this string in a
#: server response or a page is unambiguously a leak.
FAKE = "ZZTESTONLY"
ENV = {"QB_PROMOS": f"{FAKE}:75:2:monthly:25"}


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _with_promo(fn):
    """Run `fn` with the fixture promo in the real environment.

    Some paths (checkout_request) read os.environ directly, because in
    production they must — the code is configured on the box, not passed
    around.
    """
    before = os.environ.get("QB_PROMOS")
    os.environ["QB_PROMOS"] = ENV["QB_PROMOS"]
    try:
        return fn()
    finally:
        if before is None:
            os.environ.pop("QB_PROMOS", None)
        else:
            os.environ["QB_PROMOS"] = before


# --- the secret ---------------------------------------------------------------
def test_no_promo_code_is_written_into_the_source():
    """The whole point. A code committed here is a code on GitHub."""
    live = BI.promos()
    assert live == {} or os.environ.get("QB_PROMOS"), \
        "promos() returned codes with QB_PROMOS unset — they are hardcoded"
    for part in (("engine", "billing.py"), ("engine", "stripeset.py"),
                 ("web", "js", "app.js"), ("server.py",)):
        text = _read(*part)
        assert "QB_PROMOS" in text or "promo" in text.lower()  # sanity
        assert FAKE not in text


def test_unset_means_no_codes_and_no_box():
    """The right default for a public repo: nothing to guess, and Stripe
    renders no promo field at all."""
    assert BI.promos({}) == {}
    assert BI.promos_for("monthly", {}) == []
    before = os.environ.pop("QB_PROMOS", None)
    try:
        _url, _h, body = BI.checkout_request(
            "sk_test_x", "price_x", 7, "a@b.c", "https://s", "https://c",
            plan_id="monthly")
        assert b"allow_promotion_codes" not in body
    finally:
        if before is not None:
            os.environ["QB_PROMOS"] = before


def test_the_public_status_endpoint_names_no_code():
    """/api/billing/status renders the plans page BEFORE anybody signs
    in, so anything in it is readable by anyone with a network tab. It
    used to send the codes so the page could advertise them; a secret
    code cannot be advertised."""
    srv = _read("server.py")
    body = srv[srv.index("def _billing_get("):]
    body = body[:body.index("\n    def ", 1)]
    assert 'out["promos"]' not in body, "the status endpoint leaks the codes"
    assert "promos_for" not in body and "promo_named" not in body


def test_the_pages_name_no_code():
    """Nothing the browser receives may name one — not the plan cards,
    not the checkout panel."""
    app = _read("web", "js", "app.js")
    assert "_coPromoNote" not in app, "the checkout page advertises a code"
    assert ".promos" not in app, "app.js still reads promos off the status"
    assert "promo code box" not in app.lower()


def test_there_is_no_helper_left_whose_job_was_to_advertise_one():
    assert not hasattr(BI, "promo_blurb"), \
        "promo_blurb existed only to print a code on a plan card"


# --- parsing ------------------------------------------------------------------
def test_a_promo_is_read_from_the_environment():
    got = BI.promos(ENV)[FAKE]
    assert got["percent_off"] == 75
    assert got["duration"] == "repeating"
    assert got["duration_in_months"] == 2
    assert got["plans"] == ("monthly",)
    assert got["max_redemptions"] == 25


def test_codes_are_matched_however_they_are_typed():
    """Read off a phone screen and typed by hand."""
    for typed in (FAKE.lower(), f"  {FAKE.title()} ", FAKE):
        assert BI.promo_named(typed, ENV), typed
    assert BI.promo_named(FAKE + "S", ENV) is None
    assert BI.promo_named("", ENV) is None


def test_a_malformed_entry_drops_itself_and_not_the_buy_button():
    """Parsed on the checkout path, so one typo must not take payment
    down for everything else in the list."""
    env = {"QB_PROMOS": f"BAD:200:2:monthly, JUNK, {FAKE}:50:1:yearly"}
    got = BI.promos(env)
    assert set(got) == {FAKE}, got
    assert got[FAKE]["plans"] == ("yearly",)


def test_a_hundred_percent_off_is_refused():
    """That is a free subscription wearing a discount's clothes, it is
    what QB_CODES is for, and it does not need a card."""
    assert BI.promos({"QB_PROMOS": f"{FAKE}:100:2:monthly"}) == {}
    assert BI.promos({"QB_PROMOS": f"{FAKE}:0:2:monthly"}) == {}


def test_an_unknown_plan_name_is_not_silently_a_code_for_everything():
    assert BI.promos({"QB_PROMOS": f"{FAKE}:75:2:platinum"}) == {}


def test_a_code_that_cannot_survive_the_format_is_never_offered():
    """A comma separates entries and a colon separates fields, so a code
    containing either cannot round-trip — it would silently become a
    DIFFERENT code, and Ethan would hand friends a string that does not
    work. A code with a space cannot be typed into Stripe's box at all.

    The assertion is that the intended string never comes back, not that
    nothing does: "with,comma" parses as the tail entry "COMMA", which is
    the corruption this rule exists to make impossible."""
    for bad in ("A B", "AB", "with:colon", "with,comma", ""):
        got = BI.promos({"QB_PROMOS": f"{bad}:75:2:monthly"})
        assert bad.upper() not in got, (bad, got)


# --- the money gate -----------------------------------------------------------
def test_the_promo_box_only_opens_on_a_plan_that_has_a_promo():
    """All three plans hang off ONE Stripe Product, so `applies_to`
    cannot separate them and any coupon offered at checkout applies to
    what is in the cart. Two months against the yearly price is one
    invoice: $225 down to $56.25."""
    def check():
        for plan_id in BI.PLAN_ORDER:
            _u, _h, body = BI.checkout_request(
                "sk_test_x", "price_x", 7, "a@b.c",
                "https://s", "https://c", plan_id=plan_id)
            offered = b"allow_promotion_codes=true" in body
            assert offered == bool(BI.promos_for(plan_id)), plan_id
        assert BI.promos_for("yearly") == []
        assert BI.promos_for("sixmonth") == []
        assert BI.promos_for("monthly")
    _with_promo(check)


def test_the_cap_is_sent_at_creation_because_it_cannot_be_set_later():
    """Stripe fixes max_redemptions when the promotion code is made. A
    code for a dozen friends is unlimited the moment one screenshots
    it."""
    from engine import stripeset as SS
    sent = {}

    def fake_post(url, headers, body, timeout=20):
        sent["url"], sent["body"] = url, body.decode()
        return {"id": "promo_1", "active": True}

    real, BI._post = BI._post, fake_post
    try:
        _with_promo(lambda: SS.create_promotion_code("sk_x", FAKE, "co_1"))
    finally:
        BI._post = real
    assert "max_redemptions=25" in sent["body"], sent["body"]
    assert sent["url"].endswith("/promotion_codes")


def test_no_cap_means_no_parameter_rather_than_a_zero():
    """max_redemptions=0 is not "unlimited" to Stripe, it is invalid."""
    from engine import stripeset as SS
    sent = {}

    def fake_post(url, headers, body, timeout=20):
        sent["body"] = body.decode()
        return {"id": "p", "active": True}

    env_before = os.environ.get("QB_PROMOS")
    os.environ["QB_PROMOS"] = f"{FAKE}:75:2:monthly"
    real, BI._post = BI._post, fake_post
    try:
        SS.create_promotion_code("sk_x", FAKE, "co_1")
    finally:
        BI._post = real
        if env_before is None:
            os.environ.pop("QB_PROMOS", None)
        else:
            os.environ["QB_PROMOS"] = env_before
    assert "max_redemptions" not in sent["body"], sent["body"]


# --- stopping a code being used twice -----------------------------------------
def test_a_single_use_code_is_the_only_defence_that_cannot_be_walked_around():
    """Ethan: "make sure they are just use once then they can never be
    used again ... how do we fight someone just making a new account and
    using the same promo code again?"

    A cap of 1 is enforced globally by Stripe: the code is spent, and a
    second account with a second card cannot revive it. Everything else
    is a guess about who is behind an email address."""
    got = BI.promos({"QB_PROMOS": f"{FAKE}:75:2:monthly:1"})[FAKE]
    assert got["max_redemptions"] == 1


def test_first_time_only_is_the_default():
    """A promo that quietly works for existing subscribers is a discount
    on revenue already earned. The safe direction is the default, and
    opening it up has to be deliberate."""
    assert BI.promos({"QB_PROMOS": f"{FAKE}:75:2:monthly:1"})[FAKE][
        "first_time_only"] is True
    for word in ("any", "ANY", "all", "anyone"):
        got = BI.promos({"QB_PROMOS": f"{FAKE}:75:2:monthly:0:{word}"})[FAKE]
        assert got["first_time_only"] is False, word


def test_the_restriction_reaches_stripe():
    from engine import stripeset as SS
    sent = {}

    def fake_post(url, headers, body, timeout=20):
        sent["body"] = body.decode()
        return {"id": "p", "active": True}

    def run(raw):
        before = os.environ.get("QB_PROMOS")
        os.environ["QB_PROMOS"] = raw
        real, BI._post = BI._post, fake_post
        try:
            SS.create_promotion_code("sk_x", FAKE, "co_1")
        finally:
            BI._post = real
            if before is None:
                os.environ.pop("QB_PROMOS", None)
            else:
                os.environ["QB_PROMOS"] = before
        return sent["body"]

    assert "restrictions%5Bfirst_time_transaction%5D=true" in run(
        f"{FAKE}:75:2:monthly:1")
    assert "first_time_transaction" not in run(f"{FAKE}:75:2:monthly:0:any")


def test_an_account_that_already_subscribed_is_not_offered_the_box():
    """One promo per ACCOUNT. Stripe's first_time_transaction says the
    same about the CUSTOMER; the two catch different halves of the same
    trick, and neither catches a brand-new email with a new card — which
    is what the single-use cap is for."""
    def check():
        _u, _h, fresh = BI.checkout_request(
            "sk", "p", 7, "a@b.c", "https://s", "https://c",
            plan_id="monthly", allow_promo=True)
        _u2, _h2, again = BI.checkout_request(
            "sk", "p", 7, "a@b.c", "https://s", "https://c",
            plan_id="monthly", allow_promo=False)
        assert b"allow_promotion_codes=true" in fresh
        assert b"allow_promotion_codes" not in again
    _with_promo(check)


def test_the_endpoint_decides_the_promo_flag_from_the_database():
    """Read off the request body it would be a discount for anyone who
    opens the network tab."""
    srv = _read("server.py")
    block = srv[srv.index("if path == \"checkout\":"):]
    block = block[:block.index("else:")]
    assert "allow_promo=fresh" in block
    assert "has_subscribed_before" in block
    assert "body.get(\"allow_promo\")" not in block
    assert "body.get(\"promo\")" not in block


def test_a_live_code_with_no_cap_is_reported_not_passed():
    """max_redemptions and the restrictions are fixed when Stripe creates
    the promotion code and cannot be changed after. A code already live
    without its cap needs a NEW code, and saying so is the whole value of
    checking."""
    from engine import stripeset as SS
    spec = BI.promos({"QB_PROMOS": f"{FAKE}:75:2:monthly:1"})[FAKE]
    problems = SS._code_problems({"max_redemptions": None,
                                  "restrictions": {}}, spec)
    assert len(problems) == 2, problems
    assert any("unlimited" in p and "NEW code" in p for p in problems)
    assert any("first-time" in p or "paid before" in p for p in problems)
    ok = {"max_redemptions": 1,
          "restrictions": {"first_time_transaction": True}}
    assert SS._code_problems(ok, spec) == []


def test_generated_codes_are_unguessable_and_readable():
    """They are read off a phone and typed by somebody else, so no 0/O
    and no 1/I/L — and long enough that guessing is not a strategy."""
    import re as _re
    src = _read("launch.py")
    alpha = _re.search(r'_CODE_ALPHABET = "([^"]+)"', src).group(1)
    for bad in "01OIL":
        assert bad not in alpha, bad
    assert len(alpha) >= 30
    block = src[src.index("def _promo_new_cli"):]
    block = block[:block.index("\ndef ", 1)]
    assert "secrets" in block, "codes must not come from `random`"
    assert "range(10)" in block, "codes got shorter than ten characters"
    assert ":1\"" in block or ":1'" in block or '}:1' in block, \
        "generated codes are no longer single-use"


# --- the seam with the redemption codes ---------------------------------------
def test_no_code_belongs_to_both_systems():
    """If a string were both a redemption code and a promotion code,
    which one it did would depend on which box it was typed into — and
    one of them grants a free year."""
    both = {"QB_CODES": f"{FAKE}:12:5", "QB_PROMOS": f"{FAKE}:75:2:monthly"}
    overlap = set(RD.catalogue(both)) & set(BI.promos(both))
    assert overlap == {FAKE}, "the guard's own fixture stopped working"
    real = set(RD.catalogue()) & set(BI.promos())
    assert not real, (f"{sorted(real)} is both a redemption code and a "
                      f"checkout promo — pick one system for it")


def test_a_checkout_code_in_the_redeem_box_is_told_where_to_go():
    """Otherwise a friend who was handed a code and tried the obvious box
    is told it is not valid, and concludes the code is broken."""
    msg = _with_promo(lambda: BI.promo_misdirect())[FAKE]
    assert FAKE in msg and "75%" in msg and "2 month" in msg
    assert "checkout" in msg.lower() and "not valid" not in msg


def test_redeeming_a_checkout_code_refuses_without_burning_an_attempt():
    """Typing a real code into the wrong box is not a guess. Counting it
    would spend the hourly allowance and lock somebody out of the code
    they hold."""
    conn = _db()
    try:
        RD.redeem(conn, 1, FAKE, env={"QB_CODES": ""},
                  elsewhere=_with_promo(lambda: BI.promo_misdirect()))
        raise AssertionError("a checkout code must not grant free months")
    except RD.RedeemError as exc:
        assert "checkout code" in str(exc), str(exc)
    assert RD._recent_attempts(conn, 1, time.time()) == 0


def test_a_wrong_guess_still_gets_the_decoy_and_still_counts():
    """The generic refusal protects the PRIVATE grants and must survive
    this. One message, one timing, and the rate limit still moves."""
    conn = _db()
    try:
        RD.redeem(conn, 1, "NOTACODE", env={"QB_CODES": "REAL:1:1"},
                  elsewhere=_with_promo(lambda: BI.promo_misdirect()))
        raise AssertionError("unknown code was accepted")
    except RD.RedeemError as exc:
        assert str(exc) == "That code is not valid."
    assert RD._recent_attempts(conn, 1, time.time()) == 1


def test_the_grant_path_never_imports_the_thing_that_moves_money():
    """engine/redeem.py grants access with NO payment, and that claim is
    only worth something if it holds structurally."""
    import ast
    names = set()
    for node in ast.walk(ast.parse(_read("engine", "redeem.py"))):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
            names.update(a.name for a in node.names)
    assert "billing" not in names and "stripe" not in names, sorted(names)


def test_the_endpoint_hands_the_promo_sentences_down():
    srv = _read("server.py")
    block = srv[srv.index("def _billing_redeem("):]
    block = block[:block.index("\n    def ", 1)]
    assert "promo_misdirect()" in block and "elsewhere=" in block


# --- talking to Stripe --------------------------------------------------------
def test_the_coupon_stripe_gets_is_the_coupon_the_environment_describes():
    from engine import stripeset as SS
    spec = BI.promos(ENV)[FAKE]
    ok = {"percent_off": 75, "duration": "repeating", "duration_in_months": 2}
    assert SS._coupon_problems(ok, FAKE, spec) == []
    for bad, why in ((dict(ok, percent_off=50), "50"),
                     (dict(ok, duration_in_months=12), "12"),
                     (dict(ok, duration="forever"), "forever")):
        problems = SS._coupon_problems(bad, FAKE, spec)
        assert problems and any(why in p for p in problems), (why, problems)


def test_setup_reports_a_deactivated_code_instead_of_passing_it():
    """A code switched off in the dashboard still EXISTS, so the
    idempotent path finds it and would otherwise report success for a
    code nobody can use."""
    from engine import stripeset as SS

    def fake_get(url, key, timeout=20, headers=None):
        assert (headers or {}).get("Stripe-Version"), \
            "the promo reads no longer pin an API version"
        return {"data": [{"code": FAKE, "active": False,
                          "coupon": {"id": "co_1", "percent_off": 75,
                                     "duration": "repeating",
                                     "duration_in_months": 2}}]}

    real, BI._get = BI._get, fake_get
    try:
        res = _with_promo(lambda: SS.ensure_promos("sk_test_x", create=True))
    finally:
        BI._get = real
    row = res[FAKE]
    assert row["active"] is False
    assert any("switched OFF" in p for p in row["problems"]), row


def test_a_refused_call_says_which_call_it_was():
    """`billing._get` and `billing._post` produce byte-identical text for
    a refusal, so "Stripe refused the request (HTTP 400)" named neither
    endpoint nor transport. That cost a round trip on 2026-08-22."""
    from engine import stripeset as SS

    def boom(*a, **kw):
        raise BI.BillingUnavailable("Received unknown parameter: coupon")

    real, BI._post = BI._post, boom
    try:
        _with_promo(lambda: SS.create_promotion_code("sk_test_x", FAKE, "co_1"))
        raise AssertionError("the failure was swallowed")
    except BI.BillingUnavailable as exc:
        said = str(exc)
    finally:
        BI._post = real
    assert "promotion code" in said and "co_1" in said, said
    assert "2024" in said, "the pinned API version is not in the message"


def test_no_error_can_carry_the_key():
    """The one thing that must never reach a terminal or a scrollback."""
    from engine import stripeset as SS
    secret = "sk_live_do_not_ever_print_me"

    def boom(*a, **kw):
        raise BI.BillingUnavailable("nope")

    for fn, args in ((SS.create_coupon, (secret, FAKE)),
                     (SS.create_promotion_code, (secret, FAKE, "co_1"))):
        real, BI._post = BI._post, boom
        try:
            _with_promo(lambda: fn(*args))
            raise AssertionError("swallowed")
        except BI.BillingUnavailable as exc:
            assert secret not in str(exc), str(exc)
        finally:
            BI._post = real


def test_the_promo_calls_pin_an_api_version():
    """A parameter Stripe documents as `coupon` was refused as unknown,
    which is what a newer default version answers when a parameter has
    moved."""
    from engine import stripeset as SS
    head = SS._promo_headers("sk_test_x", "idem-1")
    assert head["Stripe-Version"] == SS.PROMO_API_VERSION
    assert head["Idempotency-Key"] == "idem-1"
    assert SS.PROMO_API_VERSION >= "2020-03-01"


def test_a_caller_cannot_swap_the_key_through_the_headers():
    import urllib.request
    seen = {}

    class FakeResp:
        def read(self): return b"{}"
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_open(req, timeout=None):
        seen["auth"] = req.get_header("Authorization")
        return FakeResp()

    real, urllib.request.urlopen = urllib.request.urlopen, fake_open
    try:
        BI._get("https://x/y", "sk_real",
                headers={"Authorization": "Bearer sk_attacker",
                         "Stripe-Version": "2024-06-20"})
    finally:
        urllib.request.urlopen = real
    assert seen["auth"] == "Bearer sk_real", seen


# --- the deploy ---------------------------------------------------------------
def test_the_deploy_creates_the_codes_so_nobody_has_to():
    """The Stripe key lives in /etc/qellys/env on the server and nowhere
    else, so the server is the only place that CAN create the coupon."""
    raw = _read("deploy", "deploy.sh")
    # Comments stripped: the block above this step explains at length why
    # it is --promos-setup and not --stripe-setup, and a substring search
    # would fail on the explanation rather than on the mistake.
    sh = "\n".join(l for l in raw.splitlines()
                   if not l.lstrip().startswith("#"))
    assert "--promos-setup" in sh, "the deploy no longer creates promo codes"
    assert "--stripe-setup" not in sh, \
        "the deploy must never mint Products or Prices unattended"
    i = sh.index("--promos-setup")
    assert "||" in sh[i:i + 200], \
        "a Stripe failure would abort the deploy (set -e is on)"


def test_the_narrow_flag_only_touches_coupons():
    src = _read("launch.py")
    block = src[src.index('if "--promos" in argv'):]
    block = block[:block.index('if "--stripe" in argv')]
    assert "_stripe_promos_cli" in block
    assert "ensure_catalogue" not in block and "create_price" not in block


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("CREATE TABLE users(id INTEGER PRIMARY KEY);"
                       "INSERT INTO users(id) VALUES(1);")
    RD.init(conn)
    return conn


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
