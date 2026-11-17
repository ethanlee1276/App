"""A tapped pick opens the player's page, the pick heading it (2026-11-17).

Ethan, asked whether a pick on the Edge and Most Likely boards should keep
opening the pick page or open the new player page: "always send too the new
player page". What these hold:

  * every tap on a player's pick (a Most Likely row or card, an Edge card, a
    long shot, a Live row's bet, Tonight-every-league's cards, a shared
    ticket's leg) goes through openPick, which opens the player's page on
    the pick's market and hands it the pick: its own id, the board it came
    from (a Most Likely row by its own id, never another of the player's
    props) and the bet a Live row was placed at;
  * a game bet, a fight, a league with no player page and a pick the board
    no longer holds still open the pick page, and so do the routers (a
    pasted /pick/ link, a #prop/ address);
  * any other door to a player (the search, a name in a report) drops the
    pick, so a page opened from a search never wears a stale one;
  * the player's page draws the pick at the top of its Overview with the
    pick page's own pieces (pickTermsFor, the words, the metrics, why it's
    likely, the chart), redrawn with the page only when it changed, with a
    way down to the same market's every number;
  * and in a browser a tap on a Most Likely card lands on #player/<name>,
    the pick said in that board's terms with its reasons, and a game bet
    still opens its own page.

Run directly: `python3 tests/test_a_tapped_pick_opens_the_player_page.py`
(the browser check with QB_BROWSER_TESTS=1 and /usr/bin/python3).
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
sys.path.insert(0, str(Path(__file__).resolve().parent))

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
DETAIL = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
PAGE = (ROOT / "web" / "js" / "playerpage.js").read_text(encoding="utf-8")
PCSS = (ROOT / "web" / "css" / "playerpage.css").read_text(encoding="utf-8")
DCSS = (ROOT / "web" / "css" / "detail.css").read_text(encoding="utf-8")


def _fn(src, name):
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 2]


class _Harness:
    """A sibling test module, imported when a test first needs it (never at
    module scope: test_doctor)."""
    def __init__(self, name):
        self._name = name

    def __getattr__(self, attr):
        import importlib
        return getattr(importlib.import_module(self._name), attr)


CARD = _Harness("test_the_whole_pick_card_opens_its_pick")

#: The board openPick reads: one edge prop, the Most Likely row on the same
#: market at another line, and a fight.
STUBS = r"""
var state = { sport: "nfl" }, _profTab = {}, calls = [];
const PLR_LG = /^(nfl|cfb|nba|wnba|nhl|mlb|cbb)$/;
const EDGE = [{ player: "Chuba Hubbard", market: "rec", market_label: "Receptions", side: "OVER", line: 2.5, sport: "nfl" },
              { player: "Ilia Topuria", market: "ml", market_label: "Moneyline", side: "YES", line: null, sport: "ufc" }];
