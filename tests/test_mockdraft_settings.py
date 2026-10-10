"""The mock draft's settings, built to the screen Ethan sent.

Ethan, 2026-09-08, with a screenshot of FantasyPros' mock-draft settings:
"can you work on making the mock draft better. Here is an example of
more shit to add." Two cards on it — LEAGUE SETTINGS (select league,
scoring, draft type, teams, a roster line) and MOCK DRAFT SETTINGS
(draft position, cheat sheet, pick clock).

What this pins, half by reading the page and half by running its
arithmetic in node:

  * scoring and the line-up are two settings, and the format the draft
    runs on is COMPOSED from them — half PPR takes half a catch back off
    the PPR board, a superflex slot draws the superflex share bands, a
    TE premium the TE bands;
  * the roster decides the rounds, and the kicker and defence slots the
    board cannot fill are counted, said, and not drafted as blanks;
  * three draft orders, chosen by name; the default is the snake;
  * the cheat sheet orders the pool, the default card and the auto-pick;
  * the pick clock is yours, opt-in, off by default, and does something
    at zero;
  * settings survive a reload, and a corrupt store cannot throw;
  * a Sleeper league's own settings map onto all of it, and what cannot
    map is said.

Run directly: `python3 tests/test_mockdraft_settings.py`
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
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}", i) + 2]


# --- the page ------------------------------------------------------------
def test_the_two_cards_are_the_screenshots():
    body = _fn("_mockSetupHTML")
    assert "League settings" in body and "Mock draft settings" in body
    for ctl in ("mk-scoring", "mk-teprem", "mk-type", "mk-sheet", "mk-clock", "mk-chaos",
                '_mockStep("teams"', '_mockStep("slot"', '"roster." + k',
                "mk-use-league", "mk-start"):
        assert ctl in body, f"the panel lost {ctl}"
    # The roster line reads the way the screenshot writes it.
    assert "QB/WR/RB/TE" in _fn("_mockRosterLine") and "WR/RB/TE" in _fn("_mockRosterLine")


def test_scoring_and_the_line_up_are_two_settings_and_the_format_is_composed():
    fmt = _fn("_mockFmt")
    assert "_mockCfgSlots()" in fmt and "_mockCfgBonus()" in fmt, \
        "the format no longer reads the settings"
    assert "MOCK_FORMATS[_mockFormat]" in fmt, "the share bands no longer come from the preset"
    key = _fn("_mockCfgFormatKey")
    assert 'return "superflex"' in key and 'return "te_prem"' in key
    assert "roster.SFLEX" in key and "tePrem" in key
    # Keyed off the line-up and the scoring, never a format name.
    assert '"format"' not in key
    start = _fn("_mockStart")
    assert "_mockFormat = _mockCfgFormatKey()" in start
    assert "_mockDraftType = " in start
    assert "_mockScoreBoard((kit.board || []).slice(), _mockFmt(), teams)" in start, \
        "the board is scored at a default league size again"


def test_kicker_and_defence_are_on_the_line_and_not_in_the_draft():
    rounds = _fn("_mockCfgRounds")
    assert '- (r.K || 0) - (r.DST || 0)' in rounds
    assert "skipped" in rounds
    panel = _fn("_mockSetupHTML")
    assert "projects no kickers or defences" in panel
    assert "rounds.drafted" in panel and "rounds.league" in panel


def test_the_clock_is_yours_opt_in_and_off_by_default():
    i = APP.index("const MOCK_DEFAULT_CFG = {")
    assert "clock: 0" in APP[i:i + 400], "the clock is on by default"
    arm = _fn("_mockArmClock")
    assert "=== m.you" in arm, "the clock runs on somebody else's pick"
    assert "_mockAutoPick()" in arm, "nothing happens at zero"
    assert "!el || _mock !== m" in arm, "the clock outlives the room"
    auto = _fn("_mockAutoPick")
    assert "_mockNeedCounts(" in auto, "the auto-pick can hand you an illegal player"
    assert "_mockSheet(m)" in auto, "the auto-pick ignores the cheat sheet"
    # Your own click and the abandon button both stop it.
    bind = _fn("_mockBind")
    assert bind.count("_mockStopClock()") >= 2
    # The hero shows it only when it is set, on your pick, and in whole
    # seconds — never a fake "00:47" on a CPU seat.
    room = APP[APP.index("function mockDraftHTML("):APP.index("\nfunction _mockRender(")]
    assert 'id="mk-clock"' in room and "m.cfg.clock" in room
    assert "00:" not in room


def test_the_cheat_sheet_orders_the_pool_the_card_and_the_auto_pick():
    sheet = _fn("_mockSheet")
    assert '"market" ? _mockByMarket(m) : m.pool' in sheet
    room = APP[APP.index("function mockDraftHTML("):APP.index("\nfunction _mockRender(")]
    assert "const sheet = _mockSheet(m);" in room
    assert "sheet.slice(0, 40)" in room and "|| sheet[0]" in room
    assert "_mockSheet(m)" in _fn("_mockAutoPick")


def test_settings_survive_a_reload_and_a_corrupt_store_cannot_throw():
    assert 'const MOCK_CFG_KEY = "qb_mock_cfg"' in APP
    load = _fn("_mockLoadCfg")
    assert "try {" in load and "catch (e)" in load
    assert 'typeof localStorage === "undefined"' in load
    clean = _fn("_mockCleanCfg")
    for k in ("scoring", "tePrem", "draftType", "teams", "slot", "sheet", "clock", "chaos", "roster"):
        assert f"{k}" in clean, f"the clean-up forgets {k}"
    save = _fn("_mockSaveCfg")
    assert "_mockCleanCfg(_mockCfg)" in save and "localStorage.setItem(MOCK_CFG_KEY" in save
    bind = _fn("_mockBind")
    assert "_mockSaveCfg()" in bind


def test_the_advice_and_the_keeper_rounds_read_the_league_not_a_constant():
    assert "_mockFmt().slots[pos]" in _fn("_mockAdvice")
    assert "MOCK_SLOTS[pos]" not in _fn("_mockAdvice")
    keep = _fn("_mockKeeperHTML")
    assert "_mockCfgRounds(" in keep, "the keeper editor offers rounds the league does not draft"


def test_the_panel_is_styled():
    for sel in (".mk-settings {", ".mk-setcard {", ".mk-row {", ".mk-step {",
                ".mk-step-btn {", ".mk-presets {", ".mk-clock {", ".mk-clock-low {",
                ".mk-startbtn {"):
        assert sel in CSS, f"{sel} is unstyled"


def test_the_league_import_reads_the_leagues_own_objects():
    src = _fn("_mockUseLeague")
    assert "sleeperGet(`league/${leagueId}`)" in src
    assert "sleeperGet(`league/${leagueId}/drafts`)" in src
    assert "const current = drafts[0] || null;" in src
    assert "_mockApplyLeague(league, current, user.user_id, _mockCfg)" in src
    # The proxy allows exactly those paths.
    server = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    assert "league/\\d{1,25}(/rosters|/users|/drafts)?" in server


# --- the arithmetic, run ---------------------------------------------------
if not _shutil.which("node"):
    print("SKIP node is not installed; the arithmetic half of this file "
          "executes the settings rather than reading them.")

_HARNESS = r"""
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");
function grab(name, end) {
  const i = src.indexOf(name);
  if (i < 0) throw new Error("missing: " + name);
  const j = src.indexOf(end, i);
  return src.slice(i, j + end.length);
}
const code = [
  grab("const MOCK_FORMATS = {", "\n};"),
  // `var`, not `let`: a `let` inside a direct eval is scoped to the eval,
  // and the harness below reassigns both of these.
  "var _mockFormat = 'ppr';",
  grab("const MOCK_SCORING = {", "};"),
  grab("const MOCK_DRAFT_TYPES = {", "};"),
  grab("const MOCK_SHEETS = {", "};"),
  grab("const MOCK_CLOCKS = [", "];"),
  grab("const MOCK_TEAMS_RANGE = [", "];"),
  grab("const MOCK_ROSTER_MAX = {", "};"),
  grab("const MOCK_DEFAULT_CFG = {", "} };"),
  grab("const MOCK_PRESETS = {", "\n};"),
  grab("const MOCK_SLEEPER_SLOT = {", "};"),
  grab("function _mockCleanCfg(", "\n}"),
  grab("function _mockLoadCfg(", "\n}"),
  "var _mockCfg = _mockLoadCfg();",
  grab("function _mockCfgSlots(", "\n}"),
  grab("function _mockCfgBonus(", "\n}"),
  grab("function _mockCfgFormatKey(", "\n}"),
  grab("function _mockCfgLabel(", "\n}"),
  grab("function _mockCfgRounds(", "\n}"),
  grab("function _mockRosterLine(", "\n}"),
  grab("function _mockFmt(", "\n}"),
  grab("function _mockApplyLeague(", "\n}"),
  grab("function _mockPicker(", "\n}"),
  grab("function _mockScoreBoard(", "\n}"),
].join("\n");
var _mock = null;                       // no draft in progress, as at setup
eval(code);
const out = {};
// THE BOARD IS SCORED AT THE LEAGUE'S SIZE. Forty backs on a board: at
// four teams the replacement is the twelfth back (2 starters x 4 plus
// the flex share); at twelve it is the thirty-fifth. The top back's
// value over replacement must differ, or the size handed in is ignored.
const backs = Array.from({ length: 40 }, (_, i) =>
  ({ player: "RB" + i, position: "RB", proj: 60 - i, rec_pg: 2 }));
