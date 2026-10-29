# Retention: what brings people back, and what this site does about it

Ethan, 2026-10-29: *"dive deep more into the science of user retainment and
being able to keep users and having users come back to the app and feel like
they need to use our app when there's live games going on ... do research on
that, look up data research and all that ... build it."* And: *"there needs to
be a setting for when you first log into the app ... it'll prompt you to turn
on notifications."*

This is the research, what was built from it, and what was deliberately not
built. Every number below is cited, and most published numbers in this field
come from the companies that sell push tools, so they are marked as vendor
figures. Where the honest answer is "measure it on our own users", the last
section says how.

---

## 1. What the research says

**Alerts are the lever, and most people say yes or no to them once.**

- A typical iPhone app gets alerts turned on by roughly **45–50%** of users
  (Airship's 2025 median for iOS: 48.85%; Pushwoosh's 2025 survey of 600+
  apps puts most iOS apps under 50%). Android is a little higher.
  Source: [MobiLoud's opt-in benchmarks](https://www.mobiloud.com/blog/push-notification-opt-in-rate),
  [OneSignal 2024 benchmarks](https://onesignal.com/mobile-app-benchmarks-2024)
  (category range: 20.6% in games to 48.7% in finance).
- **Asking in context beats asking cold.** Apple's own guidance is to ask
  "in a context that helps people understand why your app needs
  authorization", not on first launch before there is any context, and the
  system prompt only ever appears once.
  Source: [Apple, Asking permission to use notifications](https://developer.apple.com/tutorials/data/documentation/usernotifications/asking-permission-to-use-notifications.md).
- **A primer screen before the system prompt** (our own card first, the
  phone's prompt only on "yes") lifts opt-in. Evidence is mostly anecdotal and
  vendor-published: Cluster reported ~60% in social with its own pre-ask
  screen ([Andrew Chen](https://andrewchen.com/why-people-are-turning-off-push/amp)).
  Treat it as a direction, not a promise.
- iOS 12+ also allows **provisional** alerts (delivered quietly to
  Notification Center with no prompt; the person keeps or turns them off)
  ([useyourloaf](https://useyourloaf.com/blog/provisional-authorization-of-user-notificatons/)).
  Capacitor's push plugin does not ask for it today, so it is noted for the
  native app's next pass, not built.

**Fewer, more relevant alerts keep alerts on.**

- In a Localytics survey of 1,000 US smartphone users, **10%** said they would
  turn alerts off at one a week, **37%** at 2–5 a week, and **22%** would stop
  using the app at 2–5 a week (stated intent, not measured behaviour)
  ([MarketingProfs](https://www.marketingprofs.com/charts/2018/33486/how-many-mobile-push-notifications-are-too-many)).
- Alerts set off by something the person did or cares about beat broadcasts
  by a wide margin in every vendor dataset (Segment, 1.5 billion pushes:
  behaviour-triggered alerts were opened about 8x as often as blasts —
  [Segment](https://segment.com/blog/push-notification-study-analysis)).
  Braze reports alerts sent at each person's own best hour drive about 2.6x
  the opens ([Braze](https://www.braze.com/perspectives/article/two-ways-to-master-push-campaign-timing)).
  Both are vendor figures without published controls.

**The one peer-reviewed algorithm worth copying is Duolingo's.** Yancey and
Settles (KDD 2020) chose each person's daily reminder from a pool with a
"sleeping, recovering" bandit (a template just used is worth less for a
while) and measured **+0.5% daily active users and +2% new-user retention**
over a strong baseline
([paper](https://research.duolingo.com/papers/yancey.kdd20.pdf)). It needs
volume to learn; at this site's size it would act close to random for
months, so it is listed in §4, not built.

**Live games are where a sports app is won.**

- Sports apps see users come back more often through the first 30 days than
  most categories, because events bring them back (Airship's lifecycle
  benchmarks, sports alongside finance).
- Fans check their phones about ten times a game, mostly in the breaks (a
  2026 Snapchat survey of 1,000 UK Gen Z fans, as reported: 46% in natural
  breaks, 20% during play; the source page could not be opened from here to
  confirm it). The older, better-known figure is Google's: most people watch
  with a phone or laptop within reach
  ([Think with Google](https://thinkwithgoogle.com/consumer-insights/sports-fans-and-the-second-screen)).
  The design answer is glanceable: the score where they already look, the
  moment that matters, the chat in the break.
- **Live Activities** (the score on the lock screen and in the Dynamic
  Island) are what ESPN, theScore, the NBA's and Yahoo's apps use to own a
  game on the phone; OneSignal reports apps using them have **23.7% higher
  30-day retention** (vendor figure)
  ([OneSignal](https://onesignal.com/blog/best-practices-for-using-live-activities-in-your-ios-app/),
  [Yahoo Sports](https://help.yahoo.com/kb/SLN37033.html)).
- Real (the app Ethan named) wins the live game with discussion, predictions
  and points around each play
  ([App Store](https://apps.apple.com/us/app/real-sports/id1514546162));
  reviewers also call its alerts annoying. Our game chat, Call it, trivia in
  the stoppages, karma, watch parties and the fans' player of the game are
  that layer already.

**Gambling apps are under a spotlight for exactly this.** In July 2026 the
National Consumers League asked the FTC to require consent for marketing
alerts from betting apps (93% of alerts they studied from the big
sportsbooks were ads, 62% "bet now" calls to action); Colorado banned
operator-initiated betting pushes outright (SB 26-131); bills are moving in
New York and Congress
([NCL](https://nclnet.org/ncl-petitions-ftc-for-sports-betting-prediction-market-notification-controls/),
[Covers](https://www.covers.com/industry/ncl-report-warns-sportsbooks-using-push-alerts-gambling-harm-august-2025)).
This site is not a sportsbook, but its alerts are written as if the rule
were already law: opt-in, every kind its own switch, scores and records and
the member's own bets — **never "bet now", never a pick on a lock screen**.
That is also simply what keeps alerts switched on.

---

## 2. What we will not do, and why

**Read how people use other apps, or their phone's settings.** It is not
possible on an iPhone (every app is sandboxed; there is no API for another
app's usage) and on Android it needs a special usage-access permission that
Google Play restricts and users rightly refuse. It would also break this
site's privacy promise ("we run no advertising, no tracking pixels and no
third-party scripts ... nothing on this site follows you anywhere else") and
the laws behind it. What the big apps actually use is **first-party**: what
a person does inside their own app, when, and whether they tap an alert.
That is §3 and §5.

**Buy or share data, fingerprint devices, or add third-party trackers.** Same
promise, same reason.

**"Bet now" alerts, streak guilt or loss-chasing nudges.** See §1: they are
what regulators are moving against, and they burn the alert switch.

---

## 3. What was built (2026-10-29)

| | What | Runbook |
|---|---|---|
| Ask at the right moment | After a sign-in on a phone or in the app, a card asks to turn alerts on (our primer first, then the phone's prompt). Asked again only beside something an alert serves — following a team ("a tap ten minutes before every Packers game"), a bet put in My Bets — three times at most, two weeks apart, never once on or refused, never on a desktop browser. What turns on is personal first: the followed teams' games, big moments and finals, your bets, your watches, last night's record, and the picks going up for **the leagues you follow only**. | HT |
| The game on the lock screen | On my lock screen on any live game (or within 90 minutes of the start): the score, clock and situation on the lock screen and in the Dynamic Island, kept current by the box every 20 seconds and ended at the final. | HU |
| Fewer, better picks-up alerts | At most one "picks are up" alert per phone every three hours, and when several leagues are up it is one alert naming them all, not one per league. | HV |
| Measure it | When analytics is on (QB_ANALYTICS=1, after the privacy wording in docs/AUDIT_2026-09-23.md item 14), daily totals of alerts sent by kind and of visits that came from an alert — never per person. | HV |

Already in place before this round, and part of the same picture: kickoff
alerts for followed teams, big moments (four a game at most), final scores,
the parlay on the lock screen, quiet hours (23:00–09:00 Eastern for anything
not tied to a game), the game chat and watch parties, trivia in the
stoppages, karma, streaks, pick'em, the Monday recap.

---

## 4. Next, in order of value per unit of work

1. **Provisional alerts in the iPhone app** — quiet delivery with no prompt,
   so a new install sees what an alert looks like before deciding. Native
   change (one authorization option) plus an App Store build.
2. **Each person's own best hour** for the alerts that are not tied to a
   game (picks up, last night, the Monday recap): learned on the phone from
   when it opens the app, sent to the box as a setting, never as a log.
3. **A/B the ask's wording** once analytics is on: two versions of the card,
   split by a coin flip on the phone, compared as daily totals.
4. **A recovering bandit for recurring alert wording** (Duolingo's method)
   once the alert volume can teach it something — thousands of sends a week.

---

## 5. How to know it worked

With analytics on, `python3 -m engine.analytics report 30` prints, per day:
visits, visits from an alert, alerts sent by kind; and the account lines it
already had: the share of accounts seen again after their first day and
first week (from `users.last_seen`, already in the privacy policy). The
numbers to watch, against the benchmarks in §1:

- alerts turned on per sign-in on a phone (target: above the ~45–50% iOS
  median);
- visits from alerts per alert sent, by kind (drop or rewrite the kinds
  that nobody opens);
- day-7 and day-30 return rate of new accounts, before and after.

---

## 6. Each member's own activity, and what it is for (2026-10-29, round two)

Ethan, the same day: *"I've been seeing research about how apps will use data
off your phone to see how much worth you are to them, and how to get
retention rate off of you ... look at other apps' algorithms and what they
do, and let's start implementing that stuff"* — and *"we can be recording
what users do on the app, how long they spend on it, and we can base
notifications off that."*

### What the apps that are good at this actually use

Almost all of it is **first-party usage**: what a person does inside the
app, when, and whether they open its alerts. Not their other apps (§2).

- **Each person's own hour.** Braze's Intelligent Timing sends each message
  in the person's "most engaged hour", read from their own session starts
  and alert opens, with a chosen fallback when there is too little history
  ([Braze docs](https://www.braze.com/docs/user_guide/brazeai/intelligence/intelligent_timing)).
- **Who is drifting.** Airship's churn model found how recently and how
  often someone opened the app, and how many alerts they were sent, the
  strongest signs (vendor, 2017:
  [Airship](https://www.airship.com/blog/churn-prediction-our-machine-learning-model/)).
  A peer-reviewed study of mobile games found long-run frequency the single
  most important feature among recency, frequency, money, lifetime and
  intensity ([CRORR, RFM-LIR](https://ojs.srce.hr/crorr/article/view/12125)).
- **The textbook model for "still a customer?"** when nobody cancels, they
  just stop coming: Fader, Hardie and Shang's BG/BB, built for exactly this
  data (a chance to come each day; a hidden moment someone stops for good)
  ([Marketing Science 2010](https://faculty.wharton.upenn.edu/wp-content/uploads/2012/04/Fader_et_al_mksc_10.pdf)).
- **Reading engagement as a curve, not one number.** The power-user curve
  (L28: how many people were active 1, 2 ... 28 days of the last 28) shows
  whether a core comes back daily, which DAU/MAU averages away
  ([a16z, Chen and Jin](https://a16z.com/the-power-user-curve-the-best-way-to-understand-your-most-engaged-users/)).
- **Stopping, not shouting.** Duolingo's reminders end after weeks of being
  ignored ("These reminders don't seem to be working. We'll stop sending them
  for now." — as a user reported it,
  [Medium](https://debugger.medium.com/duolingo-needs-to-chill-8f1832745ca0)).
- **Value per customer.** Every subscription business divides revenue per
  member by the cancellation rate for a lifetime value, and segments it.
  **What we will not copy:** the sportsbooks' "VIP" models that score each
  bettor's lifetime value and then treat the high scorers differently, the
  practice now under a US Senate inquiry (Blumenthal's letters, October
  2026: [SBC Americas](https://sbcamericas.com/2026/10/22/congress-blumenthal-betting-vip-letter/))
  and in lawsuits; even the industry's own group says no VIP incentives for
  anyone in a cool-off ([ROGA](https://sbcamericas.com/2025/05/29/roga-sportsbooks-guidelines-vip-players/)).
  Here value is a figure for the owner, by group, and nobody is treated
  differently by what they pay or might pay.

### What was built

| | What | Where |
|---|---|---|
| Your activity | Per member, a row a day: seconds with the site in front of them (visible and touched in the last two minutes; half an hour on a live game), visits, visits an alert opened, seconds by page, by league and by hour. Kept 120 days, deleted with the account, in the export. | engine/activity.py, web/js/activity.js |
| Two locks, then a yes | Nothing is kept until `QB_ACTIVITY=1` **and** the Privacy Policy carries the section below (`id="your-activity"`) — and then, for each member, only after **they** say yes: in Settings → Your activity, or with the unticked box on the "Make it yours" card. Settings shows them everything kept, in words; no deletes it all. Each yes and no goes in the consent log with the policy's date. | engine/activity.consented, engine/consent, account.js actHTML / mineSheet |
| Stages | new · power · regular · casual · lapsing · dormant · gone — "lapsing" measured against the member's **own** rhythm (2.5 × their usual gap, at least a week), so a Sunday-only football fan is not "drifting" on Friday. | engine/engagement.stage |
| Still around? | BG/BB fitted on our own members; kept only if, on members it never saw, it predicts who comes back better than the stages do (`fit --save`). Checked against simulation: calibrated across every quintile. | engine/engagement.fit |
| The owner's report | Stages with revenue in each and **revenue at risk**, the power-user curve, DAU/MAU, minutes a day, leagues, busiest hours, share of visits from alerts, new members still here in weeks 1, 2 and 4 by signup week, the model's view, ARPU, monthly churn and lifetime value. `demo` prints it on a made-up population. | `python3 -m engine.engagement report` |
| While you were away | A member gone longer than their own rhythm (lapsing or dormant, never "gone"), with the switch on, hears once at their own best hour: their team's game today; else the newest thing shipped since they were last here; else today's slate in their league. One a week at most; after three unanswered, none until they come back. | engine/engagement.away_pass |
| Fewer to the phones that never open them | A phone with 15 picks-up / last-night alerts in a row unopened gets those two kinds once a day at most, until its member opens any alert. Scores and their own alerts are untouched. | engine/pushalerts.IGNORED_N |

### The Privacy Policy wording to approve (it turns the switch on)

Paste as a new subsection of §2 in `web/privacy.html` (the `id` is the lock):

```html
<h3 id="your-activity">2.8 Your activity here</h3>
<p>Only if you say yes — in Settings → Your activity, or on the "Make it
  yours" card — and while you are signed in, we keep a daily record of your
  own time on this site: how many
  seconds a page of it was in front of you (only while the tab is visible and
  you have used it in the last two minutes, or watched a live game in the last
  half hour), on which of our pages and for which leagues, in which hours of
  the day, how many visits you made and how many of them one of our alerts
  opened. Never your clicks, anything you type, your location, your device, or
  anything about other apps or sites.
  (<code>activity_days</code>, <code>activity_prefs</code>,
  <code>engagement_away</code>)</p>
<p>We use it for your own alerts — to send the ones not tied to a game at the
  hour you usually look, to send fewer of the kinds you never open, and, if you
  turned on "When I’ve been away", one line a week at most with your team’s next
  game or what is new — and, as totals, to see how the site is used. It is
  never sold, shared, or used for advertising, and nothing about what you pay
  changes how we treat you. Each day’s row is deleted after 120 days, all of
  it when you say no or delete your account, and it is in Download my data.
  We keep a record of each yes and no you give us — what it was about, the
  date of this policy at the time, and when (<code>consent_log</code>) —
  until you delete your account; it is in Download my data too.</p>
```

### Before switching it on (the runbook's step HW)

1. Ethan approves (or edits) the wording above; it goes into the policy in a
   commit, and the policy's date at the top moves.
2. **The App Store privacy label** must say it before the iPhone app ships
   with it: App Store Connect → App Privacy → Usage Data → **Product
   Interaction**, "Linked to the user's identity: Yes", purposes **App
   Functionality** and **Analytics**, "Used for tracking: No"
   ([OneSignal's guide](https://documentation.onesignal.com/docs/apple-app-privacy-requirements),
   [Apple's labels](https://www.apple.com/sg/privacy/labels/)).
3. `sudo ./deploy/setenv.sh QB_ACTIVITY 1` and restart.
4. After four weeks of rows: `python3 -m engine.engagement fit`, then with
   `--save` only if it says it holds.
