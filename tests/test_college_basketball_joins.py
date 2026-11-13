"""Men's college basketball, the basketball build's third league (2026-11-13).

Ethan: "we need to add college basketball ... look at all the tools and
resources and data points we use for NBA, and obviously put that towards
college basketball." What these hold, each a way the league could quietly
be wrong while every page looked fine:

  * a school's code is ESPN's for Division I and ``espn:{id}`` for a small
    school, and a summary's team (which carries no conference) is still
    read as the Division I school the scoreboard named;
  * the scoreboard row carries what the college board reads: ranks,
    conferences, ids, the identity a card draws, regulation's two halves;
  * the board buys player prices on the games worth buying — ranked, power
    conference, still to tip — and the pacer meters the pull on those
    games, not on the whole Division I scoreboard;
  * a card's face is the school's own roster photo, so a namesake on
    another school never lends his;
  * every school a build has seen keeps its card (the standings name 365),
    and a rank is never kept;
  * the live score reads halves (``H1``), the live clock knows a college
    half is twenty minutes, and the standings are asked for the season by
    the year it ends;
  * the league is registered wherever the NBA is, the pages included.

Run directly: `python3 tests/test_college_basketball_joins.py`
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())

from engine import cbbteams                                        # noqa: E402
from engine.sources import cbbespn, espnhoops, livescores          # noqa: E402


def _team(abbr, ident, conf="", name="", color="", logo=True):
    t = {"abbreviation": abbr, "id": ident, "displayName": name or abbr,
         "shortDisplayName": name or abbr, "location": name or abbr, "name": "Mascots"}
    if conf:
        t["conferenceId"] = conf
    if color:
        t["color"], t["alternateColor"] = color, "ffffff"
    if logo:
        t["logo"] = f"https://a.espncdn.com/i/teamlogos/ncaa/500/{ident}.png"
    return t


def _event(eid, home, away, state="pre", home_rank=None, away_rank=None,
           neutral=False, conference=False, date="2026-11-14T00:00Z"):
    def comp(t, ha, rank):
        c = {"homeAway": ha, "team": t, "score": "0"}
        if rank:
            c["curatedRank"] = {"current": rank}
        return c
    return {"id": eid, "date": date, "season": {"type": 2},
            "competitions": [{"neutralSite": neutral, "conferenceCompetition": conference,
                              "competitors": [comp(home, "home", home_rank), comp(away, "away", away_rank)],
                              "status": {"period": 0, "type": {"state": state, "completed": state == "post"}}}]}


DUKE = _team("DUKE", "150", "2", "Duke Blue Devils", "003087")
UNC = _team("UNC", "153", "2", "North Carolina Tar Heels", "7BAFD4")
TEXAS = _team("TEX", "251", "23", "Texas Longhorns", "BF5700")
CALVARY = _team("CAL", "9999", "", "Calvary Warriors")          # a small school, ESPN's CAL too


# --------------------------------------------------------------- codes
def test_division_one_keeps_espns_code_and_a_small_school_its_id():
    assert espnhoops.team_key(DUKE, "cbb") == "DUKE"
    assert espnhoops.team_key(CALVARY, "cbb") == "espn:9999"
    # The pro leagues are untouched.
    assert espnhoops.team_key(CALVARY, "nba") == "CAL"


def test_a_summarys_team_is_the_school_the_scoreboard_named():
    """A summary's team dict carries no conference; the id the scoreboard
    tied to a Division I code still reads as that code."""
    espnhoops.team_key(UNC, "cbb")                                  # the scoreboard's read
    bare = {"abbreviation": "UNC", "id": "153"}
    assert espnhoops.team_key(bare, "cbb") == "UNC"
    assert livescores._side_key(bare, "cbb") == "UNC"
    assert espnhoops.team_key({"abbreviation": "XYZ", "id": "77777"}, "cbb") == "espn:77777"


# --------------------------------------------------------------- scoreboard
def test_the_scoreboard_row_carries_what_the_college_board_reads():
    payload = {"events": [_event("401", DUKE, UNC, home_rank=3, away_rank=11, conference=True),
                          _event("402", TEXAS, CALVARY, neutral=True)]}
    rows = {g["game_id"]: g for g in cbbespn.parse_scoreboard(payload)}
    g = rows["401"]
    assert (g["home"], g["away"]) == ("DUKE", "UNC")
    assert (g["home_rank"], g["away_rank"]) == (3, 11)
    assert (g["home_conf"], g["away_conf"]) == ("2", "2") and g["conference_game"]
    assert (g["home_id"], g["away_id"]) == ("150", "153")
    assert g["home_info"]["primary"] == "#003087" and g["home_info"]["logo"].endswith("/150.png")
    assert rows["402"]["away"] == "espn:9999" and rows["402"]["neutral"]
    assert espnhoops.REG_PERIODS["cbb"] == 2
    # Division I, and a page that holds a Saturday.
    assert "groups=50" in espnhoops.SCOREBOARD_QUERY["cbb"]
    assert "groups=50" in livescores.SCOREBOARD_QUERY["cbb"]


def test_the_teams_table_and_the_kept_cards():
    payload = {"events": [_event("401", DUKE, UNC, home_rank=3)]}
    teams = cbbespn.teams_from_games(cbbespn.parse_scoreboard(payload))
    assert teams["DUKE"]["id"] == "150" and teams["DUKE"]["rank"] == 3
    assert teams["DUKE"]["conf"] == "2" and teams["UNC"]["primary"] == "#7BAFD4"
    path = os.path.join(tempfile.mkdtemp(), "cards.json")
    assert cbbteams.remember_cards(teams, path) == 2
    kept = cbbteams.cards(path)
    assert set(kept) == {"DUKE", "UNC"}
    assert "rank" not in kept["DUKE"], "a rank is tonight's, never the school's"
    assert cbbteams.remember_cards(teams, path) == 0, "nothing new, nothing written"
    assert cbbteams.conference("2") == "ACC" and cbbteams.conference("999") == "999"


# --------------------------------------------------------------- what the board buys
def test_the_board_buys_the_ranked_and_power_games_still_to_tip():
    import nba_build
    games = [
        {"home": "A", "away": "B", "state": "scheduled", "kickoff": "2026-11-14T17:00Z",
         "home_conf": "5", "away_conf": "6"},                                   # a small-conference game
        {"home": "DUKE", "away": "UNC", "state": "scheduled", "kickoff": "2026-11-14T23:00Z",
         "home_rank": 3, "away_rank": 11, "home_conf": "2", "away_conf": "2", "conference_game": True},
        {"home": "TEX", "away": "espn:9999", "state": "scheduled", "kickoff": "2026-11-14T18:00Z",
         "home_conf": "23"},
        {"home": "KU", "away": "UK", "state": "live", "kickoff": "2026-11-14T16:00Z",
         "home_rank": 1, "away_rank": 2, "home_conf": "8", "away_conf": "23"},  # already tipped
        {"home": "PUR", "away": "IU", "state": "scheduled", "kickoff": "2026-11-14T20:00Z",
         "home_rank": 9, "home_conf": "7", "away_conf": "7"},
    ]
    picked = [f"{g['away']}@{g['home']}" for g in nba_build.college_board_games(games, cap=3)]
    assert picked == ["UNC@DUKE", "IU@PUR", "espn:9999@TEX"], picked
    assert nba_build.CBB_PROP_GAMES == 5
    assert nba_build.club_ids([{"home": "DUKE", "away": "UNC", "home_id": "150", "away_id": "153"}]) == \
        {"DUKE": "150", "UNC": "153"}


def test_the_pacer_meters_the_games_the_board_names():
    import launch
    board = {"games": [{"home": "DUKE", "away": "UNC", "kickoff": "2026-11-14T23:00:00Z"},
                       {"home": "A", "away": "B", "kickoff": "2026-11-14T17:00:00Z"},
                       {"home": "C", "away": "D", "kickoff": "2026-11-14T18:00:00Z"}],
             "board_games": ["UNC@DUKE"]}
    assert [g["home"] for g in launch._priced_games(board)] == ["DUKE"]
    assert len(launch._priced_games({"games": board["games"]})) == 3, "a board that names none prices all"
    import json
    path = os.path.join(tempfile.mkdtemp(), "cbb.json")
    with open(path, "w") as fh:
        json.dump(board, fh)
    assert launch._prop_games(path) == 1 and launch._slate_games(path) == 3
    assert len(launch._slate_kickoffs(path)) == 1 and launch._games_on_slate(path) == 1


# --------------------------------------------------------------- faces
def test_a_card_wears_its_own_schools_roster_photo():
    import sqlite3
    import nba_build
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE player_assets (sport TEXT, player TEXT, espn_id TEXT, headshot TEXT, seen TEXT,"
                 " PRIMARY KEY (sport, player))")
    conn.execute("INSERT INTO player_assets VALUES ('cbb','Chris Johnson','111','https://x/111.png','2026-11-10')")
    feed = {"DUKE": [{"player": "Chris Johnson", "headshot": "https://x/222.png"}]}
    got = nba_build.board_assets(conn, "cbb", {"DUKE": "150"}, fetch=lambda: (feed, []))
    assert got["Chris Johnson"]["headshot"] == "https://x/222.png"
    # The pro leagues keep the stored table, and a roster that will not
    # load leaves the stored faces as they were.
    assert nba_build.board_assets(conn, "nba", {"DUKE": "150"}) == {}
    broke = nba_build.board_assets(conn, "cbb", {"DUKE": "150"}, fetch=lambda: 1 / 0)
    assert broke["Chris Johnson"]["headshot"] == "https://x/111.png"


def test_college_rosters_are_read_by_team_id_only():
    from engine.sources import espnrosters
    from engine.sources.fetch import DataUnavailable
    asked = []

    def fetch(url, name):
        asked.append(url)
        return {"athletes": [{"fullName": "Cooper Flagg", "position": {"abbreviation": "F"},
                              "headshot": {"href": "https://a.espncdn.com/x.png"}}]}
    feed, missed = espnrosters.fetch_league("cbb", fetch=fetch, team_ids={"DUKE": "150"})
    assert feed["DUKE"][0]["headshot"].startswith("https://") and not missed
    assert asked == [f"{espnrosters.ROOT}/basketball/mens-college-basketball/teams/150/roster"]
    try:
        espnrosters.fetch_league("cbb", fetch=fetch)
    except DataUnavailable:
        pass
    else:
        raise AssertionError("college never walks the whole team list")


def test_the_face_filler_knows_colleges_folder():
    import facesfill
    assert facesfill.ESPN_FACE_DIR["cbb"] == "mens-college-basketball"


# --------------------------------------------------------------- the clock and the table
def test_the_live_score_and_clock_read_halves():
    from engine import livewp
    assert livescores.PERIOD_LETTER["cbb"] == "H"
    assert livewp.seconds_left("cbb", "H1", "10:00") == 1800.0
    assert livewp.seconds_left("cbb", "H2", "0:30") == 30.0
    assert livewp.seconds_left("cbb", "H3", "4:00") is None, "overtime has no regulation clock"


def test_the_standings_group_by_the_feeds_conference_tables():
    from engine.sources import leaguestandings as LS
    payload = {"children": [{"abbreviation": "ACC", "standings": {"entries": [
        {"team": {"abbreviation": "DUKE"}, "stats": [{"name": "wins", "value": 3}, {"name": "losses", "value": 0}]}]}}]}
    rows = LS.parse_espn(payload, groups=True)
    assert rows[0]["group"] == "ACC" and "group" not in LS.parse_espn(payload)[0]
    assert "cbb" in LS.GROUPED_BY_FEED and LS.ESPN_SEASON_SHIFT["cbb"] == 1


# --------------------------------------------------------------- registered everywhere
def test_the_league_is_registered_where_the_nba_is():
    import launch
    import server
    from engine import coverage, db, gate, hoops, ledger, oddsplan, potd, seasons
    from engine.sources import espninjuries, news, oddsapi
    assert launch.SPORT_PRIORITY.index("cbb") == launch.SPORT_PRIORITY.index("nba") + 1
    assert launch.BOARD_FILES["cbb"] == launch.CBB_OUT == "web/data/cbb.json"
    assert "cbb" in launch.FINAL_WATCH and launch._SPORT_REFRESH["cbb"] == "refresh_cbb"
    assert server.LIVE_FILES["cbb"].name == "cbb.json"
    assert "cbb" in coverage.BUILDERS and "cbb" in db.CORE_SPORTS and "cbb" in seasons.HEAVY
    assert hoops.for_league("cbb").game_minutes == 40 and hoops.for_league("cbb").probation
    assert "cbb" in ledger.TRACKED_SPORTS and "cbb" in ledger.POTD_LEAGUES
    assert "cbb" not in ledger.LIKELY_LIVE_SPORTS, "on probation: nothing staked"
    assert "cbb" in potd.TOP_PICK_LEAGUES and ("cbb",) in oddsplan.TIERS
    assert oddsapi.SPORT_CONFIG["cbb"]["sport_key"] == "basketball_ncaab"
    assert "cbb" in espninjuries.LEAGUES and "cbb" in news.FEEDS
    for name in ("cbb.json", "live_cbb.json", "rosters_cbb.json", "standings_cbb.json"):
        src = (ROOT / "engine" / "gate.py").read_text()
        assert f'"{name}"' in src, name
    assert gate is not None


def test_the_pages_draw_it():
    js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert 'api: "/api/cbb/recommendations", fallback: "data/cbb.json"' in js
    assert 'cbb: "data/live_cbb.json"' in js and 'cbb: "mens-college-basketball"' in js
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert 'data-sport="cbb" data-kind="league"' in html
    hc = (ROOT / "web" / "js" / "hoopscast.js").read_text(encoding="utf-8")
    assert '"cbb"' in hc and "cbb: 1200" in hc and "REG_PERIODS = { cbb: 2 }" in hc
    gc = (ROOT / "web" / "js" / "gamecast.js").read_text(encoding="utf-8")
    assert 'cbb: "mens-college-basketball"' in gc
    det = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
    assert "cbb: 2 }" in det



def test_a_report_says_the_school_never_the_school():
    """A game report names a club "the Celtics" and a school "Duke": the
    school takes a singular verb ("Duke has"), never "the Duke have"."""
    from engine import gamereport as GR
    g = {"away": "UNC", "home": "DUKE"}
    c = GR.Ctx(g, {"games": [g]}, names={"DUKE": "Duke", "UNC": "North Carolina"}, sport="cbb")
    assert GR.team_np(c, "DUKE") == "Duke" and GR.team_np(c, "UNC") == "North Carolina"
    assert GR.team_be(c, "DUKE", "have", "has") == "has"
    pro = GR.Ctx(g, {"games": [g]}, names={"DUKE": "Celtics"}, sport="nba")
    assert GR.team_np(pro, "DUKE") == "the Celtics" and GR.team_be(pro, "DUKE", "have", "has") == "have"


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
