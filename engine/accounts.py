"""Real accounts: email and password, stored on our own server.

Ethan, 2026-08-15: *"we will be storing user information and passwords
and logins ... we need to make a feature where you can make an account on
our website with email and password so we can store peoples bets and
fantasy leauges and search history or anything like that."*

THIS REPLACES A RULE, AND THE RULE IS WRITTEN DOWN AS CHANGED. The old
one — name plus an optional numeric PIN, no email, no password — existed
because the site was one laptop serving a LAN. It is not a security
principle we are abandoning; it was a scope, and the scope changed. What
does NOT change is the reason behind the other rule it kept getting
confused with: this app still does not ask anyone for their DraftKings or
ESPN password, because a credential to somebody else's service cannot be
scoped and cannot be revoked by us. Our own login can be both.

WHAT "STORING A PASSWORD" ACTUALLY MEANS HERE, because the phrase is
doing a lot of work: what goes in the database is a **scrypt verifier**,
not the password. It is a one-way function of it. Nobody with the file —
me, Ethan, or whoever ends up with a copy of it — can read a password out
of it, and that is the point rather than a hedge on the instruction. It
is also why this app can never email anyone their password back; it can
only ever let them set a new one. Every real service works this way, and
a service that could show you your own password would be telling you it
had failed to do this.

THE FOUR DECISIONS WORTH ARGUING WITH LATER:

  * **scrypt, not PBKDF2.** The PIN store used PBKDF2-SHA256 at 60k
    iterations, which is fine against a CPU and weak against a GPU farm.
    scrypt is memory-hard: 16MB per guess is cheap once and ruinous a
    billion times. The parameters live INSIDE the stored string, so they
    can be raised later without invalidating anybody's existing password.
  * **The session token is hashed at rest too.** Same argument as the
    password, and it is the one people skip: a token in the clear in a
    database is a live session for anyone who reads the file. We store
    sha256 of it and compare in constant time.
  * **A failed login costs the same time whether or not the email
    exists.** Otherwise the response clock is an account-enumeration
    oracle — ask about ten thousand addresses, learn which ones are real.
    A missing user is checked against a dummy verifier so the work is
    identical.
  * **Length beats character classes.** Ten characters minimum and a
    check against the obvious ones. Demanding a symbol and a digit
    produces `Password1!` on a sticky note, which is worse than a long
    passphrase by every measure anybody has managed to take.

Standard library only, like the rest of this repo. SQLite because email
uniqueness and session expiry want a real index and a real transaction,
and because the threading server can have two requests in the same table
at once.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from pathlib import Path

from .db import column_exists_or_raise

#: Owner-only, beside the other machine-local state. `*.db` is gitignored
#: and this is pinned by name in tests/test_gitignore.py as well — it
#: holds every user's email and verifier, which is the single worst file
#: in this repo to leak.
#:
#: ANCHORED TO THE REPO, not to the working directory. This was
#: `Path("data") / "accounts.db"` until 2026-08-15, which meant starting
#: the server from any other directory silently created a second, empty
#: accounts database: every user gone, new signups landing in a file that
#: is not on the backup list and that nobody would think to look for.
#: Found by doing it by accident from a scratch directory. ledger.py and
#: db.py both anchor this way; this was the one that did not.
#:
#: QB_ACCOUNTS_DB OVERRIDES IT, and exists for one reason: an end-to-end
#: test has to start a real server and sign a real account up, and doing
#: that against the file real accounts live in is how a test deletes
#: somebody. The override is read once, at import, so nothing can move
#: the database out from under a running process.
DB_PATH = Path(os.environ.get("QB_ACCOUNTS_DB", "").strip()
               or Path(__file__).resolve().parents[1] / "data" / "accounts.db")

#: scrypt work factors. 128 * N * r bytes per guess = 16MB here.
SCRYPT_N = 1 << 14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32
SCRYPT_MAXMEM = 64 * 1024 * 1024

#: Sessions last a month, refreshed on use. Long enough that a phone kept
#: in a pocket stays signed in, short enough that an abandoned device
#: stops being one eventually.
SESSION_DAYS = 30
SESSION_TTL = SESSION_DAYS * 86400

MIN_PASSWORD = 10
MAX_PASSWORD = 200          # scrypt on a 10MB "password" is a free DoS
MAX_EMAIL = 254             # the real limit on an address

#: Wrong-password throttle. Held in memory on purpose: it protects a live
#: process against a live guesser, and a restart clearing it is not the
#: threat being defended against.
MAX_FAILS = 8
LOCKOUT_S = 900

#: A forgotten password (Ethan, 2026-10-11: "there's no option for if you
#: forget your password, you can't get it back"). The verifier is one-way,
#: so nothing can be sent back — a reset link lets the owner of the address
#: choose a new one. It works for an hour and once: long enough to find the
#: email in a spam folder, short enough that a link left in an inbox is not
#: a standing key to the account.
RESET_TTL = 3600
#: At most this many links an hour to one address. The per-network auth
#: bucket caps how fast one network can ask; this caps how hard any number
#: of networks can fill a stranger's inbox with our mail.
RESET_PER_HOUR = 3
#: Where a reset link points when QB_SITE_URL is not set. NEVER the Host
#: header: that is whatever the requester typed, and a link built from it
#: sends the victim's token to the attacker's domain (Host-header
#: injection, the classic way a reset flow is broken).
SITE_URL = "https://qellysbook.com"

#: Sections an account can hold. `search` is new with this feature —
#: Ethan asked for search history alongside bets and fantasy.
#:
#: `settings` (2026-08-25) is odds format, stake display, time zone,
#: favourite teams and which leagues show in the nav — Ethan: "Settings
#: that stick". It is a preferences blob and rides the same
#: last-writer-wins rule as fantasy and bankroll, which is right for it:
#: two devices disagreeing about a display preference should settle on
#: whichever was set most recently, and there is nothing here that can
#: be lost the way a journaled bet can.
SECTIONS = ("mybets", "fantasy", "bankroll", "search", "settings")
MAX_SECTION_BYTES = 1_000_000

_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s.]+(\.[^@\s.]+)+$")

#: The handful that show up at the top of every breach corpus. Not a
#: dictionary check — a real one needs a wordlist this repo will not ship
#: — just enough that the most-guessed strings do not sail through a
#: length rule.
_OBVIOUS = {
    "password", "password1", "password123", "passw0rd", "qwertyuiop",
    "1234567890", "12345678901", "letmein123", "iloveyou1", "adminadmin",
    "welcome123", "abc123456", "football12", "baseball12", "qwerty12345",
}

_fails: dict[str, list] = {}


# --- the two strings we accept from a stranger -------------------------------
def normalize_email(email) -> str:
    """Lowercased and trimmed. Nothing cleverer, deliberately.

    Gmail treats dots and +tags as noise; most other providers do not, and
    an app that "helpfully" strips them decides two different people are
    one account. Case is the only part every provider agrees on.
    """
    return str(email or "").strip().lower()


def email_ok(email) -> bool:
    e = normalize_email(email)
    return bool(e) and len(e) <= MAX_EMAIL and bool(_EMAIL_RE.match(e))


def password_problem(password) -> str | None:
    """The reason it is not acceptable, or None. Says which rule failed.

    "Invalid password" tells someone nothing about what to type next, and
    a rule the user cannot see is a rule they cannot satisfy.
    """
    pw = password if isinstance(password, str) else ""
    if len(pw) < MIN_PASSWORD:
        return (f"Use at least {MIN_PASSWORD} characters. Length is what "
                f"makes a password hard to guess — a phrase you will "
                f"remember beats a short word with symbols in it.")
    if len(pw) > MAX_PASSWORD:
        return f"That is over {MAX_PASSWORD} characters."
    # Checked BOTH raw and stripped of decoration. An exact-match list
    # lets `password1!` through while catching `password1`, which is not
    # a distinction any guesser respects — the decorated forms are in the
    # same breach corpora. This is still a thin backstop and not a
    # dictionary check: a real one needs a wordlist this repo will not
    # ship, and the length rule above is doing most of the work.
    plain = re.sub(r"[^a-z0-9]", "", pw.lower())
    if pw.lower() in _OBVIOUS or plain in _OBVIOUS:
        return "That one is on every list of guessed passwords."
    if len(set(pw)) < 4:
        return "That is too few different characters."
    return None


# --- the verifier ------------------------------------------------------------
def hash_password(password: str, salt: bytes | None = None) -> str:
    """``scrypt$N$r$p$salt$hash`` — parameters inside, so they can be raised.

    A stored verifier that does not say how it was made can never be
    upgraded without asking everybody to reset. This one carries its own
    recipe.
    """
    salt = salt or secrets.token_bytes(16)
    with _AUTH_SLOTS:                       # 16MB a call — see AUTH_CONCURRENCY
        dk = hashlib.scrypt(str(password).encode("utf-8"), salt=salt,
                            n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P,
                            dklen=SCRYPT_DKLEN, maxmem=SCRYPT_MAXMEM)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${dk.hex()}"


def verify_password(stored: str, password: str) -> bool:
    """Constant-time compare against a stored verifier.

    `==` on a hash leaks its prefix through timing. `compare_digest` does
    not, and it costs nothing to use the right one.
    """
    try:
        algo, n, r, p, salt_hex, want = str(stored or "").split("$")
        if algo != "scrypt":
            return False
        with _AUTH_SLOTS:                   # 16MB a call — see AUTH_CONCURRENCY
            dk = hashlib.scrypt(str(password).encode("utf-8"),
                                salt=bytes.fromhex(salt_hex),
                                n=int(n), r=int(r), p=int(p),
                                dklen=len(want) // 2, maxmem=SCRYPT_MAXMEM)
    except (ValueError, TypeError, MemoryError):
        return False
    return hmac.compare_digest(dk.hex(), want)


#: HOW MANY PASSWORD HASHES MAY BE IN FLIGHT AT ONCE.
#:
#: scrypt is memory-hard on purpose — that is the whole reason it was
#: chosen over PBKDF2 — and `128 * N * r` here is 16MB PER CALL. The
#: server's own ceiling (`MAX_INFLIGHT`, 64) bounds THREADS, and the
#: comment justifying 64 says "each is a sqlite read measured in
#: milliseconds". That is true of every route except these two, and
#: these two are the ones a burst lands on.
#:
#: Measured 2026-09-09, threads all calling `hash_password`:
#:
#:    1 concurrent   0.06s   peak RSS  51 MB
#:    8 concurrent   0.24s   peak RSS 163 MB
#:   32 concurrent   0.79s   peak RSS 516 MB
#:   64 concurrent   1.67s   peak RSS 963 MB
#:
#: 963MB is the whole droplet, and what dies is the process — every
#: signed-in session with it. The per-IP limiter upstream caps the RATE
#: (20/min) and says nothing about CONCURRENCY: twenty requests from one
#: address may all be in flight in the same second, and several addresses
#: multiply it.
#:
#: 8 is chosen off that table: 163MB is affordable, and at 57ms a hash it
#: still clears ~140 sign-ins a second, which is orders of magnitude past
#: anything this site will see. Over the limit, callers WAIT rather than
#: fail — a queued sign-in that takes an extra 200ms is invisible, and a
#: 503 on the sign-up form is not.
#:
#: Deliberately here and not in server.py: this covers every caller —
#: sign-up, sign-in, the change-password path, and the dummy verify that
#: equalizes timing for unknown emails — rather than the routes somebody
#: remembered to wrap.
AUTH_CONCURRENCY = max(1, int(os.environ.get("QB_AUTH_CONCURRENCY", "") or 8))
_AUTH_SLOTS = threading.Semaphore(AUTH_CONCURRENCY)


#: Burned when the email does not exist, so a login against an unknown
#: address costs the same as one against a known address. Built once at
#: import so the cost is the scrypt call and not the salt generation.
_DUMMY = hash_password("account-enumeration-is-a-real-attack")


def _equalize(password: str) -> None:
    verify_password(_DUMMY, password)


# --- storage -----------------------------------------------------------------
_ONCE: dict = {}


def once_per_db(fn):
    """Run a schema init once per database file per process (audit F-9).

    `CREATE INDEX IF NOT EXISTS` takes the write lock even when the index is
    there, and these inits ran on every request — so every signed-in board
    poll queued behind every other one, and under load waited out the
    10-second busy timeout and 502'd. Keyed on the file's path and identity;
    a skip is confirmed by a READ of the schema (a deleted-and-recreated
    file at a reused inode has fewer objects and is initialised again). An
    in-memory database is always initialised."""
    import functools

    def _schema_n(conn):
        return conn.execute("SELECT count(*) FROM sqlite_master").fetchone()[0]

    @functools.wraps(fn)
    def run(conn, *a, **k):
        try:
            f = conn.execute("PRAGMA database_list").fetchone()[2]
            st = os.stat(f) if f else None
        except Exception:                                     # noqa: BLE001
            st = None
        key = (fn.__module__, fn.__qualname__, f, st.st_dev, st.st_ino) if st else None
        if key is not None and key in _ONCE:
            try:
                if _schema_n(conn) >= _ONCE[key]:
                    return None
            except Exception:                                 # noqa: BLE001
                pass
        out = fn(conn, *a, **k)
        if key is not None:
            try:
                _ONCE[key] = _schema_n(conn)
            except Exception:                                 # noqa: BLE001
                _ONCE.pop(key, None)
        return out
    return run


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    p = Path(path or DB_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    fresh = not p.exists()
    conn = sqlite3.connect(str(p), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _init(conn)
    if fresh:
        # The file holds emails and verifiers; default 0644 means every
        # account on the box can read it. Set before anything is written.
        try:
            os.chmod(str(p), 0o600)
        except OSError:
            pass
    return conn


@once_per_db
def _init(conn: sqlite3.Connection) -> None:
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS users (
        id         INTEGER PRIMARY KEY,
        email      TEXT NOT NULL UNIQUE,
        verifier   TEXT NOT NULL,
        created_at REAL NOT NULL,
        last_seen  REAL
      );
      CREATE TABLE IF NOT EXISTS sessions (
        token_hash TEXT PRIMARY KEY,
        user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at REAL NOT NULL,
        expires_at REAL NOT NULL
      );
      CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
      CREATE TABLE IF NOT EXISTS password_resets (
        token_hash TEXT PRIMARY KEY,
        user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at REAL NOT NULL,
        expires_at REAL NOT NULL
      );
      CREATE INDEX IF NOT EXISTS password_resets_user ON password_resets(user_id);
      CREATE TABLE IF NOT EXISTS user_data (
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        section TEXT NOT NULL,
        ts      INTEGER NOT NULL,
        payload TEXT NOT NULL,
        PRIMARY KEY (user_id, section)
      );
    """)
    _migrate(conn)
    conn.commit()


