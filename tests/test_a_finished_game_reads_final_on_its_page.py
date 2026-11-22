"""A finished game reads final on its page, in every league (step ABL, 22 November 2026).

Ethan, the Sunday morning: "We want all the live pages to match each other ... NFL is kind of like the one we
want to go off of ... how it gets data." Opened the next morning, the Knicks' 97-96 win over the Trail Blazers
read LIVE, "End of 4th Quarter" and "updated 10 hr ago", and a college basketball game's page the same, where
the NFL's finished games read Final and the day they were played. The live loop wrote a game's play file only
while the game was live, so the pass that first saw it final wrote nothing, and the file kept its last live
copy until it was pruned a day and a half later (hockey's read Final because its rink pass writes the
scoreboard onto the file). What these hold:

  * a game just ended whose file still says live is written once more, as final, a few a pass, after the live
    games, and its card on the Live tab is left as the scoreboard drew it (`livescore_build.rewrite_finals`);
  * a file still saying live, hours old, of a game the strip does not have live, is read from the archive
    instead, which builds it final from the feed (`pbpLeftLive`): the games that ended before this step;
  * a final's header says the day it was played, as the NFL's do, from the file as from the archive;
  * a past game's page names its network as the live loop's finals do: the archive reads ESPN's game summary,
    whose header names each carrier in the scoreboard's market shape, and the NFL's finished games drew none.

    python3 tests/test_a_finished_game_reads_final_on_its_page.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import livescore_build as B                                  # noqa: E402
from engine.sources import espnplays as E                    # noqa: E402

DETAIL = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")


def _hplay(pid, seq, *, team="18", value=0, home=0, away=0, period=4, clock="0:00"):
    return {"id": pid, "sequenceNumber": str(seq), "period": {"number": period, "displayValue": "4th Quarter"},
            "clock": {"displayValue": clock}, "team": {"id": team}, "participants": [{"athlete": {"id": "1"}}],
            "type": {"id": "558", "text": "Jump Shot"}, "scoringPlay": bool(value), "shootingPlay": True,
            "scoreValue": value, "pointsAttempted": 2, "awayScore": away, "homeScore": home,
            "wallclock": "2026-11-22T02:50:00Z"}


def _summary():
    return {"plays": [_hplay("p1", 1, value=2, home=95, away=96), _hplay("p2", 2, value=2, home=97, away=96)],
            "boxscore": {"players": [], "teams": []}, "header": {"id": "401910024"}}


def _game(state, eid="401910024"):
    return {"event_id": eid, "home": "NYK", "away": "POR", "home_name": "New York Knicks",
            "away_name": "Portland Trail Blazers", "home_id": "18", "away_id": "22",
            "live": {"state": state, "home_score": 97, "away_score": 96, "period": "Q4" if state == "live" else "Final",
                     "clock": "", "detail": "", "start_time": "2026-11-22T00:30Z"}}


def _left_behind(pbp, eid="401910024", league="nba"):
    """The file the last live pass wrote: the game at the end of the fourth, still live."""
    doc = {"league": league, "event_id": eid, "generated_at": "2026-11-22T02:54:44Z", "home": "NYK", "away": "POR",
           "home_name": "New York Knicks", "away_name": "Portland Trail Blazers",
           "live": {"state": "live", "home_score": 97, "away_score": 96, "period": "Q4", "clock": "",
                    "hold": "End of 4th Quarter", "start_time": "2026-11-22T00:30Z"}, "plays": []}
    (pbp / f"{league}_{eid}.json").write_text(json.dumps(doc))


def _with_fetch(fn, games, league, pbp_dir):
    real = E.fetch_summary
    E.fetch_summary = fn
    try:
        return B.attach_plays(games, league, pbp_dir=pbp_dir)
    finally:
        E.fetch_summary = real


def test_a_final_whose_file_still_says_live_is_found():
    pbp = Path(tempfile.mkdtemp())
    _left_behind(pbp)
    (pbp / "nba_2.json").write_text(json.dumps({"league": "nba", "event_id": "2", "live": {"state": "final"}}))
    _left_behind(pbp, eid="3")
    games = [_game("final"), _game("final", "2"), _game("live", "3"), _game("final", "4")]
    assert [g["event_id"] for g in B.left_live(games, "nba", pbp)] == ["401910024"], \
        "a final saying final, a live game, and a final with no file are left alone"
    assert B.left_live(games, "nba", None) == []


def test_the_pass_writes_it_once_more_as_final_and_leaves_its_card_alone():
    pbp = Path(tempfile.mkdtemp())
    _left_behind(pbp)
    games = [_game("final")]
    asked = []
    note = _with_fetch(lambda lg, eid, ttl=30: asked.append(eid) or _summary(), games, "nba", pbp)
    doc = json.loads((pbp / "nba_401910024.json").read_text())
    assert doc["live"]["state"] == "final" and "hold" not in doc["live"], doc["live"]
    assert len(doc["plays"]) == 2 and doc["plays"][-1]["id"] == "p2", "the last plays too"
    assert asked == ["401910024"]
    assert "plays" not in games[0] and games[0]["plays_state"] == "idle", "the card is as the scoreboard drew it"
    assert note == "no games in progress — no plays fetched, 1 ended game(s) written final", note
    # The next pass finds nothing more to write.
    asked.clear()
    note = _with_fetch(lambda lg, eid, ttl=30: asked.append(eid) or _summary(), games, "nba", pbp)
    assert asked == [] and note == "no games in progress — no plays fetched", note


def test_beside_live_games_a_few_a_pass_and_a_failure_costs_only_itself():
    pbp = Path(tempfile.mkdtemp())
    ended = [str(i) for i in range(B.FINAL_REWRITES_PER_PASS + 2)]
    for eid in ended:
        _left_behind(pbp, eid=eid)
    games = [_game("live", "L1")] + [_game("final", eid) for eid in ended]

    def fetch(lg, eid, ttl=30):
        if eid == "0":
            raise OSError("the feed is down")
        return _summary()
    note = _with_fetch(fetch, games, "nba", pbp)
    assert "1 of 1 live game(s)" in note and f", {B.FINAL_REWRITES_PER_PASS - 1} ended game(s) written final" in note, note
    final = [eid for eid in ended if json.loads((pbp / f"nba_{eid}.json").read_text())["live"]["state"] == "final"]
    assert final == ended[1:B.FINAL_REWRITES_PER_PASS], final
    assert games[0]["plays_state"] == "ok" and games[0]["plays"], "the live game is served first, as before"
    _with_fetch(fetch, games, "nba", pbp)
    final = [eid for eid in ended if json.loads((pbp / f"nba_{eid}.json").read_text())["live"]["state"] == "final"]
    assert final == ended[1:], "the rest the next pass; the failed one waits for its feed"


def test_a_football_final_is_written_from_its_drives():
    pbp = Path(tempfile.mkdtemp())
    _left_behind(pbp, league="nfl")
    games = [_game("final")]
    summary = {"drives": {"previous": [], "current": {}}, "header": {"id": "401910024"}, "boxscore": {"teams": []}}
    _with_fetch(lambda lg, eid, ttl=30: summary, games, "nfl", pbp)
    assert json.loads((pbp / "nfl_401910024.json").read_text())["live"]["state"] == "final"


def test_a_past_games_page_names_its_network():
    from engine import gamearchive as GA
    from engine.sources.livescores import espn_carriers
    tv = [{"type": {"shortName": "TV"}, "market": {"type": "National"}, "media": {"shortName": "CBS"}},
          {"type": {"shortName": "TV"}, "market": {"type": "Home"}, "media": {"shortName": "KHOU"}},
          {"type": {"shortName": "Radio"}, "market": {"type": "National"}, "media": {"shortName": "Westwood One"}}]
    assert espn_carriers({"broadcasts": tv}) == (["CBS"], ["KHOU"])
    assert espn_carriers({"broadcasts": [{"market": "national", "names": ["NBC"]}]}) == (["NBC"], []), \
        "the scoreboard's own shape, as before"
    comp = {"date": "2026-11-20T01:15Z", "broadcasts": tv,
            "status": {"type": {"state": "post", "name": "STATUS_FINAL", "detail": "Final", "shortDetail": "Final",
                                "completed": True}, "period": 4, "displayClock": "0:00"},
            "competitors": [
                {"homeAway": "home", "score": "26", "team": {"id": "34", "abbreviation": "HOU", "displayName": "Houston Texans"}},
                {"homeAway": "away", "score": "3", "team": {"id": "11", "abbreviation": "IND", "displayName": "Indianapolis Colts"}}]}
    payload = {"header": {"id": "401772900", "competitions": [comp]}, "drives": {"previous": []},
               "boxscore": {"teams": []}}
    real = E.fetch_summary
    E.fetch_summary = lambda lg, eid, ttl=30: payload
    try:
        doc = GA._espn_doc("nfl", "401772900")
    finally:
        E.fetch_summary = real
    assert doc and doc["live"]["state"] == "final" and doc["tv"] == ["CBS"] and doc["tv_local"] == ["KHOU"], doc


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(js)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30,
                             env={**os.environ, "TZ": "America/New_York"})
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def _fn(src, head):
    i = src.index(head)
    return src[i:src.index("\n}\n", i) + 3]


def test_the_page_reads_a_file_left_live_from_the_archive():
    i = DETAIL.index("const PBP_LEFT_LIVE_MS")
    js = _fn(APP, "function utcMs(") + DETAIL[i:DETAIL.index("\n}\n", i) + 3]
    got = _node(js + """
      const d = { live: { state: "live" }, generated_at: "2026-11-22T02:54:44Z" };
      const at = Date.parse("2026-11-22T13:00:00Z");
      console.log(JSON.stringify([
        pbpLeftLive(d, [{ event_id: "401910024", live: { state: "final" } }], "401910024", at),
        pbpLeftLive(d, [], "401910024", at),
        pbpLeftLive(d, [{ event_id: 401910024, live: { state: "live" } }], "401910024", at),
        pbpLeftLive(d, [], "401910024", Date.parse("2026-11-22T04:00:00Z")),
        pbpLeftLive({ ...d, live: { state: "final" } }, [], "401910024", at),
        pbpLeftLive({ live: { state: "live" } }, [], "401910024", at),
        pbpLeftLive(null, [], "401910024", at)]));""")
    if got is None:
        print("  SKIP node not installed")
    else:
        assert got == [True, True, False, False, False, False, False], got
    body = DETAIL[DETAIL.index("async function renderPbpPage("):]
    body = body[:body.index("\n}\n")]
    ask = ("if (d && league && event && !PBP_LEFT_LIVE_ASKED.has(`${league}_${event}`) && pbpLeftLive(d, strip, event)) {")
    assert body.index("if (!d && league && event) {") < body.index(ask) < body.index('if (state.view !== "pbp") return;')
    assert "if (got) { d = got; raw = JSON.stringify(got); } else PBP_LEFT_LIVE_ASKED.add(`${league}_${event}`);" in body, \
        "a game the archive cannot build is asked once a visit, not every poll"
    # The strip's final still stands beside it (2026-10-25): a file saying live under a strip saying final.
    assert 'if ((d.live || {}).state === "live" && ((!tvHeld.held && fast && (fast.live || {}).state === "final") || ended)) {' in body


def test_a_final_says_the_day_it_was_played():
    js = (_fn(APP, "function utcMs(") + _fn(APP, "function formatGameDate(") + _fn(DETAIL, "function pbpPlayedOn("))
    got = _node(js + """
      console.log(JSON.stringify([
        pbpPlayedOn({ live: { state: "final", start_time: "2026-11-22T00:30Z" } }),
        pbpPlayedOn({ date: "2026-11-16", live: { state: "final" } }),
        pbpPlayedOn({ live: { state: "final" } })]));""")
    if got is not None:
        assert got[0] == "Sat, Nov 21" and got[1] == "Mon, Nov 16" and got[2] == "", got
    assert ('const ago = d.archive || lv.state === "final" ? pbpPlayedOn(d) || pbpAgo(d.generated_at)'
            " : pbpAgo(d.generated_at);") in DETAIL


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    fails = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as exc:                              # noqa: BLE001
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed.")
    sys.exit(1 if fails else 0)
