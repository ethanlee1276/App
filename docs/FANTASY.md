# The Fantasy room: what it is for, what it does, what it adds next

Ethan, 2026-10-27: *"I want to make sure we're using all our tools and data
and information and all that shit we gather and collect and using it in our
fantasy room as well. And that the fantasy room is actually a useful tool and
doing what it's supposed to be. Like, I don't know how fantasy works … look at
other apps, look at other examples … create more features and think of more
features and invent more things for our fantasy room."*

This page has four parts: how fantasy football works, in plain words; what
our room does today, tab by tab, and which of our data feeds it; what the big
apps do that we don't; and the new features, built and next.

---

## 1. How fantasy football works (the 60-second version)

- **A league** is usually 10–12 friends. Before the season everyone
  **drafts** real NFL players, taking turns, until each has a full roster
  (about 15 players).
- **Every week you set a lineup** from your roster, usually: 1 QB, 2 RB,
  2 WR, 1 TE, 1 FLEX (a RB, WR or TE), 1 K (kicker) and 1 D/ST (a whole
  team's defense and special teams). Everyone else sits on your **bench**
  and scores nothing for you that week.
- **Your starters' real stats become your points.** The common scoring:
  - 1 point per 10 rushing or receiving yards, 1 per 25 passing yards;
  - 6 per rushing or receiving touchdown, 4 per passing touchdown;
  - −2 per interception thrown, −2 per fumble lost;
  - **PPR** ("point per reception") leagues add 1 point per catch; half-PPR
    adds 0.5;
  - a kicker scores 3 for a field goal (more for long ones) and 1 per extra
    point;
  - a D/ST scores for sacks (1), interceptions and fumble recoveries (2),
    defensive or return touchdowns (6), and a bonus that shrinks the more
    points the defense allows (10 for a shutout, about 0 at 21–27, negative
    past 28).
- **You play one team in your league each week.** Higher total wins. The
  best records make the **playoffs**, usually weeks 15–17.
- **The weekly rhythm:**
  - *Tuesday–Wednesday:* **waivers**. Players nobody owns are free agents;
    you put in claims for them. Many leagues use **FAAB** (a free-agent
    budget, e.g. $100 for the season): everyone bids blind, highest bid
    wins. Others use a priority order.
  - *Thursday:* the first game; players in it lock at kickoff.
  - *Sunday morning:* the injury check. Teams announce **inactives** about
    90 minutes before kickoff; starting someone who doesn't play is the
    classic way to lose.
  - *Any day:* **trades** with other managers.
- **Byes:** every NFL team has one week off; its players score zero that
  week.
- **Injury tags:** Q (questionable, usually plays), D (doubtful, usually
  doesn't), Out, IR (out for weeks).

The whole game is four decisions, every week: **who to start, who to pick
up, who to trade for, and who to drop.** A good fantasy tool answers those
four for *your* team, in *your* league's rules.

## 2. What our room does today (audited 2026-10-27)

| Tab | What it shows | What feeds it |
|---|---|---|
| **This week** | Every player's points this week (PPR), his range (the measured 10th–90th percentile), chance he plays, matchup grade, role change; members also see the stat line, touchdown chance, game script and reasons | The NFL prop board's projection chain (form, measured role, defense vs his position, game script, weather, QB/teammate out, team pace), the touchdown model, the practice reports (`engine/fantasyweek`) |
| **Usage** | Target and carry share: season vs last 4 weeks vs last week, red-zone work | nflverse weekly usage (`engine/fantasy`) |
| **Waivers & starts** | Players whose job just changed (a starter out, a rising share), the best spots this week, Sleeper's trending adds | Injuries + usage (`engine/waivers`), Sleeper trending |
| **Trade targets** | Buy low / sell high: scoring vs what the opportunity says | Volume-expected points (`engine/fantasy`) |
| **Game scripts** (members) | Implied totals, pass rate over expected, EPA, pace per game | Vegas lines + play-by-play (`engine/gamescript`, `teamprofiles`) |
| **Rankings** | Our board beside Sleeper's and your draft's live order | `engine/fantasy_ranks` |
| **Calendar** | Your roster day by day, then the league's best plays | the league desk |
| **Mock draft** | A full snake draft against a simulated room, survival odds, grades | the draft kit (`engine/fantasy_draft`, `draftplan`, `draftmarket`) |
| **Around the league** | League linking (Sleeper, ESPN, Yahoo), your league desk, camp watch, offseason moves, the draft kit | |

**The league desk** (inside Around the league, for a linked league): your
best lineup under your league's own scoring and slots, the swaps to make;
this week's head-to-head with a win chance and the swings; every team's
roster; standings; trades that help both sides; the best free agents this
week. Lineup and head-to-head read this week's projections; trades read
season averages.

**What's good:** the projections are real and measured (this week's numbers
beat season averages on 10,445 player-weeks, `docs/FANTASY_WEEK.md`); the
desk uses the league's own scoring; injuries and byes count as zero.

**What was missing** (the gaps this round closes, or plans):

1. **No team defense.** Almost every league starts a D/ST, and the desk
   valued every defense at zero, so it could not pick one, and no pickup
   list ever named one. We hold everything a defense projection needs:
   Vegas totals, each team's sacks and takeaways, each quarterback's
   interceptions.
2. **No "what do I do this week".** The answers are spread across five
   tabs. A newcomer can't tell which one matters today.
3. **No plain-English start.** Nothing says what fantasy is or what the
   tabs are for.
4. **No "A or B?"** The most common fantasy question has no direct tool.
5. **No playoff odds or power rankings** for your real league (only the
   mock draft simulates a season).
6. **Waiver help isn't about your team.** The pickups are the league's
   best, not the best *for your roster*, and nothing says what to bid or
   whom to drop.
7. **No alerts.** Nothing warns you that a starter was ruled out, which is
   the one mistake every app guards against.
8. **No look back.** No recap of the week: what you scored against your
   best possible lineup, the league's awards.
9. **Nothing live.** During games the room doesn't use the live box scores
   we already draw on every game page.
10. **Football only.** We project NBA and NHL props daily and have no NBA or
    NHL fantasy at all.

## 3. What the big apps do

- **ESPN (2025 app):** a home screen showing where each starter ranks, a
  dashboard that flags actions (check waivers, review trade offers), live
  in-game projections on the matchup and roster screens, AI weekly
  insights, boom/bust probabilities, waiver and trade grades, a trade
  analyzer ([ESPN](https://espnpressroom.com/us/press-releases/2025/08/espn-fantasy-football-30th-anniversary-new-design-new-features-all-new-fantasy-app-for-2025/),
  [IBM watsonx](https://betanews.com/2025/09/24/espn-fantasy-football-adds-ai-powered-weekly-insights-from-ibm-watsonx/)).
- **Yahoo:** "Assistant GM" sets your lineup and shows each change's effect
  on your projected score and win probability; AI draft recaps; a weekly
  league recap with top performers, letdowns and points left on the bench
  ([Yahoo](https://www.aol.com/sports/introducing-assistant-gm-smart-feature-125543677.html),
  [recaps](https://www.aol.com/sports/relive-fantasy-action-weekly-league-125545010.html)).
- **FantasyPros (league sync, 15+ hosts):** start/sit assistant, waiver
  assistant with FAAB bids, trade analyzer and trade finder, power
  rankings, playoff odds, this week's win probability
  ([FantasyPros](https://www.fantasypros.com/mcp/)).
- **Sleeper:** league chat, real-time news, injury and score alerts in one
  feed ([Play Store](https://play.google.com/store/apps/details?id=com.sleeperbot)).
- **Recap apps (League Rewind):** AI weekly recaps, season and draft
  summaries, for Sleeper leagues
  ([App Store](https://apps.apple.com/app/id6499177011)).
- **D/ST streaming (4for4, Rotowire, FantraxHQ):** points allowed from the
  Vegas implied total, sacks from both teams' pressure and sack history,
  interceptions from the opposing quarterback's history
  ([4for4](https://www.4for4.com/2019/w9/streaming-defenses-week-9-targets)).
- **FAAB:** no agreed formula; bids scale with how long the job lasts and
  your roster's need, and most guides keep a reserve for later weeks
  ([4for4](https://www.4for4.com/node/181296),
  [Fantasy Index](https://fantasyindex.com/2024/04/10/analysis/the-art-of-faab)).

Most of what they sell, we already compute better: our projections are the
prop board's measured chain, not an expert average. What they have that we
didn't is the *packaging*: one place that says what to do, the defense
slot, the season view, alerts and recaps.

## 4. The new features

Built and shipped are marked **SHIPPED** with the date; the rest is the
queue, in order.

1. **Fantasy 101** — SHIPPED 2026-10-27. A card at the top of the room: what fantasy is, the
   weekly rhythm, what each tab is for, and a glossary (flex, bye, FAAB,
   stream, handcuff, floor and ceiling). Dismissible.
2. **Team defenses (D/ST), projected** — SHIPPED 2026-10-27. Each defense's points this week
   from the opponent's Vegas implied total (the points-allowed bonus,
   scored on the league's own tiers), expected sacks (its sack rate against
   the opponent's sacks allowed), interceptions (the opposing quarterback's
   and the defense's rates), fumble recoveries and touchdowns. Into "This
   week", the lineup, the head-to-head and the pickups; a streaming list.
   Measured on the box by `dstfit.py` against each defense's season
   average, once the past seasons' turnovers are filled in (2026-10-28:
   `python3 -m engine.sources.nflpbp --team-weeks 2022-2025`; the first
   measurement read 0.0 takeaways a game off seasons stored before they
   were counted, and dstfit now refuses until they are).
3. **Your week, as a to-do list** — SHIPPED 2026-10-27. For a linked league, the top of the
   desk says what to do now: lineup fixes (with the points each gains),
   starters who are out or on a bye, questionable starters and when their
   game kicks off, your win chance, the best pickup for your roster, next
   week's byes, the best trade.
4. **Start A or B?** — SHIPPED 2026-10-27. Pick two to four players; side
   by side: points this week, range, matchup, chance to play, and the call,
   with how often each outscores the other and the clock on a questionable
   one (engine/fantasy_compare). Ask gives the same call.
5. **Playoff odds and power rankings** — SHIPPED 2026-10-27 (Sleeper
   leagues). The rest of the regular season simulated with each roster's
   projected strength and the league's own schedule; each team's playoff
   and first-place chance, projected record and seed, what record gets you
   in, and power rankings with the all-play record and luck
   (engine/fantasy_season).
6. **Waivers for your roster** — SHIPPED 2026-10-27. Free agents ranked by what they add to
   *your* starting lineup; a FAAB bid range where the league uses a budget;
   the bench player to drop.
7. **Lineup alerts** — SHIPPED 2026-10-27 (Sleeper leagues). Opt in, and a
   push tells you when a starter you still have in is out, on IR,
   suspended, on a bye or doubtful (engine/lineupalerts). The push names
   the player and his designation, both public; the replacement is the
   to-do list's, a tap away, because a push carries no projection.
8. **The week in review** — SHIPPED 2026-10-27 (Sleeper leagues). Last
   week: your score against your best possible lineup (points left on the
   bench), your costliest and best calls (and whether the costly one cost
   the game), and the league's awards (top and lowest score, blowout,
   closest game, unluckiest loss, luckiest win, sharpest lineup, most left
   on a bench, player of the week, best on a bench).
9. **Your matchup live** — SHIPPED 2026-10-27 (Sleeper leagues): the score
   as it stands from Sleeper's own points for the lineup set, each side's
   projected final with what is left projected from each game's clock,
   the win chance, slot by slot, refreshing every minute
   (engine/fantasy_live). **Fantasy points on the game pages** — SHIPPED
   2026-10-27: each football game page leads its Player stats with the
   game's top fantasy scorers, PPR and half-PPR.
10. **NBA and NHL tonight** — SHIPPED 2026-10-27: every player on each
    night's basketball and hockey boards in daily-fantasy points (1 a point,
    0.5 a three, 1.25 a rebound, 1.5 an assist, 2 a steal or block, −0.5 a
    turnover; hockey 8.5 a goal, 5 an assist, 1.5 a shot, 1.3 a blocked
    shot), from the same projections as the props, a stat the board does
    not price filled from the season average and drawn dim
    (engine/fantasy_daily). A tab of its own, "NBA & NHL tonight", while a
    slate is tonight's; the points free, the stat line the members'.
