"""The College Football Playoff race, played out from our game model.

Ethan, 2026-10-29, to "a College Football Playoff race — each contender's
chances from our game model and remaining schedule, the bracket if it
started today, and which Saturday games swing it": "do all 3".

Guarded here: the 2026 format as engine/cfprace writes it down, the field if
it started today read off the poll, chances that add up (twelve in, one
champion), a team's chance to win out as the product of its games, the swing
games' measure, the poll reader, the paywall's split of the file, and the
build hook that runs it off the board's own ratings.

    python3 tests/test_the_playoff_race.py
"""

import datetime as dt
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import cfprace, gate                              # noqa: E402
from engine.sources import cfbdata                            # noqa: E402

CONFS = {"SEC": 6, "Big Ten": 6, "ACC": 6, "Big 12": 6, "American": 4,
         "Mountain West": 4, "FBS Independents": 1}
TAG = {"SEC": "SE", "Big Ten": "BT", "ACC": "AC", "Big 12": "B1", "American": "AM",
       "Mountain West": "MW"}


def _league():
    """A small league: every conference plays a round robin, half of it
    already played (home side always wins), the rest left."""
    teams, conf, ratings = [], {}, {}
    for c, n in CONFS.items():
        for k in range(n):
            t = "ND" if c == "FBS Independents" else f"{TAG[c]}{k}"
            teams.append(t)
            conf[t] = c
            ratings[t] = (20 - 3 * k) if c in cfprace.P4 else (6 - 3 * k)
    ratings["ND"] = 14
    games = []
    day0 = dt.date(2026, 9, 5)
    k = 0
    for c in CONFS:
        ms = [t for t in teams if conf[t] == c]
        for i, a in enumerate(ms):
            for b in ms[i + 1:]:
                day = (day0 + dt.timedelta(days=7 * (k % 12))).isoformat()
                k += 1
                done = day < "2026-10-29"
                g = {"home": a, "away": b, "home_conference": c, "away_conference": c,
                     "date": day, "season": 2026, "season_type": 2,
                     "conference_game": c != "FBS Independents", "neutral_site": False,
                     "completed": done, "state": "final" if done else "scheduled",
                     "home_rank": None, "away_rank": None}
                if done:
                    g["home_score"], g["away_score"] = 28, 21
                games.append(g)
    # Notre Dame plays two SEC sides, one played and one this Saturday.
    games.append({"home": "ND", "away": "SE1", "home_conference": "FBS Independents",
                  "away_conference": "SEC", "date": "2026-10-10", "season": 2026, "season_type": 2,
                  "conference_game": False, "neutral_site": False, "completed": True,
                  "state": "final", "home_score": 30, "away_score": 27})
    games.append({"home": "SE0", "away": "ND", "home_conference": "SEC",
                  "away_conference": "FBS Independents", "date": "2026-10-31", "season": 2026,
                  "season_type": 2, "conference_game": False, "neutral_site": False,
                  "completed": False, "state": "scheduled"})
    ranks = {t: i + 1 for i, t in enumerate(sorted(teams, key=lambda t: -ratings[t])[:25])}
    return games, ratings, ranks


def _race(**kw):
    games, ratings, ranks = _league()
    return cfprace.build(games, ratings, 2.71, 16.5, "2026-10-29", ranks=ranks,
                         sims=kw.pop("sims", 1500), seed=kw.pop("seed", 7), **kw)


# --- the format, as written down -------------------------------------------------
def test_the_2026_format():
    assert cfprace.P4 == ("ACC", "Big Ten", "Big 12", "SEC")
    assert set(cfprace.G6) == {"American", "Conference USA", "MAC", "Mountain West", "Pac-12", "Sun Belt"}
    assert cfprace.FIELD == 12 and cfprace.BYES == 4
    assert cfprace.FIRST_ROUND == ((5, 12), (6, 11), (7, 10), (8, 9))
    # 1 meets the 8/9 winner, 2 the 7/10, 3 the 6/11, 4 the 5/12.
    assert {s: cfprace.FIRST_ROUND[i] for s, i in cfprace.QUARTERS} == {
        1: (8, 9), 2: (7, 10), 3: (6, 11), 4: (5, 12)}
    assert cfprace.ccg_start(2026) == dt.date(2026, 12, 3)


def test_a_game_is_priced_the_way_the_board_prices_it():
    from engine.cfb import ratings as cfbratings
    fit = cfbratings.PRIOR
    for h, a, neutral in ((10.0, 3.0, False), (0.0, 12.0, True), (30.0, -10.0, False)):
        margin = (h - a) + (0.0 if neutral else fit.home_field)
        assert math.isclose(cfprace.win_prob(h, a, fit.home_field, fit.margin_sd, neutral),
                            cfbratings.win_prob(margin, fit), abs_tol=1e-9)


# --- the field if it started today -----------------------------------------------
def test_the_field_today_is_the_poll_and_the_rules():
    out = _race()
    seeds = out["today"]["seeds"]
    assert len(seeds) == 12 and [s["seed"] for s in seeds] == list(range(1, 13))
    bids = {s["team"]: s["bid"] for s in seeds}
    for c in cfprace.P4:
        assert sum(1 for b in bids.values() if b == f"{c} leader") == 1, c
    assert sum(1 for b in bids.values() if b == "Group of Six's best") == 1
    # Seeded straight off the poll: the ranks climb with the seed.
    ranked = [s["rank"] for s in seeds if s["rank"]]
    assert ranked == sorted(ranked)


