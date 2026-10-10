"""An outside witness for the forecast chain: OpenTimestamps and a public post.

    python3 -m engine.witness status     # the anchors, newest first
    python3 -m engine.witness anchor     # stamp the chain head now (if it moved)
    python3 -m engine.witness upgrade    # fetch Bitcoin proofs for pending anchors
    python3 -m engine.witness export     # rewrite web/data/witness.json and the .ots files

Ethan, 2026-10-06: "we're not actually placing bets, but the bets can
still be tracked … and our record could be verified from recommending
those bets." Michigan has shut every prediction market, Pikkit verifies
only money placed, so the honest proof left is the one that needs no
venue: show that every pick was written down BEFORE its game and never
changed afterwards, in a way nobody has to take our word for.

The journal already has the first half (engine/ledger, audit P0-1): every
pick is sealed into `forecast_log`, a hash chain where each row's hash
covers the row and the previous hash, so editing or deleting any past
pick changes every hash after it, and the chain's HEAD commits to every
pick sealed so far. What it lacked was a witness outside this box — a
head the operator keeps beside the journal proves nothing, because
whoever can rewrite the journal can rewrite the file.

THIS IS THE WITNESS. Whenever the head moves (new picks sealed) and at
least MIN_GAP_S since the last anchor, the head is sent to the
OpenTimestamps calendars — free, no account — which fold it into a
Bitcoin transaction within a few hours. The calendar's receipt is a
pending proof; once mined, the upgraded proof names the Bitcoin block.
A block's time is set by the whole network, so the proof says: "this
exact chain head existed before block N was mined", and every pick
sealed up to that head therefore existed then too. The same head is
posted to the public channel QB_HEADS_WEBHOOK names (Discord keeps its
own timestamps), a second witness that needs no software to read.

The proofs are ordinary .ots files (web/data/ots/<head>.ots), the format
every OpenTimestamps tool reads, so a reader checks one with
`ots verify` — or any of the web verifiers — against the head printed
on the Verify page, without trusting anything we serve beyond the bytes
of the proof. The page (web/data/witness.json) lists each anchor with
its status and block, each day's picks with the anchor that covers them,
and for days whose games are done, the picks themselves.

Nothing here can change a pick: the module only READS the chain and
writes its own store (data/witness.db), the .ots files and the JSON.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
STORE = DATA / "witness.db"
OTS_DIR = ROOT / "web" / "data" / "ots"
EXPORT = ROOT / "web" / "data" / "witness.json"
#: The public calendars; the first that answers wins. Each aggregates
#: digests and commits them to Bitcoin on its own schedule (hours).
CALENDARS = ("https://a.pool.opentimestamps.org", "https://b.pool.opentimestamps.org",
             "https://a.pool.eternitywall.com", "https://ots.btc.catallaxy.com")
MAGIC = b"\x00OpenTimestamps\x00\x00Proof\x00\xbf\x89\xe2\xe8\x84\xe8\x92\x94"
OP_SHA256 = 0x08
PENDING_TAG = bytes.fromhex("83dfe30d2ef90c8e")
BITCOIN_TAG = bytes.fromhex("0588960d73d71901")
#: Unary ops and the two that carry an argument, by tag (RFC-less: the
#: python-opentimestamps serialization, which every client shares).
OPS_UNARY = {0x08: "sha256", 0x03: "ripemd160", 0x02: "sha1", 0x67: "keccak256", 0xf2: "reverse", 0xf3: "hexlify"}
OPS_BINARY = {0xf0: "append", 0xf1: "prepend"}
#: An anchor at most this often — the calendars are a public good, and
#: half an hour is finer than any claim the page makes (a pick's own
#: `lead_min` says how far before its game it was journaled).
MIN_GAP_S = 1800
#: Ask the calendar for the Bitcoin proof once a pending anchor is this old.
UPGRADE_AFTER_S = 3600
TIMEOUT_S = 10
EXPORT_DAYS = 45

SCHEMA = """
CREATE TABLE IF NOT EXISTS anchors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT, head TEXT UNIQUE, seq_to INTEGER, n INTEGER, calendar TEXT,
    status TEXT, height INTEGER, ots BLOB, upgraded_ts TEXT, posted INTEGER DEFAULT 0, note TEXT
);
"""


# ─── the OpenTimestamps wire format, the little we need ────────────────────

def varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    n, shift = 0, 0
    while True:
        b = buf[pos]
        pos += 1
        n |= (b & 0x7F) << shift
        if not b & 0x80:
            return n, pos
        shift += 7


def _read_varbytes(buf: bytes, pos: int) -> tuple[bytes, int]:
    n, pos = _read_varint(buf, pos)
    return buf[pos:pos + n], pos + n


def ots_file(digest: bytes, timestamp: bytes) -> bytes:
    """A detached .ots proof for a SHA-256 digest: the magic, the format
    version, the digest op, the digest, then the calendar's timestamp."""
    return MAGIC + varint(1) + bytes([OP_SHA256]) + digest + timestamp


