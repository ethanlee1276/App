"""A team page's schedule game opens its game page when the game is on
tonight's board.

Ethan, 2026-09-25, the Jaguars page with the schedule strip circled: "we
should be able to click on these games, and then it'll take you to, like,
the live game page for this game where it shows all the data."

`teamGameDoor` puts the game-page door (`data-team-game`, the same one the
"On tonight's board" card uses) on the strip cell and the schedule row
for the game the board carries. A game not on the board — a final from an
earlier week, a week still to come — has no game page yet, so it opens
the opponent as before, and the schedule tab's caption says which is which.
"""
import json
import os
import shutil
import subprocess
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


BOARD = {"home": "JAX", "away": "NE", "date": "2026-09-27", "id": "ne-jax-0927"}
SCHED = [{"opponent": "DEN", "at_home": False, "final": True, "date": "2026-09-20", "result": "L"},
         {"opponent": "NE", "at_home": True, "final": False, "date": "2026-09-27"},
         {"opponent": "CIN", "at_home": False, "final": False, "date": "2026-10-04"}]


def _doors():
    if not shutil.which("node"):
        return None
    prog = ("var escapeAttr=(s)=>String(s==null?'':s), teamNameIn=(sp,t)=>t, gameId=(g)=>g.id;\n"
            f"var state={{sport:'nfl', data:{{games:[{json.dumps(BOARD)}]}}}};\n"
            + _fn("teamOnBoard") + _fn("teamGameDoor")
            + f"\nvar d={{sport:'nfl'}}, p={{team:'JAX'}};"
            f"\nconsole.log(JSON.stringify({json.dumps(SCHED)}.map((g) => teamGameDoor(d, p, g))));")
    path = os.path.join(tempfile.mkdtemp(), "d.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(prog)
    out = subprocess.run(["node", path], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-600:]
    return json.loads(out.stdout)


def test_the_board_game_opens_its_page_and_the_others_open_the_opponent():
    got = _doors()
    if got is None:
        return
    past, tonight, later = got
    assert 'data-team-game="ne-jax-0927"' in tonight and 'title="Game page"' in tonight, tonight
    assert 'data-team-open="DEN"' in past and "data-team-game" not in past
    assert 'data-team-open="CIN"' in later and "data-team-game" not in later


def test_the_strip_the_rows_and_the_caption_use_it():
    home = _fn("teamHomeHTML")
    assert 'class="tm-cell${i === next ? " next" : ""}"${teamGameDoor(d, p, g)}>' in home
    assert "teamScheduleRowHTML(d, x, p)" in home, "the Last 5 rows too"
    assert "function teamScheduleRowHTML(d, g, p)" in APP
    assert "const door = p ? teamGameDoor(d, p, g)" in APP
    sched = _fn("teamScheduleHTML")
    assert "teamScheduleRowHTML(d, g, p)" in sched
    assert "the game on tonight’s board opens its game page, every other row opens the opponent" in sched
    # …and the door is the board card's own.
    assert 'if (gameBtn) return openGame(gameBtn.dataset.teamGame);' in APP


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
