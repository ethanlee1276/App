"""The NHL live page: what the league's own feed gives it, and how it is drawn.

Ethan, 2026-10-15, with two renders (the Qellys rink, and the page laid out
like ESPN's app: the scoreboard, the arena with Live / Shot Chart / Ice
Tracker / Player Tracker / Game Flow, the plays down the right, then the
team stats, the lineups and the odds) and their phone's screenshot of the old
page, a small rink in the corner of an empty box: "figure out what data we
can use for the live play by play screen for nhl like live posetions and
puck tracking".

THE DATA (engine/sources/nhlrink, livescore_build.nhl_rink_pass): the
league's play-by-play places every event on the ice — faceoffs, hits,
takeaways, giveaways, shots, blocks, goals, penalties — with who was in it
and how many skaters each side had. Each row is turned so the home team
attacks the right-hand net; a play's team is its player's, read off the
roster (a block's blocker is `team2`); the league's codes ride, a sentence
never does. The block lands on the game's deep file without moving the
file's clock (the round robin's cursor). rinkprobe.py prints, on the box,
what a real game carries — the ends, the scorer's table, whether the shift
charts are live, the goal visualizer's tracked positions.

THE PAGE (web/js/rinkcast.js + css/rinkcast.css, handed hockey by
js/gamecast.js `hoops`): what it works out from the events is pinned here —
whose puck it is (only after a faceoff, a takeaway or a giveaway), the
power play and its clock, each side's game, the attempt race, the sequence
since the last faceoff on the Live view — and the rink on the picture: the
points read off the render land where they were read.

Offline throughout; the browser half is opt-in (QB_BROWSER_TESTS=1) and
aborts every request that leaves the page's own server.

Run directly: `python3 tests/test_the_nhl_live_page.py`
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import livescore_build as B                                  # noqa: E402
import rinkprobe as P                                        # noqa: E402
from engine.sources import nhlrink as R                      # noqa: E402
from _app import app_js, page_builders  # noqa: E402  (app.js and its rooms; the game page's own card builders)

HOME_ID, AWAY_ID, GAME = 6, 3, 2026020123                    # BOS at home, NYR away
PAST, MARCH, LIND, MCAVOY, SWAY = 8477956, 8473419, 8480000, 8479325, 8480280
ZIB, TROCH, FOX, SHES, PANA = 8476459, 8476389, 8479323, 8478048, 8478550
SENTENCE = "Play stopped because the puck went over the glass"
DAY = datetime.date(2026, 10, 15)


def _spot(pid, team, first, last, num, pos, face=True):
    abbr = "BOS" if team == HOME_ID else "NYR"
    return {"playerId": pid, "teamId": team, "firstName": {"default": first}, "lastName": {"default": last},
            "sweaterNumber": num, "positionCode": pos,
            "headshot": f"https://assets.nhle.com/mugs/nhl/20262027/{abbr}/{pid}.png" if face else f"http://example.com/{pid}.png"}


ROSTER = [_spot(PAST, HOME_ID, "David", "Pastrnak", 88, "R"), _spot(MARCH, HOME_ID, "Brad", "Marchand", 63, "L"),
          _spot(LIND, HOME_ID, "Elias", "Lindholm", 28, "C"), _spot(MCAVOY, HOME_ID, "Charlie", "McAvoy", 73, "D"),
          _spot(SWAY, HOME_ID, "Jeremy", "Swayman", 1, "G"), _spot(ZIB, AWAY_ID, "Mika", "Zibanejad", 93, "C"),
          _spot(TROCH, AWAY_ID, "Vincent", "Trocheck", 16, "C"), _spot(FOX, AWAY_ID, "Adam", "Fox", 23, "D"),
          _spot(SHES, AWAY_ID, "Igor", "Shesterkin", 31, "G"), _spot(PANA, AWAY_ID, "Artemi", "Panarin", 10, "L", face=False)]


def _pl(eid, kind, period, t_in, *, side=None, sc="1551", ptype="REG", **details):
    rem = 1200 - t_in
    p = {"eventId": eid, "typeDescKey": kind, "periodDescriptor": {"number": period, "periodType": ptype},
         "timeInPeriod": f"{t_in // 60:02d}:{t_in % 60:02d}", "timeRemaining": f"{rem // 60:02d}:{rem % 60:02d}",
         "situationCode": sc, "details": details}
    if side:
        p["homeTeamDefendingSide"] = side
    return p


def _pbp(state="LIVE", situation=True):
    """A game in the league's own shape: NYR at BOS, four minutes into the third.
    The home team defends the left net in the first (no turn), the right in the
    second (a half turn), and the third never says (its shots decide)."""
    plays = [
        _pl(1, "period-start", 1, 0, side="left"),
        _pl(2, "faceoff", 1, 0, side="left", xCoord=0, yCoord=0, eventOwnerTeamId=HOME_ID, winningPlayerId=LIND, losingPlayerId=TROCH),
        _pl(3, "shot-on-goal", 1, 40, side="left", xCoord=70, yCoord=-10, eventOwnerTeamId=HOME_ID, shootingPlayerId=PAST,
            goalieInNetId=SHES, shotType="wrist", awaySOG=0, homeSOG=1),
        # The owner names BOS; the shooter is NYR's, the blocker BOS's.
        _pl(4, "blocked-shot", 1, 75, side="left", xCoord=-60, yCoord=5, eventOwnerTeamId=HOME_ID, shootingPlayerId=ZIB,
            blockingPlayerId=MCAVOY, reason="blocked"),
        _pl(5, "hit", 1, 90, side="left", xCoord=-80, yCoord=40, eventOwnerTeamId=HOME_ID, hittingPlayerId=MARCH, hitteePlayerId=FOX),
        _pl(6, "takeaway", 1, 120, side="left", xCoord=20, yCoord=-30, eventOwnerTeamId=AWAY_ID, playerId=FOX),
        _pl(7, "penalty", 1, 300, side="left", xCoord=-50, yCoord=20, eventOwnerTeamId=AWAY_ID, committedByPlayerId=FOX,
            drawnByPlayerId=PAST, descKey="hooking", duration=2, typeCode="MIN"),
        _pl(8, "stoppage", 1, 300, side="left", reason=SENTENCE),
        _pl(9, "period-start", 2, 0, side="right"),
        _pl(10, "shot-on-goal", 2, 200, side="right", sc="1451", xCoord=-75, yCoord=8, eventOwnerTeamId=HOME_ID,
            shootingPlayerId=PAST, goalieInNetId=SHES, shotType="snap", awaySOG=0, homeSOG=2),
        _pl(11, "goal", 2, 250, side="right", sc="1451", xCoord=-82, yCoord=-3, eventOwnerTeamId=HOME_ID, scoringPlayerId=PAST,
            assist1PlayerId=MARCH, assist2PlayerId=MCAVOY, goalieInNetId=SHES, shotType="wrist", awayScore=0, homeScore=1),
        _pl(12, "period-start", 3, 0),
        _pl(13, "missed-shot", 3, 100, xCoord=65, yCoord=12, eventOwnerTeamId=HOME_ID, shootingPlayerId=PAST, shotType="slap",
            reason="wide-of-net"),
        _pl(14, "shot-on-goal", 3, 160, xCoord=80, yCoord=-6, eventOwnerTeamId=HOME_ID, shootingPlayerId=MARCH,
            goalieInNetId=SHES, shotType="backhand", awaySOG=0, homeSOG=3),
        _pl(15, "giveaway", 3, 200, xCoord=150, yCoord=0, eventOwnerTeamId=AWAY_ID, playerId=PANA),       # off the ice
        _pl(16, "delayed-penalty", 3, 230, eventOwnerTeamId=AWAY_ID),
        _pl(17, "faceoff", 3, 240, xCoord=69, yCoord=22, eventOwnerTeamId=AWAY_ID, winningPlayerId=ZIB, losingPlayerId=LIND),
    ]
    doc = {"id": GAME, "season": 20262027, "gameType": 2, "gameState": state,
           "venue": {"default": "TD Garden"}, "venueLocation": {"default": "Boston"},
           "periodDescriptor": {"number": 3, "periodType": "REG"},
           "clock": {"timeRemaining": "16:00", "secondsRemaining": 960, "running": True, "inIntermission": False},
           "homeTeam": {"id": HOME_ID, "abbrev": "BOS"}, "awayTeam": {"id": AWAY_ID, "abbrev": "NYR"},
           "rosterSpots": ROSTER, "plays": plays}
    if situation:
        doc["situation"] = {"situationCode": "1451", "timeRemaining": "01:40", "secondsRemaining": 100}
    return doc


def _sk(pid, num, name, pos, toi, **kw):
    return {"playerId": pid, "sweaterNumber": num, "name": {"default": name}, "position": pos, "toi": toi,
            "goals": kw.get("g", 0), "assists": kw.get("a", 0), "sog": kw.get("sog", 0), "plusMinus": kw.get("pm", 0),
            "hits": kw.get("hits", 0), "blockedShots": kw.get("blk", 0), "pim": kw.get("pim", 0),
            "faceoffWinningPctg": kw.get("fo", 0), "shifts": 20}


def _box():
    marchand = _sk(MARCH, 63, "B. Marchand", "L", "14:00", fo=0.55)
    marchand["sog"], marchand["shots"] = None, 2                 # the older name for shots on goal
    return {"awayTeam": {"abbrev": "NYR"}, "homeTeam": {"abbrev": "BOS"}, "playerByGameStats": {
        "awayTeam": {"forwards": [_sk(ZIB, 93, "M. Zibanejad", "C", "14:10", sog=1, fo=0.4), _sk(TROCH, 16, "V. Trocheck", "C", "13:00"),
                                  _sk(PANA, 10, "A. Panarin", "L", "15:30")],
                     "defense": [_sk(FOX, 23, "A. Fox", "D", "16:20", pim=2)],
                     "goalies": [{"playerId": SHES, "sweaterNumber": 31, "name": {"default": "I. Shesterkin"}, "toi": "44:00",
                                  "saveShotsAgainst": "3/4", "goalsAgainst": 1, "starter": True},
                                 {"playerId": 1, "sweaterNumber": 40, "name": {"default": "Backup Goalie"}, "toi": "00:00",
                                  "saveShotsAgainst": "0/0", "goalsAgainst": 0}]},
        "homeTeam": {"forwards": [_sk(PAST, 88, "D. Pastrnak", "R", "15:00", g=1, sog=3, pm=1), marchand,
                                  _sk(LIND, 28, "E. Lindholm", "C", "13:30", fo=0.5)],
                     "defense": [_sk(MCAVOY, 73, "C. McAvoy", "D", "18:00", a=1, blk=1)],
                     "goalies": [{"playerId": SWAY, "sweaterNumber": 1, "name": {"default": "J. Swayman"}, "toi": "44:00",
                                  "saves": 2, "shotsAgainst": 2, "goalsAgainst": 0, "starter": True}]}}}


def _rows():
    return {r["id"]: r for r in R.rink_rows(_pbp())}


# --- the data: the league's events on the ice -----------------------------------
def test_every_event_lands_on_the_ice_turned_so_home_attacks_the_right():
    by = _rows()
    assert (by[3]["x"], by[3]["y"]) == (70.0, -10.0), "the first: home defends the left net, already attacking right"
    assert (by[10]["x"], by[10]["y"]) == (75.0, -8.0), "the second: home defends the right — a half turn, x and y"
    assert (by[11]["x"], by[11]["y"]) == (82.0, 3.0)
    assert (by[13]["x"], by[13]["y"]) == (65.0, 12.0), "the third never says; home's shots went right"
    assert by[4]["x"] == -60.0, "NYR's attempt at the left-hand net"
    assert "x" not in by[15] and "y" not in by[15], "a spot outside the boards is no spot"
    assert [by[i]["elapsed"] for i in (3, 10, 13)] == [40, 1400, 2500]
    assert by[10]["clock"] == "16:40" and by[1]["kind"] == "start" and by[16]["kind"] == "delayed"
    so = _pbp()
    so["plays"].append(_pl(18, "shot-on-goal", 5, 0, ptype="SO", xCoord=80, yCoord=0, eventOwnerTeamId=HOME_ID,
                           shootingPlayerId=PAST))
    assert 18 not in {r["id"] for r in R.rink_rows(so)}, "a shootout is not play on the ice"


def test_a_play_is_its_players_side_and_a_block_names_both():
    by = _rows()
    assert by[4]["team"] == "NYR" and by[4]["team2"] == "BOS", "the shooter's side, whatever the owner says"
    assert (by[4]["player"], by[4]["player2"], by[4]["role2"]) == ("Mika Zibanejad", "Charlie McAvoy", "blocked")
    assert by[2]["team"] == "BOS" and (by[2]["player2"], by[2]["role2"]) == ("Vincent Trocheck", "lost")
    assert by[5]["team"] == "BOS" and by[5]["player2"] == "Adam Fox"
    assert by[6]["team"] == "NYR" and by[15]["team"] == "NYR" and by[17]["team"] == "NYR"
    assert by[16]["team"] == "NYR", "a play with no man takes the owner's side"
    assert by[11]["assists"] == ["Brad Marchand", "Charlie McAvoy"] and by[11]["score"] == [0, 1]
    assert by[3]["num"] == 88 and by[3]["sog"] == [0, 1] and by[3]["shot"] == "wrist"
    assert (by[3]["player2"], by[3]["role2"]) == ("Igor Shesterkin", "goalie")


def test_the_leagues_codes_ride_and_a_sentence_never_does():
    by = _rows()
    assert (by[7]["penalty"], by[7]["minutes"], by[7]["ptype"]) == ("hooking", 2, "min")
    assert by[13]["reason"] == "wide-of-net"
    assert by[8]["kind"] == "stoppage" and "reason" not in by[8], "a sentence is not a code"
    assert SENTENCE not in json.dumps(R.rink_doc(_pbp(), _box(), lambda s: 0.1))


def test_the_situation_code_reads_the_strength_the_power_play_and_the_empty_net():
    S = R.situation
    assert S("1551") == {"away": 5, "home": 5, "pp": "", "en": ""}
    assert S("1451") == {"away": 4, "home": 5, "pp": "home", "en": ""}
    assert S("1541") == {"away": 5, "home": 4, "pp": "away", "en": ""}
    assert S("0651") == {"away": 6, "home": 5, "pp": "", "en": "away"}, "a pulled goalie's extra man is not a power play"
    assert S("0641") == {"away": 6, "home": 4, "pp": "away", "en": "away"}
    for bad in ("", "155", "15511", "1771", "2551", "abcd", None):
        assert S(bad) is None, bad


def test_the_rink_block_carries_the_men_the_building_the_clock_and_the_power_play():
    doc = R.rink_doc(_pbp(), _box())
    assert (doc["home"], doc["away"], doc["game_id"], doc["season"], doc["game_type"]) == ("BOS", "NYR", GAME, 20262027, 2)
    assert doc["venue"] == {"name": "TD Garden", "city": "Boston"}
    assert doc["clock"] == {"period": 3, "type": "REG", "left": "16:00", "intermission": False, "running": True}
    assert doc["state"] == "LIVE"
    assert doc["situation"] == {"pp": "BOS", "left": "01:40", "away": 4, "home": 5}, "the feed's own power-play block"
    assert doc["players"][str(PAST)] == {"name": "David Pastrnak", "team": "BOS", "num": 88, "pos": "R",
                                         "face": f"https://assets.nhle.com/mugs/nhl/20262027/BOS/{PAST}.png"}
    assert doc["players"][str(PANA)]["face"] == "", "a face that is not https is none"
    assert "xg" not in doc, "no model handed in, no claim either way"
    bare = R.rink_doc(_pbp(situation=False))
    assert "situation" not in bare and "box" not in bare and len(bare["events"]) == 17


def test_our_expected_goals_ride_on_each_unblocked_attempt_and_a_broken_model_on_none():
    doc = R.rink_doc(_pbp(), None, lambda shot: 0.25)
    assert doc["xg"] is True
    assert {r["id"] for r in doc["events"] if "xg" in r} == {3, 10, 11, 13, 14}, "shots, the goal and the miss — never the block"
    broken = R.rink_doc(_pbp(), None, lambda shot: 1 / 0)
    assert broken["xg"] is False and not any("xg" in r for r in broken["events"])


def test_the_box_lines_read_the_leagues_box_score():
    lines = R.box_lines(_box(), R.players_of(_pbp()))
    nyr, bos = lines["NYR"], lines["BOS"]
    assert [g["name"] for g in nyr["goalies"]] == ["Igor Shesterkin"], "the backup who never played is not listed"
    assert (nyr["goalies"][0]["sv"], nyr["goalies"][0]["sa"], nyr["goalies"][0]["starter"]) == (3, 4, True)
    assert (bos["goalies"][0]["sv"], bos["goalies"][0]["sa"]) == (2, 2), "the newer saves and shots-against fields"
    z = next(s for s in nyr["skaters"] if s["num"] == 93)
    assert (z["name"], z["fo"], z["toi"], z["pos"]) == ("Mika Zibanejad", 40, "14:10", "C"), "the roster's full name"
    m = next(s for s in bos["skaters"] if s["num"] == 63)
    assert (m["sog"], m["fo"]) == (2, 55)
    assert next(s for s in nyr["skaters"] if s["num"] == 23)["pos"] == "D"
    doc = R.rink_doc(_pbp(), ["not", "a", "box"])
    assert "box" not in doc and len(doc["events"]) == 17, "a box that will not read leaves the events"


# --- the data: onto the game file ------------------------------------------------
def _score_day(*games):
    return {"games": [{"id": gid, "gameType": 2, "gameState": st, "homeTeam": {"abbrev": h, "score": 1},
                       "awayTeam": {"abbrev": a, "score": 0}, "startTimeUTC": "2026-10-15T23:00:00Z",
                       "periodDescriptor": {"number": 3, "periodType": "REG"},
                       "clock": {"timeRemaining": "16:00", "inIntermission": False}} for gid, a, h, st in games]}


def test_the_pass_puts_the_rink_on_the_game_file_and_leaves_its_clock_alone():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        (out / "pbp").mkdir()
        f = out / "pbp" / "nhl_401802123.json"
        old = {"league": "nhl", "event_id": "401802123", "home": "BOS", "away": "NYR", "plays": [{"kind": "hockey", "id": "1"}],
               "live": {"state": "live", "period": "P2"}}
        f.write_text(json.dumps(old))
        os.utime(f, (1_700_000_000, 1_700_000_000))
        games = [{"event_id": "401802123", "home": "BOS", "away": "NYR", "live": {"state": "live", "period": "P3", "clock": "16:00"}},
                 {"event_id": "401802124", "home": "COL", "away": "DAL", "live": {"state": "live"}},
                 {"event_id": "401802125", "home": "EDM", "away": "CGY", "live": {"state": "pre"}}]
        asked = []
        note = B.nhl_rink_pass(games, out, fetch_day=lambda d: _score_day((GAME, "NYR", "BOS", "LIVE")),
                               fetch_box=lambda gid, final=False: (asked.append(("box", gid, final)), _box())[1],
                               fetch_pbp=lambda gid, final=False: (asked.append(("pbp", gid, final)), _pbp())[1],
                               xg_fn=None, today=DAY)
        assert note == "nhl rink: 1 of 2 game(s), 1 not on the league's score feed", note
        doc = json.loads(f.read_text())
        assert doc["plays"] == old["plays"], "ESPN's plays stay as they were"
        assert doc["live"]["period"] == "P3", "this pass's scoreboard, the freshest"
        assert doc["rink"]["home"] == "BOS" and len(doc["rink"]["events"]) == 17 and doc["rink"]["at"]
        assert "BOS" in doc["rink"]["box"] and doc["rink"]["situation"]["pp"] == "BOS"
        assert f.stat().st_mtime == 1_700_000_000, "the round robin's cursor is ESPN's serving, not the league's"
        assert ("pbp", str(GAME), False) in asked and ("box", str(GAME), False) in asked
        assert sorted(p.name for p in (out / "pbp").iterdir()) == ["nhl_401802123.json"], "nothing for a game not on"


def test_a_game_espn_never_served_gets_its_own_file_and_a_dead_feed_writes_nothing():
    g = {"event_id": "401802123", "home": "BOS", "away": "NYR", "home_name": "Bruins", "away_name": "Rangers",
         "live": {"state": "final"}}
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        asked = []
        note = B.nhl_rink_pass([g], out, fetch_day=lambda d: _score_day((GAME, "NYR", "BOS", "OFF")),
                               fetch_box=lambda gid, final=False: None,
                               fetch_pbp=lambda gid, final=False: (asked.append(final), _pbp(state="OFF"))[1],
                               xg_fn=None, today=DAY)
        assert note == "nhl rink: 1 of 1 game(s)", note
        assert asked == [True], "a final is fetched under the final's longer cache"
        doc = json.loads((out / "pbp" / "nhl_401802123.json").read_text())
        assert (doc["league"], doc["plays"], doc["home_name"], doc["rink"]["state"]) == ("nhl", [], "Bruins", "OFF")
        assert "box" not in doc["rink"]

        def down(gid, final=False):
            raise OSError("the league's feed is down")
        two = out / "two"
        note = B.nhl_rink_pass([g], two, fetch_day=lambda d: _score_day((GAME, "NYR", "BOS", "OFF")),
                               fetch_box=lambda gid, final=False: None, fetch_pbp=down, xg_fn=None, today=DAY)
        assert note == "nhl rink: 0 of 1 game(s), 1 unreachable", note
        assert not (two / "pbp" / "nhl_401802123.json").exists()
        assert B.nhl_rink_pass([{"event_id": "1", "live": {"state": "pre"}}], two) == "", "no game on, nothing asked"


def test_the_live_scores_build_runs_the_pass_after_the_scoreboard_and_says_so():
    src = (ROOT / "livescore_build.py").read_text(encoding="utf-8")
    i = src.index("def write(")
    body = src[i:src.index("\n\n\n", i)]
    assert body.index("os.replace(tmp, out)") < body.index("nhl_rink_pass(payload.get(\"games\") or [], Path(out_dir))"), \
        "the scoreboard is written first; a play-by-play that will not load costs the rink alone"
    assert 'payload["rink_note"] = note' in body
    assert 'for key in ("box_note", "rink_note"):' in src, "the log line says what the league's passes did"
    assert 'f"nhl_live_pbp_{gid}.json"' in src and 'f"nhl_pbp_{gid}' not in src, \
        "its own cache name: the shot ingest reads nhl_pbp_ for a month and must never see a mid-game copy"


# --- the probe ---------------------------------------------------------------------
class _Gone(Exception):
    code = 404


def _shifts(n=6):
    rows = []
    for team, base in (("NYR", 100), ("BOS", 200)):
        rows += [{"playerId": base + i, "teamAbbrev": team, "period": 3, "startTime": "03:00", "endTime": "04:30",
                  "typeCode": 517} for i in range(n)]
    return {"data": rows + [{"playerId": 999, "teamAbbrev": "BOS", "period": 3, "startTime": "03:59", "endTime": "03:59",
                             "typeCode": 505}]}


def test_the_probe_reports_the_ends_the_table_the_ice_and_the_tracking():
    frames = [{"timeStamp": 1, "onIce": {"1": {"id": 1, "x": 10.0, "y": 20.0, "sweaterNumber": 88, "teamId": 6},
                                         "puck": {"id": 1, "x": 40.0, "y": 2.0}}}, {"timeStamp": 2, "onIce": {}}]
    got = []
    text = "\n".join(P.report(_pbp(), _box(), _shifts(), fetch=lambda url: (got.append(url), frames)[1]))
    assert "period 1: home defends left; home shots at the right end 1, at the left 0 → ok" in text
    assert "period 2: home defends right; home shots at the right end 0, at the left 2 → ok" in text
    assert "period 3: home defends ABSENT; home shots at the right end 2, at the left 0 → inferred from the shots" in text
    assert '"the blocker\'s side": 1' in text, "whose side a block's owner names, for nhlrink to confirm"
    assert "the parser reads: {'pp': 'BOS', 'left': '01:40', 'away': 4, 'home': 5}" in text
    assert "on a shift at that moment: {'NYR': 6, 'BOS': 6} → the chart is live" in text
    assert got and got[0].endswith(f"/{GAME}/ev11.json"), got
    assert "frames 2; a frame:" in text and "objects on the ice in a frame 2;" in text
    assert "events 17; with a spot 11;" in text
    assert SENTENCE not in text and f"<not a code, {len(SENTENCE)} chars>" in text, "a sentence prints as its length, never its words"
    late = "\n".join(P.report(_pbp(), None, _shifts(3), fetch=lambda url: (_ for _ in ()).throw(_Gone())))
    assert "the chart lags the game" in late and "answer: _Gone 404" in late and "box: none" in late
    assert "shift charts: OSError" in "\n".join(P.ice_report(_pbp(), OSError("down")))


# --- the page: the readers --------------------------------------------------------
RC = (ROOT / "web" / "js" / "rinkcast.js").read_text(encoding="utf-8")
RC_CSS = (ROOT / "web" / "css" / "rinkcast.css").read_text(encoding="utf-8")
TEAMS = (ROOT / "web" / "js" / "teams_nhl.js").read_text(encoding="utf-8")
APP = app_js()
GC = (ROOT / "web" / "js" / "gamecast.js").read_text(encoding="utf-8")


def _deep(state="live", situation=True, box=True, xg=True, upto=None):
    """The game file as the pass leaves it, the league's events on it."""
    pbp = _pbp(situation=situation)
    if upto is not None:
        pbp["plays"] = [p for p in pbp["plays"] if p["eventId"] <= upto]
    rink = R.rink_doc(pbp, _box() if box else None, (lambda s: 0.1) if xg else None)
    rink["at"] = "2026-10-15T23:50:00Z"
    return {"league": "nhl", "event_id": "401802123", "generated_at": "2026-10-15T23:50:00Z", "home": "BOS", "away": "NYR",
            "home_name": "Bruins", "away_name": "Rangers", "plays": [],
            "live": {"state": state, "period": "P3", "clock": "16:00", "home_score": 1, "away_score": 0,
                     "win_prob": {"home_win_prob": 0.71, "away_win_prob": 0.29}},
            "records": {"NYR": "4-2-0", "BOS": "5-1-0"}, "rink": rink}


