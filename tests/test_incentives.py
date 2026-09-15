"""The NFL incentive tracker: December money, measured — never priced.

"Needs 62 receiving yards for $500,000" is usage information the
player's own sideline acts on in Weeks 17-18, and the books are slow to
price it. No free feed publishes contract incentives, so the table is
hand-curated in data/nfl_incentives.json; everything computed about a
chase — season total, distance, pace, games left — comes from our own
ingested logs. The tracker displays and annotates; it never moves a
probability.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import incentives as INC
from engine.db import connect, upsert_games, upsert_player_logs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _tbl(entries):
    p = os.path.join(tempfile.mkdtemp(), "inc.json")
    open(p, "w").write(json.dumps({"season": 2026, "entries": entries}))
    return p


def _hist(games_final=12, per_game=58.0, player="Chase Guy", team="KC"):
    """A season in progress: `games_final` team finals, the player logging
    `per_game` receiving yards in each."""
    h = connect(":memory:")
    for wk in range(1, games_final + 1):
        upsert_games(h, [{
            "sport": "nfl", "season": 2026, "period": f"2026-W{wk}",
            "game_id": f"g{wk}", "home": team, "away": "LV",
            "home_score": 24, "away_score": 17, "spread": -3.0,
            "total": 44.5, "roof": "open", "surface": "grass",
            "temp": None, "wind": None, "extra": ""}])
        upsert_player_logs(h, [{
            "sport": "nfl", "season": 2026, "period": f"2026-W{wk}",
            "game_id": f"g{wk}", "player": player, "team": team,
            "opponent": "LV", "position": "WR", "home": 1,
            "market": "rec_yds", "value": per_game}])
    return h


# --- the arithmetic ----------------------------------------------------------
def test_a_chase_is_measured_from_our_own_logs():
    p = _tbl([{"player": "Chase Guy", "team": "KC", "stat": "rec_yds",
               "threshold": 1000, "bonus_usd": 500000}])
    r = INC.report(_hist(games_final=12, per_game=58.0), 2026, p)
    e = r["entries"][0]
    assert e["total"] == 696.0 and e["need"] == 304.0
    assert e["games_left"] == 5 and e["pace"] == 58.0
    # 304 over 5 games is 60.8/game vs a 58 pace — a push, not a lock.
    assert e["status"] == "needs a push"


def test_the_status_ladder_covers_hit_pace_and_the_wire():
    hist = _hist(games_final=12, per_game=58.0)
    cases = [(600, "hit"),            # already there
             (900, "on pace"),        # 40.8/game needed vs 58 pace
             (1000, "needs a push"),  # 60.8/game needed
             (1300, "long shot")]     # 120.8/game needed
    for threshold, want in cases:
        p = _tbl([{"player": "Chase Guy", "team": "KC", "stat": "rec_yds",
                   "threshold": threshold, "bonus_usd": 100000}])
        got = INC.report(hist, 2026, p)["entries"][0]["status"]
        assert got == want, (threshold, got)
    # Season over, short of the number: missed — and never decorated.
    p = _tbl([{"player": "Chase Guy", "team": "KC", "stat": "rec_yds",
               "threshold": 2000, "bonus_usd": 100000}])
    over = INC.report(_hist(games_final=17), 2026, p)["entries"][0]
    assert over["status"] == "missed" and over["games_left"] == 0


def test_an_unmeasurable_stat_is_dropped_with_its_reason_not_guessed():
    p = _tbl([{"player": "Sack Guy", "team": "KC", "stat": "sacks",
               "threshold": 10, "bonus_usd": 250000}])
    r = INC.report(_hist(), 2026, p)
    assert not r["entries"]
    assert r["dropped"][0]["stat"] == "sacks"
    assert "ingest" in r["dropped"][0]["why"]


def test_an_empty_table_states_the_setup_instead_of_rendering_nothing():
    r = INC.report(_hist(), 2026, _tbl([]))
    assert r["entries"] == []
    assert "nfl_incentives.json" in r["note"]
    assert "December" in r["note"]


# --- the annotation: a reason, never a number --------------------------------
def test_a_live_chase_decorates_its_own_prop_card_only():
    p = _tbl([{"player": "Chase Guy", "team": "KC", "stat": "rec_yds",
               "threshold": 1000, "bonus_usd": 500000}])
    entries = INC.report(_hist(), 2026, p)["entries"]
    recs = [{"player": "Chase Guy", "market": "rec_yds", "hit_prob": 0.57,
             "reasons": ["over the line by a real margin"]},
            {"player": "Chase Guy", "market": "receptions", "reasons": []},
            {"player": "Other Guy", "market": "rec_yds", "reasons": []}]
    assert INC.decorate(recs, entries) == 1
    tagged = recs[0]
    assert any("Incentive watch" in x and "$500,000" in x
               for x in tagged["reasons"])
    assert tagged["incentive"]["status"] == "needs a push"
    assert "incentive" not in recs[1] and "incentive" not in recs[2]
    # The probability is untouched — the tracker annotates, never prices.
    assert tagged["hit_prob"] == 0.57


def test_a_hit_or_missed_incentive_no_longer_decorates():
    for threshold, games in ((600, 12), (2000, 17)):   # hit / missed
        p = _tbl([{"player": "Chase Guy", "team": "KC", "stat": "rec_yds",
                   "threshold": threshold, "bonus_usd": 500000}])
        entries = INC.report(_hist(games_final=games), 2026, p)["entries"]
        recs = [{"player": "Chase Guy", "market": "rec_yds", "reasons": []}]
        assert INC.decorate(recs, entries) == 0, threshold


# --- the wiring --------------------------------------------------------------
def test_the_nfl_board_ships_the_tracker_and_the_page_renders_it():
    src = open(os.path.join(ROOT, "engine", "pipeline.py"),
               encoding="utf-8").read()
    assert "incentives.report" in src and "incentives.decorate" in src
    assert 'out["incentives"] = inc' in src
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    i = app.index("function renderIncentives(")
    fn = app[i:app.find("\nfunction ", i + 1)]
    for needle in ("Incentive watch", 'state.sport !== "nfl"',
                   "never moves a probability"):
        assert needle in fn, needle
    assert "renderIncentives();" in app, "built but never called"
    html = open(os.path.join(ROOT, "web", "index.html"),
                encoding="utf-8").read()
    assert 'id="incentive-watch"' in html


def test_the_checked_in_table_is_valid_and_empty_by_honesty():
    """Shipping fabricated incentives would be worse than none — the file
    starts empty and fills from real December reporting."""
    p = os.path.join(ROOT, "data", "nfl_incentives.json")
    d = json.loads(open(p, encoding="utf-8").read())
    assert isinstance(d.get("entries"), list)
    assert isinstance(d.get("season"), int)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
