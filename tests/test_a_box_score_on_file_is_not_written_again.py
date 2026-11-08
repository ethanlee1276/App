"""A finished game's box score already on file as it stands is not written
again, and the ingest says where its time goes (engine/boxsettle.on_file,
ingest_for_open's ``unchanged``; engine/maintenance.ingest_for_open_bets'
``box_parts``; engine/stacksample.Sampler's ``depth``).

The settle pass's ingest on Saturday 7 November: 66 of 71 seconds in the
college box scores. Every five minutes it filed every finished college game
on the open bets' days again, some 150 rows a game, each an INSERT OR
REPLACE on the history file, while the summaries had not changed in hours.
What these hold:

  * rows already on file exactly as they stand are found so with one read,
    and any difference (a value, a missing row, another period) is not;
  * a row on file the summary no longer carries changes nothing (a write
    never removed one);
  * the second pass over an unchanged summary writes nothing and counts the
    game ``unchanged``; a corrected stat writes the game again;
  * a sampler can name two calls under its root (``fetch>loads``);
  * the ingest samples each box-score pull and the settle pass puts the
    result on its phases as ``box_parts``.

Run directly: `python3 tests/test_a_box_score_on_file_is_not_written_again.py`
"""
import copy
import datetime as dt
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import boxsettle as B, db, ledger                     # noqa: E402
from engine.stacksample import Sampler                            # noqa: E402

YESTERDAY = (dt.date.today() - dt.timedelta(days=1)).isoformat()


def _world():
    t = Path(tempfile.mkdtemp())
    L = ledger.connect(t / "l.db")
    ledger.configure_bankroll(L, starting=1000, unit_pct=1)
    H = db.connect(t / "h.db")
    return L, H


def _team(abbr, tid, name):
    return {"abbreviation": abbr, "id": tid, "displayName": name}


MICH, OSU = _team("MICH", "130", "Michigan Wolverines"), _team("OSU", "194", "Ohio State Buckeyes")


def _payload(yards="112"):
    return {"boxscore": {"players": [
        {"team": MICH, "statistics": [
            {"name": "rushing", "labels": ["CAR", "YDS", "AVG", "TD", "LONG"],
             "athletes": [{"athlete": {"displayName": "Donovan Edwards",
                                       "position": {"abbreviation": "RB"}},
                           "stats": ["18", yards, "6.2", "2", "41"]}]}]},
        {"team": OSU, "statistics": [
            {"name": "receiving", "labels": ["REC", "YDS", "AVG", "TD", "LONG"],
             "athletes": [{"athlete": {"displayName": "Some Receiver",
                                       "position": {"abbreviation": "WR"}},
                           "stats": ["5", "60", "12.0", "0", "20"]}]}]}]}}


def _college_game():
    from engine.sources.cfbdata import _team_key
    L, H = _world()
    L.execute("INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, odds, "
              "stake_units, stake_dollars, status, category) VALUES (?, 'cfb', ?, ?, "
              "'Some Receiver', 'receptions', 'OVER', 6.5, -110, 1, 10, 'open', 'main')",
              (f"{YESTERDAY}T12:00:00", YESTERDAY, YESTERDAY))
    L.commit()
    H.execute("INSERT INTO games (sport, season, period, game_id, date, home, away, home_score, "
              "away_score, extra) VALUES ('cfb', 2026, ?, '401999', ?, ?, ?, 24, 20, ?)",
              (YESTERDAY, YESTERDAY, _team_key(MICH), _team_key(OSU),
               json.dumps({"espn_game_id": "401999"})))
    H.commit()
    return L, H


def test_rows_on_file_as_they_stand_are_found_so_and_any_difference_is_not():
    L, H = _college_game()
    g = dict(H.execute("SELECT * FROM games").fetchone())
    rows = B.cfb_rows(_payload(), g)
    assert rows and not B.on_file(H, rows), "nothing on file yet"
    db.upsert_player_logs(H, rows)
    assert B.on_file(H, rows)
    changed = copy.deepcopy(rows)
    changed[0]["value"] = changed[0]["value"] + 1
    assert not B.on_file(H, changed), "a corrected stat"
    assert not B.on_file(H, rows + [dict(rows[0], market="new_market")]), "a row not on file"
    assert not B.on_file(H, [dict(r, period="2001-01-01") for r in rows]), "another day"
    assert B.on_file(H, rows[1:]), "a row on file the summary no longer carries changes nothing"
    assert not B.on_file(H, [])


def test_the_second_pass_over_an_unchanged_summary_writes_nothing():
    L, H = _college_game()
    payload = {"p": _payload()}
    fs = lambda lg, eid: payload["p"]                                  # noqa: E731
    fr = lambda lg: []                                                 # noqa: E731
    first = B.ingest_for_open(L, H, "cfb", log=lambda *a: None, fetch_rows=fr, fetch_summary=fs)
    assert first["games"] == 1 and not first.get("unchanged"), first
    before = H.total_changes
    second = B.ingest_for_open(L, H, "cfb", log=lambda *a: None, fetch_rows=fr, fetch_summary=fs)
    assert second["games"] == 0 and second["unchanged"] == 1 and second["rows"] == 0, second
    assert H.total_changes == before, "not one row written"
    payload["p"] = _payload(yards="120")                                 # a stat correction
    third = B.ingest_for_open(L, H, "cfb", log=lambda *a: None, fetch_rows=fr, fetch_summary=fs)
    assert third["games"] == 1 and not third.get("unchanged"), third
    got = H.execute("SELECT value FROM player_game_logs WHERE player='Donovan Edwards' "
                    "AND market='rush_yds'").fetchone()[0]
    assert got == 120.0
    # And the bet still grades off the rows on file.
    assert ledger.settle_from_history(L, H) == 1


def _busy(s):
    end = time.monotonic() + s
    while time.monotonic() < end:
        pass


def _leaf():
    _busy(0.3)


def _mid():
    _leaf()


def _root():
    _mid()


def test_a_sampler_can_name_two_calls_under_its_root():
    with Sampler(_root.__code__, interval=0.01, depth=2) as s:
        _root()
    secs = s.seconds()
    assert set(secs) <= {"_mid>_leaf", "_mid", "(self)"}, secs
    assert secs.get("_mid>_leaf", 0) > 0.15, secs
    with Sampler(_root.__code__, interval=0.01) as one:
        _root()
    assert set(one.seconds()) <= {"_mid", "(self)"}, one.seconds()


def test_the_settle_pass_puts_the_box_score_parts_on_its_phases():
    from engine import maintenance as M
    src = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    assert "Sampler(boxsettle.ingest_for_open.__code__, depth=2)" in src
    assert 'phases["box_parts"] = res["box_parts"]' in src
    swaps = []

    def swap(obj, name, val):
        swaps.append((obj, name, getattr(obj, name)))
        setattr(obj, name, val)

    def slow_ingest(l, h, league, log=None):
        _busy(0.2)
        return {"games": 0, "rows": 0, "purged": 0, "skipped": [], "unchanged": 3}
    swap(M, "_has_open", lambda lconn, sport, days: sport == "cfb")
    swap(B, "ingest_for_open", slow_ingest)
    from engine.sources import livescores
    swap(livescores, "ingest_finals", lambda h, lg: {"games": 0, "skipped": []})
    said = []
    try:
        res = M.ingest_for_open_bets(None, None, [YESTERDAY], log=said.append)
    finally:
        for obj, name, val in reversed(swaps):
            setattr(obj, name, val)
    assert "cfb" in (res.get("box_parts") or {}), res
    assert any("3 finished game(s) already on file" in str(x) for x in said), said


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
