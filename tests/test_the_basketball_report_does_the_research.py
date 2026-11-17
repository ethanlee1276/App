"""The basketball report does the research (2026-11-15).

Ethan: "I want our game reports for each game to be scanning for all that type
of data and matchup shit ... I just want to be able to go on our app, and that
research is already done for me for each game, for every sport." His NBA
research read who takes a ruled-out star's shots, the pace and the total, and
the last time the two met with who was missing then ("On March 28, the
Pistons crushed the Timberwolves 109-87 ... Edwards, McDaniels and Dosunmu
were all absent"). The NBA build already measured the first (engine/nba/onoff
.inheritance) and held the rest; the report now says all three, from
engine/leaguereport.basketball_research (NBA, college, WNBA):

  * What the absences change: each ruled-out rotation man's minutes and
    points, and who took the biggest one's share of the points in the games
    he missed — measured, and a sample under three games says so;
  * How the game should go: each team's form (its last ten this season, by how
    much, and its record where it plays tonight), both teams' pace against the league's (per 48
    minutes, as the tape says it; Division I's on college), the total against
    the league's average game, a close game's full minutes;
  * The last meeting: the score, each side's leading scorers, and who each
    played without that night.

    python3 tests/test_the_basketball_report_does_the_research.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gamereport as R                                   # noqa: E402
from engine import leaguereport as L                                 # noqa: E402


def _hist():
    def p(team, mins, pts, weeks):
        return {"team": team, "minutes": mins, "pts": pts, "by_week": weeks, "starter": True}
    return {
        "Tyler Herro": p("MIA", [34] * 10, [22] * 10, {"2026-10-30": {"pts": 25, "min": 35}}),
        "Bam Adebayo": p("MIA", [35] * 10, [18] * 10, {"2026-10-30": {"pts": 20, "min": 36}}),
        "Norman Powell": p("MIA", [30] * 10, [16] * 10, {"2026-10-24": {"pts": 12, "min": 30}}),
        "Jayson Tatum": p("BOS", [36] * 10, [28] * 10, {"2026-10-30": {"pts": 31, "min": 37}}),
        "Jaylen Brown": p("BOS", [34] * 10, [23] * 10, {"2026-10-30": {"pts": 24, "min": 35}}),
    }


def _conn():
    from engine import db as D
    conn = D.connect(Path(tempfile.mkdtemp()) / "history.db")
    conn.executemany("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score, date) "
                     "VALUES (?,?,?,?,?,?,?,?,?)",
                     [("nba", 2026, "2026-10-30", "BOS@MIA", "MIA", "BOS", 101, 112, "2026-10-30"),
                      ("nba", 2026, "2026-10-12", "MIA@BOS", "BOS", "MIA", 90, 95, "2026-10-12")])
    conn.commit()
    return conn


def _research(spread=-3.5, total=232.5):
    g = {"home": "BOS", "away": "MIA", "date": "2026-11-16", "kickoff": "2026-11-17T00:30:00Z",
         "spread": spread, "total": total}
    gone = {"MIA": [("Tyler Herro", 34.0)]}
    vacancy = {"MIA": {"out": gone["MIA"], "inherit": {
        "player": "Tyler Herro", "n_out": 6, "n_played": 20, "enough": True,
        "beneficiaries": {"Bam Adebayo": {"with": 0.23, "without": 0.28, "delta": 0.05},
                          "Norman Powell": {"with": 0.17, "without": 0.21, "delta": 0.04},
                          "Bench Guy": {"with": 0.05, "without": 0.055, "delta": 0.005}}}}}
    prof = {"teams": {"BOS": {"pace": 101.9, "pts": 118.0, "ranks": {"pace": 3}},
                      "MIA": {"pace": 101.2, "pts": 112.0, "ranks": {"pace": 6}}},
            "league": {"pace": 99.1, "pts": 112.5}, "n": 30}
    return g, L.basketball_research(g, hist=_hist(), gone=gone, vacancy=vacancy, prof=prof, conn=_conn(),
                                    sport="nba", day="2026-11-16")


def test_the_build_gathers_the_absences_the_pace_and_the_last_meeting():
    _g, got = _research()
    ab = got["absences"]["MIA"]
    assert ab["out"] == [{"player": "Tyler Herro", "mpg": 34.0, "ppg": 22.0}], ab
    assert [x["player"] for x in ab["takers"]] == ["Bam Adebayo", "Norman Powell"], "a 0.5-point gain is noise"
    assert got["script"]["pace"] == {"MIA": 101.2, "BOS": 101.9} and got["script"]["league_pace"] == 99.1
    m = got["meeting"]
    assert (m["day"], m["home"], m["away"], m["home_score"], m["away_score"]) == ("2026-10-30", "MIA", "BOS", 101, 112)
    assert m["leaders"]["BOS"] == [{"player": "Jayson Tatum", "pts": 31}, {"player": "Jaylen Brown", "pts": 24}]
    assert m["missing"]["MIA"] == ["Norman Powell"], m["missing"]


def _report(spread=-3.5, total=232.5, **over):
    g, meta = _research(spread, total)
    meta.update(over)
    board = {"date": "2026-11-16", "games": [g], "scan_reads": {}}
    L.attach(board, "nba", meta={"MIA@BOS": meta})
    return board["game_reports"][0]


def test_the_report_says_what_the_absences_change_measured():
    text = R.to_text(_report())
    assert "WHAT THE ABSENCES CHANGE" in text, text
    assert "Tyler Herro is out: 34 minutes and 22 points a game over the last ten." in text, text
    assert ("In the 6 games Tyler Herro missed this season, Bam Adebayo took 28% of the Heat's points (23% with Tyler Herro "
            "playing) and Norman Powell took 21% of the Heat's points (17% with Tyler Herro playing).") in text, text


def test_a_small_sample_says_so_instead_of_guessing():
    g, meta = _research()
    meta["absences"]["MIA"].update(n_out=2, enough=False)
    board = {"date": "2026-11-16", "games": [g], "scan_reads": {}}
    L.attach(board, "nba", meta={"MIA@BOS": meta})
    text = R.to_text(board["game_reports"][0])
    assert "Tyler Herro has missed 2 games this season — too few to say who takes those shots." in text, text
    assert "Bam Adebayo took" not in text


def test_how_the_game_should_go_reads_the_pace_the_total_and_a_close_game():
    text = R.to_text(_report())
    assert "HOW THE GAME SHOULD GO" in text, text
    # "The Heat" is one team, as the report says it elsewhere ("The Heat is on the second night ...").
    # Per 48 minutes, as the tape's pace row on the same page says it.
    assert ("A fast game: the Heat averages 101.2 possessions per 48 minutes (6th-fastest of 30) and the Celtics "
            "101.9 (3rd-fastest of 30); the league averages 99.1.") in text, text
    assert "The total, 232.5, is 7.5 points over the league's average game (225): a high-scoring night" in text, text
    assert "A close game by the line, the Celtics by 3.5: the starters should play their full minutes" in text, text
    slow = R.to_text(_report(spread=-12.5, total=214.5))
    assert "under the league's average game" in slow and "A close game" not in slow


def test_a_college_game_says_division_i_and_the_same_pace_as_its_tape():
    """College's pace is per 48 minutes like the tape's row, not its own 40-minute
    game (that would be a second number for the same team, two lines apart),
    and its averages are Division I's, not "the league's"."""
    g, meta = _research()
    board = {"date": "2026-11-16", "games": [g], "scan_reads": {}, "board_games": ["MIA@BOS"],
             "teams": {"MIA": {"loc": "Miami"}, "BOS": {"loc": "Boston College"}}}
    L.attach(board, "cbb", meta={"MIA@BOS": meta})
    text = R.to_text(board["game_reports"][0])
    assert "possessions per 48 minutes" in text and "Division I averages 99.1." in text, text
    assert "over Division I's average game (225)" in text and "the league" not in text, text