STUBS = """
  globalThis.window = globalThis;
  globalThis.escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  globalThis.escapeAttr = escapeHtml;
  globalThis.icon = (n) => `<i class="ico-${n}"></i>`;
  globalThis.teamMarkIn = (lg, a) => `<span class="mark">${a}</span>`;
  globalThis.teamsIn = () => NHL_TEAMS;
  globalThis.teamNameIn = (lg, a) => (NHL_TEAMS[a] || {}).nick || a;
  globalThis.pbpAgo = () => "updated just now";
  globalThis.oddsTxt = (v) => (Number(v) > 0 ? `+${v}` : String(v));
  globalThis.gameId = (g) => `${g.away}@${g.home}`;
  globalThis.pbpPropsHTML = () => "<div>our picks on the game</div>";
"""


def _node(js, gc=False):
    """`gc` loads js/gamecast.js first, as the page has it: the shared run
    (QBGamecast.track) that moves the puck and the card the newest play is
    drawn on. Without it every mark is drawn where it is, which is what a
    reader who asked for less motion sees. The page's own boxes (detail.js)
    are the real ones (_app.page_builders)."""
    node = shutil.which("node")
    if not node:
        return None
    prog = (f"{TEAMS}\n{STUBS}\n{page_builders()}\n{GC if gc else ''}\n{RC}\n"
            f"console.log(JSON.stringify((() => {{ const Q = window.QBRink; {js} }})()));")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


