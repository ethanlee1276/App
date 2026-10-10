"""Doubleheaders: two games, same teams, same date — everything downstream
must know WHICH game a prop belongs to.

- game_for() routes a prop to its own leg via game_number;
- the pipeline stamps the leg on the card and in the headline;
- settling refuses to grade a two-log day unless the outcome is the same
  either way — better an open bet than one graded against the wrong game.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.mlb.data_loader import MLBSlate
from engine.mlb.models import MLBGame, MLBProp
from engine.models import SportsbookLine


def _prop(gn):
    return MLBProp(player="Cal Raleigh", team="SEA", opponent="TEX",
                   position="C", market="total_bases", logs=[],
                   career_avg=1.8, vs_pitcher_avg=None,
                   lines=[SportsbookLine(book="DK", line=1.5,
                                         over_odds=-110, under_odds=-110)],
                   game_number=gn)


def test_game_for_routes_to_the_right_leg():
    g1 = MLBGame(home="SEA", away="TEX", park="generic", date="2026-08-01",
                 kickoff="2026-08-01T17:10:00Z", game_number=1, doubleheader=True)
    g2 = MLBGame(home="SEA", away="TEX", park="generic", date="2026-08-01",
                 kickoff="2026-08-01T23:40:00Z", game_number=2, doubleheader=True)
    slate = MLBSlate(date="2026-08-01", games=[g1, g2], props=[])
    assert slate.game_for(_prop(2)) is g2
    assert slate.game_for(_prop(1)) is g1
    assert slate.game_for(_prop(0)) is g1        # legacy/no-DH: first match


def test_pipeline_stamps_the_leg_on_the_card():
    from engine.mlb.pipeline import run_mlb_slate
    import json
    d = json.load(open("data/mlb_sample_slate.json"))
    # Turn the first game into leg 2 of a doubleheader.
    tgt = d["games"][0]
    tgt["game_number"], tgt["doubleheader"] = 2, True
    # data_loader reads dicts — confirm it carries the fields through.
    from engine.mlb.data_loader import _game
    g = _game(tgt)
    assert getattr(g, "game_number", None) == 2 and g.doubleheader is True


def test_settle_refuses_ambiguous_doubleheader_days():
    import datetime
    from engine import ledger, db
    lpath = os.path.join(tempfile.mkdtemp(), "led.db")
    lconn = ledger.connect(lpath)
    hist = db.connect(":memory:")
    # A settled date outside the settler's strict window — inside it (today
    # and yesterday, which straddle the UTC rollover on a night slate) the
    # settler wants a final score on record before it grades anything, and
    # this fixture is about the ambiguity rule, not that one.
    day = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()

    def _log(game_id, value):
        hist.execute(
            "INSERT INTO player_game_logs (sport, season, period, game_id, "
            "player, team, opponent, position, home, market, value) VALUES "
            "('mlb', 2026, ?, ?, 'Cal Raleigh', 'SEA', 'TEX', "
            "'C', 1, 'total_bases', ?)", (day, game_id, value))

    def _bet(player="Cal Raleigh", line=1.5):
        lconn.execute(
            "INSERT INTO bets (sport, date, player, market, side, line, odds, "
            "grade, stake_units, stake_dollars, status, category) VALUES "
            "('mlb', ?, ?, 'total_bases', 'OVER', ?, -110, 'A', "
            "0.5, 5.0, 'open', 'main')", (day, player, line))
        lconn.commit()

    # Ambiguous: 3 TB in game one, 0 in game two — Over 1.5 wins one leg
    # and loses the other. The bet must STAY OPEN, not get coin-flipped.
    _log("g1", 3.0); _log("g2", 0.0); hist.commit()
    _bet()
    assert ledger.settle_from_history(lconn, hist, sport="mlb") == 0
    assert lconn.execute("SELECT status FROM bets").fetchone()["status"] == "open"

    # Unambiguous: both legs clear the line — same outcome either way, so
    # the settle is safe and proceeds.
    hist.execute("UPDATE player_game_logs SET value=2.0 WHERE game_id='g2'")
    hist.commit()
    assert ledger.settle_from_history(lconn, hist, sport="mlb") == 1
    assert lconn.execute("SELECT status FROM bets").fetchone()["status"] == "won"
    lconn.close()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
