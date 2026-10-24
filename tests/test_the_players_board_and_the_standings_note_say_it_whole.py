"""v5: the Players board's empty state is the slate; the Standings note keeps its subject.

Two finds from the crawl at 390. The Players page, with no props priced,
drew a centred box of prose — the one empty state on the site that was
not the slate, so it had no mark, no title, and none of the doors every
other empty board carries. And the Standings page, on a payload with no
season field, read "has no scoring rankings of its own yet — fewer than
four teams…": a sentence with its subject missing.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()


def _fn(head):
    i = APP.index(head)
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return APP[i:min(ends)]


def test_the_players_empty_board_is_the_slate():
    body = _fn("async function renderPlayers(")
    i = body.index("if (!q) {")
    branch = body[i:body.index("return;", i)]
    assert 'class="empty-slate"' in branch and 'class="es-title"' in branch and 'class="es-sub"' in branch
    assert 'class="empty"' not in branch, "the centred box of prose is back"
    assert "No priced props on the ${escapeHtml(String(state.sport || \"\").toUpperCase())} board tonight" in branch, \
        "the title names the league"
    assert 'icon("search"' in branch


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""
      var state = {{ sport: "nfl", data: {{}} }};
      var escapeHtml = (s) => String(s == null ? "" : s);
      var teamMarkIn = () => "";
      var teamsForSport = () => ({{}});
      {_fn("function unitRankingsWaitHTML(")}
      console.log(JSON.stringify((() => {{ {js} }})()));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_the_standings_note_keeps_its_subject_without_a_season():
    got = _node("""return {
      none: unitRankingsWaitHTML({}),
      feed: unitRankingsWaitHTML({ feed_error: "timeout" }),
      wait: unitRankingsWaitHTML({ season_wait: true, first_games: "2026-09-10" }),
      dated: unitRankingsWaitHTML({ season: 2026 }),
      datedWait: unitRankingsWaitHTML({ season: 2026, season_wait: true }),
      shaped: (() => {
        const shapes = {};
        for (const t of ["A", "B", "C", "D"]) shapes[t] = { raw: { offense: 20, defense: 20 }, games: 3 };
        state.data = { team_shapes: shapes, team_shapes_season: 2025 };
        return unitRankingsWaitHTML({});
      })() };""")
    if got is None:
        print("  SKIP node not installed"); return
    flat = {k: " ".join(v.split()) for k, v in got.items()}
    assert "This season has no scoring rankings of its own yet" in flat["none"]
    assert "This season has no scoring rankings of its own yet" in flat["feed"]
    assert "The season hasn’t kicked off — first games 2026-09-10" in flat["wait"]
    assert "2026 has no scoring rankings of its own yet" in flat["dated"]
    assert "The 2026 season hasn’t kicked off" in flat["datedWait"]
    assert "until this season has its first" in flat["shaped"], "the mid-sentence subject, over last season’s table"
    for k, v in flat.items():
        assert not re.search(r">\s*has no scoring", v), f"{k}: the subject is missing again"
        assert "The  season" not in got[k] and "until  has" not in got[k], f"{k}: a blank where the season was"


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
