"""Redemption codes — access granted without a payment.

Ethan, 2026-08-20: *"i also want a spot for discount codes. i want code
'USFARATHANE' to give you 100% off 1 year."*

WHY THIS IS NOT A PADDLE COUPON, which is the obvious first answer.

A hundred-percent-off code means THERE IS NO PAYMENT. Routing a
zero-dollar transaction through a merchant of record buys nothing and
costs plenty: it needs a live Paddle account (there is not one yet), a
price object, a coupon object, and a webhook round-trip whose signature
verifier is still flagged UNVERIFIED in `paddle.py`. Every one of those is
a way for a free grant to fail in production for a reason nobody can see.

A grant that involves no money should not travel through a payment
processor. So a redeemed code writes an entitlement directly, and Paddle
stays what it is: the thing that handles actual money, later.

The useful consequence is that the paywall can be switched ON before
Paddle is live. Comp addresses and redemption codes are then the two ways
in, both of them under Ethan's hand, and the site is genuinely gated
while the processor is still being set up.

WHERE CODES ARE DEFINED, AND WHY IT IS NOT THE DATABASE
-------------------------------------------------------
In the environment, exactly like `QB_COMP_EMAILS`, and for the same
reason: nothing reachable from the web may mint access. A table of codes
with an admin endpoint is one authentication bug away from being an
unlimited free-subscription generator, and that endpoint would have to be
written, guarded and kept guarded forever. An environment variable cannot
be written by an HTTP request at all.

    QB_CODES="USFARATHANE:12:100, FRIENDS:1:25"
                    │        │   │
                    │        │   └── how many accounts may ever redeem it
                    │        └────── months of access granted
                    └─────────────── the code, case-insensitive

REDEMPTIONS are recorded in the database, because they are facts about
what happened and have to survive a restart, be counted against the cap,
and be auditable afterwards.

THE FOUR WAYS THIS COULD BE ABUSED, AND WHAT STOPS EACH
--------------------------------------------------------
* *Redeeming the same code repeatedly for infinite years.* One redemption
  per account per code, enforced by a primary key rather than by a check
  — a check races with itself under two simultaneous requests and a
  primary key does not.
* *Sharing a code with the world.* Every code carries a `max_uses`. The
  count is taken from the redemptions table inside the same transaction
  as the insert, so the cap cannot be walked past by two requests
  arriving together.
* *Guessing a code.* Attempts are rate-limited per account, and a wrong
  code is answered with the same generic message and the same timing
  whether or not the code exists — a fast "no such code" and a slow
  "already used" together are an oracle for enumerating live codes.
* *Extending an expiry forever by re-redeeming after it lapses.* The
  grant is stored as an absolute paid-through date. Re-redeeming a code
  already redeemed is refused whether or not it has expired.

Standard library only. No fetches, no processor.
"""

from __future__ import annotations

import os
import re
import time

#: Where codes are defined. See the module docstring for the format.
ENV_CODES = "QB_CODES"

#: A month, for turning "12 months" into a paid-through date. Calendar
#: months vary and a subscription boundary is not a legal deadline; 30.44
#: days is the mean Gregorian month and keeps a twelve-month grant within
#: a day of the anniversary.
MONTH_S = 30.44 * 24 * 3600

#: Codes are typed by hand off a screenshot or a group chat. Case and
#: surrounding space never mean anything; internal punctuation might, so
#: it is kept.
def normalize(code: str) -> str:
    return str(code or "").strip().upper()

#: What a code may contain. Letters, digits, dash and underscore — wide
#: enough for anything anyone would say out loud, narrow enough that a
#: code can never carry a comma or colon and break the env format it is
#: parsed out of.
CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,31}$")

#: Wrong attempts allowed per account per window before refusing to look.
MAX_ATTEMPTS = 8
ATTEMPT_WINDOW_S = 3600.0


def catalogue(env: dict | None = None) -> dict:
    """`{CODE: {"months": int, "max_uses": int}}` from the environment.

    Malformed entries are DROPPED rather than raising: this is parsed at
    request time, and one typo in a comma-separated list must not take
    the redemption endpoint down for every other code in it.
    """
    raw = (env or os.environ).get(ENV_CODES, "") or ""
    out: dict = {}
    for part in raw.split(","):
        bits = [b.strip() for b in part.split(":")]
        if len(bits) < 2:
            continue
        code = normalize(bits[0])
        if not CODE_RE.match(code):
            continue
        try:
            months = int(bits[1])
            uses = int(bits[2]) if len(bits) > 2 and bits[2] else 0
        except ValueError:
            continue
        if months <= 0 or months > 120:      # ten years is not a promo
            continue
        out[code] = {"months": months, "max_uses": max(0, uses)}
    return out


