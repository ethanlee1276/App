"""A finished game's report keeps the parlays it carried at the start, and lists the ones the Record counts (step AEA).

Ethan, 24 November 2026: "Make sure the game reports are recording all wins and loses correctly. It seems like when
I check how they did, it's missing a lot of data". Live that morning, every NFL game of the week before but its Monday
night read "unkept" on Report Picks' "How our reports did" (Thursday's Colts at Texans and all eleven of Sunday's): its
picks graded, not one of its parlays listed. The Record counted those same games' starting tickets (Thursday nights:
2 three-leg tickets, a two-leg ticket and 3 touchdown pairs from Colts at Texans; the Lions' Buccaneers game, seven),
because it reads the journal's own marking of each game's starting set (engine/parlayledger.mark_at_start); Report
Picks read the copy the game's archived file held, which for those games named no ticket the journal had.

  * The journal's marking decides (engine/reportoutcome._own_tickets, ``marks``): the tickets marked 1 are the
    report's, in the kept set's order where it names them; those marked 0 are the versions replaced before the start
    ("earlier"); the kept set only says which were on paper. A game the journal never marked reads the kept set as
    before.
  * A finished game's archived file is never written again with less than it held from the start: the kept set, the
    picks, the report kept before the start (engine/reportarchive.keep_start).
  * A started game the file beside the private board has lost is read back from its archived file
    (engine/reportkeep._from_archive), and a file that is there and cannot be read is not written over that build.
    The build log and the heartbeat count both (``report_keep``).

Offline. Run directly: `python3 tests/test_a_games_starting_parlays_stay_on_its_report.py`
"""
import copy
import gzip
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import featured as F                                     # noqa: E402
from engine import gate                                              # noqa: E402
from engine import parlayledger as PL                                # noqa: E402
from engine import reportarchive as RA                               # noqa: E402
from engine import reportkeep as K                                   # noqa: E402
from engine import reportoutcome as O                                # noqa: E402

DAY, WEEK, GAME = "2026-11-19", "2026-W11", "IND@HOU"


def _legs(*rows):
    return [{"player": p, "market": m, "side": s, "line": ln} for p, m, s, ln in rows]


#: The game's tickets as the journal holds them: the set its report carried at the start (A, C, D) and a version
#: of its three-leg ticket the board replaced before it (B).
A = _legs(("C.J. Stroud", "pass_yds", "OVER", 240.5), ("Nico Collins", "rec_yds", "OVER", 70.5),
          ("Joe Mixon", "rush_yds", "OVER", 60.5))
B = _legs(("C.J. Stroud", "pass_yds", "OVER", 250.5), ("Nico Collins", "rec_yds", "OVER", 70.5),
          ("Jonathan Taylor", "rush_yds", "OVER", 80.5))
A2 = _legs(("Daniel Jones", "pass_cmp", "OVER", 19.5), ("Michael Pittman Jr.", "receptions", "OVER", 4.5),
           ("Joe Mixon", "rush_att", "OVER", 15.5))
C = _legs(("Nico Collins", "receptions", "OVER", 4.5), ("Joe Mixon", "rush_yds", "OVER", 60.5))
D = _legs(("Joe Mixon", "anytime_td", "OVER", 0.5), ("Jonathan Taylor", "anytime_td", "OVER", 0.5))
KEPT = {"away": "IND", "home": "HOU", "game": GAME, "kept": "Thu 8:05 PM ET",
        "threes": [{"legs": A2}, {"legs": A}], "twos": [{"legs": C}], "scorers": [{"legs": D}]}


