"""Live scores must not wait on the model.

Ethan, 2026-08-16: *"none of the mlb game dispay live or have updated
scores"*.

MEASURED ON THE LIVE DROPLET, and the number is the whole story:
`mlb_recommendations.json` takes **7 minutes 39 seconds** to build, because
it prices 923 props. `web/js/app.js` read live scores out of that file — so
a score that changes every pitch waited for the entire model, and the site
showed games 8-15 minutes behind. During a game in progress that reads as
"the scores are broken". Nothing was broken; it was wired to the wrong file.

The UFC page had already solved this, and `ufc_live_build.py` says why in
its own docstring. MLB never got the same treatment.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import live_build                                             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as fh:
        return fh.read()


def _payload():
    """A doubleheader (both legs) plus a single game — the shape that broke
    the bare-pair key in parse_live, and the one a naive de-dup gets wrong."""
    return {"dates": [{"games": [
        {"gamePk": 111, "gameNumber": 1, "doubleHeader": "Y",
         "gameDate": "2026-08-16T17:05:00Z",
         "status": {"abstractGameState": "Live", "detailedState": "In Progress"},
         "teams": {"home": {"team": {"id": 112, "abbreviation": "CHC"}, "score": 3},
                   "away": {"team": {"id": 143, "abbreviation": "PHI"}, "score": 5}},
         "linescore": {"currentInningOrdinal": "6th", "inningState": "Bot",
                       "outs": 2, "balls": 1, "strikes": 2,
                       "offense": {"first": {"id": 1}, "third": {"id": 2}}}},
        {"gamePk": 222, "gameNumber": 2, "doubleHeader": "Y",
         "gameDate": "2026-08-16T21:05:00Z",
         "status": {"abstractGameState": "Preview", "detailedState": "Scheduled"},
         "teams": {"home": {"team": {"id": 112, "abbreviation": "CHC"}},
                   "away": {"team": {"id": 143, "abbreviation": "PHI"}}},
         "linescore": {}},
        {"gamePk": 333, "gameNumber": 1, "doubleHeader": "N",
         "gameDate": "2026-08-16T19:10:00Z",
         "status": {"abstractGameState": "Live", "detailedState": "In Progress"},
         "teams": {"home": {"team": {"id": 119, "abbreviation": "LAD"}, "score": 1},
                   "away": {"team": {"id": 135, "abbreviation": "SD"}, "score": 0}},
         "linescore": {"currentInningOrdinal": "3rd", "inningState": "Top", "outs": 0}},
    ]}]}


def _build(raw=None):
    was = live_build._get_json
    live_build._get_json = lambda *a, **k: (raw if raw is not None else _payload())
    try:
        return live_build.build("2026-08-16")
    finally:
        live_build._get_json = was


def test_home_and_away_are_never_swapped():
    """parse_live keys by an UNORDERED frozenset, so which side is home is
    not recoverable from a key. The first draft of live_build sorted the
    pair alphabetically, which would have reversed roughly half the cards —
    and a scoreboard that reports the wrong team ahead is worse than one
    that is late. home/away are read from the schedule, where they are
    explicit."""
    g = [x for x in _build()["games"] if x["game_pk"] == 111][0]
    assert g["home"] == "CHC" and g["away"] == "PHI"
    assert g["live"]["home_score"] == 3 and g["live"]["away_score"] == 5


def test_each_game_appears_exactly_once():
    """parse_live indexes every game under up to THREE keys — the gamePk, a
    (pair, leg) tuple, and the bare pair. Walking them all would draw each
    card three times."""
    out = _build()
    pks = [g["game_pk"] for g in out["games"]]
    assert sorted(pks) == [111, 222, 333], pks
    assert len(pks) == len(set(pks))


def test_both_legs_of_a_doubleheader_survive():
    """The pair is identical for both, so anything keyed on teams alone
    collapses them into one."""
    out = _build()
    chc = [g for g in out["games"] if g["home"] == "CHC"]
    assert len(chc) == 2
    assert {g["live"]["state"] for g in chc} == {"live", "scheduled"}


def test_the_fast_file_carries_no_priced_content():
    """It is a scoreboard. Keeping the model out of it is what makes it
    cheap — and it also keeps it clear of the paywall, because a score is a
    public fact that engine/gate.py has no reason to redact."""
    blob = json.dumps(_build())
    for leak in ("edge", "recommendation", "odds", "prop", "confidence"):
        assert leak not in blob, f"the scoreboard carries {leak}"
    assert len(blob) < 20000, f"{len(blob)} bytes is not a scoreboard"


def test_an_unreachable_feed_is_an_empty_board_not_a_crash():
    """This runs every few seconds beside a live site. One bad poll must not
    take the page down, and an empty scoreboard is a true statement about
    what we know."""
    from engine.sources.fetch import DataUnavailable

    def boom(*a, **k):
        raise DataUnavailable("network is down")
    was = live_build._get_json
    live_build._get_json = boom
    try:
        out = live_build.build("2026-08-16")
    finally:
        live_build._get_json = was
    assert out["games"] == []
    assert "unreachable" in out["note"]


def test_the_page_reads_scores_from_the_fast_file():
    app = _read("web", "js", "app.js")
    assert 'LIVE_FAST = { mlb: "data/live_mlb.json" }' in app
    i = app.index("async function fetchAllLive")
    body = app[i:i + 1800]
    assert "LIVE_FAST[sport]" in body, "the fast file is declared but unused"
    # The BETS still come from the slow board: a price minutes old is
    # defensible, a score minutes old is not.
    assert "d.game_bets" in body


def test_a_missing_fast_file_leaves_the_page_as_it_was():
    """The fast loop can be a minute behind a fresh deploy. Falling back to
    the board is what stops that minute being an empty Live Now page."""
    app = _read("web", "js", "app.js")
    i = app.index("async function fetchAllLive")
    body = app[i:i + 1800]
    assert "let games = d.games || []" in body, "no fallback source"
    assert "df.games.length" in body, "an empty fast file would blank the page"


def test_the_launcher_actually_runs_it():
    """A builder nothing calls is the most convincing kind of dead code."""
    launch = _read("launch.py")
    assert "def _live_mlb_refresher(" in launch
    assert "target=_live_mlb_refresher" in launch, "defined but never started"
    fn = launch[launch.index("def _live_mlb_refresher("):]
    fn = fn[:fn.index("\ndef ")]
    assert '_run_build(["live_build.py"])' in fn
    # Fast while a game is on, idle otherwise — same shape as the fight
    # poller it was modelled on.
    assert "LIVE_FAST_S" in fn and "LIVE_IDLE_S" in fn


def test_the_mlb_build_is_not_guillotined_at_the_default_timeout():
    """The frozen-board bug of 2026-08-17, pinned at its cause.

    _run_build kills any build at its timeout, and 180s is right for the
    fast loops — but the MLB board has never reliably fit under three
    minutes on the production box, so at the default EVERY warm build was
    killed and the board froze at its one untimed cold-start write. The
    big build passes its own ceiling; the kill prints a line, because
    three hours of silent kills is what turned a config number into a
    day-long investigation.
    """
    launch = _read("launch.py")
    fn = launch[launch.index("def refresh_mlb("):]
    fn = fn[:fn.index("\ndef ")]
    assert "_run_build(args, timeout=600)" in fn, \
        "the MLB build is back on the 180s guillotine"
    runner = launch[launch.index("def _run_build("):]
    runner = runner[:runner.index("\ndef ")]
    assert 'timeout: int = 180' in runner, \
        "the DEFAULT moved — the fast loops must stay on a short leash"
    assert runner.count("build failed:") >= 2, \
        "a killed build no longer says so in the journal"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
