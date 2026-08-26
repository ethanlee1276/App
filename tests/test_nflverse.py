"""Tests for the nflverse source layer.

Network feeds are stubbed with fixtures so these run offline and deterministically.
They verify the schema mapping (weather, spread sign), log extraction, defense
aggregation and full slate assembly.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.sources import nflverse as nv
from engine.models import PASS_YDS, RUSH_YDS, REC_YDS, RECEPTIONS


def approx(a, b, tol=1e-6):
    return abs(a - b) < tol


# --- weather + spread mapping ----------------------------------------------
def test_weather_dome_and_closed():
    assert nv.weather_from_row({"roof": "dome"}).dome is True
    assert nv.weather_from_row({"roof": "closed"}).dome is True


def test_weather_outdoor_uses_reported_values():
    w = nv.weather_from_row({"roof": "outdoors", "temp": "28", "wind": "22"})
    assert w.dome is False and w.temp_f == 28 and w.wind_mph == 22


def test_weather_outdoor_blank_defaults():
    w = nv.weather_from_row({"roof": "open", "temp": "", "wind": ""})
    assert w.dome is False and w.wind_mph == 6.0


def test_a_blank_row_is_flagged_unmeasured_rather_than_mild():
    """The defaults above are a PRIOR, and for a season they wore a
    measurement's clothes.

    nflverse fills a schedule row's temp and wind from the PLAYED game,
    so every outdoor game on a forward board is blank — which meant the
    card printed "60°F · 6mph" as a forecast all season, the journal
    recorded 6.0 as the wind each bet was made in (putting every outdoor
    football pick in the miner's "calm (<8mph)" band, a constant it
    could convict or exonerate a slice on), and the 25-mph deep-passing
    warning in engine/rules.py could never fire because the number it
    tested was a constant three times below its own threshold.

    The numbers stay — the pricing paths need one, and a mild day is the
    right prior — and everything that SHOWS or JOURNALS them checks the
    flag first."""
    assert nv.weather_from_row({"roof": "open", "temp": "", "wind": ""}).measured is False
    assert nv.weather_from_row({"roof": "outdoors"}).measured is False
    # One half reported is a real reading of that half.
    assert nv.weather_from_row({"roof": "outdoors", "wind": "19"}).measured is True
    assert nv.weather_from_row({"roof": "outdoors", "temp": "41"}).measured is True


def test_a_dome_is_measured_because_it_is_a_fact_about_a_building():
    for roof in ("dome", "closed"):
        assert nv.weather_from_row({"roof": roof}).measured is True


def test_build_games_negates_spread(monkeypatch):
    # nflverse spread_line +3 means home favored -> engine spread -3.
    rows = [{
        "season": "2024", "week": "5", "home_team": "KC", "away_team": "NO",
        "roof": "outdoors", "temp": "70", "wind": "1",
        "spread_line": "3", "total_line": "43",
    }]
    monkeypatch.setattr(nv, "load_schedules", lambda: rows)
    g = nv.build_games(2024, 5)[0]
    assert g.home == "KC" and g.away == "NO"
    assert approx(g.spread, -3.0) and approx(g.total, 43.0)


# --- game logs --------------------------------------------------------------
def _stat(name, pos, team, opp, week, **vals):
    row = {
        "player_display_name": name, "position": pos, "recent_team": team,
        "opponent_team": opp, "week": str(week), "season": "2024", "season_type": "REG",
        "passing_yards": "0", "rushing_yards": "0", "receiving_yards": "0",
        "receptions": "0", "attempts": "0", "carries": "0", "targets": "0",
    }
    row.update({k: str(v) for k, v in vals.items()})
    return row


def test_player_game_logs_order_and_market():
    rows = [
        _stat("RB One", "RB", "AAA", "BBB", 1, rushing_yards=60),
        _stat("RB One", "RB", "AAA", "CCC", 2, rushing_yards=80),
        _stat("RB One", "RB", "AAA", "DDD", 3, rushing_yards=100),
    ]
    logs = nv.player_game_logs(rows, "RB One", RUSH_YDS, upto_week=4)
    assert [l.value for l in logs] == [100, 80, 60]  # most recent first
    assert [l.week for l in logs] == [3, 2, 1]
    # upto_week excludes the target week and beyond
    assert len(nv.player_game_logs(rows, "RB One", RUSH_YDS, upto_week=3)) == 2


# --- defense profiles -------------------------------------------------------
def test_defense_profiles_relative_to_league():
    # Two defenses: BBB gives up lots of rush yards to RBs, CCC very little.
    rows = []
    for wk in (1, 2, 3):
        rows.append(_stat("RB A", "RB", "AAA", "BBB", wk, rushing_yards=120))
        rows.append(_stat("RB B", "RB", "DDD", "CCC", wk, rushing_yards=40))
    profiles = nv.build_defense_profiles(rows, upto_week=4)
    assert profiles["BBB"].vs_rb_rush > 1.0   # generous
    assert profiles["CCC"].vs_rb_rush < 1.0   # stingy
    # Toughest run defense ranks #1.
    assert profiles["CCC"].rush_rank < profiles["BBB"].rush_rank


# --- full slate assembly ----------------------------------------------------
def test_build_slate_end_to_end(monkeypatch):
    sched = [{
        "season": "2024", "week": "5", "home_team": "AAA", "away_team": "BBB",
        "roof": "outdoors", "temp": "30", "wind": "24",
        "spread_line": "-4", "total_line": "45",
    }]
    stats = []
    for wk in (1, 2, 3, 4):
        stats.append(_stat("QB Aaa", "QB", "AAA", "ZZZ", wk, passing_yards=270, attempts=34))
        stats.append(_stat("WR Aaa", "WR", "AAA", "ZZZ", wk, receiving_yards=85, targets=9))
        stats.append(_stat("RB Bbb", "RB", "BBB", "ZZZ", wk, rushing_yards=78, carries=17))
        # opponents concede so defense profiles are populated
        stats.append(_stat("WR Opp", "WR", "ZZZ", "AAA", wk, receiving_yards=70, targets=8))
        stats.append(_stat("RB Opp", "RB", "ZZZ", "BBB", wk, rushing_yards=65, carries=15))

    monkeypatch.setattr(nv, "load_schedules", lambda: sched)
    monkeypatch.setattr(nv, "load_weekly_stats", lambda season: stats)

    slate = nv.build_slate(2024, 5, upto_week=5)
    assert slate.games and slate.props
    # Weather propagated from the schedule (windy outdoor game).
    assert slate.games[0].weather.wind_mph == 24
    # Every YARDAGE prop carries real logs and a proxy line. Anytime-TD
    # props (2026-08-25) are the deliberate exception: a Yes/No scorer
    # market priced against a made-up -110 would fabricate edges on the
    # long-shot board, so their lines stay EMPTY until a real book quote
    # attaches (see build_slate's own comment).
    from engine.models import ANYTIME_TD
    td_props = [p for p in slate.props if p.market == ANYTIME_TD]
    yardage = [p for p in slate.props if p.market != ANYTIME_TD]
    for p in yardage:
        assert len(p.logs) >= 3
        assert p.lines and p.lines[0].book == "proxy"
    # One TD prop per non-QB skill player on the board, unpriced.
    assert td_props, "the TD layer vanished from the slate"
    assert all(p.lines == [] for p in td_props)
    assert all(p.market == ANYTIME_TD for p in td_props)
    assert not any(p.position == "QB" and p.player.startswith("QB")
                   for p in td_props), "passing-yards QBs got TD props"

    # And the full model pipeline runs on the real-shaped slate — the
    # yardage loop skips scorer props, so the analyzed count is the
    # yardage count, not the prop-list length.
    from engine.pipeline import run_slate
    result = run_slate(slate)
    assert result["counts"]["props_analyzed"] == len(yardage)


if __name__ == "__main__":
    import types
    class MP:  # minimal monkeypatch shim so the file runs without pytest
        def __init__(self): self._undo = []
        def setattr(self, obj, name, val):
            self._undo.append((obj, name, getattr(obj, name)))
            setattr(obj, name, val)
        def undo(self):
            for obj, name, val in reversed(self._undo): setattr(obj, name, val)

    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        needs_mp = fn.__code__.co_argcount == 1
        mp = MP() if needs_mp else None
        try:
            fn(mp) if needs_mp else fn()
            print(f"  ok  {name}")
        finally:
            if mp:
                mp.undo()
    print(f"\n{len(fns)} tests passed.")