const ML = [{ player: "Chuba Hubbard", market: "rec", market_label: "Receptions", side: "over", line: 1.5 }];
const propId = (r) => [r.player, r.market, r.side, r.line].join("|");
const pickSlug = (r) => "slug-" + r.market + "-" + r.line;
const slugify = (s) => String(s).toLowerCase().replace(/\W+/g, "-");
function findProp(id) { return EDGE.find((r) => propId(r) === id || pickSlug(r) === id) || null; }
function findLikelyProp(id) { return ML.find((r) => propId(r) === id) || null; }
function likelyTarget(r) { return EDGE.find((x) => x.player === r.player && x.market === r.market) || r; }
function openProp(id, o) { calls.push(["pick page", id, !!(o && o.likely)]); }
function openPlayerRoute(slug, name, pick) { calls.push(["player page", slug, name, pick]); }
"""


def _node(body):
    if not shutil.which("node"):
        return None
    prog = STUBS + _fn(APP, "openPick") + f"\nconsole.log(JSON.stringify((() => {{ {body} }})()));"
    path = os.path.join(tempfile.mkdtemp(), "t.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(prog)
    out = subprocess.run(["node", path], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    return json.loads(out.stdout)


def test_a_players_pick_opens_the_player_page_on_its_market():
    got = _node("""
      openPick("Chuba Hubbard|rec|OVER|2.5");
      openPick("Chuba Hubbard|rec|over|1.5", { likely: true });
      openPick("Chuba Hubbard|rec|OVER|2.5", { bet: JSON.stringify({ player: "Chuba Hubbard", market: "rec", odds: -150 }) });
      openPick("Chuba Hubbard|rec|OVER|2.5", { bet: "not json" });
      return { calls, tab: _profTab };
    """)
    if got is None:
        return
    edge, likely, bet, broken = got["calls"]
    assert edge == ["player page", "chuba-hubbard", "Chuba Hubbard",
                    {"id": "slug-rec-2.5", "likely": False, "likelyId": None, "bet": None}], edge
    assert likely[3] == {"id": "slug-rec-2.5", "likely": True, "likelyId": "Chuba Hubbard|rec|over|1.5", "bet": None}, \
        "the Most Likely row travels by its own id, at its own line"
    assert bet[3]["bet"] == {"player": "Chuba Hubbard", "market": "rec", "odds": -150}, "a Live row's bet as placed"
    assert broken[0] == "player page" and broken[3]["bet"] is None, "a bad bet never stops the tap"
    assert got["tab"] == {"Chuba Hubbard": "Receptions"}, "the page opens on the tapped market"


def test_a_game_bet_a_fight_and_a_gone_pick_keep_the_pick_page():
    got = _node("""
      openPick("game|CAR@GB|moneyline|CAR");
      openPick("Ilia Topuria|ml|YES|");
      openPick("Nobody|rec|OVER|1.5", { likely: true });
      state.sport = "ufc"; EDGE[0].sport = undefined;
      openPick("Chuba Hubbard|rec|OVER|2.5");
      return calls;
    """)
    if got is None:
        return
    assert [c[0] for c in got] == ["pick page"] * 4, got
    assert got[2] == ["pick page", "Nobody|rec|OVER|1.5", True], "the pick page says the pick is gone, as before"


def test_every_tap_goes_through_the_pick_door_and_the_routers_keep_the_pick_page():
    taps = [
        'else if (door.dataset.prop) openPick(door.dataset.prop, { likely: door.dataset.likely === "1", bet: door.dataset.bet });',
        'if (kind === "likely") return openPick(target, { likely: true });',
        'if (kind === "prop") return openPick(target);',
        'if (findProp(slug)) { openPick(slug); return; }',
    ]
    for t in taps:
        assert t in APP, t
    assert APP.count('openPick(card.dataset.prop, { likely: card.dataset.likely === "1", bet: card.dataset.bet })') == 2, \
        "the click and the keyboard"
    assert APP.count("openProp(card.dataset.prop") == 0 and APP.count("openProp(door.dataset.prop") == 0
    # The routers: a pasted pick link and a #prop/ address still open the pick page.
    assert 'if (h.startsWith("prop/")) { openProp(decodeURIComponent(h.slice(5))); return; }' in APP
    assert "openProp(slug, { likely });" in APP
    route = _fn(APP, "openPlayerRoute")
    assert "function openPlayerRoute(slug, shown, pick) {" in route
    assert "state.playerPick = pick ? { ...pick, slug: slugify(slug) } : null;" in route, \
        "any other door to a player drops the pick"
    assert "const PLR_LG = /^(nfl|cfb|nba|wnba|nhl|mlb|cbb)$/;" in APP


def test_the_player_page_heads_its_overview_with_the_pick():
    assert '`<div class="plr-tapped"></div><div class="plr-season"></div>' in PAGE, "first in the Overview"
    fill = _fn(PAGE, "plrTappedInto")
    assert 'loadRoom("js/detail.js", "css/detail.css")' in fill, "the pick page's code, loaded the first time"
    assert "p.slug !== slugify(page._plr.player)" in fill, "only on the player whose pick it is"
    assert "if (slot._html === html) return;" in fill, "redrawn only when it changed: an open fold stays open"
    assert "The pick you tapped is no longer on tonight’s board." in fill
    assert 'class="btn ghost plr-tapped-go">This market’s every number</button>' in fill
    mount = _fn(PAGE, "renderPlayerPage")
    assert 'if (state.playerPick && same._pick !== state.playerPick) plrShow(same, "overview");' in mount
    assert 'const open = state.playerPick ? "overview" : PLR_TAB[key] || "overview";' in mount
    assert mount.count("plrTappedInto(") == 2, "the first draw and every redraw"
    assert '.closest(".plr").querySelector(".plr-tonight")' in PAGE, "the way down lands on the market's card"
    for sel in (".plr-tapped:empty { display: none; }", ".plr-tapped-go {"):
        assert sel in PCSS, sel


def test_the_pick_is_drawn_with_the_pick_pages_own_pieces():
    card = _fn(DETAIL, "pickOnPlayerHTML")
    assert "pickTermsFor(p.id, p.likely, p.likelyId, p.bet)" in card
    for piece in ("${pickWordsHTML(t)}", "${pickMetricsHTML(t)}", "${whyLikelyHTML(v, r, lk)}", "${pickChartHTML(t)}",
                  'betItHTML(lk || r, "btn primary")', "data-ask-pick="):
        assert piece in card, piece
    assert card.index("whyLikelyHTML(v, r, lk)") < card.index("pickChartHTML(t)"), "why it's likely, then its chart"
    assert "The pick you tapped · ${escapeHtml(board)}" in card
    assert 'lk ? `Most Likely${t.tier ? ` · ${t.tier.word}` : ""}`' in card
    assert "if (!t) return null;" in card
    page = _fn(DETAIL, "renderPropPage")
    assert "pickTermsFor(state.propId, state.propLikely, state.propLikelyId, state.propBet)" in page, \
        "one resolution for both pages, so they never tell a pick differently"
    rule = DCSS[DCSS.index(".pp-tapped {"):]
    assert "background-image: var(--grad-tone), var(--grad-card);" in rule[:rule.index("}")], \
        "light from the left edge, not a stripe (test_no_hard_lines)"


def test_in_a_browser_a_most_likely_card_opens_the_player_page_with_its_pick():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    board = CARD._board()
    row = board["most_likely"][0]
    logs = [{"week": w, "opponent": "NO", "home": True, "value": v} for w, v in ((9, 3), (8, 2), (7, 4), (6, 1))]
    # The board's rows carry both: the games for the reasons, the values for the chart.
    row["logs"], row["recent_values"] = logs, [g["value"] for g in logs]
    game = {"kind": "game", "player": "", "home": "GB", "away": "CAR", "matchup": "CAR @ GB", "market": "moneyline",
            "bet_type": "moneyline", "side": "home", "team": "GB", "odds": -150, "model_prob": 0.62, "book": "DraftKings",
            "market_label": "Moneyline", "pick_label": "GB ML", "game_date": "2099-01-01", "line": None}
    board["game_bets"] = [dict(game, win_prob=0.62, fair_prob=0.58, ev_per_unit=0.04, grade="B")]
    body = json.dumps(board)
    srv, port = rendercheck._serve()
    got = {}
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                          service_workers="block")
                page = ctx.new_page()
                errs = []
                page.on("pageerror", lambda e: errs.append(str(e)))
                page.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb_intro_v1', '1');"
                                     " localStorage.setItem('qb.tour', 'done'); } catch (e) {}")
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
                for pat in ("**/api/recommendations*", "**/data/recommendations*.json*"):
                    page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=body))
                page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#likely", wait_until="load")
                page.wait_for_selector("#view-likely .ob-card .ob-ring", timeout=20000)
                page.locator("#view-likely .ob-card .ob-ring").first.click()
                page.wait_for_selector(".plr .plr-tapped .pp-tapped", timeout=20000)
                got["hash"] = page.evaluate("location.hash")
                got["view"] = page.evaluate("state.view")
                got["card"] = page.locator(".plr-tapped .pp-tapped").inner_text()
                got["first"] = page.evaluate(
                    "document.querySelector('[data-plr-panel=\"overview\"]').firstElementChild.className")
                got["go"] = page.locator(".plr-tapped-go").count()
                got["chart"] = page.locator(".plr-tapped .pp-tapped .pa-tile").count()
                # Another door to the same player (the search's) drops the pick.
                page.evaluate("openPlayerRoute('chuba-hubbard', 'Chuba Hubbard')")
                page.wait_for_timeout(400)
                got["after_search"] = page.locator(".plr-tapped .pp-tapped").count()
                got["errs"] = list(errs)
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert got["hash"] == "#player/chuba-hubbard" and got["view"] == "players", (got["hash"], got["view"])
    card = got["card"]
    assert "THE PICK YOU TAPPED · MOST LIKELY" in card.upper(), card[:200]
    assert "over 1.5 Receptions" in card and "DraftKings" in card, card[:300]
    # Drawn in capitals by the sheet; the words are the pick page's own.
    assert "WHY IT’S LIKELY" in card.upper() and "THE CASE FOR THE OVER 1.5" in card.upper(), "the reasons came with it"
    assert got["chart"] > 0, "and its chart against the tapped line"
    assert got["first"] == "plr-tapped", got["first"]
    assert got["go"] == 1
    assert got["after_search"] == 0, "a page opened by another door wears no stale pick"
    assert not got["errs"], got["errs"]


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
