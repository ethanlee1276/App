"""The bettor's own Edge Report (js/account.js mbEdge, GET /api/account/edge)
and the "What we keep" screen (engine/yourdata, GET /api/account/yourdata).

Ethan's second research paper (2026-10-29): "Average CLV, ROI by market,
favorite markets, usual betting hours ... Show users their own computed
profile as an 'Edge Report.' It's your transparency promise made visible,
and their history becomes a reason to stay." What these hold:

  * the report reads the log: the price against the close (the box's own
    number for a saved parlay, else the entry over a logged close), where
    the bettor wins and where they don't by market, the best and worst
    result, and the two hours most bets go in — each only once there is
    enough to say it;
  * the box answers a member's saved parlays' closing-line value, theirs
    alone, and only for a ticket whose every leg has its close;
  * "What we keep" counts every table that names this member — and only
    their rows — grouped, with how long each is kept, any table the map
    does not name under "Other", and their choices newest first.

Run directly: `python3 tests/test_your_edge_and_what_we_keep.py`
"""
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp())

from engine import accounts as A                                  # noqa: E402
from engine import yourdata as YD                                 # noqa: E402

A.DB_PATH = _TMP / "accounts.db"
READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731


def _fn(src, name):
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 2]


def test_the_report_reads_the_log():
    node = shutil.which("node")
    if not node:
        print("      (skipped: no node)")
        return
    app, acct = READ("web", "js", "app.js"), READ("web", "js", "account.js")
    words = app[app.index("const MB_PROP_WORDS = ["):app.index("];", app.index("const MB_PROP_WORDS = [")) + 2]
    js = "\n".join([words, _fn(app, "mbDecimal"), _fn(app, "mbProfit"), _fn(app, "mbMarket"), _fn(acct, "mbEdge")])
    at = 1_793_304_000_000                                          # a bet logged at a known moment
    bets = [
        {"id": "s1", "src": "slip", "legs": [{}, {}], "odds": 264, "stake": 10, "result": "loss", "desc": "A + B"},
        {"id": f"{at}1234", "odds": -110, "close": -125, "stake": 20, "result": "win", "desc": "LeBron James over 24.5 points"},
        {"id": f"{at + 60000}22", "odds": -110, "close": 100, "stake": 20, "result": "loss", "desc": "Tatum over 27.5 points"},
        {"id": "h3", "odds": 150, "stake": 10, "result": "win", "desc": "Jokic over 11.5 rebounds"},
        {"id": "h4", "odds": -110, "stake": 10, "result": "win", "desc": "Curry over 4.5 threes"},
        {"id": "h5", "odds": -110, "stake": 10, "result": "win", "desc": "Brunson over 25.5 points"},
        {"id": "h6", "odds": -110, "stake": 10, "result": "loss", "desc": "Lakers -3.5 spread"},
        {"id": "h7", "odds": -110, "stake": 10, "result": "loss", "desc": "Celtics -5.5 spread"},
        {"id": "h8", "odds": -110, "stake": 10, "result": "loss", "desc": "Knicks -2.5 spread"},
        {"id": "h9", "odds": -110, "stake": 10, "result": "pending", "desc": "Heat ML"},
    ]
    js += f"\nconsole.log(JSON.stringify(mbEdge({json.dumps(bets)}, {{ s1: 0.031 }})));"
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=30)
    e = json.loads(out.stdout)
    clv = e["clv"]
    assert clv["n"] == 3 and clv["beat"] == 2, clv
    want = (0.031 + (1 + 100 / 110) / (1 + 100 / 125) - 1 + (1 + 100 / 110) / 2 - 1) / 3
    assert abs(clv["avg"] - want) < 1e-9, (clv, want)
    names = [m["m"] for m in e["markets"]]
    assert names[0] == "points" and names[-1] == "spread", names
    assert e["markets"][-1]["roi"] == -1 and e["markets"][-1]["losses"] == 3
    assert e["best"]["id"] == f"{at}1234", "the $20 at -110 that won pays more than the $10 at +150"
    assert e["worst"]["desc"].startswith("Tatum"), "the $20 loss, not a $10 one"
    assert e["peak"] is None and e["timed"] == 2, "two timed bets is not enough to say when you bet"


