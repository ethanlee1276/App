"""The likelihood board ranks unders and game lines — the ones that rank.

Ethan, 2026-09-02: "One thing I wanna add with the most likely to hit
page is all I see us is doing overs, but we have no unders, and we also
have no money lines or spreads or totals or anything like that. So we
need to dive deeper because there is more bets that we can salvage and
look into and use data for."

Two separate faults, and one rule for fixing both.

UNDERS were refused outright by `likely.admissible` — a product refusal
from 09-01 aimed at the first MLB night's -1200 unders, which the price
cap beside it already answered. The ranking claim covers an under for
free: an AUC is symmetric under the complement, so a market whose over
ranks at 0.77 ranks its under at 0.77. The first test here pins that.

GAME LINES never reached the board at all — no maker took a game card.
The founding rule says a market appears only once it has been MEASURED
to rank, so `engine.gamerank` measured them (2026-09-02, the same
ratings-only replay the game backtests use, over the stored closes):

    nfl  moneyline 0.641   spread 0.491   total 0.497   team_total 0.513
    cfb  moneyline 0.752   spread 0.496   total 0.503   team_total 0.492

The model can say who wins and cannot say who covers. So moneylines are
on the board and spreads and totals are not — whatever anyone would
prefer — and these pins hold that line until a measurement moves it.

Run directly: `python3 tests/test_likely_gamelines.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import boards, ledger                              # noqa: E402
from engine import likely as K                                 # noqa: E402
from engine.rankfit import auc                                 # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def _fn(js, name):
    i = js.index(f"function {name}(")
    return js[i:js.index("\nfunction ", i + 1)]


def _ml(**kw):
    """An NFL moneyline card as `gamebets.moneyline_to_dict` +
    `pipeline._finish_bet` publish it."""
    d = dict(bet_type="moneyline", market="moneyline", market_label="Moneyline",
             has_market=True, home="DET", away="NO", team="DET", pick="DET",
             pick_is_home=True, pick_label="DET ML", side="", line=0.0,
             matchup="NO @ DET", win_prob=0.66, fair_prob=0.62, edge=0.04,
             odds=-165, home_odds=-165, away_odds=140,
             ev_per_unit=0.05, confidence=6.0, stake_units=0.5,
             grade="B", credible=True, headline="DET ML",
             reasons=["Power rating: DET +4.1 vs NO -1.2"], recommended=True,
             live=False, date="2026-09-14", kickoff="2026-09-14T17:00:00+00:00")
    d.update(kw)
    return d


def _prop(prob=0.62, odds=-115, **kw):
    got = {"player": "A Wideout", "team": "CIN", "opponent": "CLE",
           "market": "rec_yds", "market_label": "Receiving Yards", "side": "over",
           "line": 45.5, "book": "DK", "odds": odds, "hit_prob": prob,
           "fair_prob": 0.55, "projection": 52.0, "ev_per_unit": 0.03,
           "has_market": True, "reasons": ["because"],
           "recent_values": [40, 60, 55], "date": "2026-09-14"}
    got.update(kw)
    return got


# --- why an under is covered by the over's measurement --------------------
def test_the_ranking_is_symmetric_so_an_under_ranks_like_its_over():
    """The whole basis for admitting unders without a second
    measurement: flip every probability and every outcome and the AUC
    is unchanged. 1 - P(over) against 'went under' is the same ordering
    read from the other end."""
    pairs = [(0.9, True), (0.7, True), (0.6, False), (0.55, True),
             (0.4, False), (0.35, True), (0.2, False), (0.1, False)]
    flipped = [(1.0 - p, not o) for p, o in pairs]
    assert abs(auc(pairs) - auc(flipped)) < 1e-12
    assert auc(pairs) > 0.5


# --- which game markets earned a place ------------------------------------
def test_only_the_moneyline_has_been_shown_to_rank():
    for sport in ("nfl", "cfb"):
        assert K.rankable("moneyline", sport), sport
        for market in ("spread", "total", "team_total"):
            assert not K.rankable(market, sport), (sport, market)
    # The constant lists nothing below the floor: an entry IS the claim.
    for sport, got in K.GAME_RANK_AUC.items():
        for market, a in got.items():
            assert market in K.GAME_MARKETS and a >= K.MIN_RANK_AUC, (sport, market, a)


def test_the_shipped_figures_are_the_measured_ones():
    """Measured 2026-09-02 by engine.gamerank on this repo's history.
    Re-measure before moving these; do not tune them."""
    assert K.GAME_RANK_AUC["nfl"]["moneyline"] == 0.641
    assert K.GAME_RANK_AUC["cfb"]["moneyline"] == 0.752
    src = _src("engine", "gamerank.py")
    assert "0.6412" in src and "0.7522" in src, "the measurement log left the module"
    assert "def measure_cfb(" in src, "college is measured with the production ratings"


# --- the maker --------------------------------------------------------------
def test_a_moneyline_card_becomes_a_likelihood_row():
    row = K.from_game_bet(_ml(), sport="nfl")
    assert row is not None
    assert row["kind"] == "game" and row["market"] == "moneyline"
    assert row["model_prob"] == 0.66 and row["implied_prob"] == 0.62
    assert row["player"] == "DET ML" and row["team"] == "DET"
    assert row["opponent"] == "NO" and row["matchup"] == "NO @ DET"
    assert row["book"] == "best", "an NFL game card carries no book name"
    assert row["rank_auc"] == K.GAME_RANK_AUC["nfl"]["moneyline"]
    assert row["bettable"] is True and row["injury_status"] == ""
    # The id the page opens the game page by is built from these.
    for key in ("home", "away", "side", "line", "bet_type"):
        assert key in row, key


def test_a_dog_card_becomes_the_favourites_row():
    """The first end-to-end run put "CHI ML +190, 37%" on a board called
    Most Likely with the 63% favourite nowhere on it. The edge card
    backs the side with the EDGE; this board ranks the side that WINS.
    A moneyline is two-way with no push, so the other side is
    1 - win_prob at the other price, both on the card."""
    dog = _ml(team="NO", pick="NO", pick_is_home=False, pick_label="NO ML",
              odds=140, win_prob=0.37, fair_prob=0.38, headline="NO ML")
    row = K.from_game_bet(dog, sport="nfl")
    assert row is not None and row["flipped"] is True
    assert row["team"] == "DET" and row["player"] == "DET ML"
    assert row["odds"] == -165, "the favourite's own price"
    assert row["model_prob"] == 0.63 and row["implied_prob"] == 0.62
    assert row["opponent"] == "NO" and row["pick_is_home"] is True
    assert row["reasons"][0].startswith("The likely side.")
    assert "NO ML at +140" in row["reasons"][0]
    # The card shape rides along so the game page can draw a row the
    # edge board never published.
    assert row["win_prob"] == 0.63 and row["grade"] == "Likely"
    assert row["stake_units"] == 0.0 and row["recommended"] is False
    # And the favourite card itself is not flipped.
    assert K.from_game_bet(_ml(), sport="nfl")["flipped"] is False


def test_a_dog_card_without_the_other_price_is_refused():
    """A stale payload built before both prices travelled: the dog is
    not the likely side, and the favourite cannot be priced — refused,
    not shown as "likely"."""
    dog = _ml(team="NO", pick="NO", pick_label="NO ML", odds=140,
              win_prob=0.37, fair_prob=0.38, home_odds=None, away_odds=None)
    assert K.from_game_bet(dog, sport="nfl") is None


def test_both_moneyline_paths_carry_both_prices():
    from engine.gamebets import moneyline_to_dict, price_moneyline, price_moneyline_sharp
    d = moneyline_to_dict(price_moneyline("KC", "BUF", 0.58, -150, 130))
    assert d["home_odds"] == -150 and d["away_odds"] == 130
    rec = price_moneyline_sharp("KC", "BUF", -155, 135, -125, -120)
    assert rec is not None and rec.home_odds == -125 and rec.away_odds == -120


def test_a_flipped_row_journals_the_favourite():
    dog = _ml(team="NO", pick="NO", pick_label="NO ML", odds=140,
              win_prob=0.37, fair_prob=0.38)
    conn, n = _book([K.from_game_bet(dog, sport="nfl")])
    assert n == 1
    got = dict(conn.execute("SELECT player, odds, hit_prob FROM bets").fetchone())
    assert got == {"player": "DET", "odds": -165, "hit_prob": 0.63}, got


def _tot(**kw):
    d = _ml(bet_type="total", market="total", market_label="Total", team="",
            side="Over", line=47.5, pick_label="Over 47.5", headline="Over 47.5 points",
            odds=-110, other_odds=-110, win_prob=0.56, fair_prob=0.52)
    d.pop("home_odds"); d.pop("away_odds")
    d.update(kw)
    return d


def test_a_spread_or_total_row_is_shown_as_a_lean_with_its_figure():
    """Ethan, after the first cut shipped moneylines alone: "I only see
    money lines ... I don't see team totals over or unders ... I don't
    see spread bets." His call. They tested as a coin flip at sorting
    games, so the row carries that figure and says it is a lean."""
    for market in ("spread", "total", "team_total"):
        card = _tot(bet_type=market, market=market, team="DET",
                    pick_label=f"DET Over 24.5" if market == "team_total" else "x")
        row = K.from_game_bet(card, sport="nfl")
        assert row is not None, market
        assert row["ranked"] is False
        assert row["rank_auc"] == K.GAME_RANK_MEASURED["nfl"][market]
        assert "coin flip" in row["rank_note"] and "not a ranking" in row["rank_note"]
    ml = K.from_game_bet(_ml(), sport="nfl")
    assert ml["ranked"] is True and ml["rank_note"] == ""


def test_a_market_with_no_figure_at_all_stays_off():
    """Measured-and-failed is shown with its number; never-measured has
    nothing to say. MLB sits here until `gamerank --save` runs on the
    droplet."""
    assert K.from_game_bet(_ml(), sport="wnba") is None
    assert K.from_game_bet(_tot(), sport="wnba") is None


def test_the_shipped_table_and_the_floor_agree():
    """GAME_RANK_AUC is exactly the part of the measured table that
    cleared the floor — one measurement, two views of it."""
    for sport, got in K.GAME_RANK_MEASURED.items():
        want = {m: a for m, a in got.items() if a >= K.MIN_RANK_AUC}
        assert K.GAME_RANK_AUC.get(sport, {}) == want, sport


def test_a_total_backed_from_the_short_end_flips_to_the_likely_side():
    row = K.from_game_bet(_tot(side="Under", win_prob=0.44, fair_prob=0.47,
                               odds=-105, other_odds=-115,
                               pick_label="Under 47.5"), sport="nfl")
    assert row["flipped"] is True and row["side"] == "Over"
    assert row["player"] == "Over 47.5" and row["odds"] == -115
    assert row["model_prob"] == 0.56 and row["implied_prob"] == 0.53
    assert row["reasons"][0].startswith("The likely side.")


def test_a_spread_backed_from_the_short_end_flips_team_and_number():
    card = _tot(bet_type="spread", market="spread", market_label="Spread",
                team="NO", side="", line=3.5, pick_label="NO +3.5",
                win_prob=0.46, fair_prob=0.48, odds=-105, other_odds=-115)
    row = K.from_game_bet(card, sport="nfl")
    assert row["flipped"] is True and row["team"] == "DET"
    assert row["line"] == -3.5 and row["player"] == "DET -3.5"
    assert row["odds"] == -115 and row["model_prob"] == 0.54


def test_a_team_total_flips_its_side_and_keeps_its_team():
    card = _tot(bet_type="team_total", market="team_total", team="DET",
                side="Over", line=24.5, pick_label="DET Over 24.5",
                win_prob=0.45, fair_prob=0.49, odds=-110, other_odds=-110)
    row = K.from_game_bet(card, sport="nfl")
    assert row["flipped"] is True and row["team"] == "DET"
    assert row["side"] == "Under" and row["player"] == "DET Under 24.5"


def test_a_short_side_without_the_other_price_is_refused():
    assert K.from_game_bet(_tot(win_prob=0.44, other_odds=None), sport="nfl") is None


def test_game_rows_are_capped_apart_from_player_rows():
    """A Sunday's five cards a game is eighty leans; they must not push
    the player rows off a forty-row board."""
    cards = [_tot(home=f"H{i}", away=f"A{i}", matchup=f"A{i} @ H{i}",
                  win_prob=0.55) for i in range(30)]
    props = [_prop(player=f"P{i}", prob=0.52) for i in range(5)]
    got = K.build(props, game_bets=cards)
    assert sum(1 for r in got if r["kind"] == "game") == K.GAME_LIMIT
    assert sum(1 for r in got if r["kind"] == "prop") == 5, \
        "the 52% props survived beside twenty 55% leans"
    assert [r["model_prob"] for r in got] == sorted(
        (r["model_prob"] for r in got), reverse=True), "one order"


def test_holds_are_not_picks():
    assert K.from_game_bet(_ml(live=True), sport="nfl") is None
    assert K.from_game_bet(_ml(conditional=True), sport="nfl") is None
    assert K.from_game_bet(_ml(has_market=False), sport="nfl") is None
    # A 25% pick is not under the floor on a two-way market: its other
    # side is 75%, and that is the row (see the flip test below).
    assert K.from_game_bet(_ml(win_prob=0.25), sport="nfl")["model_prob"] == 0.75


def test_the_one_bar_applies_to_game_rows_too():
    """Cap, credibility, dedupe — the same `admissible` every maker
    answers to, so a -300 favourite is chalk here as everywhere."""
    assert K.build([], game_bets=[_ml(odds=-300, win_prob=0.75, fair_prob=0.74)]) == []
    assert K.build([], game_bets=[_ml(win_prob=0.80, fair_prob=0.62)]) == [], \
        "a 18-point disagreement with the market is our error, not a discovery"
    got = K.build([], game_bets=[_ml(), _ml()])
    assert len(got) == 1 and got[0]["kind"] == "game"


def test_a_credibility_refusal_is_censused():
    census: dict = {}
    K.build([], game_bets=[_ml(win_prob=0.80, fair_prob=0.62)], census=census)
    assert census == {"disagrees with the market by more than we credit": 1}, census


def test_game_rows_sit_beside_player_rows_ordered_by_probability():
    """One list, one sort key. A 70% moneyline outranks a 62% prop and
    nothing about the price or the market kind moves it."""
    got = K.build([_prop(prob=0.62)], game_bets=[_ml(win_prob=0.70, fair_prob=0.66)])
    assert [r["kind"] for r in got] == ["game", "prop"], got
    assert got[0]["model_prob"] == 0.70 and got[1]["model_prob"] == 0.62


# --- the shelf --------------------------------------------------------------
def test_the_game_lines_shelf_exists_for_football_and_baseball():
    for sport in ("nfl", "cfb", "mlb"):
        shelf = [s for s in boards.shelves(sport) if s["key"] == "gamelines"]
        assert shelf, sport
        assert shelf[0]["markets"] == ["moneyline", "spread", "total", "team_total"]
    assert [s["key"] for s in boards.shelves("nfl")][-1] == "gamelines", \
        "game lines shelf last — the prop shelves are what the page opens for"


def test_a_game_row_lands_on_its_shelf_with_the_measured_figure():
    row = K.from_game_bet(_ml(), sport="nfl")
    out = boards.shelves("nfl", [row])
    assert [s["key"] for s in out] == ["gamelines"]
    assert out[0]["rows"] == [row]
    assert out[0]["rank_auc"] == K.GAME_RANK_AUC["nfl"]["moneyline"]


def test_a_measured_sub_floor_market_does_not_stamp_the_shelf():
    """The droplet's store will hold the spread's 0.49 beside the
    moneyline's 0.64 — a sub-floor market never puts a row on the
    shelf, so it is not the weakest row under the header."""
    real = dict(K.GAME_RANK_AUC["nfl"])
    try:
        K.GAME_RANK_AUC["nfl"]["spread"] = 0.49
        shelf = [s for s in boards.shelves("nfl") if s["key"] == "gamelines"][0]
        assert shelf["rank_auc"] == real["moneyline"], shelf["rank_auc"]
    finally:
        K.GAME_RANK_AUC["nfl"].clear()
        K.GAME_RANK_AUC["nfl"].update(real)


def test_the_evidence_line_says_what_was_measured_off_the_board_too():
    """A reader who sees moneylines and no spreads deserves the reason."""
    for sport in ("nfl", "cfb"):
        ml = K.GAME_RANK_AUC[sport]["moneyline"]
        line = boards.guide(sport)[0]["measured"]
        assert f"{ml:.2f}" in line, line
        assert "coin flip" in line and "lean" in line, line


# --- the journal ----------------------------------------------------------
def _book(rows, sport="nfl", date="2026-W02"):
    conn = ledger.connect(":memory:")
    n = ledger.log_most_likely(conn, {"sport": sport, "date": date,
                                      "most_likely": rows})
    return conn, n


def test_a_moneyline_row_is_journaled_in_the_shape_the_settler_grades():
    """`_game_actual` grades a moneyline as the TEAM at OVER 0.5 — the
    shape `log_recommendations` has always written. The board's pick
    label ("DET ML") reads well and matches nothing in the games
    table, so the journal re-derives the team."""
    row = K.from_game_bet(_ml(), sport="nfl")
    conn, n = _book([row])
    assert n == 1
    got = dict(conn.execute("SELECT * FROM bets").fetchone())
    assert got["player"] == "DET" and got["market"] == "moneyline"
    assert got["side"] == "OVER" and got["line"] == 0.5
    assert got["category"] == "likely" and got["stake_dollars"] == 0.0
    assert got["hit_prob"] == 0.66 and got["book"] == "best"


def test_a_total_and_a_spread_row_take_their_settle_shapes():
    """Not on the board today (unmeasured), pinned so the day they are
    the journal already grades them: the matchup key at its line, the
    team at the NEGATED spread."""
    total = {"kind": "game", "player": "Over 47.5", "bet_type": "total",
             "market": "total", "matchup": "NO @ DET", "team": "", "side": "Over",
             "line": 47.5, "book": "best", "odds": -110, "model_prob": 0.56,
             "implied_prob": 0.52, "game_date": "2026-09-14"}
    spread = {"kind": "game", "player": "DET -3.5", "bet_type": "spread",
              "market": "spread", "matchup": "NO @ DET", "team": "DET", "side": "",
              "line": -3.5, "book": "best", "odds": -110, "model_prob": 0.55,
              "implied_prob": 0.52, "game_date": "2026-09-14"}
    conn, n = _book([total, spread])
    assert n == 2
    rows = {r["market"]: dict(r) for r in conn.execute("SELECT * FROM bets")}
    assert rows["total"]["player"] == "NO@DET" and rows["total"]["line"] == 47.5
    assert rows["total"]["side"] == "OVER"
    assert rows["spread"]["player"] == "DET" and rows["spread"]["line"] == 3.5
    assert rows["spread"]["side"] == "OVER"


def test_a_game_row_with_no_team_or_line_is_refused_not_stranded():
    row = K.from_game_bet(_ml(), sport="nfl")
    _conn, n = _book([{**row, "team": ""}])
    assert n == 0


def test_the_record_cuts_the_game_rows_per_sport_and_market():
    """Whether the leans drag or lift a sport's book is read off the
    record per sport and market, not off a line that pools the NFL's
    moneylines with the MLB's."""
    row = K.from_game_bet(_ml(), sport="nfl")
    conn, n = _book([row])
    assert n == 1
    conn.execute("UPDATE bets SET status='won', pnl_units=0.0606 WHERE category='likely'")
    conn.commit()
    rep = ledger.likely_report(conn)
    got = rep["by_sport_market"]["nfl"]["moneyline"]
    assert got["n"] == 1 and got["w"] == 1 and got["actual"] == 1.0
    assert got["claimed"] == 0.66
    src = _src("engine", "maintenance.py")
    assert 'by_sport_market' in src, "the weekly log prints the per-market cut"


