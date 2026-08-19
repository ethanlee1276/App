# Design queue

A worklist for the scheduled design pass. Each run takes **the first
unchecked item**, does that item and nothing else, ships it as one
reviewable commit, and ticks the box in the same commit.

One item per run is the whole discipline. A pass that touches three things
produces a diff nobody reads, and an unreviewed design change is
indistinguishable from no design change.

## Protocol

1. Read this file. Take the first `- [ ]` item.
2. **Measure before you touch anything.** Every item below names the number
   it is about. Reproduce that number first — if it does not reproduce, the
   item is stale: say so, tick it with a note, and stop. Instruments live in
   the scratchpad pattern used throughout this repo: a fixture server over
   `web/`, Chromium via Playwright at `/opt/pw-browsers/`, and a script that
   counts what actually *renders* rather than what the stylesheet claims.

   **Two rules the emoji item paid for.** Sweep *every* sport, not two: a
   two-sport census reported zero leaks while 42 were rendering elsewhere.
   And walking DOM text nodes does not see `::before { content: … }` — check
   `getComputedStyle(el, '::before').content` too, or grep the stylesheet.
   Both blind spots let real defects through a sweep that came back clean.

   **Measure the BEFORE on the same instrument.** Serve `git show HEAD:…`
   from a second port and run the identical script against both. A before
   number from a narrower script and an after number from a wider one is
   not a delta.

   **Check the instrument measures the ITEM.** The density pass built a
   per-card "does anything dominate" score, made the change, and the number
   did not move at all — because the card's most prominent element was the
   player's name both before and after, and the item was about the *numbers*.
   A metric that cannot move when the work succeeds is as useless as one
   that cannot fail. If the number does not move, suspect the ruler before
   the change.
3. Make the change. Re-measure. **The number has to move**, and you have to
   say what it moved to.
4. Screenshot at 390px and 1280px. Look at them. A measurement that improves
   while the page gets worse is a real outcome and the reason this step is
   not optional.
5. `python3 run_tests.py`. Add tests that pin the new state.
6. Commit with the before/after number in the message. Tick the box. Push to
   `claude/sports-betting-app-vhgmho`.
7. If an item turns out to need a judgement only Ethan can make, do not
   guess. Leave it unticked, write what you found under it, and move to the
   next item.

Never redesign something not on this list. If you find a new tell, add it to
the bottom rather than acting on it.

---

## Queue

- [x] **One type ramp.** DONE — 32 rendered sizes → 20: nine ramp tokens,
  seven SVG graphics sizes (a separate system inside small viewBoxes), and
  four derived from relative rules. 196 stylesheet declarations and 83
  inline ones now go through tokens; no raw px survives in either. Nine
  steps not seven, because the large end is role-differentiated — tile
  value, chart number, brand, profile name. **The item's premise was partly
  wrong and is corrected in the tests: the fractional sizes are not
  accidents.** 8.2/11.6/12.76 come from three deliberate relative rules
  (`.5em` unit suffix, `1.24em` emphasised metric, `.9em` rank chip) that
  are supposed to track their parent. They stay. Only one genuine oddity
  existed — an 8.2 SVG monogram belonging to no scale — now 8.

  ~~The rendered pages use **32 distinct font sizes**,
  including fractional accidents: 8.2, 10.8333, 12.325, 12.76, 17.98. That
  is not one ramp; it is no ramp. Collapse to ~7 steps, defined as tokens,
  and map every rule onto them. The fractional ones are the tell — nobody
  chooses 12.76px, it is what a percentage did to an inherited size.
  Expect this to move text on every page; screenshot widely.
  *Constraint:* the 11px caps section labels and the mono number sizes were
  both deliberate. Do not flatten them into the body ramp.~~

