"""Your games in your calendar: your teams this week and every game in a
parlay you saved, as a feed a phone's calendar subscribes to.

Ethan, 2026-10-24: "build everything ... including all the ideas" — docs/
IDEAS.md 12 (engine/calfeed). What these hold:

  - the address is the key (a calendar app cannot sign in): it verifies,
    a wrong one does not, and a new link stops the old one;
  - the games are the member's: their followed teams off the boards' free
    schedule, and the games of their open saved parlays with their own legs
    in the notes — never a pick from the paid half;
  - the file is a calendar every app reads: CRLF, folded at 75 octets,
    escaped text, Eastern kickoffs as the right UTC moment on both sides of
    the clocks changing, a game over hours ago left out;
  - the server answers the feed by address alone, 404s anything else, asks
    for a session for the link, and the Settings panel carries the row.

    python3 tests/test_your_games_in_your_calendar.py
"""
import datetime as dt
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_DIR = tempfile.mkdtemp()
os.environ["QB_ACCOUNTS_DB"] = os.path.join(_DIR, "accounts.db")
os.environ["QB_UNSUB_KEY"] = "calendar-test-key-" + "x" * 32
os.environ["QB_SITE_URL"] = "https://qellysbook.example"

from engine import accounts as A                                  # noqa: E402
from engine import calfeed as CF                                  # noqa: E402

READ = lambda *p: (ROOT.joinpath(*p)).read_text(encoding="utf-8")  # noqa: E731
GOOD = "correct horse battery"
NOW = dt.datetime(2026, 10, 18, 12, 0, tzinfo=dt.timezone.utc)
BOARDS = {"nfl": {"label": "NFL", "games": [
    {"home": "LA", "away": "BUF", "date": "2026-10-18", "kickoff": "13:00"},
    {"home": "KC", "away": "DEN", "date": "2026-10-18", "kickoff": "16:25"},
    {"home": "GB", "away": "DET", "date": "2026-10-18", "kickoff": "20:20"},
    {"home": "DET", "away": "MIN", "date": "2026-10-11", "kickoff": "13:00"},
    {"home": "NYG", "away": "DAL", "date": "2026-10-19", "kickoff": "20:15"}]}}


def _ml(team, game):
    return {"sport": "nfl", "player": "", "team": team, "game": game, "market": "moneyline", "side": "team",
            "line": 0, "odds": -140, "text": f"{team} ML"}


_n = [0]


def _member(teams=(), slips=()):
    _n[0] += 1
    conn = A.connect()
    try:
        code, out = A.create_user(conn, f"cal{_n[0]}@example.com", GOOD, confirmed=True)
        assert code == 200, out
        secs = {"settings": {"ts": 1, "data": {"teams": list(teams)}}}
        if slips:
            secs["mybets"] = {"ts": 1, "data": {"rows": list(slips), "deleted": []}}
        A.save_sections(conn, out["id"], secs)
        return out["id"]
    finally:
        conn.close()


def test_the_address_is_the_key_and_a_new_link_stops_the_old():
    uid = _member()
    conn = A.connect()
    try:
        tok = CF.token_for(conn, uid)
        assert CF.token_for(conn, uid) == tok, "made once, the same after"
        assert CF.user_for(conn, tok) == uid
        bad = tok[:-1] + ("A" if tok[-1] != "A" else "B")
        for wrong in (bad, f"{uid + 1}.{tok.split('.')[1]}", "", "x.y", tok + ".ics", "../" + tok):
            assert CF.user_for(conn, wrong) is None, wrong
        new = CF.token_for(conn, uid, new=True)
        assert new != tok and CF.user_for(conn, new) == uid and CF.user_for(conn, tok) is None
    finally:
        conn.close()


