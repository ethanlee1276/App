"""A parlay card says each thing once (2026-11-19).

Ethan's standing rule: no repeated information. Read as a member sees it (a
render of Report Picks from the shared fixture, the day the parlays were
rebuilt), a ticket's card said two things twice:

  * its price line ended "the legs' own prices multiplied pay +203, and a
    book's same-game price pays less", and the caveat under it began "The legs'
    own prices multiplied pay +203, short of the +206 this needs ...": the same
    price, twice, on every ticket a book is unlikely to pay enough for;
  * each leg names its backup, and a game with one good spare named it three
    times, a line a leg.

What these hold: the price line leaves the multiplied price to the caveat when
the caveat says it (the report's own card and the page's, both builders), and
the card joins the legs that share a replacement, "any leg" when all do. The
data keeps a line a leg: the watch card finds a player's backup by it.

    python3 tests/test_a_parlay_card_says_each_thing_once.py
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import gameparlays as GP  # noqa: E402

REPORT_JS = (ROOT / "web" / "js" / "report.js").read_text(encoding="utf-8")
CAVEAT = ("The legs' own prices multiplied pay +203, short of the +206 this needs once a book takes its same-game "
          "cut — pass, or play the legs as singles, unless your book pays +206 or better")


def _ticket(caveats):
    leg = lambda who, p: {"player": who, "team": "NYG", "market": "receptions", "market_label": "Receptions",  # noqa: E731
                          "side": "OVER", "line": 3.5, "odds": -200, "book": "DraftKings", "p": p}
    return {"joint": 0.34, "independent": 0.34, "fair_words": "+191", "take_words": "+206", "naive_words": "+203",
            "legs": [leg("A One", 0.72), leg("B Two", 0.70), leg("C Three", 0.68)], "caveats": caveats,
            "backups": [{"for": "A One", "leg": leg("D Spare", 0.67)}, {"for": "B Two", "leg": leg("D Spare", 0.67)},
                        {"for": "C Three", "leg": leg("D Spare", 0.67)}]}


def test_the_reports_card_leaves_the_multiplied_price_to_its_caveat():
    short = GP.card(_ticket([CAVEAT]), 1, "three", "nfl")
    assert short["price_line"] == "34% by our numbers · fair +191 · take it at +206 or better", short["price_line"]
    assert short["caveats"] == [CAVEAT], "the caveat says both prices, once"
    # A ticket a book can pay keeps the line's own word on the multiplied price: nothing else says it.
    ok = GP.card(_ticket(["A One is listed questionable — confirm they play before you bet it"]), 1, "three", "nfl")
    assert ok["price_line"].endswith("take it at +206 or better · the legs' own prices multiplied pay +203, and a "
                                     "book's same-game price pays less"), ok["price_line"]
    # The data keeps a backup line a leg (the watch card reads a player's by its opening words).
    assert len(short["backups"]) == 3 and short["backups"][0].startswith("If A One is out or that number moves: ")


def test_a_one_club_note_agrees_with_its_legs():
    """A two-leg ticket read "Both legs here is NYG's" (the three-leg one's "Every leg here is" with its
    first words swapped)."""
    three = _ticket([])
    two = dict(three, legs=three["legs"][:2])
    assert GP.side_reason(two, None).startswith("Both legs here are NYG's: no ticket with the other side's picks")
    assert GP.side_reason(three, None).startswith("Every leg here is NYG's: no ticket with the other side's picks")
    alt = dict(three, joint=0.20)
    assert GP.side_reason(two, alt) == "Both legs here are NYG's: 14 points likelier than the best ticket with both sides"


def _node(body):
    at = REPORT_JS.index("  function backupLines(t) {")
    helper = REPORT_JS[at:REPORT_JS.index("\n  }\n", at) + 5]
    js = "const escapeHtml = (s) => String(s == null ? '' : s);\n" + helper + "\n" + body
    node = shutil.which("node") or "/opt/node22/bin/node"
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_card_names_each_replacement_once():
    sep = " is out or that number moves: "
    spare, other = "D Spare over 3.5 receptions (-200, 67%)", "E Other over 40.5 receiving yards (-150, 61%)"
    legs = [{"player": "A One"}, {"player": "B Two"}, {"player": "C Three"}]
    got = _node("console.log(JSON.stringify([%s]));" % ", ".join("backupLines(%s)" % json.dumps(t) for t in (
        {"legs": legs, "backups": [f"If {n}{sep}{spare}" for n in ("A One", "B Two", "C Three")]},
        {"legs": legs, "backups": [f"If A One{sep}{spare}", f"If B Two{sep}{other}", f"If C Three{sep}{spare}"]},
        {"legs": legs[:2], "backups": [f"If A One{sep}{spare}", f"If B Two{sep}{spare}"]},
        {"legs": legs, "backups": [f"If A One{sep}{spare}"]},
        {"legs": legs, "backups": ["Some other words"]},
        {"legs": legs})))
    every, two, pair, one, odd, none = got
    assert every == [f"If any leg is out or its number moves: {spare}"], every
    assert two == [f"If A One or C Three{sep}{spare}", f"If B Two{sep}{other}"], two
    assert pair == [f"If A One or B Two{sep}{spare}"], "a two-leg ticket names its two"
    assert one == [f"If A One{sep}{spare}"] and odd == ["Some other words"] and none == []
    # Drawn on the card and in the copied report from the joined lines, and the page's own builder
    # leaves the multiplied price to the caveat that says it.
    assert "${items(backupLines(t))}</ul>" in REPORT_JS and "backupLines(t).forEach((x) => out.push(`    Backup: ${x}`));" in REPORT_JS
    assert "!(t.caveats || []).some((c) => /own prices multiplied pay/.test(String(c)))" in REPORT_JS
    assert "const lead = `If ${l.player} is out or that number moves: `;" in REPORT_JS, "the watch card's lookup stands"


if __name__ == "__main__":
    import traceback
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception:
            fails += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
