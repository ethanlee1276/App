"""The one seam where mail leaves the building — and refuses to, today.

Ethan asked for a morning card and a nightly recap by email. The content
is built in `engine/digest.py`; this is the part that needs a delivery
provider, and there is not one configured. That is a fact about the
setup rather than about the code, and the honest shape for it is a
function that says exactly what is missing instead of a stub that
returns True.

WHY THERE IS NO DEFAULT SENDER
------------------------------
`smtplib` will happily connect to localhost:25 and hand a message to
whatever is listening. On the droplet that is nothing, and if it were
something, mail sent straight from a DigitalOcean address to Gmail is
filed as spam or refused at the door: DO blocks outbound port 25 on new
accounts, and mail from an IP with no SPF, DKIM or DMARC alignment for
qellysbook.com has no reason to be trusted. A "working" sender that
silently delivers nothing is the worst of the three options, because
nobody finds out until somebody asks why they never got the email.

So: configure a relay (a transactional provider's SMTP endpoint is the
smallest step — see docs/EMAIL.md) and set the environment. Until then
`send` raises, `configured()` is False, and the site does not offer the
subscription at all.

THE PASSWORD IS NEVER IN AN ERROR MESSAGE. A key in a traceback is a key
in a log file — the same rule engine/stripeset.py keeps for the Stripe
secret, and the reason every raise below names the VARIABLE and not the
value.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage

#: Read from the environment, never from a file in the repo. The repo is
#: public; the relay password is not.
ENV_HOST = "QB_SMTP_HOST"
ENV_PORT = "QB_SMTP_PORT"
ENV_USER = "QB_SMTP_USER"
ENV_PASS = "QB_SMTP_PASS"
ENV_FROM = "QB_MAIL_FROM"

REQUIRED = (ENV_HOST, ENV_USER, ENV_PASS, ENV_FROM)


def missing() -> list:
    """Which settings are absent. Names only — never values."""
    return [name for name in REQUIRED if not os.environ.get(name, "").strip()]


def configured() -> bool:
    return not missing()


def sender() -> str:
    return os.environ.get(ENV_FROM, "").strip()


def message(to: str, subject: str, text: str, html: str = "") -> EmailMessage:
    """The message itself, built whether or not a relay exists.

    Separated from sending on purpose: the digest CLI renders this to
    stdout so the copy can be read and argued with before anybody has
    paid a provider a cent.

    BOTH PARTS, always. A text/plain alternative is not a courtesy — a
    message with only an HTML part scores worse with every filter, and
    it is unreadable in the clients that strip it.
    """
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender() or "qellysbook@invalid"
    msg["To"] = to
    # A List-Unsubscribe header is what puts the one-click control in
    # Gmail's own chrome, which is where people actually look for it —
    # and a reader who finds it there does not press Report spam.
    m = _unsub_from(text)
    if m:
        msg["List-Unsubscribe"] = f"<{m}>"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    return msg


def _unsub_from(text: str) -> str:
    for line in str(text or "").splitlines():
        if "Stop these emails:" in line:
            return line.split("Stop these emails:", 1)[1].strip()
    return ""


def send(to: str, subject: str, text: str, html: str = "") -> None:
    """Deliver one message, or raise saying what is missing.

    Raises RuntimeError naming the absent environment variables — never
    their values — and lets smtplib's own exceptions through untouched:
    a refused recipient and a bad password are different problems and
    flattening them into one message is how an evening gets spent on the
    wrong one.
    """
    gaps = missing()
    if gaps:
        raise RuntimeError(
            "email is not configured — set " + ", ".join(gaps)
            + " (see docs/EMAIL.md). Nothing was sent.")
    host = os.environ[ENV_HOST].strip()
    port = int(os.environ.get(ENV_PORT, "587").strip() or 587)
    msg = message(to, subject, text, html)
    # STARTTLS on 587, implicit TLS on 465 — the two ports every
    # transactional provider offers, and the credential must never cross
    # a plaintext connection either way.
    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as s:
            s.login(os.environ[ENV_USER], os.environ[ENV_PASS])
            s.send_message(msg)
        return
    with smtplib.SMTP(host, port, timeout=30) as s:
        s.starttls(context=ctx)
        s.login(os.environ[ENV_USER], os.environ[ENV_PASS])
        s.send_message(msg)
