"""A Most Likely board for every sport — earned per market, per box.

Ethan, 2026-08-31: "We should have a most likely page for every sport…
We should dive deeper into getting the most likely page for MLB set up."

The founding rule survives the expansion: a market appears on the
likelihood board only after it has been SHOWN to rank. The NFL's numbers
were hand-measured constants; that cannot scale (the MLB logs never
leave the droplet, so this dev box literally cannot measure them). So
`engine.rankfit` measures walk-forward AUC per (sport, market) on the
box that holds the logs and stores it beside the calibrations, and
`likely.rank_auc` reads the store first. An MLB shelf turns on where the
measurement happened, and nowhere else.

Also fixed in passing and pinned here: the CFB board wore the NFL's
0.721 touchdown AUC — `from_watch` read a flat dict with no idea whose
chain built the row. College's own measured figure is 0.675.

Run directly: `python3 tests/test_mlb_likely.py`
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import boards, likely, rankfit


def _clear_store():
    try:
        os.remove(rankfit.STORE)
    except OSError:
        pass


# --- the AUC itself --------------------------------------------------------
def test_a_perfect_ranking_scores_one_and_a_reversed_one_zero():
    perfect = [(0.9, 1), (0.8, 1), (0.2, 0), (0.1, 0)]
    reversed_ = [(p, 1 - o) for p, o in perfect]
    assert rankfit.auc(perfect) == 1.0
    assert rankfit.auc(reversed_) == 0.0


def test_ties_share_credit_and_one_sided_outcomes_refuse():
    assert rankfit.auc([(0.5, 1), (0.5, 0)]) == 0.5
    assert rankfit.auc([(0.5, 1), (0.6, 1)]) is None


# --- the measurement, walked through a stubbed harness ---------------------
def _measure(pairs_by_market, store_path, prior=None):
    from engine import db as _db, logwalk

    class _Rep:
        def __init__(self, pairs):
            self.pairs = pairs

    if prior is not None:
        with open(store_path, "w") as f:
            json.dump(prior, f)
    calls = {}
    saved = (_db.entries_for_market, logwalk.walk)
    _db.entries_for_market = lambda conn, sport, market, **kw: (
        [{"name": "x", "values": [1]}] if market in pairs_by_market else [])
    def fake_walk(sport, entries, market, **kw):
        calls[market] = True
        return _Rep(pairs_by_market[market])
    logwalk.walk = fake_walk
    try:
        lines = rankfit.measure(None, "mlb", log=lambda *_: None,
                                path=store_path)
    finally:
        _db.entries_for_market, logwalk.walk = saved
    return lines, rankfit.load(store_path)


def _good_pairs(auc_high=True, n=3000):
    # Alternate outcomes so the AUC is exactly 1.0 (or 0.5 when mixed).
    out = []
    for i in range(n):
        o = i % 3 == 0
        p = (0.7 if o else 0.3) if auc_high else 0.5
        out.append((p, 1 if o else 0))
    return out


def test_a_big_clean_sample_is_adopted_with_its_auc():
    tmp = os.path.join(tempfile.mkdtemp(), "rank_auc.json")
    lines, store = _measure({"hits": _good_pairs()}, tmp)
    assert store["mlb:hits"]["auc"] == 1.0
    assert store["mlb:hits"]["n"] == 3000
    assert any("on the board" in ln for ln in lines), lines


def test_an_auc_under_the_floor_is_stored_but_named_off_the_board():
    tmp = os.path.join(tempfile.mkdtemp(), "rank_auc.json")
    lines, store = _measure({"hits": _good_pairs(auc_high=False)}, tmp)
    assert abs(store["mlb:hits"]["auc"] - 0.5) < 0.01
    assert any("stays off the board" in ln for ln in lines), lines


def test_a_thin_sample_claims_nothing():
    tmp = os.path.join(tempfile.mkdtemp(), "rank_auc.json")
    lines, store = _measure({"hits": _good_pairs(n=500)}, tmp)
    assert "mlb:hits" not in store
    assert any("needs" in ln for ln in lines), lines


def test_a_refit_gone_thin_retires_the_old_measurement():
    """A number measured on data the box no longer holds must not keep
    a shelf open past its evidence."""
    tmp = os.path.join(tempfile.mkdtemp(), "rank_auc.json")
    prior = {"mlb:hits": {"auc": 0.71, "n": 9000, "fitted_at": "2026-07-01"}}
    lines, store = _measure({"hits": _good_pairs(n=100)}, tmp, prior=prior)
    assert "mlb:hits" not in store
    assert any("RETIRED" in ln for ln in lines), lines


# --- likely reads the store, per sport -------------------------------------
def test_an_unmeasured_mlb_market_is_not_rankable():
    _clear_store()
    assert likely.rank_auc("mlb", "hits") is None
    assert not likely.rankable("hits", "mlb")


def test_a_fitted_mlb_market_turns_itself_on():
    _clear_store()
    rankfit._save({"mlb:hits": {"auc": 0.71, "n": 9000}})
    try:
        assert likely.rank_auc("mlb", "hits") == 0.71
        assert likely.rankable("hits", "mlb")
        assert not likely.rankable("home_runs", "mlb"), "unmeasured sibling"
    finally:
        _clear_store()


def test_a_fitted_market_under_the_floor_stays_off():
    _clear_store()
    rankfit._save({"mlb:hits": {"auc": 0.55, "n": 9000}})
    try:
        assert not likely.rankable("hits", "mlb")
    finally:
        _clear_store()


def test_the_nfl_constants_still_answer_and_cfb_stops_borrowing_them():
    _clear_store()
    assert likely.rank_auc("nfl", "anytime_td") == likely.RANK_AUC["anytime_td"]
    assert likely.rank_auc("cfb", "anytime_td") == likely.CFB_TD_AUC
    assert likely.rank_auc("cfb", "anytime_td") != likely.RANK_AUC["anytime_td"]


def test_a_cfb_watch_row_carries_colleges_own_figure():
    row = likely.from_watch({"player": "A", "team": "UGA",
                             "model_prob": 0.5}, sport="cfb")
    assert row["rank_auc"] == likely.CFB_TD_AUC


# --- the shelves and the build ---------------------------------------------
def test_mlb_has_shelves_and_unlisted_sports_still_do_not():
    shape = boards.shelves("mlb")
    keys = [s["key"] for s in shape]
    assert keys == ["homers", "bats", "arms", "gamelines"], keys
    assert boards.shelves("ufc") == []


def test_mlb_shelf_auc_reads_the_fitted_store():
    _clear_store()
    # THE PLAYER SHELVES, not every shelf. Since #257 (2026-09-16) the
    # game-lines shelf has a documented moneyline figure to fall back on
    # — 0.6727, measured on the droplet — exactly as the NFL's has had
    # 0.722 all along, so it is not None with the fitted store empty and
    # asking it to be would assert that baseball never got measured.
    player = [s for s in boards.shelves("mlb") if s["key"] != "gamelines"]
    assert player, "no player shelves to check"
    assert all(s["rank_auc"] is None for s in player)
    rankfit._save({"mlb:home_runs": {"auc": 0.68, "n": 9000}})
    try:
        homers = boards.shelves("mlb")[0]
        assert homers["rank_auc"] == 0.68
    finally:
        _clear_store()


def test_the_mlb_game_lines_shelf_states_its_measured_figure():
    """The other half of #257, asked directly. An empty fitted store is
    the normal state for this shelf — nothing fits a game-line AUC
    nightly — so the documented measurement is what it has to speak
    with, and a shelf that says nothing is a shelf nobody can judge."""
    _clear_store()
    gl = [s for s in boards.shelves("mlb") if s["key"] == "gamelines"]
    assert gl, "baseball lost its game-lines shelf"
    assert gl[0]["rank_auc"] == 0.6727, gl[0]["rank_auc"]


def test_a_measured_market_flows_through_build_to_the_board():
    _clear_store()
    rankfit._save({"mlb:hits": {"auc": 0.71, "n": 9000}})
    row = {"player": "T Player", "team": "NYY", "market": "hits",
           "market_label": "Hits", "side": "over", "line": 1.5,
           "hit_prob": 0.62, "has_market": True, "odds": -130,
           "book": "fanduel", "implied_prob": 0.58}
    try:
        got = likely.build([row], sport="mlb")
        assert got and got[0]["market"] == "hits"
        assert got[0]["rank_auc"] == 0.71
        assert likely.build([row], sport="nfl") == [], \
            "an MLB measurement must not open the NFL board"
    finally:
        _clear_store()


def test_the_mlb_build_publishes_the_board():
    with open(os.path.join(ROOT, "mlb_build.py"), encoding="utf-8") as f:
        src = f.read()
    assert 'result["most_likely"] = _likely_build(' in src
    assert 'sport="mlb"' in src
    assert '_mlboards.shelves(' in src


def test_the_weekly_pass_measures_and_an_empty_store_bootstraps():
    with open(os.path.join(ROOT, "engine", "maintenance.py"),
              encoding="utf-8") as f:
        src = f.read()
    assert "_rank_measure(_rkc, _sp, log=log)" in src
    assert "measuring now, not Wednesday" in src


# --- the guide speaks each sport's own numbers ------------------------------
def _measured(sport):
    return [b for b in boards.guide(sport)
            if b["key"] == "most_likely"][0]["measured"]


def test_the_wnba_guide_does_not_quote_football():
    """The night the hoops boards launched, the WNBA page's evidence
    line read "22,099 player-weeks" — five seasons of NFL. A measurement
    sentence about a different sport's measurement is prose wearing a
    number."""
    _clear_store()
    for sport in ("mlb", "nba", "wnba"):
        got = _measured(sport)
        assert "player-weeks" not in got, (sport, got)
        assert "No market has passed" in got, (sport, got)
    assert "player-weeks" in _measured("nfl"), "the NFL keeps its own line"
    assert f"{likely.CFB_TD_AUC:.2f}" in _measured("cfb")


def test_a_fitted_store_writes_the_sentence():
    _clear_store()
    rankfit._save({"wnba:pts": {"auc": 0.7, "n": 4000},
                   "wnba:reb": {"auc": 0.66, "n": 3000},
                   "wnba:ast": {"auc": 0.55, "n": 9000},
                   "nba:pts": {"auc": 0.9, "n": 9000}})
    try:
        got = _measured("wnba")
        assert "0.66-0.70" in got and "2 measured" in got, got
        assert "7,000" in got, got
        assert "0.55" not in got, "a sub-floor fit earned no quote"
        assert "0.90" not in got, "the NBA's fit is not the WNBA's"
    finally:
        _clear_store()


def test_a_store_of_only_subfloor_fits_says_not_good_enough():
    _clear_store()
    rankfit._save({"mlb:hits": {"auc": 0.53, "n": 9000}})
    try:
        assert "not good enough" in _measured("mlb")
    finally:
        _clear_store()


def test_the_settled_yet_claim_stays_nfl_only():
    """"No NFL bet has settled yet" was true of the NFL board and shipped
    on the MLB one, where bets have settled all season."""
    for sport in ("mlb", "nba", "wnba", "cfb"):
        rec = [b for b in boards.guide(sport)
               if b["key"] == "recommendations"][0]
        assert "No NFL bet has settled" not in rec["measured"], sport
    for path, want in (("mlb_build.py", '_mlboards.guide("mlb")'),
                       ("nba_build.py", "_hboards.guide(args.league)"),
                       ("cfb_build.py", '_boards.guide("cfb")')):
        with open(os.path.join(ROOT, path), encoding="utf-8") as f:
            assert want in f.read(), (path, want)


# --- the page explains an empty board instead of guessing -------------------
def test_the_empty_state_reads_the_census_not_a_guess():
    """Ethan, 2026-08-31: "the mlb and wnba page is not loading with our
    most likely picks" — the boards were empty BY DESIGN (unmeasured rank
    store) but the page showed its one canned guess ("needs priced props
    on the slate"), which was false: props were on the slate all night.
    The build ships likely_census with the real reason; the page now
    reads it, on the Top Picks page AND the home preview."""
    with open(os.path.join(ROOT, "web", "js", "app.js"),
              encoding="utf-8") as f:
        js = f.read()
    assert "function likelyEmptyWhy(census)" in js
    assert "no market measured to rank yet" in js
    at = js.index("function renderLikely()")
    body = js[at:js.index("\nfunction ", at + 10)]
    assert "likelyEmptyWhy(state.data.likely_census)" in body
    top = js[js.index("function renderLikelyTop()"):]
    top = top[:top.index("\nfunction ", 10)]
    assert "likelyEmptyWhy(state.data.likely_census)" in top
    # And the home section only vanishes for sports with no board at
    # all — census presence, not board_shelves, is the tell, because
    # engine/boards drops rowless shelves from the payload.
    assert "state.data.likely_census === undefined" in top


def test_a_likely_card_never_prints_vs_nobody():
    """Rows default opponent to ""; hoops and MLB props may not carry
    one at all. "LV vs undefined" shipped in the first hoops render."""
    with open(os.path.join(ROOT, "web", "js", "app.js"),
              encoding="utf-8") as f:
        js = f.read()
    at = js.index("function likelyCard(r)")
    body = js[at:js.index("\nfunction ", at + 10)]
    # Re-anchored 2026-09-02: the subtitle is built once into `sub`
    # (a game row shows its matchup instead) — the guard is unchanged.
    assert 'r.opponent ? ` vs ${teamName(r.opponent)}` : ""' in body, \
        "the vs half must be conditional on having an opponent"


# --- hoops rides the same rails --------------------------------------------
def test_hoops_shelves_exist_for_both_leagues():
    for sport in ("nba", "wnba"):
        keys = [s["key"] for s in boards.shelves(sport)]
        assert keys == ["scoring", "glass", "threes"], (sport, keys)


def test_a_wnba_measurement_lights_only_the_wnba_shelf():
    _clear_store()
    rankfit._save({"wnba:pts": {"auc": 0.70, "n": 9000}})
    try:
        assert likely.rankable("pts", "wnba")
        assert not likely.rankable("pts", "nba"), \
            "one league's measurement must not open the other's board"
        w = [s for s in boards.shelves("wnba") if s["key"] == "scoring"][0]
        n = [s for s in boards.shelves("nba") if s["key"] == "scoring"][0]
        assert w["rank_auc"] == 0.70 and n["rank_auc"] is None
    finally:
        _clear_store()


def test_a_hoops_row_flows_through_build():
    _clear_store()
    rankfit._save({"wnba:pts": {"auc": 0.70, "n": 9000}})
    row = {"player": "A Guard", "team": "LV", "market": "pts",
           "market_label": "Points", "side": "over", "line": 18.5,
           "hit_prob": 0.61, "has_market": True, "odds": -125,
           "book": "fanduel", "fair_prob": 0.57}
    try:
        got = likely.build([row], sport="wnba")
        assert got and got[0]["rank_auc"] == 0.70
        assert got[0]["implied_prob"] == 0.57, \
            "hoops rows carry fair_prob; from_prop must map it"
    finally:
        _clear_store()


def test_the_hoops_build_publishes_the_board():
    with open(os.path.join(ROOT, "nba_build.py"), encoding="utf-8") as f:
        src = f.read()
    assert 'out["most_likely"] = _likely_build(' in src
    assert "sport=args.league" in src
    assert '"most_likely": [], "board_shelves": []' in src, \
        "the empty paths must still ship the shape"


def test_the_likely_tab_is_no_longer_hidden_for_hoops():
    with open(os.path.join(ROOT, "web", "js", "app.js"),
              encoding="utf-8") as f:
        js = f.read()
    at = js.index("const HIDDEN_VIEWS")
    block = js[at:at + 1200]
    import re
    nba = re.search(r"nba: \[([^\]]*)\]", block).group(1)
    wnba = re.search(r"wnba: \[([^\]]*)\]", block).group(1)
    assert '"likely"' not in nba and '"likely"' not in wnba


# --- the baseball board says WHICH market lost its rows, and where ----------
def test_the_baseball_board_counts_every_kind_and_market_on_a_part_measured_box():
    """Ethan, 2026-09-15: "MLB most likely bets are only showing hits and
    total bases. There is no money lines or pitchers props or game totals
    or anything like that." On a box whose rank store has measured
    nothing, every prop market is refused for want of a measurement and
    every game card for want of one — and the census says so PER MARKET
    AND PER KIND, which is what the page prints. The flat census could
    only ever count refusals; it could not name the market they came
    from, and that is the question the report asks."""
    _clear_store()
    hit = {"player": "T Player", "team": "NYY", "market": "hits", "market_label": "Hits",
           "side": "over", "line": 0.5, "hit_prob": 0.72, "has_market": True,
           "odds": -180, "book": "fanduel", "fair_prob": 0.66}
    k = dict(hit, player="An Arm", market="strikeouts", market_label="Strikeouts",
             line=5.5, hit_prob=0.57, odds=-120, fair_prob=0.53)
    ml = {"bet_type": "moneyline", "market": "moneyline", "has_market": True,
          "home": "NYY", "away": "BOS", "team": "NYY", "pick_label": "NYY ML",
          "win_prob": 0.64, "fair_prob": 0.60, "odds": -150, "home_odds": -150,
          "away_odds": 130, "live": False, "matchup": "BOS @ NYY"}
    flat, kinds = {}, {}
    try:
        got = likely.build([hit, k], sport="mlb", census=flat, game_bets=[ml],
                           census_by_kind=kinds)
    finally:
        _clear_store()
    # THE PROPS ARE STILL REFUSED, and still say which market lost them.
    # That half of Ethan's 2026-09-15 sentence stands: nothing has fitted
    # a ranking for hits or strikeouts on a cleared store.
    mk = kinds["prop"]["markets"]
    assert mk["hits"]["offered"] == 1 and mk["hits"]["shown"] == 0, mk
    assert mk["hits"]["refused"] == {"no measured ranking for this market yet": 1}, mk
    assert mk["strikeouts"]["refused"] == {"no measured ranking for this market yet": 1}, mk

    # THE MONEYLINE IS NOT, ANY MORE — and this is the other half of that
    # sentence being answered rather than counted. Until 2026-09-16 this
    # asserted the game row was refused for "this game market has never
    # been measured", which was true and was the complaint. #257 measured
    # it on the droplet (market 0.6727 against the model's 0.5596 on
    # 1,088 games), so the row now reaches the board.
    assert kinds["game"]["offered"] == 1 and kinds["game"]["shown"] == 1, kinds["game"]
    assert not kinds["game"]["refused"], kinds["game"]
    assert [r["pick_label"] for r in got] == ["NYY ML"], got
    row = got[0]
    assert row["prob_source"] == "market", row["prob_source"]
    assert row["rank_auc"] == 0.6727 and row["ranked"] is True
    # The model's own number stays ON the row — only the ORDER changed.
    assert row["win_prob"] == 0.64 and row["raw_prob"] == 0.60


def test_the_baseball_and_hoops_builds_hand_the_kind_census_to_the_page():
    """The football builds have published `likely_census_by_kind` since
    2026-09-07; the baseball and hoops builds handed the board a flat
    census only, so their pages could never print the per-market funnel."""
    with open(os.path.join(ROOT, "mlb_build.py"), encoding="utf-8") as f:
        src = f.read()
    assert "census_by_kind=_ml_kinds" in src
    assert 'result["likely_census_by_kind"] = _ml_kinds' in src
    with open(os.path.join(ROOT, "nba_build.py"), encoding="utf-8") as f:
        hoops = f.read()
    assert "census_by_kind=_ml_kinds" in hoops
    assert 'out["likely_census_by_kind"] = _ml_kinds' in hoops


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
