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


def test_the_tier_cliff_says_how_long_it_has_not_just_how_many():
    """Inside a tier the differences are noise — the kit's own notes say
    so — which makes the last pick before a step down the only one that
    ever really costs you. But a count alone does not answer the question:
    two left is comfortable if nobody takes one before your turn and an
    emergency if three rooms are about to. The Monte Carlo already knows
    which, so the cliff carries both."""
    i = APP.index("function _mockTierCliff(")
    body = APP[i:APP.index("\n}", i)]
    assert "sim.survive.get(" in body, "the cliff ignores the simulation"
    # Independence would be wrong — rooms take at most one each — so the
    # honest summary is the BEST single survival chance in the tier.
    assert "q > best" in body, "the tier's odds are being multiplied out"
    assert "inTier.length > 4" in body, "a deep tier is a shelf, not a cliff"


def test_the_season_is_simulated_with_the_byes_taken_out():
    """The draft simulation answers "who will be there". This answers the
    question that follows and is the reason anyone drafts: so what?

    A starters-PPG number says the roster is good on the average week, and
    fantasy is not played on the average week. Byes are exactly what an
    average cannot see: a roster whose points sit in three men who all
    rest in week eleven is a different team from one with the same total
    spread out. Measured on matched rosters, stacking three starters on
    one bye costs about a tenth of a win over fourteen weeks and two
    points of play-off odds — small, real, and correctly signed.
    """
    i = APP.index("function _mockWeekScore(")
    body = APP[i:APP.index("\n}", i)]
    assert "p.bye !== week" in body, "the season ignores byes"
    # The bench has to fill in, which is what a manager does — and it must
    # use the SAME line-up rule the final screen shows, or the season is
    # scored on a team the page never displays.
    assert "_mockLineup(" in body, "the week is not fielded as a line-up"


def test_a_simulated_week_averages_to_the_projection():
    """exp(N(mu, s)) has mean exp(mu + s^2/2), so mu has to be shifted
    down by half the variance. Without it every simulated week lands ABOVE
    the projection and the whole league outscores itself. Verified over
    200,000 draws: a projection of 15 at cv 0.6 averages 14.99."""
    i = APP.index("function _mockWeekPoints(")
    body = APP[i:APP.index("\n}", i)]
    assert "-0.5 * s * s" in body, "the lognormal mean correction is gone"


def test_the_season_says_which_of_its_inputs_is_not_measured():
    """The per-position weekly spread is the one number here that is an
    assumption rather than a measurement, and the win totals move with it.
    Stated on the page, not buried in a comment."""
    assert "MOCK_WEEK_CV" in APP
    flat = " ".join(APP.split())
    assert "the one input here that is not measured" in flat, \
        "the page no longer admits which input is assumed"
    # And the record is reported as a distribution: "9-5" is a story about
    # one season and the same roster plays a range.
    i = APP.index("function _mockSeasonHTML(")
    body = APP[i:APP.index("\n}\n", i)]
    assert "r.p10" in body and "r.p90" in body, "the season is a point estimate"
    assert "mk-hist" in body, "the distribution is not drawn"


def test_a_keeper_costs_the_round_it_was_kept_in():
    """Ethan, 2026-08-20: "do the keeper shit too."

    A keeper is not a player crossed off a list. It is a player crossed
    off AND A PICK THAT NEVER HAPPENS — the round he cost belongs to the
    room that kept him, and the draft moves straight past the slot. That
    second half is what most keeper toggles leave out, and it is the half
    that changes when players come off the board: a keeper league falls
    differently precisely because eleven rooms pick in round three instead
    of twelve, and the survival odds are wrong by exactly that much if the
    slot is left in.

    Verified on a twelve-team, eleven-round board with three keepers: the
    skipped indexes map to exactly the three (room, round) pairs kept and
    no others, the draft runs 129 picks instead of 132, and the user's own
    turns move from 5, 18, 29, 42 to 5, 18, 42, 53 — index 29 was his
    round-three pick and it is gone.
    """
    assert "function _mockSkipSet(" in APP
    # Every reader of the draft order has to honour it, or the predictor
    # describes a draft with a phantom room in it.
    sim = APP[APP.index("function mockSurvival("):]
    sim = sim[:sim.index("\n}\n")]
    assert "_mockSkipped(m, pickIdx)" in sim, \
        "the predictor still simulates a pick that does not happen"
    adv = APP[APP.index("function _mockAdvance("):]
    adv = adv[:adv.index("\n}")]
    assert "_mockSkipped(" in adv, "the live draft still plays the kept slot"
    turn = APP[APP.index("function _mockNextTurn("):]
    turn = turn[:turn.index("\n}")]
    assert "skip.has(i)" in turn, "'my next turn' ignores the skipped picks"


