"""No score on a game that has not started.

Ethan, 2026-11-15, circling the strip of games across the top of the live
page, where the 1:00 PM games each read 0 and 0: "we should not be showing
scores here if the games have not started yet." ESPN's scoreboard fills "0"
for a game not yet under way, and engine/sources/livescores.parse keeps it.
So every chip, board and header that printed whatever the feed held showed
0-0 at 1:00 PM. Now a score shows only once a game is live or over (app.js
scoreShown). That covers the strip, the baseball and football boards, the
arenas, the second screen and the game chat's header. The game cards
already asked (gameCardHTML's `score`).
"""
import html
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from _app import app_js  # noqa: E402  (app.js and the rooms it loads on first use)
from test_the_boards_come_alive import _node as boards_node, _fb, _mlb, _texts  # noqa: E402
from test_the_arenas_come_alive import _node as arenas_node, _arena  # noqa: E402

APP = app_js()
CHAT = open(os.path.join(ROOT, "web", "js", "chat.js"), encoding="utf-8").read()
FAR = "2099-11-15T18:00:00Z"            # a 1:00 PM kickoff, far enough off to say its time


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def _run(js):
    try:
        out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        print("      (skipped: no node)")
        return None
    assert out.returncode == 0, out.stderr[-800:]
    return json.loads(out.stdout)


def _strip(games):
    """pbpStripHTML in node, the page's helpers stubbed; each chip's two
    score cells, in order."""
    stubs = """
      const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
      const escapeAttr = escapeHtml, teamMarkIn = () => "", icon = () => "";
      const spoiledG = (l, g) => !!g.hid, pbpTime = () => "1:00 PM", pbpCountdown = () => "12:00";
      const gameId = (g) => `${g.away}@${g.home}`, PBP_COUNT_MS = 3600000;
      const state = { sport: "nfl", data: { games: [] } };
    """
    js = (stubs + _fn("scoreShown") + _fn("pbpStripHTML")
          + f"\nconst html = pbpStripHTML('nfl', {json.dumps(games)}, '');"
          + "\nconst chips = html.split('<button').slice(1);"
          + "\nprocess.stdout.write(JSON.stringify(chips.map((c) => [...c.matchAll(/<b>([^<]*)<\\/b>/g)].map((m) => m[1]))));")
    return _run(js)


def test_a_score_only_once_the_game_has_one():
    got = _run(_fn("scoreShown") + """
      process.stdout.write(JSON.stringify([scoreShown({ state: "scheduled", away_score: 0, home_score: 0 }),
        scoreShown({ state: "live", away_score: 0, home_score: 0 }), scoreShown({ state: "final" }),
        scoreShown({}), scoreShown(undefined)]));""")
    if got is None:
        return
    assert got == [False, True, True, False, False], got


def test_the_strip_leaves_a_game_not_started_blank():
    # The feed as it reads at 12:30 on a Sunday: the 1:00 PM games carry
    # ESPN's zeros, the early London game is on, last night's is over.
    games = [
        {"event_id": "1", "away": "TB", "home": "BUF", "live": {"state": "scheduled", "start_time": FAR,
                                                               "away_score": 0, "home_score": 0}},
        {"event_id": "2", "away": "LAC", "home": "JAX", "live": {"state": "scheduled", "start_time": FAR,
                                                                "away_score": 0, "home_score": 0}},
        {"event_id": "3", "away": "WSH", "home": "MIA", "live": {"state": "live", "period": "Q2",
                                                                "away_score": 0, "home_score": 7}},
        {"event_id": "4", "away": "NYJ", "home": "NE", "live": {"state": "final", "away_score": 24, "home_score": 21}},
        {"event_id": "5", "away": "KC", "home": "DEN", "hid": True,
         "live": {"state": "live", "away_score": 10, "home_score": 3}},
    ]
    got = _strip(games)
    if got is None:
        return
    assert got[0] == ["", ""] and got[1] == ["", ""], ("no 0-0 before kickoff", got)
    assert got[2] == ["0", "7"], ("a live 0 is a score", got)
    assert got[3] == ["24", "21"], got
    assert got[4] == ["", ""], "spoiler-free still hides it"


def test_the_boards_leave_the_zeros_off_before_the_first_snap_and_pitch():
    zeros = {"state": "scheduled", "start_time": FAR, "away_score": 0, "home_score": 0}
    got = boards_node("return [" + ", ".join([
        _fb(zeros), _mlb(zeros),
        _fb(dict(zeros, state="live", period="Q1", clock="15:00")),
        _mlb(dict(zeros, state="live", period="Top 1st")),
    ]) + "];")
    if got is None:
        return
    fb_pre, mlb_pre, fb_live, mlb_live = (_texts(s) for s in got)
    assert not any(w.isdigit() for w in fb_pre), ("no score on the football board before kickoff", fb_pre)
    assert not any(w.isdigit() for w in mlb_pre), ("no runs on the baseball board before first pitch", mlb_pre)
    assert fb_live.count("0") == 2, ("the first snap's 0-0 is a score", fb_live)
    assert mlb_live.count("0") == 2, ("so is the first inning's", mlb_live)


def test_the_arenas_say_the_names_alone_before_the_tip_and_the_drop():
    zeros = {"state": "scheduled", "start_time": "2099-01-01T00:30:00Z", "away_score": 0, "home_score": 0}
    got = arenas_node("return [" + ", ".join([
        _arena("nba", zeros), _arena("cbb", zeros, away="DUKE", home="UNC"), _arena("nhl", zeros),
    ]) + "];")
    if got is None:
        return
    nba, cbb, nhl = (_texts(s) for s in got)
    assert "LAL · TIP-OFF 7:30 PM · BOS" in nba, nba
    assert not any("LAL 0" in w or "BOS 0" in w for w in nba), nba
    assert not any("DUKE 0" in w or "UNC 0" in w for w in cbb), cbb
    assert "NYR · BOS" in nhl and not any("0 – 0" in w for w in nhl), nhl


def test_the_second_screen_and_the_chat_wait_for_a_score_too():
    big = _fn("pbpBigHTML")
    assert "side(d.away, scoreShown(lv) ? lv.away_score : null)" in big
    assert "side(d.home, scoreShown(lv) ? lv.home_score : null)" in big
    # The chat loads on its own, so it writes the rule out.
    assert 'const on = lv.state === "live" || lv.state === "final";' in CHAT
    assert "side(d.away, on ? lv.away_score : null, false)" in CHAT
    assert "side(d.home, on ? lv.home_score : null, true)" in CHAT
    # And the game cards keep asking, as they did.
    assert "(live.home_score != null && (isLive || isFinal))" in APP


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except AssertionError as e:
            fails += 1
            print(f"  FAIL {name}: {e}")
    print(f"{len(tests) - fails}/{len(tests)} passed")
    sys.exit(1 if fails else 0)
