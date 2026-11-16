"""A finished game keeps its parlays and picks, and its report says what it got right.

Ethan, 2026-11-16, with a finished Pacers at 76ers page and a live NFL report
with no Parlays or picks section: "I want the parlay tab to still be there after
the game, and people can go back and see if the parlays for the game we
recommended hit or not, and if the picks hit or not, and if the game report was
correct or not. We should be able to tell after the game on this screen if the
matchups that we reported were good or not, or if someone was like a breakout
target or a favorable candidate, we should report on if they actually did good
or not ... In all of our offense and defense matchup, we should report on if we
were correct on that or not too."

engine/reportgrade reads a finished game's report against its box score: each
player's read on the stat it leans on against his own average before the game,
each offense-against-defense claim the report wrote beside its lines against
the team's own number, and a first section, "How this report did".
engine/reportkeep keeps each game's tickets and picks beside its report and
puts them back once the game has started (the parlay journal never writes a
kept ticket); the game's page draws them (js/detail.js keptPicksFor).

    python3 tests/test_a_finished_report_says_what_it_got_right.py
"""
import copy
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gate                                              # noqa: E402
from engine import reportgrade as G                                  # noqa: E402
from engine import reportkeep as K                                   # noqa: E402

LOG = ("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, position, home, "
       "market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)")


def _conn(rows):
    from engine import db as D
    conn = D.connect(Path(tempfile.mkdtemp()) / "history.db")
    conn.executemany(LOG, rows)
    conn.commit()
    return conn


def _nba_rows(tonight=True):
    rows = []

    def add(day, player, team, opp, **st):
        for m, v in st.items():
            rows.append(("nba", 2026, day, f"MIA@BOS-{day}", player, team, opp, "", int(team == "BOS"), m, v))
    for day, (t, h, w, b) in {"2026-10-18": (25, 20, 30, 70), "2026-10-20": (27, 22, 28, 72)}.items():
        add(day, "Jayson Tatum", "BOS", "MIA", pts=t, fg3m=3)
        add(day, "Tyler Herro", "MIA", "BOS", pts=h, fg3m=2)
        add(day, "Jaylen Brown", "BOS", "MIA", pts=w, fg3m=2)
        add(day, "Bam Adebayo", "MIA", "BOS", pts=b, fg3m=0)
    if tonight:
        add("2026-10-22", "Jayson Tatum", "BOS", "MIA", pts=31, fg3m=5)
        add("2026-10-22", "Derrick White", "BOS", "MIA", pts=90, fg3m=10)
        add("2026-10-22", "Tyler Herro", "MIA", "BOS", pts=24, fg3m=2)
        add("2026-10-22", "Bam Adebayo", "MIA", "BOS", pts=80, fg3m=1)
    return rows


def _nba_report():
    return {"game": "MIA@BOS", "away": "MIA", "home": "BOS", "date": "2026-10-22", "sport": "nba", "sections": [
        {"key": "verdict", "title": "Who we think wins", "blocks": [{"type": "winner", "team": "BOS",
                                                                     "name": "Celtics", "chance": 0.7}]},
        {"key": "watch", "title": "Players to watch", "blocks": [{"type": "verdicts", "items": [
            {"player": "Jayson Tatum", "title": "Jayson Tatum", "team": "BOS", "pos": "F", "verdict": "up",
             "label": "BREAKOUT", "why": ["Miami gives up the second-most points to forwards."], "lean": ["pts", "pra"]},
            {"player": "Jaylen Brown", "title": "Jaylen Brown", "team": "BOS", "pos": "G", "verdict": "up",
             "label": "FAVORABLE", "why": ["His minutes are up with Holiday out."], "lean": ["pts"]},
            {"player": "Tyler Herro", "title": "Tyler Herro", "team": "MIA", "pos": "G", "verdict": "down",
             "label": "FADE", "why": ["Boston holds guards to the fourth-fewest points."], "lean": ["pts"]}]}]},
        {"key": "defense", "title": "Where each defense gives", "blocks": [{"type": "list", "items": [
            "MIA's defense gives up the second-most points (118.2 a game)."], "claims": [
            {"kind": "allowed", "team": "MIA", "opp": "BOS", "checks": [{"stat": "pts", "pg": 118.2, "side": "soft"}]}]}]},
        {"key": "tape", "title": "The matchup", "blocks": [{"type": "list", "items": [
            "Edge BOS: BOS's three-point shooting (2nd) against MIA's perimeter defense (28th).", "Pace is even."],
            "claims": [{"kind": "unit", "off": "BOS", "def": "MIA", "unit": "fg3m", "base": 12.0, "favors": "more"},
                       None]}]}]}


