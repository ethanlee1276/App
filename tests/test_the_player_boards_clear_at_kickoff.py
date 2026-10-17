"""The player boards clear at kickoff, the way the picks do.

Ethan, 2026-10-05: "For this board, we need to clear out all the players
once the game starts and is over just like how we do with the picks."

The picks left the board at kickoff (`rowStarted`, 2026-09-27). The boards
of PLAYERS did not: who could shine or struggle, the touchdown scenarios,
the matchup picks and the long-shot scorers kept every game's players
until the next rebuild, finished games included. Checks, executed in node
against the page's own functions: a started or finished game's players
leave every one of those boards, an upcoming game's stay, and an unknown
kickoff is not treated as started.

Run directly: `python3 tests/test_the_player_boards_clear_at_kickoff.py`
"""
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _fn(name):
    i = JS.index(f"function {name}(")
    depth, j = 0, JS.index("{", i)
    for k in range(j, len(JS)):
        if JS[k] == "{":
            depth += 1
        elif JS[k] == "}":
            depth -= 1
            if depth == 0:
                return JS[i:k + 1]
    raise AssertionError(name)


def _run(body):
    node = shutil.which("node")
    if not node:
        print("  (node not installed — skipped)")
        return None
    prog = "\n".join(_fn(n) for n in ("likelyStarted", "rowStarted", "gameKickedOff", "gameKeyStarted",
                                      "scanTopRows")) + "\n" + body
    out = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


SETUP = """
const past = new Date(Date.now() - 4 * 3600e3).toISOString();
const soon = new Date(Date.now() + 3 * 3600e3).toISOString();
var state = { data: {
  games: [
    { away: "NYJ", home: "DET", kickoff: past, live: { state: "final" } },   // over
    { away: "LAC", home: "BUF", kickoff: past },                               // under way
    { away: "SEA", home: "LA", kickoff: soon },                                // upcoming
    { away: "KC", home: "DEN" },                                               // no kickoff known
  ],
  scan_reads: {
    "NYJ@DET": { players: [{ player: "Garrett Wilson", team: "NYJ", read: "good" }] },
    "LAC@BUF": { players: [{ player: "Ladd McConkey", team: "LAC", read: "breakout" }] },
    "SEA@LA":  { players: [{ player: "Puka Nacua", team: "LA", read: "good" }] },
    "KC@DEN":  { players: [{ player: "Travis Kelce", team: "KC", read: "tough" }] },
  },
}};
"""


def test_the_shine_and_struggle_board_drops_started_and_finished_games():
    got = _run(SETUP + "console.log(JSON.stringify(scanTopRows(state.data).map((x) => x.player)));")
    if got is None:
        return
    assert got == ["Puka Nacua", "Travis Kelce"], got


def test_a_game_is_matched_by_its_two_teams():
    got = _run(SETUP + """console.log(JSON.stringify([
      gameKeyStarted("NYJ@DET"), gameKeyStarted("LAC@BUF"), gameKeyStarted("SEA@LA"),
      gameKeyStarted("KC@DEN"), gameKeyStarted("XXX@YYY"), gameKeyStarted("")]));""")
    if got is None:
        return
    assert got == [True, True, False, False, False, False], got


def test_the_scorer_and_scenario_rows_clear_by_their_team():
    got = _run(SETUP + """console.log(JSON.stringify([
      rowStarted({ player: "Breece Hall", team: "NYJ" }),
      rowStarted({ player: "Kenneth Walker", team: "SEA" })]));""")
    if got is None:
        return
    assert got == [True, False], got


def test_every_player_board_applies_the_rule():
    """Source-pinned, because each board's renderer touches the DOM."""
    assert "if (gameKickedOff(g)) continue;" in _fn("scanTopRows")
    assert "!gameKeyStarted(r.game) && !rowStarted(r)" in _fn("tdScenariosHTML")
    assert "!gameKeyStarted(`${m.away}@${m.home}`)" in _fn("matchupPicksHTML")
    ls = _fn("renderLongShots")
    assert "(state.data.long_shots || []).filter((r) => !rowStarted(r))" in ls
    assert "(state.data.longshot_watch || []).filter((r) => !rowStarted(r))" in ls


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
