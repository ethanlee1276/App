"""CFB game markets: a sharp book's disagreement is the pick; the model is the note.

Ethan, 2026-09-07: "make sure you do the same exact work to make CFB
just as good."

What was measured that day (`engine.gamecal --sport cfb`, recorded on
`engine.cfb.pipeline.CFB_MODEL_GAME_RECOMMENDATIONS`): the college
model's disagreement with the closing line carries nothing on the
moneyline or the spread, and on the total its sides beat the close at
exactly the break-even. The NFL adopted baseball's policy for the same
finding: a card priced from the ratings alone is information, shown and
never recommended; a card priced from the sharp reference book's
de-vigged pair against a soft book's price is a pick. `cfb_build` now
runs on that policy — the sharp pair read out of the same event the
soft prices come from, priced by the shared sharp pricers, the model's
cards demoted after their verdict.

Run directly: `python3 tests/test_cfb_sharp_first.py`
"""

import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cfb_build as CB                                          # noqa: E402
from engine.cfb import ratings as CR                            # noqa: E402
from engine.cfb.model import NOT_A_POWER_GAME                   # noqa: E402
from engine.cfb.pipeline import (CFB_MODEL_GAME_RECOMMENDATIONS,  # noqa: E402
                                 CFB_NO_ANCHOR, demote_model_card)
from engine.gamebets import SHARP_MIN_EV, SHARP_SUSPECT_EV      # noqa: E402
from engine.teamrates import TeamRating                         # noqa: E402


def _game(i=0, home="TOL", away="BGSU", conf="SEC", **kw):
    g = {"game_id": f"g{i}", "home": home, "away": away,
         "home_conference": conf, "away_conference": conf,
         "home_rank": None, "away_rank": None, "weekday": "Saturday",
         "kickoff": "2026-09-12T19:30Z", "date": "2026-09-12",
         "neutral_site": False, "label": f"{away} @ {home}",
         "state": "scheduled", "qb_confirmed": True,
         "participation_verified": True, "weather_checked": True,
         "indoor": False}
    g.update(kw)
    return g


RATINGS = {"TOL": TeamRating(net=3.0, off=2.0, def_=-1.0, games=13),
           "BGSU": TeamRating(net=0.0, off=0.5, def_=0.5, games=13)}


def _lines(**kw):
    # Books keyed by SIDE, the way `attach_odds` now carries them: the
    # two sides of a market are routinely at different books, so a card
    # has to be told which one it took (cfb_build._book_for_side).
    base = {"moneyline": (-160, 140), "spread": (-3.5, -110, -110),
            "total": (52.5, -110, -110),
            "ml_books": {"TOL": "FanDuel", "BGSU": "DraftKings"},
            "spread_books": {"TOL": "FanDuel", "BGSU": "DraftKings"},
            "total_books": {"over": "FanDuel", "under": "DraftKings"}}
    base.update(kw)
    return base


def _event(pinnacle=True):
    def book(key, title, h2h, spread, total):
        return {"key": key, "title": title, "markets": [
            {"key": "h2h", "outcomes": [
                {"name": "Toledo Rockets", "price": h2h[0]},
                {"name": "Bowling Green Falcons", "price": h2h[1]}]},
            {"key": "spreads", "outcomes": [
                {"name": "Toledo Rockets", "point": spread[0], "price": spread[1]},
                {"name": "Bowling Green Falcons", "point": -spread[0], "price": spread[2]}]},
            {"key": "totals", "outcomes": [
                {"name": "Over", "point": total[0], "price": total[1]},
                {"name": "Under", "point": total[0], "price": total[2]}]}]}
    books = [book("draftkings", "DraftKings", (-160, 140), (-3.5, -110, -110), (52.5, -110, -110)),
             book("fanduel", "FanDuel", (-155, 135), (-3.5, -108, -112), (52.5, -112, -108))]
    if pinnacle:
        books.append(book("pinnacle", "Pinnacle", (-150, 130), (-3.5, -108, -112), (52.5, -105, -115)))
    return {"id": "ev1", "home_team": "Toledo Rockets",
            "away_team": "Bowling Green Falcons", "bookmakers": books}


