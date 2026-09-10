"""A dark league says WHY it is dark, or it is lying.

Ethan, 2026-09-10: "we are not showing the live play by plays for nfl.
its not even showing the nfl game is live."

Three different situations reach the Live tab as the same empty shelf:

  · nothing is in progress — a quiet Tuesday, and the right answer;
  · the scoreboard REFUSED us, and `livescore_build.build` wrote down
    which scoreboard and what it said;
  · the loop that writes the file stopped, so the file on disk is a
    true statement about last week.

The builder has known the difference since the day it shipped — its own
docstring: "An empty list with no note and an empty list because ESPN
refused the request look identical to every reader downstream." It
writes `note` and `generated_at` for exactly this. Every reader
downstream threw both away: `fetchAllLive` took `games` and nothing
else, so the page drew "No games in progress right now" over all three
and gave nobody — Ethan, or the next person reading this — any way to
tell which one they were looking at.

This file pins the whole chain, because fixing one end leaves the bug
one reader away from coming back: the builder writes the note, the
fetch carries it, the sentence is the note itself rather than a
paraphrase, and the page renders it under both empty shelves.
"""

import json
import os
import re
import subprocess
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APP = (ROOT / "web" / "js" / "app.js").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    ends = [APP.find(m, i + 10)
            for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ", "\n/*:")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return APP[i:min(ends)]


def _const(name):
    """The literal a top-level `const NAME = ...;` is bound to, verbatim."""
    i = APP.index(f"const {name} = ")
    j = APP.index("\n", APP.index(";", i)) if "{" not in APP[i:APP.index("\n", i)] \
        else APP.index("\n};", i) + 3
    return APP[i:j]


# --- the builder still writes the note the page now shows -------------------
def _build_with_dead_feed(league="nfl"):
    import livescore_build as B
    from engine.sources.fetch import DataUnavailable

    real = B.fetch_rows
    B.fetch_rows = lambda lg, ttl=0: (_ for _ in ()).throw(
        DataUnavailable("403 Forbidden"))
    try:
        return B.build(league)
    finally:
        B.fetch_rows = real


def test_a_refused_scoreboard_is_an_empty_board_that_says_so():
    out = _build_with_dead_feed()
    assert out["games"] == [], out["games"]
    assert out.get("note"), "an empty board with no note is the bug"
    assert "NFL" in out["note"] and "403 Forbidden" in out["note"], out["note"]


# --- the page turns that note into the sentence it shows --------------------
def _run(program):
    node = shutil.which("node")
    if not node:
        return None
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(program)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def _harness(tail):
    return (_const("LEAGUE_LABEL") + "\n"
            + _const("LIVE_FEEDS") + "\n"
            + _const("LIVE_FEED_STALE_S") + "\n"
            + 'function escapeHtml(s) { return String(s).replace(/&/g, "&amp;")'
              '.replace(/</g, "&lt;").replace(/>/g, "&gt;"); }\n'
            + _fn("utcMs") + "\n"
            + _fn("liveFeedWhy") + "\n"
            + _fn("liveFeedWhyHTML") + "\n"
            + tail)


def _answers():
    note = _build_with_dead_feed()["note"]
    prog = _harness("""
      const now = Date.parse("2026-09-10T20:00:00Z");
      const fresh = "2026-09-10T19:59:30Z";       // 30s old
      const old   = "2026-09-10T18:00:00Z";       // 2h old
      console.log(JSON.stringify({
        note:    liveFeedWhy("nfl", {ok: true, note: NOTE, stamp: fresh}, now),
        nofile:  liveFeedWhy("nfl", {ok: false, note: "", stamp: ""}, now),
        stopped: liveFeedWhy("nfl", {ok: true, note: "", stamp: old}, now),
        quiet:   liveFeedWhy("nfl", {ok: true, note: "", stamp: fresh}, now),
        nostamp: liveFeedWhy("nfl", {ok: true, note: "", stamp: ""}, now),
        missing: liveFeedWhy("nfl", undefined, now),
        htmlOne: liveFeedWhyHTML("nfl", {nfl: {ok: true, note: NOTE, stamp: fresh},
                                         mlb: {ok: false, note: "", stamp: ""}}, now),
        htmlAll: liveFeedWhyHTML("all", {nfl: {ok: true, note: NOTE, stamp: fresh},
                                         mlb: {ok: false, note: "", stamp: ""}}, now),
        htmlQuiet: liveFeedWhyHTML("nfl", {nfl: {ok: true, note: "", stamp: fresh}}, now),
        htmlNone:  liveFeedWhyHTML("nfl", {}, now),
      }));""".replace("NOTE", json.dumps(note)))
    return _run(prog), note


def test_the_builders_own_words_are_what_the_reader_sees():
    """NOT a paraphrase. The note names the league AND the failure —
    "NFL scoreboard unreachable — 403 Forbidden" — and no sentence this
    file could invent knows that the refusal was a 403."""
    got, note = _answers()
    if got is None:
        print("  SKIP node not installed"); return
    assert got["note"] == note, (got["note"], note)


def test_a_file_that_did_not_load_is_not_an_empty_slate():
    got, _ = _answers()
    if got is None:
        print("  SKIP node not installed"); return
    assert "NFL" in got["nofile"], got["nofile"]
    assert got["nofile"] != "", "a fetch that failed must not read as no games"


def test_a_stopped_loop_is_named_by_the_files_own_age():
    """The file is served fresh by the web server and is two hours old
    inside. Without this the page shows last week's slate as today's."""
    got, _ = _answers()
    if got is None:
        print("  SKIP node not installed"); return
    assert "120 min" in got["stopped"], got["stopped"]
    assert "not running" in got["stopped"], got["stopped"]


def test_a_quiet_afternoon_gets_no_warning():
    """The fourth case, and the common one. A feed that answered
    recently with nothing in progress is not a fault, and a red line on
    every quiet evening trains a reader to ignore all four."""
    got, _ = _answers()
    if got is None:
        print("  SKIP node not installed"); return
    assert got["quiet"] == "", got["quiet"]
    assert got["missing"] == "", got["missing"]
    # A file predating `generated_at` cannot be aged, and guessing is
    # how a fix becomes its own bug report.
    assert got["nostamp"] == "", got["nostamp"]


def test_the_chip_decides_which_leagues_are_explained():
    got, note = _answers()
    if got is None:
        print("  SKIP node not installed"); return
    # BOTH leagues are dark in this fixture, and only the pressed one is
    # explained — otherwise a chip is a filter over the cards and not
    # over the reasons, which is the same bug one screen over (#148).
    assert got["htmlOne"].count("lb-why") == 1, got["htmlOne"]
    assert "MLB" not in got["htmlOne"], "the NFL chip explained a league nobody asked about"
    assert got["htmlAll"].count("lb-why") == 2, got["htmlAll"]
    # Feed order, which is Ethan's order of importance: NFL leads.
    assert got["htmlAll"].index("NFL") < got["htmlAll"].index("MLB"), got["htmlAll"]
    assert got["htmlQuiet"] == "", got["htmlQuiet"]
    assert got["htmlNone"] == "", got["htmlNone"]


# --- the wiring, which is what actually broke -------------------------------
def test_the_fetch_keeps_the_note_and_the_stamp_it_used_to_drop():
    """`fetchAllLive` read `games` and nothing else. Both fields the
    builder writes for this purpose must come out of it."""
    i = APP.index("async function fetchAllLive()")
    body = APP[i:APP.index("\n/*:", i)]
    assert "df.note" in body, "the note is dropped again"
    assert "df.generated_at" in body, "the stamp is dropped again"
    assert "_liveFeedState[sport] = feed" in body, body[-600:]
    # Recorded whether or not the file had games — an unreachable feed
    # has none, and that is the case this exists for.
    assert body.index("_liveFeedState[sport] = feed") > body.index("df.games.length"), \
        "recorded inside the has-games branch, which is the one case that needs no note"


def test_both_empty_shelves_say_why():
    """Two places draw an empty Live tab: no games anywhere, and none in
    the league whose chip is pressed. Fixing one leaves the other.

    COUNTING THE CALLS IS NOT ENOUGH, and the first draft of this test
    made exactly the mistake it is here to prevent: a reason that is
    computed, assigned and never interpolated passes a call count and
    shows the reader nothing. That IS the defect. So the assertion is
    on the interpolation."""
    i = APP.index("async function renderLiveBoard()")
    body = APP[i:APP.index("\nfunction ", i + 10)]
    assert body.count("liveFeedWhyHTML(") == 2, body.count("liveFeedWhyHTML(")
    nogames = body.index("if (!games.length)")
    assert "liveFeedWhyHTML(" in body[nogames:nogames + 700], "the empty board explains nothing"
    assert "${why}" in body, "the empty board computes a reason and drops it"
    dark = body.index("const darkWhy")
    assert "liveFeedWhyHTML(" in body[dark:dark + 200], "the dark league explains nothing"
    assert "${darkWhy}" in body, "the dark league computes a reason and drops it"


def test_the_sentence_is_escaped_before_it_reaches_the_page():
    """It carries a feed's error text — a URL, whatever the host said —
    and that is never markup."""
    body = _fn("liveFeedWhyHTML")
    assert "escapeHtml(w)" in body, body


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
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
