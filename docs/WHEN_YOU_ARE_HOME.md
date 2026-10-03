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

### Today, before Sunday's NFL board (2026-10-03)

**M1. Make the board's chances honest from its own record.** This keeps
every pick. It pulls each pick's chance toward its price by as much as
picks from the same maker (the Most Likely list, the matchup picks, the
TD scenarios, the bold picks) on the same side have earned. It saves only
if it scores better on games it never learned from. The next board build
uses it. Paste the output back:

```
cd /srv/qellys && sudo -u qellys python3 -m engine.likelycal fit --sport nfl
cd /srv/qellys && sudo -u qellys python3 -m engine.likelycal fit --sport cfb
cd /srv/qellys && sudo -u qellys python3 -m engine.likelycal fit --sport mlb
```

To undo it: `sudo -u qellys rm /srv/qellys/data/likely_calibration.json`

### NHL — load three seasons, then it runs itself (2026-10-03)

The code is on the box once the auto-updater pulls it. The NHL board builds
in the launcher's cycle from today, but it has no players until history
lands. Every NHL Edge pick goes on **paper** until its record earns money.

**H1. Disk, then a probe** (paste). The probe fetches one day, one box
score and one player from the NHL's own free feed, which this sandbox
cannot reach:

```
df -h / | tail -1
cd /srv/qellys && sudo -u qellys python3 ingest.py nhl --probe
```

**H2. Load 2023-24, 2024-25 and 2025-26** (an hour or more, in the
background; it is safe to stop and rerun, finished days are skipped):

```
cd /srv/qellys && sudo -u qellys nohup python3 ingest.py nhl --seasons 2023-2025 > /tmp/nhl_ingest.log 2>&1 &
tail -3 /tmp/nhl_ingest.log
```

**H3. When H2 ends: open the Most Likely shelves** (paste). Each hockey
market goes on the Most Likely board only if it ranks on its own walk
(the same 2,000-pair, 0.60 bar as every sport). The nightly job does this
too; this just does it now:

```
cd /srv/qellys && sudo -u qellys python3 -c "from engine import db, rankfit; rankfit.measure(db.connect(), 'nhl')"
```

**H4. Build tonight's board once by hand** (paste the last line):

```
cd /srv/qellys && sudo -u qellys python3 nhl_build.py --odds
```

**H5. Headshots, now** (paste the last line). Every club's current roster
fills the faces and moves traded players; the nightly job repeats it from
September to June:

```
cd /srv/qellys && sudo -u qellys python3 ingest.py nhl --faces
```

**H6. Re-rank after Scalpy NHL 1.0** (paste). Goals are now shots times a
regressed shooting rate and the opposing starter tilts goals and points,
so each market earns its shelf again on its own walk:

```
cd /srv/qellys && sudo -u qellys python3 -c "from engine import db, rankfit; rankfit.measure(db.connect(), 'nhl')"
```

**H7. One build from the saved odds** (paste the Odds line and the last
line). Shows the odds result, the scan's reads and how many rows each
Scalpy rule passed, without journaling anything:

```
cd /srv/qellys && sudo -u qellys python3 nhl_build.py --cached-odds --no-journal
```

That build now prints a second line, Scalpy NHL — Edge Hunter 1.0's census
(how many Elite / Strong / Small edges and passes, and the commonest pass
reasons). Paste it: it is how we will tune the Edge bar on real prices.

**H8. Live rosters and standings, now** (paste the four lines). The NHL's
own rosters and standings, and ESPN's NBA/WNBA rosters, for the team pages;
the launcher's cycle repeats both:

```
cd /srv/qellys && sudo -u qellys python3 rosters_build.py --sport nhl
cd /srv/qellys && sudo -u qellys python3 rosters_build.py --sport nba
cd /srv/qellys && sudo -u qellys python3 rosters_build.py --sport wnba
cd /srv/qellys && sudo -u qellys python3 standings_build.py --sport nhl
```

Each roster line should say `from league` (NHL) or `from roster`
(basketball). `from appearances` means the feed failed, and the line says
why.

**H9. Install the new Caddyfile** (paste the last line). The page itself
is now served without its comments (29 KB -> 11 KB gzipped on every first
visit); the updater builds the trimmed copy, but Caddy only serves it once
its config is reloaded. Validates first — a bad file is never installed:

```
cd /srv/qellys && sudo caddy validate --config deploy/Caddyfile --adapter caddyfile && sudo cp deploy/Caddyfile /etc/caddy/Caddyfile && sudo systemctl reload caddy && ls -la web/min/index.html
```

### Start here — the order to run things (2026-10-02)

Each step's commands are in its block below. Paste back the ones marked
"paste".

0. **H1–H9** — NHL (block above): probe, load three seasons, rank, build, faces, re-rank, check, rosters + standings, Caddy.
1. **R1** — recount the record (read-only, paste the whole output).
2. **R2** — give old rows their date (dry run first, then `--apply`).
3. **L1** — which Most Likely picks to stop taking (read-only, paste).
4. **P2-a** — every close before kickoff (read-only, paste).
5. **P6-a** — healthchecks.io, so you hear when the site goes stale
   (5 minutes; step by step).
6. **P6-b** — run a backup and check it, then add the weekly check.
7. **P29-a** — count the old PIN profiles (paste the number).
8. **P31-a** — turn on the usage counts (only if the first line prints 1).
9. **P3-a** — a week from now: what the number check dropped (paste).
10. Whenever: **P10-a** (optional deploy lock), **P9-a** (look at the Live
   tab during a game), **P28-a** (security log), **P45-a** (Android, later).

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

