"""Pass or run (step AIQ, 27 November 2026): each team's pass rate, the lean of the defense it meets, our read of
how often it throws, said in the NFL game report and checked once the play-by-play is in.

Ethan: "we need to make sure we are judging and recording and playing off the % of times teams pass vs run ... also
go deeper on that on who they run and pass More against and what style of defense". The numbers below are made up
for the fixture (four clubs, four weeks); the measured ones live in engine/passrun.MEASURED.
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import gamereport as GR  # noqa: E402
from engine import gamescan, passrun, reportfacts, reportgrade, reportrecord  # noqa: E402

# Fixture only: (week, offense, defense, dropbacks, designed runs, its points, theirs).
GAMES = [
    (1, "AAA", "BBB", 40, 20, 10, 24), (1, "BBB", "AAA", 30, 30, 24, 10),
    (1, "CCC", "DDD", 33, 27, 17, 17), (1, "DDD", "CCC", 36, 24, 17, 17),
    (2, "AAA", "CCC", 36, 24, 20, 13), (2, "CCC", "AAA", 30, 30, 13, 20),
    (2, "BBB", "DDD", 27, 33, 31, 3), (2, "DDD", "BBB", 42, 18, 3, 31),
    (3, "AAA", "DDD", 30, 30, 27, 6), (3, "DDD", "AAA", 39, 21, 6, 27),
    (3, "BBB", "CCC", 33, 27, 14, 21), (3, "CCC", "BBB", 36, 24, 21, 14),
    (4, "AAA", "BBB", 42, 18, 17, 30), (4, "BBB", "AAA", 30, 30, 30, 17),
    (4, "CCC", "DDD", 30, 30, 23, 20), (4, "DDD", "CCC", 33, 27, 20, 23),
]


def _conn(games=GAMES, season=2026):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE team_units (sport TEXT, season INTEGER, period TEXT, team TEXT, side TEXT, opp TEXT, "
                  "plays INTEGER, dropbacks INTEGER, rushes INTEGER)")
    conn.execute("CREATE TABLE games (sport TEXT, season INTEGER, period TEXT, home TEXT, away TEXT, "
                 "home_score REAL, away_score REAL)")
    seen = set()
    for wk, off, dfn, db, ru, pf, pa in games:
        # The week zero-padded, as the box files it (engine/sources/nflunits, engine/ingest: "012").
        conn.execute("INSERT INTO team_units VALUES ('nfl', ?, ?, ?, 'off', ?, ?, ?, ?)",
                     (season, f"{wk:03d}", off, dfn, db + ru, db, ru))
        conn.execute("INSERT INTO team_units VALUES ('nfl', ?, ?, ?, 'def', ?, ?, ?, ?)",
                     (season, f"{wk:03d}", dfn, off, db + ru, db, ru))
        key = (wk, frozenset((off, dfn)))
        if key not in seen:
            seen.add(key)
            conn.execute("INSERT INTO games VALUES ('nfl', ?, ?, ?, ?, ?, ?)", (season, f"{wk:03d}", dfn, off, pa, pf))
    return conn


def _rate(*pairs):
    return sum(d for d, _r in pairs) / sum(d + r for d, r in pairs)


def test_the_table_counts_each_rate_the_reports_way():
    tab = passrun.tables(_conn(), 2026, 5)
    t = tab["teams"]
    # Dropbacks over dropbacks and designed runs, pooled over the games, as the run rate in "How each team plays".
    assert abs(t["AAA"]["rate"] - round(_rate((40, 20), (36, 24), (30, 30), (42, 18)), 4)) < 1e-9
    assert t["AAA"]["games"] == 4 and t["AAA"]["of"] == 4
    assert t["DDD"]["rank"] == 1, "DDD throws the most of the four"
    lg = _rate(*[(g[3], g[4]) for g in GAMES])
    assert abs(tab["league"] - round(lg, 4)) < 1e-9 and tab["week"] == 5
    # Each week with its opponent, its rate and its score.
    w1 = t["AAA"]["weeks"][0]
    assert (w1["week"], w1["opp"], w1["rate"], w1["for"], w1["against"]) == (1, "BBB", round(40 / 60, 4), 10, 24)


def test_a_defense_lean_is_each_offense_against_its_own_other_games():
    tab = passrun.tables(_conn(), 2026, 5)
    # BBB's defense met AAA in weeks 1 and 4, DDD in week 2 and CCC in week 3. Each game's rate is set against that
    # offense's own rate in its other games.
    aaa = {1: (40, 20), 2: (36, 24), 3: (30, 30), 4: (42, 18)}
    ddd = {1: (36, 24), 2: (42, 18), 3: (39, 21), 4: (33, 27)}
    ccc = {1: (33, 27), 2: (30, 30), 3: (36, 24), 4: (30, 30)}
    other = lambda games, wk: _rate(*[v for k, v in games.items() if k != wk])   # noqa: E731
    want = [40 / 60 - other(aaa, 1), 42 / 60 - other(ddd, 2), 36 / 60 - other(ccc, 3), 42 / 60 - other(aaa, 4)]
    got = tab["teams"]["BBB"]
    assert abs(got["lean"] - round(sum(want) / 4, 4)) < 1e-9 and got["lean_games"] == 4
    # A lean needs three games: a season two weeks old has none.
    early = passrun.tables(_conn(), 2026, 3)
    assert all(v["lean"] is None for v in early["teams"].values())
    assert passrun.tables(None, 2026, 5) == {} and passrun.tables(sqlite3.connect(":memory:"), 2026, 5) == {}


def test_the_read_is_the_measured_model_from_week_nine():
    tab = passrun.tables(_conn(), 2026, 5)
    assert passrun.read(tab, "AAA", "BBB") is None, "week 5 needs the pass rate over expected, not filed here"
    tab = dict(tab, week=10)
    r = passrun.read(tab, "AAA", "BBB", margin=3.0)
    own, lean, lg = tab["teams"]["AAA"]["rate"], tab["teams"]["BBB"]["lean"], tab["league"]
    want = lg + passrun.C0 + passrun.OWN * (own - lg) + passrun.LEAN * lean + passrun.MARGIN * 3.0
    assert abs(r["expect"] - round(want, 4)) < 1e-9 and r["own"] == own and r["lean"] == lean
    gap = r["expect"] - r["own"]
    assert r["said"] == ("more" if gap >= passrun.SAID_GAP else "less" if gap <= -passrun.SAID_GAP else "usual")
    # A team far above the league's rate comes back part of the way: read less than its usual with no lean.
    flat = {"league": 0.58, "week": 12, "teams": {"X": {"rate": 0.68}, "Y": {"lean": 0.0}}}
    assert passrun.read(flat, "X", "Y")["said"] == "less"
    flat["teams"]["Y"]["lean"] = 0.15
    assert passrun.read(flat, "X", "Y")["said"] == "usual", "a big lean to the pass holds it up"
    assert passrun.read(flat, "X", "Z") is None, "no read without the defense's lean"
    # The scan takes each side's margin off the points the lines expect.
    sc = gamescan.passrun_scan(dict(tab), "BBB", "AAA", {"AAA": 20.0, "BBB": 27.0})
    assert sc["teams"]["AAA"]["read"] == passrun.read(tab, "AAA", "BBB", margin=-7.0)
    assert sc["teams"]["BBB"]["read"] == passrun.read(tab, "BBB", "AAA", margin=7.0)
    assert gamescan.passrun_scan({}, "BBB", "AAA") is None


def _ctx(tab, home="BBB", away="AAA"):
    g = {"home": home, "away": away, "date": "2026-11-29",
         "scan": {"passrun": gamescan.passrun_scan(tab, home, away, {home: 24.0, away: 21.0})}}
    return GR.Ctx(g, {"date": "2026-W13"}, names={})


def test_the_report_says_each_side_its_read_and_who_it_threw_most_against():
    tab = dict(passrun.tables(_conn(), 2026, 5), week=13)
    c = _ctx(tab)
    sec = GR.sec_passrun(c)
    assert sec["key"] == "passrun" and sec["title"] == "Pass or run"
    paras = [b for b in sec["blocks"] if b["type"] == "p"]
    assert len(paras) == 2 and paras[0]["text"].startswith("AAA throws on ")
    assert "Our read for this game: about " in paras[0]["text"]
    assert "often than usual against BBB" in paras[0]["text"], paras[0]["text"]
    # Each read carries what a finished game checks it by.
    cl = paras[0]["claim"]
    r = c.scan["passrun"]["teams"]["AAA"]["read"]
    assert cl == {"kind": "passrun", "season": 2026, "week": 13, "team": "AAA", "expect": r["expect"],
                  "own": r["own"], "said": r["said"]}
    hist = next(b for b in sec["blocks"] if b["type"] == "list")["items"]
    assert hist[0] == ("AAA threw most against BBB (70%, a 17–30 loss), and least against DDD (50%, "
                       "a 27–6 win)."), hist
    note = sec["blocks"][-1]
    assert note["type"] == "note" and "every season 2022–2025" in note["text"]
    assert "added nothing beyond the lean" in note["text"] and "does not move a player's number yet" in note["text"]
    assert "attempts" not in note["text"], "passing attempts missed the rule by a hair: not claimed"
    assert GR.section_hint(c, sec).startswith("AAA throws about ")
    # Week 6 without the teams' pass rate over expected: the rates and leans are said, no read and no claim, and
    # the note says what is missing; before week 4, that the read starts there.
    early = GR.sec_passrun(_ctx(dict(tab, week=6)))
    assert not any(b.get("claim") for b in early["blocks"])
    assert "it needs each team's pass rate over expected" in early["blocks"][-1]["text"]
    assert "starts at week 4" in GR.sec_passrun(_ctx(dict(tab, week=3)))["blocks"][-1]["text"]
    # Only the NFL, and only with the table.
    assert GR.sec_passrun(_ctx({})) is None
    c.sport = "cfb"
    assert GR.sec_passrun(c) is None
    i = GR.SECTIONS.index(GR.sec_identity)
    assert GR.SECTIONS[i + 1] is GR.sec_passrun, "right after how each team plays"


def test_a_finished_game_checks_the_read_once_the_play_by_play_is_in():
    conn = _conn()
    claim = {"kind": "passrun", "season": 2026, "week": 4, "team": "AAA", "expect": 0.62, "own": 0.6, "said": "more"}
    got = reportfacts.passrun_check(claim, conn)
    assert got["status"] == "right" and got["actual"] == 0.7, got          # 42 of 60
    assert got["words"] == "Right: AAA threw on 70% of its plays (42 of 60), more than its usual 60%; we read more " \
                           "than usual (about 62%).", got["words"]
    assert reportfacts.passrun_check(dict(claim, said="less"), conn)["status"] == "wrong"
    info = reportfacts.passrun_check(dict(claim, said="usual"), conn)
    assert info["status"] == "info" and info["words"].endswith("our read was about 62%.")
    # Not in yet: no grade, and a report is due again once it lands.
    late = dict(claim, week=5)
    assert reportfacts.passrun_check(late, conn) is None
    rep = {"sections": [{"key": "passrun", "blocks": [{"type": "p", "text": "x", "claim": late}]}]}
    assert not reportfacts.passrun_due(rep, conn)
    conn.execute("INSERT INTO team_units VALUES ('nfl', 2026, '005', 'AAA', 'off', 'CCC', 60, 33, 27)")
    assert reportfacts.passrun_due(rep, conn)
    rep["sections"][0]["blocks"][0]["grade"] = reportfacts.passrun_check(late, conn)
    assert rep["sections"][0]["blocks"][0]["grade"]["status"] == "wrong"   # 55%, under its 60%
    assert not reportfacts.passrun_due(rep, conn), "graded once it is in"


def test_the_record_counts_pass_or_run_as_its_own_kind():
    assert ("passrun", "Pass or run") in reportgrade.GROUPS
    assert reportrecord.SECTION_KINDS["passrun"] == ("passrun",)
    assert reportrecord.KIND_WORDS["passrun"] == "pass-or-run reads"
    lines = reportrecord.track_lines({"games": 12, "since": "2026-11-29", "groups": {"passrun": [7, 11]}}, "nfl")
    assert lines["passrun"].startswith("Our pass-or-run reads so far: 7 of 11 right (64%)"), lines
    js = (ROOT / "web" / "js" / "reportpicks.js").read_text(encoding="utf-8")
    assert '["passrun", "Pass or run"]' in js
    # A graded final read back from the archive is graded again once a pass-or-run read can be.
    src = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    body = src[src.index("def _graded_from_archive("):]
    assert "passrun_due(rep, conn)" in body[:body.index("\ndef ")]
    grade = (ROOT / "engine" / "reportgrade.py").read_text(encoding="utf-8")
    assert 'F.passrun_check(b["claim"], conn) if passrun' in grade


def test_our_read_rides_the_paid_half_and_the_rates_ride_the_game():
    from engine import gate
    tab = dict(passrun.tables(_conn(), 2026, 5), week=13)
    pr = gamescan.passrun_scan(tab, "BBB", "AAA", {"BBB": 24.0, "AAA": 21.0})
    mine = gamescan.passrun_split(pr)
    assert set(mine) == {"AAA", "BBB"} and all("read" not in row for row in pr["teams"].values())
    assert pr["teams"]["AAA"]["rate"] and pr["teams"]["BBB"]["lean"] is not None, "the facts stay on the game"
    assert "scan_reads" in gate.PAID_KEYS
    g = {"home": "BBB", "away": "AAA", "date": "2026-11-29", "scan": {"passrun": pr}}
    c = GR.Ctx(g, {"date": "2026-W13", "scan_reads": {"AAA@BBB": {"players": [], "passrun": mine}}}, names={})
    paras = [b for b in GR.sec_passrun(c)["blocks"] if b["type"] == "p"]
    assert paras[0]["claim"]["expect"] == mine["AAA"]["expect"] and paras[1]["claim"]["team"] == "BBB"
    # A free reader's copy of the game, the paid half stripped, says the rates and leans and no read.
    free = GR.Ctx(g, {"date": "2026-W13"}, names={})
    assert not any(b.get("claim") for b in GR.sec_passrun(free)["blocks"])


def _with_weeks(conn, proe_by_team, season=2026, weeks=(1, 2, 3, 4)):
    """team_weeks rows (fixture numbers): each team's pass rate over expected, 60 plays a week."""
    conn.execute("CREATE TABLE team_weeks (sport TEXT, season INTEGER, period TEXT, team TEXT, plays INTEGER, "
                 "proe REAL)")
    for t, oe in proe_by_team.items():
        for wk in weeks:
            conn.execute("INSERT INTO team_weeks VALUES ('nfl', ?, ?, ?, 60, ?)", (season, f"{wk:03d}", t, oe))
    return conn


