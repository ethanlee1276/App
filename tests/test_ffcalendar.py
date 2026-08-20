"""The fantasy start calendar — Ethan, 2026-08-18: "a calendar layout
page displaying the best possible player to play in fantasy for that
day … click on that specific day and we will show a list of the 5 best
fantasy players … and in-depth analysis on why."

What is defended here:

  * THE SCORE IS ARITHMETIC THE READER CAN CHECK: the kit's baseline
    projection × (that team's implied points ÷ the league-average
    implied), and the card prints every term. No oracle numbers.
  * A MAN RULED OUT CANNOT BE THE BEST PLAY. Out-tier designations are
    excluded from the board and NAMED in the panel, so the cut is
    visible instead of silent.
  * THE SCHEDULE STRADDLE: in August the stats season is last year's
    while the schedule file already carries next year's slate — the
    first season with unplayed games wins, same rule as ffprofile.
  * A build with no schedule cache ships no calendar, never a dead
    build.

Run directly: `python3 tests/test_ffcalendar.py`
"""

import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import fantasy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"),
           encoding="utf-8").read()


def _row(season, week, date, home, away, home_score=""):
    return {"season": str(season), "week": str(week), "gameday": date,
            "gametime": "13:00", "home_team": home, "away_team": away,
            "home_score": home_score}


def test_the_schedule_straddles_august():
    sched = [
        _row(2025, 18, "2026-01-04", "KC", "DEN", home_score="27"),
        _row(2026, 1, "2026-09-13", "KC", "LAC"),
        _row(2026, 1, "2026-09-10", "PHI", "DAL"),
    ]
    got = fantasy.upcoming_schedule(sched, 2025)
    assert [g["date"] for g in got] == ["2026-09-10", "2026-09-13"], \
        "2025 is fully played, so the 2026 slate is the calendar"
    assert got[0] == {"week": 1, "date": "2026-09-10", "time": "13:00",
                      "home": "PHI", "away": "DAL"}


def test_played_games_leave_the_calendar():
    sched = [
        _row(2026, 1, "2026-09-10", "PHI", "DAL", home_score="24"),
        _row(2026, 2, "2026-09-17", "PHI", "NYG"),
    ]
    got = fantasy.upcoming_schedule(sched, 2026)
    assert [g["week"] for g in got] == [2]


def test_no_rows_is_an_empty_calendar_not_an_error():
    assert fantasy.upcoming_schedule([], 2026) == []


def test_the_build_ships_it_and_survives_without_it():
    src = open(os.path.join(ROOT, "fantasy_build.py"),
               encoding="utf-8").read()
    assert '"schedule": _upcoming_schedule(season)' in src
    i = src.index("def _upcoming_schedule(")
    body = src[i:src.index("\ndef ", i + 10)]
    assert "return []" in body, "no schedule cache must mean no calendar"


