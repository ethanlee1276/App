"""The NFL Week-1 dress rehearsal, kept as tests instead of as a memory.

Phase 3 asked one question: build the real upcoming week and see what
breaks. On 2026-08-20 — Week 1 twenty days out, `_current_nfl_week()`
already calling it current, so this is the board the site would publish —
it broke in two places, and both were SILENT. Neither raised, neither
failed a build, neither left a mark in the payload. A rehearsal that
found them and did not pin them would be a rehearsal we have to run from
memory next August.

    python3 tests/test_nflweek1.py
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


BUILD = _read("nfl_build.py")
APP = _read("web", "js", "app.js")
CSS = _read("web", "css", "styles.css")


# --- finding 1: the radar that never drew --------------------------------------
def test_the_shape_radar_does_not_read_an_argument_that_does_not_exist():
    """`args.year`. argparse defines `season`, so this raised
    AttributeError on EVERY NFL build ever run — and the broad `except
    Exception` two lines below turned it into one warning line in a
    terminal, so the two-team radar has simply never appeared on the
    board. Measured 2026-08-20: before, "team shapes skipped: 'Namespace'
    object has no attribute 'year'"; after, "32 team(s) ranked on season
    2025".

    The lesson generalises past this one line — a broad except around a
    feature makes a typo indistinguishable from an absent feed — but the
    typo itself is what this pins."""
    # CODE ONLY. The fix's own comment names the bad attribute in order to
    # explain it, and a grep over the whole file would fail on the
    # explanation — pinning the bug's description instead of the bug.
    code = "\n".join(ln for ln in BUILD.splitlines()
                     if not ln.lstrip().startswith("#"))
    assert "args.year" not in code, \
        "args.year is back; argparse defines `season`, and the except swallows it"


def test_the_radar_ranks_the_board_s_own_season_not_the_calendar_year():
    """Today's year would also work in August, when they coincide, and
    would be wrong for `nfl_build.py 2024 5` — ranking this year's shapes
    onto a two-season-old board. The panel describes the teams on THIS
    board."""
    m = re.search(r"latest_shaped_season\(([^)]*)\)", BUILD)
    assert m, "the shapes call is gone"
    assert m.group(1).strip().endswith("args.season"), \
        f"shapes ranked off {m.group(1)!r}, not the board's own season"


# --- finding 2: the injury layer that did not run, and did not say so ----------
def test_the_board_records_whether_the_injury_layer_actually_ran():
    """THE ONE THAT MATTERS ON SEPTEMBER 9.

    nflverse publishes injuries_<season>.csv during a season, so before
    its first games the file is a 404 — verified 2026-08-20: 2026 → HTTP
    404, 2025 → 6,068 rows including 197 for its own Week 1. The data is
    not missing in principle; it is not published yet.

    The build handled that correctly and reported it to nobody: a warning
    on stdout, all 16 games priced anyway, and NOTHING in the payload to
    distinguish "no player is hurt" from "we did not look". `odds_status`
    has recorded exactly this for the price layer since the beginning.
    This is its counterpart."""
    assert '"injury_status"' in BUILD or "'injury_status'" in BUILD, \
        "the payload no longer carries injury_status"
    i = BUILD.index("injury_status = {")
    # To the end of the STATEMENT, not the first brace — "by_status": {}
    # is a nested literal and slicing at it dropped the last two keys.
    decl = BUILD[i:BUILD.index("\n    if args.injuries:", i)]
    for key in ("asked", "applied", "total", "holds", "source"):
        assert key in decl, f"injury_status dropped {key!r}"
    # `applied` must be set from the SUCCESS path only. A default of True,
    # or a set outside the try, would report a layer that never ran.
    assert "applied=True" in BUILD, "nothing ever marks the layer as applied"
    body = BUILD[i:i + 2600]
    ok = body.index("applied=True")
    err = body.index('injury_status["error"]')
    assert ok < err, "applied=True is set on the failure path"


def test_asked_and_applied_are_separate_facts():
    """Three states, not two: never asked (no --injuries), asked and
    applied, asked and refused. Collapsing the first and last would make
    a build nobody configured for injuries look identical to one whose
    feed was missing — and only the second is worth warning a reader
    about."""
    assert 'injury_status = {"asked": bool(args.injuries), "applied": False' in BUILD, \
        "asked no longer records whether --injuries was even passed"


# --- the reader-facing half ----------------------------------------------------
def test_the_page_says_when_the_prices_do_not_know():
    """The injury watch box reads ESPN's LIVE feed, which is current all
    summer. The model reads nflverse, which is not. So on Week 1 the box
    would have listed a man Questionable directly above a card priced as
    though he were fine — two sources with different knowledge and no
    label saying which fed the number."""
    assert "function injuryLayerNote(" in APP, "the note is gone"
    i = APP.index("function injuryLayerNote(")
    body = APP[i:APP.index("\n}", i)]
    assert "is.applied" in body and "is.asked" in body, \
        "the note no longer reads both halves of the status"
    assert "do not account for" in body, \
        "the note no longer says the prices exclude injuries"
    # It must not point at a list that may not be there. Measured in
    # Chromium on the real Week 1 board: the box above was empty, and the
    # first draft named it anyway. Comments stripped for the same reason
    # as the args.year check — the fix explains itself in prose that
    # quotes the wording it replaced.
    emitted = "\n".join(ln for ln in body.splitlines()
                        if not ln.lstrip().startswith("//"))
    assert "designations above" not in emitted, \
        "the note refers to a list that is empty whenever ESPN filed nothing"


def test_the_note_is_silent_on_every_board_that_never_declared_the_layer():
    """MLB and the rest own their own injury handling and publish no
    injury_status. A warning there would be a guess about a layer they
    never claimed, which is worse than saying nothing."""
    i = APP.index("function injuryLayerNote(")
    body = APP[i:APP.index("\n}", i)]
    assert re.search(r"if\s*\(!is\b", body), \
        "an absent injury_status no longer short-circuits to silence"


def test_the_note_survives_a_week_with_nobody_listed():
    """A board priced without the layer is a fact about the BOARD, not
    about whether anyone happens to be hurt. The empty-list path used to
    blank the whole box, which would have hidden the warning on exactly
    the quiet weeks where an unmodelled designation matters most."""
    i = APP.index("async function renderInjuryWatch(")
    body = APP[i:i + 4000]
    j = body.index("if (!listed.length)")
    tail = body[j:j + 400]
    assert "injuryLayerNote()" in tail, \
        "the empty-list path drops the note"


def test_the_note_is_styled_as_a_caveat_not_an_alarm():
    """Amber, inside the injury card. The board is not broken and nothing
    here is a fault — a layer that normally applies had no data, and the
    reader is handed the difference."""
    assert ".inj-nolayer" in CSS, "the note has no styling and inherits nothing"
    i = CSS.index(".inj-nolayer {")
    rule = CSS[i:CSS.index("}", i)]
    assert "var(--warn)" in rule, "the note is no longer amber"
    assert "var(--bad)" not in rule, "the note reads as an error, which it is not"


# --- the thing the rehearsal was actually for ----------------------------------
def test_week_one_still_builds_end_to_end():
    """The rehearsal itself, cheap enough to keep: the schedule the whole
    season stands on must contain a real, dated, regular-season Week 1
    with a full 16-game slate. This is the layer that, absent, makes
    every other assertion here moot.

    Skips rather than fails without the cache — a fresh checkout has no
    nflverse data and that is not a defect in this code."""
    games = os.path.join(ROOT, "data", "cache", "games.csv")
    if not os.path.isfile(games):
        print("    (skipped: no data/cache/games.csv in this checkout)")
        return
    import csv
    with open(games, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    seasons = sorted({int(r["season"]) for r in rows if r.get("season", "").isdigit()})
    latest = seasons[-1]
    wk1 = [r for r in rows if r["season"] == str(latest) and r["week"] == "1"]
    assert len(wk1) >= 14, \
        f"{latest} Week 1 has {len(wk1)} games — the schedule is partial"
    assert all(r["gameday"] for r in wk1), "a Week-1 game carries no date"
    # PRE would be a different bug wearing this one's clothes: the week
    # resolver reads `week` with no game_type filter, so a preseason row
    # numbered 1-3 would be built as a regular-season week. Verified
    # 2026-08-20: games.csv holds REG/WC/DIV/CON/SB and no PRE at all.
    assert {r["game_type"] for r in wk1} == {"REG"}, \
        "a non-REG row is numbered into Week 1 — the week resolver would build it"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