def _migrate(conn) -> None:
    """Additive column migrations, safe to run on every start.

    THE FIRST ONE OF THESE, and the pattern matters more than the columns.
    `CREATE TABLE IF NOT EXISTS` covers a new table and does nothing at all
    for a new COLUMN on a table that already exists — so an existing
    accounts.db would keep its old shape while the code expected the new
    one, and the failure lands on a live account rather than in a test.

    Additive only, by rule. Once other people's data is in here, a
    destructive migration needs a written plan and a fresh backup, not a
    line in this function.
    """
    have = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    for col, decl in (("age_confirmed", "INTEGER NOT NULL DEFAULT 0"),
                      ("terms_accepted_at", "REAL"),
                      # A phone account's number, E.164 (engine/smsverify).
                      ("phone", "TEXT")):
        if col not in have:
            # The read above is a fast path, not a lock. `once_per_db` is
            # a memo too, so on a box whose users table predates one of
            # these columns, concurrent first requests can both read it
            # missing and both ALTER it; the loser raised out of connect()
            # and answered 500 (the race the feed, billing and the digest
            # hit — nightly 2026-10-27). Only the duplicate is swallowed;
            # a lock must still raise (audit 2026-09-30, F-10).
            try:
                conn.execute(f"ALTER TABLE users ADD COLUMN {col} {decl}")
            except sqlite3.OperationalError as exc:
                column_exists_or_raise(exc)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_phone ON users(phone) WHERE phone IS NOT NULL")


