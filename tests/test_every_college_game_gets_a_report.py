"""Every college basketball game still to tip gets a game report (step AEM, 24 November 2026).

Ethan's decision B, 24 November 2026: "we always want every sport posting props and bets and game reports at all
times for every games so we learn and dial in and calibrate and all that shit too make our picks better."

College basketball wrote a report for the games it prices alone (`nba_build.college_board_games`, five a night):
that evening, 7 reports for 87 games. Now:

  * every game still to tip has a report; a priced game's is as before, every other game's reads the two teams
    (the tale of the tape, its key matchups with their claims, graded on the box score once the game is final) and
    the betting market, and says in its facts that its players are not read and why;
  * such a report is marked (`scope: teams`) and the heartbeat counts them (`reports_teams_only`);
  * a game already under way when first seen is not written (a report written after the tip is no pregame call),
    and one kept from before its start comes back as it was;
  * the NBA, which prices every game it carries, is unchanged.

Offline. Run directly: `python3 tests/test_every_college_game_gets_a_report.py`
"""
import copy
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import leaguereport as L                                 # noqa: E402

TAPE = {"rows": [{"key": "pts", "label": "Points a game", "a": "74.1", "h": "80.7", "ar": 250, "hr": 92, "plain": False},
                 {"key": "ortg", "label": "Offense: points per 100 possessions", "a": "108.7", "h": "111.6",
                  "ar": 199, "hr": 131, "plain": False},
                 {"key": "pace", "label": "Pace: possessions per 40 minutes", "a": "67.0", "h": "71.6", "ar": 321,
                  "hr": 91, "plain": True},
                 {"key": "oreb_pct", "label": "Offensive rebounding (share of misses)", "a": "34.8%",
                  "h": "38.8%", "ar": 44, "hr": 6, "plain": False}],
        # The scan's own shape (engine/nba/scan), as the board carried it for Robert Morris at Lamar that night.
        "edges": [{"team": "LAM", "tone": "off", "gap": 261, "unit": "oreb_pct", "order": 3,
                   "matchup": "LAM's offensive rebounding (6th) against RMU's defensive rebounding (267th)",
                   "text": "Edge LAM: LAM's offensive rebounding (6th) against RMU's defensive rebounding (267th)",
                   "off": "LAM", "def": "RMU", "off_unit": "oreb_pct", "base": 0.3877}],
        "teams": 366, "per100": True, "basis": "Ranks out of 366, 1st the best"}


def _game(away, home, kickoff, state=None, **more):
    g = {"away": away, "home": home, "date": "2026-11-24", "kickoff": kickoff,
         "live": {"state": state, "away_score": 30, "home_score": 41} if state else None,
         "home_name": f"{home} Name", "away_name": f"{away} Name", "nba_tape": copy.deepcopy(TAPE)}
    g.update(more)
    return g


def _board():
    """A college night: one priced game, one still to tip that the board does not price, one under way."""
    games = [_game("VAN", "OSU", "2026-11-25T00:00Z", spread=-4.5, total=151.5, home_ml=-190, away_ml=160),
             _game("RMU", "LAM", "2026-11-24T23:30Z"),
             _game("PROV", "ARIZ", "2026-11-24T22:00Z", state="live")]
    teams = {c: {"loc": n} for c, n in (("VAN", "Vanderbilt"), ("OSU", "Ohio State"), ("RMU", "Robert Morris"),
                                        ("LAM", "Lamar"), ("PROV", "Providence"), ("ARIZ", "Arizona"))}
    return {"sport": "cbb", "date": "2026-11-24", "games": games, "teams": teams, "board_games": ["VAN@OSU"]}


def _tree():
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "web", "data"))
    return os.path.join(d, "web", "data", "cbb.json")


def _facts(rep):
    s = next(s for s in rep["sections"] if s["key"] == "facts")
    return [t for b in s["blocks"] for t in b.get("items") or []]


