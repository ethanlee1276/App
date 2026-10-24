"""The iPhone widget and a saved parlay on the lock screen.

Ethan, 2026-10-24: "build everything ... including all the ideas" — docs/
IDEAS.md 11, Apple Sports' two best things. The box half is here and runs;
the Swift (deploy/ios/native) is written for the Mac and cannot be compiled
here, so what these hold is that the two halves agree:

  - /api/widget is public and carries the record, last night and today's
    pick counts — never a pick — in the keys the widget's Swift decodes;
  - a Live Activity update is shaped as Apple asks (push type liveactivity,
    the app's topic with .push-type.liveactivity, content-state matching the
    app's ContentState field for field, an end that dismisses in an hour);
  - the slip watch's pass updates an activity when the ticket's standing
    changes, not every minute, ends it when the ticket settles, and drops
    one Apple refuses; the lock screen never shows our chance;
  - only a signed-in member registers one, for a real token, five at most;
  - the page offers it only inside the iOS app with the plugin present.

    python3 tests/test_the_iphone_widget_and_lock_screen.py
"""
import base64
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
os.environ["QB_MODELS_DIR"] = os.path.join(_DIR, "models")
os.environ["QB_LIKELY_CAL"] = os.path.join(_DIR, "likely_calibration.json")

from engine import accounts as A                                  # noqa: E402
from engine import pushmine as PM                                 # noqa: E402
from engine import webpush as W                                   # noqa: E402
from engine import widgetfeed as WF                               # noqa: E402

READ = lambda *p: (ROOT.joinpath(*p)).read_text(encoding="utf-8")  # noqa: E731
NATIVE = ROOT / "deploy" / "ios" / "native"
NOW = 1_760_000_000.0


def _swift_fields(src, struct):
    at = src.index(f"struct {struct}")
    body = src[at:src.index("\n    }", at)] if "ContentState" in struct else src[at:src.index("\n}", at)]
    return re.findall(r"(?:let|var) (\w+): ", body)


def test_the_widget_feed_is_public_counts_and_the_keys_the_swift_decodes():
    web = Path(tempfile.mkdtemp()) / "web"
    (web / "data").mkdir(parents=True)
    (web / "data" / "record_head.json").write_text(json.dumps({"overall": {
        "settled": 120, "wins": 70, "losses": 47, "pushes": 3, "net_units": 9.84, "roi": 0.061}}))
    (web / "data" / "feed.json").write_text(json.dumps({"events": [
        {"kind": "settle_recap", "date": "2026-10-23", "w": 5, "l": 2, "p": 0, "net_u": 2.4}]}))
    (web / "data" / "recommendations.json").write_text(json.dumps({"date": "2026-10-24", "recommendations": [
        {"player": "Amon-Ra St. Brown", "market": "receptions", "recommended": True},
        {"player": "Jahmyr Gibbs", "market": "rush yards", "recommended": True}]}))
    import datetime as dt
    out = WF.build(web, today=dt.date(2026, 10, 24))
    assert out["record"] == {"w": 70, "l": 47, "p": 3, "units": 9.8, "roi": 6.1}, out
    assert out["last_night"] == {"date": "2026-10-23", "w": 5, "l": 2, "p": 0, "units": 2.4}
    assert out["tonight"] == [{"league": "NFL", "sport": "nfl", "picks": 2, "url": "/?sport=nfl#recommended"}]
    blob = json.dumps(out)
    assert "St. Brown" not in blob and "receptions" not in blob, "a count, never a pick"
    swift = (NATIVE / "Widget" / "RecordWidget.swift").read_text()
    assert set(_swift_fields(swift, "WidgetFeed:")) >= {"record", "last_night", "tonight"}
    rec = re.search(r"struct Record: Decodable \{([^}]*)\}", swift).group(1)
    assert set(re.findall(r"let (\w+):", rec)) == set(out["record"]), "the widget decodes the feed's record keys"
    night = re.search(r"struct Night: Decodable \{([^}]*)\}", swift).group(1)
    assert set(re.findall(r"let (\w+):", night)) == set(out["last_night"])
    board = re.search(r"struct Board: Decodable \{([^}]*)\}", swift).group(1)
    assert set(re.findall(r"let (\w+):", board)) == set(out["tonight"][0])
    assert 'URL(string: "https://qellysbook.com/api/widget")' in swift and ".after(Date().addingTimeInterval(30 * 60))" in swift
    srv = READ("server.py")
    assert 'if parsed.path in ("/api/widget", "/api/widget/"):' in srv and "widgetfeed.build()" in srv


