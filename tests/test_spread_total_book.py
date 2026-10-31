"""The spread and the total say which book is posting them, per side.

Ethan, 2026-09-08: "I don't want you too stop working until we display
the right lines and prices the books show."

The moneyline was what he reported and what the Most Likely board ranks
on, so it was named first (`tests/test_which_book.py`). The other two
game markets were left publishing a shopped price under no name at all,
which is the identical defect one market over: a reader holding his
phone on DraftKings could not tell whether our Over -105 was DraftKings'.

Naming them needs the side, not just the market. The best price on the
Over and the best on the Under are routinely at different books, and so
are the two sides of a spread; a card that took the Under and printed
the Over's book would send a reader to a window that is not offering
that number — worse than printing nothing.

Two rules the resolvers inherit from the price they name, or the name
would be a lie:

  * the same book filter (the sharp reference is skipped — nobody here
    can bet it), and
  * the same published line. A book that has moved off the consensus
    number posts NEITHER side of it, so it names neither side. Where no
    book is at the line the parsers publish -110, a number nobody is
    offering, and that fallback gets NO book's name.

Run directly: `python3 tests/test_spread_total_book.py`
"""

import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.models import Game, Weather                         # noqa: E402
from engine.sources import oddsapi as oa                        # noqa: E402

TEAMS = {"Minnesota Vikings": "MIN", "Green Bay Packers": "GB"}


def _spread_book(key, title, line=-3.5, home=-110, away=-110):
    return {"key": key, "title": title, "markets": [{"key": "spreads", "outcomes": [
        {"name": "Minnesota Vikings", "point": line, "price": home},
        {"name": "Green Bay Packers", "point": -line, "price": away}]}]}


def _total_book(key, title, line=44.5, over=-110, under=-110):
    return {"key": key, "title": title, "markets": [{"key": "totals", "outcomes": [
        {"name": "Over", "point": line, "price": over},
        {"name": "Under", "point": line, "price": under}]}]}


def _event(books, eid="e1"):
    return {"id": eid, "home_team": "Minnesota Vikings",
            "away_team": "Green Bay Packers",
            "commence_time": "2026-09-13T20:25:00Z", "bookmakers": books}


# --- the spread resolver --------------------------------------------------------
def test_each_side_of_the_spread_is_named_by_the_book_posting_it():
    """DraftKings is best on the home side, FanDuel on the away side —
    the ordinary case, and the one a single-sided lookup gets wrong."""
    ev = _event([_spread_book("draftkings", "DraftKings", -3.5, -105, -118),
                 _spread_book("fanduel", "FanDuel", -3.5, -115, -102)])
    got = oa.best_spread_books(ev, TEAMS, "MIN", "GB")
    assert got == {"MIN": "DraftKings", "GB": "FanDuel"}, got
    # …and the prices they are named for are the ones we publish.
    assert oa.parse_event_spreads(ev, TEAMS, "MIN", "GB") == (-3.5, -105, -102)


def test_a_book_off_the_consensus_number_names_neither_side():
    """It is not quoting the line we publish, so its price is not the one
    on the card and its name has no business beside it."""
    ev = _event([_spread_book("draftkings", "DraftKings", -3.5, -110, -110),
                 _spread_book("fanduel", "FanDuel", -3.5, -112, -112),
                 _spread_book("betmgm", "BetMGM", -2.5, +100, +100)])
    got = oa.best_spread_books(ev, TEAMS, "MIN", "GB")
    assert "BetMGM" not in got.values(), got
    assert got == {"MIN": "DraftKings", "GB": "DraftKings"}, got


def test_the_sharp_reference_is_never_named_on_a_spread():
    ev = _event([_spread_book("pinnacle", "Pinnacle", -3.5, -102, -102),
                 _spread_book("draftkings", "DraftKings", -3.5, -110, -110)])
    got = oa.best_spread_books(ev, TEAMS, "MIN", "GB")
    assert got == {"MIN": "DraftKings", "GB": "DraftKings"}, got


def test_a_spread_side_with_no_quote_at_the_line_gets_no_name():
    """The parser publishes -110 there. Nobody is offering it, so nobody
    is named for it — a fabricated price must not carry a real book."""
    ev = _event([{"key": "draftkings", "title": "DraftKings", "markets": [
        {"key": "spreads", "outcomes": [
            {"name": "Minnesota Vikings", "point": -3.5, "price": -105}]}]}])
    assert oa.parse_event_spreads(ev, TEAMS, "MIN", "GB") == (-3.5, -105, -110)
    got = oa.best_spread_books(ev, TEAMS, "MIN", "GB")
    assert got == {"MIN": "DraftKings"}, got


