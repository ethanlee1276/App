"""The NHL live page: what the league's own feed gives it, and how it is drawn.

Ethan, 2026-10-15, with two renders (the Qellys rink, and the page laid out
like ESPN's app: the scoreboard, the arena with Live / Shot Chart / Ice
Tracker / Player Tracker / Game Flow, the plays down the right, then the
team stats, the lineups and the odds) and his phone's screenshot of the old
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
from _app import app_js  # noqa: E402  (app.js and the rooms it loads on first use)

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
    (QBGamecast.track) that moves the puck. Without it the page draws every
    mark where it is, which is what a reader who asked for less motion sees."""
    node = shutil.which("node")
    if not node:
        return None
    prog = f"{TEAMS}\n{STUBS}\n{GC if gc else ''}\n{RC}\nconsole.log(JSON.stringify((() => {{ const Q = window.QBRink; {js} }})()));"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def _page(doc, board=None, gc=False):
    return _node(f"""
      const host = {{ innerHTML: "", dataset: {{}}, querySelector: () => null, addEventListener: () => {{}} }};
      const ctx = {{ d: {json.dumps(doc)}, league: "nhl", stripHTML: "<nav>strip</nav>", back: "<b>back</b>",
                    boardGame: {json.dumps(board)}, faces: {{}}, wire: () => {{}} }};
      Q.render(host, ctx);
      return host.innerHTML;""", gc=gc)


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


# --- the page: what it draws -------------------------------------------------------
def test_the_page_draws_the_scoreboard_the_arena_the_plays_and_the_three_cards():
    board = {"home": "BOS", "away": "NYR", "spread": -1.5, "total": 6.5, "home_ml": -150, "away_ml": 130}
    html = _page(_deep(), board)
    if html is None:
        return
    assert html.startswith("<nav>strip</nav>") and html.endswith("<b>back</b>"), "app.js's strip and way back"
    for part in ('class="card rc-score"', 'class="card rc-stage v-live"', 'class="card rc-card rc-right"',
                 'class="card rc-card rc-stats"', 'class="card rc-card rc-lineup"', 'class="card rc-card rc-odds"'):
        assert part in html, part
    for key, label in (("live", "Live"), ("shots", "Shot Chart"), ("ice", "Ice Tracker"), ("tracker", "Player Tracker"),
                       ("flow", "Game Flow")):
        assert f'data-rc-view="{key}"' in html and f'aria-label="{label}"' in html, key
    assert 'data-rc-full aria-label="Full screen"' in html
    assert "img/arena/nhl-arena.webp 1280w" in html and "img/arena/nhl-arena@640.webp 640w" in html
    assert '<div class="rc-venue"><b>TD Garden</b><span>Boston</span></div>' in html
    score = html.split('class="card rc-stage')[0]
    assert ">PP BOS 1:40</span>" in score and "SOG 0 – 4" in score and "4-2-0" in score and ">Rangers</b>" in score
    assert "BOS power play · 1:40" in html, "the badge on the arena"
    # The newest event is NYR's faceoff win: the puck is theirs, said once, and the sequence starts at the dot.
    assert 'class="rc-arrow"' in html and "Puck: NYR" in html and 'class="rc-puckmark"' in html.split('class="rc-side home"')[0]
    # The run is the period's (2026-10-15): the miss and the shot each fly to
    # the net and play goes on from there, one join; the faceoff is the drop
    # and is joined to nothing — the puck appears on the dot.
    stage = html.split('class="card rc-stage')[1].split('class="card rc-card rc-right"')[0]
    assert stage.count('class="rc-flight') == 2 and stage.count('class="rc-trail"') == 1, "a faceoff is the drop: nothing to join it to"
    # The plays: the period being played, newest first; the choices.
    assert len(re.findall(r'<div class="rc-play k-', html)) == 6
    assert html.index("Won by #93 Mika Zibanejad") < html.index("Missed shot"), "newest first"
    assert ">Now — 3rd period</option>" in html and ">1st period</option>" in html and ">Every play</option>" in html
    # The cards: the bars, the lineup, the board's lines and our win chance.
    assert 'class="rc-ts-k">Shots on goal</span>' in html and 'class="rc-ts-k">xG · our model</span>' in html
    assert ">Mika Zibanejad</td>" in html and "<p class=\"rc-mini-k\">Defence</p>" in html
    for line in ("Puck line", "Moneyline", "Total goals"):
        assert f'<span class="rc-line-k">{line}</span>' in html, line
    assert "NYR +1.5" in html and "BOS -1.5" in html and "Over 6.5" in html and "NYR +130" in html
    assert "Win chance (our model)" in html and "<b>71%</b> BOS" in html
    assert 'id="pbp-game-door" data-gid="NYR@BOS"' in html
    assert SENTENCE not in html and "onclick" not in html and "onerror" not in html


