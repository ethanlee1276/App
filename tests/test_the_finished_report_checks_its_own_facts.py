"""A finished game's report checks its own facts, and every finished game's check is kept in one list.

Ethan, 2026-11-16: "keep going with the after game report screen and stuff like
that, and think about what users would want to see after the game's over. Like,
they'd probably want to see if the data we were giving them were correct or not,
and the read we had was correct or not, and all that stuff. So we need to fact
check ourselves after the game's over and see if we were correct or not."

engine/reportfacts checks what the report gave before the game against the
final and the box score: the lines (who covered, which side of the total), our
team ratings' and the simulation's picks (and the script the game turned out to
be), how the game would go (football's script by the lines, basketball's pace,
points, close game and blowout watch), the injury report (who played, and the
regulars it missed), the touchdown chances, a player's minutes beside his
grade, and the best calls and the biggest misses. A basketball player who sat
is never graded on a zero. engine/reportrecord keeps every finished game's
check as counts, free at /api/report_record, drawn on the Report Picks page
under "How our reports did", each game opening its own graded report.

    python3 tests/test_the_finished_report_checks_its_own_facts.py
"""
import copy
import gzip
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import reportfacts as F                                  # noqa: E402
from engine import reportgrade as G                                  # noqa: E402

LOG = ("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, position, home, "
       "market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)")
TONIGHT = "2026-10-22"
NIGHTS = ("2026-10-12", "2026-10-14", "2026-10-16", "2026-10-18", "2026-10-20")


def _conn(rows):
    from engine import db as D
    conn = D.connect(Path(tempfile.mkdtemp()) / "history.db")
    conn.executemany(LOG, rows)
    conn.commit()
    return conn


def _hoops(day, player, team, opp, **st):
    return [("nba", 2026, day, f"MIA@BOS-{day}", player, team, opp, "", int(team == "BOS"), m, v)
            for m, v in st.items()]


#: A night's full line for a team's man, so the night's pace can be read.
def _full(pts, mins, **more):
    return dict(dict(pts=pts, min=mins, fgm=pts // 2.5, fga=pts, fta=4, ftm=3, oreb=1, tov=2, reb=6, ast=4,
                     stl=1, blk=0, fg3m=2, fg3a=6), **more)


def _nba_rows(holiday_listed=False):
    rows = []
    for i, day in enumerate(NIGHTS):
        rows += _hoops(day, "Jayson Tatum", "BOS", "MIA", pts=25 + i, min=36)
        rows += _hoops(day, "Jaylen Brown", "BOS", "MIA", pts=24, min=35)
        rows += _hoops(day, "Jrue Holiday", "BOS", "MIA", pts=12, min=30)
        # Benched the last night (the box files him with zero minutes): no game of his.
        rows += _hoops(day, "Derrick White", "BOS", "MIA", pts=0 if i == 4 else 15, min=0 if i == 4 else 31)
        rows += _hoops(day, "Tyler Herro", "MIA", "BOS", pts=20, min=34)
        rows += _hoops(day, "Bam Adebayo", "MIA", "BOS", pts=18, min=33)
        rows += _hoops(day, "Kel'el Ware", "MIA", "BOS", pts=8, min=24)
        # Traded away after his first three nights: his last game was for another club.
        if i < 3:
            rows += _hoops(day, "Duncan Robinson", "MIA", "BOS", pts=10, min=26)
        else:
            rows += [("nba", 2026, day, f"x-{day}", "Duncan Robinson", "DET", "NYK", "", 1, "min", 25.0)]
    rows += _hoops(TONIGHT, "Jayson Tatum", "BOS", "MIA", **_full(38, 40))
    rows += _hoops(TONIGHT, "Jaylen Brown", "BOS", "MIA", pts=0, min=0)
    rows += _hoops(TONIGHT, "Derrick White", "BOS", "MIA", **_full(22, 38))
    rows += _hoops(TONIGHT, "Bench Guy", "BOS", "MIA", **_full(61, 162))
    rows += _hoops(TONIGHT, "Tyler Herro", "MIA", "BOS", **_full(9, 21))
    rows += _hoops(TONIGHT, "Bam Adebayo", "MIA", "BOS", **_full(20, 36))
    rows += _hoops(TONIGHT, "Bench Two", "MIA", "BOS", **_full(67, 183))
    rows += _hoops(TONIGHT, "Kel'el Ware", "MIA", "BOS", pts=0, min=0)
    return rows


