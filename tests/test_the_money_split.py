"""Where the money is going on a game — the prediction markets' tapes.

Ethan, 2026-09-28, DraftKings' "% of bets placed" bars beside our game page:
"When we click on a game, I want it to also show … what percent of money is
on what team and on what spread and on what Moneyline." He chose the free
source (Kalshi and Polymarket's public trade tapes) over a paid splits feed.
Pinned here: the side each taker bought, in dollars and in trades; the
board's own spread and total only; nothing drawn from a thin tape; no
network behind an injected feed; and the page's bars.

Run directly: `python3 tests/test_the_money_split.py`
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import crowd, moneysplit as M                     # noqa: E402
from engine.sources import polysports as P                     # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
NOW = 1_790_000_000.0          # 2026-09-21 — every fixture game is still to come

GAME = {"away": "BUF", "home": "KC", "away_name": "Buffalo Bills", "home_name": "Kansas City Chiefs",
        "date": "2026-09-28", "kickoff": "16:25", "spread": 2.5, "favorite": "KC", "total": 47.5,
        "home_ml": -135, "away_ml": 115}


def _kt(side, count, yes_cents):
    """A Kalshi trade in the API's current (dollar, fixed-point) shape."""
    return {"taker_side": side, "count_fp": str(count), "yes_price_dollars": f"{yes_cents / 100:.2f}",
            "no_price_dollars": f"{1 - yes_cents / 100:.2f}"}


def test_kalshi_money_follows_the_taker():
    acc = M.kalshi_flow([_kt("yes", 100, 60), _kt("no", 50, 60), _kt("yes", 10, 60)], "home", "away")
    assert round(acc["home"]["usd"], 2) == 66.0 and acc["home"]["n"] == 2      # 110 × $0.60
    assert round(acc["away"]["usd"], 2) == 20.0 and acc["away"]["n"] == 1      # 50 × $0.40
    # the legacy cent integers read the same
    legacy = M.kalshi_flow([{"taker_side": "yes", "count": 100, "yes_price": 60, "no_price": 40}], "home", "away")
    assert round(legacy["home"]["usd"], 2) == 60.0
    # junk is skipped, never guessed
    assert M.kalshi_flow([{"taker_side": "maybe", "count": 5}, {"count": 0}, "x"], "home", "away") == {}


def test_polymarket_buys_and_sells_land_on_the_right_side():
    side_of = lambda o: ("over", "under") if o == "Over" else ("under", "over") if o == "Under" else None  # noqa: E731
    acc = M.poly_flow([{"side": "BUY", "outcome": "Over", "size": 100, "price": 0.5},
                       {"side": "SELL", "outcome": "Over", "size": 100, "price": 0.4},   # out of the over = into the under
                       {"side": "BUY", "outcome": "Push?", "size": 100, "price": 0.5}], side_of)
    assert acc == {"over": {"usd": 50.0, "n": 1}, "under": {"usd": 60.0, "n": 1}}


def test_shares_and_the_thin_tape_rule():
    s = M.split({"home": {"usd": 750.0, "n": 30}, "away": {"usd": 250.0, "n": 10}}, "home", "away")
    assert s == {"home": 0.75, "away": 0.25, "home_bets": 0.75, "away_bets": 0.25, "usd": 1000, "n": 40}
    assert M.split({"home": {"usd": 100.0, "n": 30}}, "home", "away") is None, "under $250 says nothing"
    assert M.split({"home": {"usd": 5000.0, "n": 5}}, "home", "away") is None, "five trades say nothing"


def _poly_rows():
    ev = {"slug": "nfl-buf-kc-2026-09-28", "startDate": "2026-09-28T20:25:00Z", "markets": [
        {"question": "Bills vs. Chiefs", "sportsMarketType": "moneyline", "conditionId": "0xML",
         "outcomes": json.dumps(["Bills", "Chiefs"]), "outcomePrices": json.dumps(["0.45", "0.55"]),
         "bestBid": 0.44, "bestAsk": 0.46, "liquidity": 5000},
        {"question": "Spread: Chiefs (-2.5)", "sportsMarketType": "spreads", "conditionId": "0xSP",
         "outcomes": json.dumps(["Chiefs", "Bills"]), "outcomePrices": json.dumps(["0.5", "0.5"]),
         "bestBid": 0.49, "bestAsk": 0.51, "liquidity": 5000},
        {"question": "Bills vs. Chiefs: O/U 47.5", "conditionId": "0xTOT",
         "outcomes": json.dumps(["Over", "Under"]), "outcomePrices": json.dumps(["0.5", "0.5"]),
         "bestBid": 0.49, "bestAsk": 0.51, "liquidity": 5000}]}
    return [dict(r, sport="nfl") for r in P.parse_events([ev])]


