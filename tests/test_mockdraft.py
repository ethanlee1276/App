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
    # VORP-ordered, but RE-DERIVED under the chosen format first: a
    # format that changed projections and left VORP alone would move every
    # tight end up the page while the number that decides the draft went
    # on describing a different league.
    assert "_mockScoreBoard(" in body, \
        "the pool no longer scores the board under the league's format"
    fn = APP[APP.index("function _mockScoreBoard("):]
    fn = fn[:fn.index("\n}")]
    assert "b.vorp - a.vorp" in fn, "the board is not value-ordered"
    assert "r.proj - baseline" in fn, "VORP is not re-derived from replacement"


def test_the_cpu_is_stated_not_hidden():
    i = APP.index("function _mockCpuPick(")
    body = APP[i:APP.index("\n}", i)]
    assert "_mockScore(" in body, "the CPU's rule is no longer a named function"
    j = APP.index("function _mockNeedCounts(")
    need = APP[j:APP.index("\n}", j)]
    assert '(pos === "QB" || pos === "TE")' in need, \
        "the onesie discipline is the one rule a CPU must know"


def test_the_predictor_and_the_room_share_one_rule():
    """Ethan, 2026-08-20: "run the simulation like 20k times over to see
    all the different outcomes."

    The whole value of that number is that it describes THIS room. If the
    Monte Carlo carried its own copy of the pick logic the two would
    drift — silently, because both would keep producing plausible numbers
    — and the page would publish a probability about a draft nobody is
    having. One scoring function, two callers, pinned here.
    """
    live = APP[APP.index("function _mockCpuPick("):]
    live = live[:live.index("\n}")]
    sim = APP[APP.index("function mockSurvival("):]
    sim = sim[:sim.index("\n}\n")]
    assert "_mockScore(" in live and "_mockScore(" in sim, \
        "the predictor and the room no longer score picks the same way"
    # And the personas have to reach both, or the sim predicts a room of
    # value-maximisers while the draft runs a room of characters.
    assert "personas" in live and "m.personas" in sim


def test_the_rooms_are_people_not_one_algorithm_twelve_times():
    """A room of identical value-maximisers produces a draft with almost
    no variance, and running THAT twenty thousand times just measures the
    noise term — a confident-looking probability about a league nobody
    plays in."""
    i = APP.index("const MOCK_ARCHETYPES = [")
    block = APP[i:APP.index("];", i)]
    for build in ("Zero RB", "Hero RB", "WR hoarder", "Early QB", "Elite TE"):
        assert build in block, f"lost the {build} room"
    # Dealt once and kept: a manager who is Zero-RB in round two and
    # Robust-RB in round three is not a manager.
    start = APP[APP.index("function _mockStart("):]
    start = start[:start.index("\n}")]
    assert "personas" in start, "rooms no longer carry a build"


def test_the_room_drafts_off_a_market_board_not_our_value_board():
    """Ethan, 2026-08-20: "make sure there is nothing else we can add to
    the draft simulator too make it more realistic and shit."

    Measured over 300 full drafts, the answer was one assumption. The
    CPUs were drafting off OUR board, ordered by VORP — and VORP is not
    draft order. Value over replacement says what a player is worth; a
    room says what people will pay, and the two disagree hardest exactly
    at quarterback and tight end, where the replacement is nearly as good
    but the room still takes the name it knows. The first tight end left
    the board at pick 4.9 and the first quarterback at 11.4. Real
    twelve-team drafts do neither.

    Two boards now: the market order the rooms draft from, and our VORP
    order the human is shown. The gap between them is the reason to
    prepare here rather than anywhere else — "the room has him twelfth,
    we have him twenty-fifth" only exists once the orders may differ.
    """
    assert "function _mockMarketOrder(" in APP
    assert "MOCK_SHARE_BANDS" in APP, "the market order has no share model"
    # Round one is backs and receivers. A flat share across the draft
    # schedules positions EVENLY, which put a tight end in round one by
    # construction — no amount of bounding the rooms could fix a board
    # that already had him there.
    i = APP.index("const MOCK_SHARE_BANDS = [")
    bands = APP[i:APP.index("];", i)]
    assert "until: 12" in bands, "the round-one band is gone"
    first = bands[:bands.index("},")]
    assert "TE: 0.02" in first and "QB: 0.00" in first, \
        "round one is no longer backs and receivers"
    # And both the room and its predictor must read that board.
    live = APP[APP.index("function _mockCpuPick("):]
    live = live[:live.index("\n}")]
    sim = APP[APP.index("function mockSurvival("):]
    sim = sim[:sim.index("\n}\n")]
    assert "_mockByMarket(" in live and "_mockByMarket(" in sim, \
        "somebody is still drafting off the value board"


def test_a_room_cannot_hoard_a_position():
    """The need curve only ever SOFTENED — it bottomed out at 0.2, and 0.2
    is not zero over twelve rounds. Measured: rooms finished carrying six
    quarterbacks and six tight ends. A room that might do that is a room
    whose picks tell you nothing."""
    i = APP.index("const MOCK_ROSTER_CAP = {")
    caps = APP[i:APP.index("};", i)]
    for pos in ("QB", "TE", "RB", "WR"):
        assert pos in caps, f"no cap on {pos}"
    j = APP.index("function _mockNeedCounts(")
    need = APP[j:APP.index("\n}", j)]
    assert "return 0;" in need, "the cap does not actually close the spot"
    # A zero must MEAN no. Falling through to the top candidate when
    # everything scores zero is how the cap was defeated in the first cut.
    for fn in ("function _mockCpuPick(", "function mockSurvival("):
        k = APP.index(fn)
        body = APP[k:APP.index("\n}\n" if "Survival" in fn else "\n}", k)]
        assert "total > 0" in body, \
            f"{fn} still treats a zero weight as a last resort"