def _nba_report(holiday_listed=False):
    injuries = [("Kel'el Ware (MIA) — out", {"kind": "injury", "player": "Kel'el Ware", "team": "MIA", "status": "out"}),
                ("Jaylen Brown (BOS) — questionable",
                 {"kind": "injury", "player": "Jaylen Brown", "team": "BOS", "status": "questionable"}),
                ("Bam Adebayo (MIA) — out", {"kind": "injury", "player": "Bam Adebayo", "team": "MIA", "status": "out"})]
    if holiday_listed:
        injuries.append(("Jrue Holiday (BOS) — day-to-day",
                         {"kind": "injury", "player": "Jrue Holiday", "team": "BOS", "status": "day-to-day"}))
    return {"game": "MIA@BOS", "away": "MIA", "home": "BOS", "date": TONIGHT, "sport": "nba",
            "line": "BOS by 6.5 at home, total 227.5", "sections": [
        {"key": "verdict", "title": "Who we think wins", "blocks": [{
            "type": "winner", "team": "BOS", "other": "MIA", "name": "Celtics", "other_name": "Heat", "chance": 0.7,
            "ratings": {"team": "MIA", "name": "Heat", "chance": 0.55, "same": False, "even": False}}]},
        {"key": "facts", "title": "Game facts", "blocks": [{"type": "list", "items": [
            "Tip-off: 7:30 PM ET", "Blowout watch: a spread of 10 or more"], "claims": [None, {"kind": "blowout"}]}]},
        {"key": "script", "title": "How the game should go", "blocks": [{"type": "list", "items": [
            "A fast game.", "A high-scoring night.", "A close game by the line."], "claims": [
            {"kind": "pace", "read": "fast", "league": 99.5, "pace": [["MIA", 101.0], ["BOS", 101.5]]},
            {"kind": "scoring", "read": "high", "avg": 219.6, "total": 227.5},
            {"kind": "close", "fav": "BOS", "spread": 3.5}]}]},
        {"key": "watch", "title": "Players to watch", "blocks": [{"type": "verdicts", "items": [
            {"player": "Jayson Tatum", "title": "Jayson Tatum", "team": "BOS", "pos": "F", "verdict": "up", "lean": ["pts"]},
            {"player": "Jaylen Brown", "title": "Jaylen Brown", "team": "BOS", "pos": "G", "verdict": "up", "lean": ["pts"]},
            {"player": "Tyler Herro", "title": "Tyler Herro", "team": "MIA", "pos": "G", "verdict": "up", "lean": ["pts"]},
            {"player": "Derrick White", "title": "Derrick White", "team": "BOS", "pos": "G", "verdict": "up",
             "lean": ["pts"]}]}]},
        {"key": "injuries", "title": "Injuries", "blocks": [{"type": "list", "items": [t for t, _c in injuries],
                                                               "claims": [c for _t, c in injuries]}]}]}


FINAL = {"away": "MIA", "home": "BOS", "date": TONIGHT, "live": {"state": "final", "away_score": 96, "home_score": 121}}


def _grade(report=None, rows=None, final=FINAL):
    rep = report or _nba_report()
    summary = G.grade(rep, final, _conn(rows if rows is not None else _nba_rows()), "nba", TONIGHT)
    return rep, summary


def _sec(rep, key):
    return next(s for s in rep["sections"] if s["key"] == key)


def _card(rep, name):
    return next(it for s in rep["sections"] for b in s["blocks"] for it in b.get("items") or []
                if isinstance(it, dict) and it.get("player") == name)


# --- the lines, the ratings and the simulation ----------------------------------------------------
def test_the_lines_are_checked_against_the_final():
    rep, summary = _grade()
    sc = summary["score"]
    assert sc["status"] == "info" and (sc["cover"], sc["side"]) == ("BOS", "under"), sc
    # In the bettor's own words (GRADE_VERSION 4; Ethan: "its wording is weird and can be better").
    assert sc["words"] == "Celtics −6.5, won by 25 (covered); total 227.5, 217 scored (under)", sc["words"]
    assert (sc["fav"], sc["line"], sc["total_line"]) == ("BOS", 6.5, 227.5), sc
    assert (sc["margin_miss"], sc["total_miss"]) == (18.5, 10.5) and sc["expected"] == {"home": 117.0, "away": 110.5}
    # A report's own numbers first: the call's `expect`, else its `line` words.
    rep2 = _nba_report()
    rep2["sections"][0]["blocks"][0]["expect"] = {"spread": 2.5, "total": 210.5}
    sc2 = F.score_check(rep2, FINAL, "nba")
    assert sc2["cover"] == "BOS" and sc2["side"] == "over", sc2
    assert sc2["words"].startswith("Heat −2.5, Celtics won outright by 25; total 210.5, "), sc2["words"]
    assert F.parse_line("NYR −1.5 on the puck line, total 6.5", "NYR", "BOS") == {"spread": -1.5, "fixed": 1, "total": 6.5}
    assert F.parse_line("a pick’em, total 41.5", "DET", "GB") == {"spread": 0.0, "total": 41.5}
    assert F.parse_line("DET by 3 at home", "DET", "GB") == {"spread": -3.0}
    assert F.parse_line("XYZ by 3", "DET", "GB") is None, "a club not in the game is no line"
    hockey = {"away": "BOS", "home": "NYR", "live": {"state": "final", "away_score": 2, "home_score": 3}}
    pl = F.score_check({"home": "NYR", "away": "BOS", "line": "NYR −1.5 on the puck line, total 6.5"}, hockey, "nhl")
    assert pl["cover"] == "BOS" and pl["words"] == ("NYR −1.5 on the puck line, won by only 1 (BOS covered); "
                                                    "total 6.5, 5 scored (under)"), pl
    assert F.score_check(_nba_report(), {"live": {"state": "live"}}, "nba") is None, "not before the final"


