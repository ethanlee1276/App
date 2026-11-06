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
    assert '"nhl": ("KXNHLSPREAD", "KXNHLTOTAL")' in probe, "the probe still lists them"
    # The probe confirmed both on the box (6 November), the NBA's too.
    assert kalshi.LINE_SERIES["nhl"] == ("KXNHLSPREAD", "KXNHLTOTAL")
    assert kalshi.LINE_SERIES["nba"] == ("KXNBASPREAD", "KXNBATOTAL")
    assert "wnba" not in kalshi.LINE_SERIES, "empty until May: not wired in"
    from engine import kalshitrade
    assert set(kalshitrade.BOARD_FILE) == {"nfl", "cfb"}, "the trader places on football's boards only"


def _kx_line(ticker, floor, p):
    return {"ticker": ticker, "event_ticker": ticker.rsplit("-", 1)[0], "floor_strike": floor,
            "strike_type": "greater", "prob": p, "price_basis": "book", "spread_cents": 2.0,
            "volume_24h": 3000.0, "open_interest": 5000.0, "series": ticker.split("-", 1)[0]}


def test_a_hockey_game_carries_kalshis_puck_line_and_total():
    """The puck line is the board's own bet: Calgary at home −1.5 is
    Kalshi's "Calgary wins by over 1.5 goals"; Edmonton's same strike is a
    different bet (Edmonton −1.5) and is left out."""
    g = dict(GAMES[0], spread=1.5, favorite="CGY", total=6.5)
    kl = [_kx_line("KXNHLSPREAD-26NOV05EDMCGY-EDM2", 1.5, 0.29),
          _kx_line("KXNHLSPREAD-26NOV05EDMCGY-CGY2", 1.5, 0.31),
          _kx_line("KXNHLTOTAL-26NOV05EDMCGY-6", 5.5, 0.62),
          _kx_line("KXNHLTOTAL-26NOV05EDMCGY-7", 6.5, 0.47),
          _kx_line("KXNHLSPREAD-26NOV04EDMCGY-CGY2", 1.5, 0.90)]
    got = crowd.kalshi_lines(kl, g)
    assert got == {"spread_home_line": -1.5, "kalshi_home_cover": 0.31, "total_line": 6.5,
                   "kalshi_over": 0.47}, got
    away = dict(g, favorite="EDM")
    assert crowd.kalshi_lines(kl, away)["kalshi_home_cover"] == round(1 - 0.29, 4), \
        "Edmonton −1.5: Calgary +1.5 covers when Edmonton does not win by two"
    board = {"games": [dict(g)]}
    census = crowd.attach(board, "nhl", KALSHI, [], kl)
    assert census["kalshi_spread"] == 1 and census["kalshi_total"] == 1, census


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
