"""Create the Stripe catalogue from the prices this repo already states.

Ethan, 2026-08-21: *"figure out how to code stripe into the website
seemlessly and get it all set and square."*

WHY THIS IS CODE AND NOT A DASHBOARD CHECKLIST. There are three prices,
each has to be typed into a config file as a `price_xxx` id, and a
mistyped or swapped id does not fail — it charges the wrong amount to
somebody who thinks they bought something else. The dashboard is a fine
place to *look* at prices and a bad place to *transcribe* them. So the
numbers live in `billing.PLANS`, this module creates prices to match, and
the ids come back as lines to paste rather than as digits to copy.

IT IS SAFE TO RUN TWICE. Every price carries a `lookup_key`, which Stripe
enforces as unique per account, and the first thing this does is ask
which keys already exist. A second run reports what it found and creates
nothing. That matters more than it sounds: the natural way to use this is
to run it, get interrupted, and run it again, and the natural bug is four
subscriptions' worth of duplicate prices with nothing to say which is
canonical.

IT NEVER EDITS AN EXISTING PRICE, because Stripe prices are immutable by
design — that is a feature, since a price someone is subscribed to must
not silently change under them. If `billing.PLANS` says $25 and the
existing price says $30, this REPORTS the mismatch and refuses to
pretend; changing the price is a deliberate act with live subscribers to
think about, and `docs/BILLING.md` has that path.

WHAT IT WILL NOT DO. It will not print a secret key, will not write to
secrets.local, and will not touch anything that already has a customer
attached. Writing the file itself was tempting and is wrong: the one
place a key could leak from is a file this process writes, and a human
pasting three lines is a human who has seen what landed there.

    python3 launch.py --stripe-setup      # create or verify
    python3 launch.py --stripe            # check what is configured

Standard library only, through `billing._get` / `billing._post`.
"""

from __future__ import annotations

import os
import urllib.request

from . import billing as BI

API = BI.API

#: `product:` metadata we set so a human in the dashboard can tell which
#: objects this script owns. Stripe has no other marker for it.
OWNER_TAG = "qellys-books"


class SetupError(RuntimeError):
    """The catalogue is not what it should be, and we will not guess."""


# --- reading what is already there -------------------------------------------
def existing_prices(secret_key: str) -> dict:
    """``{lookup_key: price object}`` for the three keys we care about.

    One request, not three. Stripe takes repeated `lookup_keys[]`, and
    three round trips to answer one question is three chances for a
    partial answer.
    """
    keys = [BI.PLANS[p]["lookup_key"] for p in BI.PLAN_ORDER]
    query = "&".join(f"lookup_keys[]={k}" for k in keys)
    got = BI._get(f"{API}/prices?{query}&active=true&limit=100", secret_key)
    out = {}
    for row in (got.get("data") or []):
        lk = row.get("lookup_key")
        if lk:
            out[str(lk)] = row
    return out


def find_product(secret_key: str) -> dict | None:
    """Our product, if it exists. Matched on metadata, never on name.

    A name match would attach us to whatever somebody else called
    "Qellys Book" in the dashboard, and renaming a product — which is
    allowed and harmless — would make this create a second one.
    """
    got = BI._get(f"{API}/products?active=true&limit=100", secret_key)
    for row in (got.get("data") or []):
        meta = row.get("metadata") or {}
        if str(meta.get("owner") or "") == OWNER_TAG:
            return row
    return None


# --- creating what is missing -------------------------------------------------
def create_product(secret_key: str) -> dict:
    headers = {"Authorization": f"Bearer {secret_key}",
               "Content-Type": "application/x-www-form-urlencoded",
               "Idempotency-Key": f"{OWNER_TAG}-product"}
    body = BI._form({
        "name": BI.PRODUCT_NAME,
        "description": BI.PRODUCT_DESC,
        "metadata[owner]": OWNER_TAG,
        # What shows on the card statement. Stripe truncates to 22
        # characters and uppercases it; leaving it unset means the
        # statement reads however the account is named, and an
        # unrecognised statement line is the single most common cause of
        # a dispute that was never a complaint about the product.
        "statement_descriptor": "QELLYS BOOK",
    })
    return BI._post(f"{API}/products", headers, body)