def test_the_games_are_yours_and_never_a_pick():
    slip = {"id": "1760000000700", "book": "DraftKings", "desc": "two-leg", "stake": 20, "odds": 170,
            "result": "pending", "src": "slip", "legs": [_ml("LA", "BUF @ LA"), _ml("KC", "DEN @ KC")]}
    done = dict(slip, id="1760000000701", result="win", legs=[_ml("NYG", "DAL @ NYG")])
    uid = _member(teams=["nfl:DET", "nba:BOS"], slips=[slip, done, {"id": "9", "desc": "by hand", "result": "pending"}])
    boards = json.loads(json.dumps(BOARDS))
    boards["nfl"]["recommendations"] = [{"player": "Amon-Ra St. Brown", "market": "receptions", "line": 6.5}]
    conn = A.connect()
    try:
        evs = CF.events(conn, uid, boards, now=NOW)
    finally:
        conn.close()
    titles = [e["title"] for e in evs]
    assert titles == ["BUF @ LA — your parlay", "DEN @ KC — your parlay", "DET @ GB — your team"], titles
    assert evs[0]["notes"].startswith("Your legs: LA ML.") and evs[0]["url"] == "/?sport=nfl#live"
    blob = json.dumps([dict(e, start=str(e["start"])) for e in evs])
    assert "St. Brown" not in blob and "receptions" not in blob, "nothing from the paid half"
    assert "NYG" not in blob, "a settled parlay's games are not yours to follow"
    assert all(e["start"] >= NOW - dt.timedelta(hours=6) for e in evs), "a game over hours ago is left out"


def test_the_file_is_a_calendar_every_app_reads():
    start = CF._start("2026-10-18", "13:00")
    assert start == dt.datetime(2026, 10, 18, 17, 0, tzinfo=dt.timezone.utc), "13:00 Eastern daylight"
    assert CF._start("2026-11-08", "13:00") == dt.datetime(2026, 11, 8, 18, 0, tzinfo=dt.timezone.utc), \
        "and Eastern standard after the clocks change"
    assert CF._start("2026-10-18", "TBD") is None and CF._start("soon", "13:00") is None
    long = "W" * 60 + "é" * 30
    evs = [{"uid": "nfl-2026-10-18-BUF-LA@qellysbook.com", "start": start, "minutes": 195,
            "title": "BUF @ LA — your parlay; and, more", "notes": "Your legs: LA ML.\nSecond line " + long,
            "url": "/?sport=nfl#live"}]
    text = CF.ics(evs, site="https://qellysbook.example", now=NOW)
    assert text.startswith("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n") and text.endswith("END:VCALENDAR\r\n")
    assert "\n" not in text.replace("\r\n", ""), "every line ends CRLF"
    for line in text.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75, line
    unfolded = text.replace("\r\n ", "")
    assert "DTSTART:20261018T170000Z" in unfolded and "DTEND:20261018T201500Z" in unfolded
    assert "SUMMARY:BUF @ LA — your parlay\\; and\\, more" in unfolded
    assert "DESCRIPTION:Your legs: LA ML.\\nSecond line " + long in unfolded
    assert "URL:https://qellysbook.example/?sport=nfl#live" in unfolded
    assert "REFRESH-INTERVAL;VALUE=DURATION:PT3H" in unfolded


def test_the_server_answers_by_address_and_settings_carries_the_row():
    sys.path.insert(0, str(ROOT / "tests"))
    import rendercheck
    uid = _member(teams=["nfl:DET"])
    conn = A.connect()
    try:
        tok = CF.token_for(conn, uid)
    finally:
        conn.close()
    srv, port = rendercheck._serve()
    base = f"http://127.0.0.1:{port}"

    def get(path, method="GET"):
        req = urllib.request.Request(base + path, method=method, data=b"{}" if method == "POST" else None,
                                     headers={"Content-Type": "application/json"} if method == "POST" else {})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.headers.get("Content-Type"), r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get("Content-Type"), e.read().decode()
    try:
        code, ctype, body = get(f"/api/calendar/{tok}.ics")
        assert code == 200 and ctype.startswith("text/calendar"), (code, ctype, body[:200])
        assert body.startswith("BEGIN:VCALENDAR") and "X-WR-CALNAME:Qellys — your games" in body
        assert get(f"/api/calendar/{tok[:-2]}xx.ics")[0] == 404
        assert get(f"/api/calendar/{tok}")[0] == 404
        assert get("/api/calendar/link")[0] == 401, "the link needs a session"
        assert get("/api/calendar/new", "POST")[0] == 401
    finally:
        srv.shutdown()
    app = READ("web", "js", "app.js")
    assert '<div class="set-row" id="set-cal">' in app and "${calRowHTML()}" in app
    at = app.index("function bindSettings() {")
    assert "bindCalRow();" in app[at:at + 300]
    assert '"/api/calendar/new"' in app and '"/api/calendar/link"' in app and "_calLink.webcal" in app


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
