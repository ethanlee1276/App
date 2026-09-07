# When you get home — the laptop checklist

**Start here:**

```
python3 launch.py --todo
```

That command replaces most of what this file used to be. It reads the
model store, the history database, the ledger and the environment on
whatever machine you run it on, and prints what is actually outstanding —
with the evidence, so you can disagree with it, and the exact command for
each thing. Anything it can't determine it says so, rather than guessing.

**This file now holds only what a machine cannot check.** Judgement
calls, legal questions, design decisions, and things that need your eyes.

---

## Why this file shrank from 1,964 lines

It had become a log of finished work with a checklist buried in it, and
**not one item in it could be verified**. The chores run against a
database and a set of model files on your laptop; a cloud session cannot
see them, and two weeks later neither can you. "Did I run the MLB refit?"
is not a question anybody should have to answer from memory.

So the measurable half became `--todo` and the rest is below. The old
file is not lost — `git show ecafd1d:docs/WHEN_HOME.md` has all of it,
including every measurement and the reasoning behind each decision.

---

## Yours — decisions nobody else can make

### 1. Where do the backups go? (blocks a real risk today)

`QB_BACKUP_REMOTE` is unset, so every ledger backup is written to the
same disk as the ledger. That survives a bad migration and does not
survive the failure it exists for. Pick a destination and I will wire it:

- a box you already own (rsync over ssh — cheapest, needs the box to be on)
- Backblaze B2 (~$6/TB/month, S3-compatible)
- AWS S3 (more expensive, more moving parts)

Nothing else here is blocked on this, but it is the one item where the
cost of waiting is unbounded rather than annoying.

### 2. The Odds API key (low priority, ten seconds)

Open `secrets.local` and see which line `5dc51e48` is on. Measured
2026-08-08 by `keycheck.py`: `ODDS_API_KEY` had 10,965 credits,
`ODDS_API_KEY_2` had 0.

- on **`ODDS_API_KEY_2`** → do nothing; a spent key can spend nothing.
- on **`ODDS_API_KEY`** → regenerate at your leisure. Keep the old line
  and add the new one; the ring skips dead keys.

It is a quota credential, not a payment method, and `git grep` plus
`git log --all -S` both return zero, so it never reached the repo.

### 3. Before charging anyone — not code

The paywall is **built and switched off**. `QB_PAYWALL` unset means
boards publish whole. Put your address in `QB_COMP_EMAILS` in
`/etc/qellys/env` BEFORE ever setting `QB_PAYWALL=1`, or the first thing
it does is lock you out of your own board. (`--todo` checks that order.)

Still needed, all yours:

- A Paddle account, and a real test webhook sent through it. The
  signature verifier in `engine/paddle.py` was written from memory with
  the API unreachable, and is flagged UNVERIFIED in the file. It is the
  one place where being wrong is both silent and dangerous.
- The LLC and a business bank account.
- Phase 0 in `docs/LAUNCH.md`: commercial-use terms for ~25 data feeds,
  and the Michigan/MGCB question.
- No sportsbook affiliate links until the Michigan lawyer answers.

### 4. The design queue needs a reference from you

`docs/DESIGN_QUEUE.md`'s blocked item — "the site has no point of view" —
is upstream of everything else in that file and cannot be worked without
screenshots of two or three products you actually like the look of. Ask
me to start it and I will ask you for those first.

Two smaller ones there are measured and waiting on a number you choose:
the masthead tagline (capped at 21 characters by a rule that says 34) and
the sidebar's last line (guillotined rather than faded).

### 5. Venue art

`docs/VENUE_PROMPTS.md` when you feel like making pictures — fifteen
colour renders wanted. `python3 launch.py --venues` measures each file
against its family and prints what is still off.

---

## Yours — things only your eyes settle

- **The phone menu.** Deploy, then tap Menu three or four times. Tell me
  which way it goes: if it opens cleanly the 2026-08-19 fix held; if it
  still dims with no drawer, send a recording and I need the timing
  between the drawer appearing and the dim arriving — that gap is what
  identifies which layer is winning, and no engine available to me
  reproduces it.
- **The price tape.** Verified by measurement now (the line is drawn
  exactly where the data says, and my earlier screenshots had simply
  caught it mid-animation), but worth a glance on real Kalshi data.
- **The contact sheet.** `python3 launch.py --renders --shots ~/renders/`
  writes one, with an empty slot beside each screen for your render
  images. It stays empty until you drop them in.

---

## The standing rules, easy to forget

- **`VENUE_ART_V` in `web/js/app.js` must be bumped whenever the venue
  renders are rebuilt.** A cache-busting token nobody changes is worse
  than none.
- **The deploy is on the droplet, not the laptop**, and the test suite is
  not the gate there — GitHub Actions is:

      cd /srv/qellys && ./deploy/deploy.sh --no-tests

- **Hard-refresh once** (Cmd-Shift-R) before judging anything visual. On
  the phone the installed app no longer needs this — the service worker's
  cache name is derived from the files it holds, so a deploy that changes
  the app changes the cache and the old one is deleted.

---

## What I am carrying (no action from you)

These are mine, listed so you can see them rather than so you can do
them. Each is waiting on data rather than on effort:

- **NFL Phase 3** — the Week-1 dress rehearsal, running to Sep 7.
- **The game sim into pricing** — needs a live-slate reconciliation first.
- **The loss miner's blind spot** — measurement built, waiting on ~500
  settled main rows.
- **`movecheck`** — waiting on line-movement data to accumulate; it
  correctly declines to answer until then.
- **UFC's empty-cache chain** — found, needs a live card to confirm.
