"""The team page for every league — NHL first, then the rest brought level.

Ethan, 2026-10-03: "make sure we're pulling all live data for NHL, like all
live rosters and injuries ... our rosters are good and our team data is
good and all the depth charts is good. And remember how I had you do it
when you search a team and then you click on the team and then it pulls up
the ESPN looking page with the depth chart and the injuries and the roster
... I want NHL to have the same thing. I want every single sport to have
the same thing."

Checks, one rule each:
  * the NHL's 32 clubs sit in their divisions and ESPN's spellings fold in;
  * the NHL's standings come from the league with the overtime-loss column,
    and last season's table is never shown as this season's;
  * a hockey roster carries the league's bio and the injury board's letter,
    wings read LW/RW, and the build uses the live feed with appearances as
    the fallback (and says why);
  * basketball's roster comes from ESPN's per-club rosters, spellings folded;
  * every league has its own Stats tab; hockey's depth chart is today's
    roster ordered by ice time over each man's newest games, a summer
    signing placed by what he did elsewhere;
  * the team answer carries the live roster and the page draws it;
  * the new boards are registered as free.

Run directly: `python3 tests/test_team_pages_every_sport.py`
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import db, divisions, gate, rosters, standings, teamdex   # noqa: E402
from engine.sources import espnrosters, leaguestandings, nhldata      # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def test_the_nhl_has_its_divisions_and_espns_spellings_fold_in():
    assert len(divisions.NHL) == 32
    assert divisions.group_of("nhl", "TB") == ("Eastern", "Atlantic")
    assert divisions.group_of("nhl", "VGK") == ("Western", "Pacific")
    assert divisions.canonical("nhl", "UTAH") == "UTA" and divisions.canonical("nba", "UTAH") == "UTA"


def _nhl_row(abbr, season="20262027", **kw):
    row = {"teamAbbrev": {"default": abbr}, "seasonId": season, "wins": 5, "losses": 2, "otLosses": 1,
           "goalFor": 30, "goalAgainst": 22, "homeWins": 3, "homeLosses": 1, "homeOtLosses": 0,
           "roadWins": 2, "roadLosses": 1, "roadOtLosses": 1, "streakCode": "W", "streakCount": 3,
           "l10Wins": 5, "l10Losses": 2, "l10OtLosses": 1}
    row.update(kw)
    return row


def test_nhl_standings_carry_the_overtime_loss_and_never_last_seasons_table():
    rows = leaguestandings.parse_nhl({"standings": [_nhl_row("EDM"), _nhl_row("CGY", wins=2, losses=5)]}, 2026)
    table = standings.from_feed("nhl", rows, 2026)
    teams = {t["team"]: t for g in table["groups"] for t in g["teams"]}
    assert teams["EDM"]["record"] == "5-2-1" and teams["EDM"]["points"] == 11
    assert teams["EDM"]["streak_label"] == "W3" and teams["EDM"]["last10_label"] == "5-2-1"
    assert table["score_label"] == "GF/GA"
    old = leaguestandings.parse_nhl({"standings": [_nhl_row("EDM", season="20252026", wins=50)]}, 2026)
    assert old[0]["wins"] == 0 and old[0]["team"] == "EDM", "last season's 50 wins are not this season's"
    import standings_build
    assert "nhl" in standings_build.SPORTS


def test_before_opening_night_the_table_is_this_seasons_zeros_not_empty():
    """The box, 2026-10-03: the dated table came back with no teams and the
    page fell back to an empty count. "now" is read first — last season's
    final, shown as this season's 0-0-0 — and the dated one only after."""
    asked = []
    real = leaguestandings.fetch_json

    def fake(url, name, **kw):
        asked.append(url.rsplit("/", 1)[-1])
        return {"standings": [_nhl_row("EDM", season="20252026", wins=50)]} if url.endswith("/now") \
            else {"standings": []}
    leaguestandings.fetch_json = fake
    try:
        rows = leaguestandings.fetch("nhl", 2026)
    finally:
        leaguestandings.fetch_json = real
    assert asked == ["now"] and rows[0]["team"] == "EDM" and rows[0]["wins"] == 0