const fmt0 = _mockFmt();
out.vorp4 = _mockScoreBoard(backs.slice(), fmt0, 4).find((p) => p.player === "RB0").vorp;
out.vorp12 = _mockScoreBoard(backs.slice(), fmt0, 12).find((p) => p.player === "RB0").vorp;
// A corrupt store cleans to the defaults; a wild value clamps.
out.clean_null = _mockCleanCfg(null);
out.clean_wild = _mockCleanCfg({ teams: 40, slot: 99, scoring: "nope", clock: 7,
                                 roster: { QB: 9, RB: -2, BN: "x" }, draftType: "auction" });
// Half PPR takes half a catch back; a TE premium adds on top.
_mockCfg = _mockCleanCfg({ scoring: "half", tePrem: 0.5 });
out.half_bonus = _mockCfgBonus();
out.half_key = _mockCfgFormatKey();
out.half_label = _mockCfgLabel();
// A superflex slot draws the superflex bands and a bigger QB cap.
_mockCfg = _mockCleanCfg({ roster: { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, SFLEX: 1, K: 1, DST: 1, BN: 6 } });
_mockFormat = _mockCfgFormatKey();
out.sf_key = _mockFormat;
out.sf_caps = _mockFmt().caps;
out.sf_slots = _mockFmt().slots;
out.sf_share_first = _mockFmt().share[0].share;
// The screenshot's roster: QB, 2RB, 3WR, WR/RB/TE, TE, K, DST, 6BN → 16
// rounds, 14 drafted here; on a 150-man board at 10 teams the slack is 13.
_mockCfg = _mockCleanCfg({ teams: 10, roster: { QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, SFLEX: 0, K: 1, DST: 1, BN: 6 } });
out.line = _mockRosterLine();
out.rounds_big = _mockCfgRounds(_mockCfg, 1000, 10);
out.rounds_150 = _mockCfgRounds(_mockCfg, 150, 10);
// The default picker is the snake unless a draft says otherwise.
out.default_order = [0, 1, 2, 3].map((p) => _mockPicker(p, 4)).concat([4, 5, 6, 7].map((p) => _mockPicker(p, 4)));
_mockDraftType = "linear";
out.global_order = [4, 5, 6, 7].map((p) => _mockPicker(p, 4));
// A Sleeper league, mapped.
_mockCfg = _mockCleanCfg(null);
const league = { name: "Boys", total_rosters: 10,
  roster_positions: ["QB", "RB", "RB", "WR", "WR", "WR", "FLEX", "TE", "K", "DEF", "BN", "BN", "BN", "BN", "BN", "BN", "IR", "IDP_FLEX"],
  scoring_settings: { rec: 0.5, bonus_rec_te: 0.5 } };
