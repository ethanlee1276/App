"""A saved slip settles in My Bets off the box score with the Live tab
closed: the box's slip watch writes it, by the page's own rules.

Ethan, 2026-10-14, "do 1-11", to the call "Saved slips settled by the
server? A slip saved to My Bets settles while someone has the Live tab
open; the server's pass could settle it instead": yes.

Every test runs on a throwaway accounts database and the tracker test's
own synthetic board and scoreboard; nothing reads the box's files or the
network.

    python3 tests/test_saved_slips_settle_on_the_server.py
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_DIR = tempfile.mkdtemp()
os.environ["QB_ACCOUNTS_DB"] = os.path.join(_DIR, "accounts.db")
os.environ["QB_MODELS_DIR"] = os.path.join(_DIR, "models")
os.environ["QB_LIKELY_CAL"] = os.path.join(_DIR, "likely_calibration.json")
os.environ["QB_SITE_URL"] = "https://qellysbook.example"

from engine import accounts as A                                  # noqa: E402
from engine import sliplive as SL                                 # noqa: E402
from engine import slipwatch as SW                                # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "_tracktests", ROOT / "tests" / "test_a_graded_slip_says_what_to_do_next.py")
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)

GOOD = "correct horse battery"
NOW = 1_760_000_000.0
SLIP_JS = ROOT / "web" / "js" / "slip.js"


def _slip(id_, legs, odds=170, stake=20, **kw):
    b = {"id": id_, "book": "DraftKings", "sport": "NFL", "date": "2026-10-18",
         "desc": f"slip {id_}", "stake": stake, "odds": odds, "result": "pending",
         "src": "slip", "slip_key": f"k{id_}", "legs": legs}
    b.update(kw)
    return b


def _la(odds=-140):
    return dict(T._ml("LA", odds), game="BUF @ LA")


def _buf(odds=120):
    return dict(T._ml("BUF", odds), game="BUF @ LA")


def _kc(odds=-180):
    return dict(T._ml("KC", odds), game="DEN @ KC")


def _final(la=24, buf=20, kc=27, den=20):
    """Both games over: LA hosts BUF, KC hosts DEN."""
    return SL.Live({"nfl": {}}, fast_dir=T._fast({"live_nfl.json": {"games": [
        {"event_id": "1", "home": "LA", "away": "BUF",
         "live": {"state": "final", "home_score": la, "away_score": buf, "period": 4, "clock": "0:00"}},
        {"event_id": "2", "home": "KC", "away": "DEN",
         "live": {"state": "final", "home_score": kc, "away_score": den, "period": 4, "clock": "0:00"}}]}}))


def _member(email, slips):
    conn = A.connect()
    try:
        code, out = A.create_user(conn, email, GOOD, confirmed=True)
        assert code == 200, out
        A.save_sections(conn, out["id"], {"mybets": {"ts": 1, "data": {"rows": slips, "deleted": []}}})
        return out["id"]
    finally:
        conn.close()


def _book(uid):
    conn = A.connect()
    try:
        sec = A.get_sections(conn, uid)["mybets"]
        return sec, {b["id"]: b for b in sec["data"]["rows"]}
    finally:
        conn.close()


def _sweep(uid, live, log=None):
    conn = A.connect()
    try:
        rows = [r for r in SW.pending_slips(conn) if r["user_id"] == uid]
        return SW.sweep(conn, T.GAMES, live, rows=rows, send=lambda *a: None, now=NOW,
                        site="https://qellysbook.example", log=log or (lambda *_: None))
    finally:
        conn.close()


BY_HAND = {"id": "9000", "book": "Caesars", "desc": "Rams -3", "stake": 10, "odds": -110, "result": "pending"}


# ---- the rules -------------------------------------------------------------------
def _card(status, won=0, push=0, legs=()):
    return {"now": {"status": status, "won": won, "push": push}, "legs": list(legs)}


def _leg(result, odds):
    return {"odds": odds, "live": {"result": result}}


CASES = [
    ("lost", _card("lost"), {"odds": 170}),
    ("won", _card("won", won=2), {"odds": 170}),
    ("all pushed", _card("won", push=2, legs=[_leg("push", -140), _leg("push", -180)]), {"odds": 170}),
    ("won, a leg pushed", _card("won", won=1, push=1, legs=[_leg("push", -140), _leg("won", -180)]),
     {"odds": 170}),
    ("won, a plus-money leg pushed", _card("won", won=1, push=1, legs=[_leg("push", 250), _leg("won", 110)]),
     {"odds": 600}),
    ("won, the pushed leg's price unknown", _card("won", won=1, push=1, legs=[_leg("push", None), _leg("won", -180)]),
     {"odds": 170}),
    ("won, the ticket's price unknown", _card("won", won=1, push=1, legs=[_leg("push", -140), _leg("won", -180)]),
     {"odds": None}),
    ("open", _card("open"), {"odds": 170}),
    ("not started", {"now": None, "legs": []}, {"odds": 170}),
    ("already settled", _card("won", won=2), {"odds": 170, "result": "loss"}),
]


def test_each_way_a_ticket_settles_is_the_pages_own():
    got = {name: SW.settled(dict({"result": "pending"}, **bet), card) for name, card, bet in CASES}
    assert got["lost"] == {"result": "loss"}
    assert got["won"] == {"result": "win"}
    assert got["all pushed"] == {"result": "push"}
    assert got["won, a leg pushed"] == {"result": "win", "paid_odds": -174}, \
        "+170 without a -140 leg: 2.7 / 1.714 = 1.575, -174"
    assert got["won, a plus-money leg pushed"] == {"result": "win", "paid_odds": 100}, "7.0 / 3.5 = 2.0, +100"
    for name in ("won, the pushed leg's price unknown", "won, the ticket's price unknown", "open",
                 "not started", "already settled"):
        assert got[name] is None, (name, got[name])


def _node(script):
    node = shutil.which("node")
    if not node:
        print("      (skipped: no Node)")
        return None
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1200:]
    return out.stdout


def test_the_server_and_the_page_settle_every_case_alike():
    """The page's own `settleOne` (web/js/slip.js), run on the same tickets."""
    bets = [dict({"result": "pending", "src": "slip"}, **bet) for _n, _c, bet in CASES]
    cards = [card for _n, card, _b in CASES]
    out = _node("const vm = require('vm'); const fs = require('fs');"
                "const ctx = { window: {} }; vm.createContext(ctx);"
                f"vm.runInContext(fs.readFileSync({json.dumps(str(SLIP_JS))}, 'utf8'), ctx);"
                f"const bets = {json.dumps(bets)}; const cards = {json.dumps(cards)};"
                "bets.forEach((b, i) => ctx.window.QBSlip.settleOne(b, cards[i]));"
                "process.stdout.write(JSON.stringify(bets));")
    if out is None:
        return
    for (name, card, bet), page in zip(CASES, json.loads(out)):
        ours = SW.settled(dict({"result": "pending"}, **bet), card)
        if page["result"] == bet.get("result", "pending") and page.get("settled_by") != "box":
            assert ours is None, (name, ours, page)
            continue
        assert ours is not None, (name, page)
        assert page["result"] == ours["result"] and page.get("paid_odds") == ours.get("paid_odds"), (name, page, ours)


