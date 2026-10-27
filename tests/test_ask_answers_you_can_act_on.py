"""An Ask answer you can act on: under the card about tonight's player line,
Add to slip, Track it and Watch (engine/askcards `_bet`, engine/askbot
line_shop, web/js/ask.js askActsHTML; the one-leg ticket's alerts in
engine/slipwatch and engine/pushmine).

Ethan, 2026-10-27: "Look at other apps that use AI betting ... and kind of
copy them and do it better." FanDuel's AceAI puts a bet on its slip and
Action Network's Playbook pre-fills one; neither follows it once placed.
Here a tracked bet is a ticket of one leg in the screenshot checker's shape,
so the Live tab follows it, the box settles it and the phone hears it.

What these hold: a card carries tonight's bet only when it is the one the
card is about (the same side, the same number, a price); the price card's is
at the best price on our side; line_shop names the bet field by field; a
market the box cannot follow is logged by hand instead; the tracked entry is
a leg the checker's own cleaner keeps; a ticket of one leg is a "bet" on the
phone and never "down to its last leg"; the page draws the buttons on the
last card about a bet, says what is already done, leaves the slip off for
another league's player, and styles every class it draws; the slip's dock
stands above the composer; and in a browser the three buttons do what they
say.

Run directly: `python3 tests/test_ask_answers_you_can_act_on.py`
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

from engine import askbot as AB                                # noqa: E402
from engine import askcards as AC                              # noqa: E402
from engine import slipgrade as SG                             # noqa: E402
from engine import slipwatch as SW                             # noqa: E402

ASK_JS = (ROOT / "web" / "js" / "ask.js").read_text(encoding="utf-8")
ASK_CSS = (ROOT / "web" / "css" / "ask.css").read_text(encoding="utf-8")

TONIGHT = {"player": "Josh Allen", "team": "BUF", "opponent": "KC", "market": "pass_yds",
           "market_label": "Passing Yards", "side": "UNDER", "line": 259.5, "odds": -110, "book": "FanDuel",
           "game_date": "2026-10-27", "model_prob": 0.58}
HITS = {"player": "Josh Allen", "sport": "nfl", "stat": "Passing Yards", "line": 259.5, "side": "under",
        "last_10_games": [{"vs": "MIA", "value": 233.0}, {"vs": "NE", "value": 281.0}],
        "last_5": {"games": 5, "over": 2, "under": 3, "under_hit_rate": 0.6},
        "tonight": TONIGHT}
BET = {"sport": "nfl", "player": "Josh Allen", "side": "UNDER", "line": 259.5, "odds": -110, "book": "FanDuel",
       "market": "pass_yds", "market_label": "Passing Yards", "team": "BUF", "opponent": "KC",
       "game_date": "2026-10-27", "trackable": True}
SHOP = {"picks": [{"league": "nfl", "pick": "Josh Allen UNDER 259.5 Passing Yards", "our_price": -110,
                   "our_book": "FanDuel", "player": "Josh Allen", "market": "pass_yds",
                   "market_label": "Passing Yards", "side": "UNDER", "line": 259.5, "team": "BUF",
                   "opponent": "KC", "game_date": "2026-10-27",
                   "books": [{"book": "DraftKings", "line": 259.5, "over_odds": -112, "under_odds": -108},
                             {"book": "FanDuel", "line": 259.5, "over_odds": -110, "under_odds": -110}],
                   "best_price_at_this_line": {"book": "DraftKings", "odds": -108}}]}


# --- the bet a card carries ---------------------------------------------------------------------
def test_the_hit_card_carries_tonights_bet_when_it_is_the_one_asked_about():
    assert AC.hits_card(HITS)["bet"] == BET
    over = dict(HITS, side="over", last_5={"games": 5, "over": 2, "under": 3, "over_hit_rate": 0.4})
    assert "bet" not in AC.hits_card(over), "asked about the over: no price for it on the board"
    assert "bet" not in AC.hits_card(dict(HITS, line=249.5)), "another number: not tonight's bet"
    assert "bet" not in AC.hits_card(dict(HITS, tonight=dict(TONIGHT, odds=None))), "no price, no buttons"
    assert "bet" not in AC.hits_card(dict(HITS, tonight=None))


def test_the_price_card_carries_the_bet_at_the_best_price():
    bet = AC.prices_card(SHOP)["bet"]
    assert (bet["odds"], bet["book"]) == (-108, "DraftKings"), "the best price on our side"
    assert {k: bet[k] for k in ("player", "market", "side", "line")} == \
        {"player": "Josh Allen", "market": "pass_yds", "side": "UNDER", "line": 259.5}
    plain = {"picks": [dict(SHOP["picks"][0], best_price_at_this_line=None)]}
    assert (AC.prices_card(plain)["bet"]["odds"], AC.prices_card(plain)["bet"]["book"]) == (-110, "FanDuel")
    game = {"picks": [{"league": "nfl", "pick": "Bills -2.5", "our_price": -110, "side": "BUF",
                       "books": [{"book": "FanDuel", "line": -2.5}]}]}
    assert "bet" not in AC.prices_card(game), "a game line is not a player bet"


def test_line_shop_names_the_bet_field_by_field():
    board = {"sport": "nfl", "recommendations": [dict(TONIGHT, all_lines=[
        {"book": "FanDuel", "line": 259.5, "over_odds": -110, "under_odds": -110},
        {"book": "DraftKings", "line": 259.5, "over_odds": -112, "under_odds": -108}])]}
    pick = AB.line_shop({"nfl": board}, "Josh Allen")["picks"][0]
    assert {k: pick.get(k) for k in ("player", "market", "side", "line", "team", "opponent", "game_date")} == \
        {"player": "Josh Allen", "market": "pass_yds", "side": "UNDER", "line": 259.5, "team": "BUF",
         "opponent": "KC", "game_date": "2026-10-27"}
    assert AC.prices_card({"picks": [pick]})["bet"]["book"] == "DraftKings"


def test_a_market_the_box_cannot_follow_is_logged_by_hand():
    odd = AC._bet("nfl", "Josh Allen", dict(TONIGHT, market="longest_completion"))
    assert odd and odd["trackable"] is False
    assert AC._bet("nfl", "Josh Allen", TONIGHT)["trackable"] is True


# --- the ticket of one leg --------------------------------------------------------------------
def test_a_ticket_of_one_leg_is_a_bet_and_never_down_to_its_last_leg():
    one = {"legs": [{"player": "Josh Allen"}], "now": {"status": "open", "left": 1}}
    two = {"legs": [{}, {}], "now": {"status": "open", "left": 1}}
    assert SW.last_leg(one) is False and SW.last_leg(two) is True
    pm = (ROOT / "engine" / "pushmine.py").read_text()
    assert 'return "bet" if legs == 1 else "parlay"' in pm and 'f"Your {_noun(legs)} is on"' in pm
    sw = (ROOT / "engine" / "slipwatch.py").read_text()
    assert 'legs=len(card.get("legs") or []))' in sw, "the game-on alert is told how many legs"
    slip = (ROOT / "web" / "js" / "slip.js").read_text()
    assert '(c.legs || []).length > 1 && n.status === "open"' in slip, "the Live tab's own last-leg card too"


# --- the page ------------------------------------------------------------------------------------
def _harness(script: str) -> dict:
    i = ASK_JS.index("const ASK_CARD = {")
    j = ASK_JS.index("/* WHAT TO ASK NEXT", i)
    k = ASK_JS.index("/* AN ANSWER YOU CAN ACT ON")
    m = ASK_JS.index("function askSlipCard(", k)
    stubs = """
