"""The market's number on a preseason game — shown, recorded, not ours.

Ethan, 2026-08-14: "i wanna show props for the pre season. i wanna show
either money lines or over unders or whatever i dont car."

WHAT IS ON THE CARD IS THE BOOK'S NUMBER AND NOTHING ELSE, and these tests
hold that line in the two places it could be crossed. The renderer must
emit posted prices with no edge, stake, percentage or pick beside them;
and `prefit.prices_allowed` must stay shut, because a model number next to
a market number is a recommendation whether or not it is labelled one.

THE RECORDING IS THE REASON THE GATE CAN EVER OPEN. Nothing here has ever
stored a preseason closing line, which is exactly why "has the book missed
this" is unanswerable today. Every pull appends one, and in a few Augusts
that file is the sample.

THE COST IS THE OTHER THING PINNED. Three markets on the BOARD endpoint is
three credits for every fixture in the week; the same three on the event
endpoint would be three per game. That distinction is the whole reason
this is affordable, so the market list is asserted rather than trusted.
"""

import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()

from engine.nfl import prelines as pl                         # noqa: E402


def _event(home="Detroit Lions", away="Miami Dolphins",
           commence="2026-08-15T00:00:00Z", eid="e1",
           hp=-165, ap=140, spread=-3.0, total=38.5):
    """One board event in the shape the Odds API returns."""
    def book(key):
        return {"key": key, "title": key.title(), "markets": [
            {"key": "h2h", "outcomes": [{"name": home, "price": hp},
                                        {"name": away, "price": ap}]},
            {"key": "spreads", "outcomes": [
                {"name": home, "price": -110, "point": spread},
                {"name": away, "price": -110, "point": -spread}]},
            {"key": "totals", "outcomes": [
                {"name": "Over", "price": -110, "point": total},
                {"name": "Under", "price": -110, "point": total}]}]}
    return {"id": eid, "home_team": home, "away_team": away,
            "commence_time": commence,
            "bookmakers": [book("draftkings"), book("fanduel")]}


def _board(date="2026-08-15", kickoff="2026-08-15T00:00:00Z"):
    return {"season": 2026, "weeks": [{"week": 2, "games": [
        {"date": date, "home": "DET", "away": "MIA", "state": "pre",
         "kickoff": kickoff}]}]}


# --- the cost, which is the whole reason this is affordable -----------------
def test_three_markets_on_the_board_endpoint():
    """Per MARKET for the whole slate, not per game. The event endpoint
    bills the same three PER FIXTURE, which for a sixteen-game preseason
    week is 48 credits instead of 3."""
    assert pl.PRE_MARKETS == ("h2h", "spreads", "totals")
    assert pl.CREDITS_PER_PULL == len(pl.PRE_MARKETS) == 3


def test_the_pull_is_tagged_so_it_cannot_clobber_the_live_cache():
    """The odds cache is keyed by sport. A one-market live pull and this
    three-market one would otherwise overwrite each other, and whichever
    read second would conclude the books had stopped posting a market."""
    src = open(os.path.join(ROOT, "engine", "nfl", "prelines.py"),
               encoding="utf-8").read()
    assert 'cache_tag="pre"' in src


def test_the_cache_is_hours_not_seconds():
    assert pl.PRE_TTL >= 3600


# --- reading the board ------------------------------------------------------
def test_a_fixture_that_has_not_kicked_off_still_produces_a_row():
    """The opposite of the live chart's need. A preseason line is
    interesting BEFORE the game, which is the only time it can be read."""
    rows = pl.snapshot([_event()], ts=1000.0)
    assert len(rows) == 1
    r = rows[0]
    assert r["home"] == "DET" and r["away"] == "MIA"
    assert r["spread"] == -3.0 and r["total"] == 38.5
    assert r["home_odds"] == -165 and r["away_odds"] == 140


def test_the_de_vig_comes_from_the_shared_reader():
    """`livelines.snapshot_rows` already pairs both sides from the SAME
    book. A second copy of that rule here is a second place to get it
    wrong."""
    src = open(os.path.join(ROOT, "engine", "nfl", "prelines.py"),
               encoding="utf-8").read()
    assert "snapshot_rows" in src
    assert "devig" not in src.split('"""', 2)[-1], "the arithmetic was copied"


