# Ideas — what this site could add next

Ethan, 2026-08-20: *"think of more ideas to add to th website."*

Written as a working list, not a wish list. Every entry says what it is,
**what it would be built from**, and what it costs — because the ideas
that die here are the ones that need data we do not have, and it is
cheaper to find that out in a document than in a branch.

Ordered by *value per unit of work*, not by size.

---

## 2026-10-27: act on what you read, and the lights on — next, ranked

Ethan: *"think of any other ideas where we should be looking at and do it as
well"*, then *"we can use more colors ... animations and glowing shit."*
Looked at for it: FanDuel's AceAI (adds to the slip, keeps context), Action
Network's Playbook (pre-filled slip, line compare), Rithmm, Gambly (line-move
alerts), RotoBot (fantasy and betting), Outlier and Linemate (L5/L10 hit
rates), PrizePicks, Underdog, Sleeper, Apple Sports. Built today: Ask shows
its work (runbook FH); an Ask answer you can act on, add to slip, track it
(followed live, settled off the box score, "your bet is on" by push) and
watch (FI); every league its own colour, glow and motion (FJ). Next, best
value per unit of work first:

1. **Ask reads your open bets, when you attach them.** BUILT 2026-10-27
   (runbook FK). "How's my parlay
   looking?" with the box's numbers: the paperclip offers My open bets, and
   only what is attached goes with the question. AceAI knows your bets
   because it is the book; this works for every book. Built from: My Bets
   (the page's own copy) + engine/sliplive. Small to medium.
2. **Ask from anywhere.** BUILT 2026-10-27 (FK) on the fantasy player card,
   the one door that had none (the prop page's Ask was already there). An Ask door on every player row (fantasy rows,
   Over/Under, Most Likely) with the right question filled in ("Should I
   start Gibbs this week?"). Built from: the prop page's Ask attach, which
   already exists. Small.
3. **A price watch.** "Tell me if this moves past −120" from Ask's price
   card or a prop page: Action's Line Watcher, Gambly's alert. Watches are
   player, team or edge today; a price is a fourth shape the feed's
   line_move events already answer. Medium.
4. **A win celebration.** Confetti and the payout when a tracked bet
   settles a win on the Live tab or in My Bets (Underdog, Robinhood). Built
   from: slip.js settleOne and the stadiums' fireworks. Small.
5. **Team colours on every game card.** The two teams' colours along a game
   card's top edge and its scoreboard (Apple Sports). Built from: the team
   colour table applyTeamColors reads. Small to medium.
6. **Hit-rate chips on every prop row.** L5, L10 and the season against the
   line as three chips on the Over/Under list (Outlier, Linemate). Built
   from: the logs every prop row already carries. Small.
7. **Numbers that tick.** Live scores, the record's units and a ticket's
   standing roll to their new value rather than swapping (count-ups exist
   for the record's first draw). Small.
8. **Your starters on tonight's board.** On the fantasy My team tab, the
   starters with props tonight, our side and chance for members, a count
   for free accounts. Built from: the linked roster + the board. Medium.

---

## 2026-10-25 (later): the way in and the way up — next, ranked

Ethan: *"go deeper on the free paid wall ... look at other apps ... we can
show our paid features on the sign up site."* Built today (runbook EM): an
account to use the site, the sign-up showing tonight's locked picks, Free
beside Member, the last graded pick, the plans and the trial's days; the
offer once after a new account's teams; Get picks in the top bar, a members
strip on Live, locked tabs that say what they hold. Next, best value per
unit of work first:

1. **The trial reminder the timeline implies.** BUILT 2026-10-26 (step
   198, engine/trialnote): one email about a day before the charge — when,
   what, and Manage billing → Cancel — and the same line on Live while the
   trial runs. No push: the phone's permission was given for games, not
   for billing.
2. **Win-back on a lapse.** BUILT 2026-10-26 (step 199, account.js
   pwSinceHTML): the plans page's lapse notice carries the Record curve's
   numbers since the plan ended, win or lose, once five have graded.
3. **"What brings you here?"** One tap before the form, Sleeper's first
   question — Live games, our picks, fantasy, tracking my bets — and the
   landing and the order of Free beside Member follow it. Small.
4. **True social proof.** BUILT 2026-10-26 (step 200, engine/firstlook
   proof): accounts made this week and pages in game rooms right now under
   the first screen's promise, each left off under its floor (25 / 10).
5. **Picks on your teams, as a count.** The offer and the Live strip say
   "4 of tonight's picks are on teams you follow" — the private board
   against the account's watches, a count and never a pick. Small; your
   call, since a count by team says a little more than a count by league.
6. **Yearly at month two.** A monthly member on their third bill sees
   "switch to yearly, save $75" once, in Settings. Small.
7. **Not today? Keep the door open.** BUILT 2026-10-26 (step 201,
   account.js pwLaterHTML): under the plans page's two cards, signed in,
   where alerts work — with its own Turn off.
8. **Passkeys.** Face ID / Touch ID sign-in (WebAuthn): no password to
   forget and no text-message cost per sign-in. Medium.
9. **Gift a month.** Buy a month for a friend, delivered as a code
   (engine/redeem already grants one). Medium.
10. **One free pick a day — your call.** A random one of tonight's (never
    the best), opened for free accounts 15 minutes before its game, the
    way most pick apps let a stranger taste the product. It makes a paid
    pick visible without paying, which the site has never done.

---

## 2026-10-25: the live game as a place to be — next, ranked

Ethan: *"keep diving deeper into that ideas ... think of things that I
haven't told you and that I haven't thought of."* Built today: your players
live on one strip, on the iPhone widget and the lock screen; big-moment
alerts; Call it on every live game (at-bats, drives, baskets, shots); your
ticket in the game's chat; the chat out of the corner and rebuilt; while
you were away; the game in 30 seconds. What comes next, best value per unit
of work first, each with what it is built from:

1. **Spoiler guard for TV delay — BUILT 2026-10-25 (runbook EL).** "Watching
   on TV? Delay" holds the game page and its chat back 10, 30 or 60
   seconds. The push alerts are the box's and are not held; holding them
   would need the delay on the account, read by engine/pushmine.
2. **The house posts the moment.** BUILT 2026-10-26 (step 202,
   engine/housepost): a play rated 8+ goes into its game's chat from the
   site's own account, on the play's thread, six a game at most.
3. **Call it ladders and badges.** BUILT 2026-10-26 (step 203): This week
   and Season ladders on the Call it card (ten graded calls to stand on
   one), a flame from three in a row beside a handle in the chats, and a
   share at every five in a row.
4. **The room against the math.** The who-wins vote charted through the
   game against the live win chance: "the room had CIN at 30% when the
   math had them at 70%". Built from: chat_votes snapshotted every few
   minutes (one new table) + the deep file's `wp`. Small to medium.
5. **What has to happen.** Under each live leg of a saved ticket, one
   sentence from the box: "Chase needs 14 more yards; he's at 9.7 a catch
   tonight." Free (box facts); the chance stays the membership's. Small.
6. **Recap by push.** BUILT 2026-10-26 (step 204, engine/finals): the
   final, the play of the game and the best line (the page's own words),
   on a new "Final scores of games I follow" switch.
7. **Your fantasy lineup, live.** Sleeper and ESPN leagues are linked
   already: the starters' lines on the Your players strip and the matchup's
   live score. Built from: the linked rosters + engine/yourplayers. Medium.
8. **Watch-party rooms.** A private thread inside a game's chat for a
   friend group, by invite link. Built from: engine/gamechat rooms + an
   invite token; the moderation is already there. Medium.
9. **Spoiler-free later.** Hide scores across the site for chosen games
   until tapped, for watching a recording. Built from: a per-game flag on
   the device. Small to medium.
10. **Crew watch.** Penalties and the strike zone tallied live against the
    crew's season norm. Built from: the plays' penalty rows + the referee
    assignments already read. Medium.
11. **Trivia in the stoppages.** At a timeout or between innings, one
    question off the season logs ("Who leads CIN in receiving yards?"),
    answered in the chat. Built from: the season logs the boards read.
    Medium.

---

## 2026-10-24: from other apps, for the stores — ranked

Ethan: *"think like an app developer, think like a website developer ...
look at other apps and look how they function and run and look at cool ideas
and tools that can make our app better."* Looked at: Apple Sports (praised
for restraint and speed; its standouts are widgets and Live Activities),
Action Network (line alerts — "Line Watcher" — and automatic bet import),
and what an installed web app can do now. Built today from this list: the
app-icon badge, the share-a-slip target, push alerts, the first screen that
holds still, Liquid Glass on the Duo. The rest, best value first:

**Run better**

1. **Shell from the cache, data from the network.** The service worker
   fetches the app's own code network-first, so an installed app on a weak
   signal waits for the network before it shows anything. Store apps open
   instantly from what they have and update behind. The boards and prices
   stay network-only (sw.js's first two rules); only the code would come
   from the cache, refreshed in the background, renamed on every deploy by
   the VERSION hash already there. *Half a day; the biggest felt speed-up
   left for the store app.*
   **BUILT 2026-10-24** (sw.js `appMode`, register-sw.js): an installed app
   keeps every file of the version and opens from it with no signal; a tab
   keeps the shell only. tests/test_the_app_opens_offline.py.
2. **Split app.js further.** Measured today: evaluating it is a ~270 ms
   freeze at phone speed, on every first visit. Rocket Radar moved out
   today (~7 KB gz). Next, by size: the Fantasy room (draft kit, mock draft,
   usage: ~20 KB gz), the account and paywall pages, the team pages — each
   loaded the first time it opens, as the Feed and the Toolbox already are.
   Target: under 400 KB gz. *A day or two; tests read the moved code.*
   **BUILT 2026-10-24, first cut**: the Fantasy room (186 functions, 4,412
   lines) and its styles moved to fantasy.js/fantasy.css, the meme pages'
   styles to memes.css: app.js 494 → 451 KB gz, a first visit 620 → 570.
   Under 400 still wants the account pages and team pages next.
   **BUILT IN FULL the same night**: the Record page, the game, pick and
   play-by-play pages, the account pages and the More menu's rarer pages
   each load the first time they open (record.js, detail.js, account.js,
   more.js; app.js loadRoom, with a reload rather than a mix of versions
   when a new one is out): app.js 451 → 284 KB gz, a first visit 570 → 399.
   tests/test_a_room_loads_when_its_page_opens.py.
3. **The first game's stadium photo** is the largest thing on the first
   screen and lands last (3.3 s on a slow phone). Preload it as soon as the
   board says which it is, or paint a 1 KB blurred copy first. *An hour.*
   **BUILT 2026-10-24**: the first card's photo is `fetchpriority="high"`,
   the rest lazy.
4. **Style recalculation** is the next cost after the script (0.6 s at
   phone speed): the stylesheet is 463 KB before trimming. Split the lazy
   pages' styles out the way gamecast.css is, and drop selectors that match
   nothing (Chromium's coverage tool lists them). *A day.*
   **PART BUILT 2026-10-24**: 336 rules moved out with the Fantasy and meme
   pages. Dropping unmatched selectors is still open.
   **BUILT 2026-10-25**: each room's styles moved out with its code
   (css/record.css, detail, account, more): styles.css 73 → 57 KB gz, a
   first visit 399 → 383 KB gz. Unmatched selectors: none to drop. The only
   ones that matched nothing were the chart library's own classes and
   colour classes built at run time. tests/test_a_rooms_styles_are_its_own.py
   keeps each room's sheet to classes only that room draws.
5. **Brotli** instead of gzip for the trimmed files: ~15% fewer bytes. Caddy
   needs a plugin for it, or the files pre-compressed at build. *An hour on
   the box.*
   **BUILT 2026-10-24, as zstd** (stock Caddy has no Brotli; zstd beats
   gzip and Caddy encodes it itself): `encode zstd gzip`, and level-9 gzip
   twins written beside the trimmed files (engine/shrink) and served
   pre-compressed. Live once the Caddyfile is installed (runbook DN).

**Look**

6. **Liquid Glass for the iOS app itself**: a floating capsule tab bar (iOS
   26's own look) and glass sheets for the More and Bet panels — the Duo's
   material, carried to every iPhone in the store app. *Half a day.*
   **BUILT 2026-10-24**: the iOS build and an iPhone Home Screen app float
   the tab bar as a glass capsule; the More and Bet sheets are glass on
   touch screens. No blur. tests/test_the_iphone_app_wears_its_own_glass.py.
7. **A lock-screen-style "riding" pill.** The riding tray (bets on games in
   progress) as a Dynamic-Island-shaped pill pinned under the bar, live
   score inside. *Half a day.*
   **BUILT 2026-10-24**: a centred night-glass pill above the bar, its dot
   breathing for readers who allow motion. The real lock-screen version is
   item 11.
8. **Team colours for "my team".** Pick a club in settings; its colours tint
   the bar, the glass rim and the Live disc. *Half a day.*
   **BUILT 2026-10-24**: Settings → Team colours (off by default): the bar's
   edge, the Live disc and the lit tab, the team you follow in this league.

**Features other apps have**

9. **Watches by push** (Action's Line Watcher). The Alerts page already
   matches player, team and edge watches against the feed
   (engine/alerts.py), and phones can now be knocked. A watch that fires
   becomes an alert for the member who set it. *A day; paid members only,
   the feed is a paid file.*
   **BUILT 2026-10-24** (engine/pushmine): the member's own words and a
   count, never the pick; members only; quiet hours held.
10. **Your own bets by push**: your game is starting, your bet just settled.
    Needs My Bets kept on the server for signed-in members (the account sync
    exists). *A day.*
    **BUILT 2026-10-24** for saved parlays (the slip watch already grades
    them every minute): on, last leg, settled. A bet logged by hand has no
    games to follow.
11. **iPhone widgets and Live Activities** (Apple Sports' two best things):
    tonight's top pick and the record on the Home Screen; a bet's game on the
    lock screen. Native code (WidgetKit, ActivityKit) in the iOS shell, fed by
    the same APNs key. *Several days, on the Mac; after the app is accepted.*
    **BOX HALF BUILT 2026-10-24**: /api/widget (engine/widgetfeed) and Live
    Activity updates from the slip watch (engine/webpush.apns_live). The
    Swift is written in deploy/ios/native, not compiled here; the Mac steps
    are in deploy/ios/README.md.
12. **Calendar**: an .ics feed of the games you have picks on. *Two hours.*
    **BUILT 2026-10-24** (engine/calfeed): Settings → Calendar, your teams'
    games and your open parlays' games; the address is the key.
13. **The record offline**: record.json and My Bets readable with no signal
    (read-only, dated). *Two hours.*
    **BUILT 2026-10-24**: the Record page's copy is kept for no signal and
    says when it was kept; My Bets was already on the phone.

**Tools for building and testing**

14. **Real devices.** Nothing here can run Xcode, Instruments or TestFlight:
    those need a Mac and the Apple Developer Program, and they are worth it
    once you have both — TestFlight for a beta group, Instruments for the
    iPhone's own frame timings. For Android, Play's internal testing track
    and Firebase Test Lab's free tier run the TWA on real phones. Until then
    the nightly run opens every page in Chromium on five screen shapes and
    measures the first screen at phone speed.
    **WRITTEN UP 2026-10-24** in docs/APP_STORES.md, "Testing on real
    phones".
15. **Lighthouse in the nightly run**, beside the probe added today, so a
    slower night shows up as a number rather than a feeling. *An hour.*
    **BUILT 2026-10-24** (tools/lighthouse_check.py, the nightly run):
    baseline 67 on Lighthouse's phone setting.
    **2026-10-25**: accessibility, best practices and SEO are scored in the
    same runs, and the audit that night fixed what they found (the closed
    drawer reachable by keyboard, a skipped heading level, five pages whose
    name an element also had, so a link scrolled past the page's top; a
    page that shifted as it loaded). The new baseline: performance 81,
    largest paint 4.9 s, blocked 97 ms, shift 0, accessibility 100, SEO 100.


## The rule this list is filtered through

A feature earns a place only if its numbers can be **derived from
something we already hold or can legitimately fetch**. Anything whose
centre is a number somebody would have to invent belongs in the last
section, and stays there until the data exists.

That rule already killed three obvious ones: a "trade acceptance
percentage" (no proposal has ever been logged, so there is nothing to
fit), a "confidence score" on a projection (nothing fits it), and an
opposing-defence panel inside a draft (there is no opponent).

---

## 1. Auction values — SHIPPED 2026-08-26

**What:** a dollar figure per player for auction and salary-cap leagues,
which are a large minority of drafts and got nothing from the kit.

**Built from:** VORP, which we already compute. The standard construction
is real arithmetic, not a guess: total budget across the league, minus one
dollar per roster slot, divided across the sum of positive VORP. Every
term is ours.

**Cost:** small. One function in `fantasy_draft.py`, a column on the
board, a budget input on the page.

**Why it is first:** draft season is now, it is the only format the kit
cannot serve at all, and nothing has to be invented.

**SHIPPED**, as `engine/auction.py` and the draft kit's Snake/Auction
switch: a budget input, dollars in place of the VORP column on the
overall board and in the tier cards, and a bar showing where the room's
money goes by position.

Two things the estimate above did not see, both found by running it:

* **The baseline could not be borrowed.** Reusing the kit's VORP priced
  the top pick at $136 of a $200 budget, because the snake board
  measures against the best free STARTER — right for a snake, where you
  stream the wire, and wrong for an auction, where every bench spot in
  the room is bought. Auction values are priced against the last man
  DRAFTED (QB18 / RB54 / WR66 / TE18 in a standard twelve-team room),
  which is a whole module rather than the one function this entry
  predicted. The top of the sheet now lands around 30% of a manager's
  budget and a test refuses anything outside 15–45%.
* **The sheet has to balance.** Rounding each row on its own drifts, and
  values totalling more than the league can spend are wrong by however
  much they overshoot — you find that out in the last three rounds, with
  a roster you cannot fill. Whole dollars are handed out by largest
  remainder, so the priced players plus a dollar for every remaining
  roster spot come to exactly the money in the room.

What it deliberately does NOT do is predict what a player will GO for.
We have never logged an auction, so there is nothing to fit an inflation
curve to, and the panel says so.

---

## 2. Waiver-wire and streamer board — SHIPPED 2026-08-26

**What:** every week, who to add and who to start from the free-agent
pool — the question a manager asks fourteen times a season versus once at
the draft.

**Built from:** `fantasy_lineup.per_game` for the pool, the injury board
for who just lost a job, `preseason.camp_report`'s depth-chart diffing
(already written, already tracking daily) for who just won one, and the
game scripts for the matchup. All four exist.

**Cost:** medium. Mostly assembly.

**Why:** the draft kit is a two-week product. This is the one that keeps
somebody coming back every Tuesday from September to December.

**SHIPPED**, as `engine/waivers` and the Fantasy page's Waivers tab: the
two role-change lists (jobs vacated by an Out/Doubtful/IR skill player,
ranked by the share the beneficiary already holds; and the biggest
share JUMPS against a four-week baseline). The Sleeper add/drop pulse
moved in beside them — market attention and our own signal, same
question of two sources, and they frequently disagree.

DELIBERATELY NOT CLAIMED: availability. Without league sync (idea #7)
"free agent" is a guess with a number beside it, so the board measures
role change and says plainly that it cannot see your league. A test
pins the refusal.

THE STREAMER HALF SHIPPED THE SAME DAY: `waivers.streamers` joins the
usage rows to `fantasy.game_scripts` and ranks each position by share x
the market's implied team total, tilted by pass-rate over expectation.
It is a ranking of SPOTS and says so — there is no per-week points
model here, and dressing the number as one would be the invented
precision this project refuses.

QUARTERBACKS ARE NAMED-ABSENT rather than quietly missing: every share
in this data is targets or carries, which a QB has neither of, so his
row would score ~0 and rank last — an absent measurement reading as an
opinion. Streaming a QB is nearly pure team environment and needs a
depth chart to say who starts; guessing that is how a board recommends
a backup.

---

## 3. "What changed since you last looked" — ALREADY BUILT (noted 2026-08-26)

**What:** a single strip at the top of the board naming what moved since
the reader's last visit — lines that moved past a threshold, picks that
appeared or disappeared, players newly ruled out.

**Built from:** `odds_history` and `engine/linetape.py`, both live. The
reader's last-visit timestamp is a `localStorage` value.

**Cost:** small.

**Why:** the site currently answers "what is true now" and never "what is
different". Returning readers re-read the whole board to find the two rows
that changed.

**THIS SHIPPED and the entry went stale.** It is `freshBannerHTML` in
web/js/app.js — the last-visit clock in `localStorage` (`qb_seen_ms`),
the feed's events filtered to that gap, and a strip reading "Since you
last looked (2h ago): 3 edges appeared, 2 prices moved." It has company:
`applyFreshPulses` flashes the individual rows whose side, line, odds or
projection moved since the last poll, and the welcome-back banner names
bets that settled while you were away. Left on the list, it was two
hours from being built a second time — which is the cost of a roadmap
that does not get read back against the code.

---

## 4. Bet-slip export — SHIPPED 2026-08-26

**What:** a copyable summary of the picks a reader wants to place, so
they can key them into their own book without re-reading the board.

**Built from:** the recommended board.

**Constraint, and it is absolute:** this site takes no wagers. Not a
slip, not a "Place Bet", not a balance, no "To Win" figure. This is text
to copy, and the tests that forbid a betting interface stay exactly as
they are. If that line feels thin, do not build it.

**Cost:** small. **Value:** removes the most obvious friction between
reading a pick and acting on it.

**SHIPPED**, on both surfaces: the picks card and the parlay slip each
carry "Copy as text". The line held — no stake enters either export, so
no payout can be derived from one, which is a stronger promise than
forbidding the words; a test asserts the absence structurally.

ONE REFUSAL THE PLAN DID NOT ANTICIPATE: a leg priced off our own proxy
baseline copies as "no book price yet", and a parlay containing one
shows NO combined price. Text that leaves the site and lands next to a
real betting slip is the last place a placeholder should wear the shape
of a real number.

---

## 5. A public model-versus-market scoreboard — SHIPPED 2026-08-26

**What:** one page answering "does this thing beat the closing line",
cut by sport and market, with the sample size beside every number.

**Built from:** the CLV work already in the ledger and `engine/coverage.py`.

**Cost:** medium, mostly presentation of numbers that exist.

**Why:** it is the single most persuasive thing a paid product can show,
and it is persuasive precisely because it can come out badly.

**SHIPPED** as `engine/clvboard` + the Record page's "Model vs market"
room. Three rules make it worth trusting, and all three are about
declining to flatter:

* the SAMPLE SIZE rides beside every number (closes/settled per row);
* below `ledger.CLV_MIN_N` the row still SHOWS its average and refuses
  to CALL it — hiding a number until it looks good is the failure this
  page exists to refuse, so `ready` is a separate field from the value;
* a market with settled picks and NO stored closes gets a row saying it
  cannot be graded. That silent absence is precisely how the touchdown
  board hid a broken harvest for its whole life (found and fixed the
  same day, and it now shows here as 0-of-N until closes accrue).

It has its own three-column grid rather than the record board's
`.rb-row`, which is built for five and hides its CLV column on phones —
borrowing it put the verdict in the wrong slot and then made it
invisible exactly where it matters most.

---

## 6. Alerts that fire on a condition — SHIPPED 2026-08-27

**What:** "tell me when a line I care about moves past X", delivered to
the phone.

**Built from:** the Routines infrastructure and the push path already
wired for the nightly summary.

**Cost:** medium — the condition language is the hard part; keep it to
three shapes rather than building a query builder nobody uses.

**SHIPPED**, as `engine/alerts.py` plus a Watching card at the head of
the Alerts page and a count on the nav. Three shapes, exactly as
insisted: a player, a team, or an edge size.

**The shapes were not a language problem.** The entry expected the
condition grammar to be the hard part and it was not, because the shapes
are not free — each has to be answerable off a field `engine/feed.py`
already publishes, or a watch would be re-deriving what the board
already decided. That constraint picked the three. The team shape needed
one new field on the event (the digest held the row's team and dropped
it on the way out); the other two were already there.

**Matching is stateless and happens on read.** A watch is a filter over
the published feed, not a subscription that has to be delivered — so
nothing fired is stored, a watch added at noon applies to the whole
window immediately, one deleted stops mattering the same second, and the
alert list can never drift from the feed it came from.

**The trap was the edge shape.** An `edge_died` event is the moment an
edge stopped existing, and firing "6% edge" on it would be a
notification about the opposite of what was asked for. Two tests hold
that line.

**Delivery is honest rather than promised.** The push half of the
original entry is not possible here — see the Web Push refusal below —
and the page has always said it is not a push service. What a watch buys
is the count on the nav before you open anything, and your three rows
above the two hundred that are not yours. Email is the next honest step:
the nightly digest already runs and already has a mailer.

---

## 7. Head-to-head league sync — SHIPPED 2026-08-27

**What:** read the reader's actual league — their roster, their
opponent's, the standings — and answer start/sit against the team they
are actually playing this week.

**Built from:** the Sleeper public API, already fetched daily.

**Cost:** medium-large.

**Note:** Sleeper only. ESPN and Yahoo need session cookies or an OAuth
app, and this repo does not take credentials.

**SHIPPED**, as `engine/fantasy_h2h.py` plus a head-to-head panel and a
standings table on the League Desk. The desk answered every question
against the FIELD before this; a head-to-head league is one game against
one roster, and which start is right depends on the scoreboard as much
as on the projection.

The estimate said medium-large and the shape was the surprise. Reading
the league was the easy half — Sleeper's own `matchups/{week}` board
names the opponent and `settings.leg` names the week, so nothing had to
be guessed from a calendar. The half worth building was the UNIT: the
answer is a MARGIN with a spread around it, not two totals, and the
spread had to be measured. `fantasy_lineup.per_game` now carries `_sd`,
each player's own week-to-week standard deviation, with his position's
pooled spread standing in for anyone too thin to have one — a rookie
with two identical games would otherwise report certainty.

What falls out for free is the part worth reading: ranking bench swaps
by their effect on WIN PROBABILITY rather than on points reproduces the
advice every fantasy column gives — favourites want floors, underdogs
want ceilings — without anybody writing that rule down. The same roster
gets opposite advice at +12 and −12, and nothing in the module knows the
words favourite or underdog. Two tests run exactly that.

Two things in it are approximations rather than counts, and the panel
says both: the margin is treated as normally distributed, and the two
lineups as independent. When your quarterback is throwing to their
receiver they are not — and this app measures fantasy correlation
nowhere, so it is flagged rather than fudged.

---

## 8. A "why is this board empty" panel, everywhere — DONE 2026-08-26

**What:** every empty state names the reason and the fix.

**Built from:** the status fields already emitted (`odds_status`,
`injury_status` shipped 2026-08-20).

**Cost:** small, spread thin.

**Why:** an empty board and a broken board look identical today on most
pages, and the difference is the whole trust question.

**DONE.** `engine/census` gives NFL and CFB the funnel MLB and the hoops
boards already had — the two that were missing it, with a football
season opening. The football census counts the FIRST failing gate off
each row's own `checks` list (engine/rules.condition) rather than
recomputing the thresholds the way MLB's older one must, so it cannot
drift from the decision it explains, and an unnamed new gate renders as
itself instead of vanishing. CFB's board is game bets, whose rejections
carry a written reason rather than a checks list, so it buckets those
sentences through the same digit-stripping the hoops board wrote —
which now lives in `census.reason_key` and is CALLED by hoops rather
than copied.

---

## Skew-aware yardage distributions — the measured upstream fix, 2026-08-25

The first deep NFL calibration (81,000 settled games walked forward)
measured a bias ladder that is really a skewness ladder: passing yards
unbiased, receptions −0.28, receiving yards −0.56, rushing yards −0.98 —
a stated 50% landing at 27%. The cause is structural: `prob_over` prices
every market with a symmetric normal centred on the projection's MEAN,
and yardage-per-game is right-skewed — one 45-yard breakaway drags a
season mean above the median game, so most games land under it. The more
boom-driven the stat, the bigger the bias, which is exactly the ladder
the fit found. The same wound showed from a second angle the same day:
formfit's rushing dial pinned to its grid edge wanting maximum recent
lean, with its own warning that wanting more than the family allows
means a problem upstream.

**What holds the line today:** the calibration layer, which is the
designed absorber for exactly this and now carries the correction per
market, refit nightly. It is honest but blunt — one intercept per
market cannot vary with where the line sits relative to the mean, and
the symmetric tails still feed `proj_low`/`proj_high` and the sim lab's
redraw.

**The real fix:** price yardage markets on a right-skewed family
(lognormal, or an empirical quantile map fitted from the same logs the
calibration used — the data is already in history.db). **Built from:**
`engine/statmath.prob_over` grows a per-market family switch;
`logwalk`'s walk-forward is the free judge of whether it beats
normal+intercept out of sample. **Cost:** medium, and it is a
MODEL_ERAS entry when it ships — every claim on three markets moves.
Not a pre-Week-1 change; the calibration is the right risk this week.

---

## CFB closing lines — CLOSED 2026-08-26

The season-readiness audit made the nightly closing-odds harvest
journal-driven (engine/maintenance._harvest_targets): any night MLB or
NFL bets journal, their closes are harvested for exactly the markets
bet, and CLV + process grades accrue. CFB WAS the deliberate exception,
and the blocker was a TEAM MAP, not the API: the odds-history parsers
key every price through `SPORT_CONFIG[sport]["teams"]`, and CFB's map is
built at run time from the ESPN feed inside cfb_build — 134 schools is
the kind of table that rots on paper, so it was never hardcoded. A
harvest would have stored school names no settle pass could join.

DONE, and the fix was the one written here: `engine/cfbteams` persists
every name cfb_build resolves to `data/feedstate/cfb_teams.json`
(accumulating across builds, so the table grows into the season rather
than shrinking to whichever dozen schools played that night),
`oddshistory.teams_for` reads it PER CALL so a long-running process
cannot hold the empty map it booted with, and "cfb" is in
`_HARVEST_SPORTS` behind `_cfb_map_ready()` — no map, no spend.

TWO THINGS THE PLAN DID NOT SEE, both found while building it:

* **The free closes were never taken.** `engine/lineledger` writes game
  lines to `odds_history` on every build at zero credit cost, using the
  board's OWN abbreviations — so it never needed the name map at all.
  MLB and NFL had called it since it was written; cfb_build never did.
  Its moneyline/spread/total bets had therefore been settling with no
  close available even on days a harvest ran. That is now the primary
  CFB close path, and the paid harvest is the top-up for player markets.
* **`resolve_market_keys` dropped the scorer markets**, so a
  journal-driven harvest on any night an anytime-TD pick was journaled
  asked for a market key named `anytime_td` — which the API does not
  have. NFL was affected too and had been since the TD board shipped:
  the touchdown board has never had a closing line. Fixed by inverting
  the same scorer map the live parsers use.

---

## Web push — measured and refused, 2026-08-26; shipped without a payload, 2026-10-24

**2026-10-24: it shipped** (engine/webpush, engine/pushalerts, sw.js), for
the app stores — Ethan's call, the native feature iOS review asks for. The
refusal below was right about a push that CARRIES its words: those must be
ECDH-agreed and AES-GCM-encrypted to the browser. This push carries none.
The box signs an empty request (VAPID: one ES256 signature) and the phone's
service worker asks the site what to say over the site's own HTTPS. So of
the three primitives only the signature is needed; it is written out in
plain Python (RFC 6979 deterministic nonce, the RFC's own vector in the
tests, cross-checked against the `cryptography` package) and the box uses
`cryptography` instead whenever it has a working copy. What the key guards
is small — it can send our subscribers an empty knock — and it signs only on
the background cycle, never on a request a stranger can time.

The original entry, as written:


Roadmap #8 asked for it ("an edge alert that hits a lock screen") and it
is the one delivery mechanic that did NOT ship with the others, on
purpose rather than by omission. The Web Push protocol (RFC 8291/8292)
requires P-256 ECDH key agreement and AES-128-GCM payload encryption
plus ES256-signed VAPID tokens. **The Python standard library has none
of those primitives**, and this repo is stdlib-only by doctrine — the
alternatives are adding a crypto dependency (a decision bigger than one
feature) or hand-rolling elliptic-curve cryptography, which is the
single worst category of code to write yourself on a site that holds
accounts. What shipped instead covers most of the distance: the feed is
the alert stream, the return banner says what happened while you were
gone, and the PWA install keeps the site one tap away. If push is ever
worth a dependency, `pywebpush` + a `push_subs` table beside the
accounts is a two-day build on top of the feed that already exists —
the events are the hard part, and they are done.

---

## Referees — measured and refused, 2026-10-17

The officials were a data source the site had never read, and nflverse's
games file names every NFL game's referee. `refcheck.py` asked the only
question that decides whether they are worth wiring: does a referee's past
predict a game's total against the CLOSING total, or its margin against the
closing spread, in a season his estimate never saw? On 7,340 games (2015 to
week 4 of 2026): no. Held-out correlation −0.02 on totals and −0.01 on
margins at every shrink tried, and worse than predicting nothing in 8 to 10
of 11 seasons. The closing number already has whatever a crew does. Not
wired; nflverse fills the referee only after the game in any case. NBA and
NHL crews wait on closing totals the box has only just started keeping
(engine/lineopen); the same script shape answers them when there is a season.

## Team volume from the line — measured, small, recorded 2026-10-17

The loss autopsy names usage/volume the step most often wrong, so
`volumecheck.py` asked how much of an NFL team's volume the line knows
before kickoff. On 4,316 team-games (2016-2025), held out by season:
adding the line's implied team points and the spread to a team's own and
its opponent's recent volume cuts the error 0.5-1.5% (dropbacks better in
6 of 7 seasons, carries 7 of 7). Each implied point is about +0.4
dropbacks and −0.2 carries; each point of favour −0.2 dropbacks, +0.26
carries. The floor is high (about eight dropbacks a game whatever is
known), so the volume the autopsy blames is mostly the player's share, not
the team's total. Not wired: the projection's script step already carries
the spread's part, and a 1% gain counted twice is worse than none.

## In-game live win probability — SHIPPED 2026-09-09

**This entry used to be three lines below, under "needs data we do not
have": "Needs play-by-play at a latency we do not have."** That was true
on 2026-08-20 and stopped being true on 2026-09-05, when #136 put fast
live scores on NFL, CFB, NBA and WNBA, #137 put MLB play-by-play on the
same clock, and #138 landed football drives off verified ESPN shapes.
The blocker was retired by other work and nobody came back to the list —
which is the ordinary way a list rots, and the reason this note replaces
the entry rather than quietly deleting it.

**What it is built from:** `engine/livewp.py`, and nothing new. The
remaining margin is Normal(mu, sd) with `mu` the pregame expected home
margin times the fraction of the game still to play, and `sd` the
sport's own `gamebets.MARGIN_SD` times the square root of that fraction.
P(home) is the normal CDF of the current margin plus that mean over that
SD. The SD is the same constant the pregame moneyline is priced from, so
this is the game model read from later in the evening rather than a
second opinion with its own numbers to drift.

**What it costs:** nothing per game. No fetch, no credits, no store — it
is arithmetic over the score, the clock and a line already on the card.

**What it cannot do, and says so on every row.** No possession, no down,
no distance, no timeouts. Three points up with the ball and forty
seconds left is a win; three up having just punted is a coin flip; this
prints the same number for both. `possession_blind` marks that window
(one score, under five minutes) and the row carries the sentence.

**Football and baseball only, for now.** `gamebets.MARGIN_SD` has a
measured final-margin SD for those and none for the hoops boards, and
`_sd` refuses rather than borrowing another league's variance. The
regulation clock for NBA and WNBA is in the table already; measure their
margin SD and both turn on with no change to the module.

**Not a price.** Nothing bets or journals off it. The day it becomes an
input to a stake it needs the measurement against real in-game closes
that it has never had — the same bar in `docs/THE_INFORMATION_TEST.md`
that every other new input had to clear.

---

## Ideas that need data we do not have

Kept so they are not re-proposed every month.

* **Trade acceptance probability.** Needs a corpus of proposed and
  accepted trades. `log_proposal` writes one; ask again after a season.
* **A confidence score on a projection.** Nothing fits it. The floor and
  ceiling on the draft card are the honest version.
* **Ownership and leverage for DFS.** Needs contest ownership data, which
  is paid and licence-restricted.
* **Beat-writer and news sentiment.** Needs a text corpus and a fitted
  model; without both it is a vibe with a number printed on it.

---

## Where the real constraint is

Not ideas. Nearly everything above is assembly of things already built.
The binding constraints are the ones no branch fixes: Phase 0 in
`docs/LAUNCH.md`, the Paddle verification, and the Michigan question.
Those gate *charging money*, not shipping features, and they are named in
`docs/NEXT.md` and `docs/WHEN_HOME.md`.

## Hold journal for the other one-sided markets — CLOSED 2026-08-26

engine/holdwatch measures the one-sided hold for NFL anytime-TD by
journaling the whole quoted board and settling it against the weekly TD
rows. MLB home_runs and CFB anytime-TD are the same Yes-only shape and
still price off the assumed 6% (`longshots.ONE_SIDED_HOLD`). Joining
them was mechanical, and DONE: mlb_build journals the home-run board,
cfb_build journals the TD field, and `maintenance.HOLD_MARKETS` settles
and refits all three nightly. Each market fits its OWN hold — a
touchdown book and a home-run book do not price the same juice.

TWO SHAPES THE PLAN ASSUMED AWAY, both found on the way:

* **The journal was NFL-shaped.** It stored an INTEGER `week` and
  formatted it "%03d" to join — so no MLB or CFB quote, whose stat rows
  are keyed by DATE, could ever have settled. `period` is TEXT now and
  holds exactly what `player_game_logs.period` holds. The old table was
  a day old and had never settled a row, so it is dropped and recreated
  rather than carried.
* **CFB's board is not a slate.** Its TD pull returns quotes keyed by
  player, never Props, so `record_quotes` reaches the same journal by
  the other door — and those keys are NORMALIZED names, which is why
  settle now normalizes the stat side too.

The nightly settle also moved OUT of the NFL-season guard it was written
inside: baseball settles from April, and a pass that only ran Aug–Feb
would have binned a summer of quotes.
