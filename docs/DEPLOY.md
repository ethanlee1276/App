# Pushing to the website — the exact order

Ethan, 2026-08-20: *"put in exact steps and order how i push everything
to the website."*

Asked twice now, so this is the one page that answers it end to end. It is
short on purpose. `deploy/README.md` is 540 lines about how to BUILD the
droplet — a job done once — and this is the job done every day.

---

## The short version

**Almost always, this is the whole thing:**

```bash
ssh <the droplet>
cd /srv/qellys
./deploy/deploy.sh --no-tests
```

Then force-quit the app on your phone and reopen it.

If you did not change any code yourself, you do not need step 0 below and
you do not need to touch the laptop at all. Claude pushes to GitHub; the
droplet pulls from GitHub. The laptop is not in that path.

---

## The full order, every step

### 0. Only if YOU changed files on the laptop

Skip this entirely if the work came from Claude — it is already on GitHub.

```bash
cd ~/App
git status                       # look at what you changed
git add -A
git commit -m "what you changed"
git push -u origin claude/sports-betting-app-vhgmho
```

### 1. Check the branch is green

Open GitHub → the repo → **Actions**. The newest run on
`claude/sports-betting-app-vhgmho` should have a green tick.

This is the release gate, and it is why step 3 can skip the suite.
Running the tests on the droplet takes about an hour on two vCPUs; the
tick costs nothing and tests the same code on three Python versions.

**Red tick?** Do not deploy. Tell Claude, with the name of the failing
job.

### 2. Get onto the box

```bash
ssh <the droplet>
cd /srv/qellys
```

### 3. Deploy

```bash
./deploy/deploy.sh --no-tests
```

What that one command does, in order, so nothing is a surprise:

1. backs up both databases;
2. prints the SHA it is currently on, and the one-line command to roll
   back to it;
3. `git pull --ff-only` — **it pulls for you. Do not run `git pull`
   yourself**;
4. restarts the service;
5. waits until the site answers, then prints the SHA it landed on.

The restart runs a full `refresh_all()`, so every board rebuilds by
itself. **There is no second command.** No separate build step, no
migration to run.

### 4. Read the last line

It prints the short SHA it ended on. Compare it to what Claude said the
deploy should land on.

* **Same SHA it printed at the START** — the pull brought nothing. Nearly
  always the checkout is on the wrong branch:
  `git rev-parse --abbrev-ref HEAD` will say which.
* **`--ff-only` refused** — the box has local commits or edits. Nothing
  restarted and the old code is still serving, which is the safe outcome.
  **Do not force it.** That is a tell-Claude moment.

### 5. Look at it

* On the laptop: **Cmd-Shift-R** once before judging anything visual.
* On the phone: force-quit the app and reopen. It checks for a new shell
  by itself now, but a force-quit is instant.

---

## When you are home and want the chores list

```bash
cd ~/App && python3 launch.py --todo
```

Reads your real database, ledger and environment and prints what is
actually outstanding, with the command for each. This is a laptop thing
and has nothing to do with deploying.

---

## Going live with Stripe (one job, done once)

Not part of a deploy, and the ordering is not optional — see
`docs/BILLING.md` for why each step depends on the one before it. This is
the condensed version for the droplet.

**Do the whole thing in TEST mode first.** Test and live are the same
Stripe account distinguished by the key prefix, so the switch at the end
is one line and nothing else moves.

### A. On the droplet, put the keys in

`sudo nano /etc/qellys/env`:

```
STRIPE_SECRET_KEY=sk_test_...
QB_SITE_URL=https://qellysbook.com
```

### B. Create the catalogue and paste back what it prints

```bash
cd /srv/qellys && python3 launch.py --stripe-setup
```

It prints three `STRIPE_PRICE_*` lines. Put them in `/etc/qellys/env`.
Do not type price ids out of the dashboard by hand — a swapped pair
charges the wrong amount and nothing reports it.

### C. Add the webhook, then its secret

Stripe dashboard → Developers → Webhooks → Add endpoint:

```
https://qellysbook.com/api/billing/webhook
```

Events: `checkout.session.completed`, `customer.subscription.created`,
`customer.subscription.updated`, `customer.subscription.deleted`,
`invoice.payment_failed`.

