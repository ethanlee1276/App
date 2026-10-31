# Commands waiting for you

Every command waiting to be run on the box, in one place, so a day of
building doesn't leave them scattered. Each says when. `ssh` in first, run
them top to bottom, and paste back anything that prints an error or looks
off. When one is done it moves to docs/WHEN_YOU_ARE_HOME.md's history, where
every command already lives (the letters below are its steps).

Last updated 2026-10-31, after your IS and IT paste (both done).

## 1. Now: the price question, and the thin-picks test (step IW)

Tight-end unders now come off the NFL board, from your flag audit. Nothing
to run for that. These are read-only and take a few minutes each, because
they read our odds snapshots. The first asks whether the picks we took at a
price better than the market's own chance did better; the second tests
pricing the picks no three books priced. Paste back `/tmp/iw_loss.txt`,
`/tmp/iw_fit.txt` and `/tmp/iw_thin.txt`:

```
cd /srv/qellys && sudo -u qellys nice -n 19 python3 lossaudit.py --sport nfl 2>&1 | tee /tmp/iw_loss.txt; sudo -u qellys nice -n 19 python3 likelyfit.py --sport nfl 2>&1 | tee /tmp/iw_fit.txt; sudo -u qellys nice -n 19 python3 likelyfit.py --sport nfl --book board 2>&1 | tee -a /tmp/iw_fit.txt
cd /srv/qellys && sudo -u qellys nice -n 19 python3 research/thinmarket_box.py 2>&1 | tee /tmp/iw_thin.txt
```

That the box has it first (each count 1 or more):

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh IW 2>&1 | tee /tmp/iw.txt
```

## 2. Any time today: the NBA first-basket study (step IV)

The research behind an NBA first-basket board, run on the box because the
NBA's shots live there. Read-only; paste back `/tmp/iv.txt`:

```
cd /srv/qellys && sudo -u qellys python3 tools/first_basket_study.py 2>&1 | tee /tmp/iv.txt
```

## 3. Tomorrow after the morning NFL build: first touchdown, and what the tightening held (steps IU, IT)

Sunday morning's odds pull buys the first-touchdown prices; IU shows what
the board made of them, each pick next to our chance and the price's. IT
shows what the tightening held back and why (the 60% bar, a scout caution
or a tight end's under):

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh IU IT 2>&1 | tee /tmp/sunday.txt
```

To undo the tightening without a deploy:

```
cd /srv/qellys && sudo ./deploy/setenv.sh QB_NFL_TIGHT off && sudo systemctl restart qellys
```

## 4. Tomorrow (Nov 1), from mid-morning: the new month, and the real bill (steps IP, IQ)

After the reset, the first odds pull reads the new balance and the plan
re-plans November from it. These show the plan with tonight's line, which
leagues were held for having no game and which were allowed to buy, and
what the API billed against what we estimated (about 2.0× means the 17
books double every call):

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh IP IQ 2>&1 | tee /tmp/nov1.txt
```

## 5. Tomorrow evening: the bill again, over a full day (step IQ)

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh IQ 2>&1 | tee /tmp/iq.txt
```
