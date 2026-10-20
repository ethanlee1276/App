"""The game report on every college game page (engine/gamereport, cfb_build).

Ethan, 2026-10-20: "I want you too do all of it besides D" — the college
report among it. The NFL's report, written from what a college board
carries and in college's own terms:

  * schools by their short names, ranked ones as "No. 7"; a UTC kickoff
    said in Eastern time; the venue, indoors or not; a conference game, or
    the two conferences of a non-conference one;
  * shares of the CATCHES, not the targets (college logs no targets), and
    a player's games by their dates, his opponents by name;
  * college's own unit stats — havoc, line yards, stuff rate — and ranks
    said to be raw, because they are not opponent-adjusted;
  * scoring chances (drives to the opponent's 40) instead of red-zone
    plays;
  * the meetings from the history database's own games, at their lines;
  * nothing that is the NFL's alone: no inactives list, no referee line,
    no kicking air (college's stadium altitudes are not kept, and the
    NFL's table shares codes with schools).

Run directly: `python3 tests/test_the_college_game_report.py`
"""
import copy
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import db                                               # noqa: E402
from engine import gamereport as R                                  # noqa: E402
from engine import gate                                             # noqa: E402
from engine import reportdata as RD                                 # noqa: E402

BUILD = open(os.path.join(ROOT, "cfb_build.py"), encoding="utf-8").read()


def _unit(v, r):
    return {"value": v, "rank": r}


def _units(off, dfn, games=7, blend=0.8):
    keys = ("overall", "passing", "rushing", "success", "explosive", "havoc", "line", "stuff")
    vals = {"overall": 0.21, "passing": 0.33, "rushing": 0.12, "success": 0.47, "explosive": 0.11,
            "havoc": 0.18, "line": 3.1, "stuff": 0.16}
    return {"games": games, "blend": blend,
            "off": {k: _unit(vals[k], r) for k, r in zip(keys, off)},
            "def": {k: _unit(vals[k], r) for k, r in zip(keys, dfn)}}


def _board():
    game = {"home": "IU", "away": "MIA", "date": "2026-10-24", "kickoff": "2026-10-24T19:30Z",
            "home_rank": 2, "away_rank": 7, "home_conference": "Big Ten", "away_conference": "ACC",
            "venue": "Memorial Stadium", "indoor": False, "park_name": "Memorial Stadium",
            "spread": -7.5, "total": 47.0,
            "weather": {"temp_f": 51, "wind_mph": 9, "forecast": True, "measured": True},
            "scan": {"units": {"IU": _units((5, 9, 12, 8, 20, 30, 10, 40), (3, 4, 6, 9, 11, 2, 15, 7)),
                               "MIA": _units((14, 6, 40, 22, 9, 60, 55, 70), (21, 30, 18, 25, 40, 50, 33, 61))},
                     "edges": [{"unit": "rushing", "label": "run game", "off": "IU", "def": "MIA",
                                "off_rank": 12, "def_rank": 40, "gap": 28}],
                     "method": {"teams": 136, "opponent_adjusted": False}, "n_teams": 136,
                     "redzone": {"IU": {"off": 6.1, "def": 3.2, "off_rel": 0.22, "def_rel": -0.31,
                                        "what": "scoring chances"},
                                 "MIA": {"off": 5.0, "def": 4.4, "off_rel": 0.0, "def_rel": -0.04,
                                         "what": "scoring chances"}},
                     "injuries": [], "coverage": {}, "rush": {}, "line_out": {}}}
    reads = [
        {"player": "Roman Hemby", "team": "IU", "pos": "RB", "read": "good", "label": "Good matchup",
         "usage": {"carry_share": 0.52, "carries_pg": 15.2, "tgt_share": 0.09, "rec_pg": 1.2,
                   "share_of": "catches"}, "pro": ["MIA allows 5.1 yards a carry"]},
        {"player": "Elijah Sarratt", "team": "IU", "pos": "WR", "read": "neutral", "label": "Neutral",
         "usage": {"tgt_share": 0.31, "rec_pg": 5.2, "share_of": "catches"}, "pro": []},
    ]
    return {"date": "2026-10-24", "built_at": "2026-10-24T12:00", "sport": "cfb",
            "teams": {"IU": {"name": "Indiana Hoosiers", "nick": "Indiana"},
                      "MIA": {"name": "Miami Hurricanes", "nick": "Miami"},
                      "PUR": {"name": "Purdue Boilermakers", "nick": "Purdue"}},
            "games": [game], "scan_reads": {"MIA@IU": {"players": reads}}}