Copy its signing secret into `/etc/qellys/env`:

```
STRIPE_WEBHOOK_SECRET=whsec_...
```

Then `sudo systemctl restart qellys`.

**Nothing works until this secret is set** — the endpoint refuses every
unsigned event, which means somebody can pay and never get in, with no
error on our side.

### D. Check, then actually buy something

```bash
cd /srv/qellys && python3 launch.py --stripe
```

Every line should say `ok`. Then, on the real site with the test key
loaded: sign in, pick a plan, pay with `4242 4242 4242 4242`, any future
expiry, any CVC.

Three things must be true afterwards:

1. the site lets you in within a second or two of landing back;
2. Stripe → Webhooks shows the delivery **succeeded**;
3. your account page names the plan you bought.

**This step has no substitute.** Everything can be configured correctly
while the integration is broken.

### E. Switch to live

Replace the key with `sk_live_...`, re-run `--stripe-setup` (the live
account has its own catalogue, so it makes new prices and prints new
ids), paste those in, add a webhook endpoint in the LIVE dashboard, paste
its secret in, restart. `launch.py --stripe` should now say LIVE.

---

## Turning the paywall on (do this AFTER Stripe works)

On the droplet, `/etc/qellys/env`:

```
QB_COMP_EMAILS=ethanlee1276@gmail.com
QB_CODES=USFARATHANE:12:100
QB_DISCORD_INVITE=https://discord.gg/vCAZjntyX
QB_PAYWALL=1
```

**Read the code format carefully — the last number is NOT a percentage.**
It is `CODE:months:max_uses`. So `USFARATHANE:12:100` means *12 months of
full access, redeemable 100 times in total*. There is no partial-discount
concept: a code grants the whole site, so "100% off a year" and "12 months
of access" are the same thing. The cap exists because a code posted
somewhere public is otherwise unlimited; raise or lower the 100 to taste.

The resemblance between the usage cap and "100% off" is a coincidence and
a trap — `FRIENDS:1:25` is a one-month code usable 25 times, not a 25%
discount.

then:

```bash
sudo systemctl restart qellys
cd /srv/qellys && python3 launch.py --seal
```

**Both commands. The restart is not enough.**

Redaction happens when a board is WRITTEN, so switching the flag on
changes what the next build writes and touches nothing already on disk.
Until every board has been rebuilt the picks are still sitting on the
public path, and any board whose build fails stays public indefinitely.
`--seal` strips them all immediately, prints how many rows it removed,
and exits non-zero if anything is still exposed. It is safe to run twice
and safe to run at any time.

Check it worked from your laptop:

```bash
curl -s https://qellysbook.com/data/recommendations.json | head -c 300
```

Signed out, that should show the schedule and a `locked` block — never a
pick. If you see picks, the seal did not run.

**`QB_DISCORD_INVITE` is the members' Discord**, and it lives here rather
than in the code because `web/js/app.js` is a static asset served to every
anonymous visitor — an invite compiled into it is public no matter what the
page chooses to render. The server sends it only in the answer to somebody
it has already decided is entitled. Leave it blank and the Discord panel
simply does not appear; nothing breaks. If the invite ever spreads,
revoke it in Discord, put the new one here and restart — no deploy.

**`QB_COMP_EMAILS` first, in that order, always.** Setting the flag with
an empty comp list locks you out of your own board. `launch.py --todo`
checks that ordering, and also checks that the Stripe webhook secret is
present whenever the paywall is on — because the combination of "gate on,
webhook off" is the one that takes money and grants nothing.

To turn it back off, delete the `QB_PAYWALL` line and restart. It is a
true no-op when unset — a test pins that.

---

## If something looks wrong after a deploy

**Roll back.** `deploy.sh` printed the exact command at the start, with
the old SHA already filled in. It looks like:

```bash
git checkout <old-sha> && ./deploy/deploy.sh --no-tests
```

That is always safe and always fast. Diagnose afterwards, not while the
site is down.

Useful while you are there:

```bash
sudo systemctl status qellys                    # is it even running
sudo journalctl -u qellys --since "10 min ago"  # what it said
sudo journalctl -u qellys --since "10 min ago" | grep -i "error\|traceback"
```