def test_the_read_takes_the_pass_rate_over_expected_from_week_four():
    """Step AIS (28 November 2026): a team's pass rate over expected, against the league's so far, joins the read;
    weeks 4 to 8 read it with the team's rate and the line, week 9 on with the defense's lean too."""
    oe = {"AAA": 0.05, "BBB": -0.03, "CCC": 0.0, "DDD": 0.02}
    conn = _with_weeks(_conn(), oe)
    tab = passrun.tables(conn, 2026, 5)
    lg_oe = sum(oe.values()) / 4                          # every team 60 plays a week: the plays-weighted mean
    assert abs(tab["league_proe"] - round(lg_oe, 4)) < 1e-9 and tab["teams"]["AAA"]["proe"] == 0.05
    # Week 5: the early model.
    r = passrun.read(tab, "AAA", "BBB", margin=3.0)
    k = passrun.EARLY
    own, lg = tab["teams"]["AAA"]["rate"], tab["league"]
    want = lg + k["c0"] + k["own"] * (own - lg) + k["proe"] * (0.05 - tab["league_proe"]) + k["margin"] * 3.0
    assert r["model"] == "early" and abs(r["expect"] - round(want, 4)) < 1e-9 and r["lean"] is None
    assert r["proe_rel"] == round(0.05 - tab["league_proe"], 4)
    # Week 10: the late model, with the defense's lean.
    late = dict(tab, week=10)
    r = passrun.read(late, "AAA", "BBB", margin=3.0)
    k, lean = passrun.LATE, tab["teams"]["BBB"]["lean"]
    want = (lg + k["c0"] + k["own"] * (own - lg) + k["proe"] * (0.05 - tab["league_proe"]) + k["lean"] * lean
            + k["margin"] * 3.0)
    assert r["model"] == "late" and abs(r["expect"] - round(want, 4)) < 1e-9 and r["lean"] == lean
    # A team the box has no pass rate over expected for: week 10 falls back to the step AIQ read, week 5 has none.
    del tab["teams"]["AAA"]["proe"]
    assert passrun.read(dict(tab, week=10), "AAA", "BBB")["model"] == "lean"
    assert passrun.read(tab, "AAA", "BBB") is None
    # The scan carries the league's figure the read is taken against.
    assert gamescan.passrun_scan(late, "BBB", "AAA")["league_proe"] == late["league_proe"]