def test_a_spread_tie_goes_to_the_first_book_seen():
    ev = _event([_spread_book("draftkings", "DraftKings", -3.5, -110, -110),
                 _spread_book("fanduel", "FanDuel", -3.5, -110, -110)])
    got = oa.best_spread_books(ev, TEAMS, "MIN", "GB")
    assert got == {"MIN": "DraftKings", "GB": "DraftKings"}, got


def test_no_spread_in_the_payload_names_nobody():
    assert oa.best_spread_books(_event([]), TEAMS, "MIN", "GB") == {}


# --- the total resolver ---------------------------------------------------------
def test_each_side_of_the_total_is_named_by_the_book_posting_it():
    ev = _event([_total_book("draftkings", "DraftKings", 44.5, -104, -120),
                 _total_book("fanduel", "FanDuel", 44.5, -118, -101)])
    got = oa.best_total_books(ev)
    assert got == {"over": "DraftKings", "under": "FanDuel"}, got
    assert oa.parse_event_totals(ev) == (44.5, -104, -101)


def test_a_book_off_the_consensus_total_names_neither_side():
    ev = _event([_total_book("draftkings", "DraftKings", 44.5, -110, -110),
                 _total_book("fanduel", "FanDuel", 44.5, -112, -112),
                 _total_book("betmgm", "BetMGM", 47.5, +105, +105)])
    got = oa.best_total_books(ev)
    assert "BetMGM" not in got.values(), got


def test_the_sharp_reference_is_never_named_on_a_total():
    ev = _event([_total_book("pinnacle", "Pinnacle", 44.5, -101, -101),
                 _total_book("draftkings", "DraftKings", 44.5, -110, -110)])
    assert oa.best_total_books(ev) == {"over": "DraftKings",
                                       "under": "DraftKings"}


def test_a_total_side_with_no_quote_at_the_line_gets_no_name():
    ev = _event([{"key": "draftkings", "title": "DraftKings", "markets": [
        {"key": "totals", "outcomes": [
            {"name": "Over", "point": 44.5, "price": -104}]}]}])
    assert oa.parse_event_totals(ev) == (44.5, -104, -110)
    assert oa.best_total_books(ev) == {"over": "DraftKings"}


# --- one walk, so the name cannot disagree with the number ----------------------
def test_the_resolver_reads_the_same_quotes_the_parser_prices_from():
    """Not a style point. Two separate walks over the payload can pick
    two different books for one price — the defect this whole line of
    work exists to end — so both readers share one collector."""
    ev = _event([_spread_book("draftkings", "DraftKings", -3.5, -108, -114),
                 _spread_book("fanduel", "FanDuel", -3.5, -112, -106)])
    line, home_odds, away_odds = oa.parse_event_spreads(ev, TEAMS, "MIN", "GB")
    books = oa.best_spread_books(ev, TEAMS, "MIN", "GB")
    home_pts, away_pts = oa._spread_quotes(ev, TEAMS, "MIN", "GB")
    # The book named for each side really is quoting the price published.
    assert (line, home_odds, away_odds) == (-3.5, -108, -106)
    assert (home_odds, books["MIN"]) in [(pr, bk) for p, pr, bk in home_pts
                                         if p == line]
    assert (away_odds, books["GB"]) in [(pr, bk) for p, pr, bk in away_pts
                                        if p == -line]


# --- onto the game, and onto the card -------------------------------------------
class _Slate:
    def __init__(self, games):
        self.games, self.date, self.props = games, "2026-09-13", []


def test_the_slate_pull_writes_both_sides_of_both_markets_onto_the_game():
    g = Game(home="MIN", away="GB", weather=Weather(), date="2026-09-13",
             kickoff="2026-09-13T20:25:00Z")
    ev = _event([_spread_book("draftkings", "DraftKings", -3.5, -105, -118),
                 _spread_book("fanduel", "FanDuel", -3.5, -115, -102)])
    ev["bookmakers"][0]["markets"].append(
        _total_book("draftkings", "DraftKings", 44.5, -104, -120)["markets"][0])
    ev["bookmakers"][1]["markets"].append(
        _total_book("fanduel", "FanDuel", 44.5, -118, -101)["markets"][0])
    tmp = tempfile.mkdtemp()
    real = oa.CACHE_DIR
    oa.CACHE_DIR = __import__("pathlib").Path(tmp)
    path = oa.CACHE_DIR / "odds_board_nfl_lines.json"
    path.write_text(json.dumps([ev]))
    old = time.time() - 600
    os.utime(path, (old, old))
    try:
        oa.apply_board_lines_to_slate(_Slate([g]), api_key="k", cache_only=True)
    finally:
        oa.CACHE_DIR = real
    assert (g.spread, g.spread_home_odds, g.spread_away_odds) == (-3.5, -105, -102)
    assert g.home_spread_book == "DraftKings" and g.away_spread_book == "FanDuel"
    assert (g.total, g.total_over_odds, g.total_under_odds) == (44.5, -104, -101)
    assert g.total_over_book == "DraftKings" and g.total_under_book == "FanDuel"