const draft = { type: "snake", settings: { reversal_round: 3, pick_timer: 80 },
                draft_order: { "u1": 5, "u2": 1 } };
out.league_notes = _mockApplyLeague(league, draft, "u1", _mockCfg);
out.league_cfg = JSON.parse(JSON.stringify(_mockCfg));
_mockCfg = _mockCleanCfg(null);
out.auction_notes = _mockApplyLeague({ total_rosters: 12 }, { type: "auction", settings: { pick_timer: 0 } }, "nobody", _mockCfg);
out.auction_cfg = JSON.parse(JSON.stringify(_mockCfg));
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


def test_a_corrupt_store_cleans_to_the_defaults_and_wild_values_clamp():
    r = _run()
    if r is None:
        return
    d = r["clean_null"]
    assert d["scoring"] == "ppr" and d["teams"] == 12 and d["clock"] == 0 and d["draftType"] == "snake"
    w = r["clean_wild"]
    assert w["teams"] == 16 and w["slot"] == 16, w
    assert w["scoring"] == "ppr" and w["clock"] == 0 and w["draftType"] == "snake"
    assert w["roster"]["QB"] == 2 and w["roster"]["RB"] == 0 and w["roster"]["BN"] == 6, w["roster"]


def test_half_ppr_takes_half_a_catch_back_and_the_te_premium_adds_on_top():
    r = _run()
    if r is None:
        return
    assert r["half_bonus"] == {"RB": -0.5, "WR": -0.5, "TE": 0, "QB": 0}, r["half_bonus"]
    assert r["half_key"] == "te_prem"
    assert r["half_label"] == "Half PPR · TE +0.5"


