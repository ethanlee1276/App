"""The coverage scan: does it MEASURE, or does it just agree with the docs?

Implementation maps in `docs/` are prose, and prose rots — a feed stops
resolving, a season never gets ingested, a key expires, and the table still
says ✅ because nobody edited it. This scan exists to answer the same
question by looking at the database, the cache and the config.

So the tests that matter are the ones proving it actually looks: an empty
database has to report gaps, a populated one has to report them closed, and
a layer with no free source has to stay visible forever rather than
quietly inflating the score.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import coverage as C


def test_every_sport_with_a_board_is_scanned():
    assert set(C.BUILDERS) == {"nfl", "mlb", "nba", "wnba", "cfb", "ufc"}


def test_the_scan_reads_the_database_rather_than_a_document():
    from engine import db
    conn = db.connect(":memory:")
    empty = C.cfb(conn)
    results = next(l for l in empty.layers if l.name == "Results history")
    assert results.state == C.MISSING
    assert "0 finished" in results.detail

    db.upsert_games(conn, [
        {"sport": "cfb", "season": 2025, "period": f"2025-09-{i % 28 + 1:02d}",
         "game_id": str(i), "home": "A", "away": "B",
         "home_score": 30.0, "away_score": 20.0} for i in range(500)])
    filled = C.cfb(conn)
    results = next(l for l in filled.layers if l.name == "Results history")
    assert results.state == C.OK
    # …and the variance fit flips with it, because it reads the same rows.
    variance = next(l for l in filled.layers if l.name == "Fitted variance")
    assert variance.state == C.OK


def test_a_gap_carries_the_command_that_closes_it():
    """'MLB umpires: missing' is only useful next to the thing you'd run."""
    from engine import db
    conn = db.connect(":memory:")
    for cov in (C.cfb(conn), C.wnba(conn), C.mlb(conn), C.nfl(conn)):
        for l in cov.layers:
            if l.state == C.MISSING:
                assert l.fix or l.detail, f"{cov.sport}/{l.name} says nothing"


def test_every_layer_explains_why_it_matters():
    from engine import db
    conn = db.connect(":memory:")
    for sport, build in C.BUILDERS.items():
        for l in build(conn).layers:
            assert l.why, f"{sport}/{l.name} has no reason to exist"
            assert l.state in (C.OK, C.PARTIAL, C.MISSING, C.PARKED)


def test_a_parked_layer_never_flatters_the_score():
    """Counting a gap with no free source against the model would make the
    number meaningless — and dropping it from the report would let a
    permanent blind spot disappear."""
    from engine import db
    conn = db.connect(":memory:")
    cov = C.wnba(conn)
    parked = [l for l in cov.layers if l.state == C.PARKED]
    assert parked, "the WNBA has known permanent gaps; they must stay listed"
    have, total = cov.score
    assert total == len([l for l in cov.layers if l.state != C.PARKED])
    assert have <= total


def test_the_wnba_availability_gap_is_reported_as_the_headline_upgrade():
    from engine import db
    conn = db.connect(":memory:")
    layer = next(l for l in C.wnba(conn).layers
                 if l.name.startswith("Availability"))
    assert layer.state == C.MISSING
    assert "half-Kelly" in layer.detail or "grade" in layer.detail


def test_the_report_renders_without_a_database():
    text = C.report(["cfb"])
    assert "College football" in text and "why it matters" in text
    # The legend has to survive, or 📋 rows read as failures.
    assert "no free source exists" in text


def test_cache_checks_glob_rather_than_guessing_a_filename():
    """The bug this prevents, and it fired on the real machine: the injury
    feed caches as injuries_2026.csv and Statcast as
    savant_barrels_batter_2026.csv, so a fixed-name check reported two
    working feeds as never fetched. A scan that cries wolf is worse than
    no scan — you stop reading it, and the real gap goes past you too."""
    import tempfile
    from pathlib import Path as _P
    saved = C.CACHE
    try:
        tmp = _P(tempfile.mkdtemp())
        C.CACHE = tmp
        for name in ("injuries_2026.csv", "savant_barrels_batter_2026.csv",
                     "sleeper_players_nfl.json"):
            (tmp / name).write_text("x")
        assert C._cache_age_h("injuries_*.csv") is not None
        assert C._cache_age_h("savant_*.csv") is not None
        assert C._cache_age_h("sleeper_players_nfl*.json") is not None
        # …and a genuinely absent feed still reports absent.
        assert C._cache_age_h("espn_cfb_*.json") is None
    finally:
        C.CACHE = saved