TEAM_MAP = {"Toledo Rockets": "TOL", "Bowling Green Falcons": "BGSU"}


# --- reading the sharp pair -------------------------------------------------
def test_the_sharp_pair_is_read_out_and_only_from_the_sharp_book():
    sharp = CB._sharp_for(_event(), TEAM_MAP, "TOL", "BGSU")
    assert sharp == {"moneyline": (-150, 130), "spread": (-3.5, -108, -112),
                     "total": (52.5, -105, -115)}, sharp
    # No sharp book in the payload: nothing, and the board is what it was.
    assert CB._sharp_for(_event(pinnacle=False), TEAM_MAP, "TOL", "BGSU") == {}


def test_attach_odds_carries_the_sharp_pair_on_the_entry():
    from engine.sources import oddsapi
    real = oddsapi.fetch_sport_odds
    oddsapi.fetch_sport_odds = lambda *a, **k: ([_event()], {})
    try:
        priced, _note = CB.attach_odds([_game()], {"toledo": "TOL", "bowling green": "BGSU"},
                                       cache_only=True)
    finally:
        oddsapi.fetch_sport_odds = real
    entry = priced["g0"]
    assert entry["sharp"]["moneyline"] == (-150, 130), entry
    # The bettable aggregates still exclude the sharp book — the best
    # soft moneyline is FanDuel's −155/+140, not Pinnacle's −150.
    assert entry["moneyline"] == (-155, 140), entry["moneyline"]
    assert "Pinnacle" not in entry["ml_books"].values()
    assert "Pinnacle" not in entry["spread_books"].values()
    assert "Pinnacle" not in entry["total_books"].values()


# --- pricing against it -----------------------------------------------------
def test_without_a_sharp_pair_no_sharp_card_is_built():
    priced = {"g0": _lines()}
    assert CB.sharp_game_bets([_game()], priced, RATINGS, CR.PRIOR) == []
    plays = CB.build_plays([_game()], priced, RATINGS, CR.PRIOR, {}, {},
                           skip=CB._taken_by_sharp([]))
    assert {p["market"] for p in plays} == {"side", "total", "moneyline"}


def test_a_sharp_moneyline_disagreement_is_priced_and_can_be_a_pick():
    """The NFL's arithmetic, on a college card. Near a coin flip the
    sharp path shows and never stakes (B+ needs ~3.3 points of edge,
    which at even money is 7% EV — the suspect line). On a favourite,
    Pinnacle −150/+130 against a soft −120 is +6.3% EV and a B+ pick;
    −122 is under the edge bar and −118 is past the suspect cap."""
    for soft in (104, 106, 108, 110, 112):
        priced = {"g0": _lines(moneyline=(soft, -125), sharp={"moneyline": (-110, -110)})}
        cards = CB.sharp_game_bets([_game()], priced, RATINGS, CR.PRIOR)
        ml = [c for c in cards if c["market"] == "moneyline"][0]
        assert ml["reasons"][0].startswith("Sharp anchor"), ml["reasons"][0]
        assert ml["team"] == "TOL" and ml["odds"] == soft and ml["sharp_anchored"]
        assert SHARP_MIN_EV <= ml["ev_per_unit"] <= SHARP_SUSPECT_EV
        assert ml["grade"] == "Pass" and ml["recommended"] is False, (soft, ml["grade"])
        assert CFB_NO_ANCHOR not in ml.get("warnings", [])
    picks = {}
    for soft in (-125, -122, -120, -118):
        priced = {"g0": _lines(moneyline=(soft, 115), sharp={"moneyline": (-150, 130)})}
        ml = CB.sharp_game_bets([_game()], priced, RATINGS, CR.PRIOR)[0]
        picks[soft] = (ml["grade"], ml["recommended"], round(ml["ev_per_unit"], 3),
                       float(ml["stake_units"]) > 0)
    assert picks[-120] == ("B+", True, 0.063, True), picks
    assert picks[-125][1] is False and picks[-122][1] is False, picks
    assert picks[-118][1] is False and picks[-118][2] > SHARP_SUSPECT_EV, picks
    # The model's own number rides along as context, not as the price.
    ml = CB.sharp_game_bets([_game()], {"g0": _lines(moneyline=(-120, 115),
                                                      sharp={"moneyline": (-150, 130)})},
                            RATINGS, CR.PRIOR)[0]
    assert any(r.startswith("Model context") for r in ml["reasons"]), ml["reasons"]
    assert ml["book"] == "FanDuel" and ml["game_id"] == "g0" and ml["date"] == "2026-09-12"


