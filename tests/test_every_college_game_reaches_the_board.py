"""Every college game reaches the board, not the first two dozen ESPN hands
back (engine/sources/cfbdata.whole_slate, fetch_scoreboard;
engine/sources/livescores.fetch_rows for college; cfb_build's feed census).

Ethan, Saturday 7 November 2026: "we are missing so many cfb teams. i dont
see the michigan vs michigan state game on our app." At 6 PM Eastern that
day the college board and the live file each held exactly 25 games, asked
of ESPN with `groups=80&limit=900`: twenty in play, five of the noon
finals, not one of the evening's. The playoff race's standings, built off
the same feed, had Nebraska 1-2 and Penn State 3-3 in November. ESPN cuts
the answer at about two dozen whatever `limit` says; a conference's own
board is under that on any day. What these hold:

  * an FBS answer long enough to have been cut is filled in from each FBS
    conference's own board, joined by event id, the FBS answer's own copy
    first, and the payload says what each conference added;
  * a short answer is returned as it came, and nothing more is asked;
  * a conference that cannot be fetched is named and the rest still join;
  * a game with no FBS team on a conference's page stays out (a group id
    that names an FCS league adds nothing);
  * the day's fetch asks each conference with its own cache file; the live
    board fills in the same way, its conference pages held at least a
    minute, and the NFL's live board asks once, as before;
  * the college board records how its slate was gathered.

Run directly: `python3 tests/test_every_college_game_reaches_the_board.py`
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.sources import cfbdata, livescores                     # noqa: E402
from engine.sources.fetch import DataUnavailable                    # noqa: E402

CONF = {"ACC": "1", "Big 12": "4", "Big Ten": "5", "SEC": "8", "MAC": "15",
        "Sun Belt": "37", "American": "151", "FCS": "22"}


def _side(abbr, conf, home):
    return {"homeAway": "home" if home else "away", "score": "0",
            "team": {"abbreviation": abbr, "displayName": abbr, "id": abbr.lower(),
                     "conferenceId": CONF[conf]}}


def _ev(eid, away, home, conf="Sun Belt", away_conf=None, when="2026-11-07T20:30Z",
        state="in"):
    return {"id": str(eid), "date": when,
            "status": {"type": {"state": state, "completed": state == "post"}},
            "competitions": [{"competitors": [_side(home, conf, True),
                                              _side(away, away_conf or conf, False)]}]}


def _fbs_answer(n=25):
    """ESPN's cut answer: n games, one of them a Big Ten game."""
    evs = [_ev(i, f"A{i}", f"H{i}") for i in range(1, n)]
    evs.insert(2, _ev(900, "RUTG", "WIS", "Big Ten"))
    return {"leagues": [{"abbreviation": "NCAAF"}], "events": evs}


MICH = _ev(100, "MSU", "MICH", "Big Ten", when="2026-11-08T00:30Z", state="pre")
PAGES = {
    "5": {"events": [MICH, _ev(900, "RUTG", "WIS", "Big Ten")]},     # one new, one already in
    "8": {"events": [_ev(101, "AUB", "UGA", "SEC", when="2026-11-08T00:00Z", state="pre")]},
    "15": {"events": [_ev(102, "BALL", "OHIO", "MAC", when="2026-11-07T17:00Z", state="post")]},
}


def _asker(pages, calls=None, fail=()):
    def ask(gid):
        if calls is not None:
            calls.append(gid)
        if gid in fail:
            raise DataUnavailable(f"group {gid} refused")
        return pages.get(gid, {"events": []})
    return ask


def test_a_cut_fbs_answer_is_filled_from_each_conference():
    board = _fbs_answer()
    calls = []
    out = cfbdata.whole_slate(board, _asker(PAGES, calls))
    assert calls == list(cfbdata.FBS_CONFERENCE_GROUPS), calls
    ids = [e["id"] for e in out["events"]]
    assert len(ids) == len(set(ids)) == 28, ids
    assert ids[:25] == [e["id"] for e in board["events"]], "the FBS answer first, in its order"
    dup = next(e for e in out["events"] if e["id"] == "900")
    assert dup is board["events"][2], "the FBS answer's own copy is kept"
    assert out["_asked"] == {"fbs": 25, "added": {"5": 1, "8": 1, "15": 1}, "missed": []}
    assert out["leagues"] == board["leagues"]
    games = cfbdata.parse_scoreboard(out)
    assert ("MSU", "MICH") in {(g["away"], g["home"]) for g in games}
    mich = next(g for g in games if g["home"] == "MICH")
    assert mich["date"] == "2026-11-07", "7:30 PM Eastern is Saturday's game"
    assert board["events"][0]["id"] == "1" and len(board["events"]) == 25, "the answer is not changed"


def test_a_short_answer_asks_nothing():
    board = {"events": [_ev(i, f"A{i}", f"H{i}") for i in range(cfbdata.SCOREBOARD_CUT_AT - 1)]}
    calls = []
    assert cfbdata.whole_slate(board, _asker(PAGES, calls)) is board and calls == []
    assert cfbdata.whole_slate({}, _asker(PAGES, calls)) == {} and calls == []


