"""A team page's schedule game opens its game page.

Ethan, 2026-09-25, the Jaguars page with the schedule strip circled: "we
should be able to click on these games, and then it'll take you to, like,
the live game page for this game where it shows all the data."

`teamGameDoor` puts the game-page door (`data-team-game`, the same one the
"On tonight's board" card uses) on the strip cell and the schedule row
for the game the board carries. A game not on the board — a final from an
earlier week, a week still to come — has no game page yet, so it opens
the opponent as before, and the schedule tab's caption says which is which.

2026-10-30, Ethan with ESPN's Panthers @ Packers final: "We should be able
to go to each specific game and see all this type of data that espn
offers." A final has a game page now (engine/gamearchive, /api/game): its
row carries the past-game door (`data-past-game`, with the day and the two
sides the server finds it by — tests/test_every_game_has_a_page.py). Only a
week still to come opens the opponent.
"""
import json
import os
import shutil
import subprocess
import tempfile
from _app import app_js  # noqa: E402  (app.js and the rooms it loads on first use)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = app_js()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


BOARD = {"home": "JAX", "away": "NE", "date": "2026-09-27", "id": "ne-jax-0927"}
SCHED = [{"opponent": "DEN", "at_home": False, "final": True, "date": "2026-09-20", "result": "L",
          "home": "DEN", "away": "JAX", "game_id": "2026_02_JAX_DEN"},
         {"opponent": "NE", "at_home": True, "final": False, "date": "2026-09-27"},
         {"opponent": "CIN", "at_home": False, "final": False, "date": "2026-10-04"}]


def _line(start):
    i = APP.index(start)
    return APP[i:APP.index("\n", i) + 1]


def _doors():
    if not shutil.which("node"):
        return None
    prog = ("var escapeAttr=(s)=>String(s==null?'':s), teamNameIn=(sp,t)=>t, gameId=(g)=>g.id;\n"
            f"var state={{sport:'nfl', data:{{games:[{json.dumps(BOARD)}]}}}};\n"
            + _line("const PAST_GAME_LEAGUES = ") + _fn("teamPastGameAttrs")
            + _fn("teamOnBoard") + _fn("teamGameDoor")
            + f"\nvar d={{sport:'nfl'}}, p={{team:'JAX'}};"
            f"\nconsole.log(JSON.stringify({json.dumps(SCHED)}.map((g) => teamGameDoor(d, p, g))));")
    path = os.path.join(tempfile.mkdtemp(), "d.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(prog)
    out = subprocess.run(["node", path], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-600:]
    return json.loads(out.stdout)


def test_the_board_game_and_every_final_open_a_page_and_the_rest_the_opponent():
    got = _doors()
    if got is None:
        return
    past, tonight, later = got
    assert 'data-team-game="ne-jax-0927"' in tonight and 'title="Game page"' in tonight, tonight
    for want in ('data-past-game="nfl"', 'data-pg-date="2026-09-20"', 'data-pg-home="DEN"', 'data-pg-away="JAX"',
                 'data-pg-id="2026_02_JAX_DEN"', 'title="Game page"'):
        assert want in past, (want, past)
    assert "data-team-open" not in past and "data-team-game" not in past, past
    assert 'data-team-open="CIN"' in later and "data-team-game" not in later


def test_the_strip_the_rows_and_the_caption_use_it():
    home = _fn("teamHomeHTML")
    assert 'class="tm-cell${i === next ? " next" : ""}"${teamGameDoor(d, p, g)}>' in home
    assert "teamScheduleRowHTML(d, x, p)" in home, "the Last 5 rows too"
    assert "function teamScheduleRowHTML(d, g, p)" in APP
    assert "const door = p ? teamGameDoor(d, p, g)" in APP
    sched = _fn("teamScheduleHTML")
    assert "teamScheduleRowHTML(d, g, p)" in sched
    assert "every game played opens its own page" in sched
    assert "tonight’s game opens its board, and a game still to come opens the opponent" in sched
    # …and the door is the board card's own.
    assert 'if (gameBtn) return openGame(gameBtn.dataset.teamGame);' in APP


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