def test_every_game_still_to_tip_gets_a_report_and_a_game_under_way_is_not_written():
    board = _board()
    line = L.attach(board, "cbb", meta={}, out=None, at="2026-11-24T17:30:00")
    reps = {f"{r['away']}@{r['home']}": r for r in board["game_reports"]}
    assert set(reps) == {"VAN@OSU", "RMU@LAM"}, (set(reps), line)
    assert "PROV@ARIZ" not in reps, "under way when first seen: a report written now would be no pregame call"
    assert reps["RMU@LAM"][L.SCOPE_KEY] == L.TEAMS_ONLY and L.SCOPE_KEY not in reps["VAN@OSU"]
    assert line.startswith("Game reports: 2 game(s)"), line


def test_a_teams_only_report_reads_the_tape_and_says_its_players_are_not_read():
    board = _board()
    L.attach(board, "cbb", meta={}, out=None, at="2026-11-24T17:30:00")
    rep = next(r for r in board["game_reports"] if r["home"] == "LAM")
    keys = [s["key"] for s in rep["sections"]]
    assert "tape" in keys and "facts" in keys, keys
    assert ("Players: not read for this game. Tonight we read players and buy player prices for the game we price, "
            "the ranked and power-conference games first; this report reads the two teams and the betting market."
            ) in _facts(rep), _facts(rep)
    tape = next(s for s in rep["sections"] if s["key"] == "tape")
    claims = [c for b in tape["blocks"] for c in (b.get("claims") or []) if c]
    assert claims and all(c.get("kind") == "unit" for c in claims), \
        "its key matchups carry the claims the box score grades once the game is final"
    priced = next(r for r in board["game_reports"] if r["home"] == "OSU")
    assert not any(t.startswith("Players:") for t in _facts(priced)), "a priced game's report reads its players"


def test_the_line_counts_the_nights_priced_games():
    c = type("C", (), {})()
    c.sport, c.away, c.home = "cbb", "RMU", "LAM"
    c.result = {"board_games": ["A@B", "C@D", "E@F", "G@H", "I@J"]}
    assert "for the 5 games we price" in L.teams_only_line(c)
    c.result = {"board_games": []}
    assert L.teams_only_line(c) == ("Players: not read for this game; this report reads the two teams and the "
                                    "betting market"), "past the last tip nothing is priced"
    c.result = {"board_games": ["RMU@LAM"]}
    assert L.teams_only_line(c) == ""
    c.sport, c.result = "nba", {"board_games": []}
    assert L.teams_only_line(c) == "", "the NBA prices every game it carries"


def test_a_game_written_before_its_tip_keeps_that_report_once_under_way():
    out = _tree()
    board = _board()
    L.attach(board, "cbb", meta={}, out=out, at="2026-11-24T17:30:00")
    later = _board()
    for g in later["games"]:
        if g["home"] == "LAM":
            g["live"] = {"state": "live", "away_score": 10, "home_score": 12}
    later["board_games"] = []                              # the board's priced game went to the cache's side
    line = L.attach(later, "cbb", meta={}, out=out, at="2026-11-24T18:45:00")
    reps = {f"{r['away']}@{r['home']}": r for r in later["game_reports"]}
    assert reps["RMU@LAM"].get("kept") == "Tue 5:30 PM ET", (reps["RMU@LAM"].get("kept"), line)
    assert reps["RMU@LAM"][L.SCOPE_KEY] == L.TEAMS_ONLY, "kept as written, its mark with it"
    assert "PROV@ARIZ" not in reps, "nothing kept for a game first seen under way, and nothing written for it"


def test_the_heartbeat_counts_the_teams_only_reports():
    import launch
    board = _board()
    L.attach(board, "cbb", meta={}, out=None, at="2026-11-24T17:30:00")
    d = tempfile.mkdtemp()
    path = os.path.join(d, "cbb.json")
    with open(path, "w") as fh:
        json.dump(board, fh)
    got = launch._board_counts(path)
    assert got["reports"] == 2 and got["reports_teams_only"] == 1, got
    nba = {"sport": "nba", "game_reports": [{"away": "MIA", "home": "BOS", "sections": []}]}
    with open(path, "w") as fh:
        json.dump(nba, fh)
    assert "reports_teams_only" not in launch._board_counts(path)


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
