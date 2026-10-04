"""Half the splits table in English and half in database.

Ethan, 2026-08-24, on the Record page's BY MARKET split: "spell out
those works all the way". The table read

    Hits            56-68   +0.36u
    Total Bases     61-62   +0.26u
    Outs Recorded   53-38   +7.71u
    reb              8-14   -1.95u
    ast              8-13   -1.95u
    fg3m             2-1    +1.31u
    pts              1-0    +1.33u

THE CAUSE WAS A SIXTH COPY OF ONE VOCABULARY. Four engine modules own
the labels for their own board, which is right — a market is named where
it is defined. web/js/app.js then kept a hand-typed copy for this table,
and it had drifted in the way a hand-typed copy always drifts: it
spelled the basketball markets `points`/`rebounds`/`assists`, which is
what a person would guess, while the journal stores `pts`/`reb`/`ast`,
which is what the feed sends. Every miss fell through to the raw key.

So the copy is gone. engine/markets.py merges the sport modules, the
payload carries the result, and the front end reads it — the same rule
the break-even threshold already follows: a value retyped in the front
end is a value that drifts.

THE FALLBACK IS A SAFETY NET, NOT THE PLAN. `label()` prettifies an id
it has never seen so a market added to a feed tomorrow reads as "First 3
Innings" rather than `first_3_innings`. But a stat that does not survive
title-casing — `fg3m` becomes "Fg3m" — has to be named explicitly, so
the checks below insist the real markets are NAMED rather than merely
prettified.

Run directly: `python3 tests/test_market_words.py`
"""

import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import ledger, markets                              # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


# --- the merge ------------------------------------------------------------

def test_every_board_names_its_own_markets_here():
    """The point of the merge: no sport module may define a market this
    map has never heard of. New board, new stat, this fails."""
    from engine.cfb.pipeline import MARKET_LABELS as cfb
    from engine.mlb.models import MARKET_LABELS as mlb
    from engine.models import MARKET_LABELS as nfl
    from engine.nba.pipeline import MARKET_LABELS as nba
    for name, src in (("nfl", nfl), ("mlb", mlb), ("nba", nba), ("cfb", cfb)):
        for key in src:
            assert key in markets.WORDS, (
                f"{name} prices {key!r} and engine/markets.py has never "
                f"heard of it — the splits table will render it raw")


def test_the_markets_that_shipped_raw_are_named():
    """The four from Ethan's screenshot, plus the rest of the hoops
    vocabulary that would have followed them onto the page."""
    for key, word in (("reb", "Rebounds"), ("ast", "Assists"),
                      ("pts", "Points"), ("fg3m", "3-Pointers Made"),
                      ("pra", "Pts+Reb+Ast"), ("stl", "Steals"),
                      ("blk", "Blocks")):
        assert markets.label(key) == word, \
            f"{key} reads {markets.label(key)!r}, expected {word!r}"


def test_no_real_market_relies_on_the_prettifier():
    """Every market the journal can hold is NAMED. Title-casing an id is
    the net under a new feed, not how the site is supposed to read —
    `fg3m` prettifies to "Fg3m", which is not English either."""
    for key in ("reb", "ast", "pts", "fg3m", "pra", "stl", "blk",
                "total_bases", "hits", "home_runs", "strikeouts", "outs",
                "pass_yds", "rush_yds", "rec_yds", "receptions",
                "anytime_td", "moneyline", "spread", "total", "team_total",
                "method", "distance", "fighter_finish", "first_3_innings"):
        assert key in markets.WORDS, (
            f"{key} is not named — it would reach the page as "
            f"{markets.prettify(key)!r} via the fallback")


def test_an_unknown_id_is_still_readable():
    assert markets.label("first_3_innings") == "First 3 Innings"
    assert markets.label("some_new_market") == "Some New Market"
    assert markets.label("") == "—"
    assert markets.label(None) == "—"


def test_no_market_is_named_with_its_own_id():
    """A word that is just the key retyped is a miss wearing a hat."""
    for key, word in markets.WORDS.items():
        assert word != key, f"{key} is 'named' with its own id"
        assert word.strip(), f"{key} has an empty word"


# --- the wiring -----------------------------------------------------------

def test_the_payload_carries_the_words():
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    path = os.path.join(tempfile.mkdtemp(), "record.json")
    ledger.export_json(conn, path)
    d = json.load(open(path, encoding="utf-8"))
    assert "market_words" in d, "the payload stopped carrying market_words"
    assert d["market_words"]["reb"] == "Rebounds"
    # A copy, not the live dict — a caller mutating the payload must not
    # rewrite the engine's vocabulary for the rest of the process.
    d["market_words"]["reb"] = "mutated"
    assert markets.WORDS["reb"] == "Rebounds"


def test_the_front_end_reads_the_payload_and_keeps_no_map():
    """The specific thing that drifted. If a hand-typed table comes back
    here, so does the bug."""
    assert "const MARKET_WORDS = {" not in APP, \
        "the front end is keeping its own market vocabulary again"
    assert "_marketWords = d.market_words || {}" in APP, \
        "the splits table is no longer fed from the payload"
    assert "[marketWord(k), v]" in APP, \
        "the splits table stopped translating its market ids"


def test_only_the_market_split_is_translated():
    """Grades, sides and book names are already words. Running "OVER" or
    "DraftKings" through a market map would be a lookup that can only
    miss."""
    i = APP.index("function recSplitsSection(")
    seg = APP[i:i + 900]
    assert 'cur[0] === "market"' in seg, \
        "every split is being run through the market vocabulary"


# --- the header row -------------------------------------------------------

def test_the_bar_column_has_a_heading_rather_than_an_empty_bar():
    """The header row held an empty `.rb-bar`, which still painted its
    own grey track: a blank slot that read as a rendering fault. And the
    orange stub under it had nothing saying what it measured."""
    i = APP.index('<div class="rb-row rb-labels">')
    head = APP[i:i + 700]
    assert '<span class="rb-bar"></span>' not in head, \
        "the empty grey bar is back in the splits header"
    assert '<span class="rb-barh">Win</span>' in head, \
        "the win-rate column lost its heading"
    css = open(os.path.join(ROOT, "web", "css", "styles.css"),
               encoding="utf-8").read()
    assert ".rb-barh {" in css, "the heading has no style"


def test_the_bar_says_what_it_is_to_a_screen_reader():
    """It was `aria-hidden`, which is right for decoration and wrong for
    the only win-rate signal in the table."""
    i = APP.index('<span class="rb-bar" role="img"')
    seg = APP[i:i + 260]
    assert "aria-label=" in seg, \
        "the win-rate bar is hidden from a screen reader again"
    # The words themselves are built one line above, so follow the
    # variable rather than grepping the tag for prose that is not in it.
    j = APP.rindex("const pct = ", 0, i)
    assert "win rate" in APP[j:i], \
        "the bar's spoken label stopped saying what it measures"
    assert "${pct}" in seg, "the label no longer uses that sentence"


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
