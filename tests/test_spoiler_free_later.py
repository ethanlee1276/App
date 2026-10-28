"""Spoiler-free later: a game saved for later shows no score anywhere on
this device until it is opened (docs/IDEAS.md, the live game list's ninth;
built 2026-10-28, runbook FT).

What these hold:

  * the game page offers "Watching later? Hide the score" beside the TV
    delay, in both its layouts (js/detail.js pbpSpoilHTML), and a game
    saved for later draws a veil instead of itself, mounts no chat, and has
    a "Show the game" (pbpSpoilVeilHTML, before chatMount);
  * every card that draws a score asks first (app.js spoiledG): the game
    cards and the photo's board, the rail, the Live tab's card (the clock
    stays, the score, plays and line go), the play feed, the home deck's
    live strip, the play-by-play page's own strip, the board's game page
    (no score, no bases, no room), the Your players strip, and the bet
    slip's live leg;
  * a tracked bet on a hidden game keeps its ticket and moves with the
    clock, but its number, verdict, live chance, score and bases wait
    (app.js spoilRow, every row liveTrackerRows hands out: the Live tab,
    the deck's Riding rows, the pick of the day's strip);
  * a game is matched by its id, or by its teams where a card has none or
    has only the odds feed's (college's board), and kept 36 hours at most;
    saving one sweeps out the expired;
  * and in a browser, hiding a game veils its page, its Live card says so
    with no score, and "Show the game" brings it back.

Run directly: `python3 tests/test_spoiler_free_later.py`
(the browser check with QB_BROWSER_TESTS=1 and /usr/bin/python3).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
DETAIL = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")


def _fn(src, name):
    i = src.index(f"function {name}(")
    if src[i - 6:i] == "async ":
        i -= 6
    ends = [src.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(src)]
    return src[i:min(ends)]


def test_every_card_that_draws_a_score_asks_first():
    assert 'const SPOIL_KEY = "qb_spoil_v1";' in APP
    card = _fn(APP, "gameCard")
    assert "const hid = spoiledG(state.sport, g);\n  if (hid) g = { ...g, live: { state: (g.live || {}).state } };" in card
    assert 'if (hid && (isLive || isFinal)) badge = `<div class="status-badge">Spoiler-free</div>`;' in card
    live = _fn(APP, "liveCardHTML")
    assert "const hid = spoiledG(sport, g);" in live and "plays: [], line_track: null };" in live
    assert "Spoiler-free: the score and the plays wait until you open the game." in live
    assert "playFeedMount(pfHost, shown.filter((x) => !spoiledG(x.sport, x.g)));" in APP, "the feed leaves it out"
    deck = _fn(APP, "deckGameHTML")
    assert "const hid = spoiledG(x.sport, x.g);" in deck and 'const sit = hid ? "Spoiler-free"' in deck
    assert "const lv = spoiledG(state.sport, g) ? {} : g.live || {};" in _fn(APP, "renderRail")
    assert "return trackerFastRows(rows).map(spoilRow);" in _fn(APP, "liveTrackerRows"), "every tracked bet asks"
    assert "if (r.spoiled)" in APP and "SPOILER-FREE</span>" in APP, "the Live tab's row says why it is quiet"
    assert "r.phase !== \"live\" || r.spoiled ||" in APP, "no win-chance chart under a hidden bet"
    assert 'if (s === "spoiled") return ["Hidden", ""];' in _fn(APP, "deckStateWord")
    slip = (ROOT / "web" / "js" / "slip.js").read_text(encoding="utf-8")
    assert 'spoiledG(String(l.league || l.sport || "").toLowerCase(), g))' in slip, "the slip's live leg"
    chat = (ROOT / "web" / "js" / "chat.js").read_text(encoding="utf-8")
    assert "rows = rows.filter((r) => !spoiledG(r.league, { event_id: r.event_id }));" in _fn(chat, "ypHTML"), \
        "the Your players strip"
    gp = _fn(DETAIL, "renderGamePage")
    assert "if (spoiledG(state.sport, g)) g = { ...g, live: { state: (g.live || {}).state, period: (g.live || {}).period } };" in gp, \
        "the board's game page: no score, no bases"
    assert '&& state.view === "game" && !spoiledG(state.sport, row))' in gp, "and no room mounted from it"
    strip = _fn(DETAIL, "pbpStripHTML")
    assert "hid = spoiledG(league, g);" in strip and "row(g.away, hid ? null : lv.away_score)" in strip


def test_the_game_page_offers_it_and_veils_a_saved_game():
    assert "callit: pbpTvHTML(d) + pbpSpoilHTML(d, league, event) +" in DETAIL, "the basketball and hockey layout"
    assert "${pbpTvHTML(d)}${pbpSpoilHTML(d, league, event)}" in DETAIL, "the other layout"
    page = _fn(DETAIL, "renderPbpPage")
    veil = page.index("if (d && spoiledG(league, { event_id: event, away: d.away, home: d.home })) {")
    assert veil < page.index("chatMount(league, event, d);"), "veiled before the chat mounts"
    assert 'if (typeof chatReset === "function") { chatReset(); chatFab(); }\n    host.innerHTML = pbpSpoilVeilHTML(d, league, event) + back;' in page, \
        "the room reset, and its bar taken down with it"
    v = _fn(DETAIL, "pbpSpoilVeilHTML")
    assert 'data-spoil-show="${escapeAttr(`${league}_${event}`)}">Show the game</button>' in v
    assert "Phone alerts come from the box and are not held." in v
    assert "Watching later? Hide the score</button>" in _fn(DETAIL, "pbpSpoilHTML")
    assert "const SPOIL_MS = 36 * 3600 * 1000;" in DETAIL


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""
      let store = {{}};
      const localStorage = {{ getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => {{ store[k] = String(v); }} }};
      const SPOIL_KEY = "qb_spoil_v1";
      {_fn(APP, "spoiledG")}
      const SPOIL_MS = 36 * 3600 * 1000;
      {_fn(DETAIL, "spoilSet")}
      console.log(JSON.stringify((() => {{ {js} }})()));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_a_bet_on_a_hidden_game_keeps_its_ticket_and_loses_the_rest():
    """The tracker in node: the real liveTrackerRows, spoilRow and
    spoiledG. A bet on the hidden game moves to live with its clock but
    carries no number, verdict, live chance, score or bases; a bet on
    another game keeps every one; an upcoming bet stays upcoming."""
    node = shutil.which("node")
    if not node:
        print("      (skipped: no node)")
        return
    i = APP.index("/* Tracker rows with their phase read off the fast scoreboard")
    j = APP.index("function renderLivePicks() {")
    prog = f"""
      let store = {{}};
      const localStorage = {{ getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => {{ store[k] = String(v); }} }};
      const SPOIL_KEY = "qb_spoil_v1";
      {_fn(APP, "spoiledG")}
      const SPOIL_MS = 36 * 3600 * 1000;
      {_fn(DETAIL, "spoilSet")}
      const state = {{ sport: "nfl" }};
      const live = (a, h) => ({{ event_id: a === "SF" ? "401" : "402", away: a, home: h,
        live: {{ state: "live", period: "Q3", clock: "2:00", home_score: 10, away_score: 24 }},
        players: [{{ player: "George Kittle", stats: {{ rec_yds: 88 }} }}, {{ player: "Travis Kelce", stats: {{ rec_yds: 71 }} }}] }});
      const _liveAll = {{ at: 1, games: [{{ sport: "nfl", g: live("SF", "ATL") }}, {{ sport: "nfl", g: live("KC", "DEN") }}], finals: [] }};
      {APP[i:j]}
      spoilSet("nfl_401", true, "SF", "ATL", "nfl");
      const row = (player, a, h, status) => ({{ player, market: "rec_yds", line: 60.5, side: "OVER", phase: "upcoming",
        status, live_prob: 0.4, history: [[1, 0.4]], game: {{ away: a, home: h, home_score: 3, away_score: 7, situation: "2nd & 4" }} }});
      console.log(JSON.stringify(liveTrackerRows([row("George Kittle", "SF", "ATL", "upcoming"),
        row("Travis Kelce", "KC", "DEN", "upcoming"), row("Brock Purdy", "SF", "ATL", "unmapped")])));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    hid, shown, unmapped = json.loads(out.stdout)
    assert hid["phase"] == "live" and hid["spoiled"] is True and hid["status"] == "spoiled", hid
    assert hid["current"] is None and hid["live_prob"] is None and hid["history"] == [], hid
    g = hid["game"]
    assert g["home_score"] is None and g["away_score"] is None and g["situation"] is None, g
    assert g["live"] == {} and g["players"] == [] and g["plays"] == [], g
    assert shown["status"] == "cleared" and shown["current"] == 71 and shown["game"]["home_score"] == 10, shown
    assert "spoiled" not in shown
    assert unmapped["status"] == "spoiled", unmapped
    assert unmapped["current"] is None and unmapped["game"]["away_score"] is None, unmapped


