"""The game report reads without the clutter (2026-11-15).

Ethan, after the colours: "i feel like the colors helped alot but it still
feels all cluttered and hard to digest everything. maybe we can do charts
too if you think that coul dmake anything better". So (js/report.js,
engine/gamereport._edge_chart):

  * the short version reads open and every other section folds to its
    title (<details>), a row a tap opens; the titles are the contents, so
    the jump row of chips goes, and one button opens or folds them all;
  * "How the units rank" opens on a chart — each offense against the
    defense it faces, passing, rushing, pressure and the red zone, two rank
    bars a unit, the longer the better, coloured by the league's thirds,
    the edge named — and its two tables of every number fold under it;
  * a report of one or two sections folds nothing, and the copied report
    is the whole report, every table in it.

    python3 tests/test_the_report_reads_without_the_clutter.py
"""
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from engine import gamereport as R                                   # noqa: E402

REPORT_JS = os.path.join(ROOT, "web", "js", "report.js")
REPORT_CSS = os.path.join(ROOT, "web", "css", "report.css")


def _report():
    import test_the_game_report_reads_like_the_research as T
    return T._report()


def _node(script):
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not os.path.exists(node):
        return None
    head = ("const vm = require('vm'); const fs = require('fs');"
            "const esc = (s) => String(s == null ? '' : s).replace(/[&<>\"']/g, (c) => '&#' + c.charCodeAt(0) + ';');"
            "const ctx = { window: {}, escapeHtml: esc, escapeAttr: esc,"
            " slugify: (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-'),"
            " teamName: (t) => t, playerAvatar: (p) => '<i class=av></i>' };"
            "vm.createContext(ctx);"
            f"vm.runInContext(fs.readFileSync({json.dumps(REPORT_JS)}, 'utf8'), ctx);"
            "const R = ctx.window.QBReport;")
    out = subprocess.run([node, "-e", head + script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout)


def test_the_units_chart_leads_its_section_and_the_tables_fold_under_it():
    rep = _report()
    sec = next(s for s in rep["sections"] if s["key"] == "rankings")
    chart = sec["blocks"][0]
    assert chart["type"] == "matchbars" and chart["rank_of"] == 32
    assert [sd["off"] for sd in chart["sides"]] == ["GB", "DET"]
    gb = {r["label"]: r for r in chart["sides"][0]["rows"]}
    assert list(gb) == ["Pass EPA", "Rush EPA", "Pressure", "Red-zone TD%"], list(gb)
    assert gb["Pass EPA"] == {"label": "Pass EPA", "off": 4, "def": 22, "edge": "GB"}
    assert gb["Pressure"]["edge"] == "DET" and gb["Rush EPA"]["edge"] == ""
    tables = [b for b in sec["blocks"] if b["type"] == "table" and b.get("title", "").endswith("defense")]
    assert len(tables) == 2 and all(b.get("fold") for b in tables)
    # The copied report is the whole report: every table, no chart markup.
    text = R.to_text(rep)
    assert "[Packers offense vs Lions defense]" in text and "matchbars" not in text


def test_the_page_folds_every_section_but_the_short_version():
    rep = _report()
    got = _node(f"const rep = {json.dumps(rep, ensure_ascii=False)};"
                "const two = Object.assign({}, rep, {sections: rep.sections.slice(0, 2)});"
                "process.stdout.write(JSON.stringify({full: R.html(rep, {}), two: R.html(two, {})}));")
    if got is None:
        print("      (skipped: no Node)")
        return
    full = got["full"]
    assert '<section class="gr-sec" id="gr-short"><h3 class="gr-title">The short version</h3>' in full
    folded = [s["key"] for s in rep["sections"] if s["key"] != "short"]
    for k in folded:
        assert f'<details class="gr-sec gr-fold" id="gr-{k}"><summary class="gr-title">' in full, k
    assert full.count("<details class=\"gr-sec gr-fold\"") == len(folded)
    assert "gr-toc" not in full and "data-jump=" not in full, "the folded titles are the contents"
    assert '<button type="button" class="btn ghost" data-gr-all="1">Open every section</button>' in full
    assert "gr-fold" not in got["two"] and "data-gr-all" not in got["two"], "two sections fold nothing"
    for bad in ("undefined", "[object", "NaN"):
        assert bad not in full, bad


def test_the_chart_draws_each_rank_as_a_bar_in_its_thirds():
    rep = _report()
    got = _node(f"const rep = {json.dumps(rep, ensure_ascii=False)};"
                "process.stdout.write(JSON.stringify(R.html(rep, {})));")
    if got is None:
        print("      (skipped: no Node)")
        return
    i = got.index('class="gr-chart gr-match"')
    chart = got[i:got.index("</div></div>\n      <p class=\"gr-note\">", i)]
    # 4th of 32 is the top third (green), 22nd the bottom (red), 15th neither.
    assert '<div class="gr-bar up"><span class="gr-bar-fill" style="--w:91%"></span>' in chart
    assert '<span class="gr-bar-txt">GB <b>4th</b></span>' in chart
    assert '<div class="gr-bar down"><span class="gr-bar-fill" style="--w:34%"></span>' in chart
    assert '<div class="gr-bar"><span class="gr-bar-fill" style="--w:56%"></span>' in chart, "15th: plain"
    assert chart.count('<span class="gr-edge">edge GB</span>') >= 1
    assert "GB offense <span>vs DET defense</span>" in chart
    sec = got[got.index('id="gr-rankings"'):]
    assert '<details class="gr-fold-tbl"><summary>Every number: Packers offense vs Lions defense</summary>' in sec
    css = open(REPORT_CSS, encoding="utf-8").read()
    for rule in (".gr-fold > summary.gr-title::after", ".gr-bar-fill { position: absolute; inset: 0 auto 0 0; width: var(--w, 0%);",
                 ".gr-bar.up .gr-bar-fill { background: var(--good);", ".gr-bar.down .gr-bar-fill { background: var(--bad);"):
        assert rule in css, rule
    assert ".gr-toc" not in css


def test_in_a_browser_one_button_opens_and_folds_them_all():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    rep = _report()
    with sync_playwright() as pw:
        kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
        if os.path.exists("/opt/pw-browsers/chromium"):
            kw["executable_path"] = "/opt/pw-browsers/chromium"
        browser = pw.chromium.launch(**kw)
        try:
            page = browser.new_page(viewport={"width": 390, "height": 900})
            errs = []
            page.on("pageerror", lambda e: errs.append(str(e)))
            page.set_content("<!doctype html><html><head><meta charset=utf-8></head><body><main id=m></main></body></html>")
            page.add_style_tag(path=REPORT_CSS)
            page.evaluate("""() => {
              window.escapeHtml = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => '&#' + c.charCodeAt(0) + ';');
              window.escapeAttr = window.escapeHtml;
              window.slugify = (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-');
              window.teamName = (t) => t; window.playerAvatar = () => '';
            }""")
            page.add_script_tag(path=REPORT_JS)
            page.evaluate("(rep) => { document.getElementById('m').innerHTML = window.QBReport.html(rep, {}); }", rep)
            opened = lambda: page.evaluate("[...document.querySelectorAll('details.gr-fold')].filter(d => d.open).length")  # noqa: E731
            total = page.evaluate("document.querySelectorAll('details.gr-fold').length")
            assert total >= 10 and opened() == 0
            page.click("[data-gr-all]")
            assert opened() == total and page.inner_text("[data-gr-all]") == "Fold the sections"
            page.click("[data-gr-all]")
            assert opened() == 0 and page.inner_text("[data-gr-all]") == "Open every section"
            # One section opens on its own title.
            page.click("#gr-rankings > summary")
            assert page.evaluate("document.getElementById('gr-rankings').open")
            assert page.is_visible("#gr-rankings .gr-match")
            assert not errs, errs
        finally:
            browser.close()


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
                import traceback
                traceback.print_exc(limit=6)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
