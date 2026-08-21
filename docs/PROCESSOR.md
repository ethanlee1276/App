# Taking payment — where we are and what to try next

## ✅ RESOLVED, 2026-08-21: it is Stripe

The appeal worked. The **Qellysbook** account shows compliance
requirements met, and `server.py` is wired to `engine/billing.py` for
every payment path. **The runbook is `docs/BILLING.md`; this page is now
history plus a fallback plan.**

Worth keeping for two reasons. The reasoning in §"The distinction the
whole thing turns on" is what the approved application was built on, so
if the categorisation is ever questioned again it is the argument to
repeat. And §3–§4 are the plan if the account is ever closed — an event
this business should be prepared for rather than surprised by.

`engine/paddle.py` is still in the tree and is **not wired to anything**.
Swapping back is four call sites in `server.py` — `start_checkout`,
`open_portal`, `verify_signature`, `read_event` — plus the signature
header name and the event-id field, both of which differ. Two test files
pin the current direction: `tests/test_paddle.py` asserts no `PAY.` call
survives in `server.py`, and `tests/test_stripe_wiring.py` asserts the
Stripe ones are there.

---

## How it looked on 2026-08-20, before the appeal

Ethan: *"i just went on paddles website and they dont support websites
like ours so we gotta keep looking."*

So both routes we had were shut: Stripe declined on the category, and
Paddle's own acceptable-use rules excluded us. This page was what to do
about it, and the first section was the one that mattered — it is the one
that turned out to be right.

**What I can and cannot tell you here.** I cannot reach a processor's
website from the container I run in, so nothing below is me reading a
current policy page. Where I say something is true, it is either from
this repo's own history or from the screenshot you sent. Everything else
is a question for you to put to them, written so you can copy it.

---

## The screenshot is evidence, and it changes the plan

You sent OddsJam's checkout. Look at what is in it:

* a **Link** badge inside the card field — that is Stripe Link;
* Apple Pay and Google Pay buttons in Stripe's own Payment Request
  layout;
* a card field that is a Stripe Elements iframe.

**OddsJam is a paid sports-betting tool taking card payments on Stripe.**
Same category as us, same kind of product, and they are on the processor
that told us no.

That is worth more than a list of alternatives, because it means the
category is not automatically disqualifying. Something about how the
application was described tripped a filter that OddsJam's did not.

---

## The distinction the whole thing turns on

**Qellys Books does not take wagers.** No bet is placed here, no money is
held for a customer, no odds are offered, nothing is settled for anyone.
It is a subscription to software and information. The tests in this repo
enforce that — there is no bet slip, no balance, no "place bet", and
`tests/test_preservation.py` fails the build if one appears.

That puts us in the same bucket as any analytics SaaS:

* **What we are:** a data and analytics subscription. Merchant category
  code **5817** (digital goods) or **7372** (prepackaged software).
* **What we are not:** MCC **7995**, betting and casino gambling. That is
  for taking wagers.

An application that says "sports betting" in the first line gets read as
7995 by a machine before a human sees it. An application that says
"subscription analytics software for sports data" is describing the same
product accurately and lands somewhere else. Say what is true; just say
the true thing that is not the trigger word.

---

## What to do, in order

### 1. Appeal the Stripe decision, or re-apply describing it correctly

Cheapest by a mile, and the screenshot says it can work.

**`docs/STRIPE_APPLICATION.md` is the whole thing written out** — the
categorization, the MCC, paste-ready business and feature descriptions, a
point-by-point answer to "are you a gambling business", and an audit of
the codebase confirming every claim in it. Start there rather than from
the paragraph below, which is the short form.

Ask Stripe support, in writing:

> My business is a subscription analytics platform for sports data. We
> publish statistical projections and historical performance records. We
> do not accept wagers, hold customer funds, offer odds, or settle bets —
> there is no betting functionality of any kind on the site, and no money
> moves except the subscription itself. This is the same model as OddsJam,
> Unabated and Outlier, who I understand process on Stripe. My previous
> application was declined; can you tell me which restricted category it
> was matched to, and what evidence you need to reclassify it as a
> software subscription?

Naming the specific comparable is the part that gets it to a human.

### 2. If Stripe still says no, ask WHY in writing

The answer determines everything after it. There are two very different
declines:

* **"Your MCC is restricted"** — a classification problem, and fixable by
  argument or by a different application.
* **"We do not serve this business model"** — a policy decision, and no
  amount of rewording changes it.

Do not skip this step. Every option below costs more than Stripe, and
which one is right depends on the answer.

### 3. Other merchants of record

Same shape as Paddle — they become the legal seller and handle sales tax.
Worth asking, in roughly this order:

* **FastSpring** — long-established, software-focused, has a real human
  review process rather than a checkbox.
* **2Checkout / Verifone** — takes categories others will not; more
  paperwork.
* **Lemon Squeezy** — now owned by Stripe, so assume the same policy
  answer as Stripe until told otherwise. Ask, but do not count on it.

Ask each the same question: *"Is a sports-data analytics subscription,
with no wagering functionality, within your acceptable use policy?"* Get
it in writing before building anything.

### 4. A high-risk acquirer

If everyone above says no, this is what is left. PaymentCloud, Durango,
Soar Payments, Corepay and similar brokers place merchants that the big
processors will not.

Know what you are signing up for before you like the sound of it:

* **rates around 4–6%** against Stripe's 2.9% + 30c;
* a **rolling reserve** — they hold a percentage of your revenue for
  months against chargebacks;
* **sales tax across fifty states becomes your problem again**, which a
  merchant of record was solving for us;
* setup fees and often a monthly minimum whether or not you sell
  anything.

At zero subscribers this is a bad trade. At a hundred it may be the only
one available. Do not sign one before step 2's answer is in hand.

### 5. What not to do

* **Do not take crypto as the primary method.** It restricts you to
  customers who already hold it, and for a $25 subscription the friction
  is larger than the market.
* **Do not run payments through a personal account or a friend's
  business.** That is the thing that gets funds frozen and an account
  permanently blacklisted, and it is fraud on the processor's terms.
* **Do not describe the product as something it is not to get approved.**
  The paragraph in step 1 works because every sentence in it is true. An
  application that lies gets terminated later, with the reserve held.

---

## What this means for the code

**Almost nothing, and that was the point of the seam.**

`engine/billing.py` holds what a payment MEANS — which statuses grant
access, when a subscription lapses, how an event is applied exactly once.
`engine/paddle.py` is only the provider half: the checkout URL, the
webhook signature, the API shape. Swapping processors is one module, not
a rewrite, and the entitlement rules that decide who sees a board do not
move at all.

`engine/redeem.py` needs no processor whatsoever. A hundred-percent-off
code involves no money, so it grants access directly.

**Which is why you are not blocked.** The paywall can go up today with
comps and codes as the way in — see `docs/BILLING.md`. That is a real
gate; the boards are genuinely redacted for everyone else. Card payment
plugs in behind it whenever the processor question is settled.

---

## Where this is recorded

* `engine/paddle.py`'s header still explains the Stripe-to-Paddle move
  and is now historically out of date at the end — Paddle said no too.
* `docs/BILLING.md` — how to switch the gate on without a processor.
* `docs/LAUNCH.md` Phase 0 — the data-feed terms and the Michigan
  question, which gate charging money regardless of who processes it.
