"""The price on a game card says which book is posting it.

Ethan, 2026-09-08: "I don't want you too stop working until we display
the right lines and prices the books show."

Two halves to that. The first is not showing a price that is wrong — the
age ceiling and the spread-coherence bar. The second is this one: a
price a reader can CHECK. His cards said

    Moneyline · best

and "best" is not a window anyone can walk up to. We publish the best
number across the books we request, which is the right number and, until
now, a number with nobody's name on it: holding his phone open on
DraftKings he could not tell whether our -125 was DraftKings' -125, some
other book's, or ours.

`oddsapi.best_h2h_books` names it, under exactly the rule that chose the
price — the sharp reference skipped, because nobody here can bet it, and
naming a book that is not posting the number is worse than naming none.
Both sides are carried, because the two sides' best prices are routinely
at different books and the likelihood board flips a card to the
favourite; a flipped row that kept the card's book would send a reader
to the wrong window.

Run directly: `python3 tests/test_which_book.py`
"""

import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine import likely as K                                  # noqa: E402
from engine.models import Game, Weather                         # noqa: E402
from engine.sources import oddsapi as oa                        # noqa: E402

TEAMS = {"Minnesota Vikings": "MIN", "Green Bay Packers": "GB"}


def _book(key, title, home=-125, away=105):
    return {"key": key, "title": title, "markets": [{"key": "h2h", "outcomes": [
        {"name": "Minnesota Vikings", "price": home},
        {"name": "Green Bay Packers", "price": away}]}]}


def _event(books=None, eid="e1"):
    return {"id": eid, "home_team": "Minnesota Vikings",
            "away_team": "Green Bay Packers",
            "commence_time": "2026-09-13T20:25:00Z",
            "bookmakers": books or [_book("draftkings", "DraftKings")]}


# --- the resolver ---------------------------------------------------------------
def test_it_names_the_book_holding_the_best_price_on_each_side():
    """The two sides are routinely at different books: the best price for
    the favourite and the best price for the dog are different questions
    asked of the same field."""
    ev = _event([_book("draftkings", "DraftKings", -125, 105),
                 _book("fanduel", "FanDuel", -130, 112)])
    assert oa.parse_event_h2h(ev, TEAMS) == {"MIN": -125, "GB": 112}
    assert oa.best_h2h_books(ev, TEAMS) == {"MIN": "DraftKings", "GB": "FanDuel"}


def test_the_sharp_book_is_never_named_because_it_is_never_priced():
    """Pinnacle's -118 is a better number than DraftKings' -125 and is
    not a price anyone here can take. The name has to follow the same
    rule as the price or it points at a window that will not take the
    bet."""
    ev = _event([_book("draftkings", "DraftKings", -125, 105),
                 _book("pinnacle", "Pinnacle", -118, 100)])
    assert oa.parse_event_h2h(ev, TEAMS)["MIN"] == -125
    assert oa.best_h2h_books(ev, TEAMS)["MIN"] == "DraftKings"


def test_a_side_nobody_quoted_gets_no_name():
    ev = _event([{"key": "draftkings", "title": "DraftKings", "markets": [
        {"key": "h2h", "outcomes": [
            {"name": "Minnesota Vikings", "price": -125}]}]}])
    assert oa.best_h2h_books(ev, TEAMS) == {"MIN": "DraftKings"}


def test_a_tie_goes_to_the_first_book_seen_rather_than_the_last():
    ev = _event([_book("draftkings", "DraftKings", -125, 105),
                 _book("betmgm", "BetMGM", -125, 105)])
    assert oa.best_h2h_books(ev, TEAMS) == {"MIN": "DraftKings", "GB": "DraftKings"}


# --- the attach -------------------------------------------------------------------
class _Slate:
    def __init__(self, games):
        self.games, self.date, self.props = games, "2026-09-13", []


def test_the_whole_slate_pull_writes_both_books_onto_the_game():
    g = Game(home="MIN", away="GB", weather=Weather(), date="2026-09-13",
             kickoff="2026-09-13T20:25:00Z")
    ev = _event([_book("draftkings", "DraftKings", -125, 105),
                 _book("fanduel", "FanDuel", -130, 112)])
    tmp = tempfile.mkdtemp()
    real = oa.CACHE_DIR
    oa.CACHE_DIR = __import__("pathlib").Path(tmp)
    path = oa.CACHE_DIR / "odds_board_nfl_lines.json"
    path.write_text(json.dumps([ev]))
    old = time.time() - 600
    os.utime(path, (old, old))
    try:
        res = oa.apply_board_lines_to_slate(_Slate([g]), api_key="k", cache_only=True)
    finally:
        oa.CACHE_DIR = real
    assert res.moneylines == 1, res
    assert (g.home_ml, g.away_ml) == (-125, 112)
    assert g.home_ml_book == "DraftKings" and g.away_ml_book == "FanDuel"


def _ml_card(home_rating, away_rating):
    from engine.pipeline import _game_bets
    from engine.rules import RuleConfig
    g = Game(home="MIN", away="GB", weather=Weather(), date="2026-09-13",
             home_ml=-125, away_ml=112, home_ml_book="DraftKings",
             away_ml_book="FanDuel", home_rating=home_rating,
             away_rating=away_rating)
    return next(c for c in _game_bets([g], RuleConfig())
                if c.get("bet_type") == "moneyline")


