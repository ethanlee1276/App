"""The board comes alive: how often he cleared it, a win celebrated, every
game in its teams' colours, and a ticket's numbers that tick (app.js
hitChipsHTML, winCheck/winParty, teamVivid; js/slip.js; visuals.js
mountLiveTicks).

Ethan, 2026-10-27: "make sure you do all the idea and inventions and shit u
came up with and make sure its al pushed to the site." Four of the eight
ideas in docs/IDEAS.md's newest list:

  * HIT-RATE CHIPS (Outlier, Linemate): the side we hold, then how often he
    cleared tonight's number in his last five, last ten and every stored
    game, on the Edge rows, the Most Likely cards and the Over/Under cards.
  * A WIN, CELEBRATED (Underdog, Robinhood): the first time this device
    sees a bet graded a win, confetti and what it paid, once.
  * TEAM COLOURS (Apple Sports): every game card wears its two teams'.
  * NUMBERS THAT TICK: a saved ticket's numbers on the Live tab count to
    their new value, tinted by whether it is good news for the ticket.

Run directly: `python3 tests/test_the_board_comes_alive.py`
(the browser check with QB_BROWSER_TESTS=1 and /usr/bin/python3).
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
SLIP = (ROOT / "web" / "js" / "slip.js").read_text(encoding="utf-8")
VIS = (ROOT / "web" / "js" / "visuals.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")


def _fn(src: str, head: str) -> str:
    i = src.index(head)
    return src[i:src.index("\n}\n", i) + 2]


def _node(src: str):
    out = subprocess.run(["node", "-e", src], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    return json.loads(out.stdout)


STUBS = """
const escapeAttr = (x) => String(x == null ? "" : x).replace(/"/g, "&quot;");
const escapeHtml = escapeAttr;
"""


# --- how often he cleared it ----------------------------------------------------------------
def test_the_chips_count_from_the_side_we_hold():
    if not shutil.which("node"):
        return
    fn = _fn(APP, "function hitChipsHTML(r) {")
    got = _node(STUBS + fn + """
const vals = [52, 38, 61, 44, 47, 30, 55, 41, 49, 36, 58, 40.5];   // newest first
process.stdout.write(JSON.stringify({
  over: hitChipsHTML({ recent_values: vals, line: 40.5, side: "OVER" }),
  under: hitChipsHTML({ logs: vals.map((v) => ({ value: v })), line: 40.5, side: "under" }),
  few: hitChipsHTML({ recent_values: [50, 51, 52, 53], line: 40.5 }),
  ten: hitChipsHTML({ recent_values: vals.slice(0, 10), line: 40.5 }),
  noline: hitChipsHTML({ recent_values: vals }),
}));""")
    text = lambda h: " ".join(re.sub(r"<[^>]+>", " ", h).split())  # noqa: E731
    assert text(got["over"]) == "Over 4/5 L5 7/10 L10 8/12 All", text(got["over"])
    assert 'class="hit-chip up"' in got["over"], "four in five is green"
    assert text(got["under"]) == "Under 1/5 L5 3/10 L10 3/12 All", "the under's own count; 40.5 on the line is no hit"
    assert got["under"].count('class="hit-chip down"') == 3
    assert got["few"] == "" and got["noline"] == "", "under five games, or no number: nothing to count"
    assert text(got["ten"]) == "Over 4/5 L5 7/10 L10", "All only when there is more than the last ten"


def test_the_chips_ride_every_prop_row():
    edge = _fn(APP, "function edgeRowHTML(r, i) {")
    assert "${hitChipsHTML({ recent_values: r.vals, line: r.line, side: r.side })}" in edge
    assert "${r.kind === \"game\" ? \"\" : hitChipsHTML(r)}" in _fn(APP, "function obCardHTML(r, rank, opts = {}) {")
    assert '<div class="ou-mk">${ouMarketLine(r)}</div>${hitChipsHTML(r)}' in _fn(APP, "function ouCardHTML(r) {")
    assert "${propSpark(r)}${hitChipsHTML(r)}" in APP, "the Edge card too"
    for cls in (".hit-chips {", ".hit-chip {", ".hit-chip.up {", ".hit-chip.down {"):
        assert cls in CSS, cls


# --- a win, celebrated ----------------------------------------------------------------------
def test_a_win_is_celebrated_once_and_only_when_it_is_news():
    if not shutil.which("node"):
        return
    check = _fn(APP, "function winCheck() {")
    got = _node("""
const store = {};
const localStorage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } };
let BETS = [];
const mbLoad = () => BETS;
const mbProfit = (b) => b.stake * (b.odds > 0 ? b.odds / 100 : 100 / Math.abs(b.odds));
const parties = [];
const winParty = (n, profit) => parties.push([n, Math.round(profit * 100) / 100]);
const WON_SEEN_KEY = "qb_won_seen";
const WIN_FRESH_MS = 36 * 3600 * 1000;
""" + check + """
const d = new Date(), today = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
BETS = [{ id: "a", result: "win", stake: 10, odds: 100, date: today }];
winCheck();                                                     // the device's first look
const first = parties.length;
BETS.push({ id: "b", result: "win", stake: 50, odds: -110, date: today });
winCheck();
BETS.push({ id: "c", result: "win", stake: 20, odds: 150, date: "2025-11-02" });   // an old season's, adopted
BETS.push({ id: "d", result: "win", stake: 20, odds: 150 });                       // no date at all
winCheck();
winCheck();                                                     // once only
BETS.push({ id: "e", result: "loss", stake: 5, odds: 100, date: today });
winCheck();
process.stdout.write(JSON.stringify({ first, parties, seen: JSON.parse(store[WON_SEEN_KEY]) }));""")
    assert got["first"] == 0, "the device's first look remembers every win already there, without a party"
    assert got["parties"] == [[1, 45.45]], "one party, for the fresh win, with what it paid"
    assert got["seen"] == ["a", "b", "c", "d"]
    assert "settled_at" not in APP, "the bet's own date and the diff, never a stamp (tests/test_settings)"
    assert "winCheck();" in _fn(APP, "function mbSave(bets) {")
    apply = APP[APP.index("function acctApplySection(name, sec) {"):]
    assert "faviconBadge();\n      winCheck();" in apply[:apply.index('} else if (name === "fantasy")')], \
        "a win the box settled while you were away is news on the next visit"
    assert "winCheck();            // the device's first look" in APP


def test_the_party_is_confetti_in_the_palette_and_words_for_reduced_motion():
    party = _fn(APP, "function winParty(n, profit) {")
    assert 'tfToast(`${n > 1 ? `${n} bets won` : "Your bet won"}${profit > 0 ? ` · +${mbMoney(profit)}` : ""}`);' in party
    assert party.index("tfToast(") < party.index('matchMedia("(prefers-reduced-motion: reduce)")') \
        < party.index("document.createElement"), "the words for everyone, the confetti only for motion"
    assert 'host.setAttribute("aria-hidden", "true");' in party and "setTimeout(() => host.remove(), 2400);" in party
    assert "@keyframes winBurst" in CSS and ".win-party { position: fixed;" in CSS and "pointer-events: none" in CSS


# --- team colours ----------------------------------------------------------------------------
def test_every_game_card_wears_its_teams_colours():
    if not shutil.which("node"):
        return
    fn = _fn(APP, "function teamVivid(a) {")
    got = _node("""