def test_the_week_s_best_priced_bet_and_the_weeks_beat():
    """The first paper's weekly "your best-graded bet" and its process mark,
    "Beat the close": graded on the price, win or lose, never on a streak of
    wins. Weeks run Monday to Sunday by the bet's date."""
    node = shutil.which("node")
    if not node:
        print("      (skipped: no node)")
        return
    app, acct = READ("web", "js", "app.js"), READ("web", "js", "account.js")
    words = app[app.index("const MB_PROP_WORDS = ["):app.index("];", app.index("const MB_PROP_WORDS = [")) + 2]
    js = "\n".join([words, _fn(app, "mbDecimal"), _fn(app, "mbProfit"), _fn(app, "mbMarket"), _fn(acct, "mbEdge")])
    bets = [{"id": "b1", "date": "2026-10-27", "odds": -110, "stake": 10, "result": "loss", "desc": "Mahomes over 1.5 TD"},
            {"id": "b2", "date": "2026-10-28", "odds": -110, "stake": 10, "result": "win", "desc": "Lakers ML"},
            {"id": "b3", "date": "2026-10-20", "odds": 120, "stake": 10, "result": "loss", "desc": "Celtics -4.5"},
            {"id": "b4", "date": "2026-10-13", "odds": -105, "stake": 10, "result": "win", "desc": "Under 47.5"},
            {"id": "b5", "date": "2026-08-01", "odds": 200, "stake": 10, "result": "win", "desc": "An old one"}]
    clv = {"b1": 0.05, "b2": -0.02, "b3": 0.10, "b4": -0.03, "b5": 0.2}
    js += (f"\nconst B = {json.dumps(bets)}, S = {json.dumps(clv)};"
           "\nconsole.log(JSON.stringify([mbEdge(B, S, '2026-10-29'), mbEdge(B, S, '2026-11-02'),"
           " mbEdge(B.slice(1), S, '2026-10-29')]));")
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=30)
    thu, mon, lost = json.loads(out.stdout)
    assert thu["week"]["b"]["id"] == "b1" and thu["week"]["when"] == "this week", thu["week"]
    assert thu["week"]["b"]["result"] == "loss", "the best price, whatever the result"
    assert thu["weeks"] == {"n": 3, "beat": 2}, thu["weeks"]
    assert mon["week"]["b"]["id"] == "b1" and mon["week"]["when"] == "last week", "a Monday reads last week's"
    assert lost["week"]["b"]["id"] == "b3" and lost["week"]["when"] == "last week", \
        "a week whose only priced bet lost to the close falls back to last week's"
    card = _fn(acct, "mbEdgeHTML")
    assert "Best-priced bet ${e.week.when}" in card and "against the close, win or lose" in card
    assert "Weeks you beat the close" in card and "e.weeks.n >= 3" in card


def test_my_bets_draws_it_and_the_box_fills_the_closes():
    acct = READ("web", "js", "account.js")
    assert "${mbEdgeHTML(bets)}" in acct and "  mbEdgeFill();\n  mbBoardFill();\n}" in acct
    card = _fn(acct, "mbEdgeHTML")
    for words in ("Your Edge Report", "Your price against the close", "Where you win", "Where you don’t",
                  "Best result", "Worst result", "When you bet"):
        assert words in card, words
    for never in ("bet now", "pick", "tail"):
        assert never not in card.lower().replace("picks", ""), never
    srv = READ("server.py")
    assert 'if path == "edge":' in srv and 'if path == "yourdata":' in srv


