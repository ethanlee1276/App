"""The game report on every MLB, NHL, NBA and WNBA game page (engine/leaguereport).

Ethan, 2026-10-20: "I want you too do all of it besides D" — the NFL's
game report for the other leagues among it. Each league's report in the
NFL report's shape, from what its board holds:

  * MLB: the pitching matchup (a table of the two starters, each lineup
    against tonight's hand, strikeout rates, the pens), the park, the
    weather and the plate umpire, a read on every hitter and starter, the
    injured list, and the run line said as a run line — no team totals
    read off a line a run and a half wide;
  * NHL: the tale of the tape with ranks and tonight's expected goals,
    the goalies (confirmed or not, save rate, goals saved above
    expected), the injury report and pulled props, and the reads;
  * NBA and WNBA: rest and travel off the schedule spots, who carries
    each team over his last ten (the build's own logs), where each
    defence gives up the most and the fewest, and the injury report;
  * every league: the market, the short version, what changed (a starter
    scratched, a goalie confirmed, the lineups out), no prop pick, the
    paywall, Ask, and the locked teaser in the league's own words.

Run directly: `python3 tests/test_every_league_gets_a_game_report.py`
"""
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import askbot                                           # noqa: E402
from engine import gamereport as R                                  # noqa: E402
from engine import gate                                             # noqa: E402
from engine import leaguereport as L                                # noqa: E402

REPORT_JS = os.path.join(ROOT, "web", "js", "report.js")


def _src(name):
    return open(os.path.join(ROOT, name), encoding="utf-8").read()


def _read(player, team, opp, pos, read, label, pro=(), con=(), notes=()):
    return {"player": player, "team": team, "opp": opp, "pos": pos, "read": read, "label": label,
            "pro": list(pro), "con": list(con), "notes": list(notes), "lean": ["hits", "total_bases"],
            "headshot": "", "usage": {}}


def _mlb_board():
    wheeler = {"name": "Zack Wheeler", "throws": "R", "k_rate": 0.29, "xera": 3.05, "slg_vs_l": 0.35, "slg_vs_r": 0.33}
    assad = {"name": "Javier Assad", "throws": "R", "k_rate": 0.19, "xera": 4.6, "slg_vs_l": 0.47, "slg_vs_r": 0.41}
    g = {"away": "PHI", "home": "CHC", "date": "2026-06-20", "kickoff": "2026-06-20T18:20:00Z",
         "spread": 1.5, "total": 9.5, "home_ml": 140, "away_ml": -165, "roof": "open",
         "park": {"name": "Wrigley Field", "lf_ft": 355, "cf_ft": 400, "rf_ft": 353, "roof": "open",
                  "surface": "grass", "altitude_ft": 0, "plays": "The most weather-dependent park in baseball."},
         "park_name": "Wrigley Field", "lineups_confirmed": False, "plate_umpire": "Pat Hoberg",
         "weather": {"dome": False, "temp_f": 82, "wind_mph": 16, "wind_dir": "out", "rain": False},
         "conditions": {"why": ["Wind blowing OUT at 16 mph — +19% to home-run probability"]},
         "pitchers": {"home": {"name": "Javier Assad", "throws": "R", "xera": 4.6, "k_rate": 0.19},
                      "away": {"name": "Zack Wheeler", "throws": "R", "xera": 3.05, "k_rate": 0.29}},
         "line_open": {"spread_home": 1.5, "spread_move": 0, "total": 9.0, "total_move": 0.5},
         "mlb_tape": {"sides": {
             "PHI": {"mix": "four-seamers 45%, sliders 30%, changeups 15%",
                     "vs_hand": {"hand": "R", "factor": 1.05, "hitters": 8}, "starter": wheeler,
                     "k_rate": 0.21, "pen_rank": 6, "pen_fatigue": 2.0},
             "CHC": {"mix": "sinkers 40%, sweepers 30%, cutters 20%",
                     "vs_hand": {"hand": "R", "factor": 0.99, "hitters": 7}, "starter": assad,
                     "k_rate": 0.25, "pen_rank": 27, "pen_fatigue": 7.1}},
             "park": {"name": "Wrigley Field", "hr": 1.04, "runs": 1.02, "k": 1.0},
             "weather": {"roof_closed": False, "temp_f": 82, "wind_mph": 16, "wind": "out"},
             "umpire": {"name": "Pat Hoberg", "k": 1.04, "runs": 0.97},
             "league": {"slg": 0.4, "k_rate": 0.22}}}
    reads = [_read("Zack Wheeler", "PHI", "CHC", "SP", "good", "Good matchup",
                   pro=["CHC strikes out 25.0% of the time (league 22%)", "Strikes out 29% of the batters he faces"],
                   con=["Wind blowing out at 16 mph"]),
             _read("Javier Assad", "CHC", "PHI", "SP", "tough", "Tough matchup",
                   pro=["Expected ERA 4.60"], con=["PHI rarely strikes out (21.0%)", "Expected ERA 4.60"]),
             _read("Kyle Schwarber", "PHI", "CHC", "DH", "breakout", "Breakout candidate",
                   pro=["Javier Assad allows a .470 SLG to lefties", "Barrels 18% of his batted balls",
                        "Bats 1st — the most trips to the plate"], notes=["Career against Javier Assad: 0.50 a game"]),
             _read("Seiya Suzuki", "CHC", "PHI", "RF", "tough", "Tough matchup",
                   con=["Zack Wheeler holds righties to a .330 SLG"])]
    return {"date": "2026-06-20", "games": [g], "scan_reads": {"PHI@CHC": {"players": reads}},
            "injured_list": ["Bryce Harper", "Somebody Else"],
            "recommendations": [{"player": "Bryce Harper", "team": "PHI", "line": 1.5, "odds": -130},
                                {"player": "Somebody Else", "team": "NYY"}]}


