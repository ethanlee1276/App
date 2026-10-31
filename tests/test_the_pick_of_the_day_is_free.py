"""The Pick of the Day is free — the pick, and nothing else from the board.

Ethan, 2026-10-30: "make the picks of the day free. just the pick of the
day. not the best bet or anything like that."

Guarded here:

  * the paywall's split of a card (engine/gate.free_potd): the call, the
    pick on a day it is a bet and its numbers are public; the board's best
    bet on a day the pick sits out is counted and kept back, a declined
    lean never reaches the public copy (its reason can name it), and the
    pick tracked live (`live_potd`) stays a member's;
  * `day_top_pick.json`, the same object promoted, now mixed rather than
    paid whole, carrying every league's card beside the day's top pick
    (`leagues`), each through the same split, and the seal and leak checks
    that must agree with the stripper;
  * two holes found on the way: the NFL's board is dated by week, so its
    card could never be "today's" and the day's top pick never came from
    the NFL; and hockey and the fight card were never ranked at all;
  * the page (js/potd.js): every league's card side by side, a free
    account's Home, wired where every page is — and, in a browser, what a
    reader without a plan and a member each see at a phone's width.

    python3 tests/test_the_pick_of_the_day_is_free.py
    QB_BROWSER_TESTS=1 python3 tests/test_the_pick_of_the_day_is_free.py
"""

import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import gate, potd                                  # noqa: E402

WEB = ROOT / "web"
APP = (WEB / "js" / "app.js").read_text()
PAGE = (WEB / "js" / "potd.js").read_text()
HTML = (WEB / "index.html").read_text()
TODAY = potd.slate_day()


def _fn(name, src=APP):
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 3]


def _pick(**kw):
    row = {"player": "KC", "team": "KC", "opponent": "BUF", "market": "moneyline", "kind": "game",
           "odds": -130, "book": "DraftKings", "sharp_anchored": True, "sharp_fair": 0.60,
           "fair_prob": 0.60, "price_implied": 0.565, "evidence": "sharp", "payout_units": 0.769,
           "below_bar": ""}
    row.update(kw)
    return row


def _bet_card(**kw):
    card = {"sport": "nfl", "date": TODAY, "pick": _pick(), "census": {},
            "verdict": {"call": "bet", "stake": 1.0, "why": "", "book": "DraftKings", "odds": -130}}
    card.update(kw)
    return card


def _lean_card(why="the card’s own model picks Jon Jones", **kw):
    card = {"sport": "ufc", "date": TODAY, "pick": _pick(player="Tom Aspinall ML", below_bar=why),
            "verdict": {"call": "no bet", "stake": 0.0, "why": why},
            "board_best": {"label": "Alex Pereira · Moneyline", "odds": -150, "book": "FanDuel",
                           "stake_units": 1.0, "tonight": True}, "board_staked": 3}
    card.update(kw)
    return card


# --- the paywall's split of a card ---------------------------------------------------
def test_the_card_is_free_and_its_members_half_is_not():
    assert "pick_of_the_day" not in gate.PAID_KEYS
    board = {"date": TODAY, "games": [{"home": "KC"}], "most_likely": [_pick()],
             "pick_of_the_day": _bet_card(board_best={"label": "x"}, board_staked=2)}
    pub = gate.redact(board, "recommendations.json")
    card = pub["pick_of_the_day"]
    assert card["pick"]["player"] == "KC" and card["verdict"]["call"] == "bet"
    assert card["pick"]["fair_prob"] == 0.60, "the card's own numbers are the free card's"
    assert "board_best" not in card and "board_staked" not in card
    assert pub["locked"]["pick_of_the_day.board_best"] == 2, "counted, so the page can say members have one"
    assert pub["most_likely"] == [], "the rest of the board stays paid"
    assert board["pick_of_the_day"]["board_best"], "the members' copy is untouched"


def test_a_declined_lean_never_reaches_the_public_copy():
    pub = gate.redact({"pick_of_the_day": _lean_card()}, "ufc.json")
    card = pub["pick_of_the_day"]
    assert card["pick"] is None
    assert card["verdict"] == {"call": "no bet", "stake": 0.0, "why": gate.LEAN_WHY}
    blob = json.dumps(pub)
    assert "Aspinall" not in blob and "Jon Jones" not in blob, "the lean, or its reason, named"
    assert "Pereira" not in blob, "the board's best bet named"


