"""Checkout discount codes.

Ethan, 2026-08-22: *"Make a promo code for 75% off the first 2 months. The
promo code will be MUDBONE."*

THE SITE NOW HAS TWO CODE SYSTEMS, which is the thing `billing.py` used to
refuse to do, so these tests are mostly about the seam between them:

* `engine/redeem.py` codes grant free months with no payment at all.
* Stripe promotion codes take a percentage off a real subscription.

The two failures that matter are a code claimed by both systems, and a
discount offered on a plan it was never priced for — the second being
worth real money, because all three plans are Prices on one Stripe
Product and a "2 months" coupon against the yearly price is 75% off a
whole year.

Run directly: `python3 tests/test_promo.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import billing as BI
from engine import redeem as RD

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def test_mudbone_exists_and_is_what_was_asked_for():
    promo = BI.promo_named("MUDBONE")
    assert promo, "MUDBONE is not in billing.PROMOS"
    assert promo["percent_off"] == 75
    assert promo["duration"] == "repeating"
    assert promo["duration_in_months"] == 2


def test_codes_are_matched_however_they_are_typed():
    """These are read off a phone screen and typed by hand."""
    for typed in ("mudbone", "  MudBone ", "MUDBONE"):
        assert BI.promo_named(typed), typed
    assert BI.promo_named("MUDBONES") is None
    assert BI.promo_named("") is None


def test_every_promo_is_a_valid_code_string():
    """A code carrying a comma or colon would break the QB_CODES env
    format it is checked against, and one carrying a space cannot be
    typed into Stripe's box at all."""
    for code, promo in BI.PROMOS.items():
        assert code == code.upper(), code
        assert RD.CODE_RE.match(code), f"{code} is not a usable code string"
        assert promo["code"] == code, "the key and the code disagree"


def test_no_code_belongs_to_both_systems():
    """The whole reason the old comment refused Stripe's promo codes. If
    a string were both a redemption code and a promotion code, which one
    it did would depend on which box it was typed into — and one of them
    grants a free year."""
    env = {"QB_CODES": "USFARATHANE:12:100, MUDBONE:12:5, FRIENDS:1:25"}
    overlap = set(RD.catalogue(env)) & set(BI.PROMOS)
    assert overlap == {"MUDBONE"}, "the guard's own fixture stopped working"
    # And in the real environment, there must be none.
    real = set(RD.catalogue()) & set(BI.PROMOS)
    assert not real, (f"{sorted(real)} is both a redemption code and a "
                      f"checkout promo — pick one system for it")


def test_the_promo_box_only_opens_on_a_plan_that_has_a_promo():
    """The money question. All three plans hang off ONE Stripe Product,
    so `applies_to` cannot separate them and any coupon offered at
    checkout applies to whatever is in the cart. duration_in_months=2
    against the yearly price is one invoice: $225 down to $56.25."""
    for plan_id in BI.PLAN_ORDER:
        _, _, body = BI.checkout_request(
            "sk_test_x", "price_x", 7, "a@b.c",
            "https://s", "https://c", plan_id=plan_id)
        offered = b"allow_promotion_codes=true" in body
        assert offered == bool(BI.promos_for(plan_id)), plan_id
    assert BI.promos_for("yearly") == [], "MUDBONE must not reach the yearly plan"
    assert BI.promos_for("sixmonth") == []
    assert BI.promos_for("monthly")


def test_a_promo_plan_is_a_real_plan():
    for code, promo in BI.PROMOS.items():
        for plan_id in promo["plans"]:
            assert plan_id in BI.PLANS, f"{code} names unknown plan {plan_id}"


def test_the_discount_is_worth_less_than_the_term_it_discounts():
    """A sanity floor on the arithmetic: 75% off two $25 months is
    $37.50, and the subscription keeps running at full price after. If a
    promo ever gave away more than the plan's own term it would be a
    giveaway wearing a discount's clothes."""
    for code, promo in BI.PROMOS.items():
        for plan_id in promo["plans"]:
            plan = BI.PLANS[plan_id]
            given = (plan["cents"] / 100.0) * (promo["percent_off"] / 100.0) \
                * promo["duration_in_months"]
            assert 0 < given < plan["cents"] / 100.0 * 12, f"{code}/{plan_id}"


def test_a_checkout_code_in_the_redeem_box_is_told_where_to_go():
    """The support question the old comment named: "why did the code work
    on the payment page but not on the account page". It gets an answer
    now instead of "that code is not valid"."""
    msg = BI.promo_misdirect()["MUDBONE"]
    assert "MUDBONE" in msg
    assert "75%" in msg and "2 month" in msg
    assert "checkout" in msg.lower()
    assert "not valid" not in msg


def test_the_grant_path_never_imports_the_thing_that_moves_money():
    """engine/redeem.py grants access with NO payment, and that claim is
    only worth something if it holds structurally. The promo sentences
    reach it as plain data from the caller, which is why adding a second
    code system did not cost this module its independence."""
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
    assert "billing" not in names and "stripe" not in names, sorted(names)


def test_the_endpoint_hands_the_promo_sentences_down():
    """The wiring, which nothing else would catch: redeem() only knows
    about checkout codes if the caller tells it, so a caller that forgot
    would silently go back to "that code is not valid"."""
    srv = _read("server.py")
    block = srv[srv.index("def _billing_redeem("):]
    block = block[:block.index("\n    def ", 1)]
    assert "promo_misdirect()" in block
    assert "elsewhere=" in block