def create_price(secret_key: str, product_id: str, plan_id: str) -> dict:
    plan = BI.PLANS[plan_id]
    headers = {"Authorization": f"Bearer {secret_key}",
               "Content-Type": "application/x-www-form-urlencoded",
               "Idempotency-Key": f"{OWNER_TAG}-price-{plan_id}"}
    body = BI._form({
        "product": product_id,
        "currency": "usd",
        "unit_amount": str(int(plan["cents"])),
        "recurring[interval]": plan["interval"],
        "recurring[interval_count]": str(int(plan["interval_count"])),
        "lookup_key": plan["lookup_key"],
        "nickname": f"{BI.PRODUCT_NAME} — {plan['name']}",
        "metadata[owner]": OWNER_TAG,
        "metadata[plan]": plan_id,
        # Digital goods, and the price on the page is the price charged.
        # `exclusive` would add tax on top at checkout and make the
        # advertised $25 a $27.13 — which is legal, and is not what the
        # page says.
        "tax_behavior": "inclusive",
    })
    return BI._post(f"{API}/prices", headers, body)


def _matches(price: dict, plan_id: str) -> list:
    """Ways an existing price disagrees with `billing.PLANS`."""
    plan = BI.PLANS[plan_id]
    rec = price.get("recurring") or {}
    bad = []
    if int(price.get("unit_amount") or 0) != int(plan["cents"]):
        bad.append(f"amount is {price.get('unit_amount')} cents, "
                   f"we say {plan['cents']}")
    if str(price.get("currency") or "").lower() != "usd":
        bad.append(f"currency is {price.get('currency')!r}, we say 'usd'")
    if str(rec.get("interval") or "") != plan["interval"]:
        bad.append(f"interval is {rec.get('interval')!r}, "
                   f"we say {plan['interval']!r}")
    if int(rec.get("interval_count") or 0) != int(plan["interval_count"]):
        bad.append(f"interval_count is {rec.get('interval_count')}, "
                   f"we say {plan['interval_count']}")
    return bad


def ensure_catalogue(secret_key: str, create: bool = True) -> dict:
    """Make Stripe's catalogue match `billing.PLANS`, or say why it cannot.

    Returns ``{product, prices: {plan: {id, created, problems}}, env: [..]}``.
    `env` is the lines to paste, and it is built from what Stripe
    actually returned — never from what we asked for — so a price that
    silently came back different is visible rather than assumed.
    """
    found = existing_prices(secret_key)
    product = find_product(secret_key)
    if product is None:
        if not create:
            return {"product": None, "prices": {}, "env": [],
                    "note": "No product yet. Run --stripe-setup to create it."}
        product = create_product(secret_key)

    out = {"product": product.get("id"), "prices": {}, "env": [],
           "note": ""}
    for plan_id in BI.PLAN_ORDER:
        plan = BI.PLANS[plan_id]
        price = found.get(plan["lookup_key"])
        created = False
        if price is None:
            if not create:
                out["prices"][plan_id] = {"id": None, "created": False,
                                          "problems": ["not created yet"]}
                continue
            price = create_price(secret_key, str(product.get("id")), plan_id)
            created = True
        problems = _matches(price, plan_id)
        out["prices"][plan_id] = {"id": price.get("id"), "created": created,
                                  "problems": problems}
        if price.get("id"):
            out["env"].append(f"{plan['env']}={price['id']}")
    return out


# --- promotion codes ----------------------------------------------------------
#
# A discount at Stripe is TWO objects, and conflating them is the usual
# way this goes wrong. A *Coupon* is the discount itself — a percentage,
# for a number of months — and has no name a customer ever types. A
# *Promotion Code* is the string somebody types, pointing at a coupon.
# One coupon can carry several codes, which is how a second code for a
# different audience gets added later without touching the discount.
#
# Both are created from `billing.promos()`, which reads the ENVIRONMENT.
# The codes are secrets: this repository is public, so a code written in
# a source file is a code anyone can read. See billing.ENV_PROMOS.


