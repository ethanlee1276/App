"""The board's live game opens the same play-by-play the Live tab does.

Ethan, 2026-09-05: "can we make where if you click on the live game from
the recconended page it will take you to the same play by play with the
new renders n shit, or implement that in with it or something. We need
it too feel seamless and easy and organized and professional."

Three doors and one way back, pinned. A game in progress on the board's
strip opens its play-by-play; a scheduled or finished one keeps the game
page. The game page offers the play-by-play for a game in progress or
just over, and only once there is an id to open. The play-by-play's
Back button returns where the reader came from. And the id itself comes
from the league's fast scoreboard — the board's rows do not all carry
one — matched the way the Live tab matches its own cards. The door
logic runs for real in node (skipped without it); the rest are source
pins.
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

APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    if APP[i - 6:i] == "async ":
        i -= 6                      # the door functions await the fast file
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return APP[i:min(ends)]


def _node(js):
    """Run the door functions with the site around them stubbed: the
    board's games, the fast scoreboard, and the two pages a door can
    open. `calls` records which page opened with what."""
    node = shutil.which("node")
    if not node:
        return None
    src = "\n".join(_fn(n) for n in ("openPbp", "pbpBack", "openGameOrPlays", "pbpIdFor"))
    prog = f"""
      const state = {{ sport: "nfl", view: "recommended", pbp: null, pbpFrom: undefined, gameId: null }};
      let _pbpShowAll = false;
      const calls = [];
      let BOARD = [], FAST = {{}};
      const findGame = (gid) => BOARD.find((g) => g.gid === gid) || null;
      async function pbpStripGames(league) {{ calls.push(["fast", league]); return FAST[league] || []; }}
      function openGame(gid) {{ calls.push(["game", gid]); }}
      function switchView(name, push) {{ calls.push(["view", name]); state.view = name; }}
      {src}
      (async () => {{ {js} }})().then((out) => console.log(JSON.stringify(out)))
        .catch((e) => {{ console.error(e && e.stack || e); process.exit(1); }});
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


# --- the strip's card -----------------------------------------------------------
def test_a_card_on_the_board_goes_through_the_live_aware_door():
    body = _fn("renderGames")
    assert "const open = () => openGameOrPlays(el.dataset.gid);" in body
    assert "const open = () => openGame(" not in body, "the card no longer opens the game page blind"
    assert "pbpStripGames(state.sport).catch(() => {});" in body, "the fast file is asked for before the tap"
    assert '(g.live || {}).state === "live") && LIVE_FAST[state.sport]' in body


