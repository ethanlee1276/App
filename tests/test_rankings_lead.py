"""The football team rankings lead the standings page, and an empty
table cannot hide them.

Ethan, 2026-09-08, the third time in the same words: "For nfl and cfb
on the rankings page, we should have a section ranking the current
ranking for teams defense and offense." The section was built on 09-02
(`standings.unit_rankings`, drawn by `unitRankingsHTML`) and on 09-05
taught to render on a football page with no rankings yet. Both times
it was drawn LAST — under eight division tables on the NFL, under
130-odd conference rows on the CFB — and the page's empty-table branch
returned before ever reaching it, which before Week 1 is the NFL on
any day the league feed answers with no teams. The nav button that
opens the page says "Rankings". He was on the right page, looking at
the top of it.

What this pins:

  * the rankings are drawn once and placed first on the page, above
    the postseason block and the division tables;
  * the empty-table branch renders them too, before its slate;
  * the title and the nav hint say rankings on a football page;
  * the wait section's heading says what is ranked below it — last
    season's finished games until this one has its first — and, run
    in node, ranks offense by most scored and defense by fewest
    allowed, all thirty-two teams, and shows no fallback for fewer
    than four.

Run directly: `python3 tests/test_rankings_lead.py`
"""

import json
import os
import subprocess
import sys
import tempfile
import shutil as _shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
HTML = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
DOC = open(os.path.join(ROOT, "docs", "DROPLET_CHECKS.md"), encoding="utf-8").read()


def _fn(name):
    i = APP.index(name)
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return APP[i:min(ends)]


def test_the_rankings_are_drawn_first_not_last():
    body = _fn("async function renderStandings(")
    assert "const rankings = unitRankingsHTML(d.unit_rankings, d);" in body, \
        "the rankings are no longer drawn once into a variable"
    # The bottom slot is gone; the variable is placed at the top of the
    # page, above the postseason block and the division tables.
    assert "${unitRankingsHTML(d.unit_rankings, d)}" not in body, \
        "the rankings are slotted at the bottom of the page again"
    tpl = body[body.index("host.innerHTML = `\n"):]
    assert tpl.index("${rankings}") < tpl.index("Postseason"), "under the bracket"
    assert tpl.index("${rankings}") < tpl.index('class="ros-teams"'), "under the tables"
    assert tpl.index("${rankings}") < tpl.index("${pressureHTML(d.pressure, d)}")
    # The Teams heading keeps its top margin when something sits above it.
    assert "b.started || rankings ? \"\" : ' style=\"margin-top:0\"'" in body


def test_an_empty_table_still_shows_the_rankings():
    body = _fn("async function renderStandings(")
    i = body.index("if (!groups.length) {")
    branch = body[i:body.index("return;", i)]
    assert '`${rankings}<div class="empty-slate">' in branch, \
        "the empty-table branch hides the rankings again"
    # And the variable is built BEFORE that branch, or it is undefined there.
    assert body.index("const rankings = unitRankingsHTML") < i


def test_the_title_and_the_nav_say_rankings_on_a_football_page():
    body = _fn("async function renderStandings(")
    assert 'const isFootball = sport === "nfl" || sport === "cfb";' in body
    assert 'isFootball ? "rankings & standings" : "standings"' in body
    assert 'data-view="standings" data-hint="team rankings, records &amp; the bracket"' in HTML
    assert "asked a third time" in DOC and "recommendations.json" in DOC


def test_the_wait_heading_says_what_is_ranked_below_it():
    body = _fn("function unitRankingsWaitHTML(")
    assert "ranked on the ${escapeHtml(String(shapeSeason))} season’s finished" in body
    assert "has no scoring rankings of its own yet" in body
    assert "No ${season} scoring rankings yet" not in body, \
        "the heading says 'no rankings' over a table of ranked teams"


# --- the section, run ---------------------------------------------------------
if not _shutil.which("node"):
    print("SKIP node is not installed; the arithmetic half of this file "
          "executes the section rather than reading it.")

