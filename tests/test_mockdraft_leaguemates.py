"""Leaguemates' draft tendencies, measured from your Sleeper league.

Ethan, 2026-09-08, with FantasyPros' mock-draft settings screen: "can you
work on making the mock draft better. Here is an example of more shit
to add." Under its "Select League" row: "More realistic mock drafts
using your league's settings and leaguemates' draft tendencies." The
settings shipped first; this is the tendencies.

A room of builds drawn from a weight table is a room of strangers. Your
league is eleven particular people, and the one thing known about how
each of them drafts is how they drafted: Sleeper keeps every pick of
every past draft keyed by the manager who made it. So the page reads
the most recent completed draft and measures each manager's build from
the first six rounds, then deals that build to the room the league's
draft order seats them in.

What this pins, half by reading the page and half by running the read
in node on a fixture draft:

  * each of the nine builds is recognised from the shape that defines
    it — no back in five, one back early and no more, three backs in
    five, three receivers in four, a quarterback or a tight end two
    rounds before the room's median, both two rounds after it, a
    balanced first four, and best-available for the rest;
  * the quarterback and tight-end tells are read against the room's own
    median, and a room too small to have one reads neither;
  * keeper picks are not picks; a pick with no `picked_by` is charged to
    the seat on the clock; fewer than five picks is unmeasured;
  * the most recent draft a manager appears in decides; seats come from
    the draft order, or the roster list until there is one;
  * the seating applies only at the league's own size, the rooms are
    called by name where the league gave one, and the store cleans;
  * the fetch reads only paths the server's Sleeper allowlist accepts.

Run directly: `python3 tests/test_mockdraft_leaguemates.py`
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
DOC = open(os.path.join(ROOT, "docs", "DRAFT_PLAN.md"), encoding="utf-8").read()


def _fn(name):
    i = APP.index(name)
    return APP[i:APP.index("\n}", i)]


# --- what the page reads ---------------------------------------------------
def test_the_rooms_are_seated_from_the_league_not_only_drawn():
    """`_mockStart` dealt every room a draw from the table. It asks the
    league first now, and the draw is what an unmeasured room gets."""
    start = _fn("function _mockStart(")
    assert "_mockSeatRooms(teams, _mockLeague)" in start, "rooms are drawn, not seated"
    seat = _fn("function _mockSeatRooms(")
    assert "_mockDrawArchetype()" in seat, "an unmeasured room has no build"
    assert "league.teams !== teams" in seat, \
        "a twelve-team seating is being applied to a ten-team room"


def test_the_rooms_are_called_by_name_where_the_league_gave_one():
    room = APP[APP.index("function mockDraftHTML("):]
    room = room[:room.index("\nfunction _mockSetupHTML(")]
    assert room.count("_mockRoomName(m,") >= 4, \
        "the pick log, the board, the clock line and the hero no longer share one name"
    assert '"Room " + (e.team + 1)' not in room and '"Team " + (e.team + 1)' not in room, \
        "a room is numbered where the league named it"
    # Sleeper names are the league's text, not ours: escaped on every
    # surface they reach.
    assert "escapeHtml(_mockRoomName(m," in room
    assert 'title="${escapeAttr(_mockRoomTitle(m, e.team))}"' in room


def test_the_fetch_reads_this_season_then_last_and_only_completed_drafts():
    use = APP[APP.index("async function _mockUseLeague("):]
    use = use[:use.index("\n}")]
    for needle in ("league/${leagueId}/users", "league.previous_league_id",
                   "league/${league.previous_league_id}/drafts",
                   "draft/${d.draft_id}/picks", 'd.status !== "complete"',
                   "_mockBuildLeague(league, current, users, rosters",
                   "_mockSaveLeague()", "_mockLeagueSummary(_mockLeague)"):
        assert needle in use, f"the league read lost: {needle}"
    # The roster list is a fallback for a draft with no order, not a
    # second read on every click.
    assert "Object.keys(current.draft_order || {}).length" in use
    # A draft that will not read is a draft not measured, not a failed click.
    assert use.count("catch (e)") >= 4


def test_every_path_the_read_touches_is_on_the_servers_allowlist():
    from server import sleeper_path_ok as ok
    for path in ("league/123456/users", "league/123456/rosters",
                 "league/123456/drafts", "draft/987654/picks"):
        assert ok(path), path
    assert not ok("league/123456/transactions/1"), "the allowlist is wider than the read"


def test_the_panel_lists_the_seats_and_the_doc_says_the_mock_is_the_exception():
    setup = _fn("function _mockSetupHTML(")
    assert "${_mockMatesHTML(c)}" in setup, "the seats are read and never shown"
    mates = _fn("function _mockMatesHTML(")
    assert "unmeasured" in mates and "mk-mate-line" in mates and "escapeHtml(s.name" in mates
    assert "seated at ${lg.teams} teams" in mates, "a size mismatch is silent"
    assert ".mk-mate-line" in CSS and ".mk-mates" in CSS
    assert "_mockBuildLeague" in DOC and "previous_league_id" in DOC


# --- the read, run ----------------------------------------------------------
if not _shutil.which("node"):
    print("SKIP node is not installed; the arithmetic half of this file "
          "executes the read rather than reading it.")

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
  // `var`, not `const`: a `const` inside a direct eval is scoped to the
  // eval, and the harness below reads the table's keys after it.
  grab("const MOCK_ARCHETYPES = [", "\n];").replace("const MOCK_ARCHETYPES", "var MOCK_ARCHETYPES"),
  grab("const MOCK_ARCH_TOTAL", ";"),
  grab("function _mockDrawArchetype(", "\n}"),
  grab("const MOCK_TELL_ROUNDS", ";"),
  grab("const MOCK_TELL_MIN_PICKS", ";"),
  grab("const MOCK_MATE_NAME_MAX", ";"),
  grab("function _mockShapeOf(", "\n}"),
  grab("function _mockRoomMedians(", "\n}"),
  grab("function _mockTendency(", "\n}"),
  grab("function _mockReadDraft(", "\n}"),
  grab("function _mockBuildLeague(", "\n}"),
  grab("function _mockCleanLeague(", "\n}"),
  grab("function _mockLeagueFrom(", "\n}"),
  grab("function _mockLeagueSummary(", "\n}"),
  grab("function _mockSeatRooms(", "\n}"),
  grab("function _mockRoomName(", "\n}"),
  grab("function _mockRoomTitle(", "\n}"),
].join("\n");
eval(code);
const out = {};

// TWELVE MANAGERS, ONE SHAPE EACH, rounds one to eight (u8 has nine).
// The medians they make: first QB 7, first TE 6 — so early is a
// quarterback by round 5 or a tight end by round 4, late is both a
// quarterback in 9 and a tight end in 8 or never.
const SHAPES = {
  u1: "RB RB RB WR WR WR QB TE",        // three backs in five: robust
  u2: "WR WR WR WR TE RB QB RB",        // no back in five: zero
  u3: "RB WR WR WR TE WR QB RB",        // one back, early, no more: hero
  u4: "WR WR WR RB RB QB TE RB",        // three receivers in four: hoarder
  u5: "QB RB WR RB WR TE RB WR",        // quarterback at 1.01: early QB
  u6: "RB TE WR RB WR QB WR RB",        // tight end in two: elite TE
  u7: "RB WR WR RB WR RB WR RB",        // neither, ever: late-round onesies
  u8: "RB WR RB WR WR WR K QB TE",      // two and two, QB in 8: balanced
  u9: "WR WR K RB WR TE QB RB",         // one back, late, two receivers: bpa
  u10: "RB WR WR",                      // three picks: unmeasured
  u11: "RB RB WR WR WR TE QB RB",       // round one is a KEEPER: hero
  u12: "RB RB WR WR TE QB WR RB",       // you: balanced
};
const ORDER_2025 = { u1: 1, u2: 2, u3: 3, u4: 4, u5: 5, u6: 6, u7: 7, u8: 8, u9: 9, u10: 10, u11: 11, u12: 12 };
const picks2025 = [];
for (const [uid, line] of Object.entries(SHAPES)) {
  line.split(" ").forEach((pos, i) => picks2025.push({
    round: i + 1, draft_slot: ORDER_2025[uid],
    // u3's picks carry no picked_by: charged to the seat on the clock.
    picked_by: uid === "u3" ? "" : uid,
    pick_no: i * 12 + ORDER_2025[uid],
    is_keeper: uid === "u11" && i === 0 ? true : null,
    metadata: { position: pos, first_name: pos, last_name: String(i + 1) } }));
}
const draft2025 = { draft_id: "d2025", season: "2025", status: "complete", type: "snake",
                    draft_order: ORDER_2025, settings: { rounds: 15 } };
const read = _mockReadDraft(draft2025, picks2025);
out.room = read.room;
out.keys = Object.fromEntries(Object.entries(read.managers).map(([u, m]) => [u, m.key]));
out.lines = { u1: read.managers.u1.line, u11: read.managers.u11.line, u10: read.managers.u10.line };
out.picks_u11 = read.managers.u11.picks;

// A ROOM TOO SMALL FOR A MEDIAN reads no timing tell: with two
// managers there is no room to be early against, so a quarterback at
// 1.01 reads as best-available, not early QB — the other, two and two.
const tiny = [];
const TINY = { a: "QB RB WR RB WR TE RB WR", b: "RB WR RB WR WR TE QB RB" };
for (const [uid, line] of Object.entries(TINY)) line.split(" ").forEach((pos, i) =>
  tiny.push({ round: i + 1, picked_by: uid, metadata: { position: pos } }));
const tinyRead = _mockReadDraft({ season: "2024", draft_order: { a: 1, b: 2 } }, tiny);
out.tiny_room = tinyRead.room;
out.tiny_keys = { a: tinyRead.managers.a.key, b: tinyRead.managers.b.key };

// THIS SEASON'S DRAFT, done, says u1 went Zero RB; last season's says
// Robust. The most recent decides, and the seat says which season.
const picks2026 = "WR WR WR WR TE RB QB RB".split(" ").map((pos, i) =>
  ({ round: i + 1, picked_by: "u1", metadata: { position: pos } }));
const draft2026 = { draft_id: "d2026", season: "2026", status: "complete", type: "snake",
                    draft_order: { u1: 1 } };
// THE CURRENT DRAFT, not yet run, seats everybody.
const ORDER_NOW = { u2: 1, u3: 2, u4: 3, u5: 4, u12: 5, u6: 6, u7: 7, u8: 8, u9: 9, u10: 10, u11: 11, u1: 12 };
const current = { draft_id: "dnow", season: "2026", status: "pre_draft", type: "snake", draft_order: ORDER_NOW };
const league = { league_id: "L1", name: "Boys", total_rosters: 12, previous_league_id: "L0" };
const users = [
  { user_id: "u1", display_name: "Mike", metadata: { team_name: "Mike's Marauders" } },
  { user_id: "u2", display_name: "dan" },
  { user_id: "u4", display_name: "Pat", metadata: { team_name: "A Team Name Far Too Long For The Panel" } },
  { user_id: "u12", display_name: "ethan" },
];
const built = _mockBuildLeague(league, current, users, [], [
  { draft: draft2026, picks: picks2026 }, { draft: draft2025, picks: picks2025 }], "u12");
out.built = { teams: built.teams, you: built.you, measured: built.measured, from: built.from,
              seats: built.seats.map((s) => [s.slot, s.userId, s.name, s.key, s.from]) };
out.summary = _mockLeagueSummary(built);
const clean = _mockCleanLeague(built);
out.clean_name_u4 = clean.seats.find((s) => s.userId === "u4").name;
out.clean_measured = clean.measured;

// SEATED at twelve, drawn at ten.
const at12 = _mockSeatRooms(12, clean);
const keys = new Set(MOCK_ARCHETYPES.map((a) => a.key));
out.seat12 = { u1: [at12[11].key, at12[11].who, at12[11].measured, at12[11].from],
               u10: [keys.has(at12[9].key), at12[9].who, at12[9].measured],
               u2: [at12[0].key, at12[0].who], all_named: at12.every((p) => "who" in p) };
const at10 = _mockSeatRooms(10, clean);
out.seat10_named = at10.filter((p) => p.who).length;
out.seat10_keys_ok = at10.every((p) => keys.has(p.key));

// SEATS FROM THE ROSTER LIST when the draft has no order yet.
const byRoster = _mockBuildLeague(league, null, users,
  [{ roster_id: 1, owner_id: "u2" }, { roster_id: 2, owner_id: "u1" }, { roster_id: 3, owner_id: "" }],
  [{ draft: draft2025, picks: picks2025 }], "u12");
out.roster_seats = byRoster.seats.map((s) => [s.slot, s.userId, s.key]);

// THE STORE CLEANS.
out.clean_null = _mockCleanLeague(null);
const wild = _mockCleanLeague({ teams: 12, you: "u12", from: ["2025"], seats: [
  { slot: 13, userId: "u9", key: "robust_rb" },
  { slot: 2, userId: "u2", key: "nope", name: "x".repeat(50) },
  { slot: 5, userId: "u12", key: "balanced" }, null] });
out.wild = { n: wild.seats.length, key0: wild.seats[0].key, name0: wild.seats[0].name.length,
             measured: wild.measured };

// THE NAMES THE ROOM USES.
const m = { you: 0, personas: [
  { name: "Best available" },
  { name: "Robust RB", who: "Mike", measured: true, from: "2025", line: "RB-RB-RB-WR-WR-WR" },
  { name: "Zero RB" },
  { name: "Hero RB", who: "Dan", measured: false } ] };
out.names = [0, 1, 2, 3].map((i) => _mockRoomName(m, i));
out.titles = [0, 1, 2, 3].map((i) => _mockRoomTitle(m, i));
out.from_two = _mockLeagueFrom({ from: ["2026", "2025", "2026"] });
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


EXPECTED = {"u1": "robust_rb", "u2": "zero_rb", "u3": "hero_rb", "u4": "wr_room",
            "u5": "early_qb", "u6": "elite_te", "u7": "late_round", "u8": "balanced",
            "u9": "bpa", "u10": None, "u11": "hero_rb", "u12": "balanced"}


def test_every_build_is_recognised_from_the_shape_that_defines_it():
    r = _run()
    if r is None:
        return
    assert r["room"] == {"qb": 7, "te": 6}, r["room"]
    assert r["keys"] == EXPECTED, {k: (r["keys"].get(k), v) for k, v in EXPECTED.items()
                                   if r["keys"].get(k) != v}


def test_a_keeper_is_not_a_pick_and_a_pick_with_no_owner_charges_the_seat():
    r = _run()
    if r is None:
        return
    # u11's round-one back is a keeper: with it counted they read as
    # balanced; without it, one back early and no more — hero.
    assert r["keys"]["u11"] == "hero_rb"
    assert r["picks_u11"] == 7 and r["lines"]["u11"] == "RB-WR-WR-WR-TE", r["lines"]
    # u3's picks carry no picked_by and are charged to seat 3.
    assert r["keys"]["u3"] == "hero_rb"
    assert r["lines"]["u1"] == "RB-RB-RB-WR-WR-WR"
    assert r["lines"]["u10"] == "RB-WR-WR" and r["keys"]["u10"] is None


def test_a_room_too_small_for_a_median_reads_no_timing_tell():
    r = _run()
    if r is None:
        return
    assert r["tiny_room"] == {"qb": None, "te": None}
    assert r["tiny_keys"] == {"a": "bpa", "b": "balanced"}, r["tiny_keys"]


def test_the_most_recent_draft_decides_and_the_seats_follow_the_order():
    r = _run()
    if r is None:
        return
    b = r["built"]
    assert b["teams"] == 12 and b["you"] == "u12" and b["from"] == ["2026", "2025"]
    seats = {s[1]: s for s in b["seats"]}
    assert [s[0] for s in b["seats"]] == list(range(1, 13)), "seats are not in order"
    assert seats["u1"][0] == 12 and seats["u1"][3] == "zero_rb" and seats["u1"][4] == "2026", seats["u1"]
    assert seats["u2"][3] == "zero_rb" and seats["u2"][4] == "2025"
    assert seats["u10"][3] is None and seats["u10"][4] == ""
    assert seats["u12"][0] == 5
    assert seats["u1"][2] == "Mike's Marauders" and seats["u2"][2] == "dan" and seats["u9"][2] == ""
    # Ten measured rivals: eleven seats less the unmeasured u10; you are not a rival.
    assert b["measured"] == 10, b["measured"]
    assert r["summary"] == "10 of 11 leaguemates measured from the 2026 and 2025 drafts", r["summary"]
    assert len(r["clean_name_u4"]) == 28 and r["clean_measured"] == 10
    assert r["from_two"] == "the 2026 and 2025 drafts"


def test_seated_at_the_leagues_size_and_drawn_at_any_other():
    r = _run()
    if r is None:
        return
    s = r["seat12"]
    assert s["u1"] == ["zero_rb", "Mike's Marauders", True, "2026"], s["u1"]
    assert s["u10"] == [True, "", False], s["u10"]
    assert s["u2"] == ["zero_rb", "dan"]
    assert s["all_named"], "a seated room lost its name key"
    assert r["seat10_named"] == 0 and r["seat10_keys_ok"], \
        "a twelve-team seating leaked into a ten-team room"


def test_seats_come_from_the_roster_list_until_the_draft_has_an_order():
    r = _run()
    if r is None:
        return
    assert r["roster_seats"] == [[1, "u2", "zero_rb"], [2, "u1", "robust_rb"]], r["roster_seats"]


def test_the_store_cleans_and_the_rooms_are_named_as_the_league_named_them():
    r = _run()
    if r is None:
        return
    assert r["clean_null"] is None
    w = r["wild"]
    assert w == {"n": 2, "key0": None, "name0": 28, "measured": 0}, w
    assert r["names"] == ["You", "Mike", "Room 3", "Dan"], r["names"]
    assert r["titles"] == ["Your pick",
                           "Robust RB — measured from their 2025 draft: RB-RB-RB-WR-WR-WR",
                           "Zero RB", "Hero RB — drawn, not measured"], r["titles"]


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