def test_our_ratings_and_the_simulation_are_right_or_wrong_and_the_script_is_named():
    _rep, summary = _grade()
    assert summary["ratings"]["status"] == "wrong", summary["ratings"]
    assert summary["ratings"]["words"] == "wrong — they had the Heat (55%), the other side from the price"
    nfl = {"home": "DET", "away": "GB", "sections": [{"key": "verdict", "blocks": [{
        "type": "winner", "team": "DET", "other": "GB", "name": "Lions", "other_name": "Packers", "chance": 0.58,
        "sim": {"team": "DET", "chance": 0.61, "hist": [0.12, 0.17, 0.32, 0.22, 0.11, 0.06]}}]}]}
    fin = {"home": "DET", "away": "GB", "live": {"state": "final", "away_score": 17, "home_score": 20}}
    s = F.sim_check(nfl, fin)
    assert (s["status"], s["script"], s["share"]) == ("right", "C", 0.32), s
    assert s["words"] == ("right — it had the Lions winning 61% of its games; the game went Script C, the favorite by 1 "
                          "to 7, as 32% of them did"), s["words"]
    upset = F.sim_check(nfl, dict(fin, live={"state": "final", "away_score": 30, "home_score": 20}))
    assert (upset["status"], upset["script"], upset["share"]) == ("wrong", "B", 0.39), upset
    assert [F.script_of(m) for m in (-3, 0, 7, 8, 14, 15)] == ["B", None, "C", "A", "A", "D"]


# --- how the game would go ------------------------------------------------------------------------
def test_footballs_script_by_the_lines_is_checked_half_by_half():
    claim = {"kind": "script", "scoring": "high", "shape": "close", "cut": 47.0, "big": 6.5, "fav": "DET"}
    rep = {"home": "DET", "away": "GB", "sections": [{"key": "scripts", "blocks": [
        {"type": "p", "text": "How the lines say this game is likeliest to go: a high-scoring, close game",
         "claim": claim}]}]}
    fin = {"home": "DET", "away": "GB", "date": "2026-11-15", "live": {"state": "final", "away_score": 17, "home_score": 20}}
    summary = G.grade(rep, fin, _conn([]), "nfl", "2026-W10")
    para = rep["sections"][1]["blocks"][0]
    assert para["grade"]["status"] == "split" and para["grade"]["words"] == (
        "Half right: 37 points, not the high-scoring game read (47 or more); decided by 3, close as read."), para
    grp = next(x for x in summary["groups"] if x["key"] == "script")
    assert (grp["right"], grp["graded"], grp["what"]) == (1, 2, "How the game would go"), grp
    big = F.claim_grade("nfl", dict(claim, scoring="low", shape="big"), None,
                        dict(fin, live={"state": "final", "away_score": 10, "home_score": 27}), rep)
    assert big["status"] == "right" and big["words"] == ("Right: 37 points, low-scoring as read; DET won by 17, "
                                                         "the clear favorite as read."), big
    # The claim the football report writes beside its script (engine/gamescript's own cuts).
    from engine import gamereport as R
    assert R.script_claim({"archetype": "Everyone eats", "favorite": "DET"}) == claim
    assert R.script_claim({"archetype": "Floor, no ceiling", "favorite": "GB"})["shape"] == "big"
    assert R.script_claim({"archetype": "Something new"}) is None


