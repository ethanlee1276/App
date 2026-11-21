"""The Owner desk opens for the site's owners' accounts, listed on the box, and for nobody else.

Ethan, 2026-11-02: "my other accounts have access too the owners page too.
Only the account with [his two addresses] should have access to that page".
engine/siteowners. What these hold:

  * an address becomes its account once, exactly as the site stores it —
    an address with no account is refused, and an alias of it (a +tag, a
    Gmail dot) is a different account, because signing up proves nothing
    about an address;
  * once anybody is listed, only the listed accounts open the desk — the
    verified Qellys_Book account included only if listed — and the server's
    every door (the desk, Who's on now, the notice, the reports, Accounts,
    the account's menu flag) says the same; until then that account alone;
  * deleting an account takes it off the list; removing the last one gives
    the desk back to the Qellys_Book account;
  * the site's problems go to every owner's phones; no owner can be
    suspended or deleted from the desk;
  * the page takes the server's word, never a handle; the addresses live
    on the box, never in this repository.

Run directly: `python3 tests/test_only_the_owners_open_the_desk.py`
"""
import json
import os
import re
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_TMP = Path(tempfile.mkdtemp())

from engine import accounts as A                                  # noqa: E402
from engine import owneraccounts as OAC                           # noqa: E402
from engine import siteowners as SO                               # noqa: E402
from engine import socialfeed as SF                               # noqa: E402

A.DB_PATH = _TMP / "accounts.db"
READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731
PASS = "correct horse battery"


def _db():
    conn = A.connect(str(Path(tempfile.mkdtemp()) / "acc.db"))
    SO.init(conn)
    return conn


def _user(conn, email, handle=None):
    uid = int(A.create_user(conn, email, PASS, confirmed=True)[1]["id"])
    if handle:
        assert SF.profile_set(conn, uid, handle, "")[0] == 200
    return uid


def _site(conn, email="site@example.com"):
    uid = _user(conn, email)
    assert SF.claim(conn, email, "Qellys_Book", name="Qellys Book")[0] == 200
    return uid


def test_an_address_becomes_its_account_exactly_and_an_alias_is_not_it():
    conn = _db()
    me = _user(conn, "owner@example.com", "Owner_One")
    alias = _user(conn, "owner+x@example.com")
    ok, said = SO.add(conn, "  Owner@Example.com ")
    assert ok and said.startswith(f"account #{me} @Owner_One, made "), said
    assert SO.owner_ids(conn) == {me} and alias not in SO.owner_ids(conn), "an alias is somebody else's account"
    ok, said = SO.add(conn, "nobody@example.com")
    assert not ok and "Make the account first" in said
    assert SO.add(conn, "owner@example.com")[0], "adding twice is harmless"


def test_once_anybody_is_listed_only_they_open_the_desk():
    conn = _db()
    site = _site(conn)
    mine, other = _user(conn, "me@example.com"), _user(conn, "someone@example.com")
    assert SO.is_owner(conn, site) and not SO.is_owner(conn, mine), "nobody listed: the Qellys_Book account, as before"
    SO.add(conn, "me@example.com")
    assert SO.is_owner(conn, mine) and not SO.is_owner(conn, site) and not SO.is_owner(conn, other)
    assert not SO.is_owner(conn, None) and not SO.is_owner(conn, 0)
    SO.add(conn, "site@example.com")
    assert SO.is_owner(conn, site), "listed, it opens again"
    A.delete_user(conn, mine)
    assert SO.owner_ids(conn) == {site}, "a deleted account is off the list"
    assert conn.execute("SELECT COUNT(*) FROM site_owners WHERE user_id = ?", (mine,)).fetchone()[0] == 0
    assert SO.remove(conn, "site@example.com")[0] and SO.owner_ids(conn) == set()
    assert SO.is_owner(conn, site), "nobody listed again: the Qellys_Book account"


