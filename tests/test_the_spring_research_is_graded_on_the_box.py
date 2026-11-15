"""The spring MLB and NBA research picks are graded on the box (2026-11-15).

Ethan, answering "grade the spring MLB/NBA chats via a box command — yes or
no": "Yes to mlb and nba". The NFL chats' 166 legs were graded in the
workspace (engine/researchrecord); the spring's MLB and NBA box scores are
only on the box. docs/research/spring_2026_picks.json holds every leg the
spring cards named, and tools/grade_spring_research.py grades each against
the box's history, read-only:

  * an MLB hitter's hits, total bases, home runs and runs driven in, and a
    pitcher's strikeouts, from his plate appearances that day (a name is
    matched without its accents or a "Jr.");
  * a no-run-first-inning pick from the first inning's runs driven in, with
    the caveat said;
  * an NBA spread or total from the final, a prop from the box score;
  * a pick the history has no game for is "missing", never a loss.

    python3 tests/test_the_spring_research_is_graded_on_the_box.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

import grade_spring_research as G                                   # noqa: E402


def _db():
    from engine import db as D
    path = Path(tempfile.mkdtemp()) / "history.db"
    conn = D.connect(path)
    pa = []

    def add(pk, n, date, batter, pitcher, team, opp, inning, etype, rbi=0):
        pa.append((pk, n, 2026, date, 0, batter, "R", 0, pitcher, "R", team, opp, 1, inning, "top", etype, etype,
                   rbi))
    # 4 April: Schwarber homers at Coors; Alvarez does not.
    add(1, 1, "2026-04-04", "Kyle Schwarber", "Chase Dollander", "PHI", "COL", 1, "home_run", 1)
    add(1, 2, "2026-04-04", "Kyle Schwarber", "Chase Dollander", "PHI", "COL", 3, "single")
    add(2, 1, "2026-04-04", "Yordan Alvarez", "Luis Morales", "HOU", "ATH", 1, "field_out")
    # 31 March: Hunter Brown strikes out seven; Soto hits once.
    for i in range(7):
        add(3, 10 + i, "2026-03-31", f"Batter {i}", "Hunter Brown", "BOS", "HOU", 1 + i, "strikeout")
    add(4, 1, "2026-03-31", "Juan Soto", "Andre Pallante", "NYM", "STL", 1, "single")
    # 25 May: José Ramírez (accents in the feed) homers.
    add(5, 1, "2026-05-25", "José Ramírez", "Zack Littell", "CLE", "WSH", 2, "home_run", 1)
    # 6 April: SEA at TEX scoreless in the first; ATL at LAA not.
    add(6, 1, "2026-04-06", "Julio Rodríguez", "Jacob deGrom", "SEA", "TEX", 1, "strikeout")
    add(6, 2, "2026-04-06", "Corey Seager", "Logan Gilbert", "TEX", "SEA", 1, "field_out")
    add(7, 1, "2026-04-06", "Ronald Acuña Jr.", "José Soriano", "ATL", "LAA", 1, "home_run", 1)
    # 5 April: Harper drives in exactly one; a doubleheader for Alvarez on the 1st.
    add(8, 1, "2026-04-05", "Bryce Harper", "Tomoyuki Sugano", "PHI", "COL", 1, "double", 1)
    add(9, 1, "2026-04-01", "Yordan Alvarez", "Garrett Crochet", "HOU", "BOS", 1, "field_out")
    add(10, 1, "2026-04-01", "Yordan Alvarez", "Brayan Bello", "HOU", "BOS", 1, "single", 2)
    conn.executemany(
        "INSERT INTO mlb_pa (game_pk, at_bat, season, date, batter_id, batter, bat_side, pitcher_id, pitcher, "
        "pitch_hand, team, opponent, home, inning, half, event, event_type, rbi) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", pa)
    games = [("nba", 2025, "2026-04-02", "MIN@DET", "DET", "MIN", 120, 110, "2026-04-02"),
             ("nba", 2025, "2026-04-02", "LAL@OKC", "OKC", "LAL", 130, 115, "2026-04-02"),
             ("nba", 2025, "2026-04-03", "TOR@MEM", "MEM", "TOR", 100, 113, "2026-04-03"),
             ("nba", 2025, "2026-05-09", "OKC@LAL", "LAL", "OKC", 100, 115, "2026-05-09")]
    conn.executemany("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score, date) "
                     "VALUES (?,?,?,?,?,?,?,?,?)", games)
    conn.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, "
                     "market, value) VALUES (?,?,?,?,?,?,?,?,?)",
                     [("nba", 2025, "2026-05-09", "OKC@LAL", "Marcus Smart", "LAL", "OKC", "ast", 4)])
    conn.commit()
    conn.close()
    return path


PICKS = [
    {"date": "2026-04-04", "sport": "mlb", "who": "Kyle Schwarber", "market": "home_runs", "line": 0.5, "side": "over",
     "game": "PHI@COL", "role": "pick"},
    {"date": "2026-04-04", "sport": "mlb", "who": "Yordan Alvarez", "market": "home_runs", "line": 0.5, "side": "over",
     "game": "HOU@ATH", "role": "pick"},
    {"date": "2026-03-31", "sport": "mlb", "who": "Hunter Brown", "market": "strikeouts", "line": 6.5, "side": "over",
     "game": "BOS@HOU", "role": "pick"},
    {"date": "2026-03-31", "sport": "mlb", "who": "Juan Soto", "market": "hits", "line": 0.5, "side": "over",
     "game": "NYM@STL", "role": "pick"},
    {"date": "2026-05-25", "sport": "mlb", "who": "Jose Ramirez", "market": "home_runs", "line": 0.5, "side": "over",
     "game": "WSH@CLE", "role": "pick"},
    {"date": "2026-04-06", "sport": "mlb", "who": "SEA@TEX", "market": "nrfi", "line": None, "side": "yes",
     "game": "SEA@TEX", "role": "pick"},
    {"date": "2026-04-06", "sport": "mlb", "who": "ATL@LAA", "market": "nrfi", "line": None, "side": "yes",
     "game": "ATL@LAA", "role": "pick"},
    {"date": "2026-04-05", "sport": "mlb", "who": "Bryce Harper", "market": "rbi", "line": 0.5, "side": "over",
     "game": "PHI@COL", "role": "pick"},
    {"date": "2026-04-01", "sport": "mlb", "who": "Yordan Alvarez", "market": "rbi", "line": 0.5, "side": "over",
     "game": "BOS@HOU", "role": "pick"},
    {"date": "2026-04-02", "sport": "nba", "who": "DET", "market": "spread", "line": -3.5, "side": "", "game": "MIN@DET",
     "role": "pick"},
    {"date": "2026-04-02", "sport": "nba", "who": "LAL", "market": "spread", "line": 9.5, "side": "", "game": "LAL@OKC",
     "role": "pick"},
    {"date": "2026-04-03", "sport": "nba", "who": "TOR", "market": "spread", "line": -13, "side": "", "game": "TOR@MEM",
     "role": "pick"},
    {"date": "2026-05-09", "sport": "nba", "who": "Marcus Smart", "market": "ast", "line": 2.5, "side": "over",
     "game": "OKC@LAL", "role": "pick"},
    {"date": "2026-05-09", "sport": "nba", "who": "Chet Holmgren", "market": "pts", "line": 17.5, "side": "over",
     "game": "OKC@LAL", "role": "pick"},
    {"date": "2026-05-09", "sport": "nba", "who": "OKC@LAL", "market": "total", "line": 211.5, "side": "over",
     "game": "OKC@LAL", "role": "pick"},
    {"date": "2026-04-03", "sport": "nba", "who": "BOS", "market": "spread", "line": -17, "side": "", "game": "BOS@MIL",
     "role": "pick"},
]


def _graded():
    import sqlite3
    path = _db()
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return {(r["date"], r["who"], r["market"]): r for r in G.grade(conn, PICKS)}
    finally:
        conn.close()


def test_each_pick_is_graded_on_the_days_own_box():
    g = _graded()

    def res(d, who, m):
        return g[(d, who, m)]["result"], g[(d, who, m)]["value"]
    assert res("2026-04-04", "Kyle Schwarber", "home_runs") == ("won", 1)
    assert res("2026-04-04", "Yordan Alvarez", "home_runs") == ("lost", 0)
    assert res("2026-03-31", "Hunter Brown", "strikeouts") == ("won", 7)
    assert res("2026-03-31", "Juan Soto", "hits") == ("won", 1)
    assert res("2026-05-25", "Jose Ramirez", "home_runs") == ("won", 1), "José Ramírez is Jose Ramirez"
    assert res("2026-04-05", "Bryce Harper", "rbi") == ("won", 1)
    # A doubleheader: the game against the pick's opponent... both are BOS; the first is read and said.
    assert g[("2026-04-01", "Yordan Alvarez", "rbi")]["result"] in ("won", "lost")


def test_a_first_inning_is_scoreless_when_no_one_drove_a_run_in_and_the_caveat_is_said():
    g = _graded()
    assert g[("2026-04-06", "SEA@TEX", "nrfi")]["result"] == "won"
    assert g[("2026-04-06", "ATL@LAA", "nrfi")]["result"] == "lost"
    assert "wild pitch" in g[("2026-04-06", "SEA@TEX", "nrfi")]["note"]


def test_nba_spreads_totals_and_props_and_a_missing_box_is_never_a_loss():
    g = _graded()
    assert g[("2026-04-02", "DET", "spread")]["result"] == "won"          # won by 10, laid 3.5
    assert g[("2026-04-02", "LAL", "spread")]["result"] == "lost"         # lost by 15, took 9.5
    assert g[("2026-04-03", "TOR", "spread")]["result"] == "push"         # won by 13, laid 13
    assert g[("2026-05-09", "Marcus Smart", "ast")]["result"] == "won"
    assert g[("2026-05-09", "OKC@LAL", "total")]["result"] == "won"       # 215 over 211.5
    assert g[("2026-05-09", "Chet Holmgren", "pts")]["result"] == "missing"
    assert g[("2026-04-03", "BOS", "spread")]["result"] == "missing"
    assert "not in the history" in g[("2026-04-03", "BOS", "spread")]["note"]


def test_the_picks_file_holds_every_spring_card_and_the_command_reads_only():
    data = json.loads((ROOT / "docs" / "research" / "spring_2026_picks.json").read_text(encoding="utf-8"))
    picks = data["picks"]
    assert len(picks) == 39, len(picks)
    assert {p["sport"] for p in picks} == {"mlb", "nba"}
    assert all(p["market"] in G.MARKET_WORDS for p in picks), [p["market"] for p in picks if p["market"] not in G.MARKET_WORDS]
    assert all(p["role"] in ("pick", "alternative", "endorsed") for p in picks)
    src = (ROOT / "tools" / "grade_spring_research.py").read_text(encoding="utf-8")
    assert "?mode=ro" in src and "INSERT" not in src and "UPDATE" not in src.replace("UPDATE", "", 0)


def test_the_report_prints_each_pick_the_record_by_kind_and_a_line_to_paste():
    import contextlib
    import io
    import sqlite3
    path = _db()
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        G.report(G.grade(conn, PICKS))
    conn.close()
    out = buf.getvalue()
    assert "Kyle Schwarber over 0.5 home runs" in out and "WON" in out
    assert "mlb home_runs over" in out and "nba spread" in out
    line = next(ln for ln in out.splitlines() if ln.startswith("SPRING_GRADES "))
    got = json.loads(line[len("SPRING_GRADES "):])
    assert got["by_kind"]["mlb home_runs over"][:2] == [2, 1], got["by_kind"]


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
