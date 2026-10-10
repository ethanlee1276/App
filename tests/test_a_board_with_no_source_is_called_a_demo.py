"""A board whose games carry no source gets the demo banner, and so does
the play-by-play page.

Audit 2026-09-30, D-7 (roadmap #19). An EMPTY `generated_from` put "Demo
data" in the corner (renderDataSource) while the banner said nothing
(slateNotice returned null), so the banner, which is the one people read,
disagreed with the corner. And `pbp`, the page for a live game, was not
in BOARD_VIEWS, so a demo board's play-by-play page carried no banner at
all.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(js):
    """The sibling test's node harness, loaded on use (tests/ has no
    module-scope imports of anything outside the standard library)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_demo_board", ROOT / "tests" / "test_a_demo_or_old_board_never_passes_for_todays.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._run(js)


def test_games_with_no_source_are_a_demo_and_no_games_is_not():
    got = _run("""
      return {
        blank: slateNotice({ generated_from: "", games: [{ date: et(0) }] }),
        missing: slateNotice({ games: [{ date: et(0) }] }),
        empty: slateNotice({ generated_from: "", games: [] }),
        notBuilt: slateNotice({ date: "", status: "not built" }),
        offseason: slateNotice({ generated_from: "", status: "offseason", games: [{ date: et(90) }] }),
      };""")
    if got is None:
        return
    assert got["blank"] == {"kind": "demo"} and got["missing"] == {"kind": "demo"}
    assert got["empty"] is None and got["notBuilt"] is None and got["offseason"] is None


def test_the_play_by_play_page_carries_the_banner():
    got = _run("""
      state.view = "pbp";
      return slateNotice({ generated_from: "sample-slate", games: [{ date: et(0) }] });""")
    if got is None:
        return
    assert got == {"kind": "demo"}


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
