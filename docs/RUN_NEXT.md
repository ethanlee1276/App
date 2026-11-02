# Commands waiting for you

Every command waiting to be run on the box, in one place, so a day of
building doesn't leave them scattered. Each says when. `ssh` in first, run
them top to bottom, and paste back anything that prints an error or looks
off. When one is done it moves to docs/WHEN_YOU_ARE_HOME.md's history, where
every command already lives (the letters below are its steps).

Last updated 2026-11-02 at 22:00 UTC, after you ran JK, JJ and JI (Done,
below). Earlier that day the Owner desk was locked to the accounts you list
(step JK); a failed payment got one day's grace before access pauses, and
Terms §5.7 was rewritten to say so, with the email it needs (step JJ); a
cancelled trial lost its access, one trial per person, a failed charge
started telling the member, and the Owner desk got its account tools (step
JI). Before that, Who's on now became the desk's first card (step JH). Done:

- **JK:** your two accounts are on the Owner desk's list, and nobody else
  opens it (`python3 -m engine.siteowners list` shows who is on it).
- **JJ:** you armed the notices,
  `QB_POLICY_NOTICE 2026-10-29,2026-11-01,2026-11-02`, and restarted the
  site at 21:58 UTC. 29 October's had gone to all 14 accounts with an
  address; 1 and 2 November's had 14 each to go. They send between 10:00
  and 20:00 Eastern, 60 a day at most, so both should finish that evening;
  item 1 checks.
- **JI:** every line as it should be — the Terms dated 2 November, the
  policy's owner-tools and one-trial sections, the Accounts card, the trial
  rule from 2 November 00:00 Eastern, and the failed-charge notice in the
  billing sweep.

- **The outage:** the weekly backup check filled the disk at 04:32 UTC and
  left its copy behind. You deleted the leftovers, restarted the site
  (back at 11:19 UTC) and fixed Backblaze's cap. The check, the pre-repair
  copies and the low-disk warning are fixed in the code (step JG), and
  item 0 below sees what's left.

- **JD, second run:** JE's same-game rule made things worse (+8.99u over 418
  tickets with it, +12.80u over 511 without), so it's off. What held in both
  runs: same-game pairs lost 9.5% over 213 and two-game pairs made 11.1% over
  298. Every pair that makes sense posts again, but money now rides only on
  two-game parlays; same-game ones are always tracked (step JF). Item 2 runs
  the study once more on the new rule.
- **JD, first run:** Edge parlays made +3.4% over 162, +15.2% since 10-15.
  It read only football's games; fixed for the second run.
- **IZ:** the restated record is on the site. 1,405 staked, 769–636,
  +23.03u, +3.2% ROI, 7,557 tracked.
- **JB:** college's price test can't run yet. Only 8 of 2,087 college picks
  had the market's chance at pick time, so the cap stays off. No setenv.
- **JA study:** the board's team chance beat a coin, the home rate and the
  tip records alone on games it never saw.
- **IX:** showed Duke's lead back at 52% with no receivers anywhere. That's
  fixed (step JC), and item 3 checks it.

## 0. Any time now: the disk and the backups (step JG)

Read-only. Old pre-repair copies prune on their own once this is live; this
shows what's in the backup folders, how full the disk is, and the backup
log:

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh JG 2>&1 | tee /tmp/jg.txt
```

And 1.4 GB you can clear now: /var/backups/qellys only holds backups from
before October 4 (they go to /srv/qellys/backups now, and offsite):

```
sudo find /var/backups/qellys -type f -mtime +20 -print -delete
```

The backup runs at 04:00 UTC: from the first run after Backblaze cleared
the old versions, the backup log's last lines should say "offsite copy
updated".

## 1. An hour after the restart, or tomorrow: the notices went out; the trimmed files; alerts on your phone (steps JH, JJ)

The notices you armed (JJ, Done above) go out from the push loop between
10:00 and 20:00 Eastern. Who's on now names a member a week after theirs
reached them, and the new Terms §5.7 takes effect for an existing account
30 days after its email. An hour after the restart (or tomorrow after
11:00 Eastern), both 1 and 2 November's should read 14 told, 0 to go:

```
cd /srv/qellys && sudo -u qellys python3 -m engine.policynotice status
```

If both still read 0 told inside those hours, the restart didn't take:
run `sudo systemctl restart qellys` once more.

The Caddy config with the new files' trimmed copies — the Owner desk's
(Who's on now included) and the notice bar's (it checks itself
first and keeps the old one if anything is wrong; run it again if you ran it
before 2 November):

```
cd /srv/qellys && sudo caddy validate --config deploy/Caddyfile --adapter caddyfile && sudo cp deploy/Caddyfile /etc/caddy/Caddyfile && sudo systemctl reload caddy
```

Not a command: on your phone, sign in to one of your two listed accounts
and turn alerts on (the Alerts page). The Owner desk then pushes
every listed account's phones when the site needs you — a board that hasn't rebuilt on
a day its league plays, grading stopped, the disk filling, a failed update,
odds credits running low — once a day each, held through your quiet hours.
The desk's Switches card says "On · 1 phone" once it's set.

Then the read-only check (`1`, `1`, `True`, the notices' counts, `1`), and
the two emails as a member gets them:

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh JH 2>&1 | tee /tmp/jh.txt
cd /srv/qellys && sudo -u qellys python3 -m engine.policynotice preview 2026-11-01
cd /srv/qellys && sudo -u qellys python3 -m engine.policynotice preview 2026-11-02
```

## 2. Any time after this push: the parlay study once more (steps JF, JD)

Read-only, about 3 minutes. Section 1 is the board's rule now (every pair
that makes sense, two of each kind a day); section 4 shows JE's lift rule
beside it. The header's commit should be this push's or later:

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh JD 2>&1 | tee /tmp/jd.txt
```

## 3. Any time now, after a college build: receivers are back (steps JC, IX)

The college board rebuilds through the evening. After the next build, each
game's top three should include receivers, and nobody's chance should be
above 0.30:

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh IX 2>&1 | tee /tmp/ix.txt
```

## 4. Any time now: the NFL's first touchdown, and what the tightening held (steps IU, IT)

Sunday morning's odds pull buys the first-touchdown prices (November's
budget is fresh). IU shows the board, each pick next to our chance and the
price, and any game still unpriced with our top three. IT shows what the
tightening held back and why (the 60% bar, a scout caution, a tight end's
under, and a receiving-yards under):

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh IU IT 2>&1 | tee /tmp/sunday.txt
```

## 5. Any evening now, after the NBA build: first basket on Long Shots (step JA)

Tonight's NBA board had no prices at all: "matched 0 props across 0
events", with October's budget spent. November's budget buys them, first
basket included. This shows the board, and how many of its picks have
graded:

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh JA 2>&1 | tee /tmp/ja.txt
```

## 6. Any time now: the new month, and the real bill (steps IP, IQ)

After the reset, the first odds pull reads the new balance and the plan
re-plans November from it. These show the plan with tonight's line, which
leagues were held for having no game, and which were allowed to buy. They
also show what the API billed against what we estimated (about 2.0× means
the 17 books double every call):

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh IP IQ 2>&1 | tee /tmp/nov1.txt
```

## 7. A day after item 6: the bill again, over a full day (step IQ)

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh IQ 2>&1 | tee /tmp/iq.txt
```

## 8. The next college game day (Nov 7), after its build: college's first touchdown, priced (step IX)

With November's budget the pull buys first-touchdown prices. The same
check shows the picks against our chance, and the next morning how many
finished games had their first scorer marked:

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh IX 2>&1 | tee /tmp/ix.txt
```
