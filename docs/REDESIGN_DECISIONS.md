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