def test_a_superflex_slot_draws_the_superflex_bands_and_a_bigger_qb_cap():
    r = _run()
    if r is None:
        return
    assert r["sf_key"] == "superflex"
    assert r["sf_slots"]["SFLEX"] == 1 and r["sf_slots"]["FLEX"] == 1
    assert r["sf_caps"]["QB"] >= 3 and r["sf_caps"]["QB"] >= r["sf_slots"]["QB"] + r["sf_slots"]["SFLEX"] + 1
    assert r["sf_share_first"]["QB"] >= 0.25, "round one is not drafting quarterbacks"


def test_the_roster_decides_the_rounds_and_the_board_caps_them():
    r = _run()
    if r is None:
        return
    assert r["line"] == "QB, 2RB, 3WR, WR/RB/TE, TE, K, DST, 6BN"
    big = r["rounds_big"]
    assert (big["league"], big["wanted"], big["drafted"], big["skipped"]) == (16, 14, 14, 2), big
    small = r["rounds_150"]
    assert small["drafted"] == 13 and small["wanted"] == 14, small


def test_the_board_is_scored_at_the_leagues_size_not_a_default_twelve():
    """`_mockScoreBoard` read the size off `_mock`, which at the moment
    the board is scored is the previous draft or null — so a ten-team
    league's replacement level was computed for a twelve-team one, every
    draft. The size is handed in now, and it changes the answer."""
    r = _run()
    if r is None:
        return
    assert r["vorp4"] != r["vorp12"], (r["vorp4"], r["vorp12"])
    assert r["vorp4"] < r["vorp12"], "a smaller league has a nearer replacement"


def test_the_default_order_is_the_snake_and_a_draft_can_say_otherwise():
    r = _run()
    if r is None:
        return
    assert r["default_order"] == [0, 1, 2, 3, 3, 2, 1, 0]
    assert r["global_order"] == [0, 1, 2, 3]


def test_a_sleeper_league_maps_onto_every_setting_and_says_what_it_dropped():
    r = _run()
    if r is None:
        return
    c = r["league_cfg"]
    assert c["teams"] == 10 and c["slot"] == 5
    assert c["roster"] == {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 1, "SFLEX": 0, "K": 1, "DST": 1, "BN": 6}, c["roster"]
    assert c["scoring"] == "half" and c["tePrem"] == 0.5
    assert c["draftType"] == "3rr" and c["clock"] == 90
    notes = " · ".join(r["league_notes"])
    assert "IR/IDP_FLEX" in notes and "dropped" in notes, notes
    assert "your seat is 5" in notes and "3rd-round reversal" in notes and "90s clock" in notes
    a = r["auction_cfg"]
    assert a["draftType"] == "snake" and a["clock"] == 0 and a["teams"] == 12
    assert "auction" in " ".join(r["auction_notes"])


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