def _nhl_board():
    tape = {"sides": {
        "BOS": {"gf": 2.91, "ga": 3.2, "sog_for": 28.1, "sog_against": 31.5, "xgf_ev": 2.21, "xga_ev": 2.6,
                "ranks": {"gf": 20, "ga": 24, "sog_for": 22, "sog_against": 27, "xgf_ev": 19, "xga_ev": 26},
                "starter": "Jeremy Swayman", "starter_sv": 0.904, "starter_gsax": -3.4, "starter_share": 0.7,
                "starter_sure": False, "starter_source": "", "b2b": True, "xg": 2.7,
                "season_weight": 0.6, "gp_season": 6,
                "injuries": [{"player": "Charlie McAvoy", "status": "Out", "injury": "Shoulder"}]},
        "TOR": {"gf": 3.6, "ga": 2.7, "sog_for": 33.2, "sog_against": 27.0, "xgf_ev": 2.7, "xga_ev": 2.2,
                "ranks": {"gf": 3, "ga": 6, "sog_for": 2, "sog_against": 5, "xgf_ev": 4, "xga_ev": 7},
                "starter": "Anthony Stolarz", "starter_sv": 0.918, "starter_gsax": 4.2, "starter_share": 0.8,
                "starter_sure": True, "starter_source": "dailyfaceoff", "b2b": False, "xg": 3.4,
                "season_weight": 1.0, "gp_season": 6, "injuries": []}},
        "teams": 32, "pulled": ["Brad Marchand"]}
    g = {"away": "BOS", "home": "TOR", "date": "2026-10-21", "kickoff": "2026-10-21T23:00:00Z",
         "spread": -1.5, "total": 6.5, "home_ml": -175, "away_ml": 150, "nhl_tape": tape}
    reads = [_read("Auston Matthews", "TOR", "BOS", "C", "breakout", "Breakout spot",
                   pro=["BOS gives up the 6th-most shots a game", "TOR is expected to score 3.4 — a high-event night",
                        "Faces Jeremy Swayman, -3.4 goals saved above expected lately"]),
             _read("David Pastrnak", "BOS", "TOR", "RW", "tough", "Tough matchup",
                   con=["Faces Anthony Stolarz, +4.2 goals saved above expected lately"]),
             _read("Anthony Stolarz", "TOR", "BOS", "G", "neutral", "Neutral",
                   pro=["BOS shoots the 11th-fewest a game"], con=["A lopsided game"])]
    return {"date": "2026-10-21", "games": [g], "scan_reads": {"BOS@TOR": {"players": reads}}}


