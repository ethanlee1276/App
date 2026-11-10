"""The matchup scan's charting and tracking tables are kept between builds
until one of their files changes (engine/gamescan._kept_tables,
charting_tables, tracking_tables).

The NFL build at 03:18 on 10 November spent 2.6 seconds of its matchup scan
on these two tables. The charting table joins FTN's file to the season's
play-by-play, a 47 MB file read whole to find 23,647 plays (0.74 of its 0.93
seconds on a copy of the same files), and both are worked out again every
build from files the fetch layer refreshes a few times a day. What these
hold:

  * a kept table is exactly the table its files give, and a second build
    works neither table out again;
  * a changed file or another week works the table out again;
  * a file due its refresh is read the plain way (that read is the one that
    refreshes it), and nothing is kept from it;
  * a table whose copy would not read back equal is never kept;
  * only a build against the production history keeps; the scan elsewhere
    (the backtest, the tests) works its tables out as it always did.

Run directly: `python3 tests/test_the_scan_keeps_its_file_tables.py`
"""
import csv
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import gamescan as G                                   # noqa: E402
from engine.sources import fetch as FE                              # noqa: E402
from engine.sources import ftn as F                                 # noqa: E402
from engine.sources import ngs as NGS                               # noqa: E402


def _chart(game, play, week, **flags):
    """One FTN charting row (tests/test_the_play_charting_is_read_and_shown.py's)."""
    row = {"nflverse_game_id": game, "nflverse_play_id": str(play), "week": str(week),
           "n_blitzers": "0", "n_pass_rushers": "4", "n_defense_box": "7"}
    for k in ("is_play_action", "is_screen_pass", "is_rpo", "is_motion", "is_no_huddle",
              "is_qb_out_of_pocket", "is_interception_worthy", "is_throw_away", "is_catchable_ball",
              "is_contested_ball", "is_created_reception", "is_drop", "is_qb_fault_sack"):
        row[k] = "FALSE"
    row.update({k: (str(v).upper() if isinstance(v, bool) else str(v)) for k, v in flags.items()})
    return row


def _play(game, play, week, posteam, defteam, kind, **who):
    """One play-by-play row, the columns the charting join reads."""
    row = {"game_id": game, "play_id": f"{play}.0", "week": str(week), "posteam": posteam, "defteam": defteam,
           "play_type": kind, "pass_attempt": "1" if kind == "pass" else "0",
           "rush_attempt": "1" if kind == "run" else "0", "qb_dropback": "1" if kind == "pass" else "0",
           "qb_scramble": "0", "sack": "0", "interception": "0", "complete_pass": "0",
           "passer_player_id": "", "passer_player_name": "", "receiver_player_id": "",
           "receiver_player_name": "", "rusher_player_id": "", "rusher_player_name": ""}
    row.update(who)
    return row


def _game_fixture(g, week):
    """One game: ten PHI dropbacks against CHI (four blitzed), four runs."""
    charted, plays = [], []
    for i in range(10):
        charted.append(_chart(g, i + 1, week, n_pass_rushers=5 if i < 4 else 4, n_blitzers=1 if i < 4 else 0,
                              is_interception_worthy=(i == 0), is_catchable_ball=(i < 8),
                              is_drop=(i == 1), is_contested_ball=(i == 2), is_play_action=(i < 3)))
        plays.append(_play(g, i + 1, week, "PHI", "CHI", "pass", passer_player_id="00-H",
                           passer_player_name="J.Hurts", receiver_player_id="00-S",
                           receiver_player_name="D.Smith"))
    for i in range(4):
        charted.append(_chart(g, 20 + i, week, n_defense_box=8 if i < 3 else 5))
        plays.append(_play(g, 20 + i, week, "PHI", "CHI", "run", rusher_player_id="00-B",
                           rusher_player_name="S.Barkley"))
    return charted, plays

NGS_ROWS = [
    {"season": "2026", "week": "1", "team_abbr": "PHI", "player_display_name": "DeVonta Smith",
     "player_position": "WR", "targets": "10", "avg_separation": "3.0", "avg_cushion": "6.0",
     "avg_intended_air_yards": "12", "percent_share_of_intended_air_yards": "40",
     "avg_yac_above_expectation": "0.5"},
    {"season": "2026", "week": "2", "team_abbr": "LAR", "player_display_name": "Puka Nacua",
     "player_position": "WR", "targets": "12", "avg_separation": "2.0", "avg_cushion": "5.0",
     "avg_intended_air_yards": "8", "percent_share_of_intended_air_yards": "35",
     "avg_yac_above_expectation": "1.0"},
]


def _write(path, rows):
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def _season_fixture():
    """Five such games, weeks 1-4: past every table's minimum (40 dropbacks
    a defence, 30 attempts a passer, 8 targets a receiver)."""
    charted, plays = [], []
    for n, week in enumerate((1, 2, 3, 3, 4)):
        c, p = _game_fixture(f"2026_{week:02d}_CHI_PHI_{n}", week)
        charted += c
        plays += p
    return charted, plays


