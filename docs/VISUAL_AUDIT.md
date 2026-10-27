# Visual audit — 2026-10-25

Ethan: *"we need to fix the visuals of the app. I need u to audit the whole
thing. The settings and account area and shit like that is ugly and doesn't
look like real settings and more shit like that is the same. Check all of
it."*

How it was checked: every page and screen (41 pages, the game, pick and
team pages, the More sheet, the account page's four tabs, plans, sign-in,
sign-up and reset), on an iPhone-size screen and a desktop, signed out and
signed in as a member, screenshotted top to bottom and looked at one by one.
Then again after the fixes, in both themes. Every row below is fixed.

## What made the whole app look like a web form

| # | Finding | Where | Fix |
|---|---|---|---|
| G1 | The page never told the browser it is dark (`color-scheme` unset), so the browser drew its light controls: a **white checkbox** on sign-up, a **white input** for the bankroll goal, **blue checkboxes** on Alerts, light date pickers and select menus | every form | `color-scheme: dark` on the theme (`light` on the light theme); gold checkboxes |
| G2 | Every button **shouted**: uppercase with wide letter spacing (TONIGHT'S PICKS, LOG IN, SYNC NOW, COPY LINK, BACK TO THE BOARD) | every page | sentence case, the weight doing the work, pill shape, 40px tall |
| G3 | A gold, spaced-out **"why?†"** beside nearly every page title, and gold spaced **"more"** links | every page | a quiet "Why?" chip; "More" as a plain link |
| G4 | Subtitles under titles **start in lower case** ("every game in progress…", "pull up form…") — they were written to follow a dash that is gone | ~230 subtitles | the first letter capitalised |
| G5 | **Selects** in three sizes and two fonts (the Toolbox's in monospace); no shared field style | Home, Most Likely, Toolbox, My Bets | one field style: dark, hairline, rounded, a drawn chevron |
| G6 | **Buttons touching** and the next heading jammed under them | Live, Line Shopping | a gap between, room after |
| G7 | A sentence broken into **columns** ("This / board is · Thu, / Jan 1 · — first one / starts in…") | Home's "next game" note | laid out as a sentence |
| G8 | Streak's sign-in box with **square corners** and a square button, unlike everything else | The Streak | the shared radius and button |
| G9 | A player's **name wrapping** to two lines because Copy link and the grade crowd it | Players | the name gets the row |

## The account and settings area

| # | Finding | Fix |
|---|---|---|
| S1 | The Settings tab was **a stack of cards**: a billing card holding the whole plans advert (price, nine ticks), two fantasy cards of paragraphs, then a "Settings" card of pill rows | rebuilt as a phone's own settings screen: grouped lists with a small header over each group, rows with an icon tile, the name, the value, a chevron or a switch |
| S2 | Choices drawn as **rows of pills** (seven time zones), on/off as **two pills** (Team colours: Off / Your team; the two emails) | two or three options: a segmented control in the row; on/off: a switch; longer lists: their own screen with a check beside the one in force |
| S3 | A **paragraph under every control** | one short footnote under a group where one is needed |
| S4 | **Sign out and Delete account hidden** in a disclosure inside the billing card | their own rows at the bottom, in red |
| S5 | The email **said twice** ("Sign-in & plan — you@… only you see this", then "Signed in — you@…") | once, as the Email row |
| S6 | Desktop: the settings column **narrower than and offset from** the tabs above it | one column, aligned |
| S7 | Sign-in: **placeholder-only fields**, the main action a **grey ghost button**, a decorative eye in the card head, two paragraphs and a list of ticks | labelled fields, a gold Log in, one line of assurance |
| S8 | Sign-up: the **white checkbox**, placeholder-only fields, "Already have an account? LOG IN Forgot password?" crowded on one line | labelled fields, a gold checkbox, the links on their own lines |
| S9 | Alerts on this phone: **blue checkboxes**, an "OFF" pill, TURN ALERTS ON | switches in a grouped list, a gold "Turn alerts on" |
| S10 | My Bets' form: **square native selects and date box**, uppercase labels | the shared field style, sentence-case labels |
| S11 | Bankroll: a **white native input** for the goal, and the bankroll and the unit sharing one borderless strip ("$ 1000 1 % / unit") | the shared field style; two labelled fields, what a unit comes to under them |
| S12 | Membership's own screen: the plan in a box, a status sentence beside a ghost button, "HAVE A CODE?" over a code box that shouted its placeholder in capitals; **"Free"** for somebody with no plan, on a site that has none | rows: the plan, its price, when it renews; Manage billing as a row; the code as a field and a gold Apply; "No membership" |
| S13 | Friends: a striped card, a section title with a Why? chip, friends as removable pills | a friend a row (their initials in the tile), Remove at the end; the invite link a group of its own |
| S14 | Signed out, the fantasy link forms were drawn **twice** (on the sign-in screen and on Settings › Fantasy leagues), two elements with one id: the screen the reader opened stayed **empty** | drawn once, on their settings screen |
| S15 | "Link a league" on the fantasy pages opened the account page at its top; signed in, the forms were three taps away | it opens Settings › Fantasy leagues and lands on it |

## What a row does while it works

Two buttons replaced their own text while they worked: Manage billing
("Opening secure checkout…") and Copy my invite link ("Copied"). As rows,
that would have flattened the row to a line of text, and Manage billing's
error went looking for a card that a settings screen does not have (it
would have thrown). A row keeps its tile and chevron; only its name says
what is happening, and a billing error has its own line under the group.

## Where it is held

`tests/test_settings_read_like_a_phones_own.py` (the browser half drives
the settings list, a screen and back, Membership, the sign-in screen and
the Alerts switches), with the tests that pinned the old markup moved to
the new: `test_account_settings`, `test_fantasy_links`, `test_tour`,
`test_your_games_in_your_calendar`, `test_forgot_password`.

# The Fantasy room — 2026-10-27

Ethan: *"go through the visuals of the fantasy room as well. Like, look at
how other fantasy apps and fantasy rooms and shit like that looks visually
... It doesn't feel like a professionally built app."*

How it was checked: every Fantasy tab, top to bottom, at a phone width (390)
and a desktop width (1280), on the live site's own public files, then again
after each change. The apps it was held against: ESPN's 2025 rebuild (a
personal home first, a matchup view with the score pinned, live projections,
action items), Yahoo's (more on screen at once), Sleeper (position colours,
the matchup head-to-head), FantasyPros (ranges, tiers, start/sit).

