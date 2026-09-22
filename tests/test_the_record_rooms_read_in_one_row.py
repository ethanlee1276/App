"""v5: the Record page's rooms read in one row.

Ethan, 2026-09-22: "keep going on whatever other pages and stuff you
still have to do." The learning, calibration, era, loss-pattern, Pick
of the Day, long-shot and book-report sections each drew their rows
with their own inline flex and a raw rgba border — eleven builders,
twenty-odd rows, every one a little different. They share one class
now (.rec-row, with a word for each room's variant), the hairline
token instead of the raw border, and the page's small size; nothing a
room says has changed.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()

ROOMS = ("recSelfTuningSection", "recLossPatternsSection", "recHypothesisLab", "recEraSection", "recPotdSection",
         "calBucketRows", "calSplitRow", "calScoreBlock", "recCalibrationSection", "recLongshotSection", "renderBookReport")


def _fn(name):
    m = re.search(r"^(async )?function " + name + r"\(", APP, re.M)
    assert m, name
    i = m.start()
    return APP[i:APP.index("\n}\n", i)]


def test_no_room_draws_its_own_row_any_more():
    for name in ROOMS:
        body = _fn(name)
        assert "1px solid rgba" not in body, f"{name}: a raw border survived"
        assert 'style="display:flex' not in body, f"{name}: an inline flex row survived"
        assert 'class="rec-' in body, f"{name}: no room row at all"


def test_each_rooms_variant_is_a_word():
    assert 'class="rec-row mid tall${isCurrent ? "" : " dim"}"' in _fn("recEraSection"), "a past era is dimmed, the running one is not"
    assert 'class="rec-row flush tight"' in _fn("recPotdSection")
    assert 'class="rec-row flush"' in _fn("calSplitRow")
    assert 'class="rec-row mid"' in _fn("calBucketRows") and 'class="rec-row mid"' in _fn("renderBookReport")
    assert 'class="rec-row mute"' in _fn("recHypothesisLab"), "the watchlist's quiet rows"
    assert _fn("recSelfTuningSection").count('class="rec-row"') >= 4, "markets, dials, players, trends"
    assert 'class="rec-block chart"' in _fn("recCalibrationSection") and 'class="rec-block"' in _fn("calScoreBlock")
    assert '<div class="rec-cards">' in _fn("calScoreBlock"), "the score cards' shelf"
    assert 'class="rec-note"' in _fn("recCalibrationSection") and 'class="rec-note"' in _fn("recLongshotSection")


def test_the_row_is_the_pages_own_and_tokened():
    i = CSS.index(".rec-row {")
    rule = CSS[i:CSS.index("}", i)]
    assert "display: flex" in rule and "flex-wrap: wrap" in rule and "gap: 12px" in rule
    assert "border-bottom: var(--hairline) solid var(--border-soft)" in rule and "font-size: var(--fs-sm)" in rule
    for v in (".rec-row.mid { align-items: center; }", ".rec-row.tall { padding: 10px 14px; }",
              ".rec-row.tight { gap: 8px; padding: 4px 0; border-bottom: 0; border-top: var(--hairline) solid var(--border-soft); }",
              ".rec-row.flush { padding-left: 0; padding-right: 0; }", ".rec-row.dim { opacity: .75; }",
              ".rec-row.mute { color: var(--text-mute); font-size: var(--fs-xs); }",
              ".rec-block { padding: 12px 14px; border-top: var(--hairline) solid var(--border-soft); }",
              ".rec-block.chart { padding: 14px 14px 4px; }", ".rec-cards { display: flex; gap: 18px; flex-wrap: wrap; }"):
        assert v in CSS, v
    assert ".rec-note { padding: 10px 14px; margin: 0; font-size: var(--fs-xs); color: var(--text-mute);" in CSS


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
