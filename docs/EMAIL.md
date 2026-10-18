# Email — what is built, and the three things it needs from you

Ethan, 2026-08-25: *"Comms — email makes it a company … A morning
'Today's Card' digest and a nightly settle recap."*

**Both digests are built and neither can be sent yet.** That is not a
half-finished feature; it is the honest split between the part that is
code and the part that is an account somebody has to open. Everything
below the line is done:

| Piece | Where | State |
|---|---|---|
| The morning card | `engine/digest.morning` | done |
| The nightly recap | `engine/digest.nightly` | done |
| Gate discipline (a locked digest carries counts, not picks) | `engine/digest` | done |
| Opt-in, per account, per digest | `digest_optin` in accounts.db | done |
| One-click unsubscribe, no sign-in | `/unsubscribe?t=…` | done |
| The preview CLI | `python3 digest.py morning` | done |
| Password reset email (2026-10-11) | `engine/accounts.reset_message`, `server._send_reset` | done; sends through Resend (HTTPS) once its key is on the box, or the site's Gmail if DigitalOcean unblocks SMTP (runbook step 26) |
| Actually sending | `engine/mailer.send` | **needs a provider** |

Read the copy before anything else:

    python3 digest.py morning
    python3 digest.py nightly
    python3 digest.py morning --locked     # what a signed-out reader gets

---

## Resend, over HTTPS — what the box actually sends through (2026-10-11)

The first test of the Gmail relay on the droplet: "Could not reach
smtp.gmail.com on port 587". DigitalOcean blocks outbound SMTP (25, 465,
587) on newer accounts. Resend's API is HTTPS on port 443, which the box
already uses for every feed, so `engine/mailer` sends through it whenever
`QB_RESEND_KEY` is set (it wins over the SMTP settings):

    QB_RESEND_KEY=re_…            # resend.com → API Keys, Sending access
    QB_MAIL_FROM=noreply@qellysbook.com   # on the domain Resend verified
    QB_MAIL_REPLY_TO=qellysbook@gmail.com # replies reach the site's inbox

The domain is verified in Resend with its "Sign in to Cloudflare" button,
which writes the SPF/DKIM records into the qellysbook.com zone; Resend
sends only from a verified domain, never from @gmail.com. The free plan
is 100 messages a day, so `bulk_ok()` is False here too and reset emails
are capped at 90 a day. Step-by-step: runbook step 26.

## The site's Gmail — one-to-one mail only (2026-10-11)

