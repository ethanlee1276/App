"""Start him or bench him, in the panel his own roster row opens.

Ethan, 2026-09-09: *"when you click on a player, it will show you weekly
fantasy projections, and trade targets and if you should bench them for
that week."* Trade targets the dossier already carried. This is the other
two.

THE THING THIS FILE IS REALLY GUARDING is that they are TWO DIFFERENT
NUMBERS and the panel never blends them:

  * the DAY projection — his team's next game, the board's baseline
    scaled by that game's environment, exactly as the start calendar
    scores every card. Week-specific.
  * the CALL — start or bench, out of the league desk, under his own
    league's scoring and slots, computed on season-long per-game
    averages. NOT week-specific.

Printing a season mean under the words "this week" is the class of
mistake this codebase has a rule about, so each is labelled with what it
is and the tests below check the labels as hard as the numbers.

And with no league linked there is no call to make. The panel says so and
points at the Account page rather than inventing a start/sit against a
roster it cannot see — the same refusal `has_me` makes on the desk.

Everything here is EXECUTED. These are pure functions over two payloads
the app already has, so there is no excuse for reading the source and
calling it a test.

Run directly: `python3 tests/test_this_week.py`
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
#: The week's drawing (js/fantasyweek.js), loaded on first use beside
#: app.js; the harness loads it whole, as the page does.
WEEK_JS = open(os.path.join(ROOT, "web", "js", "fantasyweek.js"), encoding="utf-8").read()


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
    """A top-level `const NAME = ...;` lifted whole, brace-matched."""
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
function nflName(t) { return String(t || ""); }
function injTone(s) { return "var(--bad)"; }
function injFind(sport, name) { return (INJ || {})[name] || null; }
"""

#: One Thursday game and one Sunday game, so "his team's NEXT game" is a
#: choice rather than the only row on the board.
_FF = {
    "schedule": [
        {"date": "2026-09-10", "home": "SEA", "away": "NE", "week": 1,
         "time": "8:20 PM"},
        {"date": "2026-09-13", "home": "DET", "away": "GB", "week": 1},
    ],
    "scripts": [
        {"home": "SEA", "away": "NE", "home_implied": 26.0, "away_implied": 18.0,
         "total": 44.0, "spread": -8.0, "archetype": "Shootout",
         "read": "Seattle throws early."},
        {"home": "DET", "away": "GB", "home_implied": 25.0, "away_implied": 23.0,
         "total": 48.0, "spread": -2.0, "archetype": "Track meet", "read": ""},
    ],
    "draft_kit": {"board": [
        {"player": "Star Wr", "team": "SEA", "position": "WR", "pos_rank": 3,
         "proj": 16.0, "tier": 1, "vorp": 5.0, "ppg": 15.0},
        {"player": "Hurt Rb", "team": "SEA", "position": "RB", "pos_rank": 9,
         "proj": 12.0, "tier": 3, "vorp": 2.0, "ppg": 11.0},
        {"player": "Bench Te", "team": "DET", "position": "TE", "pos_rank": 14,
         "proj": 7.0, "tier": 5, "vorp": 0.5, "ppg": 6.5},
    ]},
    "usage": [], "buy_sell": {}, "ranks": {}, "camp": {}, "offseason": {},
}