def test_basketballs_pace_points_close_game_and_blowout_watch():
    rep, summary = _grade()
    facts = _sec(rep, "facts")["blocks"][0]["grades"]
    assert facts[0] is None and facts[1]["words"] == "Right: a blowout, decided by 25.", facts
    pace, points, close = _sec(rep, "script")["blocks"][0]["grades"]
    # 129.3 and 104.3 possessions over 240 minutes a side: 116.8 per 48.
    assert pace["status"] == "right" and pace["words"] == ("Right: 116.8 possessions per 48 minutes, over the "
                                                           "league’s 99.5."), pace
    assert points["words"] == "Wrong: 217 points, 2.6 under the average game (219.6).", points
    assert close["words"] == "Wrong: decided by 25, a blowout.", close
    tug = F.claim_grade("nba", {"kind": "pace", "read": "split", "league": 99.5, "pace": [["MIA", 96.0], ["BOS", 120.0]],
                                "fast": "BOS", "slow": "MIA"}, G.box(_conn(_nba_rows()), "nba", FINAL, TONIGHT,
                                                                     ("pts", "min", "fgm", "fga", "fta", "ftm", "oreb",
                                                                      "tov", "reb", "fg3m")), FINAL, rep)
    assert tug["status"] == "info" and tug["words"] == ("Celtics won the tug of war: 116.8 possessions per 48 "
                                                        "minutes, nearer its 120.0 than Heat’s 96.0."), tug
    assert F.claim_grade("nba", {"kind": "scoring", "read": "average", "avg": 219.6}, None, FINAL, rep)["words"] == \
        "It finished at 217 points, 2.6 under the average game (219.6)."
    grp = next(x for x in summary["groups"] if x["key"] == "script")
    assert (grp["right"], grp["graded"]) == (2, 4), grp


# --- the injury report and the touchdown chances ---------------------------------------------------
def test_the_injury_report_is_checked_and_a_regular_it_missed_is_named():
    rep, summary = _grade()
    ware, brown, bam = _sec(rep, "injuries")["blocks"][0]["grades"]
    assert ware == {"status": "right", "says": "sits", "played": False, "words": "Right: sat out."}, \
        "the NBA's box files a man who sat with zero minutes"
    assert brown["status"] == "sat" and brown["words"] == "Sat out.", brown
    assert bam["status"] == "wrong" and bam["words"] == "Wrong: played — 36 minutes, 20 points.", bam
    inj = summary["injuries"]
    assert (inj["right"], inj["wrong"], inj["missed_names"]) == (1, 2, ["Jrue Holiday"]), inj
    assert inj["words"] == ("1 of the 2 listed out or doubtful sat; the one listed questionable or day-to-day sat; "
                            "1 regular sat without being on it (Jrue Holiday)"), inj["words"]
    assert inj["missed"] == ["Not on our injury report: Jrue Holiday (Celtics) didn’t play — 30 minutes a game in "
                             "4 of Celtics’ last 4."], inj["missed"]
    first = _sec(rep, "graded")
    heads = [b.get("text") for b in first["blocks"] if b.get("type") == "h"]
    assert "Missing from our injury report" in heads, heads
    # Listed, he is not missed; benched once (Derrick White), traded (Duncan Robinson): neither is a regular who sat.
    _rep2, s2 = _grade(_nba_report(holiday_listed=True))
    assert s2["injuries"]["missed_names"] == [] and s2["injuries"]["words"].endswith(
        "no regular sat without being on it"), s2["injuries"]
    # A football box keeps only the men with a stat: no stats is said as that, never "sat".
    rows = [("nfl", 2026, "010", "DET-010", "Jahmyr Gibbs", "DET", "GB", "RB", 1, "rush_att", 22.0),
            ("nfl", 2026, "010", "DET-010", "Jahmyr Gibbs", "DET", "GB", "RB", 1, "rush_yds", 140.0),
            ("nfl", 2026, "010", "GB-010", "Josh Jacobs", "GB", "DET", "RB", 0, "rush_att", 6.0),
            ("nfl", 2026, "010", "GB-010", "Josh Jacobs", "GB", "DET", "RB", 0, "rush_yds", 40.0)]
    bx = G.box(_conn(rows), "nfl", {"home": "DET", "away": "GB"}, "2026-W10", F.FOOT_LINES)
    out = F.injury_check("nfl", {"player": "Jayden Reed", "team": "GB", "status": "out"}, bx)
    assert out["words"] == "No stats in the box score, as listed." and out["status"] == "right", out
    q = F.injury_check("nfl", {"player": "Josh Jacobs", "team": "GB", "status": "questionable", "pos": "RB"}, bx)
    assert q["words"] == "Played — 6 carries for 40 yards." and q["status"] == "played", q
    assert F._says("Out (season)") == "sits" and F._says("Probable") == "plays" and F._says("Day-To-Day") == "maybe"