def walk(timestamp: bytes) -> dict:
    """{"pending": [calendar uris], "bitcoin": [block heights], "ok": bool}
    out of a serialized timestamp — enough to say what a proof proves.
    Full verification (hashing through the ops to a block's merkle root)
    is the reader's `ots verify`; this only reads the attestations."""
    out = {"pending": [], "bitcoin": [], "ok": True}

    def item(pos: int) -> int:
        tag = timestamp[pos]
        pos += 1
        if tag == 0x00:                                     # attestation
            atag, payload_pos = timestamp[pos:pos + 8], pos + 8
            payload, pos = _read_varbytes(timestamp, payload_pos)
            if atag == PENDING_TAG:
                uri, _ = _read_varbytes(payload, 0)
                out["pending"].append(uri.decode("utf-8", "replace"))
            elif atag == BITCOIN_TAG:
                height, _ = _read_varint(payload, 0)
                out["bitcoin"].append(height)
            return pos
        if tag in OPS_BINARY:
            _arg, pos = _read_varbytes(timestamp, pos)
        elif tag not in OPS_UNARY:
            raise ValueError(f"unknown op 0x{tag:02x}")
        return stamp(pos)

    def stamp(pos: int) -> int:
        while timestamp[pos] == 0xFF:
            pos = item(pos + 1)
        return item(pos)

    try:
        stamp(0)
    except (IndexError, ValueError) as exc:
        out["ok"] = False
        out["error"] = str(exc)
    return out


# ─── the calendars ─────────────────────────────────────────────────────────

def _http(method: str, url: str, body: bytes | None = None) -> bytes:
    req = urllib.request.Request(url, data=body, method=method, headers={
        "Accept": "application/vnd.opentimestamps.v1",
        "User-Agent": "qellys-witness/1", "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        return r.read()


def stamp_digest(digest: bytes, calendars=CALENDARS, http=_http) -> tuple[str, bytes]:
    """POST the digest to the first calendar that answers; returns
    (calendar, serialized pending timestamp). Raises when none does."""
    last: Exception | None = None
    for cal in calendars:
        try:
            got = http("POST", f"{cal}/digest", digest)
            if got and walk(got)["ok"]:
                return cal, got
            last = ValueError(f"{cal}: unreadable receipt")
        except Exception as exc:                             # noqa: BLE001
            last = exc
    raise RuntimeError(f"no calendar answered: {last}")


def upgrade_digest(digest: bytes, calendar: str, http=_http) -> bytes | None:
    """The calendar's current timestamp for the digest — with the Bitcoin
    attestation once mined, None while still pending (HTTP 404)."""
    try:
        got = http("GET", f"{calendar}/timestamp/{digest.hex()}")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    return got if got and walk(got)["bitcoin"] else None


# ─── the store ─────────────────────────────────────────────────────────────

def connect(path: Path | str = STORE) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _iso(now: _dt.datetime) -> str:
    return now.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(ts: str) -> _dt.datetime:
    return _dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))


def chain_head(ledger_conn) -> tuple[str | None, int]:
    """(head hash, seq) of the forecast chain as it stands, from the
    chain itself — the LAST sealed row, which verify_forecast_log has
    already checked links to everything before it."""
    try:
        r = ledger_conn.execute("SELECT hash, seq FROM forecast_log ORDER BY seq DESC LIMIT 1").fetchone()
    except sqlite3.Error:
        return None, 0
    return (r[0], int(r[1])) if r else (None, 0)