# --- the builds hand their cards over -------------------------------------
def test_every_build_hands_its_game_cards_to_the_board():
    nfl = _src("engine", "pipeline.py")
    at = nfl.index("_likely = _likely_board(")
    assert "game_bets=game_bets" in nfl[at:at + 200]
    assert "game_bets=out.get(\"game_bets\") or []" in _src("cfb_build.py")
    assert "game_bets=result.get(\"game_bets\") or []" in _src("mlb_build.py")


def test_the_weekly_pass_measures_game_markets_where_the_history_is():
    """An MLB moneyline can only earn its shelf on the droplet."""
    src = _src("engine", "maintenance.py")
    assert "from .gamerank import measure_and_store as _game_rank" in src
    assert '_game_rank(_rkc, _sp, log=log)' in src


def test_the_store_writer_keeps_and_retires_honestly(monkeypatch=None):
    """Stored when measured (floor or not — a sub-floor number on record
    is what stops a shelf being claimed by prose); retired when the box
    can no longer support it; left alone when it could not be measured
    at all, so a transient failure never erases a measurement."""
    import json
    import tempfile
    from engine import gamerank as G
    path = os.path.join(tempfile.mkdtemp(), "rank_auc.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"mlb:moneyline": {"auc": 0.62, "n": 900, "kind": "game"},
                   "mlb:hits": {"auc": 0.61, "n": 5000}}, f)
    real = G.measure
    seq = [G.GameRank("mlb", "spread", games_seen=1000, pairs=[(0.5, True)] * 500,
                      auc=0.49),
           G.GameRank("mlb", "moneyline", games_seen=1000, pairs=[],
                      note="100 quoted games — needs 400"),
           G.GameRank("mlb", "total", games_seen=0, note="could not measure — x")]
    G.measure = lambda conn, sport: seq
    try:
        lines = G.measure_and_store(None, "mlb", log=lambda *_: None, path=path)
    finally:
        G.measure = real
    with open(path, encoding="utf-8") as f:
        store = json.load(f)
    assert store["mlb:spread"]["auc"] == 0.49 and store["mlb:spread"]["kind"] == "game"
    assert "mlb:moneyline" not in store, "retired — too few games now"
    assert store["mlb:hits"]["auc"] == 0.61, "a prop entry is not this writer's to touch"
    assert any("RETIRED" in ln for ln in lines)


