"""Zeno's Record — Ethan's own sportsbook bets, published beside the model's.

Ethan, 2026-09-21: *"We need to implement my juice reel record on the
site as well so people can track my actual betting record from Winible
and shit. We can add a spot on the record page called "Zenos Record" it
will track all my bets on FanDuel and DraftKings and theScore Bet and
then we can make a page for "Zenos Picks" and it will sync with my
sports books and pull my bets with the line and shit and let people
tail it. This would be just for me so my record can show on the site for
everyone. no one else should be able to log in and show this data."*

A DIFFERENT KIND OF TRUTH FROM THE REST OF THE RECORD, kept in a
different place on purpose. Every other row on the Record page is a pick
the MODEL made, journaled at the price it found and graded by OUR
settler against the box score. These are bets a PERSON placed with real
money at a real book, and the book already settled them — so the result
here is the sportsbook's own, never re-graded, never re-priced. Two
records with two provenances in one table is how a public number stops
meaning anything; this is its own store (`data/zeno.db`), its own block
in `record.json`, and its own section on the page.

WHERE THE ROWS COME FROM, and what this cannot do. FanDuel, DraftKings
and theScore Bet publish no API for a customer's bet history. Juice Reel
gets it because Ethan links his sportsbook logins to Juice Reel's own
service, and this site will not hold those logins to do the same. So the
pipeline is book → Juice Reel → an export of what Juice Reel has → this
store, through `import_rows`, which is idempotent: a row imported open
and imported again settled UPDATES rather than duplicates.

OWNER-ONLY, BY CONSTRUCTION RATHER THAN BY ROLE. There is exactly one
way to write here from outside the box — a POST carrying
`QB_OWNER_TOKEN` from `/etc/qellys/env` — and there is no per-account
path at all, so "no one else should be able to log in and show this
data" is not a permission check that could be misconfigured; it is the
absence of any feature by which anyone else could. Reading is public,
which is the point.

DOLLARS, NOT UNITS. The model's books are sized in units because a unit
is a house convention. These were placed in money and the book settled
them in money; converting to units would put a number on the page that
Ethan never bet. ROI is profit over the dollars at risk, with pushes and
voids out of the denominator — the same rule the model's record uses.

A PARLAY IS ONE BET. The legs ride along as a list for the page to show;
the stake, the price and the result belong to the ticket. Counting legs
as bets is how a 5-leg loss becomes five losses and a record page starts
lying in the direction that flatters nobody.
"""

from __future__ import annotations

import csv
import datetime as _dt
import hashlib
import io
import json
import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("QB_ZENO_DB", "").strip()
               or (Path(__file__).resolve().parents[1] / "data" / "zeno.db"))

#: The books Ethan bets at, as the page names them. Anything else is kept
#: under whatever the import called it — never dropped for being unknown.
BOOKS = {
    "fanduel": "FanDuel",
    "draftkings": "DraftKings",
    "thescore": "theScore Bet",
}

#: What the book said happened to the ticket. `cashout` is a settled
#: result with its own payout, not a win or a loss.
RESULTS = ("open", "won", "lost", "push", "void", "cashout")

#: The environment variable that authorises a write from outside the box.
OWNER_TOKEN_ENV = "QB_OWNER_TOKEN"

RECENT_LIMIT = 40


