"""v5: the Market Scanner rests like the deck and its rows read like the
book; every board's empty state gets the doors.

Ethan, 2026-09-22: "keep going on whatever other pages and stuff you
still have to do."

On a quiet board the scanner's six sections each drew a "nothing here"
row over a stake box that sized nothing. When all six are empty it is
one quiet card with the doors now, and the stake box appears only when
there is a split to size. A board with anything on it draws each row
in the book's row — the bet, the books and the prices beneath it, the
number on the right over its detail, a pair's two legs on one sub-line,
a steam alert's state as the pill — with no inline-styled row left.

And the section enhancer adds the same three doors to every board
page's empty state, once, and to no page off the list.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _strip(src):
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


def _fn(name):
    for head in (f"function {name}(", f"async function {name}("):
        if head in APP:
            i = APP.index(head); break
    else:
        raise AssertionError(f"no function {name}")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return _strip(APP[i:min(ends)])


def _const(name):
    i = APP.index(f"const {name} = ")
    return APP[i:APP.index(";\n", i) + 1]


def test_a_quiet_scanner_is_one_card_with_the_doors():
    body = _fn("renderScanner")
    assert "if (!stale.length && !longs.length && !arbs.length && !middles.length && !lows.length\n      && !anchors.length && !steam.length) {" in body, \
        "all six sections, or it is not quiet"
    i = body.index('<div class="hd-quiet lv-quiet"><i class="live-dot paused"></i>Nothing out of')
    assert '${boardEmptyDoors("scanner")}${scanFoot}`;\n    bindEmptyDoors(host);\n    return;' in body[i:i + 700], \
        "the doors, minus this page, wired; then the note; then nothing else"
    assert 'host.innerHTML = freshness + (arbs.length || middles.length || lows.length ? stakeInput : "")' in body, \
        "the stake box only when there is a split to size"
    assert 'const scanFoot = `<p class="list-note">' in body, "the foot is the note it always was, in the note's class"
    assert body.count("${scanFoot}") == 2, "the foot on both branches"


def test_every_scanner_row_is_the_books_row():
    body = _fn("renderScanner")
    pair = _fn("scanPairRow")
    for src, what in ((body, "renderScanner"), (pair, "scanPairRow")):
        assert 'style="display:flex' not in src and 'class="drow"' not in src, f"{what}: an inline-styled row survived"
        assert "rgba(255,255,255" not in src, f"{what}: a raw border survived"
    assert '<div class="hd-row hd-scan">${scanMark(t)}<div class="hd-what"><b>${escapeHtml(t.bet)}</b>' in body, "the stale line"
    assert '<b class="hd-pl" style="color:var(--good)">${t.gap_pts.toFixed(2)} pts cheap</b>' in body
    assert '<b class="hd-pl" style="color:var(--bad)">${(t.measured_roi * 100).toFixed(1)}% historically</b>' in body, "the plus-money prop"
    assert '<b class="hd-pl" style="color:var(--good)">+${(a.profit_pct * 100).toFixed(2)}% · $${ret.toFixed(2)} locked</b>' in body, "the arb"
    assert '<span class="hd-warn">${icon(\'warn\')} 5%+ edge' in body
    assert '<b class="hd-pl">${(h.hold_pct * 100).toFixed(1)}% hold</b>' in body, "the low hold"
    assert 'const leg = (side, l) => `${side} ${escapeHtml(String(l.line))} @ ${escapeHtml(l.book)} ${american(l.odds)}`;' in pair
    assert '<span>${leg("Over", p.over)} · ${leg("Under", p.under)}</span></div>' in pair, "a pair's legs on one sub-line"
    assert '<div class="hd-num"><span class="hd-o">${american(b.odds)}</span>' in body, "the sharp anchor's price pill"
    assert '<span class="hd-p">+${((b.ev_per_unit || 0) * 100).toFixed(1)}% EV</span>' in body
    assert '<div class="hd-state"><span class="hd-chip ${cls[1]}">${cls[0]}</span>' in body, "a steam alert's state as the pill"
    assert '? ["Stale", "", "old move — informational only"]' in body and '? ["Live", "good", "value still available near the sharp number"]' in body
    assert '<input id="scan-stake" class="scan-stake" type="number"' in body and "border:1px solid" not in body
    sec = _fn("scanSection")
    assert '<div class="hd-card">' in sec
    assert ".hd-scan .hd-state span { color: var(--text-mute); font-size: var(--fs-xs); text-align: right; }" in CSS
    assert ".scan-stake { width: 90px; background: transparent; color: inherit; font: inherit;" in CSS
    assert ".hd-scan .hd-state { flex: 0 1 auto; min-width: 0; max-width: 52%; }" in CSS, "the right column yields on a phone"
    assert ".hd-scan .hd-what { flex: 1 1 120px; min-width: 120px; }" in CSS


def test_every_boards_empty_state_gets_the_doors_once():
    subs = _fn("enhanceSectionSubs")
    assert "enhanceNotes(root);\n  enhanceEmpties(root);" in subs, "run with the other enhancers, on every render"
    views = _const("EMPTY_DOOR_VIEWS")
    for v in ("injuries", "weather", "alerts", "futures", "longshots", "standings", "rosters", "streak", "scanner", "record", "mybets", "zeno"):
        assert f'"{v}"' in views, v
    for v in ("messages", "account", "signup", "checkout", "paywall", "discord", "about"):
        assert f'"{v}"' not in views, f"{v} is not a board"
    body = _fn("enhanceEmpties")
    assert 'querySelectorAll(".view .empty-slate:not([data-doors])")' in body and 'es.dataset.doors = "1";' in body, "once per empty state"
    assert 'if (!EMPTY_DOOR_VIEWS.has(key) || es.querySelector(".es-doors")) return;' in body, \
        "not off the list, and not over doors a page drew itself"
    assert 'es.insertAdjacentHTML("beforeend", boardEmptyDoors(key));\n    bindEmptyDoors(es);' in body
    assert 'String(view.id || "").replace(/^view-/, "")' in body, "the page's own key, so it never offers itself"


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
