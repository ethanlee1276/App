"""Bets that stay open after the game is over.

"we have props from today that are over but they haven't closed on the site.
how can we change that so the prop automatically records when the game ends"

The machinery was already there: launch.py's background cycle calls
`settle_open` every pass, it throttles itself to 15 minutes, and it grades
anything whose game has finished. What it could not grade was anything whose
RESULTS were not in the history DB yet — settlement compares a bet to a
stored stat line, so a finished game nobody ingested is indistinguishable
from a game still in progress.

So `settle_open` ingests first. It ingested MLB, and it ingested NBA for any
date with an open NBA pick. It did not ingest the WNBA — which is the league
that needed it most, because the NBA is dark from June to October and the
WNBA plays through exactly those months. The one basketball board with live
bets all summer was the one whose picks could not close until the next
morning's maintenance pass.
"""

import datetime as _dt
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import maintenance as M

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = open(os.path.join(ROOT, "engine", "maintenance.py"), encoding="utf-8").read()


# --- the gap ----------------------------------------------------------------
def test_both_basketball_leagues_grade_intraday():
    """The NBA had an intraday ingest and the WNBA did not."""
    i = SRC.index("def ingest_for_open_bets(")
    block = SRC[i:i + 2200]
    assert '("nba", _nba_day)' in block
    assert '("wnba", _wnba_day)' in block


def test_a_league_is_only_pulled_when_it_has_an_open_pick_that_day():
    """Otherwise a quiet night costs a feed round-trip per open date for
    leagues with nothing riding on them."""
    i = SRC.index("def ingest_for_open_bets(")
    block = SRC[i:i + 2200]
    assert "_has_open(lconn, league, [d])" in block
    helper = SRC[SRC.index("def _has_open("):]
    assert "WHERE status='open' AND sport=?" in helper[:400], \
        "the open-pick check is not scoped to the league being ingested"


def test_baseball_is_only_pulled_when_it_has_an_open_pick_too():
    """It used to run unconditionally, so a WNBA-only night still paid for
    a full MLB results fetch."""
    i = SRC.index("def ingest_for_open_bets(")
    block = SRC[i:i + 2200]
    assert '_has_open(lconn, "mlb", days)' in block


def test_both_settle_paths_share_one_ingest():
    """They drifted once already: the intraday pass learned about the WNBA
    and the --settle CLI did not, so the same bet graded on one path and
    sat open on the other."""
    launch = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    assert "from engine.maintenance import ingest_for_open_bets" in launch
    assert "ingest.ingest_mlb_results(hconn, day, day" not in launch, \
        "the CLI still ingests baseball and only baseball"


def test_one_leagues_feed_hiccup_cannot_strand_the_others_bets():
    """The try/except has to be INSIDE the loop. Wrapping the whole loop
    means a WNBA outage skips the NBA ingest sitting after it — and both
    would then miss the MLB settle below."""
    i = SRC.index("def ingest_for_open_bets(")
    block = SRC[i:i + 2200]
    body = block[block.index("for d in days:"):]
    assert body.index("try:") < body.index("ingest_day(hconn, d)")
    assert "except Exception:" in body


def test_a_missing_source_module_degrades_rather_than_crashing():
    """_hoops_ingesters imports through a function so a broken source is
    "that league does not grade intraday", not a dead settle pass."""
    nba, wnba = M._hoops_ingesters()
    assert callable(nba) and callable(wnba)
    i = SRC.index("def _hoops_ingesters(")
    assert SRC[i:i + 1200].count("except Exception:") >= 2


def test_the_wnba_ingester_asks_for_the_wnba():
    """espnhoops serves both leagues off one parser; the league argument is
    the only thing that distinguishes them, and defaulting it would have
    quietly ingested basketball's other league."""
    i = SRC.index("def wnba(conn, date):")
    assert 'league="wnba"' in SRC[i:i + 200]


# --- the surrounding contract, unchanged ------------------------------------
def test_it_throttles_so_it_is_cheap_to_call_every_cycle():
    assert M.SETTLE_EVERY_S == 900
    conn_state = os.path.join(tempfile.mkdtemp(), "s.json")
    with open(conn_state, "w") as fh:
        json.dump({"last_settle_ts": 1_000_000.0}, fh)
    # 60 seconds after the last pass: a no-op, without touching the journal.
    assert M.settle_open(log=lambda *_: None, state_path=conn_state,
                         now=1_000_060.0) == 0


def test_force_overrides_the_throttle():
    """`--settle` by hand has to work the moment you run it, not up to
    fifteen minutes later."""
    state = os.path.join(tempfile.mkdtemp(), "s.json")
    with open(state, "w") as fh:
        json.dump({"last_settle_ts": 1_000_000.0}, fh)
    import inspect
    assert "force" in inspect.signature(M.settle_open).parameters
    src = inspect.getsource(M.settle_open)
    assert "if not force and" in src


def test_the_lookback_covers_a_closed_laptop_overnight():
    assert M.SETTLE_LOOKBACK_DAYS >= 2


def test_the_launcher_calls_it_every_cycle():
    launch = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    fn = launch[launch.index("def _background_refresher("):]
    fn = fn[:fn.index("\n\n\n")]
    assert "_run_autosettle()" in fn, \
        "nothing settles tonight's bets until tomorrow's first cycle"


def test_a_settle_writes_the_record_page():
    """Grading a bet that the Record page never learns about is the same as
    not grading it, from where the owner is sitting."""
    src = open(os.path.join(ROOT, "engine", "maintenance.py"),
               encoding="utf-8").read()
    i = src.index("def settle_open(")
    block = src[i:i + 4000]
    assert 'export_json(lconn, ROOT / "web" / "data" / "record.json")' in block


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
