# Venue photos — the drop-in slot

Put an image here and the stadium card uses it as its backdrop
automatically; delete it and the card falls back to the drawn night
scene. No build step, no code change.

Naming: `{sport}/{HOME_TEAM_ABBR}.jpg`
  mlb/COL.jpg   → Coors Field card (Rockies home games)
  nfl/KC.jpg    → Arrowhead card
  nba/LAL.jpg   → the Lakers' arena card

- Use the abbreviation exactly as the site shows it (the home team's).
- ~800×500 or larger looks right; the card crops to cover.
- JPG only (the card requests .jpg).
- LIVE games always use the drawn scene — it carries the ball spot,
  the bases and the live wind, which a photo cannot.
- Only ship images you have the rights to use.
