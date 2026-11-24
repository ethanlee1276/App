"""WHO STEPS UP: when a team's receivers or backs are ruled out, the report says where their work went, our picks
carry the step they were priced with, and both are measured (step AEC).

Ethan, 24 November 2026: "the LA Rams receiver room is basically empty. Puka and Adams is out so now it's all their
other receivers and tight ends too step up so we need too gather data on who steps up in these situations ... make
sure it's in the bets and reports and measured with bets".

  * engine/stepup.for_team: the vacated share, the team's own games without them (who took the targets, against
    what each had with them), the board's measured lift on the picks it raised, the tight-end note (said, not
    priced), and a graded read on each teammate named, only where a step up was measured;
  * engine/reportgrade: those reads are their own group, "Who steps up", on the report and the Record;
  * engine/ledger._stamp_team: a journaled pick keeps the teammate step it was priced with (`bets.mate_mult`), and
    engine/stepup.bet_record says how those picks have done, by league and book (the Record page's section).

Offline. Run directly: `python3 tests/test_who_steps_up_when_receivers_sit.py`
"""
import os
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import reportgrade as G                                  # noqa: E402
from engine import stepup as S                                       # noqa: E402

LOG = ("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, position, home, "
       "market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)")


def _conn(rows):
    from engine import db as D
    conn = D.connect(Path(tempfile.mkdtemp()) / "history.db")
    conn.executemany(LOG, rows)
    conn.commit()
    return conn


def _line(wk, player, pos, targets=0.0, carries=0.0, rec_yds=0.0, rush_yds=0.0, team="LA", opp="SF", box=False):
    gid = f"{team}-{wk:03d}" + ("-box" if box else "")
    return [("nfl", 2026, f"{wk:03d}", gid, player, team, opp, pos, 1, m, float(v))
            for m, v in (("targets", targets), ("carries", carries), ("rec_yds", rec_yds), ("rush_yds", rush_yds))]


def _rams(puka_out=(6, 7), adams_out=(7, 9), weeks=11):
    """The Rams' first eleven weeks: Nacua and Adams the top two, the work going to Atwell and the tight end in the
    games they missed. Week 11 from the same-night box score, as the newest week is before nflverse's file lands."""
    rows = []
    for wk in range(1, weeks + 1):
        puka, adams = wk not in puka_out, wk not in adams_out
        both_out = not (puka or adams)
        box = wk == weeks
        if puka:
            rows += _line(wk, "Puka Nacua", "WR", 10, rec_yds=95)
        if adams:
            rows += _line(wk, "Davante Adams", "WR", 9, rec_yds=80)
        rows += _line(wk, "Tutu Atwell", "WR", 4 + 3 * (not puka) + 2 * (not adams), rec_yds=40 + 30 * both_out, box=box)
        rows += _line(wk, "Colby Parkinson", "TE", 3 + 3 * both_out + (not puka), rec_yds=30, box=box)
        rows += _line(wk, "Kyren Williams", "RB", 3, 18, 20, 80, box=box)
        rows += _line(wk, "Blake Corum", "RB", 1, 6, 5, 25, box=box)
        if wk <= 5:
            rows += _line(wk, "Gone Receiver", "WR", 3, rec_yds=20)       # cut after week 5: never named
    return rows


ROWS = [{"player": "Tutu Atwell", "team": "LA", "market": "receptions",
         "mate_card": {"out": ["Puka Nacua", "Davante Adams"], "case": "above_new", "applied": 1.19}},
        {"player": "Tutu Atwell", "team": "LA", "market": "rec_yds",
         "mate_card": {"out": ["Puka Nacua"], "case": "above_new", "applied": 1.12}},
        {"player": "Kyren Williams", "team": "LA", "market": "rush_yds", "mate_card": None}]
OUT = [("Puka Nacua", "WR", "OUT"), ("Davante Adams", "WR", "OUT")]


def _texts(got):
    return [t for t, _cl in got["lines"]]