#: What the sport hands the one page, as text: each part, its rows, and its words for every row.
PARTS = """
  const partsOf = (ctx) => {
    const P = Q.parts(ctx), out = {};
    for (const [key, v] of Object.entries(P)) if (typeof v !== "function") out[key] = v;
    out.says = (P.rows || []).map((p) => P.say(p));
    out.wire = typeof P.wire;
    return out;
  };
"""


def _parts(doc, board=None, gc=True):
    """Hockey's parts of the page (QBRink.parts), as detail.js gpKit asks for them."""
    return _node(f"""{PARTS}
      return partsOf({{ d: {json.dumps(doc)}, league: "nhl", lv: {json.dumps(doc.get("live") or {})},
                       boardGame: {json.dumps(board)}, faces: {{}} }});""", gc=gc)


def test_the_page_and_the_parser_read_a_situation_code_alike():
    codes = ["1551", "1451", "1541", "0651", "0641", "1560", "1771", "2551", "155", ""]
    got = _node(f"return {json.dumps(codes)}.map((c) => Q.sitOf(c));")
    if got is None:
        return
    assert got == [R.situation(c) for c in codes]


def test_the_puck_is_somebodys_only_after_a_faceoff_a_takeaway_or_a_giveaway():
    one = lambda kind, team, **kw: {"id": 1, "kind": kind, "team": team, "elapsed": 10, **kw}
    cases = {"faceoff": (one("faceoff", "NYR"), "away"), "takeaway": (one("takeaway", "BOS"), "home"),
             "giveaway": (one("giveaway", "BOS"), "away"), "shot": (one("sog", "BOS"), ""), "hit": (one("hit", "NYR"), ""),
             "block": (one("block", "NYR", team2="BOS"), ""), "goal": (one("goal", "BOS"), ""), "nothing": (None, "")}
    docs = {k: {"home": "BOS", "away": "NYR", "rink": {"events": [e] if e else []}} for k, (e, _) in cases.items()}
    got = _node(f"const D = {json.dumps(docs)}; return Object.fromEntries(Object.entries(D).map(([k, d]) => [k, Q.puckAfter(d)]));")
    if got is None:
        return
    assert got == {k: want for k, (_, want) in cases.items()}
    ends = _node("""const d = { home: "BOS", away: "NYR" };
      return [Q.endOf(d, { x: 70 }), Q.endOf(d, { x: -60 }), Q.endOf(d, { x: 10 }), Q.endOf(d, {})];""")
    assert ends == ["away", "home", "neutral", ""], "the right-hand end is the away side's: home attacks it"


