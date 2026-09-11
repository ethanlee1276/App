"""College game bets settle — which needs the season's results on file.

Ethan, 2026-09-06: "CFB doesn't seem to have settled its bets or it's
not showing all the bets that recommended on the record page."

`settle_from_history` grades a game bet — moneyline, spread, total,
team total — only from a `games` row on the bet's own date. The nightly
ingests three college feeds: closing lines and player logs both refresh
the season being played, and the RESULTS did not. Their guard was a
count of finished games, so once the four-season backfill had landed,
the block never ran again and no 2026 college result ever reached the
table. Player props still settled (their logs arrive on Monday); every
college game bet stayed open for ever.

Run directly: `python3 tests/test_cfb_settles.py`
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db, ingest, ledger, maintenance

SATURDAY = "2026-08-29"
BETS = [("moneyline", "UGA", 0.5, "OVER"), ("spread", "UGA", -7.5, "OVER"),
        ("total", "CLEM@UGA", 55.5, "UNDER"), ("team_total", "UGA", 27.5, "OVER"),
        ("anytime_td", "Ryan Williams", 0.5, "OVER")]


def _books():
    tmp = tempfile.mkdtemp()
    hist = db.connect(os.path.join(tmp, "h.db"))
    book = ledger.connect(os.path.join(tmp, "l.db"))
    book.executemany(
        "INSERT INTO bets (ts, sport, date, player, market, side, line, book, odds, "
        "stake_units, stake_dollars, status, category) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(SATURDAY + "T12:00:00", "cfb", SATURDAY, who, mkt, side, line, "DK",
          -110, 1.0, 10.0, "open", "main") for mkt, who, line, side in BETS])
    # The player logs arrive on their own (the Monday refresh); the game's
    # result is the thing that was never ingested.
    hist.execute(
        "INSERT INTO player_game_logs (sport, season, period, game_id, player, "
        "team, opponent, position, home, market, value) VALUES "
        "('cfb', 2026, ?, 'g1', 'Ryan Williams', 'ALA', 'UGA', 'WR', 1, 'anytime_td', 1.0)",
        (SATURDAY,))
    book.commit(); hist.commit()
    return book, hist


def _status(book):
    return {r["market"]: r["status"] for r in
            book.execute("SELECT market, status FROM bets")}


def test_without_the_seasons_results_only_the_prop_settles():
    book, hist = _books()
    assert ledger.settle_from_history(book, hist, "cfb") == 1
    got = _status(book)
    assert got["anytime_td"] == "won"
    for market in ("moneyline", "spread", "total", "team_total"):
        assert got[market] == "open", f"{market} graded with no game on file"


def test_the_game_bets_settle_the_moment_the_result_lands():
    book, hist = _books()
    ledger.settle_from_history(book, hist, "cfb")
    hist.execute(
        "INSERT INTO games (sport, season, period, game_id, home, away, "
        "home_score, away_score) VALUES ('cfb', 2026, ?, 'CLEM@UGA', 'UGA', "
        "'CLEM', 34, 21)", (SATURDAY,))
    hist.commit()
    assert ledger.settle_from_history(book, hist, "cfb") == 4
    got = _status(book)
    assert all(s != "open" for s in got.values()), got
    # 34-21: Georgia covered −7.5 and won, its team total cleared 27.5,
    # and 55 stayed under 55.5.
    assert got["moneyline"] == "won" and got["spread"] == "won"
    assert got["team_total"] == "won" and got["total"] == "won"


def test_the_nightly_refreshes_the_season_being_played():
    src = (ROOT / "engine" / "maintenance.py").read_text()
    i = src.index("from .ingest import ingest_cfb_history")
    block = src[i:src.index("cfb history backfill failed", i)]
    assert "in_season = today.month >= 8 or today.month <= 1" in block
    assert "[season] if in_season else []" in block, "no in-season refresh"
    assert "ttl=None if backfill else CFB_RESULTS_TTL" in block, \
        "a nightly re-read of a week-old cache settles nothing"
    assert "backfill = have < _CFB_MIN" in block, "the backfill still runs on a fresh box"
    assert maintenance.CFB_RESULTS_TTL < 24 * 3600


def test_the_ttl_reaches_the_feed():
    seen = {}

    def _stub(season, ttl=None, id_to_abbr=None):
        seen[season] = ttl
        return {"games": [], "skipped": []}

    from engine.sources import cfbfastr
    keep = cfbfastr.fetch_season
    cfbfastr.fetch_season = _stub
    try:
        conn = db.connect(os.path.join(tempfile.mkdtemp(), "h.db"))
        ingest.ingest_cfb_history(conn, [2026], id_to_abbr={}, quiet=True, ttl=3600)
        ingest.ingest_cfb_history(conn, [2024], id_to_abbr={}, quiet=True)
    finally:
        cfbfastr.fetch_season = keep
    assert seen[2026] == 3600, "the in-season refresh must beat the cache"
    assert seen[2024] is None, "a finished season keeps the feed's own default"


def test_a_refresh_cannot_erase_the_closing_lines_or_invent_a_scoreless_row():
    conn = db.connect(os.path.join(tempfile.mkdtemp(), "h.db"))
    row = {"sport": "cfb", "season": 2026, "period": SATURDAY,
           "game_id": "CLEM@UGA", "home": "UGA", "away": "CLEM",
           "home_score": 34, "away_score": 21, "spread": -7.5, "total": 55.5}
    db.upsert_games(conn, [row])
    # The results feed carries scores and no lines — the shape a refresh
    # writes over a row the lines pass has already annotated.
    db.upsert_games(conn, [{**row, "spread": None, "total": None}])
    got = conn.execute("SELECT spread, total, home_score FROM games "
                       "WHERE sport='cfb' AND period=?", (SATURDAY,)).fetchone()
    assert (got["spread"], got["total"], got["home_score"]) == (-7.5, 55.5, 34)
    # And the parser hands us only finished games, so no future Saturday
    # arrives as a scoreless row the settle guard would wait on.
    from engine.sources import cfbfastr
    src = (ROOT / "engine" / "sources" / "cfbfastr.py").read_text()
    i = src.index("def parse_schedule")
    assert 'skip("no final score")' in src[i:i + 2500]
    assert hasattr(cfbfastr, "fetch_season")


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
