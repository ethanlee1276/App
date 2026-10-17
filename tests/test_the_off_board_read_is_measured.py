"""The off-board read is replayed on finished seasons and its numbers
measured — a report that changes nothing (engine/slipreadfit).

Ethan, 2026-10-13: "add all of them", the second being the check that
"ours 88%" on a leg no board carries is what such legs do.

Every test here runs on a synthetic two-season NFL history (the read's own
fixture, tests/test_an_off_board_leg_gets_our_read._nfl_db): nothing reads
data/history.db or the network. The real run is the box's (runbook 41).

    python3 tests/test_the_off_board_read_is_measured.py
"""

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_SANDBOX = Path(tempfile.mkdtemp())
os.environ["QB_MODELS_DIR"] = str(_SANDBOX / "models")
os.environ["QB_LIKELY_CAL"] = str(_SANDBOX / "likely_calibration.json")

from engine import db as DB                                       # noqa: E402
from engine import slipread as SR                                 # noqa: E402
from engine import slipreadfit as SRF                             # noqa: E402

_spec = importlib.util.spec_from_file_location("_readtests", ROOT / "tests" / "test_an_off_board_leg_gets_our_read.py")
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)


def _history():
    """The read's fixture plus a games row for every game it logs, so the
    replay has a card (spread, total, weather) for each."""
    path, conn = T._nfl_db()
    rows = []
    seen = set()
    for r in conn.execute("SELECT DISTINCT season, period, game_id, team, opponent, home FROM player_game_logs "
                          "WHERE sport='nfl'").fetchall():
        season, period, gid, team, opp, home = r
        key = (season, period, gid)
        if key in seen:
            continue
        seen.add(key)
        h, a = (team, opp) if home else (opp, team)
        rows.append({"sport": "nfl", "season": season, "period": period, "game_id": gid, "home": h, "away": a,
                     "home_score": None, "away_score": None, "spread": -3.5, "total": 45.5, "roof": "outdoors",
                     "surface": "grass", "temp": 58.0, "wind": 6.0, "extra": None,
                     "date": f"{season}-10-{int(period):02d}"})
    DB.upsert_games(conn, rows)
    conn.commit()
    return path, conn


def test_a_read_as_of_a_week_sees_nothing_played_after_it():
    SR.clear_cache()
    path, conn = _history()
    logs = SR.FOOTBALL_LOGS["rush_att"]
    full, _ = SR.games(conn, "nfl", "Josh Allen", logs, [2026, 2025])
    cut, _ = SR.games(conn, "nfl", "Josh Allen", logs, [2026, 2025], before=(2026, "003"))
    assert max(g["period"] for g in full if g["season"] == 2026) == "005"
    assert max(g["period"] for g in cut if g["season"] == 2026) == "002", "a week after the cutoff leaked"
    assert [g for g in cut if g["season"] == 2025] == [g for g in full if g["season"] == 2025], \
        "last season is the anchor, whole"
    assert SR._seasons(conn, "nfl", asof=(2025, "009")) == [2025] and SR._seasons(conn, "nfl") == [2026, 2025]
    assert max(r["week"] for r in SR._nfl_wide(conn, 2026, before=3)) == 2
    assert max(r["week"] for r in SR._nfl_wide(conn, 2026)) == 5
    board = T._nfl_board()
    who = {"player": "Josh Allen", "team": "BUF", "position": "QB"}
    row = SR.football(conn, board, "nfl", dict(T.ALLEN), who, asof=(2026, "003"))
    assert row and row["projection"] is not None
    assert all(int(l["week"]) < 3 for l in row["logs"] if not l.get("prior")), row["logs"]
    assert row["season_games"] == 2
    live = SR.football(conn, board, "nfl", dict(T.ALLEN), who)
    assert live["season_games"] == 5, "the live read, with no cutoff, is tonight's"
    # The two defences the model rated are not the same table: the as-of
    # one was built on two weeks, the live one on five.
    assert SR.defence_ratings(conn, "nfl", 2026, asof=(2026, "003"))["MIA"]["rb_rush_att"]["games"] == 2
    assert SR.defence_ratings(conn, "nfl", 2026)["MIA"]["rb_rush_att"]["games"] == 5


def test_the_replay_prices_every_role_at_a_book_line_and_a_ladder():
    SR.clear_cache()
    path, conn = _history()
    before = os.path.getmtime(path)
    rows = SRF.replay(conn, "nfl", [2026], markets=("rush_att", "pass_yds"))
    assert rows, "nothing replayed"
    assert os.path.getmtime(path) == before, "the replay wrote to the history database"
    assert {r["arm"] for r in rows} == {"book", "ladder"}
    assert {r["market"] for r in rows} == {"rush_att", "pass_yds"}
    assert all(0.0 < r["ours"] < 1.0 and 0.0 < r["last8"] < 1.0 and r["hit"] in (0, 1) for r in rows)
    assert all(r["line"] % 1 == 0.5 for r in rows), "a line a push can land on"
    assert all(r["season"] == 2026 for r in rows), "only the seasons asked for are replayed"
    players = {r["player"] for r in rows if r["market"] == "rush_att"}
    assert "Josh Allen" in players and "RB BUF" in players and "QB MIA" not in players, \
        "a quarterback with three carries a game is not a role a book hangs a prop on"
    # Up the ladder the chance of the over falls: the read is one
    # distribution priced at five numbers, not five numbers.
    by: dict = {}
    for r in rows:
        by.setdefault((r["player"], r["period"], r["market"]), []).append((r["line"], r["ours"]))
    for seq in by.values():
        seq.sort()
        assert all(a[1] >= b[1] for a, b in zip(seq, seq[1:])), seq
    # As of: a read for week 3 is made on two 2026 games, never five.
    assert all(r["games"] <= int(r["period"]) - 1 + 17 for r in rows)
    assert max(r["games"] for r in rows if r["period"] == "001") <= 17


def test_the_report_says_claimed_against_landed_and_changes_nothing():
    SR.clear_cache()
    path, conn = _history()
    rows = SRF.replay(conn, "nfl", [2026], markets=("rush_att",))
    scored = SRF.score(rows)
    assert set(scored) == {"rush_att"} and {"book", "all"} <= set(scored["rush_att"])
    book = scored["rush_att"]["book"]
    assert book["n"] == sum(1 for r in rows if r["arm"] == "book")
    assert 0.0 <= book["brier"]["ours"] <= 1.0 and 0.0 <= book["brier"]["last8"] <= 1.0
    assert all(0.0 <= c["said"] <= 1.0 and 0.0 <= c["landed"] <= 1.0 for c in book["calibration"])
    txt = SRF.report(scored, "test")
    assert "rush_att" in txt and "calibration" in txt and "Nothing here changes the model" in txt
    assert "last8" in txt and "ours" in txt
    out = _SANDBOX / "fit.json"
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = SRF.main(["--sport", "nfl", "--seasons", "2026", "--db", path, "--markets", "rush_att",
                         "--limit", "40", "--json", str(out)])
    assert code == 0 and "rush_att" in buf.getvalue() and out.exists()
    import json
    saved = json.loads(out.read_text())
    assert saved["sport"] == "nfl" and saved["seasons"] == [2026] and "rush_att" in saved["scored"]
    assert saved["reads"] <= 40, "the limit caps the reads"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
