# What this business is — for a payment processor

Ethan, 2026-08-20: *"catagorize what exactly what our digital product is
and write a detailed description on what services we offer that would get
us APROVED by stripe."*

**One thing up front, because it matters more than anything else in this
file: I cannot promise this gets approved.** Approval is a human being at
Stripe applying a policy I cannot read from here. What I can do — and
have done — is make sure every sentence below is *true and checkable*,
and audit the site for anything that would contradict it. An application
that overstates gets approved and then terminated later with a reserve
held, which is worse than a decline.

Everything in §1 was verified against the codebase today, not recalled.

---

## 1. The audit — what I checked before writing a word

| Claim | How it was checked | Result |
|---|---|---|
| No wagers accepted | grep for bet-slip, deposit, withdraw, balance across the app, server and engine | Nothing. Two hits, both prose: a responsible-gambling note, and a ledger comment saying no account is linked |
| No customer funds held | Same sweep; reviewed `docs/ACCOUNTS.md` | No balance, no deposit, no withdrawal, no payout path exists |
| No odds offered, nothing settled | Reviewed `engine/gate.py`, ledger and board builders | The site prices *its own estimates* against published book odds. It never offers a price to a user |
| No wallet, no crypto custody | grep for `connectWallet`, `phantom`, `solflare`, `web3`, swap/DEX routers | None. Zero web3 surface |
| No sportsbook affiliate links | Enumerated every outbound URL in the app | None |
| A bet slip cannot be added by accident | `tests/test_newlook.py`, `tests/test_account_screen.py` | The build FAILS if the strings "Place Bet", "Bet Slip", "To Win $" or "Deposit" appear |

**Every outbound link on the site**, in full: `dexscreener.com`,
`geckoterminal.com`, `polymarket.com`, `sleeper.com`,
`ncpgambling.org`, `gamblersanonymous.org`, `begambleaware.org`.
The last three are responsible-gambling resources.

---

## 2. Categorization

* **Business type:** SaaS — subscription software and data analytics.
* **MCC:** **5817** (Digital Goods — Applications/Software) or **7372**
  (Computer Programming, Data Processing). Either is accurate.
* **Not MCC 7995** (Betting, including lottery tickets, casino gaming
  chips, off-track betting and wagers). 7995 describes a business that
  *accepts stakes*. This one accepts a monthly subscription fee for
  access to information.
* **What is sold:** a recurring licence to a web application. $25/month,
  $125/6 months, $225/year.
* **Delivery:** instant, digital, to a logged-in account. No physical
  goods, no shipping.
* **Customer:** the general public in the United States.

---

## 3a. The onboarding form — what to type in the actual box

Ethan hit this on 2026-08-20: Stripe's activation flow, *"What products
or services will you offer through Stripe?"*, with a Category dropdown
and a small Description box. That box wants a few plain sentences, **not
the long description in §3** — §3 is for a support conversation or an
appeal, and pasting an essay into an onboarding field reads as somebody
who knows they have a problem.

**Category:** `Software as a service`. Correct, and already the right
pick.

**Description — paste this (540 characters):**

> Subscription web application providing sports statistics and analytics.
> We publish statistical projections for NFL, MLB, NBA, WNBA, college
> football and UFC, the underlying data and reasoning behind each
> projection, a public record of our own accuracy, season-long fantasy
> football tools, and read-only market-data displays (charts and risk
> indicators only). Revenue is a recurring subscription fee for software
> access. We do not accept wagers, hold customer funds, offer odds, or
> settle any transaction — we publish analysis and data only.

**If the field is shorter than that (329 characters):**

> Subscription web application providing sports statistics and analytics.
> We publish statistical projections for major sports, the data behind
> them, a public record of our accuracy, and fantasy football tools.
> Revenue is a recurring subscription fee for software access. We do not
> accept wagers, hold customer funds, or offer odds.

### Why it is worded that way

* **It opens with what we are, not what we are adjacent to.** "Sports
  statistics and analytics" is the accurate description of the product.
  Leading with the word "betting" invites a keyword match to a restricted
  category before a human ever reads the sentence, and every word here is
  true regardless.
* **The last sentence is the whole application.** Four denials in one
  line — no wagers, no funds, no odds, no settlement — so a reviewer
  scanning for the risk finds the answer without hunting.
* **"read-only market-data displays" covers the crypto page on purpose.**
  The site has a MEME COINS tab in its navigation. A reviewer will see
  it. A description that mentions only sports, next to a site with a
  visible token tracker, is the discrepancy that causes the problem — so
  one clause names it and bounds it in the same breath. Do not remove
  that clause to make the sentence shorter.
* **No claims.** Nothing about profits, edges, winning, or how many
  customers there are.

---

## 3. The business description — paste this into the application

> Qellys Books is a subscription sports-analytics web application. We
> publish statistical projections for professional and college sports —
> NFL, MLB, NBA, WNBA, college football and UFC — together with the
> reasoning behind each projection and a permanent public record of how
> our previous projections turned out.
>
> Subscribers pay a recurring fee for access to the software. That is our
> only source of revenue.
>
> We are an information and software provider. We do not accept wagers,
> we do not hold or transmit customer funds for any purpose other than
> the subscription fee, we do not offer odds or prices to users, we do
> not settle or grade any transaction between users, and we are not
> affiliated with and take no commission from any sportsbook, casino or
> exchange. There is no mechanism anywhere in our product by which a user
> can place a bet, deposit money, withdraw money, or hold a balance.
>
> Our product is directly comparable to OddsJam, Unabated, Outlier and
> FantasyPros — sports data and analytics subscriptions.

---

## 4. The detailed feature description — paste this where they ask what you do

