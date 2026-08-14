"""Preseason gets ingested — into its own table, priced by nothing.

Ethan, 2026-08-14, when preseason opened with an empty board: "we didn't
recommend props or anything like that", and then "yeah keep going" to the
step underneath the answer.

WHY THIS IS A DATA PROBLEM AND NOT A TASTE PROBLEM. Whether August can
ever be modelled is unanswerable today for one concrete reason: nflverse
publishes no preseason player stats — its weekly file carries REG and
POST — so this repo has never stored a single preseason snap. Measured on
the ingested database: 2021-2025 hold periods 001-022 and nothing else.
There is nothing to fit on, and no amount of arguing about the model
changes that. This is the collection step.

NOTHING HERE PRICES ANYTHING and the tests below hold that line.

THE SEPARATE TABLE IS THE WHOLE SAFETY ARGUMENT. Every consumer of
`player_game_logs` reads it by (sport, season, period) and none filter by
season type, because until now none had to. A preseason row in that table
would enter the roster page's "last seen", the identity map's current
club, the team-log charts and every form window — silently, in August,
where a starter's series and a half would average in beside a full
September game. Sharing a table and remembering to filter is a rule
someone has to keep; a different table is a rule the schema keeps.
"""

import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db, ingest
from engine.sources import nflpreseason as pre

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GAME = {"season": 2026, "week": 2, "game_id": "401772000",
        "home": "KC", "away": "BUF", "state": "post"}

# The shape ESPN's summary endpoint returns, trimmed to what is read.
BOX = {"boxscore": {"players": [
    {"team": {"abbreviation": "BUF"}, "statistics": [
        {"name": "passing", "labels": ["C/ATT", "YDS", "AVG", "TD", "INT"],
         "athletes": [{"athlete": {"displayName": "Mitch Trubisky",
                                   "position": {"abbreviation": "QB"}},
                       "stats": ["12/18", "141", "7.8", "1", "0"]}]},
        {"name": "rushing", "labels": ["CAR", "YDS", "AVG", "TD", "LONG"],
         "athletes": [{"athlete": {"displayName": "Ray Davis",
                                   "position": {"abbreviation": "RB"}},
                       "stats": ["9", "-3", "-0.3", "1", "6"]}]},
        {"name": "receiving", "labels": ["REC", "YDS", "AVG", "TD", "LONG", "TGTS"],
         "athletes": [{"athlete": {"displayName": "Keon Coleman",
                                   "position": {"abbreviation": "WR"}},
                       "stats": ["4", "52", "13.0", "0", "21", "6"]},
                      {"athlete": {"displayName": "Benched Guy",
                                   "position": {"abbreviation": "WR"}},
                       "stats": ["--", "--", "--", "--", "--", "--"]}]},
    ]},
    {"team": {"abbreviation": "KC"}, "statistics": [
        {"name": "kicking", "labels": ["FG", "PCT"],
         "athletes": [{"athlete": {"displayName": "Kicker"}, "stats": ["1/1", "100"]}]},
    ]},
]}}


def _rows():
    return pre.parse_boxscore(BOX, GAME)


# --- the parse -------------------------------------------------------------
def test_it_reads_the_markets_the_prop_model_uses():
    got = {(r["player"], r["market"]): r["value"] for r in _rows()}
    assert got[("Mitch Trubisky", "pass_yds")] == 141
    assert got[("Ray Davis", "carries")] == 9
    assert got[("Keon Coleman", "rec_yds")] == 52
    assert got[("Keon Coleman", "receptions")] == 4
    assert got[("Keon Coleman", "targets")] == 6


def test_columns_are_found_by_label_not_position():
    """ESPN adds columns. A parser reading `stats[1]` is correct until the
    day it silently is not, and the number it returns after that is a
    different statistic wearing the right name."""
    src = open(os.path.join(ROOT, "engine", "sources", "nflpreseason.py"),
               encoding="utf-8").read()
    fn = src[src.index("def parse_boxscore("):]
    assert "cols = {lab: i for i, lab in enumerate(labels)}" in fn
    assert "cols.get(label)" in fn


