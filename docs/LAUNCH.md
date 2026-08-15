# Going public: the plan

Ethan, 2026-08-15:

> *"We need to come up with a clear plan on how to execute this website to
> be on its own dedicated server for anyone and everyone to use. We need to
> figure out the legal stuff and what I can and cannot put on the website
> … Then once we figure that out we need to make sure we can continue
> working on the website and update it like we have been."*

**I am not a lawyer.** Where this touches law it tells you what to ask and
who to ask it of, and marks which answers can invalidate work already
done. Everything else — servers, hardening, deployment — is mine to do and
is specified here concretely.

The order below is deliberate: **the cheapest questions that can kill the
most work go first.** Standing up a server before checking whether Stripe
will process this business, or whether the data feeds allow commercial
use, is how you spend three weeks on something that then has to be rebuilt.

---

## Phase 0 — three answers to get before building anything else

Each is days, not weeks, and mostly free. Each can change what gets built.

### 0.1 Will Stripe actually process this?

**The risk:** Stripe's restricted-business list covers gambling and
gambling-adjacent services. A paid sports-betting-picks subscription may
land there depending on how it is described. If the answer is no, the
billing layer needs a different processor and `engine/billing.py` gets
rewritten against a different API.

**Do this:** open a Stripe account, describe the business honestly in the
application — *subscription access to sports statistical models and
analysis; no wagers accepted, no money held on behalf of users, no
affiliate handoff* — and **get the answer in writing before launch**.
Ask support directly if the application does not resolve it.

**Why it is first:** an account frozen after launch takes customer money
with it, and unwinding that is worse than any amount of pre-launch delay.

### 0.2 Do the data feeds allow commercial use?

**This is the finding most likely to be missed, because nothing breaks
when you get it wrong — it just becomes someone else's decision later.**

The app reads ~25 external sources. Personal use and a paid product are
different licences on most of them.

| Source | Used for | The question |
|---|---|---|
| The Odds API | every sportsbook price | Which plan permits use in a **paid** product, and may prices be displayed to subscribers? Paid tiers exist; confirm the tier and the redistribution right. |
| ESPN (`site.api`, `lm-api-reads`) | scores, schedules, CFB, fantasy | **Undocumented endpoints with no public licence.** Fine for a hobby, materially riskier inside a paid product. Assume no right and plan a replacement, or get written permission. |
| NBA/WNBA CDN | box scores, player art | Same shape as ESPN. |
| nflverse | the NFL model's whole history | Open data, but check the licence terms and the attribution it requires. |
| Sleeper | fantasy leagues | Read its API terms for commercial use. |
| Yahoo Fantasy | fantasy leagues | Developer terms — already an approved app, confirm commercial is allowed. |
| MLB Stats API | scores, lineups | Terms restrict commercial use in practice; confirm. |
| Polymarket / Kalshi | prediction-market prices | Check both. |
| CFBD | recruiting layer | Has explicit terms and a paid tier. |
| Solana / Dexscreener / RugCheck | Rocket Radar | Check if that page ships publicly. |

**Do this:** one pass through the terms of each, and treat "undocumented
endpoint" as "no licence" rather than "not prohibited". Where a source
fails, the options are: pay for a commercial tier, replace it, or drop the
feature from the public site while keeping it locally.

**This can reshape the product.** If ESPN comes off the table, scores and
schedules need a paid provider — a real recurring cost, and worth knowing
before pricing is set.

### 0.3 Michigan: is a paid picks service regulated here?

**Answered in part, 2026-08-15.** Ethan is in Michigan, which has legal
online sports betting regulated by the **Michigan Gaming Control Board**
(MGCB) under the Lawful Sports Betting Act. And, in his words: *"this
isn't a website you make bets on, it's just a betting tool."* That
distinction is the right one and it is the one the whole design already
holds — no wagers accepted, no funds held, no bet slip.

**What that likely means, and why it still needs a lawyer:** operating a
sportsbook is licensed; publishing analysis is ordinarily speech. The
question is where a *paid* service that recommends specific bets sits
between them, and that is a Michigan-specific answer I should not guess
at.

**The sharpest line to ask about is affiliate money.** Taking revenue
share or referral fees from a sportsbook is a different activity from
selling analysis, and Michigan regulates sports betting vendors and
suppliers. **Do not add sportsbook affiliate links or a "bet this at DK"
handoff until this is answered** — it is the change most likely to pull
the business inside a licensing regime, and it is easy to add later and
painful to unwind.

Ask an attorney licensed in Michigan:

**The risk:** selling sports-betting information for money is regulated in
some jurisdictions, separately from operating a sportsbook. This is a
narrow, answerable question that a lawyer can resolve quickly — and
guessing at it is exactly the kind of thing that reads fine until it
doesn't.

1. Does Michigan regulate paid sports-betting information or handicapping
   services, and does anything need registering with the MGCB?
