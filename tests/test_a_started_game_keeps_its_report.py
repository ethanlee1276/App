"""A game under way keeps the report it had before it started (engine/reportkeep).

Ethan, 2026-11-16, with a finished game's page: "show ... if these props won
or lost and if the parlays won or lost ... and if our game report and reads
was correct ... for all sports", and the same day: "all bets and parlays made
from the game reports should be categorized as 'report' bets".

Every board takes a game's picks down when it starts and every build writes
every report again, so a game under way or over had its report written with
no picks card and no read picks: nothing of ours left to grade on the
finished page, and Report Picks lost the game. Now each build keeps the
report of every game not yet started (its bets with it) beside the private
board, and a started game's report is the kept one, marked with when it was
last written; college's too, once its board prices none of the night.

    python3 tests/test_a_started_game_keeps_its_report.py
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
from engine import gamereport as R                                   # noqa: E402
from engine import leaguereport as L                                 # noqa: E402
from engine import reportbets as RB                                  # noqa: E402
from engine import reportkeep as K                                   # noqa: E402


class _Fixtures:
    """The every-league report test's boards, imported when a test needs them."""
    def __getattr__(self, attr):
        import importlib
        return getattr(importlib.import_module("test_every_league_gets_a_game_report"), attr)


E = _Fixtures()

TATUM = {"kind": "prop", "player": "Jayson Tatum", "team": "BOS", "opponent": "MIA", "market": "points",
         "market_label": "Points", "side": "Over", "line": 24.5, "odds": -135, "book": "DraftKings",
         "model_prob": 0.63, "tier": "strong", "tier_label": "Strong", "game_date": "2026-10-22"}


def _tree():
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "web", "data"))
    return d, os.path.join(d, "web", "data", "nba.json")


def _board(rows=True, state=None, sport="nba"):
    board, meta = E._nba_board()
    if rows:
        board["likely_board"] = {"rows": [copy.deepcopy(TATUM)]}
    else:
        # The board took the game's picks down at its start (engine/likely).
        board["likely_board"] = {"rows": []}
    if state:
        board["games"][0]["live"] = {"state": state, "away_score": 99, "home_score": 112}
    if sport == "cbb":
        board["board_games"] = ["MIA@BOS"] if rows else []
    return board, meta


def _attach(board, meta, out, at, sport="nba"):
    line = L.attach(board, sport, meta=meta, out=out, at=at)
    return (board.get("game_reports") or [None])[0], line


def _card_players(rep):
    card = next((s for s in (rep or {}).get("sections") or [] if s.get("key") == "card"), None)
    return [it.get("player") for b in (card or {}).get("blocks") or [] for it in b.get("items") or []
            if isinstance(it, dict) and it.get("bet")]


def test_a_game_not_yet_started_is_kept_beside_the_private_board_with_its_bets():
    d, out = _tree()
    board, meta = _board()
    rep, line = _attach(board, meta, out, "2026-10-22T10:00:00")
    assert _card_players(rep) == ["Jayson Tatum"], rep and [s["key"] for s in rep["sections"]]
    assert "kept" not in rep, "a report before its game is the one written now"
    assert [b["player"] for b in board[RB.KEY]] == ["Jayson Tatum"]
    path = K.path_for("nba", gate._full_dir_for(out))
    assert str(path).startswith(os.path.join(d, "data", "built")), path
    assert not str(path).startswith(os.path.join(d, "web")), "the reports are paid: the kept ones stay private"
    kept = json.load(open(path))["games"]["MIA@BOS|2026-10-22"]
    assert kept["at"] == "2026-10-22T10:00:00", kept["at"]
    assert [b["player"] for b in kept["report"][RB.PRIVATE]] == ["Jayson Tatum"], "its bets kept with it"
    assert "started game" not in line, line


