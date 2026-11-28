"""The comps' index reads this season's rows alone on a night (step AEP, 24 November 2026).

A comps market's index (engine/comps: every past player-game with his form over the ten games before it) is read
off the whole history, and it was kept on every season at once, so a night's new box scores read every season
again: college basketball's four comps markets took 9.0 to 11.8 seconds each at 18:46 that evening, about 40
seconds of a 416-second build. Each season's spots are now kept on their own with what each player carries out of
the season (his last ten values and his games so far), so:

  * the index is the whole read's, spot for spot and in the same order (players across seasons, a player's form
    carried over a season's turn, a man with too few games, two games on one day, rows with no value);
  * a night's rows in this season read this season's rows again and no earlier season;
  * a change in an earlier season reads that season and every one after it again, since their form carries;
  * a sport with rows filed under no season is read whole, as before.

Offline. Run directly: `python3 tests/test_comps_read_this_season_alone.py`
"""
import os
import random
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import comps as C, db, logcache                         # noqa: E402


class _Sandbox:
    """A history file and a feedstate directory of the test's own, with the cache switched on for that file."""

    def __enter__(self):
        self.dir = tempfile.mkdtemp()
        self.keep = os.environ.get("QB_FEEDSTATE_DIR")
        os.environ["QB_FEEDSTATE_DIR"] = os.path.join(self.dir, "feedstate")
        self.conn = db.connect(os.path.join(self.dir, "history.db"))
        self.enabled = logcache.enabled_for
        logcache.enabled_for = lambda conn: True
        return self

    def __exit__(self, *exc):
        logcache.enabled_for = self.enabled
        self.conn.close()
        if self.keep is None:
            os.environ.pop("QB_FEEDSTATE_DIR", None)
        else:
            os.environ["QB_FEEDSTATE_DIR"] = self.keep
        shutil.rmtree(self.dir, ignore_errors=True)


def _row(season, day, game, player, value, market="pts"):
    return {"sport": "cbb", "season": season, "period": day, "game_id": game, "player": player, "team": "T",
            "opponent": "U", "position": "G", "home": 1, "market": market, "value": value}


def _history(conn, seed=11):
    """Three seasons; most men play all three, one only the last, one too few games for a form; a doubleheader."""
    rnd = random.Random(seed)
    rows = []
    for season, nights in ((2024, 14), (2025, 14), (2026, 6)):
        for k in range(nights):
            day = f"{season}-11-{k + 1:02d}"
            for p in range(6):
                if p == 5 and season != 2026:
                    continue                                      # a freshman: this season only
                rows.append(_row(season, day, f"g{season}-{k}", f"Player {p}", float(rnd.randint(0, 30))))
            rows.append(_row(season, day, f"g{season}-{k}", "Player 0", float(k), market="reb"))
    rows += [_row(2026, "2026-11-03", "g-dh-2", "Player 1", 31.0), _row(2026, "2026-11-03", "g-dh-1", "Player 1", 2.0),
             _row(2025, "2025-11-01", "g-short", "Seldom Used", 4.0), _row(2026, "2026-11-02", "g-none", "Player 2", None)]
    db.upsert_player_logs(conn, [r for r in rows if r["value"] is not None])
    conn.execute("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, position, "
                 "home, market, value) VALUES ('cbb', 2026, '2026-11-02', 'g-none', 'Player 2', 'T', 'U', 'G', 1, "
                 "'pts', NULL)")
    conn.commit()


def _counting():
    calls = []
    was = C._season_spots

    def wrapped(conn, sport, market, season, carry, *a, **kw):
        calls.append(season)
        return was(conn, sport, market, season, carry, *a, **kw)
    C._season_spots = wrapped
    return calls, lambda: setattr(C, "_season_spots", was)


def test_the_index_is_the_whole_reads_spot_for_spot():
    with _Sandbox() as sb:
        _history(sb.conn)
        whole = C.spot_index(sb.conn, "cbb", "pts")
        assert C.season_spots(sb.conn, "cbb", "pts") == whole
        assert C.season_spots(sb.conn, "cbb", "pts") == whole, "and again, served from the kept seasons"
        assert C.season_spots(sb.conn, "cbb", "reb") == C.spot_index(sb.conn, "cbb", "reb")
        # A form carried over the season's turn: Player 0's first 2025 spot reads his last ten 2024 games.
        first_2025 = next(s for s in whole if s[1] == "Player 0" and s[0][0] == 2025)
        assert first_2025[0] == (2025, "2025-11-01")
        # That day's three games (the night's own and a doubleheader's two) in game order, as the whole read
        # gives them: g-dh-1, g-dh-2, then g2026-2.
        dh = [s for s in whole if s[1] == "Player 1" and s[0] == (2026, "2026-11-03")]
        assert len(dh) == 3 and [s[3] for s in dh][:2] == [2.0, 31.0], dh
        assert not any(s[1] == "Seldom Used" for s in whole), "one game is no form"
        a, b = C._BandIndex(whole), C._kept_index(sb.conn, "cbb", "pts")
        assert list(a.forms) == list(b.forms) and list(a.values) == list(b.values)


def test_a_nights_rows_read_this_season_alone():
    with _Sandbox() as sb:
        _history(sb.conn)
        C.season_spots(sb.conn, "cbb", "pts")
        calls, undo = _counting()
        try:
            db.upsert_player_logs(sb.conn, [_row(2026, "2026-11-09", "g-new", "Player 3", 17.0)])
            sb.conn.commit()
            got = C.season_spots(sb.conn, "cbb", "pts")
        finally:
            undo()
        assert calls == [2026], f"this season's rows alone: {calls}"
        assert got == C.spot_index(sb.conn, "cbb", "pts")


def test_an_earlier_seasons_change_reads_it_and_every_season_after():
    with _Sandbox() as sb:
        _history(sb.conn)
        C.season_spots(sb.conn, "cbb", "pts")
        calls, undo = _counting()
        try:
            db.upsert_player_logs(sb.conn, [_row(2025, "2025-11-20", "g-late", "Player 4", 29.0)])
            sb.conn.commit()
            got = C.season_spots(sb.conn, "cbb", "pts")
        finally:
            undo()
        assert calls == [2025, 2026], f"the season changed and the one its form carries into: {calls}"
        assert got == C.spot_index(sb.conn, "cbb", "pts")


def test_a_sport_with_rows_filed_under_no_season_is_read_whole():
    with _Sandbox() as sb:
        _history(sb.conn)
        db.upsert_player_logs(sb.conn, [_row(None, "2023-11-01", "g-old", "Player 0", 5.0)])
        sb.conn.commit()
        calls, undo = _counting()
        try:
            got = C.season_spots(sb.conn, "cbb", "pts")
        finally:
            undo()
        assert calls == [] and got == C.spot_index(sb.conn, "cbb", "pts")


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