def _cards(**kw):
    from engine.pipeline import _finish_bet
    from engine.rules import RuleConfig
    g = Game(home="MIN", away="GB", weather=Weather(), date="2026-09-13", **kw)
    cfg = RuleConfig()
    out = {}
    for d in [{"bet_type": "spread", "team": "MIN", "grade": "B",
               "confidence": 7.0, "edge": 0.03, "odds": -105},
              {"bet_type": "spread", "team": "GB", "grade": "B",
               "confidence": 7.0, "edge": 0.03, "odds": -102},
              {"bet_type": "total", "side": "Over", "grade": "B",
               "confidence": 7.0, "edge": 0.03, "odds": -104},
              {"bet_type": "total", "side": "Under", "grade": "B",
               "confidence": 7.0, "edge": 0.03, "odds": -101},
              {"bet_type": "team_total", "team": "MIN", "side": "Over",
               "grade": "B", "confidence": 7.0, "edge": 0.03, "odds": -110}]:
        key = d["bet_type"] + ":" + (d.get("team") or d.get("side") or "")
        out[key] = _finish_bet(dict(d), g, cfg)
    return out


def test_the_card_names_the_book_for_the_side_it_actually_took():
    """Both sides ride along and `book` is the one taken. An away spread
    card printing the home side's book is the failure that makes naming
    the book worse than leaving it blank."""
    got = _cards(spread=-3.5, spread_home_odds=-105, spread_away_odds=-102,
                 home_spread_book="DraftKings", away_spread_book="FanDuel",
                 total=44.5, total_over_odds=-104, total_under_odds=-101,
                 total_over_book="DraftKings", total_under_book="FanDuel")
    assert got["spread:MIN"]["book"] == "DraftKings"
    assert got["spread:GB"]["book"] == "FanDuel"
    assert got["spread:GB"]["home_book"] == "DraftKings"
    assert got["spread:GB"]["away_book"] == "FanDuel"
    assert got["total:Over"]["book"] == "DraftKings"
    assert got["total:Under"]["book"] == "FanDuel"
    assert got["total:Under"]["over_book"] == "DraftKings"
    assert got["total:Under"]["under_book"] == "FanDuel"


def test_a_team_total_carries_no_book_because_no_book_quotes_it():
    """It is derived from the game total and the spread, not read off a
    menu. An empty book is the honest answer; borrowing the game total's
    would name a book for a number it never posted."""
    got = _cards(spread=-3.5, total=44.5, total_over_book="DraftKings",
                 total_under_book="FanDuel", home_spread_book="DraftKings")
    assert got["team_total:MIN"].get("book", "") == ""


def test_a_game_priced_before_the_books_were_named_still_builds_a_card():
    """Older board files carry no book fields at all; the card must come
    out blank rather than raising."""
    got = _cards(spread=-3.5, total=44.5)
    assert got["spread:MIN"]["book"] == "" and got["total:Over"]["book"] == ""


# --- and the college board, which was naming the wrong book -------------------
def _cfb_event():
    """Both sides genuinely split, because that is the ordinary case and
    the one a single-sided lookup gets wrong: DraftKings is best on the
    away spread and the Over, FanDuel on the home spread and the Under."""
    def book(key, title, spread, total):
        return {"key": key, "title": title, "markets": [
            {"key": "h2h", "outcomes": [
                {"name": "Toledo Rockets", "price": -160},
                {"name": "Bowling Green Falcons", "price": 140}]},
            {"key": "spreads", "outcomes": [
                {"name": "Toledo Rockets", "point": -3.5, "price": spread[0]},
                {"name": "Bowling Green Falcons", "point": 3.5, "price": spread[1]}]},
            {"key": "totals", "outcomes": [
                {"name": "Over", "point": 52.5, "price": total[0]},
                {"name": "Under", "point": 52.5, "price": total[1]}]}]}
    return {"id": "ev1", "home_team": "Toledo Rockets",
            "away_team": "Bowling Green Falcons",
            "bookmakers": [book("draftkings", "DraftKings", (-110, -110), (-110, -110)),
                           book("fanduel", "FanDuel", (-108, -112), (-112, -108))]}


