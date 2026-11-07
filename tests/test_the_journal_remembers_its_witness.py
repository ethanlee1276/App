"""Fifty-seven columns, and never the one that says what was selected on.

Chasing why the Edge book runs at CLV -0.12 over 828 settled bets, the
obvious question is whether the sharp-anchored rows carry it and the
model rows drag it down. That question cannot be asked. The journal
records `raw_prob`, `cal_temp`, `cal_bias`, `closing_odds`,
`fair_consensus`, `consensus_books`, `move_delta`, `move_steam`,
`velo_delta`, `tto_proj`, `opp_zone_rate` — every signal anybody
thought to store — and nothing at all about WHICH WITNESS said the
price was wrong. The ledger's own comment says so in passing: "the
ranking turns on which WITNESS backed the fair, and `bets` carries odds
and edge but not".

This module has learned that lesson three times and written it down
each time. `cal_temp` exists because "you cannot measure a signal you
do not store". `shrink_in_force` exists because "a row that does not
remember what priced it cannot be re-judged when the fit moves".
`move_delta` exists because movement was called "purely informational"
for months while it was rejecting picks outright. The witness is the
fourth, and it is the one the Edge board's own rebuild turns on.

ONLY THE BOOKS THAT PRICE AGAINST A FAIR WRITE IT. That is a boundary,
not an oversight — and the distinction matters because `game_day` WAS
an oversight (eight of eleven inserts forgot it, and 134 NFL rows sat
unsettleable in a bucket called "2026-W01"). A witness answers "whose
number says this price is wrong". A long shot, a prediction market, a
form pick and a UFC card are not selected that way, and stamping them
"model" would be inventing a fact about how they were chosen.

IT ONLY PAYS FORWARD. Nothing here retro-fills the rows already
settled; it makes the question answerable over the next few hundred.

EVERY DATE IS DERIVED FROM THE CLOCK, as house style and no more than
that. A fixture spelling a date out passes on the day it is written and
can fail at a later midnight — which is what happened to
tests/test_the_days_pick_is_decided_once_not_re_decided_hourly.py two
days after it shipped.

MEASURED HERE, HOWEVER: it makes no difference to these inserts today.
A row dated eight days ago journals exactly as one dated tomorrow does,
because `in_play_reason` needs more than a stale `game_date` to refuse.
So this is hygiene against a guard that may tighten, not a dependency
being relied on — said plainly because an unverified "this is why"
comment is worse than none.

Run directly:
`python3 tests/test_the_journal_remembers_its_witness.py`
"""

import datetime as dt
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import ledger, potd                              # noqa: E402

SRC = (ROOT / "engine" / "ledger.py").read_text(encoding="utf-8")

#: Tomorrow, so `in_play_reason` cannot refuse the row for having
#: started. Derived, never spelled — see the module docstring.
SOON = (dt.datetime.utcnow() + dt.timedelta(days=1)).date().isoformat()


def _ledger():
    conn = ledger.connect(Path(tempfile.mkdtemp()) / "l.db")
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1)
    return conn


def _prop(**kw):
    row = {"player": "Josh Allen", "team": "BUF", "opponent": "NYJ",
           "market": "pass_yds", "market_label": "Passing Yards",
           "side": "OVER", "line": 240.5, "book": "fanduel", "odds": -115,
           "hit_prob": 0.62, "raw_prob": 0.62, "implied_prob": 0.56,
           "model_prob": 0.62, "projection": 262.0,
           "game_date": SOON, "date": SOON, "kickoff": "13:00",
           "has_market": True, "recommended": True, "edge": 0.06,
           "confidence": 0.7, "grade": "A", "stake_units": 1.0,
           "logs": [], "recent_values": []}
    row.update(kw)
    return row


def _game(**kw):
    """A recommended moneyline. `pick` is the side — `log_recommendations`
    reads the team off THAT, not off `team`, and a fixture without it
    journals nothing while looking correct."""
    row = {"recommended": True, "bet_type": "moneyline",
           "market": "moneyline", "pick": "BUF", "team": "BUF",
           "home": "BUF", "away": "NYJ", "book": "fanduel", "odds": -122,
           "win_prob": 0.58, "edge": 0.03, "confidence": 0.7,
           "grade": "B+", "stake_units": 1.0, "date": SOON,
           "game_date": SOON}
    row.update(kw)
    return row