def test_redeeming_a_checkout_code_refuses_without_burning_an_attempt():
    """Typing a real code into the wrong box is not a guess. Counting it
    would spend the hourly allowance and lock somebody out of the code
    they are holding."""
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("CREATE TABLE users(id INTEGER PRIMARY KEY);"
                       "INSERT INTO users(id) VALUES(1);")
    RD.init(conn)
    try:
        RD.redeem(conn, 1, "MUDBONE", env={"QB_CODES": ""},
                  elsewhere=BI.promo_misdirect())
        raise AssertionError("a checkout code must not grant free months")
    except RD.RedeemError as exc:
        assert "checkout code" in str(exc), str(exc)
    assert RD._recent_attempts(conn, 1, __import__("time").time()) == 0


def test_a_redemption_code_still_gets_the_generic_refusal():
    """The decoy protects the PRIVATE codes and must survive this. A
    wrong guess still gets one message and one timing, and still counts
    against the rate limit."""
    import sqlite3, time
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("CREATE TABLE users(id INTEGER PRIMARY KEY);"
                       "INSERT INTO users(id) VALUES(1);")
    RD.init(conn)
    try:
        RD.redeem(conn, 1, "NOTACODE", env={"QB_CODES": "REAL:1:1"})
        raise AssertionError("unknown code was accepted")
    except RD.RedeemError as exc:
        assert str(exc) == "That code is not valid."
    assert RD._recent_attempts(conn, 1, time.time()) == 1


def test_the_page_reads_the_discount_from_the_server():
    """A percentage hardcoded in app.js is a second source for a number
    Stripe is the authority on, and the failure mode is a page promising
    75% while the coupon gives 50%."""
    app = _read("web", "js", "app.js")
    fn = app[app.index("function _coPromoNote("):]
    fn = fn[:fn.index("\nfunction ", 1)]
    assert "_pwStatus" in fn and ".promos" in fn
    assert "75" not in fn, "the discount is hardcoded in the page"
    assert "MUDBONE" not in fn, "the code is hardcoded in the page"


def test_the_server_only_advertises_promos_it_would_accept():
    """What the status endpoint sends is built from promos_for(), the
    same function that decides whether Stripe's box appears — so the page
    cannot invite a code into a checkout that has no box for it."""
    srv = _read("server.py")
    block = srv[srv.index('out["promos"]'):]
    block = block[:block.index("\n\n")] if "\n\n" in block[:800] else block[:800]
    assert "promos_for" in block
    assert "PLAN_ORDER" in block


def test_the_coupon_stripe_gets_is_the_coupon_this_repo_describes():
    from engine import stripeset as SS
    ok = {"percent_off": 75, "duration": "repeating", "duration_in_months": 2}
    assert SS._coupon_problems(ok, "MUDBONE") == []
    for bad, why in ((dict(ok, percent_off=50), "50"),
                     (dict(ok, duration_in_months=12), "12"),
                     (dict(ok, duration="forever"), "forever")):
        problems = SS._coupon_problems(bad, "MUDBONE")
        assert problems, why
        assert any(why in p for p in problems), (why, problems)


def test_setup_reports_a_deactivated_code_instead_of_passing_it():
    """A promotion code switched off in the dashboard still EXISTS, so
    the idempotent path finds it and would otherwise report success for a
    code nobody can use."""
    from engine import stripeset as SS
    calls = {}

    def fake_get(url, key, timeout=20):
        calls["url"] = url
        return {"data": [{"code": "MUDBONE", "active": False,
                          "coupon": {"id": "co_1", "percent_off": 75,
                                     "duration": "repeating",
                                     "duration_in_months": 2}}]}

    real = BI._get
    BI._get = fake_get
    try:
        res = SS.ensure_promos("sk_test_x", create=True)
    finally:
        BI._get = real
    row = res["MUDBONE"]
    assert row["active"] is False
    assert any("switched OFF" in p for p in row["problems"]), row


def test_the_deploy_creates_the_codes_so_nobody_has_to():
    """The reason this is wired into deploy.sh at all: the Stripe key
    lives in /etc/qellys/env on the server and nowhere else, so the
    server is the only place that CAN create the coupon. Asking for a
    hand-run command was making a person do a machine's job."""
    raw = _read("deploy", "deploy.sh")
    # COMMENTS STRIPPED FIRST. The block above this step explains at
    # length why it is --promos-setup and not --stripe-setup, and a
    # substring search fails on the explanation rather than on the
    # mistake. That shape has bitten this suite repeatedly.
    sh = "\n".join(l for l in raw.splitlines() if not l.lstrip().startswith("#"))
    assert "--promos-setup" in sh, "the deploy no longer creates promo codes"
    assert "--stripe-setup" not in sh, \
        "the deploy must never mint Products or Prices unattended"
    # Never fatal: a Stripe outage is not a reason to refuse a deploy.
    i = sh.index("--promos-setup")
    assert "||" in sh[i:i + 200], \
        "a Stripe failure would abort the deploy (set -e is on)"


def test_the_narrow_flag_only_touches_coupons():
    """--promos-setup is what the deploy calls. If it ever grew the
    ability to create a Price, the deploy would silently gain it too."""
    src = _read("launch.py")
    block = src[src.index('if "--promos" in argv'):]
    block = block[:block.index('if "--stripe" in argv')]
    assert "_stripe_promos_cli" in block
    assert "ensure_catalogue" not in block and "create_price" not in block


def test_the_blurb_is_built_from_the_promo_not_written_out():
    assert BI.promo_blurb("yearly") == ""
    said = BI.promo_blurb("monthly")
    assert "75%" in said and "2 months" in said


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