def test_the_card_carries_both_and_names_the_side_it_took():
    """Both sides ride, and `book` is whichever one the card backed —
    asserted on a card that took the HOME side and one that took the
    away, because a `book` hard-wired to the home team passes the first
    of those on its own."""
    home_card = _ml_card(6.0, 0.0)
    assert home_card["team"] == "MIN", home_card["team"]
    assert home_card["home_book"] == "DraftKings"
    assert home_card["away_book"] == "FanDuel"
    assert home_card["book"] == "DraftKings", home_card["book"]

    away_card = _ml_card(0.0, 6.0)
    assert away_card["team"] == "GB", away_card["team"]
    assert away_card["home_book"] == "DraftKings"
    assert away_card["away_book"] == "FanDuel"
    assert away_card["book"] == "FanDuel", away_card["book"]


# --- the row ------------------------------------------------------------------------
def _card(**kw):
    d = dict(bet_type="moneyline", market="moneyline", market_label="Moneyline",
             has_market=True, home="MIN", away="GB", team="GB", pick_is_home=False,
             pick_label="GB ML", side="", line=0.0, matchup="GB @ MIN",
             win_prob=0.42, fair_prob=0.42, edge=0.0, odds=120,
             home_odds=-140, away_odds=120, home_book="DraftKings",
             away_book="FanDuel", book="FanDuel", ev_per_unit=0.0,
             confidence=6.0, stake_units=0.0, grade="Pass", credible=True,
             headline="GB ML", reasons=[], recommended=False, live=False,
             date="2026-09-13", game_spread=-1.5)
    d.update(kw)
    return d


def test_the_book_flips_with_the_price_when_the_row_flips_to_the_favourite():
    """The edge card backs the dog at FanDuel; the likely row shows the
    favourite at -140, which is DraftKings' number. Keeping FanDuel on it
    would send a reader to a window that is not posting it."""
    row = K.from_game_bet(_card(), "nfl")
    assert row is not None and row["flipped"] is True
    assert row["team"] == "MIN" and row["odds"] == -140
    assert row["book"] == "DraftKings", row["book"]


def test_an_unflipped_row_keeps_the_book_the_card_came_with():
    row = K.from_game_bet(_card(team="MIN", pick_is_home=True, pick_label="MIN ML",
                                odds=-140, book="DraftKings", win_prob=0.58,
                                fair_prob=0.58), "nfl")
    assert row["flipped"] is False and row["book"] == "DraftKings"


def test_a_card_with_no_book_still_reads_best_rather_than_blank():
    """Older board files and sports that do not resolve a book keep the
    word they had — an empty chip beside a price is worse than a vague
    one."""
    row = K.from_game_bet(_card(home_book="", away_book="", book=""), "nfl")
    assert row["book"] == "best"


def test_the_college_card_carries_both_sides_from_the_shared_resolver():
    src = open(os.path.join(ROOT, "cfb_build.py"), encoding="utf-8").read()
    assert 'entry["ml_books"] = oddsapi.best_h2h_books(ev, team_map)' in src
    assert '"home_book": _mlb.get(g["home"], ""),' in src
    assert '"home_book": play.get("home_book", ""),' in src


def test_the_page_prints_the_book_and_the_age_on_the_card():
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    css = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
    card = app[app.index("function likelyCard("):]
    card = card[:card.index("\nfunction ", 10)]
    assert '<span class="book">· ${escapeHtml(r.book)}</span>${priceAgeChip(r)}' in card
    assert ".pick .price-age" in css


def _node(js):
    """Run the chip in node, or skip where node is not installed."""
    import shutil, subprocess, tempfile
    node = shutil.which("node")
    if not node:
        return None
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    i = app.index("function priceAgeChip(")
    fn = app[i:app.index("\n}", i) + 2]
    prog = f"""
      var escapeHtml = (s) => String(s == null ? "" : s);
      {fn}
      console.log(JSON.stringify((() => {{ {js} }})()));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_the_age_chip_reads_in_the_units_a_reader_thinks_in():
    got = _node("""
      return {
        fresh: priceAgeChip({ price_age_s: 30 }),
        minutes: priceAgeChip({ price_age_s: 1800, priced_from: "board" }),
        hours: priceAgeChip({ price_age_s: 5 * 3600 }),
        days: priceAgeChip({ price_age_s: 3 * 86400 }),
        none: priceAgeChip({}),
        proxy: priceAgeChip({ price_age_s: null }),
        junk: priceAgeChip({ price_age_s: "soon" }),
      };
    """)
    if got is None:
        return
    assert "just now" in got["fresh"], got["fresh"]
    assert "30m ago" in got["minutes"] and "board pull" in got["minutes"]
    assert "5h ago" in got["hours"] and "3d ago" in got["days"]
    # A row with no age keeps the card it had rather than growing an
    # empty chip: older board files and undated sports must not regress.
    assert got["none"] == "" and got["proxy"] == "" and got["junk"] == ""


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