def test_a_hockey_goalie_who_did_not_start_is_never_missing_from_the_injury_report():
    """A regular skater who sat is named; a goalie who sat for the other one is
    not (he sits for a teammate, not an injury), nor is a skater who played."""
    rows = []

    def add(day, player, team, pos, **st):
        rows.extend(("nhl", 2026, day, f"x-{day}", player, team, "BOS" if team == "NYR" else "NYR", pos,
                     int(team == "NYR"), m, v) for m, v in st.items())
    for day in NIGHTS:
        add(day, "Artemi Panarin", "NYR", "L", toi=19.5, points=1)
        add(day, "Adam Fox", "NYR", "D", toi=23.0, points=1)
        add(day, "Jonathan Quick", "NYR", "G", toi=60.0, saves=28)
        add(day, "David Pastrnak", "BOS", "R", toi=20.0, points=1)
    add(TONIGHT, "Artemi Panarin", "NYR", "L", toi=20.1, points=2)
    add(TONIGHT, "Igor Shesterkin", "NYR", "G", toi=60.0, saves=31)
    add(TONIGHT, "David Pastrnak", "BOS", "R", toi=21.0, points=0)
    fin = {"home": "NYR", "away": "BOS", "date": TONIGHT, "live": {"state": "final", "away_score": 2, "home_score": 3}}
    conn = _conn(rows)
    bx = G.box(conn, "nhl", fin, TONIGHT, ("toi", "points", "saves"))
    got = F.missed("nhl", {"sections": []}, bx, conn, fin, TONIGHT, set())
    assert [m["player"] for m in got] == ["Adam Fox"], got
    assert F.missed_words(got[0], "nhl", {"NYR": "Rangers"}) == (
        "Not on our injury report: Adam Fox (Rangers) didn’t play — 23 minutes on the ice a game in 4 of Rangers’ "
        "last 4.")


def test_touchdown_chances_say_who_scored_against_what_we_said():
    rows = [("nfl", 2026, "010", "DET-010", "Jahmyr Gibbs", "DET", "GB", "RB", 1, "anytime_td", 2.0),
            ("nfl", 2026, "010", "DET-010", "Jahmyr Gibbs", "DET", "GB", "RB", 1, "rush_att", 22.0),
            ("nfl", 2026, "010", "GB-010", "Josh Jacobs", "GB", "DET", "RB", 0, "anytime_td", 0.0)]
    rep = {"home": "DET", "away": "GB", "sections": [{"key": "redzone", "blocks": [{"type": "list", "items": [
        "Jahmyr Gibbs (RB): 52% to score", "Jayden Reed (WR): 28% to score"], "claims": [
        {"kind": "td", "player": "Jahmyr Gibbs", "team": "DET", "pos": "RB", "p": 0.52},
        {"kind": "td", "player": "Jayden Reed", "team": "GB", "pos": "WR", "p": 0.28}]}]}]}
    fin = {"home": "DET", "away": "GB", "date": "2026-11-15", "live": {"state": "final", "away_score": 17, "home_score": 20}}
    summary = G.grade(rep, fin, _conn(rows), "nfl", "2026-W10")
    gibbs, reed = rep["sections"][1]["blocks"][0]["grades"]
    assert (gibbs["status"], gibbs["words"]) == ("hit", "Scored 2."), gibbs
    assert (reed["status"], reed["words"]) == ("miss", "No touchdown."), reed
    assert summary["tds"] == {"n": 2, "scored": 1, "expected": 0.8, "words": (
        "1 of the 2 players we gave one scored; our chances added up to 0.8")}, summary["tds"]
    assert G.summary_lines(summary)[-1] == ("Touchdown chances: 1 of the 2 players we gave one scored; our chances "
                                            "added up to 0.8")
    assert summary["graded"] == 0, "a chance is not a read"


# --- why a read missed, and the standouts -----------------------------------------------------------
def test_a_player_who_sat_is_never_graded_on_a_zero_and_his_minutes_are_said():
    rep, summary = _grade()
    assert _card(rep, "Jaylen Brown")["grade"] == {"stat": "pts", "status": "dnp", "words": "Didn’t play."}, \
        "zero minutes in the NBA's box is a night he sat, not a zero"
    herro = _card(rep, "Tyler Herro")["grade"]
    assert herro["words"] == "Wrong: 9 points; the last 5 games averaged 20. In 21 minutes (usually 34).", herro
    assert herro["vol"] == {"stat": "min", "actual": 21.0, "avg": 34.0, "words": "In 21 minutes (usually 34)."}
    white = _card(rep, "Derrick White")["grade"]
    assert (white["avg"], white["n"]) == (15.0, 4), "the night he sat is no game of his"
    tatum = _card(rep, "Jayson Tatum")["grade"]
    assert "vol" not in tatum, "40 minutes against his 36 is not far off his own"
    assert F.volume_note("nfl", {"pos": "RB"}, {"stats": {"rush_att": 6.0}}, [18.0, 17.0, 19.0])["words"] == \
        "On 6 carries (usually 18)."
    assert F.volume_note("nfl", {"pos": "K"}, {"stats": {}}, []) is None


