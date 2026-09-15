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
| Actually sending | `engine/mailer.send` | **needs a provider** |

Read the copy before anything else:

    python3 digest.py morning
    python3 digest.py nightly
    python3 digest.py morning --locked     # what a signed-out reader gets

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
