"""Most Likely game rows rank on the number measured to rank best.

Ethan, 2026-09-07: "you worked on the NFL and CFB Most Likely model
and made it better."

The one thing measured to rank winners better than the model is the
closing market itself: on this box's stored closes the book's de-vigged
moneyline sorts NFL winners at 0.722 (1,420 games) against the model's
0.677, and college winners at 0.791 (3,011 games) against 0.752. So a
moneyline row on either football board now ranks on the book's number
for its side, keeps the model's number on the card, and says which
number ordered it. A sharp-anchored card ranks on its own probability,
which is the sharp book's fair — a market number. Spreads, totals and
team totals have no market figure and are exactly what they were.

Run directly: `python3 tests/test_likely_ranks_on_market.py`
"""

import inspect
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import boards, db, likely as K                    # noqa: E402


def _ml(**kw):
    d = dict(bet_type="moneyline", market="moneyline", market_label="Moneyline",
             has_market=True, home="DET", away="NO", team="DET", pick="DET",
             pick_is_home=True, pick_label="DET ML", side="", line=0.0,
             matchup="NO @ DET", win_prob=0.66, fair_prob=0.62, edge=0.04,
             odds=-165, home_odds=-165, away_odds=140, ev_per_unit=0.05,
             confidence=6.0, stake_units=0.5, grade="B", credible=True,
             headline="DET ML", reasons=["Power rating: DET +4.1 vs NO -1.2"],
             recommended=True, live=False, date="2026-09-14",
             kickoff="2026-09-14T17:00:00+00:00")
    d.update(kw)
    return d


def _tot(**kw):
    d = dict(bet_type="total", market="total", market_label="Total", has_market=True,
             home="DET", away="NO", team="", side="Over", line=47.5, pick_label="Over 47.5",
             matchup="NO @ DET", win_prob=0.60, fair_prob=0.52, edge=0.08, odds=-110,
             other_odds=-110, ev_per_unit=0.1, confidence=6.0, stake_units=0.0,
             grade="Pass", credible=True, headline="Over 47.5", reasons=[],
             recommended=False, live=False, date="2026-09-14")
    d.update(kw)
    return d


def test_the_market_figure_is_measured_the_way_the_models_is():
    """`gamerank.measure_market_moneyline` — the close itself, de-vigged,
    against whether home won — proven on a synthetic book, NOT on this
    box's database. run_tests.py is explicit that the suite must not
    read the box it runs on; the first version of this test did, and it
    was green here and a crash on GitHub's clone, which holds no history
    (every CI run from 47ec2b7 to fbf4aaf failed on it). The real
    figures are re-measured on the droplet, docs/DROPLET_CHECKS.md."""
    from engine.gamerank import measure_market_moneyline
    conn = db.connect(":memory:")
    rows = []
    # Ten games: the book makes the home side −200 in five (home wins
    # four), +150 in five (home wins one), one tie at −110 which must be
    # dropped, one game with no quote which must not count.
    for i in range(5):
        rows.append(("A%d" % i, "B%d" % i, 24, 17 if i < 4 else 31, (-200, 170)))
    for i in range(5):
        rows.append(("C%d" % i, "D%d" % i, 17 if i < 4 else 31, 24, (150, -170)))
    rows.append(("T", "U", 20, 20, (-110, -110)))
    rows.append(("X", "Y", 30, 3, None))
    games = []
    for n, (h, a, hs, as_, ml) in enumerate(rows):
        extra = {"ml": list(ml)} if ml else {}
        games.append({"sport": "nfl", "season": 2025, "period": str(n + 1),
                      "game_id": f"2025-{n + 1}-{a}@{h}", "home": h, "away": a,
                      "home_score": hs, "away_score": as_, "date": "2025-09-%02d" % (7 + n),
                      "extra": json.dumps(extra)})
    db.upsert_games(conn, games)
    conn.row_factory = sqlite3.Row
    r = measure_market_moneyline(conn, "nfl")
    assert r.games_seen == 12 and r.games_quoted == 11 and r.pushes == 1, (r.games_seen, r.games_quoted, r.pushes)
    assert len(r.pairs) == 10
    # Favourites won 4 of 5 and dogs 1 of 5: the close orders them well
    # but not perfectly — AUC = P(fair of a winner > fair of a loser).
    from engine.rankfit import auc
    assert abs(auc(r.pairs) - 0.8) < 1e-9, auc(r.pairs)
    assert "the close itself" in r.note


def test_the_figures_are_the_ones_written_down():
    """The constants are documented measurements (2026-09-07, this box's
    schedule closes: NFL 0.722 on 1,420 games, college 0.7905 on 3,011),
    and the market beats the model on both. Only the moneyline was
    measured, so only the moneyline ranks on the market."""
    assert K.GAME_RANK_MARKET == {"nfl": {"moneyline": 0.722},
                                  "cfb": {"moneyline": 0.7905}}, K.GAME_RANK_MARKET
    for sport, floor in (("nfl", 0.70), ("cfb", 0.77)):
        want = K.GAME_RANK_MARKET[sport]["moneyline"]
        assert want > K.GAME_RANK_MEASURED[sport]["moneyline"] >= floor - 0.1
    for sport in K.GAME_RANK_MARKET:
        assert set(K.GAME_RANK_MARKET[sport]) == {"moneyline"}, "only the moneyline was measured"


