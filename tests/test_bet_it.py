"""Bet it: every pick carries the book's own bet-slip link (engine/betlinks),
and the Discord page shows what the site posts by itself.

Ethan, 2026-10-06: "build the bet it button and the discord page too."
Fixtures only; no network, nothing written outside a temp directory.

Run directly: `python3 tests/test_bet_it.py`
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import betlinks as B                               # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DK = "https://sportsbook.draftkings.com/event/1?outcomes="
MGM = "https://sports.{state}.betmgm.com/en/sports?options="


def _o(name, price, link=None, point=None, desc=None):
    o = {"name": name, "price": price}
    if point is not None:
        o["point"] = point
    if desc:
        o["description"] = desc
    if link:
        o["link"] = link
    return o


def _event():
    return {
        "id": "ev1", "commence_time": "2026-10-11T17:00:00Z",
        "home_team": "Buffalo Bills", "away_team": "Los Angeles Chargers",
        "bookmakers": [
            {"key": "draftkings", "link": "https://sportsbook.draftkings.com/event/1",
             "markets": [
                 {"key": "player_pass_yds", "link": "https://sportsbook.draftkings.com/event/1?cat=pass",
                  "outcomes": [_o("Over", -110, DK + "allen-o", 249.5, "Josh Allen"),
                               _o("Under", -110, DK + "allen-u", 249.5, "Josh Allen")]},
                 {"key": "player_rush_yds_alternate",
                  "outcomes": [_o("Over", -180, DK + "cook-60", 60.5, "James Cook")]},
                 {"key": "player_anytime_td",
                  "outcomes": [_o("Yes", 450, DK + "coleman-td", None, "Keon Coleman")]},
                 {"key": "spreads",
                  "outcomes": [_o("Buffalo Bills", -110, DK + "buf-6.5", -6.5),
                               _o("Los Angeles Chargers", -110, DK + "lac+6.5", 6.5)]},
                 {"key": "totals",
                  "outcomes": [_o("Over", -105, DK + "o47.5", 47.5), _o("Under", -115, DK + "u47.5", 47.5)]},
             ]},
            {"key": "fanduel", "link": "https://sportsbook.fanduel.com/event/1",
             "markets": [{"key": "player_pass_yds", "outcomes": [
                 _o("Over", 100, "https://sportsbook.fanduel.com/addToBetslip?id=allen-o", 249.5, "Josh Allen")]}]},
            {"key": "pinnacle", "link": "https://www.pinnacle.com/e/1",
             "markets": [{"key": "player_pass_yds", "outcomes": [
                 _o("Over", 105, "https://www.pinnacle.com/allen-o", 249.5, "Josh Allen")]}]},
            {"key": "betmgm", "link": "https://sports.{state}.betmgm.com/en/sports/events/1",
             "markets": [
                 {"key": "h2h", "outcomes": [_o("Buffalo Bills", -300, MGM + "buf-ml"),
                                             _o("Los Angeles Chargers", 240, MGM + "lac-ml")]},
                 {"key": "player_receptions", "outcomes": [_o("Over", -120, None, 3.5, "Khalil Shakir")]},
             ]},
        ]}


def _banked(tmp, cache_name="odds_event_nfl_ev1_abcd1234.json", now=None):
    body = json.dumps(_event())
    out = B.bank(body, cache_name, cache_dir=tmp, now=now)
    return body, out


def _board():
    allen = {"player": "Josh Allen", "market": "pass_yds", "side": "OVER", "line": 249.5, "odds": -110,
             "book": "DraftKings", "team": "BUF", "opponent": "LAC",
             "all_lines": [{"book": "DraftKings", "line": 249.5, "over_odds": -110, "under_odds": -110},
                           {"book": "FanDuel", "line": 249.5, "over_odds": 100, "under_odds": -120}]}
    return {
        "recommendations": [dict(allen),
                            {"player": "James Cook", "market": "rush_yds", "side": "OVER", "line": 60.5,
                             "odds": -180, "book": "DraftKings", "team": "BUF", "opponent": "LAC"},
                            {"player": "Khalil Shakir", "market": "receptions", "side": "OVER", "line": 3.5,
                             "odds": -120, "book": "BetMGM", "team": "BUF", "opponent": "LAC"},
                            {"player": "Nobody", "market": "receptions", "side": "OVER", "line": 3.5,
                             "odds": -120, "book": "Fliff", "team": "BUF", "opponent": "LAC"}],
        "long_shots": [{"player": "Keon Coleman", "market": "anytime_td", "side": "YES", "line": 0.5,
                        "odds": 450, "book": "DraftKings", "team": "BUF", "opponent": "LAC"}],
        "game_bets": [{"bet_type": "spread", "market": "spread", "team": "BUF", "line": -6.5, "odds": -110,
                       "book": "DraftKings", "home": "BUF", "away": "LAC", "pick_label": "BUF -6.5"},
                      {"bet_type": "total", "market": "total", "side": "Over", "line": 47.5, "odds": -105,
                       "book": "DraftKings", "home": "BUF", "away": "LAC", "pick_label": "Over 47.5"},
                      {"bet_type": "moneyline", "market": "moneyline", "team": "BUF", "line": 0, "odds": -300,
                       "book": "BetMGM", "home": "BUF", "away": "LAC", "pick_label": "BUF ML"}],
        "pick_of_the_day": {"date": "2026-10-11", "pick": dict(allen)},
        "player_stats": {"Josh Allen": {"book": "DraftKings", "odds": -110, "player": "x", "market": "y", "side": "z"}},
    }


def test_the_links_leave_the_paid_cache_for_their_own_small_file():
    tmp = Path(tempfile.mkdtemp())
    body, out = _banked(tmp)
    assert '"link"' in body and '"link"' not in out, "the odds cache keeps the body WITHOUT the links"
    back = json.loads(out)
    assert back["bookmakers"][0]["markets"][0]["outcomes"][0]["price"] == -110, "prices untouched"
    side = tmp / "betlinks_event_nfl_ev1_abcd1234.json"
    assert side.exists()
    ev = json.loads(side.read_text())["events"]["ev1"]
    assert ev["slip"]["draftkings|player_pass_yds|josh allen|over|249.5"] == DK + "allen-o"
    assert ev["slip"]["draftkings|player_anytime_td|keon coleman|yes|"] == DK + "coleman-td"
    assert ev["slip"]["draftkings|totals|los angeles chargers@buffalo bills|over|47.5"] == DK + "o47.5"
    assert ev["page"]["draftkings"].endswith("/event/1")
    # A body with no links, or that is not ours, comes back exactly as it went in.
    plain = json.dumps({"id": "x", "bookmakers": []})
    assert B.bank(plain, "odds_event_nfl_x_1.json", cache_dir=tmp) == plain
    assert B.bank("not json", "odds_event_nfl_x_1.json", cache_dir=tmp) == "not json"
    assert B.bank(body, "odds_budget.json", cache_dir=tmp) == body


def test_old_link_files_are_pruned_and_never_read():
    tmp = Path(tempfile.mkdtemp())
    _banked(tmp)
    old = tmp / "betlinks_event_nfl_old_1.json"
    old.write_text(json.dumps({"events": {"old": {"slip": {"x": "https://x"}, "page": {}}}}))
    stale = time.time() - B.KEEP_S - 60
    os.utime(old, (stale, stale))
    assert "old" not in B.load("nfl", cache_dir=tmp)
    assert B.prune(tmp) == 1 and not old.exists()
    assert B.load("nba", cache_dir=tmp) == {}, "another league's links are not this one's"


def test_every_kind_of_pick_gets_its_own_slip():
    tmp = Path(tempfile.mkdtemp())
    _banked(tmp)
    board = _board()
    n = B.stamp(board, "recommendations.json", env={}, cache_dir=tmp)
    rec = board["recommendations"]
    assert rec[0]["bet_link"] == DK + "allen-o" and rec[0]["bet_link_kind"] == "slip"
    assert rec[1]["bet_link"] == DK + "cook-60", "a Most Likely rung on the alternate ladder"
    assert board["long_shots"][0]["bet_link"] == DK + "coleman-td", "anytime TD: Yes, no line on the book"
    gb = board["game_bets"]
    assert gb[0]["bet_link"] == DK + "buf-6.5", "the team's own spread number"
    assert gb[1]["bet_link"] == DK + "o47.5", "the total, matched to its game"
    assert gb[2]["bet_link"] == "https://sports.mi.betmgm.com/en/sports?options=buf-ml", "{state} → mi"
    assert board["pick_of_the_day"]["pick"]["bet_link"] == DK + "allen-o"
    assert n == 9, "every pick with a slip or its game's pages, the Fliff row included"


def test_the_box_lists_every_book_with_the_bet_own_book_first_then_best_price():
    """Ethan, 2026-10-06: "a box that shows all the different sports books …
    so it doesn't just send someone to one specific sportsbook"."""
    tmp = Path(tempfile.mkdtemp())
    _banked(tmp)
    board = _board()
    B.stamp(board, "recommendations.json", env={}, cache_dir=tmp)
    allen = board["recommendations"][0]
    assert allen["bet_links"] == [["DraftKings", DK + "allen-o", -110],
                                  ["FanDuel", "https://sportsbook.fanduel.com/addToBetslip?id=allen-o", 100]]
    assert all(t != "Pinnacle" for t, _, _ in allen["bet_links"]), "no US action, never offered"
    # The game's page at every book, once on the board; the row points at it.
    nobody = board["recommendations"][3]
    assert nobody["bet_ev"] == "ev1" and "bet_link" not in nobody
    pages = dict(board["bet_pages"]["ev1"])
    assert set(pages) == {"DraftKings", "FanDuel", "BetMGM"}
    assert pages["BetMGM"] == "https://sports.mi.betmgm.com/en/sports/events/1"


