"""The live page said a fresh game was four hours old.

Ethan, 2026-09-06, from a screenshot of a live MLB game: "firs. is says
its 200 mins old at the top?"  It said 240, and 240 minutes is not a
number a stale-data bug picks at random — it is exactly the September
Eastern offset.  `livescore_build.py` stamped `generated_at` with
`datetime.now().isoformat()`: local time on a box whose service runs
America/New_York, carrying no offset at all.  The reader appended a `Z`
and read it as UTC, so every live game on every page claimed to be four
hours stale the moment it was written.

It survived this long because `generated_at` has several readers and
only one of them does arithmetic: the others slice the string for a
clock face (`.slice(11, 16)`), which is right either way.  `pbpAgo` is
the one that subtracts.

Both sides are pinned here, because fixing either alone leaves the bug
one writer away from returning: the builder must emit UTC with an
explicit `Z`, and the reader must only assume UTC when the stamp says
nothing about its zone.
"""

import datetime as dt
import json
import os
import re
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
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return APP[i:min(ends)]


def test_the_builder_stamps_real_utc_with_the_zone_on_it():
    import livescore_build

    got = livescore_build._utc_stamp()
    assert got.endswith("Z"), got
    when = dt.datetime.strptime(got, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    drift = abs((dt.datetime.now(dt.timezone.utc) - when).total_seconds())
    assert drift < 120, f"{got} is {drift:.0f}s from now — a local-time stamp wearing a Z"


def test_no_writer_of_generated_at_stamps_a_naive_local_clock():
    src = (ROOT / "livescore_build.py").read_text()
    # The builder is allowed exactly one clock, and it is the UTC one.
    bare = re.findall(r"_dt\.datetime\.now\(\)", src)
    assert not bare, f"{len(bare)} naive now() left in livescore_build.py"
    # Every place the field is actually SET carries the UTC stamp — either
    # directly or through the one `now` the builder computes per league.
    setters = [ln.strip() for ln in src.splitlines()
               if re.search(r'"generated_at":\s*[A-Za-z_]', ln)]
    assert len(setters) == 4, setters
    for ln in setters:
        assert re.search(r'"generated_at":\s*(now\b|_utc_stamp\(\))', ln), ln
    nows = [ln.strip() for ln in src.splitlines() if re.match(r"\s*now = ", ln)]
    assert "now = _utc_stamp()" in nows, nows


def test_the_reader_only_assumes_utc_when_the_stamp_names_no_zone():
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed"); return
    prog = _fn("pbpAgo") + """
      const t = new Date(Date.now() - 120000);
      const pad = (n) => String(n).padStart(2, "0");
      const utc = `${t.getUTCFullYear()}-${pad(t.getUTCMonth() + 1)}-${pad(t.getUTCDate())}`
        + `T${pad(t.getUTCHours())}:${pad(t.getUTCMinutes())}:${pad(t.getUTCSeconds())}`;
      console.log(JSON.stringify({
        zed:    pbpAgo(utc + "Z"),
        offset: pbpAgo(utc + "+00:00"),
        naive:  pbpAgo(utc),
        east:   pbpAgo(new Date(t.getTime() + 3600000).toISOString().replace("Z", "+01:00")),
        junk:   pbpAgo("not a time"),
        empty:  pbpAgo(""),
      }));"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout.strip())
    # A stamp two minutes old reads as two minutes old however it spells
    # its zone — that is the whole defect.
    for key in ("zed", "offset", "naive", "east"):
        assert got[key] == "updated 2 min ago", f"{key}: {got[key]}"
    assert got["junk"] == "" and got["empty"] == "", got


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
