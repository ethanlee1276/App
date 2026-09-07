"""Roadmap #7 — the features hiding in the engine, now on the site.

Three shipped in this pass and are pinned here; two were already live
and their homes are named so the claim is checkable:

  * Kalshi vs the BOOKS divergence — venue against venue, no model in
    the row (the board already carried Kalshi vs OUR number).
  * The book report card — booksharp's measurements published free by
    the daily chores, rendered on the Scanner page.
  * The sim lab — the prop page redraws the model's own distribution,
    2,000 animated draws converging on the published hit probability.
  * (already live) Correlation finder = Parlay Mode: simjoint-priced
    same-game tickets with the price they must beat.
  * (already live) Stale-line sniper = the Scanner's stale table, plus
    the feed's stale_line events (tests/test_feed.py).

Run directly: `python3 tests/test_unique_features.py`
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import booksharp, gate                            # noqa: E402
from engine.sources import kalshi as kx                       # noqa: E402


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


APP = _read("web", "js", "app.js")


# --- Kalshi vs the books -----------------------------------------------------

def _mkt(prob=0.62):
    return {"ticker": "KXNFLGAME-26SEP13-NODET-DET",
            "title": "Will the Lions beat the Saints?", "prob": prob,
            "volume_24h": 900, "price_basis": "book", "spread_cents": 2}


def _game(hm=-190, am=160):
    return {"home": "DET", "away": "NO", "home_name": "Detroit Lions",
            "away_name": "New Orleans Saints", "home_ml": hm, "away_ml": am}


def _board_rows(prob, hm=-190, am=160):
    d = kx.board([_mkt(prob=prob)], {"nfl": [_game(hm, am)]},
                 {("nfl", "NO@DET"): 0.60})
    return d["rows"], d


def test_divergence_is_venue_vs_venue_with_no_model_in_it():
    rows, d = _board_rows(prob=0.74)
    r = rows[0]
    # The books at -190/+160 devig to ~64% home; Kalshi at 74% is ~+10
    # points dearer — flagged, signed toward the exchange.
    assert r["book_p"] is not None and 0.60 < r["book_p"] < 0.68
    assert r["book_gap_pts"] > 4 and r["divergence"] is True
    assert d["n_divergent"] == 1


def test_agreement_inside_the_vig_is_not_a_story():
    rows, d = _board_rows(prob=0.65)
    assert rows[0]["divergence"] is False
    assert d["n_divergent"] == 0


def test_no_moneylines_no_divergence_claim():
    d = kx.board([_mkt()], {"nfl": [{"home": "DET", "away": "NO"}]},
                 {("nfl", "NO@DET"): 0.60})
    assert "book_p" not in d["rows"][0]


def test_the_intel_page_renders_the_divergence_strip():
    assert "Kalshi vs the books" in APP
    assert "r.divergence" in APP


# --- the book report card ----------------------------------------------------

def _history():
    """Ten series, two books: SharpBook opens at what becomes the close,
    SlowBook opens well off it and drifts in — the exact shape the card
    exists to expose."""
    rows = []
    for i in range(12):
        player = f"P{i}"
        for t, (sharp, slow) in enumerate([(-110, 130), (-110, 110),
                                           (-110, -110)]):
            base = 1_000 + i * 100 + t * 10
            rows.append({"ts": base, "player": player, "market": "hits",
                         "book": "SharpBook", "line": 1.5, "odds": sharp})
            rows.append({"ts": base + 1, "player": player, "market": "hits",
                         "book": "SlowBook", "line": 1.5, "odds": slow})
    return rows


def test_payload_ranks_the_sharp_book_above_the_slow_one():
    doc = booksharp.payload(_history())
    ranked = [b for b in doc["books"] if b["ranked"]]
    assert [b["book"] for b in ranked][:2] == ["SharpBook", "SlowBook"]
    assert ranked[0]["mae_pts"] < ranked[1]["mae_pts"]
    assert doc["note"] and doc["min_series"] == booksharp.MIN_SERIES


def test_the_report_is_a_registered_free_board():
    """Facts about BOOKS — no pick, no line, no model probability — and
    shareable content is the point. Free by decision, in the registry."""
    assert "bookreport.json" in gate.FREE_FILES
    assert "bookreport.json" in gate.KNOWN_BOARDS
    doc = {"books": [{"book": "X"}]}
    assert gate.redact(doc, "bookreport.json") == doc


def test_the_chores_publish_it_and_the_scanner_renders_it():
    src = _read("engine", "maintenance.py")
    assert 'gate.publish(doc, Path("web/data/bookreport.json")' in src
    assert "renderBookReport" in APP
    assert "Book report card" in APP


# --- the sim lab -------------------------------------------------------------

def test_the_sim_lab_draws_from_the_models_own_curve():
    """The toy must not invent: sd is recovered from the published
    projection, line and hit probability, and the copy says the draws
    teach the pick's uncertainty rather than adding information."""
    i = APP.index("function simParams(r)")
    body = APP[i:APP.index("\nfunction ", i + 1)]
    assert "invNorm(1 - p)" in body
    assert "r.hit_prob" in body and "r.projection" in body
    assert "return null" in body, "no degenerate-prop refusal"
    assert "the model’s own curve" in APP
    assert "simLabHTML(r)" in APP and "bindSimLab(r)" in APP


def test_the_already_live_halves_still_have_their_homes():
    """The claim in this file's header, checkable: Parlay Mode is the
    correlation finder, the Scanner + feed are the sniper."""
    assert "function renderParlays" in APP
    assert 'out["stale"] = stale_quotes(results)' in _read(
        "engine", "pipeline.py")
    assert "def stale_diff" in _read("engine", "feed.py")


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
