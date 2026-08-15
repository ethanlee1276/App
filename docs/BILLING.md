# Subscriptions

Ethan, 2026-08-15: *"we will be accepting money for people to use the
website once it is complete."*

Built 2026-08-15. **Nothing is charging anyone yet, and nothing is gated
yet** — see "What is switched off" below. This page is what to do when you
want it live.

---

## The one rule the design comes from

**Card numbers never touch this server.** Customers type them on a
Checkout page hosted by Stripe. We store a customer id and a status.

That is what keeps this repo out of PCI scope entirely. The moment we
render a card field, the compliance surface stops being a paragraph and
becomes a project. **Do not build a card form**, and do not accept a card
number through any endpoint here, ever.

The second rule follows from the first: **the browser is never believed
about payment.** A page coming back from Checkout saying "I paid" is a
claim from an untrusted party — anyone can send that request with curl.
Entitlement moves only when a **signed webhook** says so. `success_url` is
for showing a thank-you and has no power to grant anything.

---

## What you have to do — in this order

The order matters; the webhook secret does not exist until the endpoint
does.

**1. Stripe account.** [dashboard.stripe.com](https://dashboard.stripe.com).
This is the step nobody else can do for you: it needs your identity and,
for live mode, your bank details.

**2. A Product with a recurring Price.** Products → Add product, set a
monthly price. Copy the **price id** — it looks like `price_1Abc...`, and
it is *not* the product id.

**3. Keys into `secrets.local`:**

```
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PRICE_ID=price_...
```

Use the **test** key first. `sk_test_` and `sk_live_` look nearly
identical in a config file and behave completely differently; the billing
card shows a "Stripe test mode" chip so you can tell at a glance which one
is loaded.

**4. A public HTTPS address.** Stripe has to reach the webhook, so
`localhost` will not do. `tailscale serve --bg 8000` prints one — and you
need it for accounts anyway, since passwords are refused over cleartext
(`docs/ACCOUNTS.md`).

**5. The webhook, last.** Developers → Webhooks → Add endpoint, pointing
at `https://your-address/api/billing/webhook`, subscribed to:

```
checkout.session.completed
customer.subscription.created
customer.subscription.updated
customer.subscription.deleted
invoice.payment_failed
```

Copy its **signing secret** (`whsec_...`) into `secrets.local` as
`STRIPE_WEBHOOK_SECRET`, and restart the server.

**Until that secret is set, the webhook endpoint refuses every event.**
That is deliberate: an unsigned webhook that gets accepted is a
free-subscription button for anybody who finds the URL, and "we will add
the secret later" is exactly how it ships that way.

**6. Test it with Stripe's own tooling** before touching live mode:

```
stripe listen --forward-to https://your-address/api/billing/webhook
stripe trigger checkout.session.completed
```

Card `4242 4242 4242 4242`, any future expiry, any CVC.

---

## What is switched off

**No feature checks entitlement.** The plumbing is complete and the status
is real, but nothing anywhere asks "has this person paid?" before
answering. That is deliberate rather than unfinished: the site is free
today, and switching a paywall on before you have said what is behind it
would lock you out of your own board on the strength of an inference.

When you decide, the check is one call — `billing.status_for(conn, uid)`
returns `entitled` — and the decision worth making first is what stays
free. A tout site that hides its record behind a paywall is asking to be
trusted about the one number it will not show, and this project's
positioning is the opposite of that (`docs/COMPETITIVE_RECIPE.md`).

---

## How a subscription moves

| Stripe status | Access | Why |
|---|---|---|
| `active` | yes | |
| `trialing` | yes | a trial is a deliberate grant |
| `past_due` | yes, until the paid period ends | a failed renewal is usually an expiry date, not a decision — locking someone out on the first failed charge turns a payment blip into a refund request |
| `canceled` | no | |
| `unpaid` | no | |
| `incomplete` | no | a Checkout that was never finished is not a subscription |

Cancelling happens on **Stripe's portal**, reached from Manage billing. A
company that builds its own cancel flow is deciding how hard it is to
leave, and this one is not going to be that.

---

## What the signature check is doing

`/api/billing/webhook` is a public URL that grants paid access, so
`verify_signature` is the load-bearing function in `engine/billing.py`:

* HMAC-SHA256 over Stripe's exact `{timestamp}.{raw body}` construction;
* compared with `hmac.compare_digest`, never `==`;
* a timestamp outside a 5-minute tolerance is **rejected** — a captured
  valid webhook is otherwise valid forever, so a cancellation could be
  replayed to undo an upgrade, or a payment replayed to extend access;
* it takes the **raw body**. Parsing and re-serializing JSON changes bytes
  — key order, spacing, unicode escapes — and the signature is over bytes,
  so a re-serialized body fails to verify even when it is honest. The
  server reads the raw bytes before any JSON parsing for exactly this.

Event ids are remembered, so a Stripe retry is not a second grant. Stripe
delivers *at least* once, not exactly once.

Events we do not act on are answered **200 and ignored** — anything that
is not 2xx gets retried, so rejecting an irrelevant event creates a retry
loop that never ends.

---

## What has NOT been verified

Written against an API this container cannot reach, and said plainly
rather than implied to work.

**Verified here, by test:** signature verification against forged, wrong-
secret, replayed and tampered payloads; idempotency on retry; the status
state machine; entitlement including the `past_due` grace; the request
shapes; the full checkout → renewal → cancellation sequence driven through
the real endpoint with a fake signing secret.

**Not verified, and cannot be from here:** that Stripe accepts our
Checkout Session parameters, that the live event JSON matches the shapes
read in `read_event`, and the portal call. Those need step 6 above. The
field names come from Stripe's documented API, but this repo has shipped a
bug from exactly that kind of confidence before — `pass_att` was read from
a market that did not exist and everything downstream read zero without an
error — so treat the first live run as the real test.

---

## Where the code is

| | |
|---|---|
| `engine/billing.py` | signatures, state, request shapes, storage |
| `server.py` | `_billing_get` / `_billing_post` / `_billing_webhook`, raw-body handling |
| `web/js/app.js` | the subscription row on the account card |
| `tests/test_billing.py` | the security properties, pinned |
