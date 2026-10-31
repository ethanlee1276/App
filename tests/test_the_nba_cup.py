"""The NBA Cup tracker: the groups, the differential tiebreaker, our chances.

Ethan, 2026-10-29, to "an NBA Cup tracker — group standings, the
point-differential tiebreaker, our odds for each team to advance": "do all 3".

Guarded here: the 2026 draw (six groups of five, every club once), which
games count as group games, the league's tie order — head-to-head, then
point differential with overtime counting zero, then points scored without
overtime's — the wild card without a head-to-head, chances that add up
(eight through, one winner a group, one Cup), the scoreboard fields the
tracker reads, and the paywall's split of the file.

    python3 tests/test_the_nba_cup.py
"""

import itertools
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import divisions, gate, nbacup                    # noqa: E402
from engine.sources import espnhoops                          # noqa: E402


def _game(h, a, day, hs=None, as_=None, period=4, notes="", reg=None):
    g = {"home": h, "away": a, "date": day, "kickoff": f"{day}T23:30Z", "season_type": 2,
         "completed": hs is not None, "home_score": hs, "away_score": as_, "period": period,
         "notes": notes}
    if reg:
        g["home_reg"], g["away_reg"] = reg
    return g


def _ratings(seed=1):
    rng = random.Random(seed)
    return {t: rng.gauss(0, 4) for ts in nbacup.GROUPS.values() for t in ts}


def _schedule(played_through="2026-11-07"):
    days = ["2026-10-30", "2026-11-03", "2026-11-07", "2026-11-10", "2026-11-14",
            "2026-11-17", "2026-11-21", "2026-11-24", "2026-11-25", "2026-11-27"]
    out = []
    for g, ts in nbacup.GROUPS.items():
        for k, (a, b) in enumerate(itertools.combinations(ts, 2)):
            day = days[k]
            out.append(_game(a, b, day, *( (110, 100) if day <= played_through else (None, None))))
    return out


# --- the draw --------------------------------------------------------------------
def test_six_groups_of_five_every_club_once():
    every = [t for ts in nbacup.GROUPS.values() for t in ts]
    assert len(nbacup.GROUPS) == 6 and all(len(ts) == 5 for ts in nbacup.GROUPS.values())
    assert sorted(every) == sorted(divisions.NBA), "the league's own codes, each club once"
    for g, ts in nbacup.GROUPS.items():
        conf = nbacup.conference(g)
        assert all(divisions.NBA[t][0] == conf for t in ts), g
    assert nbacup.GROUP_PLAY == ("2026-10-30", "2026-11-27")
    assert nbacup.KNOCKOUTS["final"] == "2026-12-11"


def test_a_group_game_is_one_meeting_inside_the_window():
    games = [_game("BKN", "DET", "2026-10-30", 101, 99),
             _game("DET", "BKN", "2026-11-20"),                   # the same pair again
             _game("BKN", "BOS", "2026-11-03"),                   # different groups
             _game("MIL", "ORL", "2026-12-15"),                   # outside the window
             _game("NY", "PHI", "2026-11-07", 99, 98)]            # ESPN's code for the Knicks
    got = nbacup.cup_games(games)
    assert [(g["home"], g["away"]) for g in got] == [("BKN", "DET"), ("NYK", "PHI")]


def test_the_feeds_own_billing_wins_when_it_has_one():
    games = [_game("BKN", "DET", "2026-11-03", 101, 99),
             _game("DET", "BKN", "2026-11-14", 99, 101, notes="East Group A")]
    got = nbacup.cup_games(games)
    assert [(g["home"], g["date"]) for g in got] == [("DET", "2026-11-14")]


# --- the tie order ---------------------------------------------------------------
def test_head_to_head_breaks_a_two_way_tie_before_the_differential():
    w = {"A": 3, "B": 3}; l = {"A": 1, "B": 1}
    pd = {"A": 40, "B": 5}; pf = {"A": 500, "B": 500}; net = {"A": 0, "B": 0}
    order = nbacup._rank(["A", "B"], w, l, pd, pf, net, {("A", "B"): "B"}, random.Random(1))
    assert order == ["B", "A"], "B beat A, so B is ahead whatever the differential"
    # Without the meeting, the differential decides; then points.
    assert nbacup._rank(["A", "B"], w, l, pd, pf, net, {}, random.Random(1)) == ["A", "B"]
    pd2 = {"A": 5, "B": 5}; pf2 = {"A": 480, "B": 510}
    assert nbacup._rank(["A", "B"], w, l, pd2, pf2, net, {}, random.Random(1)) == ["B", "A"]


def test_the_wild_card_has_no_head_to_head():
    w = {"A": 3, "B": 3}; l = {"A": 1, "B": 1}; pd = {"A": 40, "B": 5}; pf = {"A": 0, "B": 0}
    order = nbacup._rank(["A", "B"], w, l, pd, pf, {"A": 0, "B": 0}, {("A", "B"): "B"},
                         random.Random(1), h2h=False)
    assert order == ["A", "B"]


