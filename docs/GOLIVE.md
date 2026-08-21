# Going live — where you are, and what you type

Switching the site from free to charging. Read this once before starting;
it takes about twenty minutes.

**There are three places you will be working.** Every instruction below is
labelled with which one, because that is the thing that goes wrong.

| | | |
|---|---|---|
| 💻 | **Mac Terminal** | your own laptop. The prompt looks like `ethancarson@Ethans-MacBook-Air App %` |
| 🖥️ | **Droplet** | the server, after `ssh qellys`. The prompt looks like `root@ubuntu-s-1vcpu-1gb-nyc1:/srv/qellys#` |
| 🌐 | **Browser** | Stripe's website, on your Mac |

**How to tell where you are:** look at the prompt. If it says
`root@ubuntu-...` you are on the droplet. If it says
`ethancarson@Ethans-MacBook-Air` you are on your Mac. `exit` takes you
from the droplet back to the Mac.

---

## The short version

Almost all of it is one guided script. It asks you one question at a
time, tells you when to go to the browser, and writes every setting
itself.

💻 **Mac Terminal:**

```bash
ssh qellys
```

🖥️ **Droplet:**

```bash
cd /srv/qellys
./deploy/deploy.sh --no-tests
sudo ./deploy/golive.sh
```

Then follow what it says. **That is the whole thing.** The rest of this
page is what it is doing, in case you want to do it by hand or something
goes sideways.

You can stop at any point with `Ctrl-C` and run `sudo ./deploy/golive.sh`
again later — it picks up where you left off and skips what is already
done.

---

## What the script asks you for

**One value.** Everything else it fetches, creates, or already knows.

| What it asks for | Where you get it | Looks like |
|---|---|---|
| `STRIPE_SECRET_KEY` | 🌐 Stripe → Developers → API keys → Secret key → Reveal | `sk_test_51Abc...` |

That is the only thing you have to go and find. The rest:

| Setting | How it gets set |
|---|---|
| `STRIPE_PRICE_MONTHLY` / `SIXMONTH` / `YEARLY` | created in Stripe by the script, written straight in |
| `STRIPE_WEBHOOK_SECRET` | the script creates the endpoint through Stripe's API and takes the secret from the reply — you never see it |
| `QB_SITE_URL` | set to `https://qellysbook.com` |
| `QB_DISCORD_INVITE` | offered as your invite; press Enter |
| `QB_CODES` | set to `USFARATHANE:12:100` |
| `QB_COMP_EMAILS` | offered as your address; press Enter |

Nothing that can be looked up is typed. The three price ids and the
signing secret are the four strings most often pasted into the wrong
slot, and a swapped pair of price ids charges the wrong amount to
somebody who picked the other plan without failing anywhere.

**When it asks for the key, nothing appears as you paste.** That is on
purpose — the value is not echoed and does not go into your shell
history. Paste and press Enter. It checks the key against Stripe
immediately and tells you the mode and the account name, so you know it
landed.

---

## Step by step, if you would rather do it yourself

### Step 0 — get the code onto the server

💻 **Mac Terminal:**

```bash
ssh qellys
```

If that says `Could not resolve hostname`, you do not have the alias yet.
Use `ssh root@qellysbook.com` instead, and set the alias up afterwards —
see the bottom of this page.

🖥️ **Droplet:**

```bash
cd /srv/qellys
./deploy/deploy.sh --no-tests
```

It ends with `up, answering after ~3s`. Everything from here is on the
droplet unless it says otherwise.

---

### Step 1 — the Stripe secret key

🌐 **Browser:**

1. Go to **dashboard.stripe.com**
2. Top right, make sure the **Test mode** toggle is **ON**
3. Left sidebar → **Developers** → **API keys**
4. Under "Standard keys" find **Secret key**, click **Reveal**
5. Copy it — it starts with `sk_test_`

🖥️ **Droplet:**

```bash
sudo ./deploy/setenv.sh STRIPE_SECRET_KEY
```