def test_the_split_holds_at_any_depth_and_the_live_tracker_stays_paid():
    pub = gate.redact({"cfb": {"pick_of_the_day": _lean_card()}, "live_potd": [_pick()],
                       "pick_of_the_day": _bet_card()}, "cfb.json")
    assert pub["cfb"]["pick_of_the_day"]["pick"] is None
    assert pub["live_potd"] == [] and "live_potd" in gate.PAID_KEYS
    assert pub["pick_of_the_day"]["pick"]["player"] == "KC"


def test_the_seal_counts_what_the_split_takes():
    """`unsealed()` reads `_paid_rows`; it has to see a members' half on the
    public path, and nothing once the stripper has run."""
    board = {"pick_of_the_day": _lean_card()}
    assert gate._paid_rows(board, "ufc.json") == 2, "the lean and the board's bet"
    assert gate._paid_rows(gate.redact(board, "ufc.json"), "ufc.json") == 0
    assert gate._paid_rows({"pick_of_the_day": _bet_card()}, "nfl.json") == 0, "a bet is free"


# --- day_top_pick.json --------------------------------------------------------------------
def test_the_days_top_pick_file_is_mixed_now():
    name = "day_top_pick.json"
    assert name not in gate.PAID_FILES and name in gate.MIXED_FILES and name in gate.KNOWN_BOARDS
    top = {"date": TODAY, "pick": _lean_card()["pick"], "sport": "ufc",
           "runners_up": [dict(_pick(), sport="nfl"), dict(_lean_card()["pick"], sport="ufc")],
           "leagues": {"nfl": _bet_card(), "ufc": _lean_card()}, "census": {}}
    pub = gate.redact(top, name)
    assert pub["pick"] is None and pub["sport"] == "" and pub["verdict"]["call"] == "no bet"
    assert [p["player"] for p in pub["runners_up"]] == ["KC"], "the bets it beat, never a lean"
    assert pub["leagues"]["nfl"]["pick"]["player"] == "KC"
    assert pub["leagues"]["ufc"]["pick"] is None and "board_best" not in pub["leagues"]["ufc"]
    assert pub["locked"]["leagues.ufc.board_best"] == 3
    assert gate._paid_rows(top, name) > 0 and gate._paid_rows(pub, name) == 0
    assert gate.leaks(pub, name) == [], "the free runners-up are not the next UFC"
    assert gate.leaks({"runners_up": [{"odds": -110, "hit_prob": .6}], "other": [{"edge": .1}]},
                      name) == ["other"], "only the list named free is excused"


def test_every_leagues_card_rides_beside_the_top_pick():
    tomorrow = (dt.date.fromisoformat(TODAY) + dt.timedelta(days=1)).isoformat()
    boards = {"nfl": {"pick_of_the_day": _bet_card()},
              "mlb": {"pick_of_the_day": _bet_card(sport="mlb", date="2026-08-01")},   # out of season
              "ufc": {"pick_of_the_day": _lean_card(date=tomorrow)},                  # Saturday's card
              "nba": None}
    out = potd.day_top_pick(boards, TODAY)
    assert set(out["leagues"]) == {"nfl", "ufc"}, out["leagues"].keys()
    assert out["leagues"]["ufc"]["board_best"], "the members' file keeps the whole card"


def test_the_nfl_card_dated_by_week_is_todays():
    """The NFL board's `date` is "2026-W08": compared as a day it never
    matched, and the day's top pick could not come from the NFL."""
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    card = _bet_card(date="2026-W08", decided_at=stamp, generated_at=stamp)
    assert potd.card_day(card) == TODAY
    out = potd.day_top_pick({"nfl": {"pick_of_the_day": card}}, TODAY)
    assert out["sport"] == "nfl" and out["pick"]["player"] == "KC", out["census"]
    assert "nfl" in out["leagues"]
    assert potd.card_day({"date": "2026-10-29"}) == "2026-10-29"
    assert potd.card_day({}) == ""


def test_hockey_and_the_fight_card_are_ranked():
    import launch
    assert {"nhl", "ufc"} <= set(potd.TOP_PICK_LEAGUES)
    assert launch.POTD_BOARD_FILES["ufc"] == launch.UFC_OUT
    assert "ufc" not in launch.BOARD_FILES, "the stale-board warnings read that registry; the fight card is not rebuilt every cycle"


