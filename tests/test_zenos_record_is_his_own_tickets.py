"""Zeno's Record — Ethan's real sportsbook bets, on the site, owner-only.

Ethan, 2026-09-21: *"implement my juice reel record on the site … a spot
on the record page called "Zenos Record" … a page for "Zenos Picks" …
let people tail it. This would be just for me so my record can show on
the site for everyone. no one else should be able to log in and show
this data."*

THREE THINGS THIS FILE HOLDS THE FEATURE TO.

A DIFFERENT TRUTH IN A DIFFERENT PLACE. Every other row on the Record
page is a pick the model made and OUR settler graded. These are tickets
a person placed and the BOOK settled. They live in their own store and
their own block, and nothing here may read or write the model's journal.

DOLLARS AND TICKETS. Placed in money, settled in money, shown in money.
A parlay is one ticket however many legs; a push is refunded and stays
out of the ROI denominator — the record page's own rule.

ONE DOOR, AND IT IS A SECRET, NOT A ROLE. There is no per-account write
path to build on or misconfigure. The bearer of `QB_OWNER_TOKEN` writes;
with no token set the door is 503 to everyone, never open.

Run directly:
`python3 tests/test_zenos_record_is_his_own_tickets.py`
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import zeno                                       # noqa: E402


def _store():
    return zeno.connect(Path(tempfile.mkdtemp()) / "z.db")


def _tickets():
    return [
        {"book": "FanDuel", "external_id": "A1", "placed_at": "2026-09-20T18:00",
         "sport": "nfl", "event": "LAC @ KC", "market": "spread",
         "selection": "Chiefs -3.5", "line": -3.5, "odds": "-110",
         "stake": "50", "result": "Pending"},
        {"book": "DraftKings", "external_id": "B7", "placed_at": "2026-09-19T12:00",
         "sport": "nfl", "selection": "Mahomes o275.5 pass yds", "odds": "+105",
         "stake": "25", "payout": "51.25", "result": "Won",
         "settled_at": "2026-09-19T23:00"},
        {"book": "theScore Bet", "placed_at": "2026-09-18", "sport": "mlb",
         "selection": "3-leg parlay", "odds": "+600", "stake": "10",
         "result": "Lost", "legs": "Yankees ML; Judge HR; Over 8.5"},
        {"book": "FanDuel", "external_id": "C2", "placed_at": "2026-09-18",
         "selection": "Bills ML", "odds": "-150", "stake": "30", "result": "push"},
    ]


# --- the store ------------------------------------------------------------
def test_the_same_export_twice_is_a_no_op():
    conn = _store()
    assert zeno.import_rows(conn, _tickets())["added"] == 4
    again = zeno.import_rows(conn, _tickets())
    assert again == {"added": 0, "updated": 0, "unchanged": 4, "skipped": 0}, again
    assert conn.execute("SELECT COUNT(*) FROM zeno_bets").fetchone()[0] == 4


def test_a_ticket_that_settles_later_is_updated_not_duplicated():
    """The same bet arrives open tonight and settled tomorrow."""
    conn = _store()
    rows = _tickets()
    zeno.import_rows(conn, rows)
    rows[0] = dict(rows[0], result="won", payout="95.45")
    got = zeno.import_rows(conn, rows)
    assert got["updated"] == 1 and got["added"] == 0, got
    r = conn.execute("SELECT result, payout, settled_at FROM zeno_bets "
                     "WHERE key='fanduel:A1'").fetchone()
    assert r["result"] == "won" and r["payout"] == 95.45 and r["settled_at"]


def test_a_ticket_without_an_id_still_dedupes_across_its_own_settlement():
    """No ticket id: the key is the contents that do not change when the
    book settles it — not the result or payout, or the settled re-import
    would be a second bet."""
    conn = _store()
    open_row = {"book": "thescore", "placed_at": "2026-09-18", "selection":
                "3-leg parlay", "odds": "+600", "stake": "10", "result": "open"}
    zeno.import_rows(conn, [open_row])
    zeno.import_rows(conn, [dict(open_row, result="lost", payout="0")])
    assert conn.execute("SELECT COUNT(*) FROM zeno_bets").fetchone()[0] == 1
    assert conn.execute("SELECT result FROM zeno_bets").fetchone()[0] == "lost"


def test_a_parlay_is_one_ticket_with_its_legs_along_for_the_ride():
    conn = _store()
    zeno.import_rows(conn, _tickets())
    b = zeno.block(conn)
    assert b["overall"]["losses"] == 1, b["overall"]
    parlay = next(r for r in b["recent"] if r["selection"] == "3-leg parlay")
    assert parlay["legs"] == ["Yankees ML", "Judge HR", "Over 8.5"], parlay
    assert parlay["profit"] == -10.0


def test_the_record_is_in_dollars_with_pushes_out_of_the_denominator():
    conn = _store()
    rows = _tickets()
    rows[0] = dict(rows[0], result="won", payout="95.45")
    zeno.import_rows(conn, rows)
    o = zeno.block(conn)["overall"]
    # 50 + 25 + 10 at risk; the 30 push was refunded and is not in it.
    assert o["staked"] == 85.0, o
    assert o["returned"] == 146.7, o
    assert o["profit"] == 61.7 and o["wins"] == 2 and o["losses"] == 1
    assert o["pushes"] == 1 and o["settled"] == 4
    assert abs(o["roi"] - 61.7 / 85.0) < 1e-4, o["roi"]


def test_a_won_ticket_with_no_payout_on_the_row_gets_it_from_the_price():
    r = zeno.normalize({"book": "fanduel", "selection": "x", "odds": "-150",
                        "stake": "30", "result": "won"})
    assert r["payout"] == 50.0, r          # 30 + 30 * 100/150


def test_odds_arrive_in_every_shape_a_book_prints_them():
    assert zeno._odds("+150") == 150 and zeno._odds("-110") == -110
    assert zeno._odds("150") == 150
    assert zeno._odds("1.91") == -110 and zeno._odds("2.5") == 150
    assert zeno._odds("") is None and zeno._odds("even") is None


def test_results_and_books_are_read_the_way_exports_spell_them():
    for word, want in (("W", "won"), ("Loss", "lost"), ("PUSH", "push"),
                       ("Cashed Out", "cashout"), ("Voided", "void"),
                       ("Pending", "open"), ("", "open")):
        assert zeno._result(word) == want, word
    for word, want in (("FanDuel", "fanduel"), ("DK", "draftkings"),
                       ("FD", "fanduel"), ("Caesars", "caesars"),
                       ("DraftKings Sportsbook", "draftkings"),
                       ("theScore Bet", "thescore"), ("The Score", "thescore")):
        assert zeno._book(word) == want, word


def test_a_row_that_is_not_a_bet_is_skipped_not_stored():
    conn = _store()
    got = zeno.import_rows(conn, [{"book": "fanduel", "selection": "", "stake": "5"},
                                  {"book": "fanduel", "selection": "x", "stake": "0"},
                                  "not even a dict"])
    assert got["skipped"] == 3 and got["added"] == 0, got


# --- getting an export in -------------------------------------------------
def test_a_juice_reel_shaped_csv_maps_its_headers_and_reports_the_rest():
    text = ("Sportsbook,Bet ID,Date Placed,Sport,Event,Bet Type,Selection,"
            "Odds,Wager,Payout,Result,Cool Column\n"
            "FanDuel,FD1,2026-09-20 18:00,NFL,LAC @ KC,Spread,Chiefs -3.5,"
            "-110,50,,Pending,x\n")
    rows, unknown = zeno.parse_csv(text)
    assert unknown == ["Cool Column"], unknown
    r = zeno.normalize(rows[0])
    assert r["book"] == "fanduel" and r["external_id"] == "FD1"
    assert r["selection"] == "Chiefs -3.5" and r["odds"] == -110
    assert r["stake"] == 50.0 and r["result"] == "open"


def test_a_json_export_is_read_too():
    rows, unknown = zeno.parse_text(json.dumps(
        {"bets": [{"book": "draftkings", "selection": "x", "stake": 5}]}))
    assert len(rows) == 1 and unknown == []
    rows, _u = zeno.parse_text("[{\"book\":\"fanduel\",\"selection\":\"y\",\"stake\":1}]")
    assert rows[0]["selection"] == "y"


# --- its own place --------------------------------------------------------
def test_the_store_never_touches_the_models_journal():
    """Two provenances that shared a table would make both worthless."""
    src = (ROOT / "engine" / "zeno.py").read_text(encoding="utf-8")
    assert "from .ledger" not in src and "import ledger" not in src, \
        "zeno reaches into the model's journal"
    assert "FROM bets" not in src and "INTO bets" not in src


def test_the_export_carries_the_block_and_the_paywall_never_strips_it():
    from engine import gate, ledger
    os.environ["QB_ZENO_DB"] = str(Path(tempfile.mkdtemp()) / "z.db")
    zeno.DB_PATH = Path(os.environ["QB_ZENO_DB"])
    conn = zeno.connect()
    zeno.import_rows(conn, _tickets())
    conn.close()
    lconn = ledger.connect(Path(tempfile.mkdtemp()) / "l.db")
    out = Path(tempfile.mkdtemp()) / "record.json"
    ledger.export_json(lconn, out)
    got = json.loads(out.read_text(encoding="utf-8"))["zeno"]
    assert got["overall"]["settled"] == 3 and got["overall"]["open"] == 1, got["overall"]
    assert "zeno" not in gate.PAID_KEYS
    assert "zeno" not in gate.paid_keys_for("record.json")


def test_a_missing_or_broken_store_is_an_empty_block_not_a_failed_export():
    got = zeno.block_or_empty(Path("/nonexistent/dir/z.db"))
    assert got["n_rows"] == 0 and got["overall"]["settled"] == 0, got
    # AND A CORRUPT ONE, which is a different exception. A missing path
    # raises OSError; a file that is not a database raises
    # sqlite3.DatabaseError — and a guard narrowed to the first survived
    # a mutation run because this test only ever tried the first.
    junk = Path(tempfile.mkdtemp()) / "z.db"
    junk.write_text("this is not a database", encoding="utf-8")
    got = zeno.block_or_empty(junk)
    assert got["n_rows"] == 0, got


# --- the one door ---------------------------------------------------------
def test_no_token_configured_means_closed_not_open():
    real = os.environ.pop(zeno.OWNER_TOKEN_ENV, None)
    try:
        assert zeno.owner_token_ok("anything") is None
        assert zeno.owner_token_ok("") is None
    finally:
        if real is not None:
            os.environ[zeno.OWNER_TOKEN_ENV] = real


def test_only_the_configured_token_opens_it():
    os.environ[zeno.OWNER_TOKEN_ENV] = "s3cret-token-for-test"
    try:
        assert zeno.owner_token_ok("s3cret-token-for-test") is True
        assert zeno.owner_token_ok("s3cret-token-for-tesT") is False
        assert zeno.owner_token_ok("") is False
        assert zeno.owner_token_ok(None) is False
    finally:
        del os.environ[zeno.OWNER_TOKEN_ENV]


def test_there_is_no_per_account_write_path_to_misconfigure():
    """'no one else should be able to log in and show this data' — not a
    permission check, the absence of any feature by which they could."""
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    i = src.index("def _zeno_import(self)")
    body = src[i:src.index("def _tailfade_get", i)]
    assert "self._account(" not in body, "the import consults a signed-in account"
    assert "owner_token_ok" in body
    assert "503" in body and "403" in body


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class _Site:
    """A real server over a real socket — the gate is headers and status
    codes, and a unit test of the handler would not exercise either."""

    def __init__(self, token):
        self.dir = tempfile.mkdtemp(prefix="qb-zeno-")
        self.port = _free_port()
        self.db = os.path.join(self.dir, "z.db")
        env = dict(os.environ)
        env.update({"QB_ACCOUNTS_DB": os.path.join(self.dir, "a.db"),
                    "QB_ZENO_DB": self.db, "QB_PAYWALL": "",
                    "QB_COMP_EMAILS": ""})
        env.pop(zeno.OWNER_TOKEN_ENV, None)
        if token is not None:
            env[zeno.OWNER_TOKEN_ENV] = token
        self.proc = subprocess.Popen(
            [sys.executable, "server.py", "--port", str(self.port)],
            cwd=ROOT, env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True)
        self.base = "http://127.0.0.1:%d" % self.port
        end = time.time() + 40
        while time.time() < end:
            if self.proc.poll() is not None:
                raise AssertionError("server died:\n"
                                     + (self.proc.stdout.read() or "")[:1200])
            try:
                self.call("GET", "/api/zeno")
                return
            except Exception:                                # noqa: BLE001
                time.sleep(0.25)
        raise AssertionError("server never answered")

    def call(self, method, path, body=None, headers=None):
        req = urllib.request.Request(self.base + path, method=method,
                                     data=body.encode() if body else None)
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode()

    def stop(self):
        self.proc.kill()
        self.proc.wait(timeout=10)


_CSV = ("Sportsbook,Bet ID,Date Placed,Sport,Selection,Odds,Wager,Payout,Result\n"
        "FanDuel,FD9,2026-09-20 18:00,NFL,Chiefs -3.5,-110,50,,Pending\n"
        "DraftKings,DK2,2026-09-19,NFL,Mahomes o275.5,+105,25,51.25,Won\n")


def test_over_the_wire_the_door_is_closed_without_a_token_on_the_box():
    site = _Site(token=None)
    try:
        code, body = site.call("POST", "/api/zeno/import", _CSV,
                               {"X-Owner-Token": "whatever"})
        assert code == 503, (code, body)
        code, body = site.call("GET", "/api/zeno")
        assert code == 200 and json.loads(body)["n_rows"] == 0, (code, body)
    finally:
        site.stop()


def test_over_the_wire_only_the_owner_writes_and_everyone_reads():
    site = _Site(token="owner-token-for-the-test")
    try:
        code, body = site.call("POST", "/api/zeno/import", _CSV,
                               {"X-Owner-Token": "not-it"})
        assert code == 403, (code, body)
        code, body = site.call("POST", "/api/zeno/import", _CSV)
        assert code == 403, (code, body)
        code, body = site.call("POST", "/api/zeno/import", _CSV,
                               {"X-Owner-Token": "owner-token-for-the-test",
                                "X-Zeno-Source": "juicereel"})
        assert code == 200, (code, body)
        got = json.loads(body)
        assert got["added"] == 2 and got["unknown_headers"] == [], got
        # Public read, no cookie, no token — and it is the import that
        # just landed, not the last build's file.
        code, body = site.call("GET", "/api/zeno")
        z = json.loads(body)
        assert code == 200 and z["n_rows"] == 2 and z["overall"]["open"] == 1
        assert z["open"][0]["selection"] == "Chiefs -3.5"
        # Bearer form works too, for a phone shortcut.
        code, body = site.call("POST", "/api/zeno/import", _CSV,
                               {"Authorization": "Bearer owner-token-for-the-test"})
        assert code == 200 and json.loads(body)["unchanged"] == 2, body
    finally:
        site.stop()


# --- the box ---------------------------------------------------------------
def test_the_cli_refuses_to_create_a_root_owned_store():
    """The service runs as `qellys` under ProtectSystem=strict. A store
    this command creates as root is readable the day it is made and never
    writable again: every later import 500s and the page reads "could
    not be read". The box already carries 6,098 root-owned cache files
    from exactly this mistake, so the CLI refuses and prints the right
    command rather than trusting the runbook to be read."""
    import pwd
    real_uid, real_pw = os.geteuid, pwd.getpwuid
    d = Path(tempfile.mkdtemp())
    try:
        os.geteuid = lambda: 0                     # pretend to be root
        pwd.getpwuid = lambda _u: type("P", (), {"pw_name": "qellys"})()
        why = zeno._root_trap(d / "z.db")
        assert why and "sudo -u qellys" in why, why
        assert zeno._cli(["import", str(d / "nope.csv")]) == 2
        # Root into root's own directory is fine — that is not the trap.
        pwd.getpwuid = lambda _u: type("P", (), {"pw_name": "root"})()
        assert zeno._root_trap(d / "z.db") is None
    finally:
        os.geteuid, pwd.getpwuid = real_uid, real_pw
    # And not root at all: nothing to say.
    assert zeno._root_trap(d / "z.db") is None or os.geteuid() == 0


# --- the page --------------------------------------------------------------
def _js():
    return (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")


def test_the_record_page_draws_the_card_and_the_site_has_the_page():
    src = _js()
    i = src.index("const receipts = calendar")
    assert "recZenoSection(d.zeno, scope)" in src[i:i + 600], src[i:i + 600]
    assert '"zeno"' in src[src.index("const VIEW_ORDER"):src.index("const VIEW_ORDER") + 900]
    wall = src[src.index("const WALL_OPEN"):src.index("];", src.index("const WALL_OPEN"))]
    assert '"zeno"' in wall, "the picks page is behind the paywall"
    assert 'if (name === "zeno") renderZeno();' in src
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert 'id="view-zeno"' in html and 'data-view="zeno"' in html
    assert 'id="zeno-body"' in html


def _render(kind, z, scope=""):
    import shutil
    if not shutil.which("node"):
        return None
    src = _js()
    body = src[src.index("function zenoMoney"):src.index("function recPotdSection")]
    harness = """