# ---- the box writes it --------------------------------------------------------------
def test_the_box_settles_saved_slips_with_the_live_tab_closed():
    won = _slip("1760000000101", [_la(), _kc()])
    lost = _slip("1760000000102", [_buf(), _kc()], odds=350)
    done = _slip("1760000000103", [_la(), _kc()], result="win", settled_by="box", settled_at="x")
    uid = _member("won@example.com", [won, lost, BY_HAND, done])
    said = []
    out = _sweep(uid, _final(), log=said.append)
    assert out["settled"] == 2 and out["slips"] == 2, out
    sec, book = _book(uid)
    assert book[won["id"]]["result"] == "win" and book[lost["id"]]["result"] == "loss"
    for b in (book[won["id"]], book[lost["id"]]):
        assert b["settled_by"] == "box" and b["settled_at"] == "2025-10-09T08:53:20.000Z", b
        assert b["legs"] == (won if b["id"] == won["id"] else lost)["legs"], "the slip itself unchanged"
        assert "paid_odds" not in b
    assert book["9000"] == BY_HAND, "a bet logged by hand is never touched"
    assert book[done["id"]] == done, "a settled slip is never touched"
    assert sec["ts"] == 1, "the stamp is the sync's to move"
    assert any("2 saved slip(s) settled in My Bets off the box score" in s for s in said), said
    assert _sweep(uid, _final())["settled"] == 0, "settled once"


