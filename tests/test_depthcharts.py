"""Tests for the depth-chart adapter (offline, fixture-driven)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.sources import depthcharts as dc
from engine.injuries import evaluate_injuries
from engine.models import Injury, Prop, GameLog, SportsbookLine, REC_YDS


def _row(name, team, dp, rank, week=5):
    return {"season": "2024", "week": str(week), "club_code": team,
            "full_name": name, "depth_position": dp, "depth_team": str(rank),
            "position": dp}


ROWS = [
    _row("Big Tackle", "KC", "LT", 1),
    _row("Nickel Guy", "BUF", "NB", 1),
    _row("Boundary One", "BUF", "LCB", 1),
    _row("Backup Corner", "KC", "RCB", 2),
    _row("Last Week LT", "KC", "LT", 1, week=4),
]


def test_index_keeps_best_rank():
    rows = ROWS + [_row("Big Tackle", "KC", "LT", 3)]  # extra formation listing
    idx = dc.index_for_week(rows, 5)
    assert idx[("KC", "big tackle")] == ("LT", 1)
    # wrong-week rows are excluded
    assert ("KC", "last week lt") not in idx


def test_refine_starter_roles():
    injuries = [
        Injury("Big Tackle", "KC", "T", "OT", "OUT"),        # generic OT -> LT
        Injury("Nickel Guy", "BUF", "CB", "cb1", "OUT"),      # boundary -> slot
        Injury("Boundary One", "BUF", "CB", "cb1", "OUT"),    # stays cb1
    ]
    res = dc.refine_injury_roles(injuries, ROWS, 5)
    assert injuries[0].role == "LT"
    assert injuries[1].role == "slot_cb"
    assert injuries[2].role == "cb1"
    assert res.refined == 2 and res.demoted == 0


def test_backup_demoted_and_knockon_cancelled():
    injuries = [Injury("Backup Corner", "KC", "CB", "cb1", "OUT")]
    res = dc.refine_injury_roles(injuries, ROWS, 5)
    assert res.demoted == 1
    assert injuries[0].role == "depth_cb1"

    # A demoted backup CB no longer boosts the opposing receiver.
    prop = Prop("WR X", "BUF", "KC", "WR", REC_YDS,
                [GameLog(w, "X", 60) for w in range(1, 5)], 58, None,
                [SportsbookLine("proxy", 55.0)], "wr1")
    effect = evaluate_injuries(prop, injuries)
    assert effect.multiplier == 1.0


def test_starter_slot_cb_triggers_slot_knockon():
    injuries = [Injury("Nickel Guy", "BUF", "CB", "cb1", "OUT")]
    dc.refine_injury_roles(injuries, ROWS, 5)
    prop = Prop("Slot WR", "KC", "BUF", "WR", REC_YDS,
                [GameLog(w, "X", 55) for w in range(1, 5)], 52, None,
                [SportsbookLine("proxy", 50.0)], "slot")
    effect = evaluate_injuries(prop, injuries)
    assert effect.multiplier > 1.0
    assert any("slot" in r.lower() for r in effect.reasons)


# ---------------------------------------------------------------------------
# The 2025/2026 nflverse schema (NFL readiness audit, 2026-09-02).
#
# The release is keyed by a snapshot date `dt` and speaks `team /
# player_name / pos_abb / pos_rank`. The adapter read only the legacy
# `week / club_code / full_name / depth_position / depth_team` names and
# so returned NOTHING for every current-season chart — the QB-dependency
# watch and the knock-on refinement were silently off. These pin the
# second spelling, with the shape of the real 2026 file.
# ---------------------------------------------------------------------------

def _nrow(name, team, pos, rank, dt="2026-09-02"):
    return {"season": "2026", "dt": dt + "T14:05:00Z", "team": team,
            "player_name": name, "pos_abb": pos, "pos_rank": str(rank),
            "pos_grp": "offense", "pos_name": pos}


NEW_ROWS = [
    _nrow("Jacoby Brissett", "ARI", "QB", 1),
    _nrow("Kyler Murray", "ARI", "QB", 2),
    _nrow("Tua Tagovailoa", "ATL", "QB", 1),
    _nrow("Big Tackle", "KC", "LT", 1),
    _nrow("Backup Corner", "KC", "RCB", 2),
    # last week's snapshot: Murray was the starter, and the tackle too
    _nrow("Kyler Murray", "ARI", "QB", 1, dt="2026-08-26"),
    _nrow("Jacoby Brissett", "ARI", "QB", 2, dt="2026-08-26"),
    _nrow("Tua Tagovailoa", "ATL", "QB", 1, dt="2026-08-26"),
    _nrow("Big Tackle", "KC", "LT", 1, dt="2026-08-26"),
]


def test_the_current_nflverse_schema_is_read_at_all():
    """Before the fix this was an empty dict for the real 2026 file."""
    idx = dc.index_for_week(NEW_ROWS, 1)
    assert idx, "date-keyed rows produced no index"
    assert idx[("KC", "big tackle")] == ("LT", 1)
    assert idx[("KC", "backup corner")] == ("RCB", 2)


def test_the_latest_snapshot_answers_for_this_week():
    qb1 = dc.qb1_map(NEW_ROWS, 1)
    assert qb1 == {"ARI": "Jacoby Brissett", "ATL": "Tua Tagovailoa"}


def test_the_snapshot_a_week_back_answers_for_last_week():
    prev = dc.qb1_map(NEW_ROWS, 1, back_days=7)
    assert prev["ARI"] == "Kyler Murray"
    # Nothing at least seven days older than the only snapshot -> nothing,
    # not the current snapshot mislabelled as last week.
    only_now = [r for r in NEW_ROWS if r["dt"].startswith("2026-09-02")]
    assert dc.qb1_map(only_now, 1, back_days=7) == {}


def test_a_qb1_change_between_snapshots_fires_the_dependency_note():
    notes = dc.qb_dependency(NEW_ROWS, 2, [])
    assert "ARI" in notes and "Jacoby Brissett" in notes["ARI"]
    assert "Kyler Murray" in notes["ARI"]
    assert "ATL" not in notes


def test_the_legacy_week_keyed_schema_still_works():
    """The old spelling is not dropped for the new one."""
    assert dc.qb1_map(ROWS + [_row("Old QB", "KC", "QB", 1)], 5) == {"KC": "Old QB"}
    # a legacy file with rows for the asked week only
    assert ("KC", "last week lt") in dc.index_for_week(ROWS, 4)


def test_new_schema_backups_are_still_demoted():
    injuries = [Injury("Backup Corner", "KC", "CB", "cb1", "OUT"),
                Injury("Big Tackle", "KC", "T", "OT", "OUT")]
    res = dc.refine_injury_roles(injuries, NEW_ROWS, 1)
    assert injuries[0].role == "depth_cb1"
    assert injuries[1].role == "LT"
    assert res.demoted == 1 and res.refined == 1


# --- the load is slimmed to what this module reads (2026-09-02) -------------
def test_slim_rows_keeps_only_the_columns_the_readers_use():
    from engine.sources import depthcharts as D
    csv = ("dt,team,player_name,espn_id,gsis_id,pos_grp,pos_abb,pos_rank\n"
           "2026-09-02,DET,Jared Goff,1,00-1,QB,QB,1\n")
    rows = D.slim_rows(csv, 21)
    assert rows == [{"dt": "2026-09-02", "team": "DET", "player_name": "Jared Goff",
                     "pos_abb": "QB", "pos_rank": "1"}]
    for c in ("espn_id", "gsis_id", "pos_grp"):
        assert c not in rows[0]


def test_slim_rows_keeps_the_newest_snapshots_and_the_week_back_one():
    """`qb1_map(week - 1, back_days=7)` needs a snapshot at least seven
    days older than the newest; the cut keeps three weeks, not one day."""
    from engine.sources import depthcharts as D
    csv = ("dt,team,player_name,pos_abb,pos_rank\n"
           "2026-03-22,DET,Spring Guy,QB,1\n"
           "2026-08-20,DET,Camp Guy,QB,1\n"
           "2026-09-02,DET,Week One,QB,1\n")
    rows = D.slim_rows(csv, 21)
    assert [r["player_name"] for r in rows] == ["Camp Guy", "Week One"]
    # and the readers see the same answers they always did
    assert D.qb1_map(rows, 1) == {"DET": "Week One"}
    assert D.qb1_map(rows, 1, back_days=7) == {"DET": "Camp Guy"}


def test_slim_rows_keeps_every_week_of_the_legacy_schema():
    from engine.sources import depthcharts as D
    csv = ("week,club_code,full_name,depth_position,depth_team,jersey_number\n"
           "1,DET,A,QB,1,16\n2,DET,B,QB,1,16\n18,DET,C,QB,1,16\n")
    rows = D.slim_rows(csv, 21)
    assert [r["week"] for r in rows] == ["1", "2", "18"]
    assert "jersey_number" not in rows[0]
    assert D.qb1_map(rows, 18) == {"DET": "C"}


def test_the_loader_streams_through_slim_rows_not_fetch_csv():
    """The 2026 file is 492,320 rows; fetch_csv into a list was 550 MB of
    dicts held for the whole build for one day's six columns."""
    import inspect
    from engine.sources import depthcharts as D
    src = inspect.getsource(D.load_depth_charts)
    # the fetch only refreshes the cache; the rows stream off the file
    assert "fetch_text(url, local.name)" in src and "fetch_csv(" not in src
    assert "_slim(lambda: open(local" in src
    assert D.KEEP_DAYS >= 14
    for key in ("dt", "week", "team", "club_code", "player_name", "full_name",
                "player_display_name", "depth_position", "position", "pos_abb",
                "depth_team", "depth", "pos_rank"):
        assert key in D.KEEP_COLUMNS, key


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
