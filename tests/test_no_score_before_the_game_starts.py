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

APP = app_js()
JS = lambda f: open(os.path.join(ROOT, "web", "js", f), encoding="utf-8").read()  # noqa: E731
DETAIL, CHAT = JS("detail.js"), JS("chat.js")
FAR = "2099-11-15T18:00:00Z"            # a 1:00 PM kickoff, far enough off to say its time
NOW = 1_800_000_000_000                 # the clock the board code reads, held still


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


def _boards(calls):
    """The boards' own code in node (detail.js, from PBP_BOARD to the page),
    with every league's team table and the page's helpers stubbed, as
    test_the_boards_come_alive.py and test_the_arenas_come_alive.py run it;
    each call's drawing comes back as its lit words."""
    i = DETAIL.index("const PBP_BOARD = ")
    src = DETAIL[i:DETAIL.index("async function renderPbpPage(", i)]
    tables = "".join(JS(f) + "\n" for f in ("teams.js", "teams_mlb.js", "teams_nba.js", "teams_wnba.js", "teams_nhl.js"))
    js = (tables + "globalThis.teamsForSport = (l) => ({ mlb: MLB_TEAMS, nba: NBA_TEAMS, wnba: WNBA_TEAMS, nhl: NHL_TEAMS,"
          " nfl: TEAMS })[l] || {};\n"
          + "globalThis.escapeHtml = (s) => String(s).replace(/[&<>\"']/g, (c) => `&#${c.charCodeAt(0)};`);\n"
          + "globalThis.liveHoldWord = (lv) => (lv || {}).hold ? String(lv.hold) : '';\n"
          + "globalThis.tzTime = () => '7:30 PM';\n"
          + f"Date.now = () => {NOW};\n"
          + src.replace("\nconst ", "\nvar ").replace("\nlet ", "\nvar ")
          + f"\nprocess.stdout.write(JSON.stringify([{', '.join(calls)}]));")
    got = _run(js)
    if got is None:
        return None
    return [[html.unescape(re.sub(r"<[^>]+>", "", t)).strip()
             for t in re.findall(r"<text[^>]*>(.*?)</text>", svg, flags=re.S)] for svg in got]


def _fb(live):
    d = {"away": "TB", "home": "DAL", "live": live, "plays": [{"kind": "football", "id": "p1", "event": "Rush"}]}
    return f"pbpBoardSVG({json.dumps(d)}, 'nfl')"


def _mlb(live):
    return f"pbpBoardSVG({json.dumps({'away': 'TBR', 'home': 'MIL', 'live': live, 'events': []})}, 'mlb', null)"


def _arena(league, live, away=None, home=None):
    d = {"away": away or ("NYR" if league == "nhl" else "LAL"), "home": home or "BOS", "live": live}
    if league == "nhl":
        d["rink"] = {"events": [{"id": 1, "kind": "faceoff", "team": "NYR", "sc": "1551"}]}
    else:
        d["plays"] = [{"kind": "hoops", "id": "1", "event": "Jump Shot"}]
    return f"pbpArenaSVG({json.dumps(d)}, {json.dumps(league)}, {{}})"


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
    got = _boards([_fb(zeros), _mlb(zeros), _fb(dict(zeros, state="live", period="Q1", clock="15:00")),
                   _mlb(dict(zeros, state="live", period="Top 1st"))])
    if got is None:
        return
    fb_pre, mlb_pre, fb_live, mlb_live = got
    assert not any(w.isdigit() for w in fb_pre), ("no score on the football board before kickoff", fb_pre)
    assert not any(w.isdigit() for w in mlb_pre), ("no runs on the baseball board before first pitch", mlb_pre)
    assert fb_live.count("0") == 2, ("the first snap's 0-0 is a score", fb_live)
    assert mlb_live.count("0") == 2, ("so is the first inning's", mlb_live)


def test_the_arenas_say_the_names_alone_before_the_tip_and_the_drop():
    zeros = {"state": "scheduled", "start_time": "2099-01-01T00:30:00Z", "away_score": 0, "home_score": 0}
    got = _boards([_arena("nba", zeros), _arena("cbb", zeros, away="DUKE", home="UNC"), _arena("nhl", zeros)])
    if got is None:
        return
    nba, cbb, nhl = got
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
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
