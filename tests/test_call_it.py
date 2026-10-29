"""Call it: before each at-bat or drive, call how it ends; the box grades it
off the game's own deep file (engine/callit).

Ethan, 2026-10-25: "create things I've never even thought of." What these
hold: one unit open at a time, locked once it is under way; a call changes
only while it is open; a result grades every call on it, a void counts for
nobody; the streak and the room's best; the server reads only a league it
plays and an id of digits; the page, the privacy page and account deletion.

    python3 tests/test_call_it.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_DIR = tempfile.mkdtemp()
os.environ["QB_ACCOUNTS_DB"] = os.path.join(_DIR, "accounts.db")

from engine import accounts as A                                  # noqa: E402
from engine import callit as CI                                   # noqa: E402

LIVE = {"state": "live"}


def _mlb(done=0, pitches=0, results=()):
    events = [{"kind": "atbat", "at_bat": i, "event_type": (list(results) + ["field_out"] * done)[i]}
              for i in range(done)]
    return {"league": "mlb", "event_id": "9", "live": dict(LIVE), "events": events,
            "current": {"batter": "Pete Alonso", "pitcher": "Raisel Iglesias", "pitches": pitches}}


def _nfl(ended=(), plays=0, team="KC"):
    return {"league": "nfl", "event_id": "5", "live": dict(LIVE),
            "drives": [{"id": str(i), "result": r} for i, r in enumerate(ended)] + [{"id": "x"}],
            "drive": {"team": team, "plays": plays}}


def test_one_unit_open_locked_once_under_way():
    op = CI.open_unit(_mlb(done=3))
    assert op["unit"] == "ab3" and op["prompt"] == "Pete Alonso up against Raisel Iglesias"
    assert [k for k, _ in op["choices"]] == ["hit", "out", "k", "walk"]
    assert CI.open_unit(_mlb(done=3, pitches=1))["unit"] == "ab3", "open through the first pitch"
    assert CI.open_unit(_mlb(done=3, pitches=2)) is None, "locked from the second"
    nfl = CI.open_unit(_nfl(ended=("Punt", "Touchdown")))
    assert nfl["unit"] == "dr2" and nfl["prompt"] == "KC's drive"
    assert CI.open_unit(_nfl(plays=3)) is None
    assert CI.open_unit(dict(_mlb(), live={"state": "final"})) is None
    assert CI.open_unit({"league": "nfl2", "event_id": "1", "live": LIVE}) is None


def _hoops(plays, state="live"):
    return {"league": "nba", "event_id": "8", "live": {"state": state}, "plays": plays}


def _p(pid, event="Jump Shot", points=0, scoring=False, shot=False):
    return {"id": pid, "event": event, "points": points, "scoring": scoring, "shot": shot}


def test_basketball_calls_the_next_points_and_hockey_the_next_shot():
    assert CI.open_unit(_hoops([]))["unit"] == "sc0", "before any score, the first one"
    plays = [_p("1", points=2, scoring=True), _p("2", "Defensive Rebound")]
    op = CI.open_unit(_hoops(plays))
    assert op["unit"] == "sc1" and [k for k, _ in op["choices"]] == ["three", "two", "ft"]
    assert CI.open_unit(_hoops(plays + [_p("3", "Turnover"), _p("4", "Steal")])) is None, "locked two plays in"
    later = plays + [_p("3", "Turnover"), _p("4", "Free Throw", points=1, scoring=True)]
    assert CI.result_of(_hoops(later), "sc1") == "ft" and CI.result_of(_hoops(plays), "sc1") == ""
    assert CI.result_of(_hoops(later), "sc0") == "two" and CI.result_of(_hoops(later), "sc99") == "void"
    three = plays + [_p("5", "Three Point Jumper", points=3, scoring=True)]
    assert CI.result_of(_hoops(three), "sc1") == "three"
    nhl = lambda rows: {"league": "nhl", "event_id": "4", "live": {"state": "live"}, "plays": rows}  # noqa: E731
    rows = [_p("10", "Faceoff"), _p("11", "Shot", shot=True), _p("12", "Hit")]
    assert CI.open_unit(nhl(rows))["unit"] == "sh11"
    for ev, want in (("Blocked Shot", "block"), ("Missed Shot", "miss"), ("Shot", "save"), ("Goal", "goal")):
        r = _p("13", ev, shot=True, scoring=(ev == "Goal"))
        assert CI.result_of(nhl(rows + [r]), "sh11") == want, ev


def test_a_call_open_when_the_game_ends_is_void():
    conn, (a,) = _users(1)
    try:
        doc = _hoops([_p("1", points=2, scoring=True)])
        assert CI.call(conn, a, doc, "sc1", "three", now=1.0)[0] == 200
        CI.grade(conn, doc)
        assert CI.state(conn, a, doc).get("last") is None, "still open"
        CI.grade(conn, dict(doc, live={"state": "final"}))
        assert CI.state(conn, a, dict(doc, live={"state": "final"}))["last"]["result"] == "void"
    finally:
        conn.close()


def test_how_a_unit_ended():
    doc = _mlb(done=6, results=("single", "strikeout", "walk", "field_error", "grounded_into_double_play", "home_run"))
    assert [CI.result_of(doc, f"ab{i}") for i in range(6)] == ["hit", "k", "walk", "void", "out", "hit"]
    assert CI.result_of(doc, "ab6") == "", "not over yet"
    words = ("Touchdown", "Field Goal", "Punt", "Interception", "Downs", "Missed FG", "End of Half",
             "Fumble Return Touchdown", "Blocked Punt")
    doc = _nfl(ended=words)
    assert [CI.result_of(doc, f"dr{i}") for i in range(len(words))] == \
        ["td", "fg", "punt", "turnover", "turnover", "turnover", "void", "turnover", "turnover"]


_made = [0]


def _users(n):
    conn = A.connect()
    out = []
    for _ in range(n):
        _made[0] += 1
        code, u = A.create_user(conn, f"ci{_made[0]}@example.com", "correct horse battery", confirmed=True)
        assert code == 200, u
        out.append(u["id"])
    return conn, out


def test_calls_change_while_open_grade_once_and_a_void_counts_for_nobody():
    conn, (a, b) = _users(2)
    try:
        doc = _mlb(done=0)
        assert CI.call(conn, a, doc, "ab0", "hit", now=1.0)[0] == 200
        assert CI.call(conn, a, doc, "ab0", "k", now=2.0)[1]["call"] == "k", "changed while open"
        assert CI.call(conn, b, doc, "ab0", "out", now=3.0)[0] == 200
        assert CI.call(conn, a, doc, "ab1", "hit")[0] == 409, "only the unit open now"
        assert CI.call(conn, a, doc, "ab0", "homer")[0] == 400
        assert CI.call(conn, a, _mlb(done=0, pitches=2), "ab0", "hit")[0] == 409, "locked"
        after = _mlb(done=1, results=("strikeout",))
        assert CI.grade(conn, after) == 2
        sa, sb = CI.state(conn, a, after), CI.state(conn, b, after)
        assert sa["last"] == {"unit": "ab0", "call": "k", "result": "k", "right": True}
        assert sb["last"]["right"] is False and sa["game"] == {"right": 1, "total": 1}
        assert sa["streak"] == 1 and sb["streak"] == 0
        assert CI.call(conn, a, after, "ab0", "hit")[0] == 409, "never after"
        CI.call(conn, a, after, "ab1", "hit", now=5.0)
        void = _mlb(done=2, results=("strikeout", "field_error"))
        CI.grade(conn, void)
        sv = CI.state(conn, a, void)
        assert sv["last"]["right"] is None and sv["streak"] == 1 and sv["game"]["total"] == 1, \
            "a void counts for nobody and breaks nobody's streak"
        assert CI.state(conn, None, void)["signed_in"] is False and "mine" not in CI.state(conn, None, void)
    finally:
        conn.close()


def test_the_streak_and_the_rooms_best():
    conn, (a, b) = _users(2)
    try:
        doc = {"league": "nfl", "event_id": "77", "live": dict(LIVE), "drives": [{"id": "x"}],
               "drive": {"team": "KC", "plays": 0}}
        ended = []
        for i, (res, ca, cb) in enumerate((("Touchdown", "td", "punt"), ("Punt", "punt", "punt"),
                                           ("Field Goal", "td", "fg"), ("Punt", "punt", "td"),
                                           ("Touchdown", "td", "td"))):
            CI.call(conn, a, doc, f"dr{i}", ca, now=10.0 + i)
            CI.call(conn, b, doc, f"dr{i}", cb, now=10.5 + i)
            ended.append(res)
            doc = dict(doc, drives=[{"id": str(j), "result": r} for j, r in enumerate(ended)] + [{"id": "x"}])
            CI.grade(conn, doc)
        assert CI.streaks(conn, a) == (2, 2) and CI.streaks(conn, b) == (1, 2)
        st = CI.state(conn, a, doc)
        assert [r["right"] for r in st["board"]] == [4, 3] and st["board"][0]["handle"] == "a fan"
    finally:
        conn.close()


def test_the_server_reads_only_a_league_it_plays_and_an_id_of_digits():
    import server
    with tempfile.TemporaryDirectory() as d:
        keep = server.WEB
        server.WEB = Path(d)
        (Path(d) / "data" / "pbp").mkdir(parents=True)
        (Path(d) / "data" / "pbp" / "mlb_9.json").write_text(json.dumps(_mlb(done=2)))
        out = {}
        h = object.__new__(server.Handler)
        h._send = lambda code, body, kind=".json", headers=None: out.update(code=code, body=json.loads(body))
        h._account = lambda conn: None
        try:
            for bad in ("nfl2/9", "mlb/../x", "mlb/9a", "mlb/", "mlb/12345678901234567", "soccer/1"):
                h._callit(bad)
                assert out["code"] == 404, bad
            h._callit("mlb/9")
            assert out["code"] == 200 and out["body"]["open"]["unit"] == "ab2" and out["body"]["signed_in"] is False
            h._callit("mlb/9", {"unit": "ab2", "call": "hit"})
            assert out["code"] == 401, "a call needs an account"
        finally:
            server.WEB = keep


def test_the_page_the_privacy_page_and_deletion():
    det = (ROOT / "web" / "js" / "detail.js").read_text()
    assert "${pbpCallItHTML(d, league)}" in det
    assert "pbpCallItHTML(d, league) + pbpFootHTML() })) {" in det, "the basketball page draws its own layout"
    for page in ("hoopscast.js", "rinkcast.js"):
        assert '${(ctx && ctx.callit) || ""}' in (ROOT / "web" / "js" / page).read_text(), page
    fn = det[det.index("function ciBodyHTML("):det.index("function ciPaint(")]
    assert "escapeHtml(v.open.prompt)" in fn and "escapeHtml(r.handle)" in fn and "escapeHtml(label)" in fn
    assert 'if (typeof window !== "undefined" && !window._ciBound)' in det
    srv = (ROOT / "server.py").read_text()
    assert 'or parsed.path.startswith("/api/callit/")' in srv
    priv = (ROOT / "web" / "privacy.html").read_text()
    assert "<code>callit_calls</code>" in priv
    acc = (ROOT / "engine" / "accounts.py").read_text()
    assert '"callit_calls",' in acc[acc.index("def delete_user("):acc.index("def export_user(")]
    assert 'out["call_it_calls"] = calls' in acc


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