FINAL = {"away": "MIA", "home": "BOS", "date": "2026-10-22",
         "live": {"state": "final", "away_score": 104, "home_score": 121}}


def _items(rep, key):
    sec = next(s for s in rep["sections"] if s["key"] == key)
    return [it for b in sec["blocks"] for it in b.get("items") or [] if isinstance(it, dict)]


def test_each_player_read_is_graded_on_its_stat_against_his_own_average():
    rep = _nba_report()
    summary = G.grade(rep, FINAL, _conn(_nba_rows()), "nba", "2026-10-22")
    tatum, brown, herro = _items(rep, "watch")
    assert tatum["grade"]["status"] == "right" and tatum["grade"]["stat"] == "pts", tatum["grade"]
    assert (tatum["grade"]["actual"], tatum["grade"]["avg"], tatum["grade"]["n"]) == (31.0, 26.0, 2)
    assert tatum["grade"]["words"] == "Right: 31 points, above his 26 average over his last 2 games."
    assert brown["grade"] == {"stat": "pts", "status": "dnp", "words": "Didn’t play."}, "his club's box, not his"
    assert herro["grade"]["status"] == "wrong", "a fade who beat his average was a wrong read"
    assert herro["grade"]["words"] == "Wrong: 24 points, above his 21 average over his last 2 games."
    groups = {x["key"]: x for x in summary["groups"]}
    assert (groups["candidates"]["right"], groups["candidates"]["graded"], groups["candidates"]["dnp"]) == (1, 1, 1)
    assert (groups["fades"]["right"], groups["fades"]["graded"]) == (0, 1)


def test_every_offense_against_defense_claim_is_graded_on_the_night():
    rep = _nba_report()
    G.grade(rep, FINAL, _conn(_nba_rows()), "nba", "2026-10-22")
    d = next(b for s in rep["sections"] if s["key"] == "defense" for b in s["blocks"])
    assert d["grades"][0]["status"] == "right", d["grades"]
    assert d["grades"][0]["words"] == "Right: MIA gave up 121 points (it allows 118.2 a game) to BOS."
    t = next(b for s in rep["sections"] if s["key"] == "tape" for b in s["blocks"])
    assert t["grades"][1] is None, "a line that claims nothing is not graded"
    assert t["grades"][0]["words"] == "Right: BOS made 15 threes against MIA (averages 12).", t["grades"][0]
    # The night's unit is the season's own arithmetic, one night of it (engine/nba/teams).
    from engine.nba import teams as T
    one = T.season_profiles({("BOS", "d"): {"opp": "MIA", "pts": 100.0, "fg3m": 12.0}, ("MIA", "d"): {"opp": "BOS", "pts": 90.0}},
                            min_games=1)
    assert one["BOS"]["fg3m"] == 12.0 and one["BOS"]["margin"] == 10.0
    assert T.season_profiles({("BOS", "d"): {"opp": "MIA", "pts": 1.0}, ("MIA", "d"): {"opp": "BOS"}})["BOS"] == \
        {"games": 1}, "a season still needs its MIN_GAMES"