def test_the_day_math_runs_under_node():
    """The SHIPPED join and scoring, on known answers: implied ÷ average
    scales the baseline, the sort is by that product, and the out-tier
    lands in the excluded list rather than the board."""
    node = shutil.which("node")
    if not node:
        return
    i = APP.index("let _ffCalSel = null;")
    fns = APP[i:APP.index("const FFCAL_DOW", i)]
    check = """
const injFind = (sport, name) => name === "Hurt Guy"
  ? { status: "Injured Reserve" } : null;
const injTone = (s) => s ? "var(--bad)" : "";
""" + fns + """
const F = (msg) => { console.error(msg); process.exit(1); };
const d = {
  scripts: [{ home: "KC", away: "DEN", home_implied: 30, away_implied: 10,
              total: 40, spread: -10, archetype: "A", read: "r" }],
  schedule: [{ week: 1, date: "2026-09-13", time: "13:00",
               home: "KC", away: "DEN" }],
  draft_kit: { board: [
    { player: "Chief Star", team: "KC", proj: 10, position: "RB" },
    { player: "Bronco Star", team: "DEN", proj: 18, position: "WR" },
    { player: "Hurt Guy", team: "KC", proj: 25, position: "RB" },
    { player: "Bye Guy", team: "SF", proj: 30, position: "WR" },
  ] },
};
if (_ffImpliedAvg(d) !== 20) F("league average implied");
const env = _ffDayEnv(d)["2026-09-13"];
if (!env || env.length !== 2) F("two teams wear the game");
const { rows, out } = _ffDayBoard(d, "2026-09-13");
// 10 × (30/20) = 15 for the Chief; 18 × (10/20) = 9 for the Bronco —
// the WORSE baseline wins the day on environment, which is the point.
if (rows[0].r.player !== "Chief Star") F("environment must reorder");
if (Math.abs(rows[0].score - 15) > 1e-9) F("chief score");
if (Math.abs(rows[1].score - 9) > 1e-9) F("bronco score");
if (rows.some((x) => x.r.player === "Bye Guy")) F("no game, no board");
if (!out.some((x) => x.r.player === "Hurt Guy")) F("IR must be excluded by name");
if (rows.some((x) => x.r.player === "Hurt Guy")) F("IR must not rank");
console.log("ok");
"""
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False) as f:
        f.write(check)
        path = f.name
    try:
        r = subprocess.run([node, path], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr or r.stdout
    finally:
        os.unlink(path)


def test_the_render_pass_landed_honest():
    """Ethan's calendar render, followed with only real numbers:
    month navigation, a play-quality legend whose "elite" cut is computed
    from the season itself, the day-summary strip, checklist cards, and
    a weekly-range strip on the profile sourced from the player's own
    games. What the render shows that we have no honest source for —
    salaries, ownership, boom rates — is omitted, same rule as the
    player-page render."""
    i = APP.index("function ffCalendarHTML(")
    body = APP[i:APP.index("function ffCalDayHTML(", i)]
    for hook in ('data-calnav="-1"', 'data-calnav="1"', 'data-calnav="first"'):
        assert hook in body, f"month nav lost {hook}"
    assert "ffcal-legend" in body and "ELITE SLATE" in body
    # The render's three-column layout: grid left, ranked plays middle, the
    # selected player's read right — one panel, tap a card to load it.
    assert "ffcal-layout" in body and "ffcal-panel" in body
    assert "ffCalPanelHTML(" in body, "the layout must mount the read panel"
    j = APP.index("function _ffCalQual(")
    qual = APP[j:APP.index("function ffCalendarHTML(", j)]
    assert "vals[Math.floor(vals.length * 0.75)]" in qual, \
        "the elite cut is the season's own top quarter, never a magic number"
    k = APP.index("function ffCalDayHTML(")
    day = APP[k:APP.index("\ndocument.addEventListener", k)]
    assert "ffcal-checks" in day and 'icon("check", 12)' in day, \
        "the why is a checklist of facts, not a paragraph of vibes"
    m = APP.index("function ffProfileHTML(")
    prof = APP[m:APP.index("\nfunction ", m + 10)]
    assert "Worst week" in prof and "weekly.length >= 4" in prof, \
        "the range is his own weeks, and it waits for a real sample"
    for sel in (".ffcal-nav {", ".ffcal-mark {", ".ffp-range {"):
        assert sel in CSS, f"{sel} is unstyled"
    # And what we cannot source stays out.
    for banned in ("Ownership", "Boom %", "Salary"):
        assert banned not in day and banned not in body, \
            f"{banned} has no honest source here"


def test_the_page_is_wired_and_the_why_is_printed():
    i = APP.index('subtabbedHTML("fantasy"')
    assert '["days", "Calendar"' in APP[i:i + 2400]
    j = APP.index("function ffCalDayHTML(")
    body = APP[j:APP.index("\ndocument.addEventListener", j)]
    assert "against a league-average" in body, \
        "the environment term must show its denominator"
    assert "mult.toFixed(2)" in body, "the multiplier itself is printed"
    assert "Ruled out that day and excluded:" in body
    assert 'data-dossier="${escapeAttr(r.player)}"' in body, \
        "the panel keeps its door to the full profile"
    assert 'data-calpick="${escapeAttr(r.player)}"' in body, \
        "cards load the read panel, and the tap is delegated"
    assert 'closest("[data-calday]")' in APP, "day taps are delegated"
    assert 'closest("[data-calpick]")' in APP, "card taps are delegated"
    for sel in (".ffcal-grid {", ".ffcal-cell {", ".ffcal-card {",
                ".ffcal-layout {", ".ffcal-panel {", ".ffcal-vs {"):
        assert sel in CSS, f"{sel} is unstyled"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
