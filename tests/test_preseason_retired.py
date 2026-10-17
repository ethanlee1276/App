"""The NFL preseason surface is retired — gone from the site, dormant in
the tree.

Ethan, 2026-08-25: "I wanna get rid of the pre season section for nfl.
No need too have it anymore, I'd rather just be prepared for the regular
season to start."

WHAT "RETIRED" MEANS HERE, precisely, because half-removals are the
worst removals — a section that is gone from the nav but still built,
or unbuilt but still served, is a page frozen at its last refresh
wearing a live site's masthead:

  * the page block, the empty-slate branch and the horizon pointer are
    out of web/;
  * the launcher no longer builds nfl_preseason.json, and the gate no
    longer registers it (unknown = gated, the safe direction);
  * maintenance's RETIRED_BOARDS deletes the stale copy from web/data
    and data/built — the droplet's leftover file leaves on the first
    daily chore after deploy;
  * the ENGINE stays: nflpre.py, engine/sources/nflpreseason,
    engine/nfl/prestarters + prelines + prefit, and the preseason box
    ingest all still import and pass their own tests, because next July
    somebody will want them and they were measured, not guessed, the
    first time. Two test files that pinned the retired SURFACE
    (test_preseason_board, test_preseason_says_why) retired with it;
    their lesson — a reason must travel to where the question gets
    asked — is quoted where the code changed.

This file replaced them, and pins the removal the same way they pinned
the feature: so it cannot un-happen by accident.

Run directly: `python3 tests/test_preseason_retired.py`
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import gate                                       # noqa: E402
from engine import maintenance as M                           # noqa: E402


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


APP = _read("web", "js", "app.js")
HTML = _read("web", "index.html")
LAUNCH = _read("launch.py")


def test_the_page_carries_no_preseason_section():
    # Behaviour, not prose: the retirement comments left in place QUOTE
    # the old strings (that is what a written-down rule change looks
    # like), so this pins the code that could ACT — the render entry
    # points and the fetch path — never the words.
    assert 'id="preseason-board"' not in HTML
    assert "renderPreseason" not in APP
    assert "loadPreseason" not in APP
    assert '"data/nfl_preseason.json' not in APP, \
        "something in the page still fetches a board nothing builds"


def test_the_empty_slate_no_longer_promises_a_block_below():
    """The old branch said "The schedule and scores are below" — with the
    block gone that sentence would point at nothing. Checked on the
    emitted template markers, not the words a comment may quote."""
    assert 'es-title">Preseason' not in APP
    assert "state.preseason" not in APP


def test_the_launcher_no_longer_builds_it():
    assert "def refresh_preseason" not in LAUNCH
    assert "refresh_preseason(quiet=quiet)" not in LAUNCH
    # The dormant --prescan CLI may still NAME the file; nothing may
    # WRITE it. The launcher's only write was refresh_preseason's.
    assert 'path.write_text(json.dumps(payload' not in LAUNCH


def test_the_gate_treats_it_as_unknown_which_means_gated():
    assert "nfl_preseason.json" not in gate.KNOWN_BOARDS
    assert "nfl_preseason.json" not in gate.FREE_FILES
    assert not gate.is_free("nfl_preseason.json")


def test_maintenance_sweeps_the_stale_copy_off_the_public_path():
    """The droplet still has the last built file after a deploy; the
    daily chores must remove it rather than leave frozen August scores
    being served into December."""
    assert "nfl_preseason.json" in M.RETIRED_BOARDS
    root = Path(tempfile.mkdtemp())
    (root / "web" / "data").mkdir(parents=True)
    (root / "data" / "built").mkdir(parents=True)
    (root / "web" / "data" / "nfl_preseason.json").write_text("{}")
    (root / "data" / "built" / "nfl_preseason.json").write_text("{}")
    (root / "web" / "data" / "record.json").write_text("{}")
    n = M.remove_retired_boards(root=root)
    assert n == 2
    assert not (root / "web" / "data" / "nfl_preseason.json").exists()
    assert (root / "web" / "data" / "record.json").exists(), \
        "the sweep touched a file it was never told about"
    # Idempotent: a second pass finds nothing and breaks nothing.
    assert M.remove_retired_boards(root=root) == 0


def test_the_sweep_runs_inside_the_daily_chores():
    src = _read("engine", "maintenance.py")
    i = src.index("def run_if_due")
    assert "remove_retired_boards(log=log)" in src[i:], \
        "the sweep exists but nothing runs it — the droplet keeps the file"


def test_the_engine_stays_dormant_not_deleted():
    """The other half of the deal: retirement is not amnesia. The modules
    import, their own tests still run in the suite, and the CLI's
    docstring says out loud that the surface is gone."""
    import engine.sources.nflpreseason                        # noqa: F401
    import engine.nfl.prestarters                             # noqa: F401
    import engine.nfl.prelines                                # noqa: F401
    import engine.nfl.prefit                                  # noqa: F401
    assert "RETIRED FROM THE SITE 2026-08-25" in _read("nflpre.py")


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
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
