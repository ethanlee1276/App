"""The race pages: the NFL's and college football's playoff races and the NBA Cup.

Ethan, 2026-10-29: "do all 3" — the second and third of which were the
playoff race and the Cup tracker; and 2026-11-03, the NFL's: "do all of
them". One page a league (js/race.js, loaded the
first time it opens), named for its league in the menu, and quiet for every
league that has no race.

Guarded here: the wiring a page needs (its row, its section, its route, its
stub, the offline copy), what a member and a reader without a plan each
see — the facts for both, the model's numbers for the member only, and the
lock card in their place — and, in a browser, both pages drawn at a phone's
width without an error or a sideways scroll.

    python3 tests/test_the_race_pages.py
    QB_BROWSER_TESTS=1 python3 tests/test_the_race_pages.py
"""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import gate                                       # noqa: E402

WEB = ROOT / "web"
APP = (WEB / "js" / "app.js").read_text()
RACE = (WEB / "js" / "race.js").read_text()
HTML = (WEB / "index.html").read_text()


def _fixtures():
    import test_the_nba_cup as C
    import test_the_playoff_race as P
    from engine import nbacup
    cfp = P._race(sims=800)
    cfp["generated_at"] = "2026-10-29T18:00:00"
    cup = nbacup.build(C._schedule(), C._ratings(), "2026-11-08", 2.4, 8.5, sims=800, seed=1)
    return cfp, cup


def _nfl():
    import test_the_nfl_playoff_race as N
    from engine import nflrace
    out = nflrace.build(N._season(), {t: (i % 9) - 4.0 for i, t in enumerate(N.TEAMS)}, "2026-10-15",
                        season=2026, sims=800, seed_=2)
    out["generated_at"] = "2026-11-03T18:00:00"
    return out


# --- the wiring --------------------------------------------------------------------
def test_the_page_is_wired_where_every_page_is():
    assert 'data-view="race"' in HTML and '<span class="sb-race">Playoff race</span>' in HTML
    assert 'id="view-race"' in HTML and 'id="race-body"' in HTML and 'id="race-sub"' in HTML
    order = APP[APP.index("const VIEW_ORDER = ["):APP.index("];", APP.index("const VIEW_ORDER = ["))]
    assert '"race"' in order
    assert 'if (name === "race") renderRace();' in APP
    assert 'function renderRace(...a) { return roomCall(renderRace, "renderRace", "js/race.js", "css/race.css", a); }' in APP
    assert "async function renderRace()" in RACE
    sw = (WEB / "sw.js").read_text()
    assert '"/js/race.js", "/css/race.css"' in sw
    acct = (WEB / "js" / "account.js").read_text()
    why = acct[acct.index("const PW_WHY = {"):acct.index("};", acct.index("const PW_WHY = {"))]
    assert "race:" not in why, "open to a reader without a plan since 2026-11-03: the page's own lock says what is a member's"
    wall = APP[APP.index("const WALL_OPEN = ["):APP.index("];", APP.index("const WALL_OPEN = ["))]
    assert '"race"' in wall


def test_the_row_is_named_for_its_league_and_quiet_elsewhere():
    assert '.sb-race").forEach((el) => { el.textContent = state.sport === "nba" ? "NBA Cup" : "Playoff race"; });' in APP
    hidden = APP[APP.index("const HIDDEN_VIEWS = {"):APP.index("\n};", APP.index("const HIDDEN_VIEWS = {"))]
    for sport in ("mlb", "wnba", "nhl", "ufc", "polymarket", "fantasy"):
        line = next(ln for ln in hidden.splitlines() if ln.strip().startswith(f"{sport}:")
                    or f" {sport}: [" in ln)
        assert '"race"' in line, sport
    for sport in ("nba", "cfb"):
        line = next(ln for ln in hidden.splitlines() if ln.strip().startswith(f"{sport}:"))
        assert '"race"' not in line, sport
    assert "  nfl: [], mlb: [\"race\"]," in hidden, "the NFL's race is open (2026-11-03)"


def test_it_reads_through_the_entitled_route():
    assert 'const RACE_FILES = { nfl: "nfl_race.json", cfb: "cfp_race.json", nba: "nba_cup.json" };' in RACE
    assert "const res = await paidFetch(name);" in RACE
    assert "data/cfp_race" not in RACE and "data/nba_cup" not in RACE and "data/nfl_race" not in RACE


# --- what each reader sees ----------------------------------------------------------
def _render(fn, payload):
    js = f"""
    const state = {{ sport: "cfb", view: "race" }};
    const escapeHtml = (s) => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
    const teamMarkIn = (sp, t) => `<i data-mark="${{t}}"></i>`;
    const teamNameIn = (sp, t) => t;
    const plural = (n, w) => `${{n}} ${{w}}${{n === 1 ? "" : "s"}}`;
    const formatGameDate = (s) => s;
    const memberLockHTML = (t, b) => `<div class="card member-lock"><b>${{t}}</b><p>${{b}}</p></div>`;
    {RACE}
    console.log(JSON.stringify({fn}({json.dumps(payload)})));
    """
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_a_member_sees_the_race_and_its_numbers():
    cfp, cup = _fixtures()
    html = _render("cfpHTML", cfp)
    assert "If it started today" in html and "The contenders" in html
    assert "member-lock" not in html
    top = cfp["teams"][0]
    assert f"{round(cfp['chances'][top['team']]['playoff'] * 100)}%" in html or ">99%" in html
    if cfp["swing"]:
        assert "The games that swing it" in html
    html = _render("cupHTML", cup)
    assert "The groups" in html and "To win the Cup" in html and "How a tie is broken" in html
    assert "point differential (overtime counts zero)" in html
    assert "member-lock" not in html


