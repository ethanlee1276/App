"""The transparency pillar, and the two ways it can quietly stop being one.

The competitive study in docs/COMPETITIVE_RECIPE.md names this as the moat
competitors structurally cannot copy — a tool that sells picks cannot afford
to publish that most picks don't beat the close. A moat made of a promise is
not a moat, so these tests pin the promise to code:

  * both proper scoring rules are published, not just the gentler one;
  * the reliability diagram is a diagram — a curve against the diagonal —
    and not the bucket table wearing a chart's name;
  * the bad number ships too. Every branch that reports a score reports it
    whether or not we won, and there is no code path that hides a loss.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
DOC = open(os.path.join(ROOT, "docs", "COMPETITIVE_RECIPE.md"), encoding="utf-8").read()


def _fn(src: str, name: str) -> str:
    """One top-level function's body, by brace-free bracketing on the next
    top-level `function` keyword. Cheaper than parsing JS and sufficient
    here, where every function in this file is declared at column zero."""
    i = src.index(f"function {name}(")
    j = src.find("\nfunction ", i + 1)
    return src[i:j if j > 0 else len(src)]


def _flat(text: str) -> str:
    """Whitespace collapsed. Prose in a template literal wraps to fit the
    column, so a sentence worth asserting on routinely spans a line break —
    matching literally would fail on formatting rather than on meaning."""
    return " ".join(text.split())


# --- the numbers -------------------------------------------------------------
def test_both_proper_scoring_rules_reach_the_payload():
    from engine import ledger
    src = open(os.path.join(ROOT, "engine", "ledger.py"), encoding="utf-8").read()
    block = src[src.index("def calibration("):src.index("HEALTH_MIN_BETS")]
    for key in ("brier_model", "brier_market", "brier_edge",
                "logloss_model", "logloss_market", "logloss_edge", "ece"):
        assert f'"{key}"' in block, key
    assert hasattr(ledger, "LOGLOSS_CLAMP")


def test_log_loss_is_clamped_finite():
    """Unbounded at the ends: a 0% forecast on something that happened costs
    infinity, and one row would swallow the whole score."""
    from engine import ledger
    assert 0 < ledger.LOGLOSS_CLAMP < 0.01
    worst = ledger._log_loss_one(0.0, 1.0)
    assert worst == ledger._log_loss_one(ledger.LOGLOSS_CLAMP, 1.0)
    import math
    assert math.isfinite(worst)


def test_the_market_is_scored_on_the_same_bets_under_both_rules():
    """A score with nothing to beat is a number, not a claim. Brier already
    compared against the de-vigged close; log loss has to as well or it is
    decoration."""
    from engine import ledger
    src = open(os.path.join(ROOT, "engine", "ledger.py"), encoding="utf-8").read()
    block = src[src.index("def calibration("):src.index("HEALTH_MIN_BETS")]
    assert "ll_market += _log_loss_one(fair" in block
    assert "se_market += (fair - won) ** 2" in block


def test_ece_is_population_weighted():
    from engine import ledger
    src = open(os.path.join(ROOT, "engine", "ledger.py"), encoding="utf-8").read()
    block = src[src.index("def calibration("):src.index("HEALTH_MIN_BETS")]
    line = [l for l in block.splitlines() if 'b["actual"] - b["predicted"]' in l]
    assert line and 'b["n"] *' in line[0], line


# --- the picture -------------------------------------------------------------
def test_the_reliability_diagram_draws_the_diagonal():
    """The whole point of the chart. Predicted on x, realized on y, and the
    line y=x to measure the distance from. Without it this is a scatter plot
    of two numbers nobody can compare."""
    body = _fn(APP, "reliabilityDiagram")
    assert 'x1="${x(0)}" y1="${y(0)}" x2="${x(1)}" y2="${y(1)}"' in body
    assert "stroke-dasharray" in body
    assert "perfect" in body


def test_the_axes_are_labelled_in_english():
    body = _fn(APP, "reliabilityDiagram")
    assert "model said (%)" in body
    assert "actually hit (%)" in body


def test_dot_area_tracks_sample_size_not_dot_radius():
    """Radius scaling triples the apparent weight of a bucket that is three
    times bigger, which is the opposite of what a reader should take from
    it. Area is linear in n only if the radius goes as sqrt(n)."""
    body = _fn(APP, "reliabilityDiagram")
    assert "Math.sqrt(b.n / maxN)" in body


def test_the_whiskers_are_the_same_band_as_the_rows():
    """A dot whose interval crosses the diagonal has not missed — it has not
    spoken yet. Using a different band here than the rows above would have
    the same bucket read as a miss in one place and noise in the other."""
    body = _fn(APP, "reliabilityDiagram")
    assert "b.actual - b.ci" in body and "b.actual + b.ci" in body


def test_a_one_bucket_diagram_is_not_drawn():
    """Two points make a shape; one point makes a dot next to a line, which
    invites a reading the sample cannot support."""
    body = _fn(APP, "reliabilityDiagram")
    assert "pts.length < 2" in body


def test_the_diagram_is_rendered_on_the_record_page():
    body = _fn(APP, "recCalibrationSection")
    assert "reliabilityDiagram(cal.buckets)" in body
    # And the era-scoped chart gets one too — the current model is the one
    # anybody is actually deciding about.
    assert "reliabilityDiagram(era.buckets)" in body


# --- the promise -------------------------------------------------------------
def test_the_losing_number_ships_too():
    """The line that makes this a moat rather than marketing."""
    body = _flat(_fn(APP, "calScoreBlock"))
    assert "tout with a website" in body
    assert "either way" in body


def test_both_outcomes_have_a_rendered_branch():
    """No path returns empty when we lose. The score block builds one card
    per rule from the same template regardless of sign, and only a NULL
    edge — meaning no comparison exists at all — suppresses it."""
    rule = _fn(APP, "scoreRule")
    assert "if (edge == null) return" in rule
    assert re.search(r"edge\s*>\s*0", rule), "sign only picks a colour"
    # The one early return is the missing-data case, not the losing case.
    assert rule.count("return \"\"") == 1


def test_the_two_rules_disagreeing_is_explained_rather_than_hidden():
    """Both are strictly proper, so disagreement is a finding: the gap
    against the market lives in the confident calls. Silently showing two
    contradictory verdicts is worse than showing one."""
    body = _flat(_fn(APP, "calScoreBlock"))
    assert "(cal.brier_edge > 0) !== (cal.logloss_edge > 0)" in body
    assert "not a contradiction" in body


# --- the roadmap -------------------------------------------------------------
def test_the_recipe_carries_the_source_study_unedited():
    """A living roadmap that quietly rewrites its own source is a diary, not
    a record. The study is appended verbatim below our ledger."""
    assert "# Source study, preserved unedited" in DOC
    assert "Claw Arbs" in DOC and "Swish" in DOC


def test_the_guardrails_are_decisions_not_backlog():
    """These are the items that must never drift into 'not built yet'."""
    for phrase in ("No automated bet placement",
                   "No credential sharing",
                   "No IP, device or identity spoofing",
                   "No user betting data published"):
        assert phrase in DOC, phrase


def test_the_recipe_records_what_was_not_built():
    """The half of the file that makes it usable next month."""
    assert "## Not built today" in DOC
    assert "## What to distrust in the study" in DOC


# --- the splits (recipe #3) --------------------------------------------------
def _splitdb():
    import tempfile
    from engine import ledger
    conn = ledger.connect(tempfile.mktemp(suffix=".db"))
    return conn


def _add(conn, name, market, day_offset, p, won, ts_day="2026-07-01"):
    import datetime
    d = (datetime.date.fromisoformat(ts_day)
         + datetime.timedelta(days=day_offset)).isoformat()
    conn.execute(
        "INSERT INTO bets (ts,sport,date,player,market,side,line,book,odds,"
        "hit_prob,edge,status) VALUES (?,'mlb',?,?,?,'OVER',0.5,'DK',-110,?,"
        "0.05,?)", (ts_day + "T18:00:00", d, name, market, p,
                    "won" if won else "lost"))


def test_the_aggregate_hides_a_hot_market_and_the_split_finds_it():
    """The whole argument for this feature, as a measurement.

    Fifty picks at 60% that hit 60%, and fifty at 60% that hit 40%. The
    aggregate averages to something that looks nearly clean; the split shows
    one market on the diagonal and one twenty points off it."""
    from engine import ledger
    conn = _splitdb()
    for i in range(50):
        _add(conn, f"A{i}", "total_bases", 0, 0.60, i < 30)
    for i in range(50):
        _add(conn, f"B{i}", "strikeouts", 0, 0.60, i < 20)
    conn.commit()
    agg = ledger.calibration(conn)
    by = {m["market"]: m for m in ledger.calibration_splits(conn)["markets"]}
    assert abs(by["total_bases"]["ece"]) < 0.01
    assert by["strikeouts"]["ece"] > 0.15
    # And the aggregate sits between them, showing neither.
    assert agg["ece"] < by["strikeouts"]["ece"]


def test_a_thin_market_is_held_back_and_counted_not_dropped():
    """A row whose band is wider than any miss it could show reports noise
    with the authority of a measurement. But silently dropping it hides how
    much of the board the table is speaking for."""
    from engine import ledger
    conn = _splitdb()
    for i in range(50):
        _add(conn, f"A{i}", "total_bases", 0, 0.60, i < 30)
    for i in range(5):
        _add(conn, f"C{i}", "hits", 0, 0.60, i < 3)
    conn.commit()
    s = ledger.calibration_splits(conn)
    assert [m["market"] for m in s["markets"]] == ["total_bases"]
    assert s["markets_held_back"] == 1
    # The held-back picks are still in the headline number.
    assert ledger.calibration(conn)["n"] == 55


def test_one_horizon_bucket_reads_as_degenerate_rather_than_as_a_chart():
    """Everything resolving same-day is a true fact about how we bet. A bar
    chart with one bar implies a comparison that does not exist."""
    from engine import ledger
    conn = _splitdb()
    for i in range(50):
        _add(conn, f"A{i}", "total_bases", 0, 0.60, i < 30)
    conn.commit()
    assert ledger.calibration_splits(conn)["horizon_degenerate"] is True


def test_a_real_horizon_spread_is_not_degenerate():
    from engine import ledger
    conn = _splitdb()
    for i in range(50):
        _add(conn, f"A{i}", "total_bases", 0, 0.60, i < 30)
    for i in range(50):
        _add(conn, f"F{i}", "home_runs", 40, 0.30, i < 14)
    conn.commit()
    s = ledger.calibration_splits(conn)
    assert s["horizon_degenerate"] is False
    labels = [h["label"] for h in s["horizons"]]
    assert "Same day" in labels and "15+ days" in labels


def test_the_horizon_is_measured_in_whole_days_from_the_publish_DAY():
    """`ts` carries a time and `date` does not. Subtracting them raw makes a
    pick published at 6pm for tomorrow measure 0.75 days, which floors to
    zero and lands in the same-day bucket."""
    from engine import ledger
    assert "substr(ts, 1, 10)" in ledger._HORIZON_SQL
    conn = _splitdb()
    for i in range(45):
        _add(conn, f"T{i}", "total_bases", 1, 0.60, i < 27)
    conn.commit()
    s = ledger.calibration_splits(conn)
    got = {h["label"] for h in s["horizons"] if h["n"]}
    assert got == {"1–3 days"}, got


# --- the forecast log (recipe #4) --------------------------------------------
def _sealed(n=6):
    import datetime
    from engine import ledger
    conn = _splitdb()
    now = datetime.datetime.now().isoformat()
    for i in range(n):
        conn.execute(
            "INSERT INTO bets (ts,sport,date,player,market,side,line,book,"
            "odds,hit_prob,edge,status) VALUES (?,'mlb','2026-08-02',?,"
            "'hits','OVER',0.5,'DK',-110,0.6,0.05,'won')", (now, f"P{i}"))
    conn.commit()
    ledger.seal_forecasts(conn)
    return conn


def test_sealing_is_idempotent():
    """It runs every refresh. A second pass must add nothing."""
    from engine import ledger
    conn = _sealed()
    assert ledger.seal_forecasts(conn) == 0
    assert ledger.verify_forecast_log(conn)["n"] == 6


def test_an_edited_forecast_breaks_the_chain_at_that_row():
    """The point of the whole structure: you cannot quietly change what you
    said you believed."""
    from engine import ledger
    conn = _sealed()
    good = ledger.verify_forecast_log(conn)
    assert good["ok"] and good["head"]
    conn.execute("UPDATE forecast_log SET hit_prob=0.95 WHERE seq=3")
    conn.commit()
    bad = ledger.verify_forecast_log(conn)
    assert bad["ok"] is False
    assert bad["broken_at"] == 3
    # Everything BEFORE the break is still proven — that is why the report
    # names a row instead of returning a boolean.
    assert bad["verified_through"] == 2


def test_a_deleted_forecast_breaks_the_chain_too():
    """Deletion is the tout's move — drop the losers, keep the winners."""
    from engine import ledger
    conn = _sealed()
    conn.execute("DELETE FROM forecast_log WHERE seq=4")
    conn.commit()
    assert ledger.verify_forecast_log(conn)["ok"] is False


