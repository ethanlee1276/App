"""Three boards, three levels of evidence, three journals — said out loud.

Ethan, 2026-08-30: "it might be confusing for people using the site that
wants to know what good bets are that will win. we need to be more clear
on what bets are what and what bets to use and trust and whats being
recorded and not."

The confusion was earned. The site shows boards that select on different
things, carry very different amounts of evidence, and are journaled to
three different places — and nothing told a reader any of that. Worst of
all, the board that LOOKS most authoritative is the one with the least
behind it: "Tonight's bets" selects on edge, and the edge claim tests at
0.468 AUC.

TWO RULES HOLD THIS TOGETHER, and both exist because this codebase keeps
making the same mistake in prose.

  * Every number is DERIVED from the measurement it describes. The
    likelihood blurb used to carry "0.72 AUC" and "0.69-0.77" as typed
    text in app.js; those are `likely.RANK_AUC`, and a copy of a
    measurement in a template rots at the next refit.

  * Every "we record this" is checked against the code that records it.
    A claim about journaling, asserted in a paragraph and enforced
    nowhere, is exactly the shape of the bugs this session has been
    fixing all day.

Run directly: `python3 tests/test_board_guide.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import boards                               # noqa: E402
from engine import ledger                               # noqa: E402
from engine.likely import RANK_AUC                      # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _app():
    with open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8") as f:
        return f.read()


# --- the numbers are measurements, not prose -----------------------------
def test_the_ranking_figures_come_from_the_fitted_values():
    """Refit the model and this sentence follows it. Typed text would
    not, and would go on claiming last month's number."""
    g = boards.by_key()["most_likely"]
    assert f"{RANK_AUC['anytime_td']:.2f}" in g["measured"]
    lo, hi = min(RANK_AUC.values()), max(RANK_AUC.values())
    assert f"{lo:.2f}-{hi:.2f}" in g["measured"]


def test_moving_a_fitted_auc_moves_the_sentence():
    """The strongest form of the test above: change the source, and the
    copy has to change with it."""
    real = dict(RANK_AUC)
    try:
        RANK_AUC["anytime_td"] = 0.999
        assert "0.999" in boards.by_key()["most_likely"]["measured"] \
            or "1.00" in boards.by_key()["most_likely"]["measured"]
    finally:
        RANK_AUC.clear()
        RANK_AUC.update(real)


def test_no_board_blurb_in_the_page_types_its_own_measurement():
    """`renderLikely` carried both AUC figures inline. They are gone, and
    the guide is the only place they can come from."""
    src = _app()
    body = src[src.index("function renderLikely()"):
               src.index("function renderLongShots()")]
    assert "0.72" not in body and "0.69" not in body, body[:400]
    assert 'boardGuide("most_likely")' in body


# --- what we say is recorded is what records it --------------------------
def test_every_board_names_the_journal_that_actually_writes_it():
    """THE CLAIM CHECKED AGAINST THE CODE. Each entry's `journal` is the
    ledger category some function really inserts under — not a word
    chosen to sound right."""
    import inspect
    got = boards.by_key()
    assert "'likely'" in inspect.getsource(ledger.log_most_likely)
    assert got["most_likely"]["journal"] == "likely"
    assert '"longshot", flat_stake' in inspect.getsource(ledger.log_longshots)
    assert got["long_shots"]["journal"] == "longshot"
    # The main book is category 'main' unless paper mode is on, and
    # log_recommendations is the only thing that writes it.
    src = inspect.getsource(ledger.log_recommendations)
    assert 'category = "paper" if paper else "main"' in src
    assert got["recommendations"]["journal"] == "main"


def test_only_the_board_that_stakes_money_says_it_does():
    got = boards.by_key()
    assert got["recommendations"]["money"] is True
    assert got["most_likely"]["money"] is False
    assert got["long_shots"]["money"] is False
    # And the zero-dollar claim is true of the code, not just the copy —
    # checked on the function that writes the ROW, since `log_longshots`
    # delegates to `_journal_longshot_rows` and asserting on the wrapper
    # would pass without proving anything.
    import inspect
    for fn in (ledger.log_most_likely, ledger._journal_longshot_rows):
        src = inspect.getsource(fn)
        assert "stake_dollars" in src, fn.__name__
        assert "flat_stake, 0.0" in src, fn.__name__


def test_the_summary_line_says_where_each_one_lands():
    for b in boards.guide():
        line = boards.summary_line(b)
        assert b["selects_on"] in line
        if b["money"]:
            assert "Record page" in line
        else:
            assert b["journal"] in line and "not staked" in line


# --- the honest part -----------------------------------------------------
def test_the_weakest_board_is_named_as_the_weakest():
    """The uncomfortable one, and the reason this file exists. "Tonight's
    bets" is the only board staking money and the one with the least
    evidence: its edge claim tests at 0.468 AUC against 0.72 for the
    ranking. A guide that buried that would be decoration."""
    rec = boards.by_key()["recommendations"]
    assert f"{boards.EDGE_AUC:.3f}" in rec["measured"]
    assert "coin flip" in rec["measured"]
    assert "least evidence" in rec["trust"]
    assert "unproven" in rec["trust"]


def test_the_boards_are_ordered_by_evidence_not_by_prominence():
    keys = [b["key"] for b in boards.guide()]
    assert keys.index("most_likely") < keys.index("recommendations")


def test_it_says_no_nfl_bet_has_settled_yet():
    """A reader deciding what to trust needs to know the live record
    cannot referee this yet — otherwise "recorded" reads as "proven"."""
    assert "settled yet" in boards.by_key()["recommendations"]["measured"]


# --- it reaches the page -------------------------------------------------
def test_the_guide_travels_with_the_slate():
    from engine.pipeline import run_slate
    got = run_slate(os.path.join(ROOT, "data", "sample_slate.json"))
    keys = {b["key"] for b in got.get("board_guide") or []}
    assert keys == {"most_likely", "long_shots", "recommendations"}, keys


def test_every_guided_board_is_a_real_payload_key():
    """A guide entry for a board that does not exist is a paragraph about
    nothing; a board with no entry loses its explanation silently."""
    from engine.pipeline import run_slate
    got = run_slate(os.path.join(ROOT, "data", "sample_slate.json"))
    for b in boards.guide():
        assert b["key"] in got, b["key"]


def test_the_page_draws_it_under_all_three_boards():
    src = _app()
    for key in ("most_likely", "long_shots", "recommendations"):
        assert f'boardGuide("{key}")' in src, key


def test_a_board_with_no_entry_draws_nothing_rather_than_undefined():
    src = _app()
    body = src[src.index("function boardGuide(key)"):]
    body = body[:body.index("\nfunction ")]
    assert "if (!g) return \"\";" in body
    # And every field it prints is escaped — this text is ours, but the
    # payload is a file on disk and the page treats it like any other.
    assert body.count("escapeHtml(") >= 4, body


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
