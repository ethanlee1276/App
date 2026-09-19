"""The MLB play-by-play page's feed: every pitch, every at-bat, the ball
in flight, and who is up.

Ethan's render, 2026-09-05: the rail reads "Ball · Juan Soto takes a
ball high", "Called Strike", "Foul · 95 MPH fastball", "Lineout to CF ·
Aaron Judge (102.4 MPH, 379 FT)", each with a time; the park animates
the batted ball's arc; the strip under it names the batter and the
pitcher. `pbp.game_events` and `pbp.current_at_bat` are those rows,
composed from the fields the pitch parser has read since it shipped
(`isPitch`, `call.code`, `type.description`, `startSpeed`) and the
at-bat fields the card's strip reads — never from the feed's sentences.

`hitData` and the times are new reads, tolerant by construction; the
fixture carries them in the Stats API's documented shape and
docs/DROPLET_CHECKS.md §2b is the probe that confirms it on a cached
game.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.mlb.sources import pbp                                # noqa: E402

PROSE = "The feed's own sentence about what happened"


def _pitch(n, code, ptype="Four-Seam Fastball", speed=95.1, balls=None,
           strikes=None, in_play=False, hit=None, t="2026-08-28T23:14:05Z"):
    ev = {"isPitch": True, "pitchNumber": n,
          "details": {"type": {"code": "FF", "description": ptype},
                      "call": {"code": code, "description": PROSE},
                      "description": PROSE, "isInPlay": in_play},
          "pitchData": {"startSpeed": speed},
          "startTime": t, "endTime": t}
    if balls is not None:
        ev["count"] = {"balls": balls, "strikes": strikes, "outs": 1}
    if hit:
        ev["hitData"] = hit
    return ev


def _play(ab, inning, half, batter, pitcher, events, event="", rbi=0,
          scoring=False, away=0, home=0):
    return {
        "about": {"atBatIndex": ab, "inning": inning, "halfInning": half,
                  "isScoringPlay": scoring, "startTime": "2026-08-28T23:13:00Z",
                  "endTime": "2026-08-28T23:14:30Z"},
        "matchup": {"batter": {"id": 592450, "fullName": batter},
                    "pitcher": {"id": 519242, "fullName": pitcher}},
        "result": {"event": event, "eventType": event.lower().replace(" ", "_"),
                   "rbi": rbi, "awayScore": away, "homeScore": home,
                   "description": PROSE},
        "playEvents": events,
    }


HIT = {"launchSpeed": 102.4, "launchAngle": 18.0, "totalDistance": 379.0,
       "trajectory": "line_drive", "coordinates": {"coordX": 128.5, "coordY": 62.3}}


def _payload():
    return {"allPlays": [
        _play(0, 6, "top", "Juan Soto", "Chris Sale", [
            _pitch(1, "C", balls=0, strikes=1, t="2026-08-28T23:12:00Z"),
            _pitch(2, "B", "Slider", 84.3, balls=1, strikes=1),
            _pitch(3, "F", balls=1, strikes=2),
            {"isPitch": False, "details": {"description": PROSE}},   # a pickoff
            _pitch(4, "S", "Slider", 85.0, balls=1, strikes=3),
        ], event="Strikeout", away=3, home=2),
        _play(1, 6, "top", "Aaron Judge", "Chris Sale", [
            _pitch(1, "B", balls=1, strikes=0),
            _pitch(2, "X", in_play=True, hit=HIT, balls=1, strikes=0),
        ], event="Lineout", away=3, home=2),
        _play(2, 6, "top", "Giancarlo Stanton", "Chris Sale", [
            _pitch(1, "B", balls=1, strikes=0, t="2026-08-28T23:16:00Z"),
        ]),                                                    # in progress
    ]}


# --- rows ------------------------------------------------------------------
def test_pitches_and_at_bats_ride_one_list_in_order():
    rows = pbp.game_events(_payload())
    kinds = [r["kind"] for r in rows]
    assert kinds == ["pitch"] * 4 + ["atbat"] + ["pitch"] * 2 + ["atbat"] + ["pitch"], kinds
    assert [r["at_bat"] for r in rows][:5] == [0, 0, 0, 0, 0]


def test_a_pitch_row_says_the_call_in_words_not_the_feeds_sentence():
    rows = pbp.game_events(_payload())
    first = rows[0]
    assert first["call"] == "Called strike" and first["code"] == "C"
    assert first["pitch"] == "Four-Seam Fastball" and first["speed"] == 95.1
    assert first["batter"] == "Juan Soto" and first["pitcher"] == "Chris Sale"
    assert (first["balls"], first["strikes"]) == (0, 1)
    assert first["time"] == "2026-08-28T23:12:00Z"
    assert rows[1]["call"] == "Ball" and rows[1]["pitch"] == "Slider"
    assert rows[2]["call"] == "Foul"
    assert rows[3]["call"] == "Swinging strike"


def test_an_unknown_call_code_falls_back_to_the_calls_own_description_then_the_code():
    pay = _payload()
    ev = pay["allPlays"][0]["playEvents"][0]
    ev["details"]["call"] = {"code": "ZZ", "description": "Some new call"}
    assert pbp.game_events(pay)[0]["call"] == "Some new call"
    ev["details"]["call"] = {"code": "ZZ"}
    assert pbp.game_events(pay)[0]["call"] == "ZZ"
    ev["details"]["call"] = {}
    assert pbp.game_events(pay)[0]["call"] == "Pitch"


def test_a_pickoff_is_not_a_pitch_row():
    rows = pbp.game_events(_payload())
    assert sum(1 for r in rows if r["kind"] == "pitch" and r["at_bat"] == 0) == 4


def test_the_at_bat_row_is_the_cards_row_plus_the_ball_in_flight():
    rows = pbp.game_events(_payload())
    ab = [r for r in rows if r["kind"] == "atbat"]
    assert ab[0]["event"] == "Strikeout" and ab[0]["hit"] is None
    assert ab[0]["time"] == "2026-08-28T23:14:30Z", "the at-bat's end time"
    judge = ab[1]
    assert judge["batter"] == "Aaron Judge" and judge["event"] == "Lineout"
    assert judge["hit"] == {"launch_speed": 102.4, "launch_angle": 18.0,
                            "distance": 379.0, "trajectory": "line_drive",
                            "x": 128.5, "y": 62.3}, judge["hit"]
    # The same fields the card's strip already reads, unchanged.
    card = pbp.recent_plays(_payload())
    assert [c["event"] for c in card] == ["Strikeout", "Lineout"]
    assert (judge["away_score"], judge["home_score"]) == (3, 2)


def test_the_in_play_pitch_is_flagged_and_carries_no_hit_of_its_own():
    rows = pbp.game_events(_payload())
    x = [r for r in rows if r["kind"] == "pitch" and r["code"] == "X"][0]
    assert x["in_play"] is True and x["call"] == "In play, out"
    assert "hit" not in x, "the ball in flight rides the at-bat row"


def test_the_feeds_prose_never_reaches_a_row():
    flat = json.dumps(pbp.game_events(_payload()))
    assert PROSE not in flat
    assert '"description"' not in flat


def test_missing_hit_data_and_times_are_none_not_a_crash():
    pay = _payload()
    for p in pay["allPlays"]:
        p["about"].pop("startTime", None); p["about"].pop("endTime", None)
        for e in p["playEvents"]:
            e.pop("startTime", None); e.pop("endTime", None)
            e.pop("hitData", None); e.pop("count", None)
    rows = pbp.game_events(pay)
    assert all(r["time"] == "" for r in rows)
    assert all(r["hit"] is None for r in rows if r["kind"] == "atbat")
    assert all(r["balls"] is None for r in rows if r["kind"] == "pitch")
    assert pbp._hit({"hitData": {"launchSpeed": None}}) is None, "all-empty is None"
    assert pbp._hit({"hitData": "x"}) is None
    for pay in ({}, None, {"allPlays": None}, {"allPlays": [{}]}):
        pbp.game_events(pay)


# --- who is up --------------------------------------------------------------
def test_the_at_bat_in_progress_names_the_batter_and_the_pitcher():
    cur = pbp.current_at_bat(_payload())
    assert cur["batter"] == "Giancarlo Stanton" and cur["pitcher"] == "Chris Sale"
    assert cur["batter_id"] == 592450 and cur["pitcher_id"] == 519242
    assert (cur["inning"], cur["half"]) == (6, "T")
    assert cur["pitches"] == 1


def test_between_at_bats_there_is_nobody_up():
    pay = _payload()
    pay["allPlays"] = pay["allPlays"][:2]          # the last play is complete
    assert pbp.current_at_bat(pay) is None
    assert pbp.current_at_bat({"allPlays": []}) is None
    assert pbp.current_at_bat({}) is None


# --- the deep file ------------------------------------------------------------
def test_the_mlb_deep_file_carries_the_events_and_the_current_at_bat():
    import tempfile
    from pathlib import Path
    import live_build as M
    d = Path(tempfile.mkdtemp())
    g = {"game_pk": 777, "home": "BOS", "away": "NYY",
         "live": {"state": "live", "start_time": ""}}
    M.write_pbp(g, _payload(), pbp.recent_plays(_payload(), 0), d)
    doc = json.loads((d / "mlb_777.json").read_text())
    assert len(doc["events"]) == 9 and doc["events"][-1]["kind"] == "pitch"
    assert doc["current"]["batter"] == "Giancarlo Stanton"
    assert [p["event"] for p in doc["plays"]] == ["Strikeout", "Lineout"]
    assert PROSE not in (d / "mlb_777.json").read_text()


def test_the_probe_can_describe_a_cached_payload():
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "espnprobe.py"), encoding="utf-8").read()
    assert '"--file"' in src and "json.load(fh)" in src
    doc = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "docs", "DROPLET_CHECKS.md"), encoding="utf-8").read()
    assert "## 2b." in doc or "### 2b." in doc
    assert "hitData" in doc and "--file" in doc


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