def _nba_board():
    games = [{"home": "BOS", "away": "MIA", "date": "2026-10-22", "kickoff": "2026-10-22T23:30:00Z",
              "spread": -11.5, "total": 214.5, "home_ml": -800, "away_ml": 550}]
    spots = [{"home": "BOS", "away": "MIA", "arena": "TD Garden", "feet": 20, "spread": -11.5,
              "teams": {"home": {"team": "BOS", "rest": "2plus", "flags": ["blowout"]},
                        "away": {"team": "MIA", "rest": "b2b_home", "flags": ["b2b_home", "long_trip", "blowout"],
                                 "from": "DEN", "days_since": 1, "miles": 1760, "tz_shift": 2}}}]
    hist = {"Jayson Tatum": {"team": "BOS", "starter": True, "minutes": [36, 38, 35, 37],
                             "pts": [30, 25, 28, 27], "reb": [9, 8, 7, 10], "ast": [5, 4, 6, 5], "fg3m": [3, 4, 2, 3]},
            "Jaylen Brown": {"team": "BOS", "starter": True, "minutes": [34, 33, 35], "pts": [24, 22, 20]},
            "Bam Adebayo": {"team": "MIA", "starter": True, "minutes": [35, 34, 36], "pts": [18, 20, 16],
                            "reb": [11, 10, 12]},
            "Tyler Herro": {"team": "MIA", "starter": True, "minutes": [33, 35, 34], "pts": [22, 25, 21]},
            "Bench Guy": {"team": "MIA", "minutes": [12, 10], "pts": [4, 6]}}
    listed = {"Tyler Herro": {"player": "Tyler Herro", "status": "Out", "injury": "Ankle"},
              "Jaylen Brown": {"player": "Jaylen Brown", "status": "Questionable", "injury": "Hamstring"}}
    dvp = {"MIA": {"pts": {"pg": 118.2, "league": 113.0, "rank": 2, "of": 30, "games": 8},
                   "reb": {"pg": 41.0, "league": 44.0, "rank": 29, "of": 30, "games": 8}},
           "BOS": {"fg3m": {"pg": 10.1, "league": 12.8, "rank": 30, "of": 30, "games": 8}}}
    meta = L.nba_meta(games, hist, listed, dvp, False)
    return {"date": "2026-10-22", "games": games, "schedule_spots": spots}, meta


def _attach(board, sport, **kw):
    line = L.attach(board, sport, **kw)
    assert board.get("game_reports"), line
    return board["game_reports"][0], line


