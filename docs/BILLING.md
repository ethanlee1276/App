# Subscriptions

Ethan, 2026-08-15: *"we will be accepting money for people to use the
website once it is complete."*

**The processor is Stripe. The account is live, the code is wired to it,
and the only thing between here and taking money is putting four values
into a config file on the droplet.** This page is the runbook for that,
in the order the steps actually work in.

---

## What it costs, and where those numbers live

| Plan | Price | Billed |
|---|---|---|
| Monthly | $25 | every month |
| 6 months | $125 | every 6 months |
| Yearly | $225 | every year |

Every plan is the same product. Length of commitment is the only axis —
a tier that withheld features would need a second entitlement model and a
second way to be wrong about what somebody paid for.

**These numbers are stated in two places and they must agree.**
`engine/billing.PLANS` decides what Stripe charges; the `PLANS` array in
`web/js/app.js` decides what the page advertises. Nothing connects them at
runtime — the browser sends a plan *id* and the server looks up a price by
that id — so they can drift apart silently and the site keeps working. It
just advertises $125 and charges $225, which is a chargeback the customer
is right about. `tests/test_stripe_plans.py` parses the JavaScript and
compares every number, both directions. **If you change a price, change
both.**

---

## Setting it up — the whole thing, in order

The order matters: the webhook secret does not exist until the endpoint
does, and the endpoint needs a public address.

### 1. Get the secret key

Stripe dashboard → Developers → API keys → **Secret key**.

Use the **test** key (`sk_test_…`) first, all the way through step 6. Test
and live are the same Stripe account distinguished by that prefix, so
going live later is one line and nothing else moves. The billing card
shows a "Stripe test mode" chip so you can tell at a glance which one is
loaded.

Put it in `secrets.local` (laptop) or `/etc/qellys/env` (droplet):

```
STRIPE_SECRET_KEY=sk_test_...
```

### 2. Create the Product and the three Prices

```
python3 launch.py --stripe-setup
```

This creates them in your Stripe account and prints three lines to paste.
**Do not transcribe price ids from the dashboard by hand.** A swapped pair
does not fail; it charges the wrong amount to somebody who chose the other
plan, and nothing anywhere reports it.

It is safe to run twice — every price carries a `lookup_key`, which Stripe
enforces as unique, so a second run finds what exists and creates nothing.
It never edits an existing price: Stripe prices are immutable on purpose,
since a price somebody is subscribed to must not change under them. If one
disagrees with `billing.PLANS` it says so and stops.

Paste what it prints:

```
STRIPE_PRICE_MONTHLY=price_...
STRIPE_PRICE_SIXMONTH=price_...
STRIPE_PRICE_YEARLY=price_...
```

### 3. A public HTTPS address

Stripe has to reach the webhook, so `localhost` will not do. The droplet
already has one (`qellysbook.com`). On a laptop, `tailscale serve --bg
8000` prints one — and you need HTTPS for accounts anyway, since passwords
are refused over cleartext (`docs/ACCOUNTS.md`).

If the site answers on more than one hostname, pin the return trip:

```
QB_SITE_URL=https://qellysbook.com
```

Without it the address Stripe sends the customer back to is whatever they
typed — which for somebody who arrived on a bare IP is a certificate
warning after they have paid.

### 4. The webhook, last

Developers → Webhooks → **Add endpoint**, pointing at

```
https://qellysbook.com/api/billing/webhook
```

subscribed to exactly these events:

```
checkout.session.completed
customer.subscription.created
customer.subscription.updated
customer.subscription.deleted
invoice.payment_failed
```

Copy its **signing secret** (`whsec_…`) in as `STRIPE_WEBHOOK_SECRET`, and
restart.

**Until that secret is set, the endpoint refuses every event.** That is
deliberate — an unsigned webhook that gets accepted is a free-subscription
button for whoever finds the URL. But understand what it means with the
paywall on: **people can pay and never get access**, the money arrives,
Stripe's dashboard shows a failing endpoint, and this side reports
nothing. `launch.py --todo` calls that state out by name for exactly this
reason.

### 5. Check what the server sees

```
python3 launch.py --stripe
```

Reports the key and its mode, all three prices, the webhook secret and the
return URL. It never prints a key value — a key in a terminal is a key in
a scrollback buffer, a screenshot and a support thread.

### 6. Buy something, with a test card

**This is the step that has no substitute.** Everything above can be
correct while the integration is broken, because the pieces are tested in
isolation and a verifier that works and is never called looks exactly like
one that works.

