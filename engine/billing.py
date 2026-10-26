"""Subscriptions through Stripe: money we never touch.

Ethan, 2026-08-15: *"we will be accepting money for people to use the
website once it is complete."*

CARD NUMBERS NEVER REACH THIS SERVER, and that is the whole architecture
rather than a nicety. The customer is sent to a Checkout page hosted by
Stripe, types the card there, and comes back with nothing sensitive in
hand. We store a customer id and a subscription status. That is what keeps
this repo out of PCI scope entirely — the moment a card field is rendered
by us, the compliance surface stops being a paragraph and becomes a
project. Do not build a card form.

THE ONLY SOURCE OF TRUTH IS STRIPE, NEVER THE BROWSER. A page returning
from Checkout saying "I paid" is a claim from an untrusted party; anybody
can issue that request with curl. Entitlement moves only when a **signed
webhook** says it does, or when we ask Stripe directly. `success_url` is
for showing a thank-you, and this module deliberately gives it no power to
grant anything.

WHICH MAKES SIGNATURE VERIFICATION THE LOAD-BEARING FUNCTION HERE.
`/api/billing/webhook` is a public endpoint that grants paid access. Without
a verified signature it is a free-subscription button for anyone who finds
the URL. `verify_signature` is pure, and it is the most heavily tested
thing in this file:

  * HMAC-SHA256 over Stripe's exact `{timestamp}.{body}` construction;
  * compared with `hmac.compare_digest`, never `==`;
  * a timestamp older than the tolerance is REJECTED, because a captured
    valid webhook replayed a month later is otherwise still valid;
  * and it takes the RAW BODY. Parsing and re-serializing JSON changes
    bytes — key order, spacing, unicode escapes — and the signature is
    over bytes, so a re-serialized body fails to verify even when honest.

WRITTEN AGAINST AN API THIS CONTAINER CANNOT REACH, like the Yahoo
adapter, and with the same split: everything that can be decided without
the network is pure and unit-tested (signatures, state, request shapes),
and the two calls that must go out are thin. The parts that CANNOT be
verified from here are named in docs/BILLING.md rather than implied to
work.

Standard library only. No `stripe` package — it is a dependency this repo
does not otherwise need, and the two calls are a form POST each.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.stripe.com/v1"

#: Stripe signs `{timestamp}.{raw body}` and sends
#: `t=<unix>,v1=<hex>` in the `Stripe-Signature` header. Five minutes is
#: Stripe's own recommended tolerance.
SIGNATURE_TOLERANCE = 300

#: Statuses that mean "this account has paid and may use paid features".
#: `trialing` counts — a trial is a deliberate grant, not an accident.
#:
#: `past_due` DOES NOT, and did until 2026-10-12. Ethan: a failed payment
#: or a cancellation "should lock them too the paywall screen". The grace
#: it replaced was meant to run "until the period they last paid for
#: ends", but the date it read was the NEW period's end — Stripe moves the
#: period forward when it opens the renewal invoice, paid or not — so a
#: card that failed on the 1st kept the site until the 1st of the next
#: month: Stripe's whole retry window, unpaid. A failed card now walls the
#: account at once. The paywall says why and opens Stripe's billing page,
#: where the card is changed and the open invoice paid, and the payment
#: that goes through lets them straight back in.
ENTITLED = ("active", "trialing")
#: …and the ones that end it. `incomplete` is a Checkout that was never
#: finished, which is not a subscription at all.
NOT_ENTITLED = ("past_due", "canceled", "unpaid", "incomplete",
                "incomplete_expired", "paused", "none")
#: STILL OPEN AT STRIPE, entitled or not. A walled `past_due` card is still
#: being retried there and an `unpaid` one still opens an invoice every
#: period, so deleting the account (server `_live_subscription`) and buying
#: a second plan (`_billing_post`) are both refused while a row says one of
#: these: either would leave Stripe billing a card for a subscription this
#: side has lost track of. The fix for a failed card is Stripe's billing
#: page, never a second subscription.
OPEN = ("active", "trialing", "past_due", "unpaid")
#: Nothing further comes from Stripe about these. A cancelled subscription
#: is never revived — coming back is a new Checkout, which arrives through
#: the webhook or the return trip — and `none` is no subscription at all.
#: `refresh` skips them.
FINAL = ("canceled", "incomplete_expired", "none")

#: Events we act on. Anything else is acknowledged (200) and ignored —
#: Stripe retries anything it does not get a 2xx for, so a 500 on an event
#: we simply do not care about becomes a retry loop.
HANDLED = (
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.payment_failed",
)


class BillingUnavailable(RuntimeError):
    """Stripe is not configured, or would not answer."""


# --- configuration -----------------------------------------------------------
#: The three plans, and the ONLY place their money lives on this side.
#:
#: `web/js/app.js` has a `PLANS` array that draws the same three cards.
#: These two lists are the same rule with two callers, and
#: `tests/test_stripe_plans.py` fails if their prices ever disagree — a
#: page advertising $125 while Checkout charges $225 is not a display bug,
#: it is a chargeback.
#:
#: `months` is what a discount code has to cover to make a term free, and
#: it is why 6 months is `interval=month, interval_count=6` rather than
#: some fraction of a year: Stripe bills on the interval it is given, and
#: "every 6 months" is a real recurring interval there.
PLANS = {
    "monthly": {
        "id": "monthly", "name": "Monthly", "months": 1, "cents": 2500,
        "interval": "month", "interval_count": 1,
        "env": "STRIPE_PRICE_MONTHLY", "lookup_key": "qellys_monthly",
    },
    "sixmonth": {
        "id": "sixmonth", "name": "6 months", "months": 6, "cents": 12500,
        "interval": "month", "interval_count": 6,
        "env": "STRIPE_PRICE_SIXMONTH", "lookup_key": "qellys_sixmonth",
    },
    "yearly": {
        "id": "yearly", "name": "Yearly", "months": 12, "cents": 22500,
        "interval": "year", "interval_count": 1,
        "env": "STRIPE_PRICE_YEARLY", "lookup_key": "qellys_yearly",
    },
}

#: Display order, and the fallback when a request names no plan.
PLAN_ORDER = ("monthly", "sixmonth", "yearly")
DEFAULT_PLAN = "monthly"

#: The free trial. Ethan, 2026-08-22: "we should completly get rid of the
#: free plan and only have the paid plans. if anything we can offer a 3 day
#: free trial only for the $25 plan."
#:
#: MONTHLY ONLY, and that is the whole design. A trial on the yearly plan
#: would hand three days of the product to somebody who then walks, at the
#: cost of a $225 commitment they never make; on the monthly plan the
#: worst case is one $25 conversion lost. It is also the plan somebody
#: undecided actually picks.
#:
#: A CARD IS STILL COLLECTED. Stripe Checkout takes the payment method up
#: front and converts automatically when the trial ends, which is what
#: makes this a trial rather than a giveaway — and it is why the Terms have
#: to say so plainly. A free trial that quietly starts charging is the
#: single most complained-about pattern in subscriptions, and the law in
#: several states has a name for it.
TRIAL_DAYS = 3
TRIAL_PLAN = "monthly"

#: Checkout discount codes — a PERCENTAGE off a real subscription.
#:
#: WHY THESE LIVE AT STRIPE WHEN `engine/redeem.py` EXISTS.
#: They are not the same kind of thing. A redemption code grants months of
#: access with NO payment at all, which is why it never touches a
#: processor. "75% off" is a payment — a real subscription, a real card,
#: charged less — and there is no way to express that without the thing
#: that moves the money. So this is a Stripe Coupon plus a Promotion Code,
#: typed into Stripe's own checkout box.
#:
#: WHY THE CODE IS NOT WRITTEN HERE. Ethan, 2026-08-22: *"we do not want
#: to display to people that code is a thing. its a secret promo code i
#: will only be givving my friends."*
#:
#: This repository is PUBLIC. A code in this file is a code on the open
#: internet, and so is one in a docstring, a commit message or a test
#: fixture. `QB_CODES` already solved exactly this for the redemption
#: codes and the reasoning transfers unchanged: a secret belongs in the
#: environment, which nothing reachable from the web can read.
#:
#:     QB_PROMOS="SOMECODE:75:2:monthly:1:new"
#:                    │     │  │    │     │  │
#:                    │     │  │    │     │  └── "new" (default) or "any"
#:                    │     │  │    │     └───── max redemptions (0 = no cap)
#:                    │     │  │    └─────────── which plans may offer it
#:                    │     │  └──────────────── months the discount runs
#:                    │     └─────────────────── percent off
#:                    └───────────────────────── the code, as typed
#:
#: HOW A CODE IS STOPPED FROM BEING USED TWICE, which is three separate
#: mechanisms because no single one covers it:
#:
#: * `max redemptions` is a HARD, GLOBAL ceiling that Stripe enforces.
#:   A code with a cap of 1 is spent the moment anybody uses it, and a
#:   second account with a second card cannot revive it. This is the only
#:   one of the three that a determined person cannot walk around, which
#:   is why `--promo-new` mints one single-use code per friend rather
#:   than one shared code for all of them.
#: * "new" sets Stripe's `first_time_transaction` restriction: the code
#:   is refused for any customer who has ever paid an invoice here. That
#:   stops an existing subscriber from cancelling and re-buying at 75%
#:   off. It does NOT stop a fresh account — a new customer has no
#:   history by definition. Use "any" for a deliberate win-back offer to
#:   somebody who has already paid.
#: * One per ACCOUNT, enforced on our side at checkout: an account that
#:   has ever held a subscription is not offered the box at all.
#:
#: What none of these can do is recognise the same PERSON behind a new
#: email and a new card. Nothing can, short of storing something about
#: the card — which would change what this site keeps about a payment
#: method, and the Privacy Policy says plainly that it keeps nothing.
#: A single-use code per friend makes the question moot instead.
#:
#: Unset means NO promo codes at all: Stripe's box never renders, and
#: there is nothing to guess. That is the right default for a site whose
#: source anyone can read.
#:
#: MONTHLY ONLY, AND THIS IS THE PART THAT COSTS MONEY.
#: All three plans are Prices on ONE Stripe Product, so Stripe's own
#: `applies_to` cannot tell them apart — a coupon offered at checkout is
#: offered on whatever plan is in the cart. And a 2-month duration does
#: not mean "two billing periods", it means invoices raised in the next
#: two months. On the yearly plan that is exactly one invoice: 75% off
#: $225, a full year for $56.25. On six months it is $125 down to $31.25.
#: A promo meant to cost $37.50 would instead cost $168.75, and nothing
#: would fail — it would just quietly be the best deal on the site.
#:
#: So the gate is on OUR side: `allow_promotion_codes` is switched on only
#: for a plan the entry names. On the other two Stripe never renders the
#: box, so there is nothing to type a code into.
ENV_PROMOS = "QB_PROMOS"

#: Same character rule as a redemption code, and for the same reason: a
#: code carrying a colon or a comma would break the format it is parsed
#: out of, and one carrying a space cannot be typed into Stripe's box.
PROMO_CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,31}$")


def promos(env: dict | None = None) -> dict:
    """`{CODE: {...}}` from the environment. Never raises.

    Malformed entries are DROPPED rather than raising: this is read on
    the checkout path, and one typo in a comma-separated list must not
    take the buy button down for everything else in it.
    """
    raw = (env if env is not None else os.environ).get(ENV_PROMOS, "") or ""
    out: dict = {}
    for part in raw.split(","):
        bits = [b.strip() for b in part.split(":")]
        if len(bits) < 4:
            continue
        code = bits[0].strip().upper()
        if not PROMO_CODE_RE.match(code):
            continue
        try:
            pct = int(bits[1])
            months = int(bits[2])
            cap = int(bits[4]) if len(bits) > 4 and bits[4] else 0
        except ValueError:
            continue
        # First-time-only unless explicitly opened up. The default is the
        # safe direction: a promo that quietly works for existing
        # subscribers is a discount on revenue already earned.
        first_time = str(bits[5]).strip().lower() not in (
            "any", "all", "anyone") if len(bits) > 5 else True
        # A 0% coupon is a no-op and a 100% one is a free subscription
        # wearing a discount's clothes — that is what QB_CODES is for,
        # and it does not need a card.
        if not (1 <= pct <= 99) or not (1 <= months <= 24):
            continue
        plans = tuple(p for p in bits[3].replace("|", " ").split()
                      if p in PLANS)
        if not plans:
            continue
        out[code] = {
            "code": code,
            "percent_off": pct,
            "duration": "repeating",
            "duration_in_months": months,
            "plans": plans,
            "max_redemptions": max(0, cap),
            "first_time_only": first_time,
            # Named for the dashboard, where Ethan has to recognise it.
            # The code itself is IN the name because Stripe shows coupon
            # names and promotion codes on different screens.
            "coupon_name": f"{code} — {pct}% off {months} months",
        }
    return out


def promos_for(plan_id: str, env: dict | None = None) -> list:
    """Every promo that may be entered while buying this plan."""
    return [p for p in promos(env).values() if str(plan_id) in p["plans"]]


def promo_named(code: str, env: dict | None = None) -> dict | None:
    """A promo by code, case-insensitively — people type these by hand."""
    return promos(env).get(str(code or "").strip().upper())


def promo_misdirect() -> dict:
    """``{CODE: sentence}`` for `redeem.redeem(elsewhere=...)`.

    The site has two code systems and the person holding a code has no
    reason to know which box theirs goes in. Without this, a checkout
    promo typed into the account page's redemption box is answered "that
    code is not valid", which reads as "the code is broken".

    This reveals nothing: the sentence is only ever reached by somebody
    who already typed the exact code. A wrong guess still gets the decoy,
    still counts against the rate limit, and still cannot be told apart
    from a used-up code.

    Living HERE rather than in `redeem.py` is the point: that module
    grants access with no payment and keeps no import from anything that
    moves money. It takes this as plain data.
    """
    out = {}
    for code, p in promos().items():
        months = int(p["duration_in_months"])
        out[code] = (
            f"{code} is a checkout code, not a redemption code — it takes "
            f"{p['percent_off']}% off your first {months} "
            f"month{'s' if months != 1 else ''} of a subscription. Pick a "
            f"plan, then enter it in the promo code box on the payment page.")
    return out


def has_subscribed_before(conn, user_id: int) -> bool:
    """True once this account has ever had a subscription row.

    ONE TRIAL PER ACCOUNT, decided here rather than by Stripe — Stripe
    will happily start a second trial for a returning customer, and
    "cancel on day two, resubscribe on day four" would be a permanently
    free account otherwise. `subscriptions` holds one row per user and it
    is written the moment a purchase or a trial completes, so its
    existence is the whole test.
    """
    try:
        row = conn.execute(
            "SELECT 1 FROM subscriptions WHERE user_id=?",
            (int(user_id),)).fetchone()
    except Exception:                                        # noqa: BLE001
        # A lookup that breaks must not hand out a free trial. Refusing
        # one costs a conversion; granting one to everybody costs the
        # first month of every subscription on the site.
        return True
    return row is not None


def trial_days_for(plan_id: str, eligible: bool) -> int:
    """How many trial days this checkout gets. Zero for every other plan."""
    if not eligible:
        return 0
    return TRIAL_DAYS if str(plan_id) == TRIAL_PLAN else 0

#: What the product is called in Stripe's own catalogue. The dashboard,
#: the invoice and the customer's card statement all read from this.
PRODUCT_NAME = "Qellys Book"
PRODUCT_DESC = ("Subscription access to sports analytics: model "
                "projections, probability estimates and research tools.")

ENV_SECRET = "STRIPE_SECRET_KEY"
ENV_WEBHOOK_SECRET = "STRIPE_WEBHOOK_SECRET"
#: The pre-plan single price. Still read, as `monthly`, so an install
#: configured before there were three plans keeps working.
ENV_LEGACY_PRICE = "STRIPE_PRICE_ID"


def _env() -> None:
    from . import secrets as _s
    _s.load_local_secrets()


def keys() -> tuple[str, str, str]:
    """``(secret_key, webhook_secret, monthly_price_id)``.

    Raises with the setup steps rather than returning blanks: an empty
    key produces a Stripe error about authentication that says nothing
    about what to go and do.

    THE THIRD ELEMENT IS THE MONTHLY PRICE, not "the" price — there are
    three now. Callers that want a specific plan use `price_for()`. This
    shape is kept because `configured()` and every existing caller test
    the same thing through it: can we charge anybody at all.
    """
    _env()
    sk = os.environ.get(ENV_SECRET, "").strip()
    wh = os.environ.get(ENV_WEBHOOK_SECRET, "").strip()
    price = _price_env("monthly")
    if not sk or not price:
        raise BillingUnavailable(
            "Stripe is not set up yet. Run `python3 launch.py "
            "--stripe-setup` to create the Product and the three Prices, "
            "then put STRIPE_SECRET_KEY and the three STRIPE_PRICE_* "
            "lines it prints into secrets.local. Add "
            "STRIPE_WEBHOOK_SECRET once the webhook endpoint exists. "
            "docs/BILLING.md has the order to do it in.")
    return sk, wh, price


def _price_env(plan_id: str) -> str:
    """The configured price id for a plan, or ``""``.

    Reads the environment on every call rather than caching. Caching
    would mean a price corrected in secrets.local needs a restart to take
    effect, and the failure mode of a stale price id is charging the
    wrong amount.
    """
    plan = PLANS.get(plan_id)
    if not plan:
        return ""
    got = os.environ.get(plan["env"], "").strip()
    if not got and plan_id == "monthly":
        got = os.environ.get(ENV_LEGACY_PRICE, "").strip()
    return got


def price_for(plan_id: str) -> str:
    """The Stripe price id to charge for this plan.

    REFUSES AN UNKNOWN PLAN RATHER THAN FALLING BACK. A request naming a
    plan we do not have is either a typo in our own front end or somebody
    poking the endpoint, and quietly substituting the monthly price means
    charging $25 to a person who believes they bought a year.
    """
    _env()
    if plan_id not in PLANS:
        raise BillingUnavailable(f"No such plan: {plan_id!r}.")
    got = _price_env(plan_id)
    if not got:
        raise BillingUnavailable(
            f"The {PLANS[plan_id]['name']} plan has no price configured. "
            f"Set {PLANS[plan_id]['env']} in secrets.local — "
            "`python3 launch.py --stripe-setup` prints all three.")
    return got


def plan_of(price_id: str) -> str | None:
    """Which of our plans a price id belongs to, or None.

    Used to label a subscription after the fact. A price id we do not
    recognise is not an error — it could be a legacy price, or one
    created by hand in the dashboard — so this returns None rather than
    guessing, and the caller says "subscribed" instead of naming a term
    it cannot prove.
    """
    if not price_id:
        return None
    _env()
    for pid in PLAN_ORDER:
        if _price_env(pid) == str(price_id):
            return pid
    return None


def plan_catalogue() -> list:
    """The three plans, each marked with whether it can be sold today.

    The page needs this: a plan whose price id is missing must not render
    a buy button that produces a 502 after the customer has committed.
    """
    _env()
    out = []
    for pid in PLAN_ORDER:
        plan = dict(PLANS[pid])
        plan["ready"] = bool(_price_env(pid))
        plan["price"] = plan["cents"] / 100.0
        plan.pop("env", None)
        plan.pop("lookup_key", None)
        out.append(plan)
    return out


def configured() -> bool:
    try:
        keys()
        return True
    except BillingUnavailable:
        return False


def live_mode(secret_key: str) -> bool:
    """Whether this key spends real money.

    Worth surfacing on the page. `sk_test_` and `sk_live_` look nearly
    identical in a config file and behave completely differently, and
    "why did nobody get charged" is a bad thing to debug in production.
    """
    return str(secret_key or "").startswith("sk_live_")


# --- the load-bearing function -----------------------------------------------
def parse_signature(header: str) -> tuple[int, list]:
    """``(timestamp, [v1 signatures])`` from a `Stripe-Signature` header.

    A list because Stripe sends more than one v1 during a secret roll,
    and rejecting the second one breaks exactly the operation that exists
    to avoid downtime.
    """
    ts, sigs = 0, []
    for part in str(header or "").split(","):
        k, _, v = part.strip().partition("=")
        if k == "t":
            try:
                ts = int(v)
            except ValueError:
                ts = 0
        elif k == "v1":
            sigs.append(v)
    return ts, sigs


def verify_signature(raw_body: bytes, header: str, secret: str,
                     tolerance: int = SIGNATURE_TOLERANCE,
                     now: float | None = None) -> bool:
    """Whether this webhook really came from Stripe.

    THE FUNCTION THAT STANDS BETWEEN A PUBLIC URL AND FREE SUBSCRIPTIONS.
    Takes the RAW BODY: the signature is over bytes, and JSON that has
    been parsed and re-serialized is different bytes even when it means
    the same thing.
    """
    if not secret or not isinstance(raw_body, (bytes, bytearray)):
        return False
    ts, sigs = parse_signature(header)
    if not ts or not sigs:
        return False
    now = time.time() if now is None else now
    # A REPLAY IS A REAL ATTACK, not a theoretical one: a webhook captured
    # once is otherwise valid forever, so a cancellation event could be
    # replayed to undo an upgrade, or a payment event replayed to extend
    # access. The timestamp is inside the signed payload, so it cannot be
    # edited without breaking the signature.
    if abs(now - ts) > tolerance:
        return False
    signed = f"{ts}.".encode() + bytes(raw_body)
    want = hmac.new(str(secret).encode(), signed, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(want, s) for s in sigs)


# --- what a status means ------------------------------------------------------
def entitled(status: str, period_end: float | None = None,
             now: float | None = None, cancel_at_end: bool = False) -> bool:
    """Whether this subscription state grants paid access right now.

    `cancel_at_end` is a subscription cancelled from Stripe's portal,
    which by default runs to the end of the period already paid for. It
    keeps those days, and the wall goes up on the second the period ends —
    without waiting for Stripe's closing webhook, which Bot Fight Mode can
    eat (see `reconcile_session`).
    """
    st = str(status or "none").lower()
    if st in NOT_ENTITLED or st not in ENTITLED:
        return False
    if cancel_at_end and period_end:
        now = time.time() if now is None else now
        try:
            return float(period_end) > now
        except (TypeError, ValueError):
            return True
    return True


def describe(status: str, period_end: float | None = None,
             cancel_at_end: bool = False) -> str:
    """A sentence for the page. Says what is true, including the awkward
    cases — "payment failed" with what to do is more useful than
    "inactive"."""
    st = str(status or "none").lower()
    when = ""
    if period_end:
        try:
            when = time.strftime("%-d %b %Y", time.localtime(float(period_end)))
        except (TypeError, ValueError):
            when = ""
    # The paywall shows these too (app.js pwLapseHTML, next to its Update
    # card button), so they name the fix without naming a page.
    if cancel_at_end and when and st in ("active", "trialing"):
        ended = float(period_end) <= time.time()
        return (f"Cancelled — access {'ended' if ended else 'until'} {when}. "
                f"Nothing further will be charged.")
    if st == "active":
        return f"Subscribed — renews {when}." if when else "Subscribed."
    if st == "trialing":
        return f"Free trial — ends {when}." if when else "Free trial."
    if st == "past_due":
        return ("Payment failed — your access is paused. Update your card "
                "and the site opens again as soon as the payment clears.")
    if st == "canceled":
        return ("Cancelled. Nothing further will be charged — pick a plan "
                "to come back any time.")
    if st == "unpaid":
        return ("Unpaid — access has stopped. Update your card and pay the "
                "open invoice to start it again.")
    # Stripe pauses a subscription too (a trial that ended without a card,
    # or a pause set from the dashboard), and rows stored under the old
    # processor can still say it. "No subscription." would tell somebody
    # who deliberately paused that they have nothing (moved here from the
    # retired engine/paddle.py, roadmap #53).
    if st == "paused":
        return ("Paused — billing is suspended and access is off until you "
                "resume it. Nothing has been cancelled.")
    return "No subscription."


# --- request shapes (pure, so they can be tested without the network) --------
def _form(pairs: dict) -> bytes:
    return urllib.parse.urlencode(
        {k: v for k, v in pairs.items() if v not in (None, "")}).encode()


#: How long a double-tap is treated as one click, in seconds.
#:
#: Idempotency keys are bucketed by this. Longer is not safer: the key
#: also decides how soon somebody may deliberately start a SECOND
#: checkout — after cancelling, or to switch plans — and Stripe replays
#: the first session's response for 24 hours to a repeated key. Ten
#: minutes covers a slow phone and a fat thumb without stranding anyone.
IDEMPOTENCY_WINDOW = 600


def idempotency_key(user_id: int, plan_id: str, now: float | None = None) -> str:
    """The value for Stripe's `Idempotency-Key` HEADER.

    THIS USED TO BE A FORM FIELD NAMED `idempotency_key`, which is not a
    thing. Stripe reads idempotency from a header; a body parameter by
    that name is simply not the feature, so the double-tap protection the
    comment claimed was never switched on.

    It also used to be `qb-checkout-{user_id}` with no time component,
    which is worse than nothing had it worked: a fixed key per account
    means Stripe replays that account's FIRST session forever, so
    somebody who cancelled and came back — or who bought monthly and
    wanted yearly — would be handed a stale Checkout URL for the old
    plan, or a dead one, and no error would say why.
    """
    now = time.time() if now is None else float(now)
    bucket = int(now // IDEMPOTENCY_WINDOW)
    return f"qb-{int(user_id)}-{plan_id}-{bucket}"


def checkout_request(secret_key: str, price_id: str, user_id: int,
                     email: str, success_url: str, cancel_url: str,
                     plan_id: str = DEFAULT_PLAN,
                     now: float | None = None,
                     trial_days: int = 0,
                     allow_promo: bool = True,
                     coupon: str = "") -> tuple[str, dict, bytes]:
    """``(url, headers, body)`` for a Checkout Session.

    `client_reference_id` is how the webhook finds its way back to a row
    in our own users table. Without it a completed payment arrives with a
    Stripe customer id and no way to say whose it is.

    The plan is stamped into metadata in BOTH places — on the session and
    on the subscription — because they are different objects and the
    later `customer.subscription.updated` events carry only the
    subscription's own. Stamped one place, the plan is known at purchase
    and forgotten at the first renewal.
    """
    body = _form({
        "mode": "subscription",
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": str(int(user_id)),
        "customer_email": email,
        "metadata[plan]": plan_id,
        "metadata[user_id]": str(int(user_id)),
        "subscription_data[metadata][plan]": plan_id,
        "subscription_data[metadata][user_id]": str(int(user_id)),
        # An address is collected because a card issuer's AVS check wants
        # one, not because we want the address. Stripe holds it.
        "billing_address_collection": "auto",
    })
    # The promo-code box, and ONLY on a plan that has a promo. See PROMOS:
    # the three plans share one Stripe Product, so a coupon offered at
    # checkout is offered on whatever is in the cart, and a "2 months"
    # discount against a yearly price is 75% off the whole year.
    #
    # This does leave the site with two code systems — Stripe's, here, and
    # ours in engine/redeem.py — which is the thing the old comment here
    # refused to do. What makes it survivable is that they cannot both
    # claim the same code (tests/test_promo.py fails if they overlap) and
    # that typing a checkout code into the account page's redeem box now
    # gets told where it actually goes, instead of "that code is not
    # valid".
    # A REFERRAL'S DISCOUNT (engine/referrals) rides in as the session's
    # own coupon, chosen by the caller from the database. Stripe takes a
    # coupon or the promo box, never both, so a referred first purchase
    # gets its $6.25 and no box.
    if coupon:
        body += b"&" + _form({"discounts[0][coupon]": str(coupon)})
    elif allow_promo and promos_for(plan_id):
        body += b"&" + _form({"allow_promotion_codes": "true"})
    if int(trial_days or 0) > 0:
        # PAYMENT METHOD STILL COLLECTED. Stripe's default for a
        # subscription Checkout is to take the card up front and convert
        # when the trial ends, which is what this is: a trial, not a
        # giveaway. Left implicit rather than set, because Stripe's
        # default is the behaviour we want and pinning it here would be a
        # second place for it to drift from the dashboard.
        body += b"&" + _form({
            "subscription_data[trial_period_days]": str(int(trial_days)),
        })
    return f"{API}/checkout/sessions", {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Idempotency-Key": idempotency_key(user_id, plan_id, now),
    }, body


def portal_request(secret_key: str, customer_id: str,
                   return_url: str) -> tuple[str, dict, bytes]:
    """The Stripe-hosted page where someone changes a card or cancels.

    Cancelling is THEIRS to do, on Stripe's own page. Building our own
    cancel flow would mean a company deciding how hard it is to leave,
    and this one is not going to be that.
    """
    body = _form({"customer": customer_id, "return_url": return_url})
    return f"{API}/billing_portal/sessions", {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/x-www-form-urlencoded",
    }, body


def _post(url: str, headers: dict, body: bytes, timeout: int = 20) -> dict:
    """NOTHING FROM `headers` EVER REACHES AN EXCEPTION. The secret key
    lives there, and a key in a traceback is a key in a log file."""
    req = urllib.request.Request(url, data=body, headers=dict(headers),
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            said = json.loads(exc.read().decode("utf-8", "replace"))
            detail = str((said.get("error") or {}).get("message") or "")
        except Exception:                                # noqa: BLE001
            detail = ""
        raise BillingUnavailable(
            f"Stripe refused the request (HTTP {exc.code})."
            f"{' ' + detail if detail else ''}") from exc
    except Exception as exc:                             # noqa: BLE001
        raise BillingUnavailable(f"Could not reach Stripe: {exc}") from exc


def _get(url: str, secret_key: str, timeout: int = 20,
         headers: dict | None = None) -> dict:
    """A read from Stripe. SAME RULE AS `_post`: the key never escapes.

    Separate from `_post` rather than a mode flag on it, because the two
    have different failure meanings — a failed read is "we could not
    check", a failed write may be "we charged somebody and lost the
    reply" — and a caller that cannot tell them apart retries the wrong
    one.
    """
    # `headers` is for a caller that must pin a Stripe-Version (see
    # stripeset.PROMO_API_VERSION). The Authorization line is set LAST so
    # a caller cannot replace the key by passing one of its own.
    head = dict(headers or {})
    head["Authorization"] = f"Bearer {secret_key}"
    req = urllib.request.Request(url, headers=head, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            said = json.loads(exc.read().decode("utf-8", "replace"))
            detail = str((said.get("error") or {}).get("message") or "")
        except Exception:                                # noqa: BLE001
            detail = ""
        raise BillingUnavailable(
            f"Stripe refused the request (HTTP {exc.code})."
            f"{' ' + detail if detail else ''}") from exc
    except Exception as exc:                             # noqa: BLE001
        raise BillingUnavailable(f"Could not reach Stripe: {exc}") from exc


def start_checkout(user_id: int, email: str, success_url: str,
                   cancel_url: str, plan_id: str = DEFAULT_PLAN,
                   trial_days: int = 0, allow_promo: bool = True,
                   coupon: str = "") -> str:
    """The Stripe-hosted URL to send the customer to.

    `trial_days` and `allow_promo` are decided by the CALLER, from the
    database, and never from anything the browser sent. A trial length
    taken off a request body would be a free subscription for anyone who
    edited it, and a promo flag taken off one would let an account that
    has already subscribed re-buy at a discount by editing a checkbox.
    """
    sk, _wh, _monthly = keys()
    price = price_for(plan_id)
    url, headers, body = checkout_request(sk, price, user_id, email,
                                          success_url, cancel_url, plan_id,
                                          trial_days=int(trial_days or 0),
                                          allow_promo=bool(allow_promo),
                                          coupon=str(coupon or ""))
    out = _post(url, headers, body)
    got = out.get("url")
    if not got:
        raise BillingUnavailable("Stripe did not return a Checkout URL.")
    return str(got)


def referral_coupon_request(secret_key: str) -> tuple[str, dict, bytes]:
    """The referral's Stripe coupon (engine/referrals.COUPON_ID): $6.25 off,
    as an AMOUNT — never a percentage, see that module — repeating for one
    month, which covers the first payment whether or not a trial comes
    first (a 3-day trial's first charge lands inside the month; the next
    renewal does not)."""
    from engine import referrals as RF
    body = _form({"id": RF.COUPON_ID, "amount_off": str(RF.NEW_MEMBER_OFF_CENTS), "currency": "usd",
                  "duration": "repeating", "duration_in_months": "1",
                  "name": "Referral — $6.25 off your first payment"})
    return f"{API}/coupons", {"Authorization": f"Bearer {secret_key}",
                              "Content-Type": "application/x-www-form-urlencoded",
                              "Idempotency-Key": f"qb-{RF.COUPON_ID}"}, body


_referral_coupon_ok = False


def ensure_referral_coupon() -> str:
    """The coupon's id, made in Stripe the first time a referred account
    checks out. Already there is fine; anything else raises
    BillingUnavailable and the caller checks out without it."""
    global _referral_coupon_ok
    from engine import referrals as RF
    if _referral_coupon_ok:
        return RF.COUPON_ID
    sk, _wh, _m = keys()
    try:
        got = _get(f"{API}/coupons/{RF.COUPON_ID}", sk)
        if got.get("id") == RF.COUPON_ID:
            _referral_coupon_ok = True
            return RF.COUPON_ID
    except BillingUnavailable:
        pass
    url, headers, body = referral_coupon_request(sk)
    try:
        _post(url, headers, body)
    except BillingUnavailable as exc:
        if "already exists" not in str(exc).lower():
            raise
    _referral_coupon_ok = True
    return RF.COUPON_ID


def credit_request(secret_key: str, customer_id: str, cents: int, key: str,
                   note: str) -> tuple[str, dict, bytes]:
    """A credit on a customer's Stripe balance, which Stripe takes off
    their next invoice by itself. NEGATIVE is a credit in Stripe's
    terms. The Idempotency-Key is the referral's own, so a retry is the
    same credit, never a second one."""
    body = _form({"amount": str(-abs(int(cents))), "currency": "usd", "description": note})
    return (f"{API}/customers/{customer_id}/balance_transactions",
            {"Authorization": f"Bearer {secret_key}",
             "Content-Type": "application/x-www-form-urlencoded",
             "Idempotency-Key": str(key)}, body)


def credit_balance(customer_id: str, cents: int, key: str, note: str) -> str:
    sk, _wh, _m = keys()
    url, headers, body = credit_request(sk, customer_id, cents, key, note)
    return str(_post(url, headers, body).get("id") or "")


def settle_referrals(conn) -> int:
    """Pay every referral credit owed to a member Stripe knows, now —
    from the webhook the moment a friend's membership goes active, and
    from the sweep for any the webhook could not pay. Never raises."""
    try:
        from engine import referrals as RF
        return RF.settle(conn, lambda uid: status_for(conn, uid).get("customer_id"), credit_balance)
    except Exception:                                        # noqa: BLE001
        return 0


def open_portal(customer_id: str, return_url: str) -> str:
    sk, _wh, _price = keys()
    url, headers, body = portal_request(sk, customer_id, return_url)
    out = _post(url, headers, body)
    got = out.get("url")
    if not got:
        raise BillingUnavailable("Stripe did not return a portal URL.")
    return str(got)


# --- reading an event ---------------------------------------------------------
def read_event(payload: dict) -> dict | None:
    """``{user_id, customer_id, subscription_id, status, period_end}``.

    Returns None for an event we do not act on — which is acknowledged
    with a 200 rather than an error, because Stripe retries anything that
    is not 2xx and a rejected irrelevant event becomes a retry loop.

    `user_id` is only present on the Checkout event; subscription updates
    carry the customer id instead, and the caller matches on that. That
    asymmetry is Stripe's, not ours, and pretending otherwise is how the
    link between a payment and an account gets quietly lost.
    """
    kind = str((payload or {}).get("type") or "")
    if kind not in HANDLED:
        return None
    obj = (((payload or {}).get("data") or {}).get("object") or {})
    out = {"event": kind, "customer_id": None, "subscription_id": None,
           "user_id": None, "status": None, "period_end": None,
           "plan": None, "cancel_at_end": None, "at": None}
    # WHEN STRIPE MADE THE EVENT, which is not when it reaches us. Stripe
    # does not deliver in order and retries a failed delivery for days, so
    # a payment failure first refused at the door (Bot Fight Mode, a
    # restart) can land AFTER the payment that fixed it. `apply_event`
    # drops an event older than the one the row already reflects; while a
    # failed card walled nobody, arriving late cost nothing, and now it
    # would wall a customer who has paid.
    try:
        out["at"] = float(payload.get("created"))
    except (TypeError, ValueError):
        out["at"] = None
    # Stamped by `checkout_request` on both the session and the
    # subscription, so it survives past the first renewal. Read here
    # rather than looked up from the price, because a price id we no
    # longer have in our env — an old one, or one made by hand in the
    # dashboard — would come back None and blank a plan we already knew.
    meta = obj.get("metadata")
    if isinstance(meta, dict):
        got = str(meta.get("plan") or "")
        out["plan"] = got if got in PLANS else None

    if kind == "checkout.session.completed":
        ref = obj.get("client_reference_id")
        try:
            out["user_id"] = int(ref) if ref is not None else None
        except (TypeError, ValueError):
            out["user_id"] = None
        out["customer_id"] = obj.get("customer")
        out["subscription_id"] = obj.get("subscription")
        # A completed Checkout with a paid invoice is active; Stripe sends
        # the subscription event too, and that one carries the real status.
        out["status"] = ("active" if obj.get("payment_status") == "paid"
                         else "incomplete")
        return out

    if kind == "invoice.payment_failed":
        out["customer_id"] = obj.get("customer")
        out["subscription_id"] = obj.get("subscription")
        out["status"] = "past_due"
        return out

    # customer.subscription.*
    out["customer_id"] = obj.get("customer")
    out["subscription_id"] = obj.get("id")
    if not out["plan"]:
        # No metadata: an older subscription, or one created by hand.
        # The price id on the first line item still identifies the plan
        # when it is one of ours, and identifies nothing when it is not,
        # which `plan_of` reports as None rather than a guess.
        try:
            items = ((obj.get("items") or {}).get("data") or [])
            out["plan"] = plan_of(((items[0] or {}).get("price")
                                   or {}).get("id"))
        except (IndexError, AttributeError, TypeError):
            out["plan"] = None
    out["status"] = ("canceled" if kind.endswith(".deleted")
                     else str(obj.get("status") or "none"))
    out["period_end"] = _period_end(obj)
    # CANCELLED, BUT PAID THROUGH A DATE. Stripe's portal cancels at the
    # period's end by default: the subscription stays `active` and carries
    # `cancel_at_period_end` (newer API versions may set `cancel_at` to
    # that date instead), and it is deleted when the date comes. Either
    # one counts; both false — a cancellation undone — is False, not None,
    # so the stored flag is cleared rather than kept.
    out["cancel_at_end"] = bool(obj.get("cancel_at_period_end")
                                or obj.get("cancel_at"))
    return out


def _period_end(obj: dict) -> float | None:
    """Paid-through, from wherever this API version keeps it.

    STRIPE MOVED IT. `current_period_start/end` used to sit on the
    Subscription; on recent API versions they live on each subscription
    ITEM instead, because a subscription can hold items on different
    cycles. A new account gets a new API version, so a brand-new install
    reads None from the old location and nothing says why.

    Found on the first real purchase: the row came back `active` with the
    right plan and `period_end` NULL. Which looks harmless and is not —
    `entitled()` grants `past_due` only while the paid-through date is in
    the future, so a null makes `bool(period_end)` False and cuts a
    customer off the instant a renewal fails. The whole grace period,
    which exists because a failed renewal is usually an expiry date
    rather than a decision, was silently switched off.

    Both locations are read, newest first, and the LATEST item wins when
    there are several — access should end when the last thing they paid
    for ends, not the first.
    """
    best = None
    try:
        for item in ((obj.get("items") or {}).get("data") or []):
            got = (item or {}).get("current_period_end")
            if got is None:
                continue
            got = float(got)
            best = got if best is None else max(best, got)
    except (AttributeError, TypeError, ValueError):
        best = None
    if best is not None:
        return best
    end = obj.get("current_period_end")
    try:
        return float(end) if end is not None else None
    except (TypeError, ValueError):
        return None


# --- storage ------------------------------------------------------------------
from .accounts import once_per_db as _once_per_db   # noqa: E402  (audit F-9)


@_once_per_db
def init(conn) -> None:
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS subscriptions (
        user_id         INTEGER PRIMARY KEY
                        REFERENCES users(id) ON DELETE CASCADE,
        customer_id     TEXT,
        subscription_id TEXT,
        status          TEXT NOT NULL DEFAULT 'none',
        period_end      REAL,
        updated_at      REAL NOT NULL
      );
      CREATE INDEX IF NOT EXISTS subs_customer
        ON subscriptions(customer_id);
      -- Stripe retries, and a retry must not be a second grant. Seen ids
      -- are remembered so replaying an event is a no-op.
      CREATE TABLE IF NOT EXISTS billing_events (
        event_id TEXT PRIMARY KEY,
        seen_at  REAL NOT NULL
      );
    """)
    # `plan` arrived after the table did, so it is added rather than
    # declared. ALTER TABLE ADD COLUMN throws when the column is already
    # there and there is no IF NOT EXISTS for it in SQLite, so the
    # existing columns are read first — cheaper and clearer than
    # catching an exception whose message we would have to match on.
    have = {r[1] for r in conn.execute("PRAGMA table_info(subscriptions)")}
    if "plan" not in have:
        conn.execute("ALTER TABLE subscriptions ADD COLUMN plan TEXT")
    # The lapse lock (2026-10-12), added the same way: whether Stripe will
    # cancel this at the period's end, when we last read the subscription
    # from Stripe ourselves (`refresh`), and the creation time of the
    # newest event the row reflects (`apply_event`'s ordering).
    # And the trial reminder (engine/trialnote, 2026-10-26): the trial end
    # this row was last reminded about, so the day-before email goes once.
    for col, kind in (("cancel_at_end", "INTEGER"), ("checked_at", "REAL"),
                      ("event_at", "REAL"), ("trial_noted", "REAL")):
        if col not in have:
            conn.execute(f"ALTER TABLE subscriptions ADD COLUMN {col} {kind}")
    conn.commit()


