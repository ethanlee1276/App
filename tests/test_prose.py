"""The prose lanes: the LLM narrates, the arithmetic decides.

Three lanes and one law. The nightly postmortem and the weekly brief run
themselves from the settle pass; the triage bench is CLI-only. Nothing
here may set a probability, spend past the monthly cap automatically, or
skip a sport — Ethan's requirement is every sport we offer (mlb, nba,
wnba, nfl, cfb, ufc), and coverage is enforced structurally rather than
hoped for from the model's mood.
"""

import datetime
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import ledger
from engine import prose as P

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TODAY = datetime.date.today().isoformat()


def _journal():
    """Graded picks across three sports on one night, plus traps: an open
    bet, a sampler row, and an NFL bet under a week label."""
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))

    def bet(sport, player, date=TODAY, status="won", cat="main", pnl=0.45):
        conn.execute(
            "INSERT INTO bets (sport,date,player,market,side,line,odds,"
            "grade,stake_units,status,category,pnl_units,hit_prob) VALUES "
            "(?,?,?,'hits','OVER',1.5,-110,'B',0.5,?,?,?,0.6)",
            (sport, date, player, status, cat, pnl))

    bet("mlb", "Bat One")
    bet("mlb", "Bat Two", status="lost", pnl=-0.5)
    bet("wnba", "Guard One")
    bet("ufc", "Fighter One", status="lost", pnl=-0.5)
    bet("mlb", "Still Open", status="open", pnl=0)
    bet("mlb", "Sampler Row", status="won", cat="stale")
    bet("nfl", "Week Label", date="2026-W1")
    conn.commit()
    return conn


def _tmp(name):
    return os.path.join(tempfile.mkdtemp(), name)


CANNED = {"headline": "A split night", "overall": "Some won, some lost.",
          "by_sport": [{"sport": "mlb", "note": "The bats split."},
                       {"sport": "cricket", "note": "off-pack, dropped"}]}


# --- the pack: every sport that graded, none that didn't ---------------------
def test_the_pack_covers_every_sport_that_graded_that_night():
    pack = P.postmortem_pack(_journal(), TODAY)
    assert pack["sports"] == ["mlb", "ufc", "wnba"]
    assert pack["by_sport"]["mlb"]["graded"] == 2
    assert pack["by_sport"]["mlb"]["won"] == 1


def test_open_bets_and_sampler_rows_are_not_narrated_as_wagers():
    pack = P.postmortem_pack(_journal(), TODAY)
    players = [p["player"] for p in pack["by_sport"]["mlb"]["picks"]]
    assert "Still Open" not in players
    assert "Sampler Row" not in players


def test_the_diary_date_never_chases_a_week_label():
    """NFL journals under "2026-W1", and "W" string-sorts above every
    digit — MAX(date) alone would send the nightly diary after a label
    that is not a night. Football's cadence belongs to the weekly brief."""
    conn = _journal()
    assert P.diary_date(conn) == TODAY


# --- coverage is structural, not the model's mood ----------------------------
def test_a_sport_the_model_skipped_is_backfilled_from_the_packs_numbers():
    pack = P.postmortem_pack(_journal(), TODAY)
    by = P._ensure_coverage(CANNED, pack["sports"], P._night_fallback(pack))
    assert set(by) == {"mlb", "ufc", "wnba"}          # cricket dropped
    assert by["mlb"] == "The bats split."
    assert "0-1" in by["ufc"] and "-0.50u" in by["ufc"]


def test_the_weekly_brief_pack_lists_every_tracked_sport():
    """Ethan's requirement, verbatim: mlb, nba, wnba, nfl, cfb, ufc —
    every sport we offer, every week, journaled or not."""
    pack = P.brief_pack(_journal())
    assert set(pack["sports"]) == {"mlb", "nfl", "cfb", "nba", "wnba", "ufc"}
    fb = P._week_fallback(pack)
    assert "Nothing journaled yet" in fb("cfb")
    by = P._ensure_coverage({"by_sport": []}, pack["sports"], fb)
    assert set(by) == set(pack["sports"])


# --- the guards: key, cap, cadence -------------------------------------------
def test_no_key_is_a_silent_skip_never_a_crash():
    from engine import secrets as _sec
    keep = os.environ.pop("ANTHROPIC_API_KEY", None)
    was = _sec._loaded
    _sec._loaded = True
    try:
        assert P.nightly(_journal(), log=lambda *a: None,
                         path=_tmp("pm.json")) == "no-key"
    finally:
        _sec._loaded = was
        if keep is not None:
            os.environ["ANTHROPIC_API_KEY"] = keep


def test_the_cap_stands_the_automatic_lane_down():
    keep_key = os.environ.get("ANTHROPIC_API_KEY")
    os.environ["ANTHROPIC_API_KEY"] = "sk-test"
    os.environ["QELLYS_LLM_CAP_USD"] = "0"
    called = []
    orig = P._call
    P._call = lambda *a, **k: called.append(1)
    try:
        out = P.nightly(_journal(), log=lambda *a: None, path=_tmp("pm.json"))
        assert out == "capped" and not called
    finally:
        P._call = orig
        del os.environ["QELLYS_LLM_CAP_USD"]
        if keep_key is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)