# --- the page ------------------------------------------------------------------------------
def test_the_page_is_wired_where_every_page_is():
    wall = APP[APP.index("const WALL_OPEN = ["):APP.index("];", APP.index("const WALL_OPEN = ["))]
    assert '"potd"' in re.sub(r"//[^\n]*", "", wall), "the page is free"
    order = APP[APP.index("const VIEW_ORDER = ["):APP.index("];", APP.index("const VIEW_ORDER = ["))]
    assert '"potd"' in order
    assert 'function renderPotdPage(...a) { return roomCall(renderPotdPage, "renderPotdPage", "js/potd.js", "css/potd.css", a); }' in APP
    assert 'if (name === "potd") renderPotdPage();' in APP
    assert "async function renderPotdPage()" in PAGE
    assert 'id="view-potd"' in HTML and 'id="potd-body"' in HTML and 'id="potd-sub"' in HTML
    assert '"/js/potd.js", "/css/potd.css"' in (WEB / "sw.js").read_text()
    from engine import shrink
    assert "js/potd.js" in shrink.FILES and "css/potd.css" in shrink.FILES
    assert "/js/potd.js /css/potd.css" in (ROOT / "deploy" / "Caddyfile").read_text()
    more = (WEB / "js" / "more.js").read_text()          # the list lives with its page
    assert '"potd"],' in more[more.index("const FEATURES = ["):], "a Features row"
    assert '["The Pick of the Day, every league, with its record", 1]' in (WEB / "js" / "account.js").read_text()


def test_a_free_accounts_home_is_the_free_pick():
    sw = _fn("_switchViewNow")
    assert 'if (name === "recommended" && isWalled()) { name = "potd"; dir = 0; }' in sw
    # Before the wall's own check, so the plans never open over it.
    assert sw.index('name = "potd"') < sw.index("if (wallBlocked(name))")
    sv = _fn("switchView")
    assert sv.index('if (name === "recommended" && isWalled()) name = "potd";') < sv.index("wallBlocked(name)"), \
        "a tab tap asks the wall before the switch does"
    assert 'walled && b.dataset.view !== "recommended"' in _fn("markLockedNav")
    assert '(name === "game" || name === "prop" || name === "potd") ? "recommended"' in sw, "Home stays lit"


def test_it_reads_through_the_entitled_route():
    assert 'paidFetch("day_top_pick.json")' in PAGE
    assert "data/day_top_pick" not in PAGE, "a member would be handed the stranger's copy"