def test_the_mlb_report_reads_the_pitching_matchup_the_park_and_the_reads():
    rep, line = _attach(_mlb_board(), "mlb")
    assert line.startswith("Game reports: 1 game(s)"), line
    assert rep["sport"] == "mlb" and rep["title"] == "Phillies at Cubs", rep["title"]
    keys = [s["key"] for s in rep["sections"]]
    assert keys == ["short", "facts", "market", "pitching", "watch", "weather", "injuries", "before"], keys
    text = R.to_text(rep)
    for want in ("PHI −1.5 on the run line, total 9.5; the moneyline makes PHI a 60% favorite",
                 "On the mound: Zack Wheeler (PHI, R, 3.05 xERA, 29% K) against Javier Assad (CHC, R, 4.60 xERA, 19% K)",
                 "Tired bullpen: CHC (7.1 relief innings the last two days)",
                 "Could shine: Kyle Schwarber (PHI)", "Could struggle: Seiya Suzuki (CHC)",
                 "The lineups are not out yet",
                 "First pitch: Saturday, Jun. 20, 2:20 PM ET",
                 "Ballpark: Wrigley Field — open air, grass; 355 feet to left, 400 to center, 353 to right",
                 "Lineups: not out yet", "Plate umpire: Pat Hoberg",
                 "The run line opened at PHI −1.5 and has not moved", "The total opened at 9 and is up 0.5",
                 "Phillies' starter throws four-seamers 45%, sliders 30%, changeups 15%",
                 "PHI's lineup hits right-handed pitching 5% better than its average (8 hitters measured).",
                 "CHC's lineup hits right-handed pitching about its average (7 hitters measured)",
                 "CHC strikes out 25.0% of the time (league 22%)",
                 "The pens: Phillies' bullpen ranks 6th; Cubs' bullpen ranks 27th and threw 7.1 relief innings "
                 "the last two days — tired",
                 "Wrigley Field plays +4% home runs, +2% runs, ±0% strikeouts against an average park",
                 "Weather: 82°F, wind 16 mph blowing out",
                 "Plate umpire Pat Hoberg: +4% strikeouts, −3% runs in his games",
                 "On the injured list: Bryce Harper (PHI).",
                 "Lineups post two to four hours before first pitch"):
        assert want in text, (want, text)
    # The starters' table, slugging by side as baseball writes it.
    tab = next(b for s in rep["sections"] if s["key"] == "pitching" for b in s["blocks"] if b["type"] == "table")
    assert tab["head"] == ["", "Zack Wheeler (PHI)", "Javier Assad (CHC)"]
    assert ["SLG allowed, lefties", ".350", ".470"] in tab["rows"], tab["rows"]
    # A run line implies no margin: no team totals read off it.
    assert "That puts" not in text and " points" not in text
    # Both starters' reads under the table, for and against; the hitters
    # in the watch list, breakout first.
    pitch = next(s for s in rep["sections"] if s["key"] == "pitching")
    cards = next(b for b in pitch["blocks"] if b["type"] == "verdicts")["items"]
    assert [c["title"] for c in cards] == ["Zack Wheeler", "Javier Assad"]
    assert "Against: wind blowing out at 16 mph." in cards[0]["why"], cards[0]["why"]
    # A reason that opens on a team's code keeps its capitals.
    assert "Against: PHI rarely strikes out (21.0%)." in cards[1]["why"], cards[1]["why"]
    watch = next(s for s in rep["sections"] if s["key"] == "watch")
    shine = next(b for b in watch["blocks"] if b["type"] == "verdicts")["items"][0]
    assert shine["title"] == "Kyle Schwarber" and shine["verdict"] == "up" and len(shine["why"]) == 4