def test_restoring_the_edit_restores_the_same_head():
    """A hash chain that did not reproduce would make every alarm useless."""
    from engine import ledger
    conn = _sealed()
    head = ledger.verify_forecast_log(conn)["head"]
    conn.execute("UPDATE forecast_log SET hit_prob=0.95 WHERE seq=3")
    conn.commit()
    assert not ledger.verify_forecast_log(conn)["ok"]
    conn.execute("UPDATE forecast_log SET hit_prob=0.6 WHERE seq=3")
    conn.commit()
    v = ledger.verify_forecast_log(conn)
    assert v["ok"] and v["head"] == head


def test_the_log_holds_the_claim_and_never_the_outcome():
    """An outcome arrives after sealing. Storing it would mean writing into
    a row that is supposed to be frozen — which is the one thing the chain
    exists to make impossible."""
    from engine import ledger
    for banned in ("status", "actual", "pnl_units", "pnl_dollars",
                   "closing_line"):
        assert banned not in ledger.FORECAST_FIELDS, banned
    assert "hit_prob" in ledger.FORECAST_FIELDS
    src = open(os.path.join(ROOT, "engine", "ledger.py"), encoding="utf-8").read()
    i = src.index("_FORECAST_LOG = ")
    ddl = src[i:src.index('"""', src.index('"""', i) + 3)]
    for banned in ("pnl_units", "closing_line", "actual"):
        assert banned not in ddl, banned