# --- the page ---------------------------------------------------------------
def test_the_render_gate_no_longer_drops_unders():
    js = _src("web", "js", "app.js")
    gate = _fn(js, "showableLikelyRow")
    assert "under" not in gate, gate
    assert "LIKELY_HEAVIEST_PRICE" in gate, "the cap stays"


def test_a_game_row_is_drawn_as_the_pick_it_is_and_opens_the_game_page():
    js = _src("web", "js", "app.js")
    door = _fn(js, "likelyDoor")
    assert 'r.kind === "game"' in door and "gameBetAttrs(r)" in door
    opn = _fn(js, "likelyOpen")
    assert 'r.kind === "game"' in opn and "gameBetId(r)" in opn
    row = _fn(js, "likelyRow")
    assert "r.pick_label" in row and "likelyGameMark(r, 30)" in row
    assert '" · lean"' in row, "a lean row says so in the list too"
    card = _fn(js, "likelyCard")
    assert "r.pick_label" in card and "likelyGameMark(r, 56)" in card
    assert "r.rank_note" in card and "${lean}" in card
    shelf = _fn(js, "likelyShelf")
    assert "r.ranked === false" in shelf
    mark = _fn(js, "likelyGameMark")
    assert "leagueMark(state.sport, size)" in mark and "teamMark(r.team, size)" in mark


def test_the_game_page_finds_the_row_by_the_same_id():
    """`openProp` falls through to the game row by gameBetId, so the row
    must carry the id's five parts verbatim from the card. Re-anchored
    2026-09-02: the two lookups (edge cards, and the likelihood board
    for a FLIPPED row the edge board never published) became one shared
    `findGameRow`, which the slip and the share card use too."""
    js = _src("web", "js", "app.js")
    assert "const b = findGameRow(state.propId);" in js
    i = js.index("function findGameRow(id)")
    body = js[i:js.index("\n}", i)]
    assert "d.game_bets" in body and "d.most_likely" in body, body
    gid = _fn(js, "gameBetId")
    for part in ("b.away", "b.home", "b.market || b.bet_type", "b.side || b.team", "b.line"):
        assert part in gid, part


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
