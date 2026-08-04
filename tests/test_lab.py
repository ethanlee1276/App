"""The Lab — the walk-forward harnesses, published instead of printed.

Half a dozen backtests have always replayed the PRODUCTION pricer over
stored history. Every one of them printed to a terminal and vanished,
which meant the only evidence that accrues faster than a forward record
was invisible from a phone. This runs them on a weekly clock, normalizes
them into one shape, and publishes ``web/data/backtest.json``.

The tests below mostly guard HONESTY, because the numbers involved are
the easiest in betting to fool yourself with:

* **Basis.** A prop priced against a naive baseline measures predictive
  skill, not an edge over a book. Basis travels with every row.
* **Refusals are reported, not swallowed.** ``engine.gamebets`` refuses
  to price a league whose scoring baseline was never registered rather
  than borrow another league's variance. That refusal reaches the page
  as the honest gap it is.
* **Coverage is stated per sport**, including the sports that have no
  harness at all — a gap named is information, a gap omitted is a lie
  of composition.
"""

import json
import os
import random
import sys
import tempfile
import datetime as _dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db, lab

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _seeded(n_players=12, n_games=40, real_lines=True, market="total_bases"):
    """A history deep enough for a real walk-forward, optionally with a
    harvested close on every game (stored normalized, as the feed does)."""
    conn = db.connect(":memory:")
    rng = random.Random(11)
    rows, odds = [], []
    for p in range(n_players):
        name = f"Bat {p}"
        for g in range(n_games):
            date = f"2026-05-{g + 1:02d}" if g < 31 else f"2026-06-{g - 30:02d}"
            rows.append({"sport": "mlb", "season": 2026, "period": date,
                         "game_id": f"g{g}", "player": name, "team": "BOS",
                         "opponent": "NYY", "position": "OF", "home": 1,
                         "market": market,
                         "value": max(0, int(rng.gauss(1.6, 1.3)))})
            if real_lines:
                odds.append({"sport": "mlb", "taken_at": date + "T22:00:00",
                             "event_id": f"e{g}", "home": "BOS", "away": "NYY",
                             # The odds feed normalizes names; the join
                             # depends on it (engine.mlb.backtest._norm_name).
                             "player": name.lower(), "market": market,
                             "book": "dk", "line": 1.5, "over_odds": -115,
                             "under_odds": -105})
    db.upsert_player_logs(conn, rows)
    if odds:
        db.upsert_odds_history(conn, odds)
    return conn


def _quiet(*a, **k):
    pass


# --- the harness actually runs -----------------------------------------------
def test_a_real_walk_forward_produces_real_numbers():
    conn = _seeded()
    out = lab.mlb_props(conn, markets=("total_bases",), log=_quiet)
    assert out, "a 40-game history should replay"
    m = out[0]
    assert m["n"] > 100
    assert m["mae"] and m["brier"]
    assert m["bins"] and all(b["n"] for b in m["bins"])
    # Skill is the number that matters, and it needs its own sample bar.
    assert m["skill"] and "base_rate" in m["skill"]


def test_harvested_closes_make_the_basis_market_relative():
    m = lab.mlb_props(_seeded(real_lines=True), markets=("total_bases",),
                      log=_quiet)[0]
    assert m["basis"] == "book"
    assert m["used_real_lines"] == m["total_priced"]
    assert "book" in m["segments"]


def test_without_harvested_closes_the_basis_says_naive():
    """The distinction the whole page hangs on: beating a trailing average
    is not beating a sportsbook."""
    m = lab.mlb_props(_seeded(real_lines=False), markets=("total_bases",),
                      log=_quiet)[0]
    assert m["basis"] == "naive"
    assert m["used_real_lines"] == 0


def test_a_thin_history_replays_nothing_rather_than_something():
    conn = _seeded(n_players=2, n_games=4)
    assert lab.mlb_props(conn, markets=("total_bases",), log=_quiet) == []


