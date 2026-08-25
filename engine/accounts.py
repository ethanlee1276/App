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

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from pathlib import Path

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
        dk = hashlib.scrypt(str(password).encode("utf-8"),
                            salt=bytes.fromhex(salt_hex),
                            n=int(n), r=int(r), p=int(p),
                            dklen=len(want) // 2, maxmem=SCRYPT_MAXMEM)
    except (ValueError, TypeError, MemoryError):
        return False
    return hmac.compare_digest(dk.hex(), want)


#: Burned when the email does not exist, so a login against an unknown
#: address costs the same as one against a known address. Built once at
#: import so the cost is the scrypt call and not the salt generation.
_DUMMY = hash_password("account-enumeration-is-a-real-attack")


def _equalize(password: str) -> None:
    verify_password(_DUMMY, password)


# --- storage -----------------------------------------------------------------
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
                      ("terms_accepted_at", "REAL")):
        if col not in have:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} {decl}")


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
    return 200, {"id": int(cur.lastrowid), "email": e}


def _throttled(key: str) -> int:
    hits = [t for t in _fails.get(key, []) if time.time() - t < LOCKOUT_S]
    _fails[key] = hits
    if len(hits) < MAX_FAILS:
        return 0
    return int(LOCKOUT_S - (time.time() - hits[0])) + 1


def _note_fail(key: str) -> None:
    _fails.setdefault(key, []).append(time.time())
    if len(_fails) > 4096:                       # bounded: this is memory
        for k in list(_fails)[:1024]:
            _fails.pop(k, None)


def authenticate(conn, email, password) -> tuple[int, dict]:
    """``(status, body)``. Never says which half was wrong.

    "No such account" and "wrong password" are the same message on
    purpose: told apart, they turn the login form into a way to check
    whether an address is registered here.
    """
    e = normalize_email(email)
    wait = _throttled(e)
    if wait:
        return 429, {"error": f"Too many attempts. Try again in "
                              f"{max(1, wait // 60)} minute(s)."}
    row = conn.execute("SELECT id, verifier FROM users WHERE email=?",
                       (e,)).fetchone()
    if row is None:
        _equalize(str(password or ""))
        _note_fail(e)
        return 403, {"error": "Wrong email or password."}
    if not verify_password(row["verifier"], str(password or "")):
        _note_fail(e)
        return 403, {"error": "Wrong email or password."}
    _fails.pop(e, None)
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
    conn.commit()
    return 200, {"ok": True}


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
    if "subscriptions" in have:
        conn.execute("DELETE FROM subscriptions WHERE user_id=?", (int(user_id),))
    # The streak game's tables (engine/streak.py) and tail-or-fade's
    # (engine/tailfade.py) — same posture as `subscriptions`: created by
    # another module, so their absence is normal, and their presence
    # must not outlive the account.
    for table in ("streak_picks", "streak_state", "tf_calls"):
        if table in have:
            conn.execute(f"DELETE FROM {table} WHERE user_id=?",
                         (int(user_id),))
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
    return out
