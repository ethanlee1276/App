"""A college receiver thrown at who caught nothing is a zero, not a missing game.

Ethan, 2026-10-13: "We worked so hard on nfl so ik CFB and mlb and nba
and ufc is missing stuff." The college play file names the intended
receiver on 78% of 2025's incompletions and 92% of 2026's (21% of 2024's,
when the parser was written and decided college had no targets). A named
target proves he was thrown at, so engine/sources/cfbstats now writes
his receiving zeros (ZERO_WHEN keyed on `targets`), and measured on the
board's own population (cfbtargetfit.py) that lowers the squared error of
the board's form in 2025 and 2026, for catches and for yards.

Pinned here, offline:

  * a catch is a target, and a named incompletion or interception is one;
  * ``targets=False`` is the old logs exactly — the measurement's other arm;
  * a target named the same as the passer is a shape the row cannot
    resolve, and is left alone;
  * no target COUNT is ever written (short where the feed leaves an
    incompletion unnamed);
  * the college reader splits lines rather than holding a StringIO;
  * the measurement runs on rows handed to it, and keeps its bar and its
    result in its docstring.

Run directly: `python3 tests/test_college_receivers_thrown_at.py`
"""
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.sources import cfbstats as C       # noqa: E402

GAMES = {"401": {"period": "2026-09-12", "home": "UGA", "away": "OSU",
                 "home_name": "Georgia", "away_name": "Ohio State"}}


def _play(**kw):
    row = {"game_id": "401", "season": "2026", "week": "3", "team": "Georgia",
           "opponent": "Ohio State", "yards_to_goal": "40", "down": "1", "distance": "10"}
    row.update(kw)
    return row


def _value(out, player, market):
    return next((r["value"] for r in out["rows"]
                 if r["player"] == player and r["market"] == market), None)


def test_a_catch_and_a_named_miss_are_both_targets_and_only_the_named_miss_is_new():
    rows = [_play(completion_player="QB", completion_yds="0", reception_player="Tight End",
                  reception_yds="0"),
            _play(incompletion_player="QB", target_player="Slot WR", target_player_id="99"),
            _play(interception_thrown_player="QB", target_player="Slot WR")]
    new = C.parse_player_stats(rows, 2026, GAMES)
    old = C.parse_player_stats(rows, 2026, GAMES, targets=False)
    # The tight end's 0-yard catch wrote a yards zero before and still does.
    for out in (new, old):
        assert _value(out, "Tight End", "receptions") == 1
        assert _value(out, "Tight End", "rec_yds") == 0
    # The slot receiver thrown at twice is a zero now and absent before.
    for market in ("receptions", "rec_yds", "rec_td", "anytime_td"):
        assert _value(new, "Slot WR", market) == 0, market
        assert _value(old, "Slot WR", market) is None, market
    # The passer's attempts are the same either way: the target only names
    # who it was thrown at.
    assert _value(new, "QB", "pass_att") == _value(old, "QB", "pass_att") == 3
    assert not any(r["market"] == "targets" for r in new["rows"])


def test_old_logs_are_reproduced_exactly_when_targets_are_off():
    rows = [_play(rush_player="Back", rush_yds="4"),
            _play(completion_player="QB", completion_yds="12", reception_player="Wide Out",
                  reception_yds="12"),
            _play(incompletion_player="QB", target_player="Wide Out"),
            _play(incompletion_player="QB", target_player="Other WR")]
    old = C.parse_player_stats(rows, 2026, GAMES, targets=False)
    new = C.parse_player_stats(rows, 2026, GAMES)
    key = lambda out: sorted((r["player"], r["market"], r["value"]) for r in out["rows"])
    added = set(key(new)) - set(key(old))
    # Everything the old logs wrote is still written, unchanged; the only
    # additions are the never-caught receiver's zeros.
    assert set(key(old)) <= set(key(new))
    assert added == {("Other WR", m, 0.0) for m in ("anytime_td", "receptions", "rec_yds", "rec_td")}


def test_a_target_named_as_the_passer_is_left_alone():
    out = C.parse_player_stats([_play(incompletion_player="QB", target_player="QB")], 2026, GAMES)
    assert _value(out, "QB", "receptions") is None
    assert _value(out, "QB", "pass_att") == 1


def test_the_college_reader_splits_lines_rather_than_holding_a_stringio():
    src = inspect.getsource(C._stream)
    assert "splitlines(keepends=True)" in src and "StringIO(" not in src.split('"""')[-1]


