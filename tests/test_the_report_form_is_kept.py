"""The game reports' player form is kept between builds until the logs, the
players named or the NFL's schedule file change (engine/reportdata.player_form
through engine/logcache.memo).

The NFL build at 02:27 on 10 November: its game reports took 4.4 seconds,
3.5 of them the player form, the last games and season totals of every
player the reports name, read from the whole log table every build for
numbers that change only when a game is ingested. What these hold:

  * the kept form is exactly what the table answers (`_player_form`), for
    the NFL and for college;
  * a second build reads nothing; a new log row, another set of players or
    a changed schedule file reads it again;
  * a read that fails is never kept, and the reports get the answer they
    always got (`_player_form` answering {});
  * `_player_form` without ``strict`` still answers {} on a failed read.

Run directly: `python3 tests/test_the_report_form_is_kept.py`
"""
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db, logcache                                    # noqa: E402
from engine import reportdata as RD                                 # noqa: E402


def _row(sport, season, period, gid, player, team, market, value, opp="BBB", home=1):
    return {"sport": sport, "season": season, "period": period, "game_id": gid, "player": player,
            "team": team, "opponent": opp, "position": "WR", "home": home, "market": market,
            "value": value}


class _Kept:
    """A real history database in a scratch folder, the kept reads on."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.environ.get("QB_FEEDSTATE_DIR")
        os.environ["QB_FEEDSTATE_DIR"] = os.path.join(self.tmp.name, "feedstate")
        self.enabled, self.reads = logcache.enabled_for, []
        self.real = RD._player_form
        logcache.enabled_for = lambda c: True
        RD._player_form = lambda *a, **k: (self.reads.append(a[2] and sorted(a[2])), self.real(*a, **k))[1]
        self.conn = db.connect(os.path.join(self.tmp.name, "history.db"))
        rows = []
        for wk in range(1, 6):
            rows += [_row("nfl", 2026, f"{wk:03d}", f"AAA-{wk}", "Wide Out", "AAA", "rec_yds", 50.0 + wk),
                     _row("nfl", 2026, f"{wk:03d}", f"AAA-{wk}", "Wide Out", "AAA", "receptions", 4.0 + wk % 2),
                     _row("nfl", 2026, f"{wk:03d}", f"AAA-{wk}", "Run Back", "AAA", "rush_yds", 70.0 + wk),
                     _row("nfl", 2026, f"{wk:03d}", f"AAA-{wk}", "W.Out", "AAA", "rz_tgt", 1.0)]
        rows += [_row("nfl", 2025, f"{wk:03d}", f"CCC-{wk}", "Old Hand", "CCC", "rec_yds", 30.0 + wk)
                 for wk in range(1, 4)]
        rows += [_row("cfb", 2026, f"2026-10-{d:02d}", f"g{d}", "College Back", "IU", "rush_yds", 90.0 + d,
                      opp="PUR", home=d % 2) for d in (3, 10, 17)]
        rows += [_row("cfb", 2026, f"2026-10-{d:02d}", f"g{d}", "College Back", "IU", "rz_car", 3.0, opp="PUR")
                 for d in (3, 10, 17)]
        db.upsert_player_logs(self.conn, rows)
        self.conn.commit()
        self.sched = Path(self.tmp.name) / "games.csv"
        self.sched.write_text("season,week,game_type,gameday,home_team,away_team,home_score,away_score,"
                              "location,spread_line,total_line\n"
                              "2026,5,REG,2026-10-05,BBB,AAA,20,24,Home,3.0,44.5\n", encoding="utf-8")
        return self

    def __exit__(self, *exc):
        RD._player_form, logcache.enabled_for = self.real, self.enabled
        self.conn.close()
        if self.old is None:
            os.environ.pop("QB_FEEDSTATE_DIR", None)
        else:
            os.environ["QB_FEEDSTATE_DIR"] = self.old
        self.tmp.cleanup()


NFL = {"Wide Out": "AAA", "Run Back": "AAA", "Old Hand": "CCC"}


def test_the_kept_form_is_what_the_table_answers_for_both_leagues():
    with _Kept() as k:
        nfl = RD.player_form(k.conn, 2026, NFL, sport="nfl", schedule=str(k.sched))
        plain = k.real(k.conn, 2026, NFL, "nfl", str(k.sched))
        cfb = RD.player_form(k.conn, 2026, {"College Back": "IU"}, sport="cfb")
        cfb_plain = k.real(k.conn, 2026, {"College Back": "IU"}, "cfb", None)
    assert nfl == plain and set(nfl) == {"Wide Out", "Run Back", "Old Hand"}, nfl
    assert nfl["Wide Out"]["season"]["games"] == 5 and nfl["Old Hand"].get("last_season")
    assert nfl["Wide Out"]["games"][0]["where"] == "away", "the venue off the schedule file"
    assert cfb == cfb_plain and cfb["College Back"]["rz"]["rz_car"] == 9.0, cfb


def test_a_second_build_reads_nothing_and_a_change_reads_again():
    with _Kept() as k:
        first = RD.player_form(k.conn, 2026, NFL, sport="nfl", schedule=str(k.sched))
        again = RD.player_form(k.conn, 2026, NFL, sport="nfl", schedule=str(k.sched))
        note = logcache.status()["report_form.nfl"]
        assert len(k.reads) == 1 and again == first and note["kept"] is True, (k.reads, note)
        db.upsert_player_logs(k.conn, [_row("nfl", 2026, "006", "AAA-6", "Wide Out", "AAA", "rec_yds", 99.0)])
        k.conn.commit()
        moved = RD.player_form(k.conn, 2026, NFL, sport="nfl", schedule=str(k.sched))
        note = logcache.status()["report_form.nfl"]
        assert len(k.reads) == 2 and note["kept"] is False and note["why"] == "rows changed", note
        assert moved["Wide Out"]["season"]["games"] == 6
        fewer = RD.player_form(k.conn, 2026, {"Wide Out": "AAA"}, sport="nfl", schedule=str(k.sched))
        assert len(k.reads) == 3 and set(fewer) == {"Wide Out"}, "another set of players is read again"
        RD.player_form(k.conn, 2026, {"Wide Out": "AAA"}, sport="nfl", schedule=str(k.sched))
        assert len(k.reads) == 3
        time.sleep(0.01)
        k.sched.write_text(k.sched.read_text(encoding="utf-8").replace("Home", "Neutral"), encoding="utf-8")
        os.utime(k.sched, (time.time() + 5, time.time() + 5))
        venue = RD.player_form(k.conn, 2026, {"Wide Out": "AAA"}, sport="nfl", schedule=str(k.sched))
        assert len(k.reads) == 4, "a changed schedule file is read again"
        assert venue["Wide Out"]["games"][1]["where"] == "neutral", venue["Wide Out"]["games"]


def test_a_failed_read_is_never_kept():
    with _Kept() as k:
        broke = {"on": True}
        real = k.real

        def flaky(conn, season, players, sport="nfl", schedule=None, strict=False):
            if broke["on"]:
                if strict:
                    raise sqlite3.OperationalError("database is locked")
                return {}
            return real(conn, season, players, sport, schedule, strict=strict)
        RD._player_form = flaky
        got = RD.player_form(k.conn, 2026, NFL, sport="nfl", schedule=str(k.sched))
        assert got == {}, "the answer the reports always got on a failed read"
        assert logcache.status().get("report_form.nfl", {}).get("kept") is not True
        broke["on"] = False
        whole = RD.player_form(k.conn, 2026, NFL, sport="nfl", schedule=str(k.sched))
        assert whole == real(k.conn, 2026, NFL, "nfl", str(k.sched)), "nothing was kept from the failure"


def test_the_plain_read_still_answers_nothing_on_a_failed_read():
    conn = sqlite3.connect(":memory:")
    assert RD._player_form(conn, 2026, NFL, "nfl") == {}, "no table: an empty answer, as before"
    try:
        RD._player_form(conn, 2026, NFL, "nfl", strict=True)
    except sqlite3.OperationalError:
        pass
    else:
        raise AssertionError("strict lets the failure through")
    assert RD.player_form(None, 2026, NFL) == {} and RD.player_form(conn, 2026, {}) == {}


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