def test_a_moneyline_row_ranks_on_the_market_and_keeps_the_models_number():
    for sport, fig in (("nfl", 0.722), ("cfb", 0.7905)):
        row = K.from_game_bet(_ml(), sport=sport)
        assert row["model_prob"] == 0.62 and row["prob_source"] == "market", (sport, row)
        assert row["win_prob"] == 0.66 and row["implied_prob"] == 0.62
        assert row["rank_auc"] == fig and row["ranked"] is True
        # The card's edge and EV are still the model's claim.
        assert row["edge"] == 0.04
        assert row["rank_note"].startswith("Ranked on the market’s number, 62%")
        assert "The model rates this side at 66%" in row["rank_note"]


def test_the_flip_is_decided_on_the_ranking_number():
    """The market makes DET 62%: a dog card for NO (38% fair) flips to
    the DET row at 62%, and the model's own 37%/63% rides along."""
    dog = _ml(team="NO", pick="NO", pick_is_home=False, pick_label="NO ML",
              odds=140, win_prob=0.37, fair_prob=0.38, headline="NO ML")
    row = K.from_game_bet(dog, sport="nfl")
    assert row["flipped"] is True and row["player"] == "DET ML" and row["odds"] == -165
    assert row["model_prob"] == 0.62 and row["win_prob"] == 0.63
    # …and where the MODEL is short but the market is not, no flip: the
    # row is the market's side at the market's number.
    row = K.from_game_bet(_ml(win_prob=0.40), sport="nfl")
    assert row["flipped"] is False and row["model_prob"] == 0.62 and row["win_prob"] == 0.40


def test_a_sharp_anchored_card_ranks_on_its_own_fair():
    """Its probability IS a market number — the sharp book's de-vigged
    fair — and the sharpest one on the board."""
    row = K.from_game_bet(_ml(win_prob=0.60, fair_prob=0.55, sharp_anchored=True), sport="nfl")
    assert row["model_prob"] == 0.60 and row["prob_source"] == "sharp"
    assert row["rank_auc"] == 0.722 and row["rank_note"].startswith("Ranked on the sharp book’s fair")


def test_markets_without_a_market_figure_are_what_they_were():
    row = K.from_game_bet(_tot(), sport="nfl")
    assert row["model_prob"] == 0.60 and row["prob_source"] == "model"
    assert row["rank_auc"] == K.GAME_RANK_MEASURED["nfl"]["total"] and row["ranked"] is False
    # A sport with no market table ranks on the model too.
    real = K.GAME_RANK_MARKET.pop("nfl")
    try:
        row = K.from_game_bet(_ml(), sport="nfl")
        assert row["model_prob"] == 0.66 and row["prob_source"] == "model"
        assert row["rank_auc"] == K.GAME_RANK_MEASURED["nfl"]["moneyline"]
    finally:
        K.GAME_RANK_MARKET["nfl"] = real


def test_the_model_credibility_bar_still_refuses_a_market_ranked_row():
    """Ranking on the market does not launder a model that disagrees
    with the book by 18 points — the card still prints that number."""
    census: dict = {}
    assert K.build([], game_bets=[_ml(win_prob=0.80, fair_prob=0.62)], census=census) == []
    assert census == {"the model's own read disagrees with the market by more than we credit": 1}, census
    got = K.build([], game_bets=[_ml()])
    assert len(got) == 1 and got[0]["prob_source"] == "market"


def test_the_board_sorts_on_the_ranking_number():
    """Two moneylines: the model likes A more, the market likes B more.
    The board orders on the market."""
    a = _ml(home="A", away="X", team="A", pick="A", matchup="X @ A", pick_label="A ML",
            win_prob=0.70, fair_prob=0.60)
    b = _ml(home="B", away="Y", team="B", pick="B", matchup="Y @ B", pick_label="B ML",
            win_prob=0.62, fair_prob=0.68)
    got = K.build([], game_bets=[a, b])
    assert [r["player"] for r in got] == ["B ML", "A ML"], [(r["player"], r["model_prob"]) for r in got]
    assert [r["model_prob"] for r in got] == [0.68, 0.60]


def test_the_shelf_and_the_guide_carry_the_market_figure():
    row = K.from_game_bet(_ml(), sport="nfl")
    shelf = boards.shelves("nfl", [row])[0]
    assert shelf["key"] == "gamelines" and shelf["rank_auc"] == 0.722
    for sport in ("nfl", "cfb"):
        line = boards.guide(sport)[0]["measured"]
        mkt, ml = K.GAME_RANK_MARKET[sport]["moneyline"], K.GAME_RANK_AUC[sport]["moneyline"]
        assert f"{ml:.2f} on the model" in line and f"ranks them at {mkt:.2f}" in line, line
        assert "ordered on it" in line


def test_every_sharp_game_card_says_so():
    """`ranking_number` reads `sharp_anchored`; the NFL's three sharp
    branches stamp it (college's `_finish_sharp` already did)."""
    from engine import pipeline
    src = inspect.getsource(pipeline._game_bets)
    assert src.count('"sharp_anchored"') >= 3 or src.count("sharp_anchored") >= 3, src.count("sharp_anchored")
    import cfb_build
    assert 'card["sharp_anchored"] = True' in inspect.getsource(cfb_build._finish_sharp)


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
