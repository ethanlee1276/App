"""Sign up and sign in with a phone number: a code by text, through Twilio Verify.

Ethan, 2026-10-25, on Real's first screen: "you can either make an account
with an email or a phone number. So we should add that option as well."

OFF UNTIL IT IS CONFIGURED. Three values, set with `sudo ./deploy/setenv.sh`
and never written anywhere else:

    TWILIO_ACCOUNT_SID   the account
    TWILIO_AUTH_TOKEN    its secret
    TWILIO_VERIFY_SID    a Verify service (VA…), made in Twilio's console

Without all three, `configured()` is False, the page never offers the phone
option, and the two endpoints answer 503. Nothing here holds a code: Twilio
generates, texts and checks it, so a code never touches this server's disk
or logs.

WHAT IT COSTS, AND WHY IT IS FENCED. Each code sent is a paid text (Twilio
Verify bills per successful verification, plus the carrier's fee), and an
open "text this number" button is how SMS-pumping fraud runs up a bill:
somebody scripts it at premium-rate numbers abroad. So:
  * US and Canadian numbers only (+1), checked here before Twilio is asked;
  * at most PER_NUMBER sends to one number and PER_IP from one address an
    hour, in memory (Twilio's own Fraud Guard sits behind that);
  * a wrong code is answered the same way whatever was wrong.

A phone account has no password. It signs in the way it signed up — a
code — and its email column holds a non-deliverable placeholder
(`{digits}@phone.invalid`, `.invalid` being the name reserved for exactly
this) so every part of the site keyed on an account's address keeps
working; engine/mailer refuses to send to one.

Standard library only.
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

ENV_SID, ENV_TOKEN, ENV_SERVICE = "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_VERIFY_SID"
API = "https://verify.twilio.com/v2/Services"
PER_NUMBER = 3
PER_IP = 6
WINDOW_S = 3600
PLACEHOLDER = "@phone.invalid"

_sent: dict = {}


class SmsUnavailable(RuntimeError):
    """Twilio is not configured, or would not answer."""


def configured(env=None) -> bool:
    e = os.environ if env is None else env
    return all(str(e.get(k) or "").strip() for k in (ENV_SID, ENV_TOKEN, ENV_SERVICE))


def normalize(phone) -> str:
    """``+1XXXXXXXXXX`` for a US or Canadian number, or "". The area code and
    exchange may not start with 0 or 1 (the North American plan's own rule)."""
    d = re.sub(r"\D", "", str(phone or ""))
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    if len(d) != 10 or d[0] in "01" or d[3] in "01":
        return ""
    return "+1" + d


def placeholder_email(phone: str) -> str:
    return re.sub(r"\D", "", phone) + PLACEHOLDER


def is_placeholder(email) -> bool:
    return str(email or "").lower().endswith(PLACEHOLDER)


def say(phone: str) -> str:
    """``(555) 201-4567`` for a page; the stored form stays E.164."""
    d = re.sub(r"\D", "", phone)[-10:]
    return f"({d[:3]}) {d[3:6]}-{d[6:]}" if len(d) == 10 else phone


def allow(phone: str, ip: str, now: float | None = None) -> bool:
    """Room for one more text to this number from this address."""
    t = time.time() if now is None else now
    for k in list(_sent):
        _sent[k] = [x for x in _sent[k] if t - x < WINDOW_S]
        if not _sent[k]:
            _sent.pop(k)
    if len(_sent.get(f"n:{phone}", [])) >= PER_NUMBER or len(_sent.get(f"i:{ip}", [])) >= PER_IP:
        return False
    _sent.setdefault(f"n:{phone}", []).append(t)
    _sent.setdefault(f"i:{ip}", []).append(t)
    return True


def _request(path: str, form: dict, env=None, opener=None) -> dict:
    """NOTHING FROM THE AUTH HEADER EVER REACHES AN EXCEPTION, as with
    engine/billing's Stripe calls: the token in a traceback is the token in
    a log file."""
    e = os.environ if env is None else env
    sid, token, service = (str(e.get(k) or "").strip() for k in (ENV_SID, ENV_TOKEN, ENV_SERVICE))
    if not (sid and token and service):
        raise SmsUnavailable("Phone sign-in is not switched on.")
    req = urllib.request.Request(
        f"{API}/{service}/{path}", data=urllib.parse.urlencode(form).encode(),
        headers={"Authorization": "Basic " + base64.b64encode(f"{sid}:{token}".encode()).decode(),
                 "Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with (opener or urllib.request.urlopen)(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        raise SmsUnavailable(f"Twilio refused the request (HTTP {exc.code}).") from None
    except Exception:                                        # noqa: BLE001
        raise SmsUnavailable("Could not reach Twilio.") from None


def start(phone: str, env=None, opener=None) -> bool:
    """Text a code to this number. True when Twilio says one is on its way."""
    out = _request("Verifications", {"To": phone, "Channel": "sms"}, env, opener)
    return str(out.get("status") or "") == "pending"


def check(phone: str, code, env=None, opener=None) -> bool:
    """True only when Twilio approves this code for this number."""
    c = re.sub(r"\D", "", str(code or ""))
    if not 4 <= len(c) <= 10:
        return False
    try:
        out = _request("VerificationCheck", {"To": phone, "Code": c}, env, opener)
    except SmsUnavailable:
        return False
    return str(out.get("status") or "") == "approved"