_HARNESS = r"""
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");
function grab(name, end) {
  const i = src.indexOf(name);
  if (i < 0) throw new Error("missing: " + name);
  const j = src.indexOf(end, i);
  return src.slice(i, j + end.length);
}
// `var`: the grabbed functions read these as free variables at call time.
var state = { sport: "nfl", data: {} };
var _stdUnitsAll = false;
var escapeHtml = (s) => String(s == null ? "" : s);
var teamMarkIn = () => "";
var teamsForSport = () => ({});
eval([grab("function unitRankingsHTML(", "\n}"),
      grab("function unitRankingsWaitHTML(", "\n}")].join("\n"));
const names = (html) => [...html.matchAll(/std-name">([^<]+)</g)].map((m) => m[1].trim());
const rows = (html) => (html.match(/std-unit-row/g) || []).length;
const out = {};
// THIRTY-TWO SHAPED TEAMS: T32 scores the most, T01 allows the fewest.
const shapes = {};
for (let i = 1; i <= 32; i++) {
  const t = "T" + String(i).padStart(2, "0");
  shapes[t] = { raw: { offense: 15 + i, defense: 15 + i }, games: 17 };
}
const d = { season: 2026, season_wait: false, feed_error: "" };
state.data = { team_shapes: shapes, team_shapes_season: 2025 };
let html = unitRankingsHTML(null, d);
out.rows = rows(html);
const nm = names(html);
out.first_off = nm[0]; out.first_def = nm[32]; out.last_off = nm[31];
out.sub_ranked = html.includes("ranked on the 2025 season’s finished");
out.sub_ranked_until = html.includes("until 2026 has its first");
out.says_own = html.includes("2026 has no scoring rankings of its own yet");
out.no_yet = !html.includes("No 2026 scoring rankings yet");
// KICKOFF STILL AHEAD: the build's wait fields drive the sentence.
html = unitRankingsHTML(null, { season: 2026, season_wait: true, first_games: "2026-09-10" });
out.wait_sentence = html.includes("hasn’t kicked off") && html.includes("first games 2026-09-10");
out.wait_rows = rows(html);
// NO SHAPES ON THE BOARD: the reason, no table.
state.data = {};
html = unitRankingsHTML(null, d);
out.none_rows = rows(html);
out.none_reason = html.includes("has no scoring rankings of its own yet");
out.none_from = html.includes("from finished games");
// THREE SHAPED TEAMS is not a ranking.
state.data = { team_shapes: { A: shapes.T01, B: shapes.T02, C: shapes.T03 }, team_shapes_season: 2025 };
out.three_rows = rows(unitRankingsHTML(null, d));
// THE REAL RANKINGS, when the season has them.
const ur = { measure: "points per game",
  offense: [1, 2, 3, 4, 5].map((r) => ({ rank: r, team: "O" + r, value: 40 - r, record: "1-0" })),
  defense: [1, 2, 3, 4, 5].map((r) => ({ rank: r, team: "D" + r, value: 10 + r, record: "1-0" })) };
html = unitRankingsHTML(ur, d);
out.real_rows = rows(html);
out.real_first = names(html)[0];
out.real_sub = html.includes("from the same finished games");
out.real_no_wait = !html.includes("of its own yet");
// NOT FOOTBALL: nothing.
state.sport = "mlb";
out.mlb = unitRankingsHTML(null, d);
console.log(JSON.stringify(out));
"""


def _run():
    node = _shutil.which("node")
    if not node:
        return None
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(_HARNESS)
        path = fh.name
    try:
        res = subprocess.run([node, path, os.path.join(ROOT, "web", "js", "app.js")],
                             capture_output=True, text=True, timeout=60)
    finally:
        os.unlink(path)
    assert res.returncode == 0, res.stderr[-2000:]
    return json.loads(res.stdout)


def test_before_the_first_final_every_team_is_ranked_on_last_season():
    r = _run()
    if r is None:
        return
    assert r["rows"] == 64, r["rows"]
    assert r["first_off"] == "T32" and r["last_off"] == "T01", (r["first_off"], r["last_off"])
    assert r["first_def"] == "T01", r["first_def"]
    assert r["sub_ranked"] and r["sub_ranked_until"], "the heading no longer says what is ranked"
    assert r["says_own"] and r["no_yet"]
    assert r["wait_sentence"] and r["wait_rows"] == 64


def test_no_shapes_is_the_reason_alone_and_three_teams_is_no_ranking():
    r = _run()
    if r is None:
        return
    assert r["none_rows"] == 0 and r["none_reason"] and r["none_from"]
    assert r["three_rows"] == 0, r["three_rows"]


def test_the_seasons_own_rankings_replace_the_wait_and_other_sports_get_nothing():
    r = _run()
    if r is None:
        return
    assert r["real_rows"] == 10 and r["real_first"] == "O1"
    assert r["real_sub"] and r["real_no_wait"]
    assert r["mlb"] == ""


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
