"""The football and baseball scoreboard has a column for every block in it.

Ethan, 2026-09-06, circling the top card on his phone: "this area on the
play by play screen is bugged out." The header then was five children (away
block, away score, the state, home score, home block) and the phone rule
lifted the state onto a row of its own while handing the other four THREE
columns, so the home block wrapped under the away team. The day after, with
the state lifted, the two scores sat one grid gap apart and read as one
number ("2 3", ringed: "fix how bunched up these number are").

Since 2026-10-27 the header is the basketball page's scoreboard (Ethan,
circling the NBA's: "We want all of these too look like nba for all
sports"): three blocks, the away side, the clock, the home side, on every
width. Each side carries its own score, so the clock always stands between
the two numbers, on a phone as on a desk, and nothing is lifted out of the
row. These hold that shape:

  - the board is three blocks and every layout gives it three columns;
  - the home side mirrors the away side (its crest on the outside, its
    score toward the clock), on a desk and on a phone;
  - the watch buttons are a row of their own under the board, not a block
    in it (tests/test_the_live_scoreboard_on_a_phone.py measures it).

The test counts rather than matching a literal, so a fourth block added to
the board fails here instead of silently wrapping on someone's phone.
"""

import re
import sys
from pathlib import Path

from _app import app_js, styles_css  # noqa: E402  (app.js and its rooms; every sheet)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APP = app_js()
CSS = styles_css()
SHEET = (ROOT / "web" / "css" / "detail.css").read_text(encoding="utf-8")

BOARD = APP[APP.index("function pbpBoardHTML("):APP.index("async function renderPbpPage(")]
CARD = BOARD[BOARD.index('<div class="card pbp-hero"'):]


def _tracks(decl):
    """How many columns a grid-template-columns value declares."""
    return len(re.findall(r"(?:minmax\([^)]*\)|[\d.]+fr|auto|[\d.]+px)", decl))


def _board_rule(media=None):
    hay = SHEET
    if media:
        i = SHEET.index(f"@media (max-width: {media}px) {{\n  .pbp-hero {{")
        hay = SHEET[i:SHEET.index("\n}\n", i)]
    m = re.search(r"\.pbp-hero \{[^}]*grid-template-columns:\s*([^;}]+)", hay)
    assert m, f"no board grid rule (media={media})"
    return m.group(1).strip()


def _blocks():
    """The board's own children: the two sides and the clock between them."""
    return (len(re.findall(r'\$\{side\("(?:away|home)"\)\}', CARD))
            + len(re.findall(r'<div class="pbp-sb-mid">', CARD)))


def test_the_board_is_three_blocks_the_clock_between_the_sides():
    assert _blocks() == 3, CARD[:400]
    assert CARD.index('${side("away")}') < CARD.index('<div class="pbp-sb-mid">') < CARD.index('${side("home")}')


def test_every_layout_has_a_column_per_block():
    assert _tracks(_board_rule()) == _blocks()
    assert _tracks(_board_rule(media=720)) == _blocks(), "the phone keeps the clock between the sides"
    # Nothing is lifted out of the row any more: the clock is the divider.
    assert not re.search(r"\.pbp-sb-mid \{[^}]*grid-column:\s*1 / -1", SHEET)


def test_the_home_side_mirrors_the_away_side():
    desk = re.search(r"(?m)^\.pbp-sb-side\.home \{([^}]*)\}", SHEET)
    assert desk and "row-reverse" in desk.group(1) and "text-align: right" in desk.group(1), desk
    phone = SHEET[SHEET.index("@media (max-width: 720px) {\n  .pbp-hero {"):]
    phone = phone[:phone.index("\n}\n")]
    assert 'grid-template-areas: "crest pts" "team team"' in phone
    assert 'grid-template-areas: "pts crest" "team team"' in phone


def test_the_watch_row_is_not_a_block():
    assert CARD.index('${side("home")}') < CARD.index('watchHTML(d, league, "pbp-watch")')
    assert ".pbp-hero > .pbp-watch { grid-column: 1 / -1; margin-top: 0; }" in CSS


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
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
