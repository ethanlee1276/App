# Commands waiting for you

Every command waiting to be run on the box, in one place, so a day of
building doesn't leave them scattered. Each says when. `ssh` in first, run
them top to bottom, and paste back anything that prints an error or looks
off. When one is done it moves to docs/WHEN_YOU_ARE_HOME.md's history, where
every command already lives (the letters below are its steps).

Last updated 2026-11-05, after the NBA board started reading who starts
tonight before the tip (step KG: nothing to run, item 1m shows the box's
own verdict once the weekly refit has run it), and on 2026-11-04 after
the NBA's alternate lines got their own
correction (step KF: nothing to run, item 1l shows it once the weekly refit
has fitted it), every NBA rate started reading past a
player's last twenty games, checked on the box's seasons every week by
itself (step KD: nothing to run, item 1k), the NBA's three waiting checks started
running themselves in the weekly refit (step KC: items 1j and 1k need
nothing from you now), the NBA's graded record started grading the
scout's flags and the NBA build started keeping each game's spread and
total (step KB: nothing to run, item 1k), a deploy learned to wait for the weekly jobs
instead of killing them (step KA: items 1f and 1g), the NBA board learned to read the rotation
(a man's first games back, a role that jumped, a regular's return) and a
scout started naming the spots that still go wrong (step JZ: item 1k), the
NBA lab put points and threes on shot
volume and left a better spread waiting for one check (step JY: item 1j),
NBA Most Likely came back on the page and
the plan started saying where the month's credits went (step JW: item
00), and Long Shots got its faces back (step JX: item 00), and on 2026-11-03 after Most Likely learned by market and side too
(step JV: item 1h2), Caesars got its backup-book test (step JU:
item 1i), the weekly backup zip was fixed and a cleanup
written for after tonight's backup (step JT: item 0), Fliff took the tenth
book's slot (step JS: item 1b), the weather desk was paused while a
read-only check finds why its calls lost (step JR: item 1h), the models'
weekly refit learned to finish
in pieces and reach the NFL again (step JQ: item 1g), the college board
learned to build through a
busy history file and the college rosters file was cut from 13.3 MB to 5.6
MB (nothing to run for either; item 1f's command shows the board), the Lab
learned to finish in pieces and the
heartbeat started saying why a weekly job or a build failed (step JP: item
1f), the NBA Cup and the College Football Playoff got their brackets (step
JO: item 1e), the standings, rosters, injuries,
weather and races opened to free accounts (nothing to run), today's free
pick started travelling — an alert you turn on, the sign-up and the plans, a
share card (step JN: item 1d) — and the NFL got its playoff race (step JM:
item 1c). On 2 November the
odds feed was cut to ten books (step JL: item 1b) and you ran JK, JJ and JI
(Done, below).
Earlier that day the Owner desk was locked to the accounts you list
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
- **The trimmed files:** you put in the new Caddy config at 22:05 UTC, and
  the Owner desk's and the notice bar's files are served trimmed. Its
  "Unnecessary header_up" warnings are expected (the Caddyfile says why).

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

## 00. First, when you're home: NBA Most Likely is back, and where the credits went (step JW)

**NBA Most Likely.** The board had the picks the whole time (92 this
morning, journaled and graded every day: 1,087 settled at 65.7%). The page
hid every one. NBA picks carry no raw model number, the page read that
empty number as 0%, and it hid them as broken. Fixed in the page; nothing
to run. Once the box has this commit, open the NBA page and Most Likely.
If the board ever has picks the page can't show, the empty box now says
so instead of "nothing priced".

**Credits.** Nothing ran away. 100,000 a month is 3,333 a day, and the plan
spends nearly all of it on purpose (left-over credits expire). This month
opened with a college Saturday, an NFL Sunday (the dearest day, about 5,250
for the NFL alone) and a Monday night. About 10,000 by the 4th is on the
plan; its table allowed about 12,500 for those days. Read-only, it prints
the plan with a new "this month so far" line, then every day since the
renewal by sport:

```
cd /srv/qellys && sudo -u qellys python3 -m engine.oddsplan --month
```

Or both checks in one go:

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh JW 2>&1 | tee /tmp/jw.txt
```

Paste it back. "on its pace ✓" is what to expect; "AHEAD" means the day
lines show where.

**Long Shots faces (step JX).** Every Long Shots card drew initials since it
became first-scorer picks: the first-scorer price list has no photo. Each
build now gives those rows the photo the player's other props carry, or the
sport's stored one. Nothing to run; after the next NBA build this says how
many first-basket rows have a face:

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh JX 2>&1 | tee /tmp/jx.txt
```

## 0. Tomorrow, after the 04:00 UTC backup: offsite works, then clear about 13 GB (steps JT, JG)

You fixed Backblaze's cap and lifecycle and deleted the October 15
leftover. Why there's been no weekly zip since 8 October: the 15 October
run was cut off at the chores' one-hour limit while copying history.db,
its leftovers stayed, and the next two runs refused for lack of room
without clearing them. Fixed (step JT): it clears its own leftovers first
and leaves history.db to the nightly backup, which keeps three copies and
sends them offsite. Read-only first; the backup log should end with
`offsite copy updated`:

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh JT 2>&1 | tee /tmp/jt.txt
```

Then, **only if it says `offsite copy updated`**, the cleanup. These are
copies something newer covers (step JT says what each one is):

```
sudo rm -f /srv/qellys/data/backups/.scratch-*.db
sudo rm -f /srv/qellys/data/backups/pre-repair-closes-20261006-225314/history.db
sudo rm -f /srv/qellys/data/backups/backup_2026-09-20.zip /srv/qellys/data/backups/backup_2026-09-27.zip
df -h / | tail -1
```

Paste back both. Right now the nightly skips history.db because the disk
is too full for its copy; after this, the next night's log should say
`backed up: data/history.db`.

## 1. An hour after the restart, or tomorrow: the notices went out, and alerts on your phone (steps JH, JJ)

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

## 1b. Tomorrow evening, a day after this push: which books answered, and the bill (steps JS, JL, IQ)

You, 2026-11-02: "cut the books to 10". The feed bills every ten books a
call names as one region, so seventeen made every call cost double. Now
it's DraftKings, FanDuel, BetMGM, Caesars, Fanatics, Hard Rock, BetRivers,
theScore Bet, Fliff and Pinnacle (the sharp reference). Your JL run
showed theScore Bet answers as `espnbet` and its second key never did, so
that slot is Fliff's (you, 2026-11-03: "fliff"; step JS). Nothing to run:
it takes effect when the site restarts with the new code. A day on, this
shows which books answered (Fliff should be among them), and the plan's
"API's own bill" line, which should read about 1.0× now:

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh JL IQ 2>&1 | tee /tmp/jl.txt
```

## 1c. After the next NFL build: the NFL playoff race (step JM)

The NFL now has a race page (the Playoff race row on its menu). The next
NFL build writes it; this shows the week, the games left, when it was built
and each conference's seven if the season ended today:

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh JM 2>&1 | tee /tmp/jm.txt
```

## 1d. An hour after this push: today's free pick travels (step JN)

The Pick of the Day page has a switch at the top, "Today's pick, as an
alert" (also in Alerts), off until a reader turns it on: once a day, when
the pick is up, the phone hears the league and the pick's record — never
the pick on a lock screen. The sign-up and the plans now show today's free
pick, and every pick on the page has a Share card button. Nothing to run;
this shows the page has the switch, how many phones asked for the alert
and whether today's went, and today's free pick as the sign-up reads it:

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh JN 2>&1 | tee /tmp/jn.txt
```

Not a command: turn the switch on on your own phone to see the alert
arrive with tomorrow's pick.

## 1e. After the next NBA build, and again from 7 December: the two brackets (step JO)

The NBA Cup's page now draws the knockout bracket (the bracket if group
play ended today until 27 November), and from selection day, 6 December,
college's race page becomes the playoff bracket. Nothing to run; this
shows the Cup's eight and, once the committee has named them, the twelve:

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh JO 2>&1 | tee /tmp/jo.txt
```

Before 6 December the college line reads `False [] None` — that's right.

## 1f. The day after tomorrow: the Lab's first pieces, and why (step JP)

**Wednesday's run was killed by my pushes, not by the hour** (step KA): it
was 85 minutes into MLB, the first sport, when a push restarted the site at
16:59 UTC. MLB goes to the back of tomorrow's line, so the other five
sports go first and publish as they finish. A push no longer stops a job
in progress. Still, MLB alone ran past 85 minutes, so when its turn comes
it will likely be cut off at the hour; the check below says so, and that
is the line to paste.

The Lab's page has been stamped 29 September since then: its run built every
sport and published only at the end, and was cut off each night at the
hour. It now publishes each sport as it finishes, and the heartbeat carries
each weekly job's outcome. Nothing to run; tomorrow's chores start it. This
shows the Lab's outcome, any failing board's note, and each sport's date:

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh JP 2>&1 | tee /tmp/jp.txt
```