2. Subscribers will be in other states. Does that change it, and are there
   states to geo-block?
3. Rules on **advertising** a paid picks service — required disclaimers,
   prohibited claims, minimum-age statements?
4. Does taking sportsbook **affiliate** revenue change the answer? (See
   above. Ask now even though the answer today is "we don't".)

Budget a couple of hours of a gaming/regulatory attorney's time. That is
the cheapest insurance on this list.

### 0.1 revisited — Stripe

Ethan, 2026-08-15: *"if stripe allows it then we will use stripe but if
not then we will find an alternative."* Right call, and the code is built
for it: everything Stripe-specific is in `engine/billing.py`, and the rest
of the app only ever asks "is this account entitled". A different
processor is a rewrite of one file, not of the feature.

---

## Phase 1 — the legal and business foundation

Everything here is standard for taking money from strangers.

**1.1 An entity.** Form an LLC before the first paid subscriber. It is the
liability shield between the business and your personal assets, and it is
cheap. Then a business bank account, and Stripe onto that account rather
than a personal one.

**1.2 Terms of Service.** Must state plainly: this is information and
analysis, not betting advice and not a guarantee; we accept no wagers and
hold no funds; no outcome is promised; subscription terms, renewal, and
how to cancel; the limitation of liability.

**1.3 Privacy Policy — and it has to match the code.** We now store
emails, password verifiers, logged bets, fantasy leagues and **search
history**. Most privacy policies are wrong because nobody asks the
engineers; `docs/ACCOUNTS.md` is an accurate description of what is
actually held, and the policy should be written from it. Also required:
how to export (built), how to delete (built), and who it is shared with
(Stripe, for billing — nobody else).

If any subscriber is in the EU or UK, GDPR applies. If California
subscribers pass CCPA/CPRA thresholds, that applies. Both want the same
things we already built — export and delete — plus disclosure.

**1.4 Subscription law.** Auto-renewal rules (California's are the
strictest and effectively set the national standard) require clear
disclosure before purchase, a renewal reminder, and cancellation as easy
as sign-up. Stripe's customer portal satisfies the last one, which is why
billing already routes cancellation there.

**1.5 Age gate and responsible gambling.** 18+ or 21+ depending on
jurisdiction, stated at sign-up, plus a problem-gambling resource line
(1-800-GAMBLER). Standard, expected, and cheap.

**1.6 Claims discipline — you are already ahead here.** The FTC requires
substantiation for performance claims. This project journals every pick at
its real book price and grades it in public, which is exactly the evidence
most tout sites cannot produce. **Do not add a single marketing claim the
Record page cannot back**, and the compliance side of advertising is
mostly handled by construction.

---

## Phase 2 — the server

### 2.1 What the current setup is, honestly

`server.py` is a stdlib `http.server`. Python's own documentation says it
is not intended for production. On a LAN, serving one person, that was the
right call. Public, it needs a real front door.

**What an audit found, measured on 2026-08-15:**

| | |
|---|---|
| **`/api/profile/<name>` takes writes with no credential.** Anyone can create unlimited profiles, up to 1MB each. Verified: three were created from curl with no auth. On a LAN, harmless. Public, it is free disk for whoever finds it. | **must fix** |
| **No security headers at all.** No CSP, no `X-Content-Type-Options`, no `Referrer-Policy`, no HSTS. | **must fix** |
| `/api/recommendations` runs the full pipeline per request | **must fix** — trivially DoS-able; serve the pre-built JSON instead |
| `/api/sleeper/` proxies to Sleeper and caches to our disk | allowlisted, but reconsider exposing it publicly |
| Path traversal on static files | **already correct** — resolved paths + `is_relative_to` |
| Passwords over cleartext | **already refused** (`docs/ACCOUNTS.md`) |
| Webhook forgery | **already refused** (`docs/BILLING.md`) |

**And one found while writing the deploy config, before any of it
shipped.** Behind a reverse proxy, `client_address` is *the proxy* —
every request arrives from 127.0.0.1. `_local_only()` would have been
true for the entire internet, which would have silently opened both
guards above: strangers could create profiles again, and passwords would
have been accepted over cleartext. The app now reads the real caller from
`X-Forwarded-For`, trusting it **only** when the connection came from
loopback (i.e. from our own proxy) and taking the **last** hop rather than
the first, since a client can put anything in the front of that list.
This is the single most important line in the Caddyfile, and it is
commented there so nobody removes it as noise.

**Rate limiting is in the app, not the proxy.** Caddy has no built-in rate
limiter — it needs a third-party plugin, and a protection that depends on
somebody remembering to install a plugin will be missing on the day it
matters. 300 reads/min and 20 auth requests/min per caller, in separate
buckets: the first cut shared one counter, so ordinary page polling ate
the auth budget and would have locked people out of signing in. The Stripe
webhook is exempt — it is authenticated by signature, and a retry burst
during an incident is when we least want to drop payment events.