#: The Stripe API version the promo calls are made against.
#:
#: PINNED, and only here. Every other call in this file rides the
#: account's default version, which is right for them — they read fields
#: that have never moved. These two endpoints are different: on
#: 2026-08-22 `POST /v1/promotion_codes` with the documented `coupon`
#: parameter came back "Received unknown parameter: coupon" from Ethan's
#: account, which is what a newer default version answers when a
#: parameter has been renamed or relocated under it. Naming a version
#: makes the request mean the same thing next year as it does today.
#:
#: The fields read back — id, active, percent_off, duration,
#: duration_in_months — are identical across every version that has ever
#: had these endpoints, so pinning costs nothing.
PROMO_API_VERSION = "2024-06-20"


def _promo_headers(secret_key: str, idem: str) -> dict:
    return {"Authorization": f"Bearer {secret_key}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Stripe-Version": PROMO_API_VERSION,
            "Idempotency-Key": idem}


def _promo_call(what: str, fn, *args, **kw):
    """Run one Stripe call, and say WHICH ONE when it fails.

    `billing._get` and `billing._post` produce byte-identical text for a
    refusal, so "Stripe refused the request (HTTP 400)" from anywhere in
    this file named no endpoint and no parameter. That turned a one-line
    fix into a guessing exercise. The label is added here rather than in
    billing so the two transports keep their single, key-safe error path.

    PARAMETER NAMES ONLY — never values, and never headers. The secret
    key lives in the headers and a key in a traceback is a key in a log.
    """
    try:
        return fn(*args, **kw)
    except BI.BillingUnavailable as exc:
        raise BI.BillingUnavailable(f"{what}: {exc}") from exc


def find_coupon(secret_key: str, promo_id: str) -> dict | None:
    """Our coupon for a promo, by the owner/promo stamp in its metadata."""
    got = _promo_call("listing coupons", BI._get,
                      f"{API}/coupons?limit=100", secret_key,
                      headers={"Stripe-Version": PROMO_API_VERSION})
    for c in got.get("data") or []:
        meta = c.get("metadata") or {}
        if (str(meta.get("owner") or "") == OWNER_TAG
                and str(meta.get("promo") or "") == promo_id):
            return c
    return None


def find_promotion_code(secret_key: str, code: str) -> dict | None:
    """An existing promotion code by the string customers type.

    Asked of Stripe by `code=`, NOT filtered from a list of ours: the
    name is unique across the whole account, so a code created by hand in
    the dashboard has to be found too — otherwise this creates a second
    one, Stripe refuses the duplicate, and the error says nothing useful.
    """
    got = _promo_call("looking up promotion code " + str(code), BI._get,
                      f"{API}/promotion_codes?code={code}&limit=10", secret_key,
                      headers={"Stripe-Version": PROMO_API_VERSION})
    for c in got.get("data") or []:
        if str(c.get("code") or "").upper() == str(code).upper():
            return c
    return None


def create_coupon(secret_key: str, promo_id: str) -> dict:
    promo = BI.promos()[promo_id]
    headers = _promo_headers(secret_key, f"{OWNER_TAG}-coupon-{promo_id}")
    pairs = {
        "percent_off": str(int(promo["percent_off"])),
        "duration": promo["duration"],
        "name": promo["coupon_name"],
        "metadata[owner]": OWNER_TAG,
        "metadata[promo]": promo_id,
    }
    if promo["duration"] == "repeating":
        pairs["duration_in_months"] = str(int(promo["duration_in_months"]))
    return _promo_call(f"creating the coupon ({', '.join(sorted(pairs))})",
                       BI._post, f"{API}/coupons", headers, BI._form(pairs))


def create_promotion_code(secret_key: str, promo_id: str,
                          coupon_id: str) -> dict:
    promo = BI.promos()[promo_id]
    headers = _promo_headers(secret_key,
                             f"{OWNER_TAG}-promocode-{promo_id}")
    pairs = {
        "coupon": coupon_id,
        "code": promo["code"],
        "metadata[owner]": OWNER_TAG,
        "metadata[promo]": promo_id,
    }
    # A CAP, IF ONE WAS ASKED FOR. Same reasoning as QB_CODES' max_uses:
    # a code meant for a dozen friends is otherwise unlimited the moment
    # one of them screenshots it. Stripe fixes this AT CREATION — a
    # promotion code's max_redemptions cannot be changed afterwards — so
    # a code that needs a cap needs it now, not later.
    if int(promo.get("max_redemptions") or 0) > 0:
        pairs["max_redemptions"] = str(int(promo["max_redemptions"]))
    # Refuse the code to anyone who has ever paid an invoice here. Stops
    # an existing subscriber cancelling and re-buying at a discount; does
    # NOT stop a brand-new account, which has no history to look at.
    if promo.get("first_time_only", True):
        pairs["restrictions[first_time_transaction]"] = "true"
    return _promo_call(
        f"creating promotion code {promo['code']} on coupon {coupon_id} "
        f"({', '.join(sorted(pairs))}) against API {PROMO_API_VERSION}",
        BI._post, f"{API}/promotion_codes", headers, BI._form(pairs))


