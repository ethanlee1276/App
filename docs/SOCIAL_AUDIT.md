# The social feature: audit and build list (2026-10-07)

Ethan, 2026-10-07: *"go deeper … add a full social feature … take reference
from something like facebook or reddit … there needs to be profiles for
users which means a profile page … do a full audit of what we would need to
make this a full feature on the site then do it."*

## 1. What the reference apps do

| App | What it does that matters here |
|---|---|
| **Reddit** | Feed sorts: Hot, New, Top (by day, week, all), with Hot computed as `log10(score) + age/45000` so a busy post rises and then fades over hours. Topic channels (subreddits). Threaded comments under every post, with votes on comments. Profile pages list posts and comments with a karma total. Text posts that carry a title and a body. Report, block, mod queue. |
| **Facebook** | A profile page: cover banner, avatar, name, bio ("About"), friends and followers, and that person's posts. Reactions and comments with replies. @mentions that notify. A notifications bell with an unseen count. Share and copy-link on every post. Edit and delete your own posts. |
| **Pikkit** | Bets are synced from sportsbooks, so every record is real and nobody can type one in. Leaderboards of the best performers. You follow people and tail their action with one tap. |
| **Action Network** | You follow friends and experts and get a live feed of their picks, plus an alert when someone you follow posts. A bet cannot be edited once it is entered, and records are built from those logged bets. Leaderboard and season review. |
| **Betstamp** | Records verified against the market, a community of friends, and picks sold through a verified marketplace. |

The lesson all three betting apps share: **a record nobody can fake is what
makes the feed worth reading.** Reddit and Facebook supply the shape:
profiles, follows, threads, notifications and sorting.

## 2. What the site had before today (2026-10-06 build)

Public posts of 1–3 board legs with a caption · Tail (whale tail) with a
counter and links to the books · likes · one level of comments · a handle and
a bio · reports (3 hide) · owner hide · slurs refused and swearing masked ·
paid legs locked for readers who have not paid.

## 3. Gaps, and what was built for each

| # | Gap | Built |
|---|---|---|
| 1 | No profile page | A profile page at `#feed/u/<handle>`: a banner and avatar in the colour the person picks, display name, @handle, bio, favourite team crest, the date they joined, and a stat row (record, units, ROI, followers, following, tails received). Tabs for Posts and Record. |
| 2 | No follows | Follow and unfollow, with follower and following counts and lists, a **Following** feed tab, and a notification on a new follower. |
| 3 | No record | **Every posted parlay is graded automatically** from the journal's own results: each leg is checked against the stat the journal recorded (the same source the Record page uses). The post shows Won, Lost, Push or Pending with a mark on each leg. The profile shows W-L-P, units (1 unit per post at the posted price) and ROI, all-time and for the last 30 days. |
| 4 | Records could be gamed | Legs can only be posted **before their game starts**, legs can never be edited, and only the caption can be changed, within 15 minutes, marked "edited". This is the Action Network rule. |
| 5 | One feed order | **Hot** (Reddit's formula over likes, tails and comments), **New**, **Top** (today, this week, this month, all time) and **Following**, with sport chips and a Picks / Talk switch. |
| 6 | Parlays only | **Talk posts**: a title and a body (up to 2,000 characters) with a sport tag — Reddit's text post — for "who's starting at QB for the Jets?" threads. |
| 7 | Flat comments | **Replies** one level deep (Instagram/Facebook style), **likes on comments**, and @mentions that link to the profile and notify. |
| 8 | No notifications | A notifications page and an unseen-count badge on The Feed's sidebar entry: likes, tails, comments, replies, mentions, new followers, and "your parlay won/lost". |
| 9 | No leaderboard | **Top bettors**: units won over the last 30 days (5 or more graded posts to qualify), win rate, and most tailed this week. |
| 10 | No search | Search people by handle and posts by player, team or words. |
| 11 | No sharing | A permalink for every post (`#feed/post/<id>`) and profile, with Copy link and the phone's own share sheet. |
| 12 | Thin moderation | **Block** a user: you stop seeing each other, and neither can follow or comment on the other. Report reasons. New accounts (under a day old) are capped at 3 posts a day. A cap of 100 follows a day. |
| 13 | Friends layer separate | The profile carries **Add friend** (the existing request flow) and **Message** when you are already friends, so the private inbox and the public feed join up. |
| 14 | Weight on the first visit | The social code loads **only when someone opens The Feed** (`js/social.js`, `css/social.css`), as the chart library already does. Everyone else downloads nothing extra. |

## 4. Data and tools

- **Storage:** SQLite `accounts.db`, as the rest of the account features use. New tables: follows, blocks, comment likes, notifications. Posts gain a kind, a title, a body, a result and an edit time; profiles gain a display name, an avatar colour and a favourite team. Everything is deleted with the account and included in its export.
- **Grading:** the journal (`ledger.db`, table `bets`) already stores the actual stat for every graded pick. A leg is graded by comparing its own line with that actual value, so a leg posted at a different book's line is still graded at the line the poster took. Game legs use the journal's game keys (`ledger.game_row_keys`). Grading runs when the feed is read (the same lazy fold the tail/fade record uses), so it needs no new scheduled job.
- **Ranking:** Reddit's Hot formula, computed in SQL at read time; at this site's volume no cache is needed.
- **No new outside service, key or cost.**

## 5. Deliberately not built, and why

- **Photo uploads (avatars, images in posts).** These need image storage, resizing, and moderation of uploaded pictures, which is the most dangerous part of running a public site (illegal images). The avatar is a colour plus initials or a team crest instead. It can be revisited with a moderation service if Ethan wants it.
- **Syncing real sportsbook accounts (Pikkit's model).** That needs sportsbook logins, which this site does not take.
- **Push notifications to the phone and email alerts.** The bell and its badge cover it on the site. Push needs the web-push setup and permission prompts; it can come next if wanted.
- **Downvotes.** Reddit's downvote turns a betting feed into a pile-on over losing tickets; likes and tails measure what this feed is for.
- **Paid picks shown to people who have not paid.** Unchanged from yesterday: a paid leg shows only the player and market to a reader who has not paid.