- [x] **Emoji are not an icon set.** DONE — **2352 → 506 rendered
  occurrences, 26 → 13 distinct**, measured over 176 pages (8 sports × 11
  views × 2 widths). Every glyph the item named is now at zero: 🗓 (240),
  ✓ (178+650), 🌙 (176), ✕ (134), ⚠ (90), 🔍 (42), ✗ (16+108), 🏟, ⛰,
  🛒, ⏳, ➖, ✅, ⛔, 🔴, ☁. 6146 drawn icons render in their place.

  **The item's number was low, and the reason matters more than the fix.**
  It counted 42 emoji-bearing *text nodes*. Two whole classes were
  invisible to that instrument:
  1. `content: "✓"` in the stylesheet — generated content is not a text
     node. Those two rules alone rendered **758 times**, more than every
     emoji on the Recommended page combined, and they survived a 176-page
     sweep that reported clean. They are now masked SVG, so
     `background-color` still drives the green/red split and the light
     theme.
  2. A census over two sports reported **zero literal leaks** while
     **42** were rendering on the other six — `<svg …>` printed as visible
     angle brackets, because `gameContext` handed an icon-bearing string to
     `escapeHtml`. Breadth is not optional; `tests/test_icons.py` now
     catches both classes at source level with a lexer, plus a negative
     control proving the detector can fail.

  Two icons were drawn wrong and only the **screenshots** said so: a bowl
  seen from above (two concentric ellipses) reads unmistakably as an **eye**
  at 13px. Made that same mistake twice — the venue chip and the dome wind
  gauge — and caught it both times at step 4, never at step 3.

  Deliberately left, so a later pass does not "fix" them: arrows (→,
  typography between two numbers), the sport logos, the 34px empty-state
  and About-page pictograms, and the lucky-clover chip (a tone choice; the
  drawn set is deliberately austere). `test_the_illustration_exemption_is_narrow`
  bounds that allowance so it cannot quietly grow.

  ~~42 emoji-bearing text nodes carry real
  meaning right now — 🏟️ ⛰ 📅 🔴 ✓ ✕. They render differently on every
  platform, they cannot take the page's colour, and they are the single
  loudest "assembled quickly" signal left. Replace the load-bearing ones
  with inline SVG that inherits `currentColor`, matched to the hand-drawn
  style already in `web/js/visuals.js`. Status marks (✓ ✕ 🔴) first — they
  appear most and matter most.
  *Constraint:* do not import an icon library. Lucide-in-a-pastel-circle is
  the exact thing the audit was checking for; trading one tell for another
  is not progress.~~

