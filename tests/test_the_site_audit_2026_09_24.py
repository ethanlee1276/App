"""The site audit's smaller fixes, 2026-09-24 (docs/AUDIT_2026-09-24.md).

Ethan: "act like a professional audit company performing a 100k audit on
our website to make sure it's flawless and no bugs or errors in the code
or making sure all data is being used correctly and all data is going
where it should and check the visuals on the site too see where to
improve."

Each test here pins one finding the audit fixed in the same commit. The
larger ones have their own files: test_ask_has_a_daily_ceiling.py and
test_a_projected_hitter_waits_for_his_lineup.py.
"""
import ast
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def test_a_build_s_working_keys_never_reach_the_published_board():
    """F-8: the demo generator published `_potd_pool`, every row the caps cut."""
    from engine import gate
    root = Path(tempfile.mkdtemp())
    public = root / "web" / "data" / "fixture_board.json"
    payload = {"date": "2026-09-24", "most_likely": [], "_potd_pool": [{"player": "Cut Row"}]}
    _, full = gate.publish(payload, public)
    for path in (public, Path(full)):
        doc = json.loads(path.read_text())
        assert "_potd_pool" not in doc and doc["date"] == "2026-09-24", path
    assert "_potd_pool" in payload, "the caller's dict is not mutated"


def test_the_record_page_mounts_its_chart_after_writing_it():
    """F-5: the mount sat after `_recordRooms`'s return and never ran."""
    rooms = _fn("_recordRooms")
    assert "mountEChartsAnalytics" not in rooms
    body = APP[APP.index("  bindRecordScopes(host);\n  bindSubtabs(host);"):][:600]
    assert "mountEChartsAnalytics(host)" in body


def test_high_confidence_mode_repaints_the_board_it_filters():
    """F-6: the switch called `renderCards`, which no longer exists."""
    assert "renderCards()" not in APP and "typeof renderCards" not in APP
    i = APP.index("localStorage.setItem(HCM_KEY")
    assert "if (state.data) renderAll();" in APP[i:i + 700]


def test_no_subtitle_opens_on_a_dangling_dash():
    """V-2: 229 subtitles open "— …" on a line of their own."""
    body = _fn("enhanceSectionSubs")
    assert "lead.nodeValue = lead.nodeValue.replace(/^\\s*[—–]\\s*/, \"\");" in body
    assert body.index("lead.nodeValue") < body.index("title.dataset.subEnhanced"), \
        "trimmed on every pass, short subtitles included"


def test_the_picks_come_before_the_method():
    """V-1: the board guide and the ranking note filled a phone's first screen."""
    guide = _fn("boardGuide")
    assert '<details class="ls-note board-guide">' in guide and "<summary>" in guide
    assert guide.count("escapeHtml(") >= 4
    likely = _fn("renderLikely")
    note = likely[likely.index("note.innerHTML"):likely.index("</details>`;")]
    assert "<details class=\"ls-note board-guide\"><summary><b>How it’s ranked</b>" in note
    assert note.index("<summary>") < note.index("likelyRefusedNote(") < note.index("likelyMarketFunnel(")
    block = CSS[CSS.index("/* The board guide, folded (boardGuide)"):]
    assert ".board-guide > summary" in block and "#" not in block.split("*/", 1)[1].split("\n\n")[0]


def test_no_market_list_repeats_a_key():
    """F-7: calibrate.py and playerfit.py each listed "cfb" twice."""
    for f in ("calibrate.py", "playerfit.py"):
        tree = ast.parse((ROOT / f).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
                assert len(keys) == len(set(keys)), (f, keys)


def test_the_box_can_measure_what_this_machine_cannot():
    import homecheck
    for name in ("hold", "weight"):
        assert name in homecheck.CHECKS and homecheck.CHECKS[name][2], name
    runbook = (ROOT / "docs" / "WHEN_YOU_ARE_HOME.md").read_text(encoding="utf-8")
    assert "homecheck.py weight" in runbook


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