def already_handled(conn, event_id: str) -> bool:
    """True if this exact event has been applied before.

    Stripe delivers at least once, not exactly once. Without this, a
    retried `checkout.session.completed` is a second subscription row and
    a retried cancellation can undo a fresh upgrade.
    """
    if not event_id:
        return False
    row = conn.execute("SELECT 1 FROM billing_events WHERE event_id=?",
                       (str(event_id),)).fetchone()
    if row:
        return True
    conn.execute("INSERT INTO billing_events (event_id, seen_at) VALUES (?,?)",
                 (str(event_id), time.time()))
    conn.execute("DELETE FROM billing_events WHERE seen_at < ?",
                 (time.time() - 60 * 86400,))
    conn.commit()
    return False


def user_for_customer(conn, customer_id: str) -> int | None:
    if not customer_id:
        return None
    row = conn.execute("SELECT user_id FROM subscriptions WHERE customer_id=?",
                       (str(customer_id),)).fetchone()
    return int(row["user_id"]) if row else None


def apply_event(conn, event: dict) -> bool:
    """Move a subscription to what Stripe says it is. True if applied.

    Refuses to guess: an event whose customer we have never seen and
    which carries no `client_reference_id` cannot be attributed to an
    account, and inventing one would attach somebody's payment to the
    wrong person.
    """
    if not event:
        return False
    uid = event.get("user_id")
    if uid is None:
        uid = user_for_customer(conn, event.get("customer_id"))
    if uid is None:
        return False
    was = conn.execute("SELECT status, period_end, event_at FROM subscriptions "
                       "WHERE user_id=?", (int(uid),)).fetchone()
    at = event.get("at")
    if at is not None and was is not None and was[2] is not None \
            and float(at) < float(was[2]):
        # OLDER THAN WHAT THE ROW ALREADY SAYS: a late delivery, or a
        # retry of one (see `read_event`). Dropped — applying it would put
        # back a state Stripe has already moved past, and a payment
        # failure put back over the payment that fixed it walls somebody
        # who has paid.
        return False
    cancel = event.get("cancel_at_end")
    # A NEW SUBSCRIPTION STARTS CLEAN. Somebody who cancelled, lapsed and
    # bought again keeps their row (one per account), and the Checkout
    # event carries no date and no cancel flag — so COALESCE would hand
    # the new plan the old one's "cancelled, paid through last month" and
    # wall a customer who paid a minute ago. When the subscription id
    # changes, the date and the flag are the new event's or nothing.
    fresh = ("excluded.subscription_id IS NOT NULL AND "
             "excluded.subscription_id IS NOT subscription_id")
    conn.execute(
        "INSERT INTO subscriptions (user_id, customer_id, subscription_id, "
        "status, period_end, plan, cancel_at_end, event_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET "
        "  customer_id=COALESCE(excluded.customer_id, customer_id), "
        "  subscription_id=COALESCE(excluded.subscription_id, subscription_id), "
        "  status=excluded.status, "
        f"  period_end=CASE WHEN {fresh} THEN excluded.period_end "
        "    ELSE COALESCE(excluded.period_end, period_end) END, "
        # COALESCE, so an event that carries no plan — an
        # invoice.payment_failed, say — leaves the known one alone
        # instead of blanking the term off the account page.
        "  plan=COALESCE(excluded.plan, plan), "
        f"  cancel_at_end=CASE WHEN {fresh} THEN excluded.cancel_at_end "
        "    ELSE COALESCE(excluded.cancel_at_end, cancel_at_end) END, "
        "  event_at=COALESCE(excluded.event_at, event_at), "
        "  updated_at=excluded.updated_at",
        (int(uid), event.get("customer_id"), event.get("subscription_id"),
         str(event.get("status") or "none"), event.get("period_end"),
         event.get("plan"), None if cancel is None else int(bool(cancel)),
         None if at is None else float(at), time.time()))
    conn.commit()
    # A trial, a subscription, a conversion, a cancellation or a renewal,
    # counted (no account attached) when analytics is switched on; a no-op
    # otherwise. See engine/analytics.py.
    from engine import analytics as AN
    kind = AN.transition(was[0] if was else None, was[1] if was else None,
                         event.get("status"), event.get("period_end"))
    if kind:
        AN.record(kind)
    # A REFERRED ACCOUNT'S FIRST MEMBERSHIP, PAID (engine/referrals): the
    # member whose code it came in on is owed $6.25 on their next bill.
    # `active` is a paid invoice — a trial is `trialing`, and a failed
    # first charge is `incomplete` or `past_due` — so a referral that
    # never pays never earns. Once per referred account, however often
    # Stripe repeats itself.
    if str(event.get("status") or "") == "active":
        try:
            from engine import referrals as RF
            if RF.first_payment(conn, int(uid)) is not None and configured():
                settle_referrals(conn)
        except Exception:                                    # noqa: BLE001
            pass
    return True