def _coupon_problems(coupon: dict, promo_id: str,
                     promo: dict | None = None) -> list:
    """Ways a coupon already at Stripe disagrees with `billing.PROMOS`.

    Reported, never silently corrected. A live coupon may already be on
    somebody's subscription, and rewriting the discount under them is not
    a thing a setup command should do on its own.
    """
    promo = promo or BI.promos()[promo_id]
    bad = []
    if int(coupon.get("percent_off") or 0) != int(promo["percent_off"]):
        bad.append(f"gives {coupon.get('percent_off')}% off, "
                   f"we say {promo['percent_off']}%")
    if str(coupon.get("duration") or "") != promo["duration"]:
        bad.append(f"duration is {coupon.get('duration')!r}, "
                   f"we say {promo['duration']!r}")
    if promo["duration"] == "repeating":
        got = int(coupon.get("duration_in_months") or 0)
        if got != int(promo["duration_in_months"]):
            bad.append(f"runs {got} month(s), "
                       f"we say {promo['duration_in_months']}")
    return bad


def _code_problems(existing: dict, promo: dict) -> list:
    """Ways a promotion code ALREADY at Stripe differs from the config.

    Reported, never fixed. `max_redemptions` and the restrictions are
    fixed when a promotion code is created — Stripe will not let them
    change afterwards — so the only remedy is to deactivate the code and
    make a new one. Saying so is worth more than silently passing a code
    that has no cap on it.
    """
    bad = []
    want_cap = int(promo.get("max_redemptions") or 0)
    got_cap = existing.get("max_redemptions")
    got_cap = int(got_cap) if got_cap is not None else 0
    if want_cap != got_cap:
        bad.append(
            f"the live code allows {got_cap or 'unlimited'} redemption(s), "
            f"the config says {want_cap or 'unlimited'} — a cap cannot be "
            f"changed after creation, so this needs a NEW code")
    want_first = bool(promo.get("first_time_only", True))
    got_first = bool((existing.get("restrictions") or {})
                     .get("first_time_transaction"))
    if want_first != got_first:
        is_now = ("first-time-only" if got_first
                  else "open to anyone who has paid before")
        bad.append(f"the live code is {is_now}, the config says the "
                   f"opposite — also fixed at creation, so this needs a "
                   f"NEW code")
    return bad


def ensure_promos(secret_key: str, create: bool = True) -> dict:
    """Make Stripe's coupons match `billing.PROMOS`, or say why they don't.

    Returns ``{promo_id: {code, coupon, created, active, problems}}``.
    Idempotent: a code that already exists is inspected, not recreated.
    """
    out: dict = {}
    for promo_id, promo in BI.promos().items():
        row = {"code": promo["code"], "coupon": None, "created": False,
               "active": False, "problems": []}
        existing = find_promotion_code(secret_key, promo["code"])
        if existing:
            row["active"] = bool(existing.get("active"))
            coupon = existing.get("coupon") or {}
            row["coupon"] = coupon.get("id")
            row["problems"] = _coupon_problems(coupon, promo_id, promo)
            row["problems"] += _code_problems(existing, promo)
            row["redeemed"] = int(existing.get("times_redeemed") or 0)
            row["cap"] = existing.get("max_redemptions")
            if not row["active"]:
                row["problems"].append(
                    "the code exists at Stripe but is switched OFF — "
                    "nobody can use it until it is reactivated there")
            out[promo_id] = row
            continue
        if not create:
            row["problems"].append("not created yet")
            out[promo_id] = row
            continue
        coupon = find_coupon(secret_key, promo_id) or create_coupon(
            secret_key, promo_id)
        row["coupon"] = coupon.get("id")
        row["problems"] = _coupon_problems(coupon, promo_id, promo)
        made = create_promotion_code(secret_key, promo_id, str(coupon.get("id")))
        row["created"] = True
        row["active"] = bool(made.get("active"))
        out[promo_id] = row
    return out


