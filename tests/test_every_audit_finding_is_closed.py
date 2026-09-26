"""The site audit's open findings, closed (docs/AUDIT_2026-09-24.md).

Ethan, 2026-09-24: "fix all issues found in the audit. Don't come back
till all issues are fixed and re runs tests too confirm all issues are
fixed." The larger closures have their own files —
test_the_page_is_served_what_it_reads.py (M-3), test_contrast.py (M-5),
test_the_playoff_form_window.py (H-4's known limit). This file holds L-7
and the three visual findings.
"""
import json
import shutil
import subprocess
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


# --- L-7: data computed and never shown -------------------------------------
def test_the_mlb_game_page_names_both_bullpens():
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed")
        return
    prog = (_fn("ordinal") + "const PEN_TIRED = 6;\n" + _fn("mlbPenNotes") +
            "process.stdout.write(JSON.stringify(mlbPenNotes({away: 'NYY', home: 'BOS',"
            " bullpen_rank: {NYY: 3, BOS: 27}, bullpen_fatigue: {NYY: 4.2, BOS: 7.5}})));")
    got = json.loads(subprocess.run([node, "-e", prog], capture_output=True, text=True,
                                    timeout=60, check=True).stdout)
    assert got[0] == "NYY bullpen ranks 3rd of 30", got
    assert got[1].startswith("BOS bullpen ranks 27th of 30, tired — 7.5 relief innings"), got
    page = _fn("renderGamePage")
    assert "if (mlb) notes.push(...mlbPenNotes(g));" in page
    assert "state.data.injured_list" in page, "the injured list reaches the game page"


def test_the_threshold_is_the_model_s_own():
    from engine.mlb.bullpen import TIRED_MIN
    assert f"const PEN_TIRED = {TIRED_MIN:g};" in APP


def test_a_sharp_priced_pick_says_so():
    page = _fn("renderPropPage")
    assert "r.sharp_anchored ?" in page and "Priced off the sharp book" in page


def test_the_operator_diagnostics_reach_the_operator_not_the_phone():
    from engine import inputcheck, served
    board = {"recommendations": [], "bar_status": ["receptions: no bet is possible"],
             "td_census": {"quoted": 3}}
    out = served.served(board)
    assert "bar_status" not in out and "td_census" not in out
    lines = inputcheck.report({"nfl": {**board, "recommendations": [{"market": "receptions"}]}})
    assert any("nfl bar: receptions: no bet is possible" in ln for ln in lines), lines


def test_devigcheck_follows_a_public_board_to_its_census():
    from engine import devigcheck
    root = Path(tempfile.mkdtemp())
    (root / "web" / "data").mkdir(parents=True)
    (root / "data" / "built").mkdir(parents=True)
    pub, full = root / "web" / "data" / "nfl.json", root / "data" / "built" / "nfl.json"
    pub.write_text(json.dumps({"sport": "nfl", "long_shots": []}))
    full.write_text(json.dumps({"sport": "nfl", "long_shots": [], "td_census": {"quoted": 3}}))
    board, read, note = devigcheck.load(str(pub))
    assert read == str(full) and board["td_census"] == {"quoted": 3} and "census" in note


# --- Visual 1: the picks lead Home ------------------------------------------
def test_the_stadiums_lead_then_the_picks_and_the_tools_close_the_deck():
    """Ethan, 2026-09-24: the venues go back to the top, above the picks."""
    i = APP.index("const HOME_DECK_ORDER = ")
    order = json.loads(APP[i + len("const HOME_DECK_ORDER = "):APP.index(";", i)])
    # No edge section on the home since 2026-09-26 — Ethan, 2026-09-26: "the edge bets can be its own menu or tab. We shouldn't show that on the main page anymore".
    assert order.index("games") < order.index("likely") and "edge" not in order
    assert order.index("live") < order.index("games")
    assert order[-1] == "tools"


def test_the_rooms_leave_the_deck_s_zones_in_the_deck():
    """The deck adopted its zones and the rooms' first pass took every one
    back, so a phone never saw the deck's order on a first load."""
    body = _fn("subtabbedDOM")
    assert 'if (el && !el.closest("#home-deck")) panel.appendChild(el);' in body


# --- Visual 2: the home's games are a strip ---------------------------------
def test_the_home_game_cards_drop_the_dial_on_a_phone():
    phone = CSS[CSS.index("#home-deck #games-sport { display: none; }"):][:1200]
    assert '#home-deck .hd-sec[data-sec="games"] .wind-wrap .wind { display: none; }' in phone
    assert '#home-deck .hd-sec[data-sec="games"] .gc-venue { display: none; }' in phone


# --- Visual 3: one Share on the pick page -----------------------------------
def test_the_pick_page_strip_is_four_buttons():
    page = _fn("renderPropPage")
    strip = page[page.index('<div class="pp-actions">'):page.index('<div id="fr-send-slot">')]
    assert strip.count("<button") == 4, strip
    assert ">Share</button>" in strip and "data-card=" not in strip and "shareBtn(" not in strip
    i = APP.index('const open = e.target.closest && e.target.closest("[data-send-pick]");')
    opener = APP[i:i + 1400]
    assert 'shareBtn("pick", pickSlug(r))' in opener and "Share card" in opener
    assert "Sign in to send it to a friend." in opener, "signed out still gets the link and the card"


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
