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

## Turning the paywall on (separate job, done once)

Not part of a deploy. On the droplet, edit `/etc/qellys/env`:

```
QB_COMP_EMAILS=ethanlee1276@gmail.com
QB_CODES=USFARATHANE:12:100
QB_PAYWALL=1
```

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

**`QB_COMP_EMAILS` first, in that order, always.** Setting the flag with
an empty comp list locks you out of your own board, and with no processor
live there is no account that can pay to get back in. `launch.py --todo`
checks that ordering.

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