def _kx(ticker, floor=None, prob=0.5, **kw):
    event = ticker.rsplit("-", 1)[0]
    row = {"ticker": ticker, "event_ticker": event, "series": event.split("-")[0], "prob": prob,
           "price_basis": "book", "spread_cents": 2.0, "volume_24h": 5000.0, "open_interest": 0.0,
           "title": "", "subtitle": ""}
    if floor is not None:
        row.update(floor_strike=floor, strike_type="greater")
    row.update(kw)
    return row


def test_the_ids_ride_along_only_when_asked():
    rows = _poly_rows()
    assert rows[0]["condition_id"] == "0xML"
    plain = crowd.crowd_lines(rows[0], dict(GAME), False)
    assert "poly_spread_cid" not in plain and "poly_total_cid" not in plain, "the board's crowd block stays as it was"
    got = crowd.crowd_lines(rows[0], dict(GAME), False, ids=True)
    assert got["poly_spread_cid"] == "0xSP" and got["poly_total_cid"] == "0xTOT"
    kx = crowd.kalshi_lines([_kx("KXNFLSPREAD-26SEP28BUFKC-KC3", 2.5), _kx("KXNFLTOTAL-26SEP28BUFKC-48", 47.5)],
                            dict(GAME), ids=True)
    assert kx["kalshi_spread_ticker"] == "KXNFLSPREAD-26SEP28BUFKC-KC3" and kx["kalshi_spread_yes"] == "home"
    assert kx["kalshi_total_ticker"] == "KXNFLTOTAL-26SEP28BUFKC-48"
    assert "kalshi_spread_ticker" not in crowd.kalshi_lines([_kx("KXNFLSPREAD-26SEP28BUFKC-KC3", 2.5)], dict(GAME))


def test_a_game_gets_all_three_bars_from_both_venues():
    result = {"games": [dict(GAME)]}
    kwin = [_kx("KXNFLGAME-26SEP28BUFKC-KC", title="Kansas City wins", prob=0.55),
            _kx("KXNFLGAME-26SEP28BUFKC-BUF", title="Buffalo wins", prob=0.45)]
    kline = [_kx("KXNFLSPREAD-26SEP28BUFKC-KC3", 2.5), _kx("KXNFLTOTAL-26SEP28BUFKC-48", 47.5)]
    tapes = {
        "KXNFLGAME-26SEP28BUFKC-KC": [_kt("yes", 100, 55)] * 12,          # money on KC
        "KXNFLGAME-26SEP28BUFKC-BUF": [_kt("no", 100, 45)] * 4,           # a NO on Buffalo is money on KC too
        "KXNFLSPREAD-26SEP28BUFKC-KC3": [_kt("no", 100, 50)] * 12,        # KC does NOT cover: money on BUF +2.5
        "KXNFLTOTAL-26SEP28BUFKC-48": [_kt("yes", 100, 50)] * 12,         # over
    }
    poly = {"0xML": [{"side": "BUY", "outcome": "Bills", "size": 1000, "price": 0.45}] * 4,
            "0xSP": [], "0xTOT": [{"side": "BUY", "outcome": "Under", "size": 100, "price": 0.5}] * 4}
    census = M.attach(result, "nfl", kwin, kline, _poly_rows(), kalshi_trades=lambda t: tapes.get(t, []),
                      poly_trades=lambda c: poly.get(c, []), now=NOW)
    m = result["games"][0]["money"]
    assert census["games"] == 1 and set(m) >= {"ml", "spread", "total", "venues"}
    # KC: 12×$55 + 4×$55 (NO on BUF at 55¢) = $880; BUF: 4×$450 = $1800
    assert m["ml"]["home"] == round(880 / 2680, 3) and m["ml"]["away_bets"] == round(4 / 20, 3)
    assert m["spread"]["away"] == 1.0 and m["spread"]["line"] == -2.5
    assert m["total"]["over"] == round(600 / 800, 3) and m["total"]["line"] == 47.5
    assert m["venues"] == ["Kalshi", "Polymarket"]


