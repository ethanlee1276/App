"""Basketball's Most Likely picks reach the page (the NBA page and Most Likely).

Ethan, 2026-11-04: "we still don't have any most likely picks showing on
the NBA page or the most likely page." The board carried 92 of them that
morning, journaled and graded every day (1,087 settled, 65.7%), and the
page drew none: its shrink check read `engine_raw_prob: null` as a claim
of 0% — `Number(null)` is 0, and 0 is finite — sat 58 points from the
book, and hid every NBA (and NHL) pick as an artefact. Their pipelines
hand the board no pre-shrink claim; the engine has always read a missing
claim as no claim. What these hold:

  * a missing claim (null, absent, "") is no claim, and never a reason to
    hide a row; a real one past the bar still is;
  * the page lets past exactly the rows the engine's own bar does
    (`likely.engine_credible`), every combination of source, rung, find
    and claim — the market's number, a sharp or anchored rung, a real find;
  * an NBA pick as the engine writes it is shown;
  * a board that HAS picks the page did not draw says so — under way and
    on Live, or held back by this page, which is a fault to report —
    instead of blaming a quiet slate;
  * the home's Top picks draws the one board even with no shelf;
  * in a browser, the NBA page and the Most Likely page show the picks.

Run directly: `python3 tests/test_basketball_most_likely_reaches_the_page.py`
(the browser check with QB_BROWSER_TESTS=1 and /usr/bin/python3).
"""
import itertools
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

from engine import likely as L                           # noqa: E402

JS = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")


def _fn(name):
    """One top-level function's source, by brace balance (the name is
    matched with its parenthesis, so a longer name sharing the prefix is
    never taken for it)."""
    i = JS.index(f"function {name}(")
    depth, j = 0, JS.index("{", i)
    for k in range(j, len(JS)):
        if JS[k] == "{":
            depth += 1
        elif JS[k] == "}":
            depth -= 1
            if depth == 0:
                return JS[i:k + 1]
    raise AssertionError(f"{name} never closes")


def _const(name):
    i = JS.index(f"const {name} = ")
    return JS[i:JS.index(";\n", i) + 2]


