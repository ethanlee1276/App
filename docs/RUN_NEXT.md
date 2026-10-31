# Commands waiting for you

Every command waiting to be run on the box, in one place, so a day of
building doesn't leave them scattered. Each says when. `ssh` in first, run
them top to bottom, and paste back anything that prints an error or looks
off. When one is done it moves to docs/WHEN_YOU_ARE_HOME.md's history, where
every command already lives (the letters below are its steps).

Last updated 2026-10-31 evening, after your IW, IV and IX paste (all done).

## 1. Now: the new stakes and the record (step IZ)

The record now leads with the picks we stake: Edge on the price ladder, and
Most Likely tracked for its hit rate until a league beats the price (the
NBA's has). Nothing to run for the change. These show the rule's answer per
league and rerun the study from the live receipts (read-only). Paste back
`/tmp/iz.txt` and `/tmp/iz_study.txt`:

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh IZ JA JB 2>&1 | tee /tmp/iz.txt
cd /srv/qellys && python3 tools/stake_study.py 2>&1 | tee /tmp/iz_study.txt
```

## 2. Now: college's price test (step JB)

College's "bolder than the books" picks claim 69% and hit 53%, the NFL's
problem before its price cap. This runs the same test on college's board
(read-only, a few minutes). Paste back `/tmp/jb.txt`:

```
cd /srv/qellys && sudo -u qellys nice -n 19 python3 pricetrust.py --sport cfb 2>&1 | tee /tmp/jb.txt
```

Only if its "The one board" line for college says PASSES, this turns the cap
on for college:

```
cd /srv/qellys && sudo ./deploy/setenv.sh QB_PRICE_TRUST_ADD cfb && sudo systemctl restart qellys
```

## 3. Any time: the NBA first-basket study again (step JA)

Same study as IV, now also scoring the board's own team chance (the home
lean plus both teams' tip records) on games it never saw. Read-only; paste
back `/tmp/ja_study.txt`:

```
cd /srv/qellys && sudo -u qellys python3 tools/first_basket_study.py 2>&1 | tee /tmp/ja_study.txt
```

## 4. Tomorrow after the morning NFL build: first touchdown, and what the tightening held (steps IU, IT)

Sunday morning's odds pull buys the first-touchdown prices (November's
budget is fresh). IU shows the board, each pick next to our chance and the
price, and any game still unpriced with our top three. IT shows what the
tightening held back and why (the 60% bar, a scout caution, a tight end's
under, and now a receiving-yards under):

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh IU IT 2>&1 | tee /tmp/sunday.txt
```

To undo the NFL tightening without a deploy:

```
cd /srv/qellys && sudo ./deploy/setenv.sh QB_NFL_TIGHT off && sudo systemctl restart qellys
```

## 5. Tomorrow evening, after the NBA build: first basket on Long Shots (step JA)

The NBA's first-basket board, and how many of its picks have graded:

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh JA 2>&1 | tee /tmp/ja.txt
```

## 6. Tomorrow (Nov 1), from mid-morning: the new month, and the real bill (steps IP, IQ)

After the reset, the first odds pull reads the new balance and the plan
re-plans November from it. These show the plan with tonight's line, which
leagues were held for having no game, and which were allowed to buy. They
also show what the API billed against what we estimated (about 2.0× means
the 17 books double every call):

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh IP IQ 2>&1 | tee /tmp/nov1.txt
```

## 7. Tomorrow evening: the bill again, over a full day (step IQ)

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh IQ 2>&1 | tee /tmp/iq.txt
```

## 8. The next college game day, after its build: college's first-touchdown board (step IX)

Saturday's college board was empty because October's odds budget was spent
(the pull was capped at 0 games). November's budget buys it again. This shows
the board (with any unpriced game's top three by our numbers), and how many
finished games had their first scorer marked for grading. Run it after the
build and again the next morning:

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh IX 2>&1 | tee /tmp/ix.txt
```
