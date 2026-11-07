"""A live game on the iPhone's lock screen and in its Dynamic Island
(engine/gameactivity, deploy/ios/native GameActivity, web/js/detail.js
lockGameHTML; Ethan, 2026-10-29: "users come back to the app ... when
there's live games going on").

What these hold:

  * the app's GameAttributes.ContentState is the box's `state`, field for
    field, and the plugin builds it from the same keys;
  * a member keeps at most MAX_GAMES games, a token that is not hex or a
    game that is not one is refused, and only a member can keep one (the
    server answers 401 signed out);
  * the pass sends a game its new score only when it changed, ends it at
    the final and forgets it, forgets a game Apple says is gone, and costs
    nothing (sends nothing, makes no table) when nobody kept a game or
    there is no Apple key;
  * the page offers it only in the iOS app, signed in, live or within an
    hour and a half of the start, never once final; account deletion and
    the privacy policy both name the table; never a pick on the card.

Run directly: `python3 tests/test_a_live_game_on_the_lock_screen.py`
"""
import json
import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import gameactivity as GA                              # noqa: E402

NATIVE = ROOT / "deploy" / "ios" / "native"
NOW = 1_760_000_000.0
READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731


def _swift_fields(src, struct):
    at = src.index(f"struct {struct}")
    body = src[at:src.index("\n    }", at)] if "ContentState" in struct else src[at:src.index("\n}", at)]
    return re.findall(r"(?:let|var) (\w+): ", body)


def _game(state="live", away=10, home=14, period="3rd", clock="4:12", detail="2nd & 7 at DEN 45", poss="KC"):
    return {"event_id": "401", "home": "KC", "away": "DEN",
            "live": {"state": state, "away_score": away, "home_score": home, "period": period, "clock": clock,
                     "detail": detail, "possession": poss, "start_time": "2026-10-29T00:20:00Z"}}


def _board(tmp, games):
    p = Path(tmp) / "live_nfl.json"
    p.write_text(json.dumps({"games": games}))
    return Path(tmp)


def test_the_app_draws_what_the_box_sends():
    s = GA.state(_game())
    assert s == {"away": 10, "home": 14, "status": "live", "clock": "3rd 4:12", "last": "2nd & 7 at DEN 45",
                 "poss": "KC"}, s
    swift = (NATIVE / "Shared" / "GameAttributes.swift").read_text()
    assert _swift_fields(swift, "ContentState") == list(s), "the Swift ContentState and gameactivity.state disagree"
    plug = (NATIVE / "App" / "GameActivityPlugin.swift").read_text()
    for k in s:
        assert f's["{k}"]' in plug, k
    assert GA.state(_game(state="final"))["clock"] == "Final" and GA.state(_game(state="final"))["poss"] == ""
    pre = GA.state(_game(state="pre", detail="Thu 8:15 PM", away=0, home=0))
    assert pre["status"] == "pre" and pre["clock"] == "Thu 8:15 PM" and pre["last"] == ""
    assert "GameActivityPlugin()" in (NATIVE / "App" / "MainViewController.swift").read_text()
    assert "GameLiveActivity()" in (NATIVE / "Widget" / "QellysWidgets.swift").read_text()


def test_what_a_member_may_keep():
    conn = sqlite3.connect(":memory:")
    for i in range(GA.MAX_GAMES):
        assert GA.add(conn, 1, "nfl", f"g{i}", "a" * 64, now=NOW)[0] == 200
    code, out = GA.add(conn, 1, "nfl", "g9", "a" * 64, now=NOW)
    assert code == 400 and "most" in out["error"]
    assert GA.add(conn, 1, "nfl", "g0", "b" * 64, now=NOW)[0] == 200, "the same game again is a new token, not a sixth"
    assert GA.add(conn, 2, "nfl", "g1", "not hex", now=NOW)[0] == 400
    assert GA.add(conn, 2, "soccer", "g1", "a" * 64, now=NOW)[0] == 400
    assert GA.add(conn, 2, "nfl", "../etc", "a" * 64, now=NOW)[0] == 400
    assert GA.remove(conn, 1, "nfl", "g0")[0] == 200
    assert conn.execute("SELECT COUNT(*) FROM push_game_activities WHERE user_id = 1").fetchone()[0] == GA.MAX_GAMES - 1


