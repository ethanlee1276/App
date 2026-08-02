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

## Outstanding — things the prototype fakes

Both must be closed during migration rather than shipped as-is.

- **§5.3 `material`.** The flag that gates every amber stroke is supposed to
  be computed upstream — true when the condition actually moved a number for
  at least one play at that venue. The prototype derives a stand-in from
  thresholds (wind ≥ 8mph, altitude ≥ 3000ft, any roof). Wiring the real
  flag is a build change in `engine/`.
- **The conditions column in the past-performance table.** §6.4 asks for
  WIND on NFL and PARK on MLB. The slate's game logs carry
  `{week, opponent, value, home}` and nothing about conditions, so the
  column is omitted rather than filled with em dashes. `engine/` has the
  weather per game; it has to reach the payload first.
