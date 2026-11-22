"""Baseball's game page and play files work like every other league's (step ABM, 22 November 2026).

Ethan, the Sunday morning: "NFL is kind of like the one we want to go off of ... how it runs and how it works,
how it gets data." Step ABL wrote a just-ended game's play file once more as final in every league the live
loop serves; baseball's files come from their own loop (live_build), which had the same gap, and its page
matched the scoreboard strip by `event_id` alone where baseball's rows carry `game_pk`, so a baseball page
never read the strip's final (2026-10-25's fix for a file frozen at the last live write) and step ABL's
archive check could not tell a live baseball game from a finished one. What these hold:

  * a baseball game just ended whose file still says live is written once more, as final, its card left as
    the scoreboard drew it (`live_build.rewrite_finals`, through livescore_build's own `left_live`);
  * the page finds a baseball game on the strip by its `game_pk`, everywhere it looks one up.

    python3 tests/test_baseballs_game_page_works_like_the_others.py
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
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

import live_build as LB                                       # noqa: E402

DETAIL = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")


def _play(event, batter, *, inning=9, half="bottom", rbi=0, away=3, home=4):
    return {"result": {"event": event, "eventType": event.lower().replace(" ", "_"), "rbi": rbi,
                       "awayScore": away, "homeScore": home},
            "about": {"inning": inning, "halfInning": half, "isScoringPlay": bool(rbi)},
            "matchup": {"batter": {"fullName": batter}, "pitcher": {"fullName": "A Closer"}}}


def _payload():
    return {"allPlays": [_play("Single", "First Batter"), _play("Home Run", "Second Batter", rbi=1)]}


def _game(state, pk=776655):
    return {"game_pk": pk, "home": "NYY", "away": "BOS", "home_name": "New York Yankees",
            "away_name": "Boston Red Sox",
            "live": {"state": state, "home_score": 4, "away_score": 3, "period": "Bot 9", "start_time": ""}}


def _left_behind(pbp, pk=776655):
    doc = {"league": "mlb", "event_id": str(pk), "generated_at": "2026-09-20T02:40:00Z", "home": "NYY",
           "away": "BOS", "live": {"state": "live", "home_score": 3, "away_score": 3, "period": "Bot 9"},
           "plays": []}
    (pbp / f"mlb_{pk}.json").write_text(json.dumps(doc))


class _Feeds:
    """The feeds stubbed: the play-by-play, the win chances (down) and the box score (none)."""
    def __init__(self, fn):
        self.fn = fn

    def __enter__(self):
        import engine.mlb.sources.pbp as P
        self.P, self.was = P, (P.fetch_live_playbyplay, P.fetch_live_win_probability, LB._box_players)
        P.fetch_live_playbyplay = self.fn

        def down(pk, ttl=30):
            raise OSError("no win chances")
        P.fetch_live_win_probability = down
        LB._box_players = lambda g: []

    def __exit__(self, *exc):
        self.P.fetch_live_playbyplay, self.P.fetch_live_win_probability, LB._box_players = self.was


def test_a_just_ended_baseball_game_is_written_once_more_as_final():
    pbp = Path(tempfile.mkdtemp())
    _left_behind(pbp)
    games = [_game("final")]
    asked = []
    with _Feeds(lambda pk, ttl=30: asked.append(pk) or _payload()):
        note = LB.attach_plays(games, pbp_dir=pbp)
    doc = json.loads((pbp / "mlb_776655.json").read_text())
    assert doc["live"]["state"] == "final" and doc["live"]["home_score"] == 4, doc["live"]
    assert [p.get("event") for p in doc["plays"]][-1] == "Home Run", doc["plays"]
    assert asked == [776655]
    assert "plays" not in games[0] and games[0]["plays_state"] == "idle", "the card is as the scoreboard drew it"
    assert note == "no games in progress — no plays fetched, 1 ended game(s) written final", note
    asked.clear()
    with _Feeds(lambda pk, ttl=30: asked.append(pk) or _payload()):
        note = LB.attach_plays(games, pbp_dir=pbp)
    assert asked == [] and note == "no games in progress — no plays fetched", "and once only"


def test_beside_live_games_and_a_dead_feed_costs_only_that_game():
    pbp = Path(tempfile.mkdtemp())
    for pk in (1, 2):
        _left_behind(pbp, pk)
    games = [_game("live", 9), _game("final", 1), _game("final", 2)]

    def fn(pk, ttl=30):
        if pk == 1:
            raise OSError("statsapi refused")
        return _payload()
    with _Feeds(fn):
        note = LB.attach_plays(games, pbp_dir=pbp)
    assert "1 of 1 live game(s)" in note and ", 1 ended game(s) written final" in note, note
    assert json.loads((pbp / "mlb_1.json").read_text())["live"]["state"] == "live", "it waits for its feed"
    assert json.loads((pbp / "mlb_2.json").read_text())["live"]["state"] == "final"
    assert games[0]["plays"] and games[0]["plays_state"] == "ok"


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(js)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_the_page_finds_a_baseball_game_on_the_strip_by_its_game_pk():
    i = APP.index("function utcMs(")
    j = DETAIL.index("const PBP_LEFT_LIVE_MS")
    js = APP[i:APP.index("\n}\n", i) + 3] + DETAIL[j:DETAIL.index("\n}\n", j) + 3]
    got = _node(js + """
      const d = { live: { state: "live" }, generated_at: "2026-09-20T02:40:00Z" };
      const at = Date.parse("2026-09-20T12:00:00Z");
      console.log(JSON.stringify([pbpLeftLive(d, [{ game_pk: 776655, live: { state: "live" } }], "776655", at),
                                  pbpLeftLive(d, [{ game_pk: 776655, live: { state: "final" } }], "776655", at)]));""")
    if got is not None:
        assert got == [False, True], got
    page = DETAIL[DETAIL.index("async function renderPbpPage("):]
    page = page[:page.index("\n}\n")]
    assert "const fast = (strip || []).find((g) => String(g.event_id || g.game_pk) === String(event));" in page
    assert "strip = (strip || []).map((g) => (String(g.event_id || g.game_pk) === String(event)" in page
    assert "String(g.event_id) === String(event)" not in DETAIL, "no lookup by the event id alone"


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