def test_once_it_starts_the_report_is_the_one_it_had_before():
    _d, out = _tree()
    board, meta = _board()
    _attach(board, meta, out, "2026-10-22T10:00:00")
    later, meta2 = _board()
    _attach(later, meta2, out, "2026-10-22T18:45:00")               # the last build before the tip
    live, meta3 = _board(rows=False, state="live")
    rep, line = _attach(live, meta3, out, "2026-10-22T20:10:00")
    assert _card_players(rep) == ["Jayson Tatum"], "its picks card, though the board took the picks down"
    assert rep["kept"] == "Thu 6:45 PM ET", rep.get("kept")
    assert [b["player"] for b in live[RB.KEY]] == ["Jayson Tatum"], "Report Picks keeps the game"
    assert all(RB.PRIVATE not in r for r in live["game_reports"]), "its bets lifted onto the board, as before"
    assert "; 1 started game kept as written before the start" in line, line
    # The kept one is not written over by a build after the start.
    final, meta4 = _board(rows=False, state="final")
    rep2, _ = _attach(final, meta4, out, "2026-10-23T01:30:00")
    assert rep2["kept"] == "Thu 6:45 PM ET" and _card_players(rep2) == ["Jayson Tatum"]
    # The game's start, not only its live state: the clock passed with the feed still saying "pre".
    late, meta5 = _board(rows=False, state="pre")
    rep3, _ = _attach(late, meta5, out, "2026-10-22T19:40:00")
    assert rep3.get("kept") == "Thu 6:45 PM ET", "past its 7:30 PM start the picks are down: the kept report"


def test_a_game_first_seen_under_way_is_written_as_before():
    _d, out = _tree()
    live, meta = _board(rows=False, state="live")
    rep, line = _attach(live, meta, out, "2026-10-22T20:10:00")
    assert rep and "kept" not in rep and _card_players(rep) == [], "nothing kept: the report written now"
    assert "started game" not in line, line
    path = K.path_for("nba", gate._full_dir_for(out))
    assert "MIA@BOS|2026-10-22" not in json.load(open(path))["games"], "a started game's new report is not kept"


def test_college_keeps_the_nights_reports_once_its_board_prices_none():
    _d, out = _tree()
    out = out.replace("nba.json", "cbb.json")
    board, meta = _board(sport="cbb")
    rep, _ = _attach(board, meta, out, "2026-10-22T10:00:00", sport="cbb")
    assert _card_players(rep) == ["Jayson Tatum"]
    over, meta2 = _board(rows=False, state="final", sport="cbb")
    assert over["board_games"] == []
    rep2, line = _attach(over, meta2, out, "2026-10-23T01:30:00", sport="cbb")
    assert rep2 is not None, f"the finished game keeps its report: {line}"
    assert rep2["kept"] == "Thu 10:00 AM ET" and _card_players(rep2) == ["Jayson Tatum"]


def test_started_reads_the_live_state_and_both_ways_the_boards_write_a_start():
    utc, et = K.stamps("2026-11-16T13:05:00")
    assert (utc, et) == ("2026-11-16T18:05:00+00:00", "2026-11-16T13:05:00"), "a plain stamp is Eastern"
    assert K.started({"live": {"state": "final"}, "date": "2026-11-20"}, utc)
    assert K.started({"date": "2026-11-16", "kickoff": "2026-11-16T18:00Z"}, utc), "an ISO start passed"
    assert not K.started({"date": "2026-11-16", "kickoff": "2026-11-16T18:30Z"}, utc)
    assert K.started({"date": "2026-11-16", "kickoff": "13:00"}, utc), "the NFL's bare Eastern clock"
    assert not K.started({"date": "2026-11-16", "kickoff": "16:25"}, utc)
    assert K.started({"date": "2026-11-12", "kickoff": "20:15"}, utc), "Thursday's game on Monday"
    assert not K.started({"date": "", "kickoff": "soon"}, utc), "unreadable is not started"
    assert not K.started(None, utc)


