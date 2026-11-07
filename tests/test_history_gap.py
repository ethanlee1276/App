"""Games on the schedule, no props, and no explanation anywhere.

Reported: "wnba isnt displaying any props at all". The WNBA season is
running in August, so this was not an offseason board.

Every prop on the hoops boards is projected from stored player game logs —
`player_history()` reads `player_game_logs`, and a player needs three games
before a prop is built. That database had never been ingested for the WNBA,
so the schedule loaded, the games rendered, and zero props came out.

The gap itself is a one-command fix. What made it a bug rather than a chore
is that NOTHING said so. `renderEmptySlate` only fires when there are no
GAMES, so on a night with games it never ran, and the board showed a slate
with an empty pick list — visually identical to a night where the model
looked at everything and liked nothing. Those two are opposite facts and
they need opposite responses.

Also pinned here: the "More" menu opened to the LEFT of its own button.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


JS = _read("web", "js", "app.js")
CSS = _read("web", "css", "styles.css")
BUILD = _read("nba_build.py")


# --- the build has to notice -----------------------------------------------
def test_the_build_reports_games_with_no_props_as_a_gap():
    i = BUILD.index('if games and not slate.props:')
    block = BUILD[i:i + 1200]
    assert '"history_gap"' in block, "the gap never reaches the page"
    for field in ("players_found", "seasons", "teams"):
        assert field in block, f"the payload omits {field}"


def test_the_fix_command_names_the_league_being_built():
    """`python3 ingest.py nba` on the WNBA board would run for two hours and
    change nothing about the page you were looking at.

    It is now printed only in the TERMINAL — see the test below for why —
    so this checks the line that still exists rather than the payload
    field that was removed."""
    i = BUILD.index('if games and not slate.props:')
    block = BUILD[i:i + 1600]
    assert "ingest.py {args.league}" in block
    assert '"fix"' not in block, "the command is back in the public payload"


def test_the_repair_command_never_reaches_the_public_payload():
    """Ethan, 2026-08-23, with an operator instruction circled on the live
    site: "lets get all the little things like this telling ME what to do
    off the website since this website is live for anyone to use."

    history_gap is served to every visitor. It carried the shell command
    that repairs the gap, and the page printed it in a <code> block — so
    the site handed its own to-do list to people who cannot run it and
    should never have been shown it. The instruction belongs in the
    terminal, where the person who can act on it is standing, and the
    print below still carries it."""
    i = BUILD.index('if games and not slate.props:')
    block = BUILD[i:i + 1600]
    payload = block[block.index('out["history_gap"]'):]
    payload = payload[:payload.index("}")]
    assert "python3" not in payload and "ingest.py" not in payload, (
        "the payload is instructing the reader again")
    assert 'print(f"    Fix: python3 ingest.py' in BUILD, (
        "the terminal lost the instruction too — this was a move, not a "
        "deletion")


def test_it_only_fires_when_there_are_games():
    """An offseason board has no games AND no props, and that is a different
    message — the one about nothing being scheduled."""
    assert "if games and not slate.props:" in BUILD


def test_the_terminal_says_it_too():
    i = BUILD.index('if games and not slate.props:')
    block = BUILD[i:i + 1200]
    assert "NO props to build" in block
    assert "3+ games" in block, "nothing states the threshold that was missed"


# --- the page has to show it ------------------------------------------------
def _empty_fn():
    start = JS.index("function renderEmptySlate()")
    return JS[start:JS.index("\n}\n", start)]


def test_the_page_renders_the_gap_even_though_games_exist():
    """The bug: renderEmptySlate returned early whenever games were present,
    so on the exact night this matters it never ran."""
    fn = _empty_fn()
    gap_at = fn.index("state.data.history_gap")
    early_return = fn.index("if (!noGames || !el)")
    assert gap_at < early_return, \
        "the history gap is checked after the early return that skips it"


def test_the_message_says_what_is_missing_without_issuing_an_order():
    """It used to print the repair command. What a READER needs is the two
    facts underneath it: this is a data gap, not a verdict on the games,
    and it clears on its own."""
    fn = _empty_fn()
    block = fn[fn.index("state.data.history_gap"):]
    assert "gap.fix" not in fn, "the command is back on the page"
    assert "<code>" not in block, "something is still being quoted as a shell line"
    assert "have not been loaded yet" in block
    assert "fills on the refresh" in block, (
        "nothing tells the reader it resolves without them")


def test_the_message_does_not_blame_the_model():
    """"No qualifying plays" is a verdict on prices. This is not that, and
    saying so is the whole point of the panel."""
    fn = _empty_fn()
    block = fn[fn.index("state.data.history_gap"):]
    assert "no player history" in block
    assert "Nothing is broken" in block


def test_the_games_stay_visible_under_the_gap():
    """The schedule is real. Hiding it would turn a data gap into a
    different lie."""
    fn = _empty_fn()
    block = fn[fn.index("state.data.history_gap"):]
    assert 'games-title").style.display = ""' in block


def test_the_panel_moves_up_for_a_gap_and_back_afterwards():
    """It normally sits eighth in the view, which is fine when everything
    above it is empty too. With games present that put it ~900px down, past
    where anyone had already decided the site was broken. Moving a node on
    one render must not leave it moved on the next."""
    fn = _empty_fn()
    assert "anchor.after(el)" in fn
    assert "homeIndex" in fn, "no way back to the original position"
    assert "delete el.dataset.homeIndex" in fn


# --- the More menu ----------------------------------------------------------
def test_the_more_menu_opens_under_its_own_button():
    """The More menu is gone (NEW LOOK, 2026-08-11): its whole reason to
    exist was a header with no room, and the sidebar has room for every
    destination. What must survive redesigns is the DESTINATIONS — Why Us
    and About stay reachable, one click, no popover."""
    html = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    assert 'data-sport="why"' in html and 'data-sport="about"' in html
    assert html.index('data-sport="why"') > html.index('id="sidebar"')

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