def test_the_report_names_who_took_the_targets_in_the_games_without_them():
    got = S.for_team(_conn(_rams()), 2026, 12, "LA", "Rams", OUT, ROWS)
    t = _texts(got)
    assert t[0] == ("Rams without Puka Nacua (WR, 32% of the targets) and Davante Adams (WR, 29% of the targets): "
                    "61% of the targets this season to fill"), t[0]
    assert t[1] == ("In the only game this season without them (week 7), the targets went to: Tutu Atwell (WR) 9 "
                    "(4 a game with them), 70 yards; Colby Parkinson (TE) 7 (3 a game with them), 30 yards; Kyren "
                    "Williams (RB) 3 (3 a game with them), 20 yards"), t[1]
    assert "Gone Receiver" not in " ".join(t), "a man not with the team lately is never named"
    assert ("Our numbers raise Tutu Atwell's receiving yards ×1.12 and catches ×1.19, the lift measured over four "
            "seasons for a player whose teammate ahead of him at his position is out, in every number we price on "
            "him") in t
    assert any(x.startswith("When a third or more of a team's targets sat, over four seasons a tight end caught 12% "
                            "more than his own form") for x in t), "61% gone: the tight end's measured note"
    assert got["vacated"] == {"targets": 0.614} and got["outs"] == ["Puka Nacua", "Davante Adams"]


def test_a_step_up_is_claimed_only_where_one_was_measured():
    got = S.for_team(_conn(_rams()), 2026, 12, "LA", "Rams", OUT, ROWS)
    claims = [cl for _t, cl in got["lines"] if cl]
    assert [(c["player"], c["pos"], c["stat"], c["favors"], c["group"]) for c in claims] == [
        ("Tutu Atwell", "WR", "targets", "more", "stepup"), ("Colby Parkinson", "TE", "targets", "more", "stepup")]
    # The back is named taking targets, never claimed: over four seasons backs got no more when receivers sat.
    assert not any(c["player"] == "Kyren Williams" for c in claims)
    # One receiver out at under a third of the targets: the tight end is not claimed (his lift was measured past it).
    one = S.for_team(_conn(_rams(adams_out=(7,))), 2026, 12, "LA", "Rams", [("Davante Adams", "WR", "OUT")], ROWS)
    assert [cl["player"] for _t, cl in one["lines"] if cl] == ["Tutu Atwell"], one["lines"]
    assert not any("tight end caught" in t for t in _texts(one))


def test_never_out_together_reads_the_games_without_the_biggest_one():
    got = S.for_team(_conn(_rams(puka_out=(6,), adams_out=(9,))), 2026, 12, "LA", "Rams", OUT, ROWS)
    assert _texts(got)[1].startswith("In the only game this season without Puka Nacua (week 6), the targets went to: "
                                     "Tutu Atwell (WR) 7 (4.2 a game with Puka Nacua), 40 yards"), _texts(got)[1]


def test_a_back_out_leaves_his_carries_and_not_a_line_of_targets():
    got = S.for_team(_conn(_rams()), 2026, 12, "LA", "Rams", [("Kyren Williams", "RB", "OUT")], ROWS)
    assert _texts(got) == ["Rams without Kyren Williams (RB, 75% of the carries): 75% of the carries this season to "
                           "fill", "That player has not missed a game this season, so there is no game of this "
                           "team's own to read it from yet"], _texts(got)