# --- the store ------------------------------------------------------------
def connect(path: str | Path | None = None) -> sqlite3.Connection:
    p = Path(path or DB_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS zeno_bets (
        id          INTEGER PRIMARY KEY,
        key         TEXT NOT NULL UNIQUE,
        book        TEXT NOT NULL,
        placed_at   TEXT,
        event_at    TEXT,
        sport       TEXT,
        event       TEXT,
        market      TEXT,
        selection   TEXT NOT NULL,
        line        REAL,
        odds        INTEGER,
        stake       REAL NOT NULL,
        payout      REAL,
        result      TEXT NOT NULL DEFAULT 'open',
        legs        TEXT,
        source      TEXT NOT NULL,
        raw         TEXT,
        imported_at TEXT NOT NULL,
        settled_at  TEXT
      );
      CREATE INDEX IF NOT EXISTS zeno_result ON zeno_bets(result);
      CREATE INDEX IF NOT EXISTS zeno_placed ON zeno_bets(placed_at);
    """)
    conn.commit()
    return conn


def _now() -> str:
    return _dt.datetime.utcnow().isoformat(timespec="seconds")


def _num(x, cast=float):
    if x is None or x == "":
        return None
    try:
        s = str(x).strip().replace("$", "").replace(",", "").replace("+", "")
        return cast(float(s)) if cast is int else cast(s)
    except (TypeError, ValueError):
        return None


def _odds(x):
    """American odds from '+150', '-110', '150', '1.91' (decimal)."""
    if x is None or x == "":
        return None
    s = str(x).strip().replace(",", "")
    try:
        v = float(s)
    except ValueError:
        return None
    if s.startswith(("+", "-")) or abs(v) >= 100:
        return int(round(v))
    if v > 1.0:                      # decimal odds
        return int(round((v - 1) * 100)) if v >= 2.0 else int(round(-100 / (v - 1)))
    return None


def _result(x) -> str:
    s = str(x or "").strip().lower()
    table = {"w": "won", "win": "won", "won": "won", "winner": "won",
             "l": "lost", "loss": "lost", "lost": "lost", "lose": "lost",
             "p": "push", "push": "push", "pushed": "push", "tie": "push",
             "void": "void", "voided": "void", "cancelled": "void",
             "canceled": "void", "refund": "void", "refunded": "void",
             "cashout": "cashout", "cashed out": "cashout",
             "cash out": "cashout",
             "open": "open", "pending": "open", "unsettled": "open",
             "live": "open", "": "open"}
    return table.get(s, "open")


#: What an export might call a book, beyond its name. "DK" and "FD" are
#: how people write them; an export that abbreviates would otherwise
#: file every DraftKings ticket under a book called "dk".
BOOK_ALIASES = {"dk": "draftkings", "fd": "fanduel", "score": "thescore",
                "thescorebet": "thescore"}


def _book(x) -> str:
    s = str(x or "").strip().lower().replace(" ", "").replace("_", "")
    for k in BOOKS:
        if k in s:
            return k
    for alias, k in BOOK_ALIASES.items():
        if s == alias or (len(alias) > 2 and alias in s):
            return k
    return s or "other"


def _key(row: dict) -> str:
    """One ticket, one row — however many times it is imported."""
    ext = str(row.get("external_id") or "").strip()
    if ext:
        return f"{row['book']}:{ext}"
    # No ticket id: the ticket IS its contents. A settled re-import of the
    # same open bet keeps this key because result and payout are not in
    # it, which is what lets the re-import update rather than duplicate.
    fp = "|".join(str(row.get(k) or "").strip().lower() for k in
                  ("book", "placed_at", "selection", "odds", "stake"))
    return f"{row['book']}:h:{hashlib.sha1(fp.encode()).hexdigest()[:16]}"


def normalize(row: dict) -> dict | None:
    """One bet in the store's shape, or None if it is not a bet."""
    sel = str(row.get("selection") or row.get("bet") or "").strip()
    stake = _num(row.get("stake"))
    # A free play risked nothing; the export says so in its own column.
    actual = _num(row.get("risk_actual"))
    if actual is not None and actual >= 0 and str(row.get("risk_actual")).strip():
        stake = actual
    if not sel or stake is None or stake < 0:
        return None
    if stake == 0 and actual is None:
        return None
    legs = row.get("legs")
    if isinstance(legs, str):
        try:
            legs = json.loads(legs)
        except ValueError:
            legs = [x.strip() for x in legs.split(";") if x.strip()]
    out = {
        "book": _book(row.get("book")),
        "external_id": str(row.get("external_id") or "").strip(),
        "placed_at": str(row.get("placed_at") or "").strip() or None,
        "event_at": str(row.get("event_at") or "").strip() or None,
        "sport": str(row.get("sport") or "").strip().lower() or None,
        "event": str(row.get("event") or "").strip() or None,
        "market": str(row.get("market") or "").strip().lower() or None,
        "selection": sel,
        "line": _num(row.get("line")),
        "odds": _odds(row.get("odds")),
        "stake": round(stake, 2),
        "payout": _num(row.get("payout")),
        "result": _result(row.get("result")),
        "legs": legs if isinstance(legs, list) and legs else None,
        "settled_at": str(row.get("settled_at") or "").strip() or None,
    }
    # PROFIT ON THE ROW, PAYOUT NOT: the payout is the stake back plus the
    # signed profit. A loss's profit is negative and lands on zero.
    profit = _num(row.get("profit"))
    if out["payout"] is None and profit is not None and out["result"] != "open":
        out["payout"] = round(max(0.0, out["stake"] + profit), 2)
    # A settled ticket with no payout on the row: the result implies it.
    if out["payout"] is None:
        if out["result"] == "lost":
            out["payout"] = 0.0
        elif out["result"] in ("push", "void"):
            out["payout"] = out["stake"]
        elif out["result"] == "won" and out["odds"] is not None:
            o = out["odds"]
            win = out["stake"] * (o / 100.0 if o > 0 else 100.0 / -o)
            out["payout"] = round(out["stake"] + win, 2)
    out["key"] = _key(out)
    return out


def import_rows(conn, rows, source: str = "manual") -> dict:
    """Add or update tickets. ``{added, updated, unchanged, skipped}``.

    IDEMPOTENT ON THE TICKET. The same bet arrives open tonight and
    settled tomorrow; the second import updates result, payout and
    settled_at on the row it already has. Nothing else about a stored
    row is overwritten by a later import — the stake and price a ticket
    was placed at do not change after the fact, and a source that says
    otherwise is wrong about that ticket, not the store.
    """
    out = {"added": 0, "updated": 0, "unchanged": 0, "skipped": 0}
    now = _now()
    for raw in rows or []:
        r = normalize(raw if isinstance(raw, dict) else {})
        if r is None:
            out["skipped"] += 1
            continue
        cur = conn.execute("SELECT id, result, payout, settled_at FROM zeno_bets "
                           "WHERE key=?", (r["key"],)).fetchone()
        if cur is None:
            conn.execute(
                "INSERT INTO zeno_bets (key, book, placed_at, event_at, sport, "
                "event, market, selection, line, odds, stake, payout, result, "
                "legs, source, raw, imported_at, settled_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (r["key"], r["book"], r["placed_at"], r["event_at"], r["sport"],
                 r["event"], r["market"], r["selection"], r["line"], r["odds"],
                 r["stake"], r["payout"], r["result"],
                 json.dumps(r["legs"]) if r["legs"] else None,
                 source, json.dumps(raw, default=str), now,
                 r["settled_at"] or (now if r["result"] != "open" else None)))
            out["added"] += 1
            continue
        changed = (cur["result"] != r["result"]
                   or (r["payout"] is not None and cur["payout"] != r["payout"]))
        if changed:
            conn.execute(
                "UPDATE zeno_bets SET result=?, payout=?, settled_at=?, raw=? "
                "WHERE id=?",
                (r["result"], r["payout"],
                 r["settled_at"] or (now if r["result"] != "open" else None),
                 json.dumps(raw, default=str), cur["id"]))
            out["updated"] += 1
        else:
            out["unchanged"] += 1
    conn.commit()
    return out


