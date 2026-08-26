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

## 2. Waiver-wire and streamer board (in-season, matters from Week 1)

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

---

## 3. "What changed since you last looked"

**What:** a single strip at the top of the board naming what moved since
the reader's last visit — lines that moved past a threshold, picks that
appeared or disappeared, players newly ruled out.

**Built from:** `odds_history` and `engine/linetape.py`, both live. The
reader's last-visit timestamp is a `localStorage` value.

**Cost:** small.

**Why:** the site currently answers "what is true now" and never "what is
different". Returning readers re-read the whole board to find the two rows
that changed.

---

## 4. Bet-slip export — for the sportsbook, never here

**What:** a copyable summary of the picks a reader wants to place, so
they can key them into their own book without re-reading the board.

**Built from:** the recommended board.

**Constraint, and it is absolute:** this site takes no wagers. Not a
slip, not a "Place Bet", not a balance, no "To Win" figure. This is text
to copy, and the tests that forbid a betting interface stay exactly as
they are. If that line feels thin, do not build it.

**Cost:** small. **Value:** removes the most obvious friction between
reading a pick and acting on it.

---

## 5. A public model-versus-market scoreboard

**What:** one page answering "does this thing beat the closing line",
cut by sport and market, with the sample size beside every number.

**Built from:** the CLV work already in the ledger and `engine/coverage.py`.

**Cost:** medium, mostly presentation of numbers that exist.

**Why:** it is the single most persuasive thing a paid product can show,
and it is persuasive precisely because it can come out badly.

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

## 8. A "why is this board empty" panel, everywhere

**What:** every empty state names the reason and the fix.

**Built from:** the status fields already emitted (`odds_status`,
`injury_status` shipped 2026-08-20).

**Cost:** small, spread thin.

**Why:** an empty board and a broken board look identical today on most
pages, and the difference is the whole trust question.

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