def test_no_layer_checks_a_cache_name_nothing_writes():
    """Every glob in the scan must match something a source actually
    writes, or it is a permanent false alarm."""
    import re
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "engine", "coverage.py"),
               encoding="utf-8").read()
    globs = set(re.findall(r'_cache_age_h\("([^"]+)"\)', src))
    assert globs, "the scan checks no caches at all"
    engine_src = ""
    for dirpath, _dirs, files in os.walk(os.path.join(root, "engine")):
        for f in files:
            if f.endswith(".py"):
                engine_src += open(os.path.join(dirpath, f),
                                   encoding="utf-8").read()
    for g in globs:
        stem = g.split("*")[0]
        assert stem in engine_src, (
            f"nothing in engine/ ever writes a cache starting {stem!r} — "
            f"this check can only ever report a false gap")


def test_an_out_of_season_board_is_not_reported_as_a_failure():
    """NFL in July has journaled nothing because there was nothing to bet.
    Flagging that ❌ next to a real gap trains you to skim the rows that
    matter.

    BOTH INPUTS ARE STUBBED, and the second one is the fix. The branch under
    test fires on `not (o or s) and dormant` — an empty journal AND a
    dormant board. This stubbed only `C.ROOT`, which controls the board
    status; `o` and `s` come from `_journal()`, which opens the REAL ledger
    through `ledger.DEFAULT_DB` and ignores `C.ROOT` entirely.

    So the test passed for as long as the live journal happened to hold no
    NFL bets, and failed on Ethan's machine the first evening it did — the
    run-up change (SEASON_RUNUP_DAYS) let the launcher build Week 1 in
    August, which journaled six game bets, which made `o` non-zero, which
    skipped the branch. Nothing about the behaviour under test had changed.

    `ledger.connect()` resolves DEFAULT_DB at call time precisely so a test
    can repoint it, which is what this now does.
    """
    import tempfile, json as _json
    from pathlib import Path as _P
    from engine import ledger as _led
    saved_root, saved_db = C.ROOT, _led.DEFAULT_DB
    try:
        tmp = _P(tempfile.mkdtemp())
        (tmp / "web" / "data").mkdir(parents=True)
        (tmp / "web" / "data" / "recommendations.json").write_text(
            _json.dumps({"status": "offseason"}))
        C.ROOT = tmp
        _led.DEFAULT_DB = tmp / "ledger.db"      # empty: no bets, any sport
        assert C._journal("nfl") == (0, 0), \
            "the ledger stub did not take — this test is reading a real one"
        layer = C._journal_layer("nfl")
        assert layer.state == C.PARTIAL
        assert "out of season" in layer.detail
    finally:
        C.ROOT, _led.DEFAULT_DB = saved_root, saved_db


def test_a_dormant_board_with_journaled_bets_is_not_called_out_of_season():
    """The other half of that branch, which nothing covered.

    "Out of season" is a claim about having bet NOTHING. A board that is
    dormant today but holds settled bets from last season has a real record
    to report, and saying "nothing journaled yet" over the top of it would
    be false — the exact case the run-up change created in August."""
    import tempfile, json as _json
    from pathlib import Path as _P
    from engine import ledger as _led
    saved_root, saved_db = C.ROOT, _led.DEFAULT_DB
    try:
        tmp = _P(tempfile.mkdtemp())
        (tmp / "web" / "data").mkdir(parents=True)
        (tmp / "web" / "data" / "recommendations.json").write_text(
            _json.dumps({"status": "offseason"}))
        C.ROOT = tmp
        _led.DEFAULT_DB = tmp / "ledger.db"
        conn = _led.connect(_led.DEFAULT_DB)
        conn.execute(
            "INSERT INTO bets (ts, sport, date, player, market, side, line,"
            " odds, stake_units, status, category) "
            "VALUES ('t','nfl','2026-09-13','X','rush_yds','OVER',1,-110,"
            "1,'won','main')")
        conn.commit(); conn.close()
        assert C._journal("nfl") == (0, 1)
        layer = C._journal_layer("nfl")
        assert "out of season" not in layer.detail, layer.detail
    finally:
        C.ROOT, _led.DEFAULT_DB = saved_root, saved_db


