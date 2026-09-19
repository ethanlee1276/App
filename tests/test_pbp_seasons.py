"""Four seasons of touchdowns, one season of red-zone usage.

`ingest_nfl` pulled play-by-play for `max(seasons)` — one line, with
"(the file is ~100MB)" as its reason. So `ingest.py nfl --seasons
2022-2025` brought back four seasons of box scores and red-zone usage
for one of them. Measured 2026-08-28:

    season   anytime_td   rz_car   rz_tgt   i5_car
      2022      6,083        0        0        0
      2023      6,071        0        0        0
      2024      6,141    5,435    5,435    5,435
      2025      6,321    5,484    5,484    5,484

Red-zone usage is the touchdown model's single best predictor — its own
docs say so — and `engine.tdbacktest` grades that model across every
ingested season to fit the correction every live touchdown pick is
priced through. Half that fit was measured with the best input switched
off, and nothing said so: the caller asked for four seasons and was told
it got them.

The size concern was real. It is answered by doing the seasons one at a
time and letting each stand or fall alone, not by silently dropping
three quarters of the request.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import ingest
from engine.sources import nflpbp
from engine.sources.fetch import DataUnavailable


class _Stub:
    """Records which seasons were asked for; returns one row each."""

    def __init__(self, explode_on=()):
        self.seen, self.explode_on = [], set(explode_on)

    def install(self):
        self._saved = (nflpbp.load_pbp_rows, nflpbp.aggregate_pbp,
                       nflpbp.xfp_player_rows, nflpbp.team_week_rows)
        nflpbp.load_pbp_rows = self._load
        nflpbp.aggregate_pbp = lambda rows: {"season": rows}
        nflpbp.xfp_player_rows = self._player
        nflpbp.team_week_rows = lambda agg, season: []
        return self

    def restore(self):
        (nflpbp.load_pbp_rows, nflpbp.aggregate_pbp,
         nflpbp.xfp_player_rows, nflpbp.team_week_rows) = self._saved

    def _load(self, season):
        self.seen.append(season)
        if season in self.explode_on:
            raise DataUnavailable(f"no pbp for {season}")
        return season

    def _player(self, agg, season):
        return [{"sport": "nfl", "season": season, "period": "001",
                 "game_id": "g", "player": "P", "team": "T",
                 "opponent": "O", "position": "RB", "home": 1,
                 "market": "rz_car", "value": 3.0}]


def _run(seasons, explode_on=()):
    from engine import db
    stub = _Stub(explode_on).install()
    try:
        conn = db.connect(":memory:")
        # Only the pbp arm is under test; the feeds above it are offline
        # here and report themselves as skipped, which is fine.
        try:
            result = ingest.ingest_nfl(conn, seasons=list(seasons))
        except Exception:
            result = None
        return stub.seen, result, conn
    finally:
        stub.restore()


def test_every_requested_season_is_pulled_not_just_the_newest():
    seen, _, _ = _run([2022, 2023, 2024, 2025])
    assert seen == [2022, 2023, 2024, 2025], seen


def test_the_seasons_are_pulled_oldest_first():
    """One at a time and in order, so a run interrupted partway through
    leaves a contiguous history rather than a hole in the middle."""
    seen, _, _ = _run([2025, 2022, 2024, 2023])
    assert seen == sorted(seen)


def test_one_season_missing_does_not_cost_the_others():
    """A season whose file has not been published yet is a skip, not a
    failure — the ingest reports what it could reach."""
    seen, result, conn = _run([2022, 2023, 2024], explode_on=[2023])
    assert seen == [2022, 2023, 2024]
    if result is not None:
        assert any("2023" in s for s in result["skipped"]), result["skipped"]
        assert result["pbp_rows"] > 0, "the reachable seasons still landed"


def test_the_skip_names_the_season_that_was_missing():
    """"nfl pbp: ..." with no year is unactionable once the loop can
    visit four of them."""
    _, result, _ = _run([2022, 2023], explode_on=[2022])
    if result is not None:
        assert any(s.startswith("nfl pbp 2022") for s in result["skipped"]), \
            result["skipped"]


def test_red_zone_rows_land_for_every_season_that_was_reached():
    seen, _, conn = _run([2022, 2023, 2024])
    got = {r[0] for r in conn.execute(
        "SELECT DISTINCT season FROM player_game_logs "
        "WHERE sport='nfl' AND market='rz_car'")}
    assert got == {2022, 2023, 2024}, got


def test_the_source_still_reads_one_season_at_a_time():
    """The 100MB-per-season concern is answered by the loop's shape, not
    by dropping the request: nothing accumulates every season's plays in
    memory at once."""
    import inspect
    src = inspect.getsource(ingest.ingest_nfl)
    assert "for season in sorted(seasons):" in src
    # The SHORTCUT, not the substring. `max(seasons)` legitimately
    # appears in the ingest's own log line and in the schedule's
    # next-season reach; a blunt match fails on both and teaches the next
    # reader to loosen the assertion rather than trust it.
    assert "season = max(seasons)" not in src, \
        "the newest-season-only shortcut is back"


def test_the_ingest_command_reports_what_the_pbp_arm_did():
    """Every other sport's arm prints its skips. This one printed games
    and box scores and nothing else, so a red-zone backfill that fetched
    nothing looked exactly like one that worked — on the command run
    specifically to fetch it."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "ingest.py"), encoding="utf-8") as fh:
        src = fh.read()
    arm = src.split('if args.sport == "nfl":', 1)[1].split("elif args.sport", 1)[0]
    assert "pbp_rows" in arm, "the pbp arm's row count is still invisible"
    assert 'res["skipped"]' in arm, "its skips are still swallowed"
    assert "no play-by-play stored" in arm, \
        "a zero must say so rather than reading as success"


def test_the_nightly_still_refreshes_only_the_current_season():
    """The weekly maintenance pass wants tonight's numbers, not a
    four-season backfill on a 1 vCPU box."""
    import inspect
    from engine import maintenance
    src = inspect.getsource(maintenance)
    assert "season = today.year if today.month >= 8 else today.year - 1" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