def test_the_report_says_why_in_the_reads_own_parts():
    oe = {"AAA": 0.06, "BBB": -0.04, "CCC": 0.0, "DDD": 0.0}
    tab = passrun.tables(_with_weeks(_conn(), oe), 2026, 5)
    c = _ctx(dict(tab, week=6))
    para = next(b for b in GR.sec_passrun(c)["blocks"] if b["type"] == "p")
    # Early: the rate counts for little, the pass rate over expected is said against the league's, and the lean is a
    # fact beside the read, not part of it.
    rel = round(100 * (0.06 - tab["league_proe"]))
    assert "a few games' rate is mostly the score" in para["text"], para["text"]
    assert f"it throws {rel} points more than the league does on the same downs, distances and scores" in para["text"]
    assert para["claim"]["kind"] == "passrun" and para["claim"]["week"] == 6
    c = _ctx(dict(tab, week=13))
    para = next(b for b in GR.sec_passrun(c)["blocks"] if b["type"] == "p")
    assert "Why: " in para["text"] and "often than usual against BBB" in para["text"].split("Why: ")[1]
    note = GR.sec_passrun(c)["blocks"][-1]["text"]
    assert "its pass rate over expected" in note and "from week 9, also about 0.3 of the lean" in note
    m = passrun.MEASURED
    lo, hi = (round(100 * x) for x in m["side_early"])
    assert f"{lo}% to {hi}% of the time in weeks 4 to 8" in note


if __name__ == "__main__":
    fns = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as e:                                       # noqa: BLE001
            failed += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {fn.__name__}: {e!r}")
    print(f"\n{len(fns) - failed} tests passed." if not failed else f"\n{failed} failed.")
    sys.exit(1 if failed else 0)
