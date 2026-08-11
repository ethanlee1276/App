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

## Replacing the variant renders with full-res versions

The `variants/` files were sliced from a 1536px contact sheet, so each
is ~460×400 upscaled 2×. If you have the original renders as separate
full-size images, overwrite the matching `variants/` file (same name,
JPG) and every card sharpens up with no other change.