def test_the_report_opens_on_how_it_did_and_the_call():
    rep = _nba_report()
    summary = G.grade(rep, FINAL, _conn(_nba_rows()), "nba", "2026-10-22")
    first = rep["sections"][0]
    assert first["key"] == "graded" and first["title"] == "How this report did"
    lines = first["blocks"][0]["items"]
    assert lines[0] == "Who we think wins: right — Celtics, our call, won 121-104.", lines
    lost = G.call_line(_nba_report(), dict(FINAL, live={"state": "final", "away_score": 110, "home_score": 99}))
    assert lost["words"] == "wrong — our call was Celtics; MIA won 110-99", lost
    assert "Breakout candidates: 1 of 1 beat their average; 1 didn’t play." in lines, lines
    assert "Fades: 0 of 1 fell short of it." in lines and "Offense against defense: 2 of 2 right." in lines
    assert first["blocks"][1]["text"] == "In all, 3 of the report’s 4 graded reads were right."
    assert (summary["right"], summary["graded"], summary["status"]) == (3, 4, "graded")
    assert rep["graded"] is summary
    G.grade(rep, FINAL, _conn(_nba_rows()), "nba", "2026-10-22")
    assert [s["key"] for s in rep["sections"]].count("graded") == 1, "graded again, never doubled"


def test_before_the_box_score_every_read_waits_and_before_the_final_nothing_is_graded():
    rep = _nba_report()
    summary = G.grade(rep, FINAL, _conn(_nba_rows(tonight=False)), "nba", "2026-10-22")
    assert summary["status"] == "pending"
    assert all(it["grade"]["status"] == "pending" for it in _items(rep, "watch"))
    assert rep["sections"][0]["blocks"][0]["text"].startswith("The box score is not in yet")
    live = dict(FINAL, live={"state": "live"})
    fresh = _nba_report()
    assert G.grade(fresh, live, _conn(_nba_rows()), "nba", "2026-10-22") is None
    assert "graded" not in fresh and fresh["sections"][0]["key"] == "verdict"
    assert G.grade(fresh, FINAL, None, "nba", "2026-10-22")["status"] == "pending", "no history file: waits"


def test_football_reads_the_week_the_run_game_and_the_angles():
    rows = []
    for wk, (a, b, ctc) in {"008": (100, 20, 60), "009": (90, 30, 70), "010": (130, 20, 98)}.items():
        rows += [("nfl", 2026, wk, f"2026_{wk}", "Saquon Barkley", "PHI", "IND", "RB", 1, "rush_yds", a),
                 ("nfl", 2026, wk, f"2026_{wk}", "Jalen Hurts", "PHI", "IND", "QB", 1, "rush_yds", b),
                 ("nfl", 2026, wk, f"2026_{wk}", "A. J. Brown", "PHI", "IND", "WR", 1, "rec_yds", ctc),
                 ("nfl", 2026, wk, f"2026_{wk}", "Michael Pittman", "IND", "PHI", "WR", 0, "rec_yds", 50)]
    rep = {"game": "IND@PHI", "away": "IND", "home": "PHI", "date": "2026-11-15", "sport": "nfl", "sections": [
        {"key": "matchups", "title": "Who's guarding who", "blocks": [{"type": "verdicts", "items": [
            {"player": "A. J. Brown", "team": "PHI", "pos": "WR", "verdict": "favorable", "lean": ["rec_yds"]},
            {"player": "Michael Pittman", "team": "IND", "pos": "WR", "verdict": "neutral"}]}]},
        {"key": "trenches", "title": "In the trenches", "blocks": [{"type": "list", "items": [
            "PHI's pass protection ranks 3rd against IND's pass rush (20th) — edge PHI.",
            "PHI's run game ranks 2nd against IND's run defense (29th) — edge PHI."],
            "claims": [None, {"kind": "team", "team": "PHI", "opp": "IND", "stat": "rush_yds", "favors": "more"}]}]},
        {"key": "angles", "title": "The angles", "blocks": [{"type": "list", "items": ["Brown against the WR1 funnel."],
            "claims": [{"kind": "player", "player": "A. J. Brown", "team": "PHI", "pos": "WR", "stat": "rec_yds",
                        "favors": "more"}]}]}]}
    g = {"away": "IND", "home": "PHI", "date": "2026-11-15", "live": {"state": "final", "away_score": 17, "home_score": 27}}
    summary = G.grade(rep, g, _conn(rows), "nfl", "2026-W10")
    brown, pittman = _items(rep, "matchups")
    assert brown["grade"]["words"] == "Right: 98 receiving yards, above his 65 average over his last 2 games."
    assert "grade" not in pittman, "a neutral read claims nothing"
    tr = next(b for s in rep["sections"] if s["key"] == "trenches" for b in s["blocks"])
    assert tr["grades"][0] is None, "no sacks are stored: the pass rush's edge is not graded"
    assert tr["grades"][1]["words"] == "Right: PHI had 150 rushing yards (averages 120 over its last 2 games).", tr
    an = next(b for s in rep["sections"] if s["key"] == "angles" for b in s["blocks"])
    assert an["grades"][0]["status"] == "right"
    groups = {x["key"]: (x["right"], x["graded"]) for x in summary["groups"]}
    assert groups == {"matchups": (1, 1), "angles": (1, 1), "units": (1, 1)}, groups