With the test key loaded, on the real site: sign in, pick a plan, pay with

```
4242 4242 4242 4242   any future expiry   any CVC   any ZIP
```

Then check three things:

1. you land back on the site and it lets you in — within a second or two,
   not after a refresh;
2. Stripe → Developers → Webhooks shows the delivery **succeeded**;
3. your account page says which plan you are on.

If (1) fails but (2) succeeded, the return-trip poll is the suspect. If
(2) failed, it is the signature or the URL, and Stripe shows you the
response body.

### 7. Switch to live

Replace `STRIPE_SECRET_KEY` with the `sk_live_…` key, re-run
`--stripe-setup` (the live account has its own separate catalogue, so it
creates the three prices again and prints live price ids), swap those in,
add a webhook endpoint in the live dashboard and swap its secret in.
Restart. `launch.py --stripe` should say LIVE.

### 8. Only then, the paywall

`QB_PAYWALL=1`. **`QB_COMP_EMAILS` must contain your own address first**,
or the first thing the paywall does is lock you out of your own board.
Then `python3 launch.py --seal`, because turning the flag on changes what
the *next* build writes and touches nothing already on disk.

---

## Discount codes are ours, not Stripe's

`engine/redeem.py` grants entitlement directly for a number of months. No
card, no subscription, nothing to cancel.

```
QB_CODES=USFARATHANE:12:100
```

The format is `CODE:months:max_uses`. **The last number is not a
percentage** — that is `USFARATHANE`, giving 12 months of full access,
redeemable 100 times in total. There is no partial-discount concept: a
code opens the whole site, so "100% off a year" and "12 months of access"
are the same grant. The cap exists because a code posted somewhere public
is otherwise unlimited.

One redemption per account, enforced by a primary key rather than by a
check — a check races with itself under two simultaneous requests and a
primary key does not. Wrong guesses are rate-limited per account and
answered with the same message and the same timing whether or not the code
exists, so a fast "no such code" cannot be used to enumerate live ones.

Stripe's own promotion codes are **deliberately switched off**
(`allow_promotion_codes` is absent from the Checkout request). Two coupon
systems that know nothing about each other makes "why did my code work on
the account page but not at checkout" a question with no good answer.

A code that covers the whole term means there is nothing to charge, so
checkout skips the processor entirely and writes the grant. A code that
covers *less* than the term says so and does not pretend to be free.

---

## The members' Discord

An active subscription includes it. The invite is configured on the box:

```
QB_DISCORD_INVITE=https://discord.gg/...
```

**Not in the repository, and not in the JavaScript bundle.** `app.js` is a
static asset served to every anonymous visitor, so an invite compiled into
it is public whatever the page renders — the render gate would be on the
wrong side of the wire. `/api/billing/status` returns it only inside the
branch that has already established the caller is entitled, and
`tests/test_paywall_live.py` fetches `/js/app.js`, `/`, both legal pages
and an anonymous status response to prove the string is in none of them.

It is still not a hard boundary: Discord decides who gets in, and any
member can paste the link in a group chat. What this buys is that we never
hand it to a non-member. If it spreads, revoke and reissue in Discord,
change the line, restart.

Terms §5.7 covers the rest — Discord is a third party, their rules govern
conduct there, and access ends when the subscription does.

### The page it lives on

`#discord` is a real view with a nav row of its own, and it is the same
page in three states:

| State | What it shows |
|---|---|
| Just paid | "Account created", the welcome hero, and the join button |
| Member, later | The same page without the toast or the eyebrow |
| Not subscribed | The same page as a sales page — "See the plans" where the join button goes, and **no invite in the HTML at all** |

The welcome is a one-shot. It is armed at account creation and again when
a payment lands (the two are different moments behind the wall: you sign
up, hit the wall, and pay), and it is spent the first time the page draws.
`localStorage`, because a piece of confetti does not earn an account
field, and every read is inside a `try` — a private window throws on
access and an uncaught throw at boot is a blank site.

The nav row exists because the welcome is seen once. Ethan, 2026-08-21:
*"if someone doesnt join immedietly, they still have the option to join
later."*

### QB_INSTAGRAM

```
QB_INSTAGRAM=https://instagram.com/yourhandle
```

Optional and **not a secret** — it is quoted to people who have not
subscribed, which is the point of quoting it, so it rides on the status
payload outside the entitled branch. Unset, the Discord page simply drops
the sentence that mentions it.