def test_a_kept_player_joins_the_roster_that_kept_him():
    """Not merely deleted. On the roster, every rule that reads one — need,
    the caps, the line-up, the bye clash — sees him with no special case
    anywhere. Verified in a browser across three drafts: all three keepers
    absent from the best-available column, and the user's own sitting top
    of his roster before he has picked."""
    i = APP.index("function _mockStart(")
    body = APP[i:APP.index("\n}", i)]
    assert "_mock.rosters[k.team].push(p)" in body, \
        "a keeper is deleted rather than owned"
    assert "_mock.pool = _mock.pool.filter" in body, \
        "a keeper is still draftable"
    # A league that shrinks must not keep a player owned by a room that
    # no longer exists.
    assert "k.team < teams" in body, "keepers survive a smaller league"


def test_the_keeper_editor_will_not_take_an_impossible_entry():
    """A room has one pick per round to give up, so it cannot keep two
    players in the same one — and the same man cannot be kept twice."""
    i = APP.index('if (t.id === "mk-keep-add")')
    body = APP[i:i + 900]
    assert "k.player === who" in body, "the same player can be kept twice"
    assert "k.team === team && k.round === round" in body, \
        "one room can keep two players with one pick"


def test_keepers_survive_a_reload():
    """Somebody preparing for a real keeper league runs the same mock a
    dozen times against the same four players. Re-entering them each time
    is how a feature goes unused."""
    assert "MOCK_KEEPER_KEY" in APP and "localStorage" in APP
    i = APP.index("let _mockKeepers = ")
    assert "Array.isArray(v)" in APP[i:i + 400], \
        "a corrupt store would throw on the next draft"


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


# --- the draft room, built to Ethan's render 2026-08-20 -----------------------
# He sent a mock-draft mockup and asked for the page to match it. Most of it
# is built. Three things in it are not, and these tests are why they stay
# out — a render is a picture and cannot be argued with, so the argument
# lives here.


def test_there_is_no_countdown_clock():
    """The render showed "00:47" ticking on a team. Our rooms are not
    people: a CPU pick is computed in under a millisecond. A countdown
    would be an animation pretending somebody is deciding on the other
    end, and the first reader who let it run out and watched nothing
    happen would know. The SEAT on the clock is real and is shown."""
    room = APP[APP.index("function mockDraftHTML("):]
    room = room[:room.index("\nfunction _mockRender(")]
    for bad in ("setInterval", "00:", "countdown", "timeLeft", "secondsLeft"):
        assert bad not in room, f"a clock crept into the draft room: {bad!r}"


def test_the_clock_became_a_real_picks_until_you_counter():
    """Ethan, 2026-08-20: "make the clock a real picks-until-your-turn
    counter." Same box, same question ("how long have I got?"), answered
    in the unit a draft actually has.

    IT COUNTS PICKS THAT HAPPEN. A keeper-held slot is skipped rather than
    drafted, so counting the raw index gap would promise twenty-two
    players coming off the board when three of those slots are keepers and
    only nineteen do. `_mockNextTurn` already skips them and this counts
    the same way, so the two cannot disagree about one draft.

    Verified in Chromium against an independent recount that walks the
    draft forward: 26 of 26 steps agreed, through the snake turn."""
    fn = APP[APP.index("function _mockPicksUntil("):]
    fn = fn[:fn.index("\n}")]
    assert "_mockSkipSet(" in fn and "skip.has(" in fn, \
        "the counter counts index positions, not picks that happen"
    assert "_mockNextTurn(" in fn, "it no longer agrees with the draft's own turn order"
    assert "picks: null" in fn or "picks == null" in APP, \
        "no state for 'you have no turn left', which reads as zero"
    # And the button reads the same counter rather than recomputing it.
    room = APP[APP.index("function mockDraftHTML("):]
    room = room[:room.index("\nfunction _mockRender(")]
    assert "until.picks" in room, "the hero or the button grew a second counter"


