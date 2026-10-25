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

#: RESEND, OVER HTTPS (2026-10-11). The first real test of the Gmail relay
#: on the box ended in "Could not reach smtp.gmail.com on port 587":
#: DigitalOcean blocks the mail ports (25, 465, 587) on newer accounts and
#: often will not lift it. An HTTPS API on port 443 — the port every odds
#: feed already uses — cannot be blocked that way. With QB_RESEND_KEY set,
#: every message goes through https://api.resend.com/emails instead of
#: SMTP, from an address on qellysbook.com (Resend sends only for a domain
#: it has verified), with replies going to QB_MAIL_REPLY_TO.
ENV_RESEND = "QB_RESEND_KEY"
ENV_REPLY_TO = "QB_MAIL_REPLY_TO"
RESEND_URL = "https://api.resend.com/emails"
RESEND_REQUIRED = (ENV_RESEND, ENV_FROM)


class ResendError(RuntimeError):
    """Resend refused the message. Carries the HTTP status and Resend's own
    error name — never the key."""

    def __init__(self, status: int, name: str, detail: str = ""):
        super().__init__(f"Resend refused the message ({status} {name}) {detail}".strip())
        self.status, self.name, self.detail = status, name, detail

#: THE SITE'S OWN GMAIL (Ethan, 2026-10-11: "i have an email for the site.
#: its qellysbook@gmail.com"). Gmail's SMTP server takes an APP PASSWORD —
#: sixteen letters Google makes once 2-Step Verification is on — never the
#: account's real password. It suits ONE-TO-ONE mail: a password reset to
#: the person who asked, an alert to the owner. It does not suit a mailing
#: list: a personal Gmail account sends a few hundred messages a day, and
#: a suspension for bulk sending takes the site's only inbox with it. So
#: `bulk_ok()` is False on Gmail and the digests stay off (docs/EMAIL.md).
GMAIL_HOSTS = ("smtp.gmail.com", "smtp.googlemail.com")
#: Shown as the sender when QB_MAIL_FROM is a bare address.
SENDER_NAME = "Qellys Book"


def transport() -> str:
    """``"resend"`` when its key is set (it wins over SMTP), else ``"smtp"``."""
    return "resend" if os.environ.get(ENV_RESEND, "").strip() else "smtp"


def missing() -> list:
    """Which settings are absent. Names only — never values."""
    need = RESEND_REQUIRED if transport() == "resend" else REQUIRED
    return [name for name in need if not os.environ.get(name, "").strip()]


def configured() -> bool:
    return not missing()


def is_gmail() -> bool:
    return (transport() == "smtp"
            and os.environ.get(ENV_HOST, "").strip().lower() in GMAIL_HOSTS)


def bulk_ok() -> bool:
    """Whether a mailing to many people may go out: only through an SMTP
    provider. Never Gmail (a few hundred a day, and a suspension takes the
    site's inbox with it) and never Resend's free plan (100 a day — a
    mailing would spend the day's password resets)."""
    return configured() and transport() == "smtp" and not is_gmail()


def reply_to() -> str:
    return os.environ.get(ENV_REPLY_TO, "").strip()


def sender() -> str:
    """QB_MAIL_FROM, with the site's name in front of a bare address, so the
    inbox reads "Qellys Book" rather than an address on its own."""
    from email.utils import formataddr, parseaddr
    raw = os.environ.get(ENV_FROM, "").strip()
    name, addr = parseaddr(raw)
    if addr and not name and "@" in addr:
        return formataddr((SENDER_NAME, addr))
    return raw


def _clean_password(pw: str) -> str:
    """Google shows an app password in four groups of four ("abcd efgh ijkl
    mnop") and the letters are the password, so the spaces come out. Only
    for Gmail: another provider's password may hold a real space."""
    return "".join(pw.split()) if is_gmail() else pw.strip()


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
    if reply_to():
        msg["Reply-To"] = reply_to()
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
    # A phone account's placeholder address (engine/smsverify) is reserved
    # as undeliverable; nothing is ever sent to one.
    if str(to or "").lower().endswith(".invalid"):
        raise RuntimeError("that account signs in by phone and has no email address — nothing was sent.")
    gaps = missing()
    if gaps:
        raise RuntimeError(
            "email is not configured — set " + ", ".join(gaps)
            + " (see docs/EMAIL.md). Nothing was sent.")
    if transport() == "resend":
        return _send_resend(to, subject, text, html)
    host = os.environ[ENV_HOST].strip()
    port = int(os.environ.get(ENV_PORT, "587").strip() or 587)
    user = os.environ[ENV_USER].strip()
    password = _clean_password(os.environ[ENV_PASS])
    msg = message(to, subject, text, html)
    # STARTTLS on 587, implicit TLS on 465 — the two ports every
    # transactional provider offers, and the credential must never cross
    # a plaintext connection either way.
    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as s:
            s.login(user, password)
            s.send_message(msg)
        return
    with smtplib.SMTP(host, port, timeout=30) as s:
        s.starttls(context=ctx)
        s.login(user, password)
        s.send_message(msg)


