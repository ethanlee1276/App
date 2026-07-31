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
    matter."""
    saved = C.ROOT
    import tempfile, json as _json
    from pathlib import Path as _P
    try:
        tmp = _P(tempfile.mkdtemp())
        (tmp / "web" / "data").mkdir(parents=True)
        (tmp / "web" / "data" / "recommendations.json").write_text(
            _json.dumps({"status": "offseason"}))
        C.ROOT = tmp
        layer = C._journal_layer("nfl")
        assert layer.state == C.PARTIAL
        assert "out of season" in layer.detail
    finally:
        C.ROOT = saved


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
        first = tail.split()[0]
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
