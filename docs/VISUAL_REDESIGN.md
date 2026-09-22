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

## What the big apps do (research, 2026-09-22)

Ethan: "Use other sport book apps and websites … on what layouts work
best for organizations and ease of use without loosing information."
Read from reviews and the vendors' own pages (FanDuel, DraftKings,
theScore Bet / ESPN Bet, Action Network, Pikkit, and the sportsbook-UX
guides from Symphony, Altenar, CrustLab and GammaStack). The
conventions they share:

1. **A fixed five-tab bar** that never moves: Home · Sports (A–Z) ·
   Live · My Bets · Account/More. Ours: Home · Picks · Live · Results ·
   More — same shape; "Picks" is our Sports, "Results" is our My Bets.
2. **Home opens with a quick-link row** of circular icons (Live Now,
   promos, then league icons) and everything else below is a short,
   labelled stack: Live now → featured/popular games → trending →
   promos. Nothing on the home is a table; every section has a "See
   all" door. Ours: the league strip + the deck.
3. **A game card shows the three markets in columns** (spread · ML ·
   total, the "6-pack") and tapping anywhere else opens the game page,
   where markets are segmented into tabs (Popular / Game lines / Player
   props). Ours: the stadium card carries the line in its sub-line;
   the game page has the rooms.
4. **My Bets is Open / Settled** with a bet card of selection, price,
   stake → to win, a status chip and, in play, live progress. Ours:
   Riding rows and the record page.
5. **Pick trackers (Action, Pikkit) put the record on the profile** —
   W-L, units, ROI, win rate, CLV, with a units/$/ROI toggle — and the
   pick card carries the bettor, the legs, the combined price, the unit
   size and a one-tap Tail/Copy that names the book with the best
   price. Ours: the record tiles, Zeno's tickets with Copy.
6. **Don't overload the home; keep the menu flat.** Progressive
   disclosure: the essentials first, the detail one tap away, clear
   labels (Live, Upcoming, Popular), personalisation (favourite teams
   first). The one thing every guide warns against is HIDING
   information to look clean — "without losing information" is the
   brief, and the fold failed it.

What that implies for Qellys, and what v2 does: the home is a labelled
stack in the mock's order, built by ARRANGING the board's own zones
rather than redrawing them thinner. The deck owns Live now, Riding,
The record and Zeno's picks (new content) and adopts the stadium
strip, the Pick of the Day card, the Most Likely shelves, Best bets
and the quick tools from the board — same renderers, same information,
new order. No fold. Stats, the performance chart, the cards grid and
the watchlists follow below in their rooms.

Sources: wsn.com and oddsscanner.com FanDuel app reviews; sailgp.com
and oddsassist.com DraftKings app reviews; frontofficesports.com and
bettingapps.com on the ESPN Bet → theScore Bet home; pikkit.com
(bet-tracker, copy-bets, following-leaderboard) and the App Store
listing; actionnetwork.com FAQ and PRO reviews; symphony-solutions.com,
altenar.com, crustlab.com, gammastack.com sportsbook-UX guides.

## Going back

Before any of this shipped, the site as it stood was pushed as branch
`backup/pre-redesign-2026-09-22` (commit `e5454319`; the git proxy
refuses tags, so it is a branch). To restore the whole site:

    git fetch origin backup/pre-redesign-2026-09-22
    git checkout -B claude/sports-betting-app-vhgmho origin/backup/pre-redesign-2026-09-22
    git push -u origin claude/sports-betting-app-vhgmho

The droplet's timer deploys it within five minutes. Data (the ledger,
Zeno's book) is not in git and is untouched either way.

## Status

Ethan approved the mock ("I like what you sent"). Build order: tab bar
and More sheet → Home → Picks/Live filters → retire the sidebar on
phones. Desktop (1280) keeps the sidebar; it is not the cluttered
surface.

* **Slice 1 — SHIPPED 2026-09-22.** The five-tab bar (Home · Picks ·
  Live · Results · More; Picks is the tonight page renamed) and the
  More sheet, built at open from the sidebar's own buttons via
  `MORE_GROUPS` in app.js — pills grouped Bet · Follow · Research ·
  Proof, search at the top. The tour card no longer auto-opens on
  phones. Pinned by `tests/test_the_phone_tab_bar_ends_in_more.py`,
  which also proves no sidebar destination is unreachable from the
  sheet.
