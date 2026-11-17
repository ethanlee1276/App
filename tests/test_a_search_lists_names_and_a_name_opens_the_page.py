"""A search lists names; a name opens the player's page (2026-11-17).

Ethan, with two screenshots, the pick page a search card had opened circled
beside the new player page's "Tonight's markets" card: "let's get rid of this
page in the screenshot that's circled and replace it with the actual player
page we just added, then we will show that chart like how you have it in the
other screenshot. So when you search a player it will just show there name and
headshot then the user had too click on there name and it will pull them to
the actual player page."

So (web/js/app.js renderPlayers):

  * a search, and the page before anything is typed, answer with rows of a
    face and a name (the club and position under it, for two players who
    share a name); no cards;
  * each row is a door to #player/<name> (the [data-player-page] listener),
    which is the one place the view draws a player's card: the market card on
    the player's own page, at full depth, opening nothing (the pick page left
    the player's flow), with the pick page's Bet it and Ask on it;
  * the back bar names the search and brings its words back;
  * a name tapped needs no second search; a Trending row opens the page; a
    recent chip is a search; a fighter's page is the card of career rates.

    python3 tests/test_a_search_lists_names_and_a_name_opens_the_page.py
    QB_BROWSER_TESTS=1 python3 tests/test_a_search_lists_names_and_a_name_opens_the_page.py
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

from _app import app_js, decl  # noqa: E402

APP = app_js()
PAGE = open(os.path.join(ROOT, "web", "js", "playerpage.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()


def _render():
    i = APP.index("async function renderPlayers(")
    return APP[i:APP.index("\n/* The UFC hero", i)]


def test_a_search_and_the_page_before_it_list_names_not_cards():
    body = decl("renderPlayers")
    assert "  const routed = !!(q && state.playerSlug);\n" in body, "the address, not the words typed, draws a card"
    # Every answer a search can give is the list: the board's names, the league's, the rosters'.
    assert "searchListHTML(shown.map((p) => _profRows.get(p)[0]))" in body
    assert "${searchListHTML(hits)}" in body
    assert "${searchListHTML(misses.map((m) => ({ ...m, sport: state.sport })))}" in body
    # And a card only where the address names the player.
    assert body.count("profileHTML(") == 2 and body.count("{ deep: true, inPage: true }") == 2
    assert body.count("renderPlayerPage(") == 3, "priced tonight, from the league, known only to a roster"
    assert "Tonight’s players" in body and "everyone with a prop on tonight’s" in body, "the page before a search says what it lists"
    assert "data-lookup" not in body and "roster-hit" not in body, "the old Profile and Roster buttons"


def test_a_row_is_a_face_a_name_and_a_door_to_the_page():
    row = decl("searchRowHTML")
    assert '<button type="button" class="psr-row" data-player-page="${escapeAttr(slugify(m.player))}"' in row
    assert "playerAvatar(m.player, m.team, { size: 44, headshot: m.headshot })" in row
    assert 'class="psr-go" aria-hidden="true"' in row
    # The focus ring is the site's own (styles.css :where(… button …):focus-visible).
    for sel in (".psr-list {", ".psr-row {", ".psr-row:hover {", ".psr-who {", ".psr-nm {", ".psr-sub {", ".psr-go {"):
        assert sel in CSS, sel
    assert ".psr-row::before {" in CSS and "background: var(--psr-c); }" in CSS, "the club's stripe"
    assert "\n  --psr-c: var(--brand);\n" in CSS, "a row with no club wears the brand's"
    assert "min-height: 64px;" in CSS[CSS.index(".psr-row {"):CSS.index("}", CSS.index(".psr-row {"))], "a thumb's target"


def test_a_tapped_name_needs_no_second_search_and_keeps_its_spelling():
    lst = decl("searchListHTML")
    assert "_searchListed.clear();" in lst and "_searchListed.set(slugify(m.player), m);" in lst
    body = decl("renderPlayers")
    assert "const tapped = routed ? _searchListed.get(state.playerSlug) : null;" in body
    assert "const hits = tapped ? [tapped] : await leagueSearchAfterPause(q, seq, host);" in body
    route = decl("openPlayerRoute")
    assert "const name = shown || (_searchListed.get(slugify(slug)) || {}).player || deslug(slug);" in route


def test_trending_opens_the_page_and_a_recent_chip_searches():
    assert "if (name) openPlayerRoute(slugify(name), name);" in decl("openPlayer")
    search = decl("searchFor")
    assert 'state.playerSlug = "";' in search and "state.search = q;" in search and "renderPlayers();" in search
    i = APP.index('e.target.closest(".sr-chip")')
    assert "searchFor(chip.dataset.q);" in APP[i:i + 200]


def test_a_fighters_page_is_the_card_of_career_rates():
    body = decl("renderPlayers")
    i = body.index('if (m.sport === "ufc") {')
    assert 'host.innerHTML = `<div class="player-grid">${ufcProfileHTML(m)}</div>`;' in body[i:i + 160]
    assert i < body.index("leagueLogs(m.player, m.sport)"), "a fighter has no game logs to ask for"


def test_the_page_is_handed_one_players_card_and_heads_it():
    i = PAGE.index("function renderPlayerPage(host, player, sport) {")
    mount = PAGE[i:PAGE.index("\n}\n", i)]
    assert "plrCardOf" not in PAGE and ".roster-hit" not in mount, "nothing left to sort out"
    i = PAGE.index("function plrMarkets(page, kept) {")
    markets = PAGE[i:PAGE.index("\n}\n", i)]
    assert ('if (tonight.firstElementChild) tonight.insertAdjacentHTML("afterbegin", '
            '`<h3 class="plr-h">${plrTonightTitle(page)}</h3>`);') in markets


def test_the_browse_shows_rows_enough_to_fill_a_screen():
    cap = decl("playerBrowseCap")
    assert '"(max-width: 760px)").matches) ? 12 : 30;' in cap


def _whole(name):
    """A small top-level function of app.js, to its closing brace. The site's
    escaper is read this way: its quote characters lose `decl`'s tokenizer."""
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}", i) + 2]


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(js)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=60)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout)