def test_the_nhl_report_reads_the_tape_the_goalies_and_the_injuries():
    rep, _line = _attach(_nhl_board(), "nhl")
    keys = [s["key"] for s in rep["sections"]]
    assert keys == ["short", "facts", "market", "tape", "goalies", "watch", "injuries", "before"], keys
    assert rep["title"] == "Bruins at Maple Leafs", rep["title"]
    text = R.to_text(rep)
    for want in ("TOR −1.5 on the puck line, total 6.5; the moneyline makes TOR a 61% favorite",
                 "In net: Jeremy Swayman (BOS, not confirmed) against Anthony Stolarz (TOR)",
                 "Our game model expects BOS 2.7 and TOR 3.4 goals",
                 "BOS is on the second night of a back-to-back",
                 "Could shine: Auston Matthews (TOR)", "Could struggle: David Pastrnak (BOS)",
                 "Out: Charlie McAvoy (BOS)",
                 "Puck drop: Wednesday, Oct. 21, 7:00 PM ET",
                 "Bruins: the second night of a back-to-back",
                 "BOS has played 6 games this season, so last season still carries 40% of its numbers",
                 "Jeremy Swayman for BOS — probable, not confirmed; .904 save rate; \u22123.4 goals saved above "
                 "expected lately; started 70% of Bruins' recent games",
                 "Anthony Stolarz for TOR — confirmed",
                 "TOR shoots the 2nd-most, and BOS allows the 6th-most shots — a busy night for BOS's goalie",
                 "Charlie McAvoy (BOS) — out, shoulder",
                 "Every book took Brad Marchand's props down before puck drop",
                 "Starting goalies are confirmed after the morning skate; not yet for BOS"):
        assert want in text, (want, text)
    tab = next(b for s in rep["sections"] if s["key"] == "tape" for b in s["blocks"] if b["type"] == "table")
    assert ["Goals for a game", "2.91 (20th)", "3.60 (3rd)"] in tab["rows"], tab["rows"]
    assert tab["rows"][-1] == ["Expected goals tonight", "2.7", "3.4"], tab["rows"][-1]
    goalies = next(s for s in rep["sections"] if s["key"] == "goalies")
    assert any(b["type"] == "verdicts" for b in goalies["blocks"])


def test_the_nba_report_reads_rest_who_carries_each_team_and_the_defences():
    board, meta = _nba_board()
    rep, _line = _attach(board, "nba", meta=meta)
    keys = [s["key"] for s in rep["sections"]]
    assert keys == ["short", "facts", "market", "carry", "defense", "injuries", "before"], keys
    assert rep["title"] == "Heat at Celtics"
    text = R.to_text(rep)
    for want in ("BOS by 11.5 at home, total 214.5; the moneyline makes BOS an 85% favorite",
                 "MIA is on the second night of a back-to-back",
                 "Out: Tyler Herro (MIA)",
                 "Leading the scoring lately: Bam Adebayo (MIA, 18 points a game) and Jayson Tatum (BOS, 27.5 points a game)",
                 "Blowout watch: a spread of 10 or more",
                 "Tip-off: Thursday, Oct. 22, 7:30 PM ET", "Arena: TD Garden",
                 "Heat: on the second night of a back-to-back; 1,760 miles from DEN (a day ago); the clock moved "
                 "ahead 2 hours",
                 "That puts BOS at about 113 points and MIA at about 101.5",
                 "MIA's defence gives up the most points (118.2 a game, 2nd-most; league 113)",
                 "MIA's defence gives up the fewest rebounds (41 a game, 2nd-fewest; league 44)",
                 "BOS's defence gives up the fewest threes (10.1 a game, 1st-fewest; league 12.8)",
                 "Per game, not per possession",
                 "Tyler Herro (MIA) — out, ankle", "Jaylen Brown (BOS) — questionable, hamstring",
                 "Still to be decided: Jaylen Brown (BOS, questionable)"):
        assert want in text, (want, text)
    carry = next(s for s in rep["sections"] if s["key"] == "carry")
    players = [b for b in carry["blocks"] if b["type"] == "players"]
    # The man ruled out is not among who carries his team; a bench player
    # with two games is not either.
    miami = [i["player"] for i in players[0]["items"]]
    assert miami == ["Bam Adebayo"], miami
    assert "Bam Adebayo (MIA) — Starter: 35 minutes" in text, text
    assert players[1]["items"][0]["text"] == ("36.5 minutes, 27.5 points, 8.5 rebounds, 5 assists, 3 threes a game "
                                              "over his last 4"), players[1]["items"][0]["text"]
    # The WNBA reads the NBA's report.
    board2, meta2 = _nba_board()
    assert L.attach(board2, "wnba", meta=meta2).startswith("Game reports: 1 game(s)")


def test_a_chance_is_read_with_its_article():
    assert [R.a_pct(x) for x in (0.6, 0.85, 0.18, 0.11, 0.08, 0.81, 0.5)] == \
        ["a 60%", "an 85%", "an 18%", "an 11%", "an 8%", "an 81%", "a 50%"]