If the first line says `'cut_off': True` with a sport in `last`, that sport
alone outgrows the hour — paste it and I will cut its replay down.

The second line lists any board whose last build failed, and where. It
should be `{}`. From 07:56 on 3 November the college board failed every
build with `database is locked`, waiting to store last week's results. The
holder was the settle pass, which runs every five minutes: once the
official NFL file for Monday night landed, each pass locked the history
file and kept it for minutes. It now lets go before it fetches anything,
a locked write is tried again, and a lock costs the college build only
that refresh (its log says `CFB results not stored this build`). If `cfb`
shows up there again, paste the line.

## 1g. Thursday: the models' weekly refit reaches the NFL (step JQ)

**Wednesday's round was killed two minutes in by my push at 17:30 UTC**
(step KA), on its first piece of twelve (`yardage_mixture`); the NFL's fits
still read 25 August. The round carries over: tomorrow's chores continue it,
and a push no longer stops it part-way. The check below is the same.

The weekly deep refit, which re-learns each sport from its whole history,
was cut off at the hour every Wednesday since 2 September, inside MLB, so
the NFL's deep fits stopped in late August. It now runs as a round of
pieces, NFL first, continued day by day until done. Nothing to run;
tomorrow's chores begin it. On Thursday this shows the job's last line, the
round (what is done, what is left) and the fitted dates:

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh JQ 2>&1 | tee /tmp/jq.txt
```

If the first line says `'cut_off': True`, paste it: one piece outgrew the
budget on its own and needs cutting down.

## 1h. Any time after this push: the weather desk is paused, and why it lost (step JR)

You, 2026-11-03: "1, yes" to hiding the weather picks. Its calls claimed
about 86% and won about half. It now makes no calls: the page says it is
paused, and it keeps grading the calls it would have made, out of sight.
One cause is fixed already (it priced some evening markets against the
next day's forecast). Read-only, about a minute: the first line should say
`paused:` with the reason and `weather rows: 0`; the rest says whether the
wrong day was the whole story or the same-day forecasts were too sure:

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh JR 2>&1 | tee /tmp/jr.txt
```