def test_a_pushed_leg_is_paid_without_it_or_left_for_the_member():
    paid = _slip("1760000000201", [_la(), _kc()])
    unknown = _slip("1760000000202", [dict(_la(), odds=None), _kc()])
    both = _slip("1760000000203", [_la(), _kc()])
    uid = _member("push@example.com", [paid, unknown])
    assert _sweep(uid, _final(la=20, buf=20))["settled"] == 1
    _sec, book = _book(uid)
    assert book[paid["id"]]["result"] == "win" and book[paid["id"]]["paid_odds"] == -174
    assert book[unknown["id"]]["result"] == "pending" and "settled_by" not in book[unknown["id"]], \
        "won with a pushed leg whose price is not known: the member sets it, as the page says"
    uid2 = _member("pushes@example.com", [both])
    assert _sweep(uid2, _final(la=20, buf=20, kc=17, den=17))["settled"] == 1
    assert _book(uid2)[1][both["id"]]["result"] == "push"


def test_an_open_slip_stays_open_and_still_gets_its_alert():
    left = _slip("1760000000301", [_la(), _kc()])
    uid = _member("open@example.com", [left])
    out = _sweep(uid, SL.Live({"nfl": {}}, fast_dir=T._scores(first_state="final")))
    assert out["settled"] == 0 and out["noted"] == 1, out
    assert _book(uid)[1][left["id"]]["result"] == "pending"
    # The game ends: the alerted slip is still graded, and settles.
    assert _sweep(uid, _final())["settled"] == 1
    assert _book(uid)[1][left["id"]]["result"] == "win"


def test_the_pages_next_sync_adopts_it_and_a_stale_copy_never_unsettles_it():
    import server as S
    slip = _slip("1760000000401", [_la(), _kc()])
    uid = _member("sync@example.com", [slip])
    _sweep(uid, _final())
    conn = A.connect()
    try:
        stored = A.get_sections(conn, uid)
    finally:
        conn.close()
    phone = {"mybets": {"ts": 5_000, "data": {"rows": [slip], "deleted": []}}}
    merged = S.merge_sections(stored, phone)["mybets"]
    row = next(r for r in merged["data"]["rows"] if r["id"] == slip["id"])
    assert row["result"] == "win" and row["settled_by"] == "box", "the phone's pending copy never un-settles it"
    assert merged["ts"] > 5_000, "and the stamp moves past the phone's, so the phone adopts the book"


def test_one_writer_keeps_the_sync_and_the_settle_from_losing_each_other():
    """The sync reads, the box settles meanwhile, the sync writes its merge.
    With one lock the box waits for the sync's write and settles on top of
    it: both the phone's new bet and the settle survive."""
    import server as S
    slip = _slip("1760000000501", [_la(), _kc()])
    uid = _member("race@example.com", [slip])
    new = {"id": "1760000000599", "book": "FanDuel", "desc": "Bills ML", "stake": 5, "odds": 120,
           "result": "pending"}
    errors = []

    def box():
        c2 = A.connect()
        try:
            SW.write_settles(c2, uid, {slip["id"]: {"result": "win"}}, "2026-10-18T23:00:00.000Z")
        except Exception as exc:                                  # noqa: BLE001
            errors.append(exc)
        finally:
            c2.close()
    c1 = A.connect()
    try:
        with A.one_writer(c1):
            stored = A.get_sections(c1, uid)
            t = threading.Thread(target=box)
            t.start()
            time.sleep(0.4)
            assert t.is_alive(), "the box waits for the sync's write"
            phone = {"mybets": {"ts": 9_000, "data": {"rows": [slip, new], "deleted": []}}}
            A.save_sections(c1, uid, S.merge_sections(stored, phone))
        t.join(15)
    finally:
        c1.close()
    assert not errors, errors
    _sec, book = _book(uid)
    assert book[new["id"]]["result"] == "pending", "the phone's new bet survives"
    assert book[slip["id"]]["result"] == "win", "and so does the settle"


def test_the_sync_takes_the_same_lock():
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    i = src.index('            if path == "data":\n                sections = body.get("sections")')
    body = src[i:src.index('if path == "digest":', i)]
    assert "with A.one_writer(conn):" in body
    assert body.index("with A.one_writer(conn):") < body.index("A.get_sections(") < body.index("A.save_sections(")
    w = (ROOT / "engine" / "slipwatch.py").read_text(encoding="utf-8")
    ws = w[w.index("def write_settles("):w.index("\ndef ", w.index("def write_settles(") + 1)]
    assert "with A.one_writer(conn):" in ws


def test_the_runbook_says_so():
    doc = (ROOT / "docs" / "WHEN_YOU_ARE_HOME.md").read_text(encoding="utf-8")
    assert "settled in My Bets off the box score" in doc


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
