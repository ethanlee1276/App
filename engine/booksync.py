"""Bets pulled from the user's own sportsbook, turned into rows we keep.

Ethan, 2026-08-23: *"We need to keep working on how users can seamlessly
sync there bets and shit on the site and have it automatically sync there
bets every time they log on the app. With juice reel, you only have to
log onto your sports book once then every time you log onto the app after
that it automatically syncs the bets from those accounts."*

WHAT THIS FILE IS AND IS NOT
----------------------------
It is the part of that feature that does not depend on which aggregator
we buy: taking a list of wagers from somewhere else and folding it into
a book the user has been keeping by hand, repeatedly, without ever
double-counting one or overwriting a correction they made.

The fetching lives in `engine/sharpsports.py`. This file never makes a
request and never sees a credential.

THE HARD PART IS NOT THE FETCH, IT IS THE SECOND SYNC
-----------------------------------------------------
The first import into an empty book is trivial. Every import after that
runs against a book that already contains:

  * rows this importer wrote last time, which must be UPDATED (a pending
    bet has since graded) and not appended again;
  * rows the user typed by hand for the very same wager, because they
    logged it on their phone before the sync ran — a duplicate here is
    worse than a missing bet, because it silently doubles their staked
    total and halves their apparent ROI;
  * rows the user EDITED after an import, which must survive the next
    one. A sync that overwrites a human correction teaches people not to
    correct anything.

`web/js/app.js` already dedupes by `bet_sig` — date|book|desc|stake|odds
— and that is the right key for two devices sharing one typed book. It
is the wrong key here, because `desc` is the one field a human and a
sportsbook will never write the same way:

    typed by the user   "Judge o1.5 TB"
    from the book       "Aaron Judge Over 1.5 Total Bases"

So an imported row carries the book's own slip id, and matching happens
in two tiers: the id when we have seen the slip before, and an
ACCOUNTING match when we have not. Date, book, stake and price are
facts both sides agree on; the words are not.
"""

from __future__ import annotations

#: Marks a row this importer wrote. The site shows it as synced rather
#: than typed, and `--mybets-audit` can tell the two apart.
SRC_PREFIX = "book:"

#: SharpSports' own status vocabulary, mapped to the three words the My
#: Bets page understands. Anything unrecognised stays pending rather
#: than being guessed into a win or a loss — an unknown status is a bet
#: we do not know the result of, which is exactly what pending means.
STATUS = {
    "pending": "pending",
    "open": "pending",
    "won": "won",
    "win": "won",
    "lost": "lost",
    "loss": "lost",
    "lose": "lost",
    "push": "push",
    "refunded": "push",
    "void": "push",
    "voided": "push",
    "cancelled": "push",
    "canceled": "push",
    "cashed_out": "cashed out",
    "cashedout": "cashed out",
}

#: Results that mean "this bet is finished". A finished row must never be
#: pushed back to pending by a later sync — see `_prefer`.
SETTLED = ("won", "lost", "push", "cashed out")


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and f not in (float("inf"), float("-inf")) else None


def _money(v):
    """Stake or payout, rounded to the cent the book actually charged."""
    f = _num(v)
    return None if f is None else round(f, 2)


def _date_of(stamp) -> str:
    """`2026-08-23` from an ISO timestamp, or "" if there is not one.

    The DAY, not the instant. My Bets is a daily book and the user's own
    rows carry a date; keeping the time would make every imported row
    fail an accounting match against the row they typed.
    """
    s = str(stamp or "").strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    return ""


def normalize(slip: dict, book: str = "") -> dict | None:
    """One SharpSports BetSlip as a My Bets row, or None if unusable.

    FIELD NAMES ARE THEIRS, not ours, and they are the documented ones:
    `id`, `status`, `atRisk`, `toWin`, `payout`, `placedAt`, `gradedAt`,
    `oddsAmerican` and `bookDescription`.

    `bookDescription` is the fallback for the words on purpose. Their
    own guidance is that the accounting attributes and bookDescription
    are always present while the structured breakdown may not be, so a
    mapper that insists on `event`/`market`/`selection` drops exactly the
    bets that are hardest to reconstruct by hand. A row with a clumsy
    description and the right money in it is worth far more to a bettor
    than no row.
    """
    if not isinstance(slip, dict):
        return None
    stake = _money(slip.get("atRisk"))
    odds = _num(slip.get("oddsAmerican"))
    if odds is None:
        odds = _num(slip.get("slipOddsAmerican"))
    if stake is None or stake <= 0 or odds is None:
        # No money or no price is not a bet we can grade or size. Dropped
        # rather than defaulted: a zero-stake row would sit in somebody's
        # book looking like a real wager they had forgotten.
        return None
    desc = str(slip.get("bookDescription") or "").strip()
    if not desc:
        desc = _describe(slip)
    if not desc:
        return None
    status = str(slip.get("status") or "").strip().lower().replace("-", "_")
    row = {
        "book": str(book or slip.get("book") or "").strip() or "Other",
        "sport": str(slip.get("league") or slip.get("sport") or "").strip(),
        "date": _date_of(slip.get("placedAt")) or _date_of(slip.get("gradedAt")),
        "desc": desc,
        "stake": stake,
        "odds": int(round(odds)),
        "result": STATUS.get(status, "pending"),
        "ext_id": str(slip.get("id") or "").strip(),
        "src": SRC_PREFIX + (str(book or slip.get("book") or "book").lower()),
    }
    payout = _money(slip.get("payout"))
    if payout is not None:
        row["payout"] = payout
    return row if row["date"] and row["ext_id"] else None


