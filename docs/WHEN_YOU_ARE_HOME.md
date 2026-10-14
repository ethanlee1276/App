# Run these when you're home

Ethan, 2026-09-09, from work: *"please save all the code you need me too
run for when I'm home."*

Short list, in order. Everything is copy-paste. **Block 1 is the only one
that changes anything** — the rest are read-only and just tell me what
the box is actually doing, which is the half I cannot see from here.

Paste the output back with the block number and I can carry on.

The long history of one-off checks lives in `DROPLET_CHECKS.md`; this
file is only what is outstanding right now, and lines get deleted from it
as they are done. Pruned to that on 2026-10-02 (audit #13): every
answered or finished block moved there, word for word.

### Start here — 2026-10-13 (Ethan: "save all code for when I'm home")

Everything from 2026-10-12 and 10-13, in order: the parlay checker in
Ask (live chances, the hedge, a better number, saved slips on the Live
tab, our read on a leg no board carries, better legs, the cash-out
check, the last-leg alert), the subscription check on every open, the
MLB profit calendar that stopped at September, a Most Likely profit
calendar beside the edge one (step 46; nothing to run), and bets that
settle minutes after the final instead of the next day (step 47; J), a
game line no board prices graded by our own game model (step 48), a
carry chart for every NFL and college runner (step 49; K), a route
chart for every NFL receiver (step 50; K), and whether the charts' data
can make better picks — measured, it can't on its own (step 51); L
re-reads the closing line, where our own record points instead. The
charts read empty for every player the afternoon they shipped (the
box had already run that day's chores, which fill them); the box now
fills an empty chart table by itself within minutes (step 52; K shows
it). College now counts a receiver thrown at who caught nothing as a
zero (step 53; M). The NBA board, a week before opening night, now reads
the clubs' current rosters and ESPN's injury board (step 54; N), with a
check of whether a teammate's number should move when a regular sits
(step 55; O). Every UFC card now says where its line opened and where it
is now (step 56; P). The chart's X sits below the phone's status bar
(step 57), and every carry and route chart shows the player's face — his
photo, or his initials when no photo loads (step 58; Q). Your two calls
from H are built: a college receiving bet now waits for the play file and
is graded at zero when it shows he was thrown at (step 59; R), and the NBA
board prices points + rebounds, points + assists and rebounds + assists
(step 60; S). Tap any football pick, on Most Likely or anywhere else, and
its page now draws his route chart or carry chart in place, with no
button; the player page has it too, and the parlay checker's football
legs carry a chart button (step 61; T). Each player's chart leads with
what he does, a back's carries and a receiver's or tight end's targets,
whatever the bet (step 62; T). A quarterback's pick now draws every
throw he made, where it went and whether it was caught, and the sacks he
took (step 63; U). A college receiver's pick draws every pass thrown his
way that the play file names, 2025 on (step 64; V). A baseball pick now
draws the hitter's hit tracker (every ball he put in play, where it
landed and how hard) or the pitcher's pitch chart (every pitch, where it
crossed the plate and what came of it) (step 65; W). A basketball pick
draws his shot chart: every shot he took on the half court, made or
missed, each zone beside the league's percentage (step 66; X). A hockey
pick draws the skater's shot map or the goalie's save map, off the shots
the box already stores for the xG model (step 67; Y). Every player pick in
every league now has a Role chart beside his own: how much he is used,
game by game (snaps, targets, carries and his share of his team's;
minutes and starts; plate appearances and his spot in the order, or a
pitcher's pitch count and rest; ice time and shots) (step 68; Z). A
kicker's pick draws every field goal and extra point he tried, by
distance, made or missed, in what weather, each distance band beside the
league's rate (step 69; AA). Every fighter on the UFC card now has a
Fight history button: each fight on his record, who, how it ended, the
round and the time in it, and both men's numbers (step 70; AB). Every
player pick in the NFL, college, NBA, NHL and MLB now has a Matchup chip
beside his own chart: his chart's zones, how much of his volume goes to
each, what tonight's opponent allows there against the league, and one
fit number; context only (step 71; AC). Every hitter's chart now
carries our own expected average and slugging (xBA, xSLG), from how hard
and at what angle each ball left the bat, and a test on games the table
never saw decides whether they are ever more than context (step 72; AD).
The whole picture, sport by sport, is in
`docs/ALL_SPORTS_GAPS_2026-10-13.md`.
All of it is on the box already; it pulls every five minutes. Lettered,
so it never clashes with the numbered steps further down that every note
refers to. Paste back what each one prints, with its letter.

Nothing here changes anything except C (only if email isn't on yet),
D's Stripe settings, Q's photo fill (photo addresses only — the same
thing tomorrow's chores would write) and AD's two model files (the table
the chores would fit anyway, and the test's verdict). Every command runs on the box (`ssh` in first).

**A. The box has today's code.** The first line should end `Our own expected average and slugging on every hitter's chart, measured before any use`
(or be newer), and the second should print `has today's code`. If it prints nothing or
"Not a valid commit name", the box hasn't pulled yet: wait five minutes
and run both again.
```
git -C /srv/qellys log --oneline -1
git -C /srv/qellys merge-base --is-ancestor 653332e2 HEAD && echo "has today's code"
```

**B. Health check** (paste all of it):
```
uptime; free -m
ps -eo pid,ni,pcpu,pmem,etime,args --sort=-pcpu | head -8
for p in / /js/app.js /data/recommendations.json /data/record.json; do curl -s -o /dev/null -w "$p %{http_code} %{size_download}B %{time_total}s\n" http://127.0.0.1:8000$p; done
journalctl -u qellys --since "2 hours ago" --no-pager | grep -iE "refresh|cycle|took|build|slip watch" | tail -15
```

**C. Is email on?** "Forgot password?" and the new last-leg email both
need it:
```
curl -s http://127.0.0.1:8000/api/account/me; echo
```
`"reset_by_email": true` means it's on; go to D. `false` means step 26
below isn't done yet. It takes about ten minutes: a Resend account, its
key put on the box with `sudo ./deploy/setenv.sh QB_RESEND_KEY`, a
restart, then the test email in 26 D. Until then the Forgot page sends
people to qellysbook@gmail.com, and the Live tab says email isn't
switched on instead of offering the last-leg switch.

**D. Stripe** (step 37 says why). Three settings in Stripe's dashboard,
nothing to type on the box:
* Developers → Webhooks → your endpoint → **Send test webhook**. It
  should say `200`. If it's blocked, Bot Fight Mode is on; docs/DEPLOY.md
  says how to turn it off.
* Settings → Billing → **Customer portal**: "Update payment methods" and
  "Invoice history" switched on. That's how a locked customer pays.
* Settings → Billing → **Subscriptions and emails**: "Send emails when
  card payments fail" switched on.

Then two read-only checks. They print statuses, counts and times, never
an email. Open the site on a subscribed account first; the second line
should then print under 60 (seconds since Stripe was last asked):
```
cd /srv/qellys && sudo -u qellys python3 -c "import time; from engine import accounts as A, billing as B; c=A.connect(); B.init(c); n=time.time(); print([tuple(r) for r in c.execute('SELECT status, COUNT(*), SUM(checked_at IS NOT NULL), ROUND(MAX(?-checked_at)/3600.0,1) FROM subscriptions GROUP BY status', (n,))])"
cd /srv/qellys && sudo -u qellys python3 -c "import time; from engine import accounts as A, billing as B; c=A.connect(); B.init(c); print(c.execute('SELECT ROUND(?-MAX(checked_at)) FROM subscriptions', (time.time(),)).fetchone()[0])"
```
In the first, each tuple is (status, accounts, read from Stripe, hours
since the oldest read). Every status except `canceled` and `none` should
have the third number equal to the second, and the last under 6.

**E. The parlay checker's measurements** (read-only, a few minutes each;
paste back the tables). Steps 38, 39 and 41 say how to read them:
```
cd /srv/qellys && sudo -u qellys python3 -m engine.proplivefit
cd /srv/qellys && sudo -u qellys python3 -m engine.slipread nfl "Josh Allen" rush_att over 5.5 -130
cd /srv/qellys && sudo -u qellys python3 -m engine.slipreadfit --sport nfl --seasons 2023 2024 2025
cd /srv/qellys && sudo -u qellys python3 -m engine.slipreadfit --sport cfb --seasons 2024 2025 --limit 3000
```
* The first replays the live chance on three NFL seasons. If "blend"
  beats "ours" by much, say so; changing the model is your call.
* The second is our read on a prop no board carries. `"found": "read"`
  with a projection means it works.
* The last two replay that read on seasons already played. "ours" should
  beat "last8" on Brier (lower is better) in every market, and each
  calibration band should land near what it said.

**F. Walk it on your phone.**
1. In Ask, tap the paperclip, then **Grade a parlay screenshot**, with any
   slip.
2. On the card, check the grade, "Why we say X%" under a leg, any leg our
   model reads off the board, the better legs, the hedge and the
   cash-out box.
3. Type a stake and tap **Save to My Bets**.
4. Open the Live tab. The slip is under **Your saved slips**, and the
   email switch sits above it. Tick it if C said email is on.

**G. After a game night with a saved slip open** (step 44). The first
prints a line for each minute a slip reached its last leg; the second
lists every alert noted, and `mailed` 1 means the email went:
```
journalctl -u qellys --since "12 hours ago" --no-pager | grep "slip watch"
cd /srv/qellys && sudo -u qellys python3 -c "from engine import accounts as A; c = A.connect(); print([tuple(r) for r in c.execute('SELECT user_id, bet_id, fired_at, mailed FROM slip_alerts')])"
```
During an NHL game, the new hockey box file (step 38). It prints when it
was written, each game, and how many player lines it has:
```
cd /srv/qellys && sudo -u qellys python3 -c "import json; d=json.load(open('web/data/live_nhl_box.json')); print(d['generated_at'], [(g['away']+'@'+g['home'], g['state'], len(g['players'])) for g in d['games']])"
```

**H. Your calls.** Answer any time; nothing breaks while they wait.
* **UFC in the parlay checker?** A fight leg reads "not on our board"
  today (step 38b).
* **Quarterback carries on the board itself?** The market gets measured
  first, as the other five were (step 39b).
* **The football matchup check.** Should the model's own matchup step
  count when the scan has no lean on him (step 39b)?
* **College in the off-board read's lineup and usage steps** (step 43).
* **A fresh odds pull of a slip's own markets** when our price is old.
  A 4-leg ticket over two games costs about 3–4 credits, from the same
  daily budget the board uses, so you'd pick a daily cap (step 36,
  round three).
* **Cancel at the end of the month, or at once?** Stripe's portal
  setting (step 37). The site handles either.
* **The last-leg alert on the Alerts bell too?**
* **Pull a Most Likely pick when its line moves a point against it
  before kickoff?** L's answer first (step 51).
* ~~**Grade a college receiving bet the way the book does when the play
  file shows he was thrown at** (step 53)?~~ **Answered 2026-10-13: yes**
  ("Also add both from my calls, the CFB and nba things"). Built: step 59,
  R. Past grades stay as they were.
* ~~**NBA points + rebounds, points + assists, rebounds + assists?**~~
  **Answered 2026-10-13: yes.** Built: step 60, S — three more credits on
  every NBA game pulled; the WNBA's request is unchanged.
* **Let the measurement read summed markets** (step 60)? The weekly walk
  that earns a market its Most Likely shelf reads stored stat rows, and no
  row is stored for a sum, so PRA has never been measured — and neither
  can the three new combos be. They are on the Edge board and in the
  parlay checker, not Most Likely. Teaching the walk to add the parts up
  would let all four be measured (and shelved only if they clear the
  floor), but it also lets the weekly calibration fit PRA, which moves
  PRA's numbers on the Edge board — so it is yours to say.

**I. Why the MLB profit calendar stops at September** (step 45 says how
to read it; read-only, paste all of it):
```
cd /srv/qellys && sudo -u qellys python3 mlbprobe.py
```

**J. Bets settle minutes after the final** (step 47; read-only). Run it
the morning after a game night, and again late on a game night about
half an hour after a game ends. Paste all of it:
```
journalctl -u qellys --since "6 hours ago" --no-pager | grep -E "settle:|settled|box scores|UFC:|desk:" | tail -20
cd /srv/qellys && sudo -u qellys python3 settlecheck.py
```
`OWED` should read 0, or only show rows marked "no stat line for him
yet". `last pass` should be under 6 min.

**K. The carry chart and the route chart** (steps 49, 50 and 52;
read-only). Nothing needs running to fill them any more: since step 52
the box starts the fill by itself within a cycle of finding a chart
table empty, and the nightly keeps them current. This shows that it
did — the first command prints the fill's own log (it should end
`charts: filled`), the second what is stored, and each one's last
line should end "the screenshot's numbers". Paste all of it:
```
journalctl -u qellys --since "today" --no-pager | grep -E "charts:|engine.chartfill" | tail -8; sudo -u qellys cat /srv/qellys/data/cache/weekly_chartfill.log
cd /srv/qellys && sudo -u qellys python3 carryfill.py && sudo -u qellys python3 routefill.py
```
If the log is empty and the checks say "no carries stored yet", the
fill hasn't run: fill them by hand (a few minutes; it reads this
season's and last season's play-by-play and last season's route
charting, a ~49 MB file) and paste that too:
```
cd /srv/qellys && sudo -u qellys python3 carryfill.py --fill && sudo -u qellys python3 routefill.py --fill
```

**L. The closing line, on the repaired closes** (step 51; read-only,
seconds). On 2026-09-29 the loss audit found Most Likely picks that lost
the close hit 12–18% where we claimed 62% — but that was two days before
the NFL closes were repaired (until 2026-09-29 an NFL "close" could be
an in-game line, and a pick losing during the game moves its own line).
Since the repair, the same-book check (2026-10-04) has Most Likely losing
about 2 points to its close and the Edge picks beating theirs by about
2½. This re-reads the lost-the-close picks on the repaired closes and
says what each is: a scratch graded as a loss, news the market had
before us, or a close that is still not one. Paste all of it:
```
cd /srv/qellys && sudo -u qellys python3 closecheck.py --sport nfl 2>&1 | tail -80
```
If the lost-the-close picks still hit far under their claim and the
finals sit near the close, that is news, and the fix is a last look
before kickoff that pulls (or flags) a pick once its line has moved a
point against it — your call in H.

**M. College receivers thrown at who caught nothing** (step 53; a few
minutes). The nightly writes this season's; this re-reads last season's
college player file with the new rule too (player rows only — no
schedule, no lines), then checks. The first lines should show both
seasons with thousands of receiver-games on the record as 0; the VOIDS
lines are for your call in H. Paste all of it:
```
cd /srv/qellys && sudo -u qellys python3 cfbzeros.py --fill
```
Any time after, the check alone (read-only):
```
cd /srv/qellys && sudo -u qellys python3 cfbzeros.py
```
And the measurement, if you want to see it for yourself (read-only,
about a minute):
```
cd /srv/qellys && sudo -u qellys python3 cfbtargetfit.py
```

**N. The NBA board knows who plays where, and who is hurt** (step 54;
read-only, seconds). Opening night is a week out, so check both feeds
read on the box now. The first line should say roughly 450 to 550
players and no clubs missing; the second counts ESPN's injury words —
paste it, so every word that means "not playing" is checked against the
list the board holds as out:
```
cd /srv/qellys && sudo -u qellys python3 -c "
import collections, nba_build
t, missed = nba_build.current_teams('nba')
print(len(t), 'players placed by the club rosters; clubs missing:', missed or 'none')
i = nba_build.hoops_injuries('nba')
print(len(i), 'on the injury board:', dict(collections.Counter(v['status'] for v in i.values())))
"
```
From opening night on, every NBA build prints what it read (paste it the
first night):
```
grep -E "Rosters|Injuries|another club now" /srv/qellys/data/logs/nba_build.log
```

**O. When a regular sits, is the NBA board's number for his teammates
off?** (step 55; read-only, a few minutes). It replays every stored NBA
season with the board's own projection and prints, per season, how far
teammates ran above or below it in games a regular had just started
missing, against ordinary games. The last lines say whether the bar
written into the script before its first run is met. Paste all of it:
```
cd /srv/qellys && sudo -u qellys python3 nbavacancy.py
```

**P. UFC: the line on the card, and what the record says** (step 56;
read-only). On the next card each fight's card says where its line opened
and where it is now (the build log says how many bouts had two pulls):
```
grep "Line moves" /srv/qellys/data/logs/ufc_build.log
```
Then the two questions the NFL record answered in August, asked of the
UFC picks journaled since then — does our number know anything the price
doesn't, and did our picks beat the close:
```
cd /srv/qellys && sudo -u qellys python3 stakecheck.py --info --sport ufc --include-measurement
cd /srv/qellys && sudo -u qellys python3 stakecheck.py --clv --sport ufc --include-measurement
```
And the first question for every sport in one go (a minute; paste it all):
```
cd /srv/qellys && for s in nfl cfb mlb nba wnba nhl; do echo "== $s"; sudo -u qellys python3 stakecheck.py --info --sport $s; done
```

**Q. Every chart shows the player's face** (step 58; seconds). The daily
chores fill the charts' missing photos by themselves from tomorrow; this
does it now (it writes photo addresses only, and is safe to repeat):
```
cd /srv/qellys && sudo -u qellys python3 facesfill.py --sport nfl && sudo -u qellys python3 facesfill.py --sport cfb
```
Then the check (read-only). Each line should say every chart player, or
all but a handful, has a face; paste it with any names it lists:
```
cd /srv/qellys && sudo -u qellys python3 facesfill.py --check
```
From tomorrow the chores' own line says it (`faces: ... cfb ...`):
```
journalctl -u qellys --since "today" --no-pager | grep "faces:"
```

**R. College receivers thrown at are graded** (step 59; read-only,
seconds). Nothing to run for it to work. After Saturday's games, a
receiving bet on a man with no line in the box score waits for the play
file (it lands within about three days); the grading check calls those
`waiting on the college play file`, not stuck. Paste it on Sunday or
Monday:
```
cd /srv/qellys && sudo -u qellys python3 homecheck.py grading
```
And from next week, M's VOIDS line should stop growing for new games
(every void after today is a man the play file never had):
```
cd /srv/qellys && sudo -u qellys python3 cfbzeros.py
```

**S. The NBA prices points + rebounds, points + assists and rebounds +
assists** (step 60; read-only, seconds). The first line should list eight
markets, the second print `16 13`:
```
cd /srv/qellys && sudo -u qellys python3 -c "from engine.sources.oddsapi import SPORT_CONFIG as C; from engine.oddsbudget import EVENT_CREDITS as E; print(sorted(C['nba']['markets'].values())); print(E['nba'], E['wnba'])"
```
From opening night, every NBA build prices them; paste the first night's
count (each line on the board names its market, so this counts them):
```
cd /srv/qellys && python3 -c "import json,collections; d=json.load(open('web/data/nba.json')); print(collections.Counter(r.get('market') for r in (d.get('recommendations') or []) + (d.get('near_misses') or [])))"
```

**T. The charts on every football pick** (step 61; read-only, seconds).
Nothing to run for it to work. The first line should print `1` (the site
serves the chart that draws itself on a page), the second a few hundred
characters of a receiver's targets:
```
curl -s http://127.0.0.1:8000/js/carrychart.js | grep -c "function mount(el)"
curl -s "http://127.0.0.1:8000/api/players/routes?sport=nfl&player=Amon-Ra%20St.%20Brown" | head -c 300; echo
```
Then on your phone: Most Likely, tap any NFL receiver's or back's pick and
scroll past Form. His chart is there, already drawn: a back's Carry chart
(even on a receptions pick) with a `Carries | Targets` switch showing how
many of each he has this season; a receiver's or tight end's Route chart,
with the switch only if he has 3+ carries this season. If it says "No
targets on file", paste K's output.

**U. The passing chart** (step 63; read-only, seconds). Nothing to run
for it to fill: the box sees the new table empty and reads the
play-by-play into it within minutes of pulling (the same catch-up as
step 52). The first line counts the throws stored per season and kind;
the second is Josh Allen at the Rams in week 5, which should print
`LA {'att': 19, 'cmp': 12, 'yds': 210.0, 'td': 1, 'int': 1, 'sk': 1}`
(the box score, to the yard); the third is what the page asks for:
```
cd /srv/qellys && sudo -u qellys python3 -c "from engine import db; c=db.connect(); print(c.execute('SELECT season, kind, COUNT(*) FROM passes GROUP BY season, kind ORDER BY season DESC').fetchall())"
cd /srv/qellys && sudo -u qellys python3 -c "from engine import db, passes; c=db.connect(); d=passes.chart(c, 'Josh Allen', 2026); g=[x for x in d['games'] if x['week']==5][0]; print(g['opp'], {k: g['line'][k] for k in ('att','cmp','yds','td','int','sk')})"
curl -s "http://127.0.0.1:8000/api/players/chart?kind=passes&sport=nfl&player=Josh%20Allen" | head -c 300; echo
```
An empty first line or `{"filling": true}` from the third means it is
still filling: wait ten minutes and run them again. Then on your phone:
tap any quarterback's pick (passing yards, attempts, completions,
touchdowns, interceptions, even his rushing). His Passing chart is drawn
after Form with a `Passes | Carries` switch: every throw from the pocket
to where it landed, green for the yards after the catch, a red × for an
interception or a sack.

**V. The college target chart** (step 64; read-only, seconds). Nothing
to run: the box sees the college targets empty and reads the play file
into them within minutes, as in U. The first line counts the college
targets stored per season (2025 and 2026 only, by design) and how many
were caught; the second is what the page asks for:
```
cd /srv/qellys && sudo -u qellys python3 -c "from engine import db; c=db.connect(); print(c.execute(\"SELECT season, COUNT(*), SUM(complete) FROM targets WHERE sport='cfb' GROUP BY season\").fetchall())"
curl -s "http://127.0.0.1:8000/api/players/routes?sport=cfb&player=Jeremiah%20Smith" | head -c 300; echo
```
`{"filling": true}` means it is still reading: wait ten minutes. Then on
your phone: CFB, Most Likely, tap any college receiver's pick. His Target
chart is drawn after Form: each catch a line straight up from the line
as long as the yards it gained, each miss the file names a ring at the
line, in the order thrown.

**W. The hit tracker and the pitch chart** (step 65; read-only, seconds).
Nothing to run: the box sees the two new baseball tables empty and reads
this season's newest 400 finals from MLB's play-by-play within minutes
of pulling, then 400 more every night until the season is in (about a
week; the newest games come first, so this postseason and September are
on the charts from the first read). The fill's own log (the last
command) says `charts: empty — MLB 2026 mlb_pitches; reading them now`,
then `MLB 2026: 400 games, … plate appearances, … pitches; … older games
left for the nightly`. The first command counts what is stored per
season; the second and third are what the page asks for (any hitter and
any starter who played this month will do):
```
cd /srv/qellys && sudo -u qellys python3 -c "from engine import db; c=db.connect(); print(c.execute('SELECT season, COUNT(DISTINCT game_pk), COUNT(*) FROM mlb_pa GROUP BY season').fetchall(), c.execute('SELECT season, COUNT(*) FROM mlb_pitches GROUP BY season').fetchall())"
curl -s "http://127.0.0.1:8000/api/players/chart?kind=spray&sport=mlb&player=Aaron%20Judge" | head -c 300; echo
curl -s "http://127.0.0.1:8000/api/players/chart?kind=pitches&sport=mlb&player=Tarik%20Skubal" | head -c 300; echo
sudo -u qellys tail -5 /srv/qellys/data/cache/weekly_chartfill.log
```
Empty lists or `{"filling": true}` mean it is still reading: wait ten
minutes. `MLB 2026: not read — …` in the log means MLB's Stats API
refused the box; paste it (the box tries again on its own a while later). Then on your phone: MLB, Most Likely, tap any
hitter's pick (hits, total bases, home runs, RBIs, runs, walks). His Hit
tracker is drawn after Form: every ball he put in play where it landed,
gold for a home run, green for a hit, grey for an out, with the exit
velocity, launch angle and distance in the list under it; the season tab
splits the field into pulled, up the middle and opposite field. A
strikeouts or outs pick draws the pitcher's Pitch chart instead: every
pitch from the catcher's view, coloured by called strike, whiff, foul,
in play or ball, his pitch mix with speed, whiff rate and CSW, and the
season's share of pitches in each part of the zone.

