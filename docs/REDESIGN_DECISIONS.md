# Night Form — decisions that override the spec

The redesign spec (`REDESIGNSPEC.md`) is the direction. This file records
the places the build deliberately departs from it, and why. Without it, the
next pass reads the spec, sees the code disagreeing, and "fixes" the code.

Each entry is a decision that has already been made. Do not re-open one
without Ethan.

---

## 1. Green and red stay. Amber's job narrows.

**Spec says** (§3.1, §8.2): *"Never introduce: emerald/`#22c55e`"*, and
routes every favourable number through amber — *"Positive EV, edge values,
winning results, CLV gains, active nav item, live/material venue conditions
→ amber"*.

**We do instead:**

| | means |
|---|---|
| **green / red** | a **number** is favourable or against you — edge, EV, hit prob, wins, losses, CLV |
| **amber** | a **condition** is live or material — the LIVE badge, wind that moved a line, a roof, the active nav item, the data-mode pill |

**Why.** Ethan reads this board every night and green/red for won/lost is
the one convention he does not want re-taught. It is also a *better*
encoding than the spec's: two orthogonal things — "is this number good" and
"is this condition live" — were being pushed through one accent. The spec
half-noticed this itself, warning that more than ~8 amber elements on a
screen means something is being decorated rather than encoded. Splitting
them keeps amber under that bar honestly rather than by rationing.

The green is `#33C77A` dark / `#12734B` light — slightly deeper than the
site's current `#34d399`, because bone on `#08090B` is a hotter surround
than the old near-black panel. Red is the spec's own brick.

**The spec's actual concern was never green.** It was emerald-on-near-black
with 12px rounded cards and four KPI tiles — a whole stack. In agate type
at zero radius, a green number does not read as generated.

---

## 2. Venue cards stay, front and centre on Recommended.

**The spec contradicts itself here.** §1.3 lists every venue-card field as
must-survive: the venue diagram, the LIVE badge with period and clock, team
badges and names, live score, line summary, date and kickoff, the live
situation line, the wind compass dial, temperature and wind, the per-game
link, and horizontal scroll. §7 then says *"Venue cards → conditions strip
+ engraved marks"*.

**§1.3 wins.** A preservation contract outranks a layout suggestion. The
first prototype followed §7 and measurably dropped 205 strings against the
live page.

The cards are the **first block on Recommended**, directly under the nav,
where they are on the live site — not below the summary tiles. They are
re-cut as engraving, not deleted, and every field is verified rendering.

The conditions strip is **not** on Recommended. §6.5's own words are that it
*"gives the venue marks a permanent home outside the Recommended page"* — so
it belongs on the other fifteen views, where there are no cards. Two venue
surfaces on one page duplicated the information and pushed the cards down.

---

## 3. The light theme is derived from Direction 03.

**Spec says** nothing. Night Form is dark-only, and §1.1 lists the theme
toggle as must-survive. That is a gap, not a decision.

**We do:** derive light from Appendix A Direction 03 "The Form" — `#F2EFE6`
paper, `#14120E` ink, brick `#C8102E` — so both modes are one design at
inverted value rather than two products. Amber darkens to `#B87400` because
`#FFB000` on paper fails contrast.

---

## 4. Tailwind and React are translated, not adopted.

§4 ships a `tailwind.config.js` and §5.3 a TSX `<VenueMark />`. This site
has no build step, no npm at runtime, no React and no Tailwind — it is
vanilla, and that is load-bearing: it renders with the network unplugged.
The tokens are CSS custom properties and `VenueMark` is a function that
returns SVG. Same design, expressed in the stack that exists.

---

## 5. The prototype's last three ideas are declined, not pending.

Decided 2026-08-02, after rendering the prototype and the live page side by
side. These had sat unresolved long enough to look like a backlog; they are
not one. **The prototype is now a record of what was adopted, not a list of
what is owed.**

### §6.4 the entry block — NOT adopted

The prototype renders each pick as a three-column entry: a 96px venue-mark
gutter, the pick with a projection-vs-line rule and a recent-form table, and
a 200px right rail carrying the hero number. Six picks is roughly six
screens.

**We keep the compact ranked list.** The list answers "what am I betting"
in one screen, which is the question the page exists for, and every field
the entry block shows already lives behind the per-pick `why?` panel. The
detail is not missing; it is one click away instead of always open.

### Agate tables — the premise was stale