# --- coverage, stated honestly -----------------------------------------------
def test_every_sport_appears_with_what_it_has_or_why_it_has_nothing():
    out = lab.build(hconn=_seeded(), log=_quiet, nfl=False)
    for sport in ("mlb", "nfl", "cfb", "nba", "wnba", "ufc"):
        s = out["sports"][sport]
        for half in ("props", "game_lines"):
            block = s[half]
            assert block.get("markets") or block.get("unavailable"), \
                f"{sport}.{half} is neither a result nor a stated reason"


def test_a_league_with_no_registered_variance_says_so():
    """engine.gamebets refuses to price a league whose scoring baseline was
    never registered, rather than quietly borrowing another league's — so
    the page reports a refusal, not an empty table."""
    out = lab.build(hconn=_seeded(), log=_quiet, nfl=False)
    for sport in ("nba", "wnba"):
        why = out["sports"][sport]["game_lines"]["unavailable"]
        assert "scoring baseline" in why and sport in why


def test_the_sports_with_no_prop_harness_are_named_not_omitted():
    out = lab.build(hconn=_seeded(), log=_quiet, nfl=False)
    for sport in ("nba", "wnba", "cfb", "ufc"):
        assert out["sports"][sport]["props"]["unavailable"]


def test_the_basis_caveat_ships_with_the_data():
    out = lab.build(hconn=_seeded(), log=_quiet, nfl=False)
    note = out["basis_note"].lower()
    assert "naive" in note and "not an edge" in note


# --- the weekly clock --------------------------------------------------------
def test_it_runs_once_a_week_and_can_be_forced():
    p = os.path.join(tempfile.mkdtemp(), "backtest.json")
    conn = _seeded(n_players=2, n_games=4)          # fast: nothing replays
    assert lab.run_if_due(hconn=conn, log=_quiet, path=p) == "ok"
    assert lab.run_if_due(hconn=conn, log=_quiet, path=p) == "already"
    assert lab.run_if_due(hconn=conn, log=_quiet, path=p, force=True) == "ok"
    later = _dt.date.today() + _dt.timedelta(days=lab.LAB_EVERY_DAYS)
    assert lab.run_if_due(hconn=conn, log=_quiet, path=p, today=later) == "ok"


def test_a_broken_harness_never_takes_the_settle_pass_down():
    """The settle pass must never fail because a backtest did."""
    class _Exploding:
        def execute(self, *a, **k):
            raise RuntimeError("db is on fire")

        def close(self):
            pass

    p = os.path.join(tempfile.mkdtemp(), "backtest.json")
    assert lab.run_if_due(hconn=_Exploding(), log=_quiet, path=p) in ("ok", "failed")


def test_the_published_path_is_absolute():
    """The launcher does not run from the repo root; a relative default
    would write the page's data into whatever directory was current."""
    assert lab.LAB_PATH.is_absolute()
    assert lab.LAB_PATH.parts[-2:] == ("data", "backtest.json")


# --- the page ----------------------------------------------------------------
def test_the_lab_is_wired_into_the_site():
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    html = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    assert 'id="view-lab"' in html and 'data-sport="lab"' in html
    assert 'if (name === "lab") renderLab();' in app
    assert '"record", "lab"' in app            # a standalone page, like The Book
    assert "data/backtest.json" in app


def test_the_page_refuses_to_headline_a_thin_or_naive_roi():
    """The two ways a backtest ROI lies: too few bets, or priced against a
    baseline nobody could have bet. Both must reach the reader."""
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    assert "LAB_ROI_MIN_BETS = 100" in app
    i = app.index("function labPropCard")
    card = app[i:i + 3000]
    assert "noise, not a result" in card
    assert "NOT an edge over a book" in card
    # A muted tone on both, so the colour never says "result" either.
    assert "(naive || thin) ? \"\" : toneOf(m.roi)" in card


def test_the_page_calls_out_a_hedging_model():
    """Perfect calibration with no sharpness is the failure that looks like
    success — a model answering "about average" to everything."""
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    i = app.index("function labPropCard")
    assert "hedging, not" in app[i:i + 3000]


def test_the_maintenance_pass_runs_the_lab():
    """Ethan's standing rule: anything needed every run gets automated. A
    backtest you have to remember to run is a backtest that stops running."""
    src = open(os.path.join(ROOT, "engine", "maintenance.py"),
               encoding="utf-8").read()
    assert "lab.run_if_due" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