const MINUS="\\u2212", SPORT_META={nfl:{name:"NFL"}};
const escapeHtml=(x)=>String(x==null?"":x), icon=()=>"", american=(o)=>(o>0?"+":"")+o;
const plural=(n,w)=>n+" "+w+(n===1?"":"s");
let cache=null; const loadRecordOnce=async()=>cache;
const doc={el:{},getElementById(id){return this.el[id];}};
global.document=doc; global.navigator={clipboard:{writeText:async()=>{}}};
""" + body + """
const z=JSON.parse(process.argv[2]), kind=process.argv[3], scope=process.argv[4]||"";
if (kind==="card") process.stdout.write(recZenoSection(z, scope));
else { cache={zeno:z}; doc.el["zeno-body"]={innerHTML:"",querySelectorAll:()=>[]};
  renderZeno().then(()=>process.stdout.write(doc.el["zeno-body"].innerHTML)); }
"""
    path = os.path.join(tempfile.mkdtemp(), "r.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(harness)
    out = subprocess.run(["node", path, json.dumps(z), kind, scope],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-800:]
    return out.stdout


def _block():
    conn = _store()
    rows = _tickets()
    rows[0] = dict(rows[0], result="won", payout="95.45")
    zeno.import_rows(conn, rows)
    zeno.import_rows(conn, [{"book": "fanduel", "external_id": "OPEN1",
                             "event_at": "2026-09-21T20:15", "sport": "nfl",
                             "event": "LAC @ KC", "selection": "Chiefs -3.5",
                             "odds": "-110", "stake": "50", "result": "open"}])
    return zeno.block(conn)


def test_the_card_says_dollars_the_book_settled_and_a_parlay_once():
    got = _render("card", _block())
    if got is None:
        return
    assert "Zeno’s Record" in got
    assert "$61.70" in got and "$85.00 risked" in got, got[:600]
    assert "72.6% ROI" in got
    assert "settled by\n        the book, not by our model" in got or "settled by the book" in got.replace("\n        ", " ")
    assert got.count("3-leg parlay") == 1
    assert "Yankees ML" in got, "the legs are not shown"
    assert "u</span>" not in got, "a unit crept onto a page that is in dollars"


def test_the_card_scopes_to_a_league_and_stays_off_one_with_no_rows():
    z = _block()
    assert "NFL" in _render("card", z, "nfl")
    assert _render("card", z, "cfb") == ""


def test_the_picks_page_lists_what_is_riding_with_a_way_to_tail_it():
    got = _render("page", _block())
    if got is None:
        return
    assert "Riding now" in got and "1 open ticket" in got, got[:500]
    assert "Chiefs -3.5" in got and "LAC @ KC" in got and "-110" in got
    assert 'class="btn-ghost zeno-copy"' in got, "nothing to tail with"
    assert "Copy" in got
    assert "$50.00 at risk" in got


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{fails} failed" if fails else f"\n{ran} tests passed.")
    sys.exit(1 if fails else 0)