def test_hockey_reads_the_shots_against_the_number_coming_in():
    rows = [("nhl", 2026, "2026-10-21", "BOS@TOR", p, "TOR", "BOS", "", 1, "sog", v)
            for p, v in (("Auston Matthews", 6), ("Mitch Marner", 4), ("William Nylander", 3))]
    rows.append(("nhl", 2026, "2026-10-21", "BOS@TOR", "David Pastrnak", "BOS", "TOR", "", 0, "sog", 5))
    rep = {"game": "BOS@TOR", "away": "BOS", "home": "TOR", "date": "2026-10-21", "sport": "nhl", "sections": [
        {"key": "tape", "title": "The matchup", "blocks": [{"type": "list", "items": ["TOR shoots the most."],
            "claims": [{"kind": "team", "team": "TOR", "opp": "BOS", "stat": "sog", "favors": "more", "base": 31.5}]}]}]}
    g = {"away": "BOS", "home": "TOR", "date": "2026-10-21", "live": {"state": "final", "away_score": 2, "home_score": 4}}
    G.grade(rep, g, _conn(rows), "nhl", "2026-10-21")
    gr = rep["sections"][1]["blocks"][0]["grades"][0]
    assert gr["words"] == "Wrong: TOR had 13 shots on goal (averages 31.5 a game).", gr


def test_the_reports_write_the_claims_a_finished_game_is_graded_by():
    gr = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    lr = (ROOT / "engine" / "leaguereport.py").read_text(encoding="utf-8")
    assert '{"kind": "team", "team": off, "opp": dfn, "stat": "rush_yds",' in gr
    assert '**({"lean": list(r.get("lean") or [])} if r.get("lean") else {}),' in gr
    assert '"kind": "player", "player": r.get("player")' in gr, "the angles"
    assert '{"kind": "allowed", "team": t, "opp": c.opp[t], "checks": soft_checks}' in lr
    assert '{"kind": "team", "team": t, "opp": c.opp[t], "stat": "sog", "favors": "more",' in lr
    assert "def _unit_claim(e: dict)" in lr and 'out["lean"] = list(r["lean"])' in lr
    br = (ROOT / "engine" / "breakouts.py").read_text(encoding="utf-8")
    assert 'out["lean"] = list(r["lean"])' in br
    # A key matchup carries what grades it: the offense, its unit and its own number.
    from engine.nba import scan as S
    prof = {"n": 30, "teams": {"BOS": {"ranks": {"fg3m": 2}, "fg3m": 16.2}, "MIA": {"ranks": {"opp_fg3m": 29}}}}
    edges = [e for e in S.key_matchups("BOS", "MIA", prof) if e.get("unit") == "fg3m"]
    assert edges and (edges[0]["off"], edges[0]["def"], edges[0]["off_unit"], edges[0]["base"]) == ("BOS", "MIA", "fg3m", 16.2)
    from engine.leaguereport import _unit_claim
    assert _unit_claim(edges[0]) == {"kind": "unit", "off": "BOS", "def": "MIA", "unit": "fg3m", "base": 16.2,
                                     "favors": "more"}
    assert _unit_claim(dict(edges[0], tone="def", off_unit="tov"))["favors"] == "more", \
        "a defense's edge in turnovers is more of them"
    # The claims are codes, never a sentence the plain-words pass rewrites.
    from engine import gamereport as R
    assert {"lean", "claims", "grade", "grades"} <= R.PLAIN_SKIP and {"lean", "claims"} <= R._NOT_TEXT
    blk = R._claimed_list([("One line", {"kind": "team"}), ("", {"kind": "lost with its line"}), ("Two", None)])
    assert blk == {"type": "list", "items": ["One line.", "Two."], "claims": [{"kind": "team"}, None]}


