"""Multi-market game logs for the Players page (engine/statlogs.py).

Ethan, 2026-08-17: "when i search an nfl player it will only display yard
props with that chart, but i also wanna be able to maybe see reception
props … and same for mlb, i wanna see more then just bases prop chart."

Everything here runs against ITS OWN temp database — never
data/history.db. The module's whole contract is machine-dependent on
purpose (a fresh clone builds an empty section, the droplet fills it),
which is exactly why a test that read the real DB would measure the
machine and not the code.

Run directly: `python3 tests/test_statlogs.py`
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db as _db
from engine import statlogs
from engine.models import MARKET_LABELS


def _fixture():
    """A temp history DB with two NFL players across several markets."""
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "hist.db")
    conn = _db.connect(path)
    rows = []
    # A back with 12 weeks of rushing + receiving work: enough for the
    # N_GAMES cap to bite, spread over two seasons so ordering is tested
    # where it can actually break (season first, then zero-padded week).
    for wk in range(1, 13):
        season = 2025 if wk > 4 else 2026
        rows.append(dict(sport="nfl", season=season, period=f"{wk:03d}",
                         game_id=f"G{season}{wk}", player="Test Back",
                         team="GB", opponent="CHI", position="RB", home=wk % 2,
                         market="rush_yds", value=60 + wk))
        rows.append(dict(sport="nfl", season=season, period=f"{wk:03d}",
                         game_id=f"G{season}{wk}", player="Test Back",
                         team="GB", opponent="CHI", position="RB", home=wk % 2,
                         market="receptions", value=wk % 5))
    # Two games only — under MIN_GAMES, must be dropped, because a
    # two-bar chart is an anecdote wearing chart clothes.
    for wk in (1, 2):
        rows.append(dict(sport="nfl", season=2026, period=f"{wk:03d}",
                         game_id=f"T{wk}", player="Thin Sample", team="DET",
                         opponent="MIN", position="WR", home=1,
                         market="rec_yds", value=40 + wk))
    _db.upsert_player_logs(conn, rows)
    conn.commit()
    conn.close()
    return path


def test_a_missing_db_yields_an_empty_section_not_an_error():
    """The honest-degradation half of the contract: CI and fresh clones
    build boards; they just build them without the extra markets."""
    recs = [{"player": "Anyone"}]
    out = statlogs.for_board(recs, "nfl", db_path="/nowhere/at/all.db")
    assert out == {}


def test_every_ingested_market_ships_for_a_board_player():
    path = _fixture()
    out = statlogs.for_board([{"player": "Test Back"}], "nfl", db_path=path)
    per = out["Test Back"]
    assert set(per) == {"Rushing Yards", "Receptions"}
    # Capped at N_GAMES, newest first: season 2026 weeks 4..1 lead, then
    # 2025 weeks 12..7 — twelve games ingested, ten shipped.
    rush = per["Rushing Yards"]
    assert len(rush) == statlogs.N_GAMES
    assert rush[0]["week"] == 4 and rush[1]["week"] == 3
    assert all(isinstance(g["week"], int) for g in rush)
    assert all(set(g) == {"opponent", "home", "value", "week"} for g in rush)


def test_two_games_is_an_anecdote_and_ships_nothing():
    path = _fixture()
    out = statlogs.for_board([{"player": "Thin Sample"}], "nfl", db_path=path)
    assert out == {}, "a 2-game series must not become a chart"


def test_only_board_players_are_queried():
    """The section is for tonight's players — shipping the whole league
    would be megabytes of JSON nobody asked for."""
    path = _fixture()
    out = statlogs.for_board([{"player": "Somebody Else"}], "nfl", db_path=path)
    assert out == {}


def test_the_anytime_td_label_matches_the_priced_market():
    """The Players page dedupes chips BY LABEL: the priced market's chip
    wins and the history chip yields. That only works while this module
    spells anytime_td exactly as MARKET_LABELS does — a drift here puts
    the same stat on two chips."""
    labels = dict(statlogs.SPORT_MARKETS["nfl"])
    assert labels["anytime_td"] == MARKET_LABELS["anytime_td"]


def test_display_order_is_decided_by_the_module_not_the_query():
    """JSON keeps insertion order and the page renders chips in payload
    order — so the order must be SPORT_MARKETS order, not whatever the
    GROUP BY happened to return."""
    path = _fixture()
    out = statlogs.for_board([{"player": "Test Back"}], "nfl", db_path=path)
    assert list(out["Test Back"]) == ["Rushing Yards", "Receptions"]


def test_both_pipelines_attach_the_section():
    """Presence of the KEY is asserted — never its content, which is a
    property of the machine's ingest, not of this code."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "engine", "pipeline.py"),
        encoding="utf-8").read()
    assert '"player_stats": statlogs.for_board(results, "nfl")' in src
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "engine", "mlb", "pipeline.py"),
        encoding="utf-8").read()
    assert '"player_stats": statlogs.for_board(results, "mlb")' in src


