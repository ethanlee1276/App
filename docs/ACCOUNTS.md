# Accounts, passwords, and money

Ethan, 2026-08-15:

> *"I need you to go into our docs and shit where it say we will never
> store passwords and we will never take money because that is not true.
> we will be storing user information and passwords and logins and we
> will be accepting money for people to use the website once it is
> complete. we need to make a feature where you can make an account on
> our website with email and password so we can store peoples bets and
> fantasy leauges and search history or anything like that."*

This page is the corrected record. Where an older doc said the site would
never take a login or never take money, that is superseded here.

---

## What changed, and what did not

The repo had two separate rules that kept getting quoted as one sentence.
They came apart on 2026-08-15.

| | Before | Now |
|---|---|---|
| Our own login | name + optional numeric PIN, no email | **email + password** |
| Somebody else's login (DraftKings, ESPN) | never asked for | **still never asked for** |
| Charging for the site | "never holds money" | **will charge for access** |
| Taking wagers | never | **still never** |

**The rule that survived is the narrower one, and it is the one worth
keeping.** We can scope, rotate, expire and delete a Qellys password. We
can do none of those to your DraftKings password, and an ESPN session
cookie grants full account access with no way to limit it. That asymmetry
is the whole argument, and it is unaffected by us having accounts of our
own. Yahoo works because OAuth2 gives a revocable, scoped token instead
of a password — see `docs/FANTASY_PLATFORMS.md`.

The money rule came apart the same way. Charging a subscription is
ordinary software business. Accepting a **wager** is a licensed activity
in most US states. The old docs banned both under one heading, which is
how a business decision ended up looking like it had been settled by a
design review. Subscription billing is planned; the bet slip, the
deposit and the balance chip are still out.

---

## "Storing passwords" — what is actually on disk

What goes in `data/accounts.db` is a **scrypt verifier**, not a password.

```
scrypt$16384$8$1$<16-byte salt, hex>$<32-byte hash, hex>
```

It is a one-way function of the password. Nobody holding that file — not
me, not Ethan, not whoever ends up with a copy — can read a password out
of it. That is not a hedge on the instruction; it is what storing a
password correctly means, and every service you have an account with does
it this way. A service that could show you your own password would be
telling you it had failed to.

The visible consequence: **this app can never email anyone their password
back.** It can only let them set a new one. If that ever needs to change,
the thing to add is a reset flow, not plaintext storage.

Four decisions worth arguing with later:

* **scrypt, not PBKDF2.** The old PIN store used PBKDF2-SHA256 at 60k
  iterations — fine against a CPU, weak against a GPU farm. scrypt is
  memory-hard: 16MB per guess is nothing once and ruinous a billion
  times. The parameters live inside the stored string, so they can be
  raised later without invalidating anyone's existing password.
* **Session tokens are hashed at rest too.** This is the one people skip.
  A token stored in the clear is a live session for anyone who reads the
  database. We store its sha256 and compare in constant time.
* **A failed login costs the same time whether or not the email exists.**
  Otherwise the response clock is an account-enumeration oracle. A
  missing user is checked against a dummy verifier so the work matches.
  Measured: 0.042s either way.
* **Length beats character classes.** Ten characters minimum, plus a
  check against the obvious ones. Demanding a symbol and a digit produces
  `Password1!` on a sticky note, which is worse by every measure anyone
  has managed to take.

---

## What an account holds

Four sections, synced across every device you sign in on:

| Section | What it is |
|---|---|
| `mybets` | your own bet log, merged by signature so a device race can never lose one |
| `fantasy` | league links, draft id, pasted rankings |
| `bankroll` | bankroll and unit size |
| `search` | recent player searches — new with accounts |

The merge is **shared with the old PIN store** rather than reimplemented:
union by bet signature, tombstones for deletions, and a graded bet is
never un-settled by a stale pending copy from another device. Two
implementations of "never lose a logged bet" is one too many.

Search history is the one section that records what somebody was
*thinking* rather than what they did, so it says on the page that it is
kept, and it has its own Clear button.

## Giving it back

* **Download my data** — `GET /api/account/export`, everything we hold,
  as JSON. Deliberately excludes the verifier and session tokens: an
  export is a file people mail around, and it should not carry the two
  secrets that would let somebody else be them.
* **Delete my account** — removes the account, every section, and every
  session, in one transaction. Requires the password again, because it
  cannot be undone.
* **Change password** — signs out every other device. A password change
  is usually an answer to "somebody else may have this", and leaving
  those sessions alive answers it with nothing.

---

## The endpoints

| Method | Path | |
|---|---|---|
| POST | `/api/account/signup` | `{email, password}` → session cookie |
| POST | `/api/account/login` | same |
| POST | `/api/account/logout` | ends the session server-side |
| GET | `/api/account/me` | `{signed_in, email}` |
| GET | `/api/account/data` | stored sections |
| POST | `/api/account/data` | `{sections}` → merged sections |
| POST | `/api/account/password` | `{old, new}` |
| POST | `/api/account/delete` | `{password}` |
| GET | `/api/account/export` | everything, as JSON |