def test_a_reserve_list_absence_counts_while_it_is_fresh():
    rows = _rams(puka_out=(10, 11))
    fresh = S.for_team(_conn(rows), 2026, 12, "LA", "Rams", [], ROWS, reserve=[("Puka Nacua", "WR", "IR")])
    assert fresh and _texts(fresh)[0].startswith("Rams without Puka Nacua (WR"), fresh
    assert "In the 2 games this season without that player (weeks 10 and 11)" in _texts(fresh)[1]
    # Gone since week 5: his teammates' own form carries it, so nothing is said.
    stale = S.for_team(_conn(rows), 2026, 12, "LA", "Rams", [], ROWS, reserve=[("Gone Receiver", "WR", "IR")])
    assert stale is None
    assert S.for_team(_conn(rows), 2026, 12, "LA", "Rams", [], ROWS) is None, "nobody out, nothing to say"
    # The same rule for the week's report and injured reserve: gone since week 5 is no fresh hole either way.
    assert S.for_team(_conn(rows), 2026, 12, "LA", "Rams", [("Gone Receiver", "WR", "IR")], ROWS) is None
    both = S.for_team(_conn(rows), 2026, 12, "LA", "Rams", [("Puka Nacua", "WR", "IR")], ROWS,
                      reserve=[("Puka Nacua", "WR", "IR")])
    assert _texts(both)[0].startswith("Rams without Puka Nacua (WR") and both["outs"] == ["Puka Nacua"], \
        "on both lists, said once"


def test_the_read_is_a_lookup_by_the_tables_key():
    conn = _conn(_rams())
    plan = " ".join(str(r[-1]) for r in conn.execute(
        "EXPLAIN QUERY PLAN SELECT period, player, position, market, value FROM player_game_logs WHERE sport='nfl' "
        "AND season=? AND period IN (?,?) AND game_id IN (?,?) AND team=? AND market IN ('targets','carries')",
        (2026, "001", "002", "LA-001", "LA-002", "LA")).fetchall())
    assert plan.startswith("SEARCH") and "SCAN" not in plan, plan
    weeks = S.usage_by_week(conn, 2026, "LA", 12)
    assert sorted(weeks) == list(range(1, 12)) and weeks[11]["Tutu Atwell"]["targets"] == 4.0, \
        "the newest week read off the same-night box score's ids"
    assert S.usage_by_week(conn, 2026, "LA", 1) == {} and S.usage_by_week(None, 2026, "LA", 12) == {}


def _ctx(conn, injuries, rows=ROWS, sport="nfl"):
    return types.SimpleNamespace(
        sport=sport, conn=conn, season=2026, teams=("SF", "LA"), name=lambda t: {"SF": "49ers", "LA": "Rams"}[t],
        scan={"injuries": injuries, "reserve": {}}, result={"date": "2026-W12", "recommendations": rows})


def test_the_injury_section_says_it_and_the_grader_counts_it_as_its_own():
    rows = _rams()
    inj = [{"player": "Puka Nacua", "position": "WR", "status": "Out", "team": "LA"},
           {"player": "Davante Adams", "position": "WR", "status": "OUT", "team": "LA"},
           {"player": "Brock Purdy", "position": "QB", "status": "QUESTIONABLE", "team": "SF"}]
    blocks = S.report_blocks(_ctx(_conn(rows), inj))
    assert blocks[0] == {"type": "h", "text": "Who steps up"} and len(blocks) == 2, blocks
    assert blocks[1]["items"][0].startswith("Rams without Puka Nacua") and blocks[1]["items"][0].endswith(".")
    assert S.report_blocks(_ctx(_conn(rows), inj, sport="cfb")) == [], "NFL first"
    assert S.report_blocks(_ctx(None, inj)) == []
    # Week 12: Atwell got 8 targets (his last ten averaged 5.1), Parkinson 2 (his averaged 3.4).
    rows += _line(12, "Tutu Atwell", "WR", 8, rec_yds=88) + _line(12, "Colby Parkinson", "TE", 2, rec_yds=15)
    report = {"home": "LA", "away": "SF", "sections": [{"key": "injuries", "title": "Injuries and availability",
                                                        "blocks": blocks}]}
    fin = {"home": "LA", "away": "SF", "date": "2026-11-30", "live": {"state": "final", "away_score": 20,
                                                                        "home_score": 24}}
    summary = G.grade(report, fin, _conn(rows), "nfl", "2026-W12")
    grp = next(g for g in summary["groups"] if g["key"] == "stepup")
    assert (grp["what"], grp["right"], grp["graded"]) == ("Who steps up", 1, 2), grp
    assert "Who steps up: 1 of 2 beat their average" in G.summary_lines(summary)
    grades = [g for g in blocks[1]["grades"] if g]
    assert [(g["status"], g["actual"]) for g in grades] == [("right", 8.0), ("wrong", 2.0)], grades
    assert grades[0]["words"].startswith("Right: 8 targets; the last 10 games averaged"), grades[0]["words"]
    assert S.census([report], {"recommendations": ROWS}) == {"teams": 1, "reads": 2, "moved": 2}
    assert S.census([], {}) == {}


