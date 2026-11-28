"""An FBS team's buy game is stored so bets grade, and stays out of the fit.

Ethan, 2026-09-06, after the backlog clear: 179 college bets stuck with
"no stat line", most of them on games an FBS side played against an FCS
opponent — UAPB@MIZ, BCU@UCF, EIU@MINN, MASS@RUTG. The board prices
every game an FBS team plays, and `cfbfastr.parse_schedule` stored only
FBS-vs-FBS, so those bets had no result row to grade against and never
would.

Both sides being FBS is the right rule for the FIT and the wrong one for
the LEDGER. The fit is protected by the KEY instead: an FCS side has no
FBS abbreviation and lands as `espn:<id>`, which is what
`teamrates.compute_team_ratings` already excludes on — its docstring
names the 70-0 buy game that was an FBS team's whole rating for a
fortnight — and what `cfb.ratings.fit_from_history` now excludes on too.

Run directly: `python3 tests/test_cfb_buy_games.py`
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db, ledger, teamrates
from engine.cfb import ratings as cfbratings
from engine.sources import cfbfastr

IDS = {"61": "UGA", "142": "MIZ", "194": "OSU", "2306": "KU"}


def _row(home_id, away_id, hs, as_, home_div="fbs", away_div="fbs",
         date="2026-09-05", gid="1"):
    return {"home_division": home_div, "away_division": away_div,
            "home_points": str(hs), "away_points": str(as_),
            "home_id": home_id, "away_id": away_id, "game_id": gid,
            "start_date": f"{date}T18:00:00.000Z"}


def test_a_buy_game_is_stored_with_the_fcs_side_keyed_espn():
    out = cfbfastr.parse_schedule(
        [_row("142", "9999", 52, 3, away_div="fcs")], 2026, id_to_abbr=IDS)
    assert out["games"], out["skipped"]
    g = out["games"][0]
    assert (g["home"], g["away"]) == ("MIZ", "espn:9999")
    assert g["game_id"] == "espn:9999@MIZ"
    assert (g["home_score"], g["away_score"]) == (52, 3)


def test_a_game_with_no_fbs_side_is_still_nothing_we_price():
    out = cfbfastr.parse_schedule(
        [_row("8001", "9999", 21, 20, home_div="fcs", away_div="fcs")],
        2026, id_to_abbr=IDS)
    assert out["games"] == []
    assert out["skipped"] == {"no FBS side": 1}


def test_an_unmapped_fbs_school_no_longer_takes_a_real_game_with_it():
    """It was dropped outright; now it is stored under the fallback key
    and `ingest.remap_cfb_team_keys` repairs it when the map arrives."""
    out = cfbfastr.parse_schedule([_row("61", "7777", 30, 24)], 2026,
                                  id_to_abbr=IDS)
    assert len(out["games"]) == 1
    assert out["games"][0]["away"] == "espn:7777"


def _fill(conn, n_real, n_buy):
    rows = []
    for i in range(n_real):
        rows.append({"sport": "cfb", "season": 2025, "period": f"2025-09-{i % 28 + 1:02d}",
                     "game_id": f"r{i}", "home": "UGA" if i % 2 else "OSU",
                     "away": "MIZ" if i % 2 else "KU",
                     "home_score": 28 + (i % 7), "away_score": 21 + (i % 5)})
    for i in range(n_buy):
        rows.append({"sport": "cfb", "season": 2025, "period": f"2025-08-{i % 28 + 1:02d}",
                     "game_id": f"b{i}", "home": "UGA", "away": f"espn:{9000 + i}",
                     "home_score": 63, "away_score": 3})
    conn = conn
    db.upsert_games(conn, rows)
    return conn


def test_the_fitted_constants_are_identical_with_and_without_buy_games():
    """The invariance that makes storing them safe. A 63-3 blowout would
    lift the scoring baseline and widen the margin spread — the two
    numbers the college stake depends on."""
    clean = db.connect(os.path.join(tempfile.mkdtemp(), "a.db"))
    dirty = db.connect(os.path.join(tempfile.mkdtemp(), "b.db"))
    _fill(clean, 60, 0)
    _fill(dirty, 60, 40)
    plain = teamrates.compute_team_ratings(clean, "cfb", shrink=8.0)
    a = cfbratings.fit_from_history(clean, plain, min_games=10)
    b = cfbratings.fit_from_history(dirty, plain, min_games=10)
    assert a.games == b.games == 60, (a.games, b.games)
    for field in ("margin_sd", "total_sd", "team_total_sd", "home_field"):
        assert getattr(a, field) == getattr(b, field), field


def test_a_table_of_only_buy_games_reports_too_few_rather_than_fitting_on_them():
    conn = db.connect(os.path.join(tempfile.mkdtemp(), "c.db"))
    _fill(conn, 0, 40)
    got = cfbratings.fit_from_history(conn, {}, min_games=10)
    assert got.games == 0, got
    assert "needed to fit" in got.note


def test_a_bet_on_the_fbs_side_of_a_buy_game_settles():
    hist = db.connect(os.path.join(tempfile.mkdtemp(), "h.db"))
    book = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    db.upsert_games(hist, cfbfastr.parse_schedule(
        [_row("142", "9999", 52, 3, away_div="fcs", date="2026-09-05")],
        2026, id_to_abbr=IDS)["games"])
    book.executemany(
        "INSERT INTO bets (ts, sport, date, player, market, side, line, book, odds, "
        "stake_units, stake_dollars, status, category) VALUES "
        "(?,'cfb','2026-09-05',?,?,?,?,'DK',-110,1.0,10.0,'open','main')",
        [("2026-09-05T12:00:00", "MIZ", "spread", "OVER", -38.5),
         ("2026-09-05T12:00:00", "MIZ", "moneyline", "OVER", 0.5),
         ("2026-09-05T12:00:00", "MIZ", "team_total", "OVER", 44.5)])
    book.commit()
    assert ledger.settle_from_history(book, hist, "cfb") == 3
    got = {r["market"]: r["status"] for r in
           book.execute("SELECT market, status FROM bets")}
    assert got == {"spread": "won", "moneyline": "won", "team_total": "won"}, got



def test_a_total_on_a_buy_game_settles_by_naming_either_side():
    """The row is keyed `espn:9999@MIZ` and the board bet `UAPB@MIZ`, so
    the exact key can never match. The date and one named side identify
    the fixture."""
    hist = db.connect(os.path.join(tempfile.mkdtemp(), "h.db"))
    book = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    db.upsert_games(hist, cfbfastr.parse_schedule(
        [_row("142", "9999", 52, 3, away_div="fcs", date="2026-09-05")],
        2026, id_to_abbr=IDS)["games"])
    book.execute(
        "INSERT INTO bets (ts, sport, date, player, market, side, line, book, odds, "
        "stake_units, stake_dollars, status, category) VALUES "
        "(?,'cfb','2026-09-05','UAPB@MIZ','total','OVER',48.5,'DK',-110,1.0,10.0,'open','main')",
        ("2026-09-05T12:00:00",))
    book.commit()
    assert ledger.settle_from_history(book, hist, "cfb") == 1
    row = book.execute("SELECT status, actual FROM bets").fetchone()
    assert row["status"] == "won" and row["actual"] == 55.0, dict(row)


def test_an_ambiguous_matchup_key_is_refused_rather_than_guessed():
    """Two fixtures on one date both naming a side of the key is not a
    fixture — it is a coin flip, and a wrong grade is worse than an open
    bet because nothing downstream can tell it from a right one."""
    hist = db.connect(os.path.join(tempfile.mkdtemp(), "h.db"))
    book = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    db.upsert_games(hist, [
        {"sport": "cfb", "season": 2026, "period": "2026-09-05", "game_id": "espn:9999@MIZ",
         "home": "MIZ", "away": "espn:9999", "home_score": 52, "away_score": 3},
        {"sport": "cfb", "season": 2026, "period": "2026-09-05", "game_id": "UAPB@OSU",
         "home": "OSU", "away": "UAPB", "home_score": 40, "away_score": 10}])
    book.execute(
        "INSERT INTO bets (ts, sport, date, player, market, side, line, book, odds, "
        "stake_units, stake_dollars, status, category) VALUES "
        "(?,'cfb','2026-09-05','UAPB@MIZ','total','OVER',48.5,'DK',-110,1.0,10.0,'open','main')",
        ("2026-09-05T12:00:00",))
    book.commit()
    assert ledger.settle_from_history(book, hist, "cfb") == 0
    assert book.execute("SELECT status FROM bets").fetchone()["status"] == "open"


def test_an_exact_key_still_wins_and_the_fallback_never_runs_for_it():
    hist = db.connect(os.path.join(tempfile.mkdtemp(), "h.db"))
    book = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    db.upsert_games(hist, [
        {"sport": "cfb", "season": 2026, "period": "2026-09-05", "game_id": "KU@UGA",
         "home": "UGA", "away": "KU", "home_score": 24, "away_score": 20},
        {"sport": "cfb", "season": 2026, "period": "2026-09-05", "game_id": "MIZ@OSU",
         "home": "OSU", "away": "MIZ", "home_score": 70, "away_score": 0}])
    book.execute(
        "INSERT INTO bets (ts, sport, date, player, market, side, line, book, odds, "
        "stake_units, stake_dollars, status, category) VALUES "
        "(?,'cfb','2026-09-05','KU@UGA','total','UNDER',49.5,'DK',-110,1.0,10.0,'open','main')",
        ("2026-09-05T12:00:00",))
    book.commit()
    assert ledger.settle_from_history(book, hist, "cfb") == 1
    row = book.execute("SELECT status, actual FROM bets").fetchone()
    assert row["actual"] == 44.0 and row["status"] == "won", dict(row)


def test_a_box_whose_teams_feed_never_answered_still_fits():
    """teamrates' own docstring: "on a box where the teams feed never
    answered every key is a fallback key". A backfill run without the
    map keys BOTH sides `espn:<id>`, so an unconditional filter would
    throw the entire history away and put college back on the prior —
    the state this module exists to get off. Caught by the suite before
    it shipped, 2026-09-06."""
    conn = db.connect(os.path.join(tempfile.mkdtemp(), "d.db"))
    rows = []
    for i in range(60):
        rows.append({"sport": "cfb", "season": 2025,
                     "period": f"2025-09-{i % 28 + 1:02d}", "game_id": f"u{i}",
                     "home": f"espn:{100 + i % 12}", "away": f"espn:{200 + i % 12}",
                     "home_score": 28 + (i % 7), "away_score": 21 + (i % 5)})
    db.upsert_games(conn, rows)
    got = cfbratings.fit_from_history(conn, {}, min_games=10)
    assert got.games == 60, got

if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