def test_the_power_play_is_the_feeds_or_worked_out_from_the_penalties():
    got = _node(f"""
      const d = {json.dumps(_deep())};
      const out = {{ feed: Q.powerPlay(d) }};
      delete d.rink.situation;
      const pen = (id, team, at, mins) => ({{ id, kind: "penalty", team, period: 3, elapsed: at, minutes: mins, sc: "1541" }});
      d.rink.events.push(pen(90, "BOS", 2600, 2));
      out.sheet = Q.powerPlay(d);
      d.rink.events.push({{ id: 91, kind: "goal", team: "NYR", period: 3, elapsed: 2630, sc: "1541" }});
      out.cut = Q.powerPlay(d);
      d.rink.events.push({{ id: 92, kind: "faceoff", team: "BOS", period: 3, elapsed: 2635, sc: "1551" }});
      out.even = Q.powerPlay(d);
      return out;""")
    if got is None:
        return
    assert got["feed"] == {"side": "home", "left": 100}, "the feed's own block: BOS, 1:40"
    assert got["sheet"] == {"side": "away", "left": 80}, "BOS's minor at 43:20, the clock at 44:00"
    assert got["cut"] == {"side": "away", "left": None}, "a goal on the power play ends a minor; the time is not told"
    assert got["even"] is None


