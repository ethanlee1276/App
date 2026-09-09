"""The Record page says how much of the record is real money.

Ethan, 2026-09-09, asking what would make the site more trustworthy as
traffic grows. This is the biggest thing the feed audit turned up:
`money_bets` and `paper_bets` are computed on eleven scopes and were
rendered on none.

`engine/ledger.performance` has published the split since it was written,
and said in its own comment exactly why it exists:

    "The two counts below say the split out loud so a reader never has to
     infer it from a suspiciously small dollar figure beside a large unit
     one."

That is the shape the page had. `net_units` pools both books — honest,
and the right way to pool them. `net_dollars` counts only the picks with
money on them, by construction, because a paper row settles with
`pnl_dollars` 0. A reader seeing a large unit figure beside a small
dollar one had nothing on screen to explain the gap.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _js():
    return open(os.path.join(HERE, "web", "js", "app.js"), encoding="utf-8").read()


def _fn(js, name):
    i = js.index(f"function {name}(")
    return js[i:js.index("\nfunction ", i + 1)]


def _nocomments(src):
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", " ", src)


def test_the_ledger_still_publishes_the_split():
    """If this ever stops being computed, the page below is drawing a
    sentence about nothing."""
    led = open(os.path.join(HERE, "engine", "ledger.py"), encoding="utf-8").read()
    assert '"money_bets"' in led and '"paper_bets"' in led


def test_the_verdict_card_renders_it():
    fn = _nocomments(_fn(_js(), "recordVerdictHTML"))
    assert "moneySplitHTML(o)" in fn, \
        "the Record page still never mentions the split"


def test_all_three_shapes_of_the_answer_are_written():
    """All paper, all money, and a mix are three different sentences.
    A single template with a zero in it reads as broken on two of them."""
    fn = _nocomments(_fn(_js(), "moneySplitHTML"))
    assert "if (!paper)" in fn, "no wording for a record that is all money"
    assert "else if (!money)" in fn, "no wording for a record that is all paper"
    assert "pools both" in fn, \
        "the mixed case does not say the unit figure covers both books"


def test_the_dollar_figure_is_named_as_money_only():
    fn = _nocomments(_fn(_js(), "moneySplitHTML"))
    assert "net_dollars" in fn
    assert "actually bet" in fn or "only the picks" in fn, \
        "the dollar figure is shown without saying what it excludes"


def test_a_record_without_the_counts_says_nothing():
    """A record.json built before this shipped carries neither count. A
    sentence about a split we cannot see is worse than no sentence."""
    fn = _nocomments(_fn(_js(), "moneySplitHTML"))
    assert re.search(r"money == null \|\| paper == null.*return \"\"", fn, re.S), \
        "a missing count does not fall through to silence"


def test_the_memes_board_did_not_quietly_inherit_this():
    """`memeVerdictHTML` shares this markup by coincidence and is a
    different book with its own rules."""
    js = _js()
    i = js.index("function memeVerdictHTML(")
    body = js[i:js.index("\nfunction ", i + 1)]
    assert "moneySplitHTML" not in body


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