| # | Finding | Fix |
|---|---|---|
| F1 | The room opened on **onboarding and navigation, no content**: the Fantasy 101 card open on every visit (the whole first screen on a phone), four tiles of numbers nobody acts on (the season's year, a count of usage rows, of trade flags, of game scripts), and ten described cards before the first player | 101 opens on the first visit only, then as the reader left it, its steps as numbered tiles and its glossary folded; the four tiles became one line: the week, its games, who is on a bye; the rooms became app-style tiles with an icon (all eleven on one phone screen) |
| F2 | **Your own league was the last room**, under the camp report, the offseason and the draft kit | "My team" is a room of its own, first, and opens first when a league is linked |
| F3 | **Every card wore a brown wash** top to bottom: the gold glow's height was the card's, so a 4,000px list read muddy | the glow is a fixed 160px at the top of every card, site-wide; long lists are clean below it |
| F4 | **Player rows were text**: "8 in 10 weeks 8.3–38.2" and "PPR this week" in typewriter type on every row, no position colours | one player row for the room: face, name and chips, a colour badge for the position (QB red, RB green, WR blue, TE orange, K purple, D/ST grey), the team's mark and the kickoff in the reader's time zone, the floor-to-ceiling range as a bar on one scale with his number marked, the number large on the right; a wide screen gives the bar its own column |
| F5 | **Buy low / Sell high was one huge card a player** (GAP, ACTUAL, xFP boxes and the same sentence on every card): five players a phone screen | a row a player with a bar (scored against expected), the gap on the right, the sentence said once above the list: twelve players a screen (8,033 → 2,724px) |
| F6 | **Waivers rows broke on a desktop** (the number fell to a line of its own) and repeated their note on every row | the same row, with a share bar from where his share was to where it is |
| F7 | **The usage table broke on a phone**: the fantasy sheet re-showed the bar the phone rule hid, so every trend chip fell to its own line, and names ran to an ellipsis | the bar hidden again after the rule it must beat; the name over a line with the position badge |
| F8 | The head-to-head card was **five paragraphs** between the score and the lineup | the odds as a bar under the number; how they are figured under a fold (every word kept) |
| F9 | The league desk sat **under two long lists** (the roster's usage, the waiver watch) | both folded under their counts, so the live score, the to-do list and the lineup are a screen from the top; the lineup's slots wear their player's position colour |
| F10 | "How these numbers are built" stood **between the reader and the list** on This week, and the byes were said twice | folded under the list; the byes on the room's first line |
| F11 | Around the league listed **every rookie, a hundred rows** | twelve, the rest under a fold |

Held by the tests that already pinned these pieces (moved to the new
markup), plus `test_fantasy_101` (first visit open, then as left) and
`test_fantasy_tonight` (the night's rows wear the same row and badges).

# The whole app, pass one — 2026-10-27

The same request, then "look at all the other visuals for everything else".
Every main page (21 of them) at a phone and a desktop width, signed out, on
the live site's own public files, laid side by side on one sheet so the
things every page repeats show up as repeats.

| # | Finding | Fix |
|---|---|---|
| A1 | **Every subtitle wore the amber rule**: a 2px gold bar and a block of text under every section title on every page, so pages read as documents | a short subtitle is a muted line under its title; the rule stays for an explanation the reader opened behind "why?" |
| A2 | **Every card wore a stripe** down its left in the faintest colour when it had no grade: lists, forms and notes opened on a quotation bar | only a card with a grade (a pick's tier, a game bet, a long shot) wears one |
| A3 | **The stadium band was a 44px dark strip on a phone** over the Record, Live, Edge and Most Likely titles, reading as a glitch | gone on a phone; a computer keeps its 64px band |
| A4 | Row descriptions and fact chips in **typewriter type** ("QB · vs Cowboys", "3 games on the card") | the page's own type; prices and figures keep the mono |
| A5 | **The Edge page had no name at the top**: it opened on its legend, and the picks' own heading three blocks down took the page title's size | "Edge picks" first, with its line; the picks' heading is a section head again |
| A6 | The Record's scope buttons **shouted in tracked capitals** across three rows | sentence case, the same weight as every other filter |

Checked after in both themes. Held by the tests that pinned each rule
(moved to the new values): `test_the_venue_heads_the_proof_pages`,
`test_an_empty_board_carries_the_card`, `test_controls_look_clickable`.

# The lights on — 2026-10-27

Ethan: "i feel like we can use more colors and shit throughout the site too
to be more exciting and shit like that. animations and glowing shit." The
apps people call exciting (PrizePicks' neon More/Less, Underdog's yellow on
black, Sleeper's multi-hue accents and glowing live dots, DraftKings' and
Robinhood's green/red glows, Apple Sports' team colours) all do the same
three things: a colour per thing you can tell apart, light on what is live or
chosen, and motion when something arrives. Gold stays the brand (his call,
2026-08-23); around it:

| # | What was flat | Now |
|---|---|---|
| L1 | **Every league was gold**: seven identical crests | each league its own colour (football gold, college blaze, baseball sky, basketball violet, the WNBA coral, hockey ice, the UFC red); the open one ringed and glowing in it, on a phone and on the desktop's pills |
| L2 | **Every page the same black** whatever league was open | the top of every page glows in the league in view, and a section's icon wears it |
| L3 | **The home's four doors were four gold tiles** | Fantasy violet, Most Likely green, Edge gold, Bankroll sky, each tile washed and its icon lit in its own, glowing under the pointer |
| L4 | **Most Likely's third tier was grey** | Top green, Strong gold, Worth a look sky; the top two rings glow; the top tier's cards glow green; the night's best pick (#1) wears a moving holographic rim |
| L5 | **Nothing moved when a page opened** | the page rises in, section by section and card by card, once (never on a redraw, so a live page never flickers) |
| L6 | Buttons and cards **sat still under the pointer** | gold buttons are a lit gradient that glows; cards lift with a lit rim (mouse only); everything gives a little under a tap |
| L7 | **The brand and the AI were plain text** | the title is gold with a sweep of light across it; Ask Qellys glows, a sheen crosses it and its sparkle twinkles |
| L8 | Up and down chips were outlines; the record's rings were flat | tinted chips; rings that glow green up, red down |

Held by `test_the_lights_on` (and `test_design_tells`, whose shadow rule now
allows the `--glow-*` family: still one system of tokens). Checked in both
themes on a phone and a desktop. A phone keeps its budget: no blur, no layer
per card, and reduced motion zeroes every animation.