def test_a_pick_keeps_the_step_it_was_priced_with_and_the_record_counts_them():
    from engine import ledger as L
    assert S.mate_mult({"mate_card": {"case": "above_new", "applied": 1.19}}) == 1.19
    assert S.mate_mult({"mate_card": {"case": "back", "applied": 0.91}}) == 0.91
    assert S.mate_mult({"mate_card": {"case": None, "applied": 1.0, "if_sits": {}}}) is None, "questionable: none"
    assert S.mate_mult({"mate_card": {"case": "above_cont", "applied": 1.0}}) is None, "measured, not moved"
    assert S.mate_mult({"mate_mult": 1.12}) == 1.12 and S.mate_mult({}) is None and S.mate_mult(None) is None
    assert S.mate_mult({"mate_card": {"case": "above_new", "applied": 40}}) is None
    conn = L.connect(Path(tempfile.mkdtemp()) / "ledger.db")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(bets)")}
    assert "mate_mult" in cols

    def put(player, category, row, status="open", pnl=None):
        cur = conn.execute("INSERT INTO bets (ts, sport, date, player, market, side, line, category, status, "
                           "pnl_units) VALUES ('2026-11-25T20:00:00', 'nfl', '2026-W13', ?, 'receptions', 'OVER', "
                           "4.5, ?, ?, ?)", (player, category, status, pnl))
        L._stamp_team(conn, cur, row)
    put("Tutu Atwell", "likely", dict(ROWS[0], team="LA"), "won", 0.08)
    put("Colby Parkinson", "likely", {"team": "LA", "mate_mult": 1.12}, "lost", -0.1)
    put("Kyren Williams", "likely", {"team": "LA"}, "won", 0.09)
    put("Puka Nacua", "report", {"team": "LA", "mate_card": {"case": "back", "applied": 0.9}}, "won", 0.9)
    put("Tutu Atwell", "main", dict(ROWS[0], team="LA"))
    got = {r["player"] + "|" + r["category"]: r["mate_mult"] for r in conn.execute(
        "SELECT player, category, mate_mult FROM bets")}
    assert got == {"Tutu Atwell|likely": 1.19, "Colby Parkinson|likely": 1.12, "Kyren Williams|likely": None,
                   "Puka Nacua|report": 0.9, "Tutu Atwell|main": 1.19}, got
    rec = S.bet_record(conn)
    assert rec == {"nfl": {"likely": {"raised": [1, 1, 0, -0.02]}, "report": {"lowered": [1, 0, 0, 0.9]},
                           "edge": {"open": 1}}}, rec
    assert L._stepup_record(conn, None) == rec


def test_injured_reserve_reads_as_words():
    from engine import gamereport as R
    assert R.status_words("IR") == "on injured reserve" and R.status_words("OUT") == "out"
    assert R.status_words("Questionable") == "questionable" and R.status_words(None) == ""


def test_the_pages_name_the_group():
    rp = (ROOT / "web" / "js" / "reportpicks.js").read_text()
    assert '["stepup", "Who steps up"]' in rp, "Report Picks' totals list the group"
    rec = (ROOT / "web" / "js" / "record.js").read_text()
    assert "function recStepupSection(" in rec and "recStepupSection(d.stepup_record" in rec
    assert ("stepup", "Who steps up") in G.GROUPS and G.RIGHT_WORDS["stepup"] == "beat their average"


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
                traceback.print_exc()
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
