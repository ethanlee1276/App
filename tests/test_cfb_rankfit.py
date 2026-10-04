"""College yardage is measured on college logs, or it is not on the board.

Ethan, twice on 2026-09-02: "make sure everything I'm telling you to do
for NFL is also being implemented for college football because I'm still
not seeing any props for college football." College had no yardage
market at all — `engine.sources.oddsapi` bought full-game markets only
and `cfb_build` journalled `"recommendations": []` unconditionally.

Adding one is two separate things, and the whole discipline of this
board lives in keeping them separate:

  * the MODEL, which college can borrow — `logwalk.walk` hands every
    non-MLB sport to the same generic chain, `build_projection` takes
    `sport` only to key its self-tuning stores, and `evaluate_prop`
    already reads "cfb" as football;
  * the MEASUREMENT, which college cannot borrow and once did. The
    college touchdown board wore the NFL's 0.721 by accident until
    `likely.CFB_TD_AUC` was measured on college player-weeks
    (`engine.cfbtdfit`). A yardage shelf opened on the NFL's 0.761
    would be that same mistake with a different number.

So these tests pin the shape of the answer rather than a value: the
walk runs on college logs, the store gates itself on its own sample,
and until a box has walked them college yardage has NO number — not the
NFL's, not a default, not a shelf.

Run directly: `python3 tests/test_cfb_rankfit.py`
"""

import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _sandbox():
    """A models dir and a history DB nobody else can see.

    `rankfit.STORE` is bound at import to `modelstate.path(...)`, which
    reads QB_MODELS_DIR, so every call below passes an explicit path
    instead of relying on the environment being swept.
    """
    d = tempfile.mkdtemp(prefix="cfb-rankfit-")
    return os.path.join(d, "history.db"), os.path.join(d, "rank_auc.json")


def _logs(market, players=120, games=30, seed=11, spread=0.9):
    """Chronological college rushing lines for N backs of varying skill.

    Synthetic on purpose: the number this produces is not a claim about
    college football, it is a claim about the plumbing. What is being
    tested is that college logs reach the walk and the walk's verdict
    reaches the store — never that the verdict is any particular AUC.
    """
    rnd = random.Random(seed)
    rows = []
    for i in range(players):
        skill = 20 + i * spread
        for g in range(games):
            rows.append({
                "sport": "cfb", "season": 2024 + g // 15,
                "period": f"2024-09-{g + 1:02d}", "game_id": f"g{i}-{g}",
                "player": f"Player {i}", "team": "AAA", "opponent": "BBB",
                "position": "RB", "home": g % 2, "market": market,
                "value": max(0.0, rnd.gauss(skill, skill * 0.6)),
            })
    return rows


def _conn(rows):
    from engine import db
    path, store = _sandbox()
    conn = db.connect(path)
    db.upsert_player_logs(conn, rows)
    return conn, store


# --- the markets college is measured on -------------------------------
def test_college_football_is_in_the_fitter_s_market_table():
    from engine import rankfit
    assert rankfit.MARKETS["cfb"] == ("pass_yds", "rush_yds", "rec_yds",
                                      "receptions")


def test_the_nfl_is_deliberately_not_in_it():
    """Its five markets are hand-measured constants in `likely.RANK_AUC`,
    and a store entry would silently override them. Separate decision."""
    from engine import rankfit
    assert "nfl" not in rankfit.MARKETS


# --- the walk runs on college logs ------------------------------------
def test_the_generic_chain_walks_college_logs_and_settles_pairs():
    """The load-bearing claim behind reusing the NFL model: nothing in
    the shared projection path is nflverse-shaped, so college logs walk
    it unchanged."""
    from engine import db
    from engine.logwalk import walk
    conn, _ = _conn(_logs("rush_yds", players=8, games=20))
    entries = db.entries_for_market(conn, "cfb", "rush_yds")
    assert len(entries) == 8
    report = walk("cfb", entries, "rush_yds")
    assert report.pairs, "college logs produced no settled pairs"
    assert all(0.0 <= p <= 1.0 for p, _ in report.pairs)