def _form_conn(extra_bos_home_wins=0):
    from engine import db as D
    conn = D.connect(Path(tempfile.mkdtemp()) / "history.db")
    rows = [("2026-10-12", "BOS", "MIA", 90, 95), ("2026-10-30", "MIA", "BOS", 101, 112),
            ("2026-11-02", "BOS", "NYK", 110, 100), ("2026-11-04", "BOS", "PHI", 105, 99),
            ("2026-11-06", "ORL", "MIA", 100, 98), ("2026-11-08", "MIA", "ATL", 121, 111),
            # Last season and tonight: neither is this season's form.
            ("2026-04-01", "MIA", "BOS", 80, 120), ("2026-11-16", "BOS", "MIA", 130, 90)]
    rows += [(f"2026-10-{d:02d}", "BOS", "CHA", 100, 90) for d in range(14, 14 + extra_bos_home_wins)]
    conn.executemany("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score, date) "
                     "VALUES ('nba', 2026, ?, ?, ?, ?, ?, ?, ?)",
                     [(d, f"{a}@{h}", h, a, hs, as_, d) for d, h, a, hs, as_ in rows])
    conn.commit()
    return conn


def test_the_form_says_each_teams_record_margin_and_where_it_plays():
    got = L.team_form(_form_conn(), "nba", "BOS", "MIA", "2026-11-16")
    assert got["MIA"] == {"n": 4, "w": 2, "l": 2, "margin": 0.5, "where": "road", "venue_w": 1, "venue_l": 1}, got
    assert got["BOS"] == {"n": 4, "w": 3, "l": 1, "margin": 5.5, "where": "home", "venue_w": 2, "venue_l": 1}, got
    g, meta = _research()
    meta["form"] = got
    board = {"date": "2026-11-16", "games": [g], "scan_reads": {}}
    L.attach(board, "nba", meta={"MIA@BOS": meta})
    text = R.to_text(board["game_reports"][0])
    assert ("Form: the Heat is 2-2 in its 4 games this season, outscoring teams by 0.5 points a game; the Celtics "
            "are 3-1 in their 4 games this season, outscoring teams by 5.5 points a game.") in text, text
    assert "Where they play: the Celtics are 2-1 at home and the Heat is 1-1 on the road this season." in text
    # Ten finals or more: the last ten.
    ten = L.team_form(_form_conn(extra_bos_home_wins=8), "nba", "BOS", "MIA", "2026-11-16")
    assert ten["BOS"]["n"] == 10 and ten["BOS"]["venue_w"] == 10, ten
    meta["form"] = ten
    board = {"date": "2026-11-16", "games": [g], "scan_reads": {}}
    L.attach(board, "nba", meta={"MIA@BOS": meta})
    assert "the Celtics are 10-0 over their last ten" in R.to_text(board["game_reports"][0])
    # Under three finals this season: nothing said; the build gathers it.
    assert L.team_form(_conn(), "nba", "BOS", "MIA", "2026-11-16") == {}
    assert "form" in L.basketball_research(g, hist=_hist(), conn=_form_conn(), sport="nba", day="2026-11-16")


def test_the_last_meeting_is_the_precedent_with_who_was_missing():
    text = R.to_text(_report())
    assert "THE LAST MEETING" in text, text
    assert "Oct. 30: the Celtics beat the Heat 112-101 on the road." in text, text
    assert "The Celtics' leading scorers: Jayson Tatum (31 points) and Jaylen Brown (24 points)." in text, text
    assert "The Heat played without Norman Powell that night." in text, text


def test_the_sections_sit_in_the_researchs_order_and_the_build_fills_them():
    rep = _report()
    keys = [s["key"] for s in rep["sections"]]
    for a, b in (("script", "absences"), ("absences", "meetings")):
        assert keys.index(a) < keys.index(b), keys
    src = (ROOT / "nba_build.py").read_text(encoding="utf-8")
    assert "_gr_research(" in src and "gone=gone, vacancy=_vacancy, prof=_prof, conn=conn" in src
    # No meeting in the history, no section; no profile, no pace.
    assert not L.last_meeting(_conn(), "nba", "LAL", "OKC", "2026-11-16", {})
    assert "script" not in L.basketball_research({"home": "A", "away": "B"}, hist={}, prof={})


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc(limit=6)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
