# Commands waiting for you

Every command waiting to be run on the box, in one place, so a day of
building doesn't leave them scattered. Each says when. `ssh` in first, run
them top to bottom, and paste back anything that prints an error or looks
off. When one is done it moves to docs/WHEN_YOU_ARE_HOME.md's history, where
every command already lives (the letters below are its steps).

Last updated 2026-11-01, after the disk filled (step JG). Done:

- **The outage:** the weekly backup check filled the disk at 04:32 UTC and
  left its copy behind. You deleted the leftovers, restarted the site
  (back at 11:19 UTC) and fixed Backblaze's cap. The check, the pre-repair
  copies and the low-disk warning are fixed in the code (step JG), and
  item 0 below sees what's left.

- **JD, second run:** JE's same-game rule made things worse (+8.99u over 418
  tickets with it, +12.80u over 511 without), so it's off. What held in both
  runs: same-game pairs lost 9.5% over 213 and two-game pairs made 11.1% over
  298. Every pair that makes sense posts again, but money now rides only on
  two-game parlays; same-game ones are always tracked (step JF). Item 1 runs
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
  fixed (step JC), and item 2 checks it.

## 0. Today, half an hour after this push: the disk and the backups (step JG)

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

Tomorrow after 04:00 UTC, run the JG check again: the backup log's last
lines should say "offsite copy updated" once Backblaze has cleared the old
versions.

## 1. Any time after this push: the parlay study once more (steps JF, JD)

Read-only, about 3 minutes. Section 1 is the board's rule now (every pair
that makes sense, two of each kind a day); section 4 shows JE's lift rule
beside it. The header's commit should be this push's or later:

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh JD 2>&1 | tee /tmp/jd.txt
```

## 2. Tonight, after the next college build: receivers are back (steps JC, IX)

The college board rebuilds through the evening. After the next build, each
game's top three should include receivers, and nobody's chance should be
above 0.30:

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh IX 2>&1 | tee /tmp/ix.txt
```

## 3. Tomorrow after the morning NFL build: first touchdown, and what the tightening held (steps IU, IT)

Sunday morning's odds pull buys the first-touchdown prices (November's
budget is fresh). IU shows the board, each pick next to our chance and the
price, and any game still unpriced with our top three. IT shows what the
tightening held back and why (the 60% bar, a scout caution, a tight end's
under, and a receiving-yards under):

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh IU IT 2>&1 | tee /tmp/sunday.txt
```

## 4. Tomorrow evening, after the NBA build: first basket on Long Shots (step JA)

Tonight's NBA board had no prices at all: "matched 0 props across 0
events", with October's budget spent. November's budget buys them, first
basket included. This shows the board, and how many of its picks have
graded:

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh JA 2>&1 | tee /tmp/ja.txt
```

## 5. Tomorrow (Nov 1), from mid-morning: the new month, and the real bill (steps IP, IQ)

After the reset, the first odds pull reads the new balance and the plan
re-plans November from it. These show the plan with tonight's line, which
leagues were held for having no game, and which were allowed to buy. They
also show what the API billed against what we estimated (about 2.0× means
the 17 books double every call):

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh IP IQ 2>&1 | tee /tmp/nov1.txt
```

## 6. Tomorrow evening: the bill again, over a full day (step IQ)

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh IQ 2>&1 | tee /tmp/iq.txt
```

## 7. The next college game day (Nov 7), after its build: college's first touchdown, priced (step IX)

With November's budget the pull buys first-touchdown prices. The same
check shows the picks against our chance, and the next morning how many
finished games had their first scorer marked:

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh IX 2>&1 | tee /tmp/ix.txt
```
