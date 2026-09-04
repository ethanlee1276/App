"""A pre-game ranking stayed on the page after kickoff, saying nothing.

`engine/boardlint --sport cfb` on the droplet, 2026-09-03, board built
19:48:35:

    MOST LIKELY: 18 rows, 16 flagged
      Under 58.5   UCF  v BCU   ! LEAN measured 0.50  ! STARTED
      Over 53.5    RUTG v MASS  ! LEAN measured 0.50  ! STARTED
      ... eight of them

The LEAN flags are Ethan's own call (task #107 — spreads and totals shown
as labelled leans) and the lint says so: "not a defect". STARTED is not
annotated that way, and it is the one worth acting on.

`showableLikelyRow` filters shrink artefacts and the -250 price cap and
NEVER LOOKED AT KICKOFF, though every game row carries one. The edge
board refuses a started game at the rules layer — "this is a pre-game
model and cannot price an in-play market" — and the likelihood board had
no equivalent anywhere, at build time or on the page. Nothing was wrong
when it published; it simply never expired.

LABELLED, NOT HIDDEN, and that is the whole design decision. Dropping
the row would make cards vanish under a reader on the sixty-second
refresh, which is Ethan's complaint from 2026-08-31 about a different
board: "ill be staring at the live page at the open bets and ill scroll
and shit then the open bets will just dissapear." A row that changes
what it SAYS is honest. A row that disappears while you are reading it
is that bug, one board over. So the filter is deliberately untouched and
this file pins that it stays untouched.

Run directly: `python3 tests/test_likely_started.py`
"""

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

JS = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()


def _fn(name):
    """One top-level function's source, by brace balance."""
    i = JS.index(f"function {name}")
    depth, j = 0, JS.index("{", i)
    for k in range(j, len(JS)):
        if JS[k] == "{":
            depth += 1
        elif JS[k] == "}":
            depth -= 1
            if depth == 0:
                return JS[i:k + 1]
    raise AssertionError(f"{name} never closes")


# --- the rule -----------------------------------------------------------------
def test_the_started_check_behaves_across_every_shape_a_row_carries():
    """Executed, not read. The parsing is the part that can be quietly
    wrong, and a rule about time that is only source-pinned is a rule
    nobody has run."""
    prog = _fn("likelyStarted") + """
const past = new Date(Date.now() - 3600e3).toISOString();
const soon = new Date(Date.now() + 3600e3).toISOString();
const cases = [
  ["kickoff an hour ago",      {kickoff: past},                        true],
  ["kickoff an hour ahead",    {kickoff: soon},                        false],
  ["live flag set",            {live: true},                           true],
  ["no kickoff at all",        {},                                     false],
  ["naive local timestamp",    {kickoff: "2026-09-03T19:00:00"},       false],
  ["+00:00 offset, past",      {kickoff: past.replace("Z","+00:00")},  true],
  ["-0400 offset, past",       {kickoff: "2020-01-01T12:00:00-0400"},  true],
  ["unparseable",              {kickoff: "not a time"},                false],
  ["game_kickoff fallback",    {game_kickoff: past},                   true],
  ["null row",                 null,                                   false],
];
let bad = [];
for (const [name, row, want] of cases) {
  if (likelyStarted(row) !== want) bad.push(name);
}
console.log(bad.length ? "FAIL " + bad.join(", ") : "OK");
"""
    out = subprocess.run(["node", "-e", prog], capture_output=True, text=True,
                         timeout=60)
    assert out.returncode == 0, out.stderr[-400:]
    assert out.stdout.strip() == "OK", out.stdout.strip()


def test_a_kickoff_with_no_timezone_is_not_a_verdict():
    """THE CASE THAT WOULD MISLABEL A WHOLE SLATE. A bare local
    timestamp cannot be compared against a clock in another zone;
    guessing the reader's is how a 1pm kickoff reads as "under way" in
    London three hours early. No offset, no verdict — the same rule
    `boardlint._started` takes when `t.tzinfo is None`."""
    src = _fn("likelyStarted")
    assert "Z|[+-]" in src, "the timezone guard is gone"
    py = open(os.path.join(ROOT, "engine", "boardlint.py"), encoding="utf-8").read()
    i = py.index("def _started")
    assert "if t.tzinfo is None:" in py[i:i + 700], \
        "boardlint dropped its own naive-timestamp guard; these two must agree"


# --- the decision -------------------------------------------------------------
def test_a_started_row_is_still_shown():
    """THE POINT. `showableLikelyRow` is the filter that removes rows,
    and it must not learn about kickoff: a card that disappears under a
    reader mid-scroll is the complaint this fix exists NOT to cause."""
    src = _fn("showableLikelyRow")
    for banned in ("likelyStarted", "kickoff", "live"):
        assert banned not in src, \
            f"showableLikelyRow now drops rows on {banned} — they will vanish " \
            f"under the reader on the 60-second refresh"


def test_both_render_paths_say_so():
    """The board draws rows two ways — full cards and the compact list —
    and a label on one of them is a label a reader may never see."""
    assert "startedChip(r)" in _fn("likelyCard"), "the card does not label it"
    assert 'likelyStarted(r) ? " · under way"' in _fn("likelyRow"), \
        "the compact row does not label it"


def test_the_chip_has_a_style_to_wear():
    assert re.search(r"\.chip\.warn\s*\{", CSS), \
        "chip warn has no rule — the label renders unstyled"


def test_the_label_says_what_it_means_rather_than_just_flagging():
    """"under way" alone reads as a status badge. The title has to say
    why the row is still there and what it is worth — that the board
    ranks pre-game and this is what it thought before kickoff."""
    src = _fn("startedChip")
    assert "under way" in src
    for phrase in ("pre-game", "does not re-price", "vanish"):
        assert phrase in src, f"the explanation lost: {phrase}"


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