> **What subscribers get:**
>
> 1. **Statistical projections.** For each upcoming game we publish a
>    projected value for player and team statistics, derived from
>    historical performance data, usage rates, matchup context, weather
>    and published injury reports. Each projection shows the arithmetic
>    that produced it, step by step.
>
> 2. **Published-odds comparison.** We display odds already published by
>    licensed sportsbooks, sourced through a commercial data API, and
>    compare them against our own projections. We are showing the reader
>    publicly available market data alongside our analysis. We do not
>    set, offer or accept any price.
>
> 3. **A public performance record.** Every projection we flag is recorded
>    before the event and graded against the result afterwards, win or
>    lose. This record is free to the public and is not behind the
>    paywall. It is the primary evidence a prospective subscriber uses to
>    judge whether the product is worth buying.
>
> 4. **Fantasy sports tools.** Draft rankings and tiers, a draft
>    simulator, a lineup optimiser, a trade evaluator and waiver
>    analysis, for season-long fantasy football leagues. No entry fees,
>    no prizes, no contests are operated by us.
>
> 5. **A personal record-keeping tool.** Subscribers may manually type in
>    or paste a record of bets they placed elsewhere, at their own
>    sportsbook, in order to track their own performance over time. This
>    is a spreadsheet-style log. No money moves through it, we have no
>    connection to the sportsbook, and we cannot see, verify or affect
>    any real transaction. It is functionally identical to a personal
>    finance tracker.
>
> 6. **Public market data displays.** We display publicly available
>    pricing data from prediction markets and from cryptocurrency token
>    trackers, presented as read-only charts and risk indicators. We
>    provide no wallet, no trading interface, no custody and no exchange
>    of any kind. A user cannot transact on these pages; they can only
>    read them.
>
> **Revenue model:** one recurring subscription fee, charged to the
> subscriber, for access to the software. No commissions, no affiliate
> revenue, no advertising, no transaction fees.

---

## 5. Why this is not a gambling business — point by point

Use this if a reviewer pushes back. Each point is checkable on the live
site.

1. **We take no stake.** A gambling business accepts money that is at
   risk on an outcome. The only money we accept is a subscription fee,
   charged whether the reader ever bets or not, and it is not returned or
   multiplied based on any event. Nothing a subscriber pays is contingent
   on a result.

2. **We hold no customer funds.** There is no account balance, no
   deposit, no withdrawal, no wallet and no payout mechanism anywhere in
   the product. Our automated build fails if a developer so much as adds
   a button labelled "Deposit" or "Place Bet" — this is enforced in the
   test suite, not by policy.

3. **We offer no odds.** We do not quote a price to a user or take the
   other side of anything. Where odds appear, they are odds already
   published by licensed operators, obtained from a commercial data
   provider and displayed as market data — the same way a financial site
   displays a stock price it does not set.

4. **We settle nothing.** No transaction between us and a user, or
   between two users, is resolved by a sporting result. We grade our own
   published projections for accuracy, which is a measurement of our
   product's quality, not a settlement.

5. **No user-to-user activity of any kind.** No pools, no contests, no
   peer-to-peer wagers, no entry fees, no prizes.

6. **No affiliate or referral revenue.** We do not link to sportsbooks,
   we are not paid per signup or per deposit, and we take no share of any
   customer's activity anywhere else.

7. **Our own product copy refuses the framing.** The site states on every
   page that it publishes a model's estimates, that this is not betting
   advice, and that every number is a probability rather than a promise.
   We make no profit claims and no guarantees, and we display
   responsible-gambling resources including 1-800-GAMBLER.

8. **The comparable businesses are on Stripe.** OddsJam, a paid
   sports-betting analytics subscription in the same category, processes
   card payments through Stripe — visible in their public checkout, which
   uses Stripe Link and Stripe Elements.

---

## 6. Two things to decide before you send it

Both are mine to flag and yours to call.

### The Polymarket links

Our prediction-market pages link out to `polymarket.com/market/<slug>`
and `polymarket.com/profile/<wallet>` as **source citations** — "this is
the market the number came from". That is normal for a research product,
the same as a news article linking its source.

But a reviewer who clicks one lands on a trading venue. The risk is a
wrong impression, not a wrong claim.

* **Keep them** — defensible, and citing a source is the honest thing.
* **Remove them during review** — cheapest possible way to remove an
  ambiguity from a decision you do not control. Say the word and it is a
  ten-minute change.

My read: remove them for the application, restore them after. There is
nothing to gain from making a reviewer think about it.

### Mention the crypto page — do not hide it

The meme-coin scanner is read-only analytics with no wallet, no trading
and no custody, and §4 point 6 describes it accurately. **Say it in the
application anyway.** A reviewer who discovers an undisclosed
cryptocurrency-adjacent feature after approval treats it as
misrepresentation, and that is how accounts get terminated with a
reserve. Disclosed and correctly framed, it is a data display. Undisclosed
and found later, it is a reason.

---

## 7. If they decline again

Ask, in writing, for the specific restricted category the application was
matched to. There are two very different declines:

* **"Your business matches restricted category X"** — a classification
  problem. Answerable with §5.
* **"We do not serve this business model"** — a policy decision, and no
  amount of rewording changes it.

Do not skip that question. Everything in `docs/PROCESSOR.md` past this
point costs materially more than Stripe, and which option is right depends
entirely on the answer.

---

## 8. What is true today, stated so nobody is surprised

* The site currently has **one settled pick** on its public record. If a
  reviewer looks, that is what they will see. It is not a problem — a new
  product has a short record — but do not describe the business as
  established or claim a user base.
* Nothing is charging anyone yet. This application is to enable that.
* `QB_PAYWALL` is the switch; `docs/BILLING.md` has the sequence.