# --- what the page reads ----------------------------------------------------
def _profit(r) -> float | None:
    if r["result"] == "open":
        return None
    if r["result"] in ("push", "void"):
        return 0.0
    return round(float(r["payout"] or 0.0) - float(r["stake"]), 2)


def _tally(rows) -> dict:
    t = {"settled": 0, "wins": 0, "losses": 0, "pushes": 0, "staked": 0.0,
         "returned": 0.0, "profit": 0.0, "roi": None, "open": 0,
         "open_stake": 0.0}
    for r in rows:
        if r["result"] == "open":
            t["open"] += 1
            t["open_stake"] += float(r["stake"])
            continue
        t["settled"] += 1
        if r["result"] == "won":
            t["wins"] += 1
        elif r["result"] == "lost":
            t["losses"] += 1
        elif r["result"] in ("push", "void"):
            t["pushes"] += 1
            continue                # refunded: no money at risk
        # won, lost and cashout: money was risked and the book settled it
        t["staked"] += float(r["stake"])
        t["returned"] += float(r["payout"] or 0.0)
    t["profit"] = round(t["returned"] - t["staked"], 2)
    t["roi"] = round(t["profit"] / t["staked"], 4) if t["staked"] else None
    for k in ("staked", "returned", "open_stake"):
        t[k] = round(t[k], 2)
    return t


