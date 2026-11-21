"""The Player stats room was prose where a box score belongs.

Ethan, 2026-09-10, on the play-by-play page during Patriots at
Seahawks: "make this look better and more organized and just more
visually appealing" — and of the Game info room below it, "we should be
showing more information and fix the wording."

Player stats read one wrapped line per player: `Rec Yds 19 · Receptions
4 · Targets 5`, every number carrying its own label because there was no
column to inherit one from, in whatever order the parser filled the
fields. Nothing was wrong with the numbers and nothing could be
compared — finding who led the club in targets meant reading eleven
sentences and holding the figures in your head.

Game info was three weather chips over half a screen of nothing, and one
of them read `Roof: outdoors` over `fieldturf`: a label and a value that
are not a pair, and a proper noun with no capital letter.

WHAT THIS FILE GUARDS is not the styling — it is the honesty rules the
tables live under, because they are the kind of thing that gets "tidied"
later by someone who cannot see why they are there: every key the fantasy
points read is a market the parsers actually write, every drive field is
one `football_drives` actually emits, and every table is one a screen reader
can read.

The player tables this file first guarded (pbpPlayersHTML, football split
into three; "a column nobody filled is not drawn") went on 21 November, step
AAN: since step AAK every league's box score is the one game page's own card
(gpBoxCardHTML), and their fantasy points are a card under it.
"""

import json
from _app import styles_css  # noqa: E402  (styles.css and every room's own sheet)
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from _app import app_js  # noqa: E402  (app.js and the rooms it loads on first use)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APP = app_js()
CSS = styles_css()


