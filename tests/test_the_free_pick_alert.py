"""Today's free pick is up: the Pick of the Day as an alert, once a day, for a
phone that asked (engine/pushalerts.potd_due).

Ethan, 2026-11-03, on the 30 October audit's list — "the free Pick of the
Day travels: an opt-in daily 'today's free pick is up' alert" — "do all of
them". What these hold:

  * it is said on a day the day's top pick is a bet, once that day, off the
    public copy of the file (a lean is never announced, paywall on or off),
    and never for yesterday's file;
  * it names the league and the Pick of the Day's own record — never the
    pick, its price or its side;
  * it is asked for: a phone that names no kinds gets the two it always
    had, a phone signed out may ask for it, and only a phone that asked
    hears it; a reached weekly limit stops it like every promotional alert;
  * the Pick of the Day page and the Alerts page carry its switch, and the
    privacy policy says what it says.

Run directly: `python3 tests/test_the_free_pick_alert.py`
"""
import datetime as dt
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import limits as LM                                  # noqa: E402
from engine import pushalerts as PA                              # noqa: E402
from engine import webpush as W                                  # noqa: E402

TODAY = dt.date(2026, 11, 3)
FCM = "https://fcm.googleapis.com/fcm/send/potd123:APA91bHxyz"
PICK = {"player": "Secret Player", "team": "BOS", "opponent": "NYK", "market": "points", "side": "over",
        "line": 24.5, "odds": -110, "book": "FanDuel", "sport": "nba"}
READ = lambda *p: (ROOT.joinpath(*p)).read_text(encoding="utf-8")  # noqa: E731


def _web(top=None, rec=None):
    web = Path(tempfile.mkdtemp())
    (web / "data").mkdir()
    if top is not None:
        (web / "data" / "day_top_pick.json").write_text(json.dumps(top), encoding="utf-8")
    if rec is not None:
        (web / "data" / "record.json").write_text(json.dumps(rec), encoding="utf-8")
    return web


def _top(**kw):
    out = {"date": TODAY.isoformat(), "sport": "nba", "pick": dict(PICK),
           "verdict": {"call": "bet", "stake": 1.0, "why": ""}, "runners_up": [], "leagues": {}}
    out.update(kw)
    return out


REC = {"potd": {"wins": 31, "losses": 22, "pushes": 1, "net_units": 6.42, "settled": 54}}


def _conn():
    c = sqlite3.connect(":memory:")
    PA.ensure_tables(c)
    return c


def test_it_is_said_on_a_day_the_pick_is_a_bet_and_names_the_league_and_the_record():
    got = PA.potd_due([], web=_web(_top(), REC), today=TODAY)
    assert got == {"id": "potd:2026-11-03", "kind": "potd", "league": "",
                   "title": "Today’s free pick is up",
                   "body": "NBA · our one pick of the day, free with its price. 31–22–1 so far, +6.4u.",
                   "url": "/#potd"}, got
    said = json.dumps(got)
    for secret in ("Secret Player", "BOS", "NYK", "24.5", "-110", "FanDuel", "over"):
        assert secret not in said, ("the pick never reaches a lock screen", secret)
    cold = PA.potd_due([], web=_web(_top(sport="cfb"), {"potd": {"wins": 0, "losses": 0}}), today=TODAY)
    assert cold["body"] == "College football · our one pick of the day, free with its price. Every one is graded in public."
    down = PA.potd_due([], web=_web(_top(), {"potd": {"wins": 9, "losses": 12, "net_units": -3.14}}), today=TODAY)
    assert down["body"].endswith("9–12 so far, −3.1u."), "a losing record is said as plainly"