It prints `Value for STRIPE_SECRET_KEY (paste it, then Enter):` — paste,
press Enter. **You will not see anything as you paste.** That is correct.

```bash
sudo ./deploy/setenv.sh QB_SITE_URL https://qellysbook.com
sudo systemctl restart qellys
```

---

### Step 2 — create the three prices

🖥️ **Droplet:**

```bash
python3 launch.py --stripe-setup
```

It creates the Product and the Monthly / 6-month / Yearly prices in your
Stripe account, then prints three lines like:

```
  STRIPE_PRICE_MONTHLY=price_1AbcDef...
  STRIPE_PRICE_SIXMONTH=price_1GhiJkl...
  STRIPE_PRICE_YEARLY=price_1MnoPqr...
```

Set each one, pasting the value it printed:

**Replace the `price_...` values below with the ones it just printed** —
they are examples, not commands to paste as they are. `setenv.sh` refuses
anything with `...` in it, so pasting these verbatim fails loudly rather
than writing nonsense, but it is still a wasted minute.

```bash
sudo ./deploy/setenv.sh STRIPE_PRICE_MONTHLY   price_1AbcDef...
sudo ./deploy/setenv.sh STRIPE_PRICE_SIXMONTH  price_1GhiJkl...
sudo ./deploy/setenv.sh STRIPE_PRICE_YEARLY    price_1MnoPqr...
sudo systemctl restart qellys
```

Safe to run `--stripe-setup` twice — it finds what exists rather than
making duplicates.

---

### Step 3 — the webhook

**This is the step that must not be skipped.** Without it, somebody can
pay and never get access: the money arrives, Stripe shows a failing
endpoint, and nothing on our side reports it.

🖥️ **Droplet** — the easy way, which creates it in Stripe for you:

```bash
python3 launch.py --stripe-webhook
```

It makes the endpoint with the right URL and all five events, then prints
`STRIPE_WEBHOOK_SECRET=whsec_...`. Set it:

```bash
sudo ./deploy/setenv.sh STRIPE_WEBHOOK_SECRET
sudo systemctl restart qellys
```

If it says an endpoint already exists, Stripe will not reveal an old
signing secret — it is only returned at creation. Replace it:

```bash
python3 launch.py --stripe-webhook --recreate
```

Nothing is lost: an endpoint holds no history, and Stripe retries
anything it could not deliver.

<details>
<summary>Or by hand in the dashboard</summary>

🌐 **Browser:**

1. Still in Stripe, still in **Test mode**
2. **Developers** → **Webhooks** → **Add endpoint**
3. Endpoint URL — paste exactly:

   ```
   https://qellysbook.com/api/billing/webhook
   ```

4. Click **Select events** and tick these five, nothing else:

   ```
   checkout.session.completed
   customer.subscription.created
   customer.subscription.updated
   customer.subscription.deleted
   invoice.payment_failed
   ```

5. Click **Add endpoint**
6. On the page that appears, find **Signing secret** and click to reveal
7. Copy it — it starts with `whsec_`. **This is not the key from step 1.**

🖥️ **Droplet:**

```bash
sudo ./deploy/setenv.sh STRIPE_WEBHOOK_SECRET
sudo systemctl restart qellys
```

</details>

---

### Step 4 — check

🖥️ **Droplet:**

```bash
python3 launch.py --stripe
```

Every line should say `ok`. If any says `MISS`, that setting did not
take — run its `setenv.sh` line again.

To see what is set without values:

```bash
sudo ./deploy/setenv.sh --show
```

---

### Step 5 — buy something with a test card

**No substitute for this.** Everything can be configured correctly and
the integration still be broken.

🌐 **Browser:**

1. Open **qellysbook.com**
2. Sign in, or make an account
3. Pick any plan → **Get started** → **Continue to secure checkout**
4. Pay with:

   ```
   card     4242 4242 4242 4242
   expiry   any future date, e.g. 12/34
   CVC      any 3 digits
   ZIP      any 5 digits
   ```

Then check all three:

