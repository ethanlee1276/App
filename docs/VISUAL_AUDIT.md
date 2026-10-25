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
