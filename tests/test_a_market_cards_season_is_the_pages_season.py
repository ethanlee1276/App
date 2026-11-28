"""A market card's Season tile is the season the page shows (step AGY, 25 November 2026).

Ethan, 24 November: "We want every single sports player pages to match each other". A market with no line tonight is
drawn from the player's last ten games (engine/statlogs.N_GAMES; app.js historyProfileHTML), and its Season tile reads
this season's games among those ten only where they reach the season's start (step AFD): ten games are not a season.
So once a season passed ten games the tile said "—", in every league: Jalen Brunson's points card and Connor
McDavid's shots card on the live site, beside a priced card's number.

The player page's own answer now carries each market's average over the season's games played that carry it
(engine/playerpage `markets`: the games its game log shows, each once, a basketball game of no minutes out, last
season's out), and the page fills a history card's empty Season tile from it (js/playerpage.js plrSeasonTiles) when its
numbers land, when the cards are handed to it, and when a market chip draws a card again. A season before the
league's (a player who has not played this one) fills nothing: the tile is this season's.

The browser half runs with QB_BROWSER_TESTS=1 and /usr/bin/python3.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

PAGE_JS = (ROOT / "web" / "js" / "playerpage.js").read_text(encoding="utf-8")


def _history(rows):
    from engine import db as D
    path = os.path.join(tempfile.mkdtemp(), "history.db")
    conn = D.connect(path)
    conn.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, position, "
                     "home, market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    return path


def _game(day, gid, mins, pts, reb=None, season=2026):
    out = [("nba", season, day, gid, "Jalen Brunson", "NYK", "IND", "G", 1, "min", mins),
           ("nba", season, day, gid, "Jalen Brunson", "NYK", "IND", "G", 1, "pts", pts)]
    if reb is not None:
        out.append(("nba", season, day, gid, "Jalen Brunson", "NYK", "IND", "G", 1, "reb", reb))
    return out


def test_the_page_says_each_markets_season_over_the_games_played():
    from engine import playerpage as P
    rows = (_game("2026-11-10", "g1", 34, 22, 3) + _game("2026-11-12", "g2", 36, 30, 4)
            + _game("2026-11-14", "g3", 0, 0, 0)                      # a game of no minutes: not played
            + _game("2026-11-16", "g4", 33, 26)                       # a box without rebounds
            + _game("2026-04-10", "g0", 38, 40, 9, season=2025))      # last season
    d = P.page("nba", "Jalen Brunson", "NYK", db_path=_history(rows), data_dir=tempfile.mkdtemp(), wait_ranks=False)
    assert d["season"] == 2026
    assert d["markets"] == {"Points": 26.0, "Rebounds": 3.5}, d["markets"]
    assert "Assists" not in d["markets"], "a market with no games says nothing"


def test_the_page_fills_an_empty_season_tile_and_watches_its_cards():
    i = PAGE_JS.index("function plrSeasonTiles(page)")
    fill = PAGE_JS[i:PAGE_JS.index("\n}\n", i)]
    assert '.plr-tonight .profile-spark[data-history]' in fill, "history cards only: a priced card has its season"
    assert 'tile.textContent === "—"' in fill, "a tile with a season of its own keeps it"
    assert "tileNum(v)" in fill, "said as every tile is (step AFA)"
    j = PAGE_JS.index("function plrFill(page, d) {")
    assert "page._plr.markets = d && d.markets && !plrPast(d) ? d.markets : null;\n  plrSeasonTiles(page);" in \
        PAGE_JS[j:j + 400], "a season before the league's fills nothing"
    k = PAGE_JS.index("function plrMarkets(page, kept) {")
    markets = PAGE_JS[k:PAGE_JS.index("\n}\n", k)]
    assert "plrSeasonTiles(page);" in markets and "new MutationObserver(() => plrSeasonTiles(page))" in markets
    assert "observe(tonight, { childList: true, subtree: true })" in markets, "a chip's card drawn again is filled"


def _answering(body):
    """A route handler of one argument: Playwright hands a handler that takes two the request as its second, so a
    default argument (``past=past``) is overwritten by it."""
    return lambda route: route.fulfill(status=200, content_type="application/json", body=body)


def test_in_a_browser_a_history_cards_season_is_the_pages():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    ML = __import__("test_a_market_line_can_be_moved")
    body = json.dumps(ML._board())
    srv, port = rendercheck._serve()
    got = {}

    def page_answer(past):
        return json.dumps({"sport": "nfl", "player": "Chuba Hubbard", "team": "CAR", "position": "RB",
                           "season": 2025 if past else 2026, "league_season": 2026, "seasons": [2026, 2025],
                           "markets": {"Carries": 11.44, "Receptions": 9.9}})
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                for past in (False, True):
                    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                              service_workers="block")
                    page = ctx.new_page()
                    errs = []
                    page.on("pageerror", lambda e: errs.append(str(e)))
                    page.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem("
                                         "'qb_intro_v1', '1'); localStorage.setItem('qb.tour', 'done'); } catch (e) {}")
                    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
                    page.route("**/api/players/page*", _answering(page_answer(past)))
                    for pat in ("**/api/recommendations*", "**/data/recommendations*.json*"):
                        page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=body))
                    page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl", wait_until="load")
                    page.wait_for_function("() => typeof openPlayerRoute === 'function' && state.data", timeout=20000)
                    page.evaluate("openPlayerRoute('chuba-hubbard', 'Chuba Hubbard')")
                    page.wait_for_selector(".plr .profile .form-tiles", timeout=20000)
                    # The page's own numbers in (plrFill has read its markets, or found none to read).
                    page.wait_for_function("() => { const p = document.querySelector('.plr');"
                                           " return p && p._plr && p._plr.markets !== undefined; }", timeout=20000)
                    season = ("() => [...document.querySelectorAll('.plr .plr-tonight .profile .form-tiles "
                              ".form-tile')].pop().textContent")
                    settle = ("(want) => { const t = [...document.querySelectorAll('.plr .plr-tonight .profile "
                              ".form-tiles .form-tile')].pop(); return t && t.textContent === want; }")

                    def tap(mkt, want):
                        page.locator(f".plr .prof-tab[data-mkt='{mkt}']").click()
                        try:
                            page.wait_for_function(settle, arg=want, timeout=5000)
                        except Exception:                       # noqa: BLE001 — read as it is; the assert says
                            pass
                        return page.evaluate(season)
                    priced = page.evaluate(season)
                    carries = tap("Carries", "Season—" if past else "Season11.4")
                    # Back to the priced card and to Carries again: a card drawn again is filled again.
                    back = tap("Receptions", "Season2")
                    again = tap("Carries", "Season—" if past else "Season11.4")
                    got["past" if past else "now"] = {"priced": priced, "carries": carries, "back": back,
                                                       "again": again, "errs": list(errs)}
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    now, past = got["now"], got["past"]
    assert now["priced"] == "Season2", now          # the priced card's own season (the board's), as it was
    assert now["carries"] == "Season11.4", now      # the page's season, where ten games could not say it
    assert now["back"] == "Season2" and now["again"] == "Season11.4", now  # drawn again by a chip, filled again
    assert past["carries"] == "Season—", past       # a page on last season fills nothing
    assert not now["errs"] and not past["errs"], got


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