def _write_ots(head: str, ots: bytes, out_dir: Path = OTS_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"{head}.ots"
    tmp = p.with_suffix(".ots.tmp")
    tmp.write_bytes(ots)
    os.replace(tmp, p)
    return p


def anchor(ledger_conn, store=None, now: _dt.datetime | None = None, http=_http, calendars=CALENDARS,
           post=None, min_gap_s: int = MIN_GAP_S, out_dir: Path = OTS_DIR) -> dict:
    """Stamp the current chain head if it moved and the gap has passed.
    Returns {"anchored": bool, "head", "seq_to", "why"}."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    store = store or connect()
    head, seq = chain_head(ledger_conn)
    if not head:
        return {"anchored": False, "why": "the forecast chain is empty"}
    last = store.execute("SELECT * FROM anchors ORDER BY id DESC LIMIT 1").fetchone()
    if last and last["head"] == head:
        return {"anchored": False, "head": head, "seq_to": seq, "why": "the head has not moved"}
    if last and (now - _parse(last["ts"])).total_seconds() < min_gap_s:
        return {"anchored": False, "head": head, "seq_to": seq, "why": "inside the gap"}
    try:
        cal, ts = stamp_digest(bytes.fromhex(head), calendars, http)
    except Exception as exc:                                 # noqa: BLE001
        return {"anchored": False, "head": head, "seq_to": seq, "why": f"calendars unreachable: {exc}"}
    ots = ots_file(bytes.fromhex(head), ts)
    store.execute("INSERT OR IGNORE INTO anchors (ts, head, seq_to, n, calendar, status, ots) VALUES (?,?,?,?,?,?,?)",
                  (_iso(now), head, seq, seq, cal, "pending", ots))
    store.commit()
    _write_ots(head, ots, out_dir)
    if post is None:
        post = _discord_post
    try:
        if post(f"Qellys Book witness {_iso(now)}: forecast chain through #{seq}, head {head} — "
                f"stamped on OpenTimestamps ({cal.split('//', 1)[-1]}); the Bitcoin proof follows at "
                f"qellysbook.com/#verify"):
            store.execute("UPDATE anchors SET posted=1 WHERE head=?", (head,))
            store.commit()
    except Exception:                                        # noqa: BLE001
        pass
    return {"anchored": True, "head": head, "seq_to": seq, "calendar": cal}


def upgrade_pending(store=None, now: _dt.datetime | None = None, http=_http,
                    after_s: int = UPGRADE_AFTER_S, out_dir: Path = OTS_DIR, limit: int = 20) -> int:
    """Fetch the Bitcoin proof for pending anchors old enough to have one.
    Returns how many were upgraded."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    store = store or connect()
    n = 0
    rows = store.execute("SELECT * FROM anchors WHERE status='pending' ORDER BY id").fetchall()
    for r in rows[:limit]:
        if (now - _parse(r["ts"])).total_seconds() < after_s:
            continue
        try:
            got = upgrade_digest(bytes.fromhex(r["head"]), r["calendar"], http)
        except Exception:                                    # noqa: BLE001
            continue
        if not got:
            continue
        info = walk(got)
        ots = ots_file(bytes.fromhex(r["head"]), got)
        store.execute("UPDATE anchors SET status='bitcoin', height=?, ots=?, upgraded_ts=? WHERE id=?",
                      (min(info["bitcoin"]), ots, _iso(now), r["id"]))
        store.commit()
        _write_ots(r["head"], ots, out_dir)
        n += 1
    return n


def _discord_post(content: str) -> bool:
    url = os.environ.get("QB_HEADS_WEBHOOK", "").strip()
    if not url:
        return False
    body = json.dumps({"content": content}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=TIMEOUT_S).read()
    return True


# ─── the public page's data ────────────────────────────────────────────────

def _today_et(now: _dt.datetime) -> str:
    try:
        from zoneinfo import ZoneInfo
        return now.astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    except Exception:                                        # noqa: BLE001
        return now.strftime("%Y-%m-%d")


def export_payload(ledger_conn, store=None, now: _dt.datetime | None = None, days: int = EXPORT_DAYS) -> dict:
    """What the Verify page draws. Anchors newest first; each recent day's
    sealed picks counted and tied to the first anchor that covers them;
    the picks themselves only for days whose games are over (ET), so the
    page reveals nothing a paying reader has not already seen settle."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    store = store or connect()
    anchors = [dict(r) for r in store.execute(
        "SELECT id, ts, head, seq_to, calendar, status, height, upgraded_ts, posted FROM anchors "
        "ORDER BY id DESC LIMIT 400").fetchall()]
    asc = sorted(anchors, key=lambda a: a["seq_to"])

    def cover(seq: int):
        for a in asc:
            if a["seq_to"] >= seq:
                return a
        return None

    since = (now - _dt.timedelta(days=days)).strftime("%Y-%m-%d")
    today = _today_et(now)
    try:
        rows = ledger_conn.execute(
            "SELECT seq, sealed_ts, sport, date, player, market, side, line, odds, category, lead_min "
            "FROM forecast_log WHERE date >= ? ORDER BY seq", (since,)).fetchall()
    except sqlite3.Error:
        rows = []
    by_day: dict = {}
    for r in rows:
        d = by_day.setdefault(r["date"], {"date": r["date"], "n": 0, "anchored": 0, "bitcoin": 0,
                                           "sports": {}, "picks": []})
        d["n"] += 1
        d["sports"][r["sport"]] = d["sports"].get(r["sport"], 0) + 1
        a = cover(int(r["seq"]))
        if a:
            d["anchored"] += 1
            if a["status"] == "bitcoin":
                d["bitcoin"] += 1
        if r["date"] < today:
            d["picks"].append({"seq": r["seq"], "sealed": r["sealed_ts"], "sport": r["sport"],
                               "player": r["player"], "market": r["market"], "side": r["side"],
                               "line": r["line"], "odds": r["odds"], "category": r["category"],
                               "lead_min": r["lead_min"], "anchor": a["id"] if a else None,
                               "height": (a or {}).get("height")})
    head, seq = chain_head(ledger_conn)
    return {"generated_at": _iso(now), "head": head, "seq": seq,
            "anchors": anchors, "days": sorted(by_day.values(), key=lambda d: d["date"], reverse=True),
            "how": "Each anchor is the forecast chain's head hash, stamped on OpenTimestamps and posted "
                   "publicly; the .ots file verifies with `ots verify` against that head.",
            "webhook": bool(os.environ.get("QB_HEADS_WEBHOOK", "").strip())}


def export(ledger_conn, store=None, now=None, path: Path = EXPORT) -> dict:
    payload = export_payload(ledger_conn, store, now)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")))
    os.replace(tmp, path)
    return payload


def run(ledger_conn, store=None, now=None, http=_http, post=None) -> dict:
    """The sweep's one call: anchor if due, upgrade what is ready, export."""
    store = store or connect()
    out = anchor(ledger_conn, store, now, http=http, post=post)
    out["upgraded"] = upgrade_pending(store, now, http=http)
    try:
        export(ledger_conn, store, now)
    except OSError as exc:
        out["export_error"] = str(exc)
    return out


def report(store=None, limit: int = 15) -> list[str]:
    store = store or connect()
    rows = store.execute("SELECT * FROM anchors ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    n, b = store.execute("SELECT COUNT(*), SUM(status='bitcoin') FROM anchors").fetchone()
    out = [f"witness: {n or 0} anchor(s), {b or 0} with a Bitcoin proof, "
           f"webhook {'set' if os.environ.get('QB_HEADS_WEBHOOK', '').strip() else 'NOT set'}"]
    for r in rows:
        out.append(f"  #{r['id']} {r['ts']} through forecast #{r['seq_to']} {r['head'][:16]}… "
                   f"{r['status']}{' block ' + str(r['height']) if r['height'] else ''} "
                   f"{'posted' if r['posted'] else 'not posted'}  {r['calendar']}")
    return out


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="the forecast chain's outside witness")
    ap.add_argument("cmd", choices=("status", "anchor", "upgrade", "export"))
    a = ap.parse_args(argv)
    from . import ledger as _led
    from .secrets import load_local_secrets
    load_local_secrets()
    if a.cmd == "status":
        for ln in report():
            print(ln)
        return 0
    conn = _led.connect()
    try:
        if a.cmd == "anchor":
            _led.seal_forecasts(conn)
            print(json.dumps(anchor(conn, min_gap_s=0), indent=1))
        elif a.cmd == "upgrade":
            print(f"upgraded {upgrade_pending(after_s=0)}")
        else:
            p = export(conn)
            print(f"wrote {EXPORT} — {len(p['anchors'])} anchor(s), {len(p['days'])} day(s)")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
