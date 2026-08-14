"""An empty August board has to say the word "preseason".

Ethan, 2026-08-14: "preseason started every other team for NFL yesterday
and we didn't recommend props or anything like that."

NOT PRICING PRESEASON IS DELIBERATE and the Preseason block already says
so in as many words. The defect is that the block saying it is BELOW —
and at the top of the same page, where the question actually gets asked,
the empty-slate panel was saying:

    "No games on the board right now — nothing is scheduled or in
     progress for this slate yet. Check back closer to game time."

with sixteen exhibition games listed further down the same screen. One
page, two answers, and the one that reads first was the wrong one. A
reason that does not travel to where the question is asked is not a
reason anyone has.

The same hole was in `launch.py --why-empty`, the probe whose entire job
is explaining an empty board: on the most predictable empty board of the
year it printed "no analyzed props at all" and stopped.

THE CONSTRAINT WORTH WRITING DOWN, because it decides the question rather
than merely arguing it: `engine/sources/nflverse` keeps `season_type` REG
at INGEST, so the database holds no preseason snap from any year. There
is nothing to fit a preseason model on. That is a fact about the data,
not a preference about the model, and any future "let's price preseason"
conversation starts there.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
LAUNCH = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
NFLV = open(os.path.join(ROOT, "engine", "sources", "nflverse.py"),
            encoding="utf-8").read()
ES = APP[APP.index("function renderEmptySlate()"):
         APP.index("/* ============================================================\n"
                   "   Best Bets Tonight")]


def test_the_empty_board_names_preseason():
    assert "Preseason is on" in ES
    assert "nothing in it is priced" in ES.lower()


def test_it_does_not_claim_nothing_is_scheduled_during_preseason():
    """The exact sentence that was wrong. It still exists for a genuinely
    empty night, but the preseason branch has to return before it."""
    i = ES.index("Preseason is on")
    rest = ES[i:]
    assert "return;" in rest[:rest.index("No games on the board right now")], \
        "the preseason branch falls through to 'nothing is scheduled'"


def test_the_panel_can_see_the_preseason_payload():
    """`renderEmptySlate` is synchronous and runs long before the fetch
    lands, which is why it could not know. The loader stashes the payload
    and re-runs the panel."""
    assert "state.preseason = data;" in APP
    i = APP.index("state.preseason = data;")
    assert "renderEmptySlate" in APP[i:i + 300], "the panel is never re-run"
    assert "const pre = state.preseason;" in ES


def test_it_retires_itself_with_the_block_it_points_at():
    """`show_until` is the last fixture's date. The message must stop when
    the schedule does, or the Week 1 board opens under a banner about
    exhibitions."""
    assert "pre.show_until" in ES
    assert 'new Date().toISOString().slice(0, 10) <= pre.show_until' in ES


def test_it_is_nfl_only():
    """MLB in August is a real slate. This message on it would be false."""
    assert '(state.sport || "nfl") === "nfl"' in ES


def test_the_probe_explains_it_too():
    """`--why-empty` exists to explain an empty board. On the most
    predictable empty board of the year it said 'no analyzed props at
    all' and stopped."""
    i = LAUNCH.index("def why_empty(")
    fn = LAUNCH[i:LAUNCH.index("\ndef ", i + 10)]
    assert "It is PRESEASON" in fn
    assert "nfl_preseason.json" in fn
    assert "season_type REG" in fn, "the probe must name the real constraint"


def test_the_probe_survives_a_missing_or_stale_payload():
    """The file is written by the launcher and may not exist. An
    explanation that crashes the explainer is worse than none."""
    i = LAUNCH.index("def why_empty(")
    fn = LAUNCH[i:LAUNCH.index("\ndef ", i + 10)]
    assert "except Exception:" in fn and "pd = None" in fn
    assert 'pd.get("show_until") or ""' in fn, "a payload with no end date must not match"


def test_the_ingest_really_does_drop_preseason():
    """The claim both messages make. If this ever changes — nflverse
    starts shipping PRE, or someone widens the filter — the messages
    become false and this test is where that gets caught."""
    assert 'in ("REG", "")' in NFLV, \
        "the season_type filter moved; the preseason copy may now be wrong"


def test_nothing_here_prices_a_preseason_game():
    """The whole point. The board stays empty; this change only explains
    why. A future patch that starts pricing August has to delete these
    words rather than leave them contradicting the board above them."""
    assert "nflpre.py" in os.listdir(ROOT)
    pre = open(os.path.join(ROOT, "nflpre.py"), encoding="utf-8").read()
    assert "IT DOES NOT PRICE ANYTHING, on purpose." in pre


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