The item read "0 of 9 converted". It does not reproduce: **32 rules already
set `font-variant-numeric: tabular-nums`**, so the site's numeric columns
already line up. The instrument that produced "0" was reading the first cell
of the first row, which is a player name — the same class of ruler error the
design queue's own protocol warns about ("suspect the ruler before the
change").

What is genuinely undone is the prototype's mono *voice*: 10.5px monospace
with dotted row rules. **Declined.** It is a large legibility cost on a
board read nightly, for a stylistic gain, and figures that align already
carry the function the agate treatment was for.

### §6.2 masthead right block — NOT re-cut

The prototype has a right-aligned uppercase edition line with a mono
timestamp. The live masthead has the data-mode pill, the updated stamp, the
date and the theme toggle. **The pill stays**: it is the at-a-glance
live-vs-cached signal, and §9 lists the data-mode pill as promoted and never
hidden — the edition treatment would bury it. The spacing in this block was
also tuned in response to a specific complaint about crowding; disturbing it
needs a reason better than a prototype.

---

## Closed — the two things the prototype used to fake

Both are computed by the build now. Kept here because the *reasoning* is
the part worth not re-deriving.

### §5.3 `material` — the flag that gates every amber stroke

`engine/pipeline.py::_conditions` (NFL) and `engine/mlb/pipeline.py::_conditions`
(MLB). The prototype used thresholds — wind ≥ 8mph, altitude ≥ 3000ft, any
roof — and that answers a **different question**. It says the condition is
*big*, not that it *did anything*. A 20mph wind at a venue whose only priced
prop is a market the wind model never touches moved nothing, and the mark
should be dim; a threshold cannot tell those two cases apart.

What ships instead: ask the model for its own per-market multipliers
(`evaluate_weather`, `evaluate_park`), keep the ones that are not 1.0, and
intersect with the markets **actually priced at that game tonight**. The
reasons shown on the card are the model's own sentences, so the mark and the
card cannot disagree about why it is lit.

Two cases that shaped it:

- **A roof is material on its own terms.** `evaluate_weather` returns flat
  multipliers for a dome *because* nothing else applies, so materiality
  cannot come from the multipliers there. §5.1: "the absence of weather is
  information."
- **Wrigley.** Its park factors (hr 1.04, run 1.02) sit under
  `evaluate_park`'s own thresholds, so the building moves nothing — but
  16mph blowing out is the most famous wind effect in baseball, and the
  park's own profile text says to check the wind before anything else there.
  Weather is priced in the **home-run** model, not in `evaluate_park`. The
  first version flagged that game material with an **empty reason list**,
  which is precisely what §5.1 forbids: an amber stroke encoding nothing.

### §6.4 the conditions column — WIND for NFL, PARK for MLB

- **MLB needs no new data source.** A game log already records the opponent
  and whether the player was home, and those two facts name the venue
  exactly (`parks.park_of_game`). The HR factor rides along, because "Coors"
  only means something if you know it plays +22%.
- **NFL needs a join.** The weekly player feed carries no weather at all;
  the `games` table does. `db.nfl_game_winds` keys on `game_id`, which is
  `AWAY@HOME`. The lookup tries **both** orderings rather than trusting
  `log.home`, because nflverse weekly rows have no home flag and `GameLog`
  defaults it to `True` — a lookup that believed it would miss every away
  game.
- **The season is not the calendar year.** Week 18 of the 2025 season is
  played in January 2026. Keying on the year sent every January slate
  looking in a season the database had not started, and the column came back
  empty. `nfl_season_of` cuts at March.

Where the data genuinely is not there the column is **omitted**, not filled
with em dashes — a blank column looks like the data is missing rather than
not applicable.

## 6. `--text-mute` was one token doing two jobs. Now there are four.

Closed 2026-08-07. This sat open as an explicit "a person has to decide
this" for good reason — it could not be fixed by changing a colour.

**The fault.** `--text-mute` measured **Lc 15** on every dark ground, which
APCA calls the point of invisibility, across **223 uses** — 108 in the
stylesheet, 114 in the inline styles `app.js` writes, one in the social
card. Not decoration either: `.section-title`, `.tile .k` (the label on
every metric tile), `.matchup .away`, `.pick .book`, `.game-sub.starters`.
`--text-dim` was also under its own target, at Lc 51 against 60.

Being exact about the standard, because it is easy to borrow the wrong
argument here: this was **not** a case of WCAG flattering a dark pair. It
measured 2.57:1, which fails AA for large text (3.0) as well as normal
(4.5). Both algorithms agreed.

