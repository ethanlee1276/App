"""The mock draft simulator — Ethan, 2026-08-18: "Add a mock draft
simulator."

Its arithmetic is executed in `tests/test_mockdraft_logic.py` (node);
this file pins the DISCIPLINES into the page source:

  * ONE BOARD. The sim drafts from the kit's own published 150 — the
    same players, projections and VORP the draft kit page shows — so
    the simulator and the kit can never disagree about who is good.
  * A STATED CPU, not a personality engine. Best-available by VORP with
    noise and a positional-need multiplier, all visible in one function.
  * ARITHMETIC AT THE END, not a letter grade. Your best legal starting
    lineup's projected PPG against the rooms' own — a grade would imply
    a model of drafting skill nobody fitted.

Run directly: `python3 tests/test_mockdraft.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"),
           encoding="utf-8").read()


def test_the_fantasy_page_has_the_room():
    i = APP.index('subtabbedHTML("fantasy"')
    body = APP[i:i + 1200]
    assert '"mock", "Mock draft"' in body
    assert 'id="mock-room"' in body


def test_the_pool_is_the_kits_own_board():
    """Captured at render from the fantasy payload — the first cut read
    state.data, which on the fantasy page is a SPORT board with no
    draft_kit in it, and the room told everyone the kit was empty."""
    assert "_mockKit = d.draft_kit || {}" in APP
    i = APP.index("function _mockStart(")
    body = APP[i:i + 400]
    assert "_mockKit || {}" in body
    assert "(b.vorp || 0) - (a.vorp || 0)" in body, \
        "the pool must be ordered by the kit's own value metric"


def test_the_cpu_is_stated_not_hidden():
    i = APP.index("function _mockCpuPick(")
    body = APP[i:APP.index("\n}", i)]
    assert "_mockNeed(" in body and "Math.exp(" in body
    j = APP.index("function _mockNeed(")
    need = APP[j:APP.index("\n}", j)]
    assert '(pos === "QB" || pos === "TE")' in need, \
        "the onesie discipline is the one rule a CPU must know"


def test_the_end_is_arithmetic_not_a_letter_grade():
    i = APP.index("let _mock = null;")
    block = APP[i:APP.index("function _mockRender(", i)]
    assert "_mockStartersPPG" in block
    for grade in ('"A+"', '"B+"', "gradeClass"):
        assert grade not in block, \
            "a draft grade implies a skill model nobody fitted"


def test_the_binding_survives_every_rerender():
    """The room's innerHTML is replaced on every pick, so the click
    handler must be DELEGATED from the room node the page owns — a
    handler on the buttons themselves dies with the first render."""
    i = APP.index("function _mockBind(")
    body = APP[i:APP.index("\n}", i + 200)]
    assert 'room.addEventListener("click"' in body
    # Anchored to the FANTASY page's assembly — bindSubtabs(host) appears
    # on every sub-tabbed page, and the first one is someone else's.
    j = APP.index("host.innerHTML = _ffLead")
    assert "_mockBind(host)" in APP[j:j + 2200]


def test_an_unfinished_draft_survives_a_data_refresh():
    """The fantasy page re-renders when its payload refreshes; the room
    re-emits from module state, so a draft in progress must not reset."""
    assert "let _mock = null;" in APP
    i = APP.index('subtabbedHTML("fantasy"')
    assert "${mockDraftHTML()}" in APP[i:i + 1200], \
        "the room must re-emit the LIVE draft, not a fresh setup panel"


def test_every_face_the_kit_stores_reaches_the_room():
    """Ethan, 2026-08-18: "Make sure all spots have head shots." The kit
    page and this room both hand the avatar r.headshot — but the field
    only exists because fantasy_build stamps the kit's rows with the
    faces map. Pinned at both ends so neither half can quietly drop it."""
    i = APP.index("const face = (p, size)")
    assert "headshot: p.headshot" in APP[i:i + 200]
    fb = open(os.path.join(ROOT, "fantasy_build.py"), encoding="utf-8").read()
    j = fb.index("_face_rows = [")
    block = fb[j:j + 600]
    for rows in ('kit.get("board")', 'kit.get("sleepers")',
                 'kit.get("tiers")'):
        assert rows in block, f"the stamp loop lost {rows}"
    # Camp and the rankings table are stamped after assembly.
    k = fb.index('"ranks": fantasy_ranks.build')
    tail = fb[k:k + 900]
    for rows in ('"risers"', '"fallers"', '"new_starters"', '"rows"'):
        assert rows in tail, f"the late stamp lost {rows}"


def test_the_room_is_styled():
    for sel in (".mk-log-row {", ".mk-advice {", ".mk-sel {"):
        assert sel in CSS, f"{sel} is unstyled"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
