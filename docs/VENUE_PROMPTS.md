# Venue art kit — prompts, filenames, and how to check the result

Fifteen colour renders are missing. Not absent — *present and wrong*, which
is worse, and this file exists so the next attempt does not repeat the
2026-08-11 batch's mistakes.

Run `python3 launch.py --venues` before and after. It measures every file
against its own family's reference and prints exactly what is still off.

---

## What went wrong the first time

The three `*-steel.jpg` renders are the target. They came out of a
different generation than the fifteen colour files, which were **cut out
of five-colour contact sheets** — and it shows in five specific ways:

| | reference (`football-steel`) | the sheet tiles |
|---|---|---|
| size | 1536×1024 | 994×798 … 1522×1092 |
| aspect | **3:2 landscape** | ~1:1, nearly square |
| what is tinted | the **floodlights only** | everything, grass included |
| sky | clean near-black | orange haze and cloud |
| detail | individual seats readable | soft, glowing, ~60% the bytes per pixel |

The square crop is the loudest of these. The card crops to cover, so a
1:1 source is a different composition of a different scene — it cannot
be rescued by tinting or sharpening.

**Generate each colour as its own full render.** Do not make a sheet and
cut it. `tools/venues_ingest.py` can cut sheets and that ability is what
produced the problem: a sheet divides one image's pixel budget five ways.

---

## The house look, in words

Every render, whatever the colour:

- **Empty stadium at night.** No crowd, no players, no ball in play.
- **Elevated wide-angle from behind one end** — behind the end zone,
  behind home plate, behind the baseline. Symmetric, centred, horizon
  high in the frame so the bowl fills it.
- **Clean near-black sky.** No clouds, no haze, no light bloom.
- **The colour lives in the FLOODLIGHTS.** The rig throws tinted light
  across the bowl and the seats pick it up. The playing surface keeps its
  own colour — grass stays green, hardwood stays wood.
- **Sharp.** Individual seats distinguishable in the upper deck, surface
  markings legible.
- **Nothing readable.** No text, no logos, no sponsor boards, no team
  identity. The scoreboard is dark and blank.
- **1536×1024**, 3:2 landscape, PNG out of the generator.

---

## The prompts

Take the base for the family, then substitute the lighting line. Keep
everything else identical between colours — that identity is the whole
point of the exercise.

### Base — football (`football-*`)

> Empty American football stadium at night, photographed from an elevated
> position directly behind one end zone, wide-angle lens, perfectly
> symmetric composition. Full bowl of empty dark seats rising on all
> sides, tiers and individual seats sharply resolved. Green turf with
> crisp white yard lines, yard numbers and hash marks; yellow goalposts.
> Large blank dark scoreboard high on the far rim. Clean near-black night
> sky, no clouds. {LIGHTING}. Photorealistic architectural photography,
> ultra sharp, high micro-detail, no bloom or haze, no people, no text,
> no logos, no team branding. 1536x1024, 3:2 landscape.

### Base — baseball (`baseball-*`)

> Empty baseball stadium at night, photographed from an elevated position
> directly behind home plate, wide-angle lens, symmetric composition.
> Green outfield grass with mowing stripes, brown infield dirt, clean
> white base paths and foul lines. Full bowl of empty dark seats,
> individual seats sharply resolved. Large blank dark scoreboard beyond
> the outfield. Clean near-black night sky, no clouds. {LIGHTING}.
> Photorealistic architectural photography, ultra sharp, high
> micro-detail, no bloom or haze, no people, no text, no logos, no team
> branding. 1536x1024, 3:2 landscape.

### Base — basketball (`basketball-*`)

> Empty indoor basketball arena at night, photographed from an elevated
> position behind one baseline, wide-angle lens, symmetric composition.
> Polished light hardwood court with crisp white and painted lines, both
> hoops visible. Full bowl of empty dark seats rising steeply, individual
> seats sharply resolved. Large blank dark scoreboard above centre court.
> {LIGHTING}. Photorealistic architectural photography, ultra sharp, high
> micro-detail, no bloom or haze, no people, no text, no logos, no team
> branding. 1536x1024, 3:2 landscape.