def test_the_live_view_flies_the_last_shot_and_joins_its_sequence():
    html = _page(_deep(upto=14), gc=True)
    if html is None:
        return
    stage = html.split('class="card rc-stage')[1].split('class="card rc-card rc-right"')[0]
    # The puck runs the sequence on the shared timeline (QBGamecast.track):
    # a translate along the points, not a flight of its own.
    assert 'class="rc-flight' in stage and '<animateTransform attributeName="transform" type="translate"' in stage and 'class="rc-ring"' in stage
    assert stage.count('class="rc-trail"') == 1, "the miss and the shot of the third, joined"
    assert 'data-half="right"' in stage, "a phone sees the half the shot went up in"
    assert "Shot on goal" in stage and "saved by #31 Igor Shesterkin" in stage and "in the NYR end" in stage
    assert "rc-arrow" not in stage, "after a shot the puck is loose: no arrow"


def test_what_the_feed_does_not_carry_draws_nothing_and_a_final_holds_no_puck():
    bare = _deep(situation=False, box=False, xg=False)
    bare["rink"].pop("venue")
    html = _page(bare)
    if html is None:
        return
    assert "rc-venue" not in html and "xG" not in html and "our model</i>" not in html
    assert "The lineups fill in from the league's box score once the game is on." in html
    final = _page(_deep(state="final"))
    assert "rc-arrow" not in final and "rc-puckmark" not in final and "rc-pp" not in final and "Puck:" not in final
    assert '<span class="rc-per">Final</span>' in final and ">Latest — 3rd period</option>" in final
    pre = _deep(state="scheduled")
    pre["rink"]["events"], pre["rink"]["box"] = [], {}
    pre["live"] = {"state": "scheduled", "start_time": "2026-10-15T23:00Z"}
    html = _page(pre)
    assert "Puck drop" in html and "No plays yet." in html and "The team stats fill in from the opening faceoff." in html


def test_the_views_draw_the_shots_the_ice_the_men_and_the_race():
    got = _node(f"""
      const host = {{ innerHTML: "", dataset: {{}}, querySelector: () => null, addEventListener: (t, f) => {{ host["on" + t] = f; }} }};
      const ctx = {{ d: {json.dumps(_deep())}, league: "nhl", boardGame: null, faces: {{}} }};
      Q.render(host, ctx);
      host.contains = () => true;
      const click = (attr, v) => host.onclick({{ target: {{ closest: () => ({{ dataset: {{ [attr]: v }}, hasAttribute: () => false }}) }} }});
      const out = {{}};
      click("rcView", "shots"); out.shots = host.innerHTML;
      click("rcShots", "away"); out.away = host.innerHTML;
      click("rcView", "ice"); out.ice = host.innerHTML;
      click("rcIce", "hit"); out.hits = host.innerHTML;
      click("rcView", "tracker"); out.tracker = host.innerHTML;
      click("rcView", "flow"); out.flow = host.innerHTML;
      click("rcStats", "shots"); out.flat = host.innerHTML;
      click("rcLineup", "goalies"); out.goalies = host.innerHTML;
      click("rcRight", "trends"); out.trends = host.innerHTML;
      click("rcRight", "plays");
      host.onchange({{ target: {{ closest: () => ({{ value: "0" }}) }} }}); out.every = host.innerHTML;
      return out;""")
    if got is None:
        return
    marks = lambda html: len(re.findall(r'class="rc-shot (?:made|miss|block)"', html.split("rc-card rc-right")[0]))
    assert "rc-stage v-shots" in got["shots"] and marks(got["shots"]) == 6, "five BOS attempts and NYR's blocked one"
    assert marks(got["away"]) == 1 and 'data-half="left"' in got["away"] and "NYR 0/0" in got["away"] and "BOS 1/4" in got["away"]
    ice = lambda html: len(re.findall(r'class="rc-ice ', html))
    assert ice(got["ice"]) == 5 and ice(got["hits"]) == 1, "the giveaway off the ice is never drawn"
    assert got["tracker"].count('class="rc-trk-row"') == 8 and got["tracker"].count('class="rc-trk-row goalie"') == 2
    assert "Who is on the ice is not in the league's live feed" in got["tracker"]
    assert 'class="rc-flow"' in got["flow"] and "Attempts <b>1</b> – <b>5</b>" in got["flow"]
    assert 'class="rc-flat"' in got["flat"] and "NYR shoot at the left net, BOS at the right" in got["flat"]
    assert "Goals saved above expected" in got["goalies"] and "our model" in got["goalies"]
    assert "Last five minutes: NYR <b>0</b> attempts, BOS <b>2</b>." in got["trends"]
    assert len(re.findall(r'<div class="rc-play k-', got["every"])) == 17, "every play of the game"


