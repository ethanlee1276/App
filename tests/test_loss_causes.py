"""Loss causes: the postmortem's evidence layer, computed not narrated.

The nightly diary's prompt asked its writer to "note when a loss looks
like variance" while handing it nothing to reason from. Now the settle
pass tags every loss with the most specific measurable circumstance the
ingested results support — blowout (final margin off the games table,
reached through the player's own result row), short run (journaled
projected vs actual minutes, hoops), or variance, the honest default —
and the prose lane narrates tags instead of guessing causes. The tag
annotates the row; it never touches the grade.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import causes, db, ledger

D = "2026-07-01"


def _journal():
    lconn = ledger.connect(os.path.join(tempfile.mkdtemp(), "led.db"))
    hconn = db.connect(":memory:")
    return lconn, hconn


def _bet(lconn, player, sport="nba", market="points", status="lost", **kw):
    cols = ("sport,date,player,market,side,line,odds,grade,stake_units,"
            "stake_dollars,status,category").split(",")
    vals = [sport, D, player, market, "OVER", 25.5, -110, "A", 1.0, 10.0,
            status, "main"]
    for k, v in kw.items():
        cols.append(k)
        vals.append(v)
    lconn.execute(f"INSERT INTO bets ({','.join(cols)}) "
                  f"VALUES ({','.join('?' * len(vals))})", vals)
    lconn.commit()


def _game(hconn, sport="nba", hs=118.0, aw=90.0, game_id="AWY@HOM"):
    db.upsert_games(hconn, [{"sport": sport, "season": 2026, "period": D,
                             "game_id": game_id, "home": "HOM", "away": "AWY",
                             "home_score": hs, "away_score": aw}])


def _log(hconn, player, sport="nba", market="points", value=18.0,
         game_id="AWY@HOM"):
    db.upsert_player_logs(hconn, [{
        "sport": sport, "season": 2026, "period": D, "game_id": game_id,
        "player": player, "team": "HOM", "opponent": "AWY", "position": "G",
        "home": 1, "market": market, "value": value}])


def _cause(lconn, player):
    return lconn.execute("SELECT loss_cause FROM bets WHERE player=?",
                         (player,)).fetchone()[0]


# --- the three tags ----------------------------------------------------------
def test_a_blowout_final_earns_the_blowout_tag():
    lconn, hconn = _journal()
    _bet(lconn, "Garbage Time")
    _log(hconn, "Garbage Time")
    _game(hconn, hs=118, aw=90)                    # 28-pt final, NBA bar is 20
    causes.backfill(lconn, hconn)
    assert _cause(lconn, "Garbage Time") == "blowout (28-pt final)"


def test_a_close_game_with_full_minutes_is_just_variance():
    lconn, hconn = _journal()
    _bet(lconn, "Full Run", proj_minutes=34.0, actual_minutes=33.0)
    _log(hconn, "Full Run")
    _game(hconn, hs=104, aw=101)                   # 3-pt game
    causes.backfill(lconn, hconn)
    assert _cause(lconn, "Full Run") == "variance"


def test_short_minutes_earn_the_short_run_tag():
    lconn, hconn = _journal()
    _bet(lconn, "Early Hook", sport="wnba",
         proj_minutes=32.0, actual_minutes=19.0)   # 59% of projection
    causes.backfill(lconn, hconn)
    assert _cause(lconn, "Early Hook") == "short run (19 of 32 min)"


def test_the_blowout_outranks_the_short_run():
    """Garbage time is WHY the minutes were short — the root cause wins."""
    lconn, hconn = _journal()
    _bet(lconn, "Sat Late", proj_minutes=34.0, actual_minutes=22.0)
    _log(hconn, "Sat Late")
    _game(hconn, hs=125, aw=95)
    causes.backfill(lconn, hconn)
    assert _cause(lconn, "Sat Late").startswith("blowout")


def test_baseball_margins_speak_in_runs():
    lconn, hconn = _journal()
    _bet(lconn, "Run Rule", sport="mlb", market="hits")
    _log(hconn, "Run Rule", sport="mlb", market="hits", value=0.0)
    _game(hconn, sport="mlb", hs=11, aw=2)         # 9-run final, bar is 6
    causes.backfill(lconn, hconn)
    assert _cause(lconn, "Run Rule") == "blowout (9-run final)"


def test_a_ufc_loss_has_nothing_measurable_and_says_so():
    lconn, hconn = _journal()
    _bet(lconn, "Chin Check", sport="ufc", market="moneyline")
    causes.backfill(lconn, hconn)
    assert _cause(lconn, "Chin Check") == "variance"


# --- the sweep's discipline --------------------------------------------------
def test_only_losses_are_tagged_and_regrades_clear_stale_tags():
    lconn, hconn = _journal()
    _bet(lconn, "Winner", status="won")
    _bet(lconn, "Loser")
    causes.backfill(lconn, hconn)
    assert lconn.execute("SELECT loss_cause FROM bets WHERE player='Winner'"
                         ).fetchone()[0] is None
    assert _cause(lconn, "Loser") == "variance"
    # The resettle pass flips the loss to a win: the tag must not outlive it.
    lconn.execute("UPDATE bets SET status='won' WHERE player='Loser'")
    lconn.commit()
    causes.backfill(lconn, hconn)
    assert lconn.execute("SELECT loss_cause FROM bets WHERE player='Loser'"
                         ).fetchone()[0] is None


def test_the_sweep_never_rewrites_an_existing_tag():
    """Tags are written once — new evidence changes future tags, not
    settled history (the receipts rule, applied to annotations)."""
    lconn, hconn = _journal()
    _bet(lconn, "Tagged Once")
    causes.backfill(lconn, hconn)                  # no scores yet → variance
    _log(hconn, "Tagged Once")
    _game(hconn, hs=130, aw=90)                    # blowout lands afterwards
    causes.backfill(lconn, hconn)
    assert _cause(lconn, "Tagged Once") == "variance"


def test_settling_a_bet_tags_it_in_the_same_pass():
    """The hook lives inside settle_from_history, so every caller —
    launcher, maintenance, CLI — gets tagging without knowing about it."""
    lconn, hconn = _journal()
    _bet(lconn, "Fresh Loss", status="open")
    _log(hconn, "Fresh Loss", value=18.0)          # under the 25.5 OVER
    _game(hconn, hs=118, aw=90)
    n = ledger.settle_from_history(lconn, hconn)
    assert n >= 1
    row = lconn.execute("SELECT status, loss_cause FROM bets "
                        "WHERE player='Fresh Loss'").fetchone()
    assert row["status"] == "lost"
    assert row["loss_cause"] == "blowout (28-pt final)"


# --- the evidence reaches the writer and the page ----------------------------
def test_the_pack_hands_the_writer_tags_not_room_to_guess():
    from engine import prose
    lconn, _ = _journal()
    _bet(lconn, "Beat Close", loss_cause="variance", closing_line=26.5)
    _bet(lconn, "Faded", loss_cause="blowout (28-pt final)", closing_line=24.5)
    _bet(lconn, "Lucky Win", status="won", closing_line=24.5)
    pack = prose.postmortem_pack(lconn, D)
    s = pack["by_sport"]["nba"]
    assert s["loss_causes"] == {"variance": 1, "blowout": 1}
    # OVER 25.5 closing 26.5 = the market came to us; closing 24.5 = faded.
    assert s["process"] == {"lost_beat_close": 1, "lost_market_faded": 1,
                            "won_market_faded": 1}
    for p in s["picks"]:
        assert "cause" in p and "process" in p and "clv" in p
    assert prose.SYSTEM_NIGHT.count("never re-diagnose") == 1


def test_the_receipts_table_ships_the_cause():
    lconn, _ = _journal()
    _bet(lconn, "On The Page", loss_cause="short run (19 of 32 min)",
         pnl_units=-1.0)
    rows = ledger.recent_settled(lconn)
    assert rows[0]["cause"] == "short run (19 of 32 min)"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
