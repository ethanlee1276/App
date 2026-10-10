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

WHAT THIS FILE GUARDS is not the styling — it is the two honesty rules
the new tables live under, because both are the kind of thing that gets
"tidied" later by someone who cannot see why they are there:

  · a column nobody filled is NOT DRAWN, so an all-dash column never
    stands in for real zeroes;
  · every key the tables read is a market the parsers actually write,
    and every drive field is one `football_drives` actually emits.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


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
def test_every_box_column_is_a_market_a_parser_writes():
    """The tables invent no field. Each key must appear in the parser
    that names markets for that league, or the column is a heading over
    numbers nobody produces."""
    src = _block("const PBP_BOX_FOOTBALL = [", "\n];")
    keys = set(re.findall(r'"([a-z_]+)"', src)) - {"Passing", "Rushing", "Receiving"}
    assert len(keys) >= 10, keys
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
        'const PBP_LEAD_STAT = { nba: ["points"] };',
        'const PBP_FOOTBALL = new Set(["nfl", "cfb"]);',
        'const teamMarkIn = () => ""; const teamNameIn = (l, a) => a;',
        'const pbpAgo = () => "updated 1s ago";',
        _block("const PBP_BOX_FOOTBALL = [", "\n];"),
        _block("const PBP_BOX_HEAD = {", "\n};"),
        _line("const pbpStat = "),
        _fn("pbpBoxGroupHTML"), _fn("pbpBoxGenericHTML"), _fn("pbpPlayersHTML"),
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


def test_a_column_nobody_filled_is_not_drawn():
    """An all-dash TD column reads as "nobody scored" and is really
    "this feed did not send the field". The reader cannot tell those
    apart, and only one of them is a fact."""
    got = _node("""
      const noTD = { away: "NE", home: "SEA", players: [
        {player: "A", team: "NE", stats: {carries: 9, rush_yds: 48}},
        {player: "B", team: "NE", stats: {carries: 3, rush_yds: 10}}]};
      const withTD = { away: "NE", home: "SEA", players: [
        {player: "A", team: "NE", stats: {carries: 9, rush_yds: 48, rush_td: 1}},
        {player: "B", team: "NE", stats: {carries: 3, rush_yds: 10}}]};
      console.log(JSON.stringify({
        without: pbpPlayersHTML(noTD, "nfl"),
        with:    pbpPlayersHTML(withTD, "nfl"),
      }));""")
    if got is None:
        print("  SKIP node not installed"); return
    assert ">TD<" not in got["without"], "an empty TD column was drawn anyway"
    assert ">CAR<" in got["without"] and ">YDS<" in got["without"], got["without"][:400]
    # One player with the field is enough to earn the column, and the
    # player without it gets a dash rather than an invented zero.
    assert ">TD<" in got["with"], got["with"][:400]
    assert "—" in got["with"], got["with"][:400]


def test_football_splits_into_three_tables_and_nothing_else_does():
    """A passer and a slot receiver share almost no statistics. One
    table with every column is mostly dashes."""
    got = _node("""
      const d = { away: "NE", home: "SEA", players: [
        {player: "QB", team: "NE", stats: {pass_cmp: 17, pass_att: 23, pass_yds: 174, rush_yds: 36, carries: 5}},
        {player: "WR", team: "NE", stats: {rec_yds: 26, receptions: 3, targets: 4}}]};
      const hoops = { away: "NE", home: "SEA", players: [
        {player: "G", team: "NE", stats: {points: 22, rebounds: 4, assists: 7}}]};
      console.log(JSON.stringify({
        nfl: pbpPlayersHTML(d, "nfl"), nba: pbpPlayersHTML(hoops, "nba"),
      }));""")
    if got is None:
        print("  SKIP node not installed"); return
    for head in ("Passing", "Rushing", "Receiving"):
        assert f">{head}<" in got["nfl"], (head, got["nfl"][:600])
    # The QB appears in passing AND rushing — the same player, twice,
    # which is what a box score does.
    assert got["nfl"].count(">QB") == 2, got["nfl"]
    # A league whose stat keys have not been read gets ONE table built
    # from its own keys, not football's headings over foreign numbers.
    assert "Passing" not in got["nba"], got["nba"]
    assert "points" in got["nba"] and "rebounds" in got["nba"], got["nba"]


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
def test_the_roof_and_the_field_are_called_something():
    i = APP.index("const PBP_ROOF_WORD = {")
    roof = APP[i:APP.index("};", i)]
    assert '"Open air"' in roof and "outdoors:" in roof, roof
    j = APP.index("const PBP_SURFACE_WORD = {")
    surf = APP[j:APP.index("};", j)]
    assert '"FieldTurf"' in surf and "fieldturf:" in surf, surf
    # An unmapped value is shown title-cased, never swallowed.
    assert "pbpTitleCase(boardGame.roof)" in APP
    assert "pbpTitleCase(boardGame.surface)" in APP
    # And the raw "Roof: outdoors" spelling is gone.
    assert "Roof: ${" not in APP, "the label-and-value tile is back to a sentence"


def test_every_fact_tile_is_a_label_and_a_value():
    """Three of these had the value as the big text and one had the
    label there, so the reader had to work out which line was the
    question."""
    i = APP.index("const infoCards = boardGame ? [")
    cards = APP[i:APP.index("].filter(Boolean)", i)]
    for label in ("Venue", "Roof", "Surface", "Temperature", "Wind", "Capacity"):
        assert f'"{label}"' in cards, f"{label} tile is gone"
    assert 'class="pbp-info-k"' in APP, "the label has no class of its own"
    assert ".pbp-info-k {" in CSS


def test_the_table_is_a_table_for_a_screen_reader_too():
    """`scope` is the whole difference between a table and a layout: it
    is what makes a reader announce "A.J. Brown, targets, 4"."""
    for body in (_fn("pbpBoxGroupHTML"), _fn("pbpBoxGenericHTML"), _fn("pbpTotalsHTML")):
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