def test_each_sides_game_the_race_and_the_clock_come_off_the_events():
    got = _node(f"""
      const d = {json.dumps(_deep())};
      const ot = JSON.parse(JSON.stringify(d)); ot.rink.clock = {{ period: 4, type: "OT", left: "4:00" }};
      const po = JSON.parse(JSON.stringify(ot)); po.rink.game_type = 3;
      const off = JSON.parse(JSON.stringify(d)); delete off.rink.clock;
      return {{ t: Q.teamStats(d), f: Q.flow(d), p: Q.pressure(d, 300), q: Q.quiet(d),
               now: [Q.nowElapsed(d), Q.nowElapsed(ot), Q.nowElapsed(po), Q.nowElapsed(off)] }};""")
    if got is None:
        return
    bos, nyr = got["t"]["home"], got["t"]["away"]
    assert (bos["goals"], bos["sog"], bos["att"], bos["hits"], bos["blocks"]) == (1, 4, 5, 1, 1)
    assert (nyr["goals"], nyr["sog"], nyr["att"], nyr["take"], nyr["give"], nyr["pim"]) == (0, 0, 1, 1, 1, 2)
    assert (bos["fow"], nyr["fow"], bos["fo"]) == (1, 1, 2)
    assert (bos["ppo"], bos["ppg"]) == (1, 1), "the goal came at five on four"
    assert round(bos["xg"], 2) == 0.5 and bos["xgn"] == 5 and nyr["xgn"] == 0, "our model on each unblocked attempt"
    assert got["f"]["goals"] == [{"t": 1450, "side": "home", "n": 3}] and len(got["f"]["pts"]) == 7
    assert got["p"] == {"away": 0, "home": 2} and got["q"] == {"away": 2640, "home": 80}
    assert got["now"] == [2640, 3660, 4560, 2640], "the third at 16:00; overtime five minutes, a playoff's twenty"


def test_the_rink_on_the_picture_puts_each_point_where_it_was_read():
    got = _node("return { cp: Q.CP.map(([uv, px]) => [uv, px, Q.toArt(uv[0], uv[1])]), far: Q.toArt(150, 60), edge: Q.toArt(99, 42) };")
    if got is None:
        return
    inside = [(uv, want, at) for uv, want, at in got["cp"] if abs(uv[0]) <= 99 and abs(uv[1]) <= 42]
    assert len(inside) == 17, len(inside)
    for uv, want, at in inside:
        assert abs(want[0] - at[0]) < 0.5 and abs(want[1] - at[1]) < 0.5, (uv, want, at)
    # A point on the boards themselves is held a foot inside them: within a
    # foot of the art's own scale (about eleven pixels at the end boards).
    for uv, want, at in got["cp"]:
        assert abs(want[0] - at[0]) < 12 and abs(want[1] - at[1]) < 12, (uv, want, at)
    assert len(got["cp"]) == 25 and got["far"] == got["edge"], "a spot past the boards is held at them"


def test_each_side_wears_a_colour_that_reads_on_the_dark_panels():
    got = _node("""return [["NYR", "BOS"], ["BOS", "NYR"], ["TOR", "TBL"], ["EDM", "WSH"], ["PIT", "LAK"], ["XXX", "YYY"]]
      .map(([away, home]) => Q.colours({ away, home }));""")
    if got is None:
        return
    assert got[0] == {"home": "#fdb927", "away": "#1a52c3"}, "the Rangers in their blue, lifted to read, as Ethan's render"
    assert got[1] == {"home": "#1a52c3", "away": "#fdb927"}
    assert got[2] == {"home": "#325ba0", "away": "#ffffff"}, "two blues alike: the away side takes its white"
    assert got[3] == {"home": "#c8102e", "away": "#ff4c00"}, "a navy far too dark gives way: Washington red, Edmonton orange"
    assert got[4] == {"home": "#a2aaad", "away": "#fcb514"}, "black gives way: the Kings' silver, the Penguins' gold"
    assert got[5] == {"home": "var(--text-mute)", "away": "var(--brand)"}, "a club off the table takes the site's own"


def test_a_play_reads_as_the_feeds_codes_and_names():
    got = _node(f"""
      const d = {json.dumps(_deep())};
      const k = {{ men: Object.fromEntries(Object.values(d.rink.players).map((p) => [p.name, p])) }};
      const by = Object.fromEntries(d.rink.events.map((e) => [e.id, e]));
      return [11, 7, 4, 17, 8, 13, 2].map((i) => Q.playWords(by[i], d, k));""")
    if got is None:
        return
    goal, pen, block, face, stop, miss, first = got
    assert goal == {"title": "Goal", "sub": "#88 David Pastrnak (PP) · wrist · assist #63 Brad Marchand, #73 Charlie McAvoy"}
    assert pen == {"title": "Penalty", "sub": "Hooking · 2 min · #23 Adam Fox · drawn by #88 David Pastrnak"}
    assert block == {"title": "Blocked shot", "sub": "shot by #93 Mika Zibanejad · blocked by #73 Charlie McAvoy"}
    assert face == {"title": "Faceoff", "sub": "Won by #93 Mika Zibanejad over #28 Elias Lindholm"}
    assert stop == {"title": "Stoppage", "sub": ""}, "the sentence never reached the page"
    assert miss["sub"] == "#88 David Pastrnak · slap · wide of net" and first["title"] == "Faceoff"


