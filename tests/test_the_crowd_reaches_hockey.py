"""Kalshi and Polymarket on every NHL game (the all-sports audit, 2026-11-05).

The NHL board has called the crowd hook (engine/crowd.attach_to_board) in
its after-hooks since it was built, and the hook asked both venues for a
league neither reader listed: Polymarket's tags and /sports keys had no
"nhl", Kalshi's game series and league hints had none. So no hockey game
ever carried a crowd price, the game report's market section had nothing
to say for hockey, and the crowd study (engine/crowdfit) had no NHL rows.
Each name is a candidate, like every other league's: the build's per-tag
and per-series report says which are real (crowdprobe.py on the box).

Run directly: `python3 tests/test_the_crowd_reaches_hockey.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import crowd                                         # noqa: E402
from engine.sources import kalshi, polysports                    # noqa: E402

GAMES = [{"home": "CGY", "away": "EDM", "date": "2026-11-05", "kickoff": "2026-11-06T02:00:00Z",
          "home_ml": 120, "away_ml": -140}]

EVENT = {"slug": "nhl-edm-cgy-2026-11-05", "startDate": "2026-11-06T02:00:00Z", "markets": [
    {"slug": "nhl-edm-cgy-2026-11-05", "question": "Oilers vs. Flames", "sportsMarketType": "moneyline",
     "outcomes": "[\"Oilers\", \"Flames\"]", "outcomePrices": "[\"0.57\", \"0.43\"]",
     "bestBid": 0.56, "bestAsk": 0.58, "liquidity": "18000", "volume24hr": 40000},
    {"slug": "nhl-edm-cgy-puck", "question": "Puck Line: Oilers (-1.5)",
     "outcomes": "[\"Oilers\", \"Flames\"]", "outcomePrices": "[\"0.33\", \"0.67\"]"},
    {"slug": "nhl-edm-cgy-goals", "question": "Oilers vs. Flames: Total Goals O/U 6.5",
     "outcomes": "[\"Over\", \"Under\"]", "outcomePrices": "[\"0.5\", \"0.5\"]"},
    {"slug": "nhl-edm-cgy-p1", "question": "Oilers vs. Flames: 1st Period Winner",
     "outcomes": "[\"Oilers\", \"Flames\"]", "outcomePrices": "[\"0.4\", \"0.6\"]"}]}

KALSHI = [{"ticker": "KXNHLGAME-26NOV05EDMCGY-CGY", "event_ticker": "KXNHLGAME-26NOV05EDMCGY",
           "title": "Calgary wins", "subtitle": "", "prob": 0.44, "price_basis": "book",
           "spread_cents": 2.0, "volume_24h": 3000.0, "open_interest": 5000.0}]


def test_both_readers_list_the_nhl():
    assert polysports.SPORT_TAGS["nhl"] == ("nhl",) and polysports.SPORT_KEYS["nhl"] == ("nhl",)
    assert kalshi.SPORT_SERIES["nhl"][0] == "KXNHLGAME"
    assert kalshi.sport_of(KALSHI[0]) == "nhl"
    assert kalshi.sport_of({"ticker": "KXNBAGAME-26NOV05LALBOS-BOS"}) == "nba", "the others unchanged"
    probe = (ROOT / "crowdprobe.py").read_text(encoding="utf-8")
    assert '"nhl": ("KXNHLSPREAD", "KXNHLTOTAL")' in probe, "the spread and total names wait for the probe"
    assert "nhl" not in kalshi.LINE_SERIES, "unconfirmed series are not wired in"


def test_only_the_winner_is_the_moneyline():
    rows = polysports.parse_events([EVENT])
    assert len(rows) == 1 and rows[0]["teams"] == ["Oilers", "Flames"], rows
    for m in EVENT["markets"][1:]:
        assert not polysports.is_moneyline(m), m["question"]


def test_a_hockey_game_carries_both_venues():
    board = {"games": [dict(g) for g in GAMES]}
    poly = [dict(r, sport="nhl") for r in polysports.parse_events([EVENT])]
    census = crowd.attach(board, "nhl", KALSHI, poly)
    c = board["games"][0]["crowd"]
    assert census["polymarket"] == 1 and census["kalshi"] == 1, census
    assert c["polymarket"] == 0.43, "the Flames are the home side"
    assert c["kalshi"] == 0.44
    assert "model" not in c


def test_the_nhl_board_calls_the_hook():
    src = (ROOT / "nhl_build.py").read_text(encoding="utf-8")
    assert '("crowd prices", lambda: __import__("engine.crowd", fromlist=["x"]).attach_to_board(out, SPORT))' in src


def test_the_runbook_and_the_catchup_run_the_probe():
    line = "cd /srv/qellys && sudo -u qellys nice -n 19 python3 crowdprobe.py nhl nba wnba"
    for doc in ("docs/WHEN_YOU_ARE_HOME.md", "tools/catchup.sh", "docs/RUN_NEXT.md"):
        assert line in (ROOT / doc).read_text(encoding="utf-8"), doc
    assert "step KL" in (ROOT / "docs" / "RUN_NEXT.md").read_text(encoding="utf-8")


if __name__ == "__main__":
    import inspect
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
