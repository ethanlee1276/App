# Subscriptions

Ethan, 2026-08-15: *"we will be accepting money for people to use the
website once it is complete."*

Built 2026-08-15. **Nothing is charging anyone yet, and nothing is gated
yet** — see "What is switched off" below. This page is what to do when you
want it live.

---

## Turning it on — Ethan, 2026-08-20

*"lets get the pay wall going. i want it 100% full force so we can start
charging for the site."*

**The switch works today. Charging cards does not, and the gap between
those two sentences is the whole of this section.**

### What you can do right now

Switch the gate on and let people in with **codes**. A code is a real
entitlement with no processor behind it (`engine/redeem.py`), so it works
with Paddle still unbuilt. On the droplet, in `/etc/qellys/env`:

```
QB_COMP_EMAILS=ethanlee1276@gmail.com
QB_CODES=USFARATHANE:12:100
QB_PAYWALL=1
```

then **two** commands, not one:

```bash
sudo systemctl restart qellys
cd /srv/qellys && python3 launch.py --seal
```

The restart alone is not enough, and this is the trap. `redact()` runs
inside `publish()`, so turning the flag on changes what the NEXT build
writes and does not touch one file already on disk. Measured 2026-08-20
by running the real server with the flag on and curling the picks file:
it returned all 293 recommendations. A restart does rebuild most boards,
so the site mostly seals itself — "mostly" and "by accident" are not a
paywall, and a board whose build fails stays public forever.

`launch.py --seal` strips every board on the public path immediately,
prints what it removed, and exits non-zero if anything still carries a
paid row. `launch.py --todo` checks the same thing on every run.

**`QB_COMP_EMAILS` FIRST, IN THAT ORDER, ALWAYS.** Setting `QB_PAYWALL=1`
with an empty comp list locks you out of your own board and there is no
account that can pay to get back in. `python3 launch.py --todo` checks
that ordering and will say so.

`USFARATHANE:12:100` is `CODE:months:max_uses` — twelve months, a hundred
accounts. Change the cap or add more codes as a comma-separated list. A
redemption is one per account, cannot be re-run when it lapses, and the
attempt limiter stops anyone guessing at the rest.

### What still stands between you and money

None of this is code, and none of it is something I can finish:

1. **A Paddle account, and a real test webhook sent through it.** The
   signature verifier in `engine/paddle.py` was written from memory with
   the API unreachable and is flagged UNVERIFIED in the file. It is the
   one place where being wrong is both silent and dangerous: a verifier
   that wrongly accepts is a free-subscription generator, and one that
   wrongly rejects loses payments nobody sees fail.
2. **The LLC and a business bank account.** Paddle pays out to a business.
3. **Phase 0 in `docs/LAUNCH.md`** — commercial-use terms for around
   twenty-five data feeds, and the Michigan/MGCB question. Charging for a
   product built on feeds whose terms forbid commercial use is the kind
   of problem that arrives as a letter, not as a bug.

Until those are done the honest configuration is **paywall on, codes and
comps as the way in**. That is a real gate — the boards are genuinely
redacted for everyone else — and it is the state the code is built for.

### Checking it worked

```
curl -s https://qellysbook.com/data/recommendations.json | head -c 400
```

Signed out, that should show the schedule and a `locked` block rather
than picks. If it still shows picks, the flag did not take: check the env
file and that the restart actually happened.

---

## The processor is Paddle, not Stripe

**Stripe said no**, on the category rather than on anything we do
(Ethan, 2026-08-15: *"no we cant use stripe so we gotta find a different
alternative"*). Paddle is the replacement, and the reasoning is worth
keeping because the alternatives look superficially reasonable:

* **PaymentCloud / PayKings — rejected.** They are high-risk merchant
  account brokers. They advertise to gambling-adjacent businesses because
  they charge for it: 4–6% plus a rolling reserve and a multi-year
  contract, for what is factually a software subscription. We would be
  buying gambling-merchant pricing for a SaaS product.
* **Adyen / Nuvei — right destination, wrong stage.** Both genuinely
  handle regulated verticals and both underwrite you properly. Both also
  want enterprise volume and a trading history we do not have. Nuvei is
  the fallback if Paddle declines.
* **Worldpay** — will probably take us, but it is a traditional acquirer:
  contracts, PCI paperwork, and a developer experience a decade behind.

**Paddle is a merchant of record.** They are the legal seller; they take
the payment, own the risk assessment, handle sales tax and VAT, and pay us
out. Two things follow. The category question is theirs and already
answered, so we are not re-litigating "sports betting" with every
processor. And digital-goods sales tax across fifty states never becomes
our problem. The price is roughly 5% + 50¢ against Stripe's 2.9% + 30¢ —
about two points for someone else to own risk and tax.

**How to describe the product when applying**, because the wording is what
gets screened: *subscription access to sports analytics software; no
wagering, no funds held, no payouts*. `docs/ACCOUNTS.md` and the Record
page are the supporting evidence, and both are accurate.

### What survived the switch, and what did not

The split was deliberate. `engine/billing.py` holds everything about what
a payment **means** — which statuses grant access, the paid-through date,
the replay guard, the schema, `status_for`. `engine/paddle.py` holds only
the processor half, and its `read_event` returns the identical dict, so
the storage layer cannot tell which processor produced it. A test asserts
those two shapes stay equal, because a silent divergence there loses a
field and nobody notices until a subscription goes missing.

The Stripe functions are still in `billing.py`. They are not wired to
anything and are kept in case Paddle also declines — deleting them would
throw away the working half of a day.

### ⚠️ Two things that are NOT done

**The signature scheme is unverified.** `paddle.verify_signature` was
written from memory: the dev container's egress blocks
`developer.paddle.com` and `api.paddle.com`, so it could not be checked
against their documentation or a real payload. The tests prove the
construction is self-consistent and has the properties a verifier needs —
accepts a correctly signed body, rejects a changed byte, a changed
timestamp, a stale one, and never compares digests with `==`. They do
**not** prove it is Paddle's construction. **First thing after the account
exists:** send a test webhook from the dashboard, confirm it is accepted,
then change one byte and confirm it is refused. A verifier that is wrong
in the accepting direction is indistinguishable from a working one.

**Paddle's checkout needs a CSP change.** Their overlay runs Paddle.js
loaded from `cdn.paddle.com`, and our `script-src` is `'self'`. So the
checkout will silently not appear until that host is allowed — exactly
the failure the Rocket Radar charts had. Add it when the integration
lands, with the same rule as `frame-src`: name the host, never `https:`.

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
