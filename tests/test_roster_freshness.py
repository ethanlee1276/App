"""A cached nflverse file must not outlive the news it describes.

FOUND FIVE DAYS AFTER CUT-DOWN DAY, hunting a different bug. Three
loaders — rosters, weekly stats, snap counts — each began with
`if local.exists(): return load_local_csv(local)`, in front of a fetch
layer that already carries a 12-hour TTL and a stale-file fallback. So
the first file ever written, by a fetch or by a hand export, was served
FOREVER. For rosters that means August 26th's cuts, and every trade and
waiver claim since, never reach the Week 1 board: a cut player stays
ACT with props built off last season, a claimed player does not exist,
a traded one keeps his old team. For weekly stats it is worse — a file
cached in Week 1 would freeze every projection at Week 1 for the season.

The early return was meant for the hand-export case, and the fetch
layer already covers it: an export lands on the same cache path, and
when the release URL fails, `fetch_text` falls back to exactly that
file. Nothing was gained; a season of freshness was lost.

Run directly: `python3 tests/test_roster_freshness.py`
"""

import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine.sources import fetch as _fetch
from engine.sources import nflverse

CSV = "full_name,team,position,status,headshot_url\nA Back,DET,RB,ACT,\n"


def _with_cache(files: dict):
    """A throwaway CACHE_DIR holding `files`, patched into both modules."""
    tmp = Path(tempfile.mkdtemp())
    for name, (text, age_s) in files.items():
        p = tmp / name
        p.write_text(text)
        t = time.time() - age_s
        os.utime(p, (t, t))
    return tmp


def _patched(cache_dir, fetcher=None):
    saved = (nflverse.CACHE_DIR, _fetch.CACHE_DIR, nflverse.fetch_csv)
    nflverse.CACHE_DIR = _fetch.CACHE_DIR = cache_dir
    if fetcher is not None:
        nflverse.fetch_csv = fetcher
    return saved


def _restore(saved):
    nflverse.CACHE_DIR, _fetch.CACHE_DIR, nflverse.fetch_csv = saved


def test_an_existing_roster_file_no_longer_bypasses_the_fetch():
    """The contract: the loader ASKS the fetch layer even when a cache
    file exists — the TTL decides, not exists()."""
    calls = []

    def spy(url, name, **kw):
        calls.append(name)
        return [{"full_name": "Fresh Guy", "team": "KC",
                 "position": "WR", "status": "ACT"}]
    tmp = _with_cache({"roster_2026.csv": (CSV, 3 * 24 * 3600)})
    saved = _patched(tmp, spy)
    try:
        rows = nflverse.load_rosters(2026)
    finally:
        _restore(saved)
    assert calls == ["roster_2026.csv"], calls
    assert "Fresh Guy" in {r["full_name"] for r in rows}


def test_weekly_stats_and_snap_counts_carry_the_same_contract():
    for loader, name in ((nflverse.load_weekly_stats, "player_stats_2026.csv"),
                         (nflverse.load_snap_counts, "snap_counts_2026.csv")):
        calls = []

        def spy(url, cname, **kw):
            calls.append(cname)
            return [{"player_name": "x"}]
        tmp = _with_cache({name: ("player_name\nold\n", 3 * 24 * 3600)})
        saved = _patched(tmp, spy)
        try:
            loader(2026)
        finally:
            _restore(saved)
        assert calls and calls[0] == name, (loader.__name__, calls)


def test_a_fresh_cache_is_still_served_without_a_download():
    """The TTL's other half: a file under 12 hours old costs no request.
    Uses the REAL fetch layer with the network stubbed to explode."""
    tmp = _with_cache({"roster_2026.csv": (CSV, 60)})
    saved = _patched(tmp)
    real_open = _fetch.urllib.request.urlopen
    _fetch.urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(
        OSError("network must not be touched"))
    try:
        rows = nflverse.load_rosters(2026)
    finally:
        _fetch.urllib.request.urlopen = real_open
        _restore(saved)
    assert rows[0]["full_name"] == "A Back"


