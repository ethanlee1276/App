"""The Live tab's Play feed opens, and college reads its own halves.

Ethan, 2026-11-14, on the Live tab with 23 college games on: "clicking the
play feed button throws an error and glitches the page." The Games / Play
feed pair is drawn by the same helper as the league chips, with the same
class, and the league chips' handler caught it too: a tap on Play feed set
the league to undefined and the redraw threw on its name ("Cannot read
properties of undefined (reading 'toUpperCase')"), for every league.

And on the same screen: a college game's plays read "Q2 5:46" under a card
that said H2. College plays two halves (app.js halfPeriod): the card's
plays, the feed, the game page's groups, the game chat and the gamecast.
The feed's faces were initials for every league; the live file now keeps
each player's ESPN id, and a play card draws his headshot from it. The Live
tab names the league as the strip does, NCAAB.

    python3 tests/test_the_play_feed_opens_on_college.py
    QB_BROWSER_TESTS=1 python3 tests/test_the_play_feed_opens_on_college.py
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APP = (ROOT / "web" / "js" / "app.js").read_text()
CHAT = (ROOT / "web" / "js" / "chat.js").read_text()
CAST = (ROOT / "web" / "js" / "gamecast.js").read_text()
DETAIL = (ROOT / "web" / "js" / "detail.js").read_text()


def _fn(src, name):
    i = src.index(f"function {name}(")
    j = src.find("\nfunction ", i + 10)
    return src[i:j if j != -1 else len(src)]


def test_only_the_league_chips_set_the_league():
    board = _fn(APP, "renderLiveBoard")
    assert 'host.querySelectorAll(".lb-chip[data-chip]").forEach((b) =>' in board
    assert 'host.querySelectorAll(".lb-chip").forEach' not in board, "the view pair caught by the league handler"
    assert "if (!want) return;" in board
    assert "lgCode(_liveChip)" in board


def test_college_reads_its_halves_everywhere_a_play_is_timed():
    js = f"{_fn(APP, 'halfPeriod')}\nconsole.log(JSON.stringify([0,1,2,3,4,5].map(halfPeriod)));"
    import subprocess
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == ["", "H1", "H2", "OT", "2OT", "3OT"]
    assert 'd.league === "cbb" ? (p) => halfPeriod(p.period)' in _fn(APP, "pbpGroups")
    plays = _fn(APP, "playsHTML")
    assert 'const halves = g.league === "cbb" || String(g.room || "").startsWith("cbb_");' in plays
    assert "halves ? halfPeriod(p.period)" in plays
    assert "playsHTML({ ...g, room: (g.event_id || g.game_pk) ? `${sport}_${g.event_id || g.game_pk}`" in APP, \
        "the live card's room names the league, cbb_..."
    assert DETAIL.count("away: d.away, league, room: pbpRoom(d, league) })") == 2
    assert 'sport === "cbb" ? halfPeriod(p.period)' in _fn(CHAT, "pfItemHTML")
    assert 'CH.league === "cbb" ? halfPeriod(p.period)' in _fn(CHAT, "chatPlayWhen")
    assert 'league === "cbb" ? halfPeriod(p.period)' in CAST


def test_a_play_card_draws_his_face_from_his_espn_id():
    import livescore_build as B
    payload = {"boxscore": {"players": [{"team": {"abbreviation": "DUKE", "id": "150"}, "statistics": [{
        "labels": ["MIN", "PTS"], "names": ["MIN", "PTS"], "keys": ["minutes", "points"],
        "athletes": [{"athlete": {"id": "4433137", "displayName": "Cooper Flagg", "headshot": {
            "href": "https://a.espncdn.com/i/headshots/mens-college-basketball/players/full/4433137.png"},
            "position": {"abbreviation": "F"}}, "starter": True, "stats": ["30", "21"]}]}]}]}}
    rows = B.pbp_players("cbb", payload, {"home": "DUKE", "away": "UNC"})
    if rows:                                               # the parser's own shape decides
        assert rows[0].get("id") == "4433137", rows[0]
    src = (ROOT / "livescore_build.py").read_text()
    assert 'if r.get("espn_id"):\n            row["id"] = str(r["espn_id"])' in src
    # In chat.js, which loads with the feed: the first page has no room for it.
    assert "function espnFace(league, id)" in CHAT and 'cbb: "mens-college-basketball"' in CHAT
    body = _fn(CHAT, "pcBodyHTML")
    assert "function pcBodyHTML(p, d, plays, full, league)" in body
    assert "espnFace(league, row.id)" in body and "headshot: shot || null" in body
    assert "pcBodyHTML(p, g, g.big || [], false, sport)" in CHAT and "pcBodyHTML(p, d, chatAllPlays(), true, CH.league)" in CHAT


def test_the_live_tab_names_the_league_as_the_strip_does():
    card = _fn(APP, "liveCardHTML")
    assert '<span class="lb-league">${escapeHtml(lgCode(sport))}</span>' in card
    assert 'label: s === "all" ? "All" : lgCode(s),' in _fn(APP, "renderLiveBoard")
    assert 'const lgCode = (s) => LEAGUE_LABEL[s] || String(s || "").toUpperCase();' in APP
    assert re.search(r'cbb: "NCAAB"', APP)
    assert "escapeHtmllgCode" not in APP and not re.search(r"[A-Za-z_]lgCode\(", APP), "a call folded into a name"


# --- in a browser ---------------------------------------------------------------------
def _live():
    def play(i, period, clock, team, player, event, scoring, pts, a, h):
        return {"kind": "hoops", "id": f"9{i}", "period": period, "clock": clock, "team": team, "player": player,
                "event": event, "scoring": scoring, "shot": True, "points": pts, "away_score": a,
                "home_score": h, "at": f"2026-11-14T01:{10 + i:02d}:00Z", "rating": 6.5, "wpa": 20.0}

    def game(eid, home, away, period, plays, players):
        return {"event_id": eid, "home": home, "away": away, "home_name": f"{home} U", "away_name": f"{away} U",
                "live": {"state": "live", "home_score": plays[-1]["home_score"],
                         "away_score": plays[-1]["away_score"], "period": f"H{period}", "clock": "5:01"},
                "plays_state": "fresh", "plays": plays, "big": plays, "players": players}
    g1 = game("401", "FSU", "AMCC", 2,
              [play(1, 1, "4:10", "FSU", "Kam Taylor", "Three Point Jumper", True, 3, 30, 41),
               play(2, 2, "5:46", "FSU", "Cooper Schwieger", "Dunk Shot", True, 2, 49, 75)],
              [{"player": "Cooper Schwieger", "team": "FSU", "position": "F", "id": "5104567",
                "stats": {"pts": 12.0, "reb": 7.0}},
               {"player": "Kam Taylor", "team": "FSU", "position": "G", "stats": {"pts": 9.0}}])
    g2 = game("402", "FLA", "MRMK", 2,
              [play(3, 3, "1:12", "FLA", "Isaiah Brown", "Layup", True, 2, 70, 72)],
              [{"player": "Isaiah Brown", "team": "FLA", "position": "G", "id": "5100001", "stats": {"pts": 14.0}}])
    return {"generated_at": "2026-11-14T01:30:00Z", "league": "cbb", "games": [g1, g2]}


def _run():
    from playwright.sync_api import sync_playwright
    import rendercheck
    srv, port = rendercheck._serve()
    body = json.dumps(_live())
    out, errs = {}, []
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": 382, "height": 580}, service_workers="block",
                                          is_mobile=True, has_touch=True)
                page = ctx.new_page()
                page.on("pageerror", lambda e: errs.append(str(e)))
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/data/live_cbb.json*", lambda r: r.fulfill(status=200, content_type="application/json",
                                                                          body=body))
                page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
                page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb.tour','done');"
                                     "localStorage.removeItem('qb_live_view');}catch(e){}")
                page.goto(f"http://127.0.0.1:{port}/index.html?sport=cbb#live", wait_until="load")
                page.wait_for_timeout(2500)
                out["games"] = page.evaluate("""() => ({
                  text: document.getElementById('live-board').innerText,
                  chips: [...document.querySelectorAll('.lb-chip[data-chip]')].map((b) => b.textContent.trim()),
                  tags: [...document.querySelectorAll('.lb-league')].map((e) => e.textContent.trim())})""")
                page.click('[data-live-view="feed"]')
                page.wait_for_timeout(2000)
                out["feed"] = page.evaluate("""() => ({
                  items: document.querySelectorAll('.pf-item').length,
                  when: [...document.querySelectorAll('.pf-when')].map((e) => e.textContent.trim()),
                  photos: [...document.querySelectorAll('.pf-item img.avatar-photo')].map((i) =>
                    i.getAttribute('src') || i.getAttribute('data-src') || ''),
                  pressed: document.querySelector('[data-live-view="feed"]').getAttribute('aria-pressed')})""")
                page.click('[data-live-view="games"]')
                page.wait_for_timeout(1200)
                page.click('.lb-chip[data-chip="all"]')
                page.wait_for_timeout(1200)
                out["after"] = page.evaluate("""() => ({
                  all: document.querySelector('.lb-chip[data-chip="all"]').getAttribute('aria-pressed'),
                  cards: document.querySelectorAll('#live-board .lb-card').length})""")
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    return out, errs


def test_in_a_browser_the_play_feed_opens_and_reads_halves():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("skip: set QB_BROWSER_TESTS=1")
        return
    out, errs = _run()
    assert not errs, errs
    g = out["games"]
    assert "H2 5:46" in g["text"] and "Q2" not in g["text"], g["text"][:600]
    assert "NCAAB 2" in g["chips"] and "CBB 2" not in g["chips"], g["chips"]
    assert g["tags"] and set(g["tags"]) == {"NCAAB"}, g["tags"]
    f = out["feed"]
    assert f["pressed"] == "true" and f["items"] == 3, f
    assert set(f["when"]) == {"H2 5:46", "H1 4:10", "OT 1:12"}, f["when"]
    assert any("mens-college-basketball/players/full/5104567.png" in s or "5104567" in s for s in f["photos"]), f
    assert out["after"] == {"all": "true", "cards": 2}, out["after"]


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
