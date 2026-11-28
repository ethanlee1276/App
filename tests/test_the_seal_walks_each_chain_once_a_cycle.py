"""The loop's seal step walks each chain once a cycle (launch._seal_forecasts,
engine/ledger.verify_forecast_log's ``drift``, record_heads).

The `forecast-seal` step took 9.8 to 13.5 seconds of every cycle on 9
November. It verified both chains end to end, the forecast chain together
with a walk of the whole journal for drift that nothing in the step reads;
then `record_heads` sealed and verified both chains again, end to end, and
only then saw that today's heads were already written, which they are on
every cycle but the day's first. What these hold:

  * the day's heads are written once, from chains sealed and walked when
    they are written; on every other cycle `record_heads` walks nothing;
  * ``drift=False`` answers the chain's own question exactly as the full
    walk does (whole, broken and where), without the drift counts;
  * the seal step asks for the chain only, still says loudly when it breaks,
    and the record export, the daily heads, the nightly report and the
    doctor still count the drift.

Fixture ledgers in a temp directory, never the box's.

Run directly: `python3 tests/test_the_seal_walks_each_chain_once_a_cycle.py`
"""
import contextlib
import io
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import ledger                                          # noqa: E402


def _ledger():
    path = Path(tempfile.mkdtemp()) / "ledger.db"
    conn = ledger.connect(path)
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1)
    return conn, path


def _bet(conn, player="A Judge", status="won", line=1.5):
    cur = conn.execute(
        "INSERT INTO bets (ts, sport, date, player, market, side, line, odds, hit_prob, "
        "edge, stake_units, stake_dollars, status, actual, pnl_units, pnl_dollars, category, "
        "lead_min) VALUES ('2026-09-01T16:00:00', 'mlb', '2026-09-01', ?, 'hits', 'OVER', ?, -110, 0.6, "
        "0.05, 1.0, 10.0, ?, 2.0, 0.91, 9.09, 'main', 180)", (player, line, status))
    conn.commit()
    return cur.lastrowid


@contextlib.contextmanager
def _counting():
    names = ("verify_forecast_log", "verify_audit_log", "seal_forecasts", "seal_audit")
    keep = {n: getattr(ledger, n) for n in names}
    calls = {n: 0 for n in names}

    def wrap(n):
        def f(*a, **k):
            calls[n] += 1
            return keep[n](*a, **k)
        return f
    try:
        for n in names:
            setattr(ledger, n, wrap(n))
        yield calls
    finally:
        for n, f in keep.items():
            setattr(ledger, n, f)


def test_the_days_heads_are_walked_when_written_and_not_on_every_cycle():
    conn, _ = _ledger()
    _bet(conn)
    with _counting() as calls:
        head = ledger.record_heads(conn, post=False)
    assert head and head["forecast_n"] == 1 and head["ok"] and head["drifted"] == 0
    assert calls == {"verify_forecast_log": 1, "verify_audit_log": 1, "seal_forecasts": 1, "seal_audit": 1}, calls
    _bet(conn, player="B Witt")
    with _counting() as calls:
        assert ledger.record_heads(conn, post=False) is None, "once a day"
    assert calls == {"verify_forecast_log": 0, "verify_audit_log": 0, "seal_forecasts": 0, "seal_audit": 0}, calls
    conn.close()


def test_the_chain_alone_answers_as_the_full_walk_does():
    conn, _ = _ledger()
    for i in range(4):
        _bet(conn, player=f"P{i}")
    ledger.seal_forecasts(conn)
    full, chain = ledger.verify_forecast_log(conn), ledger.verify_forecast_log(conn, drift=False)
    assert full["ok"] and chain["ok"] and full["n"] == 4
    assert {k: v for k, v in full.items() if k not in ("drifted", "unexplained", "missing")} == chain
    assert "drifted" not in chain and full["drifted"] == 0
    conn.execute("UPDATE forecast_log SET line = line + 1 WHERE seq = 3")    # a hand edit under the chain
    conn.commit()
    full, chain = ledger.verify_forecast_log(conn), ledger.verify_forecast_log(conn, drift=False)
    assert not chain["ok"] and chain["broken_at"] == 3 and chain["verified_through"] == 2
    assert chain == full, "a broken chain answers the same either way"
    conn.close()


def test_the_seal_step_asks_for_the_chain_only_and_still_says_when_it_breaks():
    import launch
    src = (ROOT / "launch.py").read_text(encoding="utf-8")
    blk = src[src.index("def _seal_forecasts("):]
    blk = blk[:blk.index("\ndef ", 1)]
    assert "_led.verify_forecast_log(conn, drift=False)" in blk
    assert blk.count("verify_forecast_log(") == 1 and blk.count("verify_audit_log(") == 1
    conn, path = _ledger()
    _bet(conn)
    _bet(conn, player="B Witt")
    ledger.seal_forecasts(conn)
    ledger.record_heads(conn, post=False)                     # today's heads already written
    conn.execute("UPDATE forecast_log SET line = line + 1 WHERE seq = 2")
    conn.commit()
    conn.close()
    from engine import discordfeed, witness
    keep = (ledger.connect, witness.run, discordfeed.run)
    out = io.StringIO()
    try:
        ledger.connect = lambda *a, **k: keep[0](path)
        witness.run = lambda c: {}
        discordfeed.run = lambda c: {}
        with _counting() as calls, contextlib.redirect_stdout(out):
            launch._seal_forecasts(quiet=True)
    finally:
        ledger.connect, witness.run, discordfeed.run = keep
    assert "FORECAST LOG BROKEN at #2" in out.getvalue(), out.getvalue()
    assert calls["verify_forecast_log"] == 1 and calls["verify_audit_log"] == 1, calls


def test_the_drift_count_is_still_asked_where_it_is_read():
    src = (ROOT / "engine" / "ledger.py").read_text(encoding="utf-8")
    assert '"forecast_log": (seal_forecasts(conn), verify_forecast_log(conn))[1]' in src, "the record export"
    rh = src[src.index("def record_heads("):src.index("def integrity_report(")]
    assert "verify_forecast_log(conn)," in rh and "drift=False" not in rh, "the daily heads"
    ir = src[src.index("def integrity_report("):src.index("def _prereg_block(")]
    assert '"forecast": verify_forecast_log(conn)' in ir, "the nightly report"
    doc = (ROOT / "doctor.py").read_text(encoding="utf-8")
    assert "v = ledger.verify_forecast_log(c)\n" in doc, "the doctor"


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
