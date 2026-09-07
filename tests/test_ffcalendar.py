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


# --- the day cell has to hold what it prints -----------------------------------
# Ethan, 2026-08-20: "the calander doesnt fir the numbers and shit so fix
# that. issue on both mobile and website." Measured in Chromium at twelve
# widths on the real September 2026 board before touching anything, which
# is the only reason the causes below are stated rather than guessed —
# there were three, and only one of them was about a phone.


def test_the_score_can_never_be_squeezed_by_its_own_row():
    """CAUSE ONE, and the width-independent one. `.ffcal-pts` had no
    shrink guard, so flexbox compressed it below its own text: "18.9"
    needs ~20px at its size and was measured at 18.4px in EVERY viewport
    from 1800 down to 390. A shrinking flex item is not a small-screen
    problem, which is why this showed on the desktop too."""
    i = CSS.index(".ffcal-pts {")
    rule = CSS[i:CSS.index("}", i)]
    assert "flex: none" in rule, \
        "the score can be shrunk below its digits again"
    j = CSS.index(".ffcal-best > :first-child {")
    assert "flex: none" in CSS[j:CSS.index("}", j)], \
        "the face can be squashed, which pushes the score off its baseline"


def test_the_calendar_stops_being_a_column_before_it_gets_too_narrow():
    """CAUSE TWO, and the one that looked like a cell bug and was not.
    Three columns (calendar | best plays | panel) beside a 280px sidebar
    left each day 44.3px at a 1280px window — while the SAME cell measured
    112px at 1100px, where the calendar already spans the row. A day cell
    twice as wide on a smaller screen is a layout fault, not a styling
    one. The breakpoint now sits where three columns actually stop
    fitting: at 1501 a cell is 60.8px and passes; below 1500 the calendar
    takes the whole row."""
    i = CSS.index(".ffcal-layout { display: grid")
    tail = CSS[i:]
    k = tail.index("grid-template-columns: minmax(0, 1fr) 300px")
    head = tail[:k]
    q = head.rindex("@media (max-width:")
    width = int(head[q:].split("max-width:")[1].split("px")[0].strip())
    assert width >= 1400, (
        f"the three-column layout survives down to {width}px, where the "
        "calendar column is too narrow for seven days")


def test_a_phone_stacks_the_cell_instead_of_shrinking_either_half():
    """CAUSE THREE. Seven columns in 390px is a 48.8px cell whatever the
    layout does — there is no column count left to trade away, and the
    face and score overlapped by 6.1px (10.4px at 360px). They stack
    below 520 instead, which removes the width pressure rather than
    shrinking either one to fit."""
    # BY CONTENT, not by position — styles.css already had an unrelated
    # `@media (max-width: 520px)` a few thousand lines earlier, and
    # indexing for the string found that one instead. Find the narrow
    # block that actually mentions the calendar cell.
    import re
    block = None
    for m in re.finditer(r"@media \(max-width: (\d+)px\) \{", CSS):
        if int(m.group(1)) > 560:
            continue
        body = CSS[m.end():CSS.index("\n}", m.end())]
        if ".ffcal-best" in body:
            block = body
            break
    assert block, "no narrow-width block styles the calendar cell at all"
    assert "column" in block, \
        "the narrow-cell stack is gone; face and score will overlap again"
    assert ".ffcal-pts" in block and "margin-left: 0" in block, \
        "the score keeps its auto margin while stacked, which off-centres it"


def test_the_name_is_gated_on_the_CELL_not_the_viewport():
    """THE REASON THIS BUG EXISTED AT ALL. The viewport says nothing about
    how wide a day cell is — measured on one board, an 1800px window gave
    an 80px cell and an 1100px window gave 112px. Any media query gets
    that backwards, and this one did: the surname truncated to "Mc..." for
    THREE different players on a single screen (McCaffrey, McBride,
    McLaurin), to one stray letter at 1440, and to nothing at 390.

    A name cut to two letters is not a shorter name, it is a wrong one.
    So it is hidden by default and revealed by a container query only
    where it fits whole."""
    assert "container-type: inline-size" in CSS, \
        "the cell is not a container; the name cannot know its own width"
    assert "@container" in CSS, "the name is back on a viewport rule"
    i = CSS.index(".ffcal-name {")
    assert "display: none" in CSS[i:CSS.index("}", i)], \
        "the name shows by default, so narrow cells truncate it again"
    j = CSS.index("@container")
    assert "min-width" in CSS[j:CSS.index("}", CSS.index("{", j) + 1) + 1], \
        "the container query is not keyed on width"


def test_nothing_in_the_cell_relies_on_a_name_that_may_be_absent():
    """The name is display:none in most cells, so it cannot be the thing
    that carries identity. The face is always drawn, and the cell titles
    itself for a pointer — tapping opens the panel that names him."""
    i = APP.index('class="ffcal-cell')
    cell = APP[i:APP.index("</div>`);", i)]
    assert "playerAvatar(" in cell, "no face; a nameless cell identifies nobody"
    assert "title=" in cell, \
        "no hover name, so a mouse user cannot recover who the number is"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