class _Files:
    """Fresh cached feed files in a scratch cache, the models in another,
    and each table's working-out counted."""

    def __enter__(self):
        self.cache, self.models = tempfile.TemporaryDirectory(), tempfile.TemporaryDirectory()
        self.old = FE.CACHE_DIR, os.environ.get("QB_MODELS_DIR"), F.season_tables, NGS.season_tables
        FE.CACHE_DIR = Path(self.cache.name)
        os.environ["QB_MODELS_DIR"] = self.models.name
        charted, plays = _season_fixture()
        self.pbp = FE.CACHE_DIR / "pbp_2026.csv"
        _write(FE.CACHE_DIR / "ftn_charting_2026.csv", charted)
        _write(self.pbp, plays)
        for kind in NGS.KINDS:
            _write(FE.CACHE_DIR / f"ngs_{kind}.csv", NGS_ROWS if kind == "receiving" else [NGS_ROWS[0]])
        self.worked = {"charting": 0, "tracking": 0}
        real_f, real_n = F.season_tables, NGS.season_tables

        def _f(*a, **k):
            self.worked["charting"] += 1
            return real_f(*a, **k)

        def _n(*a, **k):
            self.worked["tracking"] += 1
            return real_n(*a, **k)
        F.season_tables, NGS.season_tables = _f, _n
        return self

    def __exit__(self, *exc):
        FE.CACHE_DIR, models, F.season_tables, NGS.season_tables = self.old
        if models is None:
            os.environ.pop("QB_MODELS_DIR", None)
        else:
            os.environ["QB_MODELS_DIR"] = models
        self.cache.cleanup()
        self.models.cleanup()


def test_a_kept_table_is_its_files_table_and_a_second_build_works_out_neither():
    with _Files() as f:
        plain_c, plain_t = G.charting_tables(2026, 5), G.tracking_tables(2026, 5)
        assert f.worked == {"charting": 1, "tracking": 1}
        assert plain_c["defense"]["CHI"]["blitz"] == 20 and ("PHI", "D.Smith") in plain_c["receivers"]
        assert ("PHI", "J.Hurts") in plain_c["qbs"] and plain_c["partial"] == 4
        assert ("PHI", "DeVonta Smith") in plain_t["receivers"]
        first_c, first_t = G.charting_tables(2026, 5, keep=True), G.tracking_tables(2026, 5, keep=True)
        assert first_c == plain_c and first_t == plain_t and f.worked == {"charting": 2, "tracking": 2}
        again_c, again_t = G.charting_tables(2026, 5, keep=True), G.tracking_tables(2026, 5, keep=True)
        assert again_c == plain_c and again_t == plain_t
        assert f.worked == {"charting": 2, "tracking": 2}, "the second build works out neither"
        assert isinstance(next(iter(again_c["receivers"])), tuple), "the player keys come back as they were"


def test_a_changed_file_or_another_week_works_the_table_out_again():
    with _Files() as f:
        G.charting_tables(2026, 5, keep=True)
        assert f.worked["charting"] == 1
        G.charting_tables(2026, 4, keep=True)
        assert f.worked["charting"] == 2, "another week"
        charted, plays = _season_fixture()
        _write(f.pbp, plays[:-2])                               # the play-by-play changed
        changed = G.charting_tables(2026, 5, keep=True)
        assert f.worked["charting"] == 3 and changed == G.charting_tables(2026, 5)
        G.charting_tables(2026, 5, keep=True)
        assert f.worked["charting"] == 4, "kept again under the new file (one plain read between)"


def test_a_file_due_its_refresh_is_read_plainly_and_nothing_is_kept():
    with _Files() as f:
        due = time.time() - F.TTL + 30                          # inside the minute's slack, still served
        os.utime(FE.CACHE_DIR / "ftn_charting_2026.csv", (due, due))
        for _ in range(2):
            G.charting_tables(2026, 5, keep=True)
        assert f.worked["charting"] == 2, "worked out every time, the plain way"
        assert not os.path.exists(os.path.join(os.environ["QB_MODELS_DIR"], "scan_charting_nfl_2026.json"))


def test_a_table_that_would_not_read_back_equal_is_never_kept():
    with _Files() as f:
        odd = {"season": 2026, "weeks": {1: 2}}                 # an int key comes back a string
        F.season_tables = lambda *a, **k: (f.worked.__setitem__("charting", f.worked["charting"] + 1), odd)[1]
        assert G.charting_tables(2026, 5, keep=True) == odd
        assert G.charting_tables(2026, 5, keep=True) == odd and f.worked["charting"] == 2
        assert not os.path.exists(os.path.join(os.environ["QB_MODELS_DIR"], "scan_charting_nfl_2026.json"))
    assert G._unpack_tables(json.loads(json.dumps(G._pack_tables(
        {"qbs": {("PHI", "J.Hurts"): {"attempts": 10, "iw_rate": 0.1}}, "partial": None})))) == \
        {"qbs": {("PHI", "J.Hurts"): {"attempts": 10, "iw_rate": 0.1}}, "partial": None}


def test_only_a_build_on_the_production_history_keeps():
    import inspect
    src = inspect.getsource(G.attach_nfl)
    assert "_keep = _lc.enabled_for(conn)" in src
    assert "charting_tables(season, week, keep=_keep), tracking_tables(season, week, keep=_keep)" in src
    from engine import logcache
    assert logcache.enabled_for(object()) is False, "the scan's tests pass conn=object(): never kept"


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
