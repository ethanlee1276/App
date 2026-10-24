"""Every journaled row says which code and which model files priced it,
and a game bet keeps the raw inputs a prop keeps.

Audit 2026-09-30, B8-1 / B8-2 (roadmap #23). No row carried the commit or
the model-file digest that priced it: `MODEL_ERAS` is hand-kept and its own
comment admits one era went unrecorded for eleven days. And game bets stored
none of `raw_prob` / `cal_temp`, so a game pick could not be re-derived the
way a prop can. Now:

  * `ledger.model_sha()` is "<commit>[+dirty]:<model-files digest>", and a
    per-connection TEMP trigger stamps it on EVERY insert into `bets` that
    did not set it itself — thirteen insert paths today and whatever gets
    added next, without anyone having to remember;
  * the stamp is not an audited field, so stamping never opens an audit row;
  * game bets store `raw_prob` (the engine's own number before the market
    blend) and `cal_temp` (the shrink in force).
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _conn():
    from engine import ledger as L
    return L.connect(Path(tempfile.mkdtemp()) / "l.db")


def test_the_sha_names_code_and_models():
    from engine import ledger as L
    sha = L.model_sha()
    assert ":" in sha, sha
    code, models = sha.split(":", 1)
    assert len(models) == 8 and all(c in "0123456789abcdef" for c in models)


def test_the_models_digest_moves_when_a_model_file_does():
    from engine import ledger as L
    d = Path(tempfile.mkdtemp())
    (d / "calibration.json").write_text('{"t": 1.0}')
    a = L.models_digest(d)
    (d / "calibration.json").write_text('{"t": 1.1}')
    os.utime(d / "calibration.json", ns=(1, 10 ** 18))
    b = L.models_digest(d)
    assert a != b and len(a) == 8
    assert L.models_digest(Path(tempfile.mkdtemp())) == L.models_digest(Path(tempfile.mkdtemp()))


def test_any_insert_is_stamped_and_an_explicit_stamp_is_kept():
    from engine import ledger as L
    conn = _conn()
    import datetime as _dt
    now = _dt.datetime.utcnow().isoformat(timespec="seconds")
    conn.execute("INSERT INTO bets (ts, sport, date, player, market, side, line, odds, status) "
                 "VALUES (?,'nfl','2026-09-01','A','m','OVER',1.5,-110,'open')", (now,))
    conn.execute("INSERT INTO bets (ts, sport, date, player, market, side, line, odds, status, model_sha) "
                 "VALUES (?,'nfl','2026-09-01','B','m','OVER',1.5,-110,'open','abc:12345678')", (now,))
    # A row copied in from an old table was not priced by this code.
    conn.execute("INSERT INTO bets (ts, sport, date, player, market, side, line, odds, status) "
                 "VALUES ('2025-01-01T00:00:00','nfl','2025-01-01','C','m','OVER',1.5,-110,'open')")
    got = dict(conn.execute("SELECT player, model_sha FROM bets").fetchall())
    assert got["A"] == L.model_sha() and got["B"] == "abc:12345678"
    assert got["C"] is None, "an old row was told today's code priced it"
    n = conn.execute("SELECT count(*) FROM bets_audit").fetchone()[0]
    assert n == 0, "stamping opened an audit row"
    conn.close()


def test_a_game_bet_keeps_its_raw_inputs():
    from engine import ledger as L
    conn = _conn()
    L.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    result = {"sport": "mlb", "date": "2026-07-24", "recommendations": [], "game_bets": [
        {"bet_type": "moneyline", "recommended": True, "pick": "NYY", "odds": -125,
         "win_prob": 0.60, "edge": 0.045, "confidence": 6.0, "grade": "Play",
         "stake_units": 1.0, "engine_raw_prob": 0.6312, "cal_temp": 0.8}]}
    assert L.log_recommendations(conn, result) == 1
    r = conn.execute("SELECT raw_prob, cal_temp, model_sha FROM bets").fetchone()
    assert r["raw_prob"] == 0.6312 and r["cal_temp"] == 0.8
    assert r["model_sha"] == L.model_sha()
    conn.close()


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
