"""The Best Parlays page: every report parlay ranked best to worst (step AAL, 21 November).

Ethan, 2026-11-21: "Add a feature where it takes the best two leg and three leg
parlays for each sport and ranks them like how we rank the most likely picks for
the best parlays to the worst parlays to pick. I want that on a separate page and
I want player prop parlays and touchdown parlays to have their own separate
sections for users to scroll through and look through".

engine/gameparlays.rank_parlays ranks each board's posted tickets across its games,
a list a kind (two-leg, three-leg, scorer pairs), in the Most Likely board's tiers
from each ticket's checks, then our chance (a football pair's research first);
js/bestparlays.js draws it on its own page, a section for the player-prop parlays
and one for the touchdown (goal-scorer) pairs. Members only, as the reports are.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gameparlays as GP          # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
HTML = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
PAGE = (ROOT / "web" / "js" / "bestparlays.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "bestparlays.css").read_text(encoding="utf-8")


def _t(joint, cls="balanced", book=True, filled=False, playable=True, caveats=(), legs=2, p=0.66, research=None):
    t = {"joint": joint, "class": cls, "filled": filled, "playable": playable, "caveats": list(caveats),
         "legs": [{"player": f"P{i}", "market": "receptions", "side": "OVER", "line": 4.5, "p": p,
                   **({"research": research} if research is not None else {})} for i in range(legs)]}
    if book is True:
        t["one_book"] = {"book": "DraftKings", "words": "One book has every leg: DraftKings"}
    elif book is False:
        t["one_book"] = {"none": True, "words": "No one book in our pull has both legs at these numbers"}
    elif book == "gone":
        t["one_book"] = {"gone": True, "words": "Can't be placed as written now"}
    return t


def _gp(games):
    return {"sport": "nfl", "games": [dict(x, away=a, home=h) for (a, h), x in games]}


def test_the_tiers_are_most_likelys_from_the_checks():
    assert GP.rank_tier({"class2": True, "book": True, "own": True, "price": True, "together": True}) == "top"
    assert GP.rank_tier({"class2": True, "book": None, "own": True, "price": None, "together": True}) == "top", \
        "a check that cannot say is not against it"
    assert GP.rank_tier({"class2": True, "book": False, "own": True, "price": True, "together": True}) == "strong"
    assert GP.rank_tier({"class2": False, "book": False, "own": True, "price": True, "together": True}) == "look"
    two = GP.rank_checks(_t(0.45), "twos", "nfl")
    assert two == {"class2": True, "book": True, "own": True, "price": True, "together": True}
    # A three-leg ticket is Pop by v3.1's own targets: the class check passes on Pop, not on a long shot.
    assert GP.rank_checks(_t(0.27, cls="pop", legs=3), "threes", "nfl")["class"] is True
    assert GP.rank_checks(_t(0.17, cls="long", legs=3), "threes", "nfl")["class"] is False
    assert GP.rank_checks(_t(0.27, cls="pop"), "twos", "nfl")["class2"] is False, "a two-leg Pop is not Safe or Balanced"
    apart = GP.rank_checks(_t(0.45, caveats=[GP.APART_NOTE]), "twos", "nfl")
    assert apart["together"] is False
    # Scorer pairs: football's touchdown rule a scorer, no stand-in; hockey's pair at its floor.
    td = GP.rank_checks({"joint": 0.19, "legs": [{"p": 0.45}, {"p": 0.41}]}, "scorers", "nfl")
    assert td == {"rule": True, "stand_in": True, "together": True}
    assert GP.rank_checks({"joint": 0.15, "legs": [{"p": 0.45}, {"p": 0.33}]}, "scorers", "nfl")["rule"] is False
    assert GP.rank_checks({"joint": 0.26, "legs": [{"p": 0.5}, {"p": 0.52}], "stand_ins": 1}, "scorers", "nhl") == \
        {"floor": True, "stand_in": False, "together": True}


def test_the_ranking_is_tier_first_then_our_chance_across_every_game():
    gp = _gp([(("DAL", "PHI"), {"twos": [_t(0.52, book=False), _t(0.44)], "threes": [_t(0.28, cls="pop", legs=3)]}),
              (("KC", "BUF"), {"twos": [_t(0.47), _t(0.61, cls="long", book=False, playable=False)],
                               "threes": [_t(0.31, cls="pop", legs=3, filled=True)]})])
    r = GP.rank_parlays(gp, "nfl")
    got = [(e["game"], e["i"], e["tier"], e["rank"]) for e in r["twos"]]
    assert got == [("KC@BUF", 0, "top", 1), ("DAL@PHI", 1, "top", 2), ("DAL@PHI", 0, "strong", 3), ("KC@BUF", 1, "look", 4)], got
    assert r["twos"][2]["against"] == ["book"] and set(r["twos"][3]["against"]) == {"class2", "book", "price"}
    # A three-leg ticket with a fill leg is Strong behind a Top one, whatever its chance.
    assert [(e["game"], e["tier"]) for e in r["threes"]] == [("DAL@PHI", "top"), ("KC@BUF", "strong")]
    assert r["threes"][1]["against"] == ["own"]
    assert r["left_off"] == {"gone": 0, "started": 0}
    assert [e["gi"] for e in r["threes"]] == [0, 1], "each names its game's entry"


def test_a_doubleheaders_two_games_keep_their_own_tickets():
    # Two games between the same clubs on one day share "AWAY@HOME": each ranked ticket names its own entry
    # (`gi`), and the page reads that entry and the board's game at the same kickoff.
    gp = _gp([(("NYY", "BOS"), {"twos": [_t(0.41)], "date": "2026-07-04", "kickoff": "13:05"}),
              (("NYY", "BOS"), {"twos": [_t(0.52)], "date": "2026-07-04", "kickoff": "19:10"})])
    r = GP.rank_parlays(gp, "mlb")
    assert [(e["game"], e["gi"], e["i"], e["joint"]) for e in r["twos"]] == [("NYY@BOS", 1, 0, 0.52), ("NYY@BOS", 0, 0, 0.41)]
    assert "const at = games[e.gi];" in PAGE and "return at && `${at.away}@${at.home}` === e.game ? at" in PAGE
    assert "(!x.kickoff || g.kickoff === x.kickoff)" in PAGE and "const g = bpGame(d, e.game, x);" in PAGE


def test_football_pairs_rank_on_research_inside_a_tier_and_the_unplaceable_and_started_are_left_off():
    pairs = [{"joint": 0.20, "legs": [{"p": 0.45, "research": 4}, {"p": 0.44, "research": 3}]},
             {"joint": 0.17, "legs": [{"p": 0.42, "research": 6}, {"p": 0.41, "research": 5}]}]
    gp = _gp([(("DAL", "PHI"), {"scorers": pairs, "twos": [_t(0.5, book="gone")]}),
              (("KC", "BUF"), {"scorers": [dict(pairs[0])], "kept": True})])
    r = GP.rank_parlays(gp, "nfl")
    assert [(e["i"], e["joint"]) for e in r["scorers"]] == [(1, 0.17), (0, 0.2)], "11 research points ahead of 7"
    assert r["twos"] == [] and r["left_off"] == {"gone": 1, "started": 1}
    # Hockey has no research: our chance orders its pairs.
    r = GP.rank_parlays(_gp([(("BOS", "NYR"), {"scorers": pairs})]), "nhl")
    assert [e["i"] for e in r["scorers"]] == [0, 1]


def test_the_board_carries_it_inside_its_paid_parlays_after_the_reports():
    src = (ROOT / "engine" / "gameparlays.py").read_text(encoding="utf-8")
    attach = src[src.index("def attach(board: dict, sport: str)"):src.index("def for_game(")]
    assert "attach_ranked(board, sport)" in attach
    report = src[src.index("def report_only(board: dict)"):src.index("def summary(gp: dict)")]
    assert 'attach_ranked(board, str(gp.get("sport") or ""))' in report, "ranked again on the tickets the reports posted"
    from engine import gate
    assert "game_parlays" in gate.PAID_KEYS, "the ranking rides in the members' parlays"
    # On the shared fixture board: every posted ticket ranked, numbered from one.
    EG = __import__("test_each_game_gets_its_parlays")
    b = EG.board()
    b["game_parlays"] = GP.build(b, "nfl")
    GP.attach_ranked(b, "nfl")
    r = b["game_parlays"]["ranked"]
    for kind in GP.RANK_KINDS:
        n = sum(len(x.get(kind) or []) for x in b["game_parlays"]["games"])
        assert len(r[kind]) == n and [e["rank"] for e in r[kind]] == list(range(1, n + 1)), kind


def _counts(b):
    import launch as L
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "b.json")
        with open(path, "w") as fh:
            json.dump(b, fh)
        was = L._full_copy
        L._full_copy = lambda p: p
        try:
            return L._board_counts(path)
        finally:
            L._full_copy = was


def test_the_heartbeat_counts_the_tiers_and_never_a_ticket():
    # The live check's eyes on a members-only list: each kind's tickets by tier, counts only.
    EG = __import__("test_each_game_gets_its_parlays")
    b = EG.board()
    b["game_parlays"] = GP.build(b, "nfl")
    GP.attach_ranked(b, "nfl")
    want: dict = {}
    for kind in GP.RANK_KINDS:
        for e in b["game_parlays"]["ranked"][kind]:
            want.setdefault(kind, {}).setdefault(e["tier"], 0)
            want[kind][e["tier"]] += 1
    got = _counts(b)
    assert want and got["ranked_tiers"] == want, got.get("ranked_tiers")
    assert all(isinstance(n, int) for cell in got["ranked_tiers"].values() for n in cell.values())
    assert "ranked_left_off" not in got and "ranked_error" not in got
    # A failed ranking is counted by its kind of error only.
    b["game_parlays"]["ranked"] = {"twos": [], "threes": [], "scorers": [], "left_off": {"gone": 1, "started": 0},
                                   "error": "TypeError: bad thing"}
    got = _counts(b)
    assert got["ranked_error"] == "TypeError" and got["ranked_tiers"] == {}
    assert got["ranked_left_off"] == {"gone": 1, "started": 0}


def test_the_page_is_its_own_with_two_sections_and_most_likelys_tiers():
    # Its own page, in the menu beside Report Picks, opened by an old #parlays link.
    assert 'data-view="bestparlays" id="bestparlays-tab"' in HTML and 'id="view-bestparlays"' in HTML
    assert '<div id="bestparlays-body"></div>' in HTML
    assert ('function renderBestParlays(...a) { return roomCall(renderBestParlays, "renderBestParlays", '
            '"js/bestparlays.js", "css/bestparlays.css", a); }') in APP
    assert 'if (name === "bestparlays") renderBestParlays();' in APP
    assert 'const MOVED_VIEWS = { parlays: "bestparlays" };' in APP
    assert '"view:reportpicks", "view:bestparlays"' in APP
    for lst in ("const BOARD_VIEWS = [", "const VIEW_ORDER = [", "const SWIPE_VIEWS = ["):
        i = APP.index(lst)
        assert '"bestparlays"' in APP[i:APP.index("]", i)], lst
    # Two sections, as asked: the player-prop parlays (two-leg and three-leg each ranked) and the pairs.
    assert '["props", "Player prop parlays", "Two-leg and three-leg tickets", props]' in PAGE
    assert '["scorers", pairTitle, pairHint, scorers]' in PAGE
    assert '["nfl", "cfb"].includes(sport) ? ["Touchdown parlays", "touchdown pair", "Two players, each to score a touchdown"]' in PAGE
    assert 'sport === "nhl" ? ["Goal-scorer parlays", "goal-scorer pair", "Two players, each to score a goal"]' in PAGE
    assert 'const BP_TIERS = [["top", "Top parlays"' in PAGE and '["strong", "Strong"' in PAGE and '["look", "Worth a look"' in PAGE
    # Members only, as the reports' parlays are; a started game leaves the list.
    assert "if (d.locked && d.locked.game_parlays) {" in PAGE and "memberLockHTML(" in PAGE
    assert "if (!t || (t.legs || []).length < 2 || bpStarted(g)) return;" in PAGE
    # Every check against a ticket has its words, the engine's keys.
    for k in GP.RANK_AGAINST:
        assert f"  {k}: " in PAGE, k
    for sel in (".bp-card", ".bp-rank", ".bp-tier", ".bp-legs", ".bp-size", ".bp-chip"):
        assert sel in CSS, sel


def test_each_card_wears_the_reports_bet_it_button():
    # Ethan, 2026-11-15: "add bet it buttons that adds the whole parlay too your sports book. Both td parlays
    # and player prop parlays". The card's button is the report's own (js/report.js parlayBet), so the sheet,
    # its one-slip tile and its leg-by-leg tiles are the same everywhere a parlay is drawn.
    report = (ROOT / "web" / "js" / "report.js").read_text(encoding="utf-8")
    assert "liveTickets, liveGame, parlayBet };" in report
    assert '<span class="bp-bet" data-bp-bet="${_bpBet.push({ legs: t.legs || [],' in PAGE
    assert "if (_bpBet.length && typeof loadReport === \"function\") loadReport().then((R) => {" in PAGE
    assert "el.outerHTML = b ? R.parlayBet(b.legs, b.what) || \"\" : \"\";" in PAGE


def test_in_a_browser_the_page_ranks_both_sections():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import copy
    import rendercheck
    EG = __import__("test_each_game_gets_its_parlays")
    board = EG.board()
    board["game_parlays"] = GP.build(board, "nfl")
    base = board["game_parlays"]["games"][0]
    for a, h in (("DAL", "PHI"), ("KC", "BUF")):
        x = copy.deepcopy(base)
        x["away"], x["home"] = a, h
        board["game_parlays"]["games"].append(x)
        g = copy.deepcopy(board["games"][0])
        g["away"], g["home"] = a, h
        board["games"].append(g)
    GP.attach_ranked(board, "nfl")
    board.pop("locked", None)
    want = {k: len(board["game_parlays"]["ranked"][k]) for k in GP.RANK_KINDS}
    body = json.dumps(board)
    srv, port = rendercheck._serve()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
            try:
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                          service_workers="block")
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                base_url = f"http://127.0.0.1:{port}/"

                def route(r):
                    u = r.request.url
                    if not u.startswith(base_url):
                        return r.abort()
                    if "recommendations" in u and (".json" in u or "/api/recommendations" in u):
                        return r.fulfill(status=200, content_type="application/json", body=body)
                    return r.continue_()
                page.route("**/*", route)
                page.goto(f"{base_url}index.html?sport=nfl#parlays", wait_until="load")
                for _ in range(200):
                    if page.evaluate("document.querySelectorAll('#bestparlays-body .bp-card').length > 0"):
                        break
                    page.wait_for_timeout(100)
                got = page.evaluate("""() => ({ hash: location.hash, active: (document.querySelector('.view.active') || {}).id,
                  tabs: [...document.querySelectorAll('#bestparlays-body .subnav-btn')].map((b) => b.dataset.subtab),
                  sizes: [...document.querySelectorAll('#bestparlays-body [data-bp-size]')].map((b) => b.dataset.bpSize),
                  shown: [...document.querySelectorAll('#bestparlays-body [data-subgroup="props"] .bp-card')].length,
                  ranks: [...document.querySelectorAll('#bestparlays-body [data-subgroup="props"] .bp-rank')].map((b) => +b.textContent),
                  pairs: [...document.querySelectorAll('#bestparlays-body [data-subgroup="scorers"] .bp-card')].length,
                  wide: document.documentElement.scrollWidth })""")
                assert got["hash"] == "#bestparlays" and got["active"] == "view-bestparlays", got
                assert got["tabs"] == ["props", "scorers"] and got["sizes"] == ["twos", "threes"], got
                assert got["shown"] == want["twos"] and got["ranks"] == list(range(1, want["twos"] + 1)), (got, want)
                assert got["pairs"] == want["scorers"] and got["wide"] <= 390, got
                page.click('#bestparlays-body [data-bp-size="threes"]')
                page.wait_for_timeout(300)
                n3 = page.evaluate("document.querySelectorAll('#bestparlays-body [data-subgroup=\"props\"] .bp-card').length")
                assert n3 == want["threes"], (n3, want)
                assert not errors, errors
            finally:
                browser.close()
    finally:
        srv.shutdown()


def test_in_a_browser_a_cards_bet_it_puts_the_whole_ticket_on_one_slip():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    BW = __import__("test_a_parlay_is_bet_whole")
    payload, _ = BW._stamped()                     # the legs with each book's links, as the board stamps them
    board = {"sport": "nfl", "date": "2026-11-15", "recommendations": [], "most_likely": [],
             "games": [{"home": "BUF", "away": "LAC", "date": "2026-11-15", "kickoff": "13:00"}],
             "game_parlays": payload["game_parlays"]}
    GP.attach_ranked(board, "nfl")
    body = json.dumps(board)
    srv, port = rendercheck._serve()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
            try:
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                          service_workers="block", bypass_csp=True)
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)[:300]))
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                for pat in ("**/api/recommendations*", "**/data/recommendations*.json*"):
                    page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=body))
                page.goto(f"http://127.0.0.1:{port}/#bestparlays", wait_until="load")
                page.wait_for_function("document.querySelectorAll('#bestparlays-body .bp-card .gr-betit .betit').length >= 2",
                                       timeout=20000)
                # The three-leg ticket's card (no two-leg tickets here, so the page opens on three), then its sheet.
                page.click('#bestparlays-body [data-subgroup="props"] .bp-card .gr-betit .betit')
                page.wait_for_function("document.body.classList.contains('betit-open')", timeout=5000)
                tiles = page.evaluate("""[...document.querySelectorAll('#betit-sheet .bk-tile')].map((a) => ({
                    href: a.getAttribute('href'), text: a.textContent.replace(/\\s+/g, ' ').trim()}))""")
                whole = [t for t in tiles if "one slip" in t["text"]]
                assert len(whole) == 1 and "marketId[2]=734.3" in whole[0]["href"], tiles
                assert sum(1 for t in tiles if "Leg " in t["text"]) == 3, tiles
                head = page.inner_text("#betit-sheet .betit-head")
                assert head.startswith("Bet it") and "Three-leg parlay · Josh Allen over 249.5 passing yards" in head, head
                # The touchdown pair's card wears one too.
                pairs = page.evaluate("document.querySelectorAll('#bestparlays-body [data-subgroup=\"scorers\"] .bp-card .betit').length")
                assert pairs == 1, pairs
                assert not errors, errors
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    fails = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as exc:                              # noqa: BLE001
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed.")
    sys.exit(1 if fails else 0)