def _describe(slip: dict) -> str:
    """Words for a slip that arrived without `bookDescription`.

    Built from whatever structured parts are present rather than from a
    fixed template, because a parlay has no single selection and a
    straight bet has no legs.
    """
    legs = slip.get("bets") if isinstance(slip.get("bets"), list) else []
    parts = []
    for leg in legs[:4]:
        if not isinstance(leg, dict):
            continue
        bit = " ".join(str(leg.get(k) or "").strip() for k in
                       ("proposition", "position", "line") if leg.get(k))
        bit = bit.strip() or str(leg.get("event") or "").strip()
        if bit:
            parts.append(bit)
    if parts:
        return (" + ".join(parts)
                + (f" (+{len(legs) - 4} more)" if len(legs) > 4 else ""))
    return str(slip.get("event") or "").strip()


def _acct_key(row: dict) -> tuple:
    """The accounting identity of a bet: what both sides agree on.

    Date, book, stake and price. NOT the description — that is the one
    field a person and a sportsbook write differently, and keying on it
    is what would put a second copy of every bet into somebody's book on
    the first sync.

    Stake to the cent and odds as an integer, because both are quoted
    exactly by the book and typed exactly by a person copying it.
    """
    return (str(row.get("date") or ""),
            str(row.get("book") or "").strip().lower(),
            _money(row.get("stake")),
            int(round(_num(row.get("odds")) or 0)))


def _prefer(existing: dict, incoming: dict) -> dict:
    """Which copy survives when the same bet arrives twice.

    THE BOOK WINS ON MONEY, THE USER WINS ON WORDS. The sportsbook is
    the authority on whether a bet won and what it paid; the user is the
    authority on what they meant to write and which sport they filed it
    under. Merging by field rather than picking a whole row is what lets
    somebody rename a bet without the next sync undoing it.

    A settled row is never returned to pending. A sync that runs while
    the book is mid-grading would otherwise un-settle a bet the user has
    already seen resolve, which reads as the site losing their money.
    """
    out = dict(existing)
    for field in ("result", "payout", "stake", "odds", "ext_id", "src"):
        if incoming.get(field) not in (None, ""):
            out[field] = incoming[field]
    if str(existing.get("result") or "pending") in SETTLED \
            and str(incoming.get("result") or "pending") == "pending":
        out["result"] = existing["result"]
    # The description and sport stay as they are IF a person put them
    # there. An imported row has no opinion worth overriding a human's.
    for field in ("desc", "sport"):
        if not str(out.get(field) or "").strip():
            out[field] = incoming.get(field, "")
    return out


def merge(rows: list, slips: list, book: str = "") -> dict:
    """Fold fetched slips into an existing book. Idempotent by design.

    Returns ``{"rows": [...], "added": n, "updated": n, "matched": n,
    "skipped": n}`` — the counts so the page can say what the sync did
    rather than silently changing a number the reader was looking at.

    `matched` is the one worth showing: it is bets the user had already
    typed that this recognised instead of duplicating.
    """
    out = [dict(r) for r in rows if isinstance(r, dict)]
    by_ext, by_acct = {}, {}
    for i, r in enumerate(out):
        ext = str(r.get("ext_id") or "").strip()
        if ext:
            by_ext[ext] = i
        # Later rows win the accounting slot only if nothing is there —
        # the first typed copy is the one the user has been looking at.
        by_acct.setdefault(_acct_key(r), i)

    added = updated = matched = skipped = 0
    for slip in slips or []:
        new = normalize(slip, book)
        if not new:
            skipped += 1
            continue
        ext = new["ext_id"]
        if ext in by_ext:
            i = by_ext[ext]
            merged = _prefer(out[i], new)
            if merged != out[i]:
                out[i] = merged
                updated += 1
            continue
        i = by_acct.get(_acct_key(new))
        if i is not None and not str(out[i].get("ext_id") or "").strip():
            # A bet the user typed themselves. Claim it rather than
            # adding a second copy, and keep their words.
            out[i] = _prefer(out[i], new)
            by_ext[ext] = i
            matched += 1
            continue
        out.append(new)
        by_ext[ext] = len(out) - 1
        by_acct.setdefault(_acct_key(new), len(out) - 1)
        added += 1
    return {"rows": out, "added": added, "updated": updated,
            "matched": matched, "skipped": skipped}