The `+400 units` beside it is Ethan's own count of his own page, and the
page says so in those words. It is not a figure this site graded. What
this site stands behind is the Record page, and the sentence points at it
in the same breath — a performance number stated flatly in the site's own
voice is a claim the site is making, and this one is not ours to make.

---

## Sales tax is ours now

This is the one real cost of Stripe over a merchant of record. Paddle
would have been the legal seller and would have handled digital-goods
sales tax across fifty states. **Stripe is a processor, not a seller — we
are the seller.** Prices are set `tax_behavior: inclusive`, so the price on
the page is the price charged and nothing is added at checkout.

Registration thresholds are a real obligation and not a code problem.
`docs/LAUNCH.md` Phase 0 has it alongside the other things that need an
accountant rather than a commit.

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

## What gates, and what stays free

**`server._entitled` is the one check**, and the order inside it matters:
the paywall flag first, then a comped address, then a redeemed code, then
the subscription. A site running with the flag off behaves exactly as it
did before any of this existed, rather than refusing everyone.

The gate is not a check in front of a file, though — that would be a
decoration. `engine/gate.py` publishes the **redacted board to the public
path** and keeps the full one in `data/built/`, outside the web root.
There is no full copy in the served tree to leak.
`tests/test_paywall_bypass.py` walks the surface anyway.

**The Record page stays free, permanently.** Every pick graded in public,
wins and losses. A tout site that hides its record behind a paywall is
asking to be trusted about the one number it will not show, and this
project's positioning is the opposite of that
(`docs/COMPETITIVE_RECIPE.md`). The account page stays reachable too, or
somebody who has paid cannot sign in to prove it.

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

**Deleting the account takes the `subscriptions` row with it**, including
the `customer_id`. `accounts.delete_user` names the table explicitly
rather than relying on `ON DELETE CASCADE`, because the cascade only
fires on a connection that set `PRAGMA foreign_keys=ON` — see
`docs/ACCOUNTS.md`. Note what deletion does **not** do: it does not
cancel anything at Stripe. Stripe is the system of record for the money,
and a row disappearing here would otherwise leave a live subscription
billing a card every month with nothing on our side to match it to.

So **`/api/account/delete` answers 409 while `status_for` reports an
entitled state**, with a message naming the fix: cancel under Manage
billing first, which is a button on the same card. `past_due` and
`trialing` are refused too — both still have something live at Stripe.
Nobody is trapped: cancelling flips the status through the webhook and
delete then works normally. A billing lookup that *throws* lets the
delete through, deliberately — a bug in code that is switched off must
not hold somebody's data hostage.

Two consequences worth knowing:

* The client used to render every non-200 from that endpoint as "Wrong
  password.", so this refusal would have been invisible and infuriating.
  It now shows the server's message; `Wrong password.` is only the
  fallback when the response carries none.
* This makes the user do our work. The right version calls Stripe's
  cancel endpoint from the delete path and then deletes.

> **Open, and deliberately left open:** cancelling at Stripe from our
> side. It needs a live Stripe account to test against — the API is
> unreachable from this container — and guessing at it would produce a
> payment path verified by nothing. Tracked as task #131, blocked on
> #128. The 409 above is the honest interim: it never silently orphans a
> subscription, it just asks the person to press one more button.

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
the real endpoint with a fake signing secret. `tests/test_billing_e2e.py`
does that last one over actual HTTP against a real `server.py` process, so
"the verifier works but nothing calls it" is covered too — that is the
failure every unit test above would have passed through.

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
| `engine/billing.py` | plans, prices, signatures, state, request shapes, storage |
| `engine/stripeset.py` | creating the catalogue; `--stripe` / `--stripe-setup` |
| `engine/redeem.py` | discount codes — no card, no processor |
| `engine/gate.py` | what gets redacted on the way out, and `--seal` |
| `server.py` | `_billing_get` / `_billing_post` / `_billing_webhook`, raw-body handling |
| `web/js/app.js` | `PLANS`, the plans page, the checkout page, the return trip |
| `tests/test_billing.py` | the security properties, pinned |
| `tests/test_stripe_plans.py` | the page's prices vs the ones Stripe is told |
| `tests/test_stripe_wiring.py` | the request shape and what can grant access |
| `tests/test_billing_e2e.py` | a real server, a real HTTP purchase, over the wire |
| `tests/test_paywall_bypass.py` | every way somebody could read a paid board free |

`engine/paddle.py` is **not wired to anything** — see its header, and
`docs/PROCESSOR.md` for what it would take to swap back.