def test_rows_drawn_from_a_board_a_league_and_a_fight_card():
    prog = "\n".join([
        "var state = { sport: 'nfl' };",
        _whole("escapeHtml"), decl("pluralWord"), _whole("plural"), decl("slugify"),
        "function escapeAttr(s) { return escapeHtml(s); }",
        "var playerAvatar = (n, t, o) => `<i class=\"av\" data-face=\"${escapeAttr(o.headshot || '')}\" data-size=\"${o.size}\"></i>`;",
        "var teamMarkIn = (lg, t, n) => `<b class=\"mk\" data-lg=\"${lg}\">${t}</b>`;",
        "var teamNameIn = (lg, t) => ({ BUF: 'Bills', LV: 'Aces' })[t] || t;",
        "var teamPrimaryIn = (lg, t) => ({ BUF: '#00338D', LV: '#A7A9AC' })[t] || '#888888';",
        "var injTag = (lg, p) => p === 'Josh Allen' ? ` <span class=\"inj-tag\" data-lg=\"${lg}\">Q</span>` : '';",
        "var leagueBadge = (s) => `<span class=\"lg-badge\">${s}</span>`;",
        decl("_searchListed"), decl("searchListHTML"), decl("searchRowHTML"),
        """var out = {
          qb: searchRowHTML({ player: "Josh Allen", team: "BUF", position: "QB", headshot: "https://x.test/ja.png", sport: "nfl" }),
          board: searchRowHTML({ player: "James Cook", team: "BUF", position: "RB" }),
          odd: searchRowHTML({ player: '<img src=x onerror=1>', team: "BUF", position: '"QB"', sport: "nfl" }),
          away: searchRowHTML({ player: "A'ja Wilson", team: "LV", position: "F", sport: "wnba" }),
        };
        state.sport = "ufc";
        out.fighter = searchRowHTML({ player: "Islam Makhachev", sport: "ufc", team: "", games: 15,
                                      fighter: { division: "light_heavyweight" } });
        out.list = searchListHTML([{ player: "Ja'Marr Chase", team: "CIN", position: "WR" }, { player: "Josh Allen", team: "BUF" }]);
        out.listed = [..._searchListed.keys()];
        console.log(JSON.stringify(out));""",
    ])
    got = _node(prog)
    if got is None:
        print("      (skipped: no node)")
        return
    qb = got["qb"]
    assert 'data-player-page="josh-allen"' in qb and ">Josh Allen" in qb, qb
    assert 'data-face="https://x.test/ja.png" data-size="44"' in qb, "the face, at the row's size"
    assert '<span class="inj-tag" data-lg="nfl">Q</span>' in qb, "the designation beside the name"
    assert '<b class="mk" data-lg="nfl">BUF</b><span>Bills · QB</span>' in qb, qb
    assert "--psr-c:#00338D" in qb and "lg-badge" not in qb
    assert 'data-player-page="james-cook"' in got["board"] and "<span>Bills · RB</span>" in got["board"], "a board row has no league: the tab's"
    odd = got["odd"]
    assert "<img src=x" not in odd and "&lt;img src=x onerror=1&gt;" in odd and "&quot;QB&quot;" in odd, odd
    assert 'data-player-page="img-src-x-onerror-1"' in odd
    away = got["away"]
    assert '<span class="lg-badge">wnba</span>' in away and 'data-player-page="a-ja-wilson"' in away, "another league says so"
    assert '<b class="mk" data-lg="wnba">LV</b><span>Aces · F</span>' in away, "its own league's club"
    fighter = got["fighter"]
    assert "<span>light heavyweight · tracked 15 fights</span>" in fighter and 'class="mk"' not in fighter, fighter
    assert "--psr-c" not in fighter, "no club: the stylesheet's own stripe, the brand's"
    assert got["list"].startswith('<div class="psr-list">') and got["list"].count('class="psr-row"') == 2
    assert got["listed"] == ["ja-marr-chase", "josh-allen"], got["listed"]


