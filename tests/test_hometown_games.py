"""Hometown games: an NFL player's road game near where he was born.

Ethan, 2026-10-11: "one signal that I want to add for our NFL bets is
hometown returns ... when they come back to their hometown and play a game
in their hometown, I feel like that matters."

These check, one rule each: names and places are matched the way the
sources spell them; the Census map is read by header name, an incorporated
place beats a census-designated one, and a consolidated city answers to
its short name; ESPN's birthplace beats Sleeper's, a player born abroad is
not placed, two players with one name are told apart by position or not at
all; a hometown game is a ROAD game within 50 miles of his birthplace,
never his own team's home game and never a neutral site; the scout flags
both sides and only on the markets it reads; the five-season replay scores
hometown games and says how many; the card names the town; the weekly
replay rebuilds the table but never inside the test sandbox.

No network: every source here is a fixture.

Run directly: `python3 tests/test_hometown_games.py`
"""
import io
import os
import sqlite3
import sys
import tempfile
import zipfile
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["QB_MODELS_DIR"] = tempfile.mkdtemp()

from engine import hometown as HT                                   # noqa: E402
from engine import scout as SC                                      # noqa: E402

GAZ = "\t".join(["USPS", "GEOID", "GEOIDFQ", "ANSICODE", "NAME", "LSAD", "FUNCSTAT", "ALAND", "AWATER",
                 "ALAND_SQMI", "AWATER_SQMI", "INTPTLAT", "INTPTLONG   "]) + "\n" + "\n".join(
    "\t".join([st, "1", "x", "1", name, "25", "A", "1", "0", "1", "0", lat, lon]) for st, name, lat, lon in [
        ("MI", "Detroit city", "42.3830", "-83.1022"),
        ("CA", "Compton city", "33.8930", "-118.2275"),
        ("MO", "St. Louis city", "38.6358", "-90.2451"),
        ("TN", "Nashville-Davidson metropolitan government (balance)", "36.1716", "-86.7850"),
        ("CA", "East Los Angeles CDP", "34.0315", "-118.1686"),
        ("TX", "Springfield CDP", "30.0", "-95.0"),
        ("TX", "Springfield city", "31.0", "-96.0"),
        ("OH", "Columbus city", "39.9862", "-82.9855"),
    ])


def _table():
    entries = [
        {"player": "Road Receiver", "pos": "WR", "team": "CHI", "city": "Detroit", "state": "MI",
         "country": "USA", "src": "espn"},
        {"player": "Lion Back", "pos": "RB", "team": "DET", "city": "Detroit", "state": "Michigan",
         "country": "USA", "src": "sleeper"},
        {"player": "Far Away", "pos": "WR", "team": "CHI", "city": "Columbus", "state": "OH",
         "country": "USA", "src": "espn"},
    ]
    return HT.build_table(entries, HT.parse_gazetteer(GAZ))


def test_names_and_places_match_the_way_the_sources_spell_them():
    assert HT.norm_name("D.K. Metcalf") == HT.norm_name("DK Metcalf") == "dk metcalf"
    assert HT.norm_name("Marvin Harrison Jr.") == "marvin harrison"
    assert HT.norm_city("St. Louis") == HT.norm_city("Saint Louis") == "saint louis"
    assert HT.norm_city("Ft. Worth") == "fort worth"
    assert HT.state_code("Michigan") == HT.state_code("mi") == "MI"
    assert HT.state_code("Ontario") == ""


def test_the_census_map_is_read_by_header_and_prefers_real_towns():
    gaz = HT.parse_gazetteer(GAZ)
    assert gaz[("detroit", "MI")] == (42.383, -83.1022)
    assert ("saint louis", "MO") in gaz
    assert gaz[("nashville", "TN")] == gaz[("nashville davidson", "TN")], "a consolidated city's short name"
    assert ("east los angeles", "CA") in gaz
    assert gaz[("springfield", "TX")] == (31.0, -96.0), "the incorporated city beats the CDP"