# --- the chances ----------------------------------------------------------------
def test_twelve_get_in_and_one_wins_it():
    out = _race()
    ch = out["chances"]
    assert len(ch) == len(out["teams"])
    assert abs(sum(c["playoff"] for c in ch.values()) - 12) < 0.05
    assert abs(sum(c["title"] for c in ch.values()) - 1) < 0.02
    assert abs(sum(c["bye"] for c in ch.values()) - 4) < 0.05
    for c in ch.values():
        assert 0 <= c["bye"] <= c["playoff"] <= 1 and c["title"] <= c["playoff"] + 1e-9


def test_winning_out_is_the_product_of_the_games_left():
    out = _race()
    for t, games in out["remaining"].items():
        prod = 1.0
        for g in games:
            prod *= g["p"]
        assert abs(out["chances"][t]["win_out"] - prod) < 0.002, t


def test_the_same_seed_gives_the_same_race():
    assert json.dumps(_race(seed=3)["chances"], sort_keys=True) == \
        json.dumps(_race(seed=3)["chances"], sort_keys=True)


def test_the_swing_games_are_this_weeks_and_say_both_ways():
    out = _race(sims=2500)
    assert out["swing"], "a Saturday with a contender's game in it has a swing game"
    for g in out["swing"]:
        assert "2026-10-29" <= g["date"] <= "2026-10-31"
        assert g["moves"] and all(abs(m["if_home"] - m["if_away"]) >= cfprace.SWING_FLOOR for m in g["moves"])
    # Sorted by how much the game moves the field.
    assert [g["swing"] for g in out["swing"]] == sorted((g["swing"] for g in out["swing"]), reverse=True)


# --- the poll ---------------------------------------------------------------------
def _poll(kind, name, teams):
    return {"type": kind, "name": name,
            "ranks": [{"current": i + 1, "team": {"abbreviation": t}} for i, t in enumerate(teams)]}


def test_the_committee_ranking_wins_over_the_ap_poll():
    both = {"rankings": [_poll("ap", "AP Top 25", ["A", "B"]),
                         _poll("cfp", "College Football Playoff Rankings", ["B", "A"])]}
    got = cfbdata.parse_rankings(both)
    assert got["kind"] == "cfp" and got["ranks"] == {"B": 1, "A": 2}
    ap = cfbdata.parse_rankings({"rankings": [_poll("usa", "AFCA Coaches Poll", ["C"]),
                                              _poll("ap", "AP Top 25", ["A"])]})
    assert ap["kind"] == "ap" and ap["ranks"] == {"A": 1}
    assert cfbdata.parse_rankings({"rankings": [_poll("usa", "Coaches", ["C"])]}) == {}
    assert cfbdata.parse_rankings({}) == {}


def test_without_the_poll_the_scoreboard_ranks_stand_in():
    games = [{"home": "A", "away": "B", "home_rank": 3, "away_rank": None, "date": "2026-10-24"},
             {"home": "C", "away": "A", "home_rank": 9, "away_rank": 2, "date": "2026-10-31"}]
    assert cfprace.current_ranks(games, "2026-10-29") == {"A": 2, "C": 9}


# --- whose numbers -----------------------------------------------------------------
def test_the_public_copy_keeps_the_facts_and_drops_the_model():
    out = _race()
    assert "cfp_race.json" in gate.MIXED_FILES and "cfp_race.json" in gate.KNOWN_BOARDS
    pub = gate.redact(out, "cfp_race.json")
    for k in ("chances", "remaining", "swing"):
        assert not pub[k], k
    assert pub["today"] == out["today"] and pub["standings"] == out["standings"]
    assert pub["locked"] and pub["locked_reason"] == "subscription"
    assert '"playoff"' not in json.dumps(pub)


def test_the_college_build_runs_it_off_its_own_ratings():
    src = (ROOT / "cfb_build.py").read_text()
    i = src.index("from engine import cfprace as _race")
    block = src[i - 400:i + 300]
    assert "_race.publish(ratings, fit, day, teams=teams, out_path=str(Path(args.out).with_name('cfp_race.json')))" in block
    assert "except Exception as _rx:" in block, "a race that cannot run never costs the board"
    pub = (ROOT / "engine" / "cfprace.py").read_text()
    assert "gate.publish(out, p, p.name)" in pub


def test_each_day_is_read_on_the_lifetime_it_needs():
    """The college build runs every cycle: settled days on a day's cache,
    the last three and today on half an hour, the weeks ahead on six."""
    asked = []
    real = cfbdata.load_range
    cfbdata.load_range = lambda a, b, ttl=None, conferences=None: asked.append((a, b, ttl)) or []
    try:
        cfprace.load_season(2026, dt.date(2026, 10, 29))
    finally:
        cfbdata.load_range = real
    assert asked == [("2026-08-20", "2026-10-25", 24 * 3600),
                     ("2026-10-26", "2026-10-29", 30 * 60),
                     ("2026-10-30", "2026-12-06", 6 * 3600)], asked


if __name__ == "__main__":
    import inspect
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"FAIL {name}: {exc!r}")
    sys.exit(1 if fails else 0)
