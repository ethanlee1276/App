# Syncing a fantasy league that isn't Sleeper

Ethan, 2026-08-15: *"Find out how to find sync more then just sleeper
fantasy league."*

Here is the real answer, platform by platform, with the one thing that
decides each: **can it be read without a THIRD-PARTY credential.**

**Updated 2026-08-15.** This site now has its own accounts — email and
password, `engine/accounts.py`. An older version of this page said the
site "never takes a login", and that is no longer true and should not be
read as a promise.

What has not changed is the rule that actually mattered, which was always
narrower than that sentence: **we do not ask you for a password to
somebody else's service.** A Qellys password and a DraftKings password
are different objects. We can scope, rotate and delete ours; we can do
none of those things to yours, a fantasy platform's session cookie grants
full account access, does not expire quickly, and cannot be scoped down.
So platforms are sorted below by whether they need one of *those*.

---

## Tier 1 — public read API, no credential. Same shape as Sleeper.

These are cheap to add: a URL, a JSON parse, and a name join. Each is
roughly the work already done for Sleeper.

### Sleeper — **done, in production**
`https://api.sleeper.app/v1/`. No key, no auth, no registration. The
whole league graph is public: user → leagues → rosters → users → drafts →
picks. Already wired through the server's allowlisted proxy
(`server.py`, `_SLEEPER_OK`), which is what keeps it from becoming an
open relay.

### MyFantasyLeague (MFL)
`https://api.myfantasyleague.com/{year}/export?TYPE=...&L={league}&JSON=1`.
Public leagues read with no auth at all. Private leagues need an API key
the **commissioner** generates for the league — that is a league-scoped
token, not a personal password, and it is revocable. Acceptable.

### Fleaflicker
`https://www.fleaflicker.com/api/...`. Public read endpoints for league
standings, rosters and scoreboard. No auth for public leagues.

---

## Tier 2 — readable without a credential *if a setting is right*.

### ESPN — **adapter built, 2026-08-15**
ESPN's fantasy read API is reachable without any login **when the league
is set to viewable by the public.** That is a league setting, not a
credential — if your league is already public, or the commissioner will
flip it, ESPN drops into Tier 1.

`engine/sources/espnfantasy.py` reads it: scoring, roster slots and every
team's roster, in the same shape the Sleeper path already produces so the
league desk never learns which platform it is talking to. A private
league raises with a message naming the setting to change, rather than
asking for cookies.

**Two things to know before the first real run.** ESPN describes scoring
as numeric `statId`s, and this container cannot reach ESPN to confirm the
mapping — a probe to both hosts returned nothing through the proxy. So
only the ids the app can act on are mapped, and **anything unknown comes
back in `unmapped` rather than being dropped**. If your league scores
something we ignored, the page will say so with the id, and adding it is
a one-line change. This discipline is a direct response to the `pass_att`
bug: a market read from a column that did not exist, where everything
downstream quietly read zero.

A **private** ESPN league is a different story. Reading it requires two
cookies, `espn_s2` and `SWID`, copied out of a logged-in browser. Those
are session credentials for your whole ESPN account, they last months,
and there is no way to scope them to "read this one league".

**My recommendation: don't.** Ask for the league setting instead. Same
data, no credential. If you decide otherwise it is your call and I will
build it — but I would want it stored the way the profile PIN is
(hashed is impossible here, so: file permissions, never logged, never in
a payload the browser can read) and I would want it said plainly on the
page that the site is holding an ESPN session token.

---

## Tier 3 — needs a registered app. The *correct* pattern, but real work.

### Yahoo — **adapter built, 2026-08-15**
Yahoo has a proper, documented **Fantasy Sports API** with OAuth2. You
register an application at `developer.yahoo.com`, get a client ID and
secret, and the user grants access through Yahoo's own consent screen.
No password ever touches this app, the token refreshes, and you can
revoke it from your Yahoo account page at any time.