def _row_out(r) -> dict:
    legs = None
    if r["legs"]:
        try:
            legs = json.loads(r["legs"])
        except ValueError:
            legs = None
    return {"book": r["book"], "book_name": BOOKS.get(r["book"], r["book"]),
            "placed_at": r["placed_at"], "event_at": r["event_at"],
            "sport": r["sport"], "event": r["event"], "market": r["market"],
            "selection": r["selection"], "line": r["line"], "odds": r["odds"],
            "stake": r["stake"], "payout": r["payout"], "result": r["result"],
            "profit": _profit(r), "legs": legs, "settled_at": r["settled_at"]}


def block(conn) -> dict:
    """The `zeno` block of record.json — everything the page draws."""
    rows = conn.execute(
        "SELECT * FROM zeno_bets ORDER BY COALESCE(settled_at, placed_at, "
        "imported_at) DESC, id DESC").fetchall()
    by_book: dict = {}
    by_sport: dict = {}
    for r in rows:
        by_book.setdefault(r["book"], []).append(r)
        by_sport.setdefault(r["sport"] or "other", []).append(r)
    settled = [r for r in rows if r["result"] != "open"]
    # The curve, by the day the book settled it, oldest first.
    days: dict = {}
    for r in settled:
        d = str(r["settled_at"] or r["placed_at"] or "")[:10]
        days[d] = days.get(d, 0.0) + (_profit(r) or 0.0)
    cum, curve = 0.0, []
    for d in sorted(days):
        cum += days[d]
        curve.append({"date": d, "profit": round(days[d], 2),
                      "cum": round(cum, 2)})
    open_rows = sorted((r for r in rows if r["result"] == "open"),
                       key=lambda r: (r["event_at"] or r["placed_at"] or "", r["id"]))
    last = conn.execute("SELECT MAX(imported_at) FROM zeno_bets").fetchone()[0]
    return {
        "overall": _tally(rows),
        "by_book": {b: dict(_tally(v), name=BOOKS.get(b, b))
                    for b, v in by_book.items()},
        "by_sport": {s: _tally(v) for s, v in by_sport.items()},
        "recent": [_row_out(r) for r in settled[:RECENT_LIMIT]],
        "open": [_row_out(r) for r in open_rows],
        "curve": curve,
        "books": [BOOKS.get(b, b) for b in by_book],
        "n_rows": len(rows),
        "last_import": last,
    }


def block_or_empty(path=None) -> dict:
    """For `ledger.export_json`: never raises, never fails the export.

    AND NEVER SILENT. An empty block is what a quiet day produces too,
    so a failure that returned one would be indistinguishable from
    "no tickets yet" — the exact shape tests/test_silent_failures.py
    exists to catch, and it caught this. The failure block carries
    `error`, the page draws it as unavailable rather than as nothing,
    and the export line below prints it.
    """
    try:
        conn = connect(path)
        try:
            return block(conn)
        finally:
            conn.close()
    except Exception as exc:                                  # noqa: BLE001
        print(f"  ⚠️  Zeno's record not read — {type(exc).__name__}: "
              f"{exc}")
        return {"overall": _tally([]), "by_book": {}, "by_sport": {},
                "recent": [], "open": [], "curve": [], "books": [],
                "n_rows": 0, "last_import": None,
                "error": f"{type(exc).__name__}: {exc}"}


# --- the owner's door -------------------------------------------------------
def owner_token_ok(presented) -> bool | None:
    """True/False for a presented token; None when no token is configured.

    FAILS CLOSED. No `QB_OWNER_TOKEN` in the environment means nobody
    can write, not everybody — the caller answers 503, never 200.
    """
    import hmac
    want = os.environ.get(OWNER_TOKEN_ENV, "").strip()
    if not want:
        return None
    got = str(presented or "").strip()
    return bool(got) and hmac.compare_digest(want.encode(), got.encode())