# --- the parts it hands the page -----------------------------------------------------
def test_the_parts_are_the_arena_the_newest_event_the_power_play_and_the_stats_cards():
    """One page for every sport (detail.js gpPageHTML, 21 November 2026). This file drew a page of its own: a
    scoreboard, the arena, a play list down the right, and stats, lineup and odds cards. It hands the page its
    parts now, and nothing else."""
    P = _parts(_deep(), {"home": "BOS", "away": "NYR", "spread": -1.5, "total": 6.5})
    if P is None:
        return
    assert set(P) == {"stage", "now", "rows", "teamStats", "boxes", "statsExtra", "ball", "ballIcon", "ballTitle",
                      "mid", "down", "live", "says", "wire"}, sorted(P)
    stage = P["stage"]
    # The arena, in the page's own box (gpStageHTML), in the clubs' colours.
    assert stage.startswith('<div class="card gp-stage rc-stage v-live" style="--ca:#1a52c3;--ch:#fdb927">'), stage[:120]
    for key, label in (("live", "Live"), ("shots", "Shot Chart"), ("ice", "Ice Tracker"), ("tracker", "Player Tracker"),
                       ("flow", "Game Flow")):
        assert f'data-rc-view="{key}"' in stage and f'aria-label="{label}"' in stage, key
    assert 'data-rc-full aria-label="Full screen"' in stage
    assert "img/arena/nhl-arena.webp 1280w" in stage and "img/arena/nhl-arena@640.webp 640w" in stage
    assert '<div class="rc-venue"><b>TD Garden</b><span>Boston</span></div>' in stage
    assert "BOS power play · 1:40" in stage, "the badge on the arena"
    assert 'class="rc-arrow"' in stage, "the newest event is NYR's faceoff win: the puck is theirs"
    # The run is the period's (2026-10-15): the miss and the shot each fly to
    # the net and play goes on from there, one join; the faceoff is the drop
    # and is joined to nothing — the puck appears on the dot. (Without the
    # shared timeline every mark is drawn where it is.)
    still = _parts(_deep(), gc=False)["stage"]
    assert still.count('class="rc-flight') == 2 and still.count('class="rc-trail"') == 1, "a faceoff is the drop: nothing to join it to"
    # Under the clock on the page's score: the power play in the side's colour and the shots (gpChipHTML, gpNoteHTML);
    # the bar that stays says the power play too; and the clock is the league's own.
    assert P["mid"] == '<span class="gp-sb-chip" style="--pc:#fdb927">PP BOS 1:40</span><span class="gp-sb-note">SOG 0 – 4</span>'
    assert P["down"] == "PP BOS 1:40" and P["live"] == {"period": "P3", "clock": "16:00"}
    assert (P["ball"], P["ballIcon"], P["ballTitle"]) == ("away", "hockey", "Puck — from the last play")
    # The newest event on the card every sport's is drawn on (gamecast.js playNowHTML), said in a sentence.
    now = P["now"]
    assert now.startswith('<div class="card gc-dv" data-gc-dv>')
    assert '<div class="gc-k">Last play · P3 16:00</div><b>Faceoff</b>' in now
    assert '<p class="gc-dv-said">Mika Zibanejad wins the faceoff over Elias Lindholm in the NYR end.</p>' in now
    assert now.count('class="gc-chip"') == 2 and "NYR · C · #93" in now and "0 G, 0 A, 1 SOG" in now
    assert "power play" not in now and "Puck:" not in now, "the score above says both, once"
    # The league's own events as the rows of the period cards and of the list beside the page, each with its
    # words; a row keeps the league's id, the key its thread in the chat is filed under.
    assert [r["id"] for r in P["rows"]] == list(range(1, 18)) and all(r["kind"] == "hockey" for r in P["rows"])
    goal = {k: v for k, v in P["rows"][10].items() if k != "rink"}
    assert goal == {"kind": "hockey", "id": 11, "period": 2, "clock": "15:50", "team": "BOS", "player": "David Pastrnak",
                    "event": "goal", "scoring": True, "shot": False, "away_score": 0, "home_score": 1}
    assert P["says"][10] == {"html": "<b>David Pastrnak</b> scores on the power play (wrist), from <b>Brad Marchand</b> and <b>Charlie McAvoy</b>"}
    assert P["says"][0] == {"moment": "Start of the 1st period"} and P["says"][7] == {"moment": "Stoppage"}, \
        "the sentence never reached the page"
    # The Stats room, in the page's own cards (gpTsCardHTML, gpBoxCardHTML, gpCardHTML): the team stats counted
    # off the league's events, both box scores, then what only hockey has.
    assert P["teamStats"].startswith('<div class="card gp-card gp-tscard">')
    for label in ("Shots on goal", "Shot attempts", "Faceoff %", "Hits", "Power plays", "xG · our model"):
        assert f"<span>{label}</span>" in P["teamStats"], label
    assert P["boxes"].count('<div class="card gp-card gp-boxcard">') == 2
    for head in ("Forwards", "Defense", "Goalies"):
        assert P["boxes"].count(f'<th scope="col">{head}</th>') == 2, head
    assert '<th scope="row" title="Mika Zibanejad">Mika Zibanejad <span class="gp-pos">#93</span></th>' in P["boxes"]
    extra = P["statsExtra"]
    assert extra.count('<div class="card gp-card rc-icecard" style="--ca:#1a52c3;--ch:#fdb927">') == 2
    assert "<b>Shot chart</b><span>every attempt, from above</span>" in extra and "<b>Trends</b>" in extra
    assert 'class="rc-flat"' in extra and "NYR shoot at the left net, BOS at the right" in extra
    assert "Last five minutes: NYR <b>0</b> attempts, BOS <b>2</b>." in extra
    assert "goals saved above expected" in extra and "our model" in extra
    # And none of the page it used to draw.
    whole = json.dumps(P)
    for gone in ("rc-score", "rc-right", "rc-lineup", "rc-odds", "rc-line-k", "rc-ts-k", "rc-play-list", "gch-entry-slot",
                 "pbp-game-door", "Win chance (our model)", "<nav>", "pbp-foot"):
        assert gone not in whole, gone
    assert SENTENCE not in whole and "onclick" not in whole and "onerror" not in whole
    assert P["wire"] == "function"


