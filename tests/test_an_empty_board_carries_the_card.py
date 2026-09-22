"""v5: an empty board is not an apology; the Picks page reads in two columns.

Ethan, 2026-09-22: "feel like a real sportsbook app made by a real
company." Most afternoons every board is empty — prices land close to
first pitch — and the empty state was a headline and a paragraph. It
now carries what the slate already holds (how many games are on the
card, when the first one starts) and two doors to the pages that are
never empty, the live board and the record. Nothing invented: no games,
no facts; every game started, no kickoff.

And the Picks page: it opens with its name like every page, and on a
wide screen its two boards — Most likely, the edge bets — sit side by
side under section heads of one weight.
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
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _strip(src):
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


def _fn(name):
    for head in (f"function {name}(", f"async function {name}("):
        if head in APP:
            i = APP.index(head); break
    else:
        raise AssertionError(f"no function {name}")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return _strip(APP[i:min(ends)])


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""
      const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
      {_fn("pluralWord")}
      {_fn("plural")}
      {_fn("formatKickoff")}
      {_fn("deckFirstWord")}
      const tzTime = (d) => d.toISOString();
      {_fn("boardEmptyFacts")}
      let state = {{ sport: "nfl", data: null }};
      console.log(JSON.stringify((() => {{ {js} }})()));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def _facts(html):
    return re.findall(r'<span class="es-fact">([^<]*)</span>', html)


def test_the_facts_are_the_cards_own_and_nothing_else():
    got = _node("""
      const games = [{ away: "KC", home: "LAC", kickoff: "20:15", live: { state: "live" } },
                     { away: "GB", home: "CHI", kickoff: "13:00" },
                     { away: "WAS", home: "DAL", kickoff: "16:25", live: { state: "scheduled" } }];
      const out = {};
      state.data = { games }; out.three = boardEmptyFacts();
      state.data = { games: [] }; out.none = boardEmptyFacts();
      state.data = null; out.null = boardEmptyFacts();
      state.data = { games: games.map((g) => ({ ...g, live: { state: "live" } })) }; out.allLive = boardEmptyFacts();
      state.data = { games: [{ away: "A", home: "B" }] }; out.noClock = boardEmptyFacts();
      state.sport = "mlb"; state.data = { games: [{ away: "NYY", home: "BOS", kickoff: "2026-09-23T23:10:00Z" }] }; out.mlb = boardEmptyFacts();
      return out;""")
    if got is None:
        print("  SKIP node not installed"); return
    assert _facts(got["three"]) == ["3 games on the card", "Kickoff 1:00 PM ET"], \
        "the count is every game; the clock is the first game NOT yet started"
    assert got["none"] == "" and got["null"] == "", "no games, no facts"
    assert _facts(got["allLive"]) == ["3 games on the card"], "every game started: no kickoff to promise"
    assert _facts(got["noClock"]) == ["1 game on the card"]
    assert _facts(got["mlb"])[1].startswith("First pitch "), "the deck's own word for the sport"


def test_the_doors_open_the_two_pages_that_are_never_empty():
    doors = _fn("boardEmptyDoors")
    assert '<button type="button" class="btn es-door" data-es-view="live">Live now</button>' in doors
    assert '<button type="button" class="btn es-door" data-es-tool="record">The record</button>' in doors
    bind = _fn("bindEmptyDoors")
    assert "switchView(b.dataset.esView, true)" in bind
    assert 'document.querySelector(`#sidebar [data-sport="${b.dataset.esTool}"]`)' in bind and "if (src) src.click();" in bind, \
        "the record is a tool page: its own sidebar button opens it, the way the More sheet does"
    for fn, host in (("renderTonight", "host"), ("renderLikely", "note"), ("renderEdgeBoard", "host")):
        body = _fn(fn)
        i = body.index("${boardEmptyFacts()}${boardEmptyDoors()}</div>")
        assert f"bindEmptyDoors({host});" in body[i:i + 200], f"{fn}: the doors are drawn but not wired"
    assert ".empty-slate .es-facts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 14px; }" in CSS
    assert ".empty-slate .es-fact { font-family: var(--font-mono); font-size: var(--fs-xs); color: var(--text-dim);" in CSS
    assert ".empty-slate .es-doors { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }" in CSS


def test_the_picks_page_opens_with_its_name_and_reads_in_two_columns():
    body = _fn("renderTonight")
    i = body.index('<div class="section-title">Tonight’s bets\n      <span class="sub">— the pick of the day, who is likeliest to hit, and what we stake</span></div>')
    assert i < body.index("${potdHeroHTML(d)}") < body.index('<div class="tn-cols">'), "name, hero, then the boards"
    assert body.count('<section class="tn-col">') == 2
    assert '<div class="section-title">Our edge bets' in body, "a section head like its neighbour, not a minor one"
    assert '<div class="section-title">Most likely to hit tonight' in body
    assert ".tn-cols { display: grid; gap: 0 24px; align-items: start; }" in CSS
    wide = CSS[CSS.index("@media (min-width: 1100px) {\n  .tn-cols { grid-template-columns: 1fr 1fr; }"):]
    wide = wide[:wide.index("\n}")]
    assert ".tn-cols > .tn-col:only-child { grid-column: 1 / -1; }" in wide, "one board takes the width"
    assert ".tn-cols .tn-full .cards { grid-template-columns: 1fr; }" in wide, "the full cards stack in a half-width column"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