def test_it_is_said_once_a_day_and_never_for_yesterdays_file():
    web = _web(_top(), REC)
    assert PA.potd_due(["potd:2026-11-03"], web=web, today=TODAY) is None, "once"
    assert PA.potd_due([], web=web, today=TODAY + dt.timedelta(days=1)) is None, "yesterday's pick, already said"
    assert PA.potd_due([], web=_web(None), today=TODAY) is None, "no file, nothing"
    assert PA.potd_due([], web=_web(_top(pick=None, sport="", verdict={"call": "no bet"})), today=TODAY) is None


def test_a_lean_is_never_announced_with_the_paywall_on_or_off():
    lean = _top(pick=dict(PICK, below_bar="no league cleared the bar"), verdict={"call": "no bet", "stake": 0.0})
    # With the paywall off the public path holds the full file, lean and all:
    # the alert strips it the way the public copy would.
    assert PA.potd_due([], web=_web(lean, REC), today=TODAY) is None


def test_due_says_it_beside_the_other_two():
    web = _web(_top(), REC)
    (web / "data" / "feed.json").write_text(json.dumps({"events": []}), encoding="utf-8")
    real = PA.gate.board_source
    PA.gate.board_source = lambda p: p
    try:
        got = PA.due({}, web=web, today=TODAY)
        assert [m["id"] for m in got] == ["potd:2026-11-03"], got
        assert PA.due({"sent": ["potd:2026-11-03"]}, web=web, today=TODAY) == []
    finally:
        PA.gate.board_source = real


def test_it_is_asked_for_never_assumed():
    assert PA.KINDS == ("posted", "settled", "potd") and PA.DEFAULT_TOPICS == ("posted", "settled")
    c = _conn()
    code, out = PA.subscribe(c, FCM)
    assert code == 200 and out["topics"] == ["posted", "settled"], "a phone that names no kinds"
    code, out = PA.subscribe(c, FCM + "x", topics=["potd"])
    assert code == 200 and out["topics"] == ["potd"], "signed out, it may ask for this one alone"
    msg = {"kind": "potd", "league": ""}
    assert PA.wants("potd", "nfl", msg), "a phone that follows one league still hears the day's pick"
    assert not PA.wants("posted,settled", "", msg)
    srv = READ("server.py")
    assert 'topics=body.get("topics") or PA.DEFAULT_TOPICS' in srv and "or PA.KINDS" not in srv
    assert "potd" in LM.PROMO, "a reached weekly limit stops it"


def test_only_a_phone_that_asked_hears_it():
    c = _conn()
    PA.subscribe(c, FCM + "both")
    PA.subscribe(c, FCM + "pick", topics=["potd"])
    PA.subscribe(c, FCM + "all", topics=["posted", "settled", "potd"])
    knocked = []

    def knock(endpoint, k, topic=""):
        knocked.append((endpoint, topic))
        return 201
    st = PA.send(c, [PA.potd_due([], web=_web(_top(), REC), today=TODAY)], knock=knock, vapid=W.new_key(),
                 apns_cfg=False)
    assert st["sent"] == 2 and sorted(e for e, _ in knocked) == [FCM + "all", FCM + "pick"], knocked
    assert all(t == "potd-2026-11-03" for _, t in knocked)


def test_the_pages_carry_its_switch_and_the_policy_says_it():
    more = READ("web", "js", "more.js")
    zone = more[more.index("function renderPushZone(note) {"):more.index("\nfunction renderAlerts() {")]
    assert 'box("potd", "Today’s free Pick of the Day is up")' in zone
    assert '((saved && saved.topics) || ["posted", "settled"])' in zone, "off until chosen"
    assert "never a pick on a lock screen" in zone
    page = READ("web", "js", "potd.js")
    assert "function pdAlertHTML()" in page and "return lede + pdAlertHTML() + cards + when + lock;" in page
    import re
    policy = re.sub(r"\s+", " ", READ("web", "privacy.html"))
    assert "that today’s free Pick of the Day is up, in which league, and its record" in policy


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}")
    print(f"\n{sum(1 for n in globals() if n.startswith('test_'))} tests passed.")
