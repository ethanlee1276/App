"""The Messages inbox, and what the parlay slip left behind.

Ethan, 2026-08-25: *"there also should be a way for players to select
props and put them in a parlay so they can parlay props together so they
can send it to there friends"* — and — *"there should be a message button
at the top with an inbox with the messages from friends."*

THE SLIP LEFT on 2026-10-31 (Ethan: "get rid of the parlay button and the
parlay feature ... make the parlay feature an actual button"): no + Parlay
on the cards, no dock, no Parlay Mode. The Parlays page builds two-leg
tickets from our own picks instead (engine/twoleg). What stays pinned here:

  * nothing of the slip is left to draw a dead control;
  * a parlay a friend sent before that still reads in Messages, each leg a
    door to its page, and its legs travel as identity only;
  * the game-row helpers the slip used to own still answer for the cards
    and the game page that ask them;
  * Messages: the view, the envelope and its honest badge, seen-after-read.

Run directly: `python3 tests/test_slip.py`
"""

import os
import sys
from _app import app_js  # noqa: E402  (app.js and the rooms it loads on first use)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


APP = app_js()
HTML = _read("web", "index.html")
CSS = _read("web", "css", "styles.css")


def _fn(marker):
    i = APP.index(marker)
    return APP[i:APP.index("\n}", i)]


# --- the slip ----------------------------------------------------------------

def test_nothing_of_the_slip_is_left_to_draw_a_dead_control():
    assert 'id="qb-slip"' not in HTML, "the dock is back"
    assert "#qb-slip" not in CSS and ".slip-chip" not in CSS
    for gone in ("function slipToggle(", "function slipRender(", "function slipChip(",
                 "SLIP_KEY", "data-slip="):
        assert gone not in APP, gone


def test_a_shared_parlay_still_reads_in_messages_and_travels_as_identity():
    """Tickets friends sent before the slip left still arrive and still
    read: each leg a door (shareDoorAttrs) to its page. The server keeps
    taking a shared ticket's legs as player and market only."""
    i = APP.index("const doors = isParlay")
    doors = APP[i:i + 400]
    assert "shareDoorAttrs(sh.sport, l.player" in doors
    src = _read("server.py")
    assert '"send-parlay"' in src
    social = _read("engine", "social.py")
    assert "MAX_PARLAY_LEGS = 3" in social


def test_a_likelihood_game_row_is_read_as_a_game_row_not_a_player():
    """2026-09-02: the likelihood board began carrying game rows, and
    they DO have a `player` — the pick label, "DET ML". Every
    `r.player ? prop : game` branch would have filed one as a player
    prop and stored a leg naming a player who does not exist. The test
    is `kind`, asked once, in a helper the three call sites share."""
    assert "const isGameRow = (r) =>" in APP
    i = APP.index("const isGameRow = (r) =>")
    assert 'r.kind === "game"' in APP[i:i + 200]
    # The cards still ask it (the slip that owned it left, 2026-10-31).
    assert APP.count("isGameRow(r)") >= 2, "nothing asks the helper: is it dead, or did a branch go back to r.player?"


def test_the_slip_finds_a_row_the_edge_board_never_published():
    """A FLIPPED game row — the side the numbers say lands more often,
    where the edge board backed the other one on price — exists only in
    `most_likely`. A lookup reading `game_bets` alone returns nothing
    and the + Parlay button does nothing at all: the dead-control bug
    this codebase keeps rediscovering. One lookup, both lists, used by
    the slip, the share card and the game page."""
    body = _fn("function findGameRow(id)")
    assert "d.game_bets" in body and "d.most_likely" in body
    assert 'g.kind === "game"' in body
    # The share card and the game page go through the same door (the slip,
    # its third caller, left on 2026-10-31).
    assert "findProp(b.dataset.card) || findGameRow(b.dataset.card)" in APP
    assert "const b = findGameRow(state.propId);" in APP
    assert APP.count("(d.game_bets || []).find((g) => gameBetId(g) === id)") <= 1, \
        "a second bespoke game-bet lookup is how the two drift apart"


def test_the_paper_records_market_column_speaks_english():
    """Every other table on the Record page labels a market through
    `marketWord`, which reads the vocabulary engine/markets ships. The
    Most Likely table printed the raw key — invisible while that book
    held `receptions` and `pass_yds`, plain the moment its game rows put
    `team_total` in the column."""
    i = APP.index("function recLikelySection(")
    body = APP[i:APP.index("\n}", i)]
    assert "escapeHtml(marketWord(m))" in body
    assert "escapeHtml(m)}</span>" not in body


# --- messages ----------------------------------------------------------------

def test_the_messages_view_is_registered_everywhere_a_view_must_be():
    assert 'id="view-messages"' in HTML and 'id="messages-body"' in HTML
    assert '"alerts", "messages", "streak"' in APP.replace("\n", " ") or \
           '"messages"' in APP[APP.index("const VIEW_ORDER"):
                               APP.index("]", APP.index("const VIEW_ORDER"))]
    assert 'if (name === "messages") renderMessages();' in APP


def test_the_topbar_carries_the_envelope_and_an_honest_badge():
    assert 'id="nav-msg"' in HTML
    i = HTML.index('id="nav-msg-badge"')
    assert "hidden" in HTML[i - 200:i + 60], \
        "the badge ships visible — a red dot with nothing behind it"
    body = _fn("function msgBadge()")
    assert "b.hidden = !n" in body
    assert '"9+"' in body, "a 47-message badge would stretch the topbar"


def test_seen_is_marked_after_display_on_the_messages_page_too():
    # Sliced to the finder function that follows — the render-pack
    # rebuild (tabs, filters, requests) grew the body past a fixed
    # window, which is exactly the slice bug the suite keeps relearning.
    i = APP.index("async function renderMessages()")
    body = APP[i:APP.index("async function msgFinderHTML", i)]
    assert "setTimeout" in body and "/api/social/seen" in body
    assert body.index("host.innerHTML") < body.index("/api/social/seen"), \
        "seen fires before the rows are on screen"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
