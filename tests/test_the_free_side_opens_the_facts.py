"""The free side opens the facts around the games: standings, rosters, injury
reports, each game's weather, a team's own page and the playoff races.

Ethan, 2026-11-03, on the 30 October audit's list — "open the free side:
standings, rosters, injuries, weather and the races for free accounts (the
picks and prices stay paid); update the Terms' free features list" — "do
all of them". What these hold:

  * the six open for an account without a plan, and no page whose content
    is the model's output opens with them;
  * every file they read is free on disk: the standings, rosters and
    injuries are FREE_FILES, the weather rides each game on the board (the
    gate never strips `games`), a team's page is finished scorelines
    (server._team, never gated), and the races are mixed — the seeds, the
    field and the standings free, our chances, the games left and the swing
    games stripped (PAID_KEYS_BY_FILE), with the page's own lock in their
    place;
  * the plans and the sign-up say so (FL_ROWS, FREE_VS_PLAN), the plans no
    longer list the race page as a member's, and the Terms' §2 list of free
    features names them, dated, with a note that the change only adds;
  * in a browser, a free account lands on each of them — the tab bar there,
    not a wall screen — and the NFL race shows its seeds with the lock on
    our chances.

Run directly: `python3 tests/test_the_free_side_opens_the_facts.py`
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import gate                                          # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
ACCOUNT = (ROOT / "web" / "js" / "account.js").read_text(encoding="utf-8")
MORE = (ROOT / "web" / "js" / "more.js").read_text(encoding="utf-8")
RACE = (ROOT / "web" / "js" / "race.js").read_text(encoding="utf-8")
SERVER = (ROOT / "server.py").read_text(encoding="utf-8")
OPENED = ("standings", "rosters", "injuries", "weather", "team", "race")
FLAT = lambda s: re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s))  # noqa: E731


def _list(name: str) -> set:
    i = APP.index(f"const {name} = ")
    block = re.sub(r"//[^\n]*", "", APP[i:i + 9000])
    return set(re.findall(r'"([a-z]+)"', block[:block.index("]")]))


def _fn(src: str, name: str) -> str:
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i)]


def test_the_six_open_and_no_pick_page_does():
    open_ = _list("WALL_OPEN")
    assert set(OPENED) <= open_, set(OPENED) - open_
    for page in ("recommended", "props", "edge", "likely", "longshots", "futures", "ask", "scanner", "lab", "parlays"):
        assert page not in open_, page


def test_every_file_they_read_is_free_on_disk():
    for sport in ("nfl", "cfb", "nba", "mlb", "wnba", "nhl"):
        assert gate.is_free(f"standings_{sport}.json") and gate.is_free(f"rosters_{sport}.json"), sport
    assert gate.is_free("injuries.json") and gate.is_free("news.json")
    assert "games" not in gate.PAID_KEYS, "each game's weather rides the board's games, left whole"
    assert "((state.data || {}).games || []).filter((g) => g.weather)" in _fn(APP, "renderWeather")
    team = SERVER[SERVER.index("    def _team(self"):]
    team = team[:team.index("\n    def ", 10)]
    assert "NOT GATED" in team and "_entitled" not in team, "a team's page is finished scorelines"
    for f in ("nfl_race.json", "cfp_race.json", "nba_cup.json"):
        # The brackets add our line on each knockout game (2026-11-03).
        assert f in gate.MIXED_FILES and {"chances", "remaining", "swing"} <= set(gate.PAID_KEYS_BY_FILE[f]), f
    assert "const res = await paidFetch(name);" in RACE, "the entitled route, the public copy for a free reader"
    # Each race view locks our chances in place; the college race has two views,
    # the race before selection day and the playoff bracket after it.
    for view in ("nflHTML", "cfpHTML", "cfpPlayoffHTML", "cupHTML"):
        assert 'memberLockHTML("Our chances are for members"' in _fn(RACE, view), view


def test_the_plans_and_the_signup_say_so():
    rows = ACCOUNT[ACCOUNT.index("const FL_ROWS = ["):ACCOUNT.index("];", ACCOUNT.index("const FL_ROWS = ["))]
    assert '["Standings, rosters, injuries, weather and the playoff races", 1],' in rows
    why = ACCOUNT[ACCOUNT.index("const PW_WHY = {"):ACCOUNT.index("};", ACCOUNT.index("const PW_WHY = {"))]
    assert "race:" not in why, "the race page is no longer a reason the plans opened"
    line = APP[APP.index("const FREE_VS_PLAN = "):APP.index("function freeVsPlanHTML(")]
    assert "standings, rosters, injuries, weather and playoff races" in line and "our chances in the races" in line


def test_the_terms_list_them_dated_and_only_adding():
    terms = (ROOT / "web" / "terms.html").read_text(encoding="utf-8")
    flat = FLAT(terms)
    assert "Last updated 3 November 2026" in terms
    note = flat[flat.index("When this version applies."):flat.index("1. Who we are")]
    assert "The change of 3 November 2026 adds to §2’s list of what an account gets free" in note
    assert "it takes nothing away and applies to every account from that day" in note
    sec = flat[flat.index("2. What the Service is"):flat.index("3. No advice")]
    for want in ("the Pick of the Day in every league", "every game live",
                 "standings, rosters, injury reports and game-day weather",
                 "the playoff races, as they stand (our chances in them are part of the paid analysis)"):
        assert want in sec, want


# --- in a browser ------------------------------------------------------------------
def _race():
    sys.path.insert(0, str(ROOT / "tests"))
    import test_the_nfl_playoff_race as N
    from engine import nflrace
    out = nflrace.build(N._season(), {t: (i % 9) - 4.0 for i, t in enumerate(N.TEAMS)}, "2026-10-15",
                        season=2026, sims=400, seed_=2)
    out["generated_at"] = "2026-11-03T18:00:00"
    return out


def _visit(views) -> dict:
    from playwright.sync_api import sync_playwright
    sys.path.insert(0, str(ROOT / "tests"))
    import rendercheck
    who = {"signed_in": True, "email": "you@example.com", "profile": {"handle": "reader", "color": 1}}
    bill = {"signed_in": True, "email": "you@example.com", "paywall": True, "entitled": False, "plans": []}
    public = json.dumps(gate.redact(_race(), "nfl_race.json"))
    ful = lambda b, s=200: (lambda r: r.fulfill(status=s, content_type="application/json", body=b))  # noqa: E731
    srv, port = rendercheck._serve()
    got, errs = {}, []
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                for view in views:
                    ctx = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block",
                                              is_mobile=True, has_touch=True)
                    page = ctx.new_page()
                    page.on("pageerror", lambda e: errs.append(str(e)))
                    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    page.route("**/api/**", ful("{}"))
                    page.route("**/api/account/me*", ful(json.dumps(who)))
                    page.route("**/api/billing/status*", ful(json.dumps(bill)))
                    page.route("**/api/board/**", ful('{"error":"subscription required"}', 402))
                    page.route("**/data/nfl_race.json*", ful(public))
                    page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb.tour','done');}catch(e){}")
                    page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#{view}", wait_until="load")
                    page.wait_for_timeout(3000)
                    got[view] = page.evaluate("""(v) => ({ hash: location.hash, view: state.view,
                      walled: document.body.classList.contains('walled'),
                      wall: document.body.classList.contains('on-wall'),
                      tabbar: !!document.querySelector('.tabbar') && getComputedStyle(document.querySelector('.tabbar')).display !== 'none',
                      navLocked: [...document.querySelectorAll('.nav-btn[data-view="' + v + '"].nav-locked')].length,
                      lock: !!document.querySelector('#race-body .member-lock'),
                      seeds: (document.getElementById('race-body') || {}).innerText || '' })""", view)
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    return {"views": got, "errs": errs}


def test_in_a_browser_a_free_account_lands_on_each_and_the_race_locks_our_chances():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    got = _visit(OPENED)
    assert not got["errs"], got["errs"]
    for view, v in got["views"].items():
        assert v["walled"], (view, "a free account", v)
        assert v["view"] == view and v["hash"].startswith(f"#{view}"), (view, "it opened, not the plans", v)
        assert not v["wall"] and v["tabbar"], (view, "the app's own chrome, not a wall screen", v)
        assert not v["navLocked"], (view, "no lock on its menu entry", v)
    race = got["views"]["race"]
    assert race["lock"] and "IF THE SEASON ENDED TODAY" in race["seeds"].upper(), race


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}")
    print(f"\n{sum(1 for n in globals() if n.startswith('test_'))} tests passed.")
