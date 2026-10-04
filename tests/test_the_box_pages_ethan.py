"""Evidence off the single disk, and failures that reach a person.

Audit 2026-09-30, P1-12 and P1-13 (roadmap #6):

  * the nightly backup kept accounts.db and ledger.db and skipped
    history.db — the harvested closes CLV is measured against — and the
    free line history, Zeno's book, the feed state, the odds budget and
    the daily chain heads. One dead disk and the CLV evidence was gone;
  * nobody was told about anything: a dead loop, a failed unit or a stale
    heartbeat were visible only to someone already looking.

Now: the backup names every one of them; the heartbeat pings a
dead-man's switch (`QB_HEALTHCHECK_URL`) only on a clean sweep; a failed
unit emails (`qellys-alert@.service` → `engine.alert`); and the doctor
fails a heartbeat older than three cycles.
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BACKUP = (ROOT / "deploy" / "backup.sh").read_text()


def test_the_backup_names_the_clv_evidence_and_the_rest():
    for db in ("data/accounts.db", "data/ledger.db", "data/history.db", "data/zeno.db"):
        assert f'"{db}"' in BACKUP, db
    for f in ("data/cache/line_history.jsonl", "data/cache/odds_budget.json",
              "data/forecast_heads.jsonl", "data/feedstate"):
        assert f in BACKUP, f
    assert "QB_BACKUP_HISTORY" in BACKUP, "history.db can be switched off on a small disk"


def test_the_heartbeat_pings_only_on_a_clean_sweep():
    import launch
    calls = []
    saved = launch._urlopen_ping
    launch._urlopen_ping = lambda url: calls.append(url)
    old = os.environ.get("QB_HEALTHCHECK_URL")
    try:
        os.environ.pop("QB_HEALTHCHECK_URL", None)
        launch._LAST_PING[0] = 0.0
        launch._ping_healthcheck("ran", {})
        assert calls == [], "no URL, no ping"
        os.environ["QB_HEALTHCHECK_URL"] = "https://hc.example/abc"
        launch._ping_healthcheck("skipped", {})
        launch._ping_healthcheck("ran", {"nfl": "boom"})
        assert calls == [], "a skipped or failed sweep must not tell the switch all is well"
        launch._ping_healthcheck("ran", {})
        assert calls == ["https://hc.example/abc"]
        launch._ping_healthcheck("ran", {})
        assert len(calls) == 1, "throttled: one ping per few minutes is enough"
    finally:
        launch._urlopen_ping = saved
        if old is None:
            os.environ.pop("QB_HEALTHCHECK_URL", None)
        else:
            os.environ["QB_HEALTHCHECK_URL"] = old
    import inspect
    assert "_ping_healthcheck(swept, dict(_STEP_FAIL))" in inspect.getsource(launch._write_heartbeat)


def test_a_failed_unit_emails_through_the_mailer():
    unit = (ROOT / "deploy" / "qellys-alert@.service").read_text()
    assert "engine.alert" in unit and "%i" in unit
    for name in ("qellys.service", "qellys-update.service"):
        assert "OnFailure=qellys-alert@%n.service" in (ROOT / "deploy" / name).read_text(), name
    from engine import alert
    sent = []
    got = alert.run("qellys.service", send=lambda to, subj, text: sent.append((to, subj, text)),
                    env={"QB_ALERT_EMAIL": "owner@example.invalid"}, journal=lambda u: "line 1\nline 2")
    assert got == "sent" and sent and "qellys.service" in sent[0][1]
    assert "line 2" in sent[0][2]
    assert alert.run("qellys.service", send=lambda *a: None, env={},
                     journal=lambda u: "") == "no-address"


def test_the_doctor_fails_a_stale_heartbeat():
    import doctor
    tmp = Path(tempfile.mkdtemp()) / "heartbeat.json"
    tmp.write_text(json.dumps({"at_epoch": time.time() - 4 * 3600, "interval_s": 60,
                               "cycle_p50_s": 300}))
    rep = doctor.Report()
    doctor.check_heartbeat(rep, path=tmp)
    assert rep.checks[-1]["status"] == doctor.FAIL, rep.checks[-1]
    tmp.write_text(json.dumps({"at_epoch": time.time() - 60, "interval_s": 60,
                               "cycle_p50_s": 300}))
    rep = doctor.Report()
    doctor.check_heartbeat(rep, path=tmp)
    assert rep.checks[-1]["status"] == doctor.OK, rep.checks[-1]
    assert doctor.check_heartbeat in doctor.DATA_CHECKS


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