def test_one_entry_per_night_and_the_second_pass_is_free():
    keep_key = os.environ.get("ANTHROPIC_API_KEY")
    os.environ["ANTHROPIC_API_KEY"] = "sk-test"
    p = _tmp("pm.json")
    conn = _journal()
    calls = []
    orig = P._call
    P._call = lambda *a, **k: (calls.append(1), CANNED)[1]
    try:
        assert P.nightly(conn, log=lambda *a: None, path=p).startswith("done:")
        assert P.nightly(conn, log=lambda *a: None, path=p) == "already"
        assert len(calls) == 1
        stored = json.loads(open(p).read())
        assert set(stored[-1]["by_sport"]) == {"mlb", "ufc", "wnba"}
    finally:
        P._call = orig
        if keep_key is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)


def test_the_brief_holds_its_weekly_cadence():
    keep_key = os.environ.get("ANTHROPIC_API_KEY")
    os.environ["ANTHROPIC_API_KEY"] = "sk-test"
    p = _tmp("br.json")
    conn = _journal()
    calls = []
    orig = P._call
    P._call = lambda *a, **k: (calls.append(1), CANNED)[1]
    try:
        assert P.weekly(conn, log=lambda *a: None, path=p).startswith("done:")
        assert P.weekly(conn, log=lambda *a: None, path=p) == "already"
        assert len(calls) == 1
        stored = json.loads(open(p).read())
        assert set(stored[-1]["by_sport"]) == {"mlb", "nfl", "cfb", "nba",
                                               "wnba", "ufc"}
    finally:
        P._call = orig
        if keep_key is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)


def test_a_failed_call_returns_a_status_instead_of_raising():
    """The settle pass must never die on prose."""
    keep_key = os.environ.get("ANTHROPIC_API_KEY")
    os.environ["ANTHROPIC_API_KEY"] = "sk-test"
    orig = P._call

    def boom(*a, **k):
        raise P.ProseUnavailable("api down")
    P._call = boom
    try:
        assert P.nightly(_journal(), log=lambda *a: None,
                         path=_tmp("pm.json")) == "failed"
    finally:
        P._call = orig
        if keep_key is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)


# --- the meter, the contract, the doctrine -----------------------------------
def test_every_call_is_metered_before_it_is_parsed():
    import inspect
    src = inspect.getsource(P._call)
    assert "log_llm_spend" in src
    assert src.index("log_llm_spend") < src.index("json.loads(text)")


def test_the_request_carries_no_sampling_parameters():
    import inspect
    src = inspect.getsource(P._call)
    for banned in ('"temperature"', '"top_p"', '"top_k"', '"thinking"',
                   '"budget_tokens"'):
        assert banned not in src, banned


def test_the_schemas_are_strict():
    for schema in (P.SCHEMA_PROSE, P.SCHEMA_TRIAGE):
        assert schema["additionalProperties"] is False


def test_the_site_block_reads_stores_and_never_calls():
    import inspect
    src = inspect.getsource(P.site_block)
    assert "_call" not in src and "urllib" not in src
    block = P.site_block()                    # runs offline, no key needed
    assert "cap_usd" in block and "capped" in block


def test_the_export_ships_the_prose_block():
    src = open(os.path.join(ROOT, "engine", "ledger.py"),
               encoding="utf-8").read()
    assert '"prose": _prose_block(),' in src
    i = src.index("def _prose_block(")
    assert "site_block" in src[i:i + 600]


def test_both_settle_passes_run_the_lanes():
    for fname, needle in (("launch.py", "prose.nightly(lconn, print)"),
                          (os.path.join("engine", "maintenance.py"),
                           "prose.nightly(lconn, log)")):
        src = open(os.path.join(ROOT, fname), encoding="utf-8").read()
        assert needle in src, fname
        assert "prose.weekly" in src, fname


def test_the_page_renders_the_night_desk_on_every_scope():
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    i = app.index("function recProseSection(")
    fn = app[i:app.find("\nfunction ", i + 1)]
    for needle in ("The night desk", "never setting one", "by_sport",
                   "picks graded that night"):
        assert needle in fn, needle
    assert "recProseSection(d.prose, scoped ? scope : null)" in app
    assert "recProseSection(d.prose, scope)" in app, \
        "the empty-journal branch (the NFL until September) skips the desk"


def test_the_triage_bench_requires_a_watchlist():
    try:
        P.triage(_journal())
        raise AssertionError("must refuse without a watchlist")
    except P.ProseUnavailable as e:
        assert "hypotheses.py" in str(e)


def test_the_cap_is_configurable_and_survives_garbage():
    os.environ["QELLYS_LLM_CAP_USD"] = "12.5"
    try:
        assert P.cap_usd() == 12.5
        os.environ["QELLYS_LLM_CAP_USD"] = "not-a-number"
        assert P.cap_usd() == P.DEFAULT_CAP_USD
    finally:
        del os.environ["QELLYS_LLM_CAP_USD"]


def test_the_cli_offers_all_three_lanes_and_the_free_reader():
    src = open(os.path.join(ROOT, "prose.py"), encoding="utf-8").read()
    for needle in ("--postmortem", "--brief", "--triage", "--show",
                   "monthly cap"):
        assert needle in src, needle


def test_the_third_lane_is_recorded_in_the_recipe():
    doc = open(os.path.join(ROOT, "docs", "COMPETITIVE_RECIPE.md"),
               encoding="utf-8").read()
    assert "the third and final sanctioned lane: narrating" in doc
    assert "no LLM output is ever a probability, a stake, or a\ngate" in doc


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