def test_off_the_board_and_past_its_day_a_game_leaves_and_a_broken_file_never_raises():
    _d, out = _tree()
    board, meta = _board()
    _attach(board, meta, out, "2026-10-22T10:00:00")
    path = K.path_for("nba", gate._full_dir_for(out))
    nxt, meta2 = _board()
    nxt["games"][0].update(date="2026-10-24", kickoff="2026-10-24T23:30:00Z")
    _attach(nxt, meta2, out, "2026-10-23T09:00:00")
    assert set(json.load(open(path))["games"]) == {"MIA@BOS|2026-10-22", "MIA@BOS|2026-10-24"}, \
        "a day past its date, off the board, still kept (a board that blinks empty loses nothing)"
    again, meta3 = _board()
    again["games"][0].update(date="2026-10-24", kickoff="2026-10-24T23:30:00Z")
    _attach(again, meta3, out, "2026-10-24T09:00:00")
    assert set(json.load(open(path))["games"]) == {"MIA@BOS|2026-10-24"}, "two days past and off the board: gone"
    Path(path).write_text("{not json", encoding="utf-8")
    rep, _ = _attach(*_board(rows=False, state="live"), out, "2026-10-22T20:10:00")
    assert rep and "kept" not in rep, "a broken file leaves the reports as built"
    reps, n = K.hold({"games": [{"away": "A", "home": "B", "date": "2026-10-22"}]}, [{"away": "A"}],
                     Path(tempfile.mkdtemp()) / "no" / "such" / "dir" / "x" / ".." / "k.json", "bad stamp")
    assert n == 0 and reps == [{"away": "A"}]


def test_a_doubleheader_s_two_games_are_each_written_and_neither_is_kept():
    path = Path(tempfile.mkdtemp()) / "reportkeep_mlb.json"
    g1 = {"away": "PHI", "home": "NYM", "date": "2026-09-12", "kickoff": "2026-09-12T17:10:00Z"}
    g2 = dict(g1, kickoff="2026-09-12T23:10:00Z")
    r1 = {"away": "PHI", "home": "NYM", "date": "2026-09-12", "game": "PHI@NYM", "n": 1}
    r2 = dict(r1, n=2)
    other = {"away": "BOS", "home": "NYY", "date": "2026-09-12", "game": "BOS@NYY", "n": 3}
    board = {"games": [g1, g2, {"away": "BOS", "home": "NYY", "date": "2026-09-12",
                                "kickoff": "2026-09-12T23:05:00Z"}]}
    reps, n = K.hold(board, [r1, r2, other], path, "2026-09-12T09:00:00")
    assert [r["n"] for r in reps] == [1, 2, 3] and n == 0, "no report lost to a shared key"
    assert set(json.load(open(path))["games"]) == {"BOS@NYY|2026-09-12"}, "the one game with its own key is kept"
    late = [dict(r1, n=4), dict(r2, n=5), dict(other, n=6)]
    reps2, n2 = K.hold(board, late, path, "2026-09-12T20:00:00")
    assert [r["n"] for r in reps2] == [4, 5, 3] and n2 == 1, [r["n"] for r in reps2]
    assert reps2[2]["kept"] == "Sat 9:00 AM ET"
    stray = {"away": "LAD", "home": "SD", "date": "2026-09-12", "n": 7}
    assert [r["n"] for r in K.hold(board, late + [stray], path, "2026-09-12T20:00:00")[0]] == [4, 5, 3, 7], \
        "a report the board's list does not name stays, after the rest"


def test_no_board_path_keeps_nothing():
    board, meta = _board()
    L.attach(board, "nba", meta=meta)
    live, meta2 = _board(rows=False, state="live")
    L.attach(live, "nba", meta=meta2)
    assert "kept" not in live["game_reports"][0] and _card_players(live["game_reports"][0]) == []
    assert R.keep_started({}, [{"x": 1}], "nba", None, None) == ([{"x": 1}], "")


def test_every_league_keeps_them_and_the_page_says_so():
    gr = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    lr = (ROOT / "engine" / "leaguereport.py").read_text(encoding="utf-8")
    for src in (gr, lr):
        a = src.index("reports, kept = keep_started(result, reports, sport, out, at, conn)")
        assert a < src.index("result[KEY] = reports", a) < src.index("n_bets = _lift_bets(result)", a), \
            "kept before the bets are lifted, so a kept report's bets reach the board"
    js = (ROOT / "web" / "js" / "report.js").read_text(encoding="utf-8")
    assert "as written before the game started, last updated ${escapeHtml(r.kept)}" in js
    assert "no prop picks in it" not in js, "the report has had its picks card since the method came in"


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