const escapeHtml = (x) => String(x == null ? "" : x).replace(/&/g, "&amp;").replace(/</g, "&lt;")
  .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const escapeAttr = escapeHtml;
const slugify = (x) => String(x || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
const surname = (x) => String(x || "").split(" ").slice(-1)[0];
const icon = (n) => `<i data-ic="${n}"></i>`;
const document = { addEventListener() {}, querySelectorAll() { return []; } };
const state = { sport: "nfl" };
let BETS = [], SLIP = [];
const mbLoad = () => BETS.slice();
const mbSave = (b) => { BETS = b; };
const slipHas = (r) => SLIP.includes(`${r.player}|${r.market}`);
const slipToggle = () => true;
const tfToast = () => {};
const alertsFetch = () => Promise.resolve(null);
const alertsPost = () => Promise.resolve({});
let _alertsCache = { watches: [] };
"""
    src = stubs + ASK_JS[i:j] + ASK_JS[k:m] + "\n" + script
    out = subprocess.run(["node", "-e", src], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    return json.loads(out.stdout)


def _text(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def test_the_page_draws_the_buttons_and_says_what_is_done():
    if not shutil.which("node"):
        return
    bet = json.dumps(BET)
    got = _harness(f"""
const b = {bet};
const fresh = askActsHTML(b);
const entry = askBetEntry(b, 25, -110, "FanDuel");
const hand = askBetEntry(Object.assign({{}}, b, {{ trackable: false }}), 10, -105, "");
BETS = [entry]; SLIP = ["Josh Allen|pass_yds"]; _alertsCache = {{ watches: [{{ kind: "player", value: "josh allen" }}] }};
const done = askActsHTML(b);
state.sport = "nba";
const elsewhere = askActsHTML(b);
const cards = askCardsHTML({{ cards: [{json.dumps(AC.hits_card(HITS))}, {json.dumps(AC.prices_card(SHOP))}] }});
process.stdout.write(JSON.stringify({{ fresh, entry, hand, done, elsewhere, cards }}));
""")
    fresh = _text(got["fresh"])
    assert "Under 259.5 Passing Yards −110 FanDuel" in fresh, fresh
    assert "Add to slip" in fresh and "Track it" in fresh and "Watch" in fresh
    assert 'data-ic="ticket"' in got["fresh"] and 'data-ic="bell"' in got["fresh"]
    assert "We follow it on the Live tab and settle it in My Bets off the box score." in fresh
    done = _text(got["done"])
    assert "In your slip" in done and "In My Bets" in done and "Watching" in done, done
    assert 'aria-pressed="true"' in got["done"] and got["done"].count(" disabled") == 2
    assert "Add to slip" not in _text(got["elsewhere"]) and 'data-ask-act="slip"' not in got["elsewhere"], \
        "the slip holds the open board's league; another league's player is tracked or watched, not slipped"
    e = got["entry"]
    assert (e["src"], e["sport"], e["date"], e["desc"], e["stake"], e["odds"], e["result"]) == \
        ("slip", "NFL", "2026-10-27", "Josh Allen Under 259.5 Passing Yards", 25, -110, "pending")
    assert e["slip_key"] == "ask-josh-allen-pass-yds-under-259.5-2026-10-27"
    leg = SG.clean_slip({"legs": e["legs"]})["legs"]
    assert len(leg) == 1 and (leg[0]["market"], leg[0]["side"], leg[0]["line"], leg[0]["team"]) == \
        ("pass_yds", "under", 259.5, "BUF"), "a leg the checker's own cleaner keeps: the box follows it"
    assert "src" not in got["hand"] and "legs" not in got["hand"] and got["hand"]["book"] == "Other", \
        "a market the box cannot follow is a hand-logged bet"
    cards = got["cards"]
    assert cards.count('class="ask-acts"') == 1, "one card carries the buttons"
    assert cards.index('class="ask-acts"') > cards.index("ask-prices"), "the last card about a bet: the best price"
    assert "−108 DraftKings" in _text(cards)


def test_every_class_the_action_row_draws_is_styled():
    k = ASK_JS.index("/* AN ANSWER YOU CAN ACT ON")
    block = ASK_JS[k:ASK_JS.index("function askSlipCard(", k)]
    drawn = set(re.findall(r'class="([a-z-]+)', block)) | set(re.findall(r'"(ask-act[a-z-]*)', block))
    drawn = {c for c in drawn if c.startswith("ask-")}
    styled = set(re.findall(r"\.(ask-[a-z-]+)", ASK_CSS))
    assert {"ask-acts", "ask-acts-bet", "ask-acts-px", "ask-acts-row", "ask-act", "ask-track",
            "ask-track-note"} <= drawn, sorted(drawn)
    assert drawn <= styled, sorted(drawn - styled)


def test_the_slip_dock_stands_above_the_composer():
    assert ":root { --ask-foot: 142px; }" in ASK_CSS, "the composer's height before it is measured"
    assert "body.ask-open #qb-slip { bottom: var(--ask-foot); padding-bottom: 0; }" in ASK_CSS
    assert "body.ask-typing #qb-slip { display: none; }" in ASK_CSS
    i = ASK_JS.index("function askRoomSize(")
    size = ASK_JS[i:ASK_JS.index("\n}\n", i)]
    assert 'document.documentElement.style.setProperty("--ask-foot"' in size


# --- in a browser (opt-in) -------------------------------------------------------------------
def test_the_three_buttons_in_a_browser():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    answer = {"text": "**Lean under.** We have him at a median of 239.5.", "sources": [], "sig": "x",
              "cards": [AC.hits_card(HITS)], "follow": []}
    me = {"signed_in": True, "email": "you@example.com", "profile": {"handle": "fan0"}}
    bill = {"signed_in": True, "email": "you@example.com", "paywall": True, "entitled": True, "plans": []}
    posted = []

    def alerts(route):
        if route.request.url.split("?")[0].endswith("/api/alerts/watch"):
            posted.append(json.loads(route.request.post_data or "{}"))
            body = {"watches": [{"id": 1, "kind": "player", "value": "Josh Allen", "label": "Josh Allen"}]}
        else:
            body = {"watches": [], "fired": [], "unseen": 0}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

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
                                          service_workers="block", reduced_motion="reduce")
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.route(lambda url: not url.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                ok = lambda body: (lambda r: r.fulfill(status=200, content_type="application/json",  # noqa: E731
                                                       body=json.dumps(body)))
                page.route("**/api/account/me*", ok(me))
                page.route("**/api/billing/status*", ok(bill))
                page.route("**/api/ask", ok(answer))
                page.route("**/api/alerts/**", alerts)
                page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');sessionStorage.removeItem('qb.ask');"
                                     "localStorage.removeItem('qb_slip_v1');localStorage.removeItem('qb_mybets_v1');}"
                                     "catch(e){}")
                page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#ask", wait_until="load")
                page.wait_for_selector("#ask-input", timeout=20000)
                page.fill("#ask-input", "Is Josh Allen under 259.5 passing yards a good bet?")
                page.keyboard.press("Enter")
                page.wait_for_selector(".ask-acts", timeout=15000)
                page.click('[data-ask-act="slip"]')
                page.wait_for_selector('[data-ask-act="slip"].on', timeout=5000)
                slip = page.evaluate("JSON.parse(localStorage.getItem('qb_slip_v1') || '{}')")
                assert slip.get("sport") == "nfl" and [(l["player"], l["market"], l["side"], l["line"], l["odds"])
                                                      for l in slip.get("legs", [])] == \
                    [("Josh Allen", "pass_yds", "UNDER", 259.5, -110)], slip
                assert page.is_visible("#qb-slip .slip-bar"), "the dock shows"
                dock = page.evaluate("document.querySelector('#qb-slip .slip-bar').getBoundingClientRect().bottom")
                composer = page.evaluate("document.querySelector('.ask-dock').getBoundingClientRect().top")
                assert dock <= composer + 1, f"the dock ({dock}) stands above the composer ({composer})"
                page.click('[data-ask-act="track"]')
                page.fill("[data-ask-stake]", "")
                page.click(".ask-track .ask-act.primary")
                assert "Type the stake" in page.inner_text(".ask-track-note"), "no stake, nothing saved"
                page.fill("[data-ask-stake]", "25")
                page.click(".ask-track .ask-act.primary")
                page.wait_for_selector('[data-ask-act="track"].on', timeout=5000)
                bets = page.evaluate("JSON.parse(localStorage.getItem('qb_mybets_v1') || '[]')")
                assert len(bets) == 1 and bets[0]["src"] == "slip" and bets[0]["stake"] == 25 \
                    and bets[0]["legs"][0]["market"] == "pass_yds", bets
                page.click('[data-ask-act="watch"]')
                page.wait_for_selector('[data-ask-act="watch"].on', timeout=5000)
                assert posted == [{"kind": "player", "value": "Josh Allen"}], posted
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
