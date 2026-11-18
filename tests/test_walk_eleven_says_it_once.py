"""Walk 11's fixes (2026-11-18, step YB): the Cavaliers' team page, Shai
Gilgeous-Alexander's player page and the NBA Record page, read as a reader
would on a phone.

  - a basketball or hockey team page said "2026 Schedule" and "2026 at a
    glance" while the player page beside it said "2026–27 season"; every
    season on the team page now reads as its league says it;
  - the team page listed its last four games in the schedule strip and again,
    the same dates, opponents and scores, under "Last 5"; the list stays only
    where it adds the line's verdict the strip has no room for;
  - an injury read "Back · back Nov 29"; it reads "Back · est. return Nov 29"
    on the team page and the roster, and a pick card's "expected back
    2026-11-29" is a day in words too;
  - the player page's shot chart said the Previous game card's numbers again a
    screen lower (37 points, 13-20, 2 rebounds, 2 assists); for that game a
    chart's tiles leave out what the card shows, in every league's chart;
  - the Previous game card cut the Thunder and the Kings to "T…" and "Ki…" on a
    390-wide phone; a phone stacks each side;
  - the Record page's headline picks read "CHA moneyline 0.5" and "BOS@ORL
    total 222.5"; a settled list mixing books listed one pick twice with
    nothing saying which book each row was; the Process tile's "1023W 59L"
    read as a 95% record; and the verdict's claimed and landed were the edge
    board's alone beside both books' record, unlabelled. The verdict now
    lives in the Record page's own file, which paid for the pick card's day.

    python3 tests/test_walk_eleven_says_it_once.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "web" / "js"
MORE = (JS / "more.js").read_text(encoding="utf-8")
APP = (JS / "app.js").read_text(encoding="utf-8")
REC = (JS / "record.js").read_text(encoding="utf-8")
CC = (JS / "carrychart.js").read_text(encoding="utf-8")
PLR = (JS / "playerpage.js").read_text(encoding="utf-8")
PLR_CSS = (ROOT / "web" / "css" / "playerpage.css").read_text(encoding="utf-8")


def _fn(src: str, name: str) -> str:
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 2]


def _inner(src: str, name: str) -> str:
    """A function inside a module's closure (carrychart.js), two spaces in."""
    i = src.index(f"\n  function {name}(") + 1
    return src[i:src.index("\n  }\n", i) + 4]


def _node(prog: str):
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed")
        return None
    out = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_a_split_year_season_reads_as_its_league_says_it():
    i = MORE.index("const TEAM_TWO_YEARS = ")
    helper = MORE[i:MORE.index("\n", i)] + "\n" + _fn(MORE, "teamSeasonLabel")
    got = _node(helper + """
      console.log(JSON.stringify([teamSeasonLabel("nba", 2026), teamSeasonLabel("nhl", "2025"),
        teamSeasonLabel("cbb", 2026), teamSeasonLabel("nfl", 2026), teamSeasonLabel("mlb", 2026),
        teamSeasonLabel("nba", null), teamSeasonLabel("nba", 2099)]));""")
    if got is not None:
        assert got == ["2026–27", "2025–26", "2026–27", "2026", "2026", "", "2099–00"], got
    # The player page says it the same way (playerpage.js plrSeasonLabel).
    assert 'const PLR_TWO_YEARS = ["nba", "nhl", "cbb"];' in PLR
    home = _fn(MORE, "teamHomeHTML")
    assert "${escapeHtml(teamSeasonLabel(d.sport, (d.schedule || {}).season))} Schedule" in home
    assert "${escapeHtml(teamSeasonLabel(d.sport, s.season))} at a glance" in home
    sched = _fn(MORE, "teamScheduleHTML")
    assert "${escapeHtml(teamSeasonLabel(d.sport, sch.season))} Schedule" in sched
    assert "Reading ${escapeHtml(teamSeasonLabel(d.sport, _teamState.schedLoading))}…" in sched
    assert "${escapeHtml(teamSeasonLabel(d.sport, y))}</button>" in _fn(MORE, "teamSeasonChipsHTML")
    assert 'data-team-season="${escapeAttr(String(y))}"' in _fn(MORE, "teamSeasonChipsHTML"), "the chip still asks by year"
    assert "<td>${escapeHtml(teamSeasonLabel(sport, r.season))}</td>" in _fn(MORE, "teamSeasonsHTML")
    assert "teamSeasonsHTML(p, d.sport)" in MORE
    assert "${teamSeasonLabel(d.sport, p.seasons[p.seasons.length - 1].season)} to ${teamSeasonLabel(d.sport, p.seasons[0].season)}" in MORE


