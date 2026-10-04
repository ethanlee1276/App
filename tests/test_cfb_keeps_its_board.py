"""One 403 from ESPN must not blank a Saturday.

Found 2026-08-19 while rehearsing the CFB season opener. `cfb_build.py`
answered an unreachable schedule by publishing an EMPTY board with the
error as its note:

    out.update(status="unreachable", note=str(exc))
    _write(out, args.out)

`gate.publish` writes whatever it is handed, so that replaced a full
board with a blank page — and left it blank until some later cycle
happened to succeed. On a Saturday with sixty games and a flaky feed
that is the whole product gone for an hour.

It was also the outlier. `pm_build.build_kalshi` already answers the same
exception by "keeping last board"; CFB was the one build that did not.

What is defended here:

  * A PRIOR BOARD WITH GAMES SURVIVES. Nothing is written at all —
    rewriting would refresh `generated_at` and hide the staleness the
    masthead's stale bar exists to show, and republishing the public copy
    through the gate would overwrite the unredacted full board with the
    redacted one.
  * "THE FILE EXISTS" IS NOT THE TEST. A previous failed run leaves a
    zero-game payload behind, and keeping that is keeping nothing.
  * WITH NOTHING TO KEEP, THE REASON STILL SHIPS. An empty board that
    says why beats an empty board that does not.
  * THE LAUNCHER DOES NOT CALL IT "REFRESHED". Keeping a board exits 0,
    and a log line that says a stale board is current is how an outage
    hides.

Run directly: `python3 tests/test_cfb_keeps_its_board.py`
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = open(os.path.join(ROOT, "cfb_build.py"), encoding="utf-8").read()
LAUNCH = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()

import cfb_build                                                # noqa: E402


# --- the predicate, exercised ------------------------------------------------
def _tmp(doc):
    fh = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(doc, fh)
    fh.close()
    return fh.name


def test_a_board_with_games_is_worth_keeping():
    assert cfb_build._has_board(_tmp({"games": [{"home": "MICH"}]})) is True


def test_a_zero_game_board_is_not():
    """The state a previous FAILED run leaves behind. Treating it as a
    board to keep would pin the blank page in place permanently — the
    build would refuse to overwrite its own failure."""
    assert cfb_build._has_board(_tmp({"games": [], "status": "unreachable"})) is False


def test_a_missing_or_corrupt_file_is_not_a_board():
    assert cfb_build._has_board("/nonexistent/nowhere.json") is False
    fh = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    fh.write("{not json")
    fh.close()
    assert cfb_build._has_board(fh.name) is False


# --- the branch it guards ----------------------------------------------------
def test_the_unreachable_branch_keeps_rather_than_publishes():
    i = BUILD.index("# KEEP THE LAST GOOD BOARD.")
    block = BUILD[i:i + 1800]
    assert "if _has_board(args.out):" in block, \
        "the unreachable branch stopped checking for a board to keep"
    # The keep path writes NOTHING. An early return before _write is the
    # only shape that leaves generated_at — and the full copy — alone.
    keep = block[block.index("if _has_board(args.out):"):]
    keep = keep[:keep.index("out.update(status=")]
    assert "_write(" not in keep, "the keep path writes, so it is not a keep"
    assert "return" in keep
    # And with nothing to keep, the reason still ships.
    assert 'out.update(status="unreachable", note=str(exc))' in block
    assert "_write(out, args.out)" in block


def test_the_launcher_does_not_report_a_kept_board_as_refreshed():
    i = LAUNCH.index("def refresh_cfb(")
    body = LAUNCH[i:LAUNCH.index("\ndef ", i + 10)]
    assert "Keeping the last board" in body, \
        "refresh_cfb cannot tell a kept board from a fresh one"
    assert "kept last board" in body
    # The phrase the launcher matches must be the phrase the build prints.
    assert "Keeping the last board" in BUILD


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
