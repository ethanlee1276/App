"""A player who is not in the stat file is a scratch or a zero, not an open bet forever.

Ethan, 2026-09-14, from the droplet: sixteen Sunday NFL rows and eight
college rows still open beside complete stat files. Tua's passing-yards
under was open because Miami's passing yards belonged to Malik Willis;
a dozen touchdown flags were open because a backup who never touched
the ball is not in a stat file at all. The settler had no rule for
"the game is final, the file is in, and he is not in it."

The rule, as a book grades it: a scratch is void, an active player is
graded at zero, and the snap count tells them apart. Every link has to
be present — the day's games final, the official file covering every
team that played, the snap file in — or the bet stays open, because an
open bet is visible and a wrong grade is not. College has no snap file,
so absence from a final, ingested box score is voided, the conservative
grade.

Run directly: `python3 tests/test_absent_player_settles.py`
"""

import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db, ledger                                  # noqa: E402

TODAY = dt.date.today()
D = lambda n: (TODAY + dt.timedelta(days=n)).isoformat()      # noqa: E731
BET_DAY = D(-2)          # a Saturday two days back: never inside the strict window


def _world():
    t = Path(tempfile.mkdtemp())
    L = ledger.connect(t / "l.db")
    ledger.configure_bankroll(L, starting=1000, unit_pct=1)
    H = db.connect(t / "h.db")
    return L, H


def _bet(L, sport, date, player, market="rec_yds", line=60.5, side="OVER",
         game_day="", category="main"):
    L.execute(
        "INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, "
        "odds, stake_units, stake_dollars, status, category) VALUES "
        "(?, ?, ?, ?, ?, ?, ?, ?, -110, 1, 10, 'open', ?)",
        (f"{date}T12:00:00", sport, date, game_day or date, player, market, side, line, category))
    L.commit()
    return L.execute("SELECT id FROM bets ORDER BY id DESC LIMIT 1").fetchone()[0]


def _game(H, sport, season, period, game_id, home, away, date=None, final=True, extra=None):
    H.execute(
        "INSERT INTO games (sport, season, period, game_id, date, home, away, "
        "home_score, away_score, extra) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (sport, season, period, game_id, date, home, away,
         24.0 if final else None, 20.0 if final else None,
         json.dumps(extra) if extra else None))
    H.commit()


def _log(H, sport, season, period, game_id, player, team, market, value, opp="OPP"):
    db.upsert_player_logs(H, [{"sport": sport, "season": season, "period": period,
                               "game_id": game_id, "player": player, "team": team,
                               "opponent": opp, "position": "WR", "home": 1,
                               "market": market, "value": float(value)}])
    H.commit()


def _status(L, bid):
    r = L.execute("SELECT status, actual, why_note FROM bets WHERE id=?", (bid,)).fetchone()
    return r["status"], r["actual"], r["why_note"]

WEEK = "2026-W01"


def _sunday(H, teams=("MIA", "LV"), final=True, file_for=("MIA", "LV"), snaps=True):
    _game(H, "nfl", 2026, "001", "MIA@LV", teams[1], teams[0], BET_DAY, final=final)
    for t in file_for:
        _log(H, "nfl", 2026, "001", f"{t}-001", f"Starter {t}", t, "rec_yds", 60)
        if snaps:
            _log(H, "nfl", 2026, "001", f"{t}-001", f"Starter {t}", t, "snap_pct", 0.9)
    if snaps:
        _log(H, "nfl", 2026, "001", "MIA-001", "Backup Guy", "MIA", "snap_pct", 0.3)


def test_a_scratch_is_voided():
    L, H = _world()
    _sunday(H)
    bid = _bet(L, "nfl", WEEK, "Tua Tagovailoa", market="pass_yds", line=210.5,
               side="UNDER", game_day=BET_DAY, category="likely")
    assert ledger.settle_from_history(L, H) == 1
    status, actual, note = _status(L, bid)
    assert status == "void" and "scratch" in note, (status, note)


def test_an_active_player_with_no_line_is_graded_at_zero():
    L, H = _world()
    _sunday(H)
    over = _bet(L, "nfl", WEEK, "Backup Guy", market="anytime_td", line=0.5,
                game_day=BET_DAY, category="stale")
    under = _bet(L, "nfl", WEEK, "Backup Guy", market="receptions", line=2.5,
                 side="UNDER", game_day=BET_DAY, category="stale")
    assert ledger.settle_from_history(L, H) == 2
    assert _status(L, over)[:2] == ("lost", 0.0)
    assert _status(L, under)[:2] == ("won", 0.0)
    assert "graded at zero" in _status(L, over)[2]