# --- in a browser ------------------------------------------------------------
LOGS = [{"value": v, "week": w, "opponent": o, "home": h} for v, w, o, h in
        ((252, 11, "NYJ", False), (301, 10, "MIA", False), (198, 9, "KC", True), (276, 8, "NE", True))]


def _rec(player, team, opp, pos, market, label, line, grade):
    return {"player": player, "team": team, "opponent": opp, "position": pos, "market": market,
            "market_label": label, "side": "OVER", "line": line, "odds": -110, "book": "DraftKings",
            "book_name": "DraftKings", "projection": line + 12.4, "hit_prob": 0.58, "raw_prob": 0.6, "edge": 0.05,
            "grade": grade, "recommended": True, "logs": LOGS, "headshot": "", "sport": "nfl",
            "form": {"last1": 252, "last3": 250.3, "last5": 253.4, "last10": 248.0, "season": 251.2},
            "bet_links": [["DraftKings", "https://sportsbook.draftkings.test/x", -110]], "reasons": ["Volume up"]}


def _browser(run):
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return None
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return None
    import rendercheck
    srv, port = rendercheck._serve()
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                return run(browser, port)
            finally:
                browser.close()
    finally:
        srv.shutdown()


def test_in_a_browser_a_name_is_a_door_to_the_page_and_back():
    board = {"sport": "nfl", "player_stats": {}, "recommendations": [
        _rec("Josh Allen", "BUF", "MIA", "QB", "pass_yds", "Passing Yards", 245.5, "A"),
        _rec("James Cook", "BUF", "MIA", "RB", "rush_yds", "Rushing Yards", 70.5, "B+"),
        _rec("Tyreek Hill", "MIA", "BUF", "WR", "rec_yds", "Receiving Yards", 66.5, "B")]}
    shell = {"sport": "nfl", "team": "", "position": "", "seasons": [2026], "season": 2026,
             "bio": {"number": "7"}, "notes": {}, "headline": [], "splits": {"rows": [], "groups": []},
             "career": {"rows": [], "groups": [], "total": {}}}
    hits = {"players": [{"player": "Jacoby Brissett", "sport": "nfl", "team": "ARI", "position": "QB", "games": 56,
                         "rank": 0, "headshot": ""},
                        {"player": "Jacob Rodriguez", "sport": "nfl", "team": "MIA", "position": "LB", "games": 9,
                         "rank": 3, "headshot": ""}]}

    def run(browser, port):
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                  device_scale_factor=1, service_workers="block")
        page = ctx.new_page()
        errors, asked = [], []
        page.on("pageerror", lambda e: errors.append(str(e)))
        local = f"http://127.0.0.1:{port}/"
        page.route(lambda u: not u.startswith(local), lambda r: r.abort())

        def answer(obj):
            return lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(obj))

        def own_page(route):
            from urllib.parse import parse_qs, urlsplit
            q = parse_qs(urlsplit(route.request.url).query)
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps(dict(shell, player=q.get("player", [""])[0], team=q.get("team", [""])[0])))

        def search(route):
            asked.append(route.request.url)
            route.fulfill(status=200, content_type="application/json", body=json.dumps(hits))
        for pattern, obj in (("**/api/players/gamelog*", {}),
                             ("**/api/players/logs*", {"player": "x", "stats": {"Passing Yards": LOGS}}),
                             ("**/data/news.json*", {"sports": {"nfl": []}}),
                             ("**/api/recommendations*", board), ("**/data/recommendations*", board)):
            page.route(pattern, answer(obj))
        page.route("**/api/players/page*", own_page)
        page.route("**/api/players/search*", search)
        page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb.tour','done');}"
                             "catch(e){}")
        names = "els => els.map((e) => e.textContent.trim())"
        page.goto(f"{local}index.html?sport=nfl#players", wait_until="load")
        page.wait_for_selector("#players-board .psr-row", timeout=30000)
        out = {"landing": page.eval_on_selector_all("#players-board .psr-nm", names),
               "landing_cards": page.evaluate("() => document.querySelectorAll('#players-board .profile').length"),
               "landing_head": page.inner_text("#players-board .section-title")}
        page.fill("#player-search", "jacoby")
        page.wait_for_function("() => document.querySelectorAll('#players-board .psr-row').length === 2", timeout=30000)
        out["found"] = page.eval_on_selector_all("#players-board .psr-nm", names)
        out["found_head"] = page.inner_text("#players-board .section-title")
        page.click(".psr-row[data-player-page='jacoby-brissett']")
        page.wait_for_selector(".plr .plr-hero", timeout=30000)
        page.wait_for_timeout(500)
        out["page"] = {"hash": page.evaluate("() => location.hash"), "box": page.input_value("#player-search"),
                       "hero": page.inner_text(".plr-hero"),
                       "bar": page.evaluate("() => (document.querySelector('#view-players > .way-back') || {}).textContent || ''").strip(),
                       "card": page.evaluate("() => !!document.querySelector('.plr-tonight .profile')"),
                       "rows": page.evaluate("() => document.querySelectorAll('#players-board .psr-row').length")}
        page.click("#view-players > .way-back [data-way-back]")
        page.wait_for_function("() => location.hash === '#players' && !state.playerSlug", timeout=8000)
        page.wait_for_selector("#players-board .psr-row", timeout=8000)
        out["back"] = {"box": page.input_value("#player-search"),
                       "rows": page.eval_on_selector_all("#players-board .psr-nm", names)}
        page.fill("#player-search", "josh allen")
        page.wait_for_selector(".psr-row[data-player-page='josh-allen']", timeout=30000)
        out["priced_list_cards"] = page.evaluate("() => document.querySelectorAll('#players-board .profile').length")
        page.click(".psr-row[data-player-page='josh-allen']")
        page.wait_for_selector(".plr .plr-tonight .profile .prof-acts", timeout=30000)
        page.wait_for_timeout(500)
        out["card"] = page.evaluate("""() => { const t = document.querySelector('.plr-tonight');
            return {head: (t.querySelector('.plr-h') || {}).textContent, doors: t.querySelectorAll('[data-prop]').length,
                    arrows: t.querySelectorAll('.pp-go').length, deep: !!t.querySelector('.profile-deep'),
                    acts: [...t.querySelectorAll('.prof-acts .betit, .prof-acts [data-ask-pick]')].map((e) => e.textContent.trim()),
                    ask: (t.querySelector('[data-ask-pick]') || {dataset: {}}).dataset.askLabel,
                    tiles: [...t.querySelectorAll('.form-tile')].map((e) => [e.scrollWidth <= e.clientWidth + 1,
                                                                           e.querySelector('.v').getClientRects().length]),
                    wide: document.documentElement.scrollWidth}; }""")
        page.click(".plr-tonight .profile-pick")
        page.wait_for_timeout(500)
        out["after_pick"] = page.evaluate("() => [state.view, location.hash]")
        page.click(".plr-tonight .prof-acts [data-ask-pick]")
        page.wait_for_function("() => state.view === 'ask'", timeout=8000)
        out["ask"] = page.evaluate("() => askState().pick")
        page.evaluate("() => openPlayer('Tyreek Hill')")
        page.wait_for_function("() => location.hash === '#player/tyreek-hill'", timeout=8000)
        page.wait_for_selector(".plr .plr-tonight .profile", timeout=30000)
        out["trending"] = page.inner_text(".plr-hero")
        out["asked"] = len(asked)
        out["errors"] = errors
        ctx.close()
        return out
    got = _browser(run)
    if got is None:
        return
    assert got["landing"] == ["Josh Allen", "James Cook", "Tyreek Hill"] and got["landing_cards"] == 0, got
    assert "TONIGHT’S PLAYERS" in got["landing_head"].upper(), got["landing_head"]
    assert got["found"] == ["Jacoby Brissett", "Jacob Rodriguez"], got["found"]
    assert "FOUND IN NFL" in got["found_head"].upper() and "no prop on tonight’s nfl board" in got["found_head"].lower(), got["found_head"]
    pg = got["page"]
    assert pg["hash"] == "#player/jacoby-brissett" and pg["box"] == "Jacoby Brissett", pg
    assert "Jacoby" in pg["hero"] and "Brissett" in pg["hero"] and pg["card"] and pg["rows"] == 0, pg
    assert pg["bar"] == "← Back to the search", pg["bar"]
    assert got["back"] == {"box": "jacoby", "rows": ["Jacoby Brissett", "Jacob Rodriguez"]}, got["back"]
    assert got["priced_list_cards"] == 0, "a priced player is a name in the list too"
    card = got["card"]
    assert card["head"] == "Tonight’s markets" and card["deep"], card
    assert card["doors"] == 0 and card["arrows"] == 0, ("the card opens nothing on the page", card)
    assert card["acts"] == ["Bet it", "Ask"] and card["ask"] == "Josh Allen OVER 245.5 Passing Yards", card
    assert all(fits and lines == 1 for fits, lines in card["tiles"]), ("a form tile broke its number", card["tiles"])
    assert card["wide"] <= 390, card["wide"]
    assert got["after_pick"] == ["players", "#player/josh-allen"], got["after_pick"]
    assert got["ask"] == "Josh Allen|pass_yds|OVER|245.5", ("Ask carries the pick", got["ask"])
    assert "Tyreek" in got["trending"] and "Hill" in got["trending"], got["trending"]
    assert got["asked"] == 1, ("a tapped name needs no second search", got["asked"])
    assert not got["errors"], got["errors"]


if __name__ == "__main__":
    import traceback
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception:
            fails += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