# --- the league-wide search (2026-08-18) -------------------------------------
# Ethan: "The search page for players isn't working still. You should be
# able too look up any player in the league too that specific sport." The
# board knows tonight's priced players; these two functions know everyone
# who has ever appeared in an ingested game.
def test_search_finds_any_logged_player_by_substring():
    path = _fixture()
    hits = statlogs.search("nfl", "test ba", db_path=path)
    assert [h["player"] for h in hits] == ["Test Back"]
    assert hits[0]["team"] == "GB" and hits[0]["position"] == "RB"
    assert hits[0]["games"] == 12
    assert hits[0]["headshot"] == "", \
        "no stored face must read as empty, never crash"


def test_search_carries_the_stored_face():
    """Ethan, 2026-08-18: "Make sure all spots have head shots." The
    ingest stores faces in player_assets, in the same DB the search
    reads — a result without the photo is the gap he keeps noticing."""
    path = _fixture()
    conn = _db.connect(path)
    conn.execute("INSERT INTO player_assets (sport, player, espn_id, "
                 "headshot, seen) VALUES ('nfl', 'Test Back', '1', "
                 "'https://cdn/face.png', '2026-08-18')")
    conn.commit(); conn.close()
    hits = statlogs.search("nfl", "test back", db_path=path)
    assert hits[0]["headshot"] == "https://cdn/face.png"


def test_search_ranks_the_current_player_over_the_stale_namesake():
    """Two men named alike, one active this season, one gone since 2025 —
    a deadline pickup is exactly when someone gets looked up, so the
    recent man must lead."""
    path = _fixture()
    conn = _db.connect(path)
    _db.upsert_player_logs(conn, [dict(
        sport="nfl", season=2024, period="010", game_id=f"OLD{i}",
        player="Test Backman", team="NYJ", opponent="NE", position="RB",
        home=1, market="rush_yds", value=30) for i in range(20)])
    conn.commit(); conn.close()
    hits = statlogs.search("nfl", "test back", db_path=path)
    assert hits[0]["player"] == "Test Back", \
        "20 stale games outranked 12 current ones"


def test_search_is_scoped_to_the_sport_asked_about():
    path = _fixture()
    assert statlogs.search("mlb", "test ba", db_path=path) == []


def test_search_degrades_to_empty_without_a_db():
    assert statlogs.search("nfl", "anyone", db_path="/no/such/file.db") == []
    assert statlogs.for_player("nfl", "Anyone",
                               db_path="/no/such/file.db") == {}


def test_for_player_ships_the_boards_own_shape():
    """The page draws a searched-up player with the same card a priced
    star gets, so the shape must be for_board's exactly: label-keyed,
    newest first, thin samples dropped."""
    path = _fixture()
    st = statlogs.for_player("nfl", "Test Back", db_path=path)
    assert set(st) == {"Rushing Yards", "Receptions"}
    board = statlogs.for_board([{"player": "Test Back"}], "nfl",
                               db_path=path)
    assert st == board["Test Back"]
    assert statlogs.for_player("nfl", "Thin Sample", db_path=path) == {}


def test_hoops_is_in_the_market_table_with_the_pipelines_labels():
    """NBA/WNBA joined for the search. Labels must match
    engine/nba/pipeline.MARKET_LABELS — the page dedupes chips BY LABEL,
    the same argument the anytime_td comment already carries."""
    from engine.nba.pipeline import MARKET_LABELS as NBA_LABELS
    for sport in ("nba", "wnba"):
        for mid, label in statlogs.SPORT_MARKETS[sport]:
            assert NBA_LABELS.get(mid) == label, (sport, mid)


def test_the_server_serves_both_and_gates_neither():
    """Game logs are FACTS on the free footing of rosters and injuries —
    the module header carries the argument. The two routes must exist and
    must not pass through the subscription check the boards use."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "server.py"), encoding="utf-8").read()
    assert '"/api/players/search"' in src and '"/api/players/logs"' in src
    for fn in ("_players_search", "_players_logs"):
        i = src.index(f"def {fn}(")
        body = src[i:src.index("\n    def ", i + 10)]
        assert "statlogs" in body
        assert "_entitled" not in body, f"{fn} grew a paywall"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