def _board(rows=True, state=None):
    board, meta = __import__("test_a_started_game_keeps_its_report")._board(rows=rows, state=state)
    board["recommendations"] = ([{"player": "Jayson Tatum", "team": "BOS", "opponent": "MIA", "market": "pts",
                                  "recommended": True, "odds": -110}] if rows else [])
    ticket = {"legs": [{"player": "Jayson Tatum", "team": "BOS", "market": "pts", "side": "over", "line": 24.5,
                        "odds": -135, "p": 0.63, "book": "DraftKings"},
                       {"player": "Bam Adebayo", "team": "MIA", "market": "reb", "side": "over", "line": 9.5,
                        "odds": -120, "p": 0.58, "book": "DraftKings"}],
              "joint": 0.38, "independent": 0.365, "fair": 2.63, "fair_words": "+163", "take": 2.76,
              "take_words": "+176", "take_dec": 2.76, "naive_dec": 3.06}
    board["game_parlays"] = {"games": ([{"away": "MIA", "home": "BOS", "game": "MIA@BOS", "threes": [ticket],
                                          "scorers": []}] if rows else [])}
    return board, meta


def test_a_started_game_keeps_its_tickets_and_picks_and_they_are_never_journaled_again():
    from engine import leaguereport as L
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "web", "data"))
    out = os.path.join(d, "web", "data", "nba.json")
    board, meta = _board()
    L.attach(board, "nba", meta=meta, out=out, at="2026-10-22T10:00:00")
    rec = json.load(open(K.path_for("nba", gate._full_dir_for(out))))["games"]["MIA@BOS|2026-10-22"]
    assert rec["parlays"]["threes"][0]["legs"][0]["player"] == "Jayson Tatum"
    assert [r["player"] for r in rec["picks"]["likely"]] == ["Jayson Tatum"] and rec["picks"]["edge"]
    live, meta2 = _board(rows=False, state="live")
    L.attach(live, "nba", meta=meta2, out=out, at="2026-10-22T20:10:00")
    back = live["game_parlays"]["games"]
    assert len(back) == 1 and back[0]["kept"] == "Thu 10:00 AM ET", back
    assert live[K.KEPT_PICKS]["MIA@BOS"]["likely"][0]["player"] == "Jayson Tatum"
    assert K.KEPT_PICKS in gate.PAID_KEYS
    from engine import parlayledger as PL
    import sqlite3
    conn = sqlite3.connect(":memory:")
    assert PL.log_game_parlays(conn, live["game_parlays"], "nba", "2026-10-22") == 0, "a kept ticket is never journaled"
    fresh, _m = _board()
    assert PL.log_game_parlays(conn, fresh["game_parlays"], "nba", "2026-10-22") == 1