#: A Checkout Session id as Stripe issues them: cs_test_… or cs_live_…,
#: then letters and digits only. Nothing that can reach a second path
#: segment or a query string.
_SESSION_ID = re.compile(r"cs_(test|live)_[A-Za-z0-9]{1,190}")


def reconcile_session(conn, user_id: int, session_id: str) -> dict:
    """Ask Stripe directly whether this Checkout Session was paid, and
    write the entitlement if it was. Returns the status dict either way.

    WHY THIS EXISTS AT ALL. Entitlement normally moves when the signed
    webhook arrives, and the webhook is a request from Stripe's servers to
    ours — not a browser. Anything in front of the site that decides what
    a robot looks like gets a vote on whether the customer gets what they
    paid for. Cloudflare's Bot Fight Mode went on over the live site on
    2026-08-21, and on the free plan it cannot be scoped to skip a path.
    That is one example; a webhook endpoint being down, slow, or
    misconfigured are the others, and they all end the same way — money
    taken, site still locked, and a support email that starts "I paid".

    So the browser coming back from Stripe carries the session id, and we
    ASK. A read from Stripe is authoritative in a way no webhook delivery
    can be, because it does not depend on anything reaching us.

    WHAT MAKES THIS SAFE. The session id is not a credential and is not
    treated as one. It grants nothing by being presented:

      * the session is fetched from Stripe, not read from the request;
      * Stripe's own `payment_status` must say `paid`;
      * `client_reference_id` must be THIS user. A session id belonging
        to somebody else — pasted, guessed, or scraped out of a shared
        URL — entitles nobody, least of all the person holding it.

    An unpaid or unknown session changes nothing and says so quietly.
    """
    out = status_for(conn, user_id)
    sid = str(session_id or "").strip()
    # The whole shape, not a prefix (audit E-11): the id is put into the
    # Stripe URL path, and "cs_x/../../v1/customers" passes a prefix check.
    if not _SESSION_ID.fullmatch(sid):
        return out
    if out.get("entitled"):
        return out                    # already in; nothing to reconcile
    secret = keys()[0]
    sess = _get(f"{API}/checkout/sessions/{sid}?expand[]=subscription",
                secret)
    # "paid" OR A TRIAL. A subscription Checkout that starts a trial
    # completes with payment_status "no_payment_required" — Stripe took
    # the card and deliberately charged nothing yet — so requiring "paid"
    # here turned away every trial signup, and the trial plan is the
    # DEFAULT plan. Card captured, subscription trialing at Stripe,
    # customer on the paywall watching a spinner wait for a webhook that
    # Bot Fight Mode already ate: the exact situation this endpoint was
    # built to rescue, refused by its own first check. The webhook path
    # has always entitled `trialing` (ENTITLED, above); the extra
    # conditions a no-charge session must meet are below, after the
    # ownership check.
    pay = str(sess.get("payment_status") or "")
    if pay not in ("paid", "no_payment_required"):
        return out
    # THE OWNERSHIP CHECK, and it is the whole security of this endpoint.
    ref = str(sess.get("client_reference_id") or "")
    meta_uid = str((sess.get("metadata") or {}).get("user_id") or "")
    if ref != str(int(user_id)) and meta_uid != str(int(user_id)):
        return out
    sub = sess.get("subscription")
    if isinstance(sub, str):
        sub = _get(f"{API}/subscriptions/{sub}", secret)
    sub = sub or {}
    if pay != "paid":
        # A NO-CHARGE SESSION GRANTS NOTHING BY ITSELF. Stripe must say
        # the Checkout finished ("complete"), and the subscription it
        # created must be in a state the webhook path would entitle —
        # for a fresh trial that is `trialing`. An abandoned session, a
        # trial whose card setup failed, or a zero-total session with no
        # subscription behind it all stop here.
        if str(sess.get("status") or "") != "complete":
            return out
        if not sub.get("id") or str(sub.get("status") or "") not in ENTITLED:
            return out
    apply_event(conn, {
        "user_id": int(user_id),
        "customer_id": (sess.get("customer") if isinstance(sess.get("customer"), str)
                        else (sess.get("customer") or {}).get("id")),
        "subscription_id": sub.get("id"),
        # A paid session whose subscription object has not settled yet is
        # still a paid session. `active` is what Stripe will say; saying
        # it a second early is right where the alternative is telling a
        # paying customer they have nothing.
        "status": str(sub.get("status") or "active"),
        "period_end": _period_end(sub) if sub else None,
        "plan": ((sub.get("metadata") or {}).get("plan")
                 or (sess.get("metadata") or {}).get("plan")),
        "cancel_at_end": (bool(sub.get("cancel_at_period_end")
                               or sub.get("cancel_at")) if sub else None),
        # A READ OF STRIPE, true as of now — so a webhook made before it
        # and delivered after (a `customer.subscription.created` that
        # still said `incomplete`, say) cannot put the row back.
        "at": time.time(),
    })
    return status_for(conn, user_id)


