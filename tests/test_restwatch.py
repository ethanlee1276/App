"""The rest watch: certain statuses, warned risks, gated announcements.

Three strengths of claim, kept strictly apart: dominance-computed
certainty (clinched/eliminated, tiebreaker-free by construction),
late-season usage RISK (a warning the human weighs), and announced rests
(curated, and the only thing strong enough to flip a prop to Pass).
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import restwatch as RW
from engine.db import connect, upsert_games

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _game(week, home, away, hs, as_):
    return {"sport": "nfl", "season": 2026, "period": f"2026-W{week}",
            "game_id": f"g{week}-{home}-{away}", "home": home, "away": away,
            "home_score": hs, "away_score": as_, "spread": 0.0,
            "total": None, "roof": "open", "surface": "grass",
            "temp": None, "wind": None, "extra": ""}


def _season(week=14):
    """A late season with one certain clinch and one certain corpse.

    KC 12-0 while its whole division sits on 4 wins — every rival's best
    possible finish is strictly worse, so the division (and the berth) is
    KC's regardless of tiebreakers. NYJ 0-13 with seven AFC teams already
    guaranteed to finish ahead — all seven seeds are spoken for. NFC South
    teams serve as ballast so AFC records don't entangle each other."""
    h = connect(":memory:")
    games = []
    bags = ["CAR", "NO", "TB", "ATL"]
    wk = 1

    def feed(team, wins, losses):
        nonlocal wk
        for i in range(wins):
            games.append(_game(min(wk + i, week), team, bags[i % 4], 24, 10))
        for i in range(losses):
            games.append(_game(min(wk + i, week), bags[i % 4], team, 20, 3))
    feed("KC", 12, 0)
    for rival in ("DEN", "LV", "LAC"):
        feed(rival, 4, 8)
    feed("NYJ", 0, 13)
    # Seven AFC teams already strictly past NYJ's ceiling (max 8 pts).
    for t in ("BUF", "MIA", "NE", "BAL", "CIN", "PIT", "HOU"):
        feed(t, 6, 6)
    games.append(_game(week, "SEA", "ARI", 21, 20))    # stamps the week
    upsert_games(h, games)
    return h


def _rest(entries):
    p = os.path.join(tempfile.mkdtemp(), "rest.json")
    open(p, "w").write(json.dumps({"season": 2026, "entries": entries}))
    return p


# --- the certainty rules -----------------------------------------------------
def test_a_dominant_division_lead_is_a_certain_clinch():
    pic = RW.picture(_season(), 2026, _rest([]))
    assert pic["teams"]["KC"]["status"] == "clinched — division"
    assert pic["week"] == 15
    assert pic["teams"]["KC"]["risk"] == "rest risk"


def test_a_catchable_lead_is_not_called_clinched():
    """BUF at 6-6 leads nobody with certainty — its rivals can still pass
    it. The board is late before it is wrong."""
    pic = RW.picture(_season(), 2026, _rest([]))
    assert pic["teams"]["BUF"]["status"] == "in the hunt"
    assert pic["teams"]["BUF"]["risk"] == ""


def test_seven_teams_past_the_ceiling_is_a_certain_elimination():
    pic = RW.picture(_season(), 2026, _rest([]))
    assert pic["teams"]["NYJ"]["status"] == "eliminated"
    assert pic["teams"]["NYJ"]["risk"] == "shutdown risk"


def test_certainty_without_the_stretch_carries_no_risk_flag():
    """A Week-10 clinch is real but nobody rests in Week 10 — the status
    shows, the risk waits for Week 15."""
    pic = RW.picture(_season(week=9), 2026, _rest([]))
    assert pic["teams"]["KC"]["status"] == "clinched — division"
    assert pic["teams"]["KC"]["risk"] == ""
    assert pic["active"] is False and "Week" in pic["note"]


# --- the curated override ----------------------------------------------------
def test_an_announced_rest_lands_on_the_right_week_only():
    p = _rest([{"team": "KC", "week": 15, "note": "coach confirmed Friday"}])
    pic = RW.picture(_season(), 2026, p)
    assert pic["teams"]["KC"]["risk"] == "announced rest"
    assert pic["announced"] == ["KC"]
    wrong_week = _rest([{"team": "KC", "week": 18}])
    pic2 = RW.picture(_season(), 2026, wrong_week)
    assert pic2["teams"]["KC"]["risk"] == "rest risk"      # computed only


# --- the decoration: gate vs warn -------------------------------------------
def test_an_announced_rest_gates_and_a_computed_risk_only_warns():
    p = _rest([{"team": "KC", "week": 15, "note": "coach confirmed"}])
    pic = RW.picture(_season(), 2026, p)
    recs = [
        {"player": "KC Starter", "team": "KC", "market": "rec_yds",
         "recommended": True, "grade": "A", "hit_prob": 0.58, "reasons": []},
        {"player": "Jet Vet", "team": "NYJ", "market": "rec_yds",
         "recommended": True, "grade": "A", "hit_prob": 0.55, "reasons": []},
        {"player": "Bill", "team": "BUF", "market": "rec_yds",
         "recommended": True, "grade": "A", "reasons": []},
    ]
    out = RW.decorate(recs, pic)
    assert out == {"gated": 1, "warned": 1}
    kc, nyj, buf = recs
    assert kc["recommended"] is False and kc["grade"] == "Pass"
    assert "Announced rest" in kc["reasons"][0]
    assert nyj["recommended"] is True and nyj["grade"] == "A"
    assert any("shut down" in x for x in nyj["reasons"])
    assert nyj["hit_prob"] == 0.55                 # warnings never price
    assert buf["reasons"] == [] and "risk" not in str(buf.get("grade"))


# --- the wiring --------------------------------------------------------------
def test_the_board_ships_the_picture_and_gates_before_the_parlay_screen():
    src = open(os.path.join(ROOT, "engine", "pipeline.py"),
               encoding="utf-8").read()
    assert "restwatch.decorate" in src
    assert 'out["playoff_picture"] = pic' in src
    # The gate must run before parlays screen the singles — a benched
    # starter must not survive into a ticket.
    assert src.index("restwatch.decorate") < src.index('attach(out, "nfl")')


def test_the_page_renders_the_rest_watch_nfl_only():
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    i = app.index("function renderRestWatch(")
    fn = app[i:app.find("\nfunction ", i + 1)]
    for needle in ("Rest watch", 'state.sport !== "nfl"',
                   "late than wrong", "announced rest"):
        assert needle in fn, needle
    assert "renderRestWatch();" in app, "built but never called"
    html = open(os.path.join(ROOT, "web", "index.html"),
                encoding="utf-8").read()
    assert 'id="rest-watch"' in html


def test_the_checked_in_table_is_valid_and_empty_by_honesty():
    d = json.loads(open(os.path.join(ROOT, "data", "nfl_rest_watch.json"),
                        encoding="utf-8").read())
    assert isinstance(d.get("entries"), list)
    assert isinstance(d.get("season"), int)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
