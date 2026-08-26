# Ideas — what this site could add next

Ethan, 2026-08-20: *"think of more ideas to add to th website."*

Written as a working list, not a wish list. Every entry says what it is,
**what it would be built from**, and what it costs — because the ideas
that die here are the ones that need data we do not have, and it is
cheaper to find that out in a document than in a branch.

Ordered by *value per unit of work*, not by size.

---

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

## 1. Auction values — the last snake-only gap in the draft kit

**What:** a dollar figure per player for auction and salary-cap leagues,
which are a large minority of drafts and get nothing from the kit today.

**Built from:** VORP, which we already compute. The standard construction
is real arithmetic, not a guess: total budget across the league, minus one
dollar per roster slot, divided across the sum of positive VORP. Every
term is ours.

**Cost:** small. One function in `fantasy_draft.py`, a column on the
board, a budget input on the page.

**Why it is first:** draft season is now, it is the only format the kit
cannot serve at all, and nothing has to be invented.

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

## 6. Alerts that fire on a condition, not a schedule

**What:** "tell me when a line I care about moves past X", delivered to
the phone.

**Built from:** the Routines infrastructure and the push path already
wired for the nightly summary.

**Cost:** medium — the condition language is the hard part; keep it to
three shapes rather than building a query builder nobody uses.

---

## 7. Head-to-head league sync for the fantasy page

**What:** read the reader's actual league — their roster, their
opponent's, the standings — and answer start/sit against the team they
are actually playing this week.

**Built from:** the Sleeper public API, already fetched daily.

**Cost:** medium-large.

**Note:** Sleeper only. ESPN and Yahoo need session cookies or an OAuth
app, and this repo does not take credentials.

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

## Web push — measured and refused, 2026-08-26

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
* **In-game live win probability.** Needs play-by-play at a latency we do
  not have.

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