# --- getting rows in ---------------------------------------------------------
#: Header names an export might use, lower-cased, mapped onto the store's
#: fields. Juice Reel's own export is the one this is for; the list is
#: tolerant because the sample has not been seen yet, and a header it
#: does not recognise is REPORTED by `parse_csv` rather than ignored.
#: JUICE REEL'S OWN NAMES, read off a third party's parser of the same
#: export (FeeTheDeveloper/runner_sports-site, lib/juice-reel/normalize.ts)
#: before the first real file was seen: ticket fields `juice_bet_id`,
#: `sportsbook`, `books_bet_id`, `risk_amount`, `max_potential_win`,
#: `bet_result`, `amount_won_or_lost`, `odds_american`, `number_of_legs`,
#: `date_placed`, `date_settled`, `date_synced`; leg fields `bet_leg_id`,
#: `leg_type`, `bet_on`, `bet_on_spread_total_number`, `leg_sport`,
#: `leg_league`. Two of them are traps: `amount_won_or_lost` is PROFIT,
#: not the payout, and `if_freeplay_then_amount_actually_at_risk` is the
#: real stake on a free play, which is zero.
HEADERS = {
    "book": ("sportsbook", "book", "site", "operator", "sportsbook name"),
    # Juice Reel's export names the TICKET `juice_bet_id` and each LEG
    # `bet_leg_id`, one row per leg — so a three-leg parlay is three rows
    # sharing a ticket id. `group_legs` folds them back into one ticket.
    "external_id": ("id", "bet id", "ticket", "ticket id", "bet_id", "ref",
                    "juice_bet_id", "juice bet id"),
    "leg_id": ("bet_leg_id", "bet leg id", "leg id", "leg_id"),
    "placed_at": ("placed", "placed at", "date placed", "date", "bet date",
                  "timestamp", "created", "date_placed"),
    "event_at": ("event date", "game date", "start", "event time", "kickoff",
                 "event_date", "event_start", "game_date"),
    "sport": ("sport", "league", "leg_sport", "leg_league", "leg sport"),
    "event": ("event", "game", "match", "matchup", "event_name", "event name"),
    "market": ("market", "bet type", "type", "category", "leg_type", "leg type"),
    "selection": ("selection", "bet", "pick", "description", "wager name",
                  "name", "bet_on", "bet on"),
    "line": ("line", "handicap", "spread", "total",
             "bet_on_spread_total_number"),
    "odds": ("odds", "price", "american odds", "american", "odds_american",
             "odds american"),
    "stake": ("stake", "wager", "risk", "amount", "bet amount", "risked",
              "risk_amount", "risk amount"),
    # The stake that was ACTUALLY at risk, when the row says it differs —
    # Juice Reel fills this for free plays. Takes precedence over `stake`.
    "risk_actual": ("if_freeplay_then_amount_actually_at_risk",
                    "amount actually at risk", "actual risk"),
    "payout": ("payout", "return", "returned", "won amount",
               "payout amount"),
    # PROFIT, NOT PAYOUT — signed, and the stake has to be added back.
    # Mapping this onto `payout` would have scored every win at a
    # fraction of what it returned and every loss as returning nothing
    # AND losing the stake again.
    "profit": ("profit", "amount_won_or_lost", "amount won or lost",
               "net", "p&l", "pnl"),
    "result": ("result", "status", "outcome", "settled", "w/l",
               "bet_result", "bet result"),
    "settled_at": ("settled at", "settled date", "date settled", "graded",
                   "date_settled"),
    "legs": ("legs", "selections", "parlay legs"),
}

#: Columns the export carries that the store has no use for. Named so
#: they are not reported as unrecognised every import — that line is for
#: the headers that would change what gets stored.
IGNORED_HEADERS = {
    "books_bet_id", "max_potential_win", "number_of_legs", "date_synced",
    "is_odds_boosted", "clv_percent", "leg_vig", "to win",
}


def parse_csv(text: str) -> tuple[list[dict], list[str]]:
    """``(rows, unknown_headers)`` from an export's CSV text."""
    rdr = csv.DictReader(io.StringIO(text))
    fields = [f.strip() for f in (rdr.fieldnames or [])]
    lut = {}
    unknown = []
    for f in fields:
        lf = f.lower()
        hit = next((k for k, names in HEADERS.items() if lf in names), None)
        if hit and hit not in lut.values():
            lut[f] = hit
        elif lf not in IGNORED_HEADERS and not hit:
            unknown.append(f)
    rows = []
    for rec in rdr:
        rows.append({lut[k]: v for k, v in rec.items() if k in lut})
    return rows, unknown


