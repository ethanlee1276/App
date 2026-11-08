"""Every pick carries the field's fair price, and every football bet takes
its price close from our own snapshots (nba_build's props, engine/nba/
pipeline.evaluate_prop's card and the NBA journal; engine/ledger.
_snapshot_price_close).

The record's matched CLV (ledger._bet_clv_matched, audit P1-2) reads the
field's de-vigged fair at pick time (``fair_consensus``) against the field's
de-vigged close (``closing_fair``). On 8 November it covered 0 of the 145
graded NBA picks: the NBA board never journaled the field's fair. And 144 of
503 NFL picks: the snapshot price close was read under the bet's ``date``,
which for the NFL is its week's label ("2026-W10"), a key no close is ever
filed under. What these hold:

  * the NBA board's prop carries the field's fair at its number, its card
    carries it on, and the NBA journal writes it;
  * an NFL week bet's price close is read under its game's day: settled, it
    banks the field's fair close as well as a price;
  * a daily sport's bet reads its price close under its own date first,
    exactly as before.

Run directly: `python3 tests/test_every_pick_carries_the_fields_fair.py`
"""
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db, ledger, linemoves                           # noqa: E402
from engine.models import SportsbookLine                            # noqa: E402
from engine.odds import consensus_fair                              # noqa: E402
from engine.sources.oddsapi import normalize_name                   # noqa: E402

ET = ZoneInfo("America/New_York")


def test_the_nba_board_carries_the_fields_fair_to_its_journal():
    src = (ROOT / "nba_build.py").read_text(encoding="utf-8")
    assert "_field = consensus_fair(prop.lines, line)" in src
    assert '"fair_consensus": round(_field[0], 4) if _field else None,' in src
    assert '"consensus_books": _field[1] if _field else 0,' in src
    j = src.index('"proj_minutes": p.get("proj_minutes"),')
    assert '"fair_consensus": p.get("fair_consensus"),' in src[j:j + 300]
    assert '"consensus_books": p.get("consensus_books"),' in src[j:j + 300]
    from engine.nba import pipeline as P
    card_src = (ROOT / "engine" / "nba" / "pipeline.py").read_text(encoding="utf-8")
    assert '"fair_consensus": prop.get("fair_consensus"),' in card_src
    # And the journal keeps what it is handed.
    conn = ledger.connect(":memory:")
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    ledger.log_recommendations(conn, {"sport": "nba", "date": "2026-11-07", "recommendations": [
        {"player": "Jalen Brunson", "market": "pts", "side": "OVER", "line": 26.5,
         "book": "DraftKings", "odds": -110, "projection": 28.1, "hit_prob": 0.58,
         "edge": 0.05, "confidence": 5.8, "grade": "Play", "stake_units": 1.0,
         "fair_consensus": 0.512, "consensus_books": 5, "recommended": True}]})
    row = conn.execute("SELECT fair_consensus, consensus_books FROM bets").fetchone()
    assert (row["fair_consensus"], row["consensus_books"]) == (0.512, 5)
    assert P is not None


def test_the_fields_fair_is_every_book_at_the_number():
    lines = [SportsbookLine(book=b, line=26.5, over_odds=o, under_odds=u)
             for b, o, u in (("DraftKings", -115, -105), ("FanDuel", -110, -110),
                             ("BetMGM", -120, 100), ("Caesars", -110, -110))]
    lines.append(SportsbookLine(book="ESPN BET", line=27.5, over_odds=105, under_odds=-125))
    fair, n = consensus_fair(lines, 26.5)
    assert n == 4 and 0.5 < fair < 0.54, (fair, n)
    assert consensus_fair(lines[:2], 26.5) is None, "two books are not a field"


