"""A locked board says its picks are for members (USEREYES1, 18 November 2026).

The NFL dashboard, signed out on a Tuesday, read under "Qellys' top picks":
"Tonight's slate was checked and no row could be priced from a current,
credible book number — 904 under the likelihood floor · 39 no real book
price · 20 no measured ranking for this market yet · 8 heavier than -250".
The board carried twelve Most Likely picks; the paywall had kept them
(`locked.most_likely: 12`), and the page blamed the slate. Its first game was
Thursday, so it was not tonight's slate either, and the 904 were priced, only
too unlikely. Under it, "Who could shine, who could struggle" was said three
times over: the heading, its line, and the members' card. What these hold:

  * a board whose Most Likely picks are kept for members shows the members'
    card with their count, not the empty census;
  * the empty census says no row made the board, with a true minus, and
    never "Tonight's" or "could be priced";
  * the shine/struggle members' card does not repeat the heading.

    python3 tests/test_a_locked_board_says_its_picks_are_for_members.py
"""
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 3]


def test_a_locked_board_shows_the_members_card():
    top = _fn("renderLikelyTop")
    assert "const lk = (state.data.locked || {}).most_likely;" in top
    assert '!b.begun ? memberLockHTML(`${plural(lk, "pick")} for members`, "The likeliest to hit.")' in top
    # Every game begun: the count is of picks under way or decided, said so (24 November, "133 picks for members"
    # over an NBA night whose games were all final).
    assert 'b.done ? memberLockHTML(`${b.when} picks are decided`, "How every one did is free on the Record.")' in top
    assert 'memberLockHTML(`${b.when} picks are under way`' in top
    # The census still answers a board with nothing kept back.
    assert "likelyHiddenWhy(state.data) || likelyEmptyWhy(state.data.likely_census, state.data)" in top


def test_the_census_sentence_says_no_row_made_the_board():
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        return
    js = ("var escapeHtml = (s) => String(s == null ? '' : s);\n"
          "const RE_SIGN = /(^|[^\\w])-(?=[\\d.])/g;\n"
          "const trueMinus = (s) => String(s).replace(RE_SIGN, `$1\\u2212`);\n"
          + _fn("likelyEmptyWhy")
          + "\nprocess.stdout.write(JSON.stringify(likelyEmptyWhy({'under the likelihood floor': 904, "
            "'no real book price': 39, 'heavier than -250 \\u2014 chalk, not a pick': 8}, {})));")
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    got = json.loads(out.stdout)
    assert got.startswith("No row made the board — 904 under the likelihood floor · 39 no real book price"), got
    assert "8 heavier than −250" in got and "-250" not in got, got
    assert "Tonight" not in got and "could be priced" not in got, got


def test_the_shine_card_does_not_repeat_its_heading():
    scan = _fn("renderScanTop")
    assert "Who could shine and who could struggle, in every game" not in scan
    # The top picks' lock card (memberLockHTML), never a bare card that stacked ", with the reasons…" on a line of its own.
    assert 'memberLockHTML("A read on every key player is for members", "With the reasons for and against, in every game.")' in scan
    assert "ms-locked" not in scan
    assert scan.count("Who could shine, who could struggle") == 1


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