**Why it could not be repaired in place.** Lc 60 needs L 0.761 and
`--text-dim` was L 0.708. Lightening the quiet tier to its target would
have made it brighter than the tier above it and inverted the hierarchy.

**The repair is a fourth step, not a brighter third one.**

| token | Lc | role | was |
|---|---|---|---|
| `--text` | 90 | body text, preferred | unchanged |
| `--text-dim` | 60 | larger or secondary text | 51 |
| `--text-mute` | 45 | large or bold UI | 15 |
| `--text-faint` | 30 | disabled or decorative | new |

APCA's own reference targets, one tier apart, each solved against
`--panel-3` — the lightest panel, where contrast is lowest and therefore
binds — plus ~0.8 Lc of headroom. The headroom is not fussiness: solved to
exactly 45.0, the mute tier measured 44.7 on `--panel-3` and the audit
filed it under "decorative".

**The split defaults to readable, and that direction was chosen.** All 223
sites stayed on `--text-mute` and rose to Lc 45. Only five genuinely
non-text marks were demoted to `--text-faint`: the card's 4px grade
stripe, the parlay-miss stripe, two separator glyphs, and the empty-state
icon. Sorting 223 sites by hand in the other direction — quiet by default,
promote individually — would have left anything missed invisible. This way
anything missed is merely too legible.

**The disclosure chevron stayed on `--text-mute` deliberately.** It is a
control affordance, not decoration, and Lc 45 ("large or bold UI") is
exactly its target. The thing that tells you a section opens should not be
fainter than the section.

**Paper did not get the same ladder.** Measured, the light theme's
`--text-mute` is already Lc 52-64 and its `--text-dim` Lc 76-87, both above
target. Copying the dark side's numbers across would have made the light
theme worse, so only the fourth tier is new there.

**Still open, and deliberately not folded in:** `--bad` measures Lc 36,
under the 45 large/bold bar. Negative-EV and error text is set in it. That
is a colour with a job rather than a rung on a hierarchy, so moving it is a
palette decision and belongs in its own pass. `--text` also sits at Lc 89.9
on `--panel-2`, a rounding hair under APCA's *preferred* body bar — the
minimum is 75 — and was left alone because changing the colour every line
of prose is set in is a bigger change than a hierarchy repair.

`tests/test_contrast.py` pins the ladder as an **order**, not as four
floors. Four independent floor checks would stay green through an
inversion, which is the exact failure this started as.

---

## THE NEW LOOK — 2026-08-11, Ethan's render

Ethan drew the site he wanted (a dark violet sportsbook-style dashboard:
left rail of destinations, slim top bar, stadium cards, a Top Picks
strip, a performance dashboard, insights + live-now in a right rail) and
said: **"go new look … copy my render and ship it fully. make sure to do
mobile as well."** This supersedes Night Form's aesthetic decisions
wholesale. It is the owner's call, made looking at both.

**Excluded by Ethan, and by what this site is:** the balance chip and
the bet slip. There is no "Place Bet", no deposit, no wagering balance
and no "To Win". `tests/test_newlook.py` pins that. The slip-shaped needs
are served honestly: My Bets (your own log, synced to your Qellys
account) and Bankroll (your unit sizing).

**Corrected 2026-08-15.** This section used to say "this site never holds
money", full stop, and that sentence was doing two jobs. Ethan: *"we will
be accepting money for people to use the website once it is complete."*
So, precisely:

* **The site will charge for access.** A subscription is planned. That is
  ordinary software business and nothing on this page argues against it.
* **The site still takes no WAGERS.** No balance to deposit into, no bet
  placed here, no payout owed by us. That is what the excluded chip and
  slip were about, and it is the part with legal weight rather than
  design weight — accepting a wager is a licensed activity in most US
  states, and charging rent for software is not.

The two got written down as one rule, which is how a business decision
ended up looking like it had been settled by a design review.

**What the pivot changed** (each with its receipt in the tests named):
- Violet-cast neutral ramp + violet accent; the warm one-hue rule became
  a violet one-hue rule — the invariant (ground and ink agree, span
  < 40°) survived, the band moved (`test_design_tells`).
- The MARK is gold; the interface is violet (`test_newlook`,
  `test_brand`). favicon/touch icon re-rasterized from the tokens.
- Shadows and gradients are legal, but only through tokens
  (--glow/--glow-soft/--grad-*/--skeleton) — one light, one system.
- Radii came back as three tokenized steps (8/12/14) — same "no picking
  9 AND 10 AND 11" discipline, non-zero values.
