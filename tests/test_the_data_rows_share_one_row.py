"""v5: the data rows on every other page share the Record's row.

After the Record page's rooms moved to one row (.rec-row), fourteen
more builders across the site still drew theirs inline with a raw rgba
border — the Predict board, the injury watch, the UFC edge rows (which
also forced a 640px scroll on a phone), the best-bets stubs, the live
tracker's rows, the market-best list, the census funnel, the
watchlists, rest watch, incentives, the Sleeper panel, the team-form
list, the prose entries, the learning coverage. They share the row
now, each variant a word; the UFC rows wrap instead of scrolling.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()
ROWS = ("predBoardHTML", "renderInjuryWatch", "renderUFC", "renderBestBets", "renderLivePicks", "marketBestHTML",
        "censusFunnelHTML", "watchlistHTML", "renderRestWatch", "renderIncentives", "renderSleeperPanel",
        "renderTeamForm", "recProseSection", "learningCoverageHTML")


def _fn(name):
    m = re.search(r"^(async )?function " + name + r"\(", APP, re.M)
    assert m, name
    i = m.start()
    return APP[i:APP.index("\n}\n", i)]


def test_no_page_draws_its_own_data_row_any_more():
    for name in ROWS:
        body = _fn(name)
        assert "1px solid rgba(255,255,255,.05)" not in body, f"{name}: a raw border survived"
        assert re.search(r'class="[^"]*\brec-(row|note|entry|block)\b', body), f"{name}: no shared row"
    assert "1px solid rgba(255,255,255,.05)" not in APP, "a raw hairline somewhere on the site"


def test_each_pages_variant_is_a_word():
    assert 'class="ufc-edge-row rec-row mid tall${r._pick ? "" : " dim"}"' in _fn("renderUFC"), "a pass is dimmed, a bet is not"
    assert "min-width:640px" not in _fn("renderUFC"), "the UFC rows wrap on a phone instead of scrolling"
    assert '<div class="hd-card">' in _fn("renderUFC")
    assert '<div class="rec-row mid tall line${r.phase === "upcoming" ? " dim" : ""}${door ? " openable" : ""}"${door}>' in _fn("renderLivePicks"), \
        "the tracker row keeps to one line, and its door joins the one class attribute"
    assert not re.search(r'<(div|span)\s+class="[^"]*"[^>]*?\sclass="', APP), "a tag with two class attributes — the browser keeps the first and drops the row"
    assert 'class="drow rec-row mid nowrap${detail ? " watch-door" : ""}"' in _fn("watchlistHTML"), "the watch row had two style attributes before; now one class"
    assert 'class="drow ffrow-door rec-row mid nowrap"' in _fn("renderSleeperPanel")
    assert '<div class="rec-row top tall line${door ? " openable" : ""}"${door || ""}>' in _fn("marketBestHTML")
    assert ".watch-door { cursor: pointer; }" in CSS
    assert 'class="rec-row top thin dim line"' in _fn("renderBestBets")
    assert 'class="rec-row thin flush between line"' in _fn("censusFunnelHTML")
    assert '<td class="vs-cell mute">' in _fn("renderWhy") and '<td class="vs-cell">' in _fn("renderWhy")
    assert 'class="rec-row mid flush"' in _fn("renderTeamForm")
    assert 'class="rec-entry"' in _fn("recProseSection") and 'class="rec-note"' in _fn("learningCoverageHTML")
    assert 'class="rec-note"' in _fn("renderInjuryWatch")
    for v in (".rec-row.top { align-items: flex-start; }", ".rec-row.thin { padding: 4px 0; gap: 10px; }",
              ".rec-row.between { justify-content: space-between; }",
              ".rec-row.nowrap { flex-wrap: nowrap; white-space: nowrap; overflow: hidden; }",
              ".rec-entry { padding: 12px 14px; border-bottom: var(--hairline) solid var(--border-soft); }",
              ".rec-row.line { flex-wrap: nowrap; }", ".vs-cell { padding: 8px 12px; border-bottom: var(--hairline) solid var(--border-soft); }"):
        assert v in CSS, v


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