def test_a_finished_game_is_graded_in_the_build_with_the_history_file():
    from engine import db as D
    from engine import leaguereport as L
    path = Path(tempfile.mkdtemp()) / "history.db"
    conn = D.connect(path)
    conn.executemany(LOG, _nba_rows())
    conn.commit()
    conn.close()
    orig = D.connect
    D.connect = lambda *a, **k: orig(path)
    try:
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "web", "data"))
        out = os.path.join(d, "web", "data", "nba.json")
        board, meta = _board()
        L.attach(board, "nba", meta=meta, out=out, at="2026-10-22T10:00:00")
        over, meta2 = _board(rows=False, state="final")
        line = L.attach(over, "nba", meta=meta2, out=out, at="2026-10-23T01:30:00")
    finally:
        D.connect = orig
    rep = over["game_reports"][0]
    assert "; 1 finished report graded" in line, line
    assert rep["sections"][0]["key"] == "graded" and rep["graded"]["status"] == "graded", rep.get("graded")


def test_a_graded_final_is_kept_for_good_and_read_back():
    """Ethan: "people should be able to go back and still look at this data and
    see if we were right or not" (engine/reportarchive)."""
    from engine import db as D
    from engine import leaguereport as L
    from engine import reportarchive as A
    path = Path(tempfile.mkdtemp()) / "history.db"
    conn = D.connect(path)
    conn.executemany(LOG, _nba_rows())
    conn.commit()
    conn.close()
    orig = D.connect
    D.connect = lambda *a, **k: orig(path)
    try:
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "web", "data"))
        out = os.path.join(d, "web", "data", "nba.json")
        board, meta = _board()
        L.attach(board, "nba", meta=meta, out=out, at="2026-10-22T10:00:00")
        over, meta2 = _board(rows=False, state="final")
        line = L.attach(over, "nba", meta=meta2, out=out, at="2026-10-23T01:30:00")
        again, meta3 = _board(rows=False, state="final")
        line2 = L.attach(again, "nba", meta=meta3, out=out, at="2026-10-23T01:35:00")
    finally:
        D.connect = orig
    assert "; 1 finished report archived" in line, line
    assert "archived" not in line2, "nothing changed: not written again"
    # GRADED ONCE: the build after reads the graded final back, its box never queried again.
    from engine import reportgrade as RG
    calls = []
    real = RG._grade
    RG._grade = lambda *a, **k: calls.append(1) or real(*a, **k)
    D.connect = lambda *a, **k: orig(path)
    try:
        third, meta4 = _board(rows=False, state="final")
        line3 = L.attach(third, "nba", meta=meta4, out=out, at="2026-10-23T01:40:00")
    finally:
        RG._grade = real
        D.connect = orig
    assert calls == [] and "; 1 finished report graded" in line3, (calls, line3)
    assert third["game_reports"][0]["sections"][0]["key"] == "graded"
    assert [b["player"] for b in third.get("report_bets") or []] == ["Jayson Tatum"], "its bets still reach the board"
    # A new grading version grades an archived final again, once.
    RG.GRADE_VERSION += 1
    calls.clear()
    RG._grade = lambda *a, **k: calls.append(1) or real(*a, **k)
    D.connect = lambda *a, **k: orig(path)
    try:
        fourth, meta5 = _board(rows=False, state="final")
        L.attach(fourth, "nba", meta=meta5, out=out, at="2026-10-23T01:45:00")
    finally:
        RG._grade = real
        RG.GRADE_VERSION -= 1
        D.connect = orig
    assert calls == [1], calls
    where = gate._full_dir_for(out)
    f = A.path_for(where, "nba", "2026-10-22", "MIA", "BOS")
    assert f.exists() and str(f).startswith(os.path.join(d, "data", "built")), f
    assert not str(f).startswith(os.path.join(d, "web")), "the graded report is paid: never the public tree"
    doc = A.load("nba", "2026-10-22", "MIA", "BOS", where=where)
    assert doc["report"]["sections"][0]["key"] == "graded" and doc["final"] == {"away": 99, "home": 112}
    assert doc["parlays"]["threes"][0]["legs"][0]["player"] == "Jayson Tatum"
    assert doc["picks"]["likely"][0]["player"] == "Jayson Tatum"
    assert "_bets" not in doc["report"]