def test_no_prop_pick_reaches_any_league_report():
    board = _mlb_board()
    board["scan_reads"]["PHI@CHC"]["microscope"] = [{"player": "Kyle Schwarber", "market": "total_bases",
                                                     "line": 1.5, "odds": -118, "prob": 0.6123}]
    rep, _ = _attach(board, "mlb")
    text = json.dumps(rep, ensure_ascii=False)
    for mark in ("-118", "0.6123", "61%", "total_bases", "home_runs", "-130"):
        assert mark not in text, mark
    nrep, _ = _attach(_nhl_board(), "nhl")
    assert "sog" not in json.dumps(nrep) and "anytime" not in json.dumps(nrep)


def test_what_changed_sees_a_scratched_starter_a_confirmed_goalie_and_the_lineups():
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "web", "data"))
    out = os.path.join(d, "web", "data", "mlb_recommendations.json")
    _attach(_mlb_board(), "mlb", out=out, at="2026-06-19T10:00:00")
    later = _mlb_board()
    g = later["games"][0]
    g["mlb_tape"]["sides"]["PHI"]["starter"] = {"name": "Cristopher Sánchez", "throws": "L", "k_rate": 0.24,
                                                "xera": 3.4, "slg_vs_l": 0.3, "slg_vs_r": 0.36}
    g["lineups_confirmed"] = True
    g["weather"]["wind_dir"] = "in"
    rep, line = _attach(later, "mlb", out=out, at="2026-06-20T12:15:00")
    moved = next(s for s in rep["sections"] if s["key"] == "changes")
    items = next(b for b in moved["blocks"] if b["type"] == "list")["items"]
    for want in ("PHI's starting pitcher is now Cristopher Sánchez, not Zack Wheeler.",
                 "The forecast moved from 82°F, wind 16 mph blowing out to 82°F, wind 16 mph blowing in.",
                 "Both lineups are out."):
        assert want in items, (want, items)
    assert "what changed: 1 game(s) moved" in line, line
    # Hockey: the probable goalie confirmed.
    out2 = os.path.join(d, "web", "data", "nhl.json")
    _attach(_nhl_board(), "nhl", out=out2, at="2026-10-21T09:00:00")
    b2 = _nhl_board()
    b2["games"][0]["nhl_tape"]["sides"]["BOS"]["starter_sure"] = True
    rep2, _ = _attach(b2, "nhl", out=out2, at="2026-10-21T11:30:00")
    items2 = next(b for s in rep2["sections"] if s["key"] == "changes" for b in s["blocks"] if b["type"] == "list")["items"]
    assert items2 == ["BOS's starting goalie is confirmed: Jeremy Swayman."], items2
    # Basketball: a questionable man ruled out.
    out3 = os.path.join(d, "web", "data", "nba.json")
    board3, meta3 = _nba_board()
    _attach(board3, "nba", meta=meta3, out=out3, at="2026-10-22T10:00:00")
    board4, meta4 = _nba_board()
    meta4["MIA@BOS"]["injuries"] = [dict(i, status="Out") if i["player"] == "Jaylen Brown" else i
                                    for i in meta4["MIA@BOS"]["injuries"]]
    rep4, _ = _attach(board4, "nba", meta=meta4, out=out3, at="2026-10-22T17:45:00")
    items4 = next(b for s in rep4["sections"] if s["key"] == "changes" for b in s["blocks"] if b["type"] == "list")["items"]
    assert items4 == ["Jaylen Brown (BOS) is now out; he was questionable."], items4