def resend_payload(to: str, subject: str, text: str, html: str = "") -> dict:
    """The JSON Resend takes: the same message `message()` builds for SMTP —
    both parts, the reply address, the one-click unsubscribe header."""
    body = {"from": sender(), "to": [to], "subject": subject, "text": text}
    if html:
        body["html"] = html
    if reply_to():
        body["reply_to"] = reply_to()
    m = _unsub_from(text)
    if m:
        body["headers"] = {"List-Unsubscribe": f"<{m}>",
                           "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
    return body


def _send_resend(to: str, subject: str, text: str, html: str = "", opener=None) -> None:
    """POST one message to Resend. Raises ResendError on a refusal (status
    and Resend's error name, never the key) and lets a network failure
    through as the OSError it is."""
    import json
    import urllib.error
    import urllib.request
    req = urllib.request.Request(
        RESEND_URL, method="POST",
        data=json.dumps(resend_payload(to, subject, text, html)).encode("utf-8"),
        headers={"Authorization": "Bearer " + os.environ[ENV_RESEND].strip(),
                 "Content-Type": "application/json",
                 # Resend's API sits behind Cloudflare, which turns away a
                 # bare "Python-urllib" agent on some days.
                 "User-Agent": "qellysbook-mailer/1.0"})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=30) as r:
            r.read()
    except urllib.error.HTTPError as e:
        try:
            said = json.loads(e.read() or b"{}")
        except ValueError:
            said = {}
        raise ResendError(e.code, str(said.get("name") or "error"),
                          str(said.get("message") or "")[:200]) from None


# --- the owner's test send -----------------------------------------------------
def _cli(argv=None) -> int:
    """``python3 -m engine.mailer test you@example.com``

    One short message, so the owner can see the settings work before a
    customer finds out they do not. Prints what went wrong by KIND — a
    refused login, an unreachable server — and never the password.
    """
    import sys
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2 or args[0] != "test" or "@" not in args[1]:
        print("usage: sudo python3 -m engine.mailer test you@example.com")
        return 2
    # The box's settings live in /etc/qellys/env, which only root can read
    # (hence sudo); the service gets them from systemd, a shell does not.
    from . import secrets as _local
    _local.load_local_secrets()
    gaps = missing()
    if gaps:
        print("Not set yet: " + ", ".join(gaps) + ". Nothing was sent.")
        return 1
    try:
        send(args[1], "Qellys Book: test email",
             "This is a test from the Qellys Book server. If you can read "
             "it, password reset emails will reach people too.\n")
    except ResendError as exc:
        if exc.status in (401, 403) and "domain" not in exc.detail.lower():
            print("Resend refused the API key. Make a new one at resend.com → "
                  "API Keys (Sending access) and set it again with "
                  "sudo ./deploy/setenv.sh QB_RESEND_KEY.")
        else:
            print(f"Resend refused the message ({exc.status} {exc.name}): {exc.detail} "
                  f"— QB_MAIL_FROM must be an address on a domain Resend shows as "
                  f"Verified (e.g. noreply@qellysbook.com).")
        return 1
    except smtplib.SMTPAuthenticationError:
        print("The mail server refused the login. For Gmail, QB_SMTP_PASS must "
              "be an APP PASSWORD (16 letters from myaccount.google.com/apppasswords), "
              "not the account's normal password, and QB_SMTP_USER the full address.")
        return 1
    except smtplib.SMTPException as exc:
        print(f"The mail server answered but did not take the message "
              f"({type(exc).__name__}). Check QB_MAIL_FROM is the Gmail address itself.")
        return 1
    except OSError as exc:
        if transport() == "resend":
            print(f"Could not reach api.resend.com ({type(exc).__name__}). Check the "
                  f"box can reach the internet: curl -sI https://api.resend.com")
            return 1
        # No answer at all. DigitalOcean blocks the mail ports (25, 465,
        # 587) on many accounts, and from the box that looks exactly like
        # this: a timeout or a refused connection, never a refused login.
        print(f"Could not reach {os.environ.get(ENV_HOST, '').strip()} on port "
              f"{os.environ.get(ENV_PORT, '587').strip() or '587'} ({type(exc).__name__}). "
              f"If the host and port are right (Gmail: smtp.gmail.com, 587), the "
              f"hosting company is blocking outgoing mail: ask DigitalOcean support "
              f"to unblock SMTP for this droplet, or send through Resend instead "
              f"(runbook step 26).")
        return 1
    except Exception as exc:                                  # noqa: BLE001
        print(f"Not sent: {type(exc).__name__}.")
        return 1
    print(f"Sent to {args[1]} from {sender()}. Check that inbox (and its spam folder).")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
