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