**X. The shot chart** (step 66; read-only except the first line, which
reads one game). The sandbox I build in cannot reach the NBA's site, so
the play-by-play's field names come from the nba_api project's
documentation of it; the first command reads one real game the way the
chart does and prints a shot's fields and the first stored row, so we
both know the shape is what the code expects. Paste all of it:
```
cd /srv/qellys && sudo -u qellys python3 -c "from engine.nba import shots as S; p, b = S.read_once('0022501230'); a = [x for x in (p or {}).get('game', {}).get('actions', []) if x.get('actionType') in ('2pt', '3pt')]; print(sorted(a[0]) if a else 'NO SHOTS', {k: a[0].get(k) for k in ('xLegacy', 'yLegacy', 'shotDistance', 'area', 'shotResult', 'subType')} if a else ''); r = S.fold(p, b) if p and b else []; print(len(r), r[0] if r else 'NOTHING FOLDED')"
cd /srv/qellys && sudo -u qellys python3 -c "from engine import db; c=db.connect(); print(c.execute('SELECT season, COUNT(DISTINCT game_id), COUNT(*) FROM nba_shots GROUP BY season').fetchall())"
curl -s "http://127.0.0.1:8000/api/players/chart?kind=shots&sport=nba&player=Nikola%20Jokic" | head -c 300; echo
sudo -u qellys tail -5 /srv/qellys/data/cache/weekly_chartfill.log
```
The first line should list `xLegacy`, `yLegacy` and `shotDistance`
among the keys and print a stored row with a zone. If it says `NO SHOTS`
or `NOTHING FOLDED`, paste it: the shot chart waits on that. The box reads
last season's newest 300 games within minutes of pulling and 300 more a
night (this season's come first once it tips off on the 20th); `last
season's files are not on the CDN` in the log means the league no longer
keeps 2025-26 there, and the charts start on opening night. Then on your
phone, once the NBA board has picks: NBA, Most Likely, tap any pick. His
Shot chart is drawn after Form: one game's shots on the court, green in,
red rings missed, with every shot and free throw listed (the assist, the
block, fast break); the season tab puts each zone's percentage on the
floor and the splits put it beside the league's.

**Y. The shot map and the save map** (step 67; read-only, seconds).
Nothing to fill: they read the shots the xG model already stores. The
second line's last word should be `True` (our xG model is on disk, so
every shot carries its expected goals and the goalie his goals saved
above expected); `False` means the nightly xG fit has not run, and the
maps draw without those numbers:
```
curl -s "http://127.0.0.1:8000/api/players/chart?kind=shotmap&sport=nhl&player=Auston%20Matthews" | head -c 300; echo
curl -s "http://127.0.0.1:8000/api/players/chart?kind=saves&sport=nhl&player=Igor%20Shesterkin" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('season_label'), d.get('season_line'), d.get('xg_model'))"
```
Then on your phone: NHL, Most Likely, tap a skater's pick (shots on goal,
points, goals, assists): his Shot map, every attempt in the attacking
zone, gold a goal, green on goal, a ring missed, a cross blocked. A
goalie's saves or goals against draw his Save map: green saved, red in.

**Z. The role chart** (step 68; read-only, seconds). Nothing to fill: it
reads the box scores every board already reads. Each line names the
league, the player, the number his role is read by and how many games
it counts; any regular who played this season will do (change a name
that prints `None`). The last command lists five new name indexes the
box built on its own the first time it opened the database after
pulling (a second or two each); all five should print:
```
for q in "nfl&player=Ja%27Marr%20Chase" "cfb&player=Jeremiah%20Smith" "nba&player=Jalen%20Brunson" "wnba&player=Caitlin%20Clark" "mlb&player=Aaron%20Judge" "nhl&player=Auston%20Matthews"; do curl -s "http://127.0.0.1:8000/api/players/chart?kind=role&sport=$q" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('sport'), d.get('player'), d.get('lead'), [m['key'] for m in d.get('metrics', [])], (d.get('season_line') or {}).get('n'))"; done
cd /srv/qellys && sudo -u qellys python3 -c "from engine import db; c=db.connect(); print([r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='index' AND name IN ('nhl_shots_shooter','nhl_shots_goalie','mlb_pa_batter_name','mlb_pa_pitcher_name','nba_shots_name')\")])"
```
Then on your phone: any league, Most Likely, tap any player's pick. His
own chart is drawn first; the Role chip beside it switches to his role:
one strip per number, every game in order from the left, his season's
average dashed across it, the game you picked lit (tap any bar for that
game); the season tab lights his last three and adds the splits (his
last 3 and 5 beside his season, home and away, started or not).

**AA. The kicker chart** (step 69; read-only, seconds). Nothing to run:
the box sees the new `kicks` table empty and reads this season's kicks
from the NFL play-by-play within minutes of pulling (the same read the
carry, route and passing charts make), last season's with the nightly.
The fill's log says `NFL 2026: … carries, … targets, … throws, … kicks`.
The first command counts what is stored per season; the second is what
the page asks for (any kicker will do):
```
cd /srv/qellys && sudo -u qellys python3 -c "from engine import db; c=db.connect(); print(c.execute('SELECT season, kind, COUNT(*) FROM kicks GROUP BY season, kind').fetchall())"
curl -s "http://127.0.0.1:8000/api/players/chart?kind=kicks&sport=nfl&player=Brandon%20Aubrey" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('player'), d.get('season_line'), [(b['name'], b['fgm'], b['fga'], b['league']) for b in d.get('by_band', [])])"
sudo -u qellys tail -5 /srv/qellys/data/cache/weekly_chartfill.log
```
`{"filling": true}` means it is still reading: wait ten minutes. Then on
your phone: NFL, any kicker's pick (kicking points, field goals made):
his Kicker chart, the posts at the top and each field goal at the
distance it was kicked from, green made, red dashes missed, a cross
blocked; the season tab puts each distance band's rate beside the
league's.

**AB. The fight history** (step 70; read-only, seconds). Nothing to run:
whenever a card is coming up, the box's UFC tick reads four of its
fighters' records at a time off ESPN (the same cached records the
dossiers are drafted from) into a new `ufc_fights` table, and the log
says `UFC  fight history: 4 fighter(s) read, … fights, … still to read`.
Between cards nothing is read. The first command counts fighters and
fights stored; the second is the log's last lines about it; the third
asks for the chart of the fighter read most recently:
```
cd /srv/qellys && sudo -u qellys python3 -c "from engine import db; c=db.connect(); print(tuple(c.execute('SELECT COUNT(DISTINCT fighter), COUNT(*) FROM ufc_fights').fetchone()), tuple(c.execute('SELECT COUNT(*), SUM(fights = 0) FROM ufc_fighters_read').fetchone()))"
journalctl -u qellys --since "6 hours ago" --no-pager | grep "fight history" | tail -5
f=$(cd /srv/qellys && sudo -u qellys python3 -c "from engine import db; r=db.connect().execute('SELECT fighter FROM ufc_fighters_read WHERE fights > 0 ORDER BY fetched DESC LIMIT 1').fetchone(); print(r[0] if r else '')"); echo "$f"; curl -s "http://127.0.0.1:8000/api/players/chart?kind=fights&sport=ufc&player=$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$f")" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('player'), d.get('season_line'), [(g['opp'], g['result'], g['method'], g['rnd'], g['clock']) for g in d.get('games', [])[:3]])"
```
Until a card's fighters have been read, the first prints `(0, 0) (0,
None)` and the third a blank name and `None None []`. The second number
in the first command's second pair is how many fighters ESPN could not
find (each is tried again after three days). Then on your phone: UFC,
any fight, "Fight history" under either fighter: By fight draws the
fight's clock filled to where it ended (green won, red lost, grey a
draw or no contest) and both men's numbers side by side; Career draws
every fight's length on one clock, with how he wins and loses, three
rounds and five, and when his fights end.

**AC. The matchup view** (step 71; read-only, seconds). Nothing to fill:
it reads the chart tables the box already keeps. Each line names the
league, the player, which of his charts it read (routes, carries, passes,
shots, skater, goalie, hitter, pitcher), the opponent as the table spells
it, the season, the fit and the opponent's rank; any regular against any
opponent will do (change a name that prints `None`). The first ask in each
league builds that league's sums (a second or two, baseball's a few) and
keeps them three hours. The last command lists the six new indexes the
box builds on its own the first time it opens the database after pulling:
```
for q in "nfl&player=Ja%27Marr%20Chase&opp=PIT" "nfl&player=Derrick%20Henry&opp=CLE" "cfb&player=Jeremiah%20Smith&opp=Penn%20State" "nba&player=Jalen%20Brunson&opp=BOS" "nhl&player=Auston%20Matthews&opp=MTL&fam=shotmap" "nhl&player=Igor%20Shesterkin&opp=TOR&fam=saves" "mlb&player=Aaron%20Judge&opp=TOR&fam=spray"; do curl -s "http://127.0.0.1:8000/api/players/chart?kind=matchup&sport=$q" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('sport'), d.get('player'), d.get('family'), d.get('opp'), d.get('season'), d.get('fit'), (d.get('overall') or {}).get('rank'), d.get('starter', ''))"; done
cd /srv/qellys && sudo -u qellys python3 -c "from engine import db; c=db.connect(); print([r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='index' AND name IN ('carries_season','targets_season','passes_season','nba_shots_opp','nhl_shots_season','mlb_pa_season')\")])"
```
Then on your phone: any league, Most Likely, tap a player's pick. Beside
his own chart and his Role is a chip that reads `Matchup vs` and tonight's
opponent: a row for each zone of his chart (depth and side for a receiver
or a passer, the hole for a back, field position in college, the shot
zone in the NBA, the distance from the net in hockey, the strike zone in
baseball), the share of his volume there on the left, and on the right
what tonight's opponent allows there against the league, green where it
is better for him and red where it is worse. Under it: the fit, the
opponent's rank (1st is the best for him), what they allow overall, his
top zone and the sample. A hitter's left side is tonight's starter's
pitches when the MLB board names a probable, the staff's otherwise.

**AD. Our own expected stats, and the test that decides what they are
for** (step 72; a few minutes at low priority; writes two model files and
nothing else). The first line shows the table the chores fit each night
after reading the finals (none until the first night after pulling); the
second fits it now instead, the same file the chores would write, and
prints how many balls it was fitted on; the third runs the test on every
stored plate appearance and saves its verdict (add `--dry-run` to print
without saving); the fourth asks for a hitter's chart and prints his
average, expected average, slugging, expected slugging and the verdict
the chart now reads:
```
ls -la /srv/qellys/data/models/mlb_xstats.json
cd /srv/qellys && sudo -u qellys python3 -c "from engine import db; from engine.mlb import xstats as x; m=x.fit_from_db(db.connect()); print(m['n'], x.save(m) if m['n'] >= x.MIN_BALLS else 'too few balls to fit')"
cd /srv/qellys && sudo -u qellys nice -n 19 python3 -m engine.mlb.xstatsfit
curl -s "http://127.0.0.1:8000/api/players/chart?kind=spray&sport=mlb&player=Aaron%20Judge" | python3 -c "import json,sys; d=json.load(sys.stdin); L=d.get('season_line') or {}; print(d.get('player'), d.get('season'), L.get('avg'), L.get('xba'), L.get('slg'), L.get('xslg'), d.get('x_measured'))"
```
The third prints the balls the table was fitted on, the three slices'
dates and sizes, then for HITS and BASES the actual, expected and league
scores on the last slice with each half's gain against the bar and
`PASSES the bar` or `does not pass`. Paste all of it back: a pass is
written on the chart and is your call from there; it moves no price by
itself. Then on your phone: MLB, any hitter's pick, the hit tracker's
season tab: xBA under his AVG, xSLG under his SLG, and a ball's tooltip
ends with its xBA; the note under the chart says what the test found.

The numbered steps below, from 2026-10-07 to 10-13, are the full list;
anything there not marked Done still applies, in order.

### Tonight — 2026-10-07 evening, in order (Ethan: "i am home so give me all the code needed to run")

Seven steps, top to bottom. Every command runs on the box (`ssh` in
first). Paste back anything that prints an error or looks off.

1. **The box has tonight's code.** The top line should read `Social: the
   founder's profile` or something newer; if it is older, wait five
   minutes and run it again:
   ```
   git -C /srv/qellys log --oneline -1
   ```
2. **Health check** (paste all of it):
   ```
   uptime; free -m
   ps -eo pid,ni,pcpu,pmem,etime,args --sort=-pcpu | head -8
   for p in / /js/app.js /data/recommendations.json /data/record.json; do curl -s -o /dev/null -w "$p %{http_code} %{size_download}B %{time_total}s\n" http://127.0.0.1:8000$p; done
   journalctl -u qellys --since "2 hours ago" --no-pager | grep -iE "refresh|cycle|took|build" | tail -15
   ```
3. **Make your profile the Founder's.** On the site, signed in as
   yourself, open the Account page and make your profile if you have
   not (handle, name). Then run this with the email you sign in with in
   place of `you@example.com`:
   ```
   cd /srv/qellys && sudo -u qellys python3 -c "from engine import accounts as A, socialfeed as SF; print(SF.crown(A.connect(), 'you@example.com'))"
   ```
   It prints `200` and your profile with `'founder': True`. Reload the
   site: a gold **FOUNDER** pill and the gold tick beside your name on
   every post, comment, profile and leaderboard; a gold ring on your
   picture; a gold-edged profile card with "Founder · built Qellys Book"
   and a **Moderation** button. What it adds for you alone:
   - every post's dots menu: **Pin to the top of the feed** (one post
     leads For You and Latest for everybody; pinning another replaces
     it) and **Hide for everyone**; every comment: **Hide**;
   - any other profile's dots menu: **Give / Remove the verified tick**;
   - the **Moderation** tab on your Account page: everything readers
     reported and everything hidden, each with Hide or Restore, and the
     pinned post's Unpin.
   Your own posts are graded exactly like everybody's; the badge changes
   nothing about the record. Nobody can give it to themselves: only this
   command sets it. To take it back, the same command with
   `, on=False` after the email.
