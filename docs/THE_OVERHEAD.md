# The Overhead — the distinctive asset constitution

The venue diagram has a name now: **the Overhead**.

A plan view of where the game is being played, engraved, with the
conditions a price was set in drawn around it. One per game, on every
board. "Tonight's overheads." "The Bills–Chiefs overhead."

This file exists so the thing stops moving. Everything below is either
**LOCKED** (do not change without Ethan) or **VARIES** (driven by live
data, changes every game by design). That distinction is the whole
document — it is the one thing the research on generative identity is
unambiguous about, and the one thing that decides whether this asset ever
becomes recognisable.

---

## 0. Why the name is "the Overhead"

Three candidates were weighed against four criteria: not venue-bound,
survives a sentence, carries the engraving lineage, no collision with
vocabulary already in use (Book, Board, Form, Lab, Record, Zone, ledger,
slate).

**"The Overhead" names the encoding, not the object** — a plan view — so
it extends to any market, including the ones with no building. That was
the deciding criterion. "The Plate" scored higher on engraving lineage
(a plate is what banknotes and old newspaper cuts are printed *from*) but
`app.js` already says "at the plate" and "plate appearances" in MLB copy.
"The Grounds" was clean but venue-bound, which fails a six-sport site.

Checked: `grep -i overhead` over `web/` returns nothing. The word is free.

---

## 1. What is LOCKED

Per Ehrenberg-Bass, recognition is built by repetition, not novelty. The
documented failure mode of a generative identity is that variability eats
recognition — MIT Media Lab's 40,000-permutation mark was retired after
about three years for exactly this. The systems that survived (Whitney's
locked name position, Nordkyn's fixed compass form, Casa da Música's fixed
faceted silhouette) all froze a frame and varied only the inputs.

So:

| Locked | Value |
|---|---|
| **Line language** | Outline only. No fill, no gradient, no wash. `stroke-width: 1.1` for structure, `1` for surfaces and hatching. |
| **Ink** | `--text-mute` for structure, `--border` for surfaces and hatching, `--text-dim` for labels, `--text` for figures (`text.num`). Nothing else. |
| **Radius** | Zero. `rx: 0; ry: 0` on every rect in the art. |
| **Type** | `--font-mono` on every label, one weight (400), one opacity (1). |
| **Colour exception** | Exactly one, per REDESIGN_DECISIONS §6.13: team colour survives as a flat block behind the monogram, at `opacity: .5`, so you can still tell whose building it is. |
| **Accent** | Amber follows the house rule (REDESIGN_DECISIONS §1): a **condition** being live or material, never a number. The Overhead is conditions, so amber appears here — but on the LIVE badge and the wind bearing, not on the structure. |
| **Canvas** | `240 × 150`, `preserveAspectRatio="xMidYMid meet"`. Every renderer shares it. |
| **Where each datum sits** | Park/stadium name top-centre. Roof state top-centre above it. Plaques bottom corners — altitude bottom-left, HR factor bottom-right. Score, clock and situation belong to the card, not the art. |

**Frozen means frozen.** The research is unanimous that consistency, not
novelty, is what builds recognition, and Tropicana is the cautionary
number: about 20% of unit sales — roughly $30M — gone in seven weeks, from
replacing a distinctive asset with a better-looking one. The temptation to
redraw this because you have looked at it a thousand times is the single
biggest risk to it ever working. You see it far more often than anyone
else ever will.

---

## 2. What VARIES

Only live data. Nothing aesthetic.

Roof state (dome / closed / retractable-open) · surface · park HR factor ·
altitude · wind bearing and speed · temperature · which building.

That is the entire list. If a change is not one of these, it is a change
to the frame, and the frame is locked.

---

## 3. The renderers, and the bug this document was written next to

Three functions in `web/js/visuals.js`, **two** classes:

| Function | Sport | Class | Drawn with |
|---|---|---|---|
| `stadium()` | NFL, CFB, WNBA | `.stadium` | 31 `<line>`, 10 `<circle>`, 10 `<rect>`, 2 `<ellipse>`, 2 `<path>` |
| `ballpark()` | MLB | `.stadium` | **13 `<path>`**, 6 `<rect>`, 2 `<line>`, 2 `<circle>` |
| `court()` | NBA | `.field` | 4 `<path>`, 3 `<rect>`, 2 `<line>`, 2 `<circle>` |

The engraving layer re-skins from the stylesheet rather than by rewriting
the drawing code — SVG presentation attributes sit at the bottom of the
cascade, so CSS beats them, and this way no label can be silently dropped.
Good decision. But it shipped with `.field path` and **no `.stadium path`**.

`court()` was fine because it is a `.field`. `stadium()` was fine *by
accident* — it happens to draw its bowl in lines and ellipses. `ballpark()`
draws its stands, outfield fan, mow stripes, wall, infield dirt, infield
grass and plate as paths, so the entire re-skin slid off it. Computed
fills came back `rgb(31,125,65)` and `rgb(42,157,84)`: the raw greens out
of `visuals.js`.

Net effect: the site's most distinctive asset was rendering as the
pre-redesign colour cartoon **on the sport with the most history and the
board that opens first**, and had been since Night Form shipped. Two
renderers out of three followed the grammar.

Fixed in `styles.css` under "Venue art — engraving". `tests/test_overhead.py`
now fails if any renderer's element types drift away from what the
stylesheet actually matches.

**Mow stripes** are the one deletion. Filled at 18% they read as faint
stripes; engraved, each wedge becomes an arc plus two radii, and five of
them radiating from the plate is a cat's cradle. The football field's
stripes survive the same treatment because they are rectangles, which
outline into parallel lines. They carry no data, so on the ballpark they
are hidden (`.stadium path.mow`).

---

## 4. Open — do not close this quietly

**Three sports have no Overhead.** UFC, Polymarket and Kalshi have no
venue. Right now that is fine, because they have no venue cards either.
It stops being fine the moment the Overhead becomes the masthead, the
favicon, the loading state and the social card — which is the whole point
of naming it.

This needs an answer before the Overhead is promoted to those surfaces,
and the answer is probably not "draw an octagon". The honest question is
what the plan view of a *market* is when there is no building: the
Overhead names an encoding, so the extension should be an encoding, not a
picture of a room.

Unresolved. Flagged here rather than solved badly.

---

## 5. What this is not

Not a logo yet. It is a high-uniqueness, zero-fame asset: genuinely
unlike anything in the category, and seen by almost nobody. Fame is a
function of reach, not of craft, and the reach is not there yet. The
correct action for an asset in this quadrant is documented and boring —
do not change it, repeat it — which is what this file is for.
