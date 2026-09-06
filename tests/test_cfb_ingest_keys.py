"""Two feeds on one mirror name the same college game two ways.

`ab20781` rekeyed a college game row to away@home so `engine.ledger`
could look a college total up like every other sport's — three thousand
rows had been sitting open for ever. Real fix. But every OTHER file on
the sportsdataverse mirror still keys by the numeric ESPN id:

    schedule row after ab20781 : espn:52@espn:59
    player_stats_2024.csv      : 401628319
    cfb_line_odds.csv.gz       : 401628319

`cfbstats.parse_player_stats` and `cfblines.parse_lines` both look the
CSV's numeric id up in a games map built from the stored key, so both
joined ZERO rows — silently, because a parser that cannot find a game
counts a skip and moves on. Measured on the real 2023 mirror files:
player stats 0 of 182,694 joined, closing lines 0 of 1,183,529.

`cfbfastr._extra` keeps the numeric id (that parser is the only place
that still sees both names) and the two games maps alias under both.

THERE ARE TWO MAPS OVER THE SAME TABLE and that is the trap: fixing
`cfb_games_for` alone left `ingest_cfb_lines` — which builds its own —
still joining nothing. This pins both, by name, so a third map cannot be
added without one of these failing.

Run directly: `python3 tests/test_cfb_ingest_keys.py`
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db, ingest                                   # noqa: E402
from engine.sources import cfbfastr                             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ESPN_ID = "401628319"
STORED = "espn:52@espn:59"


def _row(**kw):
    d = {"sport": "cfb", "season": 2024, "period": "2024-09-07",
         "game_id": STORED, "home": "espn:59", "away": "espn:52",
         "home_score": 31, "away_score": 24,
         "extra": json.dumps({"home_name": "Home", "away_name": "Away",
                              "espn_game_id": ESPN_ID})}
    d.update(kw)
    return d


def _conn():
    conn = db.connect(":memory:")
    db.upsert_games(conn, [_row()])
    return conn


def test_the_schedule_parser_keeps_the_numeric_id_it_stops_storing():
    """It is the only place that still sees both names."""
    src = open(os.path.join(ROOT, "engine", "sources", "cfbfastr.py"),
               encoding="utf-8").read()
    assert "espn_game_id" in src, "the numeric id is dropped again"
    at = src.index("def _extra(")
    body = src[at:src.index("\ndef ", at + 10)]
    assert "espn_game_id" in body, "kept somewhere other than the row's extra"


def test_the_player_stats_map_resolves_both_names():
    """engine.sources.cfbstats looks up 401628319; the row is stored as
    espn:52@espn:59. Both must reach the SAME game."""
    games = ingest.cfb_games_for(_conn(), 2024)
    assert STORED in games, "the stored key stopped resolving"
    assert ESPN_ID in games, "the mirror's own id joins nothing"
    assert games[STORED] is games[ESPN_ID], "two names, two different games"


def test_the_closing_lines_map_resolves_both_names_too():
    """A SECOND map over the same table, in ingest_cfb_lines. Fixing only
    cfb_games_for left this one joining zero rows."""
    src = open(os.path.join(ROOT, "engine", "ingest.py"), encoding="utf-8").read()
    at = src.index("def ingest_cfb_lines(")
    # It is the last function in the module, so there may be no next def.
    nxt = src.find("\ndef ", at + 10)
    body = src[at:nxt if nxt != -1 else len(src)]
    assert "espn_game_id" in body, \
        "ingest_cfb_lines builds its own games map and still keys it one way"
    assert body.count("games[") >= 2, "only one key is written"


def test_a_game_with_no_numeric_id_still_stores_under_its_own_key():
    """The alias is additive. A row whose extra carries no espn id — an
    older backfill — must not vanish from the map."""
    conn = db.connect(":memory:")
    db.upsert_games(conn, [_row(game_id="espn:1@espn:2",
                                extra=json.dumps({"home_name": "H"}))])
    games = ingest.cfb_games_for(conn, 2024)
    assert "espn:1@espn:2" in games and len(games) == 1


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