def test_a_started_game_and_a_thin_one_get_nothing():
    started = dict(GAME, live={"state": "live"})
    result = {"games": [started]}
    M.attach(result, "nfl", [_kx("KXNFLGAME-26SEP28BUFKC-KC", title="Kansas City wins")], [], [],
             kalshi_trades=lambda t: [_kt("yes", 100, 55)] * 50, poly_trades=lambda c: [], now=NOW)
    assert "money" not in result["games"][0], "a started game's tape is live betting"
    result = {"games": [dict(GAME)]}
    M.attach(result, "nfl", [_kx("KXNFLGAME-26SEP28BUFKC-KC", title="Kansas City wins")], [], [],
             kalshi_trades=lambda t: [_kt("yes", 1, 55)] * 3, poly_trades=lambda c: [], now=NOW)
    assert "money" not in result["games"][0], "three one-dollar trades are not a split"


def test_a_venue_that_fails_costs_only_its_own_bar():
    from engine.sources.fetch import DataUnavailable

    def boom(_):
        raise DataUnavailable("down")
    result = {"games": [dict(GAME)]}
    census = M.attach(result, "nfl", [_kx("KXNFLGAME-26SEP28BUFKC-KC", title="Kansas City wins")], [], _poly_rows(),
                      kalshi_trades=boom, poly_trades=lambda c: [{"side": "BUY", "outcome": "Chiefs",
                                                                  "size": 1000, "price": 0.55}] * 12, now=NOW)
    assert census["errors"] == 1 and result["games"][0]["money"]["venues"] == ["Polymarket"]


def test_an_injected_price_feed_never_reads_a_tape_from_the_network():
    src = (ROOT / "engine" / "crowd.py").read_text(encoding="utf-8")
    assert "injected = any(f is not None for f in (kalshi_fetch, poly_fetch, kalshi_line_fetch))" in src
    b = {"games": [dict(GAME)]}
    crowd.attach_to_board(b, "nfl", kalshi_fetch=lambda: ([], {}), poly_fetch=lambda: ([], {}), record=False)
    assert "money_census" not in b


def test_the_game_page_draws_the_three_bars():
    assert "const gpMoney = isFinal ? \"\" : gameMoneyHTML(g);" in APP and "${gpMoney}" in APP
    if not shutil.which("node"):
        print("  SKIP node is not installed")
        return
    i = APP.index("function gameMoneyHTML(g)")
    depth, j = 0, APP.index("{", i)
    for k in range(j, len(APP)):
        depth += {"{": 1, "}": -1}.get(APP[k], 0)
        if depth == 0:
            fn = APP[i:k + 1]
            break
    prog = """
const MINUS = "\\u2212";
const escapeHtml = (s) => String(s);
const escapeAttr = (s) => String(s);
""" + fn + """
const g = {away: "PHI", home: "CHI", money: {
  ml: {home: 0.08, away: 0.92, home_bets: 0.2, away_bets: 0.8, usd: 52000, n: 900},
  spread: {home: 0.19, away: 0.81, home_bets: 0.3, away_bets: 0.7, usd: 21000, n: 400, line: 3.5},
  total: {over: 0.58, under: 0.42, over_bets: 0.5, under_bets: 0.5, usd: 9000, n: 200, line: 41.5},
  venues: ["Kalshi", "Polymarket"], at: "19:50"}};
const html = gameMoneyHTML(g);
const want = ["<b>92%</b> PHI", "CHI <b>8%</b>", "PHI \\u22123.5", "CHI +3.5", "<b>81%</b>",
              "Over 41.5", "Under 41.5", "<b>58%</b>", "$52,000 on 900 trades", "Kalshi and Polymarket",
              "not sportsbook customers", "width:92.0%"];
const miss = want.filter((w) => !html.includes(w));
console.log(miss.length ? "MISSING " + miss.join(" | ") : (gameMoneyHTML({away: "A", home: "B"}) === "" ? "OK" : "EMPTY?"));
"""
    out = subprocess.run(["node", "-e", prog], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-500:]
    assert out.stdout.strip() == "OK", out.stdout


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