def _fn(name):
    i = APP.index(f"function {name}(")
    ends = [APP.find(m, i + 10)
            for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ", "\n/*:")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return APP[i:min(ends)]


def _block(start, end):
    i = APP.index(start)
    return APP[i:APP.index(end, i) + len(end)]


def _line(start):
    i = APP.index(start)
    return APP[i:APP.index("\n", i)]


# --- the keys are real ------------------------------------------------------
def test_every_fantasy_point_reads_a_market_a_parser_writes():
    """The fantasy points invent no field. Each key must appear in the parser
    that names markets for that league, or the points count numbers nobody
    produces."""
    src = _fn("pbpFantasyPts")
    keys = set(re.findall(r'n\("([a-z_]+)"\)', src))
    assert len(keys) >= 8, keys
    parsers = "\n".join((ROOT / "engine" / "sources" / f).read_text()
                        for f in ("nflpreseason.py", "cfbdata.py"))
    for k in sorted(keys):
        assert f'"{k}"' in parsers or f"'{k}'" in parsers, \
            f"{k} is a column head for a market no parser writes"


def test_every_team_total_reads_a_field_the_drive_builder_emits():
    src = _fn("pbpTeamTotals")
    drives = (ROOT / "engine" / "sources" / "espnplays.py").read_text()
    entry = drives[drives.index('entry = {'):drives.index("if did not in by_id")]
    for field in ("team", "offensive_plays", "yards", "elapsed"):
        assert f"dr.{field}" in src or f'"{field}"' in src, f"{field} unread"
        assert f'"{field}"' in entry, f"{field} is not a field football_drives writes"
    # The per-play flags come off `_football_row`, not from anywhere new.
    row = drives[drives.index("def _football_row("):drives.index("def football_drives(")]
    for flag in ("turnover", "penalty", "scoring"):
        assert f"pl.{flag}" in src, flag
        assert f'"{flag}"' in row, f"{flag} is not a field the play row carries"


# --- the honesty rule, in a browser ----------------------------------------
def _node(tail):
    node = shutil.which("node")
    if not node:
        return None
    prog = "\n".join([
        'const escapeHtml = (s) => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;");',
        'const marketWord = (k) => String(k).replace(/_/g," ");',
        'const PBP_FOOTBALL = new Set(["nfl", "cfb"]);',
        'const teamMarkIn = () => ""; const teamNameIn = (l, a) => a;',
        _line("const pbpStat = "),
        _fn("pbpFantasyPts"), _fn("pbpFantasyHTML"),
        _fn("pbpClockSecs"), _line("const pbpSecsClock = "),
        _fn("pbpTeamTotals"), _fn("pbpTotalsHTML"),
        tail,
    ])
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_team_totals_are_arithmetic_over_the_drives_on_the_page():
    got = _node("""
      const d = { away: "NE", home: "SEA", drives: [
        {team: "SEA", offensive_plays: 5, yards: 67, elapsed: "2:44", plays: [{scoring: true}, {}]},
        {team: "NE",  offensive_plays: 6, yards: 23, elapsed: "4:01",
         plays: [{turnover: true}, {penalty: true}, {penalty: true}]},
        {team: "NE",  offensive_plays: 9, yards: 75, elapsed: "5:12", plays: [{scoring: true}]}]};
      console.log(JSON.stringify({
        totals: pbpTeamTotals(d, "nfl"),
        secs: pbpClockSecs("2:44"),
        junk: pbpClockSecs("—"),
        clock: pbpSecsClock(553),
        off: pbpTeamTotals({away: "A", home: "B", drives: [
          {team: "A", offensive_plays: 5, yards: 67, elapsed: "2:44", plays: [{}]}]}, "mlb"),
        loose: pbpClockSecs("14:12 left"),
        trail: pbpClockSecs("2:445"),
      }));""")
    if got is None:
        print("  SKIP node not installed"); return
    ne, sea = got["totals"]["NE"], got["totals"]["SEA"]
    assert (ne["drives"], ne["plays"], ne["yards"]) == (2, 15, 98), ne
    assert (ne["turnovers"], ne["penalties"], ne["scores"]) == (1, 2, 1), ne
    assert (sea["drives"], sea["plays"], sea["yards"]) == (1, 5, 67), sea
    assert ne["secs"] == 4 * 60 + 1 + 5 * 60 + 12, ne
    assert got["secs"] == 164 and got["junk"] == 0
    assert got["clock"] == "9:13", got["clock"]
    # Off football there are no drives to add up, and inventing a shape
    # for a payload nobody has probed is the failure this repo keeps
    # writing up.
    assert got["off"] is None, got["off"]
    # AND ONLY A PLAIN CLOCK PARSES. A loose regex would read "14:12
    # left" as fourteen minutes of possession off a string that is not a
    # duration at all, which is the invented number in miniature.
    assert got["loose"] == 0, got["loose"]
    assert got["trail"] == 0, got["trail"]


# --- the wording ------------------------------------------------------------
def test_the_old_game_info_room_is_gone_with_its_tiles():
    """Baseball's Game info room drew the park's facts as tiles (venue, roof, surface,
    temperature, wind, capacity). It went with baseball's own layout on 21 November: the
    one page's Game information card says when, on what, where and the weather
    (gpInfoHTML), and the ballpark card's head names the venue and the conditions."""
    assert "const PBP_ROOF_WORD" not in APP and "const infoCards" not in APP
    info = APP[APP.index("function gpInfoHTML("):APP.index("function gpInjuriesHTML(")]
    for label in ('"Time"', '"TV"', '"Location"', '"Weather"'):
        assert label in info, label


def test_the_table_is_a_table_for_a_screen_reader_too():
    """`scope` is the whole difference between a table and a layout: it
    is what makes a reader announce "A.J. Brown, targets, 4"."""
    # The one game page's box score card (every league's since step AAK) and the team totals.
    for body in (_fn("gpBoxCardHTML"), _fn("pbpTotalsHTML")):
        heads = re.findall(r"<th\b[^>]*>", body)
        assert heads, body[:200]
        # EVERY head, not one of them: a table with scope on some cells
        # is announced worse than one with none, because the reader
        # trusts the ones that are there.
        for th in heads:
            assert "scope=" in th, f"{th!r} in {body[:60]!r}"
        assert any('scope="col"' in t for t in heads), heads
        assert any('scope="row"' in t for t in heads), heads
    # Figures in a column line up only with tabular numerals — and the
    # rule has to be on THIS table, not merely somewhere in the file.
    i = CSS.index(".pbp-bx { ")
    rule = CSS[i:CSS.index("}", i)]
    assert "font-variant-numeric: tabular-nums" in rule, rule
    # A wide table on a narrow phone scrolls itself rather than the page.
    assert ".pbp-bx-wrap { overflow-x: auto" in CSS


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