**This is the only credential this project holds, and it is held because
of what it is, not despite it.** A session cookie cannot be scoped,
cannot be revoked short of logging out everywhere, and grants whatever
your logged-in browser can do. An OAuth token is scoped to fantasy read
access, expires, refreshes, and dies the moment you click revoke. Those
are different objects and the rule was never "no secrets" — it was never
hold a credential you cannot hand back.

**What you do once.** Register the app (free), put `YAHOO_CLIENT_ID` and
`YAHOO_CLIENT_SECRET` in `secrets.local`, then click connect on the
Fantasy tab. Yahoo shows a short code; you paste it back.

**Three things worth knowing about how it is built.**

*The redirect problem.* Yahoo wants a redirect URI and this site is
served on a LAN address with no public HTTPS name, so the usual web flow
does not fit. `oob` — Yahoo shows a code to paste — is supported for
exactly this shape and is the default. A real redirect URI can be passed
if you ever have one.

*Connecting is loopback-only.* Reading the site is LAN-wide, as it always
has been. Granting or revoking a third party's access to a Yahoo account
is not the same class of action, so `/api/yahoo/connect` and
`/api/yahoo/disconnect` only answer requests from the machine running the
server. A phone on the same coffee-shop wifi can read your lineup; it
cannot connect or disconnect your Yahoo account.

*Scoring is mapped by NAME, not by stat id.* Yahoo hands back both — and
sends **two different names for the same stat** (`name` "Passing Yards",
`display_name` "Pass Yds"). Both spellings are in the map, because a map
holding one of them scores a league silently wrong: every rule reads as
"agrees with PPR" and nothing errors. Anything that still cannot be
placed comes back in `unmapped` and reaches the page. Kicker and defense
rules are reported separately as `not_modelled`, because this app has
never projected them — that is a known limit, not a gap in the map, and
one number for both would hide a real miss inside twenty expected ones.

The token is stored at `data/yahoo_token.json` with owner-only
permissions set at creation, is never sent to the browser, and is never
logged.

---

## Tier 4 — not available.

* **NFL.com Fantasy** — no supported public API; the old endpoints were
  retired when the platform was folded.
* **CBS Sports** — a Fantasy API exists but developer registration has
  been closed for years in practice.
* **FantasyPros rankings** (not a league host, but the obvious "every
  book's consensus") — behind a paid API key, and the terms forbid
  scraping the site. This is why the Rankings tab has a **paste box**
  instead: a list you can already see, exported by you, is not scraping.

---

## Where this stands

Ethan answered the open question on 2026-08-15: **"All of them besides
MFL and Fleaflicker"** — so Sleeper, ESPN and Yahoo, and all three are
built.

| Platform | Status | What it needs from you |
|---|---|---|
| Sleeper | in production | nothing |
| ESPN | built | the league set to viewable by the public |
| Yahoo | built | one free app registration, then one approval click |
| MFL | not built | nothing (public leagues) — deliberately skipped |
| Fleaflicker | not built | nothing (public leagues) — deliberately skipped |

MFL and Fleaflicker are the *cheapest* two to add and are not built,
because Ethan does not play on them. Each is roughly an hour if that ever
changes.

**The desk above them never learns which platform it is talking to.** All
three adapters return the same shape, so `fantasy_lineup` and
`fantasy_trade` are shared and there is exactly one lineup optimiser and
one trade generator to be right or wrong.

---

## The shape this has to take in code

Whatever gets added, it goes behind one adapter interface so the pages
above it never learn which platform they are talking to:

```
league(platform, league_id)       -> {name, teams, scoring, roster_slots}
rosters(platform, league_id)      -> [{team, owner, players[]}]
picks(platform, draft_id)         -> [{pick_no, player, team}]
```

Sleeper already answers all three. Every read stays server-side and
allowlisted, exactly as `_SLEEPER_OK` does today — a proxy that forwards
arbitrary paths is an open relay on the user's own network, and that is
worth restating every time a second platform is added.