4. **Give the site its own account** (once, a different email from
   yours). Done 2026-10-07: the crown worked, but the claim answered `409
   Somebody already has that handle` because YOUR account held
   `Qellys_Book`. First move your own handle: on the site, Account page →
   Edit profile → Handle (the founder's handle is no longer locked) →
   Save. Or from the box, with your email and the handle you want (no
   "qellys" in it):
   ```
   cd /srv/qellys && sudo -u qellys python3 -c "from engine import accounts as A, socialfeed as SF; print(SF.claim(A.connect(), 'you@example.com', 'YourNewHandle'))"
   ```
   It prints `200` with the new handle and `'founder': True` still on.
   Then the site's account (the other email, already signed up) takes the
   name; it becomes `Qellys_Book` with the gold tick and the site's mark:
   ```
   cd /srv/qellys && sudo -u qellys python3 -c "from engine import accounts as A, socialfeed as SF; print(SF.claim(A.connect(), 'site@example.com', 'Qellys_Book', name='Qellys Book'))"
   ```
5. **The real sportsbook logos** on the Bet it, Tail and Pick of the Day
   sheets. On 2026-10-07 it stopped with `PermissionError` on
   `web/img/books/draftkings.png`: that folder belonged to root. Fix the
   owner once, then run it (paste the output; a line starting `--` is a
   book that keeps its coloured initials):
   ```
   sudo chown -R qellys:qellys /srv/qellys/web/img/books
   cd /srv/qellys && sudo -u qellys python3 -m engine.booklogos
   ```
   Done 2026-10-07: 14 of 17. Fanatics, theScore Bet and Kalshi missed
   (two were real icons that were not PNGs; Fanatics' domain gave the
   blank globe). The fetcher now keeps any image a browser draws and tries
   more domains; once the box shows `Logos: any image a browser draws`
   or newer in `git -C /srv/qellys log --oneline -1`, run the second line
   again.
6. **Bet-slip links for player props** (after the next props refresh;
   paste the output):
   ```
   cd /srv/qellys && sudo -u qellys python3 -m engine.betlinks nfl --props
   ```
7. **Walk it on your phone**: step 8 of the section below (Tail, posting
   from the slip, the Pick of the Day bar), then the Founder tools from
   step 3 here: pin a post, hide and restore one, open Moderation. With a
   game on, step 7 below checks the Watch button.

8. **Two red rows on the Status page** (Ethan's screenshots, 2026-10-07):
   NFL "Self-check: 8 of 384 claims fail" and "The Lab (weekly backtest):
   9 days ago". Paste all of this back. The first prints each failed
   claim (the page now also names which checks failed, on a phone too):
   ```
   cd /srv/qellys && sudo -u qellys python3 -c "import json; from engine import gate as G, boardtruth as T; T.KEEP=99; r=T.check(json.load(open(G.board_source('web/data/recommendations.json')))); print(T.line('NFL', r)); print(chr(10).join(r['problems']))"
   ```
   The Lab tries once a day once its page is a week old, so nine days
   means at least two tries failed. Its last try's output, the day it
   last tried, and whether the box ran out of memory:
   ```
   ls -la --time-style=+%F_%R /srv/qellys/web/data/backtest.json /srv/qellys/data/built/backtest.json /srv/qellys/data/cache/weekly_lab.* 2>&1
   tail -25 /srv/qellys/data/cache/weekly_lab.log
   grep -o '"lab_attempted": *"[^"]*"' /srv/qellys/data/cache/maintenance.json
   journalctl -u qellys --since "10 days ago" --no-pager | grep -iE "engine\.lab|lab:|backtest lab" | tail -15
   journalctl -k --since "10 days ago" --no-pager | grep -iE "out of memory|killed process" | tail -10
   ```

9. **What the box ran out of memory on** (2026-10-07: ten kernel kills
   of a ~1.15 GB python child between 15:54 and 22:01, under the unit's
   1600M cap). The self-check's nine FLOOR lines were picks the record's
   correction lowered after they made the list, which is on purpose; the
   check now reads their listed number. A chore the system kills now
   rests (daily 2 h, settle 30 min) instead of restarting every cycle,
   says so on the Status page, and every child writes unbuffered, so the
   next kill leaves its step in the journal. Paste all of this:
   ```
   systemctl show qellys -p MemoryMax -p MemoryCurrent -p MemoryPeak
   ps -eo pid,rss,etime,args --sort=-rss | head -6
   cat /srv/qellys/data/cache/chores_daily.json; echo
   journalctl -u qellys --since "21:57" --until "22:03" --no-pager | tail -40
   journalctl -u qellys --since today --no-pager | grep -E "killed by signal|cut off|finished in|chores \(" | tail -15
   ```

10. **Which daily step needs the memory.** Step 9's answer (2026-10-07):
    the daily pass itself, "killed by signal 9 during maintenance" at
    22:43, inside the unit's 1600M (MemoryPeak hit it). Its lines are
    unbuffered since 22:25, and from the next pull on each one ends with
    `[NOW MB, peak PEAK MB]`. Paste both; the step where the peak jumps
    is the one to fix:
    ```
    journalctl -u qellys --since "22:24" --until "22:44" --no-pager | grep -v '"GET' | tail -40
    journalctl -u qellys --since "1 hour ago" --no-pager | grep -E "MB, peak" | tail -40
    ```

11. **The memory fix, checked** (2026-10-07). The daily pass died eight
    minutes after "hold journal (mlb home_runs)": the next step, the book
    report card (engine/booksharp), loaded every odds snapshot ever saved
    into memory. It streams now and keeps only each snapshot's prices —
    measured here at 1,037 MB → 133 MB on a 146 MB history. After the
    pull showing `Book report streams` or newer, the next daily pass
    should end with a "book report" line and never "killed by signal 9";
    the peak on its lines should stay well under 600 MB. The settle chore
    was killed beside it at 23:30; its two close readers now keep only
    the fields a close is cut from (1,088 MB → 358 MB on 400,000
    snapshots, every close the same) and its lines carry the same memory
    stamp:
    ```
    journalctl -u qellys --since "3 hours ago" --no-pager | grep -E "book report|faces:|killed by signal|MB, peak" | tail -20
    ```

12. **Settling reads only its own bets' snapshots** (2026-10-08). The box's
    line history is 444 MB, 2,708,562 rows; settling grouped all of it to
    answer a handful of open bets (the 23:41 kill on the 7th). It now
    keeps only the open bets' players and markets: 28 MB against 360 MB on
    a 400,000-row test, every close the same. After the pull showing
    `Settle reads only its own bets` or newer, a day with no
    "killed by signal 9" is the check:
    ```
    journalctl -u qellys --since today --no-pager | grep -E "journal:|book report|faces:|killed by signal" | tail -20
    grep -o '"last_done": *"[^"]*"' /srv/qellys/data/cache/maintenance.json
    ```

13. **QB rushing yards against the defence — measure it** (2026-10-08,
    from the Bucs–Cowboys research: "Dallas has allowed a league-high 188
    rushing yards to quarterbacks"). The site now rates what every defence
    gives up in rushing yards TO QUARTERBACKS and shows it on a QB rushing
    pick and in the scan read, but it moves no number until it is measured
    on the box (the repo's rule). After the pull showing `Research parity`
    or newer, on the next quiet hour:
    ```
    cd /srv/qellys && sudo -u qellys python3 defensefit.py 2>&1 | tail -40
    ```
    Paste the `rush_yds` lines (RB and QB). If the QB arm's held-out gain is
    positive in every season, the next commit writes its strength into
    `defensevs.TRANSFER[("rush_yds", "QB")]` and `MODEL_STAT`; if not, the
    card keeps saying "shown for you; it has not predicted this bet".
    `docs/RESEARCH_PARITY_2026-10-08.md` is the whole audit of the four
    write-ups against the site.

    **Target depth** (same night): the units table gained six columns
    (targets and yards on short / intermediate / deep throws, per
    defence-week). The pull adds the columns empty; the nightly refresh
    fills this season on its next run, and last season — which the
    blend leans on early — needs one backfill:
    ```
    cd /srv/qellys && sudo -u qellys python3 -m engine.gamescan backfill 2025 2026
    sudo -u qellys nice -n 19 python3 ingest.py nfl --seasons 2026 2>&1 | tail -8   # the per-player tgt_short/mid/deep and att_clean/cmp_clean/att_hit/cmp_hit rows
    sudo -u qellys sqlite3 data/history.db "SELECT team, side, short_tgt, mid_tgt, deep_tgt FROM team_units WHERE season=2026 AND period='005' AND team IN ('DAL','TB')"
    ```
    (2026-10-09: the first two runs of the fitter printed no `rush_yds QB`
    line — on the old code AND on `Free data for three…`. Not the pull:
    the script's two sections could not see a shown-only stat (the
    legacy ratings never had it; the model section reads MODEL_STAT,
    which is None for it). From `The fitter measures the candidates` on
    it has a third section, "candidates — shown on the card, not in the
    number", with the per-season held-out line and the fitted b. Paste
    that. The backfill above was also first run on the old code, before
    the columns existed — run it again; and the ingest line as first
    written (`python3 -m engine.ingest --nfl`) is not a command, so the
    pocket and depth rows come from the corrected line. To see they
    landed:
    ```
    sudo -u qellys sqlite3 data/history.db "SELECT market, COUNT(*) FROM player_game_logs WHERE sport='nfl' AND season=2026 AND market IN ('tgt_short','att_clean') GROUP BY market"
    sudo -u qellys sqlite3 data/history.db "SELECT COUNT(*) FROM team_units WHERE season=2026 AND short_tgt IS NOT NULL"
    ```
    Both should be hundreds, not 0. The database is `data/history.db`
    (engine/db.DEFAULT_DB) — the first paste said `data/qellys.db`,
    which does not exist, hence "no such table".)

    **Result, 2026-10-09** — the candidates section printed
    `rush_yds QB  b = +0.302 ± 0.120 (n 955)`, held out 2021 −0.10%,
    2022 +1.26%, 2023 +0.12%, 2024 +0.09%, 2025 −1.92%, mean −0.11%.
    Fails the bar (two seasons negative, mean negative): the QB rushing
    card keeps saying "shown for you; it has not predicted this bet", and
    `defensevs.MODEL_STAT[("rush_yds", "QB")]` stays None with the numbers
    beside it. Nothing more to run for it this season.
    After the next NFL build, a receiver's pick page carries the line
    "NN% of his targets are short throws …; DAL ranks Nth of 32 against
    them". Then, on a quiet hour (it reads four seasons of play-by-play —
    the better part of an hour, memory-heavy; run it alone):
    ```
    sudo -u qellys python3 -m engine.scanfit --points /tmp/pts.pkl 2>&1 | tail -40
    ```
    Paste the `depth`, `yac_allowed` and `pocket_fit` lines (the last
    two from the free-data round the same night: yards after contact
    allowed off PFR's rushing rows, and the passer's not-hit / hit gap
    against the defence's pressure off the play-by-play). They go into
    `scanfit.MEASURED`; a signal moves a number only where the held-out
    gain is positive on average and in all but one season, and b clears
    MIN_T — the same bar every other scan signal failed.
    **Done without the box, 2026-10-13 — skip this run.** scanfit reads
    only nflverse's files, and the sandbox has them: the run took fifteen
    minutes there, reproduced the old six signals to within noise, and
    measured these three plus three new ones from the carry and route
    charts. None passes; all are in `scanfit.MEASURED` (step 51).

14. **The Gamecast** (2026-10-08, your three ESPN screenshots: "I want
    the page to look like ESPN's app"). Nothing to run — the fast loop
    already writes a game's deep file every twelve seconds while it is
    on, and from `The Gamecast` on that file carries the whole box score,
    each side's totals, the two records and the drive in progress; the
    page's rooms (js/gamecast.js) load the first time you open a live
    game. To see it: Live tab → tap a game in progress → the tabs read
    Gamecast · Box score · Play-by-play · Team stats · Odds & picks ·
    Injuries. If the Gamecast tab says only "Loading the gamecast…" for
    more than a few seconds, paste:
    ```
    curl -s -o /dev/null -w "%{http_code} %{size_download}B\n" https://qellysbook.com/js/gamecast.js
    ls -la /srv/qellys/web/min/js/ /srv/qellys/web/data/pbp/ | head -20
    ```
    (The trimmed copy is rebuilt by the updater after every pull; a 404
    on the first line means the pull has not landed.)

15. **The speed pass** (2026-10-09, your words: "the site feel super
    laggy", "all the logos and headshots take a while to load", "switching
    pages will also take a couple seconds"). Nothing to run for it to
    work — the box picks it up on its next pull. Three read-only checks
    tell me what the box itself adds, so paste all three:
    ```
    ls /srv/qellys/web/img/venues/variants/*@800.webp | wc -l
    ls -laS /srv/qellys/web/data/*.json | head -8
    cd /srv/qellys && sudo -u qellys python3 assets.py --probe --sport nfl 2>&1 | tail -25
    ```
    The first should say 30 (the phone-sized stadium renders). The second
    lists the biggest boards, which is what a sport switch downloads the
    first time. The third answers the one thing this sandbox cannot see:
    whether NFL's photo host serves the small headshot the page asks for.
    If its RESIZED lines all say FAIL, every NFL face falls back to the
    full-size photo, which is megabytes each, and that is the next fix.
    (Done 2026-10-09: the width-only resize answered 200 at 2.9 KB, so NFL
    faces now ask for exactly that shape.)

16. **The first visit to a sport** (2026-10-09, "now make the first visit
    to a sport faster too … everything needs to be faster"). Nothing to
    run for it to work. One read-only check, from the box, tells me how
    long the server itself takes to answer and how many bytes a phone
    really downloads for each board; paste what it prints:
    ```
    for u in /api/recommendations /api/mlb/recommendations /api/cfb/recommendations /api/nhl/recommendations /data/recommendations_picks.json /data/record.json /data/rosters_cfb.json; do curl -s -o /dev/null -H "Accept-Encoding: gzip" -w "$u %{http_code} wait %{time_starttransfer}s total %{time_total}s %{size_download} bytes\n" "https://qellysbook.com$u"; done
    ```
    "wait" over half a second on a board means the box is the slow part,
    not the phone. The record and roster files shrink by about 40% after
    their next rebuild (they are written compact now).
    (Done 2026-10-09: every "wait" was 0.16–0.22 s, and the split showed
    why — DNS 3 ms, connect 4 ms, the secure handshake 158 ms, then the
    first byte 4 ms after it. The server answers in 4 ms. The handshake
    number turned out to be curl's own, not the server's — see the end of
    step 17.)

17. **The slim record and the slow handshake** (2026-10-09). Nothing to
    run for the slim record to work: after the box pulls, the next settle
    pass writes `record_head.json` beside `record.json` — the same record
    without the sections only the Record page draws (about half the
    bytes) — and Home reads that instead. Two read-only checks; paste
    what they print:
    ```
    for f in record record_head; do curl -s -o /dev/null -H "Accept-Encoding: gzip" -w "$f %{http_code} %{size_download} bytes\n" "https://qellysbook.com/data/$f.json"; done
    uptime; free -m; swapon --show; vmstat 1 5; cat /proc/pressure/cpu /proc/pressure/memory; ps -eo pid,ni,rss,pcpu,comm --sort=-rss | head -8; for i in 1 2 3 4 5; do curl -s -o /dev/null -w "tls %{time_appconnect}s first byte %{time_starttransfer}s\n" https://qellysbook.com/data/record_head.json; done
    ```
    The first line should show `record_head` well under `record`; a 404
    on it only means no settle pass has run since the pull. In the second
    check, `vmstat`'s `si`/`so` columns above zero mean the box is
    swapping (the handshake waits on memory read back from disk); `st`
    above 5 means DigitalOcean is lending our one CPU to a neighbour,
    which no code change fixes; the `some avg10` lines above 10 mean the
    box is short of memory or CPU. Five handshakes all near 0.15 s is a
    steady cost; one slow and four fast was a cold start.
    (Done 2026-10-09. The slim record is 31.8 KB on the wire against
    136.7 KB for the full one. No swapping (`si`/`so` 0), no steal (`st`
    0–1); the CPU is full of the builds and chores, all at nice 10, so
    Caddy and the server still go first. The handshake is NOT the server:
    curl itself spends 0.08 s of CPU per run on this box, and from here
    Cloudflare's own site and Google's take as long as ours —
    0.119 s, 0.128 s, ours 0.102 s. A browser keeps its certificates
    loaded, so a visitor pays one round trip to New York instead. Also
    learned: Cloudflare is NOT in front of the site any more — no `cf-ray`
    or `server: cloudflare` header — whatever "Behind Cloudflare" in
    DEPLOY.md says. Don't chase the handshake again from the box; time it
    from a computer that is not the box if it ever matters.)

18. **College Most Likely** (2026-10-09, your words: "we need to fix that,
    and we need to make changes now"). The box's loss audit said the
    staked college picks were honest (claimed 63%, hit 63%) but bought at
    prices needing 65%, and the whole college board was too sure on
    unders, rushing yards and its bolder-than-the-books picks. Three
    things, in order:
    ```
    cd /srv/qellys
    sudo -u qellys python3 -m engine.posspread --sport cfb
    sudo -u qellys python3 -m engine.scouthist --sport cfb --dry-run 2>&1 | tail -40
    sudo -u qellys python3 -m engine.likelyctx fit --sport cfb --dry-run 2>&1 | tail -30
    ```
    The first SAVES college's measured spreads — WR catches ×1.20, WR
    yards ×1.35, RB rushing yards ×1.50, each better in 4-5 of 5 held-out
    seasons (the weekly job would save the same on its own). The other two
    are read-only: the scout's history and record checks, which matched
    nothing on the first run because of a join bug fixed in `e50ad436`.
    Nothing to run for the price rule: from the next college build a pick
    whose chance is below its price's break-even is graded on paper, not
    staked, and its card says "Price too high to stake".

19. **College teammate-out and new QB** (2026-10-10, "do the teammate-out
    and new QB stuff for college now"). Built and wired; nothing moves
    until college's own games pass the NFL's rule. Measure, read, then
    save (the weekly job would save the same on its own):
    ```
    cd /srv/qellys
    sudo -u qellys python3 -m engine.cfb.lineup --dry-run 2>&1 | tail -60
    sudo -u qellys python3 -m engine.cfb.lineup
    sudo -u qellys python3 -m engine.scouthist --sport cfb
    ```
    The first prints every case (a teammate ranked above or below him
    out, just now or already; a starting QB out behind a similar or a
    downgraded replacement) with its multiplier, its error and each
    season's; "ADOPT" marks the ones the next college build applies. The
    third saves the 14 scout cautions college's history proved on
    2026-10-10 (first game back, rushing overs on a team expected to
    trail, and the rest) — a pick carrying one is lowered by what history
    proved, never below its price.

20. **NFL games abroad** (2026-10-10, "make sure that our models and our
    bets ... is being adjusted for them being played out of the country").
    Nothing to run for it to work:
    - weather already comes from the real venue (since 2026-09-23 — every
      2026 site: Melbourne, Rio, London twice, Paris, Madrid, Munich,
      Mexico City);
    - the game model gives no home field at a neutral site (it was adding
      1.6 points to the listed home team in London);
    - the game page names the real stadium, with Mexico City's altitude;
    - the scout's "an over in a game played abroad" caution was tested on
      every international game since 2021 and did not hold (overs abroad
      hit no less), so it came off the cards the same day ("yes take it
      off").

21. **College touchdowns follow the team total** (2026-10-10, "we want the
    same methods and tools and models as we use for nfl"). The NFL's
    per-position exponent, measured on college's own seasons. It refits
    itself every week; nothing changes until a position passes. To see it:
    ```
    cd /srv/qellys && sudo -u qellys python3 -m engine.tdscale --sport cfb --dry-run
    ```
    "ADOPT" on a line means the weekly job will start using it for that
    position; "keep g +0.0" means no change. Takes a few minutes.

22. **Cloudflare back on, for speed** (2026-10-10). The full walkthrough,
    with what each setting is for and how to undo it, is in
    docs/DEPLOY.md under "Turning it back on, step by step". The order
    matters: SSL mode Full (strict) and Browser Cache TTL "Respect Existing
    Headers" BEFORE the orange cloud. Then on the box:
    ```
    sudo /srv/qellys/deploy/cfips.sh && sudo systemctl restart qellys
    /srv/qellys/deploy/cfips.sh --check
    ```

23. **First game back counts regulars only** (2026-10-10, "yes make that
    fix"). College's first saved history had quarterback overs in a
    player's first game back at -35%: backups who simply did not get in,
    not starters back from injuries. A return now counts only for a
    regular (top passer, top-two back by carries, top-three by catches in
    3 of the 5 games before). Re-save college's, and look at the NFL's:
    ```
    cd /srv/qellys && sudo -u qellys python3 -m engine.scouthist --sport cfb
    cd /srv/qellys && sudo -u qellys python3 -m engine.scouthist --sport nfl --dry-run
    ```
    The NFL's is saved by the weekly job on Wednesday either way; paste
    the dry run so we see what changes first. Since the second fix the
    same day, only games in the return's season and for its team make a
    regular (last November's starter who is a backup now is not one).

24. **Every college market, both boards** (2026-10-10: "QB interceptions
    ... rushing props ... pass completion props, pass attempt props, rush
    attempts, spreads, money lines ... into the most likely bets and the
    edge bets"). All of them are built, priced on Edge and settled. A
    college market opens on Most Likely when the box's own ranking walk
    measures it at 0.60 or better (the NFL's bar). To re-measure and see
    which open (saves as it goes; a few minutes):
    ```
    cd /srv/qellys && sudo -u qellys nice -n 19 python3 -c "from engine import db, rankfit; [print(l) for l in rankfit.measure(db.connect(), 'cfb')]"
    ```

25. **Five new NFL markets** (2026-10-10, "Yes add all of them"): a QB's
    pass + rush yards, a back's rush + rec yards, a kicker's points and
    field goals, a defender's tackles + assists. Each was measured before
    it went on (marketfit.py, held-out 2025: 0.683, 0.629, 0.673, 0.700,
    0.621). They are on the NFL odds request (22 credits an event, was 17)
    behind the drop-and-retry guard. After the next NFL build, see which
    the books priced and which reached Most Likely:
    ```
    cd /srv/qellys && sudo -u qellys python3 -c "
    import json, collections, os
    p = 'data/built/recommendations.json' if os.path.exists('data/built/recommendations.json') else 'web/data/recommendations.json'
    d = json.load(open(p)); new = ('pass_rush_yds','rush_rec_yds','kick_pts','fg_made','tackles_ast')
    recs = [r for r in d.get('recommendations', []) if r.get('market') in new]
    print('built:', collections.Counter(r['market'] for r in recs))
    print('book-priced:', collections.Counter(r['market'] for r in recs if r.get('has_market')))
    print('most likely:', collections.Counter(r['market'] for r in d.get('most_likely', []) if r.get('market') in new))"
    ```
    A market at zero under "book-priced" with the others filled means the
    API refused that key (the guard drops it and the rest keep working).
    Settling needs this season's box scores re-ingested once, so the
    kickers' and defenders' rows exist; the nightly ingest does it.

26. **Make "Forgot password?" email people** (2026-10-11, Ethan: "we
    have to have a forgot a password feture"). The Forgot page is built
    and the Gmail settings are on the box, but the test said **"Could not
    reach smtp.gmail.com on port 587"**: DigitalOcean blocks the mail
    ports (25, 465, 587) on newer accounts and often will not lift it. So
    the site now also sends through **Resend**, an email service the site
    talks to over normal HTTPS (port 443), which DigitalOcean does not
    block. Free for up to 100 emails a day. About 10 minutes:

    **A. The box has the new code.** The top line should read `Mail: send
    through Resend` or something newer; if older, wait five minutes:
    ```
    git -C /srv/qellys log --oneline -1
    ```

    **B. Make the Resend account and connect the domain:**
    1. Go to **https://resend.com**, sign up with qellysbook@gmail.com.
    2. **Domains → Add Domain**, type `qellysbook.com`, then click
       **Sign in to Cloudflare** and allow it. Resend adds its DNS records
       to Cloudflare for you. Wait until the domain says **Verified**
       (usually a few minutes; refresh the page).
       No Cloudflare button? Choose manual setup: Resend lists 3–4
       records. For each one, in Cloudflare → qellysbook.com → **DNS** →
       **Add record**, copy the Type, Name and Value exactly, and leave
       Proxy status as **DNS only** (grey cloud).
    3. **API Keys → Create API Key**, name `qellys site`, permission
       **Sending access**, then **Add**. Copy the key (it starts with
       `re_`); Resend shows it once. Don't send it to me.

    **C. Put it on the box** (`ssh` in), one line at a time:
    ```
    cd /srv/qellys
    sudo ./deploy/setenv.sh QB_RESEND_KEY
    sudo ./deploy/setenv.sh QB_MAIL_FROM noreply@qellysbook.com
    sudo ./deploy/setenv.sh QB_MAIL_REPLY_TO qellysbook@gmail.com
    sudo systemctl restart qellys
    ```
    The first one asks for the value and shows nothing while you type:
    paste the `re_...` key and press Enter. Emails come from "Qellys Book
    <noreply@qellysbook.com>", and anyone who hits Reply reaches
    qellysbook@gmail.com. (The Gmail settings you already set can stay;
    while QB_RESEND_KEY is set they are not used.)

    **D. Test it** (your own inbox):
    ```
    cd /srv/qellys && sudo python3 -m engine.mailer test you@example.com
    ```
    It should say `Sent to ...`. If it says the domain is not verified,
    wait for B2 to show Verified and run it again. Then on the site: Log in
    → **Forgot password?** → your account's email → **Email me a link**.
    To see the site knows mail is on (`"reset_by_email": true`):
    ```
    curl -s http://127.0.0.1:8000/api/account/me; echo
    ```
    Optional: an email when the site's service crashes:
    `sudo ./deploy/setenv.sh QB_ALERT_EMAIL qellysbook@gmail.com` then
    restart.

    **Rather send from the Gmail itself?** Ask DigitalOcean (Help →
    Support): "Please unblock outbound SMTP (port 587) on my droplet. It
    sends password-reset emails for my own site through my Gmail
    account." If they do, switch back with
    `sudo ./deploy/setenv.sh --unset QB_RESEND_KEY`,
    `sudo ./deploy/setenv.sh QB_MAIL_FROM qellysbook@gmail.com`, restart,
    and run the test in D.

    Notes: at most 90 reset emails go out a day (under Resend's free 100)
    and 3 an hour to one address. The morning/nightly digests stay off on
    Resend's free plan and on Gmail; a mailing list would use up the
    day's password resets. Until C is done, the Forgot page tells people
    to email qellysbook@gmail.com, and you can make a link by hand:
    ```
    cd /srv/qellys && sudo -u qellys python3 -m engine.accounts reset-link someone@example.com
    ```
    Email that link only to the account's own address.

27. **Hometown games for NFL picks** (2026-10-11, Ethan: "one signal that
    I want to add for our NFL bets is hometown returns"). A player's ROAD
    game within 50 miles of where he was born now raises a scout flag on
    his card ("an under in a road game in his hometown (Detroit, MI) …").
    His own team's home games never count, nor neutral sites. Like every
    flag it moves no number until the five-season replay proves it, by the
    same fixed bar as the rest (3+ points worse on that side, in both
    halves, 100+ games each). Both sides are flagged, so the replay finds
    whichever is real: if hometown players rise to it, unders on them get
    lowered; if the occasion gets to them, overs do.
    Birthplaces come from ESPN's rosters and Sleeper's player file; the
    map is the US Census place list (downloaded once).

    **A. Build the birthplace table** (a minute; prints who it placed and
    a sample of skill players born near another team's stadium — glance
    at the sample to check it looks right):
    ```
    cd /srv/qellys && sudo -u qellys python3 -m engine.hometown
    ```
    If it says the Census map could not be loaded, paste me that line.

    **B. See what five seasons say** (read-only; a few minutes):
    ```
    cd /srv/qellys && sudo -u qellys nice -n 19 python3 -m engine.scouthist --sport nfl --dry-run
    ```
    Paste back the `hometown:` line and any `PROVEN  hometown_…` line. A
    proven line starts lowering those picks after the weekly run saves it;
    none means the flag stays a note on the card. The weekly run rebuilds
    the birthplace table by itself from now on.

    **Run 1 result (2026-10-11):** 2,281 of today's players placed;
    Sleeper's file carries no birthplaces; history held only 142 hometown
    games — too few for the bar. Ethan: "ok push further." So A now also
    looks up every player in our 2021+ logs whom no roster lists today,
    by his ESPN id (from nflverse's season rosters), once each. **Run A
    again** — the first time takes 10–20 minutes (it walks ESPN's player
    pages slowly), later runs seconds. It prints `past players: …`. Then
    run B again: it now also prints **every hometown market's raw numbers**
    (hit rate against the usual rate, and every over / every under
    together) — shown, not applied, so you can see which way it leans
    even when it is too thin to prove.

    **Run 2 result (2026-10-11):** 2,792 players placed (555 past players
    from their ESPN pages) and 195 hometown games scored. Every over
    together hit 1.3 points above the usual rate and every under 2.3
    points below it, which is a lean toward players rising to the
    occasion. Catches overs ran +5.2% on 172 games. Nothing cleared the
    bar, which needs 100+ games in *each* half on one market, so nothing
    moves. The weekly run re-tests it as 2026 adds games. Nothing more to
    run.

28. **The extras** (2026-10-11, "add the three optional extras"):
    * **Crash alerts** are on: when the site's service fails, an email
      goes to qellysbook@gmail.com with the last lines of its log.
      Nothing to set. (To stop them: `sudo ./deploy/setenv.sh
      QB_ALERT_EMAIL off`.)
    * **DMARC**, so the reset emails keep landing in inboxes — in
      Cloudflare: qellysbook.com → **DNS** → **Records**. If a **TXT**
      record named `_dmarc` is already listed (Resend may have added one),
      you are done. If not, **Add record**: Type `TXT`, Name `_dmarc`,
      Content `v=DMARC1; p=none;`, then **Save**.
    * **Resend's limit**: nothing to do. 100 emails a day free; the site
      caps password resets at 90.

29. **More spots, contract years, milestones and the incentive tracker**
    (2026-10-11, Ethan: "all of it"). New on every NFL Most Likely card,
    under "Why?":
    * **Spot:** lines for primetime, extra rest (a bye, or the long week
      after a Thursday), a long trip (two or more time zones, or abroad),
      body clock (10am or earlier by his team's clock), division rematch,
      a new head coach (his first four games), altitude (Denver, Mexico
      City), a different surface from his home field, late season (team
      clinched or eliminated, week 15 on), revenge game (first time facing
      a team he played 8+ games for), contract year (the last season of
      his deal) and milestone chase. Like hometown, each moves no number
      until the five-season replay proves one side by the same fixed bar.
      A proven one then moves up to the Scout cautions and says why.
      Short weeks were already a flag (Thursday overs), so nothing new
      there.
    * **Milestone:** "913 receiving yards — needs 87 more in his last 4
      games for 1,000", from our own logs, in the last six games of the
      season. The site also lists every chase under **Milestone watch**,
      below Incentive watch.
    * **Incentive:** contract money, added by you from a news report
      (below). The card shows how far he has to go and links the report.

    **A. Build the contract table** (about a minute; nflverse's contract
    file, downloaded, never scraped). It prints how many skill players are
    in a contract year this season, with a sample:
    ```
    cd /srv/qellys && sudo -u qellys python3 -m engine.contracts
    cd /srv/qellys && sudo -u qellys python3 -m engine.contracts --player "Tee Higgins"
    ```
    The second shows one player's deals and which seasons were contract
    years (Higgins: 2023 and 2024 yes, 2025 no). The weekly run rebuilds
    the table from now on.

    **B. See what five seasons say about every spot** (read-only, a few
    minutes):
    ```
    cd /srv/qellys && sudo -u qellys nice -n 19 python3 -m engine.scouthist --sport nfl --dry-run
    ```
    Paste back the `spots, every market pooled` block and any `PROVEN`
    line. For one spot's every market, add `--spot primetime` (or
    `revenge`, `contract_year`, `extra_rest`, …).

    **C. Add an incentive when a report gives one.** Example: a report
    says a receiver gets $500,000 at 100 catches. **Put in his real name
    and the article's real link in place of the two examples.** Pasted
    as written, the example went in on 2026-10-11. Now the command
    refuses a name our game logs don't know and a link that isn't a real
    web address. If you added the example, take it out with
    `... engine.incentives remove --player "Player Name"`.
    ```
    cd /srv/qellys && sudo -u qellys python3 -m engine.incentives add --player "Player Name" --stat receptions --target 100 --bonus 500K --source https://link-to-the-report
    cd /srv/qellys && sudo -u qellys python3 -m engine.incentives list
    ```
    Stats it can track: `receptions`, `rec_yds`, `rush_yds`, `pass_yds`,
    `pass_td`, `anytime_td` (rushing plus receiving touchdowns). The link
    is required, and the card shows it. To take one out:
    `... engine.incentives remove --player "Player Name" --stat receptions`.
    `... engine.incentives milestones` lists every round-number chase from
    the logs. Everything here is a note on the card: an incentive can't be
    tested on past seasons (there is no list of past ones), so it never
    moves a number.

30. **Why the NFL board is red, and whether bigger units would help**
    (2026-10-11, Ethan: "we have won so many most likely bets … I feel
    like we should be up more money"; "save the code for when I'm
    home"). Read-only, seconds:
    ```
    cd /srv/qellys && sudo -u qellys python3 lossaudit.py --sport nfl
    ```
    Paste back, for **The one board** and **Most Likely, staked**:
    * `-- by price` — which price range loses.
    * `-- by our chance against the price` — the picks whose shown chance
      covered what the price needed to break even, against the ones it
      didn't. If the covered row clearly beats the other, the college
      rule (stake only what covers its price) is worth turning on for
      the NFL. That's your call; nothing changes until you say so.
    * `-- bigger units on the same … picks` — the same picks at 1u flat
      against 3u Top pick / 2u Strong / 1u Worth a look. Sizing multiplies
      a result. It cannot turn a loss into a win.

31. **Bills @ Rams: the four reports against our model** (2026-10-12,
    Ethan: "compare to what we have … then fix shit"). The write-up is
    `docs/RESEARCH_PARITY_2026-10-12.md`. Two model changes went in. They
    reach the board on the next NFL build by themselves, because the box
    pulls pushed code every five minutes:
    * **His own last season, week 4 on.** Every player's form is pulled
      toward his 2025 per-game number by a measured share (receiving
      yards 60% at four games, fading as the season fills). Held out on
      four seasons, every season improved. The pick page says how much.
    * **A teammate back.** A player's games without a teammate who has
      since returned count for less (Adams' games without Nacua). The card
      says **Teammate back**.

    **A. Our number at every leg the reports built or cut** (read-only,
    seconds; best before kickoff, 8:15 PM ET):
    ```
    cd /srv/qellys && sudo -u qellys python3 legcheck.py
    ```
    Each leg prints `theirs:` (the report's claim) and then ours, our best
    price and whether the board seated it.

    **B. Check the build took the changes** (read-only). It prints Adams',
    Kyren's and Stafford's projections, and any "back" card:
    ```
    cd /srv/qellys && sudo -u qellys python3 -c "
    import json; from engine.gate import board_source
    b = json.load(open(board_source('web/data/recommendations.json')))
    for r in b.get('recommendations') or []:
        if r.get('player') in ('Davante Adams', 'Kyren Williams', 'Matthew Stafford') and r.get('market') in ('rec_yds', 'receptions', 'pass_att'):
            print(r['player'], r['market'], r.get('projection'), (r.get('mate_card') or {}).get('headline', ''))"
    ```
    Adams' receiving yards should read near 64, not 90.

    **C. Re-measure on the box** (optional, a minute each; they read the
    box's own cached box scores and print the same tables):
    ```
    cd /srv/qellys && sudo -u qellys python3 seasonpriorfit.py --seasons 2022-2025
    cd /srv/qellys && sudo -u qellys python3 matefit.py --back
    ```

    **D. Decided 2026-10-12 (Ethan: "yes"):** the NFL now buys the
    alternate lines for completions, attempts and rush+rec yards too, so
    those numbers can be ranked on Most Likely and checked against our
    model. Three more Odds API credits a game (25 an event, from 22); a
    full Sunday pull goes from about 330 credits to about 375, and the
    budget pacer spaces pulls to match. College is unchanged. Nothing to
    run; it arrives with the next pull.

32. **The spread tilt: measured, and gone** (2026-10-12, Ethan: "keep
    going"). Report 1 said Buffalo throws more as the underdog. Measured
    on the board's own base (his form, his last season, the defence step),
    an underdog quarterback doesn't throw for more. The old tilt (+0.4% a
    point on an underdog's passing yards, catches and receiving yards)
    made every season 2022-2025 worse, and 2017-2021 agreed, so the board
    no longer applies it. The card now says "no script tilt is applied —
    measured". Nothing to run. To check it on the box (read-only, about a
    minute):
    ```
    cd /srv/qellys && sudo -u qellys python3 qbscriptfit.py
    ```
    Part 1 should read "not applied" for both lines. Part 2 should end
    each line with RETIRE.

    **Decided 2026-10-12 (Ethan: "yes" to keeping them):** the game-plan
    page keeps listing the game's script as a reason ("Script: expected to
    trail and throw — pass volume up"), as the Fantasy page's description
    of the game. The numbers don't use it, because it measured as adding
    nothing.

33. **Kalshi's NFL player props: what's listed** (2026-10-12; report 2
    priced Stafford 250+ yards at "Kalshi 68.5¢"). The site reads Kalshi's
    NFL game, spread and total markets and no player markets, because none
    was known, and Kalshi is blocked from where I build. Read-only, about
    a minute:
    ```
    cd /srv/qellys && sudo -u qellys python3 kalshiprops.py
    ```
    Paste back what it prints. If it finds NFL player series with open
    markets, I'll show Kalshi's price beside ours on those picks. It
    stays out of the number until it's measured, the same way the game
    lines started.

34. **The calibration replay reads last season now** (2026-10-12). The
    live board's form leans on last season from week 4, and the
    calibration fitter's replay didn't, so it was fitting corrections to
    numbers the board no longer makes. It does now (`propcal` →
    `backtest_from_stats(carry=True)`). Nothing to run: Wednesday's deep
    refit picks it up by itself. To run it sooner (about ten minutes; it
    rewrites the fitted model files and never touches the record):
    ```
    cd /srv/qellys && sudo -u qellys python3 -m engine.deepfit
    ```

35. **Last season in the usage step; defenders out** (2026-10-12, the
    rest of the Bills @ Rams follow-ups). Nothing to run for either.
    * **The usage step leans on last season too.** It's the part of the
      base built from recent targets and carries, and it read this
      season only, so the pull toward last season reached the board
      about half as hard as measured. The same pull now goes into it
      for catches, receiving yards and rushing yards. Every season
      2022-2025 improved, and 2017-2021 agreed. Passing yards got worse
      in 2025 and stays as it was. To re-measure on the box (a minute):
      ```
      cd /srv/qellys && sudo -u qellys python3 bridgefit.py
      ```
    * **A defence missing starters** (Out or Doubtful on the injury
      report) was measured and **isn't** in the number. Every market got
      worse in at least one held-out season. Injury reports only go back
      to 2022, so there's no older season to check a second idea on.
      Re-run it once 2026 is over:
      ```
      cd /srv/qellys && sudo -u qellys python3 defoutfit.py --seasons 2022-2026
      ```

36. **Ask grades a parlay from its screenshot** (2026-10-12, Ethan:
    "users can upload a screenshot of there parlay and it will rank it").
    In Ask, tap the paperclip, then **Grade a parlay screenshot**. The
    phone shrinks the picture and sends it once. Ask's model reads the
    legs off it: same key, counted as one question against the daily
    limits, with its tokens in the usage log. Every leg is then priced
    from tonight's boards by our own numbers, in code, the same way the
    board prices them:
    * a Most Likely pick at the chance it shows;
    * any other prop at the slip's exact number;
    * a scorer off the touchdown model;
    * a side or total from the board's game card.

    The card shows the grade, our chance it all hits against what the
    payout needs, every leg ranked, any pair the parlay engine would
    never build, and the weakest leg with our likeliest pick in that
    game. A leg that isn't on our boards is called out and counted at its
    own price's break-even (the grade gets a *). The picture is stored
    nowhere. Nothing to run; it arrives with the next pull. To try it,
    upload any slip screenshot from your phone. To see the reads in the
    day's spend afterwards (read-only):
    ```
    cd /srv/qellys && sudo -u qellys python3 -m engine.askbot usage
    ```

    **Later the same day, round two** (Ethan: "use all the data we have
    with defense and offense … run the parlays and legs through our 2000
    time simulations"):
    * **Why we say X%** folds under every leg. It lists the board's own
      facts, and nothing is invented for the slip.
      * Props show: our projection and its range; his recent games
        against that number; his games against this defence; the defence
        card and what it did to our number; the other steps that moved
        it most; the game script; the matchup scan's read; his
        quarterback, teammates and measured teammate-out effects; his
        injury status and warnings; and what the books say with the
        margin out (the sharp book's number, and the field's across books
        at that number).
      * A seated Most Likely pick also shows the case it was picked on,
        our record on picks like it, the four checks and the scout's
        notes.
      * Scorers show the team's expected points, red-zone chances and
        goal-line work.
      * Sides and totals show our model's reasons, the books, Kalshi and
        Polymarket on the same bet at the same number, the move since
        the line opened, where the exchange money sits, and the game
        plan.
    * **The ticket, replayed 2,000 times**, the Sim Lab's count. Legs in
      one game win and lose together exactly as the parlay engine prices
      them. The card shows how many nights it cashed, how many legs
      landed on the rest, and the leg that most often broke a ticket
      that missed by one.
    * Two legs that can't both win (both sides of one line) now grade
      0% and F instead of a small number.
    * A seated pick shows its tier word ("Top pick"), not the board's
      internal key ("top"). A "Worth a look" pick is graded at the
      tier's real hit rate, the number its Most Likely card shows, not
      our model's higher one. The swap suggestion uses the same number.
    * Fixed while building this: in a low-total, close game (e.g. WAS by
      3.5 at 41.5) the favorite's game-script line read "favored in a
      shootout — everyone eats", and the game-plan page counted that as
      backing every over. It now reads "favored in a low-scoring, close
      game" and backs no side. Wording only; no number changes.

    Nothing to run for any of it.

    **Round three, the live line** (Ethan: "make sure we are also pulling
    live line for the picks that the user puts in the parlay checker", and
    "figure out what more we can add"):
    * **Every leg's price right now, at the slip's own number.** Each
      book's price, best first, including alternate numbers. Also the
      market's chance with the margin taken out, whether it beats the
      price on the slip, where the main line sits, and when that price
      was pulled. It comes from our latest paid pull, so no extra
      credits. The NFL re-prices through game day: at the touchpoints,
      three hours out, at inactives and in the last half hour.
    * **Once a leg's game is on**, it shows the score, the clock and his
      number so far (e.g. "Has 74 of 69.5"). That comes from the
      12-second scoreboard and box score the live loop already writes.
      An over past its number shows Won and an under past it shows Lost;
      finals settle. The card says where the ticket stands (won, in play,
      yet to start). A moneyline in play reads its live win chance. A
      prop in play gets no number, because our projection assumes a whole
      game. *(Changed 2026-10-13: props in play now get a live chance —
      step 38.)*
    * **Before kickoff the card also shows:**
      * where to place it: the parlay priced at each book that quotes
        every leg, against the slip;
      * the leg it's better without, when cutting one lifts the expected
        return;
      * legs that move together or pull apart, from the parlay engine;
      * alerts first: a Questionable player, or a prop no book is pricing.
    * **Your call, not built:** a fresh Odds API pull of just the slip's
      markets, for when our price is old. It costs one credit per market
      per game per upload; a 4-leg ticket over two games is about 3–4
      credits. It draws on the same daily budget that prices the board,
      so it could delay a board refresh. Say yes and give a daily cap if
      you want it.

    Nothing to run.

37. **A failed payment or a cancellation locks the account** (2026-10-12,
    Ethan: "It should lock them too the paywall screen"). What I found,
    then what changed:
    * **Cancelling already walled people, but only if Stripe's webhook got
      through.** If Bot Fight Mode ate it, the account stayed open for good.
    * **A failed payment never walled anyone.** `past_due` kept access
      "until the paid period ends". The date it read was the end of the
      new, unpaid month, so a failed card kept the whole month free.
    * **The page put the wall up only when it first loaded.** A tab left
      open kept working.

    Now:
    * **A failed payment walls at once.** The paywall says "Payment failed
      — your access is paused" and has an **Update card** button. That
      opens Stripe's billing page, where the customer changes the card
      and pays the open invoice. The payment that clears lets them back in.
    * **Buying a second plan over a failed one is refused.** The customer
      is told to update the card instead, so nobody is billed twice.
    * **A plan cancelled from the billing page keeps the days already paid
      for**, then walls the second its date passes. A plan cancelled
      straight away walls straight away.
    * **The site asks Stripe itself** when the webhook doesn't say:
      hourly for a paying account while it uses the site, each minute
      for a walled one, and every six hours for everyone.
    * **An open tab checks again** when you come back to it, and every
      five minutes.
    * **A late webhook can't undo a newer state.** A payment failure that
      arrives after the payment that fixed it is ignored.

    The box picks this up on its own (auto-pull and restart). The first
    re-read of every subscription runs at the restart. Three things to do:
    * **Check the webhook gets through:** Stripe → Developers → Webhooks →
      your endpoint → Send test webhook. It should say `200`. If it's
      blocked, Bot Fight Mode is on; docs/DEPLOY.md says how to turn it
      off.
    * **Check the Stripe settings this depends on:**
      * Settings → Billing → Customer portal: "Update payment methods" and
        "Invoice history" switched on. That's how a locked customer pays.
      * Settings → Billing → Subscriptions and emails: "Send emails when
        card payments fail" on, so Stripe emails them the fix as well.
    * **Your call: cancel at the end of the month, or at once?** It's the
      same portal page: Cancellations → "At the end of the billing period"
      (the default: they keep what they paid for) or "Immediately" (walled
      the moment they press it). The site handles either. Nothing to code.

    Read-only check that the re-read is running. It prints only statuses,
    counts and hours since the last read, no emails:
    ```
    cd /srv/qellys && sudo -u qellys python3 -c "import time; from engine import accounts as A, billing as B; c=A.connect(); B.init(c); n=time.time(); print([tuple(r) for r in c.execute('SELECT status, COUNT(*), SUM(checked_at IS NOT NULL), ROUND(MAX(?-checked_at)/3600.0,1) FROM subscriptions GROUP BY status', (n,))])"
    ```
    Each tuple is (status, accounts, accounts read from Stripe, hours since
    the oldest read). Within six hours of the restart, every status except
    `canceled` and `none` should have the third number equal to the second,
    and the last number under 6.

38. **The parlay checker: live chances, the hedge, a better number, and
    saved slips on the Live tab** (2026-10-13, Ethan: "the hedge
    calculator and better number and saving uploaded slips too moneys and
    live chances for props mid game ... for all sports"). All of it is in
    the graded card in Ask. It covers every league the checker grades:
    NFL, college, NBA, WNBA, NHL and MLB. UFC isn't in the checker,
    because its board stores only picks.
    * **A prop in play gets its live chance.** It's what he has so far
      against the share of the game left, starting at kickoff from the
      card's own number. Football, basketball and hockey use the
      scoreboard's clock. Baseball uses the existing live-prop model:
      inning, outs, his lineup spot, who is due up, and whether a pitcher
      is still in. Overtime gets no number. The ticket's "our chance for
      the rest" now counts props in play too.
    * **Hockey's live box score is new.** During NHL games the live loop
      now writes skaters' and goalies' lines to `live_nhl_box.json` from
      the league's own box score, the same parser settlement uses. It's
      cached as `nhl_live_*`, never as `nhl_box_*` (the name settlement
      reads), so a mid-game snapshot can't be graded as a final.
    * **Baseball's live box** now carries each hitter's lineup spot and
      whether each pitcher is on the mound.
    * **The hedge.** When one leg is left, the card shows the other side
      of that leg with our last price for it. Type the price your book
      shows and it works out:
      * the bet that locks a profit either way;
      * the bet that wins your stake back if the leg misses;
      * by our chance for the leg, what locking costs or adds.
      Before anything starts, it shows the same as a plan for the leg
      that kicks off last.
    * **A better number.** Where a book quotes the same bet at another
      number that our model rates better (e.g. Over 59.5 at +150 instead
      of 69.5 at −115), the leg says so, with what it does to the ticket.
      It compares numbers the way the card would print them, and the
      sharp book is never the price to take.
    * **Save to My Bets.** Saves the slip with its legs. The Live tab's
      new **Your saved slips** panel follows every saved slip in every
      league, leg by leg, once a minute while the tab is open. When the
      box score settles a slip, it's settled in My Bets (won, lost, or
      every leg pushed). If it won with a leg pushed, it's paid at the
      price without that leg, or left for you when we don't know that
      leg's price. The follow-up call (`/api/ask/track`) reads no picture,
      calls no AI and doesn't count as a question.
    * **Fixed on the way:** basketball, hockey and baseball props that
      aren't on Most Likely got no chance from the checker. Their boards
      write a range or an SD the checker couldn't read. They're priced
      now, at the board's own chance on its own number.

    Nothing to set; the box picks it up on its own. Two read-only checks:
    * **The measurement** (a few minutes). It replays the live chance on
      the 2023–2025 NFL seasons from the cached play-by-play. It stops at
      the end of Q1, halftime and the end of Q3, and scores the shipping
      model against the kickoff number. It also scores two other ideas,
      this game's pace and a half-and-half blend. It changes nothing.
      Paste back the tables:
      ```
      cd /srv/qellys && sudo -u qellys python3 -m engine.proplivefit
      ```
      Hockey shots on goal too, if the shots table is filled (it is if
      `ingest.py nhl --shots` ever ran):
      ```
      cd /srv/qellys && sudo -u qellys python3 -m engine.proplivefit --sport nhl
      ```
      If "blend" beats "ours" by much, the first half tells us something
      the model ignores. That's your call to change, not mine.
    * **During a hockey game, the new box file** (prints when it was
      written, each game, and how many player lines it has):
      ```
      cd /srv/qellys && sudo -u qellys python3 -c "import json; d=json.load(open('web/data/live_nhl_box.json')); print(d['generated_at'], [(g['away']+'@'+g['home'], g['state'], len(g['players'])) for g in d['games']])"
      ```

38b. **Your calls from step 38.**
    * **UFC in the checker?** Its board stores only our picks, not every
      fighter's line, so a fight leg reads "not on our board". Say if you
      want it added.
    * **The Live tab's own tracked picks** use the same baseball live
      model, and they had a bug I had fixed in the checker: when the
      other team was batting, they counted the batter at the plate as
      the next man up for our hitter's side, so every hitter's live
      chance read off the opposition's order for half of each inning.
      Done 2026-10-13 (Ethan: "add all of them"): the tracker now works
      out his side's next spot from its own plate appearances, with the
      checker's arithmetic shared (engine/mlb/liveprops.due_spot). The
      "PA left" on a tracked hitter follows his own lineup now. Nothing
      to run.

39. **A leg that isn't on our board gets our own read, and a weak leg
    gets better legs** (2026-10-13, Ethan on "Josh Allen Over 5.5 Carries
    — NOT ON OUR BOARD": "We can't just not give the user information on
    a prop since it's not on our board" and "we need too offer better
    legs too replace legs with if needed"). Both are in the graded card
    in Ask, for NFL, college, NBA, WNBA, NHL and MLB.
    * **Our read.** For a player prop no board carries, the checker runs
      the board's own model for that sport on it, from the history
      database:
      * football: the same engine as the board, with his games, last
        season as the anchor, the defence rated from the database, and
        the game card's spread, total and weather;
      * basketball: the minutes model;
      * hockey: ice time × his rate;
      * baseball: the park and the opposing starter.
      Then it asks the four Most Likely checks (model, matchup, market,
      record) and says the tier the pick would earn. It also reads the
      game script for that side and says why the board didn't carry it
      (for Josh Allen: the board doesn't build carries for quarterbacks).
      It's never journaled, posted or put on a board. A player with fewer
      than three games in that market still says "not on our board".
      A player the board's injury lists name as out, or whose props every
      book took down, gets no number. A questionable one keeps his number,
      and the card says he's listed. Since step 43 the NFL read also runs
      the build's lineup steps (a teammate at his position out, his QB
      out or benched) and his measured usage role. What it still can't
      see: the role-based injury effects off the weekly report (an elite
      corner out) and the depth chart's starter/backup flag. (I said
      earlier it was missing team pace and pass rate; the live board
      doesn't price those either — that layer only runs in the backtest.)
    * **Better legs.** A leg we call weak or against, or can't price,
      gets up to three swaps. First comes the same bet at a better
      number, then the board's own picks in that game. Each is priced
      exactly as a leg, and the ticket is re-run with it in. A swap is
      only named when it leaves the ticket better. It's never a bet
      already on the ticket, never a pair the parlay engine wouldn't
      build, and never for a game that's started.
    * **Two small wording fixes.** The summary now says how many legs
      were read off the board. A pair the parlay engine never builds now
      says "Our parlay engine never pairs these" instead of "These can't
      both win", unless they really can't both win.

    Nothing to set. One read-only check: our read on a prop against the
    live boards and the box's history, as the card would show it. It
    writes nothing; paste back the output:
    ```
    cd /srv/qellys && sudo -u qellys python3 -m engine.slipread nfl "Josh Allen" rush_att over 5.5 -130
    ```
    `"found": "read"` with a projection and the checks means it works.
    `"found": ""` means the database has under three of his games in that
    market, or two players fit the name.

39b. **Your calls from step 39.**
    * **Quarterback carries on the board itself?** The read prices them
      from his own games, but the board doesn't build a carries line for
      quarterbacks, so they never reach Most Likely. Adding them would
      need the market measured first (marketfit), as the other five were.
      Say if you want that run.
    * **The football matchup check.** It follows the board's rule: only
      the scan's lean on him counts. A quarterback's runs and most backup
      roles have no lean, so their tier tops out at "Strong". The defence
      card is still shown. Say if you want the model's own matchup step
      to count when the scan has nothing.

40. **Every open of the site checks with Stripe** (2026-10-13, Ethan:
    "every time a user opens the site or launches the site it should
    check too see if they are still subscribed"). Before this, opening
    the site asked our server, and the server only went to Stripe itself
    if its last read was over an hour old. A cancellation whose webhook
    got lost could keep someone in for up to an hour.
    * **Now an open goes to Stripe.** That covers loading the site,
      launching the installed app, signing in, and coming back to an open
      tab or app (a phone usually resumes the app rather than reloading
      it). At most once a minute per account, so a reload loop can't
      hammer Stripe.
    * **The five-minute check on an open tab** still answers from our
      stored copy. Six-hourly sweep unchanged.
    * **It works both ways.** A tab that lapsed while you were away
      reloads onto the paywall. A walled tab whose owner paid or fixed
      their card somewhere else reloads into the site.

    Nothing to set; the box picks it up on its own. Read-only check. It
    prints one number, the seconds since the newest Stripe read of any
    subscription, and no emails:
    ```
    cd /srv/qellys && sudo -u qellys python3 -c "import time; from engine import accounts as A, billing as B; c=A.connect(); B.init(c); print(c.execute('SELECT ROUND(?-MAX(checked_at)) FROM subscriptions', (time.time(),)).fetchone()[0])"
    ```
    Open the site on a subscribed account, then run it. It should print
    under 60. `None` means no subscription has been read from Stripe yet.

41. **Is the off-board read honest? A replay on past seasons**
    (2026-10-13, Ethan: "add all of them"). The parlay checker's "ours
    88%" on a leg no board carries (step 39) has only been checked on
    made-up data. This replays the same arithmetic on seasons already
    played, as of each game (his games before it, the defence rated on
    the weeks before it, last season as the anchor, the game's own
    spread, total and weather), prices every prop-sized role at a
    book-like line (his trailing average to the half below) and at four
    numbers around the read's projection, and reports what landed. It's
    a report only: nothing is tuned, saved or changed, and it writes
    nothing to the database.

    Run it on the box (a few minutes for three NFL seasons; it prints
    "N reads…" as it goes) and paste back the tables:
    ```
    cd /srv/qellys && sudo -u qellys python3 -m engine.slipreadfit --sport nfl --seasons 2023 2024 2025
    ```
    College, the last two seasons, capped so it finishes in minutes:
    ```
    cd /srv/qellys && sudo -u qellys python3 -m engine.slipreadfit --sport cfb --seasons 2024 2025 --limit 3000
    ```
    How to read it: "ours" is the read; "last8" is a stand-in anyone
    could make (his last eight games as a bell curve). Ours should beat
    last8 on Brier (lower is better) in every market. The calibration
    line is the real test: "60%-70%: said 65%, landed 64% of 812" is
    honest; "said 75%, landed 58%" means the read overstates that band.
    If a market reads like that, say so and I'll look at why, in that
    market, before touching anything. Basketball, hockey and baseball
    reads aren't replayed yet; their models keep their own records.

42. **The cash-out check** (2026-10-13, Ethan: "add all of them"). On a
    graded parlay in Ask, and on every saved slip the Live tab follows,
    a box under the hedge: type the cash-out your book is offering and
    it's held to what the ticket is worth by our numbers — the ticket's
    return if the rest win (stake × payout, a pushed leg taken out)
    times our chance for the rest (live once the games are on, pre-game
    before). It says take, hold or about even (within 3% of fair), what
    the book keeps, and what holding risks ("48% to collect $36.00 and
    52% to collect nothing"). No box on a lost or won ticket, or while
    a leg in play has no live number yet — never a guess. Nothing to
    set, nothing to run; it's in the card.

43. **The NFL off-board read sees who plays around him and how much he's
    used** (2026-10-13, Ethan: "add all of them"). The read in step 39
    priced a leg without three things the board's own number has. Now
    it runs them, the same way the build does:
    * **A teammate at his position ruled out** — the depth order is
      built from our database (targets and carries, as it was first
      measured) and the board's injury lists mark who's out tonight; the
      measured step moves his number and the card says "Around him:
      RB BUF out at RB". A questionable teammate moves nothing and the
      card says what happens if he sits.
    * **His quarterback out or benched** — read off the QB-change card
      the board already publishes on the game; receivers take the
      measured step (×0.90 receiving yards behind a downgrade).
    * **His measured usage role** — the usage bridge (recent
      opportunities × season efficiency) weighs against a thin log the
      same as on the board.
    The replay in step 41 sees the depth order and the role as of each
    week; no injury report is kept for past games, so nobody is ever out
    in a replay. College isn't wired yet (its lineup step is measured
    separately); say if you want it next. Nothing to set, nothing to run.
    If the box check in step 39 prints `"mate_card"` or `"qb_card"` on a
    read whose teammate or QB is out that day, it's working.

44. **A saved slip down to its last leg says so, and can email you**
    (2026-10-13, Ethan: "add all of them"). The box watches every
    member's saved slips itself — My Bets syncs to the account store, so
    it has them with the Live tab closed — once a minute (`slip watch`
    on the launcher's log), grades each one the way the Live tab does,
    and the first time a ticket is down to the one leg that decides it:
    * the Live tab's card leads with "Last leg. KC moneyline decides it
      — the hedge and the cash-out check are below", and the phone
      buzzes once per slip (the mark rides on the My Bets entry);
    * a member who ticked "Email me when a saved slip is down to its
      last leg" (the switch sits above the saved slips on the Live tab)
      gets one email: the ticket, the leg and where it stands, our
      chance for the rest, the hedge's lock-it and stake-back numbers,
      a link to the Live tab, and a one-click unsubscribe that turns off
      only that email.
    One email per slip ever, 40 a day for the whole box, only to a member
    entitled at that moment (the live chance and the hedge are the paid
    half), and only when mail is set up — the same Resend key or Gmail
    the password resets use (`sudo ./deploy/setenv.sh`; nothing to add).
    On a site with no relay the switch isn't offered and the Live tab
    says so. Box check, after a night with a saved slip open:
    ```
    journalctl -u qellys --since "12 hours ago" --no-pager | grep "slip watch"
    cd /srv/qellys && sudo -u qellys python3 -c "from engine import accounts as A; c = A.connect(); print([tuple(r) for r in c.execute('SELECT user_id, bet_id, fired_at, mailed FROM slip_alerts')])"
    ```
    The first prints a line for each minute something fired ("1 saved
    slip(s) down to the last leg, 1 emailed"; a failed send says so with
    the error's kind); the second lists every alert noted (`mailed` 1 =
    the email went). Nothing to set.

45. **The MLB profit calendar stops at September** (2026-10-13, Ethan:
    "the mlb profit calander isn't updating, it's stuck on September").
    The calendar draws MLB edge bets once they settle, and it opened on
    the latest month that had one. September was that month, so no MLB
    edge bet has settled since September 30. The page itself was drawing
    what the record holds; the question is which step stopped after that
    day, and I can't see the box's journal from here. Two changes:
    * **The calendar opens on this month now**, every league, and a month
      with nothing settled says why. "No edge bet has settled in October
      yet. 3 are still waiting on a result, the oldest from Oct 1" means
      bets are being placed and not graded. "The last one was placed
      Sep 30" means the board stopped placing them. Your phone shows
      which one as soon as the box pulls this.
    * **A box check that names the step** (read-only, paste all of it):
      ```
      cd /srv/qellys && sudo -u qellys python3 mlbprobe.py
      ```
      Its JOURNAL lines give each of the last three weeks: the MLB edge
      bets journaled that day and how they stand, beside the finals and
      stat lines on file to settle them. Then the last edge bet, what
      the record file says, and the last MLB build's lines about its odds
      and its journal.
      * Edge rows stop on a day: the board stopped journaling. The BUILD
        lines say why. "matched 0 props" means it had no real prices,
        "Bet journal skipped" means the journal failed, and a header
        reading `exit -9` means the build was cut off.
      * Edge rows keep coming but stay open: settling stopped. "finals"
        and "stat lines" say whether the playoff results ever reached the
        database.
      * Edge rows settle but the calendar still stops: the record file
        isn't being written. The RECORD line says when it last was.

46. **Two profit calendars: Edge bets and Most Likely, every league**
    (2026-10-13, Ethan: "There should be a profit calendar for both edge
    bets and most likely bets for all sports"). The Record page's
    calendar has a switch under its title, **Edge bets | Most Likely**,
    on every league and on All bets.
    * **Most Likely** draws the same picks its record counts: the Most
      Likely list and the one board, each pick once, so a pick on both is
      one cell entry. Its months, its month line, its empty-month sentence
      ("No Most Likely pick has settled in October yet...") and its day
      taps are its own.
    * **Two fixes on the edge side.** A tapped day's list still included
      the staked Most Likely bets after the cells moved to edge picks
      only (2026-09-30), so a cell could read 3-1 over a list of five. It
      lists only edge picks now. The "still waiting on a result" count
      from step 45 counts only edge picks too.
    Nothing to set or run; it arrives with the next pull. To see it: Record
    page, pick a league, tap **Most Likely** above the calendar.

47. **Bets settle minutes after the final, every league** (2026-10-13,
    Ethan: "bets are taking way too long to settle … It should not take
    a day for all bets to settle"). Nothing to set; it arrives with the
    next pull. What held a finished game's bets open, and what changed:
    * **The settle ran once per board refresh.** That was a sweep of
      every board, a quarter of an hour or more on a busy night. It now
      has its own clock (every 5 minutes, whatever the boards are doing).
      A game going **final on a live scoreboard starts a pass within the
      minute.**
    * **Seven NFL markets waited for the next morning's file.** Rush
      attempts, pass + rush yards, rush + rec yards, kicker points, field
      goals, tackles + assists, and a quarterback's anytime touchdown.
      The same-night box score only wrote the older markets. It writes
      every board market now, kicker and defender lines included. Any
      open prop starts the pass, not just six markets.
    * **Points + rebounds + assists (NBA, WNBA) never settled.** The
      board priced and journaled it, but no feed stored a combined line.
      It grades off the three stats now, and a game missing one of them
      stays open rather than grading a short sum. Any PRA bet still open
      from the WNBA season grades on the next pass.
    * **The NBA's "is it over" was a 6-hour-old copy, the NHL's 30
      minutes.** A game that tipped and isn't final in the copy on disk
      is now asked about again (NBA every 5 minutes, NHL every 2). An NBA
      box cached before the buzzer is read again, and nothing is stored
      from a box that says the game is still on.
    * **Fight picks graded only when the UFC board rebuilt.** They're on
      the settle clock now. A bout from the last two days with no winner
      is read fresh first. Before, a copy saved before the bell could
      read as "no winner" after midnight UTC, which the ledger treats as
      a draw and voids.
    * **Desk tickets on tonight's game were first asked about
      tomorrow.** The exchange is now asked about today's events too,
      every 15 minutes (was hourly).
    * **What can still take until morning:** an NFL player missing from
      the box score entirely. He either sat (void) or played without a
      stat (graded at zero), and only the official snap file tells those
      apart. MLB, NBA, WNBA, NHL and college have no such wait.
    * **Sportsbooks' own results:** there's no way to read them without
      logging into accounts, which the site never does. Books grade off
      the same official box scores this pulls, so the answer is the same
      one, minutes after the final.
    To check it, run J at the top of this file.

48. **A side or a total no board prices gets our number and our data**
    (2026-10-13, Ethan, on a slip whose Brewers moneyline and Brewers @
    Dodgers under 7.5 both read "NOT ON OUR BOARD": "we use our data to
    explain if it's a good pick or not"). Nothing to run; it arrives with
    the next pull. A moneyline, spread or total the boards don't price
    (a game on another day's slate, a total at a different number, a
    game priced before any book posted) now runs that league's own game
    model:
    * **Baseball, NFL, college:** team ratings from this season's finals.
      Baseball adds the two starters off the board's game card when it
      has the game, and says "league-average arms" when it doesn't.
    * **Hockey:** the goals model the NHL board uses. It prices the puck
      line at 1.5 goals only and says so for any other number.
    * **NBA/WNBA:** moneylines and spreads use the futures simulation's
      game curve. Nothing of ours projects a basketball total, so a total
      gets the data and no number.
    * **Held to the market** like every game line on the boards. The
      card shows our model's own number, the market's, and what's left
      after the measured haircut. A big gap is flagged as more likely our
      rating's error than an edge.
    * **The data under "Why we say":** each team's last 10, their
      meetings this season, how often each side's games went over or
      under the leg's number, and the board's own line when it prices a
      different one.
    To see it: Ask, the paperclip, **Grade a parlay screenshot**, any slip
    with a game line from tomorrow's slate or a total off the posted
    number. The leg reads "Our read — not on our board".

49. **A carry chart for every NFL and college runner** (2026-10-13,
    Ethan, with the NFL's Next Gen Stats carry chart for Josh Allen at
    the Rams: "a carry chart exactly in the screenshot for every player
    ... for past games and ... an 'average' carry chart showing where
    they run"). K fills it now; otherwise the nightly fills it.
    * **Where:** any NFL or college player's page (search him on the
      Players tab), the **Carry chart** button beside "History vs a
      team". It shows for anyone with a rushing log.
    * **By game:** any game this season or last. Each carry is a line
      from the backfield through the hole the NFL's play-by-play records
      (left end to right end) to where it ended: red for a loss, orange
      for 0-4 yards, green for 5+ or a touchdown, a ring on a touchdown
      or a lost fumble. Under it: carries, yards, yards a carry, TDs, and
      RYOE where the NFL publishes it (running backs with 10+ carries in
      a game; first downs otherwise), then every carry listed with the
      quarter, clock, down and distance, field position and hole. Tap a
      line or a row to pick one out.
    * **Season, "where he runs":** every carry faint, plus one bold ray
      per hole, as thick as his share of carries there and as long as
      his average gain there, labelled with both. Tables for the holes,
      designed runs vs scrambles (quarterbacks), downs and field
      position, and the NGS season line for backs (RYOE, 8+ in the box,
      time to the line).
    * **What it can't show, and says so on the page:** the league's
      tracked running paths aren't published, so the bend into the hole
      is drawn, not tracked; the hole and the yards are the record.
      College play-by-play records no hole at all, so a college game's
      carries are spread across the field in the order they happened and
      the season view runs shortest to longest. A college fumble reads
      "fumbled" (the file doesn't say who recovered it), and college
      shows the quarter but not the clock (the file's clock is often the
      drive's, not the play's).
    * **Kept current:** an NFL game lands the morning after nflverse
      publishes it — the nightly now also reads the play-by-play while a
      finished game has no chart, so Thursday and Monday games don't
      wait for Tuesday. College every night in season. Last season once.

50. **A route chart for every NFL receiver** (2026-10-13, Ethan, with the
    NFL's Next Gen Stats route chart for Sam LaPorta against the
    Cardinals: "We can add route charts for wr and shit too. And if we
    don't have access too this info then we should be able too make it").
    K fills it now; otherwise the nightly fills it.
    * **Where:** any NFL player's page, the **Route chart** button beside
      the carry chart's. It shows for anyone with a receiving log, backs
      and tight ends included. Not college: the college play file names
      the target but has no air yards and no side of the field.
    * **By game:** every pass thrown to him, this season or last. How far
      past the line it went (air yards) and which third of the field
      (left, middle, right) are the play-by-play's record; the run after
      the catch is green, as long as the record says; a ring on a
      touchdown, a dashed line on an incompletion, a red cross on an
      interception. Under it: targets-catches, yards, TDs, yards after
      the catch, average depth of target, and separation where the NFL
      publishes it (5+ targets in a game; first downs otherwise), then
      every target listed with the quarter, clock, down and distance,
      field position, depth and side, and FTN's charting words (screen,
      play action, contested, drop, not catchable, a catch he made on his
      own). Checked against the screenshot: LaPorta's week 5 reads 5-5,
      88 yards, 44 after the catch, a touchdown.
    * **The routes:** for last season and before, each target is drawn in
      the shape of the route the league charted for it (go, slant, out,
      curl, dig, post, corner, drag, screen, swing, wheel, angle — from
      nflverse's participation file), ending where the ball arrived, with
      man or zone and the coverage shell on the row. **This season
      nflverse hasn't published the route charting** (it comes out a
      season behind), so 2026 targets are drawn as the throw, from the
      pocket. We measured guessing the route from the public 2026 data:
      the likeliest route for a target's depth and side matched the
      league's charting 43% of the time, so we don't guess. When nflverse
      publishes 2026's file, the nightly picks the routes up by itself.
    * **Season, "where he's thrown to":** the field in thirds and depth
      bands (behind the line, 0-9, 10-19, 20+), each shaded by his share
      of targets and labelled with catches/targets, every target a dot.
      Tables by depth, by third, by route, against man and zone, by
      coverage shell (charted seasons) and by down; catch rate, yards a
      target, contested catches won and drops; the NGS season line
      (separation, cushion, intended air yards, share of the team's air
      yards, yards after the catch over expected).
    * **What it can't show, and says so on the page:** the league's
      tracked paths aren't published, so a route's stem and break are
      drawn, not tracked, and where inside a third a ball arrived is
      spread so no two overlap; the run after the catch is drawn straight
      upfield.
    * **Kept current:** the same nightly play-by-play read as the carry
      chart (and the same "a finished game has no chart" check), the
      receiving tracking file every night, last season once.


51. **Can the new chart data make better picks? Measured — no, not on
    its own** (2026-10-13, Ethan: "is there more features or tools we
    can add to get more accurate data and able to use this data to make
    better pics"). Nothing to run. Three matchups the charts make were
    added to the scan's measurement (`engine/scanfit`) and measured on
    2022-2025 the way every scan reason is — on top of the player's form
    and the defence-versus-position step the board already takes, each
    season held out in turn:
    * **run direction** — a back's inside/outside mix against where the
      defence gives up yards: t 0.2, held-out gain below zero;
    * **side of the field** — a receiver's left/middle/right mix against
      the side a defence gives up: t at most 0.9, below zero every way;
    * **yards after the catch** — a catch-and-run receiver against a
      defence that allows yards after the catch: t 0.9, below zero.
    The three that waited on the box (target depth, yards after contact,
    the pocket split) failed too, and the six measured on 2026-09-24
    re-ran to within noise. So the charts stay what they are: the picture
    of what happened, on the page, with no number reading them. Where our
    own record points instead is the closing line: since the closes were
    repaired, Most Likely picks lose about 2 points to their close and
    the Edge picks beat theirs by about 2½ (same-book check, 2026-10-04).
    L re-reads the picks that lost the close on the repaired closes; if
    the market had news we did not, a last look before kickoff is the fix.

52. **The charts fill the day they are empty, not the next day**
    (2026-10-13, Ethan: "Also the charts aren't working for any
    players"). Nothing to run; K shows it. The charts themselves were
    fine — their tables were empty. Every carry and target is read by the
    daily chores, which run once a calendar day, and the box had already
    run that day's when the charts landed (16:55 and 17:20 UTC), so every
    player's chart said "No carries on file" and would have until the
    next day's. Now:
    * **Every cycle** the box asks whether a chart table is empty for a
      season it has played (this one or last, NFL carries and targets,
      college carries) — a few lookups — and when one is, starts the
      fill in the background (`engine/chartfill`, its log in
      `data/cache/weekly_chartfill.log`). A failed read (GitHub down) is
      tried again two hours later, not every cycle. Measured here on the
      real files: both NFL seasons in about 6 seconds once downloaded.
    * **While it fills**, the chart says so — "Carry charts are still
      being filled… check back shortly" — instead of "No carries on
      file" for a player who has hundreds. That shows only while nobody
      in the league has a row yet.
    * **Lighter on memory:** the play-by-play reader now splits the file
      into lines instead of holding it in a text buffer; the same rows,
      checked identical on every season 2021-2026, at 214 MB a season
      instead of 490 MB. The nightly read uses it too, inside the 1600 MB
      the service is allowed.

53. **College receivers thrown at who caught nothing are on the record**
    (2026-10-13, Ethan: "We worked so hard on nfl so ik CFB and mlb and
    nba and ufc is missing stuff"). M re-reads last season and shows it.
    * **What was missing:** college box scores list only players with a
      stat, so a receiver thrown at four times who caught none had no
      line at all — his history was "games he caught one", which runs
      high, and a bet on him that night was voided.
    * **What the data now has:** the college play file names the
      receiver a pass was thrown at on 78% of 2025's incompletions and
      92% of 2026's (21% in 2024, which is when the college model
      decided it had no targets). A named target proves he was thrown
      at, so that game is now a 0 for catches, yards and touchdowns.
    * **Measured** (`cfbtargetfit.py`, on the board's own players, with
      the board's own form): the error falls in both seasons for catches
      and yards — 2026 catches −1.8%, yards −1.0%; 2025 −0.3% each — and
      the old upward lean mostly goes (2026 catches +0.13 → 0.00). The
      touchdown board is unchanged (Brier within 0.0001). The bar was set
      before the run: both seasons, both markets.
    * **Not stored:** a target COUNT. The feed leaves some incompletions
      unnamed (22% in 2025), so a count would be short; nothing shows a
      college target number.
    * **The voids:** grading is unchanged — a college receiver with no
      box-score line is still voided minutes after the final. M counts
      how many past voids the play file now shows were thrown at, and
      what they would have paid. Your call in H.
    * **Lighter:** the college file reader now splits lines like the
      NFL one (same rows, checked on 2024-2026).

54. **The NBA board knows who plays where, and who is hurt** (2026-10-13,
    same ask). N checks both reads on the box. Two things the NFL board
    has had for weeks that the basketball build never did:
    * **Where he plays now.** The logs file a man under the club he
      played for, so on opening night every summer move was still under
      his old team — projected for a game he is not in, and, because the
      prop named no team, priced off whichever game the books named him
      in. The build now reads the clubs' current rosters (the Rosters
      page's own ESPN feed, cached six hours). A man the roster places
      keeps only his games for that club — the model doc's own reset
      rule, "a trade resets the sample" — so a new arrival has no prop
      until he has played three games for his new club, the floor every
      prop already has. A name the roster does not carry keeps his old
      team (a spelling the two feeds disagree on never costs a man his
      board), a club code the league map does not know moves nobody, and
      if the roster cannot be read the board is exactly what it was.
      Every prop now names its team, so the odds attach refuses a price
      from a game his team is not in, and counts it in the odds note.
    * **Who is hurt.** ESPN's injury board — fetched for the Injuries page
      all along, read by no build; the model doc calls it "the one gap
      worth money". Out, doubtful or suspended: grade D, no bet, and the
      card says "listed Out — not expected to play"; a posted Most Likely
      pick comes down. Day-to-day, questionable or probable: the number
      stands and the bet waits — "held until the lineup confirms" on the
      Edge board, and Most Likely holds it, as it does for the NFL and
      the NHL.
    * **A teammate's card says who is out** (a fresh absence: he played
      in one of the club's last three games — one out since February is
      already in every teammate's recent games), his minutes, and — from
      our own logs (`engine/nba/onoff`) — this player's share of the team's
      points, rebounds, assists or threes in the games he sat, counted
      only from his first game for the club and only with three or more
      such games. Evidence only: the minutes model has a slot for the
      minutes a vacancy opens and nothing fills it yet, because moving
      the number is a pricing change that has to be measured first.
    * The WNBA board runs the same code; its season is over.

55. **Should a teammate's number move when a regular sits? Measured on
    the box** (2026-10-13, same ask). O runs it. The books raise a
    teammate's line the moment a star is ruled out; the NBA minutes model
    has a slot for the minutes a vacancy opens and nothing has ever
    filled it, so our number for that teammate does not move. If it runs
    low in those games, the card leans under on exactly the lines the
    books just raised — and no hold catches it, because the hold is on
    the star. `nbavacancy.py` replays every stored season with the
    board's own projection (player memory held at 1.0, since it was
    fitted on later bets) and compares teammates' actual minutes and
    stats with it, per team-game, in games a 24-minute regular had just
    started missing versus ordinary ones. **The bar, written before the
    first run:** every season, minutes at least +1.0 above the number
    and points above it, both with the interval clear of zero. Meeting it
    earns a candidate rule a held-out test; nothing moves from this run.

56. **Every UFC card says where its line opened** (2026-10-13, same ask).
    P shows it. The model doc names line movement one of "the two
    upgrades worth money" in MMA, and the UFC build has stored every
    book's price on every paid pull since 2026-08-10 — read by nothing
    until today. Each pick and pass card now carries one line: "Line
    opened A −150 → −175 · B +130 → +155. The market has moved 3.2 points
    toward A (2 pulls). Shown, not priced." Only this bout's rows count
    (not his previous fight's, nothing after the start); one pull is a
    line, not a move, and says nothing. The grade's movement piece stays
    empty until P's reads say a move carries something the close does
    not. The page code grew 0.05 KB gzipped, which took the first-visit
    budget for `app.js` from 494 to 495 KB (the test file records why).

57. **The chart's X is below the status bar, and stays in reach**
    (2026-10-13, Ethan, a screenshot of McCaffrey's route chart: "fix
    this issue where the X button is stuck up top in the bar so I can't
    even click it"). Nothing to run — open any carry or route chart on
    your phone. The chart sheet started at the very top of the screen,
    under the clock and battery, where iOS keeps the taps; it now starts
    below the status bar, its last rows clear the home bar, and the X
    stays pinned top-right while the chart scrolls under it. Checked in
    Chromium with an iPhone's 59px status bar emulated: before, the X sat
    at 10px (under the bar); after, at 69px, still on screen after
    scrolling 900px, and one tap closes the chart. A desktop looks as it
    did. The page fetches styles network-first, so the fix arrives on the
    next open after the box pulls.

58. **Every chart shows the player's face** (2026-10-13, Ethan: "Make
    sure we are showing headshots in this new page"). Q fills and
    checks it. Two things left the chart's face ring empty. The chart
    looked a player's photo up by the name its play file uses, and the
    photos are stored under the roster file's spelling: "Kenny Gainwell"
    against "Kenneth Gainwell", "D.J. Moore" against "DJ Moore", and
    anyone on last season's roster but not this one. On a copy of the
    chart tables here, 637 of 685 NFL chart players had a photo that
    way. Every row carries the league's own player id, so the daily face
    pass now gives each chart player without a photo the one the roster
    file has for his id (this season's file first, then his last
    season's): 685 of 685. A name two different players share gets none
    (initials beat somebody else's face). College photos are ESPN's
    address built from the player's id, for every player whether ESPN
    has a picture of him or not, so some never load. The page now draws
    the player's initials, in his team's colour, under every photo. A
    photo that loads covers them. One that fails is followed by the
    full-size copy, then the photo the player's page was showing, and
    when none loads the initials stay. Nothing is left as an empty ring
    or a broken image. The chart reads a newly filled photo at once
    rather than after the six-hour face cache. Nothing to run but Q;
    open any chart. One test pin changed:
    `tests/test_a_carry_chart_for_every_runner.py` names the chart
    door's call, which now hands over the face.

59. **College receivers thrown at are graded, not voided** (2026-10-13,
    your call in H: "Also add both from my calls, the CFB and nba things").
    R checks it. Since 2026-09-14 a college player with no line in a final
    box score has had his prop voided, because the box lists only players
    with a stat. Now a bet in receptions, receiving yards, receiving
    touchdowns or anytime touchdown waits for the play file. If the file
    names him as thrown at, he played, and the bet is graded at zero, the
    way the book grades it: an over lost, an under won. If the file has
    his game and not him, the bet is voided as before. If the file has not
    reached his game in five days, the old rule stands. Every other
    college market still voids off the box score. Nothing settled before
    is touched: a void is never re-graded. Four test fixtures changed in
    `tests/test_absent_player_settles.py` (three) and
    `tests/test_cfbroster.py` (one). Each filed its team's rows as
    box-score rows and expected a receiving bet voided off them. They now
    file the play file's rows, so the void they test still happens. The
    wait itself is tested in
    `tests/test_a_college_receiver_thrown_at_is_graded.py`.

60. **The NBA prices points + rebounds, points + assists and rebounds +
    assists** (2026-10-13, your call in H). S checks it. All three are
    built like PRA: from columns the NBA ingest already stores, priced by
    the same pipeline, graded by adding up the parts, and named on the
    card, the shelves, the live tracker and the parlay checker. Each
    one's spread starts from a stated value (worked out the way PRA's
    0.24 works out) and is measured from the league's own logs at every
    build, as every other stat's is. The NBA's odds pull buys them: 16
    credits an event instead of 13. The WNBA's request is unchanged, and
    no alternate ladders were bought for them. Like PRA they are on the
    Edge board, not Most Likely: the weekly walk that earns a market its
    shelf cannot read a summed market yet (the new call in H). Three test
    pins changed: `tests/test_wnba.py` said the WNBA buys the NBA's exact
    markets, and `tests/test_hoops_ladder.py` said every NBA market has a
    ladder. Both now say so for the five shared markets and name the
    three NBA-only combos. `tests/test_alt_lines.py` said both leagues
    cost 13 credits an event; it now says NBA 16, WNBA 13, and still
    checks each price equals what the league's request asks for.

61. **Every football pick's page draws his chart in place** (2026-10-13,
    you: "We should show the route checker on the most likely bets as
    well like when you click on the player in the most likely bets it
    will automatically show the charts in that area with all the other
    info"). T checks it. Every door to a football pick (a Most Likely row
    or card, an Edge pick, a Live bet, a read on the game page) lands on
    the pick page, and the chart is drawn there after Form, with no tap:
    his targets for receptions and receiving yards, his runs for rushing
    yards, carries and a quarterback's passing plus rushing yards, and a
    Routes | Carries switch for rush + rec yards and anytime touchdowns,
    his own first. College draws carries only; the college play file has
    no air yards or side of the field. The player page's searched card
    draws it first under the card, and every football leg in Ask's
    parlay checker has Route chart / Carry chart buttons. On a pick page
    the long lists (every target, the season's splits, how it's drawn)
    fold under the chart, and on a wide screen the field sits beside its
    numbers. The chart is asked for as it nears the screen, kept ten
    minutes, and the page's refresh every minute leaves it as you left
    it (the game you picked, what you opened). app.js grew 0.37 KB, inside
    its 495 KB budget. No test was changed;
    `tests/test_the_pick_page_draws_his_chart.py` is new.

62. **A player's chart leads with what he does** (2026-10-13, you: "we
    are showing only receptions for RBs and only carries for WR and TE").
    T checks it. Step 61 picked the chart from the bet, so a back's
    receptions pick drew only where he is thrown to. Now both of his
    charts are asked for at once and the one he does more of this season
    leads (his carries against the passes thrown to him, read off the
    numbers, so a missing position can't flip it). The other is a tap away
    on a `Carries | Targets` switch that shows both counts, but only when
    he has 3+ of it in the same season: a receiver's two jet sweeps are
    not offered. A quarterback has his runs. College has no route chart,
    so a college receiver or tight end gets a chart only on a rushing bet.
    The parlay checker's football legs now have one "His charts" button
    that opens the same way. Checked in Chromium on real players: Saquon
    Barkley's receptions pick opens on his carries (36, Targets 7); Gibbs
    on carries (105 to 34); St. Brown and LaPorta on routes with no
    switch; Hurts on his runs. Two pins changed in my own
    `tests/test_the_pick_page_draws_his_chart.py` from step 61: the
    chart-per-market check now checks the charts each player can have,
    and the parlay door check expects the one "His charts" door.

63. **A quarterback's pick draws every throw he made** (2026-10-13, you:
    "Yes do all of them"; the first of the charts on the list). U checks
    it. A new table, `passes`, holds every dropback that ended in a throw,
    a spike or a sack, off the same NFL play-by-play the carry and route
    charts read (one read feeds all three, nightly and in the catch-up):
    air yards and the third of the field, complete or not and to whom,
    the yards after the catch, touchdowns, interceptions, a hit on him,
    and FTN's charting (play action, screen, out of the pocket, a
    throwaway, a ball that should have been picked, a drop, a blitz). The
    league's Next Gen Stats passing file (time to throw, completion over
    expected) is stored beside it, as published. Checked against the
    box score before any of it was written: Josh Allen's week 5 at the
    Rams is 19-12-210, a touchdown, an interception and one sack for 8 in
    the play-by-play, exactly nflverse's weekly line. A spiked ball counts
    as an incomplete attempt, as the box score counts it, and isn't drawn.
    The chart reads like the route chart: each game's throws from the
    pocket, the season's share of his attempts by depth and third, every
    dropback listed, and splits (depth, third, kept clean / hit /
    blitzed / play action, down, who he threw to). A quarterback's own
    chart is his throws whatever the bet, with his runs on the switch;
    passing bets now have a chart slot on the pick page and a "His
    charts" door in the parlay checker. Every chart from here on goes
    through one door, `/api/players/chart?kind=…` (engine/charts.py); the
    carry and route charts keep theirs. Pins changed and told to you: the
    chart filler's test now owes the passing table beside the other two
    (`tests/test_the_charts_fill_themselves.py`: the owed lists, the fill
    message and its log line); my own `tests/test_the_pick_page_draws_his_chart.py`
    now gives a quarterback `Passes | Carries` and a passing bet a slot;
    `tests/test_maintenance.py` stubs the passing chart's reads beside the
    route chart's (added, nothing loosened). New:
    `tests/test_a_passing_chart_for_every_passer.py`.

64. **A college receiver's pick draws every pass thrown his way** (2026-10-13,
    you: "Can we do the route tracker for CFB?"). V checks it. The college
    play file has no air yards and no side of the field, so there is no
    route to draw; what it does have since 2025 is the receiver it was
    thrown at on most incompletions (78% of 2025's, 92% of 2026's, against
    21-45% before), beside every catch, its yards, the down and the yards
    to the goal. So college targets are stored from 2025 on, in the same
    nightly read as the college logs and carries, and drawn as a Target
    chart: each catch straight upfield as long as its yards, each miss a
    ring at the line, a game in throw order and the season shortest to
    longest, with splits by down and field position. A catch lands on the
    man who caught it even when the file swaps the passer's and the
    receiver's names (the logs' own rule), so his catches and yards on the
    chart are his logged receptions and yards exactly; checked on every
    2025 game the logs keep (6,419 player-games, no difference). The file
    never names the receiver on an interception, so a pick is not on his
    chart, and the note under it says so. ALSO FIXED: the college logs drop
    a week whose scoring plays the file lost (2025 weeks 1 and 10 to 16),
    but the college carry chart was still drawing those games from the
    same file with their touchdowns missing. Both college charts now keep
    only the games the logs keep, and the box clears the rows it stored
    for the dropped ones on its next read. A college receiver now leads
    with his targets and a back with his carries, as in the NFL, and the
    parlay checker's college legs get the "His charts" door. Pins changed
    and told to you: `tests/test_a_route_chart_for_every_receiver.py` said
    the route door refuses college; it now says college waits for its own
    table (and the test is renamed to say both footballs). The chart
    filler's test owes the college targets table and its log line reads
    "7 carries, 0 targets". My own `tests/test_the_pick_page_draws_his_chart.py`
    now gives college players both charts and a college receiving bet a
    slot and door. New: `tests/test_a_target_chart_for_every_college_receiver.py`.
65. **A baseball pick draws his hit tracker or his pitch chart** (2026-10-13,
    you: "Can we do a hit tracker for mlb?" ... "Yes do all of them"). W
    checks it. MLB's free play-by-play, the same feed the nightly already
    reads for velocity and CSW, carries every plate appearance (batter,
    his side, pitcher, his hand, the result, the runs driven in) and, on a
    ball in play, the league's own exit velocity, launch angle, distance,
    batted-ball type and where it landed; and every pitch (type, speed,
    where it crossed the plate, the umpire's call). Two new tables hold it:
    `mlb_pa`, one row per plate appearance, and `mlb_pitches`, one row per
    pitch (ids only, so a season stays near 60 MB). The nightly reads
    yesterday's finals and 400 older ones a night, newest first, until
    the season is in; the chart filler (step 52) reads the first 400 the
    moment it sees the tables empty. The backfill keeps no copy of an
    older game's play-by-play in data/cache (a season of them would be
    about 1.5 GB sitting there for a month); yesterday's games keep theirs,
    as before, for the nightly's velocity reads. A hitter's pick draws his Hit
    tracker: one game's balls in play on the field with every plate
    appearance listed (a walk or a strikeout has no ball in play: listed,
    not drawn), or the season with the share he pulled, hit up the middle
    and went the other way, his hard-hit rate (95+ mph, the league's
    line), sweet-spot rate (8-32 degrees), and splits by batted-ball type,
    direction and pitcher's hand. A strikeouts or outs pick draws the
    pitcher's Pitch chart: one start's pitches from the catcher's view in
    his average strike zone, every batter he faced, the start's pitch mix;
    or the season's share of pitches in each of the zone's nine boxes and
    the four corners outside it, his whiff rate, zone rate, top speed and
    his fastball's speed start by start. Nothing on either chart is a
    model: no expected stats and no barrels (the league's barrel table is
    not in the feed, and a guessed one would be printed as if it were the
    league's). The drawings load as their own small file (js/chart-mlb.js)
    the first time a baseball chart is drawn, so the first paint does not
    grow. Every baseball pick gets the chart slot and the parlay checker's
    "His charts" door. Pins changed and told to you: my own
    `tests/test_the_pick_page_draws_his_chart.py` now gives every baseball
    bet a slot (it said only football did), and the chart filler's test
    and the maintenance test learned the baseball tables (added, nothing
    loosened). New: `tests/test_mlb_hit_tracker_and_pitch_chart.py`.
66. **A basketball pick draws his shot chart** (2026-10-13, you: "Yes do
    all of them"). X checks it. The NBA's own CDN, which already gives the
    box every box score, publishes each game's play-by-play beside it:
    every shot with where it was taken (the league's court coordinates),
    made or missed, the kind of shot, the distance, the assist, the block.
    A new table, `nba_shots`, holds one row per shot and free throw, named
    by the same game's box score (the spelling the logs and boards use).
    The nightly reads the last few days' finals and 300 older games a
    night: this season's first, then last season's, which the league's
    season file no longer lists, so they are asked for by the league's own
    game numbers (1 to 1,230); five misses in a row there and it stops for
    the night. No play-by-play file is kept in data/cache once its shots
    are stored. A basketball pick (any market) draws his Shot chart: a
    game's shots on the half court with every shot listed, or the season
    with each zone's percentage on the floor (restricted area, paint,
    mid-range, each corner three, above the break), and splits by zone
    beside the league's own percentage there, by kind of shot, by quarter
    and by distance; his minutes, rebounds, assists, steals, blocks and
    turnovers that night sit beside the shots. ALSO: steals, blocks and
    turnovers are now stored in the NBA (and WNBA) logs from both box-score
    feeds; nothing prices them. Every basketball pick gets the chart slot
    and the parlay checker's "Shot chart" door. ROUTING, ONE RULE: every
    player's pick page, in every league, now leaves the chart slot, and
    the chart module decides which of his charts to draw (and hides the
    slot when he has none, an NFL tackles bet today), so a new chart is
    routed everywhere a pick opens without touching the first-paint
    script. That also kept the first visit under its 611 KB budget, which
    the basketball rule alone had tipped over by 11 bytes. Pins changed
    and told to you: my own `tests/test_the_pick_page_draws_his_chart.py`
    now gives every player's bet a slot (it said kicking and tackles bets
    had none; their charts are hidden by the module) and a basketball
    parlay leg a door; my own `tests/test_mlb_hit_tracker_and_pitch_chart.py`
    and `tests/test_a_passing_chart_for_every_passer.py` read the new slot
    rule; the maintenance test stubs the shot reads. New:
    `tests/test_a_shot_chart_for_every_nba_player.py`.
67. **A hockey pick draws his shot map or his save map** (2026-10-13, you:
    "Yes do all of them"). Y checks it. Nothing new to fetch: the xG work
    already stores every attempt of every game (where from, what it
    became, the shooter, the goalie in net, the shot type, the strength,
    rebound or rush). Each attempt is turned to face the net at the top
    (a half turn, so his left stays his left). A skater's pick draws his
    Shot map: a game's attempts with each one listed (the goalie it went
    at, the assists on a goal, power play, rebound, rush, and our xG
    model's chance for it), or the season with his shooting percentage at
    each distance on the ice; splits by distance, kind of shot and
    strength. A goalie's saves or goals against draw his Save map: every
    shot on goal he faced (never an empty net), saved or in, his save
    percentage by distance, and goals saved above expected the way the
    board already counts it. Every hockey leg in the parlay checker gets
    its door. No pins changed. New:
    `tests/test_a_shot_map_and_save_map_for_hockey.py`.
68. **Every player pick draws his role: how much he is used, game by
    game** (2026-10-14, you: "Yes do all of them"). Z checks it. Nothing
    new to fetch: the box scores every board reads carry most of a role,
    and where the play-by-play the other charts store adds what a box
    score lacks it is read too. NFL: snap share, targets, carries,
    attempts, red-zone looks and air yards, with his share of his team's
    targets and carries that game (a share is of his own club's that
    game, so a trade takes it with him); a passer leads with his
    attempts. College: carries, catches, attempts, red-zone touches and
    his shares. NBA: minutes, starts, and the shots, threes and free
    throws he tried (the shot chart's play-by-play); WNBA: minutes and
    starts. MLB: a hitter's plate appearances, his spot in the order
    (where he came up among his side's first nine; off the bench he has
    none) and pitches seen; a pitcher's pitch count, batters faced,
    whether he started (he faced the first batter) and his days of rest.
    NHL: a skater's ice time, shots on goal, every attempt and those on
    the power play; a goalie's shots faced and his starts. A number not
    on file is a gap on the chart, never a zero. The chart describes his
    role; nothing on it moves a price. It is offered after his own chart
    (the carries, the targets, the throws, the hits, the pitches, the
    shots), never ahead of it, on every player pick in every league, and
    a WNBA pick and a college quarterback's passing pick, which had no
    chart, now have this one. The drawing loads as its own small file
    (js/chart-role.js). ALSO: the hockey, baseball and basketball charts
    now find a player by an index on his name instead of reading every
    stored shot or plate appearance (five indexes; the box builds them
    by itself, a second or two each). Pins changed, told to you: my own
    chart tests from yesterday (`tests/test_the_pick_page_draws_his_chart.py`,
    `tests/test_a_passing_chart_for_every_passer.py`,
    `tests/test_a_target_chart_for_every_college_receiver.py`,
    `tests/test_mlb_hit_tracker_and_pitch_chart.py`,
    `tests/test_a_shot_chart_for_every_nba_player.py`,
    `tests/test_a_shot_map_and_save_map_for_hockey.py`) list each bet's
    charts with the role chart at the end, and the lead rule with it
    sorted last; nothing loosened. New:
    `tests/test_a_role_chart_for_every_player.py`.
69. **A kicker's pick draws every kick he tried: the kicker chart**
    (2026-10-14, you: "Yes do all of them"). AA checks it. The NFL
    play-by-play the other football charts already read every night
    carries every field goal and extra point: the kicker, the distance,
    made, missed or blocked, the quarter, the clock, the score, and the
    game's roof, temperature and wind. A new table, `kicks`, keeps them,
    filled by the same read (this season's within minutes of pulling,
    last season's once). It does not record where across the field or
    between the uprights a kick went, so the chart places each field goal
    by its distance only, side by side in the order he tried them, and
    says so. A kicking pick (kicking points, field goals made) draws it:
    a game's field goals with every kick listed (an extra point that
    never got off is listed and counted as not made), or the season with
    each distance band's rate beside the league's; splits indoors and
    outdoors, in wind (10 mph or more) and cold (under 40°F) outdoors,
    in the fourth quarter, and with the game within three points. The
    parlay checker's kicking legs get a "Kick chart" door. Nothing on it
    moves a price. Pins changed, told to you: my own
    `tests/test_the_charts_fill_themselves.py` owes the kicks table like
    the others (and fills one kick for "filled"); my own
    `tests/test_the_pick_page_draws_his_chart.py` and
    `tests/test_a_role_chart_for_every_player.py` give a kicking bet the
    kicker chart (it had none). New:
    `tests/test_a_kicker_chart_for_every_kicker.py`.
70. **Every UFC fighter's fight history: how and when each fight ended**
    (2026-10-14, you: "Yes do all of them"). AB checks it. The ESPN
    records each fighter's dossier is drafted from carry every bout he
    has had: the opponent, won, lost or neither (a draw or no contest),
    how it ended (KO/TKO, submission or decision), the round and the time
    in it, the rounds scheduled, the division, and both men's numbers
    where ESPN tracked the bout (significant strikes and takedowns landed
    and tried, knockdowns, submission attempts). A new table,
    `ufc_fights`, keeps his last fifteen; the UFC tick reads the upcoming
    card's fighters four at a time and again after three days, and a
    fighter ESPN cannot find is remembered rather than asked for every
    tick. It is its own table on purpose: a dossier you reviewed (a red
    flag kept or deleted) is never re-drafted to add a history. Every
    fighter block on the UFC page (both corners of a fight, and a
    searched fighter's card) has a "Fight history" button: By fight draws
    the rounds he was scheduled for, filled to where it ended, with both
    men's numbers side by side; Career draws every fight's length on one
    25-minute clock, with his record, finishes won and lost, how often he
    goes the distance, first-round finishes, the average fight, by method,
    three rounds and five, and when his fights end. His photo is ESPN's
    headshot for the fighter where the site has none. Nothing on it moves
    a price. Two constants nothing read came out of app.js to pay for the
    button (the first visit sits 42 bytes inside its 611 KB budget, no
    bump). One pin changed, told to you: my own
    `tests/test_a_route_chart_for_every_receiver.py` looks for the route
    chart's button by the name of the one helper every chart button is
    now drawn by (`ccDoor`), as strictly as before; nothing loosened. New:
    `tests/test_a_fight_history_for_every_fighter.py`.
71. **Tonight's opponent beside every player's chart: the matchup view**
    (2026-10-14, you: "Yes do all of them" and "All sports screens should
    basically be identical"). AC checks it. One picture in every league:
    the zones of his own chart, a row each, with the share of his volume
    there and what tonight's opponent allows there against the league,
    then the fit (that difference weighted by his share), the opponent's
    overall rate and its rank. NFL: a receiver's targets by depth and side
    against what the defence allows his position group (tight ends against
    what it allows tight ends), a back's carries by hole, a passer's
    throws by depth and side; which of these is his own chart decides, not
    the bet. College: field position (the college play file has no hole
    and no depth or side). NBA: the shot zones and the field-goal
    percentage the defence allows. NHL: a skater's shots by distance and
    the goals a shot the opponent's goalies allow; a goalie against where
    tonight's opponent shoots from and how well, with his own save
    percentage in each band. MLB: a hitter's own slugging in each part of
    the strike zone against where tonight's starter (the board's
    probable) or the staff pitches; a pitcher's pitches against the
    opposing lineup's slugging. Every opponent rate is pulled toward the
    league's by a few dozen plays, so a zone seen a handful of times reads
    near the league, and an opponent with less than about three games
    this season is read on last season's, which the chart says. A pick
    names its opponent and the page passes it to the chart (one attribute
    on the chart's slot; the first visit stays inside its budget, no
    bump). CONTEXT ONLY: on the 2022-2025 NFL seasons, a defence's
    allowances by side, depth and run gap did not improve the picks on
    their own (scanfit), and the other leagues' are not measured, so
    nothing on it moves a price, and the note under it says so. Six
    indexes on the chart tables make the league-wide sums quick; the box
    builds them by itself after pulling. The drawing loads as its own
    small file (js/chart-matchup.js). Pins changed, told to you: my own
    `tests/test_the_pick_page_draws_his_chart.py` and
    `tests/test_a_role_chart_for_every_player.py` read the lead rule as
    "his role, then tonight's matchup, sort after every chart of what he
    did" (it was the role alone), the second-chart rule with the matchup
    exempt from "the same season" (it says which season it reads), the
    volume helper counting a matchup's zones, and the fold helper handing
    back its html when no chart is drawing; nothing loosened. New:
    `tests/test_a_matchup_view_for_every_player.py`.
72. **Our own expected average and slugging on every hitter's chart,
    measured before any use** (2026-10-14, you, on the list: "MLB
    expected stats ... I'd test it before it touches a pick"). AD runs
    the test. The box already stores every ball in play with its exit
    velocity and launch angle (the hit tracker's table). Each night, after
    reading the finals, it now fits a table on all of them
    (engine/mlb/xstats, built the way the hockey xG model is): a ball's
    chance of being a hit and the bases it was worth, by how hard and at
    what angle it left the bat, each cell pulled toward its speed band's
    and each band toward the league's, so a rare kind of ball reads near
    the usual. The hit tracker shows it: each ball's xBA in its tooltip,
    the season's xBA and xSLG under his AVG and SLG (SLG is a new tile, as
    is Launch angle beside Exit velocity), and an xBA column in the
    batted-ball and direction tables. Why ours when the board already
    reads Savant's season xSLG: Savant's is one season total, there when
    Savant answers; ours is per ball and per stretch of games, and there
    when Savant is not. THE TEST, written before any run
    (engine/mlb/xstatsfit): the stored dates in order; the table fitted
    on the first 60% and nothing later; each predictor's pull toward the
    league picked on the next 15% and nowhere else; the last 25% scored.
    For every hitter-game there with 20 or more at bats earlier that
    season, his actual average and slugging to date against his expected
    ones to date, on whether he got a hit (log loss) and his total bases
    (squared error). The expected passes only if it beats the actual by
    0.001 of log loss (hits) or 0.5% of the error (bases) in both halves
    of that last 25%, with 2,000 hitter-games or more in each. A pass
    moves nothing: the chart says so, and wiring it into a price is your
    call after. Until AD runs, the chart says it has not been measured.
    The first visit is unchanged (the drawing is in the baseball module
    that loads with the chart). New:
    `tests/test_mlb_expected_stats_measured_before_use.py`; no pin
    changed.
Everything older and lower priority (the measurements, the Discord feed,
Kalshi + Pikkit) is in "Everything to run, in order" further down; none
of it blocks tonight.

### Start here — 2026-10-07 (Social, the Account page, Bet it)

Ethan, 2026-10-07: *"save all of this for when I'm home."* Everything
from today, in order. Nothing here needs a command except step 1.

1. **Give the site its own account, once.** Sign up on the site with the
   email you want to post from as Qellys Book, then run the second
   `SF.claim` command in step 4 at the top of this file with that email. It gives the account the
   handle `Qellys_Book`, the gold tick and the crown avatar.
2. **Bet it, after the next props refresh** — paste the output back:
   ```
   cd /srv/qellys && sudo -u qellys python3 -m engine.betlinks nfl --props
   ```
   Your last run showed no per-game link file yet (no props pull had run
   since links were switched on), so player-prop slip links could not be
   checked. This run should show them banked.
3. **The book logos** — one command on the box, then look at the sheet:
   ```
   cd /srv/qellys && sudo -u qellys python3 -m engine.booklogos
   ```
   It fetches each sportsbook's own square icon (the one it ships for
   phone home screens, or Google's copy of it) into `web/img/books/` and
   writes the list the page reads; the Bet it sheet shows the icons the
   next time it opens, no deploy needed. Paste the output back: a line
   starting `--` is a book that returned nothing usable and keeps its
   coloured initials — for those, drop a PNG at `web/img/books/<key>.png`
   yourself and add the key to `manifest.json`'s `keys` list, or tell me.
   The same icons show on Social's Tail sheet (Tail opens the Bet it
   sheet now: one tile per book with every leg, a tile per leg where a
   book holds only some, and every other book's front door under "Key
   it in at").
4. **Kalshi and Polymarket in the box.** We store Kalshi tickers and
   Polymarket slugs for the games we price, but not a page address for
   a bet, and I will not guess one. Open any market on kalshi.com and
   paste me its full address (the URL bar); same for one on
   polymarket.com. If the address can be built from the ticker/slug, both
   get tiles in the box. Michigan blocks both, so they would be for
   readers in other states.
5. **One choice to check on Social:** profile covers use your banner's
   arena with the logo cut out (so nobody's name sits under a second
   Qellys Book). If you want the full logo on profiles too, say so.
6. **The props "not graded" count and the leaderboard** fill by
   themselves as people post; nothing to run.
7. **Watch button check** (next game night). The live cards and the
   play-by-play page carry a Watch button once the live loop names a
   carrier. With a game on, this prints each game and where the feed
   says it is on; paste it back:
   ```
   for f in /srv/qellys/web/data/live_*.json; do python3 -c "import json,sys; d=json.load(open('$f')); print('$f'.split('/')[-1], [(g['away']+'@'+g['home'], g.get('tv'), g.get('tv_local')) for g in d.get('games',[]) if g['live']['state']=='live'])"; done
   ```
   A game with `tv` None means the feed named no carrier and the page
   shows no button, which is the designed answer, not a bug.
8. **Walk today's three fixes on your phone** (2026-10-07 evening, after
   the box pulls — about five minutes after each push; the Status page
   shows the version). Each was walked here at 390px and 1440px with no
   errors and no sideways scroll, so anything off is worth a screenshot:
   - *Tail.* Social → any parlay → **Tail**. The Bet it sheet opens: a
     tile for a book that carries every leg on one slip, a tile per leg
     for a book holding only some (tagged "Leg 1 of 2"), then every other
     book under "Or key it in at". The count still ticks. Tap a tile:
     the book opens in a new tab and the sheet drops. Next sheet you
     open, that book sits first tagged "Your book".
   - *Posting from the slip.* Add two legs, open the tray, tap **Post to
     the feed**, tap the caption box: the page must NOT zoom (that was
     the 12.5px field; every field on a phone is 17px now). Post: the
     tray goes away and you land on the post, nothing left behind.
   - *Pick of the Day.* Home, any league with a pick: a gold **Bet it**
     bar under the pick, word centred. Tap the far right end of the bar,
     not the word — it must open (it used to take only the word). Then:
     slip links if the board has them, otherwise
     "Key it in at" with the book that priced it first, tagged "Priced
     here". Same sheet on the Picks page hero and on every card.
   Until step 3 runs, every tile is the book's colour and initials; after
   it, the real icons on all three sheets at once.

### Everything to run, in order (saved 2026-10-06, Ethan: "save all the code for me to run for when I'm home. I know it will be a big list")

This is every outstanding command, start to finish. Run straight down
and paste each output back with its number. **Parts A and B only read**
(safe any time). **Part C measures and saves verdicts** (it changes
nothing on the live board until the next build reads them). **Part D
changes things**, and step 15 waits until we've looked at step 14
together. Part E is setup you do in a browser plus two commands.

If something errors or sits silent, paste what you have and skip to the
next step; none of them depends on an earlier one except 15 (on 14).

#### A. Is the box current and healthy? (seconds)

**0. The box has today's code** (the top line should read `Runbook: Bet
it and the Discord page` or something newer; if it shows something
older, wait five minutes and try again):

```
git -C /srv/qellys log --oneline -1
```

**1. Site speed and what is eating the box** (paste all of it):

```
uptime; free -m
ps -eo pid,ni,pcpu,pmem,etime,args --sort=-pcpu | head -8
for p in / /js/app.js /data/recommendations.json /data/record.json; do curl -s -o /dev/null -w "$p %{http_code} %{size_download}B %{time_total}s\n" http://127.0.0.1:8000$p; done
journalctl -u qellys --since "2 hours ago" --no-pager | grep -iE "refresh|cycle|took|build" | tail -15
```

#### B. What the site is saying (seconds each, read-only)

**2. NFL: does the board contradict itself?** Every board on the page
read against the others: an over on one and an under on another, one bet
with two chances, a play listed to avoid that another board posts, a
reason under a pick that argues the other way, a pick on a player who is
out. Paste the whole thing; each kind tells me which builder to fix:

```
cd /srv/qellys && sudo -u qellys python3 -m engine.contradictions --sport nfl
```

**3. Hockey: why no picks?** Names the first thing stopping the NHL
board. "NO PICKS EXPECTED — preseason only" is the honest answer until
the regular season starts; anything starting with STOP is mine to fix:

```
cd /srv/qellys && sudo -u qellys python3 -m engine.nhlcheck
journalctl -u qellys --since "6 hours ago" --no-pager | grep -iE "nhl" | tail -12
```

**4. The six research reports vs the weekend's results** (Monday night's
game has settled): every report pick, our chance on the same bet, the
price, and who was closer:

```
cd /srv/qellys && python3 -m engine.scancard
```

**5. Our touchdown record against the prices we took** (re-run of T3 with
a bigger sample; banded by the chance we claimed):

```
cd /srv/qellys && python3 - <<'PY'
import sqlite3
c = sqlite3.connect('file:data/ledger.db?mode=ro', uri=True)
rows = c.execute("""SELECT date, player, MAX(hit_prob), MAX(status='won'), MAX(odds) FROM bets
  WHERE sport='nfl' AND market='anytime_td' AND UPPER(side)='OVER'
  AND category IN ('board','likely','likely_live','matchup_td') AND status IN ('won','lost')
  GROUP BY date, player""").fetchall()
imp = lambda o: 100 / (o + 100) if o > 0 else -o / (100 - o)
for lo, hi in ((0, .3), (.3, .4), (.4, .5), (.5, .6), (.6, 1.01)):
    b = [r for r in rows if r[2] is not None and r[4] and lo <= r[2] < hi]
    if b:
        print(f"{lo:.0%}-{min(hi,1):.0%}  n {len(b):3}  we said {sum(r[2] for r in b)/len(b):.0%}  "
              f"price said {sum(imp(r[4]) for r in b)/len(b):.0%}  scored {sum(r[3] for r in b)/len(b):.0%}")
print("all:", len(rows), "picks,", sum(r[3] for r in rows), "scored")
PY
```

**6. Which pages people use** (last 7 days; prints nothing useful if
analytics is still switched off, which is fine):

```
cd /srv/qellys && sudo -u qellys python3 -m engine.analytics report 7
```

#### C. Measure, then save the verdicts (minutes each, low priority)

**7. NFL: the opponent's part of interceptions and the volume markets**
(two or three minutes). An `ADOPT` line on `pass_int` becomes the NFL's
interception matchup strength:

```
cd /srv/qellys && sudo -u qellys nice -n 19 python3 marketfit.py --opp
```

**8. NFL: interceptions round two and the other markets** (a few minutes;
fetches FTN charting if it is not cached). The `pass_int/att×att+opp`
line decides whether NFL interceptions reach Most Likely:

```
cd /srv/qellys && sudo -u qellys nice -n 19 python3 marketfit.py
```

**9. College: re-read the four seasons with the new counts** (about ten
minutes):

```
cd /srv/qellys && sudo -u qellys nice -n 19 python3 ingest.py cfbhist --seasons 2022-2026 2>&1 | tail -15
```

**10. College: check the new columns landed, then measure** (the last
line says which college markets open on Most Likely, interceptions
included):

```
cd /srv/qellys && sudo -u qellys python3 -c "from engine import db; c=db.connect(); print(c.execute(\"SELECT market, COUNT(*) FROM player_game_logs WHERE sport='cfb' AND market IN ('pass_att','pass_cmp','pass_int','rush_att') GROUP BY market\").fetchall())"
sudo -u qellys nice -n 19 python3 -c "from engine import db, rankfit; [print(l) for l in rankfit.measure(db.connect(), 'cfb')]"
```

**11. The near-even tier cap.** Saves its verdict; the next build caps
the labels only if it holds. Paste the TIER CAP block:

```
cd /srv/qellys && sudo -u qellys python3 bandcheck.py --save 2>&1 | sed -n '/TIER CAP/,/^$/p'
```

**12. When to bet, re-checked against the same book's close** (a minute
or two; streams the line snapshots):

```
cd /srv/qellys && sudo -u qellys nice -n 19 python3 bettiming.py --sport nfl
```

**13. Do our parlay legs and tickets hit as claimed?** (seconds; the
sample was too small last time):

```
cd /srv/qellys && sudo -u qellys python3 -c "import json; from engine import ledger, parlayledger as P; print(json.dumps(P.calibration(ledger.connect()), indent=1, default=str))"
```

#### D. The one that changes stored data

**14. Same-book closes for past bets, dry run** (writes nothing). Paste
the counts and the OVERWRITTEN sample:

```
cd /srv/qellys && sudo -u qellys nice -n 19 python3 launch.py --repair-closes --sport nfl > /tmp/closes.txt 2>&1; echo "exit $?"; head -60 /tmp/closes.txt
```

If it sits silent past twenty minutes, check it from a second terminal
and paste this too:

```
ps -o pid,etime,rss,cmd -C python3 | grep repair-closes; free -m
```

**DONE for the NFL, 2026-10-06** (backup data/backups/pre-repair-closes-20261006-225314:
579 filled, 1,196 overwritten, 25 cleared). One sport at a time — the
all-sport run was killed for memory. Other sports later, the same way.

**15. Same-book closes, for real — only after we've looked at step 14
together.** It backs the journal up first; results, units and records do
not change, only the stored closing prices and the CLV built on them:

```
cd /srv/qellys && sudo -u qellys nice -n 19 python3 launch.py --repair-closes --sport nfl --apply 2>&1 | tail -20
```

#### E. Setup: hear about it when the site breaks (about 5 minutes)

**16. healthchecks.io (P6-a, still not set up).** Website steps first:
sign up free at https://healthchecks.io, rename "My First Check" to
"Qellys Book", set **Period 15 minutes** and **Grace 15 minutes**, check
your email is switched on under **Integrations**, then copy the ping URL
(`https://hc-ping.com/...`). Then on the box (paste the URL when asked;
the second line should print `1`):

```
cd /srv/qellys && sudo ./deploy/setenv.sh QB_HEALTHCHECK_URL
sudo grep -c '^QB_HEALTHCHECK_URL=https://hc-ping.com/' /etc/qellys/env
```

Then the failure email (your email at the prompt; a test mail should
arrive within a minute, check spam):

```
cd /srv/qellys && sudo ./deploy/setenv.sh QB_ALERT_EMAIL
sudo cp deploy/qellys-alert@.service deploy/qellys-update.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl restart qellys
sudo systemctl start qellys-alert@test.service
```

No mail? `sudo journalctl -u qellys-alert@test -n 20 --no-pager`. The
check turns green 10–15 minutes after the restart.

#### F. Kalshi + Pikkit: the site's picks placed for real, verified on Pikkit (about 20 minutes, mostly in a browser)

**ON HOLD — 2026-10-06.** Michigan has blocked every sports prediction
market (Kalshi, Polymarket, ProphetX; Novig never served Michigan), by
a court order the state calls temporary. Do not fund a Kalshi account
from Michigan. The trader is built and tested; when the court case
resolves, this section runs as written. The Michigan-legal route for a
verified record is the licensed sportsbooks (DraftKings, FanDuel,
BetMGM, Caesars), which Pikkit and Juice Reel both sync — but they ban
automated betting, so each bet is a tap by you — the **Bet it** button
(Part I) opens each pick on that book's slip. **Coinbase is not a way around it**
(checked 2026-10-06): its prediction markets are Kalshi's own contracts
routed through Kalshi's exchange, its trading API does not cover them,
and neither Pikkit nor Juice Reel syncs Coinbase.

Ethan, 2026-10-06: "link the site to a pikkit or juice reel account so we
can legitimately track all the bets the site puts in … every single edge
bet and most likely bet … We will only do nfl to start." What is built
(`engine/kalshitrade`): after every football board rebuild the box places
each pick on **Kalshi** — an exchange with an official trading API, never
a sportsbook — one contract a pick, only where Kalshi lists the same bet
at the same line. Pikkit syncs the Kalshi account by itself, so the picks
show up there as verified, nothing typed by hand. The Status page gets a
"Kalshi trader" card with the mode, today's orders and a "Verified on
Pikkit" link.

**What one contract costs.** A Kalshi contract pays $1 if the pick wins
and costs its chance in cents: a 60% pick costs about 60¢, a 35% long
shot about 35¢. Every pick is under $1; a full NFL Sunday across both
boards is roughly 60–80 picks, about $35–45. The site's units never touch
this; they stay what the record is graded on.

**What Pikkit can show.** Only what Kalshi lists: game lines match; player
props exist for the markets Kalshi carries, mostly the main games and
stats. The `run --dry` line in step 19 shows how much of a slate matches.
Still to code (blocked by the sandbox's permission filter on 2026-10-06,
retry with Ethan's go-ahead): Edge GAME bets (`game_bets`) into the edge
lane with one key per bet, prop series found on Kalshi's list by itself,
`QB_KALSHI_PRICE_RULE=any`, and defaults sized for a Sunday.

**Paper first.** In `paper` mode the box records exactly what it would
have placed, with Kalshi's price at that moment, and places nothing. Two
days of that, we read the report together, then `live`.

**17. The two accounts (browser).**
   a. **Kalshi**: sign up at https://kalshi.com, verify your identity,
      fund it (free ACH; $50 covers about one Sunday of every pick). Then
      *Account → Settings → API Keys → Create key*. It shows a **Key ID**
      and downloads a **private key file** (text starting
      `-----BEGIN PRIVATE KEY-----`). Keep both; the file goes on the
      box in step 18 and is never pasted anywhere else.
   b. **Pikkit**: in the app, use (or make) the account that will hold
      the site's record, *Connect a sportsbook → Kalshi*, log in. Copy
      your Pikkit profile link (the `links.pikkit.com/user/...` one).

**18. The key and the settings on the box.** The file first — this
pastes it straight into place with no editor: run the first line, paste
the WHOLE key file (every line from BEGIN to END), press Enter, then
**Ctrl-D**:

```
sudo sh -c 'umask 077; cat > /etc/qellys/kalshi.pem'
sudo chown qellys:qellys /etc/qellys/kalshi.pem && sudo chmod 600 /etc/qellys/kalshi.pem && sudo head -c 27 /etc/qellys/kalshi.pem; echo
```

(That prints `-----BEGIN PRIVATE KEY----` and nothing more.) Then the key
id, the Pikkit link (each prompts; paste at the prompt), paper mode and
the every-bet settings — every Most Likely tier and every staked Edge
pick, NFL only, 150 orders and $50 a day at most, paying up to 3¢ over
our own chance:

```
cd /srv/qellys && sudo ./deploy/setenv.sh QB_KALSHI_KEY_ID
sudo ./deploy/setenv.sh QB_PIKKIT_MODEL_URL
sudo ./deploy/setenv.sh QB_KALSHI_MODE paper
sudo ./deploy/setenv.sh QB_KALSHI_LANES potd,top,strong,look,edge,game
sudo ./deploy/setenv.sh QB_KALSHI_MAX_ORDERS_DAY 150
sudo ./deploy/setenv.sh QB_KALSHI_DAILY_CAP_CENTS 5000
sudo ./deploy/setenv.sh QB_KALSHI_SLACK_CENTS 3
sudo ./deploy/setenv.sh QB_KALSHI_RESERVE_CENTS 200
sudo systemctl restart qellys
```

**19. Prove it, place nothing.** `check` signs one read-only request and
prints `ok — connected; balance $…`; `run --dry` prints every pick it
would place right now, the Kalshi market it matched and the price, and
writes nothing. Paste both:

```
cd /srv/qellys && sudo -u qellys env $(sudo cat /etc/qellys/env | grep -E '^QB_(KALSHI|PIKKIT)' | xargs) python3 -m engine.kalshitrade check
cd /srv/qellys && sudo -u qellys env $(sudo cat /etc/qellys/env | grep -E '^QB_(KALSHI|PIKKIT)' | xargs) python3 -m engine.kalshitrade run --dry
```

`FAILED — HTTP 401` means the key id and the file do not belong together
(make the key again and redo step 18). `no Kalshi market for this bet`
on a prop is expected until step 20.

**20. Which Kalshi series carry player props** (paste it back; game
lines match already, props need their series named in
QB_KALSHI_PROP_SERIES and I set that from this list):

```
cd /srv/qellys && sudo -u qellys python3 -m engine.kalshitrade series
```

**21. Two days on paper — nothing to run.** The box records a pass after
every football rebuild. Then paste the report and we look at it together:

```
cd /srv/qellys && sudo -u qellys env $(sudo cat /etc/qellys/env | grep -E '^QB_(KALSHI|PIKKIT)' | xargs) python3 -m engine.kalshitrade report
```

**22. Live — only after step 21, and only when you say so:**

```
cd /srv/qellys && sudo ./deploy/setenv.sh QB_KALSHI_MODE live
sudo systemctl restart qellys
```

**The off switch, any time** (takes effect on the next pass, no restart):

```
cd /srv/qellys && sudo -u qellys python3 -m engine.kalshitrade stop      # …and `go` to resume
```

Every knob is a line in /etc/qellys/env (`sudo ./deploy/setenv.sh KEY
VALUE`, then restart): QB_KALSHI_CONTRACTS (per pick, default 1),
QB_KALSHI_MAX_ORDER_CENTS (100), QB_KALSHI_DAILY_CAP_CENTS,
QB_KALSHI_MAX_ORDERS_DAY, QB_KALSHI_RESERVE_CENTS, QB_KALSHI_LANES,
QB_KALSHI_SLACK_CENTS, QB_KALSHI_PROP_SERIES.

#### G. The record's outside witness — nothing to run, one key to set (2026-10-06, Ethan: "Do 2")

Built (`engine/witness`): whenever the forecast chain grows, its head is
stamped on OpenTimestamps (a Bitcoin timestamp, free, no account) and
posted to the public channel QB_HEADS_WEBHOOK names; the Bitcoin proof is
fetched when mined; the **Verify** page (`qellysbook.com/#verify`, under
More → Proof) lists every anchor with its downloadable proof and each
day's picks under the anchor that covers them. It runs by itself from the
seal step of every cycle. The only setup is the public post:

**23. A public channel for the anchors** (5 minutes, once). In Discord,
make a public read-only channel (e.g. `#record-anchors`), *Edit channel →
Integrations → Webhooks → New webhook*, copy its URL, then (it prompts;
paste at the prompt):

```
cd /srv/qellys && sudo ./deploy/setenv.sh QB_HEADS_WEBHOOK
sudo systemctl restart qellys
```

Then paste this after the next cycle (a few minutes) — it should show at
least one anchor, `pending` until the calendar's next Bitcoin
transaction (hours), `bitcoin block N` after:

```
cd /srv/qellys && sudo -u qellys python3 -m engine.witness status
```

Without the webhook the anchors still happen (the Bitcoin proof is the
strong witness; the post is the one anyone can read without software).

#### H. The Discord feed — the site posting to your server by itself (10 minutes, once)

Ethan, 2026-10-06: "every single night when bets settle, it'll
automatically post that day's record to the Discord … link other shit to
where the site feels more alive." Built (`engine/discordfeed`), running
from every cycle:

- **#record** (public): last night's record once every pick has graded —
  each book's W-L, units, hit rate against what we said, the best hit and
  the toughest miss; and the week, every Tuesday.
- **#picks** (members only): the Pick of the Day the cycle it locks;
  "today's board is up" with the counts by tier and the top picks; a long
  shot that cashed (+300 or longer).
- **#anchors** (public): the chain heads and Bitcoin anchors (Part G).

**24. Three webhooks.** In Discord, for each channel: *Edit channel →
Integrations → Webhooks → New webhook → Copy URL*. Then (each prompts;
paste at the prompt):

```
cd /srv/qellys && sudo ./deploy/setenv.sh QB_DISCORD_RECORD_WEBHOOK
sudo ./deploy/setenv.sh QB_DISCORD_PICKS_WEBHOOK
sudo ./deploy/setenv.sh QB_HEADS_WEBHOOK
sudo systemctl restart qellys
```

If #picks is NOT members-only, add `sudo ./deploy/setenv.sh
QB_DISCORD_PICKS_DETAIL 0` before the restart: it then posts counts and
"the Pick of the Day is locked", never the pick. The first posts arrive
on the next cycle with something to say (the board post the next game
day, the record the morning after). The log line to look for:

```
journalctl -u qellys --since "1 hour ago" --no-pager | grep -E "discord|witness" | tail
```

**25. The members' invite on the Discord page** (2 minutes, once). The
page hands the invite only to paid accounts. First, is it set already?
`1` means yes, skip the rest of this step:

```
sudo grep -c '^QB_DISCORD_INVITE=' /etc/qellys/env
```

`0`: in Discord, *Server name → Invite people → Edit invite link →
Expire after: Never*, copy it, then (paste at the prompt):

```
cd /srv/qellys && sudo ./deploy/setenv.sh QB_DISCORD_INVITE
sudo systemctl restart qellys
```

The Discord page (More → The Discord) now also lists the three channels
the site posts to, which ones are switched on, and the last few posts
that went to #record, word for word (web/data/community.json; never a
webhook URL, never a #picks post).

#### I. Bet it — the book's own bet slip on every pick (nothing to set)

Ethan, 2026-10-06: "build the bet it button". Built (`engine/betlinks`):
the odds pulls we already pay for now ask the API for each book's links
(free: billed per market and region, not per field). Every pick that
names a book gets **"Bet it at DraftKings"** (or whichever book): it
opens that book with the bet on the slip. Where the book gives no slip
link for that exact line, the button says **"Open at …"** and opens the
game at that book instead. It shows on the pick page, the Most Likely
cards, the Edge rows and the Pick of the Day. Links are filled for
Michigan (`QB_BET_STATE`, default `mi`). The links are kept in small
files beside the odds cache that delete themselves after three days, so
the cache does not grow.

**26. After the next NFL rebuild** (the first one after the deploy;
about 10 minutes), paste both. The first should show games banked and
most picks "with a bet-slip link"; the second is the cache size to
compare against tomorrow's:

```
cd /srv/qellys && sudo -u qellys python3 -m engine.betlinks nfl
du -sh /srv/qellys/data/cache
```

If the first says `0 game(s) banked`, the pull has not run since the
deploy; wait one more cycle. Off switch, any time:
`sudo ./deploy/setenv.sh QB_BET_LINKS 0` then `sudo systemctl restart qellys`.

**27. Why no player prop has a bet-slip link yet** (2026-10-06). Your
step 26 run showed 174 slip links each at DraftKings, Caesars and
FanDuel — exactly 29 games × 6 game-line outcomes — so every link banked
so far is a spread, moneyline or total, and not one player prop. This
says whether the prop pulls have run since the deploy, and whether they
came back with links. Paste the output:

```
cd /srv/qellys && sudo -u qellys python3 -m engine.betlinks nfl --props
```

**28. Social** (2026-10-06; a full social feature and then Ethan's render
and one profile for the whole site, 2026-10-07 — see `docs/SOCIAL_AUDIT.md`):
parlays, takes, polls and links, profile pages with a graded record,
follows, threaded comments, notifications, Trending Picks, Top Bettors,
tags, search, blocks, and the whale-tail Tail button. Your Account page IS
your profile now. Nothing to switch on. Parlays grade themselves from the
journal the first time anyone reads the feed after their games.

**Give the site its own account (once).** Sign up on the site with the
email you want to post from as Qellys Book, then run this on the box with
that email in place of `you@example.com`. It gives that account the handle
`Qellys_Book`, the gold verified tick and the crown avatar; nobody else can
take a name with "qellys" in it:

```
cd /srv/qellys && sudo -u qellys python3 -c "from engine import accounts as A, socialfeed as SF; print(SF.claim(A.connect(), 'you@example.com', 'Qellys_Book', name='Qellys Book'))"
```

To give (or take back) the tick on someone else's handle, `True` or `False`:

```
cd /srv/qellys && sudo -u qellys python3 -c "from engine import accounts as A, socialfeed as SF; print(SF.set_verified(A.connect(), 'SomeHandle', True))"
```

To check it is answering:

```
curl -s https://qellysbook.com/api/feed/list | head -c 300; echo
curl -s https://qellysbook.com/js/social.js | head -c 80; echo
```

The first should start with `{"posts": [`, the second with
`/* Qellys Book — Social: the feed`. Moderation from the box, any time:
the first line lists what readers reported (three reports from different
accounts hide a post or comment by themselves); the second hides post 12
(put the real number in; `'comment'` for a comment; `False` restores it).

```
cd /srv/qellys && sudo -u qellys python3 -c "from engine import accounts as A, socialfeed as SF; print(SF.reported(A.connect()))"
cd /srv/qellys && sudo -u qellys python3 -c "from engine import accounts as A, socialfeed as SF; print(SF.set_hidden(A.connect(), 'post', 12, True))"
```

#### Later (not tonight)

- **NHL calibration (H14)**, once NHL picks have graded for two weeks:
  `cd /srv/qellys && sudo -u qellys python3 -m engine.likelycal fit --sport nhl`
- **Live tab during a game (P9-a):** just open it while a game is on and
  tell me if anything looks wrong.
- **Steps 5 and 11** again every week or two, so the verdicts keep up
  with the record.

The dated sections below say what each step is for and what I do with
its output.

### Site speed — run this first (2026-10-04)

The web server and the background work (settling, refits, board builds)
share one Python process on a one-CPU box, so anything heavy in the
background makes pages wait. The automatic learning job now runs in its
own low-priority process, at most every three hours. This shows what
else is eating the box (paste all of it):

```
uptime; free -m
ps -eo pid,ni,pcpu,pmem,etime,args --sort=-pcpu | head -8
for p in / /js/app.js /data/recommendations.json /data/record.json; do curl -s -o /dev/null -w "$p %{http_code} %{size_download}B %{time_total}s\n" http://127.0.0.1:8000$p; done
journalctl -u qellys --since "2 hours ago" --no-pager | grep -iE "refresh|cycle|took|build" | tail -15
```

Run it while the site feels slow. The load average (`uptime`) and the
top processes tell whether it is the box; the `curl` times tell whether
it is the server or your phone.

### Run next: the new markets (2026-10-05, Ethan: "QB interceptions, QB Pass Attempts, QB Completions … any other market we are missing")

**What shipped.** College now counts completions, interceptions and
carries-as-a-market, builds attempts / completions / carries props, buys
their prices and walks them in the rank store; each opens on the college
Most Likely board only when the box's own walk clears 0.60. The NFL
already had the three (2026-09-27).

**Interceptions are now BUILT on both leagues** (`engine/passint`): his
picks per attempt × the attempts we project × the defence's takeaway
rate, Poisson at 0.5, Tier 3 on the edge board. College measured the
defence's part the way the model applies it — 0.529 → 0.638 held out
2023-2025, every season — and carries it at ×1.5. **The NFL carries
nothing until the box measures it**: no matchup strength, no Most Likely
figure. Both come from the pastes below. College's request is 13 credits
a game (was 12 this morning), the NFL's 17 (was 16).

**What we supply and what we are missing** — `docs/MARKET_CENSUS.md`, one
table per league: every player market the Odds API hangs for football
against what we buy, build, price, rank and settle, plus the wiring of
the one projection chain per market (which measured factor reaches which
number). Generated from the code's own tables; nothing to run. Its one
finding: `engine/teamcontext` spells three markets in words no market
answers to, so the team's pass-rate tilt never reaches completions,
passing touchdowns or rushing touchdowns — left as found and recorded,
because moving the tilt onto them is a change in those numbers nothing
has measured.

**1. NFL: the opponent as the model applies it — interceptions and the
volume markets** (reads the nflverse cache; two or three minutes, low
priority). What I do with it: a `verdict: ADOPT ×b` line on `pass_int`
becomes `defensevs.TRANSFER[("pass_int","QB")] = b`; on any other market
it becomes that market's transfer; "leave the opponent out" means the
card shows it and the number ignores it, as college does for attempts:

```
cd /srv/qellys && sudo -u qellys nice -n 19 python3 marketfit.py --opp
```

**1b. NFL: interceptions round two + the other markets** (the rate arm,
the FTN interception-worthy arm, rush+rec yards, kicking, tackles; the
FTN arm fetches the charting if it is not cached). The `pass_int/att×att+opp`
line is the one that opens Most Likely: clearing 0.60 with its ± under it
becomes `likely.RANK_AUC["pass_int"]`:

```
cd /srv/qellys && sudo -u qellys nice -n 19 python3 marketfit.py
```

**2. College: land the new columns, then measure.** The four cached
seasons re-parse with the new counts (the play files stream; ten minutes
or so on the box), then the rank walk stores what the logs support —
`pass_int` is in the walk now, attempts and opponent included, so its
line says whether the college interception shelf opens:

```
cd /srv/qellys && sudo -u qellys nice -n 19 python3 ingest.py cfbhist --seasons 2022-2026 2>&1 | tail -15
sudo -u qellys python3 -c "from engine import db; c=db.connect(); print(c.execute(\"SELECT market, COUNT(*) FROM player_game_logs WHERE sport='cfb' AND market IN ('pass_att','pass_cmp','pass_int','rush_att') GROUP BY market\").fetchall())"
sudo -u qellys nice -n 19 python3 -c "from engine import db, rankfit; [print(l) for l in rankfit.measure(db.connect(), 'cfb')]"
```

A `cfb:pass_att` / `cfb:pass_cmp` / `cfb:rush_att` line at 0.60 or
better means that market is on the college Most Likely board from the
next build. Under it, the prop is still built and priced (Edge picks can
use it); Most Likely waits.

### Run next: tier cap, then the same-book closes (2026-10-04, late night)

**1. The near-even tier cap** — judges the written-down rule and saves the
verdict; the next board build caps the labels only if it holds. Paste the
TIER CAP block back:

```
cd /srv/qellys && sudo -u qellys python3 bandcheck.py --save 2>&1 | sed -n '/TIER CAP/,/^$/p'
```

**2. Same-book closes for past bets** (Ethan said yes, 2026-10-04). New
bets now bank the close of the book we posted at (else the best close
across books) by themselves. This re-derives it for bets already settled.
Results, units and records do not change — only the stored closing price
and the CLV figures built on it. First the dry run, paste back the
summary (the counts and the OVERWRITTEN sample):

```
cd /srv/qellys && sudo -u qellys nice -n 19 python3 launch.py --repair-closes --sport nfl > /tmp/closes.txt 2>&1; echo "exit $?"; head -60 /tmp/closes.txt
```

Then, once we've looked at it together, the real one (it backs the
journal up first):

```
cd /srv/qellys && sudo -u qellys nice -n 19 python3 launch.py --repair-closes --sport nfl --apply 2>&1 | tail -20
```

**2b. If the dry run looks stuck** (Ethan's first run, 2026-10-05: four
minutes and counting — the old code read the snapshot file twice). In a
second terminal, check it is alive and not out of memory:

```
ps -o pid,etime,rss,cmd -C python3 | grep repair-closes; free -m
```

"available" over ~150 MB: let it finish (nothing prints until the end,
`head` holds it all). Over ~20 minutes, or "available" near zero: Ctrl+C
the first terminal (a dry run writes nothing), make sure
`git -C /srv/qellys log --oneline -1` shows `8e512932` or later, and
rerun step 2 — it is a single cheap pass now.

**3. Live tab "database is locked"** — nothing to run. The open-bet
tracker now reads the journal read-only and retries a lock once; the box
picks it up on its own.

### Betting checks, round 4: the near-even tier cap (2026-10-04, late night)

Round 3 settled two things: grading is right (0 of ~4,700 picks
disagree with their own stat), and near even money the one board's
tiers run backwards (Top pick 18-40, Strong 38-52, Worth a look
158-176). One command — it judges the written-down rule and SAVES the
verdict; the next board build caps those labels only if it holds:

```
cd /srv/qellys && sudo -u qellys python3 bandcheck.py --save 2>&1 | sed -n '/TIER CAP/,/^$/p'
```

Paste back the TIER CAP block. If it says HOLDS, near-even Top/Strong
picks show as "Worth a look" with a line saying why, from the next
build on. Nothing is removed. Rerun it every week or two so the verdict
keeps up with the record.

### Betting checks, round 3: where the one board's near-even losses come from (2026-10-04, night)

**Ran 2026-10-04.** Grading: 0 wrong. B1 same-book: NFL one board −1.6
pts (waiting pays), NFL Most Likely staked −2.0, Edge picks +2.7/+2.5
(the only book beating its close). B4: by tier, backwards (round 4).

Round 2 found the same-book close in the wrong store (NFL closes live in
our own line snapshots, not the bought history) and showed the one
board's near-even picks hit ~44% at EVERY claim size. Paste back:

```
cd /srv/qellys
echo "=== B1 again: same-book close ==="; sudo -u qellys nice -n 19 python3 bettiming.py --sport nfl
echo "=== B4 again: band breakdown + grading recheck ==="; sudo -u qellys python3 bandcheck.py
```

- **B1.** Now reads each book's own close from the line snapshots. It
  streams the snapshot file once (a minute or two, low priority).
- **B4.** Adds the band split by tier and by market and side, and re-grades
  every settled over/under pick from its own stored stat — any "N of M
  disagree" above 0 is a grading bug, and that is the first thing to fix.

### Betting checks, round 2: the fair close and the near-even leak (2026-10-04, night)

**Ran 2026-10-04.** B1: 0 same-book closes (wrong store, fixed in round 3).
B4: rule does not hold — the one board's band hits 44-46% at every gap.

Round 1's results are in (below). Two follow-ups, both read-only, paste
them back:

```
cd /srv/qellys
echo "=== B1 again: same-book close ==="; sudo -u qellys nice -n 19 python3 bettiming.py --sport nfl
echo "=== B4: near-even leak ==="; sudo -u qellys python3 bandcheck.py
```

- **B1 again.** Round 1 compared our price (the best on the screen) with
  ONE arbitrary book's close, which reads as "the price moved our way"
  even when nothing moved. It now compares with the SAME book's close.
  NFL only first, because it reads the odds history and the box is small;
  drop `--sport nfl` for every sport once that finishes fine.
- **B4.** The one board's −149 to −111 picks went 147-177 (claimed 62%,
  price 56%, hit 45%). This checks whether that holds by sport and in
  both halves of the season, against a rule written down before the run.
  If it says HOLDS for the one board, those picks move to paper.

### Betting checks: when to bet, the heavy favourites, the parlays (2026-10-04, late)

**Ran 2026-10-04.** B1 said "bet when posted" for NFL/MLB, but read off a
biased close (see round 2). B2: the one board loses near even money
(−149 to −111: 147-177, z −3.8); heavy favourites land on their claim.
B3: parlay legs 29 of 66 (expected 34), correlated tickets 0 of 9
(expected 2.8) — too few to act on yet.

All three are read-only and take seconds. Paste all of it back:

```
cd /srv/qellys
echo "=== B1: when to bet (posted price vs close) ==="
sudo -u qellys python3 bettiming.py
echo "=== B2: profit by price band (the loss audit) ==="
sudo -u qellys python3 lossaudit.py 2>&1 | awk '/^=== /{print} /-- by price/{f=1;print;next} /-- by /{f=0} f'
echo "=== B3: do our parlay legs and tickets hit as claimed? ==="
sudo -u qellys python3 -c "import json; from engine import ledger, parlayledger as P; print(json.dumps(P.calibration(ledger.connect()), indent=1, default=str))"
```

**Research picks box.** On Zeno's page, signed in with your owner token,
there is now a "Research picks" form under "Post a bet". Paste a report's
picks before kickoff, one a line:
`Source | Player | TEAM | market | over/under | line | chance | price`.
After the week settles, `python3 -m engine.scancard --season 2026 --week 5`
grades them.

**Nothing to run for these three; they show up by themselves.**
- *Better-price alert:* when a posted Most Likely pick's price gets 2+
  points better, it appears on the Alerts page ("Better price: …"), and a
  player or team watch catches it. "Now inside the price it is worth"
  means the new price is worth taking by the pick page's own rule.
- *This week:* the Record page now opens with a card for the last seven
  days, one per book: record, units, hit rate vs what we said vs what the
  price said, the best hit and the toughest miss.
- *Why line:* every Most Likely row shows its first reason under the bet.

### NFL research: the weekend's scorecard (2026-10-04, night)

**S1. Score the six research reports against the results — Tuesday**, once
Monday night's game has settled (paste it back). Every report pick, our
chance on the same bet, the price, and who was closer:

```
cd /srv/qellys && python3 -m engine.scancard
```

### NHL — later

**H14. Later — once NHL picks have graded for a couple of weeks.** This
makes the NHL Most Likely chances honest from their own record. It is the
same fit as M1 and saves only if it scores better on games it never
learned from. It needs 40 settled picks in a group before it touches that
group:

```
cd /srv/qellys && sudo -u qellys python3 -m engine.likelycal fit --sport nhl
```

### Start here — what is still open (2026-10-04, evening)

Already done and moved to DROPLET_CHECKS: the record recount and dates
(R1, R2), L1, the pre-game closes (P2-a), the backup check (P6-b), NHL
H1–H13/H15, the round-7 fits, the corner rules, and the TD injury test.

Superseded 2026-10-06: everything still open is in **Everything to run,
in order** at the top of this file (S1 is step 4, T3 step 5, the usage
report step 6, B1/B3 steps 12–13, P6-a step 16, H14 and P9-a under
"Later").

---

## 0. THE SITE IS DOWN — run this first, before anything else

Ethan, 2026-09-09, with a photo: *"the site crashed. It won't load
anything and won't show logos."*

**What that screenshot actually says.** The page frame, the buttons and
the nav all drew — that is the service worker serving the shell it
cached. `/data/` and `/api/` are the only things it NEVER caches, on
purpose, because a stale board is worse than an honest error. So "10
boards failed to load" plus a working-looking page means one thing: **the
app is not answering, and the browser is showing you a photograph of it.**
The missing logos are the same fact — images are not cached either.

**Bring it back first, ask why second.** The journal keeps the history, so
restarting costs you no evidence:

```bash
sudo systemctl restart qellys && sleep 3 && curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/data/recommendations.json
```

`200` means it is back. Anything else, keep going.

**Then paste me all of this at once** — it answers every likely cause in
one go, and I cannot see any of it from here:

```bash
echo "=== service ==="; systemctl status qellys --no-pager -l | head -15
echo "=== restarts ==="; systemctl show qellys -p NRestarts -p MemoryPeak -p MemoryCurrent
echo "=== last 40 log lines ==="; journalctl -u qellys -n 40 --no-pager
echo "=== was it OOM-killed? ==="; sudo dmesg -T 2>/dev/null | grep -iE "killed process|out of memory" | tail -5
echo "=== disk ==="; df -h /srv /var | sed 1d
echo "=== memory ==="; free -m
echo "=== are the board files even there ==="; ls -la /srv/qellys/web/data/*.json 2>/dev/null | head -5
echo "=== how old are they ==="; date; find /srv/qellys/web/data -name '*.json' -newermt '-2 hours' | wc -l
echo "=== which commit is deployed ==="; cd /srv/qellys && git log --oneline -3
```

**The three things it can be, and what each looks like:**

* **Out of memory.** `NRestarts` climbing, `dmesg` naming a killed
  process. This box is 2GB with `MemoryMax=1600M` and it has done this
  before (2026-09-02, the in-process Wednesday refit). Restarting works
  and it comes back.
* **Out of disk.** `df` at 100%. The builds write and the app cannot.
  Clear the cache directory, not the data: the boards are the product.
* **A bad deploy.** The auto-updater pulls every five minutes, so a
  commit that will not import takes the service down within five minutes
  of being pushed. `journalctl` shows a traceback on startup rather than
  a request. If that is what it is:

```bash
cd /srv/qellys && git log --oneline -5          # find the last one that worked
sudo systemctl stop qellys-update.timer         # stop the updater re-pulling it
cd /srv/qellys && git checkout <that-commit> && sudo systemctl restart qellys
```

Tell me the commit and I will fix forward; do not leave the updater off
longer than that, or the boards stop rebuilding.

---

---

## Disk full — 2026-10-01 (read first if the site goes stale everywhere)

What happened: the 48 GB disk filled at about 06:30 UTC and every build
failed with "No space left on device". 18 GB of it was the meme radar's
throwaway lookups in `data/cache` (`dex_pairs_*` and `rug_*`, about a
million files) that nothing ever deleted. The midnight backup tipped it
over, and the full disk emptied `data/cache/maintenance.json`.

What the code does now: the cycle deletes those lookups once they are an
hour (`dex_pairs_*`) or a day (`rug_*`) old; the backup measures free space
first and refuses without room; the chore state can no longer be left
empty; leftover test folders in /tmp are swept; and every cycle logs
"⚠️ disk low" under 2 GB free. The heartbeat carries `disk_free_gb`.

If the disk is ever full again, check in this order:

```
df -h / | tail -1
sudo du -xh --max-depth=1 /srv/qellys/data /tmp /var/log 2>/dev/null | sort -h | tail -8
ls -lhS /srv/qellys/data/backups | head
```

Never delete a `.db` or `.db-wal` file. Old `backup_*.zip` files and
`/tmp/qellys-tests-*` folders are safe to remove.

---

---

## The Record page's numbers — 2026-10-02 (R1 read-only; R2 fills a date column)

Ethan, 2026-10-02: *"make sure we are recording everything and not
missing anything ... No way we have hit 12/13 TD picks bc I've seen more
then that loose."* The page fixes are pushed. These two need the box.

**R1. Recount the record (read-only, about a minute).** Ten checks on an
in-memory copy of the ledger. It re-derives every grade and lists every
anytime-TD pick in every section with its side ("scores" or "no TD") and
the touchdowns the box score credits. It shows where the board's picks
came from, bets stuck open past their game, and rows with no calendar
day. It recounts the headline by hand and checks today's board against
the journal. Paste the whole output back:

```
cd /srv/qellys && sudo -u qellys python3 recordcheck.py --sport nfl 2>&1 | tail -200
```

**R2. Give old rows their calendar day (writes only the `game_day`
column — never a grade, never the settle key).** This is the "NaN days"
fix for rows journaled before they carried their game's date. The first
line is a dry run and prints what it would fill. Run the second only if
that count looks like check 8 of R1:

```
cd /srv/qellys && sudo -u qellys python3 launch.py --backfill-days
cd /srv/qellys && sudo -u qellys python3 launch.py --backfill-days --apply
```

**L1. Which Most Likely picks to stop taking (read-only, a minute or
two).** Ethan, 2026-10-02: *"I feel like we have collected enough data
for our most likely bets too make the models better."* The record says
our Most Likely number is honest (said 65%, hit 65%) but does not beat
the price, so the lever is which picks we take. Eight rules are tried:
- a price cap
- a minimum chance
- beating the book's price
- beating the market consensus
- dropping losing shelves
- overs or unders only
- late bets only
- (on the board) tiers

Each one is chosen on the earlier weeks and judged on the later weeks it
never saw. Nothing changes on the site from this run. A rule goes on the
board only if it PASSES here twice, two weeks apart. Paste all three
back:

```
cd /srv/qellys && sudo -u qellys python3 likelyfit.py 2>&1 | tail -150
cd /srv/qellys && sudo -u qellys python3 likelyfit.py --book board 2>&1 | tail -80
cd /srv/qellys && sudo -u qellys python3 lossaudit.py 2>&1 | tail -150
```

---

## PHASE 5 — the audit fixes (2026-09-30, Ethan: "I approve everything")

Each fix below is pushed and live on the next auto-update. These are the
halves that need the box. Nothing here changes a grade.

**P2-a. Pre-game closes, every sport (read-only, seconds).** The paid
harvest now skips a game already under way at its snapshot, every stored
price carries its game's start, and the settle path refuses a harvested
close taken after the bet's own kickoff. College football now writes line
snapshots too. (M10 and M11, the close repair, were done 2026-10-01.)
Paste it back. Every close should read before kickoff:

```
cd /srv/qellys && sudo -u qellys python3 closecheck.py --sport nfl 2>&1 | tail -40
cd /srv/qellys && sudo -u qellys python3 closecheck.py --sport mlb 2>&1 | tail -40
```

Coverage may DROP on the next few days of settles. That is expected: a
close that was an in-game price is now no close at all, which is the
honest reading.

**P3-a. What the number check took out (read-only, seconds).** Every
sentence the nightly column, the weekly brief, the pick explainer or Ask
wrote with a number not in its data is now dropped before it is shown,
and logged. A week from now, paste this back — an empty file is the good
answer:

```
cd /srv/qellys && tail -20 data/llm_drops.jsonl 2>/dev/null || echo "nothing dropped"
```

**P6-a. Hear about it when the box breaks (5 minutes) — STILL TO DO.**
On 2026-10-01 the site was 9 hours stale before anyone knew. Note: on
2026-10-01 an email was pasted into QB_HEALTHCHECK_URL by mistake; step 4
below replaces it (setenv says "updated"). The site never loaded it (no
restart), and a bad value is skipped quietly anyway.

1. **Make the account.** https://healthchecks.io → Sign Up (email, Google
   or GitHub; free, no card). Open the login link it emails you.
2. **Set up the check.** It already made one, "My First Check". Click its
   name to rename it "Qellys Book". Click **Change Schedule** (⏱/gear) and
   set **Period 15 minutes**, **Grace 15 minutes**, then Save. Under the
   **Integrations** tab, your email should be listed and switched on: that
   is where the "site went quiet" mail goes.
3. **Copy the ping URL** from the check's Details page; it looks like
   `https://hc-ping.com/1a2b3c4d-...`.
4. **Put it on the droplet** (paste the URL at the prompt), then confirm
   it took (should print `1`):
   ```
   cd /srv/qellys && sudo ./deploy/setenv.sh QB_HEALTHCHECK_URL
   sudo grep -c '^QB_HEALTHCHECK_URL=https://hc-ping.com/' /etc/qellys/env
   ```
5. **The failure email, then restart** (your email at the first prompt; a
   test mail should arrive within a minute, check spam):
   ```
   cd /srv/qellys && sudo ./deploy/setenv.sh QB_ALERT_EMAIL
   sudo cp deploy/qellys-alert@.service deploy/qellys-update.service /etc/systemd/system/
   sudo systemctl daemon-reload && sudo systemctl restart qellys
   sudo systemctl start qellys-alert@test.service
   ```
   No mail? `sudo journalctl -u qellys-alert@test -n 20 --no-pager`.
6. **What you'll see.** 10–15 minutes after the restart the check turns
   green (grey "new" until then). If the site ever stops refreshing it
   turns red about 15 minutes later and emails you.
7. Optional, later: `sudo ./deploy/setenv.sh QB_HEADS_WEBHOOK` (a Discord
   channel webhook) posts the record's daily chain heads off the box.

**P6-b. Backups now carry the CLV evidence (read-only check, a minute).**
`history.db` (3 copies kept), Zeno's book, the line history, the odds
budget, the feed state and the chain heads join accounts and the ledger.
Run one now and check it; then add the weekly restore check to cron:

```
cd /srv/qellys && sudo ./deploy/backup.sh && sudo ./deploy/backup.sh --check
( sudo crontab -l; echo '30 4 * * 0  /srv/qellys/deploy/backup.sh --check >> /var/log/qellys-backup.log 2>&1' ) | sudo crontab -
```

If the disk is tight, `sudo ./deploy/setenv.sh QB_BACKUP_HISTORY` and
set it to `0` — everything else still backs up.

**P10-a. The updater no longer runs new code as root (nothing to do).**
The five-minute auto-update still ships every green push, exactly as
before. The one step that ran code from the new checkout (the page trim)
now runs as the `qellys` user. If you ever want pushes to need your say-so
first, one line turns it on — then only a commit you tag `deploy-...`
goes live:

```
cd /srv/qellys && sudo ./deploy/setenv.sh QB_UPDATE_REQUIRE tag
```

(`off` puts it back. On GitHub, also turn on 2FA and branch protection for
the deploy branch — Settings → Branches — so a stolen token cannot push.)

**P9-a. The live overlay (look, no command).** During the next live MLB
game, open the Live tab: "The sweat" should draw its picks with a live
chance beside each. It had been blank since 2026-08-24 (a four-hour
timestamp misread). If it is still blank with a game on, paste:

```
cd /srv/qellys && head -c 300 web/data/sweat.json; echo; date -u
```

**P28-a. The security log (read-only, seconds).** Every sign-in, failed
password, owner-token refusal, forged webhook, refused code and 429 is one
line now — the account as a short tag, never the email or password. To see
the last few:

```
cd /srv/qellys && tail -n 20 data/logs/security.jsonl
```

**P45-a. The Android app (laptop, an hour; only after the policy read).**
Read `docs/APP_STORES.md` first, including its four Google Play questions,
which nobody has answered yet. If the answers allow it, follow the
"Android build steps" section there: Bubblewrap on the laptop, then
`tools/assetlinks.py` with the key's SHA-256, then commit the generated
`web/.well-known/assetlinks.json`, deploy, and upload to an internal
testing track. Never put the keystore in the repo or on the droplet.

**P31-a. Turn on the usage counts (changes a setting, a minute).** You
approved the wording; the Privacy Policy now describes the counts (daily
totals, no cookie, no id, no IP). Check the live policy says so first,
then flip the switch:

```
curl -s https://qellysbook.com/privacy.html | grep -c "as daily totals only"
sudo ./deploy/setenv.sh QB_ANALYTICS 1 && sudo systemctl restart qellys
```

The first line must print `1` (if it prints `0`, the new page has not
deployed yet — wait, don't flip). A week later:
`sudo -u qellys python3 -m engine.analytics report 7`.

**P29-a. Retire the old name+PIN profiles if nobody uses them (changes a
setting, a minute).** The PIN store from before real accounts is locked
down now (one answer, a lockout, the sign-in rate limit), but if the box has
no profiles in it there is no reason to leave the door there at all:

```
cd /srv/qellys && ls data/profiles 2>/dev/null | wc -l
```

If that prints `0`: `sudo ./deploy/setenv.sh QB_LEGACY_PROFILES off` and
`sudo systemctl restart qellys`. If it prints more than 0, leave it — those
are phones still syncing, and the store keeps working for them.

---

---

## Every read-only check, one line each

Each prints what it measured and changes nothing. Run on the box as
`cd /srv/qellys && python3 homecheck.py <name>`; paste the output back.

- `python3 homecheck.py head` — which commit this box is running
- `python3 homecheck.py filler` — FILLER: game rows at -110 with no book
- `python3 homecheck.py live` — LIVE: what the Live tab has to draw, per league
- `python3 homecheck.py grading` — GRADING: is each league's book settling, and why not
- `python3 homecheck.py record` — RECORD: what the published record.json holds
- `python3 homecheck.py edge` — EDGE: does the staked book make money, and which selector earned it
- `python3 homecheck.py bench` — BENCH: what benching a league did to the record it left
- `python3 homecheck.py sizing` — SIZING: what to stake on the likelihood board, and what it buys
- `python3 homecheck.py shelves` — SHELVES: which markets the record says to stop staking
- `python3 homecheck.py data` — DATA: what we store, whether a model reads it, and how fast we are on injury news
- `python3 homecheck.py inputs` — INPUTS: does every model input move a number on the live boards
- `python3 homecheck.py weather` — WEATHER: did the forecast reach the football games and the numbers
- `python3 homecheck.py hold` — HOLD: how steady each Most Likely board is, and why picks left
- `python3 homecheck.py weight` — WEIGHT: what each board costs a phone, and where the bytes go
- `python3 homecheck.py nba` — NBA: season labels and props graded off 0 minutes
- `python3 homecheck.py exchange` — KX-2: Kalshi ticker shapes (FETCHES; run as the build user)

Only if `homecheck.py nba` finds wrong season labels (this one changes the
history database; run it once without `--apply` first, it prints what it
would do):

```bash
cd /srv/qellys && python3 -m engine.seasons relabel nba
cd /srv/qellys && python3 -m engine.seasons relabel nba --apply
```

Secrets go in through `setenv.sh`, which prompts, so they never land in
shell history. For the owner token, pick something long and random:
`python3 -c "import secrets; print(secrets.token_urlsafe(32))"`. To use it
from a laptop shell, `read -rs QB_OWNER_TOKEN && export QB_OWNER_TOKEN`
(paste, Enter), never `export` with the value typed inline.

