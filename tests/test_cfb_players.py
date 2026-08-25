"""College football's player layer — the one the sidebar said couldn't exist.

Ethan, 2026-08-24, circling most of the CFB sidebar: "can we now work on
CFB not having any of this info."

Players, Trending and Rosters were hidden for CFB behind one sentence —
"no free player-level feed covers 134 programs" — and the sentence was
stale the day it was written: ESPN's summary endpoint carries the full
box score, keyless, in the SAME API family engine/sources/cfbdata.py has
read the scoreboard from all along. espnhoops has ingested the identical
shape for the NBA and WNBA since August. This file pins the college
version of that layer.

WHAT FOOTBALL CHANGES ABOUT THE PARSE, because basketball's parser
cannot be reused blind:

  * Groups are POSITIONAL. "YDS" means pass_yds inside the passing block
    and rush_yds inside the rushing block, so the market map is keyed
    (group, column) — a column-only map would merge every yard in the
    game into one number.
  * One player spans groups. A quarterback who scrambles appears under
    passing AND rushing; rows merge by (team, player) before they are
    emitted, or he would land in the logs twice with half a game each.
  * Positions are best-effort. When the athlete record carries none, the
    first group he appeared in is the honest guess (passing→QB,
    rushing→RB, receiving→WR) — a tight end falls to WR, a known and
    bounded mislabel, corrected whenever the feed does say.

Run directly: `python3 tests/test_cfb_players.py`
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import db, statlogs, playersearch                # noqa: E402
from engine.sources import cfbdata as C                      # noqa: E402
from engine.sources.fetch import DataUnavailable             # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _summary():
    """A summary payload in ESPN's own shape, small but structurally
    faithful: labels arrays, athletes with aligned stats, one player in
    two groups."""
    return {"boxscore": {"players": [
        {"team": {"abbreviation": "UGA"}, "statistics": [
            {"name": "passing", "labels": ["C/ATT", "YDS", "AVG", "TD", "INT"],
             "athletes": [{"athlete": {
                 "displayName": "Gunner Stockton", "id": "99",
                 "position": {"abbreviation": "QB"},
                 "headshot": {"href": "https://a.espncdn.com/99.png"}},
                 "stats": ["18/25", "264", "10.6", "2", "0"]}]},
            {"name": "rushing", "labels": ["CAR", "YDS", "AVG", "TD", "LONG"],
             "athletes": [
                 {"athlete": {"displayName": "Gunner Stockton", "id": "99"},
                  "stats": ["6", "41", "6.8", "1", "12"]},
                 {"athlete": {"displayName": "Nate Frazier", "id": "77"},
                  "stats": ["19", "112", "5.9", "1", "38"]}]},
            {"name": "receiving",
             "labels": ["REC", "YDS", "AVG", "TD", "LONG", "TGTS"],
             "athletes": [{"athlete": {"displayName": "Zachariah Branch",
                                       "id": "55"},
                           "stats": ["7", "93", "13.3", "0", "28", "9"]}]},
        ]},
        {"team": {"abbreviation": "CLEM"}, "statistics": [
            {"name": "rushing", "labels": ["CAR", "YDS", "AVG", "TD", "LONG"],
             "athletes": [{"athlete": {"displayName": "Opp Back", "id": "11"},
                           "stats": ["14", "88", "6.3", "0", "22"]}]},
        ]},
    ]}}


# --- the parse -------------------------------------------------------------

def test_a_player_in_two_groups_is_one_row():
    # TD columns joined the parse 2026-08-25 (the anytime-TD long-shot
    # board settles against them). The QB's PASSING touchdowns stay out
    # on purpose — an anytime-scorer bet pays the player who scores, not
    # the one who throws — so his anytime_td counts the rushing score
    # alone.
    rows = C.parse_summary(_summary())
    qbs = [r for r in rows if r["player"] == "Gunner Stockton"]
    assert len(qbs) == 1, "the scrambling QB landed in the logs twice"
    assert qbs[0]["stats"] == {"pass_yds": 264.0, "carries": 6.0,
                               "rush_yds": 41.0, "rush_td": 1.0,
                               "anytime_td": 1.0}


def test_yds_means_a_different_market_in_each_group():
    rows = {r["player"]: r for r in C.parse_summary(_summary())}
    assert rows["Nate Frazier"]["stats"] == {"carries": 19.0,
                                             "rush_yds": 112.0,
                                             "rush_td": 1.0,
                                             "anytime_td": 1.0}
    # A zero is a RESULT — "played and did not score" is what most
    # anytime-TD bets settle against — so the scoreless receiver still
    # carries the row.
    assert rows["Zachariah Branch"]["stats"] == {
        "receptions": 7.0, "rec_yds": 93.0, "targets": 9.0,
        "rec_td": 0.0, "anytime_td": 0.0}


def test_position_is_taken_when_given_and_guessed_when_not():
    rows = {r["player"]: r for r in C.parse_summary(_summary())}
    assert rows["Gunner Stockton"]["position"] == "QB"      # the feed said
    assert rows["Nate Frazier"]["position"] == "RB"         # group guess
    assert rows["Zachariah Branch"]["position"] == "WR"


def test_identity_rides_along_for_the_faces():
    rows = {r["player"]: r for r in C.parse_summary(_summary())}
    assert rows["Gunner Stockton"]["espn_id"] == "99"
    assert rows["Gunner Stockton"]["headshot"].endswith("99.png")


# --- the ingest ------------------------------------------------------------

def _seeded():
    conn = db.connect(":memory:")
    db.upsert_games(conn, [{
        "sport": "cfb", "season": 2026, "period": "2026-09-05",
        "game_id": "401", "home": "UGA", "away": "CLEM",
        "home_score": 34, "away_score": 21, "spread": -7.5, "total": 54.5,
        "roof": "outdoor", "surface": "grass", "temp": None, "wind": None,
        "extra": None}])
    return conn


def test_the_ingest_walks_our_own_games_and_stores_the_logs():
    conn = _seeded()
    real = C.fetch_summary
    C.fetch_summary = lambda gid, ttl=0: _summary()
    try:
        res = C.ingest_player_logs(conn, "2026-09-01", "2026-09-07",
                                   quiet=True)
    finally:
        C.fetch_summary = real
    assert res["games"] == 1 and res["skipped"] == []
    # One row per (player, market). TD columns joined 2026-08-25 (the
    # long-shot board settles on them), so each player adds his TD
    # market(s) plus the derived anytime_td: Stockton 3+2, Frazier 2+2,
    # Branch 3+2, the opposing back 2+2.
    assert res["player_logs"] == 18, res
    row = conn.execute(
        "SELECT * FROM player_game_logs WHERE sport='cfb' AND "
        "player='Gunner Stockton' AND market='pass_yds'").fetchone()
    assert row["value"] == 264.0
    assert row["season"] == 2026 and row["opponent"] == "CLEM"
    assert row["home"] == 1
    opp = conn.execute(
        "SELECT opponent, home FROM player_game_logs WHERE "
        "player='Opp Back' AND market='rush_yds'").fetchone()
    assert opp["opponent"] == "UGA" and opp["home"] == 0
    face = conn.execute(
        "SELECT espn_id FROM player_assets WHERE sport='cfb' AND "
        "player='Gunner Stockton'").fetchone()
    assert face and face["espn_id"] == "99"


def test_a_refused_summary_is_a_note_never_a_dead_run():
    """ESPN refuses this endpoint from some cloud IPs while serving the
    scoreboard fine to the same box — the nflpre ingest learned this
    first. A refusal must skip and say so, not kill the walk."""
    conn = _seeded()
    real = C.fetch_summary
    C.fetch_summary = lambda gid, ttl=0: (_ for _ in ()).throw(
        DataUnavailable("HTTP 403"))
    try:
        res = C.ingest_player_logs(conn, "2026-09-01", "2026-09-07",
                                   quiet=True)
    finally:
        C.fetch_summary = real
    assert res["games"] == 0 and res["player_logs"] == 0
    assert res["skipped"] and "403" in res["skipped"][0]


def test_an_unplayed_game_is_never_asked_for_a_box():
    conn = db.connect(":memory:")
    db.upsert_games(conn, [{
        "sport": "cfb", "season": 2026, "period": "2026-09-05",
        "game_id": "402", "home": "UGA", "away": "CLEM",
        "home_score": None, "away_score": None, "spread": None,
        "total": None, "roof": "outdoor", "surface": "grass",
        "temp": None, "wind": None, "extra": None}])
    asked = []
    real = C.fetch_summary
    C.fetch_summary = lambda gid, ttl=0: asked.append(gid) or {}
    try:
        C.ingest_player_logs(conn, "2026-09-01", "2026-09-07", quiet=True)
    finally:
        C.fetch_summary = real
    assert asked == [], "a scoreless game was asked for a box score"


# --- the pages downstream --------------------------------------------------

def test_the_logs_reach_the_player_search():
    conn = _seeded()
    real = C.fetch_summary
    C.fetch_summary = lambda gid, ttl=0: _summary()
    try:
        C.ingest_player_logs(conn, "2026-09-01", "2026-09-07", quiet=True)
    finally:
        C.fetch_summary = real
    assert "cfb" in dict(statlogs.SPORT_MARKETS)
    labels = dict(statlogs.SPORT_MARKETS)["cfb"]
    # Same vocabulary as the NFL's, because the search dedupes BY LABEL.
    from engine.models import MARKET_LABELS as NFL
    for key, label in labels:
        if key in NFL:
            assert NFL[key] == label, (key, label, NFL[key])
    assert "cfb" in playersearch.SOURCES


def test_rosters_build_treats_cfb_like_the_other_log_built_leagues():
    import rosters_build as RB
    assert "cfb" in RB.FROM_LOGS
    assert "cfb" not in RB.NO_SOURCE, \
        "cfb is simultaneously buildable and declared sourceless"


def test_the_sidebar_hides_only_what_still_has_a_reason():
    i = APP.index("const HIDDEN_VIEWS")
    seg = APP[i:APP.index("};", i)]
    j = seg.index("cfb:")
    line = seg[j:seg.index("]", j)]
    for gone in ("players", "rosters"):
        assert f'"{gone}"' not in line, \
            f"{gone} is still hidden for CFB after the layer shipped"
    # Trending STAYS hidden — but for the board's reason (the college
    # model prices games, not players; there are no player projections
    # to rank movers from), not the stale no-feed one.
    assert '"trending"' in line
    # longshots LEFT 2026-08-25: engine/cfb/tds prices anytime-TD quotes
    # off these very logs, so the page has an engine behind it now.
    assert '"longshots"' not in line
    # weather LEFT the list within the same day: CFBD venue coordinates
    # + Open-Meteo at the kickoff hour — see tests/test_cfb_weather.py.
    assert '"weather"' not in line
    k = APP.index("const HIDDEN_WHY")
    why = APP[k:APP.index("};", k)]
    assert "no free player-level feed" not in why, \
        "the stale claim this whole layer retires is still in the copy"


def test_the_roster_page_has_college_words():
    assert "cfb:" in APP[APP.index("const ROSTER_COPY"):
                         APP.index("};", APP.index("const ROSTER_COPY"))]
    assert "College rosters churn hardest" in APP


def test_the_cli_wires_the_logs_behind_scores_only():
    src = open(os.path.join(ROOT, "ingest.py"), encoding="utf-8").read()
    i = src.index('args.sport == "cfb"')
    seg = src[i:i + 3000]
    assert "ingest_player_logs" in seg, \
        "the cfb ingest no longer pulls the player layer"
    assert "args.scores_only" in seg, \
        "there is no way to skip box scores on a metered connection"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