def test_a_measured_market_lands_in_the_store_with_its_sample():
    from engine import rankfit
    conn, store = _conn(_logs("rush_yds"))
    rankfit.measure(conn, "cfb", markets=["rush_yds"],
                    log=lambda _s: None, path=store)
    got = rankfit.load(store)["cfb:rush_yds"]
    assert 0.0 <= got["auc"] <= 1.0
    assert got["n"] >= rankfit.MIN_PAIRS
    assert got["fitted_at"]


def test_a_thin_sample_claims_nothing():
    """MIN_PAIRS is the whole reason a shelf does not flicker. Eight
    players is a real walk and not a measurement."""
    from engine import rankfit
    conn, store = _conn(_logs("rush_yds", players=8, games=20))
    lines = rankfit.measure(conn, "cfb", markets=["rush_yds"],
                            log=lambda _s: None, path=store)
    assert rankfit.load(store) == {}
    assert any("before it can claim to rank" in ln for ln in lines)


def test_a_market_with_no_ingested_logs_says_so_rather_than_guessing():
    from engine import rankfit
    conn, store = _conn(_logs("rush_yds", players=4, games=12))
    lines = rankfit.measure(conn, "cfb", markets=["rec_yds"],
                            log=lambda _s: None, path=store)
    assert lines == ["rank fit cfb:rec_yds: no ingested logs"]
    assert rankfit.load(store) == {}


# --- and it is COLLEGE's number, never the NFL's ----------------------
def test_unmeasured_college_yardage_has_no_number_at_all():
    """The un-borrowing rule. `likely.rank_auc` falls back to the NFL
    constants only when the sport IS the NFL; college asking for a
    market nobody has walked gets None, and None means no shelf."""
    from engine import likely
    from engine.rankfit import STORE
    if os.path.exists(STORE):                    # a box that has measured
        return                                   # cannot answer this one
    for market in ("pass_yds", "rush_yds", "rec_yds", "receptions"):
        assert likely.rank_auc("cfb", market) is None, market
        assert likely.rankable(market, "cfb") is False, market
        # …while the NFL's own hand-measured constant is untouched.
        assert likely.rank_auc("nfl", market) == likely.RANK_AUC[market]


def test_the_college_touchdown_constant_is_still_college_s_own():
    """The precedent this work is built on: 0.675 measured on 29,047
    college player-weeks, not the NFL's 0.721."""
    from engine import likely
    assert likely.CFB_TD_AUC == 0.675
    assert likely.CFB_TD_AUC != likely.RANK_AUC["anytime_td"]


def test_a_stored_college_number_is_what_the_gate_reads():
    """The store is first in `likely.rank_auc`'s trust order, so a box
    that has walked its own logs turns its own shelf on."""
    from engine import likely, rankfit
    conn, store = _conn(_logs("rush_yds"))
    rankfit.measure(conn, "cfb", markets=["rush_yds"],
                    log=lambda _s: None, path=store)
    measured = rankfit.load(store)["cfb:rush_yds"]["auc"]
    assert rankfit.rank_auc("cfb", "rush_yds",
                            store=rankfit.load(store)) == measured
    # …and the floor is applied to it rather than assumed away.
    assert (measured >= likely.MIN_RANK_AUC) is (measured >= 0.60)


def test_a_refit_that_loses_its_sample_retires_the_measurement():
    """A number measured on data this box no longer holds is a number
    nobody can re-derive. Pinned for college because a season rolls off
    the college backfill every year."""
    from engine import rankfit
    conn, store = _conn(_logs("rush_yds"))
    rankfit.measure(conn, "cfb", markets=["rush_yds"],
                    log=lambda _s: None, path=store)
    assert "cfb:rush_yds" in rankfit.load(store)
    conn.execute("DELETE FROM player_game_logs WHERE player NOT IN "
                 "('Player 1', 'Player 2', 'Player 3')")
    conn.commit()
    lines = rankfit.measure(conn, "cfb", markets=["rush_yds"],
                            log=lambda _s: None, path=store)
    assert rankfit.load(store) == {}
    assert any("RETIRED" in ln for ln in lines)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
