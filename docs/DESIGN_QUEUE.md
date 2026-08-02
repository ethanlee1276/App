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

- [ ] **Emoji are not an icon set.** 42 emoji-bearing text nodes carry real
  meaning right now — 🏟️ ⛰ 📅 🔴 ✓ ✕. They render differently on every
  platform, they cannot take the page's colour, and they are the single
  loudest "assembled quickly" signal left. Replace the load-bearing ones
  with inline SVG that inherits `currentColor`, matched to the hand-drawn
  style already in `web/js/visuals.js`. Status marks (✓ ✕ 🔴) first — they
  appear most and matter most.
  *Constraint:* do not import an icon library. Lucide-in-a-pastel-circle is
  the exact thing the audit was checking for; trading one tell for another
  is not progress.

- [ ] **Density contrast inside a card.** Section spacing now has three
  levels (34 / 14 / 0). Inside a card everything is still evenly spaced, so
  a card's most important number reads at the same weight as its footnote.
  Pick the one number per card that the card exists to communicate, and let
  the rest recede — size, weight, and colour, not borders.

- [ ] **Fewer, larger.** Recommended shows four stat tiles of equal size, so
  none of them is the answer. Decide which single number a person opens this
  page to see, and make the layout say so. This is a composition change, not
  a token change.

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
