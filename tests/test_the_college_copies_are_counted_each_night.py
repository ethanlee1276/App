"""The college copies are counted each night, by kind and by the ids they sit under (step AFG, 25 November 2026).

Eleven days after engine/cfbdedupe's cleanup of 14 November, 112 of 186 college market logs on the live board held a
game twice (step AFE). The reads merge them now; which writer files them again is a question about game ids the board
does not show. So:

  * `cfbdedupe.census` counts a season's copies without removing anything: player-games filed more than once, and
    each extra row by kind (same day and teams, a day apart, the opponent under another code, the player's school
    under another code, the other side) and by the two ids' shapes (ESPN's number, a provisional box copy,
    away@home), with two examples a kind;
  * the daily chores run it once the night's college rows are in (maintenance.run_cfb_census), outside the suite;
  * the heartbeat carries the count (`cfb_copies`), so it is read off the site, not asked of the box.

Offline. Run directly: `python3 tests/test_the_college_copies_are_counted_each_night.py`
"""
import datetime
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import cfbdedupe, db  # noqa: E402


def _row(player, team, opp, period, gid, market="rush_yds", value=10.0):
    return {"sport": "cfb", "season": 2026, "period": period, "game_id": gid, "player": player, "team": team,
            "opponent": opp, "position": "RB", "home": 1, "market": market, "value": value}


def _file():
    path = os.path.join(tempfile.mkdtemp(), "history.db")
    rows = [
        # The opponent under another code: the play file's BUFF and a box copy's BUF a day later.
        _row("Scoop Smith", "M-OH", "BUFF", "2026-11-03", "401858249"),
        _row("Scoop Smith", "M-OH", "BUF", "2026-11-04", "BUF@M-OH-box"),
        # A day apart, same teams, two ESPN rows (Eastern and UTC days).
        _row("Wayne Harris", "KENT", "SAC", "2026-10-30", "401858001", market="rec_yds"),
        _row("Wayne Harris", "KENT", "SAC", "2026-10-31", "401858001", market="rec_yds"),
        # Same day, same teams, ESPN's number and away@home.
        _row("Terik Mulder", "KENT", "OSU", "2026-09-19", "401858002", market="rec_yds"),
        _row("Terik Mulder", "KENT", "OSU", "2026-09-19", "KENT@OSU", market="rec_yds"),
        # The other side.
        _row("Dru DeShields", "KENT", "AKR", "2026-10-24", "401858003", market="pass_yds", value=294.0),
        _row("Dru DeShields", "AKR", "KENT", "2026-10-24", "401858003x", market="pass_yds", value=19.0),
        # His school under another code.
        _row("Ty Buffalo", "BUF", "WMU", "2026-10-03", "WMU@BUF-box"),
        _row("Ty Buffalo", "BUFF", "WMU", "2026-10-03", "401858004"),
        # One game, once: no copy.
        _row("Scoop Smith", "M-OH", "WMU", "2026-11-24", "401858005"),
        # Last season's rows are another season's count.
        {**_row("Scoop Smith", "M-OH", "OHIO", "2025-11-01", "401700001"), "season": 2025},
    ]
    conn = db.connect(path)
    db.upsert_player_logs(conn, rows)
    conn.commit()
    conn.close()
    return path


def test_the_count_names_each_kind_and_the_ids():
    conn = db.connect(_file())
    try:
        got = cfbdedupe.census(conn, 2026)
    finally:
        conn.close()
    assert got["rows"] == 11 and got["games"] == 5 and got["copies"] == 5, got
    assert got["kinds"] == {"the opponent under another code": 1, "a day apart, same teams": 1,
                            "same day, same teams": 1, "the other side": 1, "his school under another code": 1}, got
    assert got["ids"]["the opponent under another code"] == {"box+espn": 1}
    assert got["ids"]["a day apart, same teams"] == {"espn+espn": 1}
    assert got["ids"]["same day, same teams"] == {"away@home+espn": 1}
    assert got["ids"]["the other side"] == {"espn+other": 1}
    ex = got["examples"]["the opponent under another code"][0]
    assert ex == ("Scoop Smith, rush_yds, 2026-11-03: 401858249 (M-OH v BUFF) and BUF@M-OH-box on 2026-11-04 "
                  "(M-OH v BUF)"), ex


def test_the_chores_keep_it_and_the_heartbeat_carries_it():
    from engine import maintenance as M
    path = _file()
    state = os.path.join(tempfile.mkdtemp(), "cfb_copies.json")
    lines = []
    doc = M.run_cfb_census(lines.append, today=datetime.date(2026, 11, 25), path=path, state_path=state)
    assert doc["season"] == 2026 and doc["games"] == 5 and doc["copies"] == 5
    assert json.loads(Path(state).read_text())["kinds"] == doc["kinds"]
    assert lines == ["  cfb copies: 5 player-game(s) of 2026 filed more than once, 5 extra row(s) (step AFG)"]
    assert M.run_cfb_census(lines.append, path=os.path.join(tempfile.mkdtemp(), "none.db")) == {}
    src = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    i = src.index("def _run_chores(")
    j = src.find("\ndef ", i + 10)
    body = src[i:j if j > 0 else len(src)]
    assert body.index('log(f"  ⚠️  cfb player backfill failed: {exc}")') < body.index("_run_cfb_census(log, today)")
    assert "if os.environ.get(modelstate.ENV_VAR):\n        return\n    run_cfb_census(log, today=today)" in src
    launch = (ROOT / "launch.py").read_text(encoding="utf-8")
    assert '"cfb_copies": _cfb_copies_public(),' in launch
    import launch as L
    real = M.CFB_COPIES_STATE
    try:
        M.CFB_COPIES_STATE = Path(state)
        pub = L._cfb_copies_public()
    finally:
        M.CFB_COPIES_STATE = real
    assert pub["games"] == 5 and pub["kinds"] == doc["kinds"] and "examples" in pub


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