def _journal(mark=True):
    """The journal with the game's tickets, and the marking its first build after the start made."""
    p = Path(tempfile.mkdtemp()) / "ledger.db"
    conn = sqlite3.connect(p)
    conn.execute("CREATE TABLE bets (id INTEGER PRIMARY KEY, sport TEXT, date TEXT, player TEXT, market TEXT, "
                 "side TEXT, line REAL, odds INTEGER, status TEXT, actual REAL, category TEXT, team TEXT)")
    conn.execute("INSERT INTO bets (sport, date, player, market, side, line, odds, status, actual, category, team) "
                 "VALUES ('nfl', ?, 'Joe Mixon', 'rush_yds', 'OVER', 60.5, -115, 'won', 88, 'report', 'HOU')",
                 (WEEK,))
    conn.executescript(PL.SCHEMA)
    PL.ensure_schema(conn)
    for source, status, legs in (("game_three", "lost", B), ("game_three", "lost", A), ("game_three", "won", A2),
                                 ("game_two", "lost", C), ("game_td", "lost", D)):
        cur = conn.execute("INSERT INTO parlays (sport, date, legs_key, parlay_type, n_legs, grade, source, status, "
                           "pnl_units) VALUES ('nfl', ?, ?, 'same_game', ?, ?, ?, ?, ?)",
                           (WEEK, PL.legs_key(legs), len(legs), GAME, source, status,
                            1.5 if status == "won" else -1.0))
        for i, l in enumerate(legs, start=1):
            conn.execute("INSERT INTO parlay_legs (parlay_id, leg_no, player, team, market, side, line, status) "
                         "VALUES (?,?,?,?,?,?,?,?)", (cur.lastrowid, i, l["player"], "", l["market"], l["side"],
                                                      l["line"], status))
    if mark:
        PL.mark_at_start(conn, "nfl", (WEEK, DAY), GAME, KEPT)
    conn.commit()
    conn.close()
    return p


def _archive(parlays=None):
    where = Path(tempfile.mkdtemp())
    doc = {"sport": "nfl", "date": DAY, "label": WEEK, "away": "IND", "home": "HOU", "game": GAME,
           "final": {"away": 16, "home": 23}, "report": {"away": "IND", "home": "HOU", "sections": []}, "results": {}}
    if parlays is not None:
        doc["parlays"] = parlays
    RA.write(RA.path_for(where, "nfl", DAY, "IND", "HOU"), doc)
    return where


def _game(path, where):
    return O.for_games("nfl", [(DAY, "IND", "HOU")], member=True, path=path, where=where)[f"{DAY}|IND|HOU"]


def _players(t):
    return [l["player"] for l in t["legs"]]


def test_report_picks_lists_the_set_the_record_counts_when_the_archive_lost_it():
    path = _journal()
    for where in (_archive(), _archive({"away": "IND", "home": "HOU", "threes": [{"legs": _legs(
            ("Nobody", "pass_yds", "OVER", 1.5), ("Else", "rec_yds", "OVER", 2.5))}]})):
        game = _game(path, where)
        assert "unkept" not in game, game
        assert [_players(t) for t in game["threes"]] == [_players({"legs": A}), _players({"legs": A2})], \
            "the two the journal marked at the start, in its order where no kept set names them"
        assert [t["status"] for t in game["twos"]] == ["lost"] and [t["status"] for t in game["scorers"]] == ["lost"]
        assert [_players(t) for t in game["earlier"]["threes"]] == [_players({"legs": B})], \
            "the version replaced before the start, apart"
    # The game's own tickets are the ones the Record counts (engine/featured reads the same marking).
    counted = F._tickets_of(sqlite3.connect(path), "nfl", [({"date": DAY, "away": "IND", "home": "HOU"},
                                                             {"label": WEEK})])[0]["tickets"]
    game = _game(path, _archive())
    mine = {kind: [sum(t["status"] == "won" for t in game.get(kind) or []),
                   sum(t["status"] == "lost" for t in game.get(kind) or [])] for kind in ("threes", "twos", "scorers")}
    assert mine == {kind: v[:2] for kind, v in counted.items()}, (mine, counted)


def test_the_kept_sets_order_stands_where_it_names_the_tickets():
    path = _journal()
    game = _game(path, _archive(KEPT))
    assert [_players(t) for t in game["threes"]] == [_players({"legs": A2}), _players({"legs": A})], \
        "in the report's own order"
    assert [t["status"] for t in game["threes"]] == ["won", "lost"]
    # A ticket the kept set holds on paper is listed apart, as before.
    paper = dict(KEPT, threes=[{"legs": A}], paper_threes=[{"legs": A2}])
    game = _game(path, _archive(paper))
    assert [_players(t) for t in game["threes"]] == [_players({"legs": A})]
    assert [_players(t) for t in game["paper"]["threes"]] == [_players({"legs": A2})]


