"""The live overlay reads its stamp as the instant it is.

Audit 2026-09-30, P1-5 (roadmap #9). engine/sweat.py stamped
`datetime.now()` — naive, the box's local clock — and the page read it as
UTC by appending "Z". On a box whose clock is Eastern every sweat file
looked four hours old against a three-minute freshness bar, and the live
win-probability overlay drew nothing from 2026-08-24.
"""

import datetime as _dt
import inspect
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
APP = (ROOT / "web" / "js" / "app.js").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def test_the_sweat_writer_stamps_utc_with_its_offset():
    from engine import sweat
    src = inspect.getsource(sweat)
    assert "_dt.datetime.now(_dt.timezone.utc).isoformat(timespec=\"seconds\")" in src
    stamp = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    parsed = _dt.datetime.fromisoformat(stamp)
    assert parsed.tzinfo is not None
    assert abs((_dt.datetime.now(_dt.timezone.utc) - parsed).total_seconds()) < 180


def test_the_page_reads_a_zoned_stamp_as_written_and_a_bare_one_as_eastern():
    if not shutil.which("node"):
        return
    p = os.path.join(tempfile.mkdtemp(), "s.js")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(_fn("stampMs") + "\nprocess.stdout.write(JSON.stringify(["
                 "stampMs('2026-09-30T21:00:00Z'), stampMs('2026-09-30T17:00:00-04:00'),"
                 "stampMs('2026-09-30T21:00:00+00:00'), stampMs('2026-09-30T17:00:00'),"
                 "stampMs('2026-12-30T16:00:00'), stampMs(''), stampMs(null)]));")
    out = subprocess.run(["node", p], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-400:]
    z, et, plus, bare_edt, bare_est, empty, none = json.loads(out.stdout)
    assert z == et == plus == bare_edt, "one instant, four spellings"
    assert bare_est == z + 91 * 86400000 - 0, "16:00 EST in December is 21:00 UTC"
    assert empty is None and none is None       # NaN serialises as null


def test_the_overlay_and_the_live_card_use_the_one_reader():
    assert "(Date.now() - stampMs(d.generated_at)) < 180000" in APP
    assert "const built = stampMs(d.generated_at) || 0;" in APP
    assert 'd.generated_at.endsWith("Z")' not in APP, "the four-hour misread is back"


def test_the_record_check_accepts_a_zoned_stamp():
    src = (ROOT / "homecheck.py").read_text()
    assert "_dt.datetime.now(made.tzinfo) if made.tzinfo else _dt.datetime.now()" in src


if __name__ == "__main__":
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