def _conn():
    conn = db.connect(":memory:")
    rows = []

    def log(player, team, opp, day, home, **stats):
        rows.extend({"sport": "cfb", "season": 2026, "period": day, "game_id": f"g{day}",
                     "player": player, "team": team, "opponent": opp, "position": "", "home": home,
                     "market": k, "value": float(v)} for k, v in stats.items())
    log("Roman Hemby", "IU", "PUR", "2026-10-17", 0, carries=18, rush_yds=97, rush_td=1, receptions=2,
        rec_yds=11, rec_td=0, rz_car=4, i5_car=2, rz_rec=0)
    log("Roman Hemby", "IU", "MSU", "2026-10-10", 1, carries=14, rush_yds=61, rush_td=0, receptions=1,
        rec_yds=8, rec_td=0, rz_car=2, i5_car=0, rz_rec=1)
    log("Elijah Sarratt", "IU", "PUR", "2026-10-17", 0, receptions=6, rec_yds=88, rec_td=1, rz_rec=2)
    log("Elijah Sarratt", "IU", "MSU", "2026-10-10", 1, receptions=4, rec_yds=52, rec_td=0, rz_rec=1)
    log("Kurtis Rourke", "IU", "PUR", "2026-10-17", 0, pass_att=31, pass_yds=244, pass_td=2)
    db.upsert_player_logs(conn, rows)
    conn.executemany("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score, "
                     "spread, total, extra) VALUES ('cfb', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
                         (2025, "2026-01-20", "a", "IU", "MIA", 27, 21, -7.5, 47.0, '{"neutral": true}'),
                         (2024, "2024-09-14", "b", "MIA", "IU", 31, 17, -3.0, 51.0, "{}"),
                         (2025, "2025-10-05", "c", "IU", "PUR", 40, 10, -20.0, 55.0, "{}")])
    return conn


def _report(**kw):
    board = _board()
    R.attach(board, conn=_conn(), sport="cfb", season=2026,
             meta={"MIA@IU": {"neutral_site": False, "conference_game": False}}, **kw)
    return board, board["game_reports"][0]


def _sec(rep, key):
    return next((s for s in rep["sections"] if s["key"] == key), None)


def test_the_facts_are_said_in_colleges_own_terms():
    _board_, rep = _report()
    assert rep["title"] == "Miami at Indiana" and rep["sport"] == "cfb"
    text = R.to_text(rep)
    assert "Kickoff: Saturday, Oct. 24, 3:30 PM ET" in text, "19:30 UTC is 3:30 PM in October"
    assert "No. 7 Miami at No. 2 Indiana" in text
    assert "Venue: Memorial Stadium" in text
    assert "Non-conference: Miami (ACC) against Indiana (Big Ten)" in text
    board = _board()
    R.attach(board, conn=_conn(), sport="cfb", season=2026,
             meta={"MIA@IU": {"neutral_site": True, "conference_game": True}})
    text = R.to_text(board["game_reports"][0])
    assert "— a neutral site" in text and "A conference game" in text


def test_shares_are_of_the_catches_and_his_games_go_by_date():
    _b, rep = _report()
    text = R.to_text(rep)
    assert "Who catches it: Elijah Sarratt (WR) 31% of the catches, 5.2 a game" in text
    assert "of the targets" not in text, "college logs no targets"
    cards = {i["player"]: dict((k, v) for k, v in i["form"])
             for b in _sec(rep, "matchups")["blocks"] if b.get("type") == "verdicts" for i in b["items"]}
    hemby = cards["Roman Hemby"]
    assert hemby["This season"] == ["2 games: 32 carries, 158 yds (4.9 a carry), 1 TD; 3 catches, 19 yds"]
    assert hemby["Last 2"][0] == "Oct. 17 at Purdue: 18 carries, 97 yds, 1 TD; 2 catches, 11 yds"
    assert hemby["Red zone"] == ["6 carries inside the 20 (2 inside the 5) — 100% of IU's; "
                                 "1 catch inside the 20 — 25% of IU's"]
    sarratt = cards["Elijah Sarratt"]
    assert sarratt["Last 2"][0] == "Oct. 17 at Purdue: 6 catches, 88 yds, 1 TD", "no targets to say"
    assert sarratt["This season"] == ["2 games: 10 catches, 140 yds (70 a game), 1 TD"]