def test_a_team_we_cannot_name_is_dropped():
    rows = pl.snapshot([_event(home="Detroit Lions FC")], ts=1.0)
    assert rows == []


def test_the_commence_time_rides_along_for_matching():
    assert pl.snapshot([_event()], ts=1.0)[0]["commence"] == "2026-08-15T00:00:00Z"


# --- matching a price to a fixture ------------------------------------------
def test_the_pair_and_the_kickoff_both_have_to_agree():
    rows = pl.snapshot([_event()], ts=1.0)
    game = {"home": "DET", "away": "MIA", "kickoff": "2026-08-15T00:00:00Z"}
    assert pl.match(rows, game) is not None
    far = {"home": "DET", "away": "MIA", "kickoff": "2026-08-29T00:00:00Z"}
    assert pl.match(rows, far) is None


def test_the_home_side_is_not_interchangeable():
    """A reversed fixture is a different game, and its spread has the
    opposite sign. Matching on an unordered pair would put one game's
    number on the other."""
    rows = pl.snapshot([_event()], ts=1.0)
    assert pl.match(rows, {"home": "MIA", "away": "DET"}) is None


def test_an_unreadable_kickoff_still_matches_on_the_pair():
    """A fixture with no kickoff is not a reason to show nothing."""
    rows = pl.snapshot([_event()], ts=1.0)
    assert pl.match(rows, {"home": "DET", "away": "MIA"}) is not None


# --- recording, which is why the gate can ever open -------------------------
def test_a_pull_is_appended_and_reads_back():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "pre.jsonl")
        pl.record(pl.snapshot([_event()], ts=10.0), p)
        pl.record(pl.snapshot([_event(hp=-180)], ts=20.0), p)
        got = pl.load(p)
        assert len(got) == 2 and got[1]["home_odds"] == -180


def test_a_corrupt_line_does_not_lose_the_file():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "pre.jsonl")
        pl.record(pl.snapshot([_event()], ts=10.0), p)
        with open(p, "a", encoding="utf-8") as fh:
            fh.write("{not json\n")
        assert len(pl.load(p)) == 1


def test_the_newest_reading_is_the_one_shown():
    board = _board()
    rows = (pl.snapshot([_event(hp=-165)], ts=10.0)
            + pl.snapshot([_event(hp=-220)], ts=99.0))
    assert pl.attach(board, rows) == 1
    assert board["weeks"][0]["games"][0]["market"]["home_odds"] == -220


def test_the_attached_block_holds_only_the_book_s_own_fields():
    """`board_payload` has nowhere to put a price and `test_preseason_board`
    keeps it that way. This is the same guard one step later: the block
    this module hangs on a fixture is the market's reading and carries no
    field of ours."""
    board = _board()
    pl.attach(board, pl.snapshot([_event()], ts=1.0))
    got = set(board["weeks"][0]["games"][0]["market"])
    assert got == {"p_home", "books", "home_odds", "away_odds",
                   "spread", "total", "taken_at"}
    for banned in ("edge", "hit_prob", "projection", "stake_units",
                   "confidence", "grade", "pick", "recommended"):
        assert banned not in got


def test_attach_says_nothing_when_there_is_nothing_recorded():
    board = _board()
    assert pl.attach(board, []) == 0
    assert "market" not in board["weeks"][0]["games"][0]


# --- when we are allowed to spend -------------------------------------------
def test_a_finished_preseason_does_not_ask_the_pacer_at_all():
    """The board is live about five weeks a year. Asking the budget for
    three credits on a slate that finished in August is a question with a
    known answer, and forty-seven weeks of pointless state writes."""
    board = _board(date="2020-08-15")
    ok, why = pl.affordable(board, now=time.time())
    assert ok is False and "unplayed" in why