- Text tiers re-solved with APCA on the new grounds (faint was Lc 13
  when eyeballed; shipped at 31+). --brand stopped being a text colour;
  --brand-2 (Lc ~50) carries accent text, and every `color: var(--brand)`
  moved to it.
- The header's four generations of layout CSS (~49KB) were deleted, not
  overridden. Sidebar = drawer = one element. The nav-indicator, More
  menu, masthead-brief, compact-nav and phone menu-grid all retired.
- Home = the render's dashboard: stadiums → Top Picks → tonight's tiles
  → Your Performance (real journal, losses in red) → the full board.
  Board-order pins updated with this paragraph as the receipt.

Display face: Archivo Narrow 700 (already self-hosted) wears the
wordmark and display duties; Bodoni stays only in og-card.

## Venue render art — 2026-08-11, Ethan's contact sheet

"Ok can you just plug them in for me?" — a 4×6 sheet: six lighting
colours each of a football stadium, basketball arena, baseball park and
UFC octagon. Sliced (web/img/venues/variants/, 2× lanczos + unsharp
from the 1536px sheet) and wired as the middle rung of the card's art
chain: team-specific photo → colour-matched family render → drawn
scene. The render is picked by the home team's first colour with real
chroma (nearest of red/gold/green/blue/violet; neutral kits → steel —
the 0.22 chroma bar exists because the White Sox' warm near-black
otherwise read as gold). Families: football serves NFL+CFB, basketball
serves NBA+WNBA, baseball serves MLB. Live games still always draw —
ball spot, bases, wind. UFC has no home team, so the card page banners
one octagon hash-picked from the event identity: same card, same arena,
different cards rotate. Overwriting a variants/ file with a full-res
version of the same render upgrades every card with no code change.

## The render-sheet pass — 2026-08-11, Ethan's 12 mobile panels

"We should be matching these pages too a tee. Obviously we won't use
some of the pages like the settings page or rewards." The honest subset
shipped: My Bets became the sheet's card list (status chips, sport
filter, legs, stake → to-win arithmetic on the user's own price); the
Results page grew the analytics header (1W/1M/3M/ALL range chips whose
NET / WIN RATE / ROI are computed inside the window — pnl_curve now
carries per-day wins/losses/stake so a 1-month chart never sits above
all-time numbers); the Live board's cards grew the per-team
SPREAD|TOTAL|ML grid (no side juice is invented — cells without a real
number show a dash); the Props page leads with one tile per market
actually priced tonight, tap to filter; game-card art carries the
sheet's temp·wind chip when a real reading exists. Excluded on the
standing no-WAGERS rule: the bet slip, Place Bet, deposits, balances,
plus Rewards and Settings by Ethan's own word. (That rule is about taking
bets, not about taking payment — see the correction above.) The analytics pass also
caught and fixed a crasher: the ALL window's Infinity days reached
toISOString and the resulting throw blanked the entire Record page.

## The desktop sheet — 2026-08-11, Ethan's 10 web panels