def test_a_conference_that_fails_is_named_and_the_rest_still_join():
    out = cfbdata.whole_slate(_fbs_answer(), _asker(PAGES, fail=("4", "8")))
    assert out["_asked"]["missed"] == ["4", "8"]
    assert out["_asked"]["added"] == {"5": 1, "15": 1}
    assert "100" in {e["id"] for e in out["events"]}


def test_a_game_with_no_fbs_team_stays_out():
    pages = {"18": {"events": [
        _ev(200, "MONT", "MTST", "FCS"),                         # two FCS schools: not ours
        _ev(201, "NDSU", "ND", "FCS", away_conf="FCS"),          # still FCS v FCS
        {"id": "202", "competitions": [{"competitors": [
            {"homeAway": "home", "team": {"abbreviation": "ND", "id": "nd",
                                          "conferenceId": "18"}},
            {"homeAway": "away", "team": {"displayName": "Navy FCS", "id": "x",
                                          "conferenceId": "22"}}]}],
         "date": "2026-11-07T19:30Z", "status": {"type": {"state": "pre"}}},
        "not an event", {"competitions": []}]}}
    out = cfbdata.whole_slate(_fbs_answer(), _asker(pages))
    new = {e["id"] for e in out["events"]} - {e["id"] for e in _fbs_answer()["events"]}
    assert new == {"202"}, new
    assert "20" not in cfbdata.FBS_CONFERENCE_GROUPS, "an unconfirmed id is not asked"
    assert set(cfbdata.FBS_CONFERENCE_GROUPS) <= set(cfbdata.CONFERENCE_IDS)


def test_the_days_fetch_asks_each_conference_with_its_own_cache():
    asked = []

    def fetch(url, cache, ttl=0, user_agent=None, **kw):
        asked.append((url, cache, ttl))
        if "groups=80" in url:
            return _fbs_answer()
        gid = url.split("groups=")[1].split("&")[0]
        return PAGES.get(gid, {"events": []})

    saved = cfbdata.fetch_json
    cfbdata.fetch_json = fetch
    try:
        out = cfbdata.fetch_scoreboard("2026-11-07", ttl=300)
        first = asked[0]
        assert first[0] == (f"{cfbdata.SCOREBOARD}?dates=20261107&groups=80&limit=900")
        assert first[1] == "espn_cfb_20261107.json"
        rest = asked[1:]
        assert [u for u, _c, _t in rest] == [
            f"{cfbdata.SCOREBOARD}?dates=20261107&groups={g}&limit=900"
            for g in cfbdata.FBS_CONFERENCE_GROUPS]
        assert [c for _u, c, _t in rest] == [f"espn_cfb_20261107_g{g}.json"
                                            for g in cfbdata.FBS_CONFERENCE_GROUPS]
        assert {t for _u, _c, t in asked} == {300}
        assert len(out["events"]) == 28 and out["_asked"]["fbs"] == 25
        # A quiet Tuesday: one ask.
        asked.clear()
        cfbdata.fetch_json = lambda url, cache, ttl=0, user_agent=None, **kw: (
            asked.append(url) or {"events": [_ev(1, "A", "B")]})
        assert len(cfbdata.fetch_scoreboard("2026-11-10")["events"]) == 1 and len(asked) == 1
    finally:
        cfbdata.fetch_json = saved


def test_the_live_board_fills_in_the_same_way():
    asked = []

    def fetch_text(url, cache, ttl=0, user_agent=None, **kw):
        asked.append((url, cache, ttl))
        if "/nfl/" in url:
            return json.dumps({"events": [_ev(7, "KC", "DEN")]})
        if "groups=80" in url:
            return json.dumps(_fbs_answer())
        gid = url.split("groups=")[1].split("&")[0]
        return json.dumps(PAGES.get(gid, {"events": []}))

    saved = livescores.fetch_text
    livescores.fetch_text = fetch_text
    try:
        rows = livescores.fetch_rows("cfb", ttl=30)
        assert ("MSU", "MICH") in {(r["away"], r["home"]) for r in rows}, rows[:3]
        assert len(rows) == 28
        base = livescores.ESPN_SCOREBOARD["cfb"]
        assert asked[0] == (base + livescores.SCOREBOARD_QUERY["cfb"],
                            "espn_cfb_scoreboard.json", 30)
        groups = asked[1:]
        assert [u for u, _c, _t in groups] == [f"{base}?groups={g}&limit=900"
                                              for g in cfbdata.FBS_CONFERENCE_GROUPS]
        assert {c for _u, c, _t in groups} == {f"espn_cfb_scoreboard_g{g}.json"
                                               for g in cfbdata.FBS_CONFERENCE_GROUPS}
        assert {t for _u, _c, t in groups} == {livescores.CFB_GROUP_TTL} and livescores.CFB_GROUP_TTL >= 60
        asked.clear()
        assert len(livescores.fetch_rows("nfl", ttl=30)) == 1 and len(asked) == 1, asked
    finally:
        livescores.fetch_text = saved


def test_the_college_board_records_how_its_slate_was_gathered():
    src = (ROOT / "cfb_build.py").read_text(encoding="utf-8")
    i = src.index('out["feed"] = {"listed": listed, "kept": len(games)}')
    assert 'out["feed"]["asked"] = board["_asked"]' in src[i:i + 600]


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
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
