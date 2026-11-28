"""A pre-game ranking stayed on the page after kickoff, saying nothing.

`engine/boardlint --sport cfb` on the droplet, 2026-09-03, board built
19:48:35:

    MOST LIKELY: 18 rows, 16 flagged
      Under 58.5   UCF  v BCU   ! LEAN measured 0.50  ! STARTED
      Over 53.5    RUTG v MASS  ! LEAN measured 0.50  ! STARTED
      ... eight of them

The LEAN flags are Ethan's own call (task #107 — spreads and totals shown
as labelled leans) and the lint says so: "not a defect". STARTED is not
annotated that way, and it is the one worth acting on.

`showableLikelyRow` filters shrink artefacts and the -250 price cap and
NEVER LOOKED AT KICKOFF, though every game row carries one. The edge
board refuses a started game at the rules layer — "this is a pre-game
model and cannot price an in-play market" — and the likelihood board had
no equivalent anywhere, at build time or on the page. Nothing was wrong
when it published; it simply never expired.

LABELLED, NOT HIDDEN, and that is the whole design decision. Dropping
the row would make cards vanish under a reader on the sixty-second
refresh, which is Ethan's complaint from 2026-08-31 about a different
board: "ill be staring at the live page at the open bets and ill scroll
and shit then the open bets will just dissapear." A row that changes
what it SAYS is honest. A row that disappears while you are reading it
is that bug, one board over. So the filter is deliberately untouched and
this file pins that it stays untouched.

Run directly: `python3 tests/test_likely_started.py`
"""

import os
import re
import shutil
import subprocess
import sys
from _app import app_js  # noqa: E402  (app.js and the rooms it loads on first use)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

JS = app_js()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()


def _fn(name):
    """One top-level function's source, by brace balance."""
    i = JS.index(f"function {name}")
    depth, j = 0, JS.index("{", i)
    for k in range(j, len(JS)):
        if JS[k] == "{":
            depth += 1
        elif JS[k] == "}":
            depth -= 1
            if depth == 0:
                return JS[i:k + 1]
    raise AssertionError(f"{name} never closes")


def _started_src():
    """The started check with everything it reads (2026-11-04): the late-tip
    constants and caches, `tipTeams`, `freshTipState`, `kickoffEpoch` and
    `likelyStarted` itself, one contiguous stretch of app.js."""
    i = JS.index("/* THE REAL TIP, NOT THE PRINTED ONE.")
    j = JS.index(_fn("likelyStarted"), i) + len(_fn("likelyStarted"))
    return JS[i:j] + "\n"


# --- the rule -----------------------------------------------------------------
def test_the_started_check_behaves_across_every_shape_a_row_carries():
    """Executed, not read. The parsing is the part that can be quietly
    wrong, and a rule about time that is only source-pinned is a rule
    nobody has run."""
    prog = _started_src() + """
const past = new Date(Date.now() - 3600e3).toISOString();
const soon = new Date(Date.now() + 3600e3).toISOString();
const cases = [
  ["kickoff an hour ago",      {kickoff: past},                        true],
  ["kickoff an hour ahead",    {kickoff: soon},                        false],
  ["live flag set",            {live: true},                           true],
  ["no kickoff at all",        {},                                     false],
  ["naive local timestamp",    {kickoff: "2026-09-03T19:00:00"},       false],
  ["+00:00 offset, past",      {kickoff: past.replace("Z","+00:00")},  true],
  ["-0400 offset, past",       {kickoff: "2020-01-01T12:00:00-0400"},  true],
  ["unparseable",              {kickoff: "not a time"},                false],
  ["game_kickoff fallback",    {game_kickoff: past},                   true],
  ["null row",                 null,                                   false],
];
let bad = [];
for (const [name, row, want] of cases) {
  if (likelyStarted(row) !== want) bad.push(name);
}
console.log(bad.length ? "FAIL " + bad.join(", ") : "OK");
"""
    # THE DROPLET HAS NO NODE. Every other file here that executes
    # JavaScript checks first and says SKIP; this one raised
    # FileNotFoundError into the deploy gate on 2026-09-04. Skipped per
    # test rather than per file, because the five read-only assertions
    # around it are exactly the ones worth running where node is absent.
    if not shutil.which("node"):
        print("  SKIP node is not installed; this test executes "
              "likelyStarted() rather than reading it. `apt install -y nodejs`")
        return
    out = subprocess.run(["node", "-e", prog], capture_output=True, text=True,
                         timeout=60)
    assert out.returncode == 0, out.stderr[-400:]
    assert out.stdout.strip() == "OK", out.stdout.strip()