def test_the_problems_reach_every_owner_and_no_owner_is_suspended_from_the_desk():
    from engine import owneralerts as OW
    from engine import pushalerts as PA
    from engine import pushmine as PM
    conn = _db()
    a, b = _user(conn, "a@example.com"), _user(conn, "b@example.com")
    PA.ensure_tables(conn)
    PM.ensure_tables(conn)
    for i, uid in enumerate((a, b)):
        assert PA.subscribe(conn, f"{i:02d}" * 32, kind="apns", user_id=uid, topics=["posted"])[0] == 200
    SO.add(conn, "a@example.com")
    SO.add(conn, "b@example.com")
    assert SO.desk_accounts(conn) == sorted((a, b))
    told = OW.alerts_pass(conn, health={"disk": {"free_gb": 0.5, "used_pct": 99.0}})
    assert told >= 2 and {r[0] for r in conn.execute("SELECT user_id FROM push_mine WHERE kind = 'account'")} == {a, b}
    for action in ("suspend", "delete"):
        code, out = OAC.act(conn, a, action, {"confirm": "a@example.com"})
        assert code == 409 and "site’s own accounts" in out["error"], (action, out)
    assert OAC.card(conn, a)["site_account"] is True


# --- the server -------------------------------------------------------------------
def _serve():
    import server
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def _call(base, path, cookie="", body=None):
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                 method="GET" if body is None else "POST",
                                 headers={"Content-Type": "application/json", **({"Cookie": cookie} if cookie else {})})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, None


def test_every_door_on_the_server_follows_the_list():
    conn = A.connect()
    site = _site(conn, "site9@example.com")
    owner = _user(conn, "boss9@example.com", "Boss_Nine")
    other = _user(conn, "alt9@example.com", "Alt_Nine")
    cookies = {u: f"qb_session={A.start_session(conn, u)}" for u in (site, owner, other)}
    conn.close()
    httpd, base = _serve()
    doors = ("/api/owner/desk", "/api/owner/whoson", "/api/owner/accounts?q=nine")
    try:
        # Nobody listed: the Qellys_Book account, as before.
        assert all(_call(base, d, cookies[site])[0] == 200 for d in doors)
        assert all(_call(base, d, cookies[owner])[0] == 404 for d in doors)
        conn = A.connect()
        assert SO.add(conn, "boss9@example.com")[0]
        conn.close()
        for d in doors:
            assert _call(base, d, cookies[owner])[0] == 200, d
            assert _call(base, d, cookies[site])[0] == 404, ("the Qellys_Book account, not listed", d)
            assert _call(base, d, cookies[other])[0] == 404 and _call(base, d)[0] == 404, d
        assert _call(base, "/api/owner/notice", cookies[other], {"clear": True})[0] == 404
        assert _call(base, "/api/owner/account", cookies[site], {"id": other, "action": "signout"})[0] == 404
        assert _call(base, "/api/account/me", cookies[owner])[1].get("whoson") is True
        assert "whoson" not in _call(base, "/api/account/me", cookies[site])[1]
        assert "whoson" not in _call(base, "/api/account/me", cookies[other])[1]
    finally:
        httpd.shutdown()


def test_the_page_takes_the_servers_word_and_the_addresses_stay_off_the_repository():
    social = READ("web", "js", "social.js")
    assert "const siteDesk = () => !!(typeof _acctUser !== \"undefined\" && _acctUser && _acctUser.whoson);" in social
    assert '=== "qellys_book")' not in social[social.index("const siteDesk"):][:300], "never a handle"
    srv = READ("server.py")
    door = srv[srv.index("def _site_door"):][:900]
    assert "SO.is_owner(conn, who[\"id\"])" in door and "is_site_account" not in door
    addr = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
    assert set(addr.findall(READ("engine", "siteowners.py"))) <= {"you@example.com", "other@example.com"}
    for name in ("docs/RUN_NEXT.md", "docs/WHEN_YOU_ARE_HOME.md"):
        for line in READ(*name.split("/")).splitlines():
            if "engine.siteowners" in line:
                assert all(a.endswith("@example.com") for a in addr.findall(line)), (name, line)
    book = READ("docs", "WHEN_YOU_ARE_HOME.md")
    assert "python3 -m engine.siteowners add you@example.com other@example.com" in book
    assert "python3 -m engine.siteowners list" in READ("tools", "catchup.sh")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}")
    print(f"\n{sum(1 for n in globals() if n.startswith('test_'))} tests passed.")
