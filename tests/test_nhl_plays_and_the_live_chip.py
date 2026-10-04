"""Hockey has a play-by-play, and the Live tab's NHL chip shows NHL bets.

Ethan, 2026-10-04: "Nhl play by plays are not working" and "MLB bets are
showing in the live tab for nhl bets". The league had no play source, so
every live hockey card said "No play-by-play source"; and the Live tab's
chip only switched the bets for leagues on the route list, which never
carried hockey — so NHL filtered the game cards and left the MLB bets.

Checks, one rule each: a live NHL game is fetched and its plays read as
hockey rows (period, clock, team, scorer, goal); a summary with no play
list says so instead of "No plays yet"; the page words hockey in periods
and goals on the card and on the full play-by-play page; the NHL chip
switches the league like every other chip.

Run directly: `python3 tests/test_nhl_plays_and_the_live_chip.py`
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import livescore_build as B                                         # noqa: E402
from engine.sources import espnplays as E                           # noqa: E402

EDM, CGY = "6", "3"


def _play(pid, *, period=1, clock="14:02", team=EDM, who="97", ptype="Shot",
          scoring=False, away=0, home=0):
    return {"id": pid, "period": {"number": period}, "clock": {"displayValue": clock},
            "team": {"id": team}, "participants": [{"athlete": {"id": who}}],
            "type": {"text": ptype}, "scoringPlay": scoring, "scoreValue": 1 if scoring else 0,
            "awayScore": away, "homeScore": home}


def _payload(with_plays=True):
    d = {"boxscore": {"players": [{"team": {"id": EDM, "abbreviation": "EDM"}, "statistics": [
        {"athletes": [{"athlete": {"id": "97", "displayName": "Connor McDavid"}}]}]}]}}
    if with_plays:
        d["plays"] = [_play("p1", ptype="Faceoff"), _play("p2"),
                      _play("p3", period=2, clock="8:15", ptype="Goal", scoring=True, home=1)]
    return d


def _games():
    return [{"event_id": "e0", "home": "EDM", "away": "CGY", "home_id": EDM, "away_id": CGY,
             "live": {"state": "live", "start_time": ""}},
            {"event_id": "s0", "home": "TOR", "away": "MTL",
             "live": {"state": "scheduled", "start_time": ""}}]


def _with_fetch(fn, games):
    real = E.fetch_summary
    E.fetch_summary = fn
    try:
        return B.attach_plays(games, "nhl")
    finally:
        E.fetch_summary = real


def test_a_live_hockey_game_is_fetched_and_reads_as_hockey():
    assert E.HOCKEY == ("nhl",) and "nhl" not in E.HOOPS
    asked = []

    def fn(league, eid, ttl=30):
        asked.append((league, eid))
        return _payload()
    games = _games()
    note = _with_fetch(fn, games)
    assert asked == [("nhl", "e0")], "only the live game, through the NHL summary"
    g = games[0]
    assert g["plays_state"] == "ok" and "no play-by-play source" not in note
    goal = g["plays"][-1]
    assert goal["kind"] == "hockey" and goal["period"] == 2 and goal["clock"] == "8:15"
    assert goal["scoring"] and goal["team"] == "EDM" and goal["event"] == "Goal"
    assert goal["home_score"] == 1
    assert games[1]["plays_state"] == "idle", "a scheduled game is not fetched"


def test_a_summary_without_plays_says_so():
    games = _games()
    note = _with_fetch(lambda league, eid, ttl=30: _payload(with_plays=False), games)
    assert games[0]["plays_state"] == "no_feed" and "plays" not in games[0]
    assert "no play list" in note, note


def _js(names):
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    out = []
    i = app.index("const PLAYS_EMPTY = {")
    out.append(app[i:app.index("};", i) + 2])
    for n in names:
        i = app.index(f"\nfunction {n}(") + 1
        j = app.find("\nfunction ", i + 10)
        k = app.find("\nconst ", i + 10)
        k2 = app.find("\n/*", i + 10)
        out.append(app[i:min(x for x in (j, k, k2) if x != -1)])
    return "\n".join(out)


def test_the_page_words_hockey_in_periods_and_goals():
    node = shutil.which("node")
    if not node:
        return
    rows = E.hoops_plays(_payload(), "nhl", 0, sides={EDM: "EDM", CGY: "CGY"})
    prog = (_js(["playsHTML", "pbpGroups"])
            + "\nconst escapeHtml = (s) => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;');"
            + "\nconst trueMinus = (s) => s;"
            + f"\nconst rows = {json.dumps(rows)};"
            + "\nconsole.log(playsHTML({plays: rows, plays_state: 'ok'}));"
            + "\nconsole.log('@@' + playsHTML({plays: [], plays_state: 'no_feed'}));"
            + "\nconsole.log('@@' + JSON.stringify(pbpGroups({league: 'nhl', plays: rows}).map(g => g.head)));")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
    out = subprocess.run([node, fh.name], capture_output=True, text=True, timeout=30)
    os.unlink(fh.name)
    assert out.returncode == 0, out.stderr
    card, empty, heads = out.stdout.split("@@")
    assert "P2 8:15" in card and "GOAL" in card and "Connor McDavid" in card, card
    assert "Q1" not in card and "+1" not in card, "hockey, not basketball"
    assert "not carrying plays" in empty
    assert json.loads(heads) == ["P2", "P1"], heads


def test_the_nhl_chip_switches_the_league_and_its_bets():
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    i = app.index('host.querySelectorAll(".lb-chip").forEach')
    handler = app[i:i + 2500]
    assert "LIVE_FEEDS[want]" in handler, "the chip switches every league with a live feed"
    j = app.index("const LIVE_FEEDS = {")
    assert "nhl:" in app[j:j + 400]
    html = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    assert 'class="sport-btn" data-sport="nhl"' in html, "the button the chip switches through"


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