### Base — octagon (`octagon-1` … `octagon-6`)

Six variations rather than six colours — the UFC card hash-picks one from
the event identity, so they only need to look like the same building on
six different nights.

> Empty mixed martial arts arena at night, the octagon cage lit at centre,
> photographed from an elevated seat, wide-angle. Dark empty tiered
> seating all around, canvas and cage clearly resolved. {LIGHTING}.
> Photorealistic, ultra sharp, no people, no text, no logos, no branding.
> 1536x1024, 3:2 landscape.

### The lighting lines

Substitute for `{LIGHTING}`. The wording is deliberate: it names the
*source* as tinted, not the scene, which is what keeps the grass green.

| slot | `{LIGHTING}` |
|---|---|
| `steel` | Neutral white stadium floodlights, cool daylight-balanced, no colour cast |
| `red` | Deep red stadium floodlights washing the bowl in crimson light; the playing surface keeps its natural colour |
| `gold` | Warm amber-gold stadium floodlights washing the bowl in golden light; the playing surface keeps its natural colour |
| `green` | Emerald green stadium floodlights washing the bowl in green light; the playing surface keeps its natural colour |
| `blue` | Deep blue stadium floodlights washing the bowl in cobalt light; the playing surface keeps its natural colour |
| `violet` | Violet-purple stadium floodlights washing the bowl in purple light; the playing surface keeps its natural colour |

`steel` already exists for all three families and is the reference — only
regenerate it if you are rebuilding a whole family at once, and if you do,
every other colour in that family has to be rebuilt with it.

---

## Filename checklist

Save into `web/img/venues/incoming/`. **The name declares the geometry**:
anything containing `colors`, `sheet` or `grid` gets cut apart on colour
seams; every other name is treated as one render and never cut. Since
these are all single renders, keep those three words out of the names.

Name each file `{family}-{colour}.png`:

```
football-red.png      baseball-red.png      basketball-red.png
football-gold.png     baseball-gold.png     basketball-gold.png
football-green.png    baseball-green.png    basketball-green.png
football-blue.png     baseball-blue.png     basketball-blue.png
football-violet.png   baseball-violet.png   basketball-violet.png
```

Fifteen files. `steel` is not on the list — it is already good in all
three families.

The word `neutral` in a filename pins that render to the `steel` slot
regardless of what its lighting reads as. Do not use it on a colour file.

---

## Shipping them

1. Drop the fifteen PNGs into `web/img/venues/incoming/`.
2. `python3 tools/venues_ingest.py` — cuts nothing (these are singles),
   reads each render's lighting colour, writes `variants/{family}-{colour}.jpg`
   at ≤1600px wide, q87. It only ever upgrades: a smaller source will not
   overwrite a bigger existing file.
3. `python3 launch.py --venues` — confirms each new file matches its
   family reference and prints the `VENUE_MATCHED` line to paste.
4. Paste that line into `web/js/app.js`.
5. **Bump `VENUE_ART_V`** in `web/js/app.js` to today's date. New bytes
   under an old filename is the one failure nothing else in the chain can
   detect, and phones hold image caches longest.
6. Delete the ingested PNGs from `incoming/` so the next run is a no-op.

Step 5 is the one people skip. The site will look unchanged on the device
you are testing on and correct on a fresh one, which is the most confusing
possible outcome.

---

## Per-stadium art (separate, and better)

`{sport}/{ABBR}.jpg` — e.g. `mlb/COL.jpg`, `nfl/KC.jpg` — beats the colour
variant for that team's home games. Those directories are empty today. Any
real render of an actual ballpark belongs there and needs no colour rule
at all, because it is not standing in for anything.