def test_a_live_game_opens_the_play_by_play_and_any_other_the_game_page():
    got = _node("""
      BOARD = [
        {gid: "a", away: "NE", home: "SEA", live: {state: "live"}},
        {gid: "b", away: "KC", home: "BUF", live: {state: "scheduled"}},
        {gid: "c", away: "DAL", home: "PHI", live: {state: "final"}},
        {gid: "d", away: "GB", home: "DET"},
        {gid: "e", away: "LAR", home: "SF", live: {state: "live"}},
      ];
      FAST = { nfl: [
        {event_id: "401", away: "NE", home: "SEA", live: {state: "live"}},
        {event_id: "402", away: "KC", home: "BUF", live: {state: "scheduled"}},
        {event_id: "403", away: "DAL", home: "PHI", live: {state: "final"}},
      ]};
      const out = {};
      for (const gid of ["a", "b", "c", "d", "e", "zzz"]) {
        calls.length = 0; state.pbp = null; state.view = "recommended";
        await openGameOrPlays(gid);
        out[gid] = { calls: calls.filter((c) => c[0] !== "fast"), pbp: state.pbp, from: state.pbpFrom };
      }
      return out;""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["a"]["calls"] == [["view", "pbp"]] and got["a"]["pbp"] == {"league": "nfl", "event": "401"}, got["a"]
    assert got["a"]["from"] == "recommended", "Back knows the board sent the reader"
    for gid in ("b", "c", "d"):
        assert got[gid]["calls"] == [["game", gid]], (gid, got[gid])
    assert got["e"]["calls"] == [["game", "e"]], "a live game the fast file does not list keeps the game page"
    assert got["zzz"]["calls"] == [["game", "zzz"]], "an unknown id still reaches the game page's own not-found state"


def test_the_card_says_what_it_opens():
    body = _fn("gameCard")
    assert 'aria-label="${isLive ? "Open the live play-by-play for" : "Open picks for"}' in body
    assert '<span class="gc-pbp">play-by-play →</span>' in body
    assert "LIVE_FAST[state.sport] ? `<span class=\"gc-pbp\">" in body, "no hint for a league without a fast file"
    assert ".status-badge.live .gc-pbp" in CSS


# --- the id ---------------------------------------------------------------------
def test_the_id_is_the_fast_files_matched_like_the_live_tab():
    got = _node("""
      FAST = {
        nfl: [
          {event_id: "401", away: "NE", home: "SEA", live: {state: "live"}},
          {event_id: "409", away: "NE", home: "MIA", live: {state: "scheduled"}},
        ],
        mlb: [
          {game_pk: 777, away: "NYY", home: "BOS", live: {state: "final", start_time: "2026-09-05T17:10:00Z"}},
          {game_pk: 778, away: "NYY", home: "BOS", live: {state: "live", start_time: "2026-09-05T23:10:00Z"}},
        ],
      };
      const out = {};
      calls.length = 0;
      out.own = await pbpIdFor({away: "X", home: "Y", event_id: "55"}, "nfl");
      out.ownPk = await pbpIdFor({away: "X", home: "Y", game_pk: 66}, "mlb");
      out.ownFetches = calls.length;
      out.nfl = await pbpIdFor({away: "NE", home: "SEA"}, "nfl");
      out.reversed = await pbpIdFor({away: "SEA", home: "NE"}, "nfl");
      out.otherHost = await pbpIdFor({away: "NE", home: "BUF"}, "nfl");
      out.leg1 = await pbpIdFor({away: "NYY", home: "BOS", game_number: 1}, "mlb");
      out.leg2 = await pbpIdFor({away: "NYY", home: "BOS", game_number: 2}, "mlb");
      out.legUnsaid = await pbpIdFor({away: "NYY", home: "BOS"}, "mlb");
      out.noFile = await pbpIdFor({away: "NE", home: "SEA"}, "ufc");
      out.none = await pbpIdFor(null, "nfl");
      return out;""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["own"] == "55" and got["ownPk"] == "66" and got["ownFetches"] == 0, \
        "a row that carries its own id never asks the fast file"
    assert got["nfl"] == "401"
    assert got["reversed"] == "", "away@home, not the pair — the fast file's own orientation"
    assert got["otherHost"] == "", "the same road team in another park is another game"
    assert got["leg1"] == "777" and got["leg2"] == "778", "a doubleheader's leg by first pitch"
    assert got["legUnsaid"] == "777", "no leg named means the first"
    assert got["noFile"] == "" and got["none"] == ""


# --- the game page's door -------------------------------------------------------
def test_the_game_page_offers_the_door_only_once_there_is_an_id():
    body = _fn("renderGamePage")
    assert '<span id="gp-pbp-slot"></span>' in body, "the slot sits in the page's own nav row"
    assert "if ((isLive || isFinal) && LIVE_FAST[state.sport]) {" in body
    assert "pbpIdFor(g, state.sport).then((id) => {" in body
    assert "if (!id || !slot || !slot.isConnected) return;" in body, "no id, no button"
    assert 'openPbp(state.sport, id, "game")' in body, "the page it opens knows to come back here"
    assert "Watch play-by-play" in body and '"Play-by-play"' in body
    assert ".gp-pbp-door" in CSS


# --- the way back ---------------------------------------------------------------
def test_back_returns_where_the_reader_came_from():
    got = _node("""
      const out = {};
      state.gameId = "2026-09-05_NE@SEA";
      for (const from of ["recommended", "game", "live", "settings", undefined]) {
        state.pbpFrom = from; out[String(from)] = pbpBack();
      }
      state.gameId = null; state.pbpFrom = "game"; out.gameGone = pbpBack();
      // openPbp records the origin: the view it was opened from, kept
      // while moving between games inside the page, and an explicit
      // origin wins.
      state.view = "live"; openPbp("nfl", "1"); out.fromLive = state.pbpFrom;
      state.view = "pbp"; openPbp("nfl", "2"); out.kept = state.pbpFrom;
      state.view = "pbp"; openPbp("nfl", "3", "game"); out.explicit = state.pbpFrom;
      return out;""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["recommended"] == {"view": "recommended", "label": "← Back to the board"}
    assert got["game"] == {"view": "game", "label": "← Back to the game"}
    for k in ("live", "settings", "undefined", "gameGone"):
        assert got[k] == {"view": "live", "label": "← Back to Live"}, (k, got[k])
    assert got["fromLive"] == "live" and got["kept"] == "live" and got["explicit"] == "game"


def test_the_page_draws_and_wires_that_way_back():
    body = _fn("renderPbpPage")
    assert "const way = pbpBack();" in body
    assert 'id="pbp-back" style="margin-top:14px">${way.label}</button>' in body
    assert "switchView(way.view)" in body
    assert 'switchView("live")' not in body, "no door in the page still hard-wired to Live"
    assert "from the Live tab or the board" in body
    hash_ = _fn("openPbpHash")
    assert 'openPbp(parts[0], parts[1], "live")' in hash_, "a hash landing goes back to the page's own tab"


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