def test_every_build_hangs_it_last_of_the_game_hooks_and_the_paywall_takes_it():
    mlb = _src("mlb_build.py")
    assert mlb.index('_lo.attach_to_board(result, "mlb")') < mlb.index("_lgr.attach(result, 'mlb', out=args.out)") \
        < mlb.index('_potd.attach(result, "mlb")')
    nhl = _src("nhl_build.py")
    assert nhl.index('("opening lines"') < nhl.index('("game reports"') < nhl.index('("pick of the day"')
    assert 'attach(\n                out, SPORT, out=args.out)' in nhl
    nba = _src("nba_build.py")
    assert nba.index("_lo.attach_to_board(out, args.league)") \
        < nba.index("_lgr.attach(out, args.league, meta=_gr_meta, out=args.out)") \
        < nba.index("_potd.attach(out, args.league, lines=potd_lines)")
    assert "_gr_meta = _gr_nba_meta(games, hist, listed, _gr_rt, _gr_last, injuries_read=bool(injuries))" in nba
    for board, name in ((_mlb_board(), "mlb_recommendations.json"), (_nhl_board(), "nhl.json"),
                        (_nba_board()[0], "nba.json")):
        L.attach(board, {"mlb_recommendations.json": "mlb", "nhl.json": "nhl", "nba.json": "nba"}[name])
        sealed = gate.redact(copy.deepcopy(board), name)
        assert not sealed.get("game_reports") and (sealed.get("locked") or {}).get("game_reports") == 1, name
    # A broken board never stops a build.
    assert L.attach({"games": [None, {"home": "BOS"}, 7]}, "nhl").startswith(("Game reports", "⚠"))
    assert L.attach({"games": [{"home": "BOS", "away": "MIA", "nhl_tape": "junk"}]}, "nhl").startswith(
        ("Game reports", "⚠"))
    assert L.build({"home": "A", "away": "B"}, {}, sport="ufc") is None


def test_ask_reads_a_league_report_whole_tables_and_cards_included():
    board = _mlb_board()
    L.attach(board, "mlb")
    facts = askbot.report_facts(board, board["games"][0])
    assert facts["short_version"][0].startswith("PHI −1.5 on the run line")
    assert "Expected ERA: 3.05 | 4.60" in facts["pitching"], facts["pitching"]
    assert any(x.startswith("Kyle Schwarber (PHI) — Breakout candidate: ") for x in facts["watch"]), facts["watch"]
    assert len(json.dumps(facts, ensure_ascii=False)) <= askbot.REPORT_CHARS
    assert "the tale of the tape and the goalies" in askbot.SYSTEM


def test_the_page_teases_every_league_in_its_own_words():
    app = _src("web/js/app.js")
    assert "const locked = !r && !_grFailed && d.locked && d.locked.game_reports;" in app
    assert 'url: cleanURL("game", gameSlug(g)), sport: state.sport' in app
    node = shutil.which("node")
    if not node:
        print("      (skipped: no Node)")
        return
    script = (
        "const vm = require('vm'); const fs = require('fs');"
        "const esc = (s) => String(s == null ? '' : s);"
        "const ctx = { window: {}, escapeHtml: esc, escapeAttr: esc, slugify: (s) => s, teamName: (t) => t,"
        " playerAvatar: () => '', document: { addEventListener() {} } };"
        "vm.createContext(ctx);"
        f"vm.runInContext(fs.readFileSync({json.dumps(REPORT_JS)}, 'utf8'), ctx);"
        "const R = ctx.window.QBReport;"
        "process.stdout.write(JSON.stringify(['nfl', 'mlb', 'nhl', 'nba', 'wnba', 'cfb', ''].map("
        "(s) => R.html(null, {sport: s}))));")
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    nfl, mlb, nhl, nba, wnba, cfb, none = json.loads(out.stdout)
    assert "the trenches" in nfl and "the trenches" in cfb and "the trenches" in none
    assert "the pitching matchup" in mlb and "the trenches" not in mlb
    assert "the goalies" in nhl and "the trenches" not in nhl
    assert "who carries each team" in nba and nba == wnba
    for teaser in (mlb, nhl, nba):
        assert "part of the subscription" in teaser


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