# --- the page: the wiring ----------------------------------------------------------
def test_the_page_is_handed_over_and_loaded_the_way_the_basketball_one_is():
    assert ('if (GC && GC.hoops && GC.hoops(host, { d, league, stripHTML, back, boardGame, faces, wire, '
            'callit: pbpTvHTML(d) + pbpAwayHTML(d, league) + pbpRecapHTML(d, league) + pbpCallItHTML(d, league) })) '
            '{ if (lv.state === "live") again(); return; }') in APP
    assert 'if (host && ctx && ctx.league === "nhl") return rink(host, ctx);' in GC
    assert "function rink(host, ctx)" in GC and 'css.href = "css/rinkcast.css";' in GC and 'el.src = "js/rinkcast.js";' in GC
    assert "if (!ctx.d || !ctx.d.rink || _rinkFailed) return false;" in GC, "a game without the league's events keeps the old rooms"
    assert 'el.addEventListener("error", () => { _rinkFailed = true; resolve(false); });' in GC
    assert "try { return window.QBRink.render(host, ctx); } catch (e)" in GC, "a page that throws hands back to the old rooms"
    for inline in ("onclick", "onerror=", "onload=", "onchange", "eval(", "new Function"):
        assert inline not in RC, f"{inline}: the page's CSP forbids it"
    assert 'data-onerr="remove"' in RC, "a face that will not load goes, through visuals.js"
    assert "window.QBRink = {" in RC


def test_the_redraw_keeps_the_picture_and_the_scroll():
    i = RC.index("  function render(host, ctx, chose) {")
    body = RC[i:RC.index("\n  }\n", i)]
    assert 'host.querySelector(".rc-frame > picture")' in body and "fresh.replaceWith(pic)" in body
    assert '[".rc-play-list", ".rc-pane"]' in body and "same && !chose" in body
    assert RC.count("render(host, S.ctx, true)") == 2, "a reader's own choice starts the list at the top"


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
    doc = json.dumps(_deep())
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
                    page.wait_for_selector(".rc-stage .rc-photo", timeout=15000)
                    page.evaluate("document.querySelectorAll('#tour-overlay, .tour-pop').forEach((n) => n.remove())")
                    page.wait_for_function("() => document.querySelector('.rc-photo').naturalWidth > 0", timeout=8000)
                    assert page.query_selector(".rc-svg .rc-ring"), "the newest event, ringed"
                    assert len(page.query_selector_all(".rc-play")) == 6
                    # The five views fit across a phone; nothing scrolls sideways.
                    assert page.evaluate("(() => { const v = document.querySelector('.rc-views'); return v.scrollWidth <= v.clientWidth + 1; })()")
                    page.click("[data-rc-view='shots']")
                    assert len(page.query_selector_all(".rc-stage.v-shots .rc-svg .rc-shot")) == 6
                    page.click("[data-rc-view='tracker']")
                    assert len(page.query_selector_all(".rc-trk-row")) == 10
                    page.click("[data-rc-view='flow']")
                    assert page.query_selector(".rc-pane .rc-flow")
                    page.click("[data-rc-view='live']")
                    # A redraw keeps the picture already painted, and where the plays were scrolled.
                    page.select_option("[data-rc-q]", "0")
                    page.evaluate("document.querySelector('.rc-photo').__kept = 1; document.querySelector('.rc-play-list').scrollTop = 60")
                    top = page.evaluate("document.querySelector('.rc-play-list').scrollTop")
                    assert page.evaluate("renderPbpPage().then(() => document.querySelector('.rc-photo').__kept === 1)"), \
                        "the redraw painted a new picture"
                    assert page.evaluate("document.querySelector('.rc-play-list').scrollTop") == top
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
