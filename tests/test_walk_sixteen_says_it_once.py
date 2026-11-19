"""Walk 16's fixes (2026-11-19, step YG).

  - the race pages' opening line read "330 games played, 1005 left in the
    regular season" (WHEN_YOU_ARE_HOME, step XO, quoting the NHL's): a count
    past a thousand reads with its comma, as college's race already did
    ("1,005 left"), on the NFL's, the NBA's and the NHL's alike.

    python3 tests/test_walk_sixteen_says_it_once.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "web" / "js"
APP = (JS / "app.js").read_text(encoding="utf-8")
RACE = (JS / "race.js").read_text(encoding="utf-8")


def _fn(src: str, name: str) -> str:
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 2]


def _node(prog: str):
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed")
        return None
    out = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_race_says_its_game_counts_with_commas():
    ledes = re.findall(r'<p class="rc-note rc-lede">(?:(?!</p>).)*?left in the regular season\.</p>', RACE, re.S)
    assert len(ledes) == 2, f"the NFL's lede and the NBA's and NHL's: {len(ledes)}"
    prog = "\n".join([_fn(APP, "escapeHtml"), _fn(APP, "pluralWord"), _fn(APP, "plural")]) + f"""
      const ledes = {json.dumps(ledes)};
      const text = (h) => h.replace(/<[^>]+>/g, " ").replace(/\\s+/g, " ").trim();
      const say = (src, d) => text(new Function("d", "plural", "escapeHtml", "return `" + src + "`;")(d, plural, escapeHtml));
      console.log(JSON.stringify(ledes.map((src) => [
        say(src, {{week: 12, games_played: 1336, games_left: 1005}}),
        say(src, {{week: 1, games_played: 1, games_left: 0}}),
      ])));"""
    got = _node(prog)
    if got is None:
        return
    nfl, season = got
    assert nfl[0] == "Week 12 next · 1,336 games played, 1,005 left in the regular season.", nfl[0]
    assert season[0] == "1,336 games played, 1,005 left in the regular season.", season[0]
    assert season[1] == "1 game played, 0 left in the regular season.", season[1]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
