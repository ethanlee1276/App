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

## The sportsbook look, and ours (research round two, 2026-09-22)

Ethan: "look at all the Sportsbook app design … we want our app to
look kind of like a sportsbook app but also like our own." Read across
the Dribbble sports-betting-app tag (LazyInterface, Pickolab's SiBet,
Hexagon's Betswipe, Ronas IT's betting concepts, Excellent Webworld,
Roohi Koohi), the Behance case studies (BetFlowX, Mobet, WOONA,
BetGo), the Figma community kits (PlayStake, Betlio, Bidibet, the
ui8 sports-bet kit) and the shipped apps (FanDuel, DraftKings,
bet365, theScore Bet). This sandbox cannot open Dribbble or Behance
pages, so the shots were read through their published descriptions
and the kits' component lists, and checked against the shipped apps.

**The genre's vocabulary — what every shot has:**

1. **A dark base and ONE accent.** Near-black or deep navy, one
   electric colour for the brand (green, blue, red-and-yellow, purple;
   gold reads "premium"), and semantic green/red kept for up/down and
   win/loss only. Layered surfaces: page → panel → card, 1px hairlines,
   12–16px radii, a soft glow on the accent.
2. **A hero banner** at the top of the home — gradient card, imagery,
   one bold headline, one pill CTA — then a **league carousel** of
   circular icons (active one filled with the accent).
3. **The match card**: crests, kickoff chip or LIVE chip, and the three
   markets as chunky **odds pills** (bold tabular numbers, a filled
   "selected" state, a flash on a price move), with a "+N markets"
   chevron to the event page.
4. **Live**: a pulsing red dot, big tabular score, period/clock, a
   thin progress or win-probability bar.
5. **The bet slip** as a bottom sheet or a floating pill with a count;
   **five bottom tabs**, often a raised centre.
6. **Type**: a geometric or condensed sans for headings, tabular
   numerals for every price, uppercase micro-labels with tracking.
7. **Analytics everywhere**: rings, sparklines, form dots (W L W), win
   probability meters; profile pages lead with a big P&L, an ROI chip,
   W-L-P and a curve.
8. **Motion**: odds flash green/red, numbers count up, skeleton
   loaders, tab indicators that slide — all short.

**What is already ours and stays:** black and gold; Bodoni Moda for
the wordmark and display lines (the "book" voice no sportsbook has);
Archivo Narrow and IBM Plex Mono; the stadium renders as the card art
(no book has a venue on a card); "Priced by a model. Graded in
public."; the record as the hero number; probabilities beside prices;
no balance, no slip, no order ticket — a Riding tray is our slip.

**What v3 borrows, in our clothes:** the hero banner (the Pick of the
Day on its stadium art); a league carousel of crests on the phone home;
odds pills on the match card (informational — one style, no "selected"
state, because nothing here is placed); the LIVE chip and win-prob bar
already shipped; a floating Riding tray above the tab bar when bets
are in play; form dots and an ROI ring on the record ribbon; the
price-move flash the ticks already do.

Sources: dribbble.com/tags/sports-betting-app and the shots named
above; behance.net sports-betting-app searches; figma.com/community
(PlayStake, "Sport betting app UI", "Sports bet mobile app UI-kit",
"Betting app UI"); ui8.net sports-bet kit; altenar.com sportsbook UX
trends; symphony-solutions.com, gammastack.com, prometteursolutions.com,
crustlab.com UX guides; deucescracked.com, rg.org, sportsbookreview.com
app comparisons; uxdesign.cc on deceptive sportsbook patterns (what
not to copy: urgency banners, fake scarcity, buried odds).

**The v3 prototype** lives in `docs/mocks/home-v3-phone.html` and
`docs/mocks/home-v3-desktop.html` — real HTML on the site's own
stylesheet, fonts and venue art (the Figma connector hit its plan's
call limit mid-build, so this round was drawn in the medium itself).
Open either file in a browser, or render both with Playwright at 390
and 1280. Awaiting Ethan's reaction before any of it is coded into the
site.

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
* **Slice 9 — the phone top bar loses a control, SHIPPED 2026-09-22.**
  The theme switch moves into the More sheet on phones (a button that
  proxies the real toggle, so the theme is still switched in one
  place); desktop keeps its toggle. The bar now carries the drawer,
  the mark, alerts, messages, the freshness chip and the account.
