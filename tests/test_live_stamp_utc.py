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

    got = livescore_build.utc_stamp()
    assert got.endswith("Z"), got
    when = dt.datetime.strptime(got, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    drift = abs((dt.datetime.now(dt.timezone.utc) - when).total_seconds())
    assert drift < 120, f"{got} is {drift:.0f}s from now — a local-time stamp wearing a Z"


# EVERY builder behind a stamp the browser SUBTRACTS.
#
# 2026-09-06: this test named ONE file and passed while the bug was still
# live on the page. `pbpAgo` reads `d.generated_at` off the deep
# play-by-play file, and that file is written by live_build.py — a
# different builder, with its own naive clock, which this test never
# looked at. The game centre went on reporting four hours after the fix
# shipped, and the screenshot that proved it also showed the new render,
# so the deploy was not the excuse.
#
# The list is now derived from the READERS rather than typed from memory:
# find every JS call to pbpAgo, confirm each is passed `generated_at`,
# and require every builder that writes that field for those files to go
# through the one UTC helper.
LIVE_BUILDERS = ("livescore_build.py", "live_build.py")


def test_the_reader_that_subtracts_only_ever_reads_generated_at():
    """If pbpAgo starts reading a second field, the builder list stops
    covering it — so the assumption is pinned, not assumed."""
    calls = re.findall(r"pbpAgo\(([^)]*)\)", APP)
    calls = [c for c in calls if c.strip() != "stamp"]     # its own signature
    assert calls, "no callers found"
    for c in calls:
        assert c.strip() == "d.generated_at", c


def test_no_writer_of_generated_at_stamps_a_naive_local_clock():
    for name in LIVE_BUILDERS:
        src = (ROOT / name).read_text()
        # A builder is allowed exactly one clock, and it is the UTC one.
        bare = re.findall(r"_dt\.datetime\.now\(\)", src)
        assert not bare, f"{len(bare)} naive now() left in {name}"
        setters = [ln.strip() for ln in src.splitlines()
                   if re.search(r'"generated_at":\s*[A-Za-z_]', ln)]
        assert setters, f"{name} writes no generated_at any more"
        for ln in setters:
            assert re.search(r'"generated_at":\s*(now\b|_utc\(\)|utc_stamp\(\))', ln), (name, ln)
        for ln in src.splitlines():
            if re.match(r"\s*now = ", ln) and "time.time" not in ln:
                assert "utc_stamp()" in ln, (name, ln.strip())


def test_the_deep_play_by_play_file_is_the_one_the_game_centre_reads():
    """Pinning WHERE the bug was, so the next reader knows which file
    matters: the page fetches data/pbp/<league>_<id>.json, and
    live_build.write_pbp is what writes it."""
    assert "data/pbp/${encodeURIComponent(league)}" in APP
    src = (ROOT / "live_build.py").read_text()
    at = src.index("def write_pbp(")
    assert "pbp_dir / f\"mlb_{g['game_pk']}.json\"" in src[at:at + 900]
    assert '"generated_at": _utc()' in src[at:at + 1400]


def test_both_builders_share_one_helper_rather_than_each_keeping_a_clock():
    """Two builders each deciding what a timestamp is IS the defect."""
    import live_build
    import livescore_build

    assert live_build._utc()[:16] == livescore_build.utc_stamp()[:16]
    assert live_build._utc().endswith("Z")
    assert "from livescore_build import utc_stamp" in (ROOT / "live_build.py").read_text()


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
