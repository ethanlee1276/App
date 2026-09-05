"""One deep play-by-play file per live game, beside the scoreboard.

Ethan, 2026-09-05: "You should be able to click on each live game and
see a deeper play by play." The card's strip stays at six plays because
the fast file is polled every twelve seconds by every open tab; a game's
whole list — 392 plays on a finished WNBA game — belongs in a file only
the reader who opened that game fetches. `livescore_build.write_pbp`
(football and hoops) and `live_build.write_pbp` (MLB) write
`web/data/pbp/{league}_{event}.json` from the payload the card's pass
already fetched, and `prune_pbp` clears them 36 hours on.

Football is grouped by DRIVE for the page — `espnplays.football_drives`
— from the same verified fields and the same row composer the card's
strip uses. Nothing here reads a play's `text` or a drive's
`description`; the football fixture puts marker strings in both.
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import livescore_build as B                                  # noqa: E402
import live_build as M                                       # noqa: E402
from engine.sources import espnplays as E                    # noqa: E402
from engine import gate                                      # noqa: E402

# THE FIXTURES ARE COPIES, NOT IMPORTS. tests/test_football_plays.py and
# tests/test_hoops_plays.py carry the same shapes, but the doctor forbids
# a test module importing another at module scope (its third-party guard
# cannot tell a sibling test from a package), so the two payloads the
# probes verified are restated here, key for key.
TEXT = "ESPN's own sentence describing the play"
DESC = "ESPN's drive summary sentence"
HTEXT = "ESPN's own sentence describing the play"
SIDES = {"14": "LVA", "5": "IND"}


def _play(pid, seq, *, period=1, clock="12:34", down=1, dist=10, yl=25,
          yards=4, ptype="Rush", scoring=False, turnover=False,
          penalty=False, away=0, home=0):
    return {
        "id": pid, "sequenceNumber": str(seq),
        "period": {"number": period}, "clock": {"displayValue": clock},
        "start": {"down": down, "distance": dist, "yardLine": yl,
                  "yardsToEndzone": 100 - yl, "team": {"id": "61"}},
        "end": {"team": {"id": "61"}},
        "statYardage": yards, "type": {"abbreviation": "RUSH", "id": "5",
                                       "text": ptype},
        "scoringPlay": scoring, "isTurnover": turnover, "isPenalty": penalty,
        "awayScore": away, "homeScore": home,
        "text": TEXT, "wallclock": "2026-09-05T00:12:00Z",
    }


def _drive(did, plays, team=("UGA", "Georgia Bulldogs", "61"), yards=25,
           elapsed="1:52"):
    abbr, name, tid = team
    return {
        "id": did, "description": DESC, "offensivePlays": len(plays),
        "plays": plays,
        "start": {"period": {"number": 1, "type": "quarter"},
                  "text": "15:00", "yardLine": 24},
        "team": {"abbreviation": abbr, "displayName": name, "id": tid},
        "timeElapsed": {"displayValue": elapsed}, "yards": yards,
    }


def _fb(dup_current_in_previous=True):
    """A finished first drive, then the drive in progress — which, as the
    probe showed, ALSO appears at the tail of `previous`."""
    d1 = _drive("40185666401", [
        _play("p1", 1, down=None, dist=None, ptype="Kickoff", yards=0),
        _play("p2", 2, yards=7),
        _play("p3", 3, down=2, dist=3, yards=3, ptype="Pass Reception"),
        _play("p4", 4, down=1, dist=10, yards=-2, ptype="Rush"),
        _play("p5", 5, down=2, dist=12, yards=0, ptype="Punt"),
    ], elapsed="2:31")
    cur = _drive("40185666402", [
        _play("p6", 6, clock="9:41", yl=30, yards=24, ptype="Pass Reception"),
        _play("p7", 7, clock="9:02", yl=54, yards=46, ptype="Pass Reception",
              scoring=True, home=7),
    ], team=("BAMA", "Alabama Crimson Tide", "333"), yards=70, elapsed="1:10")
    previous = [d1] + ([cur] if dup_current_in_previous else [])
    return {"drives": {"current": cur, "previous": previous},
            "header": {"id": "401856664"}, "boxscore": {"teams": []}}


def _hplay(pid, seq, *, team="14", parts=("2529185",), ptype="Jump Shot",
           scoring=False, shot=True, value=0, attempted=2, period=1,
           clock="9:41", away=0, home=0):
    return {
        "id": pid, "sequenceNumber": str(seq),
        "period": {"number": period, "displayValue": "1st Quarter"},
        "clock": {"displayValue": clock},
        "team": {"id": team} if team else {},
        "participants": [{"athlete": {"id": a}} for a in parts],
        "type": {"id": "558", "text": ptype},
        "scoringPlay": scoring, "shootingPlay": shot,
        "scoreValue": value, "pointsAttempted": attempted,
        "awayScore": away, "homeScore": home,
        "shortDescription": "ESPN's shorter sentence", "text": HTEXT,
        "wallclock": "2026-08-30T19:12:00Z",
    }


def _hp():
    box = lambda tid, abbr, name, aid, nm: {           # noqa: E731
        "team": {"id": tid, "abbreviation": abbr, "displayName": name},
        "statistics": [{"names": ["MIN", "PTS"],
                        "athletes": [{"athlete": {"id": aid, "displayName": nm},
                                      "stats": ["30", "22"]}]}]}
    return {"plays": [
        _hplay("p1", 1, ptype="Jumpball", parts=("2529185", "4433403"),
               shot=False, attempted=0, team=""),
        _hplay("p2", 2, scoring=True, value=2, home=2),
        _hplay("p3", 3, team="5", parts=("4433403",), attempted=3, home=2),
        _hplay("p4", 4, ptype="Defensive Rebound", shot=False, attempted=0, home=2),
        _hplay("p5", 5, ptype="Free Throw", scoring=True, value=1, attempted=1, home=3),
        _hplay("p6", 6, period=5, clock="0:41", team="5", parts=("4433403",),
               ptype="Three Point Jump Shot", scoring=True, value=3,
               attempted=3, away=88, home=90),
    ], "boxscore": {"players": [
        box("14", "LV", "Las Vegas Aces", "2529185", "A'ja Wilson"),
        box("5", "IND", "Indiana Fever", "4433403", "Caitlin Clark"),
    ], "teams": []}, "header": {"id": "401857186"}}


# --- drives -------------------------------------------------------------------
def test_drives_are_grouped_and_the_one_in_progress_comes_last_once():
    drives = E.football_drives(_fb(dup_current_in_previous=True), "cfb")
    assert [d["id"] for d in drives] == ["40185666401", "40185666402"]
    assert [len(d["plays"]) for d in drives] == [5, 2]
    assert drives[0]["team"] == "UGA" and drives[1]["team"] == "BAMA"
    assert drives[1]["yards"] == 70 and drives[1]["elapsed"] == "1:10"
    assert drives[1]["offensive_plays"] == 2 and drives[1]["period"] == 1


def test_the_later_copy_of_a_repeated_drive_wins():
    """`previous` may lag `current` by a play; the fresher listing wins
    rather than the earlier one suppressing it."""
    pay = _fb(dup_current_in_previous=True)
    # The fixture lists ONE dict in both places; give `previous` its own
    # lagging copy so only that listing is short.
    lag = dict(pay["drives"]["previous"][-1])
    lag["plays"] = lag["plays"][:1]
    pay["drives"]["previous"][-1] = lag
    drives = E.football_drives(pay, "cfb")
    assert len(drives) == 2 and len(drives[1]["plays"]) == 2


def test_scoring_is_derived_from_the_plays_not_a_drive_flag():
    drives = E.football_drives(_fb(), "cfb")
    assert drives[0]["scoring"] is False and drives[1]["scoring"] is True


def test_the_flat_list_matches_the_cards_own_order():
    drives = E.football_drives(_fb(), "cfb")
    flat = [r["id"] for d in drives for r in d["plays"]]
    assert flat == [r["id"] for r in E.football_plays(_fb(), "cfb", limit=0)]


def test_a_drive_with_no_id_still_appears_and_none_is_lost():
    pay = _fb(dup_current_in_previous=False)
    for d in pay["drives"]["previous"] + [pay["drives"]["current"]]:
        d.pop("id", None)
    assert len(E.football_drives(pay, "cfb")) == 2


# --- the deep file --------------------------------------------------------------
def _game(league="cfb", state="live", eid="e1"):
    return {"event_id": eid, "home": "UGA", "away": "BAMA",
            "home_name": "Georgia Bulldogs", "away_name": "Alabama Crimson Tide",
            "home_id": "61", "away_id": "333",
            "live": {"state": state, "home_score": 7, "away_score": 0,
                     "period": "Q1", "clock": "9:02", "start_time": ""}}


def _with_fetch(fn, games, league, pbp_dir):
    real = E.fetch_summary
    E.fetch_summary = fn
    try:
        return B.attach_plays(games, league, pbp_dir=pbp_dir)
    finally:
        E.fetch_summary = real


def test_a_live_football_game_gets_its_deep_file_with_drives_and_plays():
    d = Path(tempfile.mkdtemp())
    games = [_game(), _game(state="scheduled", eid="s1")]
    note = _with_fetch(lambda lg, eid, ttl=30: _fb(), games, "cfb", d)
    assert (d / "cfb_e1.json").is_file()
    assert not (d / "cfb_s1.json").exists(), "a scheduled game has no deep file"
    doc = json.loads((d / "cfb_e1.json").read_text())
    assert doc["league"] == "cfb" and doc["event_id"] == "e1"
    assert (doc["home"], doc["away"]) == ("UGA", "BAMA")
    assert doc["home_name"] == "Georgia Bulldogs"
    assert doc["live"]["state"] == "live" and doc["live"]["home_score"] == 7
    assert len(doc["drives"]) == 2 and len(doc["plays"]) == 7
    assert doc["plays"][-1]["id"] == "p7", "newest last"
    # The card still got its six.
    assert len(games[0]["plays"]) == B.PLAYS_PER_GAME
    assert "1 deep file(s)" in note, note


def test_no_pbp_dir_means_no_deep_file_and_the_old_note():
    games = [_game()]
    note = _with_fetch(lambda lg, eid, ttl=30: _fb(), games, "cfb", None)
    assert "deep file" not in note
    assert games[0]["plays"]


def test_a_live_hoops_game_gets_every_play_and_no_drives():
    d = Path(tempfile.mkdtemp())
    games = [{"event_id": "401857186", "home": "LVA", "away": "IND",
              "home_name": "Las Vegas Aces", "away_name": "Indiana Fever",
              "home_id": "14", "away_id": "5",
              "live": {"state": "live", "start_time": ""}}]
    _with_fetch(lambda lg, eid, ttl=30: _hp(), games, "wnba", d)
    doc = json.loads((d / "wnba_401857186.json").read_text())
    assert "drives" not in doc
    assert len(doc["plays"]) == 6 and doc["plays"][0]["kind"] == "hoops"
    assert {r["team"] for r in doc["plays"] if r["team"]} == {"LVA", "IND"}


def test_prose_never_reaches_a_deep_file():
    d = Path(tempfile.mkdtemp())
    _with_fetch(lambda lg, eid, ttl=30: _fb(), [_game()], "cfb", d)
    flat = (d / "cfb_e1.json").read_text()
    assert TEXT not in flat and DESC not in flat
    assert '"text"' not in flat and '"description"' not in flat
    games = [{"event_id": "x", "home": "LVA", "away": "IND",
              "live": {"state": "live", "start_time": ""}}]
    _with_fetch(lambda lg, eid, ttl=30: _hp(), games, "wnba", d)
    flat = (d / "wnba_x.json").read_text()
    assert HTEXT not in flat and '"shortDescription"' not in flat


def test_a_deep_file_that_fails_costs_nothing_but_itself():
    games = [_game()]
    unwritable = Path(tempfile.mkdtemp()) / "afile"
    unwritable.write_text("not a directory")
    note = _with_fetch(lambda lg, eid, ttl=30: _fb(), games, "cfb", unwritable)
    assert games[0]["plays"], "the card lost its plays"
    assert "1 of 1 live game(s)" in note and "0 deep file(s)" in note, note


def test_deep_files_carry_no_paid_key():
    d = Path(tempfile.mkdtemp())
    _with_fetch(lambda lg, eid, ttl=30: _fb(), [_game()], "cfb", d)
    doc = json.loads((d / "cfb_e1.json").read_text())
    assert not (set(doc) & set(gate.PAID_KEYS)), set(doc) & set(gate.PAID_KEYS)


# --- MLB ----------------------------------------------------------------------
def test_the_mlb_builder_writes_the_same_shape():
    from engine.mlb.sources import pbp as P
    d = Path(tempfile.mkdtemp())
    payload = {"allPlays": [
        {"result": {"event": "Single", "eventType": "single", "rbi": 0,
                    "awayScore": 0, "homeScore": 0, "description": "PROSE"},
         "about": {"inning": 1, "halfInning": "top", "isScoringPlay": False},
         "matchup": {"batter": {"fullName": "A"}, "pitcher": {"fullName": "P"}}},
        {"result": {"event": "Home Run", "eventType": "home_run", "rbi": 2,
                    "awayScore": 2, "homeScore": 0, "description": "PROSE"},
         "about": {"inning": 1, "halfInning": "top", "isScoringPlay": True},
         "matchup": {"batter": {"fullName": "B"}, "pitcher": {"fullName": "P"}}},
        {"result": {}, "about": {"inning": 1, "halfInning": "top"},
         "matchup": {"batter": {"fullName": "C"}}},           # in progress
    ]}
    games = [{"game_pk": 777, "home": "NYY", "away": "BOS",
              "live": {"state": "live", "start_time": ""}}]
    real = P.fetch_live_playbyplay
    P.fetch_live_playbyplay = lambda pk, ttl=30: payload
    try:
        note = M.attach_plays(games, pbp_dir=d)
    finally:
        P.fetch_live_playbyplay = real
    doc = json.loads((d / "mlb_777.json").read_text())
    assert doc["league"] == "mlb" and doc["event_id"] == "777"
    assert (doc["home"], doc["away"]) == ("NYY", "BOS")
    assert [p["event"] for p in doc["plays"]] == ["Single", "Home Run"]
    assert "PROSE" not in (d / "mlb_777.json").read_text()
    assert "1 deep file(s)" in note, note
    assert games[0]["plays"], "the card still got its strip"


# --- pruning and serving ----------------------------------------------------------
def test_old_deep_files_are_pruned_and_fresh_ones_kept():
    d = Path(tempfile.mkdtemp())
    old = d / "cfb_old.json"; old.write_text("{}")
    fresh = d / "cfb_new.json"; fresh.write_text("{}")
    other = d / "notes.txt"; other.write_text("keep")
    stale_at = time.time() - B.PBP_MAX_AGE_S - 60
    os.utime(old, (stale_at, stale_at))
    assert B.prune_pbp(d) == 1
    assert not old.exists() and fresh.exists() and other.exists()
    assert B.prune_pbp(Path(tempfile.mkdtemp()) / "missing") == 0


def test_the_scoreboard_write_makes_the_deep_directory_and_prunes_it():
    src = (ROOT / "livescore_build.py").read_text()
    i = src.index("def write(league: str, out_dir: Path = OUT)")
    body = src[i:src.index("\ndef main", i)]
    assert 'pbp_dir = Path(out_dir) / "pbp"' in body
    assert "build(league, pbp_dir=pbp_dir)" in body
    assert "prune_pbp(pbp_dir)" in body
    m = (ROOT / "live_build.py").read_text()
    assert 'pbp_dir = out.parent / "pbp"' in m and "prune_pbp(pbp_dir)" in m


def test_the_gate_serves_a_deep_file_free_by_its_directory():
    assert gate.is_free("pbp/cfb_401856664.json")
    assert gate.is_free("web/data/pbp/mlb_777.json")
    assert not gate.is_free("pbp/notes.txt")
    assert not gate.is_free("secret/cfb.json"), "only the named directories"
    assert not gate.is_free("cfb.json"), "the board itself is still gated"
    assert "pbp" in gate.FREE_DIRS


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