# --- accounts ----------------------------------------------------------------
def create_user(conn, email, password, confirmed=False) -> tuple[int, dict]:
    """``(status, body)``. 409 when the address is already registered.

    `confirmed` is the age-and-terms acknowledgment, and it is REQUIRED.
    Recorded server-side with a timestamp rather than trusted to a
    localStorage flag: a flag in the browser proves nothing later, and
    "did this person agree" is exactly the question you get asked when it
    matters.
    """
    e = normalize_email(email)
    if not email_ok(e):
        return 400, {"error": "That does not look like an email address."}
    why = password_problem(password)
    if why:
        return 400, {"error": why}
    if not confirmed:
        return 400, {"error": "Please confirm you are 21 or older and accept "
                              "the Terms and Privacy Policy."}
    try:
        cur = conn.execute(
            "INSERT INTO users (email, verifier, created_at, age_confirmed, "
            "terms_accepted_at) VALUES (?,?,?,1,?)",
            (e, hash_password(password), time.time(), time.time()))
        conn.commit()
    except sqlite3.IntegrityError:
        # Deliberately explicit. Hiding it protects an address that the
        # signup form would reveal anyway by refusing, and the cost of
        # coyness here is a person who cannot tell why they cannot sign up.
        return 409, {"error": "There is already an account with that email."}
    _consented(conn, cur.lastrowid)
    return 200, {"id": int(cur.lastrowid), "email": e}


def _consented(conn, user_id) -> None:
    """The 21+ and terms confirmation, in the consent log too (engine/consent:
    which policy, when) — never in the way of the account it records."""
    try:
        from . import consent
        consent.record(conn, user_id, "terms", "21 or older; the Terms and Privacy Policy")
        conn.commit()
    except sqlite3.Error:
        pass


def create_phone_user(conn, phone: str, confirmed=False) -> tuple[int, dict]:
    """``(status, body)`` for an account made with a verified phone number
    (engine/smsverify — the caller has already checked the code). No
    password: it signs in by a code, so the verifier is a random one nobody
    holds. The email column carries the non-deliverable placeholder."""
    from . import smsverify as SV
    if not SV.normalize(phone) or SV.normalize(phone) != phone:
        return 400, {"error": "That doesn’t look like a US or Canadian number."}
    if not confirmed:
        return 400, {"error": "Please confirm you are 21 or older and accept "
                              "the Terms and Privacy Policy."}
    import secrets as _s
    try:
        cur = conn.execute(
            "INSERT INTO users (email, verifier, created_at, age_confirmed, terms_accepted_at, phone) "
            "VALUES (?,?,?,1,?,?)",
            (SV.placeholder_email(phone), hash_password(_s.token_urlsafe(32)), time.time(), time.time(), phone))
        conn.commit()
    except sqlite3.IntegrityError:
        return 409, {"error": "There is already an account with that number."}
    _consented(conn, cur.lastrowid)
    return 200, {"id": int(cur.lastrowid), "email": SV.placeholder_email(phone), "phone": phone}