def _nfl_week1(tmp: Path):
    """An open week-1 receiving bet, his stat line, the game final, and our
    own snapshots of his line on the game's day; no purchased close."""
    kickoff = dt.datetime(2026, 9, 13, 13, 0, tzinfo=ET).timestamp()
    rows = []
    for h, books in ((20, (("DraftKings", -115, -105), ("FanDuel", -110, -110), ("BetMGM", -112, -108))),
                     (1, (("DraftKings", -125, 105), ("FanDuel", -120, 100), ("BetMGM", -122, 102)))):
        for book, over, under in books:
            rows.append({"ts": kickoff - h * 3600, "player": "Puka Nacua", "market": "rec_yds",
                         "book": book, "line": 79.5, "over_odds": over, "under_odds": under,
                         "start_ts": kickoff})
    p = tmp / "line_history.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    L = ledger.connect(tmp / "l.db")
    ledger.configure_bankroll(L, starting=1000, unit_pct=1.0)
    L.execute("INSERT INTO bets (ts, sport, date, player, market, side, line, book, odds, stake_units, "
              "stake_dollars, status, category, team) VALUES ('2026-09-12T12:00:00', 'nfl', '2026-W01', "
              "'Puka Nacua', 'rec_yds', 'OVER', 79.5, 'DraftKings', -110, 1, 10, 'open', 'main', 'LAR')")
    L.commit()
    H = db.connect(tmp / "h.db")
    db.upsert_games(H, [{"sport": "nfl", "season": 2026, "period": "001", "game_id": "g1",
                         "home": "LAR", "away": "SF", "home_score": 27, "away_score": 20,
                         "date": "2026-09-13", "spread": None, "total": None, "roof": "",
                         "surface": "", "temp": None, "wind": None, "extra": None}])
    db.upsert_player_logs(H, [{"sport": "nfl", "season": 2026, "period": "001", "game_id": "g1",
                               "player": "Puka Nacua", "team": "LAR", "opponent": "SF",
                               "position": "WR", "home": 1, "market": "rec_yds", "value": 96}])
    H.commit()
    return L, H, p


def test_an_nfl_week_bet_takes_its_price_close_from_its_games_day():
    with tempfile.TemporaryDirectory() as td:
        L, H, p = _nfl_week1(Path(td))
        saved = linemoves.HISTORY_PATH
        linemoves.HISTORY_PATH = p
        try:
            assert ledger.settle_from_history(L, H, sport="nfl") == 1
        finally:
            linemoves.HISTORY_PATH = saved
        b = L.execute("SELECT * FROM bets").fetchone()
    assert b["status"] == "won" and b["closing_line"] == 79.5, dict(b)
    assert b["closing_odds"] == -125, "the same book's last pre-game price"
    # The field at the last pull: the median over -122 and under +102,
    # de-vigged (122/222 against 100/202).
    assert b["closing_fair"] is not None and abs(b["closing_fair"] - 0.5261) < 1e-4, b["closing_fair"]


def test_the_price_close_reads_its_own_date_first_then_its_close_days():
    who = normalize_name("Puka Nacua")
    index = {(who, "rec_yds", "2026-09-13", 79.5): {"over": -122, "under": 102},
             (who, "pts", "2026-11-07", 26.5): {"over": -110, "under": -110},
             (who, "pts", "2026-11-06", 26.5): {"over": 150, "under": -180}}
    week = {"date": "2026-W01", "market": "rec_yds", "line": 79.5, "leg": None}
    assert ledger._snapshot_price_close(index, week, who, []) == {}, "a week's label is no close's day"
    assert ledger._snapshot_price_close(index, week, who, ["2026-09-13"]) == {"over": -122, "under": 102}
    day = {"date": "2026-11-07", "market": "pts", "line": 26.5, "leg": None}
    assert ledger._snapshot_price_close(index, day, who, ["2026-11-07"]) == {"over": -110, "under": -110}
    assert ledger._snapshot_price_close(index, day, who, ["2026-11-06", "2026-11-07"])["over"] == -110, \
        "its own date first"


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
