"""Every Most Likely row carries one plain line saying why it is there.

Ethan, 2026-10-04: "do all of it" — the why line. The row already had the
reasons, folded behind a tap; now the first one shows on the row itself:
a touchdown's goal-line role first, else the board's first case line, else
the matchup check's note, cut to fit two lines. A row with none of them
draws nothing rather than a placeholder.

Run directly: `python3 tests/test_each_likely_row_says_why.py`
"""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 3]


def _run(rows):
    js = ("function escapeHtml(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')}\n"
          + _fn("obWhyLine") + f"\nconsole.log(JSON.stringify({json.dumps(rows)}.map(obWhyLine)));")
    return json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)


def test_the_line_picks_the_best_reason_it_has():
    out = _run([
        {"lane": "td", "goal_line_text": "Gets 40% of the team's goal-line carries", "case_lines": ["x"]},
        {"lane": "yards", "goal_line_text": "ignored off the TD lane", "case_lines": ["Has gone over in 8 of 10"]},
        {"check_notes": {"matchup": "Faces the 30th-ranked run defence"}},
        {},
    ])
    assert "goal-line carries" in out[0]
    assert "8 of 10" in out[1] and "ignored" not in out[1]
    assert "30th-ranked" in out[2]
    assert out[3] == ""


def test_a_long_reason_is_cut_and_escaped():
    out = _run([{"case_lines": ["<b>" + "a" * 200]}])[0]
    assert "&lt;b>" in out and "<b>" not in out and out.count("a") < 100 and "…" in out


def test_it_sits_on_the_card_and_clamps_to_two_lines():
    assert "${obWhyLine(r)}" in _fn("obCardHTML")
    i = CSS.index(".ob-why1")
    assert "-webkit-line-clamp:2" in CSS[i:i + 300].replace(" ", "")


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