def test_an_opened_season_with_no_game_played_is_every_club_at_zero():
    """The box, 2026-10-03: inside the NHL's window, no finals, the league's
    table empty — the page got nothing. It now gets the 32 clubs at 0-0-0
    in their divisions, and the build line says why the feed was not used."""
    import standings_build as SB
    real = SB._live_table
    SB._live_table = lambda sport, season, confs: (None, "the standings feed answered with no teams")
    try:
        b = SB.build("nhl", today="2026-10-03")
    finally:
        SB._live_table = real
    assert b["team_count"] == 32 and b["source"] == "alignment" and not b["note"]
    assert b["feed_error"] == "the standings feed answered with no teams"
    assert 'd.source === "alignment"' in APP


def _nhl_roster_payload():
    return {"forwards": [
        {"id": 8478402, "firstName": {"default": "Connor"}, "lastName": {"default": "McDavid"},
         "positionCode": "C", "sweaterNumber": 97, "shootsCatches": "L", "heightInInches": 73,
         "weightInPounds": 194, "birthDate": "1997-01-13", "birthCity": {"default": "Richmond Hill"},
         "birthStateProvince": {"default": "ON"}, "headshot": "https://x/97.png"},
        {"id": 2, "firstName": {"default": "Zach"}, "lastName": {"default": "Hyman"}, "positionCode": "R"}],
        "defensemen": [], "goalies": [
        {"id": 3, "firstName": {"default": "Stuart"}, "lastName": {"default": "Skinner"}}]}


def test_a_hockey_roster_carries_the_leagues_bio_and_the_injury_letter():
    people = nhldata.parse_roster(_nhl_roster_payload(), "EDM")
    mc = people[0]
    assert (mc["number"], mc["shoots"], mc["height"], mc["weight"]) == (97, "L", "6'1\"", "194 lb")
    assert mc["birthplace"] == "Richmond Hill, ON"
    feed = {"EDM": [dict(p, player=p["name"]) for p in people]}
    out = rosters.feed_rosters("nhl", feed, {}, injuries={"Zach Hyman": {"status": "Out", "injury": "Wrist"}},
                               today="2026-10-03")
    rows = out["teams"]["EDM"]["players"]
    assert [r["position"] for r in rows] == ["C", "RW", "G"], "centres, then wings as LW/RW, goalies last"
    assert rows[0]["age"] == 29
    hyman = next(r for r in rows if r["player"] == "Zach Hyman")
    assert hyman["unavailable"] and hyman["injury"] == "Wrist"
    got, missed = nhldata.fetch_league_rosters(("EDM", "CGY"), fetch=lambda t: _nhl_roster_payload()
                                               if t == "EDM" else (_ for _ in ()).throw(nhldata.DataUnavailable("x")))
    assert set(got) == {"EDM"} and missed == ["CGY"]


def test_the_roster_build_reads_the_live_feed_and_falls_back_saying_why():
    import rosters_build as RB
    assert {"nhl", "nba", "wnba"} <= set(RB.LIVE_FEEDS) and "nhl" in RB.FROM_LOGS
    conn = db.connect(":memory:")
    real = RB._league_feed
    try:
        RB._league_feed = lambda sport: ({"EDM": [dict(p, player=p["name"]) for p in
                                                  nhldata.parse_roster(_nhl_roster_payload(), "EDM")]}, ["CGY"])
        out = RB.payload_for(conn, "nhl", "2026-10-03")
        assert out["feed"] == "live" and out["source"] == "league" and out["player_count"] == 3
        assert "CGY" in out["note"]

        def down(sport):
            raise RuntimeError("host unreachable")
        RB._league_feed = down
        out = RB.payload_for(conn, "nhl", "2026-10-03")
        assert out["source"] == "appearances" and "host unreachable" in out["note"]
    finally:
        RB._league_feed = real


def test_basketball_rosters_come_from_espns_clubs_spellings_folded():
    teams = {"sports": [{"leagues": [{"teams": [{"team": {"abbreviation": "GS", "id": "9"}},
                                                {"team": {"abbreviation": "UTAH", "id": "26"}}]}]}]}
    roster = {"athletes": [{"fullName": "Stephen Curry", "jersey": "30", "position": {"abbreviation": "PG"},
                            "age": 38, "displayHeight": "6' 2\"", "displayWeight": "185 lbs",
                            "headshot": {"href": "https://a/curry.png"},
                            "injuries": [{"status": "Day-To-Day"}]}]}

    def fetch(url, name):
        if url.endswith("/teams"):
            return teams
        if "/26/" in url:
            raise espnrosters.DataUnavailable("down")
        return roster
    got, missed = espnrosters.fetch_league("nba", fetch=fetch)
    assert set(got) == {"GSW"} and missed == ["UTA"]
    curry = got["GSW"][0]
    assert (curry["number"], curry["position"], curry["age"], curry["status"]) == ("30", "PG", 38, "Day-To-Day")
    out = rosters.feed_rosters("nba", got)
    assert out["teams"]["GSW"]["players"][0]["questionable"]


