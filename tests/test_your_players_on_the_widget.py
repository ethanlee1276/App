"""Your players on the iPhone widget and the lock screen.

The second widget (deploy/ios/native/Widget/YourPlayersWidget.swift) shows
the players the account follows with their lines right now. A widget
cannot sign in, so the app hands it a key (engine/widgetfeed). What these
hold:

  - the key is the calendar's shape: an HMAC over the link's own salt, a
    new one stops the old, off deletes the row, a wrong one is nobody;
  - GET /api/widget/mine answers a key with the account's followed
    players' lines and nothing else, and a bad key with a plain 404;
  - POST /api/widget/key needs the account;
  - the JSON keys are the ones the Swift decodes, the plugin is registered,
    the widget is in the bundle, both targets share the App Group;
  - Settings offers it only inside the app, and signing out clears it.

    python3 tests/test_your_players_on_the_widget.py
"""
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_DIR = tempfile.mkdtemp()
os.environ["QB_ACCOUNTS_DB"] = os.path.join(_DIR, "accounts.db")

from engine import accounts as A                                  # noqa: E402
from engine import alerts as AL                                   # noqa: E402
from engine import widgetfeed as WF                               # noqa: E402

NATIVE = ROOT / "deploy" / "ios" / "native"
_n = [0]


def _member():
    _n[0] += 1
    conn = A.connect()
    code, out = A.create_user(conn, f"w{_n[0]}@example.com", "correct horse battery", confirmed=True)
    assert code == 200, out
    return conn, out["id"]


IDX = {"jamarrchase": [{"player": "Ja'Marr Chase", "team": "CIN", "opp": "PIT", "league": "nfl", "event_id": "55",
                        "line": "6 rec, 94 yds, 1 TD", "state": "live", "status": "3rd 4:12", "score": "x"}]}


def test_the_key_is_the_address_a_new_one_stops_the_old_and_off_deletes_it():
    conn, uid = _member()
    try:
        k1 = WF.key_for(conn, uid)
        assert re.fullmatch(r"\d+\.[A-Za-z0-9_-]{24,64}", k1)
        assert WF.key_for(conn, uid) == k1, "the same key until a new one is asked for"
        assert WF.user_for(conn, k1) == uid
        k2 = WF.key_for(conn, uid, new=True)
        assert k2 != k1 and WF.user_for(conn, k1) is None and WF.user_for(conn, k2) == uid
        for bad in ("", "x", f"{uid}.{'A' * 32}", k2 + "x", f"{uid + 1}.{k2.split('.')[1]}"):
            assert WF.user_for(conn, bad) is None, bad
        WF.key_off(conn, uid)
        assert WF.user_for(conn, k2) is None, "off is off"
    finally:
        conn.close()


def test_the_widget_carries_the_accounts_players_and_nothing_else():
    conn, uid = _member()
    try:
        AL.add_watch(conn, uid, "player", "Ja'Marr Chase")
        AL.add_watch(conn, uid, "team", "CIN")
        out = WF.mine(conn, WF.key_for(conn, uid), idx=IDX)
        assert out["following"] == 1 and out["players"] == [{
            "player": "Ja'Marr Chase", "team": "CIN", "opp": "PIT", "line": "6 rec, 94 yds, 1 TD",
            "status": "3rd 4:12", "live": True, "url": "/#pbp/nfl/55"}]
        assert set(out) == {"players", "following", "updated"}
        assert WF.mine(conn, "nope", idx=IDX) is None
    finally:
        conn.close()


def _handler():
    import server
    h = object.__new__(server.Handler)
    out = {}
    h._send = lambda code, body, kind=".json", headers=None: out.update(code=code, body=json.loads(body))
    h._rate_limited = lambda limit, bucket="read": False
    return h, out


def test_the_endpoints():
    conn, uid = _member()
    conn.close()
    h, out = _handler()
    h._account = lambda c: None
    h._widget_key({})
    assert out["code"] == 401, "a key needs the account"
    h._widget_mine("1.bad")
    assert out["code"] == 404
    h._account = lambda c: {"id": uid}
    h._widget_key({})
    key = out["body"]["key"]
    h._widget_mine(key)
    assert out["code"] == 200 and "players" in out["body"]
    h._widget_key({"off": True})
    assert out["body"] == {"ok": True, "off": True}
    h._widget_mine(key)
    assert out["code"] == 404, "off stops the widget answering"


def _swift_lets(src, struct):
    at = src.index(f"struct {struct}")
    body = src[at:src.index("\n    }", at)]
    return re.findall(r"let (\w+): ", body)


def test_the_swift_reads_the_feeds_own_keys_and_is_wired():
    sw = (NATIVE / "Widget" / "YourPlayersWidget.swift").read_text()
    assert _swift_lets(sw, "Line: Decodable") == ["player", "team", "opp", "line", "status", "live", "url"]
    top = sw[sw.index("struct MineFeed"):sw.index("struct MineEntry")]
    assert "let players: [Line]" in top and "let following: Int" in top
    assert "https://qellysbook.com/api/widget/mine" in sw and 'URLQueryItem(name: "k", value: key)' in sw
    assert ".accessoryRectangular" in sw and ".accessoryInline" in sw, "the lock screen"
    assert "YourPlayersWidget()" in (NATIVE / "Widget" / "QellysWidgets.swift").read_text()
    assert "registerPluginInstance(WidgetKeyPlugin())" in (NATIVE / "App" / "MainViewController.swift").read_text()
    shared = (NATIVE / "Shared" / "WidgetKey.swift").read_text()
    assert 'static let group = "group.com.qellysbook.app"' in shared
    plug = (NATIVE / "App" / "WidgetKeyPlugin.swift").read_text()
    assert 'jsName = "WidgetKey"' in plug and "reloadAllTimelines" in plug
    readme = (ROOT / "deploy" / "ios" / "README.md").read_text()
    assert "group.com.qellysbook.app" in readme and "Your players on the widget" in readme


def test_settings_offers_it_only_in_the_app_and_sign_out_clears_it():
    acct = (ROOT / "web" / "js" / "account.js").read_text()
    rows = acct[acct.index("function widgetRows("):acct.index("async function widgetFlip(")]
    assert "if (!P || !inn) return [];" in rows
    assert "...widgetRows(inn)," in acct
    flip = acct[acct.index("async function widgetFlip("):]
    flip = flip[:flip.index("\n}\n")]
    assert '"/api/widget/key"' in flip and "P.set({ key: got.key })" in flip and "P.clear()" in flip
    app = (ROOT / "web" / "js" / "app.js").read_text()
    out = app[app.index("window.acctSignOut = async function"):]
    assert "window.Capacitor.Plugins.WidgetKey.clear()" in out[:1200]
    priv = (ROOT / "web" / "privacy.html").read_text()
    assert "<code>widget_links</code>" in priv and "<code>calendar_links</code>" in priv
    accts = (ROOT / "engine" / "accounts.py").read_text()
    gone = accts[accts.index("def delete_user("):accts.index("def export_user(")]
    assert '"calendar_links", "widget_links"' in gone


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