def test_the_best_calls_and_biggest_misses_lead_the_summary():
    rep, summary = _grade()
    # 22 against 15 (47% over) ahead of 38 against 27 (41% over): as a share of his own number.
    assert summary["best"] == ["Derrick White, a breakout candidate: 22 points; the last 4 games averaged 15.",
                               "Jayson Tatum, a breakout candidate: 38 points; the last 5 games averaged 27."], \
        summary["best"]
    assert summary["worst"][0] == ("Tyler Herro, a breakout candidate: 9 points; the last 5 games averaged 20. In 21 "
                                   "minutes (usually 34)."), summary["worst"]
    # The same standouts as rows, for the game's page (js/detail.js gprRightWrong).
    assert summary["best_rows"][0] == {"player": "Derrick White", "label": "a breakout candidate", "team": "BOS",
                                       "words": "22 points; the last 4 games averaged 15.", "group": "candidates",
                                       "status": "right"}, summary["best_rows"]
    assert [r["player"] for r in summary["worst_rows"]][:1] == ["Tyler Herro"], summary["worst_rows"]
    first = _sec(rep, "graded")
    heads = [b.get("text") for b in first["blocks"] if b.get("type") == "h"]
    assert heads[:2] == ["What we got most right", "What we got most wrong"], heads
    lines = first["blocks"][0]["items"]
    assert lines[:3] == ["Our pick to win: right — the Celtics won 121-96.",
                         "Our team ratings alone (unproven): wrong — they had the Heat (55%), the other side from the "
                         "price.",
                         "The lines: Celtics −6.5, won by 25 (covered); total 227.5, 217 scored (under)."], lines
    total = next(b["text"] for b in first["blocks"] if b.get("type") == "p")
    assert total == "In all, 4 of the report’s 7 graded reads were right.", total
    one = F.standouts([(0.4, "a"), (2.0, "b"), (-1.0, "c"), (-0.2, "d"), None])
    assert one == (["b", "a"], ["c", "d"])
    assert F.standout("units", None, {"status": "right", "actual": 0.58, "avg": 0.52, "words": "Right: BOS shot."},
                      "more")[0] > 0.1, "a rate weighs as a share of its own number"
    # A count near nothing weighs on its own spread (GRADE_VERSION 4): one touchdown against a 0.2 average is
    # no 400% night, and no touchdown against 0.4 no miss as big as a miss can be.
    td = F.standout("matchups", {"player": "A"}, {"status": "right", "stat": "anytime_td", "actual": 1, "avg": 0.2,
                                                  "words": "Right."}, "more")[0]
    blank = F.standout("matchups", {"player": "A"}, {"status": "wrong", "stat": "anytime_td", "actual": 0, "avg": 0.4,
                                                     "words": "Wrong."}, "more")[0]
    yards = F.standout("matchups", {"player": "B"}, {"status": "right", "stat": "rush_yds", "actual": 142, "avg": 88,
                                                     "words": "Right."}, "more")[0]
    assert round(td, 2) == 1.6 and round(blank, 2) == -0.63 and 0.6 < yards < 0.62, (td, blank, yards)
    assert G.GRADE_VERSION == 4, "every final archived before is checked again, once"


# --- the reports write what a finished game checks ------------------------------------------------
def test_the_reports_write_what_a_finished_game_checks():
    from engine import gamereport as R
    from engine import leaguereport as L
    assert R.injury_claim("Tyler Herro", "MIA", "Out", "G") == {"kind": "injury", "player": "Tyler Herro",
                                                                 "team": "MIA", "status": "out", "pos": "G"}
    assert R.injury_claim("Tyler Herro", "MIA", "") is None
    g = {"home": "BOS", "away": "MIA", "date": "2026-11-16", "kickoff": "2026-11-17T00:30:00Z", "spread": -12.5,
         "total": 232.5, "home_ml": -800, "away_ml": 550}
    meta = {"script": {"pace": {"MIA": 101.2, "BOS": 101.9}, "league_pace": 99.1, "pace_rank": {"MIA": 6, "BOS": 3},
                       "teams": 30, "total": 232.5, "league_pts": 112.5, "spread": -3.5},
            "injuries": [{"player": "Tyler Herro", "team": "MIA", "status": "Out"}]}
    board = {"date": "2026-11-16", "games": [g], "scan_reads": {},
             "schedule_spots": [{"home": "BOS", "away": "MIA", "teams": {"home": {"flags": ["blowout"]}, "away": {}}}]}
    L.attach(board, "nba", meta={"MIA@BOS": meta})
    rep = board["game_reports"][0]
    win = _sec(rep, "verdict")["blocks"][0]
    assert win["expect"] == {"spread": -12.5, "total": 232.5}, win
    script = _sec(rep, "script")["blocks"][0]
    assert [c["kind"] for c in script["claims"] if c] == ["pace", "scoring", "close"], script["claims"]
    assert script["claims"][-3]["read"] == "fast" and script["claims"][-2]["read"] == "high"
    # The blowout watch is the short version's to say, with its claim (step AII): the facts no longer repeat it.
    short = next(b for b in _sec(rep, "short")["blocks"] if b.get("type") == "list")
    i = next(i for i, t in enumerate(short["items"]) if t.startswith("Blowout watch"))
    assert short["claims"][i] == {"kind": "blowout"}, short
    facts = _sec(rep, "facts")["blocks"][0]
    assert not any(str(t).startswith("Blowout watch") for t in facts["items"]), facts
    inj = _sec(rep, "injuries")["blocks"][0]
    assert inj["claims"] == [{"kind": "injury", "player": "Tyler Herro", "team": "MIA", "status": "out"}], inj
    assert "claim" in R.PLAIN_SKIP and "expect" in R._NOT_TEXT, "what a final is checked by is never a sentence"
    src = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    assert 'blocks += [_h(f"Who can score for {team_np(c, off)}"), _claimed_list(scorers)]' in src
    assert "_claimed_list(\n                (f\"{r.get('player')} ({r.get('position') or '—'})" in src
    assert 'blocks[0]["sim"] = {k: v for k, v in (' in src and 'para["claim"] = claim' in src
    lsrc = (ROOT / "engine" / "leaguereport.py").read_text(encoding="utf-8")
    assert "injury_claim(i[\"player\"], t, i.get(\"status\"))" in lsrc, "hockey's injury lines carry claims"