def test_no_outcome_link_falls_back_to_the_game_page_and_no_book_means_no_button():
    tmp = Path(tempfile.mkdtemp())
    _banked(tmp)
    board = _board()
    B.stamp(board, "recommendations.json", env={"QB_BET_STATE": "NJ"}, cache_dir=tmp)
    shakir, nobody = board["recommendations"][2], board["recommendations"][3]
    assert shakir["bet_link_kind"] == "page" and shakir["bet_link"] == "https://sports.nj.betmgm.com/en/sports/events/1"
    assert "bet_link" not in nobody, "a book with nothing banked gets no button"
    assert "bet_link" not in board["player_stats"]["Josh Allen"], "stats are not picks"


def test_a_wrong_line_or_side_is_never_linked_to_a_neighbour():
    tmp = Path(tempfile.mkdtemp())
    _banked(tmp)
    board = {"recommendations": [
        {"player": "Josh Allen", "market": "pass_yds", "side": "OVER", "line": 250.5, "odds": -110,
         "book": "DraftKings", "team": "BUF", "opponent": "LAC"},
        {"player": "Josh Allen", "market": "pass_yds", "side": "UNDER", "line": 249.5, "odds": -110,
         "book": "DraftKings", "team": "BUF", "opponent": "LAC"}],
        "game_bets": [{"bet_type": "spread", "market": "spread", "team": "LAC", "line": -6.5, "odds": -110,
                       "book": "DraftKings", "home": "BUF", "away": "LAC"}]}
    B.stamp(board, "recommendations.json", env={}, cache_dir=tmp)
    a, b = board["recommendations"]
    assert a["bet_link_kind"] == "page", "250.5 is not on the book's slip: the game, not the 249.5"
    assert b["bet_link"] == DK + "allen-u"
    assert board["game_bets"][0]["bet_link_kind"] == "page", "LAC -6.5 is not LAC +6.5"