def test_the_advice_bar_only_appears_when_it_disagrees_with_the_card():
    """Ethan, 2026-08-20, circling the band under the hero: "it feels very
    crouded in the area i slecected." The cause was duplication, not
    spacing: at pick 1.01 the bar read "Best value on the board: Christian
    McCaffrey (RB, VORP +13.6, Tier 1)" while the card beside it showed
    McCaffrey, RB, +13.6, Tier 1. Two full-width bands spent on one fact.

    It now renders only when it has something the card does not — you are
    looking at somebody other than the board's best, or your thinnest slot
    points at a third man. Measured in a browser: absent on open, present
    after clicking the sixth row."""
    fn = APP[APP.index("function _mockAdvice("):]
    fn = fn[:fn.index("\n}\n")]
    assert "selected" in fn.split("{")[0], \
        "the advice cannot know what the card is showing"
    assert "return parts.length ? parts.join(\" \") : null" in fn, \
        "it no longer reports having nothing to say"
    room = APP[APP.index("function mockDraftHTML("):]
    room = room[:room.index("\nfunction _mockRender(")]
    assert "yourTurn && advice ?" in room, \
        "the bar renders even when _mockAdvice returned null"


def test_there_is_no_opposing_defence_panel():
    """The render had "Matchup vs Opponent" — defensive ranks, yards
    allowed, a "+8% Fantasy Boost". There is no opponent in a draft.
    Filling that panel would mean inventing a Week 1 defence for a player
    nobody has drafted, and its slot goes to the question a drafter
    actually has: will he still be there next turn."""
    card = APP[APP.index("function _mockPlayerCardHTML("):]
    card = card[:card.index("\nfunction mockDraftHTML(")]
    assert "Will he last?" in card
    for bad in ("Fantasy Boost", "Allowed (", "vs Opponent", "Matchup Rank"):
        assert bad not in card, f"an in-season matchup panel appeared: {bad!r}"


def test_no_confidence_score_and_no_lock():
    """The render's footer read "QELLYS BOOKS CONFIDENCE: 9.2/10 — LOCK".
    The site's own standing copy is that every number here is a
    probability and not a promise, and "LOCK" is the exact word that
    sentence exists to keep off the page. There is no fitted confidence
    scale behind a fantasy projection, so a 9.2 would be a decoration
    with a decimal point in it."""
    import re
    room = APP[APP.index("/* ============================ THE DRAFT ROOM"):]
    room = room[:room.index("\nfunction _mockRender(")]
    # STRIP THE COMMENTS PROPERLY rather than guessing at line prefixes.
    # Two earlier drafts of this test failed on its own explanation: once
    # on the word "clock" (which contains "lock"), and once on a
    # continuation line inside the block comment that names the banned
    # phrase in order to refuse it. The refusal has to be allowed to say
    # what it is refusing.
    code = re.sub(r"/\*.*?\*/", " ", room, flags=re.S)
    code = re.sub(r"(?m)^\s*//.*$", " ", code)
    word = re.compile(r"\block\b", re.I)
    for line in code.splitlines():
        assert not word.search(line), \
            f"certainty language in output: {line.strip()[:70]}"
    # And no fitted-looking confidence number, which is the other half.
    assert not re.search(r"\b9\.2\b", code)
    assert "/10" not in code, "a ten-point score has no fit behind it"