# --- the webhook, created for you ---------------------------------------------
#
# THE HARDEST STEP BY HAND, and the one that must not be skipped: without
# a signing secret the endpoint refuses every event, so somebody can pay
# and never get access. Doing it in the dashboard means finding
# Developers → Webhooks → Add endpoint, pasting a URL exactly, ticking
# five checkboxes out of a list of about a hundred and fifty, and then
# copying a `whsec_` string that looks confusingly like the API key.
#
# Every part of that is an API call, so it does not have to be done by
# hand at all.


def verify_key(secret_key: str) -> dict:
    """`{ok, live, account, name}` — does this key work, and whose is it?

    Called the moment a key is pasted. "Nothing appeared when I pasted"
    and "the value is wrong" look identical at a silent prompt, and the
    difference does not otherwise surface until several steps later, at
    the point where the error is about something else entirely.
    """
    got = BI._get(f"{API}/account", secret_key)
    return {
        "ok": True,
        "live": BI.live_mode(secret_key),
        "account": got.get("id") or "",
        "name": (got.get("settings") or {}).get("dashboard", {}).get("display_name")
                or got.get("business_profile", {}).get("name") or "",
        "charges_enabled": bool(got.get("charges_enabled")),
        "payouts_enabled": bool(got.get("payouts_enabled")),
    }


def find_webhook(secret_key: str, url: str) -> dict | None:
    """Our endpoint, matched on URL. None if there is not one."""
    got = BI._get(f"{API}/webhook_endpoints?limit=100", secret_key)
    for row in (got.get("data") or []):
        if str(row.get("url") or "").rstrip("/") == url.rstrip("/"):
            return row
    return None


def create_webhook(secret_key: str, url: str) -> dict:
    """Create it, subscribed to exactly the events `billing.HANDLED` lists.

    The event list comes from the module that READS them, so the two
    cannot drift. An endpoint subscribed to an event we ignore is noise;
    one missing an event we act on is a subscription that silently never
    updates.
    """
    pairs = {"url": url, "description": f"{BI.PRODUCT_NAME} — subscriptions",
             "metadata[owner]": OWNER_TAG}
    for i, event in enumerate(BI.HANDLED):
        pairs[f"enabled_events[{i}]"] = event
    headers = {"Authorization": f"Bearer {secret_key}",
               "Content-Type": "application/x-www-form-urlencoded"}
    return BI._post(f"{API}/webhook_endpoints", headers, BI._form(pairs))


def delete_webhook(secret_key: str, endpoint_id: str) -> None:
    req = urllib.request.Request(
        f"{API}/webhook_endpoints/{endpoint_id}",
        headers={"Authorization": f"Bearer {secret_key}"}, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=20):
            return
    except Exception as exc:                                 # noqa: BLE001
        raise BI.BillingUnavailable(f"could not remove the old endpoint: {exc}")


def ensure_webhook(secret_key: str, url: str, recreate: bool = False) -> dict:
    """``{secret, created, id, note}``. The secret is None when unknowable.

    STRIPE ONLY RETURNS THE SIGNING SECRET ONCE, at creation. Listing an
    endpoint later gives you its id, its URL and its events, and never
    the secret again — which is correct of them and awkward here: an
    endpoint that already exists cannot have its secret recovered.

    So when one exists and we do not hold its secret, the only way
    forward is to replace it. `recreate=True` deletes and remakes, which
    is safe because an endpoint carries no state — no history is lost, no
    event is missed while it happens, and any event Stripe cannot deliver
    it retries for days. Defaulting to False so nothing is destroyed
    without being asked.
    """
    found = find_webhook(secret_key, url)
    if found and not recreate:
        return {"secret": None, "created": False, "id": found.get("id"),
                "note": "an endpoint for this URL already exists, and Stripe "
                        "only reveals a signing secret at creation. Recreate "
                        "it to get a fresh one."}
    if found and recreate:
        delete_webhook(secret_key, str(found.get("id")))
    made = create_webhook(secret_key, url)
    return {"secret": made.get("secret"), "created": True,
            "id": made.get("id"),
            "note": "created" if not found else "replaced"}


