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

> **§1 was amended on 2026-08-08.** Ethan opened the two rows struck
> through below — *"i feel like we should have the color for the stadiums
> and arenas and shit instead of these lines we are calling stadiums"* —
> after seeing the current art, a full-colour revert and a middle option
> rendered side by side on real cards. The colour is back on the
> **surfaces**; everything else in this table still holds, and the two rows
> that changed are struck rather than deleted so the reasoning survives the
> decision. The rest of this document is unchanged and still governs.
>
> **What the colour is now:** the fills that were always in `visuals.js`
> — grass, infield dirt, hardwood, the team's own colour on stands and end
> zones. The engraving was only ever a stylesheet re-skin, so removing the
> strip rules restored the drawing exactly.
>
> **What did NOT come back, and this is the whole difference between the
> amendment and a revert:** the art still sits on the page's ground rather
> than its own. The sky wash is still flattened to `--bg-2`, every label is
> still mono at one weight, every radius is still zero, and the plaques are
> still hairline boxes. Rendered as a straight revert, the venues read as
> three cards pasted in from a different website — a radial navy gradient
> behind each one on a near-black page, with system-ui labels among mono.
>
> **One rule was added.** Labels now carry a `--bg-2` halo via
> `paint-order: stroke fill`. `--text-dim` was picked when the ground under
> every label was flat and identical; on Vikings purple, "MIN" vanished
> outright. The halo solves it for every surface at once and inverts with
> the theme, where the alternative — the old per-team ideal-contrast fill —
> would put a third type system back on the card.
>
> Enforced by `tests/test_overhead.py`, which was rewritten alongside this
> rather than deleted: the coverage guard that policed the strip rules is
> now a guard on the ground rule and the label halo.

| Locked | Value |
|---|---|
| ~~**Line language**~~ | ~~Outline only. No fill, no gradient, no wash.~~ **Amended 2026-08-08:** surfaces carry colour again. Structure that is still drawn as line keeps `stroke-width: 1.1` / `1`. |
| ~~**Ink**~~ | ~~`--text-mute` for structure, `--border` for surfaces and hatching. Nothing else.~~ **Amended:** surfaces use the drawing's own colour and the team's. **Type is unchanged and still locked:** `--text-dim`/`--text` on labels and figures, plus a `--bg-2` halo so they survive a coloured surface. |
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

## 4. The sports with no building — answered

This section used to say three markets had no Overhead and the gap was
unresolved. It is resolved, and the rule that resolves it is one line:

> **Draw the space a price is set in, to scale, with the conditions in the
> corners. What changes is what counts as space.**

**UFC has a building after all, and the first instinct was wrong.** The
note here used to say "the answer is probably not draw an octagon,"
reasoning that an octagon is a constant and a constant carries no data.
`engine/ufc/environment.py` says otherwise: the promotion's own facility
uses a **25-foot** cage and arena events use **30**. Less space means
fewer places to retreat to, so pressure fighters and wrestlers gain,
out-fighters lose, and finishes go up — and the model already prices it.

That makes the cage exactly as data-bearing as an outfield arc: a building
whose dimensions vary and whose variation moves the number. `octagon()`
draws it to scale, so an Apex card is visibly tighter than an arena card.
Altitude takes the bottom-left plaque, as it does on the ballpark; cage
size takes the bottom-right, where the park factor goes; rounds take the
top line, where roof state goes. Same grammar, different building.

**Prediction markets have no room, so the space is the probability line.**
For Polymarket and Kalshi the thing a price is set *in* is the market, and
its plan view is the 0–100 rule. `marketRule()` draws every market on the
board as a segment from the exchange's number to ours. **Length is
disagreement.** A board we agree with is a row of ticks; a board we
disagree with violently is a row of long bars, readable before a single
figure is.

One drawing for the whole board, not one per row — the Kalshi board is an
agate table and a venue-sized diagram on every line would bury it. It also
makes the shape novel rather than generic, which is the property a
visualisation needs before it can become recognisable at all.

### Still open

The Overhead is not yet on the masthead, the favicon, the loading state or
a social card, which was the reason the coverage gap mattered. Those
surfaces are the next question, and the honest blocker is that the site is
not hosted anywhere — `python3 launch.py` serves it locally and
`web/index.html` carries no `og:` tags at all. Static card first, dynamic
per-game rendering only once there is somewhere to render it.

---

## 5. What this is not

Not a logo yet. It is a high-uniqueness, zero-fame asset: genuinely
unlike anything in the category, and seen by almost nobody. Fame is a
function of reach, not of craft, and the reach is not there yet. The
correct action for an asset in this quadrant is documented and boring —
do not change it, repeat it — which is what this file is for.