def test_the_live_view_flies_the_last_shot_and_joins_its_sequence():
    P = _parts(_deep(upto=14))
    if P is None:
        return
    stage = P["stage"]
    # The puck runs the sequence on the shared timeline (QBGamecast.track):
    # a translate along the points, not a flight of its own.
    assert 'class="rc-flight' in stage and '<animateTransform attributeName="transform" type="translate"' in stage and 'class="rc-ring"' in stage
    assert stage.count('class="rc-trail"') == 1, "the miss and the shot of the third, joined"
    assert 'data-half="right"' in stage, "a phone sees the half the shot went up in"
    assert "rc-arrow" not in stage and P["ball"] == "", "after a shot the puck is loose: no arrow, nobody's puck"
    # What the caption under the arena said is the page's card now.
    assert '<div class="gc-k">Last play · P3 17:20</div><b>Shot on goal</b>' in P["now"]
    assert '<p class="gc-dv-said">Brad Marchand shoots (backhand), saved by Igor Shesterkin in the NYR end.</p>' in P["now"]
    assert "3 saves on 4" in P["now"], "the goalie's game beside the shooter's"


def test_what_the_feed_does_not_carry_draws_nothing_and_a_final_holds_no_puck():
    bare = _deep(situation=False, box=False, xg=False)
    bare["rink"].pop("venue")
    P = _parts(bare)
    if P is None:
        return
    assert "rc-venue" not in P["stage"] and "xG" not in json.dumps(P)
    assert P["boxes"] is None, "no league box score: the page's own, off the game file, stands (detail.js gpStatsHTML)"
    assert P["mid"] == '<span class="gp-sb-note">SOG 0 – 4</span>' and P["down"] == "", "no power play the sheet cannot back"
    final = _parts(_deep(state="final"))
    assert final["ball"] == "" and final["now"] == "" and final["live"] is None and final["down"] == ""
    assert "rc-arrow" not in final["stage"] and "rc-ppbadge" not in final["stage"] and "gp-sb-chip" not in final["mid"]
    # A final opens on its shot chart, with no Live view to choose (tests/test_a_finished_game_is_its_record.py).
    assert 'class="card gp-stage rc-stage v-shots"' in final["stage"] and 'data-rc-view="live"' not in final["stage"]
    pre = _deep(state="scheduled")
    pre["rink"]["events"], pre["rink"]["box"] = [], {}
    pre["live"] = {"state": "scheduled", "start_time": "2026-10-15T23:00Z"}
    P = _parts(pre)
    assert (P["stage"], P["now"], P["statsExtra"], P["ball"], P["mid"], P["live"]) == ("", "", "", "", "", None), \
        "before the puck drops there is no arena to draw: the page's own score says Puck drop"
    assert P["rows"] is None and P["teamStats"] is None and P["boxes"] is None, "nothing counted yet: the page's own stand"
    assert 'mlb: "First pitch", nba: "Tip-off", wnba: "Tip-off", cbb: "Tip-off", nhl: "Puck drop"' in APP


def test_the_views_draw_the_shots_the_ice_the_men_and_the_race():
    got = _node(f"""
      let redraws = 0, binds = 0;
      globalThis.renderPbpPage = () => {{ redraws++; }};
      const host = {{ dataset: {{}}, contains: () => true, querySelector: () => null,
                     addEventListener: (t, f) => {{ binds++; host["on" + t] = f; }} }};
      const ctx = {{ d: {json.dumps(_deep())}, league: "nhl", boardGame: null, faces: {{}} }};
      Q.parts(ctx).wire(host); Q.parts(ctx).wire(host);      // bound once, however often the page is drawn
      const click = (attr, v) => host.onclick({{ target: {{ closest: () => ({{ dataset: {{ [attr]: v }}, hasAttribute: () => false }}) }} }});
      const out = {{}};
      click("rcView", "shots"); out.shots = Q.parts(ctx).stage;
      click("rcShots", "away"); out.away = Q.parts(ctx).stage;
      click("rcView", "ice"); out.ice = Q.parts(ctx).stage;
      click("rcIce", "hit"); out.hits = Q.parts(ctx).stage;
      click("rcView", "tracker"); out.tracker = Q.parts(ctx).stage;
      click("rcView", "flow"); out.flow = Q.parts(ctx).stage;
      out.redraws = redraws; out.binds = binds;
      return out;""")
    if got is None:
        return
    marks = lambda html: len(re.findall(r'class="rc-shot (?:made|miss|block)"', html))
    assert "rc-stage v-shots" in got["shots"] and marks(got["shots"]) == 6, "five BOS attempts and NYR's blocked one"
    assert marks(got["away"]) == 1 and 'data-half="left"' in got["away"] and "NYR 0/0" in got["away"] and "BOS 1/4" in got["away"]
    ice = lambda html: len(re.findall(r'class="rc-ice ', html))
    assert ice(got["ice"]) == 5 and ice(got["hits"]) == 1, "the giveaway off the ice is never drawn"
    assert got["tracker"].count('class="rc-trk-row"') == 8 and got["tracker"].count('class="rc-trk-row goalie"') == 2
    assert "Who is on the ice is not in the league's live feed" in got["tracker"]
    assert 'class="rc-flow"' in got["flow"] and "Attempts <b>1</b> – <b>5</b>" in got["flow"]
    # A reader's choice draws the page again (detail.js renderPbpPage), which keeps the picture already painted.
    assert (got["redraws"], got["binds"]) == (6, 1)
    assert 'class="rc-pane" data-gp-scroll="rc-tracker"' in got["tracker"] and 'data-gp-scroll="rc-flow"' in got["flow"]


# --- the page: the wiring ----------------------------------------------------------
def test_the_page_asks_for_the_parts_and_a_game_without_the_leagues_events_is_the_plain_page():
    det = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
    assert 'const GP_SPORT_FILE = { nba: "hoopscast", wnba: "hoopscast", cbb: "hoopscast", nhl: "rinkcast" };' in det
    mod = det[det.index("function gpSportMod(league, d) {"):det.index("function gpPlainKit(o) {")]
    assert 'if (!name || (name === "rinkcast" && !(d || {}).rink)) return { mod: null, wait: "" };' in mod, \
        "a game without the league's events is drawn from the game file alone"
    assert 'el.addEventListener("error", done("failed"));' in mod, "a file that will not load leaves the sport on the plain page"
    plain = det[det.index("function gpPlainKit(o) {"):det.index("function gpKit(o) {")]
    assert "return { now: GC.plainNow ? GC.plainNow(o.d, o.league, o.faces) : \"\" };" in plain
    kit = det[det.index("function gpKit(o) {"):det.index("function gpStageHTML(")]
    assert "try { return { ...plain, ...mod.parts(o) }; } catch (e) {" in kit, "a part that throws leaves the page on the plain ones"
    # The old handover (js/gamecast.js `rink`, a page of its own drawn into the host) is gone.
    assert "function rink(" not in GC and "QBRink" not in GC
    assert "function render(" not in RC and "host.innerHTML" not in RC, "the page is drawn by the page"
    assert not re.search(r'class="[^"]*\bgp-', RC), "the page's own class names are written by the page's builders"
    for inline in ("onclick", "onerror=", "onload=", "onchange", "eval(", "new Function"):
        assert inline not in RC, f"{inline}: the page's CSP forbids it"
    assert 'data-onerr="remove"' in RC, "a face that will not load goes, through visuals.js"
    assert "window.QBRink = {\n    parts,\n" in RC


def test_the_redraw_keeps_the_picture_and_the_scroll():
    """The page's own rule since 21 November 2026 (detail.js gpHoldTake, gpHoldGive; pinned in
    tests/test_the_nba_live_page.py): the sport names what a redraw must leave as it is."""
    assert 'const PICTURE = `<picture data-gp-hold="arena">' in RC
    assert '`<div class="rc-pane" data-gp-scroll="rc-${view}">${pane}</div>`' in RC