def test_a_zero_snap_row_is_still_a_scratch():
    """The usage ingest can list an inactive player at 0.0 snaps. Being
    on the snap file is not playing; a snap is."""
    L, H = _world()
    _sunday(H)
    _log(H, "nfl", 2026, "001", "MIA-001", "Tua Tagovailoa", "MIA", "snap_pct", 0.0)
    bid = _bet(L, "nfl", WEEK, "Tua Tagovailoa", market="pass_yds", line=210.5,
               side="UNDER", game_day=BET_DAY)
    ledger.settle_from_history(L, H)
    assert _status(L, bid)[0] == "void"


def test_no_snap_file_yet_proves_nothing():
    L, H = _world()
    _sunday(H, snaps=False)
    bid = _bet(L, "nfl", WEEK, "Tua Tagovailoa", market="pass_yds", line=210.5,
               side="UNDER", game_day=BET_DAY)
    ledger.settle_from_history(L, H)
    assert _status(L, bid)[0] == "open"


def test_a_file_missing_a_team_that_played_proves_nothing():
    L, H = _world()
    _sunday(H, file_for=("MIA",))                       # LV played, LV not filed
    bid = _bet(L, "nfl", WEEK, "Tua Tagovailoa", market="pass_yds", line=210.5,
               side="UNDER", game_day=BET_DAY)
    ledger.settle_from_history(L, H)
    assert _status(L, bid)[0] == "open"


def test_a_day_with_a_game_still_open_proves_nothing():
    L, H = _world()
    _sunday(H, final=False)
    bid = _bet(L, "nfl", WEEK, "Tua Tagovailoa", market="pass_yds", line=210.5,
               side="UNDER", game_day=BET_DAY)
    ledger.settle_from_history(L, H)
    assert _status(L, bid)[0] == "open"


def test_a_college_player_absent_from_his_teams_final_box_is_voided():
    L, H = _world()
    bid = _bet(L, "cfb", BET_DAY, "Gabe Burkle", line=19.5, category="likely")
    _log(H, "cfb", 2026, D(-9), "401500", "Gabe Burkle", "IOWA", "rec_yds", 22)   # last week: his team
    _game(H, "cfb", 2026, D(-1), "401555", "IOWA", "ISU")                         # this week, UTC next day
    _log(H, "cfb", 2026, D(-1), "401555-box", "Some Hawkeye", "IOWA", "rec_yds", 40)
    assert ledger.settle_from_history(L, H) == 1
    assert _status(L, bid)[0] == "void"


def test_a_college_team_whose_box_never_landed_stays_open():
    L, H = _world()
    bid = _bet(L, "cfb", BET_DAY, "Gabe Burkle", line=19.5)
    _log(H, "cfb", 2026, D(-9), "401500", "Gabe Burkle", "IOWA", "rec_yds", 22)
    _game(H, "cfb", 2026, D(-1), "401555", "IOWA", "ISU")               # final, no box rows
    ledger.settle_from_history(L, H)
    assert _status(L, bid)[0] == "open"


def test_a_player_with_no_history_at_all_stays_open():
    L, H = _world()
    bid = _bet(L, "cfb", BET_DAY, "Unknown Walk-on", line=19.5)
    _game(H, "cfb", 2026, D(-1), "401555", "IOWA", "ISU")
    _log(H, "cfb", 2026, D(-1), "401555-box", "Some Hawkeye", "IOWA", "rec_yds", 40)
    ledger.settle_from_history(L, H)
    assert _status(L, bid)[0] == "open"


def test_a_desk_ticket_or_a_fighter_is_never_an_absent_player():
    """GRADED_ELSEWHERE, applied to this rule too. A predmarket row rides
    the NFL slate with a ticker in the player column; a UFC row names a
    fighter. Both look exactly like an absent player to a stat-file rule,
    and both are graded by their own settlers — see the module note on
    the 104 voided desk tickets."""
    L, H = _world()
    _sunday(H)
    ticket = _bet(L, "nfl", WEEK, "KXNFLGAME-14SEP26KC-YES", market="kalshi_ml",
                  line=41.0, side="YES", game_day=BET_DAY, category="predmarket")
    fight = _bet(L, "nfl", WEEK, "Some Fighter", market="fight_ml", line=0,
                 game_day=BET_DAY, category="ufc")
    ledger.settle_from_history(L, H)
    assert _status(L, ticket)[0] == "open"
    assert _status(L, fight)[0] == "open"


def test_the_old_sweep_no_longer_grades_football():
    """One rule per question. The end-of-loop no-show sweep asked only
    "is the week final and is he in the file?" — a file still landing
    answered yes. For the NFL and college the loop's verdict is the only
    grader now; the sweep still owns baseball and hoops, where a box score
    lists everyone who appeared."""
    L, H = _world()
    _sunday(H, file_for=("MIA",), snaps=False)        # final week, thin file
    bid = _bet(L, "nfl", WEEK, "Tua Tagovailoa", market="pass_yds", line=210.5,
               side="UNDER", game_day=BET_DAY)
    ledger.settle_from_history(L, H)
    assert _status(L, bid)[0] == "open"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
