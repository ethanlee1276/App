"""The learning loop, made visible — and kept honest.

The nightly refit already ran with no human in it: every settled bet feeds
``calibrate.fit``, a fit at its search boundary closes its own market, and
``calibhistory`` stamps each sweep with the commit that produced it. None
of that was on the site, and a learning loop nobody can see is
indistinguishable from a static model. These tests pin the block that
renders it — and pin the one decision that keeps "AI on the site" honest:
the numbers come from arithmetic over the journal, never from a language
model (the WON'T recorded in docs/COMPETITIVE_RECIPE.md).
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import calibrate as cal                           # noqa: E402
from engine import db as hist_db                              # noqa: E402
from engine import ledger                                     # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _fn(src: str, name: str) -> str:
    i = src.index(f"function {name}(")
    j = src.find("\nfunction ", i + 1)
    return src[i:j if j > 0 else len(src)]


FIXTURE = {
    "mlb:hits": {"temperature": 0.99, "intercept": 0.0, "samples": 655,
                 "brier_before": 0.2411, "brier_after": 0.241,
                 "market": "hits", "sport": "mlb"},
    "mlb:total_bases": {"temperature": 1.42, "intercept": 0.0, "samples": 412,
                        "brier_before": 0.2521, "brier_after": 0.2431,
                        "market": "total_bases", "sport": "mlb"},
    "mlb:home_runs": {"temperature": cal.GRID_MAX, "intercept": 0.1,
                      "samples": 388, "brier_before": 0.121,
                      "brier_after": 0.1205,
                      "market": "home_runs", "sport": "mlb"},
    "nfl:receptions": {"temperature": 0.80, "intercept": 0.0, "samples": 1204,
                       "brier_before": 0.2333, "brier_after": 0.2296,
                       "market": "receptions", "sport": "nfl"},
}


def _with_fixture(entries, fn):
    """Run fn() with calibrate.DEFAULT_PATH pointed at a throwaway file.

    The report reads the module attribute at call time — that is the point
    of it — so the repoint works, and the restore keeps every other test's
    view of the real path intact."""
    keep = cal.DEFAULT_PATH
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "calibration.json")
    if entries is not None:
        if isinstance(entries, str):
            open(path, "w").write(entries)
        else:
            json.dump(entries, open(path, "w"))
    cal.DEFAULT_PATH = path
    try:
        return fn()
    finally:
        cal.DEFAULT_PATH = keep


def _by_market(st):
    return {m["market"]: m for m in st["markets"]}


# --- the report reads the FILE, not load()'s runtime strip -------------------
def test_load_strips_the_record_so_the_report_reads_the_file():
    """calibrate.load() deliberately reduces the stored file to
    {key: (temperature, intercept)} — all the correction path needs. The
    first cut of this report went through load() and rendered every market
    as T=1.0 "clean" with its raw storage key for a name: every field read
    fell through to its default. The report reads the file save() wrote."""
    def check():
        stored = cal.load(cal.DEFAULT_PATH)
        assert isinstance(stored["mlb:hits"], tuple)      # the strip, pinned
        st = ledger.self_tuning_report(None)
        m = _by_market(st)["total_bases"]
        assert m["samples"] == 412
        assert m["brier_before"] == 0.2521 and m["brier_after"] == 0.2431
        assert m["sport"] == "mlb"
    _with_fixture(FIXTURE, check)


def test_each_temperature_reads_as_a_verdict_not_a_number():
    def check():
        by = _by_market(ledger.self_tuning_report(None))
        assert by["hits"]["reading"] == "clean"
        assert by["total_bases"]["reading"] == "ran hot — tempered toward 50%"
        assert by["receptions"]["reading"] == "ran shy — pushed outward"
        assert by["home_runs"]["reading"] == "closed by its own fit"
    _with_fixture(FIXTURE, check)


def test_a_boundary_fit_lands_in_the_closed_list():
    """The fitter wanting a bigger correction than the search allows is its
    own way of saying "unreliable here" — is_reliable() reads the same
    signal and the engines hard-pass the market. Nobody decided that; the
    fit did, and the page says so."""
    def check():
        st = ledger.self_tuning_report(None)
        assert st["closed"] == [{"sport": "mlb", "market": "home_runs"}]
        assert _by_market(st)["home_runs"]["at_boundary"] is True
        assert _by_market(st)["hits"]["at_boundary"] is False
    _with_fixture(FIXTURE, check)


def test_an_entry_missing_its_labels_parses_them_from_the_key():
    """Keys are "<sport>:<market>" by construction (calibrate.save), so an
    older entry that predates the label fields still names itself."""
    def check():
        st = ledger.self_tuning_report(None)
        m = st["markets"][0]
        assert (m["sport"], m["market"]) == ("nba", "points")
        assert m["samples"] == 0 and m["brier_before"] is None
    _with_fixture({"nba:points": {"temperature": 1.2}}, check)


def test_a_garbage_or_missing_file_yields_an_empty_report_not_a_raise():
    def check():
        st = ledger.self_tuning_report(None)
        assert st["markets"] == [] and st["closed"] == []
    _with_fixture("{not json", check)
    _with_fixture(None, check)          # no file at all
    def check_missing_refit():
        assert ledger.self_tuning_report(None)["last_refit"] is None
    _with_fixture(None, check_missing_refit)


# --- the trend: the same measurement over time, with causes attached ---------
def _seed_runs(conn, rows):
    for ts, code, sport, market, brier, ece in rows:
        conn.execute(
            "INSERT OR REPLACE INTO calibration_runs (ts, code, sport, market,"
            " n, brier, ece, base_rate, skill, hedged, bins, note) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (ts, code, sport, market, 500, brier, ece, 0.5, 0.1, 0.2, "[]", ""))
    conn.commit()


def test_improving_counts_markets_whose_ece_fell():
    def check():
        conn = hist_db.connect(":memory:")
        _seed_runs(conn, [
            ("2026-07-28T03:10:00.000001", "aaa", "mlb", "hits", 0.249, 0.031),
            ("2026-08-03T03:10:00.000001", "bbb", "mlb", "hits", 0.241, 0.019),
            ("2026-07-28T03:10:00.000002", "bbb", "mlb", "total_bases", 0.250, 0.024),
            ("2026-08-03T03:10:00.000002", "bbb", "mlb", "total_bases", 0.252, 0.028),
        ])
        st = ledger.self_tuning_report(conn)
        assert st["improving"] == 1 and st["tracked"] == 2
        tr = st["trend"]["mlb"]
        assert tr["hits"]["improved"] and not tr["hits"]["same_code"]
        assert not tr["total_bases"]["improved"]
    _with_fixture(FIXTURE, check)


def test_history_still_shows_when_no_calibration_file_exists():
    """A fresh checkout has sweeps in the DB before its first refit writes
    the file. The trend must not vanish with it — mlb is the default."""
    def check():
        conn = hist_db.connect(":memory:")
        _seed_runs(conn, [
            ("2026-08-03T03:10:00.000001", "aaa", "mlb", "hits", 0.249, 0.031)])
        st = ledger.self_tuning_report(conn)
        assert st["markets"] == []
        assert "hits" in st["trend"]["mlb"]
    _with_fixture(None, check)


# --- the wiring and the page -------------------------------------------------
def test_the_report_ships_in_the_record_export():
    src = open(os.path.join(ROOT, "engine", "ledger.py"),
               encoding="utf-8").read()
    assert '"self_tuning": _self_tuning_block()' in src


def test_the_page_renders_the_loop_and_only_on_the_full_record():
    fn = _fn(APP, "recSelfTuningSection")
    for needle in ("The model tunes itself", "Last refit", "Markets tuned",
                   "Self-closed", "Improving", "Is it getting better?"):
        assert needle in fn, needle
    # Scoped views (one sport's record) skip it: the loop is one system,
    # not a per-sport stat.
    assert 'scoped ? "" : recSelfTuningSection(d.self_tuning)' in APP


def test_an_empty_or_absent_block_renders_nothing_not_a_crash():
    fn = _fn(APP, "recSelfTuningSection")
    assert 'if (!st || !(st.markets || []).length) return ""' in fn
    # Field guards: a stale record.json without these fields must degrade,
    # not blank the page — the day_u lesson, applied before the bug.
    assert "(m.temperature ?? 1).toFixed" in fn
    assert "(m.samples ?? 0).toLocaleString" in fn


def test_the_page_explains_the_dial_in_both_directions():
    fn = _fn(APP, "recSelfTuningSection")
    flat = " ".join(fn.split())
    assert "ran hot" in flat and "ran shy" in flat


def test_the_no_chatbot_disclosure_matches_the_recorded_decision():
    """The section's own explanation must tie to the WON'T in the recipe —
    a page claiming a decision the docs don't record is marketing."""
    fn = _fn(APP, "recSelfTuningSection")
    assert "Why no chatbot sets these numbers" in fn
    doc = open(os.path.join(ROOT, "docs", "COMPETITIVE_RECIPE.md"),
               encoding="utf-8").read()
    assert "WON'T — a language model anywhere in the pricing path" in doc


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
