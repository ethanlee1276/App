"""A second start calendar, holding only the players he actually has.

Ethan, 2026-09-09: *"we can show the calendar like we use for the fantasy
projections … but what we need to do is make that calendar specific to a
players league if they have their league sync, so we'll still show the
calendar that we already show. I will show a different one with that
person fantasy players they have."*

Same component, same arithmetic, one filter. That is the design and it is
the reason the two are worth putting side by side: the day the LEAGUE
calls elite and the day HIS ROSTER calls elite are the same number
computed over different sets of players, and watching them disagree is
the whole product.

Two things had to change to allow it, and both are what this file guards:

  * THE SELECTION IS PER CALENDAR. `_ffCalSel`, `_ffCalPick` and
    `_ffCalMonth` were three module-level variables. With two instances on
    screen, tapping Thursday on one would have moved the other — so they
    are namespaced, and the delegated click handler reads which instance
    was tapped off the target's own root.
  * THE MISSING MEN ARE NAMED. The projection board carries 150 players
    and a roster is fifteen; a handcuff back or a rookie tight end is on
    neither. Ranking six of his eleven and calling it his calendar would
    be the worst kind of quiet.

Run directly: `python3 tests/test_roster_calendar.py`
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _fn(name):
    i = APP.index(f"function {name}(")
    j = APP.index("{", i)
    depth = 0
    for k in range(j, len(APP)):
        if APP[k] == "{":
            depth += 1
        elif APP[k] == "}":
            depth -= 1
            if depth == 0:
                return APP[i:k + 1]
    raise AssertionError(name)


def _const(name):
    i = APP.index(f"const {name} = ")
    j = APP.index("=", i) + 1
    depth = 0
    for k in range(j, len(APP)):
        if APP[k] in "[{":
            depth += 1
        elif APP[k] in "]}":
            depth -= 1
        elif APP[k] == ";" and depth == 0:
            return APP[i:k + 1]
    raise AssertionError(name)


_STUBS = """
function escapeHtml(s) { return String(s == null ? "" : s); }
function escapeAttr(s) { return String(s == null ? "" : s); }
function icon(n) { return "[" + n + "]"; }
function playerAvatar(n) { return "<i>" + n + "</i>"; }
function teamMark(t) { return "<i>" + t + "</i>"; }
function nflMap() { return {}; }
function nflName(t) { return String(t || ""); }
function injFind(sport, name) { return (INJ || {})[name] || null; }
function injTone(s) { return "var(--bad)"; }
function injTag() { return ""; }
function injShort(s) { return String(s); }
function injLineHTML() { return ""; }
function pct(v) { return v == null ? "—" : (v * 100).toFixed(0) + "%"; }
"""

#: Two game days. SEA and NE play Thursday; DET and GB play Sunday. That
#: split is what makes "his roster's calendar" a different calendar —
#: his players are on one of those teams and not the other.
_FF = {
    "schedule": [
        {"date": "2026-09-10", "home": "SEA", "away": "NE", "week": 1},
        {"date": "2026-09-13", "home": "DET", "away": "GB", "week": 1},
    ],
    "scripts": [
        {"home": "SEA", "away": "NE", "home_implied": 26.0, "away_implied": 18.0,
         "total": 44.0, "spread": -8.0, "archetype": "Shootout", "read": ""},
        {"home": "DET", "away": "GB", "home_implied": 25.0, "away_implied": 23.0,
         "total": 48.0, "spread": -2.0, "archetype": "Track meet", "read": ""},
    ],
    "draft_kit": {"board": [
        {"player": "Mine Wr", "team": "SEA", "position": "WR", "pos_rank": 3,
         "proj": 16.0, "tier": 1, "vorp": 5.0, "ppg": 15.0},
        {"player": "Theirs Rb", "team": "DET", "position": "RB", "pos_rank": 1,
         "proj": 22.0, "tier": 1, "vorp": 9.0, "ppg": 21.0},
        {"player": "Theirs Te", "team": "GB", "position": "TE", "pos_rank": 2,
         "proj": 13.0, "tier": 2, "vorp": 3.0, "ppg": 12.0},
    ]},
    "usage": [],
}

#: He owns the Thursday receiver, plus a defence nobody projects.
_MINE = [{"name": "Mine Wr", "pos": "WR", "team": "SEA"},
         {"name": "Deep Bench", "pos": "TE", "team": "SEA"}]


def _run(script, inj=None):
    src = (_STUBS
           + f"const INJ = {json.dumps(inj or {})};\n"
           + f"let _ffData = {json.dumps(_FF)};\n"
           + "\n".join(_const(c) for c in ("FFCAL_DOW", "FFCAL_MON",
                                           "FFCAL_MON_FULL", "FFCAL_STATE",
                                           "FFCAL_OPTS"))
           + "\n"
           + "\n".join(_fn(n) for n in (
               "ffNorm", "pluralWord", "plural", "_ffCalS", "_ffImpliedAvg",
               "_ffDayEnv", "_ffDayBoard", "_ffCalSay", "_ffCalQual",
               "ffCalendarHTML", "ffCalDayHTML", "ffCalPanelHTML",
               "ffDeskRoster", "ffRosterCalendarHTML"))
           + "\n" + script)
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(src)
        path = fh.name
    try:
        res = subprocess.run(["node", path], capture_output=True,
                             text=True, timeout=120)
    finally:
        os.unlink(path)
    assert res.returncode == 0, res.stderr[-2500:]
    return json.loads(res.stdout)


def _roster(mine=None, inj=None):
    out = _run(f"console.log(JSON.stringify(ffRosterCalendarHTML("
               f"_ffData, {json.dumps(mine if mine is not None else _MINE)})));",
               inj=inj)
    return " ".join(out.split())


# ---------------------------------------------------- only his players

def test_only_his_players_are_ranked():
    out = _roster()
    assert "Mine Wr" in out
    assert "Theirs Rb" not in out and "Theirs Te" not in out, \
        "the roster calendar ranked players he does not own"


def test_it_is_a_different_calendar_from_the_league_wide_one():
    """The league-wide instance still sees everybody. If the filter had
    leaked into the shared board function, this is where it would show."""
    league = _run("console.log(JSON.stringify(ffCalendarHTML(_ffData)));")
    assert "Theirs Rb" in league, league[:400]


def test_a_day_none_of_his_players_plays_carries_no_best_play():
    """Sunday belongs to Detroit and Green Bay. On his calendar it is a
    game day with nobody of his on it, and the cell must not borrow
    somebody else's man to fill the space."""
    out = _roster()
    i = out.index("Your start calendar")
    assert "Thu Sep 10" in out[i:]
    # The Sunday cell exists as a date but carries no name of his.
    assert "Theirs" not in out