def test_the_map_is_downloaded_once_and_unzipped():
    from engine.sources import fetch as F
    real = F.CACHE_DIR
    F.CACHE_DIR = tempfile.mkdtemp()
    calls = []
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("2023_Gaz_place_national.txt", GAZ)

    def fake(url):
        calls.append(url)
        return buf.getvalue()
    try:
        assert HT.load_gazetteer(fetch=fake)[("compton", "CA")]
        assert HT.load_gazetteer(fetch=fake)[("compton", "CA")]
    finally:
        F.CACHE_DIR = real
    assert calls == [HT.GAZETTEER_URL], "downloaded once, then read from the cache"
    assert "census.gov" in HT.GAZETTEER_URL


def test_espn_beats_sleeper_and_abroad_is_not_placed():
    espn = HT.from_espn({"athletes": [{"position": "offense", "items": [
        {"fullName": "Two Source", "position": {"abbreviation": "WR"},
         "birthPlace": {"city": "Compton", "state": "CA", "country": "USA"}},
        {"fullName": "Overseas Kicker", "position": {"abbreviation": "K"},
         "birthPlace": {"city": "Sydney", "country": "Australia"}},
        {"fullName": "No Birthplace", "position": {"abbreviation": "TE"}}]}]}, "LAR")
    sleeper = HT.from_sleeper({"1": {"full_name": "Two Source", "position": "WR", "team": "LAR",
                                     "birth_city": "Detroit", "birth_state": "MI"},
                               "2": {"first_name": "Old", "last_name": "Timer", "position": "RB",
                                     "birth_city": "St. Louis", "birth_state": "Missouri"},
                               "3": {"full_name": "Nowhere", "position": "QB"}})
    assert [e["player"] for e in espn] == ["Two Source", "Overseas Kicker"]
    t = HT.build_table(espn + sleeper, HT.parse_gazetteer(GAZ))
    assert HT.lookup(t, "Two Source")["city"] == "Compton", "ESPN's birthplace wins"
    assert HT.lookup(t, "Old Timer")["state"] == "MO", "Sleeper keeps retired players"
    assert HT.lookup(t, "Overseas Kicker") is None and t["counts"]["abroad"] == 1


def test_two_players_with_one_name_are_told_apart_by_position_or_not_at_all():
    gaz = HT.parse_gazetteer(GAZ)
    t = HT.build_table([{"player": "Josh Allen", "pos": "QB", "city": "Detroit", "state": "MI",
                         "country": "", "src": "espn"},
                        {"player": "Josh Allen", "pos": "LB", "city": "Compton", "state": "CA",
                         "country": "", "src": "espn"}], gaz)
    assert HT.lookup(t, "Josh Allen", "QB")["city"] == "Detroit"
    assert HT.lookup(t, "Josh Allen") is None, "with no position, neither is used"


def test_a_hometown_game_is_a_road_game_within_fifty_miles():
    t = _table()
    road, lion, far = (HT.lookup(t, n) for n in ("Road Receiver", "Lion Back", "Far Away"))
    assert HT.HOMETOWN_MILES == 50.0
    assert HT.hometown_game(road, "CHI", "DET") is not None, "the Detroit kid at Ford Field"
    assert HT.hometown_game(lion, "DET", "DET") is None, "his own team's home game is not a return"
    assert HT.hometown_game(road, "CHI", "DET", neutral=True) is None, "a neutral site is nobody's town"
    assert HT.hometown_game(far, "CHI", "DET") is None, "Columbus is 165 miles away"
    assert HT.hometown_game(None, "CHI", "DET") is None


