"""The parlay record counts one set a game: the one its report carried at the start
(2026-11-19).

Ethan, asked whether the parlay record should count only the parlays posted at
the start: "Yes."

The board posts a game's parlays afresh as lines and news move, and the journal
keeps every version it posted, so the Record page counted each game's tickets
several times over (the NFL's three-leg record read 314 graded tickets from two
weeks of games, a game posting three or four at a time). engine/parlayledger now marks each
journaled ticket `at_start`: 1 when it was in the set engine/reportkeep kept as
the game started, 0 when the board replaced it before then; and the record and
its second view count the 1s. What these hold:

  * a started game's kept set marks its own tickets 1 and every earlier
    version 0, on the board as built (before any filter), under the board's
    date or the game's own day, and the first marking stands;
  * a kept set that held no ticket held none: every version 0;
  * a game that started before the journal marked it is marked from its
    archived starting set (engine/reportarchive), nightly;
  * the record counts the starting sets and says how many versions it left
    out, and so does its split by how a game's tickets were made up (ZR).

    python3 tests/test_the_parlay_record_counts_each_games_starting_set.py
"""
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import parlayledger as PL, reportarchive  # noqa: E402


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    PL.ensure_schema(c)
    return c


def _leg(player, market, team="KC"):
    return {"player": player, "team": team, "market": market, "side": "OVER", "line": 1.5, "odds": -150,
            "book": "DraftKings", "p": 0.7}


def _t(*players, market="receptions"):
    return {"legs": [_leg(p, market) for p in players], "joint": 0.32, "take_dec": 3.4, "naive_dec": 3.3,
            "independent": 0.34}


A, B, C, D = _t("A1", "A2", "A3"), _t("B1", "B2", "B3"), _t("C1", "C2", "C3"), _t("D1", "D2", "D3")
S1, S2 = _t("S1", "S2", market="anytime_td"), _t("S3", "S4", market="anytime_td")


def _game(threes, scorers, **extra):
    return {"away": "DEN", "home": "KC", "game": "DEN@KC", "date": "2026-11-23", "threes": threes,
            "scorers": scorers, **extra}


def _journal_a_day(c, day="2026-W12"):
    """A morning build posts A, B, C and S1; an afternoon build has D for C and S2 for S1."""
    assert PL.log_game_parlays(c, {"games": [_game([A, B, C], [S1])]}, "nfl", day) == 4
    assert PL.log_game_parlays(c, {"games": [_game([A, B, D], [S2])]}, "nfl", day) == 2
    assert c.execute("SELECT count(*) FROM parlays").fetchone()[0] == 6


def _grade_all(c, status="won"):
    c.execute("UPDATE parlays SET status=?, pnl_units=?", (status, 2.4 if status == "won" else -1.0))
    c.commit()


def _marks(c):
    return {(r["source"], r["legs_key"].split("|")[0]): r["at_start"]
            for r in c.execute("SELECT source, legs_key, at_start FROM parlays")}


def test_the_set_at_the_start_is_marked_and_every_earlier_version_is_not():
    c = _conn()
    _journal_a_day(c)
    # The game starts: the board carries its kept set, marked `kept`.
    gp = {"games": [_game([A, B, D], [S2], kept="Sun 1:00 PM ET")]}
    assert PL.mark_started_games(c, gp, "nfl", "2026-W12") == 6
    got = _marks(c)
    assert got[("game_three", "a1")] == got[("game_three", "b1")] == got[("game_three", "d1")] == 1, got
    assert got[("game_three", "c1")] == 0 and got[("game_td", "s1")] == 0 and got[("game_td", "s3")] == 1, got
    # The first marking stands: a later build cannot change it.
    assert PL.mark_started_games(c, {"games": [_game([C], [S1], kept="x")]}, "nfl", "2026-W12") == 0
    assert _marks(c) == got
    # And the journal never writes a kept ticket.
    assert PL.log_game_parlays(c, gp, "nfl", "2026-W12") == 0