def user_by_phone(conn, phone: str):
    row = conn.execute("SELECT id, email FROM users WHERE phone=?", (str(phone or ""),)).fetchone()
    return {"id": int(row[0]), "email": row[1]} if row else None


def _throttled(key: str) -> int:
    hits = [t for t in _fails.get(key, []) if time.time() - t < LOCKOUT_S]
    _fails[key] = hits
    if len(hits) < MAX_FAILS:
        return 0
    return int(LOCKOUT_S - (time.time() - hits[0])) + 1


def _note_fail(key: str) -> None:
    _fails.setdefault(key, []).append(time.time())
    if len(_fails) > 4096:                       # bounded: this is memory
        _evict()


def _evict() -> None:
    """Make room WITHOUT forgiving a target (audit 2026-09-30, E-3).

    The old eviction dropped the first 1024 keys by insertion order, so a
    spray of throwaway addresses pushed a real target's counter out and
    reset its lockout. Now: expired windows go first, then the keys with
    the FEWEST recent failures — a spray's single-guess keys evict
    themselves, and an account under attack keeps its count."""
    now = time.time()
    for k in [k for k, v in _fails.items() if not v or now - v[-1] >= LOCKOUT_S]:
        _fails.pop(k, None)
    if len(_fails) > 3072:
        for k in sorted(_fails, key=lambda k: len(_fails[k]))[:len(_fails) - 3072]:
            _fails.pop(k, None)


def authenticate(conn, email, password, where: str | None = None) -> tuple[int, dict]:
    """``(status, body)``. Never says which half was wrong.

    "No such account" and "wrong password" are the same message on
    purpose: told apart, they turn the login form into a way to check
    whether an address is registered here.

    THE LOCKOUT IS PER ACCOUNT *AND* PER NETWORK (`where`, the caller's
    /24 from the server; audit 2026-09-30, E-3). Keyed on the email alone,
    eight wrong guesses from anywhere refused the real owner's CORRECT
    password for fifteen minutes — a lockout-DoS of any known address.
    Now the guesses lock out the network they came from; the owner signing
    in from their own network is never refused. The per-IP auth bucket in
    the server still caps how fast any one network can guess.
    """
    e = normalize_email(email)
    key = f"{e}|{where}" if where else e
    wait = _throttled(key)
    if wait:
        return 429, {"error": f"Too many attempts. Try again in "
                              f"{max(1, wait // 60)} minute(s)."}
    row = conn.execute("SELECT id, verifier FROM users WHERE email=?",
                       (e,)).fetchone()
    if row is None:
        _equalize(str(password or ""))
        _note_fail(key)
        return 403, {"error": "Wrong email or password."}
    if not verify_password(row["verifier"], str(password or "")):
        _note_fail(key)
        return 403, {"error": "Wrong email or password."}
    _fails.pop(key, None)
    conn.execute("UPDATE users SET last_seen=? WHERE id=?",
                 (time.time(), row["id"]))
    conn.commit()
    return 200, {"id": int(row["id"]), "email": e}


def change_password(conn, user_id: int, old: str, new: str) -> tuple[int, dict]:
    row = conn.execute("SELECT verifier FROM users WHERE id=?",
                       (int(user_id),)).fetchone()
    if row is None:
        return 404, {"error": "No such account."}
    if not verify_password(row["verifier"], str(old or "")):
        return 403, {"error": "That is not your current password."}
    why = password_problem(new)
    if why:
        return 400, {"error": why}
    conn.execute("UPDATE users SET verifier=? WHERE id=?",
                 (hash_password(new), int(user_id)))
    # Every other device is signed out. A password change is usually a
    # response to "somebody else may have this", and leaving their session
    # alive answers that with nothing.
    conn.execute("DELETE FROM sessions WHERE user_id=?", (int(user_id),))
    # …and any reset link still sitting in an inbox dies with the old
    # password, for the same reason.
    conn.execute("DELETE FROM password_resets WHERE user_id=?", (int(user_id),))
    conn.commit()
    return 200, {"ok": True}


# --- a forgotten password ------------------------------------------------------
#: Said for a link that is unknown, expired or already used — one message
#: for all three, because telling them apart helps nobody but a guesser.
RESET_EXPIRED = ("That reset link has expired or was already used — "
                 "send yourself a new one.")


def start_reset(conn, email) -> str | None:
    """A reset token for this address, or None. The RAW token is returned —
    the only moment it exists here; what is stored is its sha256, like a
    session's, so the file never holds a working link.

    THE CALLER SAYS THE SAME THING EITHER WAY. None means no such account
    OR this address already has RESET_PER_HOUR links this hour, and the
    browser is told "if there is an account, a link is on its way" in
    every case — anything else turns the form into a way to ask which
    addresses are registered here.

    Earlier unexpired links stay good until one is used: somebody who asks
    twice and opens the first email must not find it dead.
    """
    e = normalize_email(email)
    if not email_ok(e):
        return None
    row = conn.execute("SELECT id FROM users WHERE email=?", (e,)).fetchone()
    if row is None:
        return None
    now = time.time()
    conn.execute("DELETE FROM password_resets WHERE expires_at < ?", (now,))
    recent = conn.execute(
        "SELECT COUNT(*) FROM password_resets WHERE user_id=? AND created_at > ?",
        (int(row["id"]), now - 3600)).fetchone()[0]
    if recent >= RESET_PER_HOUR:
        conn.commit()
        return None
    token = secrets.token_urlsafe(32)
    conn.execute("INSERT INTO password_resets (token_hash, user_id, created_at, "
                 "expires_at) VALUES (?,?,?,?)",
                 (_token_hash(token), int(row["id"]), now, now + RESET_TTL))
    conn.commit()
    return token


