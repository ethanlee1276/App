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