def test_the_record_counts_the_starting_sets_and_says_what_it_left_out():
    c = _conn()
    _journal_a_day(c)
    PL.mark_started_games(c, {"games": [_game([A, B, D], [S2], kept="Sun 1:00 PM ET")]}, "nfl", "2026-W12")
    _grade_all(c)
    rec = PL.game_parlay_record(c)
    three, pairs = rec["nfl"]["three"], rec["nfl"]["scorers"]
    assert (three["graded"], three["wins"], three["not_counted"]) == (3, 3, 1), three
    assert (pairs["graded"], pairs["not_counted"]) == (1, 1), pairs
    view = PL.report_game_parlays(c)
    assert view["three"]["graded"] == 3 and view["scorers"]["graded"] == 1, view["three"]
    # A game still to play, or one whose starting set was never kept, counts nothing yet.
    c2 = _conn()
    _journal_a_day(c2)
    _grade_all(c2)
    assert "nfl" not in PL.game_parlay_record(c2)


def test_a_board_that_moved_on_a_day_still_marks_the_games_own_day():
    """The NBA's board rolls to the next slate while last night's games stay
    kept on it: their tickets are journaled under the game's own day."""
    c = _conn()
    t = _t("N1", "N2", "N3")
    assert PL.log_game_parlays(c, {"games": [_game([t], [], date="2026-11-18")]}, "nba", "2026-11-18") == 1
    gp = {"games": [_game([t], [], date="2026-11-18", kept="Tue 7:10 PM ET")]}
    assert PL.mark_started_games(c, gp, "nba", "2026-11-19") == 1
    assert c.execute("SELECT at_start FROM parlays").fetchone()[0] == 1


def test_a_kept_entry_it_cannot_read_never_stops_the_journal():
    c = _conn()
    _journal_a_day(c)
    bad = {"games": [_game([{"legs": ["not", "a", "leg"]}], [], kept="Sun 1:00 PM ET")]}
    assert PL.mark_started_games(c, bad, "nfl", "2026-W12") == 0
    assert set(_marks(c).values()) == {None}, "left unmarked for the night's archive pass"


def test_a_kept_set_with_no_ticket_held_none():
    c = _conn()
    _journal_a_day(c)
    assert PL.mark_started_games(c, {"games": [_game([], [], kept="Sun 1:00 PM ET")]}, "nfl", "2026-W12") == 6
    assert set(_marks(c).values()) == {0}


def test_a_game_that_started_before_the_marking_is_marked_from_its_archive():
    c = _conn()
    _journal_a_day(c)
    where = Path(tempfile.mkdtemp())
    path = reportarchive.path_for(where, "nfl", "2026-11-23", "DEN", "KC")
    reportarchive.write(path, {"sport": "nfl", "date": "2026-11-23", "label": "2026-W12", "game": "DEN@KC",
                               "away": "DEN", "home": "KC", "parlays": _game([A, B, D], [S2])})
    assert PL.mark_from_archive(c, where) == 6
    assert sorted(v for v in _marks(c).values()) == [0, 0, 1, 1, 1, 1]
    assert PL.mark_from_archive(c, where) == 0, "marked once"
    assert PL.mark_from_archive(c, where / "nowhere") == 0, "no archive, nothing to mark"