def test_the_measurement_runs_on_rows_handed_to_it_and_says_its_bar():
    import cfbtargetfit as F

    def season_rows(season):
        out = []
        weeks = ([(1, 3), (2, 4), (3, 3), (4, 2)] if season == 2025
                 else [(1, 3), (2, 4), (3, 0), (4, 5), (5, 3)])
        for week, catches in weeks:
            gid = f"{season}{week:02d}"
            base = {"game_id": gid, "season": str(season), "week": str(week), "team": "Georgia",
                    "opponent": "Ohio State", "yards_to_goal": "40"}
            for _ in range(catches):
                out.append({**base, "completion_player": "QB", "completion_yds": "9",
                            "reception_player": "Wide Out", "reception_yds": "9"})
            if not catches:
                out += [{**base, "incompletion_player": "QB", "target_player": "Wide Out"}] * 2
            out.append({**base, "rush_player": "Back", "rush_yds": "3"})
        return out

    keep = F._rows
    F._rows = season_rows
    try:
        lines = F.table((2026,))
    finally:
        F._rows = keep
    assert lines[0].startswith("season") and lines[-1].startswith("THE BAR")
    rec = next(ln for ln in lines if " receptions " in ln)
    # Week 3 (thrown at twice, no catch) is scored, and it is a thrown-at
    # zero the old logs could not see.
    assert rec.split()[-1] == "1", rec
    doc = F.__doc__
    assert "THE BAR, set before the first run" in doc and "MET" in doc
    for fact in ("14,234", "3.775", "3.765", "4,209", "-1.8%"):
        assert fact in doc, fact


def test_the_box_check_counts_the_voids_the_play_file_now_explains_and_regrades_nothing():
    import shutil
    import tempfile
    import cfbzeros
    from engine import db as D, ledger as L
    tmp = tempfile.mkdtemp()
    try:
        h = D.connect(Path(tmp) / "history.db")
        D.upsert_player_logs(h, [
            {"sport": "cfb", "season": 2026, "period": "2026-09-12", "game_id": "401",
             "player": "Slot WR", "team": "UGA", "opponent": "OSU", "position": "WR", "home": 1,
             "market": "receptions", "value": 0.0},
            {"sport": "cfb", "season": 2026, "period": "2026-09-13", "game_id": "402",
             "player": "Deep WR", "team": "UGA", "opponent": "OSU", "position": "WR", "home": 1,
             "market": "receptions", "value": 0.0},
            # A box row with a zero proves nothing about the play file.
            {"sport": "cfb", "season": 2026, "period": "2026-09-12", "game_id": "401-box",
             "player": "Box WR", "team": "UGA", "opponent": "OSU", "position": "WR", "home": 1,
             "market": "receptions", "value": 0.0}])
        h.commit()
        led = L.connect(Path(tmp) / "ledger.db")
        for player, side, odds, stake in (("Slot WR", "OVER", -120, 1.0),
                                          ("Deep WR", "UNDER", 150, 0.5),
                                          ("Box WR", "OVER", -110, 1.0),
                                          ("Scratched WR", "OVER", -110, 1.0)):
            led.execute("INSERT INTO bets (sport, date, player, market, side, line, odds, "
                        "stake_units, status) VALUES ('cfb', '2026-09-12', ?, 'receptions', ?, 2.5, "
                        "?, ?, 'void')", (player, side, odds, stake))
        led.commit()
        v = cfbzeros.voids(led, h)
        assert v["voided"] == 4 and v["thrown_at"] == 2
        assert v["over_lost"] == 1 and v["under_won"] == 1
        assert abs(v["units_if_graded"] - (-1.0 + 0.75)) < 1e-9
        lines = cfbzeros.check(led, h)
        assert lines[0] == "CFB  2026: 2 receiver-games thrown at with no catch, on the record as 0"
        assert "2 of them the play file has as thrown at" in lines[1]
        assert "(nothing is regraded)" in lines[2]
        # Nothing was regraded: every bet is still void.
        assert {r[0] for r in led.execute("SELECT status FROM bets")} == {"void"}
        led.close()
        h.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    src = (ROOT / "cfbzeros.py").read_text(encoding="utf-8")
    assert '"--fill" in argv' in src and "mode=ro" in src, "the check is read-only unless asked to fill"


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