def test_colleges_own_units_raw_ranks_and_scoring_chances():
    _b, rep = _report()
    text = R.to_text(rep)
    rankings = _sec(rep, "rankings")
    first = next(b for b in rankings["blocks"] if b.get("title") == "Miami offense vs Indiana defense")
    rows = {r[0]: r for r in first["rows"]}
    assert rows["Havoc rate"][1:3] == ["18.0% · 60th", "18.0% · 2nd"], rows["Havoc rate"]
    assert "Line yards" in rows and "Stuff rate" in rows
    assert "CFBD's PPA" in text and "not adjusted for opponents" in text
    assert "adjusted for the opponents each team has faced" not in text
    # The edge bar is 30% of 136 schools: 41 ranks.
    assert "IU's line yards rank 10th against MIA's run front (33rd)." in text
    assert "MIA's runs stuffed at the line rank 70th against IU's stuff rate (7th) — edge IU" in text
    assert "MIA gets about 5 scoring chances a game — drives that reach the opponent's 40 (about average)" in text
    assert ("IU gets about 6.1 scoring chances a game — drives that reach the opponent's 40 "
            "(22% above the average team); MIA allows about 4.4 (4% below average)") in text
    assert "red-zone plays" not in text


def test_the_meetings_come_off_the_history_database():
    _b, rep = _report()
    head = _sec(rep, "meetings")["blocks"][0]["text"]
    assert head.startswith("The last 2 meetings are split 1-1"), head
    lines = _sec(rep, "meetings")["blocks"][1]["items"]
    assert lines[0] == "Jan. 20, 2026 (neutral site): IU won 27-21 · IU −7.5, MIA covered · total 47, over.", lines
    assert lines[1] == "Sep. 14, 2024 at MIA: MIA won 31-17 · MIA −3, MIA covered · total 51, under.", lines
    assert not RD.meetings_db(None, "cfb", "IU", "MIA", "2026-10-24")


def test_nothing_that_is_the_nfls_alone():
    _b, rep = _report()
    text = R.to_text(rep)
    for nfl_only in ("Inactives post", "referee", "Kicking air", "Head coaches", "division game"):
        assert nfl_only not in text, nfl_only
    assert "Forecast for kickoff: 51°F, wind 9 mph" in text


def test_the_build_hangs_it_and_the_paywall_takes_it():
    assert "_greport.attach(out, season=_gr_season_of('cfb', args.date), sport='cfb', meta=_gr_meta)" in BUILD
    assert BUILD.index("_lo.attach_to_board(out, \"cfb\")") < BUILD.index("_greport.attach(out") \
        < BUILD.index("_potd.attach(out, \"cfb\")")
    board, _rep = _report()
    sealed = gate.redact(copy.deepcopy(board), "cfb.json")
    assert not sealed.get("game_reports") and (sealed.get("locked") or {}).get("game_reports")
    # A broken board never stops the build.
    assert R.attach({"date": "2026-10-24", "games": [None, {"home": "IU"}]}, sport="cfb").startswith(
        ("Game reports", "⚠"))


def test_no_prop_pick_reaches_the_college_report():
    board = _board()
    board["scan_reads"]["MIA@IU"]["microscope"] = [{"player": "Roman Hemby", "market": "rush_yds",
                                                     "line": 77.5, "odds": -118, "prob": 0.6123}]
    R.attach(board, conn=_conn(), sport="cfb", season=2026)
    text = json.dumps(board["game_reports"], ensure_ascii=False)
    for mark in ("77.5", "-118", "0.6123", "61%"):
        assert mark not in text, mark


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