def test_sealing_is_a_sweep_not_a_hook_on_each_insert():
    """There are eight-plus places that write a bet and a new one appears
    every time a sport does. A per-site hook is one somebody forgets, and a
    forecast log with a hole still looks complete."""
    src = open(os.path.join(ROOT, "engine", "ledger.py"), encoding="utf-8").read()
    fn = src[src.index("def seal_forecasts("):src.index("def verify_forecast_log(")]
    assert "LEFT JOIN forecast_log" in fn and "f.bet_id IS NULL" in fn
    assert "ORDER BY b.id" in fn, "an unordered sweep gives a nondeterministic head"
    launch = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    assert "_seal_forecasts(quiet=quiet)" in launch


def test_a_broken_chain_is_reported_loudly_on_the_page_and_the_console():
    """A tamper-evident log that hides its own alarm is decoration."""
    body = _flat(_fn(APP, "recForecastLog"))
    assert "Forecast log broken at" in body
    assert "still verify" in body
    launch = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    blk = launch[launch.index("def _seal_forecasts("):]
    blk = blk[:blk.index("\ndef ", 1)]
    assert "FORECAST LOG BROKEN" in blk


def test_the_head_hash_is_published():
    """Publishing it is what turns a private log into a public commitment."""
    src = open(os.path.join(ROOT, "engine", "ledger.py"), encoding="utf-8").read()
    assert '"forecast_log": (seal_forecasts(conn), verify_forecast_log(conn))[1]' in src
    assert "f.head" in APP


def test_a_missing_optional_field_cannot_blank_the_record_page():
    """The whole Record page is one template literal, so an uncaught throw
    in ANY section blanks EVERY section. A fixture without day_u proved it:
    recCurveChart called toFixed on undefined and the entire page died —
    calibration, health, parlays, all of it — over one derivable field in
    one tooltip. The chart now derives day_u from the running total when
    the payload omits it."""
    body = _fn(APP, "recCurveChart")
    assert "p.day_u != null" in body
    assert "curve[i - 1].cum_u" in body
    assert "p.day_u.toFixed" not in body


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