- [x] **Density contrast inside a card.** DONE — measured over 358 metric
  rows (8 sports × 10 views × 2 widths), before and after on one instrument:

  | | before | after |
  |---|---|---|
  | hero size ÷ supporting size | **1.09×** | **1.47×** |
  | rows under 1.2× | 348/348 | 0 |
  | hero colour distinct from siblings | 314/348 | 358/358 |
  | emphasis carried by a box | 348/348 | **0** |

  **The item's framing was slightly off and the correction is the useful
  part.** It reads as "pick the one number" — but the site had *already*
  picked it on every card type, and said so with a border: HIT PROB ·
  **EDGE** · EV/UNIT, MODEL · BOOK IMPLIED · **EDGE**, POSITION · ENTRY ·
  **NOW**. So the work was not choosing; it was saying it with type instead
  of chrome, which is what the item's own constraint asks for.

  It looked chosen and wasn't, because of a unit bug that reads as correct:
  `font-size: 1.24em` on the hero resolves `em` against the **parent**
  (`.metric`, at the card's 15px), not against the 17px its siblings are set
  in. A rule written to mean "24% bigger than the other numbers" rendered at
  **18.6px against 17px**. Nobody sees 1.6px; everybody sees the box.
  `test_type_ramp.py` had been *defending* that rule on the rationale that
  it "tracks its parent" — corrected in place rather than deleted, because
  the mistake is worth keeping visible.

  Weight is not one of the levers here: these numbers are in the mono face,
  which ships 400/500 only, so 800 gets synthesised. Size and colour do it.

  Two things measurement forced that reading would not have:
  - **Five rows had no hero at all** — the 4-up long-shot row and the
    fantasy buy-low row both *have* the number (Edge, Gap) and never marked
    it. Unfixed, they'd have been the only rows where the supporting values
    shrank with nothing rising.
  - **Not every metric row is a hierarchy.** The NFL game-script card shows
    "CHI implied" beside "GB implied" — one quantity, both sides of a game.
    Receding half a comparison just makes it quieter. The recession is
    scoped through `:has(.metric.primary)`, and degrades to "hero still
    leads, by less" where `:has()` is unsupported.

  **Left undone deliberately:** the hero still does not outrank the card's
  *title* (player/team name, 17px/800) — 0/358 before and after. 30px was
  tried and screenshotted: the hero fills its tile edge to edge while the
  supporting tiles go mostly empty, and the row reads lopsided rather than
  ordered. Whether the number should lead the whole card is a composition
  question — which is exactly the next item.

  ~~Section spacing now has three
  levels (34 / 14 / 0). Inside a card everything is still evenly spaced, so
  a card's most important number reads at the same weight as its footnote.
  Pick the one number per card that the card exists to communicate, and let
  the rest recede — size, weight, and colour, not borders.~~

- [x] **Fewer, larger.** DONE — **dominance ratio 1.000 → 1.773 mean, and
  boards where every tile is the same size AND width 10/10 → 0/10**, measured
  across five sports at 1280px and 390px. Before: four tiles, every value
  30px, every column 307px. After: the lead at 34px in a 1.7fr column, the
  other three at 22px in 1fr columns; on a phone the lead takes its own
  full-width row above the three.

  **The number chosen is Recommended bets.** The page is called Recommended
  and the question it is opened with is "what am I betting tonight". Props
  analyzed is how much was considered to get there, avg edge is how good they
  are, exposure is what they cost — all three are context FOR the count, so
  they now read as context. It leads when it is zero too: "no qualifying
  plays" is this board's most common correct answer and a large honest 0 says
  so.

  Solved with composition, per the item — no new type token. Scoped to
  `#stats`: the first version styled the shared `.stats` class, which
  eleven containers use — the Record page's eight KPI rows among them — so
  pinning it to four tracks pushed the Record page's fifth tile onto a
  second row as an orphaned box, on desktop and phone both. A test now
  forbids writing a lead rule against the bare class.

  Two more things the screenshots caught that the metric could not: a second `@media` breakpoint
  further up the file lost silently to the 760px block, so the phone grid
  stayed at two columns while the new rule said three; and "Suggested
  exposure" wraps in a narrow column, dropping its number 17px below the
  other two so the row of context read as a staircase.

  ~~Recommended shows four stat tiles of equal size, so
  none of them is the answer. Decide which single number a person opens this
  page to see, and make the layout say so. This is a composition change, not
  a token change.~~

---

## Blocked — needs Ethan

- **The site has no point of view.** This is upstream of every item above
  and no amount of token cleanup fixes it. The design is competent and
  neutral; every individual choice is the safe one. Real designed things
  make a choice that costs something. Unblocking this needs a *reference* —
  screenshots of two or three products Ethan actually likes the look of, or
  a Figma file — so the work has a direction to move toward instead of being
  re-derived from first principles every time. **Do not attempt this item
  without that reference.** Ask, then wait.

---

## Done

<!-- Move completed items here with the before → after number. -->

- **The header came apart at both ends of the width range.** Not a queue
  item — reported directly ("this area on the screen is all bugged out and
  also is taking up WAY too much space") and fixed on the spot, recorded
  here because the measurements are worth keeping.

  Three faults, independent of each other:

  1. **`flex-wrap: wrap` lived in `@media (max-width: 1799px)`** while the
     two-row layout asks for `.brand { flex: 1 0 100% }`. A 100%-wide item
     on a nowrap row cannot take a line of its own, so at 1800px and up the
     switcher wrapped to **four** rows inside a crushed brand and the page
     nav overflowed its box by 274px, printing on top of the running-ROI
     line and the status chips. Every width *below* 1800 was fine, which is
     why it survived: it only shows on a monitor bigger than the one it was
     designed on.
  2. **`.sport-group` was `display: contents`**, so all eleven buttons were
     direct children of the switcher and the row could break inside a
     group — the markets pair split at 960px, the record pair at 1100, 820
     and 768. The separator hairline then sat on whichever button started
     row two.
  3. **The More menu was left-anchored at every width** on the reasoning
     that "More" always has the menu's width to its right. It did not: at
     1280 the menu ran 119px past the viewport and gave the whole page a
     horizontal scrollbar. Pre-existing, and the widths listed as checked
     in that comment include the one it fails at.

  Header height, before → after, on a **return visit** (the state the site
  is used in — `.brand-home` is hidden by the compact masthead):

  | width | before | after | | width | before | after |
  |------:|-------:|------:|-|------:|-------:|------:|
  | 1800  | 263 | **196** | | 960 | 279 | **222** |
  | 1440  | 196 | 196     | | 900 | 254 | **197** |
  | 1280  | 232 | 232     | | 820 | 254 | **248** |
  | 1024  | 229 | **223** | | 768 | 254 | **248** |

  No group splits at any width, and no menu clipping or page horizontal
  scroll from 762 to 1800. First visit improves too (306 → 299 at 960,
  317 → 259 at 900) but stays tall on purpose — that state is the pitch.

  Pinned by `tests/test_headerwrap.py`, including a source-order assertion:
  the first cut of the fix put the switcher override ~470 lines *above* the
  rule it overrides, where four of its five declarations were silently
  dead. The layout improved anyway, because one surviving declaration was
  doing all the work — so the measurement looked like a success while most
  of the change did nothing. **A before/after number cannot tell you that a
  rule applied.** When a CSS change lands in a file this long, check where
  it sits relative to what it is overriding.


- [ ] **The masthead tagline is capped at 21 characters by a rule that says
  34.** `.tagline` is `max-width: 34ch` with `letter-spacing: .22em` and
  `text-transform: uppercase`. `ch` is the width of a "0" with NO tracking,
  so the spacing makes every rendered character wider than the unit the cap
  is counted in: measured at 1280px the element wants **292px and is given
  155px**, showing "THE NFL BOOK — THE P…" out of "The NFL Book — the
  pro-bettor prop model". Just over half.

  The intent and the effect disagree, which is what makes this a defect
  rather than a taste call — but the repair is a number somebody has to
  choose, so it is here rather than done. The masthead has free space at
  1280 and above; the cap exists to stop the brand block crowding the nav
  at smaller widths, and below 900px `.tagline` is display:none anyway.
  Options: raise the cap, express it in `em`, or drop the ellipsis and let
  the second line wrap. Measure the header height at every width in
  `test_headerwrap.py` before and after — that file exists because this
  block has broken twice.

  *Found 2026-08-19 while reading rendercheck's screenshots; not acted on,
  per the "never redesign something not on this list" rule.*

- [ ] **The sidebar guillotines its last line instead of fading it.** The
  rail is `overflow-y: auto`, so nothing is lost — but at 1280×1100 its
  content is **1201px in a 1036px box**, and what a reader sees is the
  running-ROI note sliced through the middle of "book price and graded in
  public" with no visible scrollbar (overlay scrollbars on most platforms).
  It reads as broken rather than as "there is more below". Present on every
  view, at every height under about 1250px.

  A bottom `mask-image` fade on the scroll container is the usual answer and
  costs nothing, but it is a look nobody has approved and it is not in the
  render pack — hence here. Whatever is chosen, check it against the phone
  drawer too, which uses the same element.

  *Found 2026-08-19, same pass. Measured, not acted on.*