def test_the_fill_split_counts_the_starting_sets():
    """ZR (2026-11-20): a game short of the report's own tickets fills to three,
    and the record says how each way of filling has done, on the starting sets
    and from the day tickets began to say how they were made up (FILL_SINCE)."""
    c = _conn()
    rows = [("2026-11-21T12:00:00", None, "won", 1), ("2026-11-21T12:00:00", None, "lost", 1),
            ("2026-11-21T12:00:00", "props", "lost", 1), ("2026-11-21T12:00:00", "props", "open", 1),
            ("2026-11-21T12:00:00", "board", "won", 1),
            ("2026-11-21T12:00:00", "props", "won", 0),            # replaced before the start: not counted
            ("2026-11-19T12:00:00", None, "won", 1)]               # before FILL_SINCE: in the total, not the split
    for i, (ts, fill, st, at_start) in enumerate(rows):
        c.execute("INSERT INTO parlays (ts, sport, date, legs_key, parlay_type, n_legs, grade, qualified, was_play,"
                  " notional_units, stake_units, source, status, at_start, fill, modeled_joint, pnl_units)"
                  " VALUES (?,?,?,?,?,?,?,1,0,1,0,?,?,?,?,?,?)",
                  (ts, "nba", ts[:10], f"k{i}", "same_game", 3, "A@B", "game_three", st, at_start, fill, 0.3,
                   {"won": 2.0, "lost": -1.0}.get(st)))
    c.commit()
    three = PL.game_parlay_record(c)["nba"]["three"]
    assert (three["graded"], three["wins"]) == (5, 3), three
    bf = three["by_fill"]
    assert bf["from"] == PL.FILL_SINCE == "2026-11-20"
    assert (bf["report"]["graded"], bf["report"]["wins"], bf["report"]["net_units"]) == (2, 1, 1.0), bf
    assert (bf["props"]["graded"], bf["props"]["wins"], bf["props"]["open"]) == (1, 0, 1), bf
    assert (bf["board"]["graded"], bf["board"]["wins"], bf["board"]["chance"]) == (1, 1, 0.3), bf
    assert set(bf) == {"from", "report", "props", "board"}
    js = (ROOT / "web" / "js" / "record.js").read_text(encoding="utf-8")
    assert "${close}${rebuilt}${madeUp}" in js and 'props: ["the game’s best props", ""]' in js


def test_the_journal_and_the_night_mark_them():
    src = (ROOT / "engine" / "parlayledger.py").read_text(encoding="utf-8")
    i = src.index("def journal_built_boards(")
    body = src[i:src.index("\ndef ", i + 10)]
    assert body.index("mark_started_games(conn, gp, sport, day)") < body.index("_with_leg_rows(conn, gp, sport, day)"), \
        "marked on the board as built, before the leg-row filter drops a kept ticket"
    m = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    assert "_pl.mark_from_archive(lconn)" in m
    # And once a process, on its first journal pass: right after a deploy, not the night after.
    assert body.index("mark_from_archive(conn)") < body.index("for sport, rel in BOARD_FILES.items():")
    assert "if not _ARCHIVE_MARKED:" in body


def test_the_record_page_says_it_once():
    import json
    import shutil
    import subprocess
    rj = (ROOT / "web" / "js" / "record.js").read_text(encoding="utf-8")
    i = rj.index("function gpParlaysHTML(")
    body = rj[i:rj.index("\n}\n", i)]
    assert body.count("gpOneSetHTML(") == 2, "once over a league's cards, once over the table of every league"
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed")
        return
    j = rj.index("function gpOneSetHTML(")
    fn = rj[j:rj.index("\n}\n", j) + 2]
    prog = fn + """
      const text = (h) => h.replace(/<[^>]+>/g, " ").replace(/\\s+/g, " ").trim();
      console.log(JSON.stringify([text(gpOneSetHTML([{not_counted: 1200}, {not_counted: 34}, undefined])),
        text(gpOneSetHTML([{not_counted: 1}])), gpOneSetHTML([{graded: 3}])]));"""
    out = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    many, one, none = json.loads(out.stdout)
    # Not how many (ZP, 20 November): "The 1,234 others the board posted" read as 30 parlays a game.
    assert many == one == ("One set a game: the parlays each report carried when its game started. Versions the "
                           "board replaced before a game began aren’t counted."), many
    assert none == "", "nothing left out, nothing said"


if __name__ == "__main__":
    import traceback
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception:
            fails += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