def test_overtime_counts_zero_and_its_points_count_nowhere():
    games = [_game("BKN", "DET", "2026-10-30", 120, 115, period=5, reg=(108, 108)),
             _game("MIL", "ORL", "2026-10-30", 101, 90)]
    out = nbacup.build(games, _ratings(), "2026-10-31", 2.4, 8.5, sims=200, seed=1)
    rows = {r["team"]: r for r in out["groups"]["East A"]}
    assert rows["BKN"]["w"] == 1 and rows["DET"]["l"] == 1
    assert rows["BKN"]["pd"] == 0 and rows["DET"]["pd"] == 0, "an overtime game is zero"
    assert rows["BKN"]["pf"] == 108 and rows["DET"]["pf"] == 108, "regulation's points only"
    assert rows["MIL"]["pd"] == 11 and rows["ORL"]["pd"] == -11


# --- the chances -----------------------------------------------------------------
def test_eight_go_through_one_a_group_and_one_cup():
    out = nbacup.build(_schedule(), _ratings(), "2026-11-08", 2.4, 8.5, sims=2000, seed=2)
    ch = out["chances"]
    # Each figure is rounded to a tenth of a point, so a sum over thirty
    # clubs can drift by that much thirty times.
    assert abs(sum(c["advance"] for c in ch.values()) - 8) < 0.02
    assert abs(sum(c["cup"] for c in ch.values()) - 1) < 0.02
    assert abs(sum(c["final"] for c in ch.values()) - 2) < 0.02
    for g, ts in nbacup.GROUPS.items():
        assert abs(sum(ch[t]["group"] for t in ts) - 1) < 0.004, g
    for c in ch.values():
        assert abs(c["advance"] - c["group"] - c["wildcard"]) < 0.0015
        assert c["cup"] <= c["final"] <= c["semis"] <= c["advance"] + 1e-9
    assert out["played"] == 18 and out["games_left"] == 42


def test_a_group_already_won_reads_as_won():
    games = _schedule(played_through="2026-11-27")      # every group game played
    out = nbacup.build(games, _ratings(), "2026-11-28", 2.4, 8.5, sims=300, seed=3)
    for g, rows in out["groups"].items():
        leader = rows[0]["team"]
        assert out["chances"][leader]["group"] == 1.0, g
        assert out["today"]["winners"][g] == leader


def test_each_game_left_is_priced_both_ways():
    out = nbacup.build(_schedule(), _ratings(), "2026-11-08", 2.4, 8.5, sims=200, seed=4)
    seen = {}
    for t, games in out["remaining"].items():
        for g in games:
            key = (g["date"], frozenset((t, g["opp"])))
            seen.setdefault(key, []).append(g["p"])
    assert all(len(ps) == 2 and abs(sum(ps) - 1) < 0.002 for ps in seen.values())


# --- the feed and the file --------------------------------------------------------
def test_the_scoreboard_carries_the_billing_and_regulation():
    payload = {"events": [{"id": "1", "date": "2026-11-01T00:00Z", "season": {"type": 2},
        "competitions": [{"notes": [{"type": "event", "headline": "East Group B"}],
                          "status": {"period": 5, "type": {"state": "post", "completed": True}},
                          "competitors": [
                              {"homeAway": "home", "score": "120", "team": {"abbreviation": "NY"},
                               "linescores": [{"value": 27}, {"value": 27}, {"value": 27}, {"value": 27}, {"value": 12}]},
                              {"homeAway": "away", "score": "115", "team": {"abbreviation": "PHI"},
                               "linescores": [{"value": 30}, {"value": 25}, {"value": 26}, {"value": 27}, {"value": 7}]}]}]}]}
    g = espnhoops.parse_scoreboard(payload)[0]
    assert g["notes"] == "East Group B"
    assert (g["home_reg"], g["away_reg"]) == (108, 108)


def test_the_public_copy_keeps_the_tables_and_drops_the_model():
    out = nbacup.build(_schedule(), _ratings(), "2026-11-08", 2.4, 8.5, sims=200, seed=5)
    assert "nba_cup.json" in gate.MIXED_FILES and "nba_cup.json" in gate.KNOWN_BOARDS
    pub = gate.redact(out, "nba_cup.json")
    assert not pub["chances"] and not pub["remaining"]
    assert pub["groups"] == out["groups"] and pub["today"] == out["today"]
    assert '"advance"' not in json.dumps(pub)


def test_the_nba_build_runs_it_for_the_nba_only():
    src = (ROOT / "nba_build.py").read_text()
    i = src.index("from engine import nbacup as _cup")
    block = src[i - 500:i + 400]
    assert 'if args.league == "nba":' in block and "_cup.publish(" in block
    assert "except Exception as _cx:" in block


def test_the_nights_to_come_are_not_asked_for_every_build():
    import datetime as dt
    asked = {}
    real = espnhoops.load_day
    espnhoops.load_day = lambda date, ttl=None, league="wnba": asked.setdefault(date, (ttl, league)) and []
    try:
        nbacup.load_window(dt.date(2026, 11, 10))
    finally:
        espnhoops.load_day = real
    assert asked["2026-11-09"] == (None, "nba"), "a past night: espnhoops' own lifetime"
    assert asked["2026-11-10"] == (None, "nba"), "tonight: live"
    assert asked["2026-11-11"] == (nbacup.FUTURE_TTL, "nba") and nbacup.FUTURE_TTL >= 3600
    assert sorted(asked)[0] == "2026-10-30" and sorted(asked)[-1] == "2026-11-27"


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
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