def test_a_negative_rushing_day_survives():
    """Nine carries for minus three yards is a real line and the one most
    likely to be dropped by a naive int() guard."""
    got = {(r["player"], r["market"]): r["value"] for r in _rows()}
    assert got[("Ray Davis", "rush_yds")] == -3


def test_a_player_with_no_line_is_absent_not_zero():
    """He did not catch zero passes; he did not have a receiving line.
    Storing the first as the second would put a real 0 into every average
    a future model takes."""
    names = {r["player"] for r in _rows()}
    assert "Benched Guy" not in names


def test_the_completions_cell_is_not_read_as_a_number():
    """"12/18" is two numbers in one cell. float() refuses it, which is
    correct; a parser that split on the slash would store 12 passing
    yards."""
    assert pre._stat("12/18") is None
    assert pre._stat("--") is None
    assert pre._stat("-3") == -3


def test_a_touchdown_becomes_the_market_the_board_bets():
    """The long-shot market is "did he score at all", which neither the
    rushing nor the receiving column answers alone."""
    got = {(r["player"], r["market"]): r["value"] for r in _rows()}
    assert got[("Ray Davis", "anytime_td")] == 1.0
    assert got[("Keon Coleman", "anytime_td")] == 0.0


def test_home_and_opponent_come_from_the_fixture():
    rows = {r["player"]: r for r in _rows()}
    assert rows["Keon Coleman"]["team"] == "BUF"
    assert rows["Keon Coleman"]["opponent"] == "KC"
    assert rows["Keon Coleman"]["home"] == 0


def test_an_unreadable_payload_raises_rather_than_returning_nothing():
    """An empty list is what a game nobody played looks like. Using it for
    "I could not read this" hides a broken parser behind an ordinary
    August — the same rule `parse_games` already follows."""
    from engine.sources.fetch import DataUnavailable
    try:
        pre.parse_boxscore({"boxscore": {}}, GAME)
    except DataUnavailable:
        return
    raise AssertionError("a shapeless payload parsed as an empty game")


# --- the isolation ---------------------------------------------------------
def test_the_rows_land_in_their_own_table():
    conn = db.connect(":memory:")
    n = db.upsert_preseason_logs(conn, _rows())
    assert n > 0
    assert conn.execute("SELECT COUNT(*) FROM preseason_player_logs").fetchone()[0] == n
    assert conn.execute("SELECT COUNT(*) FROM player_game_logs").fetchone()[0] == 0, \
        "preseason reached the table every projection reads"


def test_storing_the_same_game_twice_does_not_double_it():
    conn = db.connect(":memory:")
    db.upsert_preseason_logs(conn, _rows())
    db.upsert_preseason_logs(conn, _rows())
    assert conn.execute(
        "SELECT COUNT(*) FROM preseason_player_logs").fetchone()[0] == len(_rows())


def test_the_regular_ingest_refuses_a_preseason_row():
    """The other direction. nflverse ships no PRE today, so this filter
    changes nothing right now — it exists because the day that stops
    being true is the day preseason weeks 1-3 merge into regular weeks
    1-3 under the same `period`, and nobody notices until a September
    projection comes back wrong."""
    rows = [{"season_type": "PRE", "week": "1", "position": "WR",
             "player_display_name": "August Guy", "recent_team": "KC",
             "opponent_team": "BUF", "receiving_yards": "40"},
            {"season_type": "REG", "week": "1", "position": "WR",
             "player_display_name": "September Guy", "recent_team": "KC",
             "opponent_team": "BUF", "receiving_yards": "40"}]
    names = {r["player"] for r in ingest.nfl_player_log_rows(rows, 2026)}
    assert names == {"September Guy"}, names
    names = {r["player"] for r in ingest.nfl_usage_rows(rows, 2026)}
    assert "August Guy" not in names
    names = {r["player"] for r in ingest.nfl_td_rows(rows, 2026)}
    assert "August Guy" not in names


