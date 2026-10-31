# Commands waiting for you

Every command waiting to be run on the box, in one place, so a day of
building doesn't leave them scattered. Each says when. `ssh` in first, run
them top to bottom, and paste back anything that prints an error or looks
off. When one is done it moves to docs/WHEN_YOU_ARE_HOME.md's history, where
every command already lives (the letters below are its steps).

Last updated 2026-10-31.

## 1. Now: the Odds API renews on the 1st (step IS)

Makes the renewal day "set" instead of "assumed", so November's plan can
give each sport its headroom (about 19,000 credits that would otherwise go
unplanned):

```
cd /srv/qellys && sudo ./deploy/setenv.sh QB_ODDS_RESET_DAY 1 && sudo systemctl restart qellys
```

The check. The second line should say "renewal day set by QB_ODDS_RESET_DAY":

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh IS 2>&1 | tee /tmp/is.txt
```

## 2. Any time today: the NFL Most Likely audits (step IT)

The NFL Most Likely board is tightened from today: props and game lines
need 60%, and unders the scout warns about come off. Nothing to run for
that. These three read every graded NFL pick, change nothing, and say which
cuts hold up on weeks they never saw, how Sundays compare with Thursdays and
Mondays, and how long before kickoff the losers were taken. Paste back
`/tmp/it_fit.txt`, `/tmp/it_loss.txt` and `/tmp/it_flags.txt`:

```
cd /srv/qellys && sudo -u qellys python3 likelyfit.py --sport nfl 2>&1 | tee /tmp/it_fit.txt; sudo -u qellys python3 likelyfit.py --sport nfl --book board 2>&1 | tee -a /tmp/it_fit.txt; sudo -u qellys python3 lossaudit.py --sport nfl 2>&1 | tee /tmp/it_loss.txt; sudo -u qellys python3 nflaudit.py 2>&1 | tee /tmp/it_flags.txt
```

After the next NFL build (Sunday morning at the latest), what the tightening
held back:

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh IT 2>&1 | tee /tmp/it.txt
```

To undo the tightening without a deploy:

```
cd /srv/qellys && sudo ./deploy/setenv.sh QB_NFL_TIGHT off && sudo systemctl restart qellys
```

## 3. Any time today: the NBA first-basket study (step IV)

The research behind an NBA first-basket board, run on the box because the
NBA's shots live there. Read-only; paste back `/tmp/iv.txt`:

```
cd /srv/qellys && sudo -u qellys python3 tools/first_basket_study.py 2>&1 | tee /tmp/iv.txt
```

## 4. Tomorrow after the morning NFL build: the first-touchdown board (step IU)

First touchdown is now the NFL's Long Shots. Sunday morning's odds pull
buys the first-touchdown prices; this shows what the board made of them,
with each pick next to our chance and the price's:

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh IU 2>&1 | tee /tmp/iu.txt
```

## 5. Tomorrow (Nov 1), from mid-morning: the new month, and the real bill (steps IP, IQ)

After the reset, the first odds pull reads the new balance and the plan
re-plans November from it. These show the plan with tonight's line, which
leagues were held for having no game and which were allowed to buy, and
what the API billed against what we estimated (about 2.0× means the 17
books double every call):

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh IP IQ 2>&1 | tee /tmp/nov1.txt
```

## 6. Tomorrow evening: the bill again, over a full day (step IQ)

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh IQ 2>&1 | tee /tmp/iq.txt
```