def status_for(conn, user_id: int, describe_with=None) -> dict:
    """What the page shows. Never a promise the database cannot back.

    `describe_with` is how the PROCESSOR gets to write its own sentence
    for a status this module has no wording for. Paddle's `paused` is the
    live example: the storage layer stores it correctly and `entitled()`
    refuses it correctly, but the default sentence here has never heard
    of it and would fall through to "No subscription." — telling somebody
    who deliberately paused that they have nothing, which is both wrong
    and the kind of wrong that generates a support email.
    """
    say = describe_with or describe
    row = conn.execute(
        "SELECT customer_id, subscription_id, status, period_end, plan, "
        "cancel_at_end FROM subscriptions WHERE user_id=?",
        (int(user_id),)).fetchone()
    if row is None:
        return {"status": "none", "entitled": False, "plan": None,
                "plan_name": None, "note": say("none"), "customer_id": None,
                "open": False, "cancel_at_end": False}
    st, end = row["status"], row["period_end"]
    plan = row["plan"] if "plan" in row.keys() else None
    cancel = bool(row["cancel_at_end"])
    return {"status": st, "period_end": end, "plan": plan,
            "plan_name": (PLANS[plan]["name"] if plan in PLANS else None),
            "entitled": entitled(st, end, cancel_at_end=cancel),
            "note": (say(st, end, cancel) if cancel else say(st, end)),
            "customer_id": row["customer_id"],
            # Not `live`: /api/billing/status already says `live` for
            # Stripe's live mode, and this dict is merged into it.
            "open": str(st or "").lower() in OPEN,
            "cancel_at_end": cancel}