def test_the_archive_keeps_this_games_verdicts_and_refuses_a_name_that_is_not_one():
    from engine import reportarchive as A
    rep = {"away": "MIA", "home": "BOS", "sections": [{"key": "card", "blocks": [{"type": "picks", "items": [
        {"player": "Jayson Tatum", "bet": {"player": "Jayson Tatum", "market": "pts"}}]}]}]}
    doc = A.doc_for(rep, FINAL, "nba", "2026-10-22", None, {"edge": [{"player": "Bam Adebayo", "market": "reb"}]},
                    {"jaysontatum|pts": {"a": 31}, "bamadebayo|reb": {"a": 12}, "someoneelse|pts": {"a": 9}})
    assert doc["results"] == {"jaysontatum|pts": {"a": 31}, "bamadebayo|reb": {"a": 12}}, doc["results"]
    for bad in (("nba", "2026-10-22", "../x", "BOS"), ("nba", "22-10-2026", "MIA", "BOS"), ("NBA!", "2026-10-22", "A", "B")):
        assert A.path_for("/tmp", *bad) is None, bad
    assert A.path_for("/tmp", "cbb", "2026-11-16", "espn:2390", "DUKE").name == "espn-2390@DUKE.json.gz"
    assert A.load("nba", "2026-10-22", "..", "BOS", where="/tmp") is None


def test_an_old_games_page_draws_it_for_a_member():
    srv = (ROOT / "server.py").read_text(encoding="utf-8")
    assert 'if parsed.path in ("/api/report_archive", "/api/report_archive/"):' in srv
    body = srv[srv.index("def _report_archive(self, q):"):srv.index("def _record_day(self, q):")]
    assert "self._entitled(conn, self._account(conn))" in body and "402" in body, "the graded report is paid"
    assert "reportarchive.load(" in body
    detail = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
    assert "async function pbpOurReportFill(league, d)" in detail
    assert 'hero.insertAdjacentHTML("afterend", `<div id="pbp-our-report"></div>`)' in detail
    assert "results: reportResults(g, doc.results || {})" in detail and "embedded: true" in detail
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert "function reportResults(g, map)" in app and "pickResult(bet, g, map)" in app
    js = (ROOT / "web" / "js" / "report.js").read_text(encoding="utf-8")
    assert "const solo = fight || !!(extras && extras.embedded);" in js
    # A started game's tickets say how they went, and offer nothing to bet.
    assert "(t.bet_legs || []).length && !CLOSED" in js and "CLOSED = !!(r.kept || RESULTS);" in js
    assert "CLOSED = !!((g && g.kept) || RESULTS);" in js
    from engine import gameparlays as GP
    assert GP.journal_rows({"games": [{"kept": "Thu 7:02 PM ET", "threes": [{"legs": [{"player": "A", "market": "pts"}]}]}]}) == []


def test_the_page_draws_the_grades_the_kept_picks_and_how_the_report_did():
    js = (ROOT / "web" / "js" / "report.js").read_text(encoding="utf-8")
    assert "function gradeLine(gr)" in js and "${gradeLine(v.grade)}" in js
    assert "gradeLine((b.grades || [])[i])" in js, "each list line its own grade"
    assert 'const OPEN_SECTIONS = ["graded", "card", "short"];' in js
    css = (ROOT / "web" / "css" / "report.css").read_text(encoding="utf-8")
    assert ".gr-graded.won" in css and ".gr-graded.lost" in css
    detail = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
    assert "function keptPicksFor(g)" in detail and "function obRowsFor(g)" in detail
    for want in ("(kept.edge || [])", "(kept.bets || [])", "(kept.shots || []).slice()", "(kept.shelf || [])"):
        assert want in detail, want
    assert "<b>The report’s reads:</b>" in detail, "the Final card says how the report did"


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