The session cookie is `HttpOnly` (page scripts cannot read it, so an
injected script cannot steal it either), `SameSite=Lax` (another site
cannot ride it) and `Secure` **when the request arrived over HTTPS**.
That last one is conditional on purpose: setting it unconditionally would
make sign-in silently impossible over a plain-HTTP LAN address, and never
setting it would let the cookie ride a plaintext request when there *is*
a TLS front.

Wrong passwords are throttled: 8 failures per address buys a 15-minute
lockout, held in memory. It is there to slow a live guesser, and a
restart clearing it is not the threat being defended against.

---

## Before real users: two things that are not optional

**1. TLS — now enforced rather than only documented.** `server.py` is a
stdlib `http.server` speaking plain HTTP. Over a LAN that was fine for a
PIN; it is **not** fine for real passwords, because scrypt does nothing
about this. Hashing protects the password *at rest*. A password typed
into a plain-HTTP page has already crossed the network readable before it
reaches the hash, and anyone on that Wi-Fi has it — for this site and for
wherever else it was reused.

So the server refuses it. `signup`, `login`, `password` and `delete` are
rejected when the connection is cleartext **and** the browser is on
another machine:

| | |
|---|---|
| loopback over HTTP | **allowed** — nothing crosses a network |
| **over a Tailscale tailnet** | **allowed** — see below |
| another machine, no TLS | **refused**, with the fix named |
| `X-Forwarded-Proto: https` | **allowed** |

**`http://` over a tailnet is not cleartext.** Tailscale is WireGuard:
packets are encrypted device-to-device before they touch any network, so
the scheme in the address bar describes the last inch rather than the
wire. Ethan reaches the site at `http://100.87.149.86:8000` from his
phone, and refusing that would be refusing a genuinely private link —
worse than useless in practice, because the way round it is
`QB_ALLOW_INSECURE_LOGIN=1`, which switches the check off *everywhere*
including the coffee shop.

The check requires **both ends** to be in Tailscale's range
(`100.64.0.0/10`, or `fd7a:115c:a1e0::/48` for IPv6). That range is RFC
6598 shared space — Tailscale uses it and so do some ISPs for
carrier-grade NAT — so a client address alone proves nothing; requiring
our own socket for the connection to be a tailnet address too means the
packet arrived on the tailnet interface, which a CGNAT'd public path does
not do. The limit, stated rather than hidden: a network that really did
put both machines inside `100.64.0.0/10` would read as a tailnet here.
That is narrow — home LANs are `192.168`/`10.x` and CGNAT sits upstream
of the router — and a far smaller hole than the blanket override.

The session cookie still does **not** get the `Secure` flag over a
tailnet, and that is correct: browsers reject `Secure` cookies on
`http://`, so setting it would silently break sign-in. `Secure` follows
TLS, which is a different question from whether the link is private.

Reads and syncs are *not* blocked — that would break a phone on the LAN
for no gain, and a session cookie is a smaller and shorter-lived exposure
than a reused password.

The fix is `tailscale serve --bg 8000`, which prints an HTTPS URL that
works from anywhere; any reverse proxy also does. The cookie code notices
on its own and adds `Secure` once that is true.

`QB_ALLOW_INSECURE_LOGIN=1` overrides the refusal for someone who has
read this and decided the network is theirs. An environment variable
rather than a settings toggle, so it takes a decision rather than a
mis-tap — and note that **it removes the refusal, not the risk**: the
page still says the connection is not private, because it still is not.
`/api/account/me` reports `insecure` (a fact about the wire) separately
from `allowed` (our policy), so the page can never claim a private
connection because somebody set a variable.

**2. Payments go through a processor.** When subscription billing lands
it should be Stripe Checkout or equivalent — card numbers never touch
this server, so we never come near PCI scope. Do not build a card form.

Two more that are cheap and worth doing when there are real users: a
password-reset flow (needs an email sender, which this app does not have
yet), and a privacy note saying plainly what is stored — bets, leagues,
searches — since "search history" is the kind of thing people reasonably
want told to them rather than discovered.

---

## Where the code is

| | |
|---|---|
| `engine/accounts.py` | verifier, sessions, storage, export/delete |
| `server.py` | `_account_get` / `_account_post`, cookie handling, the shared merge |
| `web/js/app.js` | the card, sign-in/out, sync, search capture |
| `tests/test_useraccounts.py` | the security properties, pinned |
| `tests/test_accounts.py` | the older PIN store, still live |

The old name+PIN profiles under `data/profiles/` **keep working**. Nobody's
existing book disappears the day they make an account; the device shows
both cards until it has been moved over.