# --------------------------------------------- and it says who is absent

def test_the_players_with_no_projection_are_named_not_dropped():
    out = _roster()
    assert "Deep Bench" in out, "a rostered player vanished without a word"
    assert "not on the projection board" in out
    assert "1 player" in out and "1 other" in out, out


def test_a_roster_nobody_projects_gets_a_reason_instead_of_a_calendar():
    out = _roster(mine=[{"name": "Deep Bench", "pos": "TE", "team": "SEA"},
                        {"name": "Also Nobody", "pos": "K", "team": "DET"}])
    assert "None of your players are on the projection board" in out
    assert "Deep Bench, Also Nobody" in out
    assert "ffcal-grid" not in out, "drew an empty grid instead of the reason"


def test_no_synced_roster_draws_nothing_at_all():
    assert _roster(mine=[]) == ""


# ------------------------------------------- the two do not share a state

def test_the_two_calendars_keep_their_own_selection():
    """The bug this namespacing exists to prevent: one `_ffCalSel` for
    two calendars means tapping a day on yours moves the league's."""
    got = _run("""
      ffCalendarHTML(_ffData);                      // ns "days"
      ffRosterCalendarHTML(_ffData, """ + json.dumps(_MINE) + """);
      _ffCalS("roster").sel = "2026-09-13";
      console.log(JSON.stringify([_ffCalS("days").sel,
                                  _ffCalS("roster").sel]));""")
    assert got == ["2026-09-10", "2026-09-13"], got


def test_each_calendar_carries_its_own_namespace_on_its_root():
    league = _run("console.log(JSON.stringify(ffCalendarHTML(_ffData)));")
    mine = _roster()
    assert 'data-ffcal="days"' in league
    assert 'data-ffcal="roster"' in mine


def test_the_options_are_remembered_so_a_tap_redraws_the_same_calendar():
    """A re-render after a tap rebuilds from `FFCAL_OPTS`. If the roster
    filter were not stored there, the first tap on your own calendar
    would silently turn it into the league-wide one."""
    got = _run("""
      ffRosterCalendarHTML(_ffData, """ + json.dumps(_MINE) + """);
      const o = FFCAL_OPTS.roster;
      console.log(JSON.stringify([!!o, !!(o && o.only),
                                  o && o.only && o.only.has("mine wr"),
                                  o && o.only && o.only.has("theirs rb")]));""")
    assert got == [True, True, True, False], got


# ------------------------------------------------------ the tap handler

