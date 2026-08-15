"""The preseason on the site: a fixture list, and nothing priced.

Ethan asked for the NFL preseason on the board. It is the one part of the
calendar where this engine's premise fails — a projection is volume times
efficiency measured over prior games, and in August a starter plays a
series and a half behind a line that will not start together again — so
what shipped is schedules and scores, with the no-pricing boundary held in
three places rather than remembered:

  * `nflpreseason.py` refuses to price at all (test_nflpreseason.py)
  * `board_payload` carries no field a price could hide in
  * the rendered block says so in its own copy

WHY A BLOCK AND NOT A TAB. It is live for about five weeks a year. A nav
tab would say nothing for the other eleven months, on a header that was
already 11 buttons wide and had to be rebuilt this week to fit. The block
retires itself by comparing today against the last fixture's date, so it
is not something anyone has to remember to take down in September.

WHY ONE WEEK IS OPEN. All four expanded is 49 rows and 2,168px — measured
— which is more than a screen, below the picks, for a list whose useful
part is "what is on next". The first week with a game still to play is
open; the rest fold to a line that says enough to know whether to look.

Run directly: `python3 tests/test_preseason_board.py`
"""

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.sources import nflpreseason as pre                     # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _event(eid, date, home, away, week, hs=None, as_=None, state="pre"):
    def side(ab, sc, ha):
        return {"homeAway": ha, "team": {"abbreviation": ab},
                "score": "0" if sc is None else str(sc)}
    return {"id": str(eid), "date": f"{date}T23:00Z", "week": {"number": week},
            "competitions": [{"venue": {"fullName": "X", "indoor": False},
                "competitors": [side(home, hs, "home"), side(away, as_, "away")],
                "status": {"type": {"state": state,
                                    "completed": state == "post"}}}]}


def _season():
    """A miniature of the real 2026 shape: week 1 the Hall of Fame game
    alone and already final, then two more weeks still to come."""
    return pre.parse_games({"events": [
        _event(1, "2026-08-07", "CAR", "ARI", 1, 30, 33, "post"),
        _event(2, "2026-08-13", "CIN", "CLE", 2),
        _event(3, "2026-08-14", "BAL", "BUF", 2),
        _event(4, "2026-08-21", "DET", "GB", 3),
    ]}, 2026)


# --- the payload -------------------------------------------------------------
def test_it_groups_by_week_in_order():
    p = pre.board_payload(_season(), 2026, today=dt.date(2026, 8, 8))
    assert [w["week"] for w in p["weeks"]] == [1, 2, 3]
    assert [len(w["games"]) for w in p["weeks"]] == [1, 2, 1]


def test_the_span_and_the_counts_are_the_fixtures_own():
    p = pre.board_payload(_season(), 2026, today=dt.date(2026, 8, 8))
    assert (p["first"], p["last"]) == ("2026-08-07", "2026-08-21")
    assert p["total"] == 4 and p["complete"] == 1
    assert p["season"] == 2026


def test_show_until_is_the_last_fixture_and_that_is_the_whole_retirement():
    """The block draws itself only while today <= show_until. If this ever
    stops being the last date, the preseason stays on the board into
    October — or vanishes mid-August."""
    p = pre.board_payload(_season(), 2026, today=dt.date(2026, 8, 8))
    assert p["show_until"] == p["last"] == "2026-08-21"


def test_days_until_uses_the_caller_s_clock():
    games = _season()
    assert pre.board_payload(games, 2026, today=dt.date(2026, 8, 1))["days_until"] == 6
    assert pre.board_payload(games, 2026, today=dt.date(2026, 8, 9))["days_until"] == -2


def test_an_empty_schedule_does_not_crash_the_payload():
    p = pre.board_payload([], 2026, today=dt.date(2026, 8, 8))
    assert p["total"] == 0 and p["weeks"] == []
    assert p["first"] is None and p["show_until"] is None


def test_games_inside_a_week_are_in_kickoff_order():
    p = pre.board_payload(_season(), 2026, today=dt.date(2026, 8, 8))
    wk2 = [w for w in p["weeks"] if w["week"] == 2][0]
    assert [g["date"] for g in wk2["games"]] == ["2026-08-13", "2026-08-14"]