def test_a_set_that_held_no_ticket_lists_only_the_versions_replaced():
    p = _journal(mark=False)
    conn = sqlite3.connect(p)
    PL.mark_at_start(conn, "nfl", (WEEK, DAY), GAME, {"away": "IND", "home": "HOU", "kept": "x", "threes": []})
    conn.commit()
    conn.close()
    game = _game(p, _archive())
    assert not any(game.get(k) for k in O.TICKETS) and "unkept" not in game, game
    assert len(game["earlier"]["threes"]) == 3 and len(game["earlier"]["twos"]) == 1, game["earlier"]


def test_a_game_the_journal_never_marked_reads_its_kept_set_as_before():
    p = _journal(mark=False)
    assert _game(p, _archive()) == {"picks": _game(p, _archive())["picks"], "unkept": True}
    game = _game(p, _archive(KEPT))
    assert [t["status"] for t in game["threes"]] == ["won", "lost"] and "unkept" not in game
    conn = sqlite3.connect(p)
    assert set(O.marks(conn, "nfl", (WEEK, DAY), "HOU", "IND").values()) == {None}, "never marked"
    PL.mark_at_start(conn, "nfl", (WEEK, DAY), GAME, KEPT)
    got = O.marks(conn, "nfl", (WEEK, DAY), "HOU", "IND")
    assert sorted(got.values()) == [0, 1, 1, 1, 1] and got[PL.legs_key(B)] == 0, got
    assert O.marks(conn, "nfl", (WEEK, DAY), "HOU", "TEN") == {}, "another game: none"
    conn.close()


# --- the archive keeps what the game carried at the start ---------------------------------------
def _tree():
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "web", "data"))
    return os.path.join(d, "web", "data", "recommendations.json")


def _final():
    return {"away": "IND", "home": "HOU", "date": DAY, "kickoff": "20:15",
            "live": {"state": "final", "away_score": 16, "home_score": 23}}


def _report(kept=True, outcome=None):
    r = {"away": "IND", "home": "HOU", "date": DAY, "graded": {"status": "graded", "version": 1},
         "sections": [{"key": "card", "blocks": [{"items": [{"player": "Joe Mixon", "bet": True}]}]}] if kept else []}
    if kept:
        r["kept"] = "Thu 8:05 PM ET"
    if outcome:
        r[O.KEY] = outcome
    return r


def _read(out):
    path = RA.path_for(gate._full_dir_for(out), "nfl", DAY, "IND", "HOU")
    return json.loads(gzip.decompress(path.read_bytes()))


def test_the_archive_never_writes_a_game_again_with_less_than_it_held_from_the_start():
    out = _tree()
    picks = {"likely": [{"player": "Joe Mixon", "market": "rush_yds"}]}
    good = {"date": WEEK, "games": [_final()], "game_parlays": {"games": [dict(KEPT)]}, K.KEPT_PICKS: {GAME: picks}}
    assert RA.save(good, [_report()], "nfl", out, results={}) == 1
    first = _read(out)
    assert first["parlays"]["kept"] and first["picks"] == picks and first["report"]["kept"]
    # A build that had lost the game's record: no tickets, no picks, the report written after the start.
    bad = {"date": WEEK, "games": [_final()], "game_parlays": {"games": []}}
    RA.save(bad, [_report(kept=False, outcome={"picks": [{"player": "Joe Mixon", "status": "won"}]})], "nfl", out,
            results={})
    doc = _read(out)
    assert doc["parlays"] == first["parlays"], "the set the report carried at the start stays"
    assert doc["picks"] == picks, "and its picks"
    assert doc["report"]["kept"] == "Thu 8:05 PM ET" and doc["report"]["sections"] == first["report"]["sections"], \
        "and the report as kept before the start"
    assert doc["report"][O.KEY] == {"picks": [{"player": "Joe Mixon", "status": "won"}]}, \
        "with this build's word on how its picks did"
    # A build with a kept set of its own writes that one.
    newer = dict(KEPT, threes=[{"legs": A}], kept="Thu 8:10 PM ET")
    RA.save(dict(good, game_parlays={"games": [newer]}), [_report()], "nfl", out, results={})
    assert _read(out)["parlays"]["kept"] == "Thu 8:10 PM ET"
    assert RA.keep_start({"a": 1}, None, None, None) == ({"a": 1}, None, None), "no file: as built"