def test_every_command_the_scan_prints_actually_exists():
    """The bug this prevents, and it fired on the real machine: the WNBA
    row told Ethan to run `python3 ingest.py wnba`, and ingest.py had no
    wnba mode. A fix line that doesn't run is worse than no fix line —
    it sends you off to debug your own machine over our typo."""
    import re
    import subprocess
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "engine", "coverage.py"),
               encoding="utf-8").read()
    cmds = set(re.findall(r"python3 ([a-z_]+\.py)([^\"']*)", src))
    assert cmds, "the scan offers no commands at all"

    launch = open(os.path.join(root, "launch.py"), encoding="utf-8").read()
    for script, tail in sorted(cmds):
        assert os.path.isfile(os.path.join(root, script)), \
            f"the scan points at {script}, which does not exist"
        tail = tail.strip()
        if not tail:
            continue
        # A fix line may template the sport it belongs to. Resolve the
        # placeholder rather than skipping the row: the point of this test
        # is that "python3 ingest.py wnba" was offered for a mode that did
        # not exist, and a templated command can be wrong the same way.
        tail = tail.replace("{sport}", "mlb")
        first = tail.split()[0]
        if first.startswith("{"):
            raise AssertionError(f"{script}: unresolved placeholder {first!r} "
                                 f"— the printed command would not run")
        if first.startswith("--"):
            # A launcher flag has to be dispatched, or it silently starts
            # the server instead of doing what the row promised.
            if script == "launch.py":
                assert f'"{first}" in argv' in launch, \
                    f"launch.py never dispatches {first}"
            else:
                out = subprocess.run(
                    ["python3", os.path.join(root, script), "--help"],
                    capture_output=True, text=True, timeout=60)
                assert first in out.stdout, f"{script} has no {first}"
        else:
            # A positional subcommand has to be in that script's choices.
            out = subprocess.run(
                ["python3", os.path.join(root, script), "--help"],
                capture_output=True, text=True, timeout=60)
            assert first in out.stdout, \
                f"{script} does not accept the subcommand {first!r}"


def test_a_fix_command_never_contradicts_the_layer_it_fixes():
    """The previous test only asks whether a command RUNS. This one asks
    whether it does the thing the row promised.

    The bug it fired on: the NBA "0 player game logs" row offered
    `ingest.py nba --seasons 2021-2026 --scores-only`. That command runs,
    it is spelled correctly, and `--scores-only` is exactly the flag that
    SKIPS player logs — so it would exit looking successful (every day is
    already stored) having changed nothing. A fix line that quietly does
    the opposite of what it claims is worse than a typo, because a typo
    tells you something is wrong.
    """
    from engine import coverage
    from engine.db import connect

    conn = connect(":memory:")
    for sport, build in coverage.BUILDERS.items():
        for layer in build(conn).layers:
            fix = (layer.fix or "").lower()
            if not fix:
                continue
            if "player game logs" in layer.name.lower():
                assert "--scores-only" not in fix, (
                    f"{sport}: the fix for missing player logs passes "
                    f"--scores-only, which is what skips them")
            if "results history" in layer.name.lower():
                assert "ingest.py" in fix, (
                    f"{sport}: results are closed by an ingest, not by "
                    f"{fix!r}")


def test_a_layer_that_claims_the_launcher_refreshes_it_is_actually_refreshed():
    """"→ refreshes with the launcher" is a promise, and it was false.

    The NFL injury layer said it, and `refresh_nfl` never passed
    `--injuries` — so §7's ripple model would have gone into Week 1
    unfetched while the scan told you it was handled. A fix line nobody
    has to run is the easiest kind to leave broken.
    """
    from engine import coverage
    from engine.db import connect

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    launch = open(os.path.join(root, "launch.py"), encoding="utf-8").read()
    conn = connect(":memory:")
    claims = [(s, l) for s, build in coverage.BUILDERS.items()
              for l in build(conn).layers
              if "refreshes with the launcher" in (l.fix or "")]
    assert claims, "no layer makes this claim — did the wording change?"
    for sport, layer in claims:
        if "injury" in layer.name.lower() and sport == "nfl":
            fn = launch[launch.index("def refresh_nfl("):
                        launch.index("def refresh_predmarkets(")]
            assert "--injuries" in fn, (
                "the NFL injury layer says the launcher refreshes it, and "
                "refresh_nfl never asks for injuries")


def test_ingest_speaks_every_sport_the_scan_reports_on():
    """The scan tells you to ingest a sport; ingest.py has to know it.
    Every gap between those two lists is a fix line that fails."""
    import subprocess
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = subprocess.run(["python3", os.path.join(root, "ingest.py"), "--help"],
                         capture_output=True, text=True, timeout=60)
    for sport in C.BUILDERS:
        assert sport in out.stdout, f"ingest.py has no {sport} arm"


def test_the_launcher_exposes_it():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "launch.py"), encoding="utf-8") as fh:
        src = fh.read()
    assert '"--coverage" in argv' in src
    assert "from engine.coverage import report" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