def group_legs(rows: list[dict]) -> list[dict]:
    """One ticket per `external_id`, its legs folded into `legs`.

    A PARLAY IS ONE BET. An export with one row per leg would otherwise
    arrive as N tickets sharing an id — the store's dedupe would keep
    the first and drop the rest, which at least never triple-counts the
    stake but loses every leg but one. Rows with no id, or an id used by
    one row only, pass through untouched.
    """
    by_id: dict = {}
    order: list = []
    for r in rows:
        k = str(r.get("external_id") or "").strip()
        if not k:
            order.append(("", r))
            continue
        if k not in by_id:
            by_id[k] = []
            order.append((k, None))
        by_id[k].append(r)
    out = []
    for k, single in order:
        if single is not None:
            out.append(single)
            continue
        legs = by_id[k]
        if len(legs) == 1:
            out.append(legs[0])
            continue
        head = dict(legs[0])
        names = [str(l.get("selection") or l.get("bet") or "").strip()
                 for l in legs]
        head["legs"] = [n for n in names if n]
        head["selection"] = (f"{len(legs)}-leg parlay: "
                             + " / ".join(head["legs"])[:160])
        # The ticket's money and result are the same on every leg row —
        # the first carries them. A market of "parlay" so the page can
        # tell it from a straight.
        head["market"] = head.get("market") or "parlay"
        out.append(head)
    return out


def parse_text(text: str) -> tuple[list[dict], list[str]]:
    """JSON (a list of tickets, or {"bets": [...]}) or CSV — whichever
    the export turns out to be."""
    s = text.strip()
    if s.startswith(("[", "{")):
        data = json.loads(s)
        if isinstance(data, dict):
            data = data.get("bets") or data.get("rows") or data.get("data") or []
        return group_legs([r for r in data if isinstance(r, dict)]), []
    rows, unknown = parse_csv(s)
    return group_legs(rows), unknown


# --- CLI -------------------------------------------------------------------
def _root_trap(path=None) -> str | None:
    """The reason not to run this import as this user, or None."""
    try:
        import pwd
    except ImportError:                      # not a POSIX box: nothing to check
        return None
    if os.geteuid() != 0:
        return None
    p = Path(path or DB_PATH)
    parent = p.parent if p.parent.exists() else p.parent.parent
    try:
        owner = pwd.getpwuid(parent.stat().st_uid).pw_name
    except (OSError, KeyError):
        return None
    if owner == "root":
        return None
    return (f"  refusing to import as root: {parent} belongs to {owner}, and a "
            f"store created here as root is one the service can never write.\n"
            f"  run it as the service user instead:\n"
            f"    sudo -u {owner} python3 -m engine.zeno import <file>")


def _cli(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python3 -m engine.zeno")
    sub = ap.add_subparsers(dest="cmd")
    imp = sub.add_parser("import", help="import a Juice Reel / CSV / JSON export")
    imp.add_argument("file")
    imp.add_argument("--source", default="juicereel")
    sub.add_parser("show", help="print the record block")
    a = ap.parse_args(argv)
    if a.cmd == "import":
        # NEVER AS ROOT INTO SOMEBODY ELSE'S DIRECTORY. The service runs
        # as `qellys` under ProtectSystem=strict; a store this command
        # creates as root is one the service can read the day it is made
        # and never write again — every later import 500s and the page
        # says "could not be read". The box already carries 6,098
        # root-owned cache files from exactly this mistake. Refuse, and
        # print the command that does it right.
        problem = _root_trap()
        if problem:
            print(problem)
            return 2
        text = Path(a.file).read_text(encoding="utf-8")
        rows, unknown = parse_text(text)
        conn = connect()
        try:
            got = import_rows(conn, rows, source=a.source)
        finally:
            conn.close()
        print(f"  {got['added']} added · {got['updated']} updated · "
              f"{got['unchanged']} unchanged · {got['skipped']} skipped")
        if unknown:
            print(f"  headers not recognised (tell Claude): {unknown}")
        return 0
    if a.cmd == "show":
        conn = connect()
        try:
            print(json.dumps(block(conn), indent=1))
        finally:
            conn.close()
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