def test_the_switch_and_the_boards_it_touches():
    tmp = Path(tempfile.mkdtemp())
    _banked(tmp)
    board = _board()
    assert B.stamp(board, "recommendations.json", env={"QB_BET_LINKS": "0"}, cache_dir=tmp) == 0
    assert B.stamp(board, "record.json", env={}, cache_dir=tmp) == 0
    assert B.stamp(board, "nba.json", env={}, cache_dir=tmp) == 0, "the NFL's links never land on the NBA board"
    assert "bet_link" not in json.dumps(board)


def test_the_paywall_strips_the_link_with_the_pick():
    from engine import gate
    tmp = Path(tempfile.mkdtemp())
    _banked(tmp)
    board = _board()
    board["games"] = [{"home": "BUF", "away": "LAC"}]
    B.stamp(board, "recommendations.json", env={}, cache_dir=tmp)
    keep = os.environ.get(gate.ENV_ENABLED)
    os.environ[gate.ENV_ENABLED] = "1"
    try:
        public = gate.redact(board, "recommendations.json")
    finally:
        if keep is None:
            os.environ.pop(gate.ENV_ENABLED, None)
        else:
            os.environ[gate.ENV_ENABLED] = keep
    assert "bet_link" not in json.dumps(public) and public.get("games")