# --- nothing priced ----------------------------------------------------------
def test_the_payload_has_nowhere_to_put_a_price():
    """Not "we chose not to fill these" — the fields do not exist. A board
    that carried a null `edge` would be one commit from showing one."""
    p = pre.board_payload(_season(), 2026, today=dt.date(2026, 8, 8))
    banned = {"edge", "hit_prob", "projection", "odds", "line", "stake_units",
              "confidence", "grade", "pick", "recommended"}
    def walk(o, path="payload"):
        if isinstance(o, dict):
            for k, v in o.items():
                assert k not in banned, f"{path}.{k}"
                walk(v, f"{path}.{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, f"{path}[{i}]")
    walk(p)


def test_the_block_says_out_loud_that_the_numbers_are_not_ours():
    """A schedule sitting under a board of picks reads as picks unless it
    says otherwise, and the reader who needs telling is the one who will
    not go looking for a docstring.

    THE WORDING CHANGED ON 2026-08-14 AND HAD TO. This block used to claim
    "nothing here is priced", which was true when it showed only a
    schedule. It now carries the BOOK's posted spread, total and moneyline
    — Ethan: "i wanna show ... either money lines or over unders or
    whatever i dont car" — so the old sentence would have been a false
    statement sitting directly above a price. The claim that survives, and
    the one that actually matters, is that none of those numbers are ours.
    """
    js = _read("web", "js", "app.js")
    i = js.index("async function renderPreseason(")
    # Whitespace-normalised: this is copy inside a template literal, so it
    # wraps wherever the source line ended and a contiguous-substring match
    # fails on prose that is present and correct.
    block = " ".join(js[i:i + 2600].split())
    assert "nothing here is ours" in block
    assert "a number about a different event" in block


def test_the_block_explains_why_there_is_a_line_and_no_pick():
    """Showing a market number without saying why we are not answering it
    is the gap this feature could most easily fall into."""
    js = _read("web", "js", "app.js")
    i = js.index("async function renderPreseason(")
    block = " ".join(js[i:i + 2600].split())
    assert "preseasonFitHTML(data)" in block


# --- it is on the page, and it leaves ----------------------------------------
def test_the_board_has_a_host_and_it_is_rendered():
    html = _read("web", "index.html")
    assert 'id="preseason-board"' in html
    js = _read("web", "js", "app.js")
    assert "renderPreseason();" in js, "defined but never called"
    assert "async function renderPreseason(" in js


def test_it_sits_under_the_picks():
    """Directly below the picks, because in August it is the only football
    being played — but still below them, so the preseason never outranks a
    priced board.

    It used to also sit ABOVE the venue scroller. That stopped being true
    when Ethan moved the venues to the top of the page on 2026-08-08; the
    order there is his call and lives in test_board_order.py. What this
    still guards is the part that is about the preseason: it does not climb
    over the picks.
    """
    html = _read("web", "index.html")
    assert html.index('id="best-bets"') < html.index('id="preseason-board"')


def test_it_retires_itself_on_the_last_fixture():
    js = _read("web", "js", "app.js")
    i = js.index("async function renderPreseason(")
    block = js[i:i + 2600]
    # Anchor on the CODE, not the prose: the comment above it explains the
    # mechanism and mentions show_until first, so a bare substring search
    # measured the comment and reported the guard missing.
    i = block.index("data.show_until")
    assert "return" in block[i:i + 90], block[i:i + 90]


def test_it_draws_for_nfl_only():
    js = _read("web", "js", "app.js")
    i = js.index("async function renderPreseason(")
    assert '!== "nfl"' in js[i:i + 600]


def test_only_one_week_is_open():
    js = _read("web", "js", "app.js")
    i = js.index("async function renderPreseason(")
    block = js[i:i + 2600]
    assert "openWeek" in block
    assert "2,168px" in block or "2168" in block, \
        "the measurement that decided this is not written down"


def test_kickoffs_render_in_local_time_not_the_feeds_utc():
    """ESPN stamps kickoffs Z. Printed raw that put "23:00 UTC" beside every
    fixture — a number nobody reading this is in, on a schedule whose whole
    job is saying when to watch."""
    js = _read("web", "js", "app.js")
    i = js.index("function preseasonScoreHTML(")
    block = js[i:i + 1400]
    assert "toLocaleTimeString" in block
    assert "UTC" not in block.split("toLocaleTimeString")[1][:200]


def test_the_label_comes_from_state_not_from_a_number():
    """ESPN sends score "0" for a game nobody has played, so "has a score"
    and "has been played" are different questions — asking the wrong one
    tagged 48 scheduled fixtures as in progress on the first real run."""
    js = _read("web", "js", "app.js")
    i = js.index("function preseasonScoreHTML(")
    block = js[i:i + 900]
    assert 'g.state === "post"' in block and 'g.state === "in"' in block


# --- it runs without being asked ---------------------------------------------
def test_the_launcher_refreshes_it_every_launch():
    """A schedule that only updates when somebody remembers is a schedule
    that is wrong on the night it matters."""
    src = _read("launch.py")
    assert "def refresh_preseason(" in src
    assert "refresh_preseason(quiet=quiet)" in src
    i = src.index("def refresh_all(")
    assert "refresh_preseason" in src[i:i + 700]


def test_being_out_of_season_is_silent_not_a_warning():
    """`preseason_games` raises for eleven months of the year, which is the
    correct answer. A launcher that warns about it daily trains the reader
    to ignore the line that will one day mean something."""
    src = _read("launch.py")
    i = src.index("def refresh_preseason(")
    block = src[i:i + 1800]
    j = block.index("except DataUnavailable")
    assert "return False" in block[j:j + 120]
    assert "print" not in block[j:j + 120]


def test_the_cli_can_write_it_too():
    src = _read("nflpre.py")
    assert "def write_board(" in src and '"--out"' in src


# --- the pointer, which was a dead button ------------------------------------
#
# Ethan, 2026-08-15: "The pre season board button doesn't do anything and
# isnt displaying anything."
#
# He was right twice over, and it was one fault. `subtabbedDOM` re-parents
# Recommended into panels and hides all but the active one with
# display:none; `REC_ROOMS` files `preseason-board` under Watchlists while
# the page opens on Tonight's board. So the block rendered its HTML into a
# panel with no box — measured at 3,542 characters and 0 pixels — and the
# "Preseason is what is being played now →" link was a native anchor to a
# target the browser could not scroll to. Clicking moved the address bar
# and nothing else.
#
# The general rule this pins: ANY in-page anchor on a sub-tabbed page has
# to open the room before it scrolls, or it is a dead button.
def test_the_preseason_block_really_does_live_inside_a_sub_tab():
    """The precondition. If it ever moves to the first room this stops
    being necessary — and these tests should be read again, not deleted,
    because the reveal is what makes EVERY such link work."""
    js = _read("web", "js", "app.js")
    i = js.index("const REC_ROOMS = [")
    rooms = js[i:js.index("\n];", i)]
    assert '"preseason-board"' in rooms
    first_room = rooms[:rooms.index('["gamebets"')]
    assert "preseason-board" not in first_room, \
        "it is in the default room now; the anchor no longer needs revealing"


def test_the_jump_opens_the_room_before_it_scrolls():
    js = _read("web", "js", "app.js")
    assert "function revealAnchor(" in js
    i = js.index("function revealAnchor(")
    body = js[i:js.index("\nfunction ", i + 1)]
    # It must go through the real tab button, not flip `hidden` blind: the
    # handler also moves the bar highlight, aria-selected, the roving
    # tabindex and the hint. Setting hidden alone shows one room while the
    # bar claims another, which is a worse bug than the one being fixed.
    assert "btn.click()" in body
    assert ".subgroup" in body and "subnav-btn" in body


def test_the_pointer_click_is_bound_to_the_reveal():
    js = _read("web", "js", "app.js")
    i = js.index("function renderSlateHorizon(")
    body = js[i:js.index("\nfunction ", i + 1)]
    assert "a.slate-jump" in body
    assert "revealAnchor(" in body and "scrollIntoView" in body
    assert "preventDefault" in body


def test_a_pasted_or_reloaded_anchor_works_too():
    """The hash sticks in the URL after a click, so a refresh or a shared
    link hits the router rather than the click handler. Without this the
    same link is dead again by another route."""
    js = _read("web", "js", "app.js")
    i = js.index('window.addEventListener("hashchange"')
    body = js[i:i + 2200]
    reveal = body.index("revealAnchor(")
    bail = body.index("if (!VIEW_ORDER.includes(h) || !document.getElementById(")
    assert reveal < bail, \
        "the VIEW_ORDER bail-out runs first, so in-page anchors never reach the reveal"


def test_the_jumped_to_block_clears_the_sticky_masthead():
    """`block: "start"` puts the element at y=0, and the topbar is sticky
    at 64px (measured in Chromium at 1280 and 390), so the heading landed
    behind it — which reads as the link having gone somewhere wrong."""
    css = _read("web", "css", "styles.css")
    i = css.index("#preseason-board")
    rule = css[i:i + 90]
    assert "scroll-margin-top" in rule
    px = int(rule.split("scroll-margin-top:")[1].split("px")[0].strip())
    assert px >= 64, f"{px}px does not clear the 64px masthead"


def test_a_dead_menu_anchor_says_so_instead_of_doing_nothing():
    """The third way this bug can come back, closed.

    The sidebar menu items scroll to a block by id. Every id there is our
    own `data-anchor`, so `revealAnchor` returning null does not mean "an
    ordinary page anchor the browser could still handle" — it means the
    block was renamed or deleted, and the menu item now navigates home and
    stops. That is exactly what Ethan reported about the preseason button:
    "doesn't do anything and isn't displaying anything."

    The two other call sites are allowed to fall through quietly, and
    should: the slate jump hands an unknown hash back to the browser, and
    the hashchange router checks the element exists before it reveals.
    Only this one is a guaranteed defect, so only this one shouts — and it
    shouts through console.error, which the headless render sweep already
    fails on. That turns a future dead menu item from a bug report into a
    red line in `launch.py --check`.
    """
    js = _read("web", "js", "app.js")
    i = js.index("revealAnchor(b.dataset.anchor)")
    block = js[i:i + 700]
    assert "console.error" in block, \
        "a missing menu target is swallowed again — silent dead button"
    assert "dead menu anchor" in block
    # And it must not then try to scroll a null.
    assert block.index("console.error") < block.index("scrollIntoView")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