# --- hearing about a lapse when the webhook does not say -----------------------
#: A row is re-read from Stripe when its last read is older than this. An
#: entitled row, hourly, on the page's own status call: a lapse whose
#: webhook never arrived walls a reader who is using the site within the
#: hour.
RECHECK_S = 3600
#: A walled row that Stripe can still revive (`past_due`, `unpaid`,
#: `incomplete`), once a minute: somebody back from fixing the card on
#: Stripe's page is let in on their next page load, webhook or not.
RECHECK_LOCKED_S = 60
#: AN OPEN OF THE SITE READS STRIPE. Ethan, 2026-10-13: "every time a user
#: opens the site or launches the site it should check too see if they are
#: still subscribed". The page's boot call, its call after a sign-in and
#: its call on coming back to the tab say `fresh=1`, and the read is then
#: due once this much has passed since the last one: a reload loop asks
#: Stripe once a minute, not once a reload.
RECHECK_OPEN_S = 60
#: The launcher's sweep re-reads every row that is not final this often,
#: which covers the account nobody is loading pages for.
SWEEP_EVERY_S = 6 * 3600

#: A Subscription id as Stripe issues them. The whole shape, for the same
#: reason as `_SESSION_ID`: it is put into a URL path.
_SUB_ID = re.compile(r"sub_[A-Za-z0-9]{1,190}")