def test_the_odds_request_asks_for_links_and_banks_them():
    src = (ROOT / "engine" / "sources" / "oddsapi.py").read_text()
    assert src.count("_ask_for_links(params)") == 2, "both the board pull and the event pull"
    i = src.index('if "includeLinks=true" in url:')
    assert src.index("betlinks.bank(body, cache_name, cache_dir=CACHE_DIR)") < src.index("path.write_text(body)", i)
    fut = src[src.index("def fetch_outrights"):src.index("def parse_outrights")]
    assert "_ask_for_links" not in fut, "the futures request stays one market, one region, nothing else"
    gate_src = (ROOT / "engine" / "gate.py").read_text()
    pub = gate_src[gate_src.index("def publish("):gate_src.index("def served_sidecar")]
    assert pub.index("betlinks.stamp(payload, label)") < pub.index("would_downgrade(payload, full, label)")
    from engine.maintenance import PRUNABLE_CACHE_PREFIXES
    assert "betlinks_" in PRUNABLE_CACHE_PREFIXES


def test_the_page_draws_the_button_safely_where_the_picks_are():
    js = (ROOT / "web" / "js" / "app.js").read_text()
    fn = js[js.index("function betItHTML("):js.index("function escapeHtml(")]
    assert 'href="${safeHref(url)}"' in fn and 'rel="noopener noreferrer nofollow"' in fn and 'target="_blank"' in fn
    assert "1-800-GAMBLER" in fn and "bet_links" in fn and "bet_pages" in fn, "every book, not one"
    assert 'window.addEventListener("click"' in fn and "stopPropagation" in fn, "a tap in the box never opens the card"
    assert js.count('betItHTML(r, "mini")') >= 4, "props cards, game-line cards, Edge rows, Most Likely cards"
    for where in ('betItHTML(lk || r, "btn primary")',          # the pick page
                  '${obPriceHTML(r)}${betItHTML(r, "mini")}',     # Most Likely cards
                  'betItHTML(pick, "btn primary hd-betit")'):    # the Pick of the Day
        assert where in js, where
    edge = js[js.index("function edgeRowHTML("):js.index("function propsViewMode(")]
    assert 'betItHTML(r, "mini")' in edge
    assert js.count("bet_link: r.bet_link") + js.count("bet_link: b.bet_link") == 2