def test_the_scout_flags_both_sides_on_the_markets_it_reads():
    for market, side, want in (("rec_yds", "OVER", ["hometown_over"]), ("receptions", "UNDER", ["hometown_under"]),
                               ("anytime_td", "YES", ["hometown_over"]), ("pass_int", "OVER", [])):
        got = [f for f in SC.flags(SC.situation(market, side, line=4.5, position="WR", values=[4] * 6,
                                                hometown=True)) if f.startswith("hometown")]
        assert got == want, (market, side, got)
    assert not [f for f in SC.flags(SC.situation("rec_yds", "OVER", line=4.5, values=[4] * 6))
                if f.startswith("hometown")]
    assert "hometown" in SC.FLAGS["hometown_over"] and "hometown" in SC.FLAGS["hometown_under"]


def _hist():
    """Chicago's receiver, born in Detroit, plays eight games: seven at
    Soldier Field and one at Ford Field (week 7)."""
    from engine import db
    c = db.connect(os.path.join(tempfile.mkdtemp(), "h.db"))
    games, logs = [], []
    for wk in range(1, 9):
        home, away = ("DET", "CHI") if wk == 7 else ("CHI", f"OP{wk}")
        games.append(("nfl", 2025, str(wk), f"{away}@{home}", home, away, 24, 20, -3.0, 44.5, None))
        logs.append(("nfl", 2025, str(wk), f"CHI-00{wk}", "Road Receiver", "CHI", "DET" if wk == 7 else f"OP{wk}",
                     "WR", 0 if wk == 7 else 1, "receptions", 5 + (wk % 3)))
    c.executemany("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score, "
                  "spread, total, date) VALUES (?,?,?,?,?,?,?,?,?,?,?)", games)
    c.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, "
                  "position, home, market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)", logs)
    c.commit()
    c.row_factory = sqlite3.Row
    return c


def test_the_replay_scores_hometown_games_and_says_how_many():
    from engine import scouthist as H
    HT.save(_table())
    real = HT.neutral_keys
    HT.neutral_keys = lambda path=None: set()
    try:
        h = H.replay(_hist(), sport="nfl")
    finally:
        HT.neutral_keys = real
    hg = h["hometown"]
    assert (hg["players"], hg["games"]) == (3, 1), hg
    assert set(hg["cells"]) == {"receptions OVER", "receptions UNDER"}, "both sides, shown whether or not proven"
    assert hg["cells"]["receptions OVER"]["n"] == 1
    src = open(os.path.join(ROOT, "engine", "scouthist.py"), encoding="utf-8").read()
    assert "road games in a player's hometown scored" in src
    assert "shown, not applied" in src and "every over" in src


def _logs_db(rows):
    from engine import db
    c = db.connect(os.path.join(tempfile.mkdtemp(), "h.db"))
    c.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, "
                  "position, home, market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    c.commit()
    return c


def test_players_no_roster_lists_today_are_looked_up_once_by_their_espn_id():
    hist = _logs_db([("nfl", 2022, "3", "g1", "Retired Receiver", "CHI", "DET", "WR", 1, "receptions", 5),
                     ("nfl", 2023, "3", "g2", "Current Star", "CHI", "DET", "WR", 1, "receptions", 7),
                     ("nfl", 2022, "4", "g3", "No Id Back", "CHI", "DET", "RB", 1, "rush_yds", 40),
                     ("nfl", 2022, "5", "g4", "Blank Page", "CHI", "DET", "TE", 1, "receptions", 3)])
    rosters = {2022: [{"full_name": "Retired Receiver", "position": "WR", "espn_id": "123.0"},
                      {"full_name": "Blank Page", "position": "TE", "espn_id": "456"},
                      {"full_name": "No Id Back", "position": "RB", "espn_id": "NA"}]}
    asked = []

    def fetch(url):
        asked.append(url)
        if "/123" in url:
            return {"fullName": "Retired Receiver", "position": {"abbreviation": "WR"},
                    "birthPlace": {"city": "Detroit", "state": "MI", "country": "USA"}}
        return {"athlete": {"fullName": "Blank Page"}}            # a page with no birthplace

    out, c = HT.past_entries({"current star"}, hist=hist, seasons=[2022], fetch=fetch,
                             load=lambda season: rosters.get(season, []), pause=0)
    assert [(e["player"], e["city"]) for e in out] == [("Retired Receiver", "Detroit")]
    assert c["wanted"] == 3 and c["no_espn_id"] == 1, "today's players are not looked up; no id, no page"
    assert any("sports.core.api.espn.com" in u and u.endswith("/123") for u in asked)
    n = len(asked)

    def refuse(url):
        raise AssertionError("asked twice: " + url)
    out2, c2 = HT.past_entries({"current star"}, hist=hist, seasons=[2022], fetch=refuse,
                               load=lambda season: rosters.get(season, []), pause=0)
    assert [e["player"] for e in out2] == ["Retired Receiver"] and c2["looked_up"] == 0, \
        "every page — even one with no birthplace — is read once and kept"
    assert n == 3, asked


