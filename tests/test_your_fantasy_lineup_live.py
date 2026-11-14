"""Your fantasy lineup, live: a linked Sleeper league's matchup over the Live
tab's strip, and its starters' box lines on the strip (docs/IDEAS.md, the
live game list's seventh; built 2026-10-28, runbook FU).

What these hold:

  * the league desk answers the Live tab with the matchup and nothing else
    (`/api/leaguedesk?live=1`): no trades, pickups or to-do list, and the
    lineup alert's memory untouched; the device keeps the Sleeper username,
    which the desk turns into its id off the sync's own cached read;
  * the strip's own ask carries the starters' names (`lineup`), checked as
    names (letters, spaces and . ' - only, 48 characters, the first twenty)
    and looked up in the box-score index the followed players use, never
    kept; a starter's line says so, after the players followed, and a
    Sleeper spelling without a suffix finds the box score's with one;
  * the page asks the desk once a minute while a game is on and every five
    minutes otherwise (js/chat.js ffLiveLoad), draws the matchup over the
    strip with the win chance, and each starter's fantasy points so far on
    his line; a starter in a game saved for later holds the score back;
  * and in a browser, a signed-in reader with a linked league sees the
    matchup and "In your lineup · 21.4 pts" on the starter's line.

Run directly: `python3 tests/test_your_fantasy_lineup_live.py`
(the browser check with QB_BROWSER_TESTS=1 and /usr/bin/python3).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import yourplayers as YP  # noqa: E402

SERVER = (ROOT / "server.py").read_text(encoding="utf-8")
CHAT = (ROOT / "web" / "js" / "chat.js").read_text(encoding="utf-8")


def _e(player, team="CIN", opp="BAL", state="live", eid="401"):
    return {"player": player, "team": team, "opp": opp, "league": "nfl", "event_id": eid,
            "line": "6 rec, 94 yds, TD", "state": state, "status": "Q3 4:12", "score": "BAL 10–17 CIN"}


IDX = {"jamarrchase": [_e("Ja'Marr Chase")], "kennethwalkeriii": [_e("Kenneth Walker III", "SEA", "LAR")],
       "joeburrow": [_e("Joe Burrow")], "derrickhenry": [_e("Derrick Henry", "BAL", "CIN", state="final")]}


# --- the names a request carries ----------------------------------------------------------
def test_a_lineup_is_read_as_names_only():
    got = YP.lineup_names("Ja'Marr Chase|Amon-Ra St. Brown|D.J. Moore|Kenneth Walker III|<script>|"
                          "Josh Allen|Josh Allen|A’ja Wilson|Ronald Acuña Jr.|  Travis  Kelce |1abc|"
                          + "x" * 49)
    assert got == ["Ja'Marr Chase", "Amon-Ra St. Brown", "D.J. Moore", "Kenneth Walker III", "Josh Allen",
                   "A’ja Wilson", "Ronald Acuña Jr.", "Travis Kelce"], got
    many = "|".join(f"Player {chr(65 + i // 26)}{chr(97 + i % 26)}" for i in range(40))
    assert len(YP.lineup_names(many)) == YP.LINEUP_MAX == 20
    assert YP.lineup_names("") == [] and YP.lineup_names(None) == []


def test_the_starters_follow_the_players_followed_and_say_so():
    watches = [{"kind": "player", "value": "Joe Burrow"}, {"kind": "team", "value": "CIN"}]
    out = YP.mine(watches, IDX, lineup=["Ja'Marr Chase", "Kenneth Walker", "Joe Burrow", "Derrick Henry"])
    names = [(e["player"], bool(e.get("lineup"))) for e in out]
    # Followed first, then the starters; live before final; a followed starter is flagged too.
    assert names == [("Joe Burrow", True), ("Ja'Marr Chase", True), ("Kenneth Walker III", True),
                     ("Derrick Henry", True)], names
    assert "lineup" not in IDX["jamarrchase"][0], "the index's own rows are never written on"
    # No lineup: exactly the strip it was.
    plain = YP.mine(watches, IDX)
    assert [e["player"] for e in plain] == ["Joe Burrow"] and "lineup" not in plain[0]


def test_a_starter_not_playing_yet_adds_nothing():
    assert YP.mine([], IDX, lineup=["Josh Allen"]) == []


# --- the server ---------------------------------------------------------------------------
def test_the_strip_s_ask_carries_the_lineup_and_keeps_nothing():
    view = SERVER[SERVER.index("    def _alerts_get(self, path: str, query: dict | None = None):"):]
    view = view[:view.index('if path != "me":')]
    assert "lineup=YP.lineup_names(((query or {}).get(\"lineup\") or [\"\"])[0]))" in view
    assert 'parsed.path[len("/api/alerts/"):].strip("/"), parse_qs(parsed.query))' in SERVER


def test_the_desk_s_live_mode_is_the_matchup_and_nothing_else():
    desk = SERVER[SERVER.index("    def _league_desk(self, query: dict):"):SERVER.index("    def _league_desk_espn(")]
    assert 'live_only = (query.get("live") or [""])[0] == "1"' in desk
    assert 'if not re.fullmatch(r"[A-Za-z0-9_]{1,40}", user_id):' in desk, "a username is checked before it is read"
    assert 'grab(f"user/{user_id}", ttl=86400)' in desk, "the sync's own cached read"
    assert "if mine and rivals else []) if not live_only else []" in desk, "no trades for the Live tab"
    stop = desk.index("        if live_only:\n            return self._send(200")
    assert desk.index("out[\"live\"] = live") < stop < desk.index("self._desk_extras(") \
        < desk.index("self._remember_lineup_league(league_id, user_id)"), \
        "answered after the matchup, before the pickups and the lineup alert's memory"
    assert '{"league": out["league"], "week": out["week"],\n' in desk[stop:stop + 200]


def test_the_desk_answers_the_live_tab_from_sleeper_s_board():
    """The real handler, over HTTP, with Sleeper's answers and the live
    scoreboard stood in: a username in, the matchup out, no trade ever
    generated and nothing remembered for the lineup alert."""
    import rendercheck
    import server
    from engine import db as DB
    from engine import fantasy_live as FL
    from engine import fantasy_trade as FT
    from engine.sources import fetch as F
    sleeper = {
        "user/fan0": {"user_id": "111", "username": "fan0"},
        "league/123456": {"name": "Sunday Crew", "roster_positions": ["QB", "WR", "BN"],
                          "scoring_settings": {"rec": 1, "rec_yd": 0.1, "pass_yd": 0.04}, "settings": {"leg": 8}},
        "league/123456/rosters": [{"roster_id": 1, "owner_id": "111", "players": ["p1", "p2"], "starters": ["p1", "p2"]},
                                  {"roster_id": 2, "owner_id": "222", "players": ["p3"], "starters": ["p3", "0"]}],
        "league/123456/users": [{"user_id": "111", "display_name": "fan0"}, {"user_id": "222", "display_name": "Rival"}],
        "players/nfl": {"p1": {"first_name": "Josh", "last_name": "Allen", "position": "QB", "team": "BUF"},
                        "p2": {"first_name": "Ja'Marr", "last_name": "Chase", "position": "WR", "team": "CIN"},
                        "p3": {"first_name": "Joe", "last_name": "Burrow", "position": "QB", "team": "CIN"}},
        "league/123456/matchups/8": [{"roster_id": 1, "matchup_id": 4, "starters": ["p1", "p2"],
                                      "players_points": {"p1": 0, "p2": 21.4}},
                                     {"roster_id": 2, "matchup_id": 4, "starters": ["p3", "0"],
                                      "players_points": {"p3": 12.0}}],
    }
    asked, traded, kept = [], [], []

    def fake_fetch(url, cache_name, ttl=0, **kw):
        path = url.split("/v1/", 1)[1]
        asked.append(path)
        if path not in sleeper:
            raise F.DataUnavailable(path)
        return json.dumps(sleeper[path])
    real = (F.fetch_text, DB.connect, FL.scoreboard, FT.generate, server.Handler._remember_lineup_league)
    mem = real[1]
    F.fetch_text = fake_fetch
    DB.connect = lambda *a, **k: mem(":memory:")
    FL.scoreboard = lambda *a, **k: {"CIN": {"state": "live", "frac_left": 0.5, "clock": "Q3 4:12"}}
    FT.generate = lambda *a, **k: traded.append(1) or []
    server.Handler._remember_lineup_league = lambda self, *a: kept.append(a)
    srv, port = rendercheck._serve()
    try:
        url = f"http://127.0.0.1:{port}/api/leaguedesk?live=1&platform=sleeper&league=123456&user=fan0"
        with urllib.request.urlopen(url, timeout=30) as r:
            got = json.loads(r.read())
        try:
            urllib.request.urlopen(url.replace("user=fan0", "user=bad%20name"), timeout=30)
            bad = None
        except urllib.error.HTTPError as exc:
            bad = exc.code
    finally:
        srv.shutdown()
        F.fetch_text, DB.connect, FL.scoreboard, FT.generate, server.Handler._remember_lineup_league = real
    assert set(got) == {"league", "week", "has_me", "live"}, got
    assert got["league"] == "Sunday Crew" and got["week"] == 8 and got["has_me"] is True, got
    live = got["live"]
    assert [p["player"] for p in live["me"]["players"]] == ["Josh Allen", "Ja'Marr Chase"], live
    assert live["me"]["points"] == 21.4 and live["them"]["points"] == 12.0 and live["opponent"] == "Rival", live
    assert live["in_progress"] is True and not live["done"], live
    assert not traded and not kept, "the Live tab's ask builds no trades and remembers nothing"
    assert "user/fan0" in asked and bad == 400


# --- the page, in node --------------------------------------------------------------------
def _fn(src, name):
    i = src.index(f"function {name}(")
    if src[i - 6:i] == "async ":
        i -= 6
    ends = [src.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ", "\n// ")]
    ends = [e for e in ends if e != -1] or [len(src)]
    return src[i:min(ends)]


def test_the_page_asks_once_a_minute_while_a_game_is_on():
    load = _fn(CHAT, "ffLiveLoad")
    assert 'localStorage.getItem("ff_user")' in load and 'localStorage.getItem("ff_league")' in load
    assert "const wait = _ffLive && _ffLive.live && _ffLive.live.in_progress ? 60000 : 300000;" in load
    assert "/api/leaguedesk?live=1&platform=sleeper&league=" in load
    mount = _fn(CHAT, "yourPlayersMount")
    assert 'ffLiveLoad().then(() => fetch("/api/alerts/live" + ffLineupQuery(),' in mount, "names, once known"
    assert "_ypLast = ffLiveHTML() + ypHTML(v.players || []);" in mount
    assert '${r.lineup ? `<span class="yp-ff">${ffPtsText(r.player)}</span>` : ""}' in _fn(CHAT, "ypHTML")


def test_the_matchup_and_the_points_in_node():
    node = shutil.which("node")
    if not node:
        print("      (skipped: no node)")
        return
    key = re.search(r"\nconst ffKey = .*\n", CHAT).group(0)
    prog = f"""
      let store = {{}};
      const localStorage = {{ getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => {{ store[k] = String(v); }} }};
      const SPOIL_KEY = "qb_spoil_v1";
      const chEsc = (s) => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
      let _ffLive = null;
      {key}
      {_fn(CHAT, "ffLineupQuery")}
      {_fn(CHAT, "ffPtsText")}
      {_fn(CHAT, "ffHeld")}
      {_fn(CHAT, "ffLiveHTML")}
      const live = {{ me: {{ points: 21.4, projected: 118.6, players: [
          {{ player: "Ja'Marr Chase", team: "CIN", points: 21.4 }}, {{ player: "Kenneth Walker", team: "SEA", points: 9 }},
          {{ player: null, team: null }}] }},
        them: {{ points: 12, projected: 104.2, players: [{{ player: "Joe Burrow", team: "CIN", points: 12 }}] }},
        win_prob: 0.71, in_progress: true, done: false, opponent: "Rival" }};
      const out = {{ none: ffLiveHTML(), noNames: ffLineupQuery() }};
      _ffLive = {{ league: "Sunday Crew", week: 8, live }};
      out.card = ffLiveHTML();
      out.q = ffLineupQuery();
      out.pts = ffPtsText("Ja'Marr Chase");
      out.suffix = ffPtsText("Kenneth Walker III");
      out.other = ffPtsText("Justin Jefferson");
      store[SPOIL_KEY] = JSON.stringify({{ nfl_401: {{ l: "nfl", a: "BAL", h: "CIN", exp: Date.now() + 3600000 }} }});
      out.held = ffLiveHTML();
      console.log(JSON.stringify(out));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout)
    assert got["none"] == "" and got["noNames"] == ""
    text = re.sub(r"<[^>]+>", " ", got["card"])
    text = re.sub(r"\s+", " ", text).strip()
    assert text == "Your matchup · Sunday Crew · week 8 You 21.4 Rival 12.0 Projected 118.6–104.2 · 71% to win", text
    assert 'class="ffl" href="#fantasy"' in got["card"] and 'class="ffl-up"' in got["card"]
    assert got["q"] == "?lineup=" + "Ja'Marr%20Chase%7CKenneth%20Walker", got["q"]
    assert got["pts"] == "In your lineup · 21.4 pts" and got["suffix"] == "In your lineup · 9.0 pts", got
    assert got["other"] == "In your lineup"
    held = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", got["held"])).strip()
    assert "Spoiler-free: a game in it is saved for later" in held and "21.4" not in held and "71%" not in held, held