def _p8(d):
    der = bytes.fromhex("308187020100301306072a8648ce3d020106082a8648ce3d030107046d306b0201010420") \
        + d.to_bytes(32, "big") + bytes.fromhex("a144034200") + b"\x04" + bytes(64)
    return "-----BEGIN PRIVATE KEY-----\n" + base64.b64encode(der).decode() + "\n-----END PRIVATE KEY-----\n"


def test_a_live_activity_update_is_shaped_as_apple_asks():
    path = os.path.join(tempfile.mkdtemp(), "AuthKey.p8")
    open(path, "w").write(_p8(0x1234567890ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890ABCD))
    cfg = W.apns_config({"QB_APNS_KEY_FILE": path, "QB_APNS_KEY_ID": "ABC123DEFG", "QB_APNS_TEAM_ID": "TEAM123456",
                         "QB_APNS_TOPIC": "com.qellysbook.app"})
    got = {}

    class Out:
        stdout = "200"

    def run(cmd, input, **kw):
        got.update(cmd=cmd, input=input)
        return Out()
    state = {"title": "One leg left", "status": "open", "legs": 3, "left": 1, "won": 2, "leg": "Chiefs ML",
             "line": "DEN 17 – 21 KC, 4th 2:10"}
    assert W.apns_live("b" * 64, state, cfg, run=run, now=NOW) == 200
    heads = [got["cmd"][i + 1] for i, c in enumerate(got["cmd"]) if c == "-H"]
    assert "apns-push-type: liveactivity" in heads and "apns-topic: com.qellysbook.app.push-type.liveactivity" in heads
    assert "apns-priority: 5" in heads, "a quiet update"
    body = json.loads(got["input"])["aps"]
    assert body == {"timestamp": int(NOW), "event": "update", "content-state": state}, body
    W.apns_live("b" * 64, state, cfg, event="end", alert={"title": "t", "body": "b"}, run=run, now=NOW)
    body = json.loads(got["input"])["aps"]
    heads = [got["cmd"][i + 1] for i, c in enumerate(got["cmd"]) if c == "-H"]
    assert body["event"] == "end" and body["dismissal-date"] == int(NOW) + 3600 and "apns-priority: 10" in heads
    assert W.apns_live("not hex", state, cfg, run=run) == 0 and W.apns_live("b" * 64, state, None, run=run) == 0
    # The app's ContentState is the box's state, field for field.
    swift = (NATIVE / "Shared" / "ParlayAttributes.swift").read_text()
    assert _swift_fields(swift, "ContentState") == list(state), "the Swift ContentState and activity_state disagree"
    assert set(PM.activity_state({}).keys()) == set(state)


def _member():
    conn = A.connect()
    try:
        code, out = A.create_user(conn, f"lock{os.urandom(3).hex()}@example.com", "correct horse battery", confirmed=True)
        assert code == 200, out
        return out["id"]
    finally:
        conn.close()


def _card(status="open", left=2, results=(None, None, None), clock="2nd 4:12"):
    legs = []
    for i, r in enumerate(results):
        live = {"state": "live", "home": "KC", "away": "DEN", "home_score": 14, "away_score": 10, "clock": clock}
        if r:
            live["result"] = r
        legs.append({"market": "moneyline", "text": f"Leg {i}", "team": "KC", "live": live})
    return {"legs": legs, "now": {"status": status, "left": left, "chance": 0.61}, "hedge": {"leg": "Chiefs ML"}}