def finish_reset(conn, token, new_password) -> tuple[int, dict]:
    """``(status, body)``: set a new password from a reset link.

    A password that fails the rules does NOT spend the link — the person
    can try a better one. A good one spends it in the same transaction that
    writes the new verifier, so two tabs racing the same link cannot both
    win. Every session is ended (the old password may be the reason they
    are here) and every other link for the account dies with it.
    """
    t = str(token or "")
    row = conn.execute(
        "SELECT r.user_id, r.expires_at, u.email FROM password_resets r "
        "JOIN users u ON u.id = r.user_id WHERE r.token_hash=?",
        (_token_hash(t),)).fetchone() if t else None
    if row is None or float(row["expires_at"]) < time.time():
        return 400, {"error": RESET_EXPIRED}
    why = password_problem(new_password)
    if why:
        return 400, {"error": why}
    uid = int(row["user_id"])
    verifier = hash_password(new_password)          # the slow part, before the claim
    claimed = conn.execute(
        "DELETE FROM password_resets WHERE token_hash=? AND expires_at >= ?",
        (_token_hash(t), time.time())).rowcount
    if not claimed:
        conn.rollback()
        return 400, {"error": RESET_EXPIRED}
    conn.execute("UPDATE users SET verifier=? WHERE id=?", (verifier, uid))
    conn.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM password_resets WHERE user_id=?", (uid,))
    conn.commit()
    # Whatever wrong guesses they made before giving up are forgiven: the
    # owner of the address just proved it, and a lockout left standing
    # would refuse their new password on their next sign-in.
    e = str(row["email"])
    for k in [k for k in _fails if k == e or k.startswith(e + "|")]:
        _fails.pop(k, None)
    return 200, {"id": uid, "email": e}


def site_url() -> str:
    """The site's own address for links that leave it: QB_SITE_URL (read
    from secrets.local too), else SITE_URL. Never a request header."""
    from . import secrets as _local
    _local.load_local_secrets()
    return os.environ.get("QB_SITE_URL", "").strip().rstrip("/") or SITE_URL


def reset_link(token: str, base: str | None = None) -> str:
    """The token rides in the FRAGMENT (``#reset/…``): a browser never sends
    a fragment to any server, so it stays out of access logs, proxies and
    Referer headers. The page reads it, then takes it out of the address
    bar."""
    return f"{(base or site_url()).rstrip('/')}/#reset/{token}"


def reset_message(link: str) -> tuple[str, str, str]:
    """``(subject, text, html)`` for the reset email. Both parts — see
    engine.mailer.message."""
    import html as _html
    subject = "Reset your Qellys Book password"
    text = ("Someone asked to reset the password for the Qellys Book account "
            "at this address.\n\n"
            "If it was you, open this link within the hour to choose a new "
            "password. It works once:\n\n"
            f"{link}\n\n"
            "If it was not you, ignore this email. Your password has not "
            "changed, and nobody can change it without this link.\n\n"
            "Qellys Book\n")
    safe = _html.escape(link, quote=True)
    html = ("<p>Someone asked to reset the password for the Qellys Book "
            "account at this address.</p>"
            "<p>If it was you, open this link within the hour to choose a new "
            "password. It works once:</p>"
            f'<p><a href="{safe}">Choose a new password</a></p>'
            f"<p style=\"color:#666;font-size:13px\">{safe}</p>"
            "<p>If it was not you, ignore this email. Your password has not "
            "changed, and nobody can change it without this link.</p>"
            "<p>Qellys Book</p>")
    return subject, text, html


def end_all_sessions(conn, user_id: int) -> int:
    """Sign this account out everywhere, including here. Returns how many.

    A password change already does this, and does it for the same reason.
    This is the version for somebody who does NOT want to change their
    password: a laptop left signed in at a library, a phone that was
    sold. Without it the only way to revoke a session you cannot reach is
    to change a password you had no other reason to change.
    """
    n = conn.execute("SELECT COUNT(*) FROM sessions WHERE user_id=?",
                     (int(user_id),)).fetchone()[0]
    conn.execute("DELETE FROM sessions WHERE user_id=?", (int(user_id),))
    conn.commit()
    return int(n)


