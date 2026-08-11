# Venue photos — the drop-in slot

Put an image here and the stadium card uses it as its backdrop
automatically; delete it and the card falls back through the chain
below. No build step, no code change.

## What a card shows, in order

1. `{sport}/{HOME_TEAM_ABBR}.jpg` — a team-specific photo, if present.
2. `variants/{family}-{colour}.jpg` — Ethan's sliced night renders
   (2026-08-11). The card picks the render whose lighting matches the
   home team's colours: first team colour with real chroma maps to the
   nearest of red / gold / green / blue / violet; black-and-silver
   kits get steel. Families: football (NFL + CFB), baseball (MLB),
   basketball (NBA + WNBA).
3. The drawn night scene, if both files are missing.

LIVE games always use the drawn scene — it carries the ball spot, the
bases and the live wind, which a photo cannot.

The UFC page ignores team colours (no home team) and shows one
`variants/octagon-{1..6}.jpg` banner per card, hash-picked from the
event identity so a given card always shows the same arena.

## Per-team overrides

Naming: `{sport}/{HOME_TEAM_ABBR}.jpg`
  mlb/COL.jpg   → Coors Field card (Rockies home games)
  nfl/KC.jpg    → Arrowhead card
  nba/LAL.jpg   → the Lakers' arena card

- Use the abbreviation exactly as the site shows it (the home team's).
- ~800×500 or larger looks right; the card crops to cover.
- JPG only (the card requests .jpg).
- Only ship images you have the rights to use.

## Where the variants came from

The `variants/` files are cut from Ethan's full-resolution night
renders (2026-08-11 evening batch): three neutral singles plus a
five-colour sheet per family, ~1000-1536px per tile. The one derived
file is `octagon-6.jpg` — no neutral octagon render exists yet, so it
is the blue one desaturated; a real steel octagon render would replace
it through the normal ingest below.

## Sending new renders (the incoming/ door)

Chat recompresses images; files don't. To ship new renders at full
quality:

1. Save them into `web/img/venues/incoming/`, named with the family
   first (`football` / `baseball` / `basketball` / `octagon`). The
   NAME DECLARES THE GEOMETRY: a file containing several renders must
   say so — `colors`, `sheet` or `grid` in the name (for example
   `football-colors.png`, `octagon-sheet.png`) — and gets cut apart on
   its colour seams. Any other name is ONE render and is never cut
   (a stadium's own rim wall looks exactly like a sheet seam, so
   singles have to say they're singles). `-neutral` in the name also
   pins the render to the steel slot.
2. Run `python3 tools/venues_ingest.py`. It cuts declared sheets,
   reads each tile's LIGHTING colour (never the grass/wood), writes
   the right `variants/` files, and prints every decision. Re-runs
   only ever upgrade — a smaller source never overwrites a bigger
   file.
3. Commit and push (or just push the incoming files and let the other
   side run the ingest).

Per-team files ({sport}/{ABBR}.jpg) are separate and win over variants
— that's where the real per-stadium renders go when they exist.