def test_a_reader_without_a_plan_sees_the_facts_and_the_lock():
    cfp, cup = _fixtures()
    pub = gate.redact(cfp, "cfp_race.json")
    html = _render("cfpHTML", pub)
    assert "If it started today" in html and "The conferences" in html
    assert "member-lock" in html and "Our chances are for members" in html
    assert "The contenders" not in html and "The games that swing it" not in html
    pub = gate.redact(cup, "nba_cup.json")
    html = _render("cupHTML", pub)
    assert "The groups" in html and "member-lock" in html
    assert "To win the Cup" not in html and "<span>Adv</span>" not in html
    assert "Group games left, at our price" not in html


def test_the_nfl_race_for_a_member_and_for_a_reader_without_a_plan():
    d = _nfl()
    html = _render("nflHTML", d)
    assert "If the season ended today" in html and "The race" in html and "The divisions" in html
    assert "member-lock" not in html and "In the hunt:" in html
    top = d["teams"][0]["team"]
    c = d["chances"][top]["playoffs"]
    assert (f"{round(c * 100)}%" if 0.005 <= c <= 0.995 else ">99%") in html
    if d["swing"]:
        assert "The games that swing it" in html
    pub = gate.redact(d, "nfl_race.json")
    html = _render("nflHTML", pub)
    assert "If the season ended today" in html and "The divisions" in html
    assert "member-lock" in html and "Our chances are for members" in html
    assert "The games that swing it" not in html and "<span>No. 1</span>" not in html


def test_before_group_play_no_one_leads_the_cup():
    """At 0-0 the order is our rating's; the night before group play the
    page tagged a leader in every group and a wild-card holder anyway."""
    _, cup = _fixtures()
    for rows in cup["groups"].values():
        for r in rows:
            r.update(w=0, l=0, pd=0, pf=0)
    cup["played"] = 0
    html = _render("cupHTML", cup)
    assert "Group play has not started" in html
    assert "leads the group" not in html and "holds the wild card" not in html and "holds it today" not in html
    _, cup = _fixtures()
    assert "leads the group" in _render("cupHTML", cup), "once played, the leader is tagged"


# --- in a browser --------------------------------------------------------------------
def _browser():
    from playwright.sync_api import sync_playwright
    import rendercheck
    cfp, cup = _fixtures()
    nfl = _nfl()
    srv, port = rendercheck._serve()
    got, errs = {}, []
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                for sport, name, payload in (("cfb", "cfp_race.json", cfp), ("nba", "nba_cup.json", cup),
                                             ("nfl", "nfl_race.json", nfl)):
                    for who in ("member", "free"):
                        ctx = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block",
                                                  is_mobile=True, has_touch=True)
                        page = ctx.new_page()
                        page.on("pageerror", lambda e: errs.append(str(e)))
                        page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                        page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
                        body = json.dumps(payload if who == "member" else gate.redact(payload, name))

                        def ok(text, status=200):
                            return lambda r, *_: r.fulfill(status=status, content_type="application/json", body=text)
                        page.route(f"**/api/board/{name}", ok(body) if who == "member" else ok("{}", 402))
                        page.route(f"**/data/{name}", ok(body))
                        page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb.tour','done');}catch(e){}")
                        page.goto(f"http://127.0.0.1:{port}/index.html?sport={sport}#race", wait_until="load")
                        page.wait_for_timeout(2500)
                        got[(sport, who)] = page.evaluate("""() => ({
                            view: state.view, label: document.querySelector('.sb-race').textContent,
                            text: document.getElementById('race-body').innerText,
                            lock: !!document.querySelector('#race-body .member-lock'),
                            wide: document.documentElement.scrollWidth > window.innerWidth + 1})""")
                        ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    return got, errs


def nfl_swing():
    return bool(_nfl()["swing"])


def test_in_a_browser_both_pages_draw_at_a_phones_width():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("skip: set QB_BROWSER_TESTS=1")
        return
    got, errs = _browser()
    assert not errs, errs
    for (sport, who), g in got.items():
        assert g["view"] == "race", (sport, who, g)
        assert g["label"] == ("NBA Cup" if sport == "nba" else "Playoff race")
        assert not g["wide"], f"{sport} {who}: the page scrolls sideways at 390px"
        assert g["lock"] == (who == "free"), (sport, who)
    assert "IF IT STARTED TODAY" in got[("cfb", "member")]["text"].upper()
    assert "THE GROUPS" in got[("nba", "free")]["text"].upper()
    assert "IF THE SEASON ENDED TODAY" in got[("nfl", "free")]["text"].upper()
    assert "THE GAMES THAT SWING IT" in got[("nfl", "member")]["text"].upper() or not nfl_swing()


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
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