* **Slice 10 — v3, SHIPPED 2026-09-22.** Ethan: "Build it all and I'll
  look at it then." On the phone the league strip is a carousel of
  crests (the code in a circle, the active one ringed in gold; it still
  wraps, never scrolls). The stadium card's three-market cells are
  pills. A pick row carries the price in a grey pill beside our number
  in a green one, and the sub-line names the game and the book only.
  A live card on the home draws the win-probability bar when the fast
  scoreboard priced one, and says who leads and by how much. The
  record is a ribbon — hit-rate ring, W-L, the headline number, units,
  and the last five as form dots from the record's own rows — for the
  model and for Zeno. A riding tray floats above the tab bar on phones
  while journaled bets are in play (hidden on the Live tab it points
  at). The Pick of the Day card is the home's hero, on the venue render
  its team's colours pick, its headline in the display face (Ethan's render set that token to Archivo Narrow; the prototype showed Bodoni — one token to flip if he prefers it). Everything drawn is
  a number the board already held; nothing is drawn otherwise. Pinned
  by `tests/test_v3_looks_like_a_book_and_like_us.py`. Two things the
  first render caught: Chromium resolves a `url()` that reaches CSS
  through a custom property against the stylesheet, so the hero's art
  travels as an absolute URL (`absoluteSrc`); and an unpriced pick
  used to print the word "undefined" on the hero's sub-line.
* **Slice 11 — v4, the shell (in progress, 2026-09-22).** Ethan, with
  three screenshots of his phone: "there's a lot of repeats … it still
  kinda looks like the same old website." The repeats he circled, and
  what each became:
  * *The crest said its code twice.* The circle now holds the sport's
    glyph (football, baseball, basketball, the cage — `LEAGUE_GLYPH`,
    built by `leagueCrests()` at boot) and the code is the label
    beneath it, once. Desktop keeps its text tabs.
  * *The More sheet was thirty identical pills.* Rows in two columns,
    each carrying the sidebar button's own icon — a map, not a wall.
  * *Record was in the sheet and on the tab bar.* The sheet's Proof
    group no longer lists it; Results is the bar's.
  * *The home's Riding section repeated the tray.* Hidden on phones,
    where the tray floats; the desktop deck keeps it.
  * *Two menus.* The hamburger drawer and the More sheet held the same
    list. On phones the hamburger is hidden and the drawer never
    opens; the sheet is the one way in, and the drawer's footer — the
    High Confidence and Parlay Mode switches, the Instagram and
    Discord links — rides into the sheet as proxies of the real
    controls (`moreSheetFoot`). The drawer stays the tablet's menu
    (761–900px, where there is no tab bar). The bell left the phone
    bar with it: Injuries & News is a row in the sheet.
  * *The home in the old order, with the old headers.* The deck now
    leads with the Pick of the Day as the prototype's hero (gold
    eyebrow, the verdict as a pill, the bet in the display face over the venue
    render, the price line in mono — CSS on the card's own pieces, no
    field lost), then Live now, Riding, tonight's games, Most likely,
    Edge, the record, Zeno, tools. Every home section wears the deck's
    head; the adopted zones' old titles ("Qellys’ top picks — who’s
    most likely to hit…") keep their words one line down, quieter. The
    games row's league select, the crest strip again, is hidden on the
    phone home.
  Pinned by `tests/test_the_phone_says_nothing_twice.py` and
  `tests/test_the_phone_home_leads_with_live.py`; the drawer file's
  browser probe now measures the sheet.
* **Slice 12 — every other page (in progress).** Ethan: "Fantasy, the
  record page, all the other pages are still the same … cluttered and
  confusing and hard to read all the data." The pages are surveyed at
  390 and 1280 with fixtures built through the engine (a 70-bet record,
  a usage board); the shared pieces ship first, then each page.
  * *A page opens with its name.* Thirty of the forty views open with
    a `.section-title` and its `.sub`, drawn as the same small tracked
    caps every section head inside the page uses. The first title in a
    view is now the page's name in the display face at the hero's size,
    its purpose in a plain line beneath; the section heads under it
    keep the caps, so two levels read as two. The why? fold is untouched.
  * *Record: the calibration rows overlapped on desktop* — four cells on
    a six-column grid. They carry `rl-cal` and their own columns.
  * *Fantasy: the room index sits two abreast on phones.* Every room
    stays named and described (Ethan, 2026-09-10); eight cards no longer
    fill a screen before the first number.
  * *A caveat folds to two lines.* `.list-note` ("a caveat under content
    that IS there") and the empty state's sub-line: past 160 characters
    a note keeps its first two lines and the rest waits behind the same
    amber "more" the why? apparatus uses (`enhanceNotes`, run with the
    sub enhancer on every render). `.ls-note` — on an empty likelihood
    board, the whole answer — is never folded.
  Pinned by `tests/test_the_page_opens_with_its_name.py` and
  `tests/test_a_caveat_folds_to_two_lines.py`. What stays as it is, on
  purpose: the legal footer (the preservation test carries
  the owner's rule that the honesty copy keeps its prominence), the
  record's zero-count league chips ("no bets yet" must not look like
  "no such board"), and wrapping sub-tab rows (a scrolling tab row is
  the draggable bar Ethan caught on 2026-08-18).
* **Still open.** The desktop rail's Key insights card and the
  sub-tabbed zones the deck does not adopt sit below it; a later pass
  can retire what nobody opens. Zeno's tile and tickets appear once
  Juice Reel data lands.