Paste it back. Its last section fills as the shadow calls settle; in a week
or two it says whether the desk can come back.

## 1h2. Any time after this push: Most Likely learns by market and side (step JV)

You, 2026-11-03: "2, yes". A market that over-claims inside an honest side
(college receiving-yards unders, NFL tight-end unders) is now its own group
in the record's correction, kept only when it beats the old grouping on
games it wasn't fitted on. It refits by itself every night; this shows what
it would keep today, saving nothing:

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh JV 2>&1 | tee /tmp/jv.txt
```

Each league ends with a "by market too" line: `kept` or `not kept: the
maker level stands`.

## 1i. A quiet evening: Caesars tried as a backup sharp book (step JU)

You, 2026-11-03: "5, yes". Pinnacle's prop prices were never stored, so
this tries every stored book in Pinnacle's place on every stored pre-game
prop price with a result, and grades the bets each would have made.
Caesars has to make money in that role, call results better than the other
books' average, and beat every other book at it. Read-only, a few minutes:

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh JU 2>&1 | tee /tmp/ju.txt
```

Paste it back. Each sport ends with `holds` or `does not hold` and why.
Nothing changes on the boards either way; a `holds` comes back to you.

## 1j. Nothing to run any more: the NBA's two changes, replayed on the box (step JY)

The box runs this itself now, every week, inside the deep refit (step KC):
the spread's verdict is filed, the NBA's refit fits on it, and only then
is the spread switched on. The heartbeat's `nba_switches` says where it
stands. The command below is still there for a read whenever you want one.

