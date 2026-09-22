# Visual redesign — the Figma mock (2026-09-22)

Ethan, 2026-09-22: "the site feels so cluttered and confusing and you get
lost and its hard for a new user to find everything the site offers."
Asked how to proceed he chose **mock it in Figma before code**, and for
the home screen's job he chose **live first**.

## Where the mock lives

Figma file `A0YN30KFbY2lX6yuthVVKj` (Ethan's plan), page 1.

| node | what |
| --- | --- |
| `4:436` | Section "Mock · v1 (390)" — the four phone frames side by side |
| `4:2` | A · Home — live night |
| `4:133` | B · Home — quiet night |
| `4:226` | C · More sheet |
| `4:336` | D · Picks (sport filter pills) |
| `2:2` | Section "Components" (Pill `2:3`, SectionHeader `2:5`, GameCard `2:8`, BetRow `2:28`, PickRow `2:36`, TabBar `2:43`) |
| `VariableCollectionId:1:2` | "Qellys" variables — colours mirror `web/css/styles.css` tokens; space and radius scales |

Fonts in the mock: Bodoni Moda Bold (display), Archivo Narrow (sans),
IBM Plex Mono (numbers). The numbers on the frames are placeholders
(the +9.5% is the NFL Most Likely figure from Ethan's screenshot; Zeno's
+4.1% / 38 is invented for layout). Nothing in the mock is a claim.

## The information architecture the mock proposes

* **Five-tab bar** replaces the sidebar as the primary nav on a phone:
  Home · Picks · Live · Results · More.
* **Home, top to bottom:** Live now (horizontal strip of game cards;
  each shows the score, the clock or a HOLD word, and "N riding") →
  Riding (bets in progress, with the stat's live progress) → Tonight's
  picks (Pick of the Day in a brand-bordered card, then two rows) → The
  record (model tile + Zeno tile) → Zeno's picks. On a quiet night the
  Live strip collapses to one sentence ("Nothing live. First pitch
  7:05 ET — 3 picks queued.").
* **Sport chips become filter pills** inside Picks and Live, not
  destinations of their own.
* **More** is a bottom sheet with four groups that map onto today's
  sidebar folds: BET (Value Bets, Long Shots, Line Shopping, Futures,
  Game Lines), FOLLOW (Zeno's Picks, Alerts, My Bets, Streak,
  Bankroll), RESEARCH (Injuries & News, Players, Rosters, Rankings,
  Weather, Trending, Fantasy, Predict), PROOF (The record, The Lab,
  Methodology, Status, About).
* The first-run tutorial popup goes; the structure is the tutorial.

## Status

Mock built; awaiting Ethan's reaction before any code. When a
direction is chosen, the build order is: tokens/fonts → tab bar and
More sheet → Home → Picks/Live filters → retire the sidebar on phones.
Desktop (1280) keeps the sidebar; it is not the cluttered surface.