def test_a_kickoff_with_no_timezone_is_not_a_verdict():
    """THE CASE THAT WOULD MISLABEL A WHOLE SLATE. A bare local
    timestamp cannot be compared against a clock in another zone;
    guessing the reader's is how a 1pm kickoff reads as "under way" in
    London three hours early. No offset, no verdict — the same rule
    `boardlint._started` takes when `t.tzinfo is None`."""
    src = _fn("kickoffEpoch")
    assert "Z|[+-]" in src, "the timezone guard is gone"
    assert "kickoffEpoch(r)" in _fn("likelyStarted"), "the started check reads the printed time through it"
    py = open(os.path.join(ROOT, "engine", "boardlint.py"), encoding="utf-8").read()
    i = py.index("def _started")
    assert "if t.tzinfo is None:" in py[i:i + 700], \
        "boardlint dropped its own naive-timestamp guard; these two must agree"


# --- the decision, reversed 2026-09-27 ----------------------------------------
# Ethan, the 1pm games over and Walker, Henry and Jeanty still ranked on
# Top Picks: "all these bets should be clearing off the board once the
# game starts." The BOARDS (Top Picks, Most Likely, Tonight, Edge) now
# drop a started row — `rowStarted`, applied where each board lists its
# rows. A game's own page and its live tracker keep that game's picks
# through the game (`oneBoardAllRows`), and a posted pick is tracked on
# Live and in the Riding rail, so nothing a reader bet on vanishes.
def test_the_boards_clear_a_started_row():
    assert "!rowStarted(r)" in _fn("oneBoardRows")
    src = _fn("edgeBoardRows")
    assert "!rowStarted(r)" in src and "!rowStarted(b)" in src
    assert "!rowStarted(r)" in _fn("renderLikelyTop")
    assert "!rowStarted(r)" in _fn("renderLikely")


def test_the_game_page_and_its_tracker_keep_the_game_s_picks():
    for name in ("obGameHTML", "matchupPickCount", "pbpOurPicks"):
        src = _fn(name)
        assert "oneBoardAllRows()" in src and "oneBoardRows()" not in src, name


def test_football_kickoffs_are_read_in_eastern_time():
    """The NFL row carries "13:00" beside "2026-09-27" — the shape the old
    check refused to read, so no NFL pick ever counted as started."""
    if not shutil.which("node"):
        print("  SKIP node is not installed")
        return
    prog = _started_src() + _fn("rowStarted") + """
const state = {data: {games: [
  {home: "MIA", away: "KC", date: "2026-09-27", kickoff: "13:00", live: {state: "pre"}},
  {home: "GB", away: "ATL", date: "2026-09-27", kickoff: "20:15", live: {state: "pre"}},
  {home: "SF", away: "ARI", date: "2026-09-27", kickoff: "16:05", live: {state: "live"}}]}};
const at = (iso) => { Date.now = () => Date.parse(iso); };
const bad = [];
const want = (name, got, exp) => { if (got !== exp) bad.push(name); };
at("2026-09-27T16:59:00Z");
want("12:59 ET, 1pm kick", rowStarted({game: "KC@MIA", kickoff: "13:00", game_date: "2026-09-27"}), false);
at("2026-09-27T17:00:30Z");
want("1:00 ET, 1pm kick", rowStarted({game: "KC@MIA", kickoff: "13:00", game_date: "2026-09-27"}), true);
want("a prop by team, slate date", rowStarted({team: "KC", date: "2026-W03"}), true);
want("the night game", rowStarted({game: "ATL@GB", kickoff: "20:15", game_date: "2026-09-27"}), false);
want("a game bet, night", rowStarted({home: "GB", away: "ATL", date: "2026-09-27"}), false);
want("scoreboard says live", rowStarted({team: "SF"}), true);
want("scoreboard pre is not started", likelyStarted({live: {state: "pre"}}), false);
at("2026-12-06T17:59:00Z");
want("December, EST, 12:59", likelyStarted({kickoff: "13:00", game_date: "2026-12-06"}), false);
at("2026-12-06T18:01:00Z");
want("December, EST, 1:01", likelyStarted({kickoff: "13:00", game_date: "2026-12-06"}), true);
console.log(bad.length ? "FAIL " + bad.join(", ") : "OK");
"""
    out = subprocess.run(["node", "-e", prog], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-400:]
    assert out.stdout.strip() == "OK", out.stdout.strip()