# --- what is configured on this machine ---------------------------------------
def preflight() -> list:
    """``[(ok, headline, detail)]`` — everything that has to be true.

    ORDERED THE WAY IT BREAKS, not the way it reads. A missing secret key
    makes every later check meaningless, so it comes first and the rest
    are still reported rather than skipped: seeing all five at once is
    the difference between one round of setup and five.

    Reports, never fixes. A function that repairs configuration is a
    function that can repair it wrongly at three in the morning.
    """
    BI._env()
    checks = []

    sk = os.environ.get(BI.ENV_SECRET, "").strip()
    if not sk:
        checks.append((False, f"{BI.ENV_SECRET} is not set",
                       "Stripe cannot be called at all. Dashboard → "
                       "Developers → API keys → Secret key."))
    else:
        live = BI.live_mode(sk)
        checks.append((True,
                       f"{BI.ENV_SECRET} is set ({'LIVE' if live else 'TEST'} mode)",
                       "Real cards are charged." if live else
                       "Test mode: nobody is charged and no money moves. "
                       "Use 4242 4242 4242 4242 to walk the flow."))

    # A PRODUCT ALREADY IN STRIPE KEEPS THE NAME IT WAS CREATED WITH.
    # `PRODUCT_NAME` is only read when the product is created, so editing
    # the constant renames the site and nothing else: the dashboard, the
    # invoices and the card statement all keep saying whatever they said
    # when `--stripe-setup` first ran. Harmless right up until a customer
    # does not recognise a line on their statement, which is the single
    # most common cause of a dispute that was never a complaint.
    #
    # Reported rather than fixed, like everything else here. Renaming a
    # live product is a one-line change in the dashboard and not
    # something this should do behind anybody's back.
    if sk:
        try:
            prod = find_product(sk)
        except Exception:                                    # noqa: BLE001
            prod = None
        if prod and str(prod.get("name") or "") != BI.PRODUCT_NAME:
            checks.append((
                False,
                f"Stripe calls the product {prod.get('name')!r}, this "
                f"code calls it {BI.PRODUCT_NAME!r}",
                "Customers see Stripe's name on invoices and receipts. "
                "Dashboard → Product catalogue → the product → Edit "
                "name, and check the statement descriptor while you are "
                "there."))

    for plan_id in BI.PLAN_ORDER:
        plan = BI.PLANS[plan_id]
        got = BI._price_env(plan_id)
        if got:
            # A test price in a live key's account (or the reverse) is a
            # 404 from Stripe at the worst moment — after the customer
            # has clicked buy. The prefix is checkable here for free.
            checks.append((True, f"{plan['name']}: {plan['env']} is set",
                           f"${plan['cents'] / 100:.2f} every "
                           f"{plan['interval_count']} {plan['interval']}(s)."))
        else:
            checks.append((False, f"{plan['name']}: {plan['env']} is missing",
                           "This plan's buy button will refuse rather than "
                           "charge the wrong amount. Run --stripe-setup."))

    wh = os.environ.get(BI.ENV_WEBHOOK_SECRET, "").strip()
    checks.append((bool(wh),
                   f"{BI.ENV_WEBHOOK_SECRET} is "
                   f"{'set' if wh else 'MISSING'}",
                   "Signed events can be verified, so a payment can grant "
                   "access." if wh else
                   "THE WEBHOOK ENDPOINT REFUSES EVERY EVENT WITHOUT THIS, "
                   "which means paying customers never get access. Add the "
                   "endpoint in Stripe first — the secret does not exist "
                   "until it does."))

    site = os.environ.get("QB_SITE_URL", "").strip()
    if site:
        checks.append((site.startswith("https://"),
                       f"QB_SITE_URL={site}",
                       "Where Stripe sends the customer back."
                       if site.startswith("https://") else
                       "Stripe requires https for a live return URL."))
    else:
        checks.append((True, "QB_SITE_URL is not set (using the request host)",
                       "Fine behind one hostname. Set it if the site "
                       "answers on several, so the return trip is not "
                       "decided by whichever one the customer typed."))
    return checks