# --- sessions ----------------------------------------------------------------
def _token_hash(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def start_session(conn, user_id: int) -> str:
    """Returns the RAW token — the only moment it exists in this process.

    What is stored is its sha256. A database that holds live tokens hands
    out sessions to anyone who reads it; one that holds hashes does not.
    """
    token = secrets.token_urlsafe(32)
    now = time.time()
    conn.execute("INSERT INTO sessions (token_hash, user_id, created_at, "
                 "expires_at) VALUES (?,?,?,?)",
                 (_token_hash(token), int(user_id), now, now + SESSION_TTL))
    conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
    conn.commit()
    return token


def session_user(conn, token) -> dict | None:
    """The account behind a token, or None. Expiry is enforced here."""
    if not token:
        return None
    row = conn.execute(
        "SELECT u.id, u.email, s.expires_at FROM sessions s "
        "JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?",
        (_token_hash(token),)).fetchone()
    if row is None or float(row["expires_at"]) < time.time():
        return None
    return {"id": int(row["id"]), "email": row["email"]}


def touch_session(conn, token) -> None:
    """Slide the expiry forward on use, so an active device stays signed
    in and an abandoned one still ages out."""
    conn.execute("UPDATE sessions SET expires_at=? WHERE token_hash=?",
                 (time.time() + SESSION_TTL, _token_hash(token)))
    conn.commit()


def end_session(conn, token) -> None:
    conn.execute("DELETE FROM sessions WHERE token_hash=?",
                 (_token_hash(token),))
    conn.commit()


# --- the data an account carries ---------------------------------------------
def get_sections(conn, user_id: int) -> dict:
    out = {}
    for r in conn.execute("SELECT section, ts, payload FROM user_data "
                          "WHERE user_id=?", (int(user_id),)):
        try:
            out[r["section"]] = {"ts": int(r["ts"]),
                                 "data": json.loads(r["payload"])}
        except ValueError:
            continue
    return out


@contextlib.contextmanager
def one_writer(conn):
    """A read and the write it decides, under one write lock.

    TWO WRITERS SHARE A MEMBER'S MY BETS (2026-10-14). The page's sync
    reads the stored sections, merges its own in (server.merge_sections)
    and writes the union; the box's slip watch reads the same row, marks a
    saved slip settled and writes it back (engine/slipwatch). Each is a
    read, then a write built on what it read, so without one lock the
    later writer's copy is built on a read taken before the other's write
    and loses it: a settle the sync never saw, or a bet the phone had just
    added. BEGIN IMMEDIATE takes SQLite's write lock before the read, so
    the second writer waits (the connection's busy timeout) and then reads
    the first one's result. Works across the server's threads and any
    other process on the file alike."""
    if conn.in_transaction:
        conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        if conn.in_transaction:
            conn.rollback()
        raise
    if conn.in_transaction:
        conn.commit()


def save_sections(conn, user_id: int, sections: dict) -> None:
    """Whole sections, already merged by the caller.

    The merge policy lives in `server.py` next to the bet-signature rules
    it depends on — union by signature, tombstones, a graded bet never
    un-settled by a stale pending copy — and is shared with the older
    profile store rather than reimplemented here, because two
    implementations of "never lose a logged bet" is one too many.
    """
    for name, sec in (sections or {}).items():
        if name not in SECTIONS or not isinstance(sec, dict):
            continue
        blob = json.dumps(sec.get("data"))
        if len(blob) > MAX_SECTION_BYTES:
            continue
        conn.execute(
            "INSERT INTO user_data (user_id, section, ts, payload) "
            "VALUES (?,?,?,?) ON CONFLICT(user_id, section) DO UPDATE SET "
            "ts=excluded.ts, payload=excluded.payload",
            (int(user_id), name, int(sec.get("ts") or 0), blob))
    conn.commit()


def delete_user(conn, user_id: int) -> None:
    """Everything, in one transaction. If we are going to hold people's
    data we have to be able to actually give it back up.

    Every table is named here rather than left to `ON DELETE CASCADE`.
    The cascade is real and it works — but only on a connection that ran
    `PRAGMA foreign_keys=ON`, which is per-connection and off by default
    in SQLite. `connect()` sets it, so today the two agree. The day some
    script opens this file without it, the difference between the two
    approaches is a row in `subscriptions` outliving the account it
    belonged to: a Stripe customer_id is a pointer to a real person's
    name and card at Stripe, and the privacy page promises it is gone.
    A promise that depends on a pragma being set is not a promise.

    `subscriptions` is created by engine.billing, which may never have run
    on this database, so its absence is normal rather than an error.
    """
    conn.execute("DELETE FROM user_data WHERE user_id=?", (int(user_id),))
    conn.execute("DELETE FROM sessions WHERE user_id=?", (int(user_id),))
    have = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if "password_resets" in have:
        # A live reset link is a credential, and it dies with the account.
        conn.execute("DELETE FROM password_resets WHERE user_id=?", (int(user_id),))
    if "subscriptions" in have:
        conn.execute("DELETE FROM subscriptions WHERE user_id=?", (int(user_id),))
    # The streak game's tables (engine/streak.py) and tail-or-fade's
    # (engine/tailfade.py) — same posture as `subscriptions`: created by
    # another module, so their absence is normal, and their presence
    # must not outlive the account.
    # digest_optin joins them 2026-08-25: it holds an address's mailing
    # preferences and an unsubscribe token, and a mailing list that
    # outlives the account it belonged to is the exact thing the privacy
    # page promises does not happen.
    # friendships/friend_invites/pick_shares (engine/social.py, 2026-08-25):
    # a friendship is a channel INTO other people's inboxes, an invite is
    # a live credential, and both must die with the account that held
    # them. pick_shares carries only pick identities, but they are still
    # this account's activity and go too — from both sides, which the
    # per-table DELETE below handles for the rows this user owns and the
    # mirror rows (friend_id / to_id) need their own statements.
    # slip_alerts / slip_alert_optin (engine/slipwatch, 2026-10-13): the
    # last-leg email's opt-in, its token salt and the alerts noted — a
    # mailing preference, on the digest's reasoning.
    for table in ("streak_picks", "streak_state", "tf_calls", "digest_optin",
                  "friend_invites", "slip_alerts", "slip_alert_optin"):
        if table in have:
            conn.execute(f"DELETE FROM {table} WHERE user_id=?",
                         (int(user_id),))
    if "friendships" in have:
        conn.execute("DELETE FROM friendships WHERE user_id=? OR friend_id=?",
                     (int(user_id), int(user_id)))
    if "friend_requests" in have:
        conn.execute("DELETE FROM friend_requests WHERE from_id=? OR to_id=?",
                     (int(user_id), int(user_id)))
    for shares in ("pick_shares", "parlay_shares", "dm_messages"):
        if shares in have:
            conn.execute(f"DELETE FROM {shares} WHERE from_id=? OR to_id=?",
                         (int(user_id), int(user_id)))
    if "message_deletes" in have:
        # This account's own tombstones, and any that pointed at rows the
        # share/message deletes above just removed. A tombstone whose row
        # is gone is a permanent orphan — nothing ever sweeps it, because
        # the sweep runs off the row.
        conn.execute("DELETE FROM message_deletes WHERE user_id=?",
                     (int(user_id),))
        for kind, table in (("text", "dm_messages"),
                            ("pick", "pick_shares"),
                            ("parlay", "parlay_shares")):
            if table in have:
                conn.execute(
                    f"DELETE FROM message_deletes WHERE kind=? AND item_id "
                    f"NOT IN (SELECT id FROM {table})", (kind,))
    if "friend_nicknames" in have:
        # Both directions: the labels this account gave out AND the rows
        # where other people's labels name it — a nickname pointing at a
        # deleted account is a dangling reference, not a keepsake.
        conn.execute("DELETE FROM friend_nicknames WHERE user_id=? OR friend_id=?",
                     (int(user_id), int(user_id)))
    # The public feed's rows (engine/socialfeed): your posts with every
    # like, tail and comment under them, and your marks on other posts.
    from . import socialfeed as _feed
    _feed.delete_user(conn, user_id)
    # THE GAME CHAT, YOUR OWN PHONE ALERTS AND REFERRALS (2026-10-25):
    # your messages and every reaction, vote and report you made
    # (engine/gamechat), the reactions and reports other people left on
    # the messages that just went, the per-account alert rows
    # (engine/pushmine), and both sides of a referral (engine/referrals).
    # A phone's own subscription is the device's: it keeps the public
    # alerts it asked for, with this account unlinked from it.
    for table in ("chat_msgs", "chat_reacts", "chat_play_reacts", "chat_votes", "chat_potg", "chat_reminders",
                  "chat_reports",
                  "chat_party_members",
                  "push_mine", "push_watch_seen", "push_activities", "push_lineup_leagues", "referral_codes",
                  # A live game on the lock screen (engine/gameactivity).
                  "push_game_activities",
                  # The Alerts page's watches (engine/alerts), which had
                  # leaned on ON DELETE CASCADE alone — the very thing this
                  # function's docstring says not to trust.
                  "alert_watches", "alert_seen",
                  # Codes redeemed and the guesses counted against them
                  # (engine/redeem), likewise cascade-only until now.
                  "code_redemptions", "code_attempts",
                  # Call it's calls on live games (engine/callit), and the
                  # answers to the trivia in the stoppages (engine/trivia).
                  "callit_calls", "trivia_answers",
                  # The calendar link's salt (engine/calfeed), which had
                  # been left behind, and the iPhone widget's
                  # (engine/widgetfeed): with the row gone, neither address
                  # answers again.
                  "calendar_links", "widget_links",
                  # Passkeys (engine/passkeys): the keys, the account's
                  # handle and any challenge it had open. With the keys
                  # gone the devices' halves sign nobody in.
                  "passkeys", "passkey_users", "passkey_challenges",
                  # Karma (engine/karma): what it was for, the games
                  # watched live, the flair and the ladder choice, and the
                  # account's places in the weeks' top tens.
                  "karma_events", "karma_watch", "karma_prefs", "karma_weeks",
                  # Your own time here (engine/activity) and its switch, and
                  # when the "while you were away" alert last went
                  # (engine/engagement).
                  "activity_days", "activity_prefs", "engagement_away",
                  # Their bets' closing prices (engine/betclv) and the injury
                  # statuses last told them (engine/newsalerts).
                  "bet_clv", "news_seen",
                  # What they said yes and no to (engine/consent).
                  "consent_log"):
        if table in have:
            conn.execute(f"DELETE FROM {table} WHERE user_id=?", (int(user_id),))
    # A watch party they started stays for its friends, with them off it.
    if "chat_parties" in have:
        conn.execute("UPDATE chat_parties SET user_id=0 WHERE user_id=?", (int(user_id),))
    # A gift they bought stays bought, and one they used stays spent, with
    # them off both sides (engine/gifts).
    if "gift_codes" in have:
        conn.execute("UPDATE gift_codes SET user_id=0 WHERE user_id=?", (int(user_id),))
        conn.execute("UPDATE gift_codes SET redeemed_by=0 WHERE redeemed_by=?", (int(user_id),))
    if "chat_msgs" in have:
        for table in ("chat_reacts", "chat_reports"):
            if table in have:
                conn.execute(f"DELETE FROM {table} WHERE msg_id NOT IN (SELECT id FROM chat_msgs)")
    if "referrals" in have:
        conn.execute("DELETE FROM referrals WHERE referred_id=? OR referrer_id=?",
                     (int(user_id), int(user_id)))
    if "push_subs" in have:
        conn.execute("UPDATE push_subs SET user_id=NULL WHERE user_id=?", (int(user_id),))
    conn.execute("DELETE FROM users WHERE id=?", (int(user_id),))
    conn.commit()


def export_user(conn, user_id: int) -> dict:
    """Everything we hold about one account, as JSON.

    Deliberately includes no verifier and no session token: an export is
    a thing people mail around, and it should not carry the two secrets
    that would let somebody else be them.
    """
    row = conn.execute("SELECT email, created_at FROM users WHERE id=?",
                       (int(user_id),)).fetchone()
    if row is None:
        return {}
    out = {"email": row["email"], "created_at": row["created_at"],
           "sections": get_sections(conn, user_id)}
    # Streak-game data rides along when its tables exist: an export that
    # silently omitted a category we hold would be a partial answer to
    # "everything you have about me" wearing a complete one's name.
    have = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if "streak_state" in have:
        st = conn.execute("SELECT name, current, best FROM streak_state "
                          "WHERE user_id=?", (int(user_id),)).fetchone()
        if st:
            out["streak"] = {"name": st["name"], "current": int(st["current"]),
                             "best": int(st["best"])}
    if "streak_picks" in have:
        picks = [{"date": r["date"], "qid": r["qid"], "side": r["side"]}
                 for r in conn.execute(
                     "SELECT date, qid, side FROM streak_picks "
                     "WHERE user_id=? ORDER BY date", (int(user_id),))]
        if picks:
            out["streak_picks"] = picks
    if "tf_calls" in have:
        calls = [{"sport": r["sport"], "date": r["date"],
                  "player": r["player"], "market": r["market"],
                  "side": r["side"], "stance": r["stance"],
                  "status": r["status"], "result": r["result"]}
                 for r in conn.execute(
                     "SELECT * FROM tf_calls WHERE user_id=? "
                     "ORDER BY created_at", (int(user_id),))]
        if calls:
            out["tail_fade_calls"] = calls
    if "friendships" in have:
        n = conn.execute("SELECT COUNT(*) FROM friendships WHERE user_id=?",
                         (int(user_id),)).fetchone()[0]
        if n:
            out["friends"] = {"count": int(n)}
    if "pick_shares" in have:
        # Identities only — the rows never held anything else, which is
        # the pointer rule visible in the export too.
        sent = [{"date": r["date"], "sport": r["sport"], "player": r["player"],
                 "market": r["market"], "note": r["note"]}
                for r in conn.execute(
                    "SELECT date, sport, player, market, note FROM pick_shares "
                    "WHERE from_id=? ORDER BY created_at", (int(user_id),))]
        if sent:
            out["picks_sent_to_friends"] = sent
    if "dm_messages" in have:
        # Your words, both what you typed and when — but only YOUR side:
        # a friend's replies are the friend's data, not this export's.
        sent = [{"body": r["body"], "created_at": r["created_at"]}
                for r in conn.execute(
                    "SELECT body, created_at FROM dm_messages "
                    "WHERE from_id=? ORDER BY created_at", (int(user_id),))]
        if sent:
            out["messages_sent_to_friends"] = sent
    if "friend_nicknames" in have:
        # Only the labels YOU wrote. What other people call you is their
        # data, and this export never says it exists.
        nicks = [r["nickname"] for r in conn.execute(
            "SELECT nickname FROM friend_nicknames WHERE user_id=? "
            "ORDER BY nickname", (int(user_id),))]
        if nicks:
            out["nicknames_you_gave_friends"] = nicks
    if "parlay_shares" in have:
        # Same pointer rule: leg identities and the note, nothing priced.
        import json as _json
        sent = []
        for r in conn.execute(
                "SELECT date, sport, legs, note FROM parlay_shares "
                "WHERE from_id=? ORDER BY created_at", (int(user_id),)):
            try:
                legs = _json.loads(r["legs"])
            except ValueError:
                legs = []
            sent.append({"date": r["date"], "sport": r["sport"],
                         "legs": legs, "note": r["note"]})
        if sent:
            out["parlays_sent_to_friends"] = sent
    if "digest_optin" in have:
        # WITHOUT THE TOKEN. An export is a file people mail around, and
        # the unsubscribe token is a bearer credential — the same reason
        # this function has always refused to carry the session token or
        # the password verifier.
        d = conn.execute("SELECT morning, nightly FROM digest_optin "
                         "WHERE user_id=?", (int(user_id),)).fetchone()
        if d:
            out["email_digests"] = {"morning": bool(d["morning"]),
                                    "nightly": bool(d["nightly"])}
    if "slip_alert_optin" in have:
        # The last-leg email's switch (engine/slipwatch), and nothing of
        # its link: the same rule as the digests' row above.
        s = conn.execute("SELECT mail FROM slip_alert_optin WHERE user_id=?",
                         (int(user_id),)).fetchone()
        if s:
            out["last_leg_email"] = bool(s["mail"])
    # The public feed (engine/socialfeed, 2026-10-06): the handle, the
    # bio, every post and comment you wrote, and what you liked and tailed.
    from . import socialfeed as _feed
    mine = _feed.export_user(conn, user_id)
    if mine and (mine.get("profile") or mine.get("posts") or mine.get("comments")
                 or mine.get("likes") or mine.get("tails")):
        out["public_feed"] = mine
    # The game chat and referrals (2026-10-25): every message you posted in
    # a game's room, with the play it answered and the bet you attached;
    # your referral code and the referral your account came in on.
    if "chat_msgs" in have:
        msgs = [{"room": r["room"], "body": r["body"], "play": r["play"], "bet": r["bet"],
                 "at": r["created_at"]}
                for r in conn.execute("SELECT room, body, play, bet, created_at FROM chat_msgs "
                                      "WHERE user_id=? ORDER BY id", (int(user_id),))]
        if msgs:
            out["game_chat_messages"] = msgs
    if "referral_codes" in have:
        row = conn.execute("SELECT code FROM referral_codes WHERE user_id=?", (int(user_id),)).fetchone()
        if row:
            out["referral_code"] = row["code"]
    if "referrals" in have:
        row = conn.execute("SELECT code, attached_at, paid_at FROM referrals WHERE referred_id=?",
                           (int(user_id),)).fetchone()
        if row:
            out["joined_with_referral_code"] = {"code": row["code"], "at": row["attached_at"],
                                                "first_payment_at": row["paid_at"]}
    if "callit_calls" in have:
        calls = [dict(r) for r in conn.execute("SELECT game, unit, call, result, won, at FROM callit_calls "
                                               "WHERE user_id=? ORDER BY at", (int(user_id),))]
        if calls:
            out["call_it_calls"] = calls
    from . import karma as _karma
    out.update(_karma.export_user(conn, user_id))
    # Your own time here, a row a day (engine/activity), or that you
    # turned it off.
    if "activity_days" in have:
        from . import activity as _act
        out.update(_act.export_user(conn, user_id))
    # Every yes and no they gave us, with the policy's date (engine/consent).
    if "consent_log" in have:
        from . import consent as _consent
        out["consent_log"] = _consent.history(conn, user_id)
    # The closing prices seen for their saved slips (engine/betclv).
    if "bet_clv" in have:
        rows = [dict(zip(("bet", "leg", "entry", "close", "fair", "at"), r)) for r in conn.execute(
            "SELECT bet_id, leg, entry, best, fair, at FROM bet_clv WHERE user_id=? ORDER BY at", (int(user_id),))]
        if rows:
            out["closing_prices_of_your_bets"] = rows
    if "gift_codes" in have:
        rows = [dict(r) for r in conn.execute("SELECT code, created_at, redeemed_by IS NOT NULL AS redeemed "
                                              "FROM gift_codes WHERE user_id=? ORDER BY created_at", (int(user_id),))]
        if rows:
            out["gifts_bought"] = rows
    if "trivia_answers" in have:
        rows = [dict(r) for r in conn.execute("SELECT room, qkey, pick, at FROM trivia_answers "
                                              "WHERE user_id=? ORDER BY at", (int(user_id),))]
        if rows:
            out["trivia_answers"] = rows
    # A passkey's name and dates; its public key and id stay out, like the
    # links below (they are for checking a sign-in, not anybody's data).
    if "passkeys" in have:
        rows = [dict(r) for r in conn.execute("SELECT name, created_at, last_used FROM passkeys "
                                              "WHERE user_id=? ORDER BY created_at", (int(user_id),))]
        if rows:
            out["passkeys"] = rows
    # The two links exist or not; their values are keys, not data, and are
    # never exported (a copy of the file would open the calendar).
    for table, label in (("calendar_links", "calendar_link_made"), ("widget_links", "iphone_widget_on_since")):
        if table in have:
            row = conn.execute(f"SELECT made FROM {table} WHERE user_id=?", (int(user_id),)).fetchone()
            if row:
                out[label] = row[0]
    return out


# --- the owner's hand-made reset link ----------------------------------------
def _cli(argv=None) -> int:
    """``python3 -m engine.accounts reset-link someone@example.com``

    For the days email is not switched on (docs/EMAIL.md): somebody writes
    to support saying they are locked out, and this prints a one-hour,
    one-use link for that account. SEND IT ONLY TO THE ACCOUNT'S OWN
    ADDRESS, never to whichever address the request came from: a "From"
    line is easy to fake, and the link is the account.
    """
    import argparse
    p = argparse.ArgumentParser(prog="python3 -m engine.accounts")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("reset-link", help="print a one-hour reset link for an account")
    r.add_argument("email")
    a = p.parse_args(argv)
    conn = connect()
    try:
        e = normalize_email(a.email)
        token = start_reset(conn, e)
    finally:
        conn.close()
    if not token:
        print(f"No link: there is no account for {e}, or it already has "
              f"{RESET_PER_HOUR} unused links from the last hour.")
        return 1
    print(f"Reset link for {e} (works once, for {RESET_TTL // 60} minutes):\n")
    print(f"  {reset_link(token)}\n")
    print(f"Email it to {e} and nowhere else.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