class _Hostile(dict):
    """A row whose own `get` throws something other than AttributeError.

    Mutation is why this exists: narrowing the guard to `except
    AttributeError` passed every earlier case, because `None`, a string
    and an int all fail on `.get` in exactly that way. A dict subclass
    that misbehaves is the shape a real one takes — a row built by a
    caller that wrapped it — and it is what proves the guard is broad.
    """

    def get(self, *a, **k):
        raise RuntimeError("this row will not be read")

    def __bool__(self):
        # TRUTHY ON PURPOSE. `evidence_for` does `row or {}`, so an EMPTY
        # hostile dict is replaced by a plain one and never reaches the
        # code under test — which is how the first version of this passed
        # against a deliberately narrowed guard.
        return True


# --- one rule, shared with the card ------------------------------------
def test_the_tier_is_potds_rule_not_a_second_one():
    """A journalled tier that could disagree with the tier the reader was
    shown would be worse than none: two answers to one question, and the
    record the quieter of them."""
    body = SRC[SRC.index("def evidence_for("):]
    body = body[:body.index("\ndef ", 10)]
    assert "_potd.evidence(" in body, "the tier is recomputed here"


def test_every_witness_the_card_can_show_round_trips():
    for row, want in (({"exchange_fair": 0.55}, "exchange"),
                      ({"sharp_anchored": True, "sharp_fair": 0.55}, "sharp"),
                      ({"prob_source": "sharp"}, "sharp"),
                      ({"prob_source": "market", "implied_prob": 0.55},
                       "market"),
                      ({}, "model")):
        assert ledger.evidence_for(row) == want, row
        assert potd.evidence(row) == want, "the two rules disagree"


def test_a_row_it_cannot_read_costs_its_own_label_not_the_journal():
    """This runs inside the insert loop for every bet on every board, so
    a row shaped unexpectedly must cost its own label and nothing else."""
    for bad in (None, "not a row", 7, _Hostile()):
        assert isinstance(ledger.evidence_for(bad), str), bad


# --- the books that write it -------------------------------------------
def test_the_witnessed_books_are_the_ones_priced_against_a_fair():
    assert set(ledger.WITNESSED_BOOKS) == {
        "main", "paper", "potd", "likely", "likely_live"}, \
        ledger.WITNESSED_BOOKS
    assert set(ledger.BOOK) <= set(ledger.WITNESSED_BOOKS)
    assert set(ledger.LIKELY_BOOKS) <= set(ledger.WITNESSED_BOOKS)
    assert ledger.POTD_CATEGORY in ledger.WITNESSED_BOOKS
    # BUILT FROM THE LISTS IN FORCE, NOT SPELLED OUT — and that is a
    # claim about the SOURCE, because a literal tuple with today's five
    # names in it satisfies every assertion above. The whole point of
    # deriving it is that adding a category to `LIKELY_BOOKS` tomorrow
    # carries it here; a copy silently would not, and the copy is what
    # the test has to be able to refuse.
    decl = SRC[SRC.index("WITNESSED_BOOKS ="):]
    decl = decl[:decl.index("\n")]
    assert "BOOK" in decl and "LIKELY_BOOKS" in decl \
        and "POTD_CATEGORY" in decl, decl
    assert '"' not in decl, f"the book list is hand-copied: {decl}"


def test_the_boundary_is_written_down_where_the_column_is_made():
    """`game_day` was forgotten by eight of eleven inserts and nothing
    said so. An omission that is DELIBERATE has to be distinguishable
    from that, in the place a reader meets the column."""
    i = SRC.index("ALTER TABLE bets ADD COLUMN evidence")
    why = SRC[max(0, i - 2400):i]
    assert "deliberate" in why, "nothing says the omission is on purpose"
    assert "game_day" in why, "the precedent it must not be mistaken for"


