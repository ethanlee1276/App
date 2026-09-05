"""Every budget verdict is written down; a pull that bought nothing does
not reset the clock; the books' long-form school names resolve.

Ethan's box, 2026-09-05, opening Saturday of the college season: 63
board-line pulls, zero player-quote pulls, and no record of why — the
refresh loop runs quiet and the journal holds only web requests. Its
6pm "full pull" found every game kicked off, bought no player quotes,
and still stamped the sport's clock because the cheap board request in
the same build moved the quota stamp. And four of the 76 odds events
named schools the way books do, which ESPN shortens.
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import oddsbudget as B                                      # noqa: E402
from engine.sources import cfbdata                                      # noqa: E402

LAUNCH = (ROOT / "launch.py").read_text()


# --- the ledger ------------------------------------------------------------
def test_every_verdict_is_written_with_its_reason_and_read_back_in_order():
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "decisions.jsonl"
        B.log_decision("cfb", False, "next odds refresh in 393s", credits=63, path=f, now=1000.0, games=25)
        B.log_decision("cfb_lines", True, "refreshing odds", credits=3, path=f, now=1001.0)
        B.log_decision(None, False, "quota low", path=f, now=1002.0, kind="bought")
        rows = B.decisions(path=f)
        assert [r["lane"] for r in rows] == ["cfb", "cfb_lines", "_all"]
        assert rows[0]["ok"] is False and rows[0]["credits"] == 63 and rows[0]["games"] == 25
        assert rows[0]["reason"] == "next odds refresh in 393s" and rows[0]["iso"].startswith("1970-01-01T")
        assert rows[1]["ok"] is True and "credits" in rows[1]
        assert rows[2]["kind"] == "bought" and "credits" not in rows[2]
        assert [r["lane"] for r in B.decisions(path=f, since=1001.0)] == ["cfb_lines", "_all"]
        assert [r["lane"] for r in B.decisions(path=f, lane="cfb")] == ["cfb"]
        assert B.decisions(path=Path(d) / "missing.jsonl") == []


def test_the_ledger_is_bounded_and_never_raises():
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "decisions.jsonl"
        # A season of quiet cycles: 30,000 rows is past the size cap.
        f.write_text("\n".join(json.dumps({"ts": i, "lane": "l", "ok": True, "reason": "next odds refresh in 393s"})
                                for i in range(30_000)) + "\n")
        assert f.stat().st_size > 1_500_000
        B.log_decision("cfb", True, "r", path=f)
        lines = f.read_text().splitlines()
        assert len(lines) == B.DECISIONS_KEEP and lines[-1].endswith('"reason": "r"}')
        assert json.loads(lines[0])["ts"] == 30_000 - B.DECISIONS_KEEP + 1, "the oldest rows went, the newest stayed"
        B.log_decision("cfb", True, "r", path=Path("/proc/nope/decisions.jsonl"))   # unwritable: no raise


# --- the stamp needs a purchase ---------------------------------------------
def _state_file(d, seen="2026-09-05T18:00:00"):
    p = Path(d) / "odds_budget.json"
    st = B.BudgetState(remaining=60000, last_seen_iso=seen)
    B.save(st, p)
    return p


def test_a_pull_that_bought_nothing_leaves_the_clock_and_touchpoint_alone():
    with tempfile.TemporaryDirectory() as d:
        p = _state_file(d)
        st = B.load(p); st.sport_last_refresh["cfb"] = 100.0; st.retry_after_ts = 999.0; B.save(st, p)
        landed = B.paid_pull_result("2026-09-05T17:00:00", path=p, now=5000.0, sport="cfb", bought_enough=False)
        assert landed is True, "the quota stamp did move — that is still 'landed'"
        st = B.load(p)
        assert st.sport_ts("cfb") == 100.0, "the clock the next full pull waits on is untouched"
        assert st.last_refresh_ts != 5000.0
        assert st.retry_after_ts == 0.0, "but a failed-pull cooldown is not set either — nothing failed"
        assert not st.sport_touchpoint.get("cfb"), "and the touchpoint is not claimed"


def test_a_pull_that_bought_enough_stamps_as_before():
    with tempfile.TemporaryDirectory() as d:
        p = _state_file(d)
        landed = B.paid_pull_result("2026-09-05T17:00:00", path=p, now=5000.0, sport="cfb", bought_enough=True)
        st = B.load(p)
        assert landed and st.sport_ts("cfb") == 5000.0 and st.last_refresh_ts == 5000.0
        # the default is unchanged for every caller that does not measure
        p2 = _state_file(d)
        B.paid_pull_result("2026-09-05T17:00:00", path=p2, now=6000.0, sport="nfl")
        assert B.load(p2).sport_ts("nfl") == 6000.0


def test_a_pull_that_never_landed_still_sets_the_retry_cooldown():
    with tempfile.TemporaryDirectory() as d:
        p = _state_file(d, seen="same")
        assert B.paid_pull_result("same", path=p, now=5000.0, sport="cfb", bought_enough=False) is False
        assert B.load(p).retry_after_ts == 5000.0 + B.FAILED_PULL_RETRY_S


# --- the launcher --------------------------------------------------------------
def _fn(src, name):
    i = src.index(f"def {name}(")
    j = src.find("\ndef ", i + 10)
    return src[i:j if j != -1 else len(src)]


def test_the_launcher_logs_every_verdict_measures_the_purchase_and_shows_the_ledger():
    body = _fn(LAUNCH, "_odds_affordable")
    assert "log_decision(sport, ok, reason," in body and "kickoffs=len(kicks)" in body
    assert body.index("if not quiet:") < body.index("log_decision("), "printed or not, it is written"
    assert "\n    try:\n        from engine.oddsbudget import log_decision\n        log_decision(sport, ok, reason," in body, \
        "the ledger call sits at function level, not under the quiet check"
    cfb = _fn(LAUNCH, "refresh_cfb")
    assert 'before_spent = _spent_so_far("cfb") if spend else 0' in cfb
    assert 'bought=(_spent_so_far("cfb") - before_spent) if spend else None' in cfb
    assert "expect=CFB_LINES_COST + CFB_PLAYER_EVENT_COST" in cfb
    fin = _fn(LAUNCH, "_finish_paid_pull")
    assert "enough = bought is None or expect is None or bought >= expect" in fin
    assert "paid_pull_result(before_seen, sport=sport, bought_enough=enough)" in fin
    assert 'kind="bought"' in fin
    doc = _fn(LAUNCH, "odds_doctor")
    assert "oddsbudget.decisions(since=time.time() - 24 * 3600)" in doc and "latest per lane" in doc
    assert "CFB_PLAYER_EVENT_COST = 5" in LAUNCH


def test_the_player_event_cost_is_the_builds_own():
    import cfb_build
    i = LAUNCH.index("CFB_PLAYER_EVENT_COST = ")
    val = int(LAUNCH[i + len("CFB_PLAYER_EVENT_COST = "):].split()[0])
    assert val == cfb_build.CREDITS_PER_EVENT == len(cfb_build.PLAYER_MARKETS)


# --- the four schools --------------------------------------------------------
TEAMS = {
    "APP": {"name": "App State Mountaineers", "nick": "Mountaineers"},
    "USM": {"name": "Southern Miss Golden Eagles", "nick": "Golden Eagles"},
    "CIT": {"name": "The Citadel Bulldogs", "nick": "Bulldogs"},
    "RGV": {"name": "UTRGV Vaqueros", "nick": "Vaqueros"},
    "UGA": {"name": "Georgia Bulldogs", "nick": "Bulldogs"},
}


def test_the_books_long_form_names_resolve_and_nothing_else_moves():
    lk = cfbdata.team_lookup(TEAMS)
    assert cfbdata.resolve_team("Appalachian State Mountaineers", lk) == "APP"
    assert cfbdata.resolve_team("Southern Mississippi Golden Eagles", lk) == "USM"
    assert cfbdata.resolve_team("Citadel Bulldogs", lk) == "CIT"
    assert cfbdata.resolve_team("UT Rio Grande Valley Vaqueros", lk) == "RGV"
    assert cfbdata.resolve_team("App State Mountaineers", lk) == "APP", "ESPN's own spelling still resolves first"
    assert cfbdata.resolve_team("Georgia Bulldogs", lk) == "UGA"
    assert cfbdata.resolve_team("Nowhere State Nobodies", lk) == "", "a miss is still a counted miss"
    assert cfbdata.resolve_team("Citadel Bulldogs", {}) == "", "an alias needs the lookup to know the school"


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
