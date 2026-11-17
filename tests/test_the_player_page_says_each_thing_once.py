"""The player page says each thing once (PLRDUP1, 2026-11-17).

Ethan: "All this little stuff I'm finding with like repeating information and
all just this weird looking stuff. This is stuff you need to be finding. You
need to think like a user and wonder why all this information is here. Why is
all this repeated stuff here?"

Josh Allen's page was read top to bottom on the live site's own data that day.
The Overview said who the player is three times (the page's header, a card of
the chart's with the name, club and number, and a second name card over the
markets, with Copy link in the middle of the page), the season's totals twice,
the last game's score twice, and that game's line seven times: twice in one
table, under "This game" and again under "vs NYJ", the season's only game
against the Jets. The markets card had its own doors to the charts and the
game log, both already on the page. What these hold:

  * the page's header carries the club's door and the page's link, so the
    card that had them is not needed for either;
  * the splits under the last game name it "Previous game", the card's own
    words, and a season's one game against that club is not listed again as
    the club's row; a second meeting is, and so is the club's row when the
    player sat the last game out;
  * the markets card keeps of its old header the grade alone, its title names
    tonight's opponent, and its doors to the charts and the game log, and
    the chart its depth would draw a second time, are not shown;
  * the chart on the page draws no player card of its own (football's, every
    league's default, and baseball's, which keeps its season switch) and not
    the score of the game in the Previous game card; another game picked
    gets its card.

    python3 tests/test_the_player_page_says_each_thing_once.py
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
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

PAGE = (ROOT / "web" / "js" / "playerpage.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "playerpage.css").read_text(encoding="utf-8")
CHART = (ROOT / "web" / "js" / "carrychart.js").read_text(encoding="utf-8")
MLB = (ROOT / "web" / "js" / "chart-mlb.js").read_text(encoding="utf-8")

STUBS = r"""
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => '&#' + c.charCodeAt(0) + ';');
const escapeHtml = esc, escapeAttr = esc;
const plural = (n, one) => `${n} ${n === 1 ? one : one + 's'}`;
const trueMinus = (x) => String(x);
const TEAMS = { BUF: { name: 'Buffalo Bills', nick: 'Bills', primary: '#00338d' }, DEN: { name: 'Denver Broncos', nick: 'Broncos' } };
const teamsIn = () => TEAMS; const teamNameIn = (s, a) => (TEAMS[a] || {}).nick || a;
const teamMarkIn = (s, a) => `<i data-mark="${a}"></i>`; const lgCode = (s) => s.toUpperCase();
const playerAvatar = (n) => `<i data-face="${n}"></i>`; const injTag = () => '';
const surname = (n) => n.split(' ').pop();
const safeHref = (u) => esc(u);
const document = { addEventListener() {} };
"""


def _node(body: str, extra: str = ""):
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        return None
    js = STUBS + extra + PAGE + f"\nprocess.stdout.write(JSON.stringify((() => {{ {body} }})()));"
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout)


def test_the_header_holds_the_clubs_door_and_the_pages_link():
    doors = ("const teamLinkHTML = (s, a, label) => `<button class=\"team-link\" data-team-open=\"${a}\">${esc(label)}</button>`;"
             "const slugify = (n) => String(n).toLowerCase().replace(/[^a-z0-9]+/g, '-');"
             "const shareBtn = (kind, slug) => `<button class=\"qb-share\" data-share-kind=\"${kind}\" data-share-slug=\"${slug}\">Copy link</button>`;")
    call = "return plrHeroHTML('Josh Allen', 'nfl', 'BUF', 'QB', '', { number: 17, position: 'QB', height: '6-5', weight: '237 lb' });"
    got = _node(call, doors)
    if got is None:
        return
    assert '<button class="team-link" data-team-open="BUF">Buffalo Bills</button> · #17 · QB' in got, got
    assert got.count("Buffalo Bills") == 1, "the club's name once, as its door"
    assert '<div class="plr-share"><button class="qb-share" data-share-kind="player" data-share-slug="josh-allen">' in got
    # Where the page's helpers are not loaded (a harness), the plain name, as before.
    plain = _node(call)
    assert "Buffalo Bills · #17 · QB" in plain and "plr-share" not in plain and "team-link" not in plain
    # A fighter has no club: the division and the record, and still the page's link.
    ufc = _node("return plrHeroHTML('Islam Makhachev', 'ufc', '', 'Lightweight', '', { division: 'Lightweight', record: '27-1-0' });",
                doors)
    assert "Lightweight · 27-1-0" in ufc and "team-link" not in ufc and "qb-share" in ufc


def _splits(vs_gp: int, **last):
    cols = [{"key": "yds", "label": "YDS", "title": "Passing yards"}]
    rows = [{"key": "season", "label": "Season", "gp": 9, "values": {"passing.yds": 247.0}},
            {"key": "m:2026-11", "label": "November", "gp": 3, "values": {"passing.yds": 239.7}},
            {"key": "vs:NYJ", "label": "vs NYJ", "gp": vs_gp, "values": {"passing.yds": 196.0}},
            {"key": "away", "label": "Away", "gp": 5, "values": {"passing.yds": 245.8}}]
    return {"role": "passing", "splits": {"rows": rows, "groups": [{"key": "passing", "title": "Passing", "cols": cols}]},
            "last": {"date": "2026-11-15", "opponent": "NYJ", "home": False, "values": {"passing.yds": 196}, **last}}


def test_the_split_rows_name_the_previous_game_and_never_say_it_twice():
    labels = ("const labels = (d) => (plrSplitletHTML(d).match(/<td class=\"gl-fix\">[^<]*/g) || [])"
              ".map((x) => x.replace('<td class=\"gl-fix\">', ''));")
    got = _node(f"""{labels}
      return {{ once: labels({json.dumps(_splits(1))}), twice: labels({json.dumps(_splits(2))}),
               sat: labels({json.dumps(_splits(1, dnp=True))}), wait: labels({json.dumps(_splits(1, pending=True))}) }};""")
    if got is None:
        return
    assert got["once"] == ["Previous game", "November", "Away", "Season"], got["once"]
    assert got["twice"] == ["Previous game", "November", "vs NYJ", "Away", "Season"], "a second meeting is a split"
    assert got["sat"] == ["November", "vs NYJ", "Away", "Season"], "no row of the player's for a game sat out"
    assert got["wait"] == ["November", "vs NYJ", "Away", "Season"]
    assert "This game" not in PAGE.replace("This game’s", ""), "the card above calls it the previous game"


def test_the_market_card_keeps_only_its_grade_and_the_title_names_tonights_opponent():
    page = ("const page = (graded) => ({ _plr: { player: 'Josh Allen', sport: 'nfl' },"
            " querySelector: (s) => (graded && s === '.plr-tonight .grade' ? {} : null) });")
    got = _node(f"""{page}
      const rows = new Map([['Josh Allen', [{{ player: 'Josh Allen', opponent: 'DEN' }}]]]);
      globalThis._profRows = rows;
      const out = {{ priced: plrTonightTitle(page(true)), history: plrTonightTitle(page(false)) }};
      rows.set('Josh Allen', [{{ player: 'Josh Allen' }}]);
      out.noOpp = plrTonightTitle(page(true));
      return out;""", "var _profRows;")
    if got is None:
        return
    assert got == {"priced": "Tonight’s markets <span>vs Broncos</span>", "history": "By market",
                   "noOpp": "Tonight’s markets"}, got
    for rule in (".plr-tonight .profile-head > :not(.grade) { display: none; }",
                 ".plr-tonight .profile-head:has(.grade) { padding: 10px 14px 0; }",
                 ".plr-tonight .prof-charts, .plr-tonight .prof-depth .cc-slot { display: none; }"):
        assert rule in CSS, rule


def test_the_chart_on_the_page_draws_no_card_of_its_own():
    assert ('    el.dataset.own = "1";\n    el.dataset.last = g && !g.dnp && !g.pending ? g.date || "" : "";' in PAGE), \
        "the page marks its own slot, with the day of the game in its Previous game card"
    assert 'own: d.own === "1", last: d.last || "",' in CHART
    assert 'const card = C.own ? "" : playerHero(d, sport, S.kind);' in CHART, "no second name card"
    assert "const same = !!(C.own && g && C.last && g.date === C.last);" in CHART
    assert 'const hero = same ? "" : P && P.hero ? P.hero(g, d, [count[1], count[2]])' in CHART, "nor that game's score again"
    assert '(hero || same ? "" : title)' in CHART, "nor a title line in the card's place"
    assert "own: !!C.own,\n                   same: !!(C.own && g && C.last && g.date === C.last)," in CHART, "a league's own page is told"
    # Baseball lays its own page out: no card, the season switch and the note kept.
    assert "function hero(d, sport, own) {" in MLB and "const top = hero(d, sport, c.own) + tabs;" in MLB
    assert 'if (own) return (d.seasons.length > 1 ? `<div class="cc-bar">${pick}</div>` : "") + cover;' in MLB
    assert '(c.same ? "" : gameCard(d, g, sport))' in MLB
    # Everywhere else (a pick's page, the chart sheet) the card is drawn as it was.
    assert CHART.count("playerHero(d, sport, S.kind)") == 1 and "inline: false" in CHART


def test_in_a_browser_the_page_has_one_header_one_chart_and_no_second_score():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    from engine import db as D
    import rendercheck
    T = __import__("test_the_player_page_draws_the_charts")     # Sam LaPorta's season and targets (a sibling test)
    keep = (D.DEFAULT_DB, D.connect.__defaults__)
    path = T._history()
    D.DEFAULT_DB, D.connect.__defaults__ = path, (path,)
    srv, port = rendercheck._serve()
    got, days = {}, []
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block",
                                          color_scheme="dark")
                page = ctx.new_page()
                errs = []
                page.on("pageerror", lambda e: errs.append(str(e)))

                def routes(resp):
                    if "/api/players/routes" in resp.url and resp.ok:
                        try:
                            days.extend(g.get("date") for g in (resp.json().get("games") or []))
                        except Exception:                        # noqa: BLE001
                            pass
                page.on("response", routes)
                page.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb_intro_v1', '1');"
                                     " localStorage.setItem('qb.tour', 'done'); } catch (e) {}")
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#player/sam-laporta", wait_until="load")
                drawn = ".plr-charts .cc-inline .cc-body svg, .plr-charts .cc-inline .cc-body canvas"
                page.wait_for_selector(drawn, timeout=30000)
                page.wait_for_selector(".plr-splitlet td.gl-fix", timeout=30000)
                look = """(() => ({
                  names: document.querySelectorAll('.plr .plr-name').length,
                  door: (document.querySelector('.plr-hero .team-link') || {}).textContent || '',
                  share: !!document.querySelector('.plr-hero .qb-share'),
                  head: [...document.querySelectorAll('.plr-tonight .profile-head > *')].filter((e) => getComputedStyle(e).display !== 'none').length,
                  doors: [...document.querySelectorAll('.plr-tonight .prof-charts')].filter((e) => getComputedStyle(e).display !== 'none').length,
                  slot: Object.assign({}, document.querySelector('.plr-charts > *').dataset),
                  cards: [...document.querySelectorAll('.plr-charts .cc-hero')].map((e) => e.className),
                  splitlet: [...document.querySelectorAll('.plr-splitlet td.gl-fix')].map((e) => e.textContent),
                  title: (document.querySelector('.plr-tonight .plr-h') || {}).textContent || '',
                }))()"""
                got["first"] = page.evaluate(look)
                # The page's last game made the newest game on the chart: its score is not carded again.
                got["day"] = days[0] if days else ""
                page.evaluate("""async (day) => {
                  const el = document.querySelector('.plr-charts > *');
                  delete el.dataset.on; el.dataset.last = day; el.innerHTML = '';
                  (await ccLoad()).mount(el);
                }""", got["day"])
                page.wait_for_selector(drawn, timeout=30000)
                page.wait_for_timeout(400)
                got["same"] = page.evaluate(look)["cards"]
                chips = page.locator(".plr-charts [data-gi]")
                got["chips"] = chips.count()
                if got["chips"] > 1:
                    chips.nth(1).click()
                    page.wait_for_timeout(600)
                    got["other"] = page.evaluate(look)["cards"]
                got["errs"] = list(errs)
            finally:
                browser.close()
    finally:
        srv.shutdown()
        D.DEFAULT_DB, D.connect.__defaults__ = keep
    f = got["first"]
    assert f["names"] == 1 and f["door"] == "Detroit Lions" and f["share"], f
    assert f["head"] == 0 and f["doors"] == 0, "nothing of the second header, nor its doors"
    assert f["slot"]["own"] == "1" and f["slot"]["last"] == "2026-10-09", f["slot"]
    assert not [c for c in f["cards"] if "ph-hero" in c or "mb-hero" in c], f["cards"]
    assert len(f["cards"]) == 1, ("the chart's newest game is not the page's last: it has its card", f["cards"])
    assert f["splitlet"] == ["Previous game", "October", "Away", "Season"], f["splitlet"]
    assert f["title"] == "By market", f["title"]
    assert got["day"], "the route chart's games"
    assert got["same"] == [], ("the Previous game card's game: no second score", got["same"])
    assert got["chips"] > 1 and len(got["other"]) == 1, ("another game picked has its card", got.get("other"))
    assert not got["errs"], got["errs"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