def test_totals_and_spreads_anchor_only_at_the_same_line():
    """Pinnacle −105/−115 on 52.5 makes the under 51% fair; a soft book
    paying +100 on it is +2.2% EV — a sharp card. Move the soft line to
    53 and there is no comparison to make: no sharp card, and the model
    prices the total as before."""
    same = {"g0": _lines(total=(52.5, -120, 100), spread=(-3.5, -115, -105),
                         sharp={"total": (52.5, -105, -115), "spread": (-3.5, -108, -112)})}
    cards = CB.sharp_game_bets([_game()], same, RATINGS, CR.PRIOR)
    by = {c["market"]: c for c in cards}
    assert by["total"]["side"] == "Under" and by["total"]["odds"] == 100, by["total"]
    assert by["total"]["ev_per_unit"] >= SHARP_MIN_EV
    assert by["total"]["reasons"][0].startswith("Sharp anchor")
    # Spread: Pinnacle −108/−112 (home 49.1% / away 50.9% fair); the
    # soft book pays −105 on the away side — +1.5% EV, under the floor,
    # so the pricer declines and the model card takes the market.
    assert "spread" not in by, by.keys()
    moved = {"g0": _lines(total=(53.0, -120, 100),
                          sharp={"total": (52.5, -105, -115)})}
    assert CB.sharp_game_bets([_game()], moved, RATINGS, CR.PRIOR) == []


def test_a_sharp_priced_market_is_not_priced_twice():
    """One card per market: the sharp card where the sharp book quoted
    it, the model card everywhere else. The spread crosses the two
    vocabularies — `build_plays` calls it "side" — and the skip set is
    built through the pipeline's own mapping."""
    # Pinnacle −108/−112 makes the home side 49.6% fair; a soft book
    # paying +110 on it is +4.1% EV — a sharp spread card.
    priced = {"g0": _lines(moneyline=(-120, 115), spread=(-3.5, 110, -130),
                           sharp={"moneyline": (-150, 130), "spread": (-3.5, -108, -112)})}
    cards = CB.sharp_game_bets([_game()], priced, RATINGS, CR.PRIOR)
    assert {c["market"] for c in cards} == {"moneyline", "spread"}, cards
    sp = [c for c in cards if c["market"] == "spread"][0]
    assert sp["team"] == "TOL" and sp["line"] == -3.5 and sp["odds"] == 110, sp
    assert round(sp["ev_per_unit"], 3) == 0.041, sp["ev_per_unit"]
    taken = CB._taken_by_sharp(cards)
    assert taken == {("g0", "moneyline"), ("g0", "side")}, taken
    plays = CB.build_plays([_game()], priced, RATINGS, CR.PRIOR, {}, {}, skip=taken)
    assert [p["market"] for p in plays] == ["total"], [p["market"] for p in plays]


# --- the policy on the model's cards ----------------------------------------
def _model_card(**kw):
    card = {"bet_type": "moneyline", "market": "moneyline", "market_label": "Moneyline",
            "home": "TOL", "away": "BGSU", "team": "TOL", "pick": "TOL",
            "matchup": "BGSU @ TOL", "has_market": True, "live": False, "started": False,
            "win_prob": 0.66, "fair_prob": 0.6, "edge": 0.06, "odds": -150,
            "other_odds": 130, "home_odds": -150, "away_odds": 130,
            "ev_per_unit": 0.1, "confidence": 7.0, "grade": "A", "cfb_grade": 78,
            "stake_units": 1.4, "stake_if_confirmed_units": 0.0,
            "stake_if_measured_units": 0.0, "conditional": False,
            "recommended": True, "reasons": ["Ratings: TOL +3.0, BGSU +0.0"],
            "date": "2026-09-12", "kickoff": "2026-09-12T19:30Z"}
    card.update(kw)
    return card


