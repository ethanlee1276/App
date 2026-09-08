"""The board never publishes a blank page — and never a number we doubt.

Ethan, 2026-09-08: "Also I don't want an empty boar either we need to
have picks period."

Two days earlier the same person raised MIN_PROB to 0.55 himself, having
been shown that it costs about half the game-lines shelf. Both stand.
They only look contradictory if the board has ONE bar, and the fix is
that it has two: 0.55 is still what it takes to be called a pick, and
`RESERVE_MIN_PROB` is the floor for what gets shown when nothing clears
that — labelled, capped, unstaked and out of the book.

WHICH REFUSALS MAY MOVE, which is the whole of the design. A refusal on
this board is one of two kinds:

  * the number is WRONG or unknown — a proxy price, a price no book could
    post, a probability that disagrees with the market past
    MAX_CREDIBLE_EDGE, a moneyline contradicting its own spread, a player
    held for injury. NONE of these move. "We need picks" is not a reason
    to publish a number we believe is false, and publishing numbers we
    doubt is the failure the whole of 2026-09-08 was spent removing.
  * the bet is not ATTRACTIVE enough — the likelihood floor, and the
    -250 chalk cap. Those are product judgements, and a product
    judgement that empties the page is the owner's to overrule.

Only the FLOOR moves, and the cap is deliberately left alone: the cap
exists because of Ethan's own complaint on 2026-09-01 about "grabbing
random -1200 props", so widening it to fill a quiet night would answer
today's instruction by re-creating the bug he reported.

Run directly: `python3 tests/test_board_never_empty.py`
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine import ledger                                       # noqa: E402
from engine import likely as K                                  # noqa: E402

def _ml(**kw):
    """An NFL moneyline card, as `pipeline._finish_bet` publishes one."""
    d = dict(bet_type="moneyline", market="moneyline", market_label="Moneyline",
             has_market=True, home="DET", away="NO", team="DET", pick="DET",
             pick_is_home=True, pick_label="DET ML", side="", line=0.0,
             matchup="NO @ DET", win_prob=0.66, fair_prob=0.62, edge=0.04,
             odds=-165, home_odds=-165, away_odds=140, book="DraftKings",
             ev_per_unit=0.05, confidence=6.0, stake_units=0.5,
             grade="B", credible=True, headline="DET ML",
             reasons=["Power rating: DET +4.1 vs NO -1.2"], recommended=True,
             live=False, date="2026-09-14", kickoff="2026-09-14T17:00:00+00:00")
    d.update(kw)
    return d


def _coinflip(**kw):
    """A card BOTH of whose sides sit under the floor.

    Worth its own helper, because the obvious fixture is wrong:
    `from_game_bet` shows the likelier side, so a card at 0.44 becomes a
    0.56 row and clears the floor comfortably. Only a game near 50/50
    leaves the board with nothing.
    """
    d = dict(win_prob=0.52, fair_prob=0.51, odds=-110,
             home_odds=-110, away_odds=-110)
    d.update(kw)
    return _ml(**d)


# --- an ordinary night is untouched ---------------------------------------
def test_a_board_that_clears_the_bar_never_reaches_the_reserve():
    census = {}
    got = K.build([], game_bets=[_ml()], census=census)
    assert len(got) == 1, got
    assert not any(r.get("reserve") for r in got), got
    assert census == {}, census


# --- and a night that clears nothing still has something on it ------------
def test_nothing_clears_the_floor_so_the_closest_rows_ship_labelled():
    census = {}
    got = K.build([], game_bets=[_coinflip()], census=census)
    assert len(got) == 1, "the page must not be blank"
    row = got[0]
    assert row["reserve"] is True, row
    assert row["reserve_note"] == K.RESERVE_NOTE
    # …and `bettable` is NOT commandeered to say so. It means the market
    # has a price worth staking against, and the card spends it on "No
    # bettable price here — this market's fit against the book ran off
    # the end of its range". Flipping it on a reserve row would put a
    # false sentence about a real price on the card in order to make a
    # true point about the probability. The row carries `reserve` for
    # that, and the book is protected in the journal instead.
    assert row["bettable"] is True, row
    # The census still reports what the REAL bar refused — that is the
    # honest answer to "why is the board short", and it stays a count of
    # REFUSALS ONLY. A "the reserve ran" entry was tried here and taken
    # back out: the page totals this dict as "N turned down", so a row
    # the board chose to SHOW would have been printed as one it turned
    # away. The rows carry `reserve` and that is the whole signal.
    assert census["under the likelihood floor"] == 1, census
    assert set(census) == {"under the likelihood floor"}, census


def _scorer(prob, odds=200, implied=0.33, **kw):
    """A touchdown watch row — a ONE-SIDED probability.

    The floor has to be tested on one of these, and finding that out is
    worth writing down: a game moneyline can never fall below 0.40,
    because the two sides sum to one and `from_game_bet` shows the
    likelier of them, so max(p, 1-p) >= 0.50 on every two-way market. A
    fixture built from moneylines cannot reach the reserve floor at all,
    and a test written on one passes whatever the floor is set to.
    """
    d = {"player": "A Scorer", "team": "DET", "opponent": "NO",
         "book": "DraftKings", "odds": odds, "model_prob": prob,
         "implied_prob": implied, "reasons": ["r"],
         "game_date": "2026-09-14", "kickoff": "2026-09-14T17:00:00+00:00"}
    d.update(kw)
    return d


def test_the_reserve_floor_is_a_floor_and_not_an_open_door():
    """Below RESERVE_MIN_PROB the words on the page stop being true, so
    the board goes empty and says so rather than calling 35% "likely"."""
    census = {}
    got = K.build([], td_watch=[_scorer(0.35)], census=census)
    assert got == [], got
    assert "under the likelihood floor" in census, census
    # …and one notch above it does ship, so the line above is the floor
    # doing the work rather than the row being broken some other way.
    got = K.build([], td_watch=[_scorer(0.45, implied=0.42)])
    assert len(got) == 1 and got[0]["reserve"] is True, got


def test_the_reserve_is_capped_so_a_quiet_night_still_reads_as_one():
    cards = [_coinflip(home=f"H{i}", away=f"A{i}", team=f"H{i}",
                       pick=f"H{i}", pick_label=f"H{i} ML",
                       matchup=f"A{i} @ H{i}")
             for i in range(K.RESERVE_LIMIT + 8)]
    got = K.build([], game_bets=cards)
    assert len(got) == K.RESERVE_LIMIT, len(got)
    assert all(r.get("reserve") for r in got)


def test_the_reserve_ships_the_LIKELIEST_rows_it_has():
    """It is still a likelihood board: when more rows are available than
    the cap carries, the ones kept are the top of the list.

    Tested with MORE rows than RESERVE_LIMIT on purpose. Under the cap
    every row survives and `build`'s final sort puts them in order
    whatever order they were chosen in — so a fixture of three cards
    passes even if the fallback picks its rows worst-first, which is
    exactly the bug this is here to catch.
    """
    n = K.RESERVE_LIMIT + 5
    probs = [round(0.41 + i * 0.008, 3) for i in range(n)]
    rows = [_scorer(p, implied=p, player=f"Scorer {i}") for i, p in enumerate(probs)]
    got = K.build([], td_watch=rows)
    assert len(got) == K.RESERVE_LIMIT, len(got)
    kept = sorted(r["model_prob"] for r in got)
    assert kept == sorted(probs)[-K.RESERVE_LIMIT:], kept
    # …and they are drawn in that order too.
    shown = [r["model_prob"] for r in got]
    assert shown == sorted(shown, reverse=True), shown


def test_the_label_actually_says_the_row_is_below_the_bar():
    """Pinned on the WORDS, not on the constant.

    `row["reserve_note"] == K.RESERVE_NOTE` proves the row carries
    whatever the module happens to say, which is true of any sentence at
    all — including a cheerful one. The label is the entire reason these
    rows are allowed to ship, so what it says is the thing to hold: it
    has to tell a reader this row did not clear the bar, and that it is
    not a recommendation.
    """
    note = K.RESERVE_NOTE.lower()
    assert "below" in note and "bar" in note, K.RESERVE_NOTE
    assert "not recommended" in note, K.RESERVE_NOTE


def test_the_reserve_cap_stays_under_the_board_caps():
    """The two caps that run after it must not silently trim the reserve.

    `_cut_players` keeps PER_MARKET rows per market and then back-fills
    to LIMIT, and game rows are cut at GAME_LIMIT — so a reserve smaller
    than both passes through whole, and needs no exemption. Raising
    RESERVE_LIMIT past either would start quietly cutting the fallback
    that exists so the page is not empty, which is the sort of thing that
    is found months later on a quiet Tuesday.
    """
    assert K.RESERVE_LIMIT <= K.GAME_LIMIT, "game rows would be trimmed"
    assert K.RESERVE_LIMIT <= K.LIMIT, "player rows would be trimmed"


# --- the bars that never move ---------------------------------------------
def _refused_even_when_empty(**kw):
    census = {}
    got = K.build([], game_bets=[_coinflip(**kw)], census=census)
    return got, census


def test_a_price_no_book_posted_is_still_refused_with_the_page_empty():
    got, census = _refused_even_when_empty(has_market=False)
    assert got == [], got
    assert census == {"no real book price": 1}, census


def test_a_proxy_price_is_still_refused_with_the_page_empty():
    got, _ = _refused_even_when_empty(book="proxy")
    assert got == [], got


def test_a_probability_the_market_contradicts_is_still_refused():
    got, census = _refused_even_when_empty(fair_prob=0.20)
    assert got == [], got
    assert any("disagrees with the market" in k for k in census), census


def test_a_player_held_for_injury_is_still_held_with_the_page_empty():
    """The hold is about whether the person plays. An empty page is not
    a reason to publish a bet on someone who may be inactive."""
    assert K.admissible({"model_prob": 0.9, "odds": -110, "book": "DK",
                         "injury_status": "Doubtful"},
                        floor=K.RESERVE_MIN_PROB) != ""


def test_the_chalk_cap_is_not_relaxed_to_fill_a_quiet_night():
    """Ethan, 2026-09-01: "just grabbing random -1200 props". Filling an
    empty board by widening THAT cap would answer one instruction by
    re-creating the bug behind another."""
    row = {"model_prob": 0.50, "odds": -400, "book": "DK",
           "implied_prob": 0.50}
    why = K.admissible(row, floor=K.RESERVE_MIN_PROB)
    assert "chalk" in why, why


def test_the_floor_is_the_only_bar_the_reserve_moves():
    """Read off the function rather than asserted in prose: `admissible`
    takes one override and spends it in one place."""
    import inspect
    src = inspect.getsource(K.admissible)
    assert src.count("_floor(floor)") == 1, src


# --- the book stays a record of rows that cleared the bar -----------------
def _journal(rows):
    conn = ledger.connect(":memory:")
    n = ledger.log_most_likely(conn, {"sport": "nfl", "date": "2026-W02",
                                      "most_likely": rows})
    return conn, n


def _jrow(**kw):
    d = {"player": "A Back", "market": "rush_yds", "side": "OVER", "line": 45.5,
         "odds": -110, "model_prob": 0.56, "implied_prob": 0.50,
         "book": "DraftKings", "projection": 60.0}
    d.update(kw)
    return d


def test_a_reserve_row_never_enters_the_likely_book():
    """The bucket exists to answer whether the figure a reader acted on
    was true. Rows the board itself says did not clear the bar would make
    that number answer a different question on exactly the quiet nights
    the record is thinnest."""
    _conn, n = _journal([_jrow(reserve=True)])
    assert n == 0, "a reserve row was journalled as a result"
    _conn, n = _journal([_jrow(), _jrow(player="B Back", reserve=True)])
    assert n == 1, "the reserve row rode in beside a real one"


# --- and the page says which kind of row it is drawing --------------------
def _node(js, *fns):
    """Run the named app.js functions in node, or skip where node is not
    installed."""
    import shutil, subprocess, tempfile
    node = shutil.which("node")
    if not node:
        return None
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    src = []
    for name in fns:
        i = app.index(f"function {name}(")
        src.append(app[i:app.index("\n}", i) + 2])
    prog = """
      var escapeHtml = (s) => String(s == null ? "" : s);
      var escapeAttr = (s) => String(s == null ? "" : s);
      %s
      console.log(JSON.stringify((() => { %s })()));
    """ % ("\n".join(src), js)
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_the_card_says_the_row_is_below_the_bar():
    got = _node("""
      return { on: reserveChip({ reserve: true, reserve_note: "NOTE HERE" }),
               off: reserveChip({ reserve: false }),
               bare: reserveChip({}),
               none: reserveChip(null) };
    """, "reserveChip")
    if got is None:
        return
    assert "below the bar" in got["on"], got["on"]
    assert "NOTE HERE" in got["on"], got["on"]
    # An ordinary row grows no chip — the label has to mean something.
    assert got["off"] == "" and got["bare"] == "" and got["none"] == ""


def test_the_page_no_longer_claims_it_would_rather_sit_empty():
    """That sentence was true until 2026-09-08 and is now the opposite of
    what the board does. Copy describing the old behaviour is worse than
    no copy: it tells a reader the page is doing something it isn't.

    Pinned on what the function RENDERS rather than on the file's text,
    because the file also carries a comment explaining the change — and
    a test that greps the source cannot tell the retired sentence from
    the note recording its retirement.
    """
    got = _node("""
      return { some: likelyEmptyWhy({ "under the likelihood floor": 3 }),
               none: likelyEmptyWhy({}) };
    """, "likelyEmptyWhy")
    if got is None:
        return
    assert "would rather sit empty" not in got["some"], got["some"]
    # The state that reaches this copy at all is now the one the reserve
    # could not fill — so it names what is actually wrong, the prices,
    # rather than blaming a bar the board has already stepped below.
    assert "no row could be priced" in got["some"], got["some"]
    assert "3 under the likelihood floor" in got["some"], got["some"]
    # An empty census is a different sentence: nothing was checked at all.
    assert "books post their menus" in got["none"], got["none"]


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