def test_the_stylesheet_is_the_sites_tokens():
    for m in re.finditer(r"#[0-9a-fA-F]{3,8}\b", RC_CSS):
        raise AssertionError(f"a raw colour in css/rinkcast.css: {m.group(0)}")
    for m in re.finditer(r"transition:[^;]+;", RC_CSS):
        assert "var(--dur-" in m.group(0) and "var(--ease-" in m.group(0), m.group(0)
    assert "@media (prefers-reduced-motion: reduce) { .rc-ring { animation: none; } }" in RC_CSS
    styles = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")
    defined = set(re.findall(r"(--[\w-]+)\s*:", styles + RC_CSS + RC))
    for name in set(re.findall(r"var\((--[\w-]+)", RC_CSS + RC)):
        assert name in defined, f"{name} is read and never defined"
    assert ".rc-vs { display: none; }" in RC_CSS and ".rc-vl { display: none; }" in RC_CSS, "a phone reads the short tab words"
    for f in ("nhl-arena.webp", "nhl-arena.jpg", "nhl-arena@640.webp", "nhl-arena@640.jpg"):
        assert (ROOT / "web" / "img" / "arena" / f).exists(), f
    big = (ROOT / "web" / "img" / "arena" / "nhl-arena.webp").stat().st_size
    small = (ROOT / "web" / "img" / "arena" / "nhl-arena@640.webp").stat().st_size
    assert small < big < 300_000, (small, big)


# --- the page in a browser (opt-in) ------------------------------------------------
def test_the_page_in_a_browser_at_390_and_1280():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    chromium = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium")
    # The period-by-period line the scoreboard feed carries, for the page's line score.
    doc = json.dumps(dict(_deep(), linescores={"NYR": [0, 0, 0], "BOS": [0, 1, 0]}))
    strip = json.dumps({"games": [{"event_id": "401802123", "home": "BOS", "away": "NYR", "live": _deep()["live"]}]})
    srv, port = rendercheck._serve()
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--disable-background-networking"]}
            if os.path.exists(chromium):
                kw["executable_path"] = chromium
            browser = pw.chromium.launch(**kw)
            try:
                for width in (390, 1280):
                    ctx = browser.new_context(viewport={"width": width, "height": 900}, is_mobile=width < 600,
                                              has_touch=width < 600, service_workers="block")
                    page = ctx.new_page()
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    # Nothing leaves the machine: fonts, logos and faces are refused.
                    page.route(lambda url: not url.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    page.route("**/data/pbp/nhl_401802123.json*", lambda r: r.fulfill(status=200, content_type="application/json", body=doc))
                    page.route("**/data/live_nhl.json*", lambda r: r.fulfill(status=200, content_type="application/json", body=strip))
                    page.goto(f"http://127.0.0.1:{port}/index.html#pbp/nhl/401802123", wait_until="load")
                    # Thirty and twenty seconds (gate 169, 2026-11-09): three browser
                    # files at a time on the gate; a page that is ready returns at once.
                    page.wait_for_selector(".gp .rc-stage .rc-photo", timeout=30000)
                    page.evaluate("document.querySelectorAll('#tour-overlay, .tour-pop').forEach((n) => n.remove())")
                    page.wait_for_function("() => document.querySelector('.rc-photo').naturalWidth > 0", timeout=20000)
                    assert page.query_selector(".rc-svg .rc-ring"), "the newest event, ringed"
                    # THE ONE PAGE, in football's order: the bar that stays, the score, the arena where the field
                    # is, the line score, the play right now, the tabs and the room behind them.
                    order = page.evaluate("""(() => {
                      const main = document.querySelector('.pbp-layout.gp .pbp-main');
                      const want = ['.gp-stick', '.pbp-hero', '.gp-stage', '.gp-line', '.gc-dv', '.pbp-tabs', '.pbp-panel'];
                      return want.map((sel) => { const el = main.querySelector(':scope > ' + sel); return el ? [...main.children].indexOf(el) : -1; });
                    })()""")
                    assert all(i >= 0 for i in order) and order == sorted(order), order
                    assert page.evaluate("[...document.querySelectorAll('.pbp-tabs .pbp-tab')].map((b) => b.textContent.trim())")[:4] == \
                        ["Stats", "Play-By-Play", "Standings", "Our picks"]
                    assert not page.query_selector(".rc-score") and not page.query_selector(".rc-right"), "no page of its own"
                    # The score: the league's clock, the power play and the shots under it, the puck's side marked.
                    hero = page.evaluate("document.querySelector('.pbp-hero').textContent.replace(/\\s+/g, ' ')")
                    assert "PP BOS 1:40" in hero and "SOG 0 – 4" in hero, hero
                    # A live game opens on its plays: the league's events, a period a card, the third open.
                    assert page.evaluate("document.querySelector('.pbp-tab.active').dataset.pbpTab") == "plays"
                    assert page.evaluate("document.querySelectorAll('details.gp-dr').length") == 3
                    rows = page.evaluate("[...document.querySelectorAll('details.gp-dr[open] .lb-play')].map((r) => r.textContent.replace(/\\s+/g, ' ').trim())")
                    assert len(rows) == 6 and "Mika Zibanejad wins the faceoff over Elias Lindholm" in rows[0], rows[:2]
                    assert "Mika Zibanejad wins the faceoff over Elias Lindholm in the NYR end." in \
                        page.evaluate("document.querySelector('.gc-dv .gc-dv-said').textContent")
                    # The five views fit across a phone; nothing scrolls sideways.
                    assert page.evaluate("(() => { const v = document.querySelector('.rc-views'); return v.scrollWidth <= v.clientWidth + 1; })()")
                    page.click("[data-rc-view='shots']")
                    page.wait_for_selector(".rc-stage.v-shots")
                    assert len(page.query_selector_all(".rc-stage.v-shots .rc-svg .rc-shot")) == 6
                    page.click("[data-rc-view='tracker']")
                    page.wait_for_selector(".rc-stage.v-tracker")
                    assert len(page.query_selector_all(".rc-trk-row")) == 10
                    page.click("[data-rc-view='flow']")
                    page.wait_for_selector(".rc-pane .rc-flow")
                    page.click("[data-rc-view='live']")
                    page.wait_for_selector(".rc-stage.v-live")
                    # A redraw keeps the picture already painted (detail.js gpHoldGive).
                    page.evaluate("document.querySelector('.rc-photo').__kept = 1")
                    assert page.evaluate("renderPbpPage().then(() => document.querySelector('.rc-photo').__kept === 1)"), \
                        "the redraw painted a new picture"
                    # The Stats room: hockey's own count in the page's cards, then the shot chart and the trends.
                    page.click(".pbp-tabs [data-pbp-tab='stats']")
                    page.wait_for_selector(".pbp-panel[data-pbp-panel='stats'] .rc-icecard")
                    heads = page.evaluate("[...document.querySelectorAll('.pbp-panel .gp-card-head b')].map((b) => b.textContent)")
                    assert heads.index("Team stats") < heads.index("Rangers") < heads.index("Bruins") < heads.index("Shot chart") < heads.index("Trends"), heads
                    assert page.evaluate("document.scrollingElement.scrollWidth") <= width
                    assert not errors, errors
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()


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
