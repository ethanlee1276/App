"""The live game page as the bettor's second screen (engine/livepace, the
ticket endpoint's CLV, engine/routes /live/{sport}/{event}, js/detail.js
Your action / Prop pace / the market's line / the footer).

Ethan's research (2026-10-29), its live-page spec: "'My Action' strip ...
'needs' text ... entry → current → close price (CLV)", "Prop Pace table:
player, stat, line, current, pace projection, % to hit", "model line vs.
market (no-vig) line", "Footer: 21+, 1-800-GAMBLER, 'Analytics, not
guarantees,' link to the public track record", and "URL: /live/{sport}/
{game_id}. Public (no login), SEO-indexed". What these hold:

  * prop pace lists every prop priced on the game alike, with the market
    half only (player, market, line, the best over and under) — never our
    side, chance, edge, tier or projection — his number, his pace once a
    sixth of the game is gone, and the over's chance anchored at the
    MARKET's no-vig chance; baseball prints no chance; it is cached;
  * a signed-in reader's tickets in the game carry their CLV, nobody else's;
  * /live/{sport}/{event} answers with the game's own title and opens its
    page; anything else is not a route; Caddy hands the path to the app;
  * the page draws both cards in both layouts, the market's start line on
    the win chart, and the footer; the reader's bets in the game count as a
    "sweat".

Run directly: `python3 tests/test_the_live_page_is_the_bettors_second_screen.py`
"""
import json
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import livepace as LP                                 # noqa: E402
from engine import routes                                         # noqa: E402

READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731
PAID = ("hit_prob", "model_prob", "edge", "tier", "side", "proj", "projection", "ev", "kelly", "pick")


def _web(state="live", period=3, clock="6:00", lebron=18, extra_rows=()):
    web = Path(tempfile.mkdtemp()) / "web"
    data = web / "data"
    (data / "pbp").mkdir(parents=True)
    game = {"event_id": "401", "home": "LAL", "away": "BOS",
            "live": {"state": state, "period": period, "clock": clock, "home_score": 70, "away_score": 66,
                     "start_time": "2026-10-29T23:30:00Z"}}
    (data / "live_nba.json").write_text(json.dumps({"games": [game]}))
    (data / "pbp" / "nba_401.json").write_text(json.dumps({"home": "LAL", "away": "BOS", "players": [
        {"player": "LeBron James", "stats": {"pts": lebron, "reb": 5, "ast": 6}},
        {"player": "Jayson Tatum", "stats": {"pts": 12, "reb": 7, "ast": 3}}]}))
    rows = [
        {"player": "LeBron James", "team": "LAL", "opponent": "BOS", "market": "pts", "market_label": "Points",
         "line": 24.5, "side": "UNDER", "hit_prob": 0.61, "edge": 0.07, "tier": "top", "odds": -115, "book": "FanDuel",
         "all_lines": [{"book": "FanDuel", "line": 24.5, "over_odds": -105, "under_odds": -115},
                       {"book": "DraftKings", "line": 24.5, "over_odds": 100, "under_odds": -120}]},
        {"player": "Jayson Tatum", "team": "BOS", "opponent": "LAL", "market": "pts", "market_label": "Points",
         "line": 27.5, "side": "OVER", "hit_prob": 0.55, "odds": -110,
         "all_lines": [{"book": "BetMGM", "line": 27.5, "over_odds": -110, "under_odds": -110}]},
        {"player": "Somebody Else", "team": "NYK", "opponent": "MIA", "market": "pts", "line": 20.5,
         "all_lines": [{"book": "BetMGM", "line": 20.5, "over_odds": -110, "under_odds": -110}]},
        *extra_rows]
    (data / "nba.json").write_text(json.dumps({"recommendations": rows, "games": []}))
    return web


def test_prop_pace_is_the_market_s_half_and_the_box():
    web = _web()
    got = LP.rows_for("nba", "401", web, now=time.time())
    assert got["state"] == "live" and 0 < got["share_left"] < 1
    players = [r["player"] for r in got["rows"]]
    assert sorted(players) == ["Jayson Tatum", "LeBron James"], "this game's props, every one alike"
    for r in got["rows"]:
        assert not (set(r) & set(PAID)), f"the paid half travelled: {set(r) & set(PAID)}"
    lb = next(r for r in got["rows"] if r["player"] == "LeBron James")
    assert lb["over"] == 100 and lb["under"] == -115, "the best price each side, at the line"
    played = 1 - got["share_left"]
    assert lb["current"] == 18 and abs(lb["pace"] - round(18 / played, 1)) < 0.05
    assert 0 < lb["chance"] < 1, lb
    # A bigger number so far is a bigger chance: it is the box moving it, not our model.
    hot = LP.rows_for("nba", "401", _web(lebron=26), now=time.time())
    assert next(r for r in hot["rows"] if r["player"] == "LeBron James")["result"] == "won"
    warm = LP.rows_for("nba", "401", _web(lebron=22), now=time.time())
    assert next(r for r in warm["rows"] if r["player"] == "LeBron James")["chance"] > lb["chance"]


