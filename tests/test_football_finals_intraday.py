"""The score was on the screen and not in the database.

Ethan, 2026-09-10, about thirty minutes after the Week 1 Wednesday opener
(NE @ SEA) went final: "also none of the nfl bets settled from tonight yet.
game ended about 30 mins ago".

A football game bet grades off `games.home_score`. The only thing that had
ever written one was the once-a-day nflverse schedule refresh in
`maintenance.run_if_due` — `docs/DROPLET_CHECKS.md` recorded that as the
design: "Wednesday's final settles on Thursday's pass". So the site was
drawing the final score off ESPN's scoreboard twelve seconds after it
happened, and the journal it feeds could not see it for another fifteen
hours.

`livescores.ingest_finals` is the bridge. Its whole risk is that it writes
into the table the settler grades from, so these tests are mostly about what
it REFUSES: an in-progress score, a score already ingested from the
authority, a fixture nobody scheduled, an ambiguous pair, and an August
exhibition landing on a September row.

Nothing here reaches the network or this box's databases — the payloads are
ESPN-shaped dicts parsed by the real parser, and the history DB is
`:memory:`.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db
from engine import maintenance as M
from engine.sources import livescores as LS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MSRC = open(os.path.join(ROOT, "engine", "maintenance.py"), encoding="utf-8").read()
LSRC = open(os.path.join(ROOT, "engine", "sources", "livescores.py"),
            encoding="utf-8").read()

NE = "New England Patriots"
SEA = "Seattle Seahawks"


def _event(away_name, home_name, away_score, home_score, state, date):
    return {
        "id": "401872656", "date": date,
        "status": {"type": {"state": state, "shortDetail": "Final"},
                   "period": 4},
        "competitions": [{"competitors": [
            {"homeAway": "home", "score": home_score,
             "team": {"id": "26", "displayName": home_name,
                      "abbreviation": "SEA"}},
            {"homeAway": "away", "score": away_score,
             "team": {"id": "17", "displayName": away_name,
                      "abbreviation": "NE"}},
        ]}],
    }


def _board(*events):
    """Patch the fetch so the REAL parser runs on an ESPN-shaped payload."""
    payload = json.dumps({"events": list(events)})
    LS.fetch_text = lambda *a, **k: payload
    return payload


def _history(*fixtures):
    """An in-memory history DB holding exactly these scheduled fixtures.

    Each is (season, period, away, home, date, home_score, away_score).
    """
    conn = db.connect(":memory:")
    db.upsert_games(conn, [{
        "sport": "nfl", "season": season, "period": period,
        "game_id": f"{away}@{home}", "home": home, "away": away, "date": date,
        "home_score": hs, "away_score": as_, "spread": 0.0, "total": None,
        "roof": "outdoors", "surface": "turf", "temp": None, "wind": None,
        "extra": None,
    } for season, period, away, home, date, hs, as_ in fixtures])
    conn.commit()
    return conn


def _score(conn, game_id="NE@SEA"):
    r = conn.execute("SELECT home_score, away_score FROM games WHERE game_id=?",
                     (game_id,)).fetchone()
    return (r["home_score"], r["away_score"])


def setup_module(_m=None):
    setup_module.saved = LS.fetch_text


def teardown_module(_m=None):
    LS.fetch_text = setup_module.saved


# --- the night itself -------------------------------------------------------
def test_a_final_lands_on_the_scheduled_fixture_minutes_later():
    conn = _history((2026, "001", "NE", "SEA", "2026-09-09", None, None))
    _board(_event(NE, SEA, "13", "24", "post", "2026-09-10T00:15Z"))
    out = LS.ingest_finals(conn, "nfl")
    assert out["games"] == 1
    assert _score(conn) == (24.0, 13.0)


def test_the_ingest_is_wired_into_the_intraday_settle_for_both_leagues():
    i = MSRC.index("def ingest_for_open_bets(")
    block = MSRC[i:MSRC.index("\ndef ", i + 1)]
    assert 'for league in ("nfl", "cfb"):' in block
    assert "livescores.ingest_finals(hconn, league)" in block


def test_it_is_only_asked_for_a_league_with_an_open_pick():
    """Same rule as every other league here: a quiet night must not pay for
    a feed round-trip on a league with nothing riding on it."""
    i = MSRC.index("def ingest_for_open_bets(")
    block = MSRC[i:MSRC.index("\ndef ", i + 1)]
    body = block[block.index('for league in ("nfl", "cfb"):'):]
    assert body.index("_has_open(lconn, league, days)") < \
        body.index("ingest_finals"), "the feed is called before the gate"


def test_a_feed_outage_leaves_the_picks_open_and_the_settle_running():
    """The settle below this ingest grades everything already in the DB. A
    scoreboard blackout must not take that with it."""
    i = MSRC.index("def ingest_for_open_bets(")
    block = MSRC[i:MSRC.index("\ndef ", i + 1)]
    body = block[block.index('for league in ("nfl", "cfb"):'):]
    assert body.index("try:") < body.index("ingest_finals")
    assert "except Exception as exc:" in body


# --- what it refuses --------------------------------------------------------
def test_a_game_in_progress_is_never_written():
    """The one that would be permanent. `_game_bet_evidence` was written
    about the NBA schedule parser passing live scores into this table: a
    prop graded off a partial line self-heals on the next pass, a game bet
    graded off a partial score does not."""
    conn = _history((2026, "001", "NE", "SEA", "2026-09-09", None, None))
    _board(_event(NE, SEA, "10", "7", "in", "2026-09-10T00:15Z"))
    out = LS.ingest_finals(conn, "nfl")
    assert out["games"] == 0 and out["waiting"] == 1
    assert _score(conn) == (None, None)


def test_a_scheduled_game_is_never_written():
    conn = _history((2026, "001", "NE", "SEA", "2026-09-09", None, None))
    _board(_event(NE, SEA, "0", "0", "pre", "2026-09-10T00:15Z"))
    assert LS.ingest_finals(conn, "nfl")["games"] == 0
    assert _score(conn) == (None, None)


def test_a_score_already_ingested_is_never_overwritten():
    """nflverse is the authority — corrected, official, and the thing every
    backtest on this box reads. A scoreboard reading may fill a blank and
    may never replace an answer."""
    conn = _history((2026, "001", "NE", "SEA", "2026-09-09", 24.0, 13.0))
    _board(_event(NE, SEA, "99", "99", "post", "2026-09-10T00:15Z"))
    assert LS.ingest_finals(conn, "nfl")["games"] == 0
    assert _score(conn) == (24.0, 13.0)


def test_it_never_creates_a_fixture_nobody_scheduled():
    """Only an UPDATE, so it cannot invent a game, guess a season or a week,
    or duplicate a row under a period it derived wrongly."""
    conn = _history()
    _board(_event(NE, SEA, "13", "24", "post", "2026-09-10T00:15Z"))
    assert LS.ingest_finals(conn, "nfl")["games"] == 0
    assert conn.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 0


def test_an_august_exhibition_does_not_score_the_week_one_row():
    """ESPN's scoreboard takes no season-type filter — it returns whatever
    the league is playing today. `attach_live` documents the same collision:
    two teams who meet in preseason and again in Week 1."""
    conn = _history((2026, "001", "NE", "SEA", "2026-09-09", None, None))
    _board(_event(NE, SEA, "17", "13", "post", "2026-08-15T00:15Z"))
    assert LS.ingest_finals(conn, "nfl")["games"] == 0
    assert _score(conn) == (None, None)


def test_a_sunday_night_kickoff_still_matches_across_the_utc_boundary():
    """A 20:20 Eastern kickoff is 00:20Z the next day; nflverse stores the
    local gameday. Requiring equality would switch this off for exactly the
    games people bet."""
    conn = _history((2026, "001", "NE", "SEA", "2026-09-13", None, None))
    _board(_event(NE, SEA, "13", "24", "post", "2026-09-14T00:20Z"))
    assert LS.ingest_finals(conn, "nfl")["games"] == 1
    assert _score(conn) == (24.0, 13.0)


def test_two_candidate_fixtures_are_refused_rather_than_guessed():
    """The pair does not identify a fixture, and a coin-flip choice would
    put a wrong number in the record — which is worse than an open bet,
    because nothing downstream can tell it from a right one."""
    conn = _history((2026, "001", "NE", "SEA", "2026-09-09", None, None),
                    (2026, "002", "NE", "SEA", "2026-09-10", None, None))
    _board(_event(NE, SEA, "13", "24", "post", "2026-09-10T00:15Z"))
    out = LS.ingest_finals(conn, "nfl")
    assert out["games"] == 0
    assert out["skipped"] and "refusing to guess" in out["skipped"][0]
    assert _score(conn) == (None, None)


def test_a_final_with_no_score_is_reported_not_written_as_zero():
    conn = _history((2026, "001", "NE", "SEA", "2026-09-09", None, None))
    _board(_event(NE, SEA, None, None, "post", "2026-09-10T00:15Z"))
    out = LS.ingest_finals(conn, "nfl")
    assert out["games"] == 0 and out["skipped"]
    assert _score(conn) == (None, None)


# --- the guards, in the source ----------------------------------------------
def test_the_update_carries_its_own_blank_check():
    """Belt and braces: the SELECT filters on it and so does the UPDATE, so
    a score written between the two still cannot be clobbered."""
    i = LSRC.index("def ingest_finals(")
    block = LSRC[i:]
    upd = block[block.index("UPDATE games SET"):]
    assert "home_score IS NULL" in upd[:400], \
        "the write does not re-check that it is filling a blank"


def test_nothing_here_inserts_into_games():
    i = LSRC.index("def ingest_finals(")
    block = LSRC[i:]
    body = block[block.index('result: dict = {'):]
    assert "INSERT" not in body.upper().replace("INSERTS", ""), \
        "this pass can create a fixture"


if __name__ == "__main__":
    setup_module()
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    teardown_module()
    print(f"\n{len(fns)} tests passed.")
