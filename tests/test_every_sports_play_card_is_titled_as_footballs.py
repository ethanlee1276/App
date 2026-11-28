"""Every sport's play card is titled as football's: its side and what happened, its players on lines of their own.

Ethan, 2026-11-23: "We want all the live pages to match each other ... NFL is
kind of like the one we want to go off of." The Live tab's Play feed (and a
game room's play cards, js/chat.js pcBodyHTML) titled a football play by its
side and what happened ("CIN Pass intercepted"), each player on a line under
it with their game so far, and a baseball play by what happened. A basketball
card read "Coby White — Jump Shot", a made three not saying it was one, and a
hockey card "NJD Goal — Nico Hischier", its player on no line when the box had
no line for them. Now every card's title is its side and what happened ("MEM
Three-pointer", "NJD Goal") with its players on their own lines, and a
thread's label and a shared play add whose play it was (`pcNamed`: "MEM
Three-pointer — Coby White").

Offline. Run directly: `python3 tests/test_every_sports_play_card_is_titled_as_footballs.py`
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
CHAT = (ROOT / "web" / "js" / "chat.js").read_text(encoding="utf-8")


def _fn(name):
    i = CHAT.index(f"function {name}(")
    return CHAT[i:CHAT.index("\n}\n", i) + 3]


def _const(name):
    i = CHAT.index(f"const {name} = ")
    return CHAT[i:CHAT.index(";\n", i) + 2]


def _run(body):
    node = shutil.which("node")
    if not node:
        return None
    js = "\n".join([
        "const chEsc = (s) => String(s == null ? '' : s);",
        "const chatPlayKey = (p) => String(p.id || p.at_bat || '');",
        "const footballWords = (p) => ({ title: p.event === 'Pass Interception Return' ? 'Pass intercepted' : p.event });",
        "const playerAvatar = (n, t, o) => `<i data-a='${n}'></i>`;",
        "const espnFace = () => '';",
        _const("PLAY_RINK_WORD"), _const("PLAY_ICE_WORD"), _fn("hoopsWhat"), _fn("playTitleOf"),
        _const("PC_SWING"), _const("PC_SFX"), _const("pcOrd"), _const("pcShort"), _const("pcNorm"),
        _fn("pcBox"), _fn("pcLine"), _fn("pcPeople"), _fn("pcTitle"), _fn("pcNamed"), _fn("pcWin"), _fn("pcFacts"),
        _fn("pcBodyHTML"), body])
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(js)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _hoops(event, *, made=False, shot=True, tried=2, team="MEM", who=("Coby White",)):
    return {"kind": "hoops", "id": event, "team": team, "player": who[0], "players": list(who), "event": event,
            "scoring": made, "shot": shot, "points": tried if made else 0, "points_attempted": tried}


CASES = [
    (_hoops("Running Jump Shot", made=True, tried=3, who=("Coby White", "Brandon Miller")), "MEM Three-pointer"),
    (_hoops("Pullup Jump Shot", tried=3), "MEM Missed three-pointer"),
    (_hoops("Dunk Shot", made=True), "MEM Dunk"),
    (_hoops("Alley Oop Dunk Shot", made=True), "MEM Alley-oop"),
    (_hoops("Driving Dunk Shot"), "MEM Missed dunk"),
    (_hoops("LayUpShot", made=True), "MEM Layup"),
    (_hoops("Free Throw", made=True, tried=1), "MEM Free throw"),
    (_hoops("Technical Foul", shot=False, tried=0), "MEM Technical foul"),
    (_hoops("Flagrant Foul Type 1", shot=False, tried=0), "MEM Flagrant foul"),
    (_hoops("Bad Pass Turnover", shot=False, tried=0), "MEM Turnover"),
    (_hoops("Offensive Rebound", shot=False, tried=0), "MEM Offensive rebound"),
    (_hoops("Block", shot=False, tried=0, team="espn:2047"), "Block"),
    ({"kind": "hockey", "id": "g1", "team": "NJD", "player": "Nico Hischier", "event": "Goal", "scoring": True}, "NJD Goal"),
    ({"kind": "hockey", "id": "p1", "team": "CBJ", "player": "Dante Fabbro", "event": "Penalty"}, "CBJ Penalty"),
    ({"kind": "goal", "id": 9, "team": "NJD", "player": "Connor Brown"}, "NJD Goal"),
    ({"kind": "football", "id": "f1", "team": "CIN", "event": "Pass Interception Return",
      "players": ["Joe Burrow", "Quan Martin"]}, "CIN Pass intercepted"),
]


def test_every_card_is_titled_by_its_side_and_what_happened():
    got = _run(f"console.log(JSON.stringify({json.dumps([c[0] for c in CASES])}.map((p) => pcTitle(p, {{}}))));")
    if got is None:
        print("      (skipped: no node)")
        return
    for (play, want), title in zip(CASES, got):
        assert title == want, (play["event"] if "event" in play else play["kind"], title, want)


def test_its_players_are_on_lines_of_their_own_with_their_game_so_far():
    game = {"home": "CHA", "away": "MEM", "players": [{"player": "Coby White", "stats": {"pts": 18, "reb": 4, "ast": 3}}]}
    three = CASES[0][0]
    goal = CASES[12][0]
    got = _run(f"""console.log(JSON.stringify([pcBodyHTML({json.dumps(three)}, {json.dumps(game)}, [], false, "nba"),
      pcBodyHTML({json.dumps(goal)}, {{ home: "NJD", away: "CBJ", players: [] }}, [], false, "nhl")]));""")
    if got is None:
        return
    assert '<p class="pcard-title">MEM Three-pointer</p>' in got[0]
    assert '<span class="pcard-line"><b>C. White</b> · 18 pts, 4 reb, 3 ast</span>' in got[0]
    # A player the box has no line for yet is still named, as football's kicker is.
    assert '<p class="pcard-title">NJD Goal</p>' in got[1] and '<span class="pcard-line"><b>N. Hischier</b></span>' in got[1]


def test_a_thread_and_a_shared_play_say_whose_it_was():
    walkoff = {"kind": "atbat", "at_bat": 71, "event": "Home Run", "rbi": 3, "distance": 416, "half": "B", "inning": 10,
               "batter": "Pete Alonso", "pitcher": "Pete Fairbanks", "swing": "walkoff"}
    plays = [CASES[0][0], CASES[12][0], CASES[14][0], CASES[15][0], walkoff]
    got = _run(f"console.log(JSON.stringify({json.dumps(plays)}.map((p) => pcNamed(p, {{}}))));")
    if got is None:
        return
    assert got == ["MEM Three-pointer — Coby White", "NJD Goal — Nico Hischier", "NJD Goal — Connor Brown",
                   "CIN Pass intercepted — Joe Burrow", "Walk-off 416-ft 3-run homer — Pete Alonso"], got
    assert "const chatPlayTitle = (p) => pcNamed(p, CH.d || {});" in CHAT
    assert "pcShareHTML(sport, event, p, `${pcNamed(p, g)} · ${score}`)" in CHAT, "the Live tab's feed shares it named"
    assert "pcShareHTML(CH.league, CH.event, p, `${pcNamed(p, d)}${score ? ` · ${score}` : \"\"}`)" in CHAT
    assert "const named =" not in _fn("pcBodyHTML"), "every sport's players are named on their lines"


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