def init(conn) -> None:
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS code_redemptions (
        code       TEXT NOT NULL,
        user_id    INTEGER NOT NULL
                   REFERENCES users(id) ON DELETE CASCADE,
        months     INTEGER NOT NULL,
        granted_to REAL NOT NULL,
        created_at REAL NOT NULL,
        PRIMARY KEY (code, user_id)
      );
      CREATE INDEX IF NOT EXISTS code_redemptions_user
        ON code_redemptions(user_id);
      -- Wrong guesses, so a code cannot be enumerated by brute force.
      CREATE TABLE IF NOT EXISTS code_attempts (
        user_id INTEGER NOT NULL,
        at      REAL NOT NULL
      );
      CREATE INDEX IF NOT EXISTS code_attempts_user
        ON code_attempts(user_id, at);
    """)
    conn.commit()


def _recent_attempts(conn, user_id: int, now: float) -> int:
    row = conn.execute(
        "SELECT COUNT(*) n FROM code_attempts WHERE user_id=? AND at > ?",
        (int(user_id), now - ATTEMPT_WINDOW_S)).fetchone()
    return int(row["n"] if row else 0)


def _note_attempt(conn, user_id: int, now: float) -> None:
    conn.execute("INSERT INTO code_attempts(user_id, at) VALUES(?, ?)",
                 (int(user_id), now))
    # Keep the table from growing without bound; nothing older than the
    # window is ever read.
    conn.execute("DELETE FROM code_attempts WHERE at < ?",
                 (now - ATTEMPT_WINDOW_S * 24,))


def uses(conn, code: str) -> int:
    row = conn.execute("SELECT COUNT(*) n FROM code_redemptions WHERE code=?",
                       (normalize(code),)).fetchone()
    return int(row["n"] if row else 0)


def granted_until(conn, user_id: int) -> float | None:
    """The furthest paid-through date any redeemed code gives this account.

    MAX, not sum: two codes are not additive, and the honest reading of
    "you hold a grant to March and a grant to June" is that you are
    covered until June.
    """
    row = conn.execute(
        "SELECT MAX(granted_to) g FROM code_redemptions WHERE user_id=?",
        (int(user_id),)).fetchone()
    g = row["g"] if row else None
    return float(g) if g else None


def active(conn, user_id: int, now: float | None = None) -> bool:
    until = granted_until(conn, user_id)
    return bool(until and until > (now if now is not None else time.time()))


class RedeemError(RuntimeError):
    """Refusal, with a message written for the person typing the code."""


def redeem(conn, user_id: int, code: str, now: float | None = None,
           env: dict | None = None) -> dict:
    """Apply a code to an account. Raises RedeemError with a sentence.

    ONE GENERIC REFUSAL for "no such code" and for "that code is used
    up". Telling them apart tells an attacker which codes exist, and the
    person holding a real code sees neither message.
    """
    now = time.time() if now is None else now
    code = normalize(code)
    init(conn)

    if _recent_attempts(conn, user_id, now) >= MAX_ATTEMPTS:
        raise RedeemError("Too many attempts. Try again in an hour.")

    codes = catalogue(env)
    spec = codes.get(code) if CODE_RE.match(code or "") else None

    # The already-redeemed case is checked BEFORE the generic refusal so
    # that a real holder re-typing their own code gets a true answer
    # rather than the decoy.
    mine = conn.execute(
        "SELECT granted_to FROM code_redemptions WHERE code=? AND user_id=?",
        (code, int(user_id))).fetchone()
    if mine:
        raise RedeemError("You have already used this code.")

    if not spec or (spec["max_uses"] and uses(conn, code) >= spec["max_uses"]):
        _note_attempt(conn, user_id, now)
        conn.commit()
        raise RedeemError("That code is not valid.")

    months = int(spec["months"])
    # FROM NOW, not from an existing expiry. Stacking would let a code
    # with a hundred uses be walked forward by a hundred friends into one
    # account holding a decade.
    until = now + months * MONTH_S
    try:
        conn.execute(
            "INSERT INTO code_redemptions(code, user_id, months, granted_to,"
            " created_at) VALUES(?, ?, ?, ?, ?)",
            (code, int(user_id), months, until, now))
    except Exception as exc:                                  # noqa: BLE001
        # The primary key fired, which means a simultaneous request won
        # the race. That is the cap working, not an error worth a 500.
        raise RedeemError("You have already used this code.") from exc
    conn.commit()
    return {"code": code, "months": months, "granted_to": until}


def describe(conn, user_id: int, now: float | None = None) -> dict:
    """What the account page shows about codes on this account."""
    now = time.time() if now is None else now
    until = granted_until(conn, user_id)
    rows = conn.execute(
        "SELECT code, months, granted_to FROM code_redemptions "
        "WHERE user_id=? ORDER BY created_at DESC", (int(user_id),)).fetchall()
    return {
        "active": bool(until and until > now),
        "granted_to": until,
        "codes": [{"code": r["code"], "months": r["months"],
                   "granted_to": r["granted_to"]} for r in rows],
    }