# --- every finished game's check, kept in one list --------------------------------------------------
def test_every_graded_final_is_counted_on_the_reports_record():
    from engine import reportarchive as A
    from engine import reportrecord as RR
    where = Path(tempfile.mkdtemp())
    rep, _summary = _grade()
    for day, away, home, rp in (("2026-10-22", "MIA", "BOS", rep), ("2026-10-21", "NYK", "BOS", copy.deepcopy(rep))):
        doc = A.doc_for(rp, dict(FINAL, away=away, home=home, date=day), "nba", day, None, None, {})
        doc["away"] = away
        path = A.path_for(where, "nba", day, away, home)
        assert A.write(path, doc)
    assert RR.refresh(where, "nba") == 2
    idx = json.loads((where / A.DIR / "nba" / RR.INDEX).read_text())
    assert idx["v"] == RR.ROW_VERSION and len(idx["files"]) == 2
    rec = RR.record(where, "nba", today="2026-10-25")
    row = rec["games"][0]
    assert (row["date"], row["game"]) == ("2026-10-22", "MIA@BOS"), row
    assert row["call"] == {"team": "BOS", "right": True, "chance": 0.7} and row["ratings"] == "wrong", row
    assert row["ratings_chance"] == 0.55, row
    assert row["reads"] == [4, 7] and row["groups"]["script"] == [2, 4], row
    assert row["lines"] == {"cover": "BOS", "side": "under"} and row["injuries"] == [1, 3] and row["missed"] == 1, row
    assert row["names"] == {"MIA": "Heat", "BOS": "Celtics"}
    t = rec["totals"]
    assert (t["games"], t["call"], t["reads"], t["ratings"], t["injuries"], t["missed"]) == \
        (2, [2, 2], [8, 14], [0, 2], [2, 6], 2), t
    assert (t["since"], t["through"]) == ("2026-10-21", "2026-10-22") and rec["recent"]["games"] == 2
    # Counts and names only: nothing a member pays for leaves through it. The last slate's line (LASTNIGHT1,
    # reportrecord.last_slate) is counts of what has settled under its own key: numbers and the day, no name.
    slate = rec.get("last_slate") or {}
    assert slate.get("date") == "2026-10-22" and slate.get("games") == 1, slate

    def numbers(v):
        if isinstance(v, dict):
            return all(numbers(x) for x in v.values())
        return all(numbers(x) for x in v) if isinstance(v, list) else isinstance(v, (int, float))
    assert numbers({k: v for k, v in slate.items() if k != "date"}), slate
    flat = json.dumps({k: v for k, v in rec.items() if k != "last_slate"})
    for paid in ("words", "Tyler Herro", "pick", "price", "odds", "items"):
        assert paid not in flat, paid
    # A file read again only when it changed; a file gone is gone from the index.
    before = json.loads((where / A.DIR / "nba" / RR.INDEX).read_text())["files"]
    RR.refresh(where, "nba")
    assert json.loads((where / A.DIR / "nba" / RR.INDEX).read_text())["files"] == before
    A.path_for(where, "nba", "2026-10-21", "NYK", "BOS").unlink()
    assert RR.refresh(where, "nba") == 1 and len(RR.record(where, "nba")["games"]) == 1
    assert RR.record(where, "nhl")["games"] == [] and RR.refresh(where, "nhl") == 0
    # A pending report is no row; nor is a document that is not one.
    pend = copy.deepcopy(rep)
    pend["graded"]["status"] = "pending"
    assert RR.row_of({"report": pend, "away": "MIA", "home": "BOS"}) is None and RR.row_of({}) is None
    # The archive's save keeps the index (engine/reportarchive.save).
    asrc = (ROOT / "engine" / "reportarchive.py").read_text(encoding="utf-8")
    assert "reportrecord.refresh(where, sport)" in asrc
    with gzip.open(A.path_for(where, "nba", "2026-10-22", "MIA", "BOS")) as fh:
        assert json.load(fh)["report"]["graded"]["version"] == G.GRADE_VERSION


