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
ssh qellys
cd /srv/qellys
./deploy/deploy.sh --no-tests
```

Then force-quit the app on your phone and reopen it.

(`qellys` is an `~/.ssh/config` alias — §2 sets it up. Until you have it,
`ssh root@qellysbook.com`.)

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
ssh root@qellysbook.com
cd /srv/qellys
```

**Not `ubuntu-s-1vcpu-1gb-nyc1`.** That is the droplet's NAME in the
DigitalOcean dashboard, not a hostname — nothing resolves it, and the
`cd` on the next line then runs on your laptop instead, which is the
confusing part. The domain is an A record straight to the droplet
(143.198.169.53), so the domain works as the ssh host.

Better, once: put this in `~/.ssh/config` on the laptop.

```
Host qellys
    HostName qellysbook.com
    User root
```

Then it is `ssh qellys` for ever, and it keeps working if the IP ever
changes.

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

## The explainer: the one thing this project installs

Everything else here is the standard library. The plain-English
explainer on the prop page (engine/explainer.py) talks to the model
through the official `anthropic` Python package, and the service's
python is `/usr/bin/python3`, so it is installed for the box, once:

```bash
# The droplet image ships without pip (2026-09-05: "No module named pip"),
# so pip itself comes first.
sudo apt update && sudo apt install -y python3-pip
# Ubuntu 24.04 refuses to touch the system python without
# --break-system-packages, and then refuses to REMOVE apt's own copy of
# typing_extensions ("RECORD file not found ... installed by debian",
# 2026-09-05 on the box). --ignore-installed lays pip's newer copies
# under /usr/local, which python reads first, and leaves apt's alone.
sudo python3 -m pip install --break-system-packages --ignore-installed typing_extensions anthropic
# Must print a version AS THE SERVICE USER, or the service will not see it:
sudo -u qellys python3 -c "import anthropic; print(anthropic.__version__)"
```

Then the two values it reads, into /etc/qellys/env the usual way (the
model id is the exact string Claude gave you in chat; the key is from
console.anthropic.com):

```bash
sudo ./deploy/setenv.sh QB_EXPLAIN_MODEL <model id>
sudo ./deploy/setenv.sh ANTHROPIC_API_KEY          # prompts, reads silently
sudo systemctl restart qellys
```

Until both are set the button on the prop page says "The explainer is
not switched on for this site yet" — nothing breaks, nothing spends.
Answers are cached per build in data/explain_cache.json, so a pick
costs one call per rebuild however many people tap it.

## When you are home and want the chores list

```bash
cd ~/App && python3 launch.py --todo
```

Reads your real database, ledger and environment and prints what is
actually outstanding, with the command for each. This is a laptop thing
and has nothing to do with deploying.

---

## Going live with Stripe, and turning the paywall on

Both are one job, done once, and the ordering is not optional — see
**`docs/GOLIVE.md`**, which is every command in order with nothing else
in it. This page is for the deploy you do every day.

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

---

## Behind Cloudflare

Cloudflare went in front of the live site on 2026-08-21, which added a hop
the address logic had not accounted for:

    browser → Cloudflare → Caddy → the app

**Run this once, and after any Cloudflare change:**

```
sudo /srv/qellys/deploy/cfips.sh
sudo systemctl restart qellys
```

### Why it matters

`deploy/Caddyfile` replaces `X-Forwarded-For` with the peer Caddy saw.
Before Cloudflare that was the browser. After Cloudflare it is a Cloudflare
edge server — so every visitor in a city arrived as the same handful of
addresses, and `rate_ok` buckets by caller. That is **300 API calls and 20
sign-ins a minute shared by all of them**, not each. A quiet site never
notices; a site that has just been posted to Instagram starts handing 429s
to paying customers, and the 429 says "slow down".

Cloudflare sends the real address in `CF-Connecting-IP`. That header is
believed only when the machine that spoke to our proxy was genuinely
Cloudflare, checked against their published ranges — which is what
`cfips.sh` installs. Any client can set that header, so believing it on
sight would let anyone pick their own rate-limit bucket, or fill somebody
else's.

**Without the list nothing breaks and nothing is exposed** — the app falls
back to the forwarded hop, exactly as before. It just cannot tell your
visitors apart. `engine/cfips.py` has the long version.

```
./deploy/cfips.sh --check      # what is installed, and how old
```

Cloudflare's ranges change rarely but they do change. Weekly refresh:

```
0 5 * * 1 /srv/qellys/deploy/cfips.sh >/dev/null 2>&1
```

### Bot Fight Mode and the Stripe webhook

Bot Fight Mode challenges traffic that does not look like a browser. A
Stripe webhook is a POST from a datacentre, which is exactly that shape,
and **on the free plan Bot Fight Mode cannot be scoped to skip a path**.

Check it, do not assume it:

> Stripe → Developers → Webhooks → your endpoint → **Send test webhook**.
> A delivery that is not `200` means Cloudflare is eating it.

If it is being eaten, the fix is a WAF rule that skips
`/api/billing/webhook`, or turning Bot Fight Mode off.

**Either way a blocked webhook no longer costs a sale.** The browser comes
back from Checkout carrying the Checkout Session id, and
`/api/billing/confirm` asks Stripe directly whether that session was paid
— see `engine/billing.reconcile_session`. Nothing has to be delivered to
us for a customer to get in. The webhook is still what keeps the status
correct afterwards (renewals, cancellations, failed cards), so it is worth
fixing regardless.

### Lock the origin

Cloudflare only protects what goes through it. The droplet's IP is public,
and anyone who has it can skip the whole edge. Restrict 80/443 to
Cloudflare:

```
sudo ufw allow from 173.245.48.0/20 to any port 443 proto tcp
# …and the rest of the list in /etc/qellys/cloudflare-ips.txt
```

---

## When it gets busy

The app serves at most `QB_MAX_INFLIGHT` requests at once (default 64) and
answers `503` with a `Retry-After` beyond that.

`ThreadingHTTPServer` starts a thread per connection and has no ceiling of
its own. On a 1GB droplet a burst walks the box into swap and then into
the OOM killer, and what dies is the whole process — every signed-in
session with it, and usually the headroom you would have needed to ssh in
and fix it. A ceiling turns that into the failure anybody would choose:
a few callers retry, everyone already being served finishes.

Raise it if the box is bigger:

```
sudo ./deploy/setenv.sh QB_MAX_INFLIGHT 128
sudo systemctl restart qellys
```

Caddy serves every static file, so the only things reaching Python are API
calls. Per signed-in visitor that is roughly one account sync a minute
plus a status check per page load — the boards themselves come off disk
through Caddy with a minute of cache in front of them.