def _handler():
    """The delegated calendar click listener, lifted out of app.js."""
    needle = "const root = (nav || cell || pick).closest(\"[data-ffcal]\");"
    assert APP.count(needle) == 1
    head = 'document.addEventListener("click"'
    i = APP.rindex(head, 0, APP.index(needle))
    j = APP.index("{", APP.index("=>", i))
    depth = 0
    for k in range(j, len(APP)):
        if APP[k] == "{":
            depth += 1
        elif APP[k] == "}":
            depth -= 1
            if depth == 0:
                return APP[i:k + 1].replace(head + ", ", "", 1)
    raise AssertionError("unbalanced")


def test_a_tap_moves_only_the_calendar_it_landed_in():
    got = _run("""
      ffCalendarHTML(_ffData);
      ffRosterCalendarHTML(_ffData, """ + json.dumps(_MINE) + """);
      const onClick = """ + _handler() + """;
      // A tap on a day cell inside the ROSTER calendar.
      let redrawn = "";
      const root = { dataset: { ffcal: "roster" },
                     set outerHTML(v) { redrawn = v; } };
      const cell = { dataset: { calday: "2026-09-13" },
                     closest: (s) => (s === "[data-calday]" ? cell
                                      : s === "[data-ffcal]" ? root : null) };
      onClick({ target: { closest: (s) => (s === "[data-calday]" ? cell
                                           : s === "[data-ffcal]" ? root
                                           : null) } });
      console.log(JSON.stringify([_ffCalS("roster").sel,
                                  _ffCalS("days").sel,
                                  redrawn.indexOf('data-ffcal="roster"') >= 0,
                                  redrawn.indexOf("Theirs Rb") >= 0]));""")
    assert got[0] == "2026-09-13", got
    assert got[1] == "2026-09-10", "a tap on his calendar moved the league's"
    # …and the redraw is HIS calendar again, filter and all. Without the
    # stored options the first tap would quietly hand him the league-wide
    # one under his own heading.
    assert got[2] is True, "the redraw lost the namespace"
    assert got[3] is False, "the redraw lost the roster filter"



# --------------------------------------- every platform, one definition

def test_the_roster_comes_from_the_desk_so_every_platform_gets_one():
    """Ethan, 2026-09-09: "when they sync their ESPN league or their
    Sleeper league or both."

    The calendar first shipped inside the Sleeper card, which meant an
    ESPN-only reader never saw one. `renderLeagueDesk` is the single
    function all three platforms come through, and its payload already
    carries the whole roster — the best lineup plus everyone it did not
    seat — so that is where "his players" gets defined, once."""
    got = _run("""
      const desk = { lineup: {
        starters: [{ slot: "WR", player: "Mine Wr", position: "WR" },
                   { slot: "RB", player: null }],
        bench: [{ player: "Deep Bench", position: "TE" },
                { player: "Mine Wr", position: "WR" }] } };
      console.log(JSON.stringify(ffDeskRoster(desk)));""")
    assert [r["name"] for r in got] == ["Mine Wr", "Deep Bench"], got
    # An unfilled slot carries `player: null` and must not become a
    # roster row called "null"; a man in the lineup must not be counted
    # twice because he also turns up in another list.
    assert all(r["name"] for r in got)


def test_an_empty_slot_or_an_absent_lineup_is_simply_no_roster():
    for desk in ("null", "{}", '{"lineup": {}}',
                 '{"lineup": {"starters": [{"slot": "QB", "player": null}]}}'):
        got = _run("console.log(JSON.stringify(ffDeskRoster(%s)));" % desk)
        assert got == [], (desk, got)


def test_no_projection_board_says_so_rather_than_blaming_his_roster():
    """The desk can answer before the fantasy payload lands. "The board
    is not here" and "none of your players are on it" are two different
    facts, and this tab carries nothing else that would say either."""
    got = _run("console.log(JSON.stringify(ffRosterCalendarHTML("
               '{ draft_kit: { board: [] } },'
               '[{ name: "Mine Wr", pos: "WR" }])));')
    got = " ".join(got.split())
    assert "projection board has not loaded here yet" in got, got
    assert "None of your players" not in got


def test_the_desk_draws_it_and_the_sleeper_card_no_longer_does():
    """One instance, or the Sleeper reader gets two calendars and the
    `roster` namespace has two elements fighting over one selection."""
    assert APP.count("ffRosterCalendarHTML(") == 2, \
        "expected the definition and exactly one call site"
    i = APP.index("async function renderLeagueDesk(")
    body = APP[i:APP.index("\n/* ---------------- The team you are", i)]
    assert "ffRosterCalendarHTML(_ffData || {}, ffDeskRoster(d))" in body
    j = APP.index("function renderSleeperPanel(")
    panel = APP[j:APP.index("\n/* ============", j)]
    assert "ffRosterCalendarHTML" not in panel

if __name__ == "__main__":
    if not shutil.which("node"):
        print("SKIP node is not installed; this file executes the calendar. "
              "`apt install -y nodejs`")
        print("\n0 tests passed.")
        raise SystemExit(0)
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