def test_too_early_no_pace_and_bad_asks_are_empty():
    early = LP.rows_for("nba", "401", _web(period=1, clock="10:00"), now=time.time())
    assert all(r["pace"] is None for r in early["rows"]), "before a sixth of the game, no pace"
    assert LP.rows_for("nba", "40x", _web()) == {"rows": [], "state": ""}
    assert LP.rows_for("xfl", "401", _web()) == {"rows": [], "state": ""}
    assert LP.rows_for("nba", "999", _web(), now=time.time())["rows"] == [], "not a game on the scoreboard"


def test_it_is_cached_per_game():
    web = _web()
    t = time.time()
    a = LP.rows_for("nba", "401", web, now=t)
    (web / "data" / "nba.json").write_text(json.dumps({"recommendations": []}))
    assert LP.rows_for("nba", "401", web, now=t + 5) is a
    assert LP.rows_for("nba", "401", web, now=t + LP.CACHE_S + 1)["rows"] == []


def test_a_live_game_has_its_own_address():
    web = _web()
    r = routes.resolve("/live/nba/401", web)
    assert r and r["hash"] == "pbp/nba/401" and r["kind"] == "live"
    assert r["title"].startswith("BOS vs LAL live: score, stats and prop pace")
    assert r["canonical"].endswith("/live/nba/401")
    assert routes.resolve("/live/xfl/401", web) is None and routes.resolve("/live/nba/abc", web) is None
    assert routes.resolve("/live/nba/401/extra", web) is None
    # An id with no play file and not on the league's live board is not a game: the real 404.
    assert routes.resolve("/live/nba/999999", web) is None
    (web / "data" / "live_nba.json").write_text(json.dumps({"games": [{"event_id": "402", "away": "NYK", "home": "MIA"}]}))
    soon = routes.resolve("/live/nba/402", web)
    assert soon and soon["title"].startswith("NYK vs MIA live"), "a game not started yet is on its live board"
    assert "@entity path /player/* /game/* /pick/* /live/*" in READ("deploy", "Caddyfile")
    doc = routes.document(r, "<html><head><!-- QB:META --><title>x</title><!-- /QB:META --></head><body></body></html>")
    assert "BOS vs LAL live" in doc and 'name="qb-route"' in doc and "pbp/nba/401" in doc
    app = READ("web", "js", "app.js")
    assert "return { hash: `pbp/${segs[1].toLowerCase()}/${segs[2]}`, sport: \"\" };" in app, \
        "the installed app, opening its own copy, reads the address itself"


def test_the_server_answers_pace_and_ticket_clv():
    srv = READ("server.py")
    assert 'if parsed.path in ("/api/live/pace", "/api/live/pace/"):' in srv
    at = srv.index("def _chat_ticket(self, body: dict):")
    body = srv[at:srv.index("\n    def ", at + 10)]
    assert "BC.ticket(conn, who[\"id\"], t[\"id\"], legs=t.get(\"of\"))" in body and 'if who:' in body


def test_the_page_draws_both_cards_the_market_and_the_footer():
    from _app import app_js
    js = READ("web", "js", "detail.js")
    assert js.count('id="pbp-action"') == 1 and js.count("pbpMineSlotsHTML()") == 3, "both layouts"
    assert js.count("pbpFootHTML()") >= 2
    wire = js[js.index("  const wire = () => {"):js.index("  const wire = () => {") + 900]
    assert "pbpActionFill(league, event);" in wire and "pbpPaceFill(league, event);" in wire
    foot = js[js.index("function pbpFootHTML()"):js.index("function pbpFootHTML()") + 400]
    for w in ("21+", "Analytics, not guarantees", "1-800-GAMBLER", "#record"):
        assert w in foot, w
    assert "pbpWinChartHTML(d, league, boardGame)" in js and "const mkt = typeof pbpMarketHome === \"function\" ? pbpMarketHome(boardGame) : null;" in js
    assert 'track("sweat", league);' in js
    assert "not our pick" in js[js.index("function pbpPaceHTML()"):js.index("async function pbpPaceFill(")]
    assert "function pbpActionFill(" in app_js()


def test_the_market_line_is_the_moneylines_without_the_margin():
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        print("      (skipped: no node)")
        return
    js = READ("web", "js", "detail.js")
    fn = js[js.index("function pbpMarketHome("):js.index("function pbpFootHTML()")]
    out = subprocess.run([node, "-e", fn + "console.log(JSON.stringify([pbpMarketHome({home_ml: -150, away_ml: 130}),"
                          "pbpMarketHome({home_ml: -150}), pbpMarketHome(null)]))"],
                         capture_output=True, text=True, timeout=30)
    got = json.loads(out.stdout)
    assert abs(got[0] - (0.6 / (0.6 + 1 / 2.3))) < 1e-9 and got[1] is None and got[2] is None, got


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
