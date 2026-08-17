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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
