"""Kickoff for your teams, each in its own league (engine/kickoffs,
engine/alerts.team_hit; Ethan, 2026-10-28: "keep building and adding more
features ... we want to keep user retainment").

  * A new switch on Alerts, "My teams' games, 10 minutes before they
    start": a followed team's game about to begin, once, a tap into it.
  * A followed team is in its own league: the page keeps "nfl:MIA" in the
    account's synced settings, so a Dolphins fan's "MIA" is not the Heat.
    A bare watch counts for kickoff only when one league uses the letters.
  * The same rule now holds for big moments and final scores, which used to
    tell a Dolphins fan about every Heat game.
  * A bell rung for the game speaks instead; a game under way says nothing.

Run directly: `python3 tests/test_kickoff_for_your_teams.py`
"""
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import accounts as A                                 # noqa: E402
from engine import alerts as AL                                  # noqa: E402
from engine import finals as FN                                  # noqa: E402
from engine import gamechat as GC                                # noqa: E402
from engine import kickoffs as KO                                # noqa: E402
from engine import pushalerts as PA                              # noqa: E402
from engine import pushmine as PM                                # noqa: E402

NOW = dt.datetime(2026, 11, 1, 17, 51, tzinfo=dt.timezone.utc).timestamp()   # Sunday, 12:51 p.m. Eastern