def test_a_row_with_no_season_type_is_still_regular():
    """Older nflverse files carry no such column. Treating a missing value
    as preseason would empty five years of history."""
    rows = [{"week": "1", "position": "WR", "player_display_name": "Old File",
             "recent_team": "KC", "opponent_team": "BUF",
             "receiving_yards": "40"}]
    assert ingest.nfl_player_log_rows(rows, 2021)


# --- what may read it, and what still may not -------------------------------
#: Files allowed to read `preseason_player_logs`, each for a stated reason.
#:
#: This list started empty and the test below said so: "if a pipeline ever
#: reads it, that is a decision to price August and it should look like one
#: in the diff." Ethan made that decision on 2026-08-14 — "i wanna show
#: props for the pre season … make sure to implement scanning to see which
#: teams will be playing starters" — so the boundary MOVES rather than
#: disappearing, and this is where the move is recorded.
PRESEASON_READERS = {
    "engine/nfl/prestarters.py",   # describes usage; computes no price
    "engine/nfl/prefit.py",        # measures whether usage predicts a result
}

#: `preseason_games` — the finals — is under the same rule, added with the
#: table on 2026-08-14. The match has to be on the SQL rather than on the
#: bare name: `nflpreseason.preseason_games()` is a FUNCTION that fetches
#: the schedule, and half the launcher calls it.
_TABLE_SQL = re.compile(
    r"preseason_player_logs|(?:FROM|INTO|TABLE|UPDATE|JOIN)\s+preseason_games")


def test_only_the_declared_readers_touch_the_preseason_tables():
    """The line, redrawn. Reading the tables to say WHAT HAPPENED is now
    allowed and named; reading them to produce a NUMBER SOMEBODY BETS is
    still the thing that has to show up in a diff as its own decision."""
    import glob
    hits = []
    for path in glob.glob(os.path.join(ROOT, "engine", "**", "*.py"),
                          recursive=True) + glob.glob(os.path.join(ROOT, "*.py")):
        base = os.path.basename(path)
        if base in ("db.py", "ingest.py"):
            continue
        src = open(path, encoding="utf-8").read()
        rel = os.path.relpath(path, ROOT)
        if _TABLE_SQL.search(src) and rel not in PRESEASON_READERS:
            hits.append(rel)
    assert not hits, f"undeclared reader of the preseason tables: {hits}"


def test_the_fitter_reads_the_finals_and_still_prices_nothing():
    """`prefit` is the newest reader and the one closest to the line: it
    exists to decide whether August is priceable. It answers that question
    and does not act on it — `prices_allowed` is hard False, because a
    measured effect is not evidence the book missed it."""
    from engine.nfl import prefit
    assert prefit.prices_allowed() is False
    assert prefit.prices_allowed({"verdict": "measured"}) is False


def test_the_declared_reader_still_produces_no_price():
    """`prestarters` may read the table because it reports a HABIT — how
    many attempts a starting quarterback has taken in past Augusts. The
    moment it starts emitting an edge, a stake or a probability, it has
    become a pricing path wearing a scanner's name."""
    src = open(os.path.join(ROOT, "engine", "nfl", "prestarters.py"),
               encoding="utf-8").read()
    body = "\n".join(l for l in src.splitlines()
                     if not l.strip().startswith(("#", '"', "*")))
    for word in ("edge", "stake_units", "hit_prob", "fair_prob", "ev_per_unit"):
        assert word not in body, f"the scanner is computing {word!r}"


def test_the_cli_says_it_prices_nothing():
    src = open(os.path.join(ROOT, "ingest.py"), encoding="utf-8").read()
    i = src.index('elif args.sport == "nflpre"')
    assert "Nothing here is priced" in src[i:i + 900]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
