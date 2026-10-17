"""Every board has an age limit, and the Status page leads with a verdict.

Audit 2026-09-30, F-13 / O17 (roadmap #26). No board-age policy existed:
the server served whatever was on disk, the heartbeat said ok over a board
a failing build kept "keeping", an off-season NFL board printed FROZEN
~7,000 times, and the Status page made a reader interpret a heartbeat, a
cycle median and sixteen ages to learn whether anything was wrong — while
calling an off-season board "never built" and leaving the Lab off entirely.
"""

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
APP = (ROOT / "web" / "js" / "app.js").read_text()


def test_the_policy_names_every_board_and_an_offseason_board_is_never_stale():
    from engine import freshness as F
    assert F.board_key("recommendations.json") == "nfl"
    assert F.board_key("mlb_recommendations.json") == "mlb"
    assert F.board_key("futures_nfl.json") == "futures" and F.board_key("cfb.json") == "cfb"
    assert F.max_age_h("backtest.json") == 192 and F.max_age_h("unknown.json") == F.DEFAULT_MAX_AGE_H
    assert F.verdict("cfb", 3 * 3600)["stale"] is True
    assert F.verdict("cfb", 3600)["stale"] is False
    off = F.verdict("nfl", 90 * 86400, offseason=True)
    assert off["stale"] is False and off["offseason"] is True
    assert F.verdict("nfl", None)["stale"] is False


def test_the_server_says_when_a_board_is_over_age():
    import server
    assert server.stale_headers("cfb.json", time.time() - 3 * 3600) == [("X-Board-Stale-Hours", "3.0")]
    assert server.stale_headers("cfb.json", time.time() - 600) == []
    assert server.stale_headers("cfb.json", None) == []
    src = (ROOT / "server.py").read_text()
    assert src.count("+ stale_headers(") == 2, "both board paths carry the header"


def test_the_heartbeat_carries_the_verdict_and_the_frozen_warning_is_quiet_off_season():
    import launch
    tmp = Path(tempfile.mkdtemp()) / "nfl.json"
    tmp.write_text('{"status": "offseason", "most_likely": []}')
    old = time.time() - 40 * 86400
    os.utime(tmp, (old, old))
    real_files, real_full = dict(launch.BOARD_FILES), launch._full_copy
    launch.BOARD_FILES["nfl"] = str(tmp)
    launch._full_copy = lambda p: p
    launch._STALE_SAID.pop("nfl", None)
    try:
        import io, contextlib
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            launch._note_board("nfl", True)
        run = launch._BOARD_RUNS["nfl"]
        assert run["offseason"] is True and run["stale"] is False
        assert "FROZEN" not in out.getvalue(), "an off-season board is meant to sit still"
        tmp.write_text('{"status": "ok", "most_likely": []}')
        os.utime(tmp, (old, old))
        launch._STALE_SAID.pop("nfl", None)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            launch._note_board("nfl", True)
        assert launch._BOARD_RUNS["nfl"]["stale"] is True
        assert "FROZEN" in out.getvalue()
    finally:
        launch.BOARD_FILES.clear(); launch.BOARD_FILES.update(real_files)
        launch._full_copy = real_full
        launch._BOARD_RUNS.pop("nfl", None)


def test_the_status_page_leads_with_a_verdict_and_says_off_season():
    i = APP.index("async function renderStatus(")
    body = APP[i:APP.index("\n}\n", i)]
    assert body.index('class="st-verdict') < body.index("buildsCardHTML(hb)"), "the verdict comes first"
    assert "Everything is running and every board is current." in body
    assert "The refresh loop is not running" in body
    assert '["off-season", "off"]' in body and body.index('"off-season"') < body.index('"never built"')
    assert '<details class="st-mech">' in body, "the mechanics sit behind a disclosure"
    assert '["backtest.json", "The Lab (weekly backtest)"]' in APP
    assert '"backtest.json": 192' in APP


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
