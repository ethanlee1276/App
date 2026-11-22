"""Every game parlay and touchdown pair can be bet whole (2026-11-15).

Ethan, with a game report's three-leg parlays on screen: "we should add bet it
buttons that adds the whole parlay too your sports book. Both td parlays and
player prop parlays." Two pieces:

  * engine/betlinks stamps every leg of every posted game parlay with the
    books that hold it (`bet_links`). The legs sit under the board's
    "game_parlays" → "games", a key the walk skips for speed, so until now no
    leg carried a link at all.
  * js/report.js gives every ticket a Bet it button (the site's own sheet).
    A book holding every leg in a form that joins — FanDuel's indexed
    `marketId[0]` / `selectionId[0]`, the feed's tail rule
    (engine/socialfeed.combine_links) — gets one tile for the whole slip; a
    book holding every leg in another form gets a tile per leg, which stack on
    its slip; the rest are front doors. Nothing is guessed.

    python3 tests/test_a_parlay_is_bet_whole.py
    QB_BROWSER_TESTS=1 python3 tests/test_a_parlay_is_bet_whole.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from engine import betlinks as B, socialfeed as SF  # noqa: E402

REPORT_JS = os.path.join(ROOT, "web", "js", "report.js")
DK = "https://sportsbook.draftkings.com/event/1?outcomes="
FD = "https://sportsbook.fanduel.com/addToBetslip"


def _o(name, price, link, point=None, desc=None):
    o = {"name": name, "price": price, "link": link}
    if point is not None:
        o["point"] = point
    if desc:
        o["description"] = desc
    return o


def _fd(m, sel):
    return f"{FD}?marketId[0]={m}&selectionId[0]={sel}"


def _event():
    return {"id": "ev1", "commence_time": "2026-11-15T18:00:00Z",
            "home_team": "Buffalo Bills", "away_team": "Los Angeles Chargers",
            "bookmakers": [
                {"key": "draftkings", "link": "https://sportsbook.draftkings.com/event/1", "markets": [
                    {"key": "player_pass_yds", "outcomes": [_o("Over", -110, DK + "allen-o", 249.5, "Josh Allen")]},
                    {"key": "player_rush_yds_alternate", "outcomes": [_o("Over", -180, DK + "cook-60", 60.5, "James Cook")]},
                    {"key": "player_receptions", "outcomes": [_o("Over", -150, DK + "shakir-o", 3.5, "Khalil Shakir")]},
                    {"key": "player_anytime_td", "outcomes": [_o("Yes", 120, DK + "cook-td", None, "James Cook"),
                                                              _o("Yes", 210, DK + "kincaid-td", None, "Dalton Kincaid")]}]},
                {"key": "fanduel", "link": "https://sportsbook.fanduel.com/event/1", "markets": [
                    {"key": "player_pass_yds", "outcomes": [_o("Over", -105, _fd("734.1", "11"), 249.5, "Josh Allen")]},
                    {"key": "player_rush_yds_alternate", "outcomes": [_o("Over", -175, _fd("734.2", "22"), 60.5, "James Cook")]},
                    {"key": "player_receptions", "outcomes": [_o("Over", -145, _fd("734.3", "33"), 3.5, "Khalil Shakir")]},
                    {"key": "player_anytime_td", "outcomes": [_o("Yes", 115, _fd("734.4", "44"), None, "James Cook"),
                                                              _o("Yes", 200, _fd("734.4", "55"), None, "Dalton Kincaid")]}]},
                # Holds one leg only: offered for that leg, never as the ticket.
                {"key": "betmgm", "link": "https://sports.mi.betmgm.com/en/sports/events/1", "markets": [
                    {"key": "player_pass_yds", "outcomes": [_o("Over", -110, "https://sports.mi.betmgm.com/en/sports?options=a",
                                                               249.5, "Josh Allen")]}]},
            ]}


def _leg(player, market, side, line, odds, label, p):
    return {"player": player, "team": "BUF", "opponent": "LAC", "home": "BUF", "away": "LAC", "market": market,
            "market_label": label, "side": side, "line": line, "odds": odds, "book": "DraftKings", "p": p}


def _payload():
    three = {"joint": 0.4, "independent": 0.35, "fair_words": "+150", "take_words": "+160",
             "legs": [_leg("Josh Allen", "pass_yds", "OVER", 249.5, -110, "Passing Yards", 0.66),
                      _leg("James Cook", "rush_yds", "OVER", 60.5, -180, "Rushing Yards", 0.7),
                      _leg("Khalil Shakir", "receptions", "OVER", 3.5, -150, "Receptions", 0.68)]}
    pair = {"joint": 0.2, "independent": 0.18, "fair_words": "+400", "take_words": "+420",
            "legs": [_leg("James Cook", "anytime_td", "Yes", 0.5, 120, "Anytime TD", 0.46),
                     _leg("Dalton Kincaid", "anytime_td", "Yes", 0.5, 210, "Anytime TD", 0.42)]}
    return {"recommendations": [],
            "game_parlays": {"sport": "nfl", "games": [{"game": "LAC@BUF", "home": "BUF", "away": "LAC",
                                                        "threes": [three], "scorers": [pair]}]}}


def _stamped():
    with tempfile.TemporaryDirectory() as tmp:
        B.bank(json.dumps(_event()), "odds_event_nfl_ev1_abcd1234.json", cache_dir=tmp)
        payload = _payload()
        n = B.stamp(payload, "recommendations.json", env={"QB_BET_STATE": "mi"}, cache_dir=tmp)
    return payload, n


def test_every_leg_of_every_posted_ticket_is_linked():
    payload, n = _stamped()
    g = payload["game_parlays"]["games"][0]
    legs = g["threes"][0]["legs"] + g["scorers"][0]["legs"]
    assert n == 5, n
    for l in legs:
        books = [x[0] for x in l.get("bet_links") or []]
        assert {"DraftKings", "FanDuel"} <= set(books), (l["player"], books)
        assert len(books) <= B.PARLAY_LINKS
    allen = g["threes"][0]["legs"][0]
    assert [x[0] for x in allen["bet_links"]][0] == "DraftKings", "the leg's own book first"
    assert "BetMGM" in [x[0] for x in allen["bet_links"]]
    # The legs the walk would have skipped: they sit under "games".
    assert "games" in B.SKIP_KEYS


def test_the_heartbeat_counts_the_linked_legs():
    """The tickets are a paid key: the heartbeat is where a live check sees
    their legs were linked (launch._board_counts)."""
    import launch as L
    payload, _ = _stamped()
    payload["game_parlays"]["counts"] = {"games": 1, "threes": 1, "scorers": 1}
    payload["game_parlays"]["games"][0]["scorers"][0]["legs"][1].pop("bet_links")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "b.json")
        with open(path, "w") as fh:
            json.dump(dict(payload, most_likely=[], game_bets=[]), fh)
        was = L._full_copy
        L._full_copy = lambda p: p
        try:
            got = L._board_counts(path)
        finally:
            L._full_copy = was
    assert (got["parlay_legs"], got["parlay_legs_linked"]) == (5, 4), got

def _fd_urls(legs):
    return [next(u for t, u, px in l["bet_links"] if t == "FanDuel") for l in legs]


def test_the_feeds_rule_joins_fanduels_legs_and_nothing_else():
    payload, _ = _stamped()
    legs = payload["game_parlays"]["games"][0]["threes"][0]["legs"]
    one = SF.combine_links(_fd_urls(legs))
    assert one == (f"{FD}?marketId[0]=734.1&selectionId[0]=11&marketId[1]=734.2&selectionId[1]=22"
                   f"&marketId[2]=734.3&selectionId[2]=33"), one
    dks = [next(u for t, u, px in l["bet_links"] if t == "DraftKings") for l in legs]
    assert SF.combine_links(dks) == "", "a format that cannot be shown to join is never joined"


def _node(script):
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not os.path.exists(node):
        return None
    head = ("const vm = require('vm'); const fs = require('fs');"
            "const esc = (s) => String(s == null ? '' : s).replace(/[&<>\"']/g, (c) => '&#' + c.charCodeAt(0) + ';');"
            "const ctx = { window: {}, URL, escapeHtml: esc, escapeAttr: esc,"
            " slugify: (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-'),"
            " teamName: (t) => t, playerAvatar: () => '' };"
            "vm.createContext(ctx);"
            f"vm.runInContext(fs.readFileSync({json.dumps(REPORT_JS)}, 'utf8'), ctx);"
            "const R = ctx.window.QBReport;")
    out = subprocess.run([node, "-e", head + script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout)


#: The app's own tile and door makers (js/app.js), as the page has them.
APP_STUBS = ("ctx.bookTileHTML = (t, u, px, sub, tag) => `<a class=\"bk-tile\" href=\"${u}\" data-t=\"${t}\">${sub}|${tag || ''}</a>`;"
             "ctx.bookHomeTilesHTML = (skip) => '<a class=\"bk-tile door\">door</a>';"
             "ctx.bookKey = (t) => String(t).toLowerCase(); ctx.storeApp = () => '';")


def test_every_game_s_tickets_get_the_button():
    """Each game's tickets as Report Picks draws them (gameTickets; the
    Parlays page that drew them too left every league 2026-11-16)."""
    payload, _ = _stamped()
    gp = payload["game_parlays"]
    got = _node(APP_STUBS + f"const gp = {json.dumps(gp)};"
                "process.stdout.write(JSON.stringify({html: gp.games.map((g) => R.gameTickets(g, 'nfl')).join('')}));")
    if got is None:
        print("      (skipped: no Node)")
        return
    html = got["html"]
    assert html.count('<span class="betit-box gr-betit"><button type="button" class="betit" aria-haspopup="dialog">Bet it</button>') == 2
    fd_three = (f'href="{FD}?marketId[0]=734.1&selectionId[0]=11&marketId[1]=734.2&selectionId[1]=22'
                f'&marketId[2]=734.3&selectionId[2]=33" data-t="FanDuel">all 3 legs · one slip|')
    assert fd_three in html, html[:3000]
    assert f'href="{FD}?marketId[0]=734.4&selectionId[0]=44&marketId[1]=734.4&selectionId[1]=55" data-t="FanDuel">all 2 legs · one slip|' in html
    for i in (1, 2, 3):
        assert f'data-t="DraftKings">bet slip|Leg {i} of 3</a>' in html, i
    assert "The whole ticket, one slip" in html and "Or leg by leg" in html
    assert 'data-t="BetMGM"' not in html, "a book holding one leg of three is no way to bet the ticket"
    assert "Three-leg parlay 1 · Josh Allen over 249.5 passing yards + James Cook over 60.5 rushing yards" in html
    for bad in ("undefined", "[object", "NaN"):
        assert bad not in html, bad


def test_the_game_reports_tickets_find_their_legs_and_no_store_app_bets():
    payload, _ = _stamped()
    g = payload["game_parlays"]["games"][0]
    card = {"title": "Parlay 1", "price_line": "40% by our numbers", "legs": [{"pick": "Josh Allen over 249.5 passing yards"}]}
    rep = {"game": "LAC@BUF", "title": "Chargers at Bills", "sections": [
        {"key": "short", "title": "The short version", "blocks": [{"type": "list", "items": ["One."]}]},
        {"key": "parlays", "title": "Parlays for this game", "blocks": [
            {"type": "parlays", "kind": "three", "items": [card]},
            {"type": "parlays", "kind": "scorers", "items": [dict(card, title="Touchdown pair 1")]}]}]}
    got = _node(APP_STUBS + f"const rep = {json.dumps(rep)}; const g = {json.dumps(g)};"
                "const a = R.html(rep, {parlays: g}); const none = R.html(rep, {});"
                "ctx.storeApp = () => 'ios'; const store = R.html(rep, {parlays: g});"
                "process.stdout.write(JSON.stringify({a, none, store}));")
    if got is None:
        print("      (skipped: no Node)")
        return
    assert got["a"].count('class="betit-box gr-betit"') == 2
    assert "marketId[2]=734.3" in got["a"] and "marketId[1]=734.4&selectionId[1]=55" in got["a"]
    assert "betit" not in got["none"], "no tickets handed over: no button"
    assert "betit" not in got["store"], "the store app opens no sportsbook"


def test_the_page_joins_exactly_as_the_feed_does():
    vectors = [
        [_fd("1.1", "11"), _fd("2.2", "22")],
        [DK + "a", DK + "b"],
        [_fd("1.1", "11"), "https://other.example/x?marketId[0]=2&selectionId[0]=3"],
        [_fd("1.1", "11")],
        [f"{FD}?marketId=1&selectionId=2", f"{FD}?marketId=3&selectionId=4"],
        [f"{FD}?marketId[0]=1&selectionId[0]=2&tab=x", f"{FD}?marketId[0]=3&selectionId[0]=4&tab=x"],
        [f"{FD}?marketId[0]=1&selectionId[0]=2&tab=x", f"{FD}?marketId[0]=3&selectionId[0]=4&tab=y"],
    ]
    got = _node(f"const v = {json.dumps(vectors)};"
                "process.stdout.write(JSON.stringify(v.map((u) => R.slipCombine(u))));")
    if got is None:
        print("      (skipped: no Node)")
        return
    want = [SF.combine_links(v) for v in vectors]
    assert got == want, (got, want)
    assert want[0] and not want[1] and not want[2] and want[3] == vectors[3][0] and not want[4] and want[5] and not want[6]


def test_in_a_browser_the_button_opens_the_sheet_with_the_whole_slip():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    payload, _ = _stamped()
    board = {"sport": "nfl", "date": "2026-11-15", "recommendations": [], "most_likely": [],
             "games": [{"home": "BUF", "away": "LAC", "date": "2026-11-15", "kickoff": "13:00"}],
             "game_parlays": payload["game_parlays"]}
    body = json.dumps(board)
    srv, port = rendercheck._serve()
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                          service_workers="block", bypass_csp=True)
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)[:300]))
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                for pat in ("**/api/recommendations*", "**/data/recommendations*.json*"):
                    page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=body))
                # Report Picks, where each game's tickets carry the button (an old
                # #parlays link opens the Best Parlays page since 21 November, whose
                # cards wear the same button: tests/test_the_best_parlays_are_ranked_on_their_own_page.py).
                page.goto(f"http://127.0.0.1:{port}/#reportpicks", wait_until="load")
                page.wait_for_function("document.querySelectorAll('.gr-betit .betit').length >= 2", timeout=20000)
                assert page.evaluate("location.hash") == "#reportpicks", page.evaluate("location.hash")
                page.evaluate("document.querySelector('.rpk-game').open = true")
                page.click(".gr-parlay .gr-betit .betit")
                page.wait_for_function("document.body.classList.contains('betit-open')", timeout=5000)
                tiles = page.evaluate("""[...document.querySelectorAll('#betit-sheet .bk-tile')].map((a) => ({
                    href: a.getAttribute('href'), text: a.textContent.replace(/\\s+/g, ' ').trim()}))""")
                whole = [t for t in tiles if "one slip" in t["text"]]
                assert len(whole) == 1 and "marketId[2]=734.3" in whole[0]["href"], tiles
                assert sum(1 for t in tiles if "Leg " in t["text"]) == 3, tiles
                assert page.inner_text("#betit-sheet .betit-head").startswith("Bet it")
                assert not errors, errors
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()


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
                traceback.print_exc(limit=6)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
