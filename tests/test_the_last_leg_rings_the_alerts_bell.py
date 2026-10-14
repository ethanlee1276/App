"""A saved slip down to its last leg rings the Alerts bell too.

Ethan, 2026-10-14, "do 1-11", to the call "The last-leg alert on the
Alerts bell too?": yes.

The box's slip watch (engine/slipwatch) notes a saved slip's last leg once.
Until now that showed on the Live tab (a card and a buzz) and, for a member
who asked, by email. Now the Alerts page leads with it and its badge counts
it, until the slip settles: `/api/alerts/me` carries it as a row of the
shape the page already draws, so the phone needs no new code.

Every test runs on a throwaway accounts database and the tracker test's own
synthetic board and scoreboard; nothing reads the box's files or the network.

    python3 tests/test_the_last_leg_rings_the_alerts_bell.py
"""

import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_DIR = tempfile.mkdtemp()
os.environ["QB_ACCOUNTS_DB"] = os.path.join(_DIR, "accounts.db")
os.environ["QB_MODELS_DIR"] = os.path.join(_DIR, "models")
os.environ["QB_LIKELY_CAL"] = os.path.join(_DIR, "likely_calibration.json")
os.environ["QB_SITE_URL"] = "https://qellysbook.example"

from engine import accounts as A                                  # noqa: E402
from engine import alerts as AL                                   # noqa: E402
from engine import sliplive as SL                                 # noqa: E402
from engine import slipwatch as SW                                # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "_tracktests", ROOT / "tests" / "test_a_graded_slip_says_what_to_do_next.py")
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)

GOOD = "correct horse battery"
NOW = 1_760_000_000.0


def _one_left(id_):
    return {"id": id_, "book": "DraftKings", "sport": "NFL", "date": "2026-10-18",
            "desc": "2-leg parlay: LA moneyline + KC moneyline", "stake": 20, "odds": 170,
            "result": "pending", "src": "slip", "slip_key": f"k{id_}",
            "legs": [dict(T._ml("LA", -140), game="BUF @ LA"), dict(T._ml("KC", -180), game="DEN @ KC")]}


def _member(email, slips):
    conn = A.connect()
    try:
        code, out = A.create_user(conn, email, GOOD, confirmed=True)
        assert code == 200, out
        A.save_sections(conn, out["id"], {"mybets": {"ts": 1, "data": {"rows": slips, "deleted": []}}})
        return out["id"]
    finally:
        conn.close()


def _noted(uid, now=NOW):
    """The box's pass on this member: LA final, KC to come — one leg left."""
    conn = A.connect()
    try:
        rows = [r for r in SW.pending_slips(conn) if r["user_id"] == uid]
        live = SL.Live({"nfl": {}}, fast_dir=T._scores(first_state="final"))
        out = SW.sweep(conn, T.GAMES, live, rows=rows, send=lambda *a: None, now=now,
                       site="https://qellysbook.example", log=lambda *_: None)
        assert out["noted"] == 1, out
    finally:
        conn.close()


EVENT = {"id": "e1", "ts": "2001-01-01T00:00:00", "sport": "nfl", "kind": "line_move",
         "player": "Ja'Marr Chase", "edge": 7.0}


def _me(uid, paid=True, events=(EVENT,)):
    """GET /api/alerts/me through the server's own handler."""
    import server
    conn = A.connect()
    try:
        token = A.start_session(conn, uid)
    finally:
        conn.close()
    h = object.__new__(server.Handler)
    sent = []
    h._send = lambda code, body, ext=".json", headers=None: sent.append((code, body, ext))
    h._cookie = lambda name: token
    h._account = lambda conn: A.session_user(conn, token)
    h._entitled = lambda conn, who: paid
    h._alerts_feed = lambda conn, who, paid=None: list(events) if paid in (None, True) else []
    old = os.environ.get("QB_PAYWALL")
    os.environ["QB_PAYWALL"] = "1"
    try:
        h._alerts_get("me")
    finally:
        if old is None:
            os.environ.pop("QB_PAYWALL", None)
        else:
            os.environ["QB_PAYWALL"] = old
    assert sent[-1][0] == 200, sent[-1]
    return json.loads(sent[-1][1])