# --- in a browser (opt-in) ----------------------------------------------------------------
def test_in_a_browser_the_live_tab_shows_the_matchup_and_the_starter():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    me = {"signed_in": True, "email": "you@example.com", "profile": {"handle": "fan0"}}
    bill = {"configured": True, "signed_in": True, "email": "you@example.com", "paywall": True, "entitled": True,
            "status": "active", "plan": "monthly", "cancel_at_end": False, "plans": [{"id": "monthly", "ready": True}]}
    live = {"me": {"points": 21.4, "projected": 118.6, "players": [
                {"slot": "WR", "player": "Ja'Marr Chase", "team": "CIN", "points": 21.4, "state": "live"},
                {"slot": "QB", "player": "Josh Allen", "team": "BUF", "points": 0, "state": "pre"}]},
            "them": {"points": 12.0, "projected": 104.2, "players": [
                {"slot": "QB", "player": "Joe Burrow", "team": "CIN", "points": 12.0, "state": "live"}]},
            "win_prob": 0.71, "in_progress": True, "done": False, "opponent": "Rival"}
    desk = {"league": "Sunday Crew", "week": 8, "has_me": True, "live": live}
    asked = []

    def players(route):
        asked.append(route.request.url)
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"players": [
            dict(_e("Joe Burrow")), dict(_e("Ja'Marr Chase"), lineup=True)]}))
    ful = lambda b: (lambda r: r.fulfill(status=200, content_type="application/json", body=b))  # noqa: E731
    srv, port = rendercheck._serve()
    errs, got = [], None
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
                page = ctx.new_page()
                page.on("pageerror", lambda e: errs.append(str(e)))
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/account/me*", ful(json.dumps(me)))
                page.route("**/api/billing/status*", ful(json.dumps(bill)))
                page.route("**/api/leaguedesk*", ful(json.dumps(desk)))
                page.route("**/api/alerts/live*", players)
                page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb-seen-intro','1');"
                                     "localStorage.setItem('qb.tour','done');localStorage.setItem('ff_user','fan0');"
                                     "localStorage.setItem('ff_league','123456');}catch(e){}")
                page.goto(f"http://127.0.0.1:{port}/index.html#live", wait_until="load")
                for _ in range(40):                 # the page's CSP refuses wait_for_function's eval
                    if page.evaluate("!!document.querySelector('.ffl') && !!document.querySelector('.yp-ff')"):
                        break
                    page.wait_for_timeout(500)
                got = page.evaluate("""(() => { const a = document.querySelector('.ffl'); const r = a.getBoundingClientRect();
                  return { card: a.textContent.replace(/\\s+/g, ' ').trim(), href: a.getAttribute('href'),
                           fits: r.right <= innerWidth && r.left >= 0,
                           tags: [...document.querySelectorAll('.yp-item')].map((b) => b.textContent.replace(/\\s+/g, ' ').trim()) }; })()""")
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert not errs, errs[:3]
    assert got["href"] == "#fantasy" and got["fits"], got
    assert got["card"] == "Your matchup · Sunday Crew · week 8 You 21.4 Rival 12.0 Projected 118.6–104.2 · 71% to win", got
    assert any("Ja'Marr Chase" in t and "In your lineup · 21.4 pts" in t for t in got["tags"]), got["tags"]
    assert any(t.startswith("Joe Burrow") and "In your lineup" not in t for t in got["tags"]), got["tags"]
    from urllib.parse import unquote
    assert any("lineup=Ja'Marr Chase|Josh Allen" in unquote(u) for u in asked), asked


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
