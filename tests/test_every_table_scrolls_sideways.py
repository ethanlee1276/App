"""v4: every table scrolls sideways, with the fade.

The Lab's usage-ripple table ran six columns and was clipped at a
phone's edge mid-word. The stat tables had already fixed this with
`.rank-scroll` and its "more to the right" mask — six of thirty tables
wrapped by hand. wrapTables() wraps the rest on every render.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    return re.sub(r"^\s*//.*$", "", APP[i:APP.index("\n}\n", i)], flags=re.M)


def test_a_bare_table_is_wrapped_and_a_wrapped_one_is_left_alone():
    body = _fn("wrapTables")
    assert 'querySelectorAll("table")' in body
    assert 'if (table.closest(".rank-scroll")) return;' in body, "the hand-wrapped six would be wrapped twice"
    assert 'wrap.className = "rank-scroll tbl-scroll";' in body, "the fade is delegated to .rank-scroll; a wrapper without it has no fade"
    assert "table.replaceWith(wrap);" in body and "wrap.appendChild(table);" in body


def test_it_runs_on_every_render():
    subs = _fn("enhanceSectionSubs")
    assert "wrapTables(root);" in subs


def test_the_wrapper_keeps_the_fade_and_drops_the_rank_cap():
    assert 'document.querySelectorAll(".rank-scroll").forEach(sync)' in APP, "the delegated fade no longer watches the wrapper"
    assert ".rank-scroll.rank-more {" in CSS
    assert ".tbl-scroll { max-height: none; margin-top: 0; }" in CSS
    assert CSS.index(".tbl-scroll {") > CSS.index(".rank-scroll.rank-more {"), "declared after the rank rules, so it wins on order"


def test_the_hand_wrapped_tables_still_exist():
    assert APP.count('class="rank-scroll"') >= 3, "the ranking tables lost their own wrapper"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