def test_a_game_is_matched_by_its_id_or_its_teams_and_kept_36_hours():
    got = _node("""
      spoilSet("nfl_401", true, "SF", "ATL", "nfl");
      const r = {
        byId: spoiledG("nfl", { event_id: "401", away: "SF", home: "ATL" }),
        otherId: spoiledG("nfl", { event_id: "402", away: "SF", home: "ATL" }),   // the next meeting
        byTeams: spoiledG("nfl", { away: "SF", home: "ATL" }),                   // a card with no id
        otherLeague: spoiledG("cfb", { away: "SF", home: "ATL" }),
        none: spoiledG("nfl", null),
      };
      // College's board keys a game by the odds feed's id, not ESPN's: its teams decide.
      spoilSet("cfb_401777", true, "UGA", "BAMA", "cfb");
      r.oddsId = spoiledG("cfb", { event_id: "e912f3c0a6b1d2e3f4a5b6c7d8e9f0a1", away: "UGA", home: "BAMA" });
      r.mlbPk = spoiledG("mlb", { game_pk: 746123, away: "SF", home: "ATL" });
      const all = JSON.parse(store[SPOIL_KEY]);
      r.lasts = Math.round((all.nfl_401.exp - Date.now()) / 3600000);
      all.old_1 = { l: "nba", a: "BOS", h: "NYK", exp: Date.now() - 1 };    // expired
      store[SPOIL_KEY] = JSON.stringify(all);
      r.expired = spoiledG("nba", { away: "BOS", home: "NYK" });
      spoilSet("nba_9", true, "LAL", "PHX", "nba");                        // saving sweeps the expired
      r.swept = !("old_1" in JSON.parse(store[SPOIL_KEY]));
      spoilSet("nfl_401", false);
      r.shown = spoiledG("nfl", { event_id: "401" });
      return r;""")
    if got is None:
        print("      (skipped: no node)")
        return
    assert got == {"byId": True, "otherId": False, "byTeams": True, "otherLeague": False, "none": False,
                   "oddsId": True, "mlbPk": False, "lasts": 36, "expired": False, "swept": True, "shown": False}, got