You, 2026-11-04: "work on the nba most likely and edge bets ... find and
invent more tools and data". Two full seasons of the NBA's own play-by-play,
every idea fitted on one season and judged on the next (docs/NBA_LAB.md).
One change is on now: points and threes read a player's shot volume at his
long-run percentages, not his hot or cold streak (threes 1.68% closer,
points 0.99%). The other, a spread that follows the projection, is off
until this check says so: replayed through the board on two seasons, it
called 18,600 points overs 86% that hit 85%, where today's spread, before
its calibration, calls them 74%. Read-only, it replays every stored NBA game six
times and writes nothing; perhaps half an hour:

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh JY 2>&1 | tee /tmp/jy.txt
```

Paste it back. It ends with `shooting: projections closer in N of 5
markets` and either `spread: ready for the refit` or `spread: not yet` and
why. If ready, step JY has the refit and then the switch, in that order.

Also fixed, nothing to run: the NBA's corrections leaned to the over on
rebounds, assists and threes (about 4 points, worse than none) because the
weekly refit practised on whole-number lines where those push. It practises
on half points now; Wednesday's refit picks it up.

## 1k. Nothing to run any more: the teammate-out minutes, and the rotation's three rules (step JZ)

The box runs these itself now, every week, right before the NBA's refit
(step KC): the teammate-out minutes switch on when their held-out test
holds on the box's own seasons, and the rotation's rules stay on unless
those seasons say otherwise. The commands below are still there for a read.

You, 2026-11-04: "I want to make sure we're all ready to go for NBA ...
picking the right bets, reading the right scripts, picking the right
models". The minutes model is measured now (back-to-backs and blowouts stop
cutting minutes they don't), three new rules read the rotation (his first
games back play light, a minutes jump mostly holds, a regular's return
takes minutes back), and a scout puts the six spots that still go wrong
after our number on the cards. All in the code; nothing to switch on. Two
read-only checks on the box's own seasons, a few minutes:

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh JZ 2>&1 | tee /tmp/jz.txt
```

Paste it back. The first part should end `HOLDS — the board fills the slot
at k ...`; if it does, switch the teammate-out minutes on (one file; the
lab's two seasons say k 0.30):

```
cd /srv/qellys && sudo -u qellys nice -n 19 python3 nbavacancy.py --heldout --save
```

The second part should end `HOLDS — the board keeps all three.` If it says
`DOES NOT HOLD`, step JZ has the one line that turns the three off.

Nothing to run for the next part (step KB): the board learning that grades
the NFL's flags on our own picks now grades the NBA's too, every few hours
by itself.

Nothing to run for this one either (step KD): rebounds, assists, steals,
blocks and turnovers now read past a player's last twenty games (steals
4.5% closer on two held-out seasons, blocks 2.7-4.0%, turnovers 3.3%,
rebounds 2.0-3.2%, assists 1.6-2.4%), on from the next build, and the
weekly refit checks it on the box's own seasons and turns it off if they
disagree. For a read by hand, `bash tools/catchup.sh KD`. Record page → What it learned → NBA shows each flag once fifteen
graded picks carry one; a flag moves a number only once the record proves
it on games the fit never saw.

## 1l. After the NBA's piece of the weekly refit: the alternate lines' own correction (step KF)

Nothing to run first. Most Likely's NBA alternate lines (15+, 20+, 25+
points) were priced with a correction measured near the main line, which
undersold them: on two seasons replayed, lines it called 72-86% landed
about 90%. They get their own correction now, fitted at the alternate
lines by the weekly refit (item 1g's round fits it with the NBA). Once
that round has done the NBA, this lists the NBA's corrections; the new
ones end `@ladder`, one for each market, beside the market's own:

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh KF 2>&1 | tee /tmp/kf.txt
```

If no line ends `@ladder` after the round has done the NBA, paste it back.

## 1m. After the NBA's piece of the weekly refit: who starts tonight, the box's own verdict (step KG)

Nothing to run first. The NBA board now reads who is likely to start
before the tip (the injury report on each club's last starting five, a
regular coming back who started before he sat, each man's own starts
lately) and moves his minutes for it; it is on from this push. The weekly
refit's NBA check (`nbarules.py --save`, item 1g's round) re-measures it on
the box's own seasons and files its own verdict. Once that round has done
the NBA, this prints the switch, the verdict, when and why:

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh KG 2>&1 | tee /tmp/kg.txt
```

`starters on ready ...` is what it should say. If it says `off` or
`not yet`, paste it back with JZ's table (item 1k), which shows the rule's
own column, `the starting five`, season by season.

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

## 7. The next college game day (Nov 7), after its build: college's first touchdown, priced (step IX)

With November's budget the pull buys first-touchdown prices. The same
check shows the picks against our chance, and the next morning how many
finished games had their first scorer marked:

```
cd /srv/qellys && nice -n 19 bash tools/catchup.sh IX 2>&1 | tee /tmp/ix.txt
```
