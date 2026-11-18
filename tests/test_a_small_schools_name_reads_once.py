"""A small school's name reads once (USEREYES1, 18 November 2026).

ESPN's records for some schools below Division I repeat a word or tack an
all-caps code onto the end, and the college boards' team tables carried
them as they came: "Regent Regent Royals", "Oklahoma Panhandle PANHANDLE
ST", "Midland MIDLAND LUTHERAN", "Sterling STERLING KS", "University of
Mexico MEXICO U" — the names a November buy game's card would print. What
these hold:

  * an all-caps tail that repeats a word already in the name is dropped,
    and a word said twice in a row is said once;
  * a place named that way keeps it ("Walla Walla Wolves"), and a real
    school's capitals stand ("UCLA Bruins", "Texas A&M Aggies", "Boston U");
  * both college parsers (basketball's scoreboard, football's teams and
    scoreboard) read names through it.

    python3 tests/test_a_small_schools_name_reads_once.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.sources import espnhoops                          # noqa: E402
from engine.sources.names import tidy_team_name               # noqa: E402


def test_espns_slips_are_taken_out():
    for name, loc, want in (("Regent Regent Royals", "Regent", "Regent Royals"),
                            ("Oklahoma Panhandle PANHANDLE ST", "Oklahoma Panhandle", "Oklahoma Panhandle"),
                            ("Midland MIDLAND LUTHERAN", "Midland", "Midland"),
                            ("Sterling STERLING KS", "Sterling", "Sterling"),
                            ("University of Mexico MEXICO U", "University of Mexico", "University of Mexico")):
        assert tidy_team_name(name, loc) == want, (name, tidy_team_name(name, loc))


def test_real_names_stand():
    for name, loc in (("Walla Walla Wolves", "Walla Walla"), ("UCLA Bruins", "UCLA"),
                      ("Texas A&M Aggies", "Texas A&M"), ("Boston U", "Boston U"), ("LSU Tigers", "LSU"),
                      ("UT Martin Skyhawks", "UT Martin"), ("Miami (OH) RedHawks", "Miami (OH)"),
                      ("Colorado Colorado Springs Mountain Lions", "Colorado Colorado Springs"), ("UCLA", "UCLA")):
        assert tidy_team_name(name, loc) == name, (name, tidy_team_name(name, loc))
    assert tidy_team_name(None) == "" and tidy_team_name("") == ""


def test_the_scoreboard_reads_names_through_it():
    payload = {"events": [{"id": "401", "date": "2026-11-18T00:00Z", "competitions": [{
        "status": {"type": {"completed": False, "state": "pre"}},
        "competitors": [
            {"homeAway": "home", "score": "0", "team": {"id": "2509", "abbreviation": "PUR", "conferenceId": "7",
                                                       "displayName": "Purdue Boilermakers", "location": "Purdue"}},
            {"homeAway": "away", "score": "0", "team": {"id": "131784", "abbreviation": "RGNT",
                                                       "displayName": "Regent Regent Royals", "location": "Regent"}}]}]}]}
    games = espnhoops.parse_scoreboard(payload, league="cbb")
    assert games, "the scoreboard parsed"
    g = games[0]
    names = {g.get("home_name") or (g.get("home_info") or {}).get("name"),
             g.get("away_name") or (g.get("away_info") or {}).get("name")}
    assert "Regent Royals" in names and "Regent Regent Royals" not in names, g
    src = (ROOT / "engine" / "sources" / "cfbdata.py").read_text(encoding="utf-8")
    assert src.count("tidy_team_name(") >= 2


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