def _run(script, desk=None, inj=None, today="2026-09-09", week=None):
    src = (_STUBS
           + f"const INJ = {json.dumps(inj or {})};\n"
           + f"let _ffData = {json.dumps(_FF)};\n"
           + f"let _ffDesk = {json.dumps(desk)};\n"
           + f"let _ffWeek = {json.dumps(week)};\n"
           # Frozen clock: "his next game" must not depend on the day the
           # suite happens to run, which is how a test starts passing in
           # September and failing in October.
           + f"""const _RealDate = Date;
                 Date = class extends _RealDate {{
                   constructor(...a) {{ super(...(a.length ? a : ["{today}T12:00:00Z"])); }}
                 }};\n"""
           # The day-name tables `_ffCalSay` reads. Lifted rather than
           # stubbed: a test that supplies its own weekday names would
           # pass while the page printed Wednesday for a Thursday game.
           + "\n".join(_const(c) for c in ("FFCAL_DOW", "FFCAL_MON"))
           + "\n"
           + "\n".join(_fn(n) for n in (
               "ffNorm", "_ffImpliedAvg", "_ffDayEnv", "_ffDayBoard",
               "_ffCalSay", "_ffPlayerDay", "_ffPlayerSeat",
               "ffThisWeekHTML"))
           + "\nconst window = globalThis;\n" + WEEK_JS
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


def _panel(name, team, **kw):
    """The rendered block, with runs of whitespace collapsed.

    The copy is written across source lines, so "not on the\n draft
    board" is one sentence to a reader and two strings to `in`. Asserting
    on the raw HTML would fail on a reflow that changed nothing, which
    teaches the next person to loosen the assertion instead of reading
    it.
    """
    out = _run(f"console.log(JSON.stringify(ffThisWeekHTML("
               f"{json.dumps({'name': name, 'team': team})})));", **kw)
    return " ".join(out.split())


def _desk(starters, swaps, bench=(), current=True):
    return {"has_me": True, "lineup": {
        "starters": list(starters), "swaps": list(swaps),
        "bench": [{"player": b} for b in bench],
        "current": {"players": [s["player"] for s in starters
                                if s.get("player")], "total": 100.0}
        if current else None,
        "gain_total": 0.0}}


# ------------------------------------------------------------- the day

def test_the_day_is_his_next_game_not_the_first_on_the_board():
    """Star Wr plays Thursday; the board also holds a Sunday game. A
    panel that took `dates[0]` would be right by accident here and wrong
    for everyone on a later slate — so the fixture has both."""
    out = _panel("Star Wr", "SEA")
    assert "Thu Sep 10" in out, out
    assert "Sep 13" not in out
    # 16.0 baseline × (26.0 implied ÷ 23.0 league average) = 18.1.
    assert "18.1" in out, out
    assert "baseline 16" in out and "× 1.13" in out, out


def test_a_ruled_out_player_is_the_answer_all_by_himself():
    out = _panel("Hurt Rb", "SEA", inj={"Hurt Rb": {"status": "Out",
                                                    "injury": "hamstring"}})
    assert "Ruled out" in out and "hamstring" in out
    assert "projected for" not in out, "we projected a man who is not playing"


def test_a_player_with_no_game_left_is_told_so_rather_than_left_blank():
    out = _panel("Star Wr", "SEA", today="2026-12-01")
    assert "No upcoming game" in out, out


def test_a_man_off_the_draft_board_still_gets_his_matchup():
    """The roster rows open EVERYONE, including a backup quarterback no
    board has ever ranked. A blank panel would read as broken."""
    out = _panel("Nobody Special", "DET")
    assert "Sep 13" in out and "GB" in out, out
    assert "not on the draft board" in out


# ------------------------------------------------------- the start/sit call

def test_a_benched_man_the_desk_wants_in_is_a_start_call():
    desk = _desk(
        starters=[{"slot": "WR", "player": "Star Wr", "points": 14.2}],
        swaps=[{"slot": "WR", "out": "Someone Else", "in": "Star Wr",
                "gain": 4.4}],
        bench=["Star Wr"])
    out = _panel("Star Wr", "SEA", desk=desk)
    assert "START HIM" in out, out
    assert "+4.4" in out and "Someone Else" in out


def test_a_started_man_the_desk_wants_out_is_a_bench_call():
    desk = _desk(
        starters=[{"slot": "FLEX", "player": "Better Guy", "points": 18.0}],
        swaps=[{"slot": "FLEX", "out": "Bench Te", "in": "Better Guy",
                "gain": 6.0}],
        bench=["Bench Te"])
    out = _panel("Bench Te", "DET", desk=desk)
    assert "BENCH HIM" in out, out
    assert "Better Guy" in out and "+6" in out


def test_a_man_already_started_correctly_is_told_he_is_right():
    desk = _desk(starters=[{"slot": "WR", "player": "Star Wr", "points": 14.2}],
                 swaps=[])
    out = _panel("Star Wr", "SEA", desk=desk)
    assert "STARTING" in out and "14.2" in out
    assert "BENCH" not in out


def test_a_platform_that_cannot_see_your_lineup_says_where_he_belongs():
    """`current: null` is ESPN and Yahoo. "He is in the best lineup" is a
    true statement; "you have him started correctly" would not be, and
    the two must not share a sentence."""
    desk = _desk(starters=[{"slot": "WR", "player": "Star Wr", "points": 14.2}],
                 swaps=[], current=False)
    out = _panel("Star Wr", "SEA", desk=desk)
    assert "IN THE BEST LINEUP" in out
    assert "does not tell us who you have actually started" in out
    assert "STARTING" not in out


def test_a_man_on_your_bench_with_no_swap_is_a_plain_bench():
    desk = _desk(starters=[{"slot": "WR", "player": "Better Guy", "points": 20}],
                 swaps=[], bench=["Bench Te"])
    out = _panel("Bench Te", "DET", desk=desk)
    assert "BENCH" in out and "BENCH HIM" not in out
    assert "not in the best legal lineup" in out


# ------------------------------------------------ what it refuses to claim

def test_with_no_league_linked_there_is_no_call_at_all():
    out = _panel("Star Wr", "SEA", desk=None)
    assert "No league linked" in out and "Account page" in out
    for word in ("START HIM", "BENCH HIM", "STARTING", "BEST LINEUP"):
        assert word not in out, (word, out)
    # …but the day projection is still there. It needs no league.
    assert "18.1" in out


def test_somebody_elses_player_is_not_given_a_verdict():
    desk = _desk(starters=[{"slot": "WR", "player": "Better Guy", "points": 20}],
                 swaps=[])
    out = _panel("Star Wr", "SEA", desk=desk)
    assert "Not on your roster" in out
    for word in ("START HIM", "BENCH HIM", "STARTING"):
        assert word not in out, (word, out)


def test_the_two_numbers_are_never_presented_as_one():
    """The load-bearing honesty check. The day figure is a projection for
    a date; the call is a season per-game mean under league scoring. The
    panel must say which is which, or a reader reasonably takes 14.2 for
    Sunday's forecast."""
    desk = _desk(starters=[{"slot": "WR", "player": "Star Wr", "points": 14.2}],
                 swaps=[])
    out = _panel("Star Wr", "SEA", desk=desk)
    assert "projected for Thu Sep 10" in out
    assert "season-long per-game averages" in out
    assert "not on the day projection above it" in out


# ------------------------------------------ the week off the board (2026-10-22)
#: One week's file (engine/fantasyweek), as the room and the dossier read
#: it. Games on Thursday the 10th; the frozen clock is the 9th.
_WEEK = {
    "week": 1, "season": 2026, "byes": ["DET"],
    "teams": {"SEA": {"date": "2026-09-10"}, "NE": {"date": "2026-09-10"}},
    "players": [
        {"player": "Star Wr", "team": "SEA", "opponent": "NE", "position": "WR",
         "game": {"home": "SEA", "away": "NE", "date": "2026-09-10"},
         "ppr": 19.4, "expected": 19.4, "play": 1.0, "range": [7.2, 31.8],
         "td_prob": 0.46, "matchup": {"grade": "soft", "text": "NE allow 171 yards a game to WRs"},
         "script": {"team_implied": 26.0},
         "reasons": [{"why": "NE allow the 3rd-most receiving yards to WRs"}],
         "read": {"label": "could shine"}},
        {"player": "Hurt Rb", "team": "SEA", "opponent": "NE", "position": "RB",
         "ppr": 14.0, "expected": 9.1, "play": 0.65, "status": "Questionable",
         "practice": "Limited", "game": {"home": "SEA"}},
    ],
}


def test_his_week_off_the_board_comes_first_when_it_is_built():
    """The board's own week replaces the day estimate: the projection
    for this game, its range, his touchdown chance, the matchup and why."""
    out = _panel("Star Wr", "SEA", week=_WEEK)
    assert "19.4" in out and "projected PPR this week vs NE" in out, out
    assert "7.2–31.8" in out and "46%" in out and "soft" in out
    assert "NE allow the 3rd-most receiving yards to WRs" in out
    assert "Matchup scan: could shine" in out
    assert "baseline 16" not in out, "the day estimate drawn beside the week"


def test_a_questionable_man_shows_both_numbers_and_the_chance():
    out = _panel("Hurt Rb", "SEA", week=_WEEK)
    assert "9.1" in out and "14.0 if he plays" in out and "65% that he does" in out, out
    assert "Questionable, Limited in practice" in out


def test_a_part_from_his_season_average_says_so():
    week = json.loads(json.dumps(_WEEK))
    week["players"][0]["filled"] = ["receptions"]
    out = _panel("Star Wr", "SEA", week=week)
    assert "His catches from his season average: the board has no line on it" in out, out


def test_the_room_draws_the_week_by_position():
    """The "This week" room (QBWeek.room): the week's players by position,
    a filter that redraws in place, the byes, the chips and the
    measurement — and the locked copy says what it holds."""
    measured = {"seasons": "2023-2025", "weeks": "4-17",
                "score": {"ALL": {"n": 10445, "pairs_week": 0.7225, "pairs_season": 0.7127,
                                  "mae_week": 4.661, "mae_season": 4.828}}}
    week = dict(_WEEK, measured=measured)
    out = _run("""
      globalThis.escapeAttr = (x) => String(x == null ? "" : x);
      globalThis.playerAvatar = () => "";
      globalThis.nflMap = () => ({});
      globalThis.icon = (n) => "";
      globalThis.panelEmpty = (t) => t;
      console.log(JSON.stringify({ all: QBWeek.room(_ffWeek),
        locked: QBWeek.room({ locked_reason: "subscription" }), none: QBWeek.room(null) }));
    """, week=week)
    all_ = " ".join(out["all"].split())
    assert "Week 1 in fantasy points" in all_ and "On a bye:</b> DET" in all_
    assert 'data-ffwpos="RB"' in all_ and 'data-ffwpos="QB"' not in all_, "a filter for each position on the board"
    assert all_.index("Star Wr") < all_.index("Hurt Rb"), "ordered by what each is worth this week"
    assert "soft matchup" in all_ and "Questionable · 65% to play" in all_
    assert "14.0 if he plays" in all_ and "8 in 10 weeks 7.2–31.8" in all_ and "TD 46%" in all_
    assert "72.3% of the time to the season average’s 71.3%" in all_
    assert "part of the subscription" in out["locked"] and "not built yet" in out["none"]


def test_a_team_on_a_bye_is_told_so():
    out = _panel("Bench Te", "DET", week=_WEEK)
    assert "On a bye this week" in out, out
    assert "Sep 13" not in out, "a bye week projected off next week's game"


def test_a_locked_or_finished_week_falls_back_to_the_day():
    locked = {"locked_reason": "subscription", "week": 1}
    out = _panel("Star Wr", "SEA", week=locked)
    assert "projected for Thu Sep 10" in out and "projected PPR this week" not in out
    over = dict(_WEEK, teams={"SEA": {"date": "2026-09-01"}})
    out = _panel("Star Wr", "SEA", week=over)
    assert "projected PPR this week" not in out, "last week's numbers drawn as this week's"


def test_a_call_scored_on_the_week_says_so():
    desk = _desk(starters=[{"slot": "WR", "player": "Star Wr", "points": 19.4,
                            "basis": "week"}], swaps=[])
    out = _panel("Star Wr", "SEA", desk=desk, week=_WEEK)
    assert "on this week’s projection" in out
    assert "season-long per-game averages" not in out


def test_the_full_profile_keeps_this_week_at_the_top():
    """The full page REPLACES the compact card when the profile answers,
    which on the box is a moment after every tap. Without this block on it,
    the start/sit call and his week off the board were gone by the time a
    reader looked (found 2026-10-22)."""
    i = APP.index("function ffProfileHTML(")
    body = APP[i:APP.index("\nfunction ", i + 10)]
    assert "ffThisWeekHTML(info)" in body, "the full page dropped this week"
    assert body.index("ffThisWeekHTML(info)") < body.index('class="ffp-top"'), "and first"


def test_a_name_spelled_differently_by_the_two_sources_still_matches():
    """The kit board and Sleeper are different ingests. "A.J. Brown" and
    "AJ Brown" are one man, and a verdict that silently reads "not on
    your roster" because of a full stop is the worst kind of wrong."""
    desk = _desk(starters=[{"slot": "WR", "player": "star wr", "points": 9.9}],
                 swaps=[])
    out = _panel("Star Wr", "SEA", desk=desk)
    assert "STARTING" in out, out



def test_a_desk_that_is_not_yours_never_becomes_the_verdict_source():
    """The one claim in this file that is read rather than run, because
    the guard lives in `renderLeagueDesk` — above the pure functions the
    rest of this executes and behind a fetch.

    It matters more than its size. `_ffDesk` is a module-level stash, so
    without a clear on EVERY path out, switching to a league he has no
    roster in leaves the previous league's answer standing and the panel
    calmly tells him to start a player off a team that is not his. One
    clear at the top beats a clear on each exit, which is how one of them
    gets missed — I missed one writing this."""
    i = APP.index("async function renderLeagueDesk(")
    body = APP[i:APP.index("\n/* ---------------- The team you are", i)]
    assert body.count("_ffDesk = null;") == 1, body.count("_ffDesk = null;")
    assert body.index("_ffDesk = null;") < body.index("if (!leagueId)")
    assert body.count("_ffDesk = d;") == 1
    # …and the set is downstream of the has_me return, so a league with
    # no roster of his in it cannot reach it.
    assert body.index("if (!d.has_me)") < body.index("_ffDesk = d;")

if __name__ == "__main__":
    if not shutil.which("node"):
        print("SKIP node is not installed; this file executes the panel. "
              "`apt install -y nodejs`")
        print("\n0 tests passed.")
        raise SystemExit(0)
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
