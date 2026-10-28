"""The Under pressure card says one thing to a line (Ethan, 2026-10-28, a live
Brewers–Rays play-by-play page with the card's head circled: "the wording
is getting cluttered").

The title wrapped onto two lines beside "LIVE" run into the season note
("LIVE2026 · one-score means within 1 run"); a pill said "one-score game"
over a sentence that said the scores; the records broke at their hyphens
("113- / 70"); and the footnote, full size, spoke of "every pass of the
fast loop".

What these hold:

  * the head holds the title and LIVE and nothing else, and the season and
    what one-score means sit on a quiet line under it, on the play-by-play
    page and the game page alike;
  * the state of the game leads the sentence instead of a pill above it;
  * a club stands over its record, and the record no longer breaks;
  * the footnote is small and says only what the gold marks, when anything
    is marked;
  * in a browser at an iPhone's width: the head is one line, the season line
    is smaller than the title, no record wraps, the footnote is small.

Run directly: `python3 tests/test_the_under_pressure_card_reads_cleanly.py`
(the browser check with QB_BROWSER_TESTS=1 and /usr/bin/python3).
"""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

DETAIL = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
DETAIL_CSS = (ROOT / "web" / "css" / "detail.css").read_text(encoding="utf-8")


def _fn(name: str) -> str:
    i = DETAIL.index(f"function {name}(")
    return DETAIL[i:DETAIL.index("\n}\n", i) + 2]


def test_the_head_is_the_title_and_live_and_the_season_sits_under_it():
    card = _fn("pbpPressureHTML")
    head = card[card.index('<div class="pbp-rail-head">'):card.index("</div>", card.index('<div class="pbp-rail-head">'))]
    assert "Under pressure" in head and "LIVE" in head and 'class="mini"' not in head, head
    assert ('<p class="pbp-pr-sub">${escapeHtml(String(pr.season_used))} season · one-score means within ${') in card
    pair = _fn("pressurePairHTML")
    assert '<div class="gp-panel-title">Under pressure</div>' in pair, "the game page's card, the same way"
    assert '<p class="pbp-pr-sub">${escapeHtml(String(pr.season_used))} season · one-score means within ${' in pair


def test_the_state_leads_the_sentence_and_no_pill_says_it_again():
    card = _fn("pbpPressureHTML")
    assert "pbp-pr-chips" not in card and "pbp-pr-chips" not in DETAIL_CSS, "the pills are gone"
    assert '<p class="pbp-pr-line">${m.state ? `<b>${escapeHtml(m.state)}</b> · ` : ""}${escapeHtml(m.line)}</p>' in card
    moment = _fn("pressureMoment")
    assert "const said = (F && D && lead && lead !== fav && F.reliability != null) || (one && late);" in moment


def test_a_club_stands_over_its_record_and_the_footnote_is_small():
    for name in ("pbpPressureHTML", "pressurePairHTML"):
        assert '<span class="pr-tm">${' in _fn(name), name
    assert ".pr-table .pr-tm { display: grid; line-height: var(--lh-tight); }" in DETAIL_CSS
    assert ".pr-table .pr-tm .k { font-size: var(--fs-2xs); white-space: nowrap; }" in DETAIL_CSS
    card = _fn("pbpPressureHTML")
    assert "every pass of the fast loop" not in card and 'style="opacity:.6"' not in card, \
        "the footnote in plain words, styled by its class"
    assert '<p class="pbp-pr-foot">From ${escapeHtml(String(pr.season_used))}’s finished games${' in card
    assert ".pbp-pr-foot { margin: 10px 0 0; color: var(--text-mute); font-size: var(--fs-xs);" in DETAIL_CSS


def test_in_a_browser_the_card_reads_one_thing_to_a_line():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    import test_the_live_trackers as T
    gen = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    live = {"state": "live", "home_score": 2, "away_score": 1, "period": "Top 2nd", "outs": 1, "balls": 0, "strikes": 1, "bases": []}
    doc = T._mlb_doc()
    doc.update({"generated_at": gen, "home": "TB", "away": "MIL", "home_name": "Tampa Bay Rays",
                "away_name": "Milwaukee Brewers", "plays": [], "live": live})
    strip = {"generated_at": gen, "games": [{"game_pk": 777001, "home": "TB", "away": "MIL", "live": live}]}
    pressure = {"season": 2026, "season_used": 2026, "one_score": 1, "min_games": 4, "min_rate_n": 3,
                "teams": {"TB": {"clutch": 57, "reliability": None, "comeback": None, "choke": None, "record": "106-77-1"},
                          "MIL": {"clutch": 53, "reliability": None, "comeback": None, "choke": None, "record": "113-70"}},
                "ranked": {"clutch": [], "reliability": [], "comeback": [], "choke": []}}
    standings = {"sport": "mlb", "generated_at": gen, "pressure": pressure, "groups": []}
    serve = lambda body: (lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(body)))  # noqa: E731
    srv, port = rendercheck._serve()
    got = {}
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": 390, "height": 900}, is_mobile=True, has_touch=True,
                                          service_workers="block", reduced_motion="reduce")
                page = ctx.new_page()
                errs = []
                page.on("pageerror", lambda e: errs.append(str(e)))
                page.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb.tour', 'done'); } catch (e) {}")
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/data/pbp/mlb_777001.json*", serve(doc))
                page.route("**/data/live_mlb.json*", serve(strip))
                page.route("**/data/standings_mlb.json*", serve(standings))
                page.goto(f"http://127.0.0.1:{port}/index.html#pbp/mlb/777001", wait_until="load")
                page.wait_for_selector(".pbp-pressure .pr-tm", timeout=20000)
                got = page.evaluate("""() => {
                  const c = document.querySelector('.pbp-pressure'), h = c.querySelector('.pbp-rail-head');
                  const px = (e, k) => parseFloat(getComputedStyle(e)[k]);
                  const lh = (e) => { const v = getComputedStyle(e).lineHeight; return v === 'normal' ? px(e, 'fontSize') * 1.3 : parseFloat(v); };
                  return { head: h.getBoundingClientRect().height, headLine: lh(h), headText: h.innerText.replace(/\\n/g, ' | '),
                           title: px(h, 'fontSize'), sub: px(c.querySelector('.pbp-pr-sub'), 'fontSize'),
                           lead: (c.querySelector('.pbp-pr-line b') || {}).textContent || '',
                           records: [...c.querySelectorAll('.pr-tm .k')].map((k) => [k.textContent, k.getBoundingClientRect().height / lh(k)]),
                           foot: px(c.querySelector('.pbp-pr-foot'), 'fontSize'), body: px(document.body, 'fontSize') }; }""")
                got["errs"] = errs
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert not got["errs"], got["errs"]
    assert got["head"] <= got["headLine"] * 1.5, ("the head is one line", got)
    assert "Under pressure" in got["headText"] and "LIVE" in got["headText"] and "2026" not in got["headText"], got
    assert got["sub"] < got["title"], ("the season line is quieter than the title", got)
    assert got["lead"] == "One-run game", got
    assert [r[0] for r in got["records"]] == ["113-70", "106-77-1"], got["records"]
    assert all(r[1] < 1.5 for r in got["records"]), ("no record breaks", got["records"])
    assert got["foot"] < got["body"], ("the footnote is a footnote", got)


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