def test_the_card_and_the_season_sim_share_one_variance():
    """A floor printed on the card and a win total printed by the season
    panel must come from the same assumption, or the page is describing
    two different players. `_mockSpread` reads MOCK_WEEK_CV and calls
    `_mockWeekPoints` — the season simulator's own draw."""
    fn = APP[APP.index("function _mockSpread("):]
    fn = fn[:fn.index("\n}")]
    assert "MOCK_WEEK_CV" in fn and "_mockWeekPoints(" in fn, \
        "the card grew its own variance model"
    assert "MOCK_SEASON_WEEKS" in APP[APP.index("function _mockSpread(") - 400:
                                      APP.index("function _mockSpread(") + 900], \
        "the horizon is not the season panel's, so the two cannot be compared"


def test_the_edge_reads_the_market_map_not_an_array():
    """`m.market` is a Map of player -> slot, built once in _mockStart.
    Reading it with findIndex returns -1 for everybody, which does not
    throw — it silently deletes the whole edge panel. The failure mode is
    an absent feature, so the shape is asserted here."""
    import re
    fn = APP[APP.index("function _mockEdge("):]
    fn = fn[:fn.index("\n}")]
    assert ".get(" in fn, "the market Map is being read as an array"
    # Comments stripped: _mockEdge's own comment NAMES findIndex in order
    # to warn the next reader off it, and an un-stripped check fails on
    # the warning rather than on the mistake. Third time this file has hit
    # that shape today, which is why both checks now strip first.
    code = re.sub(r"(?m)^\s*//.*$", " ", fn)
    assert "findIndex" not in code, "our rank is read off an array again"


def test_a_board_rank_does_not_improve_as_others_are_drafted():
    """`pool` is spliced as players go, so an index into it is a rank
    among WHAT IS LEFT. Ranking against that would make a player climb our
    board every time somebody else was taken, and make his edge over the
    market grow all draft for no reason. A frozen copy is kept."""
    assert "all: pool.slice()" in APP, "the full board is no longer frozen"
    fn = APP[APP.index("function _mockOurRank("):]
    fn = fn[:fn.index("\n}")]
    assert "m.all" in fn, "our rank is measured against the shrinking pool"


def test_the_open_card_can_never_describe_a_drafted_player():
    """The card prices a DECISION — his edge, whether he lasts — and
    neither question means anything about somebody already gone. The
    selection is cleared when you draft, and a click only lands if he is
    still in the pool."""
    bind = APP[APP.index("const selEl = e.target.closest"):]
    bind = bind[:bind.index("\n  });")]
    assert "_mock.pool.some(" in bind, "any name can be selected, drafted or not"
    take = APP[APP.index("} else if (t.dataset && t.dataset.mkp) {"):]
    take = take[:take.index("} else {")]
    assert "_mockSel = null" in take, \
        "the selection survives the pick, so the card describes a taken player"


def test_every_position_has_its_own_tone():
    """The render colour-codes the chips. Own tokens rather than the
    good/bad semantic pair — a running back is not "good" and a
    quarterback is not "a warning", and borrowing those would make every
    board on the site read as a verdict."""
    for pos in ("qb", "rb", "wr", "te"):
        assert f".mk-pos-{pos}" in CSS, f"no tone for {pos.upper()}"
    assert "MOCK_POS_TONE" in APP


def test_the_room_opens_on_the_thing_you_choose_from():
    """The draft board is empty at pick 1.01 by definition — nobody has
    picked — so opening on it hands the reader a blank column beside the
    one thing they came to do."""
    assert 'let _mockTab = "pool"' in APP, \
        "the room opens on a tab that is empty at the first pick"


def test_the_new_room_is_styled():
    for sel in (".mk-hero", ".mk-hero-stats", ".mk-stage", ".mk-card",
                ".mk-edge", ".mk-detail", ".mk-tabs", ".mk-poolrow",
                ".mk-svbar", ".mk-whylist"):
        assert sel in CSS, f"{sel} is unstyled"
    # The hero's gradient goes through a token like every other gradient
    # in the file; one written inline is freelancing outside the system.
    assert "--grad-mkhero" in CSS


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