def test_how_sure_we_were_and_how_often_it_held():
    """Each tenth of a chance, how often the side we gave it won: the call's
    chance and our ratings' own (a side given 70% should win about seven in ten)."""
    from engine import reportrecord as RR
    assert [RR.band_of(x) for x in (0.5, 0.64, 0.7, 0.999, 1.0, 0.49, None)] == [50, 60, 70, 90, 90, None, None]
    rows = [{"call": {"team": "BOS", "right": True, "chance": 0.72}, "ratings": "wrong", "ratings_chance": 0.55},
            {"call": {"team": "NYK", "right": False, "chance": 0.75}},
            {"call": {"team": "LAL", "right": True, "chance": 0.58}, "ratings": "right", "ratings_chance": 0.61},
            {"call": {"team": "DEN", "right": True}}]
    t = RR.totals(rows)
    assert t["calibration"] == {"call": {"70": [1, 2], "50": [1, 1]}, "ratings": {"50": [0, 1], "60": [1, 1]}}, t
    assert t["call"] == [3, 4], "a call with no chance still counts as a call"
    assert RR.ROW_VERSION == 2, "every row read again once, with its chances"
    rp = (ROOT / "web" / "js" / "reportpicks.js").read_text(encoding="utf-8")
    assert "function rpCalibHTML(c)" in rp and "${rpCalibHTML(t.calibration)}" in rp
    assert "How sure we were, and how often it held" in rp


def test_the_record_is_served_free_and_every_page_draws_the_checks():
    srv = (ROOT / "server.py").read_text(encoding="utf-8")
    assert 'if parsed.path in ("/api/report_record", "/api/report_record/"):' in srv
    i = srv.index("def _report_record(self, q):")
    body = srv[i:srv.index("def _record_day(self, q):")]
    assert "reportrecord.record(gate.FULL_DIR, league)" in body and "_entitled" not in body, "free, as the Record is"
    assert 'self._rate_limited(RATE_GAME_PER_MIN, "report_record")' in body
    rp = (ROOT / "web" / "js" / "reportpicks.js").read_text(encoding="utf-8")
    for want in ("function rpFactsHTML(league)", "async function rpFactsFill(host, league)", "function rpFactRowHTML(r)",
                 "async function rpArchiveOpen(body, btn)", "fetch(`/api/report_record?league=${encodeURIComponent(sport)}`",
                 "fetch(`/api/report_archive?${q}`", 'How our reports did <span class="sub">— every finished game, fact-checked</span>'):
        assert want in rp, want
    assert rp.count("rpFactsHTML()") == 1 and '["facts", "How our reports did",' in rp, \
        "one tab draws it, whatever the board holds"
    css = (ROOT / "web" / "css" / "reportpicks.css").read_text(encoding="utf-8")
    for cls in (".rpk-fact-tile", ".rpk-fact-chip.won", ".rpk-fact-chip.lost", ".rpk-fact-row"):
        assert cls in css, cls
    for lit in ('"rpk-fact-chip won"', '"rpk-fact-chip lost"', '"rpk-fact-chip"'):
        assert lit in rp, f"the class written whole: {lit}"
    detail = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
    for want in ("gprLinesRow(graded.score)", "gprInjuryRow(graded.injuries)", "gprTdRow(graded.tds)",
                 "(graded.best_rows || graded.best || [])", "(graded.worst_rows || graded.worst || [])",
                 'data-rpk-facts-go="1">How every finished game’s report did</a>', "window._rpWantFacts = true"):
        assert want in detail, want
    js = (ROOT / "web" / "js" / "report.js").read_text(encoding="utf-8")
    assert "${gradeLine(b.grade)}</p>`" in js, "a paragraph's own check under it"
    assert "function winnerLinesHTML(b)" in js and "${winnerLinesHTML(b)}" in js
    assert 'gr.status === "right" || gr.status === "hit" ? "gr-graded won"' in js
    assert ".gr-res-lines" in (ROOT / "web" / "css" / "report.css").read_text(encoding="utf-8")


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
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
