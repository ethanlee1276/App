"""Which league you are looking at is not a place you can go.

Ethan, 2026-09-10, on the whole site rather than one page:

    "the sidebar on the left, I feel like could use a little more
    organization … it just needs to make sense how it's organized and
    not feel so cluttered bunch of just random shit thrown everywhere."

Measured before anything moved. Below 900px `.sidebar` is
`position: fixed; transform: translateX(-102%)` — a drawer — so on every
phone, changing league cost a hamburger tap first. That is the
most-changed control on a site covering six leagues, parked behind a
door. And the column put `NFL` and `Long Shots` at the same weight while
they answer different questions: one changes what the page is ABOUT, the
other changes which page you are on.

So the chips left for a strip at the top of `<main>`, where the board
they scope can see them, and the sidebar became a list of places only.

The two failures this file exists to catch are both ones the move
actually produced on the way here:

  * the destinations went out with the chips (Top Picks, Long Shots and
    My Bets had no sidebar row at all for one edit), and
  * five `document.querySelector(".sb-chips …")` call sites kept pointing
    at a container that no longer existed — swipe-to-switch, the games
    filter, the cross-sport door and the standings jump, all silently
    dead, none of them throwing.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    return open(os.path.join(HERE, *parts), encoding="utf-8").read()


HTML = _read("web", "index.html")
CSS = _read("web", "css", "styles.css")
APP = _read("web", "js", "app.js")


def _nocomments_html(src):
    return re.sub(r"<!--.*?-->", " ", src, flags=re.S)


def _nocomments_js(src):
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", " ", src)


def _rule(css, selector):
    """The declarations of the first rule for this exact selector, with
    the stylesheet's prose stripped first — half the arguments in that
    file quote the declarations they replaced."""
    css = re.sub(r"/\*.*?\*/", " ", css, flags=re.S)
    i = css.index(selector + " {")
    return css[i + len(selector) + 2:css.index("}", i)]


def _sidebar():
    body = _nocomments_html(HTML)
    i = body.index('<aside class="sidebar"')
    return body[i:body.index("</aside>", i)]


def _strip():
    body = _nocomments_html(HTML)
    i = body.index('<div class="sportbar"')
    return body[i:body.index("</div>", body.index('class="sportbar-in"'))]


def _sports(block):
    return re.findall(r'data-sport="([a-z]+)"', block)


LEAGUES = ["nfl", "cfb", "mlb", "nba", "wnba", "ufc"]
MARKETS = ["intel", "fantasy", "memes"]


def test_the_league_chips_are_out_of_the_drawer():
    """The whole point of the move. A chip inside `<aside>` is a chip
    behind a hamburger tap on every phone."""
    assert not re.search(r'data-kind="league"', _sidebar()), \
        "a league chip is back inside the sidebar"


def test_the_strip_carries_every_chip_the_sidebar_had():
    """The preservation rule: a reorganisation may move things and may
    not lose them. Six leagues and three markets went in."""
    got = _sports(_strip())
    for code in LEAGUES + MARKETS:
        assert code in got, f"{code} did not survive the move"


def test_the_strip_sits_inside_main_above_the_content_it_scopes():
    """Not between `</aside>` and `<main>`: `.shell` is a two-column
    grid, and a third child there becomes a third TRACK — main drops to
    a second row and the whole site renders under the strip. That is
    what the first version of this did."""
    body = _nocomments_html(HTML)
    assert body.index("<main>") < body.index('<div class="sportbar"'), \
        "the strip is a grid child of .shell, not a child of main"
    assert body.index('<div class="sportbar"') < body.index('<section class="view active"'), \
        "the strip is drawn below the board it scopes"


def test_the_strip_wraps_and_never_scrolls():
    """Nine chips do not fit 390px. A sideways-scrolling strip is the
    draggable bar Ethan caught on 2026-08-18 — it parks wherever the
    finger leaves it with half a chip clipped at the edge. Two rows on a
    phone is the correct answer; a hidden chip is not."""
    r = _rule(CSS, ".sportbar-in")
    assert "flex-wrap: wrap" in r, "the strip stopped wrapping"
    assert "overflow" not in r, "the strip took an overflow rule"
    assert "overflow" not in _rule(CSS, ".sportbar"), \
        "the strip's outer box took an overflow rule"
    assert "white-space: nowrap" not in r


def test_the_group_hairline_is_not_drawn_where_the_row_wraps():
    """Measured at 390px: the six leagues filled line one exactly, so the
    separator became the last thing on that line — a 1px tick against the
    right margin, dividing nothing. Below 760 the wrap does the grouping;
    at 760 and up every chip fits one row and the hairline earns its
    place."""
    css = re.sub(r"/\*.*?\*/", " ", CSS, flags=re.S)
    i = css.index("@media (max-width: 760px) {\n  .sportbar")
    block = css[i:css.index("\n}", i)]
    assert ".sportbar-sep { display: none; }" in block, \
        "the hairline is drawn on a wrapped row"
    assert ".sportbar-sep { display: none; }" not in css.replace(block, ""), \
        "the hairline is gone at every width, including the one it works at"


def test_the_sidebar_kept_every_destination():
    """The chips and the destinations were adjacent in the markup, and
    one over-wide deletion took both — Dashboard, Top Picks, Long Shots,
    Live Now, My Bets and Record all left the column together, leaving
    three of them reachable from nowhere but the phone tab bar."""
    bar = _sidebar()
    for view in ("recommended", "likely", "longshots", "live"):
        assert f'data-view="{view}"' in bar, f"{view} lost its sidebar row"
    for tool in ("mybets", "record"):
        assert f'data-sport="{tool}"' in bar, f"{tool} lost its sidebar row"


def test_nothing_still_reaches_for_the_container_that_moved():
    """`.sb-chips` was the sidebar's chip grid. Every selector naming it
    now matches nothing, and `querySelector` returning null is not an
    error — the feature just stops happening."""
    assert "sb-chips" not in APP, "app.js still looks for the old container"
    assert "sb-chips" not in CSS, "the stylesheet still styles the old container"
    assert "sb-chips" not in HTML


def test_every_chip_lookup_names_the_strip():
    """Five call sites reach for a chip by sport and click it: the
    cross-sport door on a board card, the games-page sport filter, the
    live-game door, the swipe target and the list the swipe chooses
    from. All five must find a real element."""
    js = _nocomments_js(APP)
    hits = re.findall(r'\.([a-z-]+) \.sport-btn\[data-sport', js)
    assert hits, "no chip lookup survives at all"
    for container in hits:
        assert container == "sportbar-in", \
            f"a chip lookup still points at .{container}"
    assert len(hits) >= 4, f"only {len(hits)} chip lookups left"


def test_the_wall_hides_the_strip_too():
    """`body.walled` hid the sidebar, and the chips used to be inside it.
    In `<main>` they are not covered by that rule — the stylesheet's own
    argument for hiding the topbar says why: "a person who has never
    signed in has no use for … a sport switcher"."""
    css = re.sub(r"/\*.*?\*/", " ", CSS, flags=re.S)
    assert "body.walled .sportbar { display: none !important; }" in css, \
        "the sport switcher renders on the pricing wall"


def test_the_chips_still_look_like_chips():
    """They kept the sidebar's fill, hairline and brand-gradient active
    state on the way over — the same active fill `.rec-scope` was matched
    to on 2026-08-24, so the site has one selected-pill look and not two.
    Only the width rule changed: three-to-a-row was right in a 208px
    column and wrong in a full-width strip."""
    r = _rule(CSS, ".sportbar-in .sport-btn")
    assert "border: var(--hairline) solid var(--border)" in r
    assert "background: var(--panel)" in r
    assert "33.3%" not in r, "the chips are still sized for a 208px column"
    active = _rule(CSS, ".sportbar-in .sport-btn.active")
    assert "background: var(--grad-brand)" in active, \
        "the selected league is no longer filled"
    assert "color: var(--brand-ink)" in active


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
            except AssertionError as e:
                fails += 1
                print(f"FAIL {name}: {e}")
            except Exception as e:
                fails += 1
                print(f"ERROR {name}: {type(e).__name__}: {e}")
    print(f"\n{ran - fails} of {ran} tests passed.")
    sys.exit(1 if fails else 0)
