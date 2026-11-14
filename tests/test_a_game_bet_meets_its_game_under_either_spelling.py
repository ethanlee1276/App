"""A game-line bet meets its game under either spelling of the club.

Found 2026-10-14 the evening Ethan got home: the basketball history is
ESPN's, and ESPN spells six NBA clubs its own way (GS, NY, NO, SA, UTAH,
WSH) and six WNBA clubs too (LV, NY, LA, GS, CONN, WSH). Every bet carries
the league's own code (GSW, NYK, LVA, NYL, WAS...), and a moneyline,
spread or total looked its game up by that code alone — so a bet on one of
those clubs could never meet its final and stayed open. The NBA's stored
rows were rewritten (`nbacodes.py`, 160,671 values on the box); the
grading now finds the game under any spelling and compares the sides as
the league spells them, so the WNBA's rows grade as they stand.

Pinned here: a WNBA moneyline on the Aces against a game stored under
"LV", a spread on the Mystics against "WSH" (the alias the WNBA's table
lacked), a total keyed by the league's codes against ESPN's game id and
spellings, an NBA moneyline on the Warriors against "GS" — and a bet on
another club that day is not graded off the wrong game.

Run directly: `python3 tests/test_a_game_bet_meets_its_game_under_either_spelling.py`
"""
import datetime as dt
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db, divisions, ledger                           # noqa: E402

DAY = (dt.date.today() - dt.timedelta(days=3)).isoformat()


def _world(sport, games):
    t = Path(tempfile.mkdtemp())
    L, H = ledger.connect(t / "l.db"), db.connect(t / "h.db")
    for gid, home, away, hs, as_ in games:
        H.execute("INSERT INTO games (sport, season, period, game_id, date, home, away, home_score, away_score) "
                  "VALUES (?, 2026, ?, ?, ?, ?, ?, ?, ?)", (sport, DAY, gid, DAY, home, away, hs, as_))
    H.commit()
    return L, H


def _bet(L, sport, market, player, side="OVER", line=0.5):
    L.execute("INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, odds, stake_units, "
              "stake_dollars, status, category) VALUES (?, ?, ?, ?, ?, ?, ?, ?, -110, 1, 0, 'open', 'potd')",
              (f"{DAY}T15:00:00", sport, DAY, DAY, player, market, side, line))
    L.commit()


def _status(L):
    return {(r[0], r[1]): r[2] for r in L.execute("SELECT market, player, status FROM bets")}


def test_the_wnbas_bets_grade_against_espns_spellings():
    L, H = _world("wnba", [("401700001", "LV", "NY", 88, 80), ("401700002", "WSH", "CONN", 70, 75)])
    _bet(L, "wnba", "moneyline", "LVA")                         # won: the Aces at home
    _bet(L, "wnba", "moneyline", "NYL")                         # lost
    _bet(L, "wnba", "spread", "WAS", line=3.5)                  # the Mystics lost by 5: -5 < 3.5
    _bet(L, "wnba", "total", "CON@WAS", side="OVER", line=140.5)    # 145: won
    assert ledger.settle_from_history(L, H, sport="wnba") == 4
    assert _status(L) == {("moneyline", "LVA"): "won", ("moneyline", "NYL"): "lost",
                          ("spread", "WAS"): "lost", ("total", "CON@WAS"): "won"}, _status(L)


def test_the_nbas_bets_grade_against_espns_spellings_and_never_the_wrong_game():
    L, H = _world("nba", [("401800001", "GS", "NY", 101, 110), ("401800002", "BOS", "MIA", 99, 90)])
    _bet(L, "nba", "moneyline", "NYK")                          # won on the road
    _bet(L, "nba", "spread", "GSW", line=-2.5)                  # lost by 9: -9 < -2.5
    _bet(L, "nba", "moneyline", "MIA")                          # its own game, not the Warriors'
    assert ledger.settle_from_history(L, H, sport="nba") == 3
    assert _status(L) == {("moneyline", "NYK"): "won", ("spread", "GSW"): "lost",
                          ("moneyline", "MIA"): "lost"}, _status(L)


def test_every_spelling_of_a_club_and_the_wnbas_washington():
    assert divisions.spellings("nba", "GSW") == ["GS", "GSW"]
    assert divisions.spellings("nba", "GS") == ["GS", "GSW"]
    assert divisions.spellings("wnba", "WAS") == ["WAS", "WSH"] and divisions.canonical("wnba", "WSH") == "WAS"
    assert divisions.spellings("mlb", "NYY") == ["NYY"], "a club with one spelling is just itself"
    assert divisions.canonical("nhl", "WSH") == "WSH", "hockey's Washington is still WSH"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