Ethan: *"i have an email for the site. its qellysbook@gmail.com."* Its
SMTP server is the relay for **password resets** (and, if
`QB_ALERT_EMAIL` is set, the owner's crash alerts): `smtp.gmail.com`,
port 587, the full address as the user, and an **app password** made at
myaccount.google.com/apppasswords — never the account's own password.
Mail sent through Gmail is signed by Google for gmail.com, so it lands
in inboxes without any DNS work. Step-by-step: runbook step 26.

What Gmail is NOT used for: the digests. A personal Gmail account sends
a few hundred messages a day, and a mailing list through it is how an
account gets suspended — taking the resets with it. `mailer.bulk_ok()` is
False on Gmail, the Account page does not offer the digests there, and
`digest.py --send` refuses. Reset emails are capped at 90 a day
(`server.RESET_MAIL_PER_DAY`) for the same reason. The digests still
need the provider below.

`sudo python3 -m engine.mailer test you@example.com` sends one message
and says what went wrong, by kind, if it did not.

---

## Why it does not just use smtplib and be done

It does use `smtplib`. The problem is not the library, it is the
delivery:

1. **DigitalOcean blocks outbound port 25** on new accounts. Mail sent
   directly from the droplet does not leave it.
2. **Mail from an IP with no SPF, DKIM or DMARC alignment for
   qellysbook.com is spam** as far as Gmail is concerned — not "might
   be", *is*. It will be filed, or refused at the door, and neither
   failure is visible from this end.
3. A sender that appears to work and silently delivers nothing is the
   worst of the three options, because nobody finds out until somebody
   asks why they never got the email.

So `engine/mailer.py` refuses loudly rather than pretending, and the
Account page says "email is not switched on yet" instead of offering a
subscription to nothing.

---

## The three steps, in order

### 1. Pick a transactional provider

Any of them work — they all speak SMTP, which is what `mailer.py`
already does. Postmark, Resend, SES, Mailgun, Brevo. What you are
buying is their IP reputation and their DKIM signing, not their API.

At a few hundred subscribers this is free or close to it on every one of
them. Do **not** use a personal Gmail account: the sending limits are
low, the terms forbid it, and a suspension takes your own mail with it.

### 2. Set the DNS records they give you

On the qellysbook.com zone, at whoever holds the domain:

* **SPF** — one TXT record listing the provider as allowed to send.
  One record only; two SPF records is a hard fail rather than two
  permissions.
* **DKIM** — the CNAME (or TXT) the provider gives you. This is the
  signature that proves the message was not altered.
* **DMARC** — `v=DMARC1; p=none; rua=mailto:you@qellysbook.com` to
  start. `p=none` means "tell me what is failing, reject nothing",
  which is the right setting until the reports come back clean. Tighten
  to `p=quarantine` after a couple of weeks of clean reports.

Send yourself a test and check the headers say `dkim=pass` and
`spf=pass` before sending anybody else anything.

### 3. Put the credentials in the environment

Never in the repo — it is public. Same file the Stripe key lives in:

    QB_SMTP_HOST=smtp.provider.com
    QB_SMTP_PORT=587
    QB_SMTP_USER=…
    QB_SMTP_PASS=…
    QB_MAIL_FROM="Qellys Book <card@qellysbook.com>"

Then:

    python3 digest.py morning --send

`--send` walks the opt-in list and sends one message per recipient, each
carrying that person's own unsubscribe token. It stops on the first
failure rather than half-delivering a run.

Once it works, the two cron lines (Eastern):

    30 9  * * *  cd /srv/qellys && python3 digest.py morning --send
    15 2  * * *  cd /srv/qellys && python3 digest.py nightly --send

The nightly one runs after the settle loop has graded the night; if it
runs before, `nightly()` returns None and sends nothing, which is the
correct behaviour rather than a bug.

---

## The last-leg email — one-to-one, like a reset (2026-10-13)

A member can ask, on the Live tab, to be emailed when a slip they saved
from the parlay checker is down to the one leg that decides it
(engine/slipwatch; runbook step 44). It is one-to-one mail — the member
switched it on, it goes to the address on the account, it carries their
own ticket — so it needs only `mailer.configured()`, the same bar as a
password reset, and the site's Gmail can carry it where the digests
need `bulk_ok()`. It is held three ways: once per slip, ever; 40 a day
across the whole box; and only to a member entitled at that moment,
since our live chance and the hedge are the paid half. Every message
carries the unsubscribe below — a `slip-` token that turns off only that
email, verified like the digest's and routed by the same page. Nothing
to set beyond what the resets already need.

## Rules the code already keeps, and should keep keeping

* **A digest with nothing to say is not sent.** A daily email that
  arrives to announce there are no picks teaches people to filter it,
  and this model passes often enough that it would happen most weeks in
  February.
* **The gate applies to an email more strictly than to a page.** A page
  is fetched by somebody signed in right now; an email leaves the
  building, gets forwarded, and sits in an inbox indefinitely. An
  unentitled digest carries counts and the free half only.
* **The nightly recap is free.** It is the evidence, on the same
  reasoning that keeps record.json ungated.
* **Every message carries a working unsubscribe**, in the body and in
  the `List-Unsubscribe` header, and the header endpoint answers a POST
  (RFC 8058) because Gmail and Apple Mail use it. One spam report costs
  more deliverability than a hundred opens earn.
* **The unsubscribe never asks for a password.** An unsubscribe that
  asks somebody to remember a login is an unsubscribe that becomes a
  spam report instead.
* **The token never leaves the server except inside the email.** It is
  a bearer credential for one action; it is not in the API response, not
  in the data export, and not in the page.
