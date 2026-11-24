"""A designation filed more than a year ago is nobody's status now, and an old filing says its year.

On 24 November 2026 ESPN's college football feed held one row in the whole league: "Kahleil Jackson (undisclosed)
is inactive for Saturday's game against Vanderbilt", Out for Florida, filed 21 November 2020. The Injuries page kept
every designation however old and printed a date past two weeks as "Nov 21", so a six-year-old line read as this
week's. A row past a year is dropped from the page and from the picks' injury list (espninjuries
.drop_old_designations), and a filing from another year shows that year.

Offline. Run directly: `python3 tests/test_a_years_old_injury_is_nobodys_status.py`
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine.sources import espninjuries as E                 # noqa: E402
from engine.sources import injuries as I                     # noqa: E402

NOW = E._parse_iso_ts("2026-11-24T03:00Z")
JACKSON = {"player": "Kahleil Jackson", "team": "Florida Gators", "status": "Out", "date": "2020-11-21T18:31Z",
           "comment": "Jackson (undisclosed) is inactive for Saturday's game against Vanderbilt."}
RUPERT = {"player": "Iliana Rupert", "team": "Golden State Valkyries", "status": "Out", "date": "2026-05-07T15:00Z"}
UNDATED = {"player": "No Date", "team": "Florida Gators", "status": "Out", "date": ""}


def test_a_row_past_a_year_is_dropped_and_a_long_term_one_kept():
    kept = E.drop_old_designations([JACKSON, RUPERT, UNDATED], now=NOW)
    assert [r["player"] for r in kept] == ["Iliana Rupert", "No Date"]
    assert E.DESIGNATION_MAX_DAYS == 365
    # A day short of the year stays.
    edge = dict(RUPERT, date="2025-11-25T03:00Z")
    assert E.drop_old_designations([edge], now=NOW) == [edge]


def test_the_page_and_the_picks_drop_it():
    build = (ROOT / "injuries_build.py").read_text(encoding="utf-8")
    assert "sports[league] = drop_old_designations(drop_stale_returns(current_rows(rows)))" in build
    got = I.live_injuries([JACKSON, dict(JACKSON, player="Ricky Pearsall", date="2026-11-22T12:00Z")],
                          now=NOW, team_key=lambda t: "FLA" if t == "Florida Gators" else "")
    assert [i.player for i in got] == ["Ricky Pearsall"], got


def test_an_old_filing_says_its_year():
    node = shutil.which("node")
    if not node:
        print("      (skipped: no node)")
        return
    sys.path.insert(0, str(ROOT / "tests"))
    from _app import decl
    js = decl("injWhen") + """
      const day = 86400e3, now = Date.now(), y = new Date().getFullYear();
      console.log(JSON.stringify([injWhen(now - 3 * day), injWhen(Date.UTC(2020, 10, 21, 18)),
                                  injWhen(Date.UTC(y, 0, 2, 12)) ]));"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(js)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    recent, old, this_year = json.loads(out.stdout)
    assert recent == "3d ago"
    assert "2020" in old and "Nov" in old, old
    import datetime as _dt
    # This year's filing says no year ("Jan 2"; "Nd ago" in the year's first fortnight).
    assert this_year.endswith("ago") or str(_dt.datetime.now().year) not in this_year, this_year


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