def _iso(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _boards(tmp):
    d = Path(tmp)
    game = lambda ev, away, home, state, start: {"event_id": ev, "away": away, "home": home,   # noqa: E731
                                                 "live": {"state": state, "start_time": _iso(start)}}
    (d / "live_nfl.json").write_text(json.dumps({"games": [
        game("401", "BUF", "MIA", "pre", NOW + 9 * 60),
        game("402", "CHI", "GB", "pre", NOW + 9 * 60),
        game("403", "NYJ", "NE", "live", NOW - 5 * 60),
        game("404", "LV", "KC", "pre", NOW + 3 * 3600)]}))
    (d / "live_nba.json").write_text(json.dumps({"games": [
        game("501", "BOS", "MIA", "scheduled", NOW + 8 * 60)]}))
    (d / "live_nhl.json").write_text(json.dumps({"games": [
        game("601", "ANA", "LA", "pre", NOW + 7 * 60)]}))
    return d


def _db():
    conn = A.connect(os.path.join(tempfile.mkdtemp(), "acc.db"))
    PM.ensure_tables(conn)
    GC.ensure_tables(conn)
    ids = []
    for who in ("amy", "bob", "cal", "dee", "eve", "fay", "gus"):
        _, out = A.create_user(conn, f"{who}@example.com", "correct-horse-battery", confirmed=True)
        ids.append(out["id"])
    return conn, ids


def _follow(conn, uid, teams=(), watches=(), topics=("kickoff",)):
    if teams:
        A.save_sections(conn, uid, {"settings": {"ts": 1, "data": {"teams": list(teams)}}})
    for w in watches:
        assert AL.add_watch(conn, uid, "team", w)[0] == 200
    assert PA.subscribe(conn, f"{uid:064x}", "apns", user_id=uid, topics=topics)[0] == 200


def _told(conn, uid):
    return [tuple(r) for r in conn.execute("SELECT id, title, body, url FROM push_mine WHERE user_id=? "
                                           "AND kind='kickoff' ORDER BY id", (uid,))]


def test_your_teams_hear_ten_minutes_out_in_their_own_league():
    with tempfile.TemporaryDirectory() as tmp:
        d = _boards(tmp)
        conn, (amy, bob, cal, dee, eve, fay, gus) = _db()
        _follow(conn, amy, teams=["nfl:MIA"], watches=["MIA"])      # the follow flow keeps both
        _follow(conn, bob, watches=["GB"])                           # a bare watch only the NFL uses
        _follow(conn, cal, watches=["MIA"])                          # bare and ambiguous: no league said
        _follow(conn, dee, teams=["nba:BOS"])
        _follow(conn, eve, teams=["nfl:GB"])
        conn.execute("INSERT INTO chat_reminders (user_id, room, start_at, title) VALUES (?,?,?,?)",
                     (eve, "nfl_402", NOW + 540, "CHI @ GB"))       # eve rang the game's own bell
        _follow(conn, fay, teams=["nfl:GB"], topics=("finals",))    # the switch is off on her phone
        _follow(conn, gus, teams=["nhl:LAK"])                        # ESPN spells the Kings "LA"
        assert KO.kickoff_pass(conn, d, now=NOW) == 4
        assert _told(conn, amy) == [("kickoff:nfl_401", "BUF @ MIA starts in 9 minutes",
                                     "Tap for the game, its chat and Call it.", "/#pbp/nfl/401")], \
            "the Dolphins' game, not the Heat's"
        assert [r[1] for r in _told(conn, bob)] == ["CHI @ GB starts in 9 minutes"]
        assert _told(conn, cal) == [], "MIA without a league is three teams: no kickoff push"
        assert [r[1] for r in _told(conn, dee)] == ["BOS @ MIA starts in 8 minutes"], "the away side too"
        assert _told(conn, eve) == [] and _told(conn, fay) == []
        assert [r[1] for r in _told(conn, gus)] == ["ANA @ LA starts in 7 minutes"]
        assert KO.kickoff_pass(conn, d, now=NOW + 60) == 0, "once a game"
        assert KO.kickoff_pass(conn, d, now=NOW + 3 * 3600 - 11 * 60) == 0, "eleven minutes out: not yet"
        assert KO.kickoff_pass(conn, d, now=NOW + 3 * 3600 - 10 * 60) == 0, "nobody follows KC or LV"
        assert PM.TTL_S["kickoff"] == 15 * 60 and "kickoff" in PA.PERSONAL


def test_one_league_or_none_for_a_bare_abbreviation():
    assert KO._one_league("GB") == "nfl" and KO._one_league("LAK") == "nhl"
    assert KO._one_league("MIA") is None and KO._one_league("LA") is None, "the Rams, the Sparks, the Kings"
    assert KO._one_league("OSU") is None, "college is not a static map"


def test_big_moments_and_finals_keep_to_the_league_you_named():
    nba = {"league": "nba", "home": "MIA", "away": "BOS", "players": []}
    nfl = {"league": "nfl", "home": "MIA", "away": "BUF", "players": []}
    w = [{"kind": "team", "value": "MIA"}]
    dolphins = {"MIA": {"nfl"}}
    assert FN._follows(w, nfl, dolphins) and not FN._follows(w, nba, dolphins), "a Dolphins fan, not the Heat"
    assert FN._follows(w, nba) and FN._follows(w, nfl), "a watch that never named a league: as before"
    play = {"players": []}
    assert PM._follows(w, nfl, play, dolphins) and not PM._follows(w, nba, play, dolphins)
    assert AL.team_hit("mia", "NFL", {"MIA", "BUF"}, dolphins) and not AL.team_hit("GB", "nfl", {"MIA"}, None)
    conn, (amy, bob, *_rest) = _db()
    A.save_sections(conn, amy, {"settings": {"ts": 1, "data": {"teams": ["nfl:MIA", "nba:mia", "xfl:DC", "GB", 7]}}})
    assert AL.team_leagues(conn, amy) == {"MIA": {"nfl", "nba"}}, "only the leagues we know, spelled ours"
    assert AL.team_leagues(conn, bob) == {}
    conn.execute("UPDATE user_data SET payload='not json' WHERE user_id=?", (amy,))
    assert AL.team_leagues(conn, amy) == {}


def test_the_alerts_page_the_loop_and_the_policy():
    from _app import app_js                    # the Alerts page loads on first use (js/more.js)
    app = app_js()
    acct = (ROOT / "web" / "js" / "account.js").read_text(encoding="utf-8")
    assert 'box("kickoff", "My teams’ games, 10 minutes before they start", !signedIn),' in app
    assert app.index('box("kickoff"') < app.index('box("clutch"') < app.index('box("finals"'), "start, middle, end"
    assert 't === "bets" || t === "kickoff" || t === "clutch"' in app and 't === "bets" || t === "kickoff" || t === "clutch"' in acct
    pm = (ROOT / "engine" / "pushmine.py").read_text(encoding="utf-8")
    assert 'told += _ko.kickoff_pass(conn, Path(web) / "data", now=t)' in pm
    assert pm.index("_gc.reminders_pass(conn, now=t)") < pm.index("_ko.kickoff_pass("), "the bells go first"
    policy = " ".join((ROOT / "web" / "privacy.html").read_text(encoding="utf-8").split())
    assert ("a game of a team you follow starting in about ten minutes (the two teams; which league a team is in "
            "comes from the teams you followed, kept with your account's settings)") in policy


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