def _render(top, rec, walled):
    stubs = f"""
    const state = {{ sport: "nfl", view: "potd" }};
    const escapeHtml = (s) => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
    const escapeAttr = escapeHtml;
    const icon = () => "", iconMark = () => "";
    const teamNameIn = (sp, t) => t, teamMarkIn = (sp, t) => `<i data-team="${{t}}"></i>`;
    const leagueMark = (s) => "", playerAvatar = (n) => "";
    const american = (o) => (o > 0 ? "+" + o : String(o).replace("-", "−"));
    const plural = (n, w) => `${{n}} ${{w}}${{n === 1 ? "" : "s"}}`;
    const MINUS = "−";
    const SPORT_META = {{ nfl: {{ name: "NFL" }}, ufc: {{ name: "UFC" }}, nba: {{ name: "NBA" }} }};
    const LEAGUE_LABEL = {{}};
    const betItHTML = (p) => `<span class="betit-box">Bet it</span>`;
    const memberLockHTML = (t, b) => `<div class="card member-lock"><b>${{t}}</b><p>${{b}}</p></div>`;
    const tzTime = (d) => "3:00 PM";
    {_fn("potdCallStrip")}
    {_fn("potdBetText")}
    {PAGE}
    console.log(JSON.stringify(pdPageHTML({json.dumps(top)}, {json.dumps(rec)}, {json.dumps(walled)})));
    """
    out = subprocess.run(["node", "-e", stubs], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _top():
    return {"date": TODAY, "generated_at": "2026-10-30T15:00:00Z", "sport": "nfl",
            "pick": dict(_pick(), sport="nfl"), "verdict": {"call": "bet", "stake": 1.0, "why": ""},
            "runners_up": [], "census": {},
            "leagues": {"ufc": _lean_card(), "nfl": _bet_card(),
                        "nba": {"sport": "nba", "date": TODAY, "pick": None, "off_day": True,
                                "note": "NBA picks resume tomorrow."}}}


REC = {"potd": {"wins": 12, "losses": 8, "pushes": 0, "net_units": 3.1, "win_rate": 0.6, "settled": 20, "open": 1},
       "potd_by_sport": {"nfl": {"wins": 5, "losses": 2, "net_units": 2.4, "win_rate": .714, "settled": 7}},
       "potd_days": {"slates": 28, "picked": 17, "by_sport": {"nfl": {"slates": 9, "picked": 6}}}}


def test_a_member_sees_every_leagues_card_and_the_boards_bet():
    html = _render(_top(), REC, False)
    assert html.index(">NFL<") < html.index(">UFC<") < html.index(">NBA<"), "the top pick, then the sat-out, then the day off"
    assert "Top pick today" in html and "KC Moneyline" in html and "Bet it" in html
    assert "Best on the board tonight" in html and "Pereira" in html, "a member's board bet on a NO BET day"
    assert "Aspinall" not in html, "the card refuses its lean for everyone"
    assert "NFL Picks of the Day: 5-2" in html and "a pick on 6 of the last 9 slates" in html
    assert "So far: 12-8" in html and "member-lock" not in html
    assert 'href="#nfl"' in html, "a member's way into the league's board"


def test_a_reader_without_a_plan_sees_the_free_card_and_the_lock():
    html = _render(gate.redact(_top(), "day_top_pick.json"), REC, True)
    assert "KC Moneyline" in html and "Bet it" in html, "the free pick"
    assert "Pereira" not in html and "Best on the board" not in html
    assert "Members see the board’s best bet tonight — one of 3 staked." in html
    assert "member-lock" in html and 'href="#nfl"' not in html
    assert "Aspinall" not in html and "Jon Jones" not in html


def test_a_day_with_no_card_yet_says_so():
    html = _render({"date": TODAY, "leagues": {}, "pick": None}, {}, True)
    assert "No league has named today’s pick yet" in html


# --- in a browser ------------------------------------------------------------------------
def _browser():
    from playwright.sync_api import sync_playwright
    import rendercheck
    full = _top()
    srv, port = rendercheck._serve()
    got, errs = {}, []
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                for who, width in (("free", 390), ("member", 1280)):
                    ctx = browser.new_context(viewport={"width": width, "height": 844}, service_workers="block",
                                              is_mobile=width < 500, has_touch=width < 500)
                    page = ctx.new_page()
                    page.on("pageerror", lambda e: errs.append(str(e)))

                    def ok(text, status=200):
                        return lambda r, *_: r.fulfill(status=status, content_type="application/json", body=text)
                    me = {"signed_in": True, "email": "you@example.com", "profile": {"handle": "reader", "color": 1}}
                    bill = {"signed_in": True, "email": "you@example.com", "paywall": True,
                            "entitled": who == "member", "plans": []}
                    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    page.route("**/api/**", ok("{}"))
                    page.route("**/api/account/me*", ok(json.dumps(me)))
                    page.route("**/api/billing/status*", ok(json.dumps(bill)))
                    page.route("**/api/feed/**", ok(json.dumps({"posts": []})))
                    page.route("**/api/board/day_top_pick.json",
                               ok(json.dumps(full)) if who == "member" else ok("{}", 402))
                    page.route("**/data/day_top_pick.json", ok(json.dumps(gate.redact(full, "day_top_pick.json"))))
                    page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb.tour','done');}catch(e){}")
                    page.goto(f"http://127.0.0.1:{port}/index.html#live", wait_until="load")
                    page.wait_for_timeout(3000)
                    if who == "free":
                        page.evaluate("document.querySelector('.tabbar .nav-btn[data-view=\"recommended\"]').click()")
                    else:
                        page.evaluate("location.hash = '#potd'")
                    page.wait_for_timeout(2500)
                    got[who] = page.evaluate("""() => ({
                        view: state.view, walled: document.body.classList.contains('walled'),
                        homeLocked: !!document.querySelector('.tabbar .nav-btn[data-view="recommended"].nav-locked'),
                        text: document.getElementById('potd-body').innerText,
                        cards: document.querySelectorAll('#potd-body .pd-card').length,
                        lock: !!document.querySelector('#potd-body .member-lock'),
                        wide: document.documentElement.scrollWidth > window.innerWidth + 1})""")
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    return got, errs


def test_in_a_browser_a_free_home_opens_the_free_pick_and_a_member_sees_every_card():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("skip: set QB_BROWSER_TESTS=1")
        return
    got, errs = _browser()
    assert not errs, errs
    free, mem = got["free"], got["member"]
    assert free["walled"] and free["view"] == "potd", free
    assert not free["homeLocked"], "Home is the free pick's door"
    assert free["cards"] == 3 and free["lock"] and not free["wide"], free
    assert "Chiefs Moneyline" in free["text"] and "Best on the board" not in free["text"]
    assert not mem["walled"] and mem["view"] == "potd" and mem["cards"] == 3 and not mem["lock"], mem
    assert "Best on the board tonight" in mem["text"] and not mem["wide"]


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
