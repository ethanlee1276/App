"""A finished game's page says if its report was right, and how its picks and parlays did (GAMEFINAL1).

Ethan, 2026-11-16, on the finished Patriots at Lions page: "this page as well
should have if the game report was correct or not and go over all that was
right and wrong with the game report along if the parlays and picks did good.
Also where I circled, its wording is weird and can be better and also we should
color code shit like the other stuff."

A game that started before its report was kept (engine/reportkeep) shows no
pick and no ticket of its own: the board took them down at the start. The
record kept them, graded on the box score, and engine/reportoutcome reads them
back onto each finished report (`outcome`) from the report stage, so the card
(js/detail.js gprCard, tested in test_a_finished_game_says_how_every_pick_went)
counts and lists them.
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import parlayledger as PL  # noqa: E402
from engine import reportoutcome as O  # noqa: E402

BETS = [
    # (sport, date, player, market, side, line, odds, status, actual, category, team)
    ("nfl", "2026-W11", "Jahmyr Gibbs", "rush_yds", "OVER", 74.5, -115, "won", 142, "likely", "DET"),
    ("nfl", "2026-W11", "Jahmyr Gibbs", "rush_yds", "OVER", 74.5, -115, "won", 142, "report", "DET"),
    ("nfl", "2026-W11", "Drake Maye", "pass_yds", "OVER", 220.5, -110, "lost", 180, "main", "NE"),
    ("nfl", "2026-W11", "Hunter Henry", "receptions", "UNDER", 4.5, -120, "void", None, "longshot", None),
    ("nfl", "2026-W11", "Sam LaPorta", "receptions", "OVER", 3.5, -125, "open", None, "board", "DET"),
    ("nfl", "2026-W11", "DET", "spread", "OVER", 3.5, -110, "won", 25, "main", None),
    ("nfl", "2026-W11", "NE@DET", "total", "UNDER", 47.5, -110, "won", 45, "main", None),
    # Not this game's: another club, another book, a parlay leg, another week, a nameless club-less row.
    ("nfl", "2026-W11", "Josh Allen", "pass_yds", "OVER", 240.5, -110, "won", 280, "likely", "BUF"),
    ("nfl", "2026-W11", "Jared Goff", "pass_yds", "OVER", 230.5, -110, "won", 260, "parlay_leg", "DET"),
    ("nfl", "2026-W10", "Jahmyr Gibbs", "rush_yds", "OVER", 70.5, -115, "lost", 50, "likely", "DET"),
    ("nfl", "2026-W11", "Someone Else", "receptions", "OVER", 2.5, -110, "won", 4, "likely", None),
]


def _journal():
    p = Path(tempfile.mkdtemp()) / "ledger.db"
    conn = sqlite3.connect(p)
    conn.execute("CREATE TABLE bets (id INTEGER PRIMARY KEY, sport TEXT, date TEXT, player TEXT, market TEXT, "
                 "side TEXT, line REAL, odds INTEGER, status TEXT, actual REAL, category TEXT, team TEXT)")
    conn.executemany("INSERT INTO bets (sport, date, player, market, side, line, odds, status, actual, category, team) "
                     "VALUES (?,?,?,?,?,?,?,?,?,?,?)", BETS)
    conn.executescript(PL.SCHEMA)

    def ticket(source, status, legs, grade="NE@DET", date="2026-W11"):
        cur = conn.execute("INSERT INTO parlays (sport, date, legs_key, parlay_type, n_legs, grade, source, status) "
                           "VALUES ('nfl', ?, ?, 'same_game', ?, ?, ?, ?)",
                           (date, f"{source}-{status}-{len(legs)}-{grade}", len(legs), grade, source, status))
        for i, (player, market, side, line, st, actual) in enumerate(legs, start=1):
            conn.execute("INSERT INTO parlay_legs (parlay_id, leg_no, player, team, market, side, line, status, actual) "
                         "VALUES (?,?,?,?,?,?,?,?,?)", (cur.lastrowid, i, player, "DET", market, side, line, st, actual))
    ticket("game_three", "lost", [("Jahmyr Gibbs", "rush_yds", "OVER", 74.5, "won", 142),
                                  ("Drake Maye", "pass_yds", "OVER", 220.5, "lost", 180)])
    ticket("game_three", "won", [("Jahmyr Gibbs", "rush_yds", "OVER", 74.5, "won", 142),
                                 ("Jared Goff", "pass_yds", "OVER", 230.5, "won", 260)])
    ticket("game_td", "open", [("Jahmyr Gibbs", "anytime_td", "OVER", 0.5, "open", None),
                               ("Amon-Ra St. Brown", "anytime_td", "OVER", 0.5, "won", 1)])
    ticket("game_three", "won", [("Josh Allen", "pass_yds", "OVER", 240.5, "won", 280),
                                 ("James Cook", "rush_yds", "OVER", 60.5, "won", 80)], grade="KC@BUF")
    ticket("game_three", "lost", [("Jahmyr Gibbs", "rush_yds", "OVER", 70.5, "lost", 50),
                                  ("Jared Goff", "pass_yds", "OVER", 230.5, "won", 260)], date="2026-W10")
    # A leg alone is no ticket.
    ticket("game_td", "void", [("Jahmyr Gibbs", "anytime_td", "OVER", 0.5, "void", None)])
    conn.commit()
    conn.close()
    return p


G = {"home": "DET", "away": "NE", "date": "2026-11-15", "live": {"state": "final", "home_score": 35, "away_score": 10}}


def test_the_game_s_picks_come_off_the_record_each_once_in_the_report_s_own_book_first():
    conn = sqlite3.connect(_journal())
    got = O.picks(conn, "nfl", "2026-W11", "DET", "NE", names={"hunterhenry"})
    by = {(p["player"], p["market"]): p for p in got}
    assert set(by) == {("Jahmyr Gibbs", "rush_yds"), ("Drake Maye", "pass_yds"), ("Hunter Henry", "receptions"),
                       ("Sam LaPorta", "receptions"), ("DET", "spread"), ("NE@DET", "total")}, sorted(by)
    gibbs = by[("Jahmyr Gibbs", "rush_yds")]
    assert gibbs == {"player": "Jahmyr Gibbs", "market": "rush_yds", "side": "OVER", "line": 74.5, "status": "won",
                     "book": "report", "team": "DET", "odds": -115, "actual": 142.0}, "the report's own book names it"
    assert by[("Hunter Henry", "receptions")]["status"] == "void", "a row with no club is the game's when the report names him"
    assert "actual" not in by[("Hunter Henry", "receptions")]
    assert by[("Sam LaPorta", "receptions")]["status"] == "pending", "an open pick waits on the box score"
    spread = by[("DET", "spread")]
    assert spread["game"] is True and spread["team"] == "DET" and spread["line"] == 3.5, spread
    assert by[("NE@DET", "total")]["game"] is True and "team" not in by[("NE@DET", "total")]
    assert not any(p["player"] in ("Josh Allen", "Jared Goff", "Someone Else") for p in got), \
        "another club's, a parlay leg's and an unnamed club-less pick are not this game's"


def test_the_game_s_tickets_come_off_the_record_with_their_legs():
    conn = sqlite3.connect(_journal())
    got = O.tickets(conn, "nfl", "2026-W11", "DET", "NE")
    assert [t["status"] for t in got["threes"]] == ["lost", "won"], got
    assert got["threes"][0]["legs"][1] == {"player": "Drake Maye", "market": "pass_yds", "side": "OVER", "line": 220.5,
                                           "status": "lost", "team": "DET", "actual": 180.0}
    assert [t["status"] for t in got["scorers"]] == ["pending"], "an open ticket waits; one leg alone is none"
    assert got["scorers"][0]["legs"][0]["status"] == "pending" and "actual" not in got["scorers"][0]["legs"][0]
    assert O.tickets(conn, "nfl", "2026-W11", "BUF", "KC")["threes"][0]["status"] == "won", "each game its own"
    empty = sqlite3.connect(":memory:")
    assert O.tickets(empty, "nfl", "2026-W11", "DET", "NE") == {}, "no parlay tables, no tickets"


def test_each_finished_report_carries_its_outcome_and_only_a_finished_one():
    path = _journal()
    live = dict(G, home="BUF", away="KC", live={"state": "live"})
    result = {"date": "2026-W11", "games": [G, live]}
    rep = {"home": "DET", "away": "NE", "date": "2026-11-15", "sections": [{"key": "x", "blocks": [
        {"type": "list", "items": [{"player": "Hunter Henry"}]}]}]}
    other = {"home": "BUF", "away": "KC", "date": "2026-11-15", O.KEY: {"stale": 1}}
    assert O.attach(result, [rep, other], "nfl", path) == 1
    assert len(rep[O.KEY]["picks"]) == 6 and len(rep[O.KEY]["tickets"]["threes"]) == 2, rep[O.KEY]
    assert O.KEY not in other, "a game not over carries none, and an old one is taken off"
    # Read again every build: a pick graded since is counted on the next.
    conn = sqlite3.connect(path)
    conn.execute("UPDATE bets SET status='won', actual=6 WHERE player='Sam LaPorta'")
    conn.commit()
    conn.close()
    O.attach(result, [rep], "nfl", path)
    assert next(p for p in rep[O.KEY]["picks"] if p["player"] == "Sam LaPorta")["status"] == "won"
    assert O.attach(result, [rep], "nfl", Path(tempfile.mkdtemp()) / "none.db") == 0, "no journal, nothing read"
    assert O.attach({"date": "2026-W11", "games": "not a list"}, [rep], "nfl", path) == 0, "never raises"
    assert O.of_game(sqlite3.connect(path), "nba", "2026-W11", G) == {}, "another league's record holds none of it"


def test_the_report_stage_reads_the_record_between_the_grade_and_the_archive():
    src = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    body = src[src.index("def keep_started("):src.index("def _grade_finals(")]
    assert (body.index("graded = _grade_finals(result, reports, sport, conn, out)")
            < body.index("reportoutcome.attach(result, reports, sport)")
            < body.index("n_arch = reportarchive.save(result, reports, sport, out)")), \
        "graded first, its outcome on it, then archived with it"


def test_the_card_is_one_function_both_pages_draw():
    detail = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
    assert "return gprCard(g, gameReportFor(g), rows, gp, { sport: state.sport, scored: true });" in detail
    assert ('${gprCard(g, doc.report, rows, doc.parlays || {}, { map: doc.results || {}, sport: doc.sport, '
            'id: "pbp-our-verdict" })}') in detail, "an old game's page says the same, from its archive"
    css = (ROOT / "web" / "css" / "detail.css").read_text(encoding="utf-8")
    for cls in (".gpr-good { --tone: var(--good); }", ".gpr-bad { --tone: var(--bad); }",
                ".gpr-warn { --tone: var(--warn); }", ".gpr-verdict", ".gpr-row", ".gpr-chip", ".gpr-cols"):
        assert cls in css, cls
    for lit in ('"gpr-won"', 'GPR_TONE = { good: "gpr-good", bad: "gpr-bad", warn: "gpr-warn", info: "gpr-info", '
                'wait: "gpr-wait" }', "${gprCls(tone)}", "${gprCls(v.tone)}"):
        assert lit in detail, lit
    assert "gpr-${" not in detail, "every tone's class written whole, so detail.css can claim it"
    assert "gp-res-list" not in detail and "gp-res-list" not in css, "the old list is gone with its words"


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
