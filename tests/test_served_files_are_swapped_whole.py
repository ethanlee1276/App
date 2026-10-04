"""A served file is swapped in whole, never written in place.

Audit 2026-09-30, F-12 (roadmap #17). `ufc_live.json`, `rosters_*.json` and
`standings_*.json` were written with `Path.write_text` straight onto the
served path. A poll that landed mid-write got truncated JSON, which Caddy
can cache for 60 s — and `ufc_live.json` is polled every 12 s during a
fight. Each now writes a sibling `.tmp` and `os.replace`s it into place.
(`engine/memeledger.py`, the fourth file named, already did.)
"""

import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _interrupted_rename(fn):
    """Run `fn` with os.replace failing — the moment a crash mid-swap
    would leave behind."""
    real = os.replace

    def boom(*a, **k):
        raise OSError("interrupted")
    os.replace = boom
    try:
        fn()
    except OSError:
        pass
    finally:
        os.replace = real


def test_standings_leave_the_old_file_whole_when_the_swap_fails():
    import standings_build as SB
    out = Path(tempfile.mkdtemp())
    (out / "standings_nfl.json").write_text('{"old": true}')
    real = SB.build
    SB.build = lambda *a, **k: {"new": True, "rows": list(range(5000))}
    try:
        _interrupted_rename(lambda: SB.write("nfl", out))
        assert json.loads((out / "standings_nfl.json").read_text()) == {"old": True}
        SB.write("nfl", out)
        assert json.loads((out / "standings_nfl.json").read_text())["new"] is True
        assert not (out / "standings_nfl.json.tmp").exists()
    finally:
        SB.build = real


def test_rosters_leave_the_old_file_whole_when_the_swap_fails():
    import rosters_build as RB
    sport = sorted(RB.NO_SOURCE)[0] if RB.NO_SOURCE else None
    if sport is None:
        return
    out = Path(tempfile.mkdtemp())
    dest = out / f"rosters_{sport}.json"
    dest.write_text('{"old": true}')
    _interrupted_rename(lambda: RB.write(sport, out))
    assert json.loads(dest.read_text()) == {"old": True}
    RB.write(sport, out)
    assert "old" not in json.loads(dest.read_text())


def test_no_served_writer_writes_in_place():
    for f, served in (("ufc_live_build.py", "    p.write_text(json.dumps(blob"),
                      ("rosters_build.py", '(out_dir / f"rosters_{sport}.json").write_text'),
                      ("standings_build.py", '(out_dir / f"standings_{sport}.json").write_text')):
        src = (ROOT / f).read_text()
        assert served not in src, f"{f} writes the served file in place"
        assert "os.replace(tmp, " in src, f"{f} has no atomic swap"
    mem = (ROOT / "engine" / "memeledger.py").read_text()
    assert re.search(r"tmp\.replace\(p\)|os\.replace\(tmp", mem)


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
