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

## 6. Third cut: Ethan's render and one profile (2026-10-07, evening)

Ethan: "The social page looks cluttered … Here is renders you must follow
for the social page and profile page. Also the account page on the feed
page and the main account page should be one page … it should all be one
main profile for the whole site." One render arrived (the social page);
the profile page was drawn in the same style because no second render
came through.

**The page, in the render's layout and the site's colours.** Gold on warm
black stays (Ethan, 2026-08-23: "carried through the whole site so
everything matches"); the render's navy is the only thing not copied.

| Render | Built |
|---|---|
| Left column: Post, Feed, Following, My Posts, Trending, Top Bettors, Tags; Sports | Same, plus Activity (notifications) with its unread count; on phones and tablets the same doors are a row of tabs |
| Banner: an athlete per sport, logo, tagline | The site's own stadium scenes (NFL, MLB, NBA, NHL, WNBA), crown and wordmark in the middle. The render's athletes are real people's likenesses. Tagline "Post your plays. Talk sports. Sweat together." — the site never prints a promise of winning |
| Composer: Parlay, Image, Poll, Link, Post | Parlay (search today's board, up to three legs), Poll (2–4 options, three days), Link (https only, not on an account's first day). No Image (section 5) |
| Chips: For You, Following, sports | Same; For You is Hot with no time window, so a quiet week never empties it |
| Post card: avatar, name, verified tick, time, sport pill, legs with team logos, odds, likes, comments, share, Tail | Same; the site's own account wears the crown mark |
| Rail: Trending Picks, Top Bettors (Win % / Units / Followers, 30D), Popular Sports, Community Stats, Discord | Same, with 7D / 30D / All |

**What the numbers mean.** Trending Picks: every open parlay from the last
two days, each leg counted once per person who posted or tailed it, over
everyone active on those posts ("72% tailing"); fewer than ten active
people shows "3 of 4 tailing" instead of a percentage. Top Bettors: Win %
is won ÷ (won + lost), Units is one unit a post at the posted price, both
need five graded posts in the window; Followers counts follows made in the
window. Community Stats: profiles, posts showing, and the feed's graded
win rate, shown once ten parlays are graded. All counted, none estimated.

**One profile.** The Account page is now your profile page: the same
header everyone else's profile wears, then Posts / Graded picks / Friends
/ Settings. Your own handle and the old `#feed/edit` both open it. The
top-bar avatar, the sync strip and your side of a chat show the profile's
initials and colour; friends and friend search see the profile name; the
streak leaderboard shows it too (appearing there is still your choice).

**Verified and the site's names.** Any handle or display name containing
"qellys", "zeno", "admin", "moderator" or "official" is refused, so nobody
can pose as the site. The owner gives the site's account its handle and
badge from the box (runbook step 28); a verified handle cannot be renamed
from the page.

**Data and tools.** Three new tables: tags, polls, votes. No outside
service, no new key, no cost. Delete and export cover all three.

