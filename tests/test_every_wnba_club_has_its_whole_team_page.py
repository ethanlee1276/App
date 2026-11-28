"""Every WNBA club has its whole team page, under either of its codes (step ABX, 22 November 2026).

Ethan, the Sunday morning: "We want every single sports player pages to match each other ... have it match
ESPN." Checking the live team pages: the Indiana Fever's had its name, roster and depth chart, and the Las Vegas
Aces' read "LV" with no name, no roster and no depth chart, as did the Valkyries', the Sparks', the Liberty's and
the Mystics'. The WNBA's stored games keep ESPN's codes (LV, GS, LA, NY, WSH) and its names and rosters are
keyed by the league's (LVA, GSV, LAS, NYL, WAS), so the five clubs whose codes differ lost everything keyed the
other way, and "LVA" found no team at all. What these hold:

  * a club's code in any of the feeds' spellings maps to the league's own (engine/divisions), in the NBA and the
    WNBA only; a side that is no club, and every other league's codes, stay as they are;
  * the page's name is the club's full name under either code;
  * the search finds the club as the stored games spell it, from either code or its name;
  * the roster board answers under either code.

    python3 tests/test_every_wnba_club_has_its_whole_team_page.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import teamdex as T                                       # noqa: E402

WNBA_STORED = ["ATL", "CHI", "CON", "DAL", "GS", "IND", "LA", "LV", "MIN", "NY", "PHX", "POR", "SEA", "TOR", "WSH"]


def test_a_clubs_code_in_any_spelling_is_the_leagues():
    for sport, code, want in (("wnba", "LV", "LVA"), ("wnba", "GS", "GSV"), ("wnba", "LA", "LAS"), ("wnba", "NY", "NYL"),
                              ("wnba", "WSH", "WAS"), ("wnba", "LVA", "LVA"), ("wnba", "IND", "IND"),
                              ("wnba", "SPO", "SPO"), ("nba", "GS", "GSW"), ("nba", "NY", "NYK"), ("nba", "GSW", "GSW"),
                              ("nfl", "LV", "LV"), ("nhl", "LA", "LA"), ("wnba", "", "")):
        assert T.club_code(sport, code) == want, (sport, code, T.club_code(sport, code))


def test_the_page_names_the_club_under_either_code():
    for code, name in (("LV", "Las Vegas Aces"), ("LVA", "Las Vegas Aces"), ("GS", "Golden State Valkyries"),
                       ("LA", "Los Angeles Sparks"), ("NY", "New York Liberty"), ("WSH", "Washington Mystics"),
                       ("IND", "Indiana Fever")):
        assert T.label(code, "wnba") == name, (code, T.label(code, "wnba"))
    assert T.label("LV", "nfl") == "Las Vegas Raiders", "another league's code is its own"
    assert T.label("SPO", "wnba") == "SPO", "no club, no name"


def test_the_search_finds_the_club_as_its_games_are_stored():
    for typed, want in (("LVA", ["LV"]), ("LV", ["LV"]), ("Las Vegas Aces", ["LV"]), ("aces", ["LV"]),
                        ("GSV", ["GS"]), ("Valkyries", ["GS"]), ("WAS", ["WSH"]), ("NYL", ["NY"]), ("IND", ["IND"])):
        assert T.resolve(typed, "wnba", WNBA_STORED) == want, (typed, T.resolve(typed, "wnba", WNBA_STORED))
    nba = ["BOS", "GSW", "LAL", "NYK", "SAS", "WAS"]
    for typed, want in (("GS", ["GSW"]), ("GSW", ["GSW"]), ("NY", ["NYK"]), ("SA", ["SAS"]), ("WSH", ["WAS"])):
        assert T.resolve(typed, "nba", nba) == want, (typed, T.resolve(typed, "nba", nba))


def test_the_roster_board_answers_under_either_code():
    import server
    tmp = Path(tempfile.mkdtemp())
    (tmp / "web" / "data").mkdir(parents=True)
    (tmp / "web" / "data" / "rosters_wnba.json").write_text(json.dumps(
        {"source": "league", "generated_at": "2026-11-22T09:00:00", "season": 2026,
         "teams": {"LVA": {"players": [{"player": "A'ja Wilson", "position": "F"}]}}}))
    (tmp / "web" / "data" / "rosters_nhl.json").write_text(json.dumps(
        {"source": "league", "teams": {"LAK": {"players": [{"player": "Anze Kopitar", "position": "C"}]}}}))
    real = server.ROOT
    server.ROOT = tmp
    try:
        for code in ("LV", "LVA"):
            got = server._live_roster("wnba", code)
            assert got and got["players"][0]["player"] == "A'ja Wilson", (code, got)
        assert server._live_roster("wnba", "IND") is None
        assert server._live_roster("nhl", "LA") is None, "no other league reads a club another way"
    finally:
        server.ROOT = real


def test_the_roster_says_height_and_weight_as_the_player_pages_do():
    # College's and basketball's rosters come in ESPN's spelling (6' 1", 214 lbs), the NFL's as 6'2" and 190 lb;
    # the team page's roster table says them all the NFL's way, as the player pages do (22 November 2026).
    import server
    tmp = Path(tempfile.mkdtemp())
    (tmp / "web" / "data").mkdir(parents=True)
    (tmp / "web" / "data" / "rosters_cfb.json").write_text(json.dumps(
        {"source": "roster", "teams": {"OSU": {"players": [
            {"player": "Julian Sayin", "position": "QB", "height": "6' 1\"", "weight": "214 lbs"},
            {"player": "Walk On", "position": "WR", "height": "", "weight": None}]}}}))
    real = server.ROOT
    server.ROOT = tmp
    try:
        got = server._live_roster("cfb", "OSU")["players"]
    finally:
        server.ROOT = real
    assert (got[0]["height"], got[0]["weight"]) == ("6'1\"", "214 lb"), got[0]
    assert got[1]["height"] == "" and got[1]["weight"] is None, "blank stays blank"


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