* **Slice 2 — SHIPPED 2026-09-22.** The phone home deck (`#home-deck`,
  first thing in the home view, phones only): Live now strip (fast
  scoreboards only, our bets' games first, a held game says so) →
  Riding (tracker rows in play, with progress) → Tonight's picks (Pick
  of the Day hero only on a BET day, then the Most Likely shelves'
  first three) → The record (model ROI and Zeno's profit, tiles only
  over settled bets) → Zeno's open tickets. The strip follows the
  scoreboard on a 20-second clock and redraws only when a score moved.
  The old zones sit unchanged under it. Pinned by
  `tests/test_the_phone_home_leads_with_live.py`.
* **Slice 3 — SHIPPED 2026-09-22.** The Picks page (the tonight view)
  in frame D's shape at every width: league scope pills, the Pick of
  the Day hero (BET days only), Most likely rows with their chance,
  edge rows with their edge — every row a door to the prop page — and
  the board's full cards under one fold. One row function
  (`deckPickRow`) and one hero (`potdHeroHTML`) serve the deck and the
  page.
* **Slice 4 — SHIPPED 2026-09-22.** The deck is the home at every
  width: one column on a phone, a two-column grid on desktop with the
  live strip across the top. The board as it was folds under the deck's
  "Everything on tonight's board" door on both (remembered; unfolds
  itself when the deck has nothing to draw). The desktop rail's Live
  now card yields to the strip.
* **Bug sweep — 2026-09-22.** A Playwright crawl of every view in
  `VIEW_ORDER` at 390 and 1280 (with the tour dismissed): no uncaught
  errors, no console errors, no horizontal overflow, every view draws
  text, the More sheet opens and a pill navigates and closes it. One
  find fixed: bare links inside cards took the browser's blue.
* **Type.** The site already ships the mock's faces (Archivo Narrow,
  Bodoni Moda, IBM Plex Mono, self-hosted in web/fonts), so no font
  change was needed; the mock was drawn in them on purpose.
* **Ethan's reaction, 2026-09-22:** "I don't like it … I don't like how
  you got rid of my stadiums and I don't like how I can't see the most
  likely to hit picks and edge picks on the main page." Two fixes:
  the fold now ships OPEN (nothing hidden unless the reader folds it),
  and a v2 mock — section "Mock · v2" (`8:939`; E phone `8:286`, F
  desktop `8:568`, StadiumCard component `8:256`) — puts the stadium
  strip, Most likely to hit (five rows, Pick of the Day first) and
  Edge picks (four rows) on the home at both widths, nothing folded.
  Ethan: "keep going" — built as slice 5 (below), with the stadium
  cards carrying the site's own venue renders.
* **Slice 5 — Home v2, SHIPPED 2026-09-22.** The deck arranges the
  home in the mock's order at every width: Live now → Riding → Tonight's games (the
  stadium strip, adopted) → Most likely (the Pick of the Day card and
  the Most Likely shelves, adopted) → Edge picks (Best bets, adopted)
  → The record → Zeno's picks → Tools (adopted). The fold is gone.
  `HOME_DECK_ADOPTS` in app.js names what moves; the deck's skeleton is
  built once so a redraw never destroys an adopted zone, and adoption
  is idempotent so subtabbedDOM's regrouping cannot pull one back.
  Verified in Chromium at 390 and 1280 with a board fixture: every
  section drawn in order, no page errors.
* **Slice 6 — the three-market row, SHIPPED 2026-09-22.** Every
  stadium card carries spread · ML · total for both teams in aligned
  columns (`gameMarketsHTML`), the "6-pack" every book's card uses,
  read from the board's own fields; "—" for a market the board did not
  price, nothing on a finished game. The sub-line under the matchup
  stops repeating the spread and total where the row draws.
* **Slice 7 — Open / Settled on the Record page, SHIPPED 2026-09-22.**
  One line under the verdict says how many bets are riding and points
  at the Live tab, from the same journal's count. Not done: a
  units / dollars / ROI toggle on the verdict — the record is kept in
  units on purpose (the site holds no money), and a dollar view would
  need the reader's own unit size from the Bankroll page; parked.
* **Slice 8 — the game page's section chips, SHIPPED 2026-09-22.**
  Every book's event page segments its markets; ours stays one page
  (nothing hidden behind a tab) and gains a sticky chip row under the
  hero — Lines & insights · Replay · Team shapes · Most likely · Game
  bets · Props · Long shots — drawn only for sections the page has,
  each chip scrolling to its section (`gpJumpHTML`).
* **Still open.** The desktop rail's Key insights card and the old
  sub-tabbed zones live on under the fold; a later pass can retire
  what nobody unfolds. Zeno's tile and tickets appear once Juice Reel
  data lands.