def refresh(conn, user_id: int, now: float | None = None, fetch=None,
            every: float | None = None) -> bool:
    """Re-read this account's subscription from Stripe and store what it
    says. True if a read was applied.

    THE WEBHOOK IS NOT ENOUGH ON ITS OWN, for the reason
    `reconcile_session` exists: it is a request from Stripe's servers to
    ours, and anything in front of the site that decides what a robot looks
    like gets a vote on whether it arrives. A GRANT that never arrived is
    rescued by the return trip from Checkout. A LAPSE that never arrived
    had nothing: a failed card or a cancellation from Stripe's dashboard
    kept the site open until somebody noticed. This is the noticing — a
    read of Stripe, paced by `every` (RECHECK_S, or RECHECK_LOCKED_S for a
    walled row), and a no-op for a final status, an unconfigured server or
    a row with no subscription id.

    `fetch(subscription_id) -> dict` replaces the Stripe call in tests,
    which never touch the network.

    Never raises for Stripe's sake: a read that fails leaves the row as it
    was — the webhook may still land, and the next due read tries again.
    """
    now = time.time() if now is None else now
    row = conn.execute(
        "SELECT status, subscription_id, checked_at FROM subscriptions "
        "WHERE user_id=?", (int(user_id),)).fetchone()
    if row is None:
        return False
    st, sid, last = str(row[0] or "none").lower(), str(row[1] or ""), row[2]
    if st in FINAL or not _SUB_ID.fullmatch(sid):
        return False
    if every is None:
        every = RECHECK_S if st in ENTITLED else RECHECK_LOCKED_S
    if last is not None and now - float(last) < every:
        return False
    if fetch is None and not configured():
        return False
    # Stamped BEFORE the read, so a Stripe that hangs is asked once per
    # interval rather than by every request that arrives while it hangs.
    conn.execute("UPDATE subscriptions SET checked_at=? WHERE user_id=?",
                 (now, int(user_id)))
    conn.commit()
    try:
        sub = (fetch(sid) if fetch is not None else
               _get(f"{API}/subscriptions/{sid}", keys()[0], timeout=5))
    except Exception:                                    # noqa: BLE001
        return False
    if not isinstance(sub, dict) or sub.get("id") != sid:
        return False
    ev = read_event({"type": "customer.subscription.updated",
                     "data": {"object": sub}})
    ev["user_id"] = int(user_id)
    # True as of the read, so an older event delivered late is dropped.
    ev["at"] = now
    return apply_event(conn, ev)


def recheck_soon(conn, user_id: int) -> None:
    """Make the next status call read Stripe, whatever the interval says.

    Called when somebody opens Stripe's billing page. Whatever they do
    there — a new card, a paid invoice, a cancellation — the page they
    come back to should already know it, not a minute later.
    """
    conn.execute("UPDATE subscriptions SET checked_at=NULL WHERE user_id=?",
                 (int(user_id),))
    conn.commit()


def sweep(conn, now: float | None = None, fetch=None) -> int:
    """Refresh every row that is not final and has not been read from
    Stripe in SWEEP_EVERY_S. The launcher runs it on a timer; returns how
    many reads were applied."""
    now = time.time() if now is None else now
    marks = ",".join("?" * len(FINAL))
    users = [r[0] for r in conn.execute(
        f"SELECT user_id FROM subscriptions WHERE status NOT IN ({marks}) "
        "AND (checked_at IS NULL OR checked_at < ?)",
        (*FINAL, now - SWEEP_EVERY_S)).fetchall()]
    return sum(1 for uid in users
               if refresh(conn, uid, now=now, fetch=fetch, every=SWEEP_EVERY_S))
