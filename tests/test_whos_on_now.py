"""Who's on now: every page open on the site, for the site's own account
alone (engine/whoson, js/here.js, the owner's desk's first card in
js/owner.js, the Privacy Policy's §2.13). Ethan, 2026-11-01: "add a feature
ONLY AVALIBLE for my Qellys Book account on the site that lets me see all
active users. It shows me all users and what page they are on." And
2026-11-02: "The Who's on and owners page should be one page".

What these hold:

  * a tab's page is kept a couple of minutes, in memory, and dropped the
    moment the tab says it is leaving; only our page names, a league or a
    game's room, and a random tab number are ever kept;
  * the page answers the verified Qellys_Book account (or the owner token)
    and nobody else, to whom it does not exist;
  * a member is named only once the policy's notice may count them and
    while they leave "Show me in Who's on now" on; everyone else is a number
    on the page they have open;
  * the policy says what the code does, and the notice that comes with the
    change says how to stay off;
  * the tab's check-in waits for the first screen, and the desk's card
    draws what it is sent and refuses everybody else; Settings carries the
    switch, the desk's row names the card, and an old #whoson link opens
    the desk.

Run directly: `python3 tests/test_whos_on_now.py`
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.pop("QB_POLICY_NOTICE", None)
_TMP = Path(tempfile.mkdtemp())

from engine import accounts as A                                  # noqa: E402
from engine import policynotice as PN                             # noqa: E402
from engine import socialfeed as SF                               # noqa: E402
from engine import whoson as W                                    # noqa: E402

A.DB_PATH = _TMP / "accounts.db"
READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731
PASS = "correct horse battery"
TAB1, TAB2, TAB3 = "a" * 16, "b" * 16, "0123456789abcdef"


def _user(conn, email, made=None, handle=None):
    uid = int(A.create_user(conn, email, PASS, confirmed=True)[1]["id"])
    if made is not None:
        conn.execute("UPDATE users SET created_at = ? WHERE id = ?", (made, uid))
        conn.commit()
    if handle:
        code, out = SF.profile_set(conn, uid, handle, "", name=handle.title())
        assert code == 200, out
    return uid


# --- the tab ------------------------------------------------------------------
def test_a_tab_is_kept_a_few_minutes_in_memory_and_dropped_when_it_leaves():
    W.clear()
    t = 1_000_000.0
    assert W.beat(TAB1, None, "likely", "nfl", now=t)
    assert W.beat(TAB2, 7, "pbp", "nfl_401873033", now=t)
    assert len(W.live(t + W.HERE_S)) == 2, "heard from inside the window"
    assert W.beat(TAB2, 7, "pbp", "nfl_401873033", now=t + 100)
    left = W.live(t + W.HERE_S + 1)
    assert [v["uid"] for v in left] == [7], "a tab silent past the window is forgotten"
    # The page it is on keeps its own clock; the visit keeps the first.
    assert W.beat(TAB2, 7, "record", "nfl", now=t + 120)
    v = W.live(t + 121)[0]
    assert v["first"] == t and v["since"] == t + 120, v
    W.leave(TAB2)
    assert W.live(t + 122) == [], "a tab that closes is gone at once"
    assert W.HERE_S <= 180, "a couple of minutes, as the policy says"


def test_only_a_page_name_a_league_or_a_game_room_and_a_random_tab_are_kept():
    W.clear()
    t = 2_000_000.0
    for bad in (("nottoshort", None, "likely", ""), (TAB1, None, "Likely<script>", ""),
                (TAB1, None, "likely", "https://evil.example/x"), (TAB1, None, "likely", "nfl_12;drop"),
                ("", None, "likely", ""), (TAB1, None, "", "")):
        assert not W.beat(*bad, now=t), bad
    assert W.live(t) == []
    assert W.beat(TAB3, None, "recommended", "", now=t)
    assert set(W.live(t)[0]) == {"uid", "view", "detail", "first", "since", "at"}, "nothing else is kept"
    # A crowd past the cap: the stalest go first, the newest stay.
    keep = W.MAX_TABS
    W.MAX_TABS = 3
    try:
        for i in range(5):
            W.beat(f"{i:016x}", None, "live", "", now=t + i)
        assert sorted(v["at"] for v in W.live(t + 5)) == [t + 2, t + 3, t + 4]
    finally:
        W.MAX_TABS = keep
        W.clear()


# --- who may be named ------------------------------------------------------------
def test_a_member_is_named_only_once_told_and_not_after_saying_no():
    d = Path(tempfile.mkdtemp())
    conn = A.connect(str(d / "acc.db"))
    try:
        now = PN.WHOSON_SINCE + 3 * 86400
        new = _user(conn, "new@example.com", made=PN.WHOSON_SINCE + 3600)      # made after the change
        old = _user(conn, "old@example.com", made=PN.WHOSON_SINCE - 30 * 86400)
        told = _user(conn, "told@example.com", made=PN.WHOSON_SINCE - 30 * 86400)
        PN.ensure_tables(conn)
        conn.execute("INSERT INTO policy_notices (user_id, notice, sent_at) VALUES (?, ?, ?)",
                     (told, PN.WHOSON, now - 8 * 86400))
        # Told about the 29 October change does not count for this one.
        conn.execute("INSERT INTO policy_notices (user_id, notice, sent_at) VALUES (?, ?, ?)",
                     (old, PN.NOTICE, now - 20 * 86400))
        conn.commit()
        assert W.nameable(conn, [new, old, told], now) == {new, told}
        A.save_sections(conn, new, {"settings": {"data": {"whoson": "off"}, "ts": 1}})
        assert W.nameable(conn, [new, old, told], now) == {told}, "a no takes them off the names"
        assert W.shown({}) and W.shown({"whoson": "on"}) and not W.shown({"whoson": "off"})
        assert W.changed({}, {"whoson": "off"}) == "not shown by name in Who's on now"
        assert W.changed({"whoson": "off"}, {}) == "shown by name in Who's on now"
        assert W.changed({}, {"whoson": "on"}) is None
    finally:
        conn.close()
        shutil.rmtree(d, ignore_errors=True)


def test_the_page_counts_every_page_and_names_one_row_a_member():
    d = Path(tempfile.mkdtemp())
    conn = A.connect(str(d / "acc.db"))
    W.clear()
    try:
        now = PN.WHOSON_SINCE + 86400
        named = _user(conn, "named@example.com", made=PN.WHOSON_SINCE + 3600, handle="SharpSam")
        quiet = _user(conn, "quiet@example.com", made=PN.WHOSON_SINCE - 86400, handle="QuietOne")
        (d / "data").mkdir()
        (d / "data" / "live_nfl.json").write_text(json.dumps({"games": [
            {"event_id": "401873033", "away": "KC", "home": "DEN", "live": {"state": "live"}}]}))
        W.beat(TAB1, named, "likely", "nfl", now=now - 300 + 200)        # an older tab of theirs
        W.beat(TAB2, named, "pbp", "nfl_401873033", now=now - 10)       # the newest: this one shows
        W.beat("c" * 16, quiet, "pbp", "nfl_401873033", now=now - 5)
        W.beat(TAB3, None, "recommended", "nfl", now=now - 1)
        snap = W.snapshot(conn, now=now, data_dir=d / "data")
        assert snap["members_total"] == 2 and snap["visitors"] == 1 and snap["unnamed_members"] == 1
        assert [m["handle"] for m in snap["members"]] == ["SharpSam"], "only the member told may be named"
        m = snap["members"][0]
        assert m["view"] == "pbp" and m["tabs"] == 2 and m["seen_s"] == 10, m
        assert m["game"] == {"away": "KC", "home": "DEN", "state": "live"}
        game = next(p for p in snap["pages"] if p["detail"] == "nfl_401873033")
        assert (game["members"], game["visitors"]) == (2, 0) and game["game"]["home"] == "DEN"
        home = next(p for p in snap["pages"] if p["view"] == "recommended")
        assert (home["members"], home["visitors"]) == (0, 1)
        assert snap["pages"][0] is game, "the busiest page first"
        assert "likely" not in [p["view"] for p in snap["pages"]], "one row a member: their newest page"
        assert "email" not in json.dumps(snap), "no address on the page, ever"
    finally:
        W.clear()
        conn.close()
        shutil.rmtree(d, ignore_errors=True)


def test_the_site_account_is_the_verified_qellys_book_alone():
    d = Path(tempfile.mkdtemp())
    conn = A.connect(str(d / "acc.db"))
    try:
        before = PN.WHOSON_SINCE - 30 * 86400                         # both made before the change
        site = _user(conn, "site@example.com", made=before)
        assert SF.claim(conn, "site@example.com", "Qellys_Book", name="Qellys Book")[0] == 200
        other = _user(conn, "fan@example.com", made=before, handle="QB_Fan")
        founder = _user(conn, "boss@example.com", handle="TheBoss")
        SF.crown(conn, "boss@example.com")
        assert W.is_site_account(conn, site)
        assert not W.is_site_account(conn, other) and not W.is_site_account(conn, founder)
        assert not W.is_site_account(conn, None) and not W.is_site_account(conn, 0)
        now = PN.WHOSON_SINCE + 86400
        assert W.nameable(conn, [other, site], now) == {site}, \
            "the account reading the page sees itself by name from the first day; nobody else is"
        SF.set_verified(conn, "Qellys_Book", False)
        assert not W.is_site_account(conn, site), "the tick is part of it"
        assert W.nameable(conn, [other, site], now) == set()
    finally:
        conn.close()
        shutil.rmtree(d, ignore_errors=True)


# --- the server -------------------------------------------------------------------
def _serve():
    import server
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def _call(base, path, body=None, cookie=""):
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                 method="GET" if body is None else "POST",
                                 headers={"Content-Type": "application/json", **({"Cookie": cookie} if cookie else {})})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, None


def test_the_endpoints_answer_the_site_account_and_nobody_else():
    W.clear()
    conn = A.connect()
    site = _user(conn, "site2@example.com")
    assert SF.claim(conn, "site2@example.com", "Qellys_Book", name="Qellys Book")[0] == 200
    fan = _user(conn, "fan2@example.com", handle="FanTwo")
    site_c = f"qb_session={A.start_session(conn, site)}"
    fan_c = f"qb_session={A.start_session(conn, fan)}"
    conn.close()
    httpd, base = _serve()
    try:
        assert _call(base, "/api/here", {"tab": TAB1, "view": "likely", "detail": "nfl"}) == (204, None)
        assert _call(base, "/api/here", {"tab": TAB2, "view": "live", "detail": "nba"}, fan_c) == (204, None)
        assert _call(base, "/api/here", {"tab": "x", "view": "<b>"})[0] == 204, "a bad one is ignored, quietly"
        assert {(v["uid"], v["view"]) for v in W.live()} == {(None, "likely"), (fan, "live")}
        assert _call(base, "/api/owner/whoson")[0] == 404, "signed out: no such page"
        assert _call(base, "/api/owner/whoson", cookie=fan_c)[0] == 404, "a member: no such page"
        code, snap = _call(base, "/api/owner/whoson", cookie=site_c)
        assert code == 200 and snap["members_total"] == 1 and snap["visitors"] == 1, snap
        # The menu row, for the site's own account alone.
        assert _call(base, "/api/account/me", cookie=site_c)[1].get("whoson") is True
        assert "whoson" not in _call(base, "/api/account/me", cookie=fan_c)[1]
        assert _call(base, "/api/billing/status")[1]["whoson_switch"] is True, "the policy's section is live"
        # Leaving takes the tab off at once.
        assert _call(base, "/api/here", {"tab": TAB2, "leave": True}, fan_c) == (204, None)
        assert [v["view"] for v in W.live()] == ["likely"]
        # The switch's no goes in the consent log with the policy's date.
        sections = {"settings": {"data": {"whoson": "off"}, "ts": int(time.time() * 1000)}}
        assert _call(base, "/api/account/data", {"sections": sections}, fan_c)[0] == 200
        from engine import consent as CS
        c2 = A.connect()
        log = CS.history(c2, fan)
        c2.close()
        mine = [(x["kind"], x["choice"]) for x in log if x["kind"] == "whoson"]
        assert mine == [("whoson", "not shown by name in Who's on now")], log
        assert all(x["policy"] == CS.policy_version() >= "2026-11-01" for x in log), "with the policy's date"
    finally:
        httpd.shutdown()
        W.clear()


# --- the policy and the notice ------------------------------------------------------
def test_the_policy_says_what_the_code_does():
    html = READ("web", "privacy.html")
    assert W.policy_ready() and 'id="who-is-on"' in html
    import re
    sec = re.sub(r"\s+", " ", html[html.index('id="who-is-on"'):html.index("<h2>3. What we do NOT collect</h2>")])
    assert "two and a half minutes" in sec and W.HERE_S == 150
    assert "never written to a disk or a database" in sec
    assert "Show me in Who’s on now" in sec and "Show me in Who’s on now" in READ("web", "js", "account.js")
    assert "2 November 2026" in sec and "9 November 2026" in sec
    import datetime as dt
    assert dt.datetime.fromtimestamp(PN.WHOSON_SINCE, PN.ET).date() == dt.date(2026, 11, 2)
    assert dt.datetime.fromtimestamp(PN.WHOSON_PHONE_FROM, PN.ET).date() == dt.date(2026, 11, 9)
    assert "(§2.13)" in html[:html.index("<h2>2.")], "the short version says it"
    # Dated the day of this change or later (a later change moves the date).
    said = re.search(r'class="legal-date">Last updated (\d{1,2} \w+ 2026)<', html)
    assert said and dt.datetime.strptime(said.group(1), "%d %B %Y").date() >= dt.date(2026, 11, 1), said
    # Nothing it keeps is a table: the policy says so rather than naming one.
    assert "CREATE TABLE" not in READ("engine", "whoson.py")


def test_the_notice_says_how_to_stay_off_and_both_changes_share_a_day():
    subject, text, html = PN.message(PN.WHOSON_SINCE, notice=PN.WHOSON)
    assert "Privacy Policy" in subject and "Who's on now" in text
    assert "Show me in Who's on now" in text and "privacy.html#who-is-on" in text and "#who-is-on" in html
    assert "Terms of Service are the same" in text
    assert PN.message(PN.SINCE)[0] == "Changes to the Qellys Book Terms and Privacy Policy", "the first is unchanged"
    d = Path(tempfile.mkdtemp())
    conn = A.connect(str(d / "acc.db"))
    try:
        for i in range(4):
            _user(conn, f"m{i}@example.com", made=PN.SINCE - 86400)
        noon = PN.WHOSON_SINCE + 12 * 3600
        box = []
        os.environ[PN.ENV] = f"{PN.NOTICE},{PN.WHOSON}"
        keep = PN.DAY_MAX
        PN.DAY_MAX = 6
        try:
            assert PN.armed(PN.NOTICE) and PN.armed(PN.WHOSON)
            assert PN.run(conn, now=noon, send=lambda *a: box.append(a[1])) == 6, "one allowance for both"
            assert [s for s in box].count("Changes to the Qellys Book Terms and Privacy Policy") == 4, \
                "the older change first"
            assert PN.run(conn, now=noon + 86400, send=lambda *a: box.append(a[1])) == 2
            assert PN.run(conn, now=noon + 2 * 86400, send=lambda *a: box.append(a[1])) == 0, "each once"
            os.environ[PN.ENV] = PN.WHOSON
            assert not PN.armed(PN.NOTICE) and PN.status(conn, PN.WHOSON)["told"] == 4
        finally:
            PN.DAY_MAX = keep
            os.environ.pop(PN.ENV, None)
    finally:
        conn.close()
        shutil.rmtree(d, ignore_errors=True)


# --- the page and the tab -------------------------------------------------------------
def _node(js):
    if not shutil.which("node"):
        return None
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_the_tab_says_its_page_its_game_and_when_it_leaves():
    here = READ("web", "js", "here.js")
    got = _node(r"""
      const sent = [], beacons = [], listeners = {}, docl = {};
      global.window = global;
      global.state = { view: "pbp", sport: "nfl", pbp: { league: "nfl", event: "401873033" } };
      global.sessionStorage = { _v: {}, getItem(k) { return this._v[k] || null; }, setItem(k, v) { this._v[k] = v; } };
      global.document = { visibilityState: "visible", addEventListener: (k, f) => { docl[k] = f; } };
      global.addEventListener = (k, f) => { listeners[k] = f; };
      global.setInterval = () => 0;
      global.setTimeout = (f) => f();
      global.fetch = (u, o) => { sent.push([u, JSON.parse(o.body)]); return Promise.resolve({}); };
      Object.defineProperty(globalThis, "navigator", { configurable: true, writable: true,
        value: { sendBeacon: (u, b) => { beacons.push(u); return true; } } });
      """ + here + r"""
      state.view = "likely"; state.pbp = null;
      listeners.hashchange();
      listeners.hashchange();                  // the same page: said once
      listeners.pagehide();
      console.log(JSON.stringify({ sent, beacons, tab: sessionStorage._v["qb.tab"] }));
    """)
    if got is None:
        print("  SKIP node not installed"); return
    assert len(got["tab"]) == 16 and all(c in "0123456789abcdef" for c in got["tab"])
    first, second = got["sent"][0][1], got["sent"][1][1]
    assert got["sent"][0][0] == "/api/here"
    assert first == {"tab": got["tab"], "view": "pbp", "detail": "nfl_401873033"}, first
    assert second == {"tab": got["tab"], "view": "likely", "detail": "nfl"}, second
    assert len(got["sent"]) == 2, "an unchanged page is not said twice"
    assert got["beacons"] == ["/api/here"], "and closing says so"
    app = READ("web", "js", "app.js")
    i = app.index('s.src = "js/here.js";')
    assert "}, 4000);" in app[i:i + 200], "after the first screen has long settled"
    assert "here.js" not in READ("web", "index.html"), "never on the first screen's path"


def test_the_owner_page_draws_what_it_is_sent_and_refuses_everybody_else():
    js = READ("web", "js", "owner.js")
    snap = {"at": 1_793_600_000, "window_s": 150, "members_total": 3, "visitors": 2, "unnamed_members": 1,
            "members": [{"handle": "SharpSam", "name": "Sam <b>", "color": 3, "view": "pbp",
                         "detail": "nfl_401873033", "tabs": 2, "on_page_s": 240, "on_site_s": 1320, "seen_s": 12,
                         "game": {"away": "KC", "home": "DEN", "state": "live"}},
                        {"handle": "Fan2", "name": "", "color": 0, "view": "likely", "detail": "nfl", "tabs": 1,
                         "on_page_s": 30, "on_site_s": 30, "seen_s": 40},
                        {"handle": "", "name": "", "color": 5, "view": "record", "detail": "nfl", "tabs": 1,
                         "on_page_s": 3, "on_site_s": 3, "seen_s": 3}],
            "pages": [{"view": "pbp", "detail": "nfl_401873033", "members": 2, "visitors": 0,
                       "game": {"away": "KC", "home": "DEN", "state": "live"}},
                      {"view": "recommended", "detail": "nfl", "members": 1, "visitors": 2}]}
    desk = {"at": 1_793_600_000, "now": {"members": 3, "visitors": 2, "pages": 2}, "switches": [],
            "alerts": {"phones": 1}, "notice": None}
    got = _node(r"""
      const hosts = { "owner-body": { innerHTML: "", firstChild: null, querySelector: () => null },
                      "owner-sub": { textContent: "" }, "od-who": { innerHTML: "" } };
      global.document = { getElementById: (id) => hosts[id] || null, querySelector: () => null,
                          visibilityState: "visible", addEventListener() {}, activeElement: null };
      global.CSS = { escape: (s) => s };
      global.state = { view: "owner" };
      global.escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
      global.escapeAttr = global.escapeHtml;
      global.toneOf = () => "";
      global.tzTime = () => "3:05:12 PM";
      global.setTimeout = () => 0; global.clearTimeout = () => {};
      let who = { status: 200, body: """ + json.dumps(snap) + r""" };
      const desk = """ + json.dumps(desk) + r""";
      global.fetch = async (u) => (u.includes("/api/owner/whoson")
        ? { status: who.status, ok: who.status === 200, json: async () => who.body }
        : { status: 200, ok: true, json: async () => desk });
      """ + js + r"""
      const tick = () => new Promise((r) => setImmediate(r));
      (async () => {
        renderOwner(); for (let i = 0; i < 6; i++) await tick();
        const page = hosts["owner-body"].innerHTML, card = hosts["od-who"].innerHTML;
        who = { status: 404, body: {} }; _woBusy = false;
        await woFill();
        console.log(JSON.stringify({ page, card, refused: hosts["od-who"].innerHTML }));
      })();
    """)
    if got is None:
        print("  SKIP node not installed"); return
    page, card = got["page"], got["card"]
    assert 'id="od-who"' in page and page.index('id="od-who"') < page.index("A notice to everybody"), \
        "Who's on now is the desk's first card"
    assert "@SharpSam" in card and "KC @ DEN" in card and "· live" in card, card[:600]
    assert "Sam &lt;b&gt;" in card and "Sam <b>" not in card, "a name is escaped"
    assert "On this page 4 min · on the site 22 min · 2 tabs" in card
    assert "12 s ago" in card and "Most Likely" in card and "3:05:12 PM" in card
    assert "1 more member on, not shown by name" in card
    for k in ("Members on", "Visitors", "Pages open", "By name", "Every page open"):
        assert k in card, k
    assert "wo-c3" in card, "the member's own colour"
    assert "no username yet" in card and ">@<" not in card, "a member with no handle is said so, not a bare @"
    assert "only for the site’s own account" in got["refused"]
    assert "Members on" in got["refused"], "refused, the card keeps the desk's own counts"


def test_settings_carry_the_switch_and_the_desk_carries_the_page():
    acc = READ("web", "js", "account.js")
    i = acc.index('title: "Show me in Who’s on now"')
    row = acc[i - 400:i + 300]
    assert "_pwStatus.whoson_switch" in row and 's.whoson !== "off"' in row and 'data-set-switch="whoson"' in row
    # One owner page (2026-11-02): no row of its own; the desk's row names it.
    assert 'href: "#whoson"' not in acc
    j = acc.index('title: "Owner desk"')
    assert "if (inn && u.whoson) {" in acc[j - 700:j] and "Who’s on now" in acc[j:j + 300]
    assert 'whoson: "Who\'s on now"' in acc, "named on Your data's list of choices"
    from engine import consent as CS
    assert "whoson" in CS.KINDS
    app = READ("web", "js", "app.js")
    assert "renderWhoson" not in app and '"whoson"' not in app[app.index("const VIEW_ORDER"):][:900]
    assert 'if (h !== "whoson") return false;' in app and app.count("if (ownerRoute(h)) return;") == 2
    assert 'id="view-whoson"' not in READ("web", "index.html")
    assert not (ROOT / "web" / "js" / "whoson.js").exists() and not (ROOT / "web" / "css" / "whoson.css").exists()


if __name__ == "__main__":
    passed = failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok  {name}")
                passed += 1
            except Exception as exc:                                      # noqa: BLE001
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
                failed += 1
    shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{passed} tests passed." if not failed else f"\n{failed} failed.")
    sys.exit(1 if failed else 0)