# --- a started game the file lost is read back from its archive -----------------------------------
def test_a_started_game_the_file_lost_is_read_back_from_its_archive():
    out = _tree()
    where = gate._full_dir_for(out)
    picks = {"likely": [{"player": "Joe Mixon", "market": "rush_yds"}]}
    RA.save({"date": WEEK, "games": [_final()], "game_parlays": {"games": [dict(KEPT)]},
             K.KEPT_PICKS: {GAME: picks}}, [_report()], "nfl", out, results={})
    path = K.path_for("nfl", where)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"games": {}}), encoding="utf-8")            # the game lost from the file
    board = {"date": WEEK, "games": [_final()], "game_parlays": {"games": []}}
    fresh = {"away": "IND", "home": "HOU", "date": DAY, "sections": []}       # written after the start: no card
    reps, n = K.hold(board, [fresh], path, "2026-11-20T09:00:00")
    assert n == 1 and reps[0]["kept"] == "Thu 8:05 PM ET", reps
    assert reps[0]["sections"] and reps[0]["sections"][0]["key"] == "card", "its picks card back"
    entry = board["game_parlays"]["games"][0]
    assert entry["kept"] == "Thu 8:05 PM ET" and [_players(t) for t in entry["threes"]] == \
        [_players({"legs": A2}), _players({"legs": A})], "its tickets back on the board, marked kept"
    assert board[K.KEPT_PICKS][GAME] == picks
    assert board[K.REPORT_KEEP_KEY] == {"kept": 1, "restored": 1}, board[K.REPORT_KEEP_KEY]
    kept = json.loads(path.read_text())["games"][f"{GAME}|{DAY}"]
    assert kept["words"] == "Thu 8:05 PM ET" and "parlays" in kept, "and in the file again"
    # The next build reads it from the file, as any other.
    board2 = {"date": WEEK, "games": [_final()], "game_parlays": {"games": []}}
    reps2, _ = K.hold(board2, [dict(fresh)], path, "2026-11-20T10:00:00")
    assert reps2[0]["kept"] == "Thu 8:05 PM ET" and board2[K.REPORT_KEEP_KEY] == {"kept": 1}
    # No archived report kept before the start: written as built, and counted.
    other = {"date": WEEK, "games": [dict(_final(), away="TEN", home="JAX")], "game_parlays": {"games": []}}
    reps3, n3 = K.hold(other, [{"away": "TEN", "home": "JAX", "date": DAY}], path, "2026-11-20T10:00:00")
    assert n3 == 0 and "kept" not in reps3[0] and other[K.REPORT_KEEP_KEY] == {"lost": 1}


def test_a_file_that_cannot_be_read_is_not_written_over():
    d = Path(tempfile.mkdtemp())
    path = d / "reportkeep_nfl.json"
    assert K._read_kept(path) == ({}, False), "no file is an empty one"
    path.write_text('{"games": {"X@Y|2026-11-22": {"report": {}}}}', encoding="utf-8")
    assert K._read_kept(path)[0]["games"], "a good file reads"
    was = K._read_kept
    K._read_kept = lambda p: ({}, True)                                       # the open failed this build
    try:
        K.hold({"games": [{"away": "A", "home": "B", "date": "2026-11-24", "kickoff": "20:15"}]},
               [{"away": "A", "home": "B", "date": "2026-11-24"}], path, "2026-11-24T09:00:00")
    finally:
        K._read_kept = was
    assert json.loads(path.read_text())["games"] == {"X@Y|2026-11-22": {"report": {}}}, "left as it was"
    path.write_text("{not json", encoding="utf-8")
    assert K._read_kept(path) == ({}, False) and (d / "reportkeep_nfl.json.unreadable").exists(), \
        "a file that is no document is set aside for a look, and the file starts again"
    folder = d / "reportkeep_cbb.json"
    folder.mkdir()
    assert K._read_kept(folder) == ({}, True), "one that cannot be opened is left for the next build"


