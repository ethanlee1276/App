# Going live — every command, in order

The one page to follow when switching the site from free to paid. It
assumes the code is already deployed and working, which it is.

`docs/BILLING.md` has the reasoning; this has only the commands.

**Do the whole thing in Stripe TEST mode first (steps 1–7), then repeat
steps 2–5 with the live key (step 8).** Test and live are the same Stripe
account distinguished by a key prefix, so the switch at the end is one
line and nothing else moves.

---

## 0. Get the code onto the box

On your Mac:

```bash
ssh qellys
cd /srv/qellys && ./deploy/deploy.sh --no-tests
```

Everything below runs on the droplet, in `/srv/qellys`.

---

## 1. Put the test key in

```bash
sudo nano /etc/qellys/env
```

Add:

```
STRIPE_SECRET_KEY=sk_test_...
QB_SITE_URL=https://qellysbook.com
```

Get the key from **Stripe → Developers → API keys → Secret key**.

Then:

```bash
sudo systemctl restart qellys
```

---

## 2. Create the Product and the three Prices

```bash
cd /srv/qellys && python3 launch.py --stripe-setup
```

It prints three lines. Paste them into `/etc/qellys/env`:

```
STRIPE_PRICE_MONTHLY=price_...
STRIPE_PRICE_SIXMONTH=price_...
STRIPE_PRICE_YEARLY=price_...
```

**Do not type price ids out of the dashboard by hand.** A swapped pair
does not fail — it charges the wrong amount to somebody who chose the
other plan, and nothing anywhere reports it.

Safe to run twice: every price carries a `lookup_key` that Stripe
enforces as unique, so a second run finds what exists and creates
nothing.

```bash
sudo systemctl restart qellys
```

---

## 3. Add the webhook, then its secret

In the Stripe dashboard: **Developers → Webhooks → Add endpoint**.

Endpoint URL:

```
https://qellysbook.com/api/billing/webhook
```

Events to select — exactly these five:

```
checkout.session.completed
customer.subscription.created
customer.subscription.updated
customer.subscription.deleted
invoice.payment_failed
```

Copy the **Signing secret** it shows you (`whsec_...`) into
`/etc/qellys/env`:

```
STRIPE_WEBHOOK_SECRET=whsec_...
```

```bash
sudo systemctl restart qellys
```

**Nothing works until this secret is set.** The endpoint refuses every
unsigned event, so a customer can pay and never get access — the money
arrives, Stripe shows a failing endpoint, and nothing on our side
reports it. This is the step to not skip.

---

## 4. Check what the server actually sees

```bash
cd /srv/qellys && python3 launch.py --stripe
```

Every line should say `ok`. It never prints a key value.

---

## 5. Buy something with a test card

**On the real site, in a browser.** This step has no substitute —
everything above can be correct while the integration is broken.

Sign in, pick a plan, pay with:

```
4242 4242 4242 4242    any future expiry    any CVC    any ZIP
```

Then check three things:

1. the site lets you in within a second or two of landing back;
2. **Stripe → Developers → Webhooks** shows the delivery **succeeded**;
3. your account page names the plan you bought.

If (1) fails but (2) succeeded, it is the return-trip poll. If (2)
failed, it is the signature or the URL, and Stripe shows you the
response body.

---

## 6. Add the Discord invite and the code

```bash
sudo nano /etc/qellys/env
```

```
QB_DISCORD_INVITE=https://discord.gg/vCAZjntyX
QB_CODES=USFARATHANE:12:100
```

`QB_CODES` is `CODE:months:max_uses`. **The last number is not a
percentage** — that is 12 months of full access, redeemable 100 times in
total. There is no partial-discount concept: a code opens the whole site.

```bash
sudo systemctl restart qellys
```

Test the code on a second account before relying on it.

---

## 7. Cancel the test subscription

In Stripe, cancel the test subscription you made in step 5 so it does not
sit there renewing in test mode and confusing you later.

---

## 8. Switch to live

```bash
sudo nano /etc/qellys/env
```

Replace the key with the **live** one (`sk_live_...`).

The live account has its own separate catalogue, so:

```bash
sudo systemctl restart qellys
cd /srv/qellys && python3 launch.py --stripe-setup
```

Paste the **new** price ids in — they are different from the test ones.

Add a webhook endpoint in the **live** dashboard (same URL, same five
events), and paste that secret in as `STRIPE_WEBHOOK_SECRET` — it is also
different from the test one.

```bash
sudo systemctl restart qellys
cd /srv/qellys && python3 launch.py --stripe
```

It should now say **LIVE**.

---

## 9. Turn the paywall on — last

```bash
sudo nano /etc/qellys/env
```

```
QB_COMP_EMAILS=ethanlee1276@gmail.com
QB_PAYWALL=1
```

**`QB_COMP_EMAILS` must contain your address.** Setting the flag with an
empty comp list locks you out of your own board.

```bash
sudo systemctl restart qellys
```

The restart seals the public path by itself — every board already on disk
is redacted before the socket opens. You do not have to run `--seal`
separately any more, but it is safe to:

```bash
cd /srv/qellys && python3 launch.py --seal
```

---

## 10. Prove it from your own laptop

```bash
curl -s https://qellysbook.com/data/recommendations.json | head -c 300
```

Signed out, that should show the schedule and a `locked` block — **never
a pick**. If you see picks, stop and run step 9's `--seal` again.

And the whole config in one look:

```bash
ssh qellys
cd /srv/qellys && python3 launch.py --todo
```

---

## If something is wrong

```bash
journalctl -u qellys -n 50 --no-pager
```

Roll back:

```bash
cd /srv/qellys && git log --oneline -5
git checkout <previous> && ./deploy/deploy.sh --no-tests
```

Turn the paywall back off — it is a true no-op when unset:

```bash
sudo nano /etc/qellys/env     # delete the QB_PAYWALL line
sudo systemctl restart qellys
```
