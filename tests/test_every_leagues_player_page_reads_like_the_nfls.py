"""Every league's player page reads like the NFL's (22 November 2026).

Ethan, the Sunday morning: "We want every single sports player pages to match each other and like have it match
ESPN ... NFL is kind of like the one we want to go off of because we put the most work in NFL, so things need to
be matching what NFL looks like and how it runs and how it works, how it gets data." Drawn side by side from the
live site's own player data (Josh Allen, Jeremiah Smith, Jalen Brunson, Caitlin Clark, Connor McDavid, Aaron
Judge, a college guard), the pages differed where the NFL's did not:

  * the header's height and weight were each feed's spelling: 6'5" and 237 lb on the NFL's and the NHL's,
    6' 2" and 190 lbs on the basketball leagues'; every page now says 6'2" and 190 lb (`nfl_height`,
    `nfl_weight`);
  * college football's and baseball's headers said no height, weight or age: their rosters' feeds sent them
    and the parsers dropped them. College football's keeps ESPN's height, weight, class and hometown,
    baseball's MLB's height, weight and hometown (its per-team fallback asks for the person too), and college
    basketball's its class; a college player with no age shows his class there ("Junior"), as ESPN's does;
  * college football's previous game said Ohio State "15-9", counting each copy of a game its games table
    holds twice, where the standings already count it once (standings.once), and one copy dated 1993; the
    record counts each game once, and a game dated outside its own season is none of it;
  * the WNBA's box scores name five clubs by ESPN's codes (GS, LA, LV, NY, WSH) where its team table has its
    own (GSV, LAS, LVA, NYL, WAS): Caitlin Clark's last opponent read "LV" with no name or colour;
  * a basketball rate rode the season's pills as a count: "81 free throw percentage".

    python3 tests/test_every_leagues_player_page_reads_like_the_nfls.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import playerpage as P, rosters as R, standings  # noqa: E402
from engine.sources import cfbdata, espnrosters                  # noqa: E402

PLR = (ROOT / "web" / "js" / "playerpage.js").read_text(encoding="utf-8")
WNBA = (ROOT / "web" / "js" / "teams_wnba.js").read_text(encoding="utf-8")


def test_every_feeds_height_and_weight_read_as_the_nfls():
    for raw, want in (('6\'5"', '6\'5"'), ('6\' 2"', '6\'2"'), ("6-2", '6\'2"'), ("74", '6\'2"'),
                      ("6 ft 2 in", '6\'2"'), ('5\'11"', '5\'11"'), ("", ""), (None, ""), ("tall", "tall")):
        assert P.nfl_height(raw) == want, (raw, P.nfl_height(raw))
    for raw, want in (("237 lb", "237 lb"), ("190 lbs", "190 lb"), ("190", "190 lb"), (210, "210 lb"),
                      ("157 lbs.", "157 lb"), ("", ""), (None, ""), ("heavy", "heavy")):
        assert P.nfl_weight(raw) == want, (raw, P.nfl_weight(raw))
    b = P.bio("nba", "Jalen Brunson", {"height": '6\' 2"', "weight": "190 lbs", "number": 11, "team": "NYK"})
    assert (b["height"], b["weight"], b["number"]) == ('6\'2"', "190 lb", "11")
    c = P.bio("cbb", "A Guard", {"height": '6\' 2"', "weight": "210 lbs", "class": "Junior"})
    assert c["class"] == "Junior"


def test_the_rosters_keep_the_size_class_and_hometown_their_feeds_send():
    espn_college = {"athletes": [{"position": "offense", "items": [{
        "fullName": "Jeremiah Smith", "jersey": "4", "position": {"abbreviation": "WR"},
        "displayHeight": '6\' 3"', "displayWeight": "215 lbs", "experience": {"displayValue": "Junior"},
        "birthPlace": {"city": "Miami Gardens", "state": "FL"}, "headshot": {"href": "https://x/y.png"}}]}]}
    got = cfbdata.parse_team_people(espn_college)[0]
    assert (got["height"], got["weight"], got["class"], got["birthplace"]) == \
        ('6\' 3"', "215 lbs", "Junior", "Miami Gardens, FL"), got
    row = R.cfb_feed_rosters({"OSU": [got]})["teams"]["OSU"]["players"][0]
    assert (row["height"], row["weight"], row["class"], row["birthplace"]) == \
        ('6\' 3"', "215 lbs", "Junior", "Miami Gardens, FL"), row
    hoops = espnrosters.parse_roster({"athletes": [{"fullName": "A Guard", "jersey": "10",
                                                    "displayHeight": '6\' 2"', "displayWeight": "210 lbs",
                                                    "experience": {"displayValue": "Sophomore"}}]})[0]
    assert hoops["class"] == "Sophomore"
    from engine.mlb.sources import mlbstats
    judge = mlbstats._roster_entry({"person": {"fullName": "Aaron Judge", "id": 592450, "birthDate": "1992-04-26",
                                               "height": '6\' 7"', "weight": 282, "birthCity": "Linden",
                                               "birthStateProvince": "CA"},
                                    "position": {"abbreviation": "RF"}, "jerseyNumber": "99"})
    assert (judge["height"], judge["weight"], judge["birthplace"], judge["born"]) == \
        ('6\' 7"', 282, "Linden, CA", "1992-04-26"), judge
    row = R.mlb_feed_rosters({"NYY": [judge]})["teams"]["NYY"]["players"][0]
    assert (row["height"], row["weight"], row["birthplace"]) == ('6\' 7"', 282, "Linden, CA")
    assert P.bio("mlb", "Aaron Judge", row)["weight"] == "282 lb"
    src = (ROOT / "engine" / "mlb" / "sources" / "mlbstats.py").read_text(encoding="utf-8")
    assert "roster?rosterType=active&hydrate=person" in src, "the fallback asks for the person too"


def test_a_college_record_counts_each_game_once_and_none_outside_its_season():
    def g(period, gid, home, away, hs, as_):
        return {"period": period, "game_id": gid, "home": home, "away": away, "hs": hs, "as": as_,
                "date": None, "season": 2026}
    by_id = {
        "401": g("2026-11-14", "401", "OSU", "NU", 28, 19),        # ESPN's copy
        "NU@OSU": g("2026-11-15", "NU@OSU", "OSU", "NU", 28, 19),  # the schedule's, a day later
        "old": g("1993-01-31", "old", "OSU", "NU", 28, 19),        # a copy dated in 1993
        "402": g("2026-11-21", "402", "NEB", "OSU", 31, 28),
        "OSU@NEB": g("2026-11-21", "OSU@NEB", "NEB", "OSU", 31, 28),
        "403": g("2026-11-07", "403", "OSU", "ORE", 28, 41),
    }
    assert P._record(by_id, "OSU", "2026-11-21", "cfb") == "1-2", P._record(by_id, "OSU", "2026-11-21", "cfb")
    assert P._record(by_id, "OSU", "2026-11-21") == "3-3", "without a league, as it was (every copy)"
    # Another league's rows are as they were, whatever their dates.
    nba = {"a": dict(g("2026-11-20", "a", "NYK", "POR", 97, 96)), "b": dict(g("2026-11-20", "b", "NYK", "POR", 97, 96))}
    assert P._record(nba, "NYK", "2026-11-21", "nba") == "2-0"
    rows = [{"season": 2026, "period": "1993-01-31", "home": "OSU", "away": "NU", "game_id": "x"},
            {"season": 2025, "period": "2026-01-19", "home": "OSU", "away": "MIA", "game_id": "cfp"},
            {"season": 2026, "period": "12", "home": "OSU", "away": "MICH", "game_id": "wk"}]
    kept = standings.once("cfb", rows)
    assert [r["game_id"] for r in kept] == ["cfp", "wk"], kept
    src = (ROOT / "engine" / "playerpage.py").read_text(encoding="utf-8")
    assert 'last["record"] = _record(by_id, g["team"], g["period"], sport)' in src


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(js)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_the_wnbas_espn_codes_read_their_clubs_and_no_club_is_listed_twice():
    got = _node(WNBA + """
      console.log(JSON.stringify({ lv: WNBA_TEAMS.LV && WNBA_TEAMS.LV.nick, ny: WNBA_TEAMS.NY && WNBA_TEAMS.NY.nick,
        gs: WNBA_TEAMS.GS && WNBA_TEAMS.GS.name, la: WNBA_TEAMS.LA && WNBA_TEAMS.LA.nick,
        wsh: WNBA_TEAMS.WSH && WNBA_TEAMS.WSH.nick, n: Object.keys(WNBA_TEAMS).length }));""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got == {"lv": "Aces", "ny": "Liberty", "gs": "Golden State Valkyries", "la": "Sparks", "wsh": "Mystics",
                   "n": 15}, got


def test_a_rate_is_no_pill_and_a_college_player_shows_his_class():
    i = PLR.index("const plrIsRate")
    fn = PLR[i:PLR.index(";\n", i) + 2]
    got = _node(fn + """
      console.log(JSON.stringify([plrIsRate({ key: "ftp", label: "FT%", title: "Free throw percentage" }),
        plrIsRate({ key: "fg3p", label: "3P%" }), plrIsRate({ key: "pct", title: "Save percentage" }),
        plrIsRate({ key: "stl", label: "STL", title: "Steals" }), plrIsRate(null)]));""")
    if got is not None:
        assert got == [True, True, True, False, False], got
    assert "PLR_PILL_SKIP.test(col.key) || plrIsRate(col)) continue;" in PLR
    assert "age !== \"\" ? `Age ${age}` : bio.class || \"\"])" in PLR, "the header: his class where he has no age"
    assert '["Class", escapeHtml(b.class || "")]' in PLR, "and the Bio menu"


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    fails = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as exc:                              # noqa: BLE001
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed.")
    sys.exit(1 if fails else 0)