def test_every_witnessed_book_names_the_column_in_its_insert():
    """THE RULE, CHECKED AT THE INSERTS, which is where `game_day` was
    broken. Read off the source so a book added after today is held to
    it too — and per STATEMENT, because `log_recommendations` writes two
    of them and the first pass stamped only one."""
    for fn in ("log_recommendations", "log_most_likely",
               "log_pick_of_the_day"):
        body = SRC[SRC.index(f"def {fn}("):]
        body = body[:body.index("\ndef ", 10)]
        stmts = re.findall(r"INSERT OR IGNORE INTO bets \(([^)]*)\)", body)
        assert stmts, fn
        for stmt in stmts:
            assert "evidence" in stmt, f"{fn} has an insert with no witness"
        assert body.count("evidence_for(") >= len(stmts), \
            f"{fn} names the column more often than it fills it"


# --- and it survives the write -----------------------------------------
def test_an_edge_prop_remembers_a_sharp_anchor():
    conn = _ledger()
    ledger.log_recommendations(conn, {
        "sport": "nfl", "date": SOON,
        "recommendations": [_prop(sharp_anchored=True, sharp_fair=0.60)]})
    got = conn.execute("SELECT category, evidence FROM bets").fetchone()
    assert got["evidence"] == "sharp", dict(got)
    assert got["category"] in ledger.WITNESSED_BOOKS, dict(got)


def test_an_edge_GAME_bet_remembers_its_witness_too():
    """THE ONE THE RULE TEST CAUGHT AND A BEHAVIOURAL TEST MISSED.
    `log_recommendations` writes the Edge book through TWO inserts —
    props and game bets — and the first pass stamped only the props.
    Scanning the body for `evidence_for(` still passed, because the
    props call was there. Only a game bet written and read back finds
    it."""
    conn = _ledger()
    ledger.log_recommendations(conn, {
        "sport": "nfl", "date": SOON, "recommendations": [],
        "game_bets": [_game(sharp_anchored=True, sharp_fair=0.60)]})
    rows = conn.execute("SELECT player, evidence FROM bets").fetchall()
    assert rows, "the game bet was not journalled at all"
    assert all(r["evidence"] == "sharp" for r in rows), [dict(r) for r in rows]


def test_an_edge_bet_with_only_our_own_number_says_model():
    conn = _ledger()
    ledger.log_recommendations(conn, {
        "sport": "nfl", "date": SOON, "recommendations": [_prop()]})
    assert conn.execute(
        "SELECT evidence FROM bets").fetchone()["evidence"] == "model"


def test_the_days_pick_remembers_its_witness():
    conn = _ledger()
    n = ledger.log_pick_of_the_day(conn, {
        "sport": "nfl", "date": SOON,
        "pick": {"player": "BUF", "team": "BUF", "market": "moneyline",
                 "bet_type": "moneyline", "side": "", "line": 0.0,
                 "book": "fanduel", "odds": -122, "model_prob": 0.58,
                 "implied_prob": 0.55, "prob_source": "market",
                 "game_date": SOON}})
    assert n == 1
    assert conn.execute(
        "SELECT evidence FROM bets").fetchone()["evidence"] == "market"


def test_the_likelihood_board_remembers_its_witness():
    from engine import likely
    conn = _ledger()
    row = likely.from_prop(_prop(), lambda m: True, sport="nfl")
    assert row, "the fixture no longer produces a likelihood row"
    row["sharp_anchored"], row["sharp_fair"] = True, 0.60
    assert ledger.log_most_likely(conn, {"most_likely": [row]}) == 1
    got = conn.execute("SELECT category, evidence FROM bets").fetchone()
    assert got["evidence"] == "sharp", dict(got)


def test_the_column_is_added_by_migration_not_only_by_a_fresh_schema():
    """Every live ledger predates it, so a CREATE-TABLE-only change would
    ship a column that exists on nobody's database."""
    assert "ALTER TABLE bets ADD COLUMN evidence" in SRC
    conn = _ledger()
    cols = [r[1] for r in conn.execute("PRAGMA table_info(bets)")]
    assert "evidence" in cols


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{fails} failed" if fails else f"\n{ran} tests passed.")
    sys.exit(1 if fails else 0)