def _node(body, extra=""):
    node = shutil.which("node")
    if not node:
        print("      (skipped: no node)")
        return None
    prog = "\n".join([_const("MAX_CREDIBLE_EDGE"), _const("LIKELY_HEAVIEST_PRICE"),
                      _fn("shrinkArtefact"), _fn("rawBarExempt"), _fn("showableLikelyRow"), extra,
                      f"console.log(JSON.stringify((() => {{ {body} }})()));"])
    path = os.path.join(tempfile.mkdtemp(prefix="nbaml-"), "t.js")
    Path(path).write_text(prog, encoding="utf-8")
    out = subprocess.run([node, path], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


# --- the rule ---------------------------------------------------------------------
def test_no_claim_is_not_a_claim_of_zero():
    got = _node("""
      return {
        nul: shrinkArtefact({ raw_prob: null, fair_prob: 0.58 }),
        absent: shrinkArtefact({ fair_prob: 0.58 }),
        blank: shrinkArtefact({ raw_prob: "", fair_prob: 0.58 }),
        noFair: shrinkArtefact({ raw_prob: 0.30, fair_prob: null }),
        far: shrinkArtefact({ raw_prob: 0.30, fair_prob: 0.58 }),
        near: shrinkArtefact({ raw_prob: 0.62, fair_prob: 0.58 }),
        zero: shrinkArtefact({ raw_prob: 0, fair_prob: 0.58 }),
      };
    """)
    if got is None:
        return
    assert got["nul"] is False and got["absent"] is False and got["blank"] is False, got
    assert got["noFair"] is False, got
    assert got["far"] is True and got["near"] is False, "a real claim past the bar is still caught"
    assert got["zero"] is True, "a real claim of 0% is a claim"


def test_the_page_lets_past_exactly_what_the_engine_does():
    cases = []
    for src, rung, bold, raw in itertools.product(
            ("model", "mixture", "market", "sharp", "anchored"), ("main", "alt"),
            (False, True), (None, 0.62, 0.30)):
        cases.append({"prob_source": src, "rung": rung, "bold": bold,
                      "engine_raw_prob": raw, "fair_prob": 0.58, "odds": -140})
    cases.append({"prob_source": "model", "rung": "main", "engine_raw_prob": 0.30, "fair_prob": None, "odds": -140})
    got = _node(f"return {json.dumps(cases)}.map((r) => showableLikelyRow(r));")
    if got is None:
        return
    # The engine's bar as `likely.admissible` applies it: `engine_credible`,
    # or a real find, which stands past it.
    want = [L.engine_credible(c) or bool(c.get("bold")) for c in cases]
    bad = [(c, g, w) for c, g, w in zip(cases, got, want) if g != w]
    assert not bad, f"the page and the engine disagree on {len(bad)} row(s): {bad[:3]}"
    # Both answers occur, so the table proves the bar and not only its exemptions.
    assert True in want and False in want


def test_the_price_cap_and_the_lock_still_stand():
    got = _node("""
      const base = { prob_source: "model", engine_raw_prob: null, fair_prob: 0.58 };
      return { chalk: showableLikelyRow({ ...base, odds: -300 }),
               ok: showableLikelyRow({ ...base, odds: -250 }),
               lockedFar: showableLikelyRow({ ...base, engine_raw_prob: 0.30, odds: -140, locked: true }) };
    """)
    if got is None:
        return
    assert got["chalk"] is False and got["ok"] is True and got["lockedFar"] is True, got


def test_an_nba_pick_as_the_engine_writes_it_is_shown():
    from engine.hoops import NBA
    from engine.nba import pipeline as NP
    prop = {"player": "A Guard", "market": "pts", "minutes": [34, 35, 33, 36, 34, 32, 35, 34],
            "values": [24, 28, 22, 30, 26, 25, 27, 23], "is_starter": True, "spread": -4.0,
            "is_favorite": True, "rest": "1day", "game_total": 232.0, "days_off": 1, "dvp_mult": 1.04,
            "dvp_note": "Matchup: BOS allow 118.0 points a game", "line": 25.5, "over_odds": -110,
            "under_odds": -110, "book": "dk", "opponent": "BOS", "team": "NYK"}
    rec = NP.shared_recommendations([prop], tune=NBA)[0]
    assert "raw_prob" not in rec, "the NBA pipeline began carrying a pre-shrink claim: re-read this test"
    row = L._row_from(rec, rec["market"], "nba", lambda m: True, rec["hit_prob"],
                      shown=0.64, source="model")
    assert row["engine_raw_prob"] is None and '"engine_raw_prob": null' in json.dumps(row)
    assert L.engine_credible(row), "the engine posts it"
    got = _node(f"return showableLikelyRow({json.dumps(dict(row, odds=-150))});")
    if got is None:
        return
    assert got is True, "the page shows what the engine posted"


# --- a board with picks the page did not draw ----------------------------------------
def _hidden_why(board, started=()):
    extra = ("const rowStarted = (r) => " + json.dumps(list(started)) + ".includes(r.player);\n"
             + _fn("pluralWord") + "\n" + _fn("plural") + "\n" + _fn("likelyHiddenWhy"))
    return _node(f"return likelyHiddenWhy({json.dumps(board)});", extra)


def test_the_empty_state_says_when_the_page_held_picks_back():
    rows = [{"player": p} for p in ("A", "B", "C")]
    none = _hidden_why({"most_likely": []})
    if none is None:
        return
    assert none == "", "no pick at all: the census sentence stands"
    held = _hidden_why({"most_likely": rows})
    assert "board has 3 picks" in held and "could not show\n    any of them" in held, held
    assert "fault on our side" in held, held
    some = _hidden_why({"most_likely": rows}, started=("A",))
    assert "2 of them" in some and "(1 more under way)" in some, some
    gone = _hidden_why({"most_likely": rows}, started=("A", "B", "C"))
    assert "3 picks are under way" in gone and "Live tab" in gone and "fault" not in gone, gone


def test_both_empty_states_read_it_first():
    top, page = _fn("renderLikelyTop"), _fn("renderLikely")
    assert "likelyHiddenWhy(state.data) || likelyEmptyWhy(state.data.likely_census, state.data)" in top
    assert "const hiddenWhy = likelyHiddenWhy(state.data);" in page
    assert "${hiddenWhy || likelyEmptyWhy(state.data.likely_census, state.data)}" in page


def test_the_home_draws_the_one_board_with_no_shelf():
    top = _fn("renderLikelyTop")
    assert "if (!shelves.length && !dropped.length && !(oneBoardOn() && oneBoardRows().length)) {" in top


# --- in a browser -------------------------------------------------------------------------
def _board(kickoff="2099-11-05T00:00Z"):
    """An NBA board as the build writes it: rows with no kickoff, no game
    date and no pre-shrink claim, their one board built by the engine."""
    from engine import likelyboard as LB
    games = [{"home": h, "away": a, "date": "2099-11-04", "kickoff": kickoff, "live": None}
             for h, a in (("DET", "PHI"), ("NYK", "BOS"), ("MIA", "CHI"))]
    rows = []
    for i, g in enumerate(games):
        for j, (mk, side) in enumerate((("reb", "UNDER"), ("ast", "UNDER"), ("blk", "OVER"))):
            rec = {"player": f"Player {i}{j}", "team": g["home"], "opponent": g["away"], "market": mk,
                   "market_label": mk, "side": side, "line": 5.5, "odds": -140, "book": "DraftKings",
                   "hit_prob": 0.64, "fair_prob": 0.58, "projection": 4.0, "reasons": ["because"],
                   "recent_values": [3, 4, 2, 5], "injury_status": ""}
            rows.append(L._row_from(rec, mk, "nba", lambda m: True, 0.64, shown=0.64, source="model"))
    lb = LB.build({"most_likely": rows, "games": games, "recommendations": [], "scan_reads": {}},
                  record={}, sport="nba", band_verdict=None)
    return {"sport": "nba", "date": "2099-11-04", "generated_at": "2099-11-04T07:00:00",
            "recommendations": [], "most_likely": rows, "likely_board": lb, "games": games,
            "board_shelves": [{"key": "likely", "title": "Most likely", "rows": rows}],
            "likely_census": {"under the likelihood floor": 3}, "player_stats": {}}


def _fulfil(body):
    # One argument: Playwright hands a two-argument handler the request too.
    return lambda route: route.fulfill(status=200, content_type="application/json", body=body)


def test_in_a_browser_the_nba_page_and_most_likely_show_the_picks():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    got = {}
    srv, port = rendercheck._serve()
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                for case, board in (("tonight", _board()), ("under way", _board("2020-01-01T00:00Z"))):
                    body = json.dumps(board)
                    for view in ("likely", "home"):
                        ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True,
                                                  has_touch=True, service_workers="block")
                        page = ctx.new_page()
                        page.add_init_script("try { localStorage.setItem('qb-seen-intro', '1');"
                                             " localStorage.setItem('qb_intro_v1', '1');"
                                             " localStorage.setItem('qb.tour', 'done'); } catch (e) {}")
                        page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                        page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json",
                                                                    body="{}"))
                        for pat in ("**/api/nba/recommendations*", "**/data/nba.json*", "**/api/board/nba.json*"):
                            page.route(pat, _fulfil(body))
                        page.goto(f"http://127.0.0.1:{port}/index.html?sport=nba#{view}", wait_until="load")
                        sel = "#likely-board .ob-card, #likely-note .es-sub" if view == "likely" \
                            else "#likely-top .ob-card, #likely-top .ls-note"
                        page.wait_for_selector(sel, timeout=30000)
                        got[(case, view)] = page.evaluate("""(view) => {
                          const host = document.getElementById(view === 'likely' ? 'likely-board' : 'likely-top');
                          const note = document.getElementById(view === 'likely' ? 'likely-note' : 'likely-top');
                          return { cards: host ? host.querySelectorAll('.ob-card').length : 0,
                                   text: (note && note.innerText) || '' };
                        }""", view)
                        ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert got[("tonight", "likely")]["cards"] >= 9, got[("tonight", "likely")]
    assert got[("tonight", "home")]["cards"] >= 1, got[("tonight", "home")]
    for view in ("likely", "home"):
        g = got[("under way", view)]
        assert g["cards"] == 0 and "under way" in g["text"] and "Live tab" in g["text"], (view, g)
        assert "no row could be priced" not in g["text"], "a board with picks does not blame the slate"


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
