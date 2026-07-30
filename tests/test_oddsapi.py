"""Tests for the Odds API adapter. Network is stubbed with a fixture payload
shaped like a real The Odds API v4 event-odds response."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.sources import oddsapi as oa
from engine.models import (
    Team, DefenseProfile, Weather, Game, Prop, GameLog, SportsbookLine,
    PASS_YDS, REC_YDS,
)
from engine.data_loader import Slate


# A representative event-odds payload (two books, two markets, over/under each).
EVENT = {
    "id": "evt123",
    "home_team": "Kansas City Chiefs",
    "away_team": "Buffalo Bills",
    "bookmakers": [
        {
            "key": "draftkings", "title": "DraftKings",
            "markets": [
                {"key": "player_pass_yds", "outcomes": [
                    {"name": "Over", "description": "Josh Allen", "price": -115, "point": 258.5},
                    {"name": "Under", "description": "Josh Allen", "price": -105, "point": 258.5},
                ]},
                {"key": "player_reception_yds", "outcomes": [
                    {"name": "Over", "description": "Amon-Ra St. Brown", "price": -110, "point": 79.5},
                    {"name": "Under", "description": "Amon-Ra St. Brown", "price": -110, "point": 79.5},
                ]},
                {"key": "h2h", "outcomes": [
                    {"name": "Kansas City Chiefs", "price": -150},
                    {"name": "Buffalo Bills", "price": 130},
                ]},
            ],
        },
        {
            "key": "fanduel", "title": "FanDuel",
            "markets": [
                {"key": "player_pass_yds", "outcomes": [
                    {"name": "Over", "description": "Josh Allen", "price": -108, "point": 257.5},
                    {"name": "Under", "description": "Josh Allen", "price": -112, "point": 257.5},
                ]},
                {"key": "h2h", "outcomes": [
                    {"name": "Kansas City Chiefs", "price": -145},
                    {"name": "Buffalo Bills", "price": 135},
                ]},
                {"key": "totals", "outcomes": [
                    {"name": "Over", "price": -108, "point": 47.5},
                    {"name": "Under", "price": -112, "point": 47.5},
                ]},
                {"key": "spreads", "outcomes": [
                    {"name": "Kansas City Chiefs", "price": -110, "point": -2.5},
                    {"name": "Buffalo Bills", "price": -110, "point": 2.5},
                ]},
            ],
        },
    ],
}


def test_normalize_name():
    assert oa.normalize_name("Amon-Ra St. Brown") == "amon ra st brown"
    assert oa.normalize_name("Michael Pittman Jr.") == "michael pittman"
    assert oa.normalize_name("Patrick Mahomes") == "patrick mahomes"
    # Accent folding: the MLB feed uses diacritics and odds feeds often don't;
    # without this every Acuña / Ramírez fails the backtest join.
    assert oa.normalize_name("Ronald Acuña Jr.") == oa.normalize_name("Ronald Acuna Jr")
    assert oa.normalize_name("José Ramírez") == "jose ramirez"


def test_parse_event_lines_pairs_and_maps():
    idx = oa.parse_event_lines(EVENT)
    allen = idx[(oa.normalize_name("Josh Allen"), PASS_YDS)]
    # Two books quoted Allen passing yards.
    books = {l.book for l in allen}
    assert books == {"DraftKings", "FanDuel"}
    dk = next(l for l in allen if l.book == "DraftKings")
    assert dk.line == 258.5 and dk.over_odds == -115 and dk.under_odds == -105
    # Receiving market maps + normalizes the hyphenated name.
    assert (oa.normalize_name("Amon-Ra St. Brown"), REC_YDS) in idx


def test_parse_event_players_lists_the_menu():
    """The book's menu is a roster source: every priced player, with the
    display name preserved for building props."""
    menu = oa.parse_event_players(EVENT)
    assert menu[(oa.normalize_name("Josh Allen"), PASS_YDS)] == "Josh Allen"
    assert menu[(oa.normalize_name("Amon-Ra St. Brown"), REC_YDS)] == "Amon-Ra St. Brown"
    # Game markets (h2h/totals/spreads) never produce "players".
    assert all(m in (PASS_YDS, REC_YDS) for _, m in menu)


def test_book_menu_props_built_from_real_lines_and_own_logs():
    """A book-priced player with no slate prop gets one built from the
    books' REAL lines + his own ingested logs — held from recommendation
    (spot 0) until the lineup confirms."""
    from engine import db
    from engine.mlb.bookmenu import add_book_listed_props
    from engine.mlb.models import MLBGame, TOTAL_BASES
    from engine.mlb.data_loader import MLBSlate

    conn = db.connect(":memory:")
    logs = [{"sport": "mlb", "season": 2026, "period": f"2026-07-{d:02d}",
             "game_id": f"MG-{d}", "player": "Menu Guy", "team": "NYY",
             "opponent": "BOS", "position": "RF", "home": 1,
             "market": "total_bases", "value": float(d % 3)}
            for d in range(1, 11)]
    db.upsert_player_logs(conn, logs)

    game = MLBGame(home="NYY", away="TOR", park="yankee",
                   lineups_confirmed=False)
    slate = MLBSlate(date="2026-07-26", games=[game], props=[])
    book_only = [
        {"player": "Menu Guy", "market": TOTAL_BASES, "home": "NYY",
         "away": "TOR",
         "lines": [SportsbookLine("DraftKings", 1.5, -115, -105)]},
        {"player": "No History", "market": TOTAL_BASES, "home": "NYY",
         "away": "TOR", "lines": [SportsbookLine("FanDuel", 1.5, -110, -110)]},
        {"player": "Menu Guy", "market": "strikeouts", "home": "NYY",
         "away": "TOR", "lines": [SportsbookLine("FanDuel", 5.5, -110, -110)]},
    ]
    assert add_book_listed_props(slate, book_only, conn) == 1

    p = slate.props[0]
    assert p.player == "Menu Guy" and p.team == "NYY" and p.opponent == "TOR"
    assert p.lines[0].book == "DraftKings" and p.lines[0].line == 1.5
    assert p.lineup_spot == 0                      # held until the card posts
    # Logs are newest-first with real dates, like a live game log.
    assert p.logs[0].date == "2026-07-10" and p.logs[-1].date == "2026-07-01"
    assert len(p.logs) == 10
    # Running it again adds nothing (already on the slate).
    assert add_book_listed_props(slate, book_only, conn) == 0


def test_parse_event_h2h_takes_best_price():
    best = oa.parse_event_h2h(EVENT, oa.TEAM_ABBR)
    # Best (highest) American price per side across the two books.
    assert best["KC"] == -145      # max(-150, -145)
    assert best["BUF"] == 135      # max(130, 135)


def test_parse_event_totals_and_spreads():
    tot = oa.parse_event_totals(EVENT)
    assert tot == (47.5, -108, -112)          # line, best over, best under
    sp = oa.parse_event_spreads(EVENT, oa.TEAM_ABBR, "KC", "BUF")
    assert sp == (-2.5, -110, -110)           # home spread, home odds, away odds


def test_parse_ignores_unknown_markets():
    ev = {"bookmakers": [{"key": "dk", "markets": [
        {"key": "player_anytime_td", "outcomes": [
            {"name": "Yes", "description": "X", "price": 120, "point": None}]}]}]}
    assert oa.parse_event_lines(ev) == {}


def _mini_slate():
    teams = {
        "KC": Team("KC", "KC", DefenseProfile("KC")),
        "BUF": Team("BUF", "BUF", DefenseProfile("BUF")),
    }
    game = Game(home="KC", away="BUF", weather=Weather(dome=False), spread=-2.5, total=47.0)
    logs = [GameLog(week=w, opponent="X", value=260) for w in range(1, 6)]
    prop = Prop(
        player="Josh Allen", team="BUF", opponent="KC", position="QB",
        market=PASS_YDS, logs=logs, career_avg=255, vs_opponent_avg=None,
        lines=[SportsbookLine(book="proxy", line=250.0)], usage_role="starter",
    )
    return Slate(date="2024-W05", teams=teams, games=[game], props=[prop])


def test_apply_odds_replaces_proxy(monkeypatch):
    monkeypatch.setattr(oa, "list_events", lambda key, ttl=300, sport='nfl', cache_only=False: [
        {"id": "evt123", "home_team": "Kansas City Chiefs", "away_team": "Buffalo Bills"}
    ])
    monkeypatch.setattr(oa, "fetch_event_odds",
                        lambda eid, key, markets=None, books=None, ttl=300, sport='nfl', cache_only=False: (EVENT, oa.Quota("491", "9")))

    slate = _mini_slate()
    res = oa.apply_odds_to_slate(slate, api_key="testkey")
    assert res.matched == 1 and res.events_used == 1
    prop = slate.props[0]
    # Proxy line gone; real book lines attached.
    assert all(l.book != "proxy" for l in prop.lines)
    assert {l.book for l in prop.lines} == {"DraftKings", "FanDuel"}

    # And the model now shops the best (lowest) real line.
    from engine.odds import best_over_line
    assert best_over_line(prop.lines).line == 257.5  # FanDuel

    # Real moneylines were attached to the game from the same payload.
    assert res.moneylines == 1
    assert slate.games[0].home_ml == -145 and slate.games[0].away_ml == 135
    # Total and spread prices came in on the same request.
    assert slate.games[0].total == 47.5
    assert slate.games[0].spread == -2.5


def test_mlb_market_mapping_and_parse():
    # An MLB event payload uses batter_/pitcher_ market keys.
    ev = {"bookmakers": [
        {"key": "draftkings", "title": "DraftKings", "markets": [
            {"key": "batter_total_bases", "outcomes": [
                {"name": "Over", "description": "Aaron Judge", "price": -120, "point": 1.5},
                {"name": "Under", "description": "Aaron Judge", "price": 100, "point": 1.5}]},
            {"key": "pitcher_strikeouts", "outcomes": [
                {"name": "Over", "description": "Zack Wheeler", "price": -115, "point": 7.5},
                {"name": "Under", "description": "Zack Wheeler", "price": -105, "point": 7.5}]},
        ]}]}
    idx = oa.parse_event_lines(ev, oa.MLB_ODDS_TO_MARKET)
    assert (oa.normalize_name("Aaron Judge"), "total_bases") in idx
    assert (oa.normalize_name("Zack Wheeler"), "strikeouts") in idx
    tb = idx[(oa.normalize_name("Aaron Judge"), "total_bases")][0]
    assert tb.line == 1.5 and tb.over_odds == -120 and tb.under_odds == 100
    # NFL market keys are ignored under the MLB map.
    assert oa.parse_event_lines({"bookmakers": [{"key": "dk", "markets": [
        {"key": "player_pass_yds", "outcomes": []}]}]}, oa.MLB_ODDS_TO_MARKET) == {}


def test_mlb_apply_odds_end_to_end(monkeypatch):
    from engine.mlb.models import MLBGame, MLBProp, MLBGameLog
    from engine.mlb.data_loader import MLBSlate
    ev = {"bookmakers": [{"key": "fanduel", "title": "FanDuel", "markets": [
        {"key": "batter_total_bases", "outcomes": [
            {"name": "Over", "description": "Aaron Judge", "price": -125, "point": 2.5},
            {"name": "Under", "description": "Aaron Judge", "price": 105, "point": 2.5}]}]}]}
    monkeypatch.setattr(oa, "list_events", lambda key, ttl=300, sport="nfl", cache_only=False: [
        {"id": "e1", "home_team": "Colorado Rockies", "away_team": "New York Yankees"}])
    monkeypatch.setattr(oa, "fetch_event_odds",
                        lambda eid, key, markets=None, books=None, ttl=300, sport="nfl", cache_only=False: (ev, oa.Quota()))

    game = MLBGame(home="COL", away="NYY", park="coors")
    prop = MLBProp("Aaron Judge", "NYY", "COL", "RF", "total_bases",
                   [MLBGameLog(i, "X", 2) for i in range(1, 6)], 2.1, None,
                   [SportsbookLine("proxy", 2.0)], bats="R", lineup_spot=2)
    slate = MLBSlate(date="2024-06-20", games=[game], props=[prop])
    res = oa.apply_odds_to_slate(slate, api_key="k", sport="mlb")
    assert res.matched == 1
    assert prop.lines[0].book == "FanDuel" and prop.lines[0].line == 2.5


def test_cache_only_serves_stale_cache_and_never_hits_network(monkeypatch):
    """The zero-spend path: between budgeted pulls, refresh cycles must reuse
    the last paid pull's cached prices instead of overwriting the site with
    proxy lines (the bug that kept the board unpriced 18 cycles out of 19)."""
    import json as _json
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        monkeypatch.setattr(oa, "CACHE_DIR", Path(td))
        # No cache yet -> cache_only refuses (never touches the network:
        # the URL is junk on purpose).
        try:
            oa._request("http://junk.invalid/x", "c.json", cache_only=True)
            assert False, "expected OddsAPIError with an empty cache"
        except oa.OddsAPIError:
            pass
        # A stale cached copy (older than any ttl) is served as-is.
        (Path(td) / "c.json").write_text(_json.dumps({"ok": 1}))
        import os as _os
        old = 1_000_000_000                     # far in the past
        _os.utime(Path(td) / "c.json", (old, old))
        data, quota = oa._request("http://junk.invalid/x", "c.json",
                                  ttl=1, cache_only=True)
        assert data == {"ok": 1}


def test_apply_odds_cache_only_skips_unpaid_events(monkeypatch):
    monkeypatch.setattr(oa, "list_events", lambda key, ttl=300, sport='nfl', cache_only=False: [
        {"id": "evt123", "home_team": "Kansas City Chiefs", "away_team": "Buffalo Bills"}
    ])

    def fake_fetch(eid, key, markets=None, books=None, ttl=300, sport='nfl',
                   cache_only=False):
        raise oa.OddsAPIError("no cached odds yet")
    monkeypatch.setattr(oa, "fetch_event_odds", fake_fetch)

    slate = _mini_slate()
    res = oa.apply_odds_to_slate(slate, api_key="k", cache_only=True)
    # Nothing cached -> nothing attached, nothing raised, nothing spent.
    assert res.matched == 0 and res.from_cache is True
    assert slate.props[0].lines[0].book == "proxy"


def test_apply_odds_reports_unmatched(monkeypatch):
    monkeypatch.setattr(oa, "list_events", lambda key, ttl=300, sport='nfl', cache_only=False: [
        {"id": "evt123", "home_team": "Kansas City Chiefs", "away_team": "Buffalo Bills"}
    ])
    monkeypatch.setattr(oa, "fetch_event_odds",
                        lambda eid, key, markets=None, books=None, ttl=300, sport='nfl', cache_only=False: ({"bookmakers": []}, oa.Quota()))
    slate = _mini_slate()
    res = oa.apply_odds_to_slate(slate, api_key="testkey")
    assert res.matched == 0 and res.unmatched


def test_resolve_market_keys_translates_engine_names():
    """Historical credits scale with markets requested, so the harvester lets
    you name just the market being backtested — in either naming scheme."""
    from engine.sources.oddshistory import resolve_market_keys
    assert resolve_market_keys("mlb", ["total_bases", "h2h"]) == \
        ["batter_total_bases", "h2h"]
    # API keys pass through; whitespace and empties are dropped.
    assert resolve_market_keys("mlb", ["batter_home_runs", " hits ", ""]) == \
        ["batter_home_runs", "batter_hits"]
    assert resolve_market_keys("nfl", ["rec_yds"]) == ["player_reception_yds"]


def test_one_sided_markets_never_fabricate_the_missing_side():
    """Home-run markets are quoted Over-only. Inventing an under at -110
    manufactured +88% EV "bets" nobody can place — the missing side must be
    stored as 0 (not offered) and never picked."""
    ev = {"bookmakers": [{"key": "draftkings", "title": "DraftKings", "markets": [
        {"key": "batter_home_runs", "outcomes": [
            {"name": "Over", "description": "Big Bopper", "price": 320, "point": 0.5}]}]}]}
    idx = oa.parse_event_lines(ev, oa.MLB_ODDS_TO_MARKET)
    ln = idx[(oa.normalize_name("Big Bopper"), "home_runs")][0]
    assert ln.over_odds == 320 and ln.under_odds == 0

    # De-vig degrades gracefully: fair prob from the quoted side + assumed hold.
    from engine.odds import devig_two_way, american_to_prob
    fair_over, fair_under = devig_two_way(320, 0)
    assert fair_over < american_to_prob(320)      # hold removed, not added
    assert abs(fair_over + fair_under - 1.0) < 1e-9

    # And side selection can only take the side that exists.
    from engine.betting import pick_side
    side, best, win, fair, edge = pick_side([ln], lambda line: 0.30)
    assert side == "OVER" and best.odds == 320



def test_name_near_misses_catch_prices_we_paid_for():
    """The dangerous half of "no real book price": a book line and a slate
    prop that are obviously the same player but whose keys didn't join.
    Those are paid-for prices being thrown away — they must be reported,
    while genuinely unoffered markets stay quiet."""
    from types import SimpleNamespace as NS
    from engine.sources.oddsapi import _name_near_misses, normalize_name

    slate = NS(props=[
        NS(player="Michael Harris II", market="total_bases"),   # book: M. Harris
        NS(player="Jackson Chourio", market="hits"),            # book: J. Chourio
        NS(player="Bench Guy", market="total_bases"),           # truly unoffered
        NS(player="Exact Match", market="hits"),
    ])
    menu = {
        (normalize_name("M Harris"), "total_bases"):
            {"player": "M Harris", "home": "ATL", "away": "NYM"},
        (normalize_name("J Chourio"), "hits"):
            {"player": "J Chourio", "home": "MIL", "away": "CHC"},
        (normalize_name("Exact Match"), "hits"):
            {"player": "Exact Match", "home": "LAD", "away": "SD"},
        (normalize_name("Someone Else"), "hits"):
            {"player": "Someone Else", "home": "LAD", "away": "SD"},
    }
    matched = {(normalize_name("Exact Match"), "hits")}
    misses = _name_near_misses(slate, menu, matched)
    got = {(m["prop"], m["book"]) for m in misses}
    assert got == {("Michael Harris II", "M Harris"),
                   ("Jackson Chourio", "J Chourio")}
    # A prop the books never offered is NOT a near miss — silence is right.
    assert all(m["prop"] != "Bench Guy" for m in misses)
    # An exactly-matched prop never reports as a miss.
    assert all(m["prop"] != "Exact Match" for m in misses)


if __name__ == "__main__":
    class MP:
        def __init__(self): self._undo = []
        def setattr(self, obj, name, val):
            self._undo.append((obj, name, getattr(obj, name))); setattr(obj, name, val)
        def undo(self):
            for obj, name, val in reversed(self._undo): setattr(obj, name, val)

    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        needs_mp = fn.__code__.co_argcount == 1
        mp = MP() if needs_mp else None
        try:
            fn(mp) if needs_mp else fn()
            print(f"  ok  {name}")
        finally:
            if mp: mp.undo()
    print(f"\n{len(fns)} tests passed.")
