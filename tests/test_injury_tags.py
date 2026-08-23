"""Injury tags on every roster surface — the layer the Cade Mays report
demanded. Ethan, 2026-08-18: "We need too make sure that every sport is
up to date with all injuries and shit like that."

The injuries PAGE was already right; the gap was everywhere else. The
draft kit ranked a man who broke his wrist the week before and said
nothing; the mock draft would happily let the CPU-adjacent human take
him; a search profile showed a season of yards with no hint the player
was on IR. One cached fetch of the board the injuries page already
builds, one lookup, and a compact colored tag wherever a player's name
is a decision.

Disciplines pinned:

  * RETURNS NEVER TAG. An "Active" cleared-to-play row is the opposite
    of a designation — tagging it would re-create the exact confusion
    the injuries page just fixed.
  * ONE FETCH, CACHED. Every surface reads the same board; nobody
    re-fetches per row.
  * THE SHORT MAP READS LONGEST-FIRST, so "Injured Reserve" cannot
    stop at a shorter key and "Out" matches only when nothing more
    specific did.

Run directly: `python3 tests/test_injury_tags.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"),
           encoding="utf-8").read()


def test_the_board_is_fetched_once_and_cached():
    i = APP.index("async function loadInjuryBoard(")
    body = APP[i:i + 600]
    assert "_injBoard && Date.now() - _injBoardAt" in body
    # boardFetch since 2026-08-20 — the wrapper that tells a refused
    # wire apart from an empty payload. Same URL, same caching.
    assert 'boardFetch("data/injuries.json?t="' in body


def test_a_return_notice_never_tags():
    i = APP.index("function injFind(")
    body = APP[i:APP.index("function injTag(", i)]
    assert "!isReturnRow(r)" in body, \
        "a cleared-to-play row tagging a player re-creates the Mays bug"


def test_every_roster_surface_carries_the_tag():
    # The kit's three row kinds.
    assert APP.count('injTag("nfl", r.player)') >= 3
    # The mock draft's shared identity block tags every row at once.
    i = APP.index("const idBlock = (p, meta)")
    assert 'injTag("nfl", p.player)' in APP[i:i + 300]
    # Search profiles, the Also-matching rows and the roster-directory
    # fallback DERIVE their league instead of naming one.
    #
    # THE PROPERTY, NOT THE CHARACTERS. This counted the exact string
    # `injTag(state.sport || "nfl"` and went red on 2026-08-23 when two of
    # the three became MORE sport-aware, not less: a cross-league search
    # result now prefers its own league (`m.sport || state.sport`), which
    # is the whole point of searching every league at once. Pinning the
    # spelling made the fix look like the regression.
    import re
    derived = [a for a in re.findall(r"injTag\(([^,]+),", APP)
               if "state.sport" in a or a.strip() in ("sport", "lg")
               or "sport" in a and not a.strip().startswith('"')]
    assert len(derived) >= 3, f"only {len(derived)} sport-aware injTag calls"
    # And a searched row prefers its OWN league over the tab it is drawn on.
    assert any("m.sport ||" in a for a in derived), \
        "a cross-league hit is tagged from whichever tab you happen to be on"
    # The Sleeper "My roster" rows tag, and the card leads with NAMES —
    # a count would send the manager hunting through his own list.
    assert 'injTag("nfl", r.name)' in APP
    assert "Carrying a designation:" in APP
    # The dossier carries the whole sentence, compact card and full page.
    assert "info.inj = injFind(" in APP
    assert "${injLineHTML(info.inj)}" in APP
    assert 'injLineHTML(injFind("nfl", p.player))' in APP


def test_the_cpu_reads_the_injury_report():
    """A multiplier, not a ban: OUT/IR-tier weight collapses, a warn-tier
    tag barely registers, and the human can still draft anyone."""
    i = APP.index("function _mockHealth(")
    body = APP[i:APP.index("\n}", i)]
    assert "injFind(" in body and "0.25" in body
    j = APP.index("function _mockCpuPick(")
    body = APP[j:APP.index("\n}", j)]
    assert "_mockHealth(p.player)" in body, "the drafting CPU stopped reading it"
    # And the Monte Carlo that PREDICTS that CPU has to weigh it the same
    # way, or the survival odds describe a room that ignores injuries
    # while the room drafting does not.
    k = APP.index("function mockSurvival(")
    sim = APP[k:APP.index("\n}\n", k)]
    assert "_mockHealth(" in sim, \
        "the predictor ignores the injury report the drafting room reads"


def test_the_draft_day_panels_tag_too():
    """The live-sync Best available chips and the advice's "take" are the
    two places a draft-day decision actually gets made."""
    i = APP.index("function dkBestAvailable(")
    body = APP[i:APP.index("\n}", i)]
    assert body.count('injTag("nfl"') == 2, \
        "both the overall chips and the by-position chips must tag"
    j = APP.index("async function dkAdvice(")
    assert 'injTag("nfl", take.player)' in APP[j:APP.index("\n}", j)]


def _fnbody(name):
    """A function's body by brace matching, not by a byte count.

    The version this replaces read `APP[i:i + 700]` and broke on
    2026-08-22 for the eighth time this session — not because the code
    stopped loading the injury board, but because a comment was added
    above the call and pushed it 40 characters past the window. A test
    that fails when you explain the line above it is measuring the
    wrong thing. (There are ~386 more of these across tests/; this
    fixes the one that was actually failing.)
    """
    start = APP.index(name)
    depth, seen = 0, False
    for j in range(APP.index("{", start), len(APP)):
        if APP[j] == "{":
            depth, seen = depth + 1, True
        elif APP[j] == "}":
            depth -= 1
            if seen and not depth:
                return APP[start:j + 1]
    raise AssertionError(name + " never closes")


def test_the_pages_load_the_board_before_painting():
    assert "loadInjuryBoard()" in _fnbody("async function renderFantasy("), \
        "fantasy renders synchronously from its payload — the board must ride the same await"
    assert "await loadInjuryBoard()" in _fnbody("async function renderPlayers(")


def test_the_short_map_reads_longest_first():
    i = APP.index("const INJ_SHORT = [")
    block = APP[i:APP.index("];", i)]
    assert block.index('"injured reserve"') < block.index('["out"'), \
        "a substring key matching first mislabels the specific status"
    assert block.rstrip().endswith('["out", "OUT"],'), \
        '"out" is the least specific key and must be the last resort'


def test_the_tag_is_styled():
    assert ".inj-tag {" in CSS
    assert ".ffd-injline {" in CSS


# ---- The pick's own player, on the pick's own card (2026-08-20) --------
# Ethan: "push injuries/weather signals into the board rather than beside
# it." The watch box answers "who is hurt tonight"; the card has to answer
# the only version of that question it is about — is the man we are
# betting on hurt. The environment half is pinned in tests/test_envband.py.

def test_the_card_carries_the_note_above_the_models_own_warnings():
    """A wire report is a different KIND of fact from a sentence the model
    wrote, and it is the one that decides whether to read the rest."""
    i = APP.index("function cardHTML(r) {")
    body = APP[i:APP.index("</article>", i)]
    assert "${pickInjuryNote(r)}" in body, "the card lost the injury note"
    assert body.index("${pickInjuryNote(r)}") < body.index("${warnings}"), \
        "the wire report was pushed below the model's own warnings"


def test_the_note_is_a_note_and_never_a_gate():
    """A card must not quietly become a different card because a fetch was
    slow. The feed can be cold, late or missing; none of that may change
    which picks exist or what they are staked at."""
    i = APP.index("function pickInjuryNote(")
    j = APP.index("\nfunction ", i + 1)
    body = APP[i:j]
    for banned in ("recommended", "stake", "_ok", "r ="):
        assert banned not in body, \
            f"pickInjuryNote touches {banned!r} — it decides display, nothing else"
    assert re.search(r"\br\.\w+\s*=[^=]", body) is None, \
        "pickInjuryNote writes back onto the pick it was handed"


def test_one_file_has_one_cache():
    """The box beside the board and the note on the card read the same
    data/injuries.json. Two caches with two TTLs meant the box could call a
    man questionable while his own card said nothing — the exact
    disagreement the box exists to prevent."""
    assert "_injCache" not in APP, "a second injury cache is back"
    i = APP.index("async function renderInjuryWatch(")
    body = APP[i:APP.index("\nfunction ", i)]
    assert "await loadInjuryBoard()" in body, \
        "the watch box fetches the board on its own again"
    # Three readers: the injuries page, the watch box, the note on each
    # card. Exactly one of them may own the fetch.
    assert APP.count('boardFetch("data/injuries.json') == 1, \
        "data/injuries.json is fetched from more than one place again"
    i = APP.index("async function renderInjuries(")
    page = APP[i:APP.index("\nfunction ", i)]
    assert "await loadInjuryBoard()" in page, \
        "the injuries page fetches the board on its own again"


def test_a_feed_that_lands_late_redraws_the_board_once():
    """cardHTML is synchronous and runs before this await resolves, so on a
    cold load every note came back empty — and would stay empty for the
    life of the page. Once, on the first landing, not on every refresh:
    re-rendering on the ten-minute cycle would restart the card reveal
    animation under a reader mid-scroll."""
    i = APP.index("async function renderInjuryWatch(")
    body = APP[i:APP.index("\nfunction ", i)]
    assert "const cold = !_injBoard;" in body
    assert "if (cold && _injBoard) renderRecommended();" in body, \
        "a cold feed no longer redraws the cards"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