const TEAMS = { CHI: { primary: "#0B162A", secondary: "#C83803" }, GB: { primary: "#203731", secondary: "#FFB612" },
                KC: { primary: "#E31837", secondary: "#FFB81C" }, LV: { primary: "#000000", secondary: "#A5ACAF" } };
const activeTeams = () => TEAMS;
""" + fn + """
process.stdout.write(JSON.stringify(["CHI", "GB", "KC", "LV", "XX"].map(teamVivid)));""")
    assert got == ["#C83803", "#FFB612", "#E31837", "#000000", "var(--brand)"], got
    # The card wears them as the light its stadium is lit by since
    # 2026-10-28 (tests/test_the_stadium_wears_its_teams_light.py).
    assert 'style="--ta:${escapeAttr(teamLight(g.away))};--tb:${escapeAttr(teamLight(g.home))}"' in APP
    assert "const hex = teamVivid(a);" in _fn(APP, "function teamLight(a) {")
    assert "background-image: var(--grad-teams-light); mix-blend-mode: overlay;" in CSS


# --- numbers that tick ------------------------------------------------------------------------
def test_a_tickets_numbers_tick_on_the_live_tab():
    assert 'data-tick="sl:${esc([l.player || l.team || "", l.market, l.line, l.side].join("|"))}"' in SLIP
    assert '${l.side === "under" ? ` data-tick-mode="invert"` : ""}' in SLIP, "an under's climbing number is bad news"
    assert 'data-tick="sn:${esc(key)}" data-tick-v="${Math.round(n.chance * 100)}"' in SLIP, \
        "the chance ticks in the units it is shown in"
    assert "nowHTML(c.now, b.id)" in SLIP
    draw = SLIP[SLIP.index("  function draw() {"):]
    assert 'if (typeof mountLiveTicks === "function") mountLiveTicks(host);' in draw[:draw.index("\n  }\n")]
    assert '(mode === "invert" ? !up : up) ? "tick-up" : "tick-down"' in VIS


# --- in a browser (opt-in) -------------------------------------------------------------------
def test_the_board_comes_alive_in_a_browser():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    from test_every_page_opens_clean import _board

    b = _board()
    vals = [52, 38, 61, 44, 47, 30, 55, 41, 49, 36, 58, 42]
    for i, r in enumerate(b.get("most_likely") or []):
        r["recent_values"] = [v - i for v in vals]
    body = json.dumps(b)
    bets = [{"id": "17000000000009", "desc": "Josh Allen Under 259.5 Passing Yards", "odds": -110, "stake": 50,
             "book": "FanDuel", "sport": "NFL", "date": "2026-10-27", "result": "pending"}]
    chromium = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium")
    srv, port = rendercheck._serve()
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists(chromium):
                kw["executable_path"] = chromium
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                          service_workers="block")
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.route(lambda url: not url.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
                for pat in ("**/api/recommendations*", "**/data/recommendations*.json*"):
                    page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=body))
                page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb.tour','done');"
                                     f"localStorage.setItem('qb_mybets_v1', {json.dumps(json.dumps(bets))});}}catch(e){{}}")
                page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#likely", wait_until="load")
                page.wait_for_timeout(1800)
                chips = page.evaluate("""(() => { const c = [...document.querySelectorAll('.view.active .hit-chips')]
                                                     .find((e) => e.offsetParent); return c ? c.textContent : ''; })()""")
                assert "".join(chips.split()) == "Over4/5L57/10L109/12All", chips
                stripe = page.evaluate("""(() => { const g = document.querySelector('.game-card');
                                                   return g ? getComputedStyle(g).getPropertyValue('--ta').trim() : 'none'; })()""")
                assert stripe and stripe != "var(--brand)" or stripe == "none", stripe
                page.evaluate("mbResult('17000000000009', 'win')")
                page.wait_for_timeout(400)
                assert page.evaluate("document.querySelectorAll('.win-party i').length") == 42
                toast = page.evaluate("(document.querySelector('.tf-toast') || {}).textContent || ''")
                assert "Your bet won · +$45.45" in toast, toast
                assert not errors, errors
                ctx.close()
            finally:
                browser.close()
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
