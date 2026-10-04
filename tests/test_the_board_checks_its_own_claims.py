"""Every build checks the claims its board makes against its own data.

Ethan, 2026-09-25: "what's next so we can keep working and making sure all
that shit is good." Two wrong claims had reached his phone that day before
anything caught them (a +700 longshot called McConkey's "likeliest over";
prices read an hour late still "priced 4m ago"). engine/boardtruth reads
each board after its build (launch._board_truth); the counts go to the
heartbeat and the Status page, the detail to the build log.
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import boardtruth as T                               # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _row(**kw):
    r = {"player": "A", "market": "rec_yds", "side": "over", "line": 40.5, "odds": -150,
         "model_prob": 0.62, "price_age_s": 600}
    r.update(kw)
    return r


def _clean():
    return {"most_likely": [_row(), _row(player="B", locked=True, now_listed=True, model_prob=0.5,
                                         lock_note="Our chance at this number is now 50%, down from 61%")],
            "scan_reads": {"X@Y": {"players": [
                {"player": "A", "pick": {"side": "over", "line": 40.5, "market": "rec_yds"},
                 "pro": ["Keenan Allen (WR) is out — 21% of the targets (6.1 a game) to go around"]},
                {"player": "C", "no_pick": {"best": {"side": "over", "line": 45.5, "market": "rec_yds",
                                                     "odds": -115, "model_prob": 0.41}}}]}},
            "data_freshness": {"played": 3, "behind": []}}


def test_a_clean_board_holds():
    rep = T.check(_clean())
    assert rep["count"] == 0, rep
    assert rep["checked"] == 5
    assert T.line("NFL", rep) == "NFL self-check: 5 claims, all hold."


def test_every_check_fires_on_its_own_case():
    b = _clean()
    b["most_likely"] += [
        _row(player="Low", model_prob=0.51),                                   # FLOOR
        _row(player="Chalk", odds=-300),                                       # CAP
        _row(player="Old", price_age_s=49 * 3600),                             # OLD PRICE
        # Between the 6h bar and the 48h ceiling the page itself says "may
        # have moved" (app.js priceAgeChip): not a problem to report.
        _row(player="Aging", price_age_s=8 * 3600),
        _row(player="Lk", locked=True),                                        # NO NOW
        _row(player="Note", locked=True, now_listed=False, model_prob=0.47,
             lock_note="Our chance at this number is now 44%, down from 60%"),  # LOCK NOTE
    ]
    b["most_likely"].append(_row(player="Res", reserve=True, model_prob=0.40))
    players = b["scan_reads"]["X@Y"]["players"]
    players.append({"player": "Gone", "pick": {"side": "over", "line": 9.5, "market": "rush_yds"}})
    players.append({"player": "McConkey", "no_pick": {"best": {"side": "over", "line": 109.5,
                                                               "market": "rec_yds", "odds": 700,
                                                               "model_prob": 0.04}}})
    players.append({"player": "D", "notes": ["David Njoku is out — his targets are open"]})
    b["data_freshness"] = {"played": 3, "behind": ["unit ratings"]}
    rep = T.check(b)
    assert rep["by_check"] == {"FLOOR": 1, "CAP": 1, "OLD PRICE": 1, "NO NOW": 1, "LOCK NOTE": 1,
                               "PICK MISSING": 1, "LONGSHOT": 1, "BARE MATE": 1, "DATA BEHIND": 1}, rep
    assert len(rep["problems"]) == T.KEEP and rep["count"] == 9
    assert "9 of" in T.line("NFL", rep) and "LONGSHOT 1" in T.line("NFL", rep)


def test_the_launcher_runs_it_and_the_heartbeat_gets_counts_only():
    import launch
    path = os.path.join(tempfile.mkdtemp(), "b.json")
    b = _clean()
    b["most_likely"].append(_row(player="Low", model_prob=0.51))
    with open(path, "w") as fh:
        json.dump(b, fh)
    real = launch._full_copy
    launch._full_copy = lambda p: p
    try:
        got = launch._board_truth("nfl", path)
    finally:
        launch._full_copy = real
    assert got == {"checked": 6, "count": 1, "by_check": {"FLOOR": 1}}, got
    assert "problems" not in got, "the heartbeat is public; the detail names picks"
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    assert '_BOARD_RUNS[name]["truth"] = _board_truth(name, BOARD_FILES[name])' in src


def test_the_status_page_shows_it():
    assert "truthRowHTML(r.truth, sub)" in APP
    for k in ("FLOOR", "CAP", "OLD PRICE", "NO NOW", "LOCK NOTE", "PICK MISSING", "LONGSHOT",
              "BARE MATE", "DATA BEHIND"):
        assert f'"{k}":' in APP[APP.index("const TRUTH_WORDS"):APP.index("function truthRowHTML")], k


def test_the_full_copy_answers_after_a_restart_seals_the_public_one():
    """2026-09-25: three restarts in eight minutes, each one re-sealing the
    public copy (gate.seal), and on a one-second window the full copy read
    as stale every time — so the self-check, and every probe on the box,
    read the paywalled copy: no picks, "all claims hold". The window is
    now minutes; a full copy hours older than the public one is still
    refused, since only a writer that bypassed publish leaves one."""
    import launch
    from engine import gate
    d = tempfile.mkdtemp()
    public = os.path.join(d, "recommendations.json")
    full = os.path.join(d, "built", "recommendations.json")
    os.makedirs(os.path.dirname(full))
    for path in (public, full):
        with open(path, "w") as fh:
            json.dump({}, fh)
    real = gate.full_board_file
    gate.full_board_file = lambda name: __import__("pathlib").Path(full)
    try:
        now = 1_800_000_000
        os.utime(public, (now, now))
        os.utime(full, (now - 300, now - 300))
        assert launch._full_copy(public) == full, "five minutes behind the seal is the same board"
        os.utime(full, (now - 3 * 3600, now - 3 * 3600))
        assert launch._full_copy(public) == public, "hours behind is a bypassed publish"
    finally:
        gate.full_board_file = real
    assert launch.FULL_COPY_LAG_S >= 300


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