def test_the_model_card_is_demoted_and_still_reaches_the_most_likely_board():
    from engine import likely
    card = demote_model_card(_model_card())
    assert card["recommended"] is False and card["grade"] == "Pass"
    assert card["stake_units"] == 0.0 and CFB_NO_ANCHOR in card["warnings"]
    # The verdict's own grade is kept — it is the record of what the
    # ratings would have done.
    assert card["cfb_grade"] == 78
    # A conditional promised a stake for the moment its starter is
    # confirmed; under the policy confirming him produces no bet either.
    hold = demote_model_card(_model_card(recommended=False, conditional=True,
                                         grade="Conditional", stake_units=0.0,
                                         stake_if_confirmed_units=1.2))
    assert hold["stake_if_confirmed_units"] == 0.0 and hold["conditional"] is True
    # The Most Likely board ranks on the model's number, not on the verdict.
    row = likely.from_game_bet(card, sport="cfb")
    assert row is not None and row["market"] == "moneyline", row


def test_the_group_of_five_rule_holds_for_a_sharp_card():
    """A game neither side of which is in a conference this board bets
    is "priced, shown with its number and its edge, never a play"
    (Ethan, 2026-09-02) — a decision about whether money follows, and a
    sharp card is money following. The favourite window that is a B+
    pick in the SEC is shown with its EV and refused in the MAC."""
    priced = {"g0": _lines(moneyline=(-120, 115), sharp={"moneyline": (-150, 130)})}
    ml = CB.sharp_game_bets([_game(conf="MAC")], priced, RATINGS, CR.PRIOR)[0]
    assert ml["recommended"] is False and ml["grade"] == "Pass" and ml["stake_units"] == 0.0
    assert round(ml["ev_per_unit"], 3) == 0.063 and ml["sharp_anchored"]
    assert any(NOT_A_POWER_GAME in r for r in ml["reasons"]), ml["reasons"]
    # …and a power opponent lifts it out, as the rule says.
    ml = CB.sharp_game_bets([_game(conf="MAC", away_conference="SEC")], priced,
                            RATINGS, CR.PRIOR)[0]
    assert ml["recommended"] is True


def test_a_started_game_is_never_a_pick():
    priced = {"g0": _lines(moneyline=(-120, 115), sharp={"moneyline": (-150, 130)})}
    ml = CB.sharp_game_bets([_game(live={"state": "live"})], priced, RATINGS, CR.PRIOR)[0]
    assert ml["live"] is True and ml["started"] is True and ml["recommended"] is False
    ml = CB.sharp_game_bets([_game(live={"state": "final"})], priced, RATINGS, CR.PRIOR)[0]
    assert ml["live"] is False and ml["started"] is True and ml["recommended"] is False


def test_the_policy_is_a_constant_and_the_build_applies_it():
    assert CFB_MODEL_GAME_RECOMMENDATIONS is False
    assert "sharp-anchor" in CFB_NO_ANCHOR and "college close" in CFB_NO_ANCHOR
    src = inspect.getsource(CB.main)
    # Sharp cards are priced BEFORE the model's plays are built, and the
    # markets they took are handed to `build_plays`.
    assert src.index("sharp_game_bets(") < src.index("plays = build_plays(")
    assert "skip=_taken_by_sharp(sharp_bets)" in src
    # Every model card — play, hold, refusal — goes through the demotion,
    # and the sharp cards lead the board.
    assert "for _card in bets + conditionals + refused:" in src
    assert "demote_model_card(_card)" in src
    assert 'out["game_bets"] = sharp_bets + bets + conditionals + refused' in src
    # The sharp pair is read on the same pass that reads the soft prices.
    assert 'entry["sharp"] = sharp' in inspect.getsource(CB.attach_odds)


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