def test_the_last_games_list_only_adds_the_lines_verdict():
    home = _fn(MORE, "teamHomeHTML")
    assert "const said = strip && !last.some((x) => x.line != null || x.ou);" in home
    assert "const recent = last.length && !said ? `<div class=\"section-title\">Last ${last.length}</div>" in home
    # What it would add: the cover and the over/under, which the strip's cells do not draw.
    row = _fn(MORE, "teamScheduleRowHTML")
    assert 'g.covered === true ? "covered"' in row and "g.ou ? `${g.ou} ${g.total}`" in row
    strip = home[home.index("const strip = "):home.index("const g = teamOnBoard(")]
    assert "covered" not in strip and "g.ou" not in strip


def test_an_injury_return_is_said_once_and_as_a_day():
    # One wording, the injuries page's (app.js injRet: "return Sun, Nov 29"), on the team page, the roster and a
    # pick card (walk 13 joined the three walk 11 had left saying it two ways).
    row = _fn(MORE, "teamInjuryRowHTML")
    assert "[r.injury, injRet(r)]" in row and "`back ${" not in row
    assert 'const back = p.return_date ? ` · ${escapeHtml(injRet(p))}` : "";' in MORE
    assert "` · back ${escapeHtml(String(p.return_date).slice(5))}`" not in MORE
    note = _fn(APP, "pickInjuryNote")
    assert "[inj.injury, injRet(inj)]" in note and "`expected back ${" not in note


def test_the_chart_leaves_the_cards_numbers_for_that_game():
    # The page hands the chart its card's tiles, and the chart's tile says nothing the card said.
    assert 'el.dataset.said = g && !g.dnp && !g.pending ? (g.tiles || []).map((t) => t.id).join(",") : "";' in PLR
    assert 'said: String(d.said || "").split(",").filter(Boolean),' in CC
    tile = _inner(CC, "tile")
    assert 'if (S && S.said && S.said.has(k)) return "";' in tile
    assert "S.said = same ? cardSaid(S.kind, C.said) : null;" in CC
    i = CC.index("S.said = same ? cardSaid(S.kind, C.said) : null;")
    j = CC.index("    S.said = null;\n    box.innerHTML =", i)
    assert i < j, "cleared once the render's tiles are drawn"
    # The table, by the card's column ids (engine/playerpage.TILES), lifted and run.
    k = CC.index("  const CARD_SAYS = {")
    table = CC[k:CC.index("\n  };\n", k) + 5]
    said = _inner(CC, "cardSaid")
    got = _node(table + "\n" + said + """
      const show = (x) => (x ? [...x].sort() : null);
      console.log(JSON.stringify({
        hoops: show(cardSaid("shots", ["box.pts", "box.reb", "box.ast", "box.fg"])),
        qbCarries: show(cardSaid("carries", ["passing.rtg", "passing.pct", "passing.yds", "passing.td"])),
        back: show(cardSaid("carries", ["rushing.car", "rushing.yds", "rushing.avg", "rushing.td"])),
        goalie: show(cardSaid("saves", ["goalie.sv", "goalie.sa", "goalie.svp", "goalie.ga"])),
        none: show(cardSaid("shots", [])),
      }));""")
    if got is not None:
        assert got["hoops"] == ["Assists", "FG", "Points", "Rebounds"], got
        assert got["qbCarries"] is None, "a passer's card says nothing a carries chart says"
        assert got["back"] == ["Carries", "TD", "Yards", "Yds/carry"], got
        assert got["goalie"] == ["GA", "Save %", "Saves", "Shots"], got
        assert got["none"] is None
    # Every label in the table is a tile its chart draws, and every id one the server's card shows.
    sheets = {"shots": "chart-hoops.js", "carries": "carrychart.js", "routes": "carrychart.js",
              "passes": "carrychart.js", "kicks": "chart-kicks.js", "shotmap": "chart-nhl.js", "saves": "chart-nhl.js"}
    server = (ROOT / "engine" / "playerpage.py").read_text(encoding="utf-8")
    tiles = server[server.index("TILES = {"):server.index("\n}\n", server.index("TILES = {"))]
    for kind, ids in re.findall(r'(\w+): \{([^}]*)\}', table):
        src = (JS / sheets[kind]).read_text(encoding="utf-8")
        for cid, label in re.findall(r'"([\w.]+)": "([^"]+)"', ids):
            assert f'tile("{label}"' in src, (kind, label)
            assert f'"{cid}"' in tiles, (kind, cid)


