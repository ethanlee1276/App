"""Camp watch: daily depth-chart snapshots diffed across the preseason.

Rules under test: snapshots only keep charted fantasy players; the diff
reports risers / fallers / new starters and ignores deep-chart churn and
cross-team moves (the roster-sync layer owns trades); one snapshot
reports "tracking started", never a league full of phantom movers; the
store prunes and survives same-day reruns.
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.preseason import (camp_movement, camp_report, depth_snapshot,
                              in_camp_window, record_snapshot)


def _p(name, team, pos, order, exp=3, active=True):
    return {"full_name": name, "team": team, "position": pos,
            "depth_chart_order": order, "years_exp": exp, "active": active,
            "status": "Active"}


BLOB_DAY1 = {
    "1": _p("Job Winner", "KC", "WR", 3, exp=0),
    "2": _p("Steady Starter", "KC", "QB", 1),
    "3": _p("Slipping Vet", "DAL", "RB", 1),
    "4": _p("Deep Churn", "DAL", "WR", 6),
    "5": _p("Chartless", "PIT", "TE", None),          # no slot — excluded
    "6": {"full_name": "Kicker Guy", "team": "KC", "position": "K",
          "depth_chart_order": 1, "years_exp": 2, "active": True},
}
BLOB_DAY5 = {
    "1": _p("Job Winner", "KC", "WR", 1, exp=0),      # WR3 -> WR1, rookie
    "2": _p("Steady Starter", "KC", "QB", 1),
    "3": _p("Slipping Vet", "DAL", "RB", 2),          # RB1 -> RB2
    "4": _p("Deep Churn", "DAL", "WR", 7),            # WR6 -> WR7: noise
    "7": _p("Traded In", "DAL", "WR", 1),             # not in day 1 — skip
}


def test_snapshot_keeps_only_charted_fantasy_players():
    snap = depth_snapshot(BLOB_DAY1)
    assert "Chartless" not in snap and "Kicker Guy" not in snap
    assert snap["Job Winner"] == {"team": "KC", "position": "WR",
                                  "order": 3, "rookie": True}


def test_movement_reports_jobs_won_and_lost_not_churn():
    store = {"2026-07-20": depth_snapshot(BLOB_DAY1),
             "2026-07-30": depth_snapshot(BLOB_DAY5)}
    mv = camp_movement(store)
    assert mv["from"] == "2026-07-20" and mv["to"] == "2026-07-30"
    assert [r["player"] for r in mv["new_starters"]] == ["Job Winner"]
    assert mv["new_starters"][0]["rookie"] is True
    assert [r["player"] for r in mv["fallers"]] == ["Slipping Vet"]
    # Deep-chart churn, unmoved starters, and new-to-team names all ignored.
    everyone = [r["player"] for rows in
                (mv["risers"], mv["fallers"], mv["new_starters"]) for r in rows]
    assert "Deep Churn" not in everyone and "Steady Starter" not in everyone
    assert "Traded In" not in everyone


def test_single_snapshot_says_tracking_started_not_phantom_movers():
    mv = camp_movement({"2026-07-30": depth_snapshot(BLOB_DAY1)})
    assert mv["days"] == 1 and mv["tracking_since"] == "2026-07-30"
    assert mv["risers"] == [] and mv["new_starters"] == []


def test_record_snapshot_overwrites_same_day_and_prunes():
    path = Path(tempfile.mkdtemp()) / "snaps.json"
    record_snapshot(BLOB_DAY1, "2026-04-01", path=path)     # beyond KEEP_DAYS
    record_snapshot(BLOB_DAY1, "2026-07-30", path=path)
    store = record_snapshot(BLOB_DAY5, "2026-07-30", path=path)  # same-day rerun
    assert sorted(store) == ["2026-07-30"]                  # pruned + overwritten
    assert store["2026-07-30"]["Job Winner"]["order"] == 1
    # An empty feed must not erase the history already collected.
    store = record_snapshot({}, "2026-07-31", path=path)
    assert "2026-07-30" in store and "2026-07-31" not in store


def test_camp_window_and_report_gate():
    assert in_camp_window("2026-08-06") and in_camp_window("2026-07-30")
    assert not in_camp_window("2026-10-01") and not in_camp_window("bogus")
    path = Path(tempfile.mkdtemp()) / "snaps.json"
    assert camp_report(None, "2026-08-06", path=path) is None
    assert camp_report(BLOB_DAY1, "2026-10-01", path=path) is None
    rep = camp_report(BLOB_DAY1, "2026-08-06", path=path)
    assert rep["window"] == "preseason" and rep["days"] == 1


# Runner at the TRUE END — a test defined after it never runs.
if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