def test_a_stale_export_survives_a_dead_network():
    """The case the old exists() check was protecting, still protected:
    the release unreachable, a hand-exported file on the cache path —
    the loader returns it rather than raising."""
    tmp = _with_cache({"roster_2026.csv": (CSV, 3 * 24 * 3600)})
    saved = _patched(tmp)
    real_open = _fetch.urllib.request.urlopen
    _fetch.urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(
        OSError("offline"))
    try:
        rows = nflverse.load_rosters(2026)
    finally:
        _fetch.urllib.request.urlopen = real_open
        _restore(saved)
    assert rows[0]["team"] == "DET"


def test_a_bom_on_an_exported_file_does_not_shift_the_columns():
    tmp = _with_cache({"roster_2026.csv": ("﻿" + CSV, 3 * 24 * 3600)})
    saved = _patched(tmp)
    real_open = _fetch.urllib.request.urlopen
    _fetch.urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(
        OSError("offline"))
    try:
        rows = nflverse.load_rosters(2026)
    finally:
        _fetch.urllib.request.urlopen = real_open
        _restore(saved)
    assert rows[0]["full_name"] == "A Back", rows[0]


def test_depth_charts_and_injuries_ask_the_fetch_layer_too():
    """The same freeze lived in two worse places: a depth chart cached
    in August names August's starters in November, and an injury file
    cached in Week 1 applies Week 1's OUT list all season."""
    from engine.sources import depthcharts, injuries
    # The depth-chart loader asks for the TEXT (it refreshes the cache and
    # streams the rows off the file — 2026-09-02, the 550 MB load); the
    # injury loader still asks for parsed rows. Both go through the fetch
    # layer, which is the contract.
    for mod, loader, name, attr in (
            (depthcharts, depthcharts.load_depth_charts,
             "depth_charts_2026.csv", "fetch_text"),
            (injuries, injuries.load_injuries, "injuries_2026.csv", "fetch_csv")):
        calls = []

        def spy(url, cname, **kw):
            calls.append(cname)
            return ("player_name\nx\n" if attr == "fetch_text"
                    else [{"player_name": "x"}])
        tmp = _with_cache({name: ("player_name\nold\n", 3 * 24 * 3600)})
        saved = (mod.CACHE_DIR, getattr(mod, attr))
        mod.CACHE_DIR = tmp
        setattr(mod, attr, spy)
        try:
            loader(2026)
        finally:
            mod.CACHE_DIR = saved[0]
            setattr(mod, attr, saved[1])
        assert calls and calls[0] == name, (loader.__name__, calls)


def test_participation_refreshes_weekly_not_never():
    """49 MB and weekly consumers: the TTL is six days, not twelve hours
    and not eternity."""
    from engine.sources import nflpart
    calls = []

    def spy(url, cname, ttl=None, **kw):
        calls.append(ttl)
        return [{"x": "1"}]
    tmp = _with_cache({"pbp_participation_2026.csv": ("x\n1\n",
                                                      30 * 24 * 3600)})
    saved = (nflpart.CACHE_DIR, nflpart.fetch_csv)
    nflpart.CACHE_DIR, nflpart.fetch_csv = tmp, spy
    try:
        nflpart.load_participation(2026)
    finally:
        nflpart.CACHE_DIR, nflpart.fetch_csv = saved
    assert calls == [6 * 24 * 3600], calls


def test_the_short_circuit_is_gone_from_the_source():
    """The pattern must not come back under a new name: no loader may
    return a local file without consulting the fetch layer first."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for fname in ("nflverse.py", "depthcharts.py", "injuries.py",
                  "nflpart.py"):
        with open(os.path.join(root, "engine", "sources", fname),
                  encoding="utf-8") as f:
            src = f.read()
        assert "if local.exists():\n        return load_local_csv" \
            not in src, fname


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