def test_the_last_leg_leads_the_alerts_and_counts_on_the_bell():
    uid = _member("bell@example.com", [_one_left("1760000000701")])
    conn = A.connect()
    try:
        AL.add_watch(conn, uid, "player", "Ja'Marr Chase")
    finally:
        conn.close()
    _noted(uid)
    d = _me(uid)
    first = d["fired"][0]
    assert first["kind"] == "last_leg" and first["player"] == "Last leg", first
    assert first["label"] == "2-leg parlay: LA moneyline + KC moneyline (DraftKings)", first
    assert first["why"] == ["KC moneyline decides it", SW.BELL_NEXT], first
    assert d["fired"][1]["player"] == "Ja'Marr Chase", "the member's watches follow it"
    assert d["unseen"] == 2, "the badge counts it with the watch that fired"
    assert d["newest"] == first["ts"] > EVENT["ts"]


def test_seen_clears_it_from_the_badge_and_keeps_it_on_the_page():
    uid = _member("seen@example.com", [_one_left("1760000000702")])
    _noted(uid)
    d = _me(uid)
    assert d["unseen"] == 1
    conn = A.connect()
    try:
        AL.mark_seen(conn, uid, d["newest"])
    finally:
        conn.close()
    again = _me(uid)
    assert again["unseen"] == 0 and again["fired"][0]["kind"] == "last_leg"


def test_a_settled_or_deleted_slip_leaves_the_bell():
    slip = _one_left("1760000000703")
    uid = _member("done@example.com", [slip])
    _noted(uid)
    assert _me(uid)["fired"][0]["kind"] == "last_leg"
    conn = A.connect()
    try:
        A.save_sections(conn, uid, {"mybets": {"ts": 2, "data": {"rows": [dict(slip, result="win")],
                                                                  "deleted": []}}})
    finally:
        conn.close()
    d = _me(uid)
    assert not [r for r in d["fired"] if r["kind"] == "last_leg"] and d["unseen"] == 0, d
    conn = A.connect()
    try:
        A.save_sections(conn, uid, {"mybets": {"ts": 3, "data": {"rows": [], "deleted": []}}})
    finally:
        conn.close()
    assert not [r for r in _me(uid)["fired"] if r["kind"] == "last_leg"]


def test_behind_the_wall_like_the_live_tab_that_follows_it():
    uid = _member("locked@example.com", [_one_left("1760000000704")])
    _noted(uid)
    d = _me(uid, paid=False)
    assert d["fired"] == [] and d["unseen"] == 0, d


def test_one_members_slip_rings_only_their_bell():
    a = _member("mine@example.com", [_one_left("1760000000705")])
    b = _member("theirs@example.com", [_one_left("1760000000706")])
    _noted(a)
    assert _me(a)["fired"][0]["kind"] == "last_leg"
    assert not [r for r in _me(b)["fired"] if r["kind"] == "last_leg"]


def test_an_alert_noted_before_the_leg_was_kept_still_reads():
    """Rows noted before 2026-10-14 have no leg: the bell says one leg decides it."""
    uid = _member("old@example.com", [_one_left("1760000000707")])
    conn = A.connect()
    try:
        SW.ensure_tables(conn)
        conn.execute("INSERT INTO slip_alerts (user_id, bet_id, fired_at, mailed) VALUES (?,?,?,0)",
                     (uid, "1760000000707", NOW))
        conn.commit()
        rows = SW.bell_rows(conn, uid)
    finally:
        conn.close()
    assert rows and rows[0]["why"][0] == "one leg decides it", rows


def test_the_old_table_gains_the_leg_column():
    db = Path(tempfile.mkdtemp()) / "old.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE slip_alerts (user_id INTEGER NOT NULL, bet_id TEXT NOT NULL, "
                 "fired_at REAL NOT NULL, mailed INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (user_id, bet_id))")
    conn.execute("INSERT INTO slip_alerts VALUES (1, 'x', 1.0, 1)")
    conn.commit()
    SW.ensure_tables(conn)
    SW.ensure_tables(conn)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(slip_alerts)")]
    assert "leg" in cols and conn.execute("SELECT COUNT(*) FROM slip_alerts").fetchone()[0] == 1
    conn.close()


def test_the_page_draws_it_with_the_code_it_already_has():
    """The row carries exactly what the Alerts page's own `firedHTML` reads,
    and the badge reads `unseen` — no new code on the phone."""
    src = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    i = src.index("function firedHTML(d)")
    body = src[i:src.index("\nfunction ", i + 1)]
    for key in ("e.player", "e.label", "e.why", "e.ts", "e.kind"):
        assert key in body, key
    assert "alertBadge((_alertsCache || {}).unseen || 0)" in src
    assert 'alertsPost("seen", { ts: d.newest })' in src


def test_the_runbook_says_so():
    doc = (ROOT / "docs" / "WHEN_YOU_ARE_HOME.md").read_text(encoding="utf-8")
    assert "rings the Alerts bell" in doc


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