def _logs(rows):
    """rows = [(player, team, position, market, value, period, season)]"""
    conn = db.connect(":memory:")
    db.upsert_player_logs(conn, [{
        "sport": "nhl", "season": s, "period": d, "game_id": f"{p}-{d}", "player": p, "team": t,
        "opponent": "CGY", "position": pos, "home": 1, "market": m, "value": v}
        for p, t, pos, m, v, d, s in rows])
    conn.commit()
    return conn


def test_every_league_has_its_stat_tab_and_hockeys_reads_like_hockey():
    rows = []
    for d in ("2026-10-08", "2026-10-10"):
        rows += [("Connor McDavid", "EDM", "C", m, v, d, 2026) for m, v in
                 (("goals", 1), ("assists", 2), ("points", 3), ("sog", 5), ("toi", 22.0))]
        rows += [("Stuart Skinner", "EDM", "G", m, v, d, 2026) for m, v in
                 (("saves", 28), ("shots_against", 30), ("goals_against", 2), ("started", 1), ("toi", 60.0))]
    t = teamdex.stat_tables(_logs(rows), "nhl", "EDM")
    keys = [s["key"] for s in t["sections"]]
    assert keys == ["skaters", "goalies"], keys
    goalies = t["sections"][1]
    assert goalies["rows"][0]["cells"][goalies["columns"].index("SV%")] == 0.933
    assert set(teamdex.STAT_SPORTS) == {"nfl", "cfb", "nhl", "nba", "wnba", "mlb"}
    assert teamdex.resolve("Edmonton Oilers", "nhl", ["EDM", "CGY"]) == ["EDM"]


def test_hockeys_depth_chart_is_todays_roster_by_ice_time():
    rows = []
    for i, d in enumerate(("2026-10-08", "2026-10-10", "2026-10-12")):
        rows.append(("Connor McDavid", "EDM", "C", "toi", 22.0, d, 2026))
        rows.append(("Adam Henrique", "EDM", "C", "toi", 13.0, d, 2026))
        rows.append(("Gone Guy", "EDM", "C", "toi", 25.0, d, 2026))       # traded away: not on today's roster
    rows.append(("Summer Signing", "BOS", "C", "toi", 18.0, "2026-03-01", 2025))   # placed by his old club
    roster = [{"player": n, "position": "C"} for n in
              ("Adam Henrique", "Connor McDavid", "Summer Signing", "Call Up")]
    depth = teamdex.usage_depth(_logs(rows), "nhl", roster)
    assert depth["source"] == "usage" and depth["market"] == "toi"
    c = depth["positions"][0]
    assert c["players"] == ["Connor McDavid", "Summer Signing", "Adam Henrique", "Call Up"], c["players"]
    assert "Gone Guy" not in c["players"]


def test_the_team_answer_carries_the_live_roster_and_the_page_draws_it():
    import server
    tmp = Path(tempfile.mkdtemp())
    (tmp / "web" / "data").mkdir(parents=True)
    (tmp / "web" / "data" / "rosters_nhl.json").write_text(json.dumps(
        {"source": "league", "generated_at": "2026-10-03T09:00:00", "season": 2026,
         "teams": {"EDM": {"players": [{"player": "Connor McDavid", "position": "C"}]}}}))
    real = server.ROOT
    server.ROOT = tmp
    try:
        got = server._live_roster("nhl", "EDM")
        assert got["source"] == "league" and got["players"][0]["player"] == "Connor McDavid"
        assert server._live_roster("nhl", "CGY") is None and server._live_roster("nba", "BOS") is None
    finally:
        server.ROOT = real
    assert "function teamLiveRosterHTML(d) {" in APP
    assert "(teamLiveRosterHTML(d) || rosterTab) + teamInjKeyHTML(d.sport)" in APP
    assert 'pub.market === "toi" ? "ice time" : "minutes"' in APP
    assert 'state.sport === "nhl" ? "W-L-OTL" : "W-L"' in APP


def test_the_new_boards_are_registered_and_free():
    for f in ("rosters_nhl.json", "standings_nhl.json"):
        assert f in gate.KNOWN_BOARDS and gate.is_free(f), f


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
