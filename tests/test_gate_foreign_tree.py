"""A board published to a tree that is not this checkout's keeps its
private copy in THAT tree, never in this checkout's data/built.

Ethan, 2026-09-14, a screenshot of The Lab: every sport "not replayed
yet", NFL "skipped", MLB "no ingested game logs deep enough", every
game-line market "no harvested closing lines stored" — on a database
holding four NFL seasons and seventeen thousand MLB closes. "It doesn't
look like we're using our data correctly or anything. And why does nfl
say skipped."

The page was the test suite's. `tests/test_lab.py` hands `run_if_due` a
flat `<tmp>/backtest.json`; `gate.publish` could not place that path in
any tree and fell back to the module's FULL_DIR — this checkout's
data/built — which is the copy `/api/board/backtest.json` serves a
subscriber. So the last run of the suite on a box publishes a four-game
seeded page, with the NFL replay switched off, over the live Lab. The
same fault was fixed for the paywall fixtures on 2026-09-03 by reshaping
the fixtures; the fallback itself stayed, and one caller was missed.

The suite's own rule: it must not read the box it runs on. Writing to it
is the same rule, worse.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import gate  # noqa: E402

PAGE = {"generated_at": "2026-09-14T13:04:01",
        "sports": {"mlb": {"props": {"unavailable": "seeded"},
                           "game_lines": {"unavailable": "seeded"}}}}


def _with_full_dir(tmp):
    """Point the module's FULL_DIR somewhere disposable for the duration,
    so the test can prove nothing landed there without touching the real
    one."""
    was = gate.FULL_DIR
    gate.FULL_DIR = Path(tmp) / "checkout" / "data" / "built"
    return lambda: setattr(gate, "FULL_DIR", was)


def test_a_flat_path_keeps_its_private_copy_beside_itself():
    with tempfile.TemporaryDirectory() as tmp:
        restore = _with_full_dir(tmp)
        try:
            public = Path(tmp) / "elsewhere" / "backtest.json"
            public.parent.mkdir(parents=True)
            _, full = gate.publish(PAGE, public, "backtest.json")
            assert Path(full) == public.parent / "built" / "backtest.json", full
            assert json.loads(Path(full).read_text())["generated_at"] \
                == PAGE["generated_at"]
            # And NOTHING in the checkout's own private directory.
            assert not gate.FULL_DIR.exists(), \
                f"the foreign board landed in this checkout: {gate.FULL_DIR}"
        finally:
            restore()


def test_the_reader_finds_the_copy_where_the_writer_put_it():
    """`board_source` resolves through the same function as `publish`;
    if the two ever drift the private copy is written where nothing
    reads it."""
    with tempfile.TemporaryDirectory() as tmp:
        restore = _with_full_dir(tmp)
        try:
            public = Path(tmp) / "elsewhere" / "backtest.json"
            public.parent.mkdir(parents=True)
            assert gate.board_source(public) == public          # nothing yet
            gate.publish(PAGE, public, "backtest.json")
            assert gate.board_source(public) \
                == public.parent / "built" / "backtest.json"
        finally:
            restore()


def test_a_board_inside_this_sites_web_tree_still_resolves_to_full_dir():
    """A public file nested one level under web/data — the light boards,
    a per-sport folder — is still this site's board and its private copy
    still belongs in FULL_DIR. Only a path OUTSIDE the web tree moves.
    Pure path arithmetic: no file is written near the real web root."""
    nested = gate._WEB / "data" / "light" / "cfb.json"
    assert gate._full_dir_for(nested) == gate.FULL_DIR
    # The shaped case is untouched: `<root>/web/data/x` → `<root>/data/built`.
    with tempfile.TemporaryDirectory() as tmp:
        shaped = Path(tmp) / "web" / "data" / "x.json"
        assert gate._full_dir_for(shaped) == Path(tmp) / "data" / "built"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
