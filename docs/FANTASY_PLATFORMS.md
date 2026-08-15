# Syncing a fantasy league that isn't Sleeper

Ethan, 2026-08-15: *"Find out how to find sync more then just sleeper
fantasy league."*

Here is the real answer, platform by platform, with the one thing that
decides each: **can it be read without a credential.**

That question is not squeamishness. The standing rule on this project is
that the site never takes a login — it exists because a sportsbook
password in a JSON file on a LAN-served laptop is a bad trade. A fantasy
platform's session cookie is the same class of object: it grants full
account access, it does not expire quickly, and it cannot be scoped down.
So platforms are sorted below by whether they need one.

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

### ESPN
ESPN's fantasy read API is reachable without any login **when the league
is set to viewable by the public.** That is a league setting, not a
credential — if your league is already public, or the commissioner will
flip it, ESPN drops into Tier 1 and costs the same work as MFL.

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

### Yahoo
Yahoo has a proper, documented **Fantasy Sports API** with OAuth2. You
register an application at `developer.yahoo.com`, get a client ID and
secret, and the user grants access through Yahoo's own consent screen.
No password ever touches this app, the token refreshes, and you can
revoke it from your Yahoo account page at any time.

This is the right way to do third-party access and it is the only Tier-3
platform worth the effort. The cost is real though: an app registration,
a redirect URI (awkward for a site served on a LAN address), a token
store, and a refresh loop. Call it a day of work versus an hour for a
Tier-1 platform.

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

## What I would build, in order

1. **MFL and Fleaflicker.** Tier 1, no credentials, ~an hour each, and
   they reuse the Sleeper adapter shape exactly.
2. **ESPN public leagues.** Same work, plus a clear message when the
   league is private that names the setting to change.
3. **Yahoo OAuth** — only if you actually have a Yahoo league. It is a
   day of work and pointless otherwise.

**The open question is which of these you actually play in.** Building
Yahoo's OAuth flow for a league that doesn't exist is a day spent on
nothing. Tell me the platforms and I will do them in that order.

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