def test_the_college_pull_keys_its_books_by_side():
    import cfb_build as CB
    from engine.sources import oddsapi
    real = oddsapi.fetch_sport_odds
    oddsapi.fetch_sport_odds = lambda *a, **k: ([_cfb_event()], {})
    game = {"game_id": "g0", "home": "TOL", "away": "BGSU",
            "kickoff": "2026-09-12T19:30Z", "date": "2026-09-12"}
    try:
        priced, _note = CB.attach_odds(
            [game], {"toledo": "TOL", "bowling green": "BGSU"}, cache_only=True)
    finally:
        oddsapi.fetch_sport_odds = real
    entry = priced["g0"]
    assert entry["spread_books"] == {"TOL": "FanDuel", "BGSU": "DraftKings"}, entry
    assert entry["total_books"] == {"over": "DraftKings", "under": "FanDuel"}, entry


def test_the_college_card_names_the_side_it_took_not_the_home_side():
    """What `_books_for` did: one lookup on the home spread and the Over,
    handed to every card in the market. On this payload that put
    FanDuel's name on a Bowling Green +3.5 card DraftKings is posting,
    and DraftKings' on an Under FanDuel is posting."""
    import cfb_build as CB
    lines = {"spread_books": {"TOL": "FanDuel", "BGSU": "DraftKings"},
             "total_books": {"over": "DraftKings", "under": "FanDuel"},
             "ml_books": {"TOL": "DraftKings", "BGSU": "FanDuel"}}
    at = lambda m, team="", side="": CB._book_for_side(m, team, side, lines,
                                                       "TOL", "BGSU")
    assert at("spread", team="TOL") == "FanDuel"
    assert at("side", team="BGSU") == "DraftKings"
    assert at("total", side="Over") == "DraftKings"
    assert at("total", side="Under") == "FanDuel"
    assert at("moneyline", team="BGSU") == "FanDuel"
    # Nothing quotes a team total, so nothing is named for one.
    assert at("team_total", team="TOL", side="Over") == ""
    # A board built before the side-keyed maps existed names nobody
    # rather than raising or borrowing a neighbouring market's book.
    assert CB._book_for_side("total", "", "Under", {}, "TOL", "BGSU") == ""


def test_the_college_board_names_the_book_on_an_away_spread_and_an_under():
    """Through `build_plays`, not just the resolver — because the wiring
    is where the old bug lived. The model here hates the home side of a
    -14.5 spread and hates an 80.5 total, so the two cards it builds are
    the AWAY spread and the UNDER: exactly the two `_books_for` named
    wrong, and the two a reader would have taken to the wrong window."""
    import cfb_build as CB
    from engine.cfb import ratings as CR
    from engine.teamrates import TeamRating
    game = {"game_id": "g0", "home": "TOL", "away": "BGSU",
            "home_conference": "SEC", "away_conference": "SEC",
            "home_rank": None, "away_rank": None, "weekday": "Saturday",
            "kickoff": "2026-09-12T19:30Z", "date": "2026-09-12",
            "neutral_site": False, "label": "BGSU @ TOL",
            "state": "scheduled", "qb_confirmed": True,
            "participation_verified": True, "weather_checked": True,
            "indoor": False}
    ratings = {"TOL": TeamRating(net=3.0, off=2.0, def_=-1.0, games=13),
               "BGSU": TeamRating(net=0.0, off=0.5, def_=0.5, games=13)}
    lines = {"g0": {"moneyline": (-160, 140), "spread": (-14.5, -110, -110),
                    "total": (80.5, -110, -110),
                    "ml_books": {"TOL": "FanDuel", "BGSU": "DraftKings"},
                    "spread_books": {"TOL": "FanDuel", "BGSU": "DraftKings"},
                    "total_books": {"over": "FanDuel", "under": "DraftKings"}}}
    plays = {p["market"]: p for p in
             CB.build_plays([game], lines, ratings, CR.PRIOR, {}, {},
                            skip=CB._taken_by_sharp([]))}
    assert plays["side"]["shared"]["team"] == "BGSU", plays["side"]["selection"]
    assert plays["side"]["book"] == "DraftKings", plays["side"]
    assert plays["total"]["shared"]["side"] == "Under", plays["total"]["selection"]
    assert plays["total"]["book"] == "DraftKings", plays["total"]
    # Both sides ride along for each, the way the NFL card carries them.
    assert plays["side"]["home_book"] == "FanDuel"
    assert plays["side"]["away_book"] == "DraftKings"
    assert plays["total"]["over_book"] == "FanDuel"
    assert plays["total"]["under_book"] == "DraftKings"


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
