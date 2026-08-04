"""The hypothesis lab: the LLM proposes, the arithmetic disposes.

What must stay true, pinned: the model's one power is naming slice
INTERSECTIONS (the miner's single-dimension sweep is provably blind to
them — the first test constructs such a world); its proposals are
constrained to the miner's own menu; the tribunal is the same z + BH
discipline as everything else; closure demands confirmed AND hot AND
market-specific; enforcement flows only through losspatterns.veto, the
gate every sport already consults; the nightly retest re-earns every
confirmation for free; and the paid call is one structured-output
request to the current API shape — offline-tested against canned
payloads, because the wire is the only part a test cannot own.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import hypotheses as hyp                          # noqa: E402
from engine import ledger                                     # noqa: E402
from engine import losspatterns as lp                         # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEAVY = lp.odds_band(-160)
DOG = lp.odds_band(150)


def _recs(feats, said, wins, n, sport="mlb", market="hits"):
    return [{"sport": sport, "market": market, "prob": said,
             "won": 1 if i < wins else 0, "feats": dict(feats)}
            for i in range(n)]


def _intersection_world():
    """Each single dimension is perfectly calibrated; the cross-cells are
    not. The miner MUST see nothing here — that blindness is the lab's
    reason to exist."""
    return (_recs({"side": "UNDER", "odds": HEAVY}, 0.65, 45, 100)
            + _recs({"side": "UNDER", "odds": DOG}, 0.65, 85, 100)
            + _recs({"side": "OVER", "odds": HEAVY}, 0.65, 85, 100)
            + _recs({"side": "OVER", "odds": DOG}, 0.65, 45, 100))


def _hyp(dims, sport="mlb", market="hits", claim="c"):
    return {"claim": claim, "rationale": "r", "sport": sport,
            "market": market, "dims": dims}


# --- the value-add, proven ---------------------------------------------------
def test_the_miner_is_blind_to_intersections_and_the_tribunal_is_not():
    world = _intersection_world()
    assert lp.mine(world)["findings"] == []
    tested = hyp.tribunal([_hyp({"side": "UNDER", "odds": HEAVY})], world)
    h = tested[0]
    assert h["status"] == "confirmed" and h["action"] == "close"
    assert h["test"]["gap_pts"] == 20.0
    assert "vetoed" in h["reading"]


def test_a_cold_confirmation_watches_and_never_closes():
    tested = hyp.tribunal([_hyp({"side": "UNDER", "odds": DOG})],
                          _intersection_world())
    assert tested[0]["status"] == "confirmed"
    assert tested[0]["action"] == "watch"


def test_a_marketless_hypothesis_may_watch_but_never_close():
    """Same conviction rule as the miner: pooled slices point, specific
    slices convict."""
    world = (_recs({"side": "UNDER", "odds": HEAVY}, 0.65, 45, 60)
             + _recs({"side": "UNDER", "odds": HEAVY}, 0.65, 45, 60,
                     market="total_bases"))
    tested = hyp.tribunal([_hyp({"side": "UNDER", "odds": HEAVY},
                                market=None)], world)
    assert tested[0]["status"] == "confirmed"
    assert tested[0]["action"] == "watch"


def test_below_the_floor_is_collecting_not_a_verdict():
    tested = hyp.tribunal([_hyp({"side": "UNDER", "book": "nowhere"})],
                          _intersection_world())
    assert tested[0]["status"] == "collecting"
    assert tested[0]["action"] is None and tested[0]["n"] == 0


def test_the_family_is_corrected_together():
    world = _intersection_world()
    hyps = [_hyp({"side": "UNDER", "odds": HEAVY}),
            _hyp({"side": "OVER", "odds": DOG}),
            _hyp({"side": "UNDER", "odds": DOG})]
    tested = hyp.tribunal(hyps, world)
    for h in tested:
        if h.get("test"):
            # q >= p up to the store's 4-decimal rounding of q.
            assert h["test"]["q"] + 5e-5 >= h["test"]["p"]


# --- the menu is the law -----------------------------------------------------
PACK = {"menu": {"side": ["UNDER"], "odds": [HEAVY]}, "sports": ["mlb"],
        "markets": [{"sport": "mlb", "market": "hits"}]}


def _raw(**over):
    h = {"claim": "c", "rationale": "r", "sport": "mlb", "market": "hits",
         "side": "UNDER", "odds": None, "prob": None, "horizon": None,
         "book": None}
    h.update(over)
    return {"hypotheses": [h], "watchlist": []}


def test_validation_admits_only_menu_values():
    ok, _ = hyp.validate(_raw(), PACK)
    assert len(ok) == 1 and ok[0]["dims"] == {"side": "UNDER"}
    for bad in (_raw(side="SIDEWAYS"),              # invented value
                _raw(sport="cricket"),              # unknown sport
                _raw(market="quidditch"),           # unknown market
                _raw(side=None)):                   # a slice of everything
        assert hyp.validate(bad, PACK)[0] == [], bad


def test_validation_caps_count_and_text_length():
    raw = {"hypotheses": [dict(_raw()["hypotheses"][0],
                               claim="x" * 999)] * 20,
           "watchlist": ["w"] * 20}
    ok, watch = hyp.validate(raw, PACK)
    assert len(ok) <= hyp.MAX_HYPOTHESES
    assert len(ok[0]["claim"]) <= 200 and len(watch) <= 5


# --- the wire, offline -------------------------------------------------------
def test_the_response_parser_handles_every_stop_state():
    good = {"stop_reason": "end_turn",
            "content": [{"type": "text",
                         "text": '{"hypotheses": [], "watchlist": []}'}],
            "usage": {"input_tokens": 10, "output_tokens": 5}}
    out, usage = hyp._parse_response(good)
    assert out == {"hypotheses": [], "watchlist": []}
    assert usage["input_tokens"] == 10
    for payload in (
        {"stop_reason": "refusal", "content": []},
        {"stop_reason": "end_turn",
         "content": [{"type": "text", "text": "not json"}]},
        {"stop_reason": "max_tokens",
         "content": [{"type": "text", "text": "{}"}]},
    ):
        try:
            hyp._parse_response(payload)
            raise AssertionError(payload)
        except hyp.HypothesisUnavailable:
            pass


def test_the_request_matches_the_current_api_contract():
    """claude-opus-5 by default, structured outputs via output_config,
    no sampling parameters (they 400 on this model family)."""
    assert hyp.DEFAULT_MODEL == "claude-opus-5"
    src = open(os.path.join(ROOT, "engine", "hypotheses.py"),
               encoding="utf-8").read()
    assert '"output_config": {"format": {"type": "json_schema"' in src
    assert '"anthropic-version"' in src
    for banned in ('"temperature"', '"top_p"', '"top_k"',
                   '"budget_tokens"'):
        assert banned not in src, banned
    # The schema is strict: every object closed, every field required.
    assert hyp.SCHEMA["additionalProperties"] is False


def test_no_key_degrades_with_instructions_not_a_crash():
    # Popping the env var is not enough: _api_key() reloads secrets.local,
    # which on a real machine HOLDS the key and quietly puts it back — so
    # this test passed on dev checkouts and failed exactly where the key
    # was plugged in. Mark the file already-loaded so the pop sticks.
    from engine import secrets as _sec
    keep = os.environ.pop("ANTHROPIC_API_KEY", None)
    was_loaded = _sec._loaded
    _sec._loaded = True
    try:
        conn = ledger.connect(":memory:")
        try:
            hyp.propose(conn)
            raise AssertionError("must raise without a key")
        except hyp.HypothesisUnavailable as e:
            assert "secrets.local" in str(e)
    finally:
        _sec._loaded = was_loaded
        if keep is not None:
            os.environ["ANTHROPIC_API_KEY"] = keep


# --- the store, the retest, the gate -----------------------------------------
def test_merge_keeps_the_original_proposal_date():
    a = dict(_hyp({"side": "UNDER"}), first_proposed="2026-07-01")
    store = {"hypotheses": [a]}
    merged = hyp.merge(store, [_hyp({"side": "UNDER"})], [], {})
    assert merged["hypotheses"][0]["first_proposed"] == "2026-07-01"
    assert len(merged["hypotheses"]) == 1          # same slice, one row


def test_retest_re_earns_status_as_the_journal_grows():
    conn = ledger.connect(":memory:")
    path = tempfile.mktemp(suffix=".json")
    hyp.save({"hypotheses": [dict(_hyp({"side": "UNDER", "odds": HEAVY}),
                                  first_proposed="2026-08-01")]}, path)
    st = hyp.retest(conn, path)                    # empty journal
    assert st["hypotheses"][0]["status"] == "collecting"
    for i in range(60):                            # said 65%, hits 45%
        conn.execute(
            "INSERT INTO bets (ts, sport, date, player, market, side, line,"
            " book, odds, hit_prob, status, category) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("2026-08-01T10:00:00", "mlb", f"2026-07-{i % 28 + 1:02d}",
             f"P{i}", "hits", "UNDER", 1.5, "dk", -160, 0.65,
             "won" if i < 27 else "lost", "main"))
    conn.commit()
    st = hyp.retest(conn, path)
    h = st["hypotheses"][0]
    assert h["status"] == "confirmed" and h["action"] == "close"
    assert h["first_proposed"] == "2026-08-01"     # identity survives


def test_enforcement_flows_only_through_the_shared_gate():
    """losspatterns.veto is the one door every sport's engine consults —
    a confirmed hot hypothesis blocks through it, with the claim named."""
    world = _intersection_world()
    tested = hyp.tribunal([_hyp({"side": "UNDER", "odds": HEAVY},
                                claim="unders on chalk run hot")], world)
    path = tempfile.mktemp(suffix=".json")
    hyp.save({"hypotheses": tested}, path)
    keep = hyp.DEFAULT_PATH
    hyp.DEFAULT_PATH = path
    empty_lp = tempfile.mktemp(suffix=".json")
    try:
        got = lp.veto("mlb", "hits", side="UNDER", odds=-155, path=empty_lp)
        assert got and "unders on chalk" in got
        assert lp.veto("mlb", "hits", side="UNDER", odds=150,
                       path=empty_lp) is None      # cold cell passes
        assert lp.veto("mlb", "total_bases", side="UNDER", odds=-155,
                       path=empty_lp) is None      # other market passes
    finally:
        hyp.DEFAULT_PATH = keep


# --- the pack: every sport, deterministic ------------------------------------
def test_the_evidence_pack_covers_every_journaled_sport():
    conn = ledger.connect(":memory:")
    rows = []
    for i in range(10):
        rows.append(("2026-08-01T10:00:00", "mlb", f"2026-07-{i+1:02d}",
                     f"A{i}", "hits", "OVER", 1.5, "dk", -120, 0.6,
                     "won", "main"))
        rows.append(("2026-08-01T10:00:00", "wnba", f"2026-07-{i+1:02d}",
                     f"B{i}", "pts", "UNDER", 14.5, "fd", 110, 0.55,
                     "lost", "main"))
    for r in rows:
        conn.execute(
            "INSERT INTO bets (ts, sport, date, player, market, side, line,"
            " book, odds, hit_prob, status, category) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", r)
    conn.commit()
    pack = hyp.evidence_pack(conn, lp_store={})
    assert pack["sports"] == ["mlb", "wnba"]
    assert {(m["sport"], m["market"]) for m in pack["markets"]} == \
        {("mlb", "hits"), ("wnba", "pts")}
    assert "UNDER" in pack["menu"]["side"] and HEAVY not in pack["menu"]["odds"]
    assert len(json.dumps(pack)) <= hyp.MAX_PACK_CHARS


# --- the wiring --------------------------------------------------------------
def test_the_free_retest_runs_on_every_settle_pass():
    maint = open(os.path.join(ROOT, "engine", "maintenance.py"),
                 encoding="utf-8").read()
    assert "hypotheses.retest(lconn)" in \
        maint[maint.index("def settle_open("):]
    launch = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    assert "hypotheses.retest(lconn)" in launch


def test_the_lab_ships_in_the_record_export_without_calling_any_api():
    src = open(os.path.join(ROOT, "engine", "ledger.py"),
               encoding="utf-8").read()
    assert '"hypothesis_lab": _hypothesis_lab_block()' in src
    fn = src[src.index("def _hypothesis_lab_block("):
             src.index("def _loss_patterns_block(")]
    assert "call" not in fn and "urllib" not in fn   # store-read only


def test_the_page_renders_the_lab_with_the_authority_stated():
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    i = app.index("function recHypothesisLab(")
    fn = app[i:app.find("\nfunction ", i + 1)]
    for needle in ("The hypothesis lab", "Confirmed", "Rejected",
                   "Collecting", "Vetoing", "vetoing picks",
                   "Why the AI only proposes",
                   "nothing an AI writes here can ever set a probability"):
        assert needle in fn, needle
    assert 'scoped ? "" : recHypothesisLab(d.hypothesis_lab)' in app


def test_the_cli_is_the_only_paid_step():
    src = open(os.path.join(ROOT, "hypotheses.py"), encoding="utf-8").read()
    for needle in ("--show", "--retest", "--dry-run", "PRICE_IN",
                   "secrets.local"):
        assert needle in src, needle


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
