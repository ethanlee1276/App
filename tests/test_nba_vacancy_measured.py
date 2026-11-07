"""When a regular sits, is the NBA board's number for his teammates off? Measured on the box.

Ethan, 2026-10-13: "ik CFB and mlb and nba and ufc is missing stuff." The
NBA build now reads the injury board and holds a ruled-out man, but the
minutes model's vacancy slot (`project_minutes(vacancy_minutes=...)`) is
empty, so a teammate's number does not move when the star sits — while
the books raise that teammate's line. nbavacancy.py replays every stored
season with the board's own projection and splits the teammates' games
into fresh-absence and normal ones, against a bar written before the
first run. Pinned here, offline, on synthetic games:

  * a team whose regular sits three games shows its teammates above the
    projection in exactly those games, and nowhere else;
  * the player memory is held at 1.0 during the replay and restored;
  * the check opens the database read-only and keeps its bar in its
    docstring.

Run directly: `python3 tests/test_nba_vacancy_measured.py`
"""
import datetime
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

import nbavacancy as V                                   # noqa: E402
from engine import db as D                               # noqa: E402


def _clubs(sits=range(20, 25), seasons=(2024, 2025)):
    conn = D.connect(":memory:")
    rows = []
    for season in seasons:
        d0 = datetime.date(season, 11, 1)
        for i in range(40):
            d = (d0 + datetime.timedelta(days=2 * i)).isoformat()
            out = i in sits
            for name, m, pts, starter in (("Star", 34, 28, True),
                                          ("Wing", 36 if out else 30, 20 if out else 15, True),
                                          ("Big", 30 if out else 28, 12, True),
                                          ("Bench", 18, 7, False)):
                if name == "Star" and out:
                    continue
                for mk, v in (("min", m), ("pts", pts), ("reb", 5), ("ast", 3), ("fg3m", 1)):
                    rows.append({"sport": "nba", "season": season, "period": d,
                                 "game_id": f"g{season}{i}", "player": name, "team": "BOS",
                                 "opponent": "MIA", "position": "S" if starter else "B",
                                 "home": 1, "market": mk, "value": float(v)})
    D.upsert_player_logs(conn, rows)
    return V.load(conn, "nba")


def test_teammates_run_above_the_number_only_in_the_games_a_regular_sat():
    res = V.replay(_clubs(), "nba")
    for season in (2024, 2025):
        by = res[season]
        # Three fresh-absence games: the first three he sat (the fourth is
        # already in everyone's recent games).
        assert by["games"]["absence"] == 3, by["games"]
        m, ci, _n = V._mean_ci(by["absence"]["min"])
        assert m > V.BAR_MINUTES and m - ci > 0, (m, ci)
        p, pci, _pn = V._mean_ci(by["absence"]["pts"])
        assert p - pci > 0
        nm, _nci, _nn = V._mean_ci(by["normal"]["min"])
        assert abs(nm) < 0.5, nm
    met, why = V.verdict(res)
    assert met and not why
    lines = V.report(res, "nba")
    assert lines[-2].startswith("THE BAR (set before the first run)") and "MET" in lines[-2]
    assert "Nothing is changed by this run" in lines[-1]


def test_a_team_nobody_sat_on_has_nothing_to_measure_and_says_so():
    res = V.replay(_clubs(sits=()), "nba")
    met, why = V.verdict(res)
    assert not met and why == ["no season has fresh-absence games to measure"]
    assert "NOT MET" in V.report(res, "nba")[-2]


def test_the_player_memory_is_held_neutral_during_the_replay_and_restored():
    from engine import playerfit
    keep = playerfit.mult_for
    seen = []

    def mine(*a, **k):
        seen.append(a)
        return 1.5
    playerfit.mult_for = mine
    try:
        res = V.replay(_clubs(), "nba")
        assert playerfit.mult_for is mine, "the replay did not put the memory back"
        assert not seen, "the replay read a memory fitted after these games"
    finally:
        playerfit.mult_for = keep
    assert res[2024]["games"]["normal"] > 0


def test_the_check_is_read_only_and_keeps_its_bar():
    src = open(os.path.join(ROOT, "nbavacancy.py"), encoding="utf-8").read()
    assert "mode=ro" in src and "db.connect(" not in src
    doc = V.__doc__
    assert "THE BAR, set before the first run" in doc
    assert "changes nothing" in doc


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