def test_the_slip_watch_updates_on_a_change_ends_on_settle_and_never_shows_our_chance():
    uid = _member()
    conn = A.connect()
    try:
        PM.ensure_tables(conn)
        assert PM.activity_add(conn, uid, "s1", "not a token")[0] == 400
        assert PM.activity_add(conn, uid, "s1", "c" * 64, now=NOW) == (200, {"ok": True})
        sent = []
        live = lambda tok, st, cfg, event="update", alert=None, now=None: sent.append((event, st, alert)) or 200  # noqa: E731
        cfg = {"QB_APNS_TOPIC": "com.qellysbook.app"}
        assert PM.activity_update(conn, uid, "s1", _card(), live=live, cfg=cfg, now=NOW) == 200
        assert PM.activity_update(conn, uid, "s1", _card(), live=live, cfg=cfg, now=NOW + 60) == 0, "no change, no push"
        PM.activity_update(conn, uid, "s1", _card(left=1, results=("won", "won", None), clock="4th 2:10"),
                           live=live, cfg=cfg, now=NOW + 120)
        assert len(sent) == 2
        ev, st, alert = sent[-1]
        assert st["title"] == "One leg left" and st["won"] == 2 and st["leg"] == "Chiefs ML" and "4th 2:10" in st["line"]
        assert alert == {"title": "Down to the last leg", "body": "Chiefs ML decides it."}, "the last leg rings once"
        for _, s, _ in sent:
            assert "chance" not in s and "61" not in json.dumps(s), "our chance stays on the Live tab"
        assert PM.activity_end(conn, uid, "s1", {"result": "win"}, live=live, cfg=cfg, now=NOW + 180) == 200
        ev, st, _ = sent[-1]
        assert ev == "end" and st["title"] == "Won" and st["status"] == "won" and st["left"] == 0
        assert PM.activity_update(conn, uid, "s1", _card(), live=live, cfg=cfg) == 0, "forgotten once ended"
        PM.activity_add(conn, uid, "s2", "d" * 64, now=NOW)
        gone = lambda *a, **k: 410  # noqa: E731
        assert PM.activity_update(conn, uid, "s2", _card(), live=gone, cfg=cfg, now=NOW) == 410
        assert PM.activity_update(conn, uid, "s2", _card(left=1), live=live, cfg=cfg) == 0, "Apple refused it: dropped"
        for i in range(PM.MAX_ACTIVITIES):
            assert PM.activity_add(conn, uid, f"m{i}", "e" * 64, now=NOW)[0] == 200
        assert PM.activity_add(conn, uid, "one-too-many", "e" * 64, now=NOW)[0] == 400
        assert PM.activity_add(conn, uid, "fresh", "e" * 64, now=NOW + PM.ACTIVITY_S + 1)[0] == 200, \
            "an activity Apple has long ended is forgotten"
    finally:
        conn.close()
    sw = READ("engine", "slipwatch.py")
    assert '_tell("activity_update", conn, r["user_id"], str(bet["id"]), card, now=t, log=log)' in sw
    assert '_tell("activity_end", conn, uid, bet_id, got, now=t, log=log)' in sw


def test_only_a_member_registers_and_only_the_ios_app_offers_it():
    srv = READ("server.py")
    at = srv.index('            if path == "activity":')
    block = srv[at:at + 900]
    assert 'who = self._account(conn)' in block and '401' in block and "PM.activity_add(" in block
    js = READ("web", "js", "slip.js")
    at = js.index("function lockPlugin() {")
    assert "C.isNativePlatform && C.isNativePlatform() && C.Plugins && C.Plugins.ParlayActivity" in js[at:at + 300]
    assert 'fetch("/api/push/activity"' in js and "lockHTML(b.id)" in js
    plugin = (NATIVE / "App" / "ParlayActivityPlugin.swift").read_text()
    assert 'jsName = "ParlayActivity"' in plugin and "pushType: .token" in plugin and "pushTokenUpdates" in plugin
    assert "registerPluginInstance(ParlayActivityPlugin())" in (NATIVE / "App" / "MainViewController.swift").read_text()
    bundle = (NATIVE / "Widget" / "QellysWidgets.swift").read_text()
    assert "RecordWidget()" in bundle and "ParlayLiveActivity()" in bundle
    readme = READ("deploy", "ios", "README.md")
    assert "NSSupportsLiveActivities" in readme and "nothing here has compiled\nit" in readme
    for f in NATIVE.rglob("*.swift"):
        assert "Not compiled here" in f.read_text() or "not compiled" in f.read_text().lower(), f


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