def _serve():
    import server
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def _get(base, path, cookie=""):
    req = urllib.request.Request(base + path, headers={"Cookie": cookie} if cookie else {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, None


def test_what_we_keep_counts_every_table_that_names_them_and_only_theirs():
    from engine import betclv as BC
    from engine import consent as CS
    from engine import pushalerts as PA
    conn = A.connect()
    try:
        _, me = A.create_user(conn, "keep@example.com", "correct horse battery", confirmed=True)
        _, them = A.create_user(conn, "them@example.com", "correct horse battery", confirmed=True)
        uid, other = me["id"], them["id"]
        A.start_session(conn, uid)
        A.start_session(conn, uid)
        A.start_session(conn, other)
        PA.subscribe(conn, "ab" * 32, kind="apns", user_id=uid)
        CS.record(conn, uid, "alerts", "on: posted")
        conn.execute("CREATE TABLE IF NOT EXISTS shiny_new_thing (user_id INTEGER, x TEXT)")
        conn.execute("INSERT INTO shiny_new_thing VALUES (?, 'a'), (?, 'b')", (uid, other))
        BC.ensure_tables(conn)
        conn.commit()
        groups = {g["title"]: g for g in YD.summary(conn, uid)}
        acct = {x["what"]: x["n"] for x in groups["Your account"]["items"]}
        assert acct["devices signed in"] == 2, acct
        assert {x["what"]: x["n"] for x in groups["Your alerts"]["items"]}["phones with alerts on"] == 1
        assert {x["what"]: x["n"] for x in groups["Your choices"]["items"]} == {
            "yeses and noes, each with the policy's date": 2}, "the Terms at sign-up and the alerts"
        assert groups["Other"]["items"] == [{"what": "shiny_new_thing", "n": 1}], "nothing kept left off"
        assert all(g["kept"] for g in groups.values())
        assert "How you use the site" not in groups, "an empty group is left out"
        with_them = {g["title"]: g["n"] for g in YD.summary(conn, other)}
        assert with_them["Your account"] == 2, "their own two: the account and one device"
    finally:
        conn.close()


def test_the_box_answers_only_its_own_member():
    from engine import betclv as BC
    httpd, base = _serve()
    try:
        conn = A.connect()
        _, me = A.create_user(conn, "edge@example.com", "correct horse battery", confirmed=True)
        uid, token = me["id"], A.start_session(conn, me["id"])
        slip = {"id": "t1", "src": "slip", "odds": 264, "legs": [{"player": "A"}, {"player": "B"}], "result": "pending"}
        half = {"id": "t2", "src": "slip", "odds": -110, "legs": [{"player": "C"}, {"player": "D"}], "result": "pending"}
        A.save_sections(conn, uid, {"mybets": {"ts": 1, "data": {"rows": [slip, half], "deleted": []}}})
        BC.ensure_tables(conn)
        for bet, leg, entry, fair in (("t1", 0, -110, 0.55), ("t1", 1, -110, 0.56), ("t2", 0, -110, 0.5)):
            conn.execute("INSERT INTO bet_clv (user_id, bet_id, leg, entry, best, fair, at) VALUES (?,?,?,?,?,?,?)",
                         (uid, bet, leg, entry, -120, fair, 1.0))
        conn.commit()
        conn.close()
        cookie = f"qb_session={token}"
        assert _get(base, "/api/account/edge")[0] == 401 and _get(base, "/api/account/yourdata")[0] == 401
        code, got = _get(base, "/api/account/edge", cookie)
        assert code == 200 and set(got["by_bet"]) == {"t1"}, "a ticket with a leg unclosed has no number"
        assert abs(got["by_bet"]["t1"] - round(3.64 * 0.55 * 0.56 - 1, 4)) < 1e-4, got
        code, yd = _get(base, "/api/account/yourdata", cookie)
        assert code == 200 and yd["choices"][0]["kind"] == "terms" and yd["groups"], yd
    finally:
        httpd.shutdown()


def test_settings_opens_it():
    acct = READ("web", "js", "account.js")
    at = acct.index('out.push(setGroup("Your data", [')
    assert 'data-set-open="yourdata"' in acct[at:at + 900] and "What we keep about you" in acct[at:at + 900]
    assert 'if (page === "yourdata") {' in acct
    fill = _fn(acct, "ydFill")
    assert '"/api/account/yourdata"' in fill and 'data-act="acctExport"' in fill and 'data-act="acctDelete"' in fill


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
