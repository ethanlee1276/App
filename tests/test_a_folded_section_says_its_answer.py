"""A folded section says its answer beside its title (20 November 2026).

Ethan, on the game report page: "make any aditions or fixes you think is needed
or and anything that would help". The report reads with our picks and the short
version open and every other section folded to its title, and a title says what
a section is about, not what it found: "Who we think wins" kept its answer a tap
away, at the top of every report. What these hold:

  * where a section's finding fits in a few words the engine writes it as the
    section's `hint`, read off the section's own blocks (so it cannot disagree
    with the section, and every league's report says it): who wins and the
    chance, the line, each club's unit edges, how many are listed and out, how
    many tickets, how many breakout candidates and fades, the air it is played in;
  * a section with nothing short to say carries no hint, and neither does one
    with nothing to count;
  * the page draws the hint in the fold's title row, hides it once the fold is
    open (the section says it itself then: each thing once), and cuts it short
    before it can push a title onto a second line.

    python3 tests/test_a_folded_section_says_its_answer.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import gamereport as R  # noqa: E402

CLUTTER = __import__("test_the_report_reads_without_the_clutter")     # its fixture report and node harness


def test_the_report_carries_each_short_answer():
    rep = CLUTTER._report()
    hints = {s["key"]: s.get("hint") for s in rep["sections"]}
    assert hints["verdict"] == "Lions 60%", hints
    assert hints["market"] == "DET by 3 at home, total 52.5"
    assert hints["rankings"] == "GB 3 edges, DET 3", "the chart's own edges, counted a club"
    assert hints["injuries"] == "2 listed, 1 out", "Zach Tom is out, Sam LaPorta questionable"
    assert hints["watch"] == "2 breakouts, 1 fade"
    assert hints["weather"] == "Indoors"
    # The title's number is the bar's own: one rounding, the page's.
    win = next(b for s in rep["sections"] if s["key"] == "verdict" for b in s["blocks"] if b["type"] == "winner")
    assert hints["verdict"] == f"{win['name']} {int(100 * win['chance'] + 0.5)}%"
    # A section with no short answer says none.
    for quiet in ("short", "facts", "identity", "matchups", "trenches", "redzone", "scripts", "before"):
        assert hints.get(quiet) is None, quiet


def test_each_hint_is_read_off_the_sections_own_blocks():
    hint = lambda key, blocks: R.section_hint(None, {"key": key, "blocks": blocks})   # noqa: E731
    claim = lambda who, status: {"kind": "injury", "player": who, "team": "NYK", "status": status}   # noqa: E731
    rows = lambda *st: [{"type": "list", "items": [f"P{i}" for i in range(len(st))],   # noqa: E731
                         "claims": [claim(f"P{i}", s) for i, s in enumerate(st)]}]
    assert hint("injuries", rows("out", "out")) == "2 out"
    assert hint("injuries", rows("questionable", "day-to-day", "out")) == "3 listed, 1 out"
    assert hint("injuries", rows("questionable")) == "1 listed"
    assert hint("injuries", [{"type": "p", "text": "Nobody is listed"}]) == ""
    # A winner's chance at the half rounds up, the way the page's bar does (Math.round; Python's round says 60).
    win = lambda p: [{"type": "winner", "team": "NYK", "name": "Knicks", "chance": p}]   # noqa: E731
    assert hint("verdict", win(0.605)) == "Knicks 61%" and hint("verdict", win(0.615)) == "Knicks 62%"
    assert round(100 * 0.605) == 60
    assert hint("verdict", [{"type": "p", "text": "No line yet"}]) == ""
    tickets = lambda *n: [{"type": "parlays", "kind": k, "items": [{}] * c}   # noqa: E731
                          for k, c in zip(("three", "two", "scorers"), n)]
    assert hint("parlays", tickets(3, 2, 3)) == "8 tickets" and hint("parlays", tickets(1)) == "1 ticket"
    assert hint("parlays", [{"type": "p", "text": "No prop prices yet"}]) == ""
    cards = lambda n: {"type": "verdicts", "items": [{}] * n}   # noqa: E731
    h = lambda t: {"type": "h", "text": t}   # noqa: E731
    assert hint("watch", [h("Breakout candidates"), cards(1), h("Fades"), cards(2)]) == "1 breakout, 2 fades"
    assert hint("watch", [h("Fades"), cards(1)]) == "1 fade"
    assert hint("watch", [h("Roles on the move"), {"type": "list", "items": ["x"]}]) == ""
    assert hint("matchups", [cards(4)]) == "", "only the sections with a short answer"
    bars = lambda *edges: [{"type": "matchbars", "sides": [{"off": "A", "rows": [{"label": "x", "edge": e} for e in edges]}]}]   # noqa: E731
    assert hint("rankings", bars("KC", "", "KC", "BUF")) == "KC 2 edges, BUF 1"
    assert hint("rankings", bars("KC")) == "KC 1 edge" and hint("rankings", bars("", "")) == ""


def test_every_leagues_report_gets_them_in_one_place():
    src = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    finish = src[src.index("def finish("):src.index("def _featured_badge(")]
    assert "hint = section_hint(c, sec)" in finish and 'sec["hint"] = hint' in finish
    league = (ROOT / "engine" / "leaguereport.py").read_text(encoding="utf-8")
    assert "return finish(c, fns, short)" in league, "baseball, hockey and basketball end in the same finish"
    # The weather's two facts are the section's own (one rule for the line and its hint).
    assert src.count("def _indoors(") == 1 and "indoors = _indoors(g)" in src and "bits = _air_words(w)" in src


def test_the_page_draws_the_hint_in_the_title_row_and_hides_it_when_open():
    rep = CLUTTER._report()
    got = CLUTTER._node(f"const rep = {json.dumps(rep, ensure_ascii=False)};"
                        "process.stdout.write(JSON.stringify(R.html(rep, {})));")
    if got is None:
        print("      (skipped: no Node)")
        return
    assert ('<details class="gr-sec gr-fold" id="gr-verdict"><summary class="gr-title"><span>Who we think wins</span>'
            '<span class="gr-hint">Lions 60%</span><span class="row-fold-chev" aria-hidden="true"></span></summary>') in got
    assert '<span>The market</span><span class="gr-hint">DET by 3 at home, total 52.5</span>' in got
    assert ('<summary class="gr-title"><span>Game facts</span><span class="row-fold-chev" aria-hidden="true"></span>'
            '</summary>') in got, "no hint, no empty span"
    assert got.count('class="gr-hint"') == sum(1 for s in rep["sections"] if s.get("hint"))
    css = (ROOT / "web" / "css" / "report.css").read_text(encoding="utf-8")
    for rule in (".gr-fold[open] > summary .gr-hint { display: none; }",
                 ".gr-fold > summary.gr-title > span:first-child { flex: 0 0 auto; max-width: 100%; }",
                 "text-overflow: ellipsis; white-space: nowrap;"):
        assert rule in css, rule


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as e:                                   # noqa: BLE001
            fails += 1
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
    if fails:
        sys.exit(1)
    print(f"\n{len(tests)} tests passed.")
