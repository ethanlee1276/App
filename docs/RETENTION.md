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