- **a)** it puts you back on the site and lets you in, within a second or two
- **b)** Stripe → Developers → Webhooks shows the delivery **succeeded**
- **c)** your account page names the plan you bought

If **(a)** fails but **(b)** succeeded, that is the return-trip poll —
tell me. If **(b)** failed, Stripe shows you the response body — tell me
what it says.

---

### Step 6 — Discord and your promo code

🖥️ **Droplet:**

```bash
sudo ./deploy/setenv.sh QB_DISCORD_INVITE https://discord.gg/vCAZjntyX
sudo ./deploy/setenv.sh QB_CODES USFARATHANE:12:100
sudo systemctl restart qellys
```

`QB_CODES` is `CODE:months:max_uses`. **The last number is uses, not a
percent** — that is 12 months of full access, redeemable 100 times. A
code opens the whole site; there is no partial discount.

---

### Step 7 — cancel your test subscription

🌐 **Browser:** in Stripe, cancel the test subscription from step 5 so it
does not sit there renewing and confusing you later.

---

### Step 8 — switch to live

**Only once step 5 worked.**

🌐 **Browser:** turn **Test mode** OFF. The live account has its own keys,
its own prices and its own webhook. Get the live secret key the same way
as step 1.

🖥️ **Droplet:**

```bash
sudo ./deploy/setenv.sh STRIPE_SECRET_KEY
sudo systemctl restart qellys
python3 launch.py --stripe-setup
```

Paste the **new** price ids — they are different from the test ones:

```bash
sudo ./deploy/setenv.sh STRIPE_PRICE_MONTHLY   price_...
sudo ./deploy/setenv.sh STRIPE_PRICE_SIXMONTH  price_...
sudo ./deploy/setenv.sh STRIPE_PRICE_YEARLY    price_...
```

🖥️ **Droplet** — the live webhook, created the same way:

```bash
python3 launch.py --stripe-webhook
sudo ./deploy/setenv.sh STRIPE_WEBHOOK_SECRET
sudo systemctl restart qellys
python3 launch.py --stripe
```

It should now say **LIVE**.

---

### Step 9 — turn the paywall on

🖥️ **Droplet:**

```bash
sudo ./deploy/setenv.sh QB_COMP_EMAILS ethanlee1276@gmail.com
sudo ./deploy/setenv.sh QB_PAYWALL 1
sudo systemctl restart qellys
```

**Your address goes in first.** With an empty comp list the first thing
the paywall does is lock you out of your own board.

The restart seals the boards on disk by itself.

---

### Step 10 — prove it from outside

💻 **Mac Terminal** (a new window, not the ssh one):

```bash
curl -s https://qellysbook.com/data/recommendations.json | head -c 300
```

You should see the schedule and a `locked` block — **never a pick**. If
you see picks, go back to the droplet and run:

```bash
python3 launch.py --seal
```

---

## Handy afterwards

🖥️ **Droplet:**

```bash
sudo ./deploy/setenv.sh --show      # what is set (values hidden)
python3 launch.py --stripe          # Stripe config
python3 launch.py --todo            # everything, including the paywall
journalctl -u qellys -n 50 --no-pager   # what the site is saying
```

**Change one setting:**

```bash
sudo ./deploy/setenv.sh KEY          # prompts, replaces the old value
sudo systemctl restart qellys
```

**Turn the paywall back off** — it is a true no-op when unset:

```bash
sudo ./deploy/setenv.sh --unset QB_PAYWALL
sudo systemctl restart qellys
```

**Roll back a deploy:**

```bash
git log --oneline -5
git checkout <the one before> && ./deploy/deploy.sh --no-tests
```

---

## The ssh alias, once

💻 **Mac Terminal:**

```bash
mkdir -p ~/.ssh && cat >> ~/.ssh/config <<'EOF'

Host qellys
    HostName qellysbook.com
    User root
EOF
```

Then `ssh qellys` works for ever, and keeps working if the server's IP
changes. `ubuntu-s-1vcpu-1gb-nyc1` is the droplet's name in the
DigitalOcean dashboard, not a hostname — nothing resolves it.