# --- in a browser (opt-in) -------------------------------------------------------------------
def test_in_a_browser_a_saved_game_is_veiled_and_its_card_says_so():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    live = {"state": "live", "period": "Q2", "clock": "4:12", "away_score": 7, "home_score": 3}
    pbp = {"league": "nfl", "event_id": "401", "home": "ATL", "away": "SF", "generated_at": "2026-10-25T17:00:00Z",
           "live": live, "plays": [{"kind": "football", "id": "p1", "period": 2, "clock": "4:12", "team": "SF",
                                    "event": "Pass Reception", "yards": 38, "scoring": True, "away_score": 7,
                                    "home_score": 3, "players": ["Brock Purdy", "George Kittle"]}],
           "drives": []}
    fast = {"games": [{"event_id": "401", "home": "ATL", "away": "SF", "live": live,
                       "plays": pbp["plays"]}]}
    srv, port = rendercheck._serve()
    try:
        with sync_playwright() as pw:
            chromium = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium")
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists(chromium):
                kw["executable_path"] = chromium
            b = pw.chromium.launch(**kw)
            try:
                p = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                  service_workers="block").new_page()
                errs = []
                p.on("pageerror", lambda e: errs.append(str(e)))
                p.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb.tour', 'done'); } catch (e) {}")
                p.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                mk = lambda body: (lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(body)))
                p.route("**/data/pbp/nfl_401.json*", mk(pbp))
                p.route("**/data/live_nfl.json*", mk(fast))
                p.route("**/api/chat/room*", mk({"room": "nfl_401", "messages": [], "votes": {"home": 0, "away": 0}}))
                p.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#pbp/nfl/401", wait_until="load")
                p.wait_for_selector("[data-spoil]", timeout=20000)
                p.click("[data-spoil]")
                p.wait_for_selector(".pbp-spoil", timeout=10000)
                veil = p.inner_text("#pbp-body")
                assert "Spoiler-free" in veil and "Show the game" in veil, veil[:300]
                assert not p.query_selector("#pbp-body .pbp-wpcard, #pbp-body .gch-entry-slot"), "nothing of the game"
                assert not p.query_selector("#gch-fab"), "no chat bar into the game's room"
                for s in (" 7–3", "7-3"):
                    assert s not in veil, veil[:300]
                # The Live tab's card: the clock, no score, and why.
                p.evaluate("switchView('live', true)")
                p.wait_for_selector(".lb-card", timeout=15000)
                card = p.inner_text(".lb-card")
                assert "Spoiler-free: the score and the plays wait until you open the game." in card, card
                assert not re.search(r"\b7\b", card.split("Spoiler-free")[0].replace("Q2", "")), card
                # And back: "Show the game" draws it again.
                p.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#pbp/nfl/401", wait_until="load")
                p.wait_for_selector("[data-spoil-show]", timeout=20000)
                p.click("[data-spoil-show]")
                p.wait_for_selector("[data-spoil]", timeout=10000)
                assert not p.query_selector(".pbp-spoil")
                assert not errs, errs
            finally:
                b.close()
    finally:
        srv.shutdown()


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