def test_a_late_tip_keeps_its_picks_until_the_scoreboard_says_the_ball_is_up():
    """Ethan, 2026-11-04, the 7pm NBA games: "They showed 7pm on the site
    but didn't start till around 7:10." The clock alone took their picks off
    the board at 7:00 while the Live tab, which follows the scoreboard, had
    nothing until the tip. A FRESH scoreboard read saying the game has not
    begun outranks the printed time for TIP_GRACE_MS; a stale read, a read
    for another league, or a game past the grace leaves the clock in charge,
    so a stopped feed never holds a pick through a game."""
    if not shutil.which("node"):
        print("  SKIP node is not installed")
        return
    prog = _started_src() + _fn("rowStarted") + _fn("gameKickedOff") + """
const state = {sport: "nba", data: {games: [
  {home: "DET", away: "PHI", date: "2026-11-04", kickoff: "2026-11-05T00:00Z", live: {state: "scheduled"}}]}};
let _pbpStrip = {league: "", at: 0, games: []};
const at = (iso) => { Date.now = () => Date.parse(iso); };
const read = (when, st, league) => { _tipRead = {league: league || "nba", at: Date.parse(when),
  games: [{home: "DET", away: "PHI", live: {state: st}}]}; };
const bad = [];
const want = (name, got, exp) => { if (got !== exp) bad.push(name); };
const prop = {team: "PHI", game_date: "2026-11-04"};
at("2026-11-04T23:59:00Z");
want("6:59, before the printed time", rowStarted(prop), false);
at("2026-11-05T00:04:00Z");
want("7:04 with no read: the clock", rowStarted(prop), true);
read("2026-11-05T00:03:30Z", "scheduled");
want("7:04, a fresh read says scheduled", rowStarted(prop), false);
want("the game too", gameKickedOff(state.data.games[0]), false);
want("a row by its own teams", likelyStarted({kickoff: "2026-11-05T00:00Z", game: "PHI@DET"}), false);
read("2026-11-05T00:03:30Z", "pre");
want("pre reads the same", rowStarted(prop), false);
read("2026-11-05T00:00:30Z", "scheduled");
want("a read 3.5 minutes old says nothing", rowStarted(prop), true);
read("2026-11-05T00:03:30Z", "scheduled", "nhl");
want("another league's read says nothing", rowStarted(prop), true);
read("2026-11-05T00:09:50Z", "live");
at("2026-11-05T00:10:00Z");
want("7:10, the scoreboard says live", rowStarted(prop), true);
read("2026-11-05T00:49:00Z", "scheduled");
at("2026-11-05T00:50:00Z");
want("50 minutes past: the clock again", rowStarted(prop), true);
state.data.games[0].live = {state: "live"};
read("2026-11-05T00:03:30Z", "scheduled");
at("2026-11-05T00:04:00Z");
want("the board's own copy saying live wins", rowStarted(prop), true);
console.log(bad.length ? "FAIL " + bad.join(", ") : "OK");
"""
    out = subprocess.run(["node", "-e", prog], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-600:]
    assert out.stdout.strip() == "OK", out.stdout.strip()


def test_a_board_watches_a_late_tip_and_draws_again_when_it_goes_up():
    src = _fn("tipWatch")
    assert "LIVE_FAST[state.sport]" in src and "TIP_GRACE_MS" in src and "PREGAME_STATES" in src
    assert "kickoffEpoch(" in src, "the printed time read the started check's way"
    assert "gameKickedOff(g)" in src and "renderAll()" in src, "draws again only when a verdict changes"
    assert "_tipRead = { league: sport, at: Date.now()" in src
    assert "tipWatch();" in _fn("manageAutoRefresh"), "every board load arms the watch"
    fresh = _fn("freshTipState")
    for cache in ("_pbpStrip", "_liveAll", "_deckFast", "_tipRead"):
        assert cache in fresh, cache
    assert "TIP_FRESH_MS" in fresh
    for fn in ("rowStarted", "gameKickedOff"):
        assert "away: g.away, home: g.home" in _fn(fn), fn


def test_the_shared_filter_stays_kickoff_blind():
    """`showableLikelyRow` also feeds the game page and the play-by-play
    tracker, which keep a started game's picks; the kickoff rule lives
    at each board instead."""
    src = _fn("showableLikelyRow")
    for banned in ("likelyStarted", "kickoff", "live"):
        assert banned not in src, \
            f"showableLikelyRow now drops rows on {banned} — they will vanish " \
            f"under the reader on the 60-second refresh"


def test_both_render_paths_say_so():
    """The board draws rows two ways — full cards and the compact list —
    and a label on one of them is a label a reader may never see."""
    assert "startedChip(r)" in _fn("likelyCard"), "the card does not label it"
    assert 'likelyStarted(r) ? " · under way"' in _fn("likelyRow"), \
        "the compact row does not label it"


def test_the_chip_has_a_style_to_wear():
    assert re.search(r"\.chip\.warn\s*\{", CSS), \
        "chip warn has no rule — the label renders unstyled"


def test_the_label_says_what_it_means_rather_than_just_flagging():
    """"under way" alone reads as a status badge. The title has to say
    why the row is still there and what it is worth — that the board
    ranks pre-game and this is what it thought before kickoff."""
    src = _fn("startedChip")
    assert "under way" in src
    for phrase in ("pre-game", "does not re-price", "vanish"):
        assert phrase in src, f"the explanation lost: {phrase}"


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