def test_the_discord_page_shows_what_the_site_posts_and_nothing_private():
    js = (ROOT / "web" / "js" / "app.js").read_text()
    page = js[js.index("const DISCORD_FEED"):js.index("function dcFirstStop(")]
    assert 'boardFetch("data/community.json"' in js
    for ch in ("record", "picks", "anchors"):
        assert f'["{ch}",' in page
    assert "${dcFeedHTML(feed)}" in page and "webhook" not in page.split("*/", 1)[1].lower()
    assert '["The Discord",' in js and '"discord"]' in js


def test_the_feed_writes_only_the_public_posts_for_the_page():
    import datetime as dt
    from engine import discordfeed as D
    from engine import ledger
    d = Path(tempfile.mkdtemp())
    conn = ledger.connect(d / "ledger.db")
    conn.execute("INSERT INTO bets (ts, sport, date, player, market, side, line, book, odds, hit_prob, status, "
                 "pnl_units, category, game_day) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 ("2026-10-12T12:00:00", "nfl", "2026-10-12", "Josh Allen", "pass_yds", "OVER", 249.5,
                  "DraftKings", -110, 0.62, "won", 0.91, "likely_live", "2026-10-12"))
    conn.commit()
    env = {"QB_DISCORD_RECORD_WEBHOOK": "https://discord.test/api/webhooks/1/SECRET-RECORD",
           "QB_DISCORD_PICKS_WEBHOOK": "https://discord.test/api/webhooks/2/SECRET-PICKS",
           "QB_DISCORD_SPORTS": "nfl"}
    sent = []
    now = dt.datetime(2026, 10, 13, 15, 0, tzinfo=dt.timezone.utc)
    board = {"games": [{"home": "BUF", "away": "LAC", "date": "2026-10-13"}],
             "pick_of_the_day": {"date": "2026-10-13", "pick": {"player": "Josh Allen", "market": "pass_yds",
                                 "side": "OVER", "line": 249.5, "odds": -110}, "verdict": {"bet": True}}}
    D.run(conn, now, env=env, boards={"nfl": board}, post_fn=lambda u, t: sent.append(u) or True,
          state_path=d / "s.json", community_path=d / "community.json")
    out = json.loads((d / "community.json").read_text())
    text = json.dumps(out)
    assert "SECRET" not in text and "discord.test" not in text, "never a webhook URL"
    assert out["channels"] == {"record": True, "picks": True, "anchors": False}
    kinds = [p["kind"] for p in out["posts"]]
    assert "record" in kinds and "potd" not in kinds and "board" not in kinds, "#picks stays in #picks"
    assert "Pick of the Day" not in text
    # A run with its own state and no community path writes no site copy at all.
    d2 = Path(tempfile.mkdtemp())
    before = D.COMMUNITY.stat().st_mtime if D.COMMUNITY.exists() else None
    D.run(conn, now, env=env, boards={}, post_fn=lambda u, t: True, state_path=d2 / "s.json")
    assert not (d2 / "community.json").exists()
    assert (D.COMMUNITY.stat().st_mtime if D.COMMUNITY.exists() else None) == before, "the site's copy untouched"


def test_the_props_report_tells_game_lines_from_player_props():
    """Ethan's first run banked 29 games × 6 game-line links and no prop;
    --props counts only the player-prop keys, and names the books."""
    tmp = Path(tempfile.mkdtemp())
    (tmp / "betlinks_event_nfl_e1_x.json").write_text(json.dumps({"sport": "nfl", "events": {"e1": {"slip": {
        "fanduel|player_reception_yds|amon ra st brown|over|64.5": "https://a",
        "draftkings|h2h|detroit lions||": "https://b"}, "page": {}}}}))
    lines = B.props_report("nfl", cache_dir=tmp)
    assert "1 per-game link file" in lines[0] and "0 per-game odds file" in lines[0]
    assert lines[1].strip() == "player-prop slip links banked: 1 at fanduel"
    empty = B.props_report("nfl", cache_dir=Path(tempfile.mkdtemp()))
    assert "newest none" in empty[0] and empty[1].strip() == "player-prop slip links banked: 0"


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