def test_an_upcoming_fixture_reaches_the_pacer():
    """And the pacer's answer — whatever it is — is the one that decides,
    so a live chart can never outbid tonight's real board."""
    import datetime as dt
    soon = (dt.date.today() + dt.timedelta(days=2)).isoformat()
    board = _board(date=soon, kickoff=soon + "T00:00:00Z")
    seen = {}
    from engine import oddsbudget
    real = oddsbudget.should_refresh

    def spy(n, **kw):
        seen["credits"] = n
        seen["sport"] = kw.get("sport")
        seen["share"] = kw.get("share")
        return False, "pacer said no"
    oddsbudget.should_refresh = spy
    try:
        ok, why = pl.affordable(board)
    finally:
        oddsbudget.should_refresh = real
    assert ok is False and why == "pacer said no"
    assert seen["credits"] == 3 and seen["sport"] == "nflpre"
    assert 0 < seen["share"] <= 0.1


def test_a_refused_pull_still_shows_the_last_number_seen():
    """Not spending is not a reason to show an empty card."""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "pre.jsonl")
        pl.record(pl.snapshot([_event()], ts=10.0), p)
        board = _board(date="2020-08-15")          # nothing upcoming: no spend
        n, note = pl.refresh(board, path=p)
        assert n == 1 and "unplayed" in note
        assert board["weeks"][0]["games"][0]["market"]["total"] == 38.5


# --- the card ---------------------------------------------------------------
def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}", i)]


def test_the_card_prints_the_posted_numbers():
    b = _fn("preseasonLineHTML")
    assert "m.spread" in b and "m.total" in b
    assert "m.home_odds" in b and "m.away_odds" in b


def test_the_card_carries_no_edge_no_stake_and_no_percentage():
    """A model number beside a market number is a recommendation whether
    or not it is labelled one. `p_home` is deliberately NOT drawn — a
    de-vigged probability on a card reads as a forecast, and this page
    does not have one."""
    b = _fn("preseasonLineHTML").lower()
    for word in ("edge", "stake", "units", "recommend", "p_home",
                 "ev_per_unit", "%"):
        assert word not in b, f"the preseason card emits {word!r}"


def test_a_fixture_with_no_price_renders_nothing():
    b = _fn("preseasonLineHTML")
    assert "if (!m) return \"\";" in b
    assert "if (!bits.length) return \"\";" in b


def test_the_spread_is_labelled_with_the_team_it_belongs_to():
    """A bare "-3" beside two team names is ambiguous, and the ambiguity
    resolves the wrong way half the time."""
    b = _fn("preseasonLineHTML")
    assert "escapeHtml(g.home)" in b and "m.spread" in b


def test_the_card_is_wired_into_the_fixture_row():
    assert "preseasonLineHTML(g)" in _fn("preseasonGameHTML")


def test_the_line_is_styled_as_agate_not_as_a_pick():
    for sel in (".pre-line", ".pre-line-lab", ".pre-line-n"):
        assert sel in CSS, sel
    i = CSS.index(".pre-line {")
    block = CSS[i:CSS.index("}", i)]
    assert "tabular-nums" in block


# --- why there is a line and no pick ----------------------------------------
def test_the_note_distinguishes_never_measured_from_measured_and_null():
    """A block that just stays quiet makes "we checked and there is
    nothing" look identical to "we never checked"."""
    b = _fn("preseasonFitHTML")
    assert "--prefit" in b
    assert '"insufficient"' in b and '"no"' in b


def test_the_page_says_the_number_is_the_book_s():
    i = APP.index("async function renderPreseason()")
    body = APP[i:APP.index("\nfunction ", i + 1)]
    assert "nothing here is ours" in body.lower()
    assert "preseasonFitHTML(data)" in body


def test_the_launcher_attaches_both_the_line_and_the_verdict():
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    i = src.index("def refresh_preseason(")
    body = src[i:src.index("\ndef ", i + 1)]
    assert "prelines" in body and 'payload["fit"]' in body


def test_the_gate_stays_shut_while_the_line_is_shown():
    """The one thing that must not drift: showing a market number is not a
    step towards pricing one, and nothing in this file opens that door."""
    from engine.nfl import prefit
    assert prefit.prices_allowed() is False


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
