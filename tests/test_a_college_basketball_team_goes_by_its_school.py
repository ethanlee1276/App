"""A college basketball team goes by its school, as college football's does
(USEREYES1, 18 November 2026).

Walking a finished college basketball game: its header said "Scarlet Knights
73 @ Cougars 85" while the report under it said Rutgers and Houston, and the
Pick of the Day said "Wildcats -1.5 Spread · Wildcats vs Panthers", a bet no
one could place without knowing which of a dozen Wildcats it meant. College
football's table names the school (ESPN's short name as `nick`), and the
basketball report and the record already did; only college basketball's
table carried ESPN's mascot as `nick`, which every page prints. What these
hold:

  * a college basketball card's `nick` is its school: ESPN's short name, else
    its location; tonight's (`cbbespn.teams_from_games`) and every card kept
    from before (`cbbteams.cards`), so a school not on tonight's slate is
    named the same way;
  * the scoreboards that show two names put the mascot over the school, as
    college football's does: the play-by-play page's and the live
    basketball page's;
  * the Pick of the Day's empty-board note is in plain words.

    python3 tests/test_a_college_basketball_team_goes_by_its_school.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import cbbteams, potd                                             # noqa: E402
from engine.sources import cbbespn                                           # noqa: E402

HOU = {"name": "Houston Cougars", "short": "Houston", "loc": "Houston", "nick": "Cougars", "abbr": "HOU"}
ACU = {"name": "Abilene Christian Wildcats", "short": "Abilene Chrstn", "loc": "Abilene Christian",
       "nick": "Wildcats", "abbr": "ACU"}


def test_a_card_is_named_by_its_school():
    assert cbbteams.school_named(HOU)["nick"] == "Houston"
    assert cbbteams.school_named(ACU)["nick"] == "Abilene Chrstn", "ESPN's short name, as college football's"
    assert cbbteams.school_named({"loc": "Rutgers", "nick": "Scarlet Knights"})["nick"] == "Rutgers"
    assert cbbteams.school_named({"name": "X Y", "nick": "Y"}) == {"name": "X Y", "nick": "Y"}, "no school: as it was"
    assert cbbteams.school_named(HOU)["name"] == "Houston Cougars", "the full name keeps the mascot"


def test_tonights_table_and_the_kept_cards_both_say_the_school():
    games = [{"home": "HOU", "away": "ACU", "home_info": HOU, "away_info": ACU, "home_id": "248", "away_id": "2000"}]
    got = cbbespn.teams_from_games(games)
    assert got["HOU"]["nick"] == "Houston" and got["ACU"]["nick"] == "Abilene Chrstn", got
    path = os.path.join(tempfile.mkdtemp(), "cbb_cards.json")
    # A card kept before 18 November carries the mascot: read, it says the school.
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"teams": {"RUTG": {"name": "Rutgers Scarlet Knights", "nick": "Scarlet Knights",
                                      "loc": "Rutgers", "short": "Rutgers"}}}, fh)
    assert cbbteams.cards(path)["RUTG"]["nick"] == "Rutgers"
    assert cbbteams.remember_cards(got, path) == 2
    kept = cbbteams.cards(path)
    assert kept["HOU"]["nick"] == "Houston" and kept["RUTG"]["nick"] == "Rutgers", kept
    assert cbbteams.remember_cards(got, path) == 0, "the same night again changes nothing"


def _fn(src, name):
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 3]


def test_the_scoreboards_put_the_mascot_over_the_school():
    """One scoreboard since step AAI (21 November): the basketball page drew its own, with its own `mascot`; every
    sport's score is the page's now (detail.js pbpBoardHTML), which names a college side the same way."""
    node = shutil.which("node") or "/opt/node22/bin/node"
    detail = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
    hoops = (ROOT / "web" / "js" / "hoopscast.js").read_text(encoding="utf-8")
    assert "const mascot" not in hoops and "hc-loc" not in hoops and "scoreboardHTML" not in hoops
    board = _fn(detail, "pbpBoardHTML")
    assert "const { big, small } = pbpSideNames(league, t, full);" in board
    assert 'if (league === "cbb") pbpCbbTeamsWarm();' in board, "a college game opened from a link reads its schools once"
    if not os.path.exists(node):
        return
    hou = dict(HOU, nick="Houston")
    acu = dict(ACU, nick="Abilene Chrstn")
    js = (_fn(detail, "pbpSideNames")
          + f"process.stdout.write(JSON.stringify([pbpSideNames('cbb', {json.dumps(hou)}, 'x'),"
            f" pbpSideNames('cbb', {json.dumps(acu)}, 'x'),"
            f" pbpSideNames('nba', {{nick: 'Celtics', name: 'Boston Celtics', loc: 'Boston'}}, 'x'),"
            f" pbpSideNames('cbb', {{name: 'Duke', nick: 'Duke'}}, 'x')]));")
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    h, a, nba, none = json.loads(out.stdout)
    assert h == {"big": "Houston", "small": "Cougars"}, h
    assert a == {"big": "Abilene Chrstn", "small": "Wildcats"}, "the mascot found past the long school name"
    assert nba == {"big": "Celtics", "small": "Boston"}, "a pro club as it was"
    assert none == {"big": "Duke", "small": ""}, "a school with no mascot after its name says none"


def test_the_empty_board_note_is_plain():
    assert potd.build([], "cbb", "2026-11-18")["note"] == "No pick today: nothing is on the board yet"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