def _render(x, row=None, sport="nfl"):
    """Report Picks' strip for one game (js/reportpicks.js rpBetsHTML), with its row when given."""
    import shutil
    import subprocess
    sys.path.insert(0, str(ROOT / "tests"))
    import test_every_finished_game_marks_its_picks_and_parlays as T
    rp = T.RP
    helpers = "".join(T._fn(n) for n in ("rpMk", "rpHit", "rpBetWords", "rpPickLI", "rpTicketWords",
                                         "rpTicketsHTML", "rpBetsHTML", "rpEarlierHTML"))
    for const in ("const RP_STRIP_MAX = ", "const RP_PAPER = "):
        helpers += rp[rp.index(const):rp.index("\n", rp.index(const)) + 1]
    score = rp[rp.index("const RP_SCORE = "):rp.index("};", rp.index("const RP_SCORE = ")) + 3] + "\nconst RP_WORDS = {};\n"
    js = """
const escapeHtml = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => "&#" + c.charCodeAt(0) + ";");
const icon = (n) => `[${n}]`;
const MINUS = "\\u2212";
const RES_GAME_MARKETS = new Set(["moneyline", "total", "spread", "team_total"]);
const teamName = (t) => t;
const marketWord = (m) => m;
const plural = (n, one, many) => `${n} ${Number(n) === 1 ? one : (many || one + "s")}`;
%s
%s
process.stdout.write(rpBetsHTML(%s, %s, true, %s));
""" % (score, helpers, json.dumps(x), json.dumps(sport), json.dumps(row))
    node = shutil.which("node") or "/opt/node22/bin/node"
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return " ".join(out.stdout.split())


def test_a_game_with_nothing_on_the_record_says_why():
    """College buys its player props for the slate's best games (twelve a pull): a game we priced none in posts
    no pick and no parlay, and its row says so where it once read as data lost."""
    path = _journal(mark=False)
    where = _archive({"away": "WIS", "home": "PUR", "no_props": "no_props_priced", "threes": [], "twos": []})
    doc = RA.load("nfl", DAY, "IND", "HOU", where)
    assert O.none_why(doc) == O.NONE_NO_PROPS and O.none_why({}) == O.NONE_POSTED
    assert O.none_why({"parlays": {"threes": []}}) == O.NONE_POSTED
    # A game the record holds nothing for: no pick, no ticket (another game's journal), and why.
    got = O.for_games("nfl", [(DAY, "IND", "HOU")], member=False, path=_journal_empty(), where=where)
    assert got == {f"{DAY}|IND|HOU": {"none": O.NONE_NO_PROPS}}, got
    said = _render({"none": "no_props"}, {"date": DAY})
    assert "we priced no player props for this game" in said, said
    assert "No picks or parlays were posted for this game." in _render({"none": "none"}, {"date": DAY})
    assert "weren’t saved for games before 16 November" in _render({"none": "none"}, {"date": "2026-11-12"}), \
        "before the report's own book began, the reason is that"
    assert _render({}, {"date": DAY}) == "", "nothing asked, nothing said"
    # A game with anything on the record lists it, and says nothing of none.
    assert "none" not in _game(path, _archive(KEPT))


def test_a_game_after_the_sixteenth_never_says_its_parlays_were_from_before_it():
    old = _render({"unkept": True}, {"date": "2026-11-15"})
    new = _render({"unkept": True}, {"date": "2026-11-22"})
    assert "Parlays weren’t saved for games before 16 November." in old, old
    assert "weren’t kept at its start, so the Record counts none of them" in new and "16 November" not in new, new
    assert "16 November" in _render({"unkept": True}), "no row to read a date from: the old line"


def _journal_empty():
    p = Path(tempfile.mkdtemp()) / "ledger.db"
    conn = sqlite3.connect(p)
    conn.execute("CREATE TABLE bets (id INTEGER PRIMARY KEY, sport TEXT, date TEXT, player TEXT, market TEXT, "
                 "side TEXT, line REAL, odds INTEGER, status TEXT, actual REAL, category TEXT, team TEXT)")
    conn.executescript(PL.SCHEMA)
    PL.ensure_schema(conn)
    conn.commit()
    conn.close()
    return p


def test_the_build_log_and_the_heartbeat_count_them():
    src = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    assert "read back from the archive" in src and "under way written as built" in src
    import launch as L
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "b.json")
        with open(p, "w") as fh:
            json.dump({"games": [], K.REPORT_KEEP_KEY: {"kept": 11, "restored": 2, "lost": 1}}, fh)
        was = L._full_copy
        L._full_copy = lambda x: x
        try:
            got = L._board_counts(p)
            with open(p, "w") as fh:
                json.dump({"games": [], K.REPORT_KEEP_KEY: {"kept": 0}}, fh)
            quiet = L._board_counts(p)
        finally:
            L._full_copy = was
    assert got["report_keep"] == {"kept": 11, "restored": 2, "lost": 1}, got
    assert "report_keep" not in quiet, "nothing started: nothing said"


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
