# Venue photos — the drop-in slot

Put an image here, name it in `VENUE_TEAM_PHOTOS` in app.js, and the
stadium card uses it as its backdrop; delete it (and its name) and the
card falls back through the chain below. No build step.

Why the name has to be listed (2026-10-09): the card used to ask for a
team photo on every game and fall back when it was missing — and none
has ever shipped, so every card waited on a failed request before its
render loaded. tests/test_the_site_feels_quick.py fails until a photo
dropped in here is named in the list, so it can never be silently unused.

## What a card shows, in order

1. `{sport}/{HOME_TEAM_ABBR}.jpg` — a team-specific photo, if present
   and named in `VENUE_TEAM_PHOTOS` (e.g. `"nfl/KC"`).
2. `variants/{family}-{colour}.jpg` — Ethan's sliced night renders
   (2026-08-11). The card picks the render whose lighting matches the
   home team's colours: first team colour with real chroma maps to the
   nearest of red / gold / green / blue / violet; black-and-silver
   kits get steel. Families: football (NFL + CFB), baseball (MLB),
   basketball (NBA + WNBA), hockey (NHL — five renders, 2026-10-03;
   the blue one also fills the violet slot).
3. The drawn night scene, if both files are missing.

Live games show the photo too (since 2026-08-13); the live bases ride
over it as an overlay.

Every render ships twice: the full WebP and an 800px phone copy
(`{name}@800.webp`), which narrow screens are served. The ingest tool
writes both; a render added by hand needs both.

The UFC page ignores team colours (no home team) and shows ONE
picture for every card: `ufc-hero.jpg`, Ethan's branded arena render
(2026-09-07, the boards dressed in Qellys Book). The six
`variants/octagon-{1..6}.jpg` files are the earlier hash-picked rotation;
the ingest tool still fills those slots, but the page no longer shows
them. To change the hero, replace `ufc-hero.jpg` (3:2, JPG) and bump
`VENUE_ART_V` in app.js so phones drop the cached copy.

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