Same contract as the mobile sheet ("match everything perfectly", minus
what we never build): the event page grew the venue-photo hero, a GAME
LINES table off the slate's own numbers and a KEY INSIGHTS panel that
renders the game's data fields (injuries, wind, park factors, lineup
status) — never ATS narratives we don't compute. The Live board becomes
full-width rows on desktop (score story left, line grid right). The
Results analytics gained the chart-plus-rail layout and an all-time
footer: total staked, total returned, average price (mean implied
probability re-expressed as American odds — a plain mean of +150 and
−110 is arithmetic on two different scales), longest win streak, all
journal-computed in engine/ledger.performance. Bankroll gained the goal
bar (user's own two numbers) and a logged-P&L-over-time chart read from
My Bets. The topbar gained the avatar chip — initials when signed in —
with no balance chip beside it, ever. The Home board keeps Ethan's
typed order (top picks → stadiums → performance) over the render's
stadiums-first arrangement: an explicit instruction he gave about this
exact question outranks a generated mock until he says otherwise.

## The Zeno sidebar — 2026-08-12, Ethan's render

"I like all the page options it offers so let's follow suit." The
sidebar regrouped to the render's shape — Dashboard + Live Now, then
RESEARCH / MODELS / MY TOOLS — with every previous destination
surviving (the preservation baseline re-swept). New in RESEARCH:
Game Lines and Watchlist open Home's own sub-tabs through the subnav's
real buttons (and correctly do nothing special on a night whose room is
empty); Weather is a new page built from the slate's own conditions
plus the desk's NWS-vs-Kalshi board, hidden for leagues with no weather
feed. New in MY TOOLS: Alerts, a digest of line movement, the injury
watch and the desk — rebuilt each refresh, explicitly NOT a push
service. MODELS lists the real specs by their real names (Scalpy 2.0,
the NFL book, Scalpy MMA), each opening its league. Not copied: the bet
slip, the Upgrade card (nothing here is for sale), Zeno's green accent
(our violet system is pinned), and decorative NEW badges — the only
badge is the live count, which is true. The nav-btn binder also gained
the missing-view guard: anchor items wear the class for its looks and
fell through to switchView(undefined).

## The full-res venue renders — 2026-08-12, the WebP miner blind spot

The nine renders Ethan sent "a little more zoomed in" turned out to
have been in the session transcript the entire time: they arrived as
WebP, and the extraction pattern only recognised JPEG (`/9j`) and PNG
(`iVBOR`) base64 magic — `UklGR` never matched, which is why "which
ones didnt you get" had the answer "none of them, until the pattern
learned RIFF." All seven uniques recovered at ~1536-1774px.

Cutting them retired the brightness-band slicer: the new sheets butt
tile-to-tile with zero dark gutter, so the cutter became a colour-seam
hunt — a straight line whose two sides disagree in colour along its
ENTIRE length (second-smallest of eight per-segment jumps, chroma
direction rescuing dark-on-dark night skies) is a grid seam; a field
or court edge dies toward the corners and fails the tail test. One
ambiguity survived: a stadium's own rim wall IS a full-width straight
colour edge (football-neutral scored 82.5, true seams 39.8-131). No
local metric separates those, so the filename became the contract —
`colors`/`sheet`/`grid` means cut, anything else is one render, never
cut, and `-neutral` pins steel. All 24 variants rebuilt at 1000-1536px
(was ~460px upscaled); octagon-6 stays the desaturated blue until a
real neutral octagon render exists. Old dark-gap splitting died for a
reason worth remembering: night renders carry genuinely pitch-black
full-width sky bands, and a threshold that finds gutters also finds
those.

## One prediction board, three rooms — 2026-08-12

"Combine the kalshi and polly market board. There is too much too
scroll through and they are basically the same thing." As PRICES they
are: both venues sell event contracts quoted in cents, and reading them
as two stacked tables meant scrolling past one to compare against the
other. So venue became a COLUMN, the two tables became one, and the
single ranking is 24h volume — the one measure both venues report the
same way.

What did NOT get flattened is where they actually differ. Kalshi runs a
two-sided book we can price against, so those rows carry our number and
the gap; Polymarket publishes a trade tape with wallet identity, which
answers "who is betting", not "what is it worth". A Polymarket row
therefore shows a dash in the model and edge columns. Filling that
column with a number nobody computed would be exactly the fake symmetry
the merge was supposed to remove — and it is why the desk's
recommendations now say out loud that they are all Kalshi.

The scroll itself was three questions stacked: what to bet, who is
betting, whether the flow signal has ever been right. Three subtabs,
measured at 1280x900 — 2.75 screens stacked became 1.37 on the tab that
opens. The venue chip is deliberately NOT colour-coded: amber is the
one accent and it means "live or material" (§1), which a venue name is
not, so the word does the work.

## Standings: the league's table, not our count — 2026-08-12

"This is not live or real data at all. We need too fix that so our
standings pages displays the actual standings of the current seasons LIVE
DATA." The tell was in the table: MLB clubs carrying TIES — 70-69-1,
66-68-4 — in a sport that has none, with the White Sox atop the AL
Central on a .504 record.

Two causes, both real. Standings were COUNTED from the games we had
ingested, which answers "what do our rows say" rather than "what are the
standings"; on a partially-ingested season those are different numbers,
not rounded ones. And the count treated any equal-score row as a tie, so
every unfinished, postponed or unscored game became half a result that
moved games played, win percentage, differential and the order.

The league's own feed is now the primary path — statsapi for MLB, ESPN's
v2 standings for the other four, both keyless and both already trusted
elsewhere here. The count stays as the FALLBACK, and the payload stamps
which one ran: a computed table now wears a banner saying so and carries
the feed's error, because a fallback that looks official is the whole
defect. `--standings` prints LIVE or ours per sport.

What we deliberately do not take from the feed is the grouping or the
order — divisions come from our own table and the sort from our own key,
so one envelope moving cannot reorganize a league or make the page
disagree with itself. And last-ten is the league's number where it sends
one, a dash where it does not: the empty ordered run was rendering as
"0-0", which reads as a measured record of nothing.