def test_a_phone_stacks_the_previous_games_sides():
    i = PLR_CSS.index("@media (max-width: 480px) {")
    rule = PLR_CSS[i:PLR_CSS.index("\n}\n", i)]
    assert ".plr-side, .plr-side:last-child { flex-direction: column; text-align: center; gap: 4px; }" in rule
    assert ".plr-pts, .plr-side:last-child .plr-pts { margin: 0; }" in rule


def test_a_headline_pick_reads_as_its_bet():
    got = _node('const MINUS = "−"; const marketWord = (m) => ({ pts: "Points" })[m] || m;\n'
                + _fn(REC, "recPotdBet") + """
      const r = (market, side, line) => recPotdBet({ market, side, line });
      console.log(JSON.stringify([r("moneyline", "OVER", 0.5), r("spread", "OVER", 4.5), r("spread", "OVER", -3.5),
        r("spread", "OVER", 0), r("total", "OVER", 222.5), r("total", "UNDER", 40.5), r("team_total", "OVER", 24.5),
        r("pts", "OVER", 24.5), r("spread", "OVER", null)]));""")
    if got is not None:
        assert got == ["moneyline", "+4.5", "−3.5", "pick’em", "over 222.5", "under 40.5", "team total over 24.5",
                       "over 24.5 Points", "spread"], got
    sec = _fn(REC, "recPotdSection")
    assert "${escapeHtml(recPotdBet(r))} · ${american(r.odds)}" in sec
    assert 'escapeHtml(String(r.market || ""))' not in sec


def test_a_list_of_books_names_each_rows_book():
    got = _node(_fn(REC, "recBookOf") + "\nconst _recMixed = new WeakMap();\n" + _fn(REC, "recMixed") + """
      const ml = { grade: "Likely (staked)" }, edge = { grade: "Play" }, tier = { grade: "Worth a look" };
      const one = [ml, { grade: "Likely" }], two = [ml, edge, tier];
      console.log(JSON.stringify([recBookOf(ml), recBookOf(edge), recBookOf({ grade: "B+" }), recBookOf(tier),
        recBookOf({ grade: "Strong" }), recBookOf({ grade: "Pick of the Day" }), recMixed(one), recMixed(two),
        recMixed(undefined)]));""")
    if got is not None:
        assert got == ["Most Likely", "Edge", "Edge", "Most Likely board", "Most Likely board", "Pick of the Day",
                       False, True, False], got
    row = _fn(REC, "recSettledRow")
    assert row.startswith("function recSettledRow(b, i, all) {")
    assert "recMixed(all) ? ` · ${escapeHtml(recBookOf(b))}` : \"\"" in row


def test_the_process_tile_says_decisions_not_a_record():
    assert "`${pr.good || 0}<i>good</i> ${pr.bad || 0}<i>bad</i>`" in REC
    assert "<i>W</i>" not in REC
    assert "${pr.flat ? ` · ${pr.flat} closed where we bet` : \"\"}" in REC


def test_the_verdict_lives_with_the_record_and_says_whose_claim():
    for name in ("recordVerdictHTML", "verdictBooksHTML", "combinedLineHTML", "moneySplitHTML", "reliabilityDiagram"):
        assert f"function {name}(" not in APP, f"{name} is first-visit bytes again"
        assert f"function {name}(" in REC, name
    v = _fn(REC, "recordVerdictHTML")
    assert "pooled ? `the Edge picks’ chance, ${calN} graded` : \"what the model said\"" in v
    assert 'pooled ? "how often those Edge picks hit" : "what happened"' in v


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