def test_the_pass_sends_changes_ends_finals_and_forgets_the_gone():
    conn = sqlite3.connect(":memory:")
    GA.add(conn, 1, "nfl", "401", "a" * 64, now=NOW)
    sent = []

    def live(token, state, cfg, event="update", now=None):
        sent.append((event, dict(state)))
        return 200
    with tempfile.TemporaryDirectory() as d:
        data = _board(d, [_game()])
        out = GA.update_pass(conn, data_dir=data, cfg={"x": 1}, live=live, now=NOW, log=lambda *a: None)
        assert out["sent"] == 1 and sent[-1][0] == "update" and sent[-1][1]["home"] == 14
        GA.update_pass(conn, data_dir=data, cfg={"x": 1}, live=live, now=NOW + 20, log=lambda *a: None)
        assert len(sent) == 1, "nothing changed, nothing sent"
        _board(d, [_game(home=21, detail="KC TD")])
        GA.update_pass(conn, data_dir=data, cfg={"x": 1}, live=live, now=NOW + 40, log=lambda *a: None)
        assert len(sent) == 2 and sent[-1][1]["home"] == 21
        _board(d, [_game(state="final", home=24)])
        out = GA.update_pass(conn, data_dir=data, cfg={"x": 1}, live=live, now=NOW + 60, log=lambda *a: None)
        assert out["ended"] == 1 and sent[-1][0] == "end" and sent[-1][1]["status"] == "final"
        assert conn.execute("SELECT COUNT(*) FROM push_game_activities").fetchone()[0] == 0, "forgotten at the final"
        GA.add(conn, 1, "nfl", "401", "a" * 64, now=NOW)
        _board(d, [_game(home=3)])
        GA.update_pass(conn, data_dir=data, cfg={"x": 1}, live=lambda *a, **k: 410, now=NOW, log=lambda *a: None)
        assert conn.execute("SELECT COUNT(*) FROM push_game_activities").fetchone()[0] == 0, "Apple said it is gone"
        GA.add(conn, 1, "nfl", "401", "a" * 64, now=NOW - GA.GAME_S - 1)
        GA.update_pass(conn, data_dir=data, cfg={"x": 1}, live=live, now=NOW, log=lambda *a: None)
        assert conn.execute("SELECT COUNT(*) FROM push_game_activities").fetchone()[0] == 0, "twelve hours at most"


def test_nothing_without_a_game_kept_or_an_apple_key():
    conn = sqlite3.connect(":memory:")
    calls = []
    assert GA.update_pass(conn, cfg={"x": 1}, live=lambda *a, **k: calls.append(1)) == \
        {"games": 0, "sent": 0, "ended": 0, "gone": 0}
    assert not conn.execute("SELECT name FROM sqlite_master WHERE name='push_game_activities'").fetchall(), \
        "looking makes no table"
    GA.add(conn, 1, "nfl", "401", "a" * 64, now=NOW)
    GA.update_pass(conn, cfg={}, live=lambda *a, **k: calls.append(1), now=NOW, log=lambda *a: None)
    assert not calls, "no Apple key, nothing sent"


def test_the_server_page_and_the_policy():
    srv = READ("server.py")
    at = srv.index('if path == "game-activity":')
    block = srv[at:at + 900]
    assert '"sign in first"' in block and "GA.remove(" in block and "GA.add(" in block
    assert '"game-activity"' in srv[srv.index('if path not in ("subscribe"'):][:200]
    launch = READ("launch.py")
    assert "_ga.run_once()" in launch and 'target=_game_activity_watcher' in launch
    assert '"push_game_activities"' in READ("engine", "accounts.py")
    priv = READ("web", "privacy.html")
    assert "<code>push_game_activities</code>" in priv and "a game you put" in priv
    det = READ("web", "js", "detail.js")
    fn = det[det.index("function lockGameHTML("):det.index("\n}\n", det.index("function lockGameHTML("))]
    assert "gameLockPlugin()" in fn and "_acctUser && _acctUser.signed_in" in fn
    assert 'st === "final"' in fn and "90 * 6e4" in fn
    assert "lockGameHTML(state.sport, row)" in det and "lockGameHTML(league, {" in det
    assert '"/api/push/game-activity"' in det
    # The card shows the score, the clock and the situation: no chance, no pick.
    w = (NATIVE / "Widget" / "GameLiveActivity.swift").read_text()
    assert "chance" not in w.lower() and "prob" not in w.lower(), "the card never carries our number"
    assert set(GA.state(_game())) == {"away", "home", "status", "clock", "last", "poss"}


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
