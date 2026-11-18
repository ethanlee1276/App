"""Walk 15's fixes (2026-11-18, step YE): Islam Makhachev's page, Arch
Manning's, Connor Hellebuyck's, college basketball's injuries, and the Record
page and the top bar on a computer.

  - a fighter's page could not be reached: UFC is a tab of its own, not a
    league the board switches to, so the search stayed on the league before
    it and read "No NFL players match “Islam Makhachev”" from the UFC tab, its
    own UFC chip, a UFC pick and a reload. The search has a league of its own
    now (searchLeague), and a fighter's address names UFC (#player/ufc/…);
  - the fighter's Career strip opened on the record the header says above it;
  - the card's game in a passing chart said "TD–INT 1–3" under a card saying
    TD 0 (the play file against the box score): that game's tile keeps the
    interceptions alone (the chart's other college fix is
    tests/test_a_college_chart_game_takes_the_box_scores_side.py);
  - college basketball's empty injury board read "rare — or the feed
    declined"; it is college football's sparse board, said the same way;
  - the Record's windows read "Lifetime, 7 days, 90 days, 30 days";
  - the top bar's search field at 1280px read "Searcl".

    python3 tests/test_walk_fifteen_says_it_once.py
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "web" / "js"
APP = (JS / "app.js").read_text(encoding="utf-8")
PLR = (JS / "playerpage.js").read_text(encoding="utf-8")
CC = (JS / "carrychart.js").read_text(encoding="utf-8")
MORE = (JS / "more.js").read_text(encoding="utf-8")
REC = (JS / "record.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")


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


def test_the_search_has_a_league_of_its_own():
    i = APP.index("function searchLeague()")
    assert APP[i:APP.index("\n", i)] == "function searchLeague() { return state.searchLeague || state.sport; }"
    assert "sport=${encodeURIComponent(lg)}&scope=sport" in _fn(APP, "leagueSearch")
    sv = _fn(APP, "switchView")
    assert 'if (name !== "players") state.searchLeague = name === "ufc" ? "ufc" : "";' in sv, \
        "the UFC tab sets it; any page but the search clears it"
    assert 'if (STANDALONE_MODES.includes(lg)) state.searchLeague = lg;' in APP, "the UFC chip searches fighters here"
    assert 'if (pick) state.searchLeague = pick.sport === "ufc" ? "ufc" : "";' in _fn(APP, "openPlayerRoute")
    assert 'writeDetail(`#player/${searchLeague() === "ufc" ? "ufc/" : ""}' in APP
    assert 'state.searchLeague = p.length >= 3 && p[1] === "ufc" ? "ufc" : "";' in APP, "a reload of a fighter's address"
    assert 'state.view === "players" ? searchLeague() : state.sport' in _fn(APP, "sportRowLeague"), "the row lights UFC"
    assert "if (state.sport === b.dataset.sport && !state.searchLeague)" in APP, "NFL from a fighter's page is a way back"


def test_the_fighter_strip_leaves_the_record_to_the_header():
    got = _node(_fn(APP, "escapeHtml") + """
      const escapeAttr = escapeHtml; const plural = (n, w) => `${n} ${w}s`;
      const plrRate = (r) => (r.pct ? `${Number(r.value).toFixed(0)}%` : Number(r.value).toFixed(2));
    """ + _fn(PLR, "plrUfcRatesHTML") + """
      const d = {tracked: 15, bio: {record: "28-1-0"}, rates: [
        {label: "SLpM", value: 2.51, lead: true}, {label: "Str. def", value: 61.5, pct: true, lead: true},
        {label: "TD/15", value: 2.93, lead: true}, {label: "TDD", value: 91.3, pct: true, lead: true},
        {label: "SApM", value: 1.56}]};
      const h = plrUfcRatesHTML(d);
      console.log(JSON.stringify({labels: (h.match(/plr-k">[^<]+/g) || []).map((x) => x.slice(7)),
                                  record: /28-1-0/.test(h), none: plrUfcRatesHTML({bio: {record: "1-0-0"}, rates: []})}));""")
    if got is None:
        return
    assert got["labels"] == ["SLpM", "Str. def", "TD/15", "TDD"], got
    assert not got["record"] and got["none"] == "", got
    assert "bio && bio.record" in PLR, "the header says it"


def test_the_cards_game_keeps_the_interceptions_alone():
    assert '"passing.td": "TD"' in CC
    i = CC.index("  function tdIntTile(line) {")
    tile = CC[i:CC.index("\n  }\n", i)]
    assert 'S && S.said && S.said.has("TD") ? tile("INT", line.int) : tile("TD–INT", `${line.td}–${line.int}`)' in tile
    assert CC.count('tdIntTile(line), tile("Yds/att"') == 2, "the college and the NFL passing tiles"


def test_college_basketballs_sparse_board_is_said_as_college_footballs():
    assert 'const note = sport === "cfb" || sport === "cbb"' in MORE
    assert "The news below names who is hurt." in MORE


def test_the_record_windows_keep_their_order():
    got = _node(_fn(APP, "escapeHtml") + "const escapeAttr = escapeHtml;\n" + _fn(REC, "recRanges")
                + _fn(REC, "recordWindowHTML") + """
      const h = recordWindowHTML([["all", Infinity, "Lifetime"], ["1w", 7, "7 days"]], "all",
        [["3m", 90, "90 days", "why"], ["1m", 30, "30 days", "The record covers 27 days so far"]]);
      console.log(JSON.stringify((h.match(/>(Lifetime|\\d+ days)</g) || []).map((x) => x.slice(1, -1))));""")
    if got is not None:
        assert got == ["Lifetime", "90 days", "30 days", "7 days"], got


def test_the_narrow_search_field_shows_the_glass_alone():
    assert ".ns-field { flex-shrink: 1; min-width: 72px; container-type: inline-size; }" in CSS
    assert "@container (max-width: 110px) { .ns-input::placeholder { color: transparent; } }" in CSS
    assert ".ns-input { text-overflow: ellipsis; }" in CSS


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