def test_a_reach_is_not_capped_by_the_size_of_the_window():
    """Measured over 300 drafts, the deepest reach in the entire sample was
    exactly eight slots — because the ninth-ranked player was not in the
    room's field of view. Eight was a wall, not a behaviour."""
    i = APP.index("const MOCK_TOPK = ")
    k = int(APP[i:APP.index(";", i)].split("=")[1].strip())
    assert k >= 12, f"the consideration window is back down to {k}"


def test_a_build_moves_a_player_in_slots_not_in_multipliers():
    """A weight multiplier has no natural scale: at 2.6x an elite-TE room
    had a real chance of taking its tight end at 1.03. A build means "I
    will take him a round early", which is a number of slots — and slots
    can be bounded where the tail of a multiplication cannot."""
    i = APP.index("const MOCK_ARCHETYPES = [")
    block = APP[i:APP.index("];", i)]
    assert "shift:" in block and "lean:" not in block, \
        "builds are expressed as multipliers again"
    assert "w:" in block, "builds are drawn uniformly again"
    # Most rooms are not characters. Drawing eight builds uniformly put
    # roughly 1.5 tight-end chasers in every draft.
    j = APP.index("function _mockDrawArchetype(")
    assert "MOCK_ARCH_TOTAL" in APP[j:j + 300], "the draw ignores the weights"


def test_a_format_re_derives_the_board_rather_than_re_skinning_it():
    """Ethan, 2026-08-20: "te premium and shit like that."

    A format is not a cosmetic setting. Superflex moves quarterbacks from
    the tenth round to the first, because the position stops having a free
    replacement — and that changes which players survive to your next
    pick, which is the whole product. Verified on the real board: the
    first quarterback moves from market slot 19 to slot 3, and six of them
    go before your second pick where under PPR it is 0.9.

    Everything falls out of the line-up by arithmetic: the line-up decides
    replacement level, replacement decides VORP, VORP decides our board,
    and the market board is built from a share the format also sets. No
    format carries a ranking of its own.
    """
    i = APP.index("const MOCK_FORMATS = {")
    block = APP[i:APP.index("\n};", i)]
    for key in ("ppr", "superflex", "te_prem"):
        assert f"{key}:" in block, f"lost the {key} format"
    assert "SFLEX" in block, "superflex has no extra starting slot"
    # The pieces that must follow the format rather than a constant.
    for fn, what in (("_mockShareAt", "share"), ("_mockNeedCounts", "caps"),
                     ("_mockLineup", "slots")):
        j = APP.index(f"function {fn}(")
        body = APP[j:APP.index("\n}", j)]
        assert "_mockFmt()" in body, f"{fn} ignores the format's {what}"


def test_te_premium_is_arithmetic_on_real_receptions():
    """The bonus is per RECEPTION. Estimating receptions from targets times
    an assumed catch rate would invent the one number the format turns on,
    so the board carries them (engine/fantasy_draft.py) and this multiplies
    them. Verified on the real board: McBride 17.7 -> 21.4, which is
    exactly 0.5 x his 7.41 catches a game."""
    i = APP.index("function _mockScoreBoard(")
    body = APP[i:APP.index("\n}", i)]
    assert "p.rec_pg" in body, "the bonus is no longer per reception"
    assert "targets" not in body, "receptions are being estimated from targets"


def test_superflex_makes_a_second_quarterback_a_starter():
    """Treating him as a bench luxury would have rooms leave a starting
    slot empty to hold a fourth receiver. The LINE-UP decides this, not a
    special case keyed off a format name."""
    i = APP.index("function _mockNeedCounts(")
    body = APP[i:APP.index("\n}", i)]
    assert "SFLEX" in body, "the need rule cannot see the superflex slot"
    assert "n < starts" in body, "a second QB is a luxury even where he starts"
    assert '"superflex"' not in body, "the rule is keyed off a format name"


def test_the_bye_warning_counts_starters_not_the_roster():
    """Two backup tight ends sharing a bye costs nothing — you were never
    starting them. What matters is how many of your best eleven go dark at
    once. Verified on a fixture: three starters on week 11 with two bench
    players also on 11 reports 3, not 5."""
    i = APP.index("function _mockByeClash(")
    body = APP[i:APP.index("\n}", i)]
    assert "_mockLineup(roster)" in body, "the clash counts the whole roster"
    assert "lineup.starters" in body
    assert "x.n >= 3" in body, "the threshold for a real hole is gone"
    # And a board with no bye data must draw nothing rather than zeroes.
    assert "p.bye" in body


def test_the_simulation_reports_the_count_it_actually_ran():
    """A phone that cannot finish twenty thousand must not claim it.
    The loop is time-boxed and the page prints `sims`, which is the
    number that happened."""
    sim = APP[APP.index("function mockSurvival("):]
    sim = sim[:sim.index("\n}\n")]
    assert "MOCK_SIM_BUDGET_MS" in sim, "the run is unbounded on a slow device"
    assert "sims: ran" in sim, "the report does not carry the real count"
    assert "sim.sims.toLocaleString()" in APP, \
        "the page states a count that is not the measured one"


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