### 2.2 The shape to deploy

One small VPS is genuinely enough — this is a low-traffic, read-heavy
site. Hetzner or DigitalOcean, ~$6–12/month, Ubuntu LTS.

```
   internet ──► Caddy (:443)  ──► launch.py (:8000, localhost only)
                  │  TLS, automatic via Let's Encrypt
                  │  static files, gzip, rate limits, security headers
                  └─ /api/* proxied; everything else served from disk
```

**Caddy** rather than nginx because it gets and renews certificates on its
own with no cron and no certbot. **systemd** to keep the app running and
restart it on failure. The app binds `127.0.0.1` so it is unreachable
except through the proxy.

**The build stays separate from the serve.** The pipeline writes
`web/data/*.json` and the site serves those files, never running the
pipeline on a request. That removes the expensive-endpoint problem
entirely, and means a failed build leaves the last good board in place
instead of a broken page.

**What actually runs the build, corrected 2026-08-15.** This section used
to say "a timer runs the build", and the systemd unit ran `server.py` —
which serves the built JSON and rebuilds none of it. Together those were
a plan and a deployment that did not match: no timer was ever written, so
in production nothing would have called the pipeline at all. The site
would have come up, answered every request, passed the deploy smoke
check, and served a frozen board indefinitely.

The unit now runs **`launch.py`**, which is where the refresh loop already
lives — ~60s page rebuilds, the faster UFC and meme clocks, the
first-of-day ingest, the 15-minute auto-settle — and which serves the
identical handler (`from server import Handler`). One process instead of
two, no timer to drift out of sync with the unit, and the same code path
that has been running on the laptop for months.

The tradeoff, stated: a crash in the refresh loop takes the serving
process with it. `Restart=always` brings it back, and the alternative —
a separate builder — is the thing to move to if that ever proves noisy.
It is not worth the second moving part until it does.

### 2.3 Before the first stranger

- [ ] the two **must fix** items above
- [ ] a domain, DNS, Caddy issuing a real certificate
- [ ] app bound to localhost, systemd unit, restart-on-failure
- [ ] `secrets.local` outside the repo, mode 0600, and **rotate every key
      currently on the laptop** — they have lived in a dev environment
- [ ] automated backups of `data/accounts.db` and `data/ledger.db`, offsite
- [ ] **a restore drill** — a backup nobody has restored is a hope
- [ ] rate limits on auth and signup
- [ ] uptime check and an alert that reaches your phone
- [ ] an error page that is not a stack trace

---

## Phase 3 — still shipping afterwards

This is the part that is easy to lose, and the goal is that **the workflow
we already use does not change**: work on the branch, tests green, push.

**3.1 Staging.** A second copy of the site on a subdomain, same server,
separate database. New work goes there first. Cheap, and it is what makes
it safe to keep moving quickly once there are real users.

**3.2 Deploy.** A script that pulls, runs the suite, and restarts —
refusing to deploy if the suite is red. The 4,300-test suite stops being a
development convenience and becomes the release gate.

**3.3 Database migrations.** `accounts.db` now holds other people's data,
so schema changes have to be additive and backwards-compatible. Current
tables use `CREATE TABLE IF NOT EXISTS`, which handles adding tables and
columns; anything destructive needs a written migration and a fresh backup
first.

**3.4 Never test against real user data.** Staging gets its own database.

**3.5 A rollback.** Tag each deploy; be able to go back one.

---

## What it costs

| | |
|---|---|
| VPS | $6–12/mo |
| Domain | ~$15/yr |
| TLS | free (Let's Encrypt) |
| Backups | ~$1–5/mo |
| Stripe | 2.9% + 30¢ per charge |
| LLC | $50–500 one-off, state-dependent |
| Lawyer, Phase 0.3 + Phase 1 docs | the real line item — a few hours |
| Data feeds | **unknown until Phase 0.2** — could be $0, could be the largest recurring cost |

---

## Who does what

**Only you can:** open the Stripe account, form the LLC, hire the lawyer,
buy the domain, create the VPS, and decide what is free versus paid.

**I can do all of:** the two must-fix security items, the Caddy and systemd
configuration, the deploy and backup scripts, the staging setup, the
migration discipline, the age gate and responsible-gambling notices, and
drafts of the Terms and Privacy Policy written from what the code actually
does — for your lawyer to review rather than to publish as-is.

**Do not start Phase 2 before Phase 0.** The three answers there decide
whether the billing layer survives, what the data costs, and whether the
product needs registering. All three are days of work and all three are
cheaper now than after launch.

---

## One product decision worth making early

What stays free.

A tout site that hides its record behind a paywall is asking to be trusted
about the one number it will not show. This project's entire positioning is
the opposite — every pick journaled at its real book price and graded in
public. **Keep the Record page free and public.** It is the proof, it is
the marketing, and putting it behind a subscription would cost more in
credibility than it could ever collect.
