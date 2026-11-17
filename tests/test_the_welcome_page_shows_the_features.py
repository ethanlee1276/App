"""The welcome page shows what the site does, the game report first (WELCOME1).

Ethan, 2026-11-17: "for the welcome page, we need to show more features, like
we need to show the game report feature on the welcome page and all that
shit". What these hold:

  * the first-look feed (engine/firstlook.reports) carries the game reports'
    own public record: the report picks graded (the `report` book of
    record_head.json, the Record page's own), and over every league's fact
    checks the games checked, the winners called, the injury listings that
    held, and the newest fact-checked game as the sample, whatever it did; a
    figure with nothing graded is left out, and None with nothing at all;
  * the sign-up screen draws the report card — what a report holds, its
    record, the sample — and a tile for every other feature, each saying free
    or members, between the members' locked cards and the form, and redraws
    the card when the feed arrives;
  * a tile says free only where the page it names is open to a free account
    (app.js WALL_OPEN), and members only where it is not;
  * in a browser at a phone's width it fits, two tiles a row.

    python3 tests/test_the_welcome_page_shows_the_features.py
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import firstlook, reportrecord                         # noqa: E402

WEB = ROOT / "web"
ACCOUNT = (WEB / "js" / "account.js").read_text(encoding="utf-8")
APP = (WEB / "js" / "app.js").read_text(encoding="utf-8")
CSS = (WEB / "css" / "account.css").read_text(encoding="utf-8")

GAME = {"v": 2, "date": "2026-11-16", "game": "POR@MIN", "away": "POR", "home": "MIN",
        "names": {"POR": "Trail Blazers", "MIN": "Timberwolves"}, "final": {"away": 98.0, "home": 106.0},
        "reads": [4, 9], "call": {"team": "MIN", "right": True, "chance": 0.543}, "injuries": [7, 7], "missed": 0}
OLDER = dict(GAME, date="2026-11-15", game="LAC@BAL", away="LAC", home="BAL",
             names={"LAC": "Chargers", "BAL": "Ravens"}, call={"team": "BAL", "right": False, "chance": 0.68})


def _records(by_league):
    def fake(where, sport, today=None):
        return by_league.get(sport) or {"sport": sport, "totals": {}, "recent": {}, "games": [], "more": 0}
    return fake


def _web(report=None):
    web = Path(tempfile.mkdtemp())
    (web / "data").mkdir()
    if report is not None:
        (web / "data" / "record_head.json").write_text(json.dumps({"report": report}), encoding="utf-8")
    return web


def test_the_feed_carries_the_reports_record_and_the_newest_game():
    was = reportrecord.record
    reportrecord.record = _records({
        "nba": {"totals": {"games": 8, "call": [4, 8], "injuries": [46, 48]}, "games": [GAME]},
        "nfl": {"totals": {"games": 14, "call": [9, 14], "injuries": [80, 85]}, "games": [OLDER]},
    })
    try:
        got = firstlook.reports(_web({"wins": 80, "losses": 41, "net_units": 0.15}), where=Path("/nowhere"))
    finally:
        reportrecord.record = was
    assert got["picks"] == {"w": 80, "l": 41, "units": round(0.15, 1)}, got
    assert got["games"] == 22 and got["calls"] == {"right": 13, "n": 22}, got
    assert got["injuries"] == {"right": 126, "n": 133}, got
    s = got["sample"]
    assert s["league"] == "nba" and s["date"] == "2026-11-16", "the newest game, whatever it did"
    assert s["names"]["MIN"] == "Timberwolves" and s["call"]["right"] is True and s["reads"] == [4, 9]
    assert set(s) <= {"league", *firstlook.SAMPLE_FIELDS}, "nothing the free page does not show"


def test_nothing_graded_is_left_out_and_none_at_all_is_none():
    was = reportrecord.record
    reportrecord.record = _records({})
    try:
        assert firstlook.reports(_web(), where=Path("/nowhere")) is None
        only = firstlook.reports(_web({"wins": 3, "losses": 2, "net_units": -0.4}), where=Path("/nowhere"))
    finally:
        reportrecord.record = was
    assert only == {"picks": {"w": 3, "l": 2, "units": -0.4}}, only
    # A reader that fails leaves the page standing.
    reportrecord.record = lambda *a, **k: (_ for _ in ()).throw(OSError("no archive"))
    try:
        assert firstlook.reports(_web(), where=Path("/nowhere")) is None
    finally:
        reportrecord.record = was
    src = (ROOT / "engine" / "firstlook.py").read_text(encoding="utf-8")
    assert 'out["reports"] = reports(web)' in src


STUBS = """
const escapeHtml = (s) => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
const icon = () => "", iconMark = (n) => `<i data-ic="${n}"></i>`;
"""


def _between(a, b):
    return ACCOUNT[ACCOUNT.index(a):ACCOUNT.index(b)]


def _node(js):
    out = subprocess.run(["node", "-e", STUBS + js], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_page_draws_the_report_card_and_the_tiles():
    fl = {"reports": {"picks": {"w": 80, "l": 41, "units": 0.2}, "calls": {"right": 13, "n": 22}, "games": 22,
                      "injuries": {"right": 126, "n": 133}, "sample": dict(GAME, league="nba")}}
    lost = {"reports": {"games": 5, "sample": dict(OLDER, league="nfl")}}
    src = _between("const WF_REPORT_STEPS = [", "/* The page the account wall held back")
    full, bare, gone, tiles = _node(src + f"""console.log(JSON.stringify([flReportHTML({json.dumps(fl)}),
        flReportHTML({{}}), flReportHTML({json.dumps(lost)}), flFeaturesHTML()]));""")
    assert "A game report for every game" in full and "Parlays made of those picks" in full
    assert "Then it grades itself" in full and full.count('class="wf-step"') == 5
    assert "<b>80–41</b>" in full and "report picks, graded" in full
    assert "<b>13 of 22</b>" in full and "winners called" in full and "<b>95%</b>" in full
    assert "NBA · Nov 16" in full and "Trail Blazers" in full and "<b>106</b>" in full
    assert "We called the Timberwolves at 54% — right" in full and 'data-ic="check"' in full
    assert "4 of 9 reads right · 7 of 7 injury listings held" in full
    assert "wf-stats" not in bare and "wf-sample" not in bare and bare.count('class="wf-step"') == 5, \
        "with no record yet, what a report holds and nothing invented"
    assert "We called the Ravens at 68% — wrong" in gone and "<b>5</b>" in gone and "games fact-checked" in gone
    assert tiles.count('<li class="wf-tile') == 10 and 'href="#features"' in tiles
    assert tiles.count(">Free<") == 6 and tiles.count(">Members<") == 4


#: Each tile, the pages it opens: free only where every one is open to a free account.
TILE_PAGES = {"Every game, live": ("live", "pbp"), "Pick of the Day": ("potd",), "The Record": ("record",),
              "Playoff races": ("race",), "Fantasy and your bets": ("fantasy", "mybets"),
              "Alerts for your teams": ("alerts",), "Most Likely and Edge": ("likely", "edge"),
              "A page for every player": ("players",), "Ask Qellys": ("ask",), "UFC, fight by fight": ("ufc",)}


def test_a_tile_says_free_only_where_a_free_account_opens_it():
    i = APP.index("const WALL_OPEN = [")
    open_ = set(re.findall(r'"([a-z_]+)"', APP[i:APP.index("];", i)]))
    tiles = re.findall(r'\["[a-z]+", "([^"]+)", "[^"]+", ([01])\]', _between("const WF_FEATURES = [", "function wfDay("))
    assert len(tiles) == 10 and {t for t, _ in tiles} == set(TILE_PAGES), tiles
    for title, free in tiles:
        views = TILE_PAGES[title]
        if free == "1":
            assert all(v in open_ for v in views), (title, views)
        else:
            assert not any(v in open_ for v in views), (title, views)


def test_the_signup_screen_places_them_before_the_form_and_redraws_the_card():
    i = ACCOUNT.index("function signupHTML()")
    su = ACCOUNT[i:ACCOUNT.index("\n}\n", i)]
    assert su.index('<div class="fl-host">') < su.index('<div class="wf-report-host">${flReportHTML(_fl)}</div>') \
        < su.index("${flFeaturesHTML()}") < su.index('id="su-form"')
    j = ACCOUNT.index("function flPaint(")
    assert "if (r && fl) r.innerHTML = flReportHTML(fl);" in ACCOUNT[j:ACCOUNT.index("\n}\n", j)]
    drawn = set(re.findall(r'class="(wf-[a-z-]+)', ACCOUNT)) | set(re.findall(r'querySelector\("\.(wf-[a-z-]+)"', ACCOUNT))
    for cls in drawn:
        assert f".{cls}" in CSS, f"{cls} has no rule in account.css"


def test_in_a_browser_it_fits_a_phone_two_tiles_a_row():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    bill = {"configured": True, "signed_in": False, "plans": [{"id": "monthly", "ready": True}], "trial_days": 3,
            "trial_plan": "monthly", "paywall": True, "account_wall": True}
    fl = {"tonight": [], "reports": {"picks": {"w": 80, "l": 41, "units": 0.2}, "calls": {"right": 13, "n": 22},
                                     "games": 22, "injuries": {"right": 126, "n": 133},
                                     "sample": dict(GAME, league="nba")}}
    ful = lambda b: (lambda r: r.fulfill(status=200, content_type="application/json", body=b))  # noqa: E731
    srv, port = rendercheck._serve()
    errs, got = [], None
    shot = os.environ.get("QB_WELCOME_SHOT")
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
                page.route("**/api/billing/status*", ful(json.dumps(bill)))
                page.route("**/api/account/me*", ful(json.dumps({"signed_in": False, "account_wall": True})))
                page.route("**/api/firstlook*", ful(json.dumps(fl)))
                page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');}catch(e){}")
                page.goto(f"http://127.0.0.1:{port}/#signup", wait_until="domcontentloaded")
                for _ in range(30):                 # the page's CSP refuses wait_for_function's eval
                    if page.evaluate("!!document.querySelector('.wf-stats')"):
                        break
                    page.wait_for_timeout(500)
                got = page.evaluate("""(() => {
                  const card = document.querySelector('.wf-report'), tiles = [...document.querySelectorAll('.wf-tile')];
                  if (!card || !tiles.length) return null;
                  const tops = new Set(tiles.map((t) => Math.round(t.getBoundingClientRect().top)));
                  const inside = [card, ...tiles].every((el) => { const r = el.getBoundingClientRect();
                    return r.left >= 0 && r.right <= innerWidth; });
                  return { text: card.textContent.replace(/\\s+/g, ' ').trim(), tiles: tiles.length, rows: tops.size,
                           inside, wide: document.documentElement.scrollWidth <= innerWidth }; })()""")
                if shot:
                    page.locator(".wf-report").screenshot(path=shot + "-report.png")
                    page.locator(".wf-features").screenshot(path=shot + "-tiles.png")
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert not errs, errs[:3]
    assert got and got["inside"] and got["wide"], got
    assert got["tiles"] == 10 and got["rows"] == 5, got
    assert "80–41" in got["text"] and "We called the Timberwolves at 54% — right" in got["text"], got


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
