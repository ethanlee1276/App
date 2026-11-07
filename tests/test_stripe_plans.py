"""Three plans, two languages, one set of prices.

Ethan, 2026-08-21: *"everything is all set so lets fully push this pay
wall and tell me how we can get this on the website with my stripe
account."*

THE FAILURE THIS FILE EXISTS FOR IS NOT A CRASH. `web/js/app.js` draws
three plan cards with prices on them; `engine/billing.py` decides what
Stripe charges. Nothing connects the two at runtime — the browser sends a
plan *id* and the server looks up a price by that id — so the two lists
can drift apart silently and the site keeps working. It just advertises
$125 and charges $225.

That is not a display bug. It is a chargeback, and it is the kind a
customer is right about.

So: every number on the page is compared against the number in the module
that spends the money, both directions, by parsing the JavaScript rather
than by restating it here. A third copy of the prices in this file would
be a third thing to drift.

    python3 tests/test_stripe_plans.py
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import billing                                     # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _js_plans():
    """The `PLANS` array out of app.js, as a list of dicts.

    Parsed, not duplicated. The array is plain enough to convert to JSON
    with two substitutions — quote the bare keys, drop the trailing
    commas — and doing it this way means the test reads whatever the file
    actually says today.
    """
    app = _read("web", "js", "app.js")
    i = app.index("const PLANS = [")
    body = app[i + len("const PLANS = "):]
    body = body[:body.index("\n];") + 2]
    body = re.sub(r"(?m)^\s*//.*$", "", body)
    body = re.sub(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:", r'\1"\2":', body)
    body = re.sub(r",(\s*[\]}])", r"\1", body)
    return json.loads(body)


# --- the two lists agree -----------------------------------------------------
def test_the_page_and_the_charge_name_the_same_plans():
    js = {p["id"] for p in _js_plans()}
    py = set(billing.PLANS)
    assert js == py, (
        f"the plan ids diverged: only on the page {js - py}, "
        f"only in billing {py - js}. A plan the page offers and billing "
        "does not is a buy button that 502s; the reverse is a price "
        "nobody can reach.")


def test_every_advertised_price_is_the_price_stripe_is_told_to_charge():
    for row in _js_plans():
        plan = billing.PLANS[row["id"]]
        assert int(round(row["price"] * 100)) == plan["cents"], (
            f"{row['id']}: the page says ${row['price']} and Stripe is "
            f"told {plan['cents'] / 100:.2f}")


def test_the_term_lengths_agree_because_a_code_is_measured_against_them():
    """`months` is not decoration. A discount code covers a term when its
    months reach the plan's, and that comparison happens in the browser
    (`_coCovers`) using the page's number, while the grant is written on
    the server using ours. Disagree and a code either reads as free and
    is not, or the reverse."""
    for row in _js_plans():
        assert row["months"] == billing.PLANS[row["id"]]["months"], \
            f"{row['id']}: term length differs between page and server"


def test_the_advertised_saving_is_arithmetic_and_not_a_claim():
    """Each longer plan prints a saving against paying monthly. Nobody
    checks it, so it is worth checking: an overstated discount is an
    advertised price that is not true."""
    js = {p["id"]: p for p in _js_plans()}
    month = js["monthly"]["price"]
    for row in js.values():
        want = month * row["months"] - row["price"]
        assert abs(row.get("save", 0) - want) < 0.005, (
            f"{row['id']}: says it saves ${row.get('save')} and the "
            f"arithmetic is ${want:.2f}")


# --- the shapes Stripe needs --------------------------------------------------
def test_six_months_is_a_real_interval_and_not_a_fraction_of_a_year():
    """Stripe bills on the interval it is given. `month` x 6 is a real
    recurring interval there; there is no half-year interval to ask for,
    and expressing it as `year` with a fractional count is not a thing."""
    plan = billing.PLANS["sixmonth"]
    assert (plan["interval"], plan["interval_count"]) == ("month", 6)
    assert billing.PLANS["yearly"]["interval"] == "year"
    assert billing.PLANS["monthly"]["interval_count"] == 1


def test_a_plan_with_no_price_configured_is_not_offered_as_ready():
    """The page must not draw a buy button for a plan the server cannot
    charge — that is a 502 after the customer has committed."""
    for name in ("STRIPE_PRICE_MONTHLY", "STRIPE_PRICE_SIXMONTH",
                 "STRIPE_PRICE_YEARLY", "STRIPE_PRICE_ID"):
        os.environ.pop(name, None)
    cat = billing.plan_catalogue()
    assert cat and not any(row["ready"] for row in cat), \
        "an unconfigured plan reported itself ready to sell"
    assert [row["id"] for row in cat] == list(billing.PLAN_ORDER)


def test_an_unknown_plan_is_refused_rather_than_substituted():
    """THE EXPENSIVE ONE. Falling back to the monthly price for a plan we
    do not recognise charges $25 to somebody who believes they bought a
    year, and nothing anywhere reports it."""
    os.environ["STRIPE_PRICE_MONTHLY"] = "price_monthly_x"
    try:
        assert billing.price_for("monthly") == "price_monthly_x"
        for bad in ("lifetime", "", "MONTHLY", "yearly "):
            try:
                billing.price_for(bad)
            except billing.BillingUnavailable:
                continue
            raise AssertionError(f"{bad!r} was quietly charged as something")
    finally:
        os.environ.pop("STRIPE_PRICE_MONTHLY", None)


def test_a_plan_configured_with_no_price_refuses_by_name():
    """…and says WHICH variable to set. "Stripe error" is not actionable
    at the moment somebody is trying to give you money."""
    os.environ.pop("STRIPE_PRICE_YEARLY", None)
    try:
        billing.price_for("yearly")
    except billing.BillingUnavailable as exc:
        assert "STRIPE_PRICE_YEARLY" in str(exc)
    else:
        raise AssertionError("an unconfigured plan produced a price")


def test_the_legacy_single_price_still_works_as_monthly():
    """An install configured before there were three plans keeps
    charging. Silently dropping it would take a working site off billing
    on a deploy that looked like a feature addition."""
    os.environ.pop("STRIPE_PRICE_MONTHLY", None)
    os.environ["STRIPE_PRICE_ID"] = "price_legacy"
    try:
        assert billing.price_for("monthly") == "price_legacy"
        # …and only monthly. The old single price was a monthly one;
        # honouring it for `yearly` would charge $25 for a year.
        try:
            billing.price_for("yearly")
        except billing.BillingUnavailable:
            pass
        else:
            raise AssertionError("the legacy price leaked onto another plan")
    finally:
        os.environ.pop("STRIPE_PRICE_ID", None)


def test_plan_of_maps_a_price_id_back_and_refuses_to_guess():
    os.environ["STRIPE_PRICE_SIXMONTH"] = "price_six"
    try:
        assert billing.plan_of("price_six") == "sixmonth"
        assert billing.plan_of("price_unknown") is None
        assert billing.plan_of("") is None
        assert billing.plan_of(None) is None
    finally:
        os.environ.pop("STRIPE_PRICE_SIXMONTH", None)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
