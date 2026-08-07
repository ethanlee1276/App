"""The blind-spot miner: learn losing patterns, don't hallucinate them.

Every "trends" tab in this industry mines one record forty ways and sells
the two streaks luck produced. The discipline pinned here is what keeps
ours from being that: a calibration test (the model's own claims vs
reality, never raw win rate), a minimum slice size, Benjamini–Hochberg
false-discovery control over EVERY slice tested, and enforcement that only
ever comes from a specific, surviving, hot slice — pooled aggregates
point, they never convict.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import ledger                                     # noqa: E402
from engine import losspatterns as lp                         # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def recs(sport, market, feats, said, wins, n):
    """n records at a constant stated probability, exactly `wins` winners —
    deterministic, so no test ever flakes on a random draw."""
    return [{"sport": sport, "market": market, "prob": said,
             "won": 1 if i < wins else 0, "feats": dict(feats)}
            for i in range(n)]


CLEAN = (recs("mlb", "hits", {"side": "OVER"}, 0.60, 60, 100)
         + recs("mlb", "total_bases", {"side": "OVER"}, 0.55, 55, 100)
         + recs("mlb", "total_bases", {"side": "UNDER"}, 0.58, 57, 98))
HOT = recs("mlb", "hits", {"side": "UNDER"}, 0.65, 45, 100)


# --- the statistics ----------------------------------------------------------
def test_a_real_miss_survives_and_closes_its_slice():
    out = lp.mine(CLEAN + HOT)
    closed = out["closed"]
    assert len(closed) == 1
    f = closed[0]
    assert (f["sport"], f["market"], f["dim"], f["value"]) == \
        ("mlb", "hits", "side", "UNDER")
    assert f["gap_pts"] == 20.0 and f["z"] < -3 and f["q"] < 0.05
    assert "closed itself" in f["reading"]


def test_calibrated_slices_produce_no_findings():
    out = lp.mine(CLEAN)
    assert out["findings"] == [] and out["closed"] == []
    assert out["tested"] > 0          # they WERE tested — and passed


def test_an_awful_slice_below_the_size_floor_is_not_even_tested():
    """Small slices are where every fake trend lives, and FDR can only
    correct the tests it is told about."""
    out = lp.mine(recs("mlb", "hits", {"side": "UNDER"}, 0.70, 10, 30))
    assert out["tested"] == 0 and out["findings"] == []


def test_a_pooled_sport_slice_may_watch_but_never_close():
    """The mlb-wide UNDER pool inherits the hits pocket's rot. Closing it
    would veto clean UNDER picks in markets that did nothing wrong —
    pooled slices point, specific slices convict."""
    out = lp.mine(CLEAN + HOT)
    # It surfaces in one of the two lists. A pooled slice that contains a
    # convicted market slice is a RESTATEMENT of it — same bets, wider
    # label — so it now lands there rather than being counted as a second
    # finding. What must not change is that it never closes.
    pooled = [f for f in out["findings"] + out["restatements"]
              if f["market"] is None]
    assert pooled, "the pooled slice should still surface somewhere"
    assert all(f["action"] == "watch" for f in pooled)
    assert "pooled" in pooled[0]["reading"]


def test_a_cold_slice_is_reported_but_never_enforced():
    """Underselling ourselves leaves money on the table; it does not lose
    any. Reported, colored differently, never a veto."""
    cold = recs("mlb", "home_runs", {"side": "OVER"}, 0.35, 55, 100)
    out = lp.mine(CLEAN + cold)
    f = [f for f in out["findings"]
         if f["market"] == "home_runs" and f["dim"] == "side"]
    assert f and f[0]["action"] == "watch" and f[0]["gap_pts"] < 0
    assert "ran cold" in f[0]["reading"]
    assert out["closed"] == []


def test_fdr_holds_when_one_signal_hides_among_many_nulls():
    records = list(CLEAN + HOT)
    for i in range(8):        # eight more calibrated slices join the family
        records += recs("mlb", f"mkt{i}", {"side": "OVER"}, 0.55, 55, 100)
    out = lp.mine(records)
    assert [f["market"] for f in out["closed"]] == ["hits"]
    for f in out["findings"]:
        assert f["q"] >= f["p"]       # the correction never flatters a test


# --- the bands: one definition for miner and veto ----------------------------
def test_odds_bands_split_at_the_prices_bettors_argue_about():
    assert lp.odds_band(-150) == "heavy favorites (-150 and shorter)"
    assert lp.odds_band(-149) == "modest favorites (-149 to -106)"
    assert lp.odds_band(-105) == "near even money"
    assert lp.odds_band(105) == "near even money"
    assert lp.odds_band(106) == "underdogs (+106 to +199)"
    assert lp.odds_band(200) == "long shots (+200 and longer)"
    assert lp.odds_band(None) is None and lp.odds_band("x") is None


def test_prob_bands_and_their_guardrails():
    assert lp.prob_band(0.49) == "stated under 50%"
    assert lp.prob_band(0.50) == "stated 50s"
    assert lp.prob_band(0.60) == "stated 60s"
    assert lp.prob_band(0.70) == "stated 70%+"
    assert lp.prob_band(0.0) is None and lp.prob_band(1.0) is None


def test_horizon_bands():
    assert lp.horizon_band(0) == "same-day"
    assert lp.horizon_band(3) == "1-3 days out"
    assert lp.horizon_band(4) == "4+ days out"
    assert lp.horizon_band(None) is None


def test_features_of_drops_what_it_cannot_band():
    f = lp.features_of(side="under", odds=None, prob=0.62, book="",
                       horizon_days=None)
    assert f == {"side": "UNDER", "prob": "stated 60s"}


def test_the_veto_bands_a_pick_exactly_as_the_miner_banded_the_record():
    """Behavioral, not a source pin: a slice mined at -160 must veto a new
    pick at -155, because both land in the same band through the same
    function. Two banding copies would drift and enforce phantom slices."""
    records = CLEAN + recs(
        "mlb", "hits",
        {"odds": lp.odds_band(-160)}, 0.65, 45, 100)
    path = tempfile.mktemp(suffix=".json")
    lp.save(lp.mine(records), path)
    assert lp.veto("mlb", "hits", odds=-155, path=path) is not None
    assert lp.veto("mlb", "hits", odds=-120, path=path) is None


# --- the journal reader ------------------------------------------------------
def _seed(conn, rows):
    for r in rows:
        conn.execute(
            "INSERT INTO bets (ts, sport, date, player, market, side, line,"
            " book, odds, hit_prob, status, category) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", r)
    conn.commit()


def test_records_from_ledger_reads_grades_and_skips_what_it_must():
    conn = ledger.connect(":memory:")
    _seed(conn, [
        ("2026-08-01T10:00:00", "mlb", "2026-08-01", "A", "hits", "OVER",
         1.5, "dk", -120, 0.61, "won", "main"),
        ("2026-08-01T10:00:00", "mlb", "2026-08-03", "B", "hits", "UNDER",
         1.5, "fd", 110, 0.55, "lost", "main"),
        ("2026-08-01T10:00:00", "mlb", "2026-08-01", "C", "hits", "OVER",
         1.5, "dk", -120, 0.61, "push", "main"),      # says nothing
        ("2026-08-01T10:00:00", "mlb", "2026-08-01", "D", "hits", "OVER",
         1.5, "dk", -120, 0.61, "open", "main"),      # not graded yet
        ("2026-08-01T10:00:00", "mlb", "2026-08-01", "E", "hits", "OVER",
         1.5, "dk", -120, None, "won", "main"),       # no claim to test
    ])
    out = lp.records_from_ledger(conn)
    assert len(out) == 2
    a, b = out
    assert a["won"] == 1 and b["won"] == 0
    assert a["feats"]["horizon"] == "same-day"
    assert b["feats"]["horizon"] == "1-3 days out"
    assert a["feats"]["odds"] == "modest favorites (-149 to -106)"
    assert b["feats"]["book"] == "fd"


def test_refresh_mines_and_persists_where_the_veto_reads():
    conn = ledger.connect(":memory:")
    rows = []
    for i in range(60):
        rows.append(("2026-08-01T10:00:00", "mlb", "2026-08-01", f"P{i}",
                     "hits", "UNDER", 1.5, "dk", -120, 0.65,
                     "won" if i < 27 else "lost", "main"))
    _seed(conn, rows)
    path = tempfile.mktemp(suffix=".json")
    out = lp.refresh(conn, path)
    assert out["closed"], "said 65% hitting 45% over 60 bets must close"
    assert lp.veto("mlb", "hits", side="UNDER", path=path)
    assert lp.veto("mlb", "hits", side="OVER", path=path) is None


def test_default_path_is_read_at_call_time_not_frozen_at_import():
    keep = lp.DEFAULT_PATH
    try:
        lp.DEFAULT_PATH = tempfile.mktemp(suffix=".json")
        lp.save({"closed": [{"sport": "mlb", "market": "hits",
                             "dim": "side", "value": "UNDER",
                             "reading": "test"}]})
        assert lp.veto("mlb", "hits", side="UNDER") is not None
    finally:
        lp.DEFAULT_PATH = keep


def test_a_missing_or_garbage_store_never_vetoes_and_never_raises():
    assert lp.veto("mlb", "hits", side="UNDER",
                   path=tempfile.mktemp()) is None
    bad = tempfile.mktemp(suffix=".json")
    open(bad, "w").write("{not json")
    assert lp.veto("mlb", "hits", side="UNDER", path=bad) is None


# --- the wiring --------------------------------------------------------------
def test_the_mlb_gate_consults_the_miner_beside_the_calibration_gate():
    src = open(os.path.join(ROOT, "engine", "mlb", "betting.py"),
               encoding="utf-8").read()
    assert "lp_veto(\"mlb\", prop.market" in src
    i = src.index("gate_ok = ")
    assert "pattern_block is None" in src[i:i + 200]
    assert "reasons.insert(0, pattern_block)" in src


def test_every_settle_pass_re_mines_the_journal():
    maint = open(os.path.join(ROOT, "engine", "maintenance.py"),
                 encoding="utf-8").read()
    fn = maint[maint.index("def settle_open("):]
    assert "losspatterns" in fn and "refresh(lconn)" in fn
    launch = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    assert "losspatterns.refresh(lconn)" in launch


def test_the_block_ships_in_the_record_export_and_cannot_sink_it():
    src = open(os.path.join(ROOT, "engine", "ledger.py"),
               encoding="utf-8").read()
    assert '"loss_patterns": _loss_patterns_block(conn)' in src
    conn = ledger.connect(":memory:")
    block = ledger._loss_patterns_block(conn)
    assert block["findings"] == [] and block["closed"] == []


def test_the_page_renders_the_miner_with_its_discipline_stated():
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    i = app.index("function recLossPatternsSection(")
    fn = app[i:app.find("\nfunction ", i + 1)]
    for needle in ("Learning from losses", "Record mined", "Slices tested",
                   "Patterns found", "Self-closed", "vetoing picks",
                   "How this avoids fake trends", "The bar stays."):
        assert needle in fn, needle
    # Empty is a designed state, in both flavors: scanned-and-clean, and
    # not-enough-data — a fresh journal must read as honest, not broken.
    assert "nothing survives" in fn and "Not enough graded bets" in fn
    assert 'if (!lp || !(lp.n_records ?? 0)) return ""' in fn
    # EVERY scope, filtered to the sport being viewed — with its own
    # clean-sheet reading so an empty filter is a verdict, not a blank.
    assert "recLossPatternsSection(d.loss_patterns, scoped ? scope : null)" \
        in app
    assert 'scoped ? "" : recLossPatternsSection' not in app
    assert "No pattern involves" in fn



# --- the preview: a closure is a pricing change, so it must be readable ------
def test_the_preview_names_which_bar_a_closure_crossed():
    """A slice that closes on three points contradicts the documented
    five-point rule unless the reading says the relative bar fired."""
    r = lp.mine(recs("mlb", "home_runs", {"side": "over"}, 0.15, 228, 1900))
    text = lp._format(r)
    assert "the relative bar" in text
    assert "WOULD CLOSE: 1" in text
    assert "every new pick landing here is refused" in text


def test_the_preview_writes_nothing_and_says_so():
    r = lp.mine(recs("mlb", "home_runs", {"side": "over"}, 0.15, 228, 1900))
    text = lp._format(r)
    assert "Nothing above has been written" in text
    assert "--apply" in text


def test_an_empty_journal_is_not_reported_as_a_clean_one():
    """Opposite meanings, identical table. `tested` is what tells them
    apart — a machine with no ledger must not read as a model that
    survived scrutiny."""
    empty = lp._format(lp.mine([]))
    assert "Nothing was TESTED" in empty
    assert "not a verdict about the model" in empty
    assert "survived false-discovery control" not in empty

    # …and a journal that WAS tested and came back clean still says so.
    clean = lp.mine(recs("mlb", "strikeouts", {"side": "over"}, 0.58, 232, 400))
    assert clean["tested"] > 0
    assert "Nothing survived false-discovery control" in lp._format(clean)


def test_a_sport_filter_never_narrows_what_gets_enforced():
    """Filtering is a reading convenience. If it could reach the store the
    veto loads, looking at one sport would silently un-close another."""
    import inspect
    src = inspect.getsource(lp.main)
    assert "shown[\"findings\"]" in src, "the filter must build a COPY"
    assert "save(result)" in src, "…and --apply must persist the full result"
    assert "save(shown)" not in src


def test_the_pooled_slice_stays_watch_in_the_preview():
    """The guard that predates the relative bar, seen through the output
    a human actually reads."""
    r = lp.mine(recs("mlb", "home_runs", {"side": "over"}, 0.15, 228, 1900))
    pooled = [f for f in r["findings"] + r["restatements"]
              if f["market"] is None]
    assert pooled and all(f["action"] == "watch" for f in pooled)
    assert "(all markets)" in lp._format(r)



# --- one fault seen twice is one fault --------------------------------------
def test_nested_slices_collapse_to_the_tightest_true_statement():
    """Ten "patterns" came out of the real journal and they were not ten
    facts: home_runs is 1,863 of the 2,434 rows in "all markets OVER". The
    same bets under a wider label are a restatement, not evidence."""
    rows = recs("mlb", "home_runs", {"side": "OVER", "prob_band": "10-20%"},
                0.15, 228, 1900)
    out = lp.mine(rows)
    assert len(out["findings"]) == 1, out["findings"]
    assert len(out["restatements"]) == 3
    for e in out["restatements"]:
        assert e["restates"] == "mlb:home_runs:prob_band=10-20%" \
            or e["restates"].startswith("mlb:home_runs:")


def test_a_restatement_says_what_it_restates():
    out = lp.mine(recs("mlb", "home_runs", {"side": "OVER",
                                            "prob_band": "10-20%"},
                       0.15, 228, 1900))
    assert all("restates" in e for e in out["restatements"])
    assert "RESTATEMENTS of the above" in lp._format(out)


def test_two_genuinely_separate_faults_both_survive():
    """The dedupe must not swallow a distinct finding. Different markets
    share no rows, so neither can restate the other."""
    a = recs("mlb", "home_runs", {"side": "OVER"}, 0.15, 228, 900)
    b = recs("mlb", "hits", {"side": "UNDER"}, 0.60, 240, 500)
    out = lp.mine(a + b)
    markets = {f["market"] for f in out["findings"]}
    assert {"home_runs", "hits"} <= markets, out["findings"]


def test_the_dedupe_never_narrows_the_veto():
    """The fault the first cut of this shipped. Two slices can cover the
    IDENTICAL rows and still enforce differently — closing prob_band=10-20%
    refuses props in that band, closing side=over refuses every over. Same
    evidence, different forward scope. Dropping one as a restatement would
    silently change pricing as a side effect of a counting fix."""
    out = lp.mine(recs("mlb", "home_runs", {"side": "OVER",
                                            "prob_band": "10-20%"},
                       0.15, 228, 1900))
    closed_dims = {(f["dim"], f["value"]) for f in out["closed"]}
    assert ("side", "OVER") in closed_dims
    assert ("prob_band", "10-20%") in closed_dims
    # …and the restated ones are still enforceable, not just reported
    assert len(out["closed"]) > len(out["findings"])


def test_the_bh_correction_is_untouched_by_the_dedupe():
    """Overlapping slices are positively dependent, a case BH is valid
    for, so every one of these was correctly TESTED. The fault was only in
    the counting, and a future reader must not 'fix' the statistics too."""
    import inspect
    src = inspect.getsource(lp._dedupe)
    assert "does NOT touch the BH correction" in src
    out = lp.mine(recs("mlb", "home_runs", {"side": "OVER",
                                            "prob_band": "10-20%"},
                       0.15, 228, 1900))
    assert out["tested"] == 4        # every slice still entered the correction


# --- which book convicted it ------------------------------------------------
def test_a_finding_records_the_categories_that_convicted_it():
    """The journal is 227 `main` bets against 3,134 pooled, and selcheck
    measured those populations 13 points apart in calibration. A finding
    has to say which book it came from."""
    rows = [dict(r, category="longshot") for r in
            recs("mlb", "home_runs", {"side": "OVER"}, 0.15, 228, 1900)]
    out = lp.mine(rows)
    f = out["findings"][0]
    assert f["categories"] == {"longshot": 1.0}
    assert f.get("measured_on") == "longshot"


def test_a_closure_convicted_on_paper_bets_says_the_block_lands_elsewhere():
    """The veto runs at pricing time on every candidate prop, but its
    consequence is felt on the ones that would have become recommendations.
    A slice that is all `longshot` rows convicting the board is worth
    saying out loud."""
    rows = [dict(r, category="longshot") for r in
            recs("mlb", "home_runs", {"side": "OVER"}, 0.15, 228, 1900)]
    out = lp.mine(rows)
    assert "the block lands on recommendations" in out["closed"][0]["reading"]


def test_a_main_slice_gets_no_such_caveat():
    rows = [dict(r, category="main") for r in
            recs("mlb", "total_bases", {"side": "OVER"}, 0.60, 500, 1000)]
    out = lp.mine(rows)
    hot = [f for f in out["findings"] + out["restatements"]
           if f["action"] == "close"]
    assert hot, "fixture must produce a closure"
    assert all("lands on recommendations" not in f["reading"] for f in hot)


def test_a_mixed_slice_is_not_labelled_as_one_book():
    """80% is the bar. A slice drawing on several books is a statement
    about the board and needs no caveat."""
    rows = [dict(r, category="main" if i % 2 else "loose") for i, r in
            enumerate(recs("mlb", "home_runs", {"side": "OVER"},
                           0.15, 228, 1900))]
    out = lp.mine(rows)
    assert out["findings"][0].get("measured_on") is None


def test_the_record_stays_json_serialisable():
    """The row-membership sets exist only to compute the dedupe. Leaving
    one in the result would make save() raise on a set."""
    import json
    out = lp.mine(recs("mlb", "home_runs", {"side": "OVER"}, 0.15, 228, 900))
    json.dumps(out)
    for f in out["findings"] + out["restatements"]:
        assert "_rows" not in f

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