def test_a_page_that_will_not_load_is_asked_again_next_run():
    hist = _logs_db([("nfl", 2024, "1", "g1", "Flaky Page", "CHI", "DET", "WR", 1, "receptions", 5)])
    load = lambda season: [{"full_name": "Flaky Page", "position": "WR", "espn_id": "789"}]  # noqa: E731

    def down(url):
        raise OSError("timed out")
    out, c = HT.past_entries(set(), hist=hist, seasons=[2024], fetch=down, load=load, pause=0, log=lambda m: None)
    assert out == [] and c["failed"] == 1
    out, c = HT.past_entries(set(), hist=hist, seasons=[2024], load=load, pause=0,
                             fetch=lambda url: {"fullName": "Flaky Page", "birthPlace": {"city": "Compton",
                                                                                         "state": "CA"}})
    assert [e["city"] for e in out] == ["Compton"]


def test_both_espn_page_shapes_are_read():
    core = {"fullName": "A B", "position": {"abbreviation": "RB"}, "birthPlace": {"city": "Dallas", "state": "TX"}}
    web = {"athlete": core}
    assert HT.from_espn_athlete(core)["city"] == HT.from_espn_athlete(web)["city"] == "Dallas"
    assert HT.from_espn_athlete({"fullName": "No Town"}) is None


def test_the_card_names_the_town():
    from engine import likelyctx as L
    HT.save(_table())
    rows = [{"player": "Road Receiver", "team": "CHI", "opponent": "DET", "position": "WR", "market": "receptions",
             "side": "UNDER", "line": 5.5, "recent_values": [5, 6, 7, 5, 6]}]
    result = {"games": [{"home": "DET", "away": "CHI", "spread": -3.0, "total": 44.5}], "recommendations": []}
    L.annotate(rows, result, "nfl")
    assert "hometown_under" in rows[0]["scout_flags"]
    assert any("his hometown (Detroit, MI)" in n for n in rows[0]["scout_notes"]), rows[0]["scout_notes"]
    rows[0]["side"] = "OVER"
    result["games"][0]["neutral_site"] = True
    L.annotate(rows, result, "nfl")
    assert not [f for f in rows[0]["scout_flags"] if f.startswith("hometown")], "a neutral site is not his town"


def test_the_weekly_replay_rebuilds_the_table_but_never_in_the_sandbox():
    src = open(os.path.join(ROOT, "engine", "scouthist.py"), encoding="utf-8").read()
    i = src.index("HT.refresh(log=print)")
    guard = src[src.rindex("if ", 0, i):i]
    assert "not a.dry_run" in guard and "HT.stale()" in guard and "modelstate.ENV_VAR" in guard
    out = io.StringIO()
    with redirect_stdout(out):
        HT.refresh(log=print, espn=[], sleeper=[], gaz={}, past=[])
    assert "could not be loaded" in out.getvalue(), "a missing map is said, not silent"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                import traceback
                traceback.print_exc()
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
