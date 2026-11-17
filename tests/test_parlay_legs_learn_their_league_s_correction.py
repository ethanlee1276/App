"""Each league's parlay legs learn how far their chances run past what they hit (LEGFIT1).

Ethan, 2026-11-16, asked whether each league should learn a correction for
parlay legs that claim more than they hit: "yes". Counted once a bet, the
NFL's legs hit 13 points under the chance we gave them and college's 6
(FOOTCAL1). engine/legfit learns, league by league and kind by kind, the share
of the way each leg's chance is pulled toward the book's fair chance — the one
that scores the graded legs best, used only when it also scores the newest
legs better — and gameparlays applies it before a leg is held to its floor.
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gameparlays as GP  # noqa: E402
from engine import legfit as LF  # noqa: E402
from engine import modelstate  # noqa: E402
from engine import parlayledger as PL  # noqa: E402
from engine import twoleg as T  # noqa: E402


def _journal(legs_by_league, pool=None):
    """A journal of game tickets: ``{(league, source): [(p_final, fair, won, p_raw), ...]}``, two legs a
    ticket, each leg its own bet, every ticket written twice over the same legs (a rebuild before the start).
    ``pool`` names the legs' pool (legs built the current way); None is the retired source, before the
    journal named pools."""
    conn = sqlite3.connect(":memory:")
    PL.ensure_schema(conn)
    for (sport, source), legs in legs_by_league.items():
        for i in range(0, len(legs) - 1, 2):
            for copy in range(2):
                cur = conn.execute("INSERT INTO parlays (sport, date, legs_key, parlay_type, n_legs, grade, source, "
                                   "status) VALUES (?,?,?,?,2,?,?,'lost')",
                                   (sport, f"2026-11-{1 + i // 20:02d}", f"{sport}{source}{i}-{copy}", "same_game",
                                    f"A{i}@H{i}", source))
                for j, (p, fair, won, raw) in enumerate(legs[i:i + 2]):
                    conn.execute("INSERT INTO parlay_legs (parlay_id, leg_no, player, market, side, line, p_final, "
                                 "fair, p_raw, status, pool) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                                 (cur.lastrowid, j + 1, f"P{i + j}", "receptions", "OVER", 3.5, p, fair, raw,
                                  "won" if won else "lost", pool))
    conn.commit()
    return conn


def _legs(n, p, fair, rate, raw=None):
    """n legs claiming p with the book at fair, hitting at about ``rate``, spread evenly through time."""
    return [(p, fair, ((k * 37) % 100) < round(rate * 100), raw) for k in range(n)]


def test_a_league_whose_legs_run_hot_is_pulled_toward_the_books():
    # Claimed 75%, the books said 62%, they hit 62%: ours should give way to the books'.
    conn = _journal({("nfl", "game_three"): _legs(120, 0.75, 0.62, 0.62),
                     ("cfb", "game_three"): _legs(120, 0.70, 0.62, 0.70),
                     ("nba", "game_three"): _legs(20, 0.75, 0.62, 0.62)})
    fit = LF.fit(conn, write=False)["fits"]
    nfl = fit["nfl:three"]
    assert nfl["fitted"] and nfl["w"] >= 0.8 and nfl["n"] == 120, nfl
    assert (nfl["claimed"], nfl["fair"]) == (0.75, 0.62) and abs(nfl["hit"] - 0.62) < 0.02, nfl
    assert nfl["test_loss"][1] < nfl["test_loss"][0] and nfl["test_n"] == 36, nfl
    assert "pulled" in nfl["why"] and "of the way to the book's" in nfl["why"]
    # Legs that hit what they claimed keep our number; a league short of MIN_N waits.
    assert fit["cfb:three"]["fitted"] is False and fit["cfb:three"]["w"] == 0.0, fit["cfb:three"]
    assert fit["nba:three"] == {"n": 20, "claimed": 0.75, "fair": 0.62, "hit": fit["nba:three"]["hit"], "w": 0.0,
                                "fitted": False, "why": "waiting on the record: 20 graded leg(s), 60 needed",
                                "shift": 0.0, "shift_n": 0,
                                "shift_why": "waiting on legs built the current way: 0 graded, 60 needed"}


def test_each_bet_counts_once_and_the_kinds_learn_apart():
    conn = _journal({("nfl", "game_three"): _legs(80, 0.75, 0.62, 0.62),
                     ("nfl", "game_td"): _legs(70, 0.40, 0.30, 0.30)})
    got = LF.graded_legs(conn)
    assert len(got[("nfl", "three")]) == 80, "each ticket written twice over the same legs: each bet once"
    assert len(got[("nfl", "scorers")]) == 70
    fit = LF.fit(conn, write=False)["fits"]
    assert set(fit) == {"nfl:three", "nfl:scorers"} and fit["nfl:scorers"]["fitted"], fit


def test_a_leg_journaled_before_its_fair_chance_was_kept_is_read_at_its_price():
    """Every leg before 16 November has no `fair`; its price stands in, so the record already speaks."""
    conn = _journal({("nfl", "game_three"): _legs(120, 0.75, None, 0.60)})
    conn.execute("UPDATE parlay_legs SET odds=-150")
    conn.commit()
    nfl = LF.fit(conn, write=False)["fits"]["nfl:three"]
    assert nfl["fair"] == 0.6 and nfl["fitted"] and nfl["w"] >= 0.8, nfl


def test_the_fit_reads_our_own_number_never_the_corrected_one():
    # Posted already corrected (p_final 0.62) but ours was 0.75 (p_raw): the fit still sees 0.75.
    conn = _journal({("nfl", "game_three"): _legs(120, 0.62, 0.62, 0.62, raw=0.75)})
    nfl = LF.fit(conn, write=False)["fits"]["nfl:three"]
    assert nfl["claimed"] == 0.75 and nfl["fitted"], nfl


def test_a_leg_is_pulled_by_its_league_s_share_and_left_alone_without_one():
    leg = {"player": "A", "p": 0.70, "fair": 0.60}
    got = LF.apply(leg, "nfl", "three", 0.5)
    assert (got["p"], got["p_raw"], got["fit_w"]) == (0.65, 0.70, 0.5) and leg["p"] == 0.70, got
    assert LF.apply({"p": 0.70}, "nfl", "three", 0.5) == {"p": 0.70}, "no book's chance, ours stands"
    # A leg with no fair chance kept: its own price's (−150 is 60%).
    priced = LF.apply({"p": 0.70, "odds": -150}, "nfl", "three", 0.5)
    assert priced["p"] == 0.65 and LF.implied(-150) == 0.6 and LF.implied(150) == 0.4 and LF.implied(0) is None
    assert LF.apply(got, "nfl", "three", 0.5) is got, "never corrected twice"
    assert LF.apply(leg, "nfl", "three", 0.0) is leg


def test_the_fit_on_file_is_read_once_and_a_bad_file_is_said():
    path = modelstate.path(LF.FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        conn = _journal({("nfl", "game_three"): _legs(120, 0.75, 0.62, 0.62)})
        LF.fit(conn)
        assert LF.w_for("nfl", "three") >= 0.8 and LF.w_for("cfb", "three") == 0.0
        assert LF.census("nfl")["three"]["fitted"] is True and LF.census("mlb") == {}
        with open(path, "w", encoding="utf-8") as f:
            f.write("{not json")
        os.utime(path, ns=(1, 10 ** 18))
        assert LF.w_for("nfl", "three") == 0.0 and LF.ERROR, "a file that cannot be read gives our own numbers"
    finally:
        if os.path.exists(path):
            os.remove(path)
    assert LF.w_for("nfl", "three") == 0.0 and LF.ERROR is None, "no file is the quiet default"


def test_the_legs_are_corrected_before_their_floor():
    keep = (T.likely_legs, T.edge_legs, GP.pool_legs, GP.priced_legs, LF.w_for)
    hot = {"player": "Hot Leg", "team": "DET", "market": "receptions", "side": "Over", "line": 3.5, "p": 0.66,
           "fair": 0.50, "pool": "likely"}
    sure = {"player": "Sure Leg", "team": "DET", "market": "rush_yds", "side": "Over", "line": 40.5, "p": 0.80,
            "fair": 0.76, "pool": "likely"}
    try:
        T.likely_legs = lambda board, sport, now=None: [dict(hot), dict(sure)]
        T.edge_legs = GP.pool_legs = GP.priced_legs = lambda board, sport, now=None: []
        LF.w_for = lambda sport, kind: 0.5 if (sport, kind) == ("nfl", "three") else 0.0
        got = {l["player"]: l for l in GP.legs_for({}, "nfl")}
        assert set(got) == {"Sure Leg"}, "0.66 pulled half way to the book's 0.50 is 0.58, under the 60% floor"
        assert (got["Sure Leg"]["p"], got["Sure Leg"]["p_raw"]) == (0.78, 0.8), got
        assert {l["player"] for l in GP.legs_for({}, "cfb")} == {"Hot Leg", "Sure Leg"}, "another league's own"
    finally:
        T.likely_legs, T.edge_legs, GP.pool_legs, GP.priced_legs, LF.w_for = keep
    assert {"p_raw", "fit_w"} <= set(GP.LEG_KEYS), "the ticket keeps our number and the share"


def test_the_journal_keeps_our_number_beside_the_posted_one():
    conn = sqlite3.connect(":memory:")
    PL.ensure_schema(conn)
    gp = {"games": [{"game": "NE@DET", "threes": [{"legs": [
        {"player": "A", "team": "DET", "market": "receptions", "side": "Over", "line": 3.5, "p": 0.65, "p_raw": 0.7,
         "fair": 0.6, "pool": "likely"},
        {"player": "B", "team": "DET", "market": "rush_yds", "side": "Over", "line": 40.5, "p": 0.8, "pool": "edge"}]}],
        "scorers": []}]}
    assert PL.log_game_parlays(conn, gp, "nfl", "2026-W11") == 1
    rows = conn.execute("SELECT player, p_final, p_raw FROM parlay_legs ORDER BY leg_no").fetchall()
    assert rows == [("A", 0.65, 0.7), ("B", 0.8, None)], rows


# --- FOOTCAL2: the shift, for legs the books agreed with ------------------------------------------
def test_football_legs_the_books_agreed_with_are_shifted_to_what_they_hit():
    """Ethan, 2026-11-17: "recalibrate football too". The NFL's legs claimed 68% and hit 55%, and the
    books' prices on them said 68% as well: pulled toward the book, they barely move. The shift moves them."""
    conn = _journal({("nfl", "game_three"): _legs(140, 0.68, 0.68, 0.55)}, pool="likely")
    nfl = LF.fit(conn, write=False)["fits"]["nfl:three"]
    assert nfl["shift"] < -0.3 and nfl["shift_n"] == 140, nfl
    assert nfl["shift_test"][1] < nfl["shift_test"][0], "kept only because the newest legs scored better for it"
    assert "claimed 68% and hit 55%" in nfl["shift_why"] and "log-odds" in nfl["shift_why"], nfl
    moved = LF.apply({"p": 0.68, "fair": 0.68}, "nfl", "three", nfl["w"] if nfl["fitted"] else 0.0, nfl["shift"])
    assert abs(moved["p"] - 0.55) <= 0.03 and moved["p_raw"] == 0.68 and moved["fit_shift"] == nfl["shift"], moved
    # Pulling toward the books could not have done it: they said what we said.
    assert abs(LF.apply({"p": 0.68, "fair": 0.68}, "nfl", "three", 1.0, 0.0).get("p", 0.68) - 0.68) < 1e-9


def test_the_retired_source_teaches_no_shift():
    """Legs from before the journal named pools came from a source the parlays no longer use
    (gameparlays.credible_row): they still teach the pull, never the shift."""
    conn = _journal({("nfl", "game_three"): _legs(140, 0.68, 0.68, 0.55)})
    nfl = LF.fit(conn, write=False)["fits"]["nfl:three"]
    assert nfl["shift"] == 0.0 and nfl["shift_n"] == 0, nfl
    assert nfl["shift_why"] == "waiting on legs built the current way: 0 graded, 60 needed", nfl


def test_legs_that_hit_what_they_claim_keep_our_number():
    conn = _journal({("cfb", "game_three"): _legs(140, 0.66, 0.60, 0.66)}, pool="likely")
    cfb = LF.fit(conn, write=False)["fits"]["cfb:three"]
    assert cfb["shift"] == 0.0 and cfb["shift_n"] == 140 and "so none" in cfb["shift_why"], cfb
    assert LF.apply({"p": 0.66, "fair": 0.60}, "cfb", "three", 0.0, 0.0) == {"p": 0.66, "fair": 0.60}


def test_the_shift_moves_a_leg_before_its_floor_and_the_ticket_keeps_it():
    keep = (T.likely_legs, T.edge_legs, GP.pool_legs, GP.priced_legs, LF.w_for, LF.shift_for)
    legs = [{"player": "Even", "team": "DET", "market": "receptions", "side": "Over", "line": 3.5, "p": 0.66,
             "fair": 0.66, "pool": "likely"},
            {"player": "Sure", "team": "DET", "market": "rush_yds", "side": "Over", "line": 40.5, "p": 0.80,
             "fair": 0.78, "pool": "likely"}]
    try:
        T.likely_legs = lambda board, sport, now=None: [dict(x) for x in legs]
        T.edge_legs = GP.pool_legs = GP.priced_legs = lambda board, sport, now=None: []
        LF.w_for = lambda sport, kind: 0.0
        LF.shift_for = lambda sport, kind: -0.4 if (sport, kind) == ("nfl", "three") else 0.0
        got = {l["player"]: l for l in GP.legs_for({}, "nfl")}
        assert set(got) == {"Sure"}, "0.66 moved -0.4 in log-odds is 0.57, under the 60% floor"
        assert got["Sure"]["p_raw"] == 0.8 and 0.72 <= got["Sure"]["p"] < 0.8 and got["Sure"]["fit_shift"] == -0.4
        assert {l["player"] for l in GP.legs_for({}, "cfb")} == {"Even", "Sure"}, "another league's own"
    finally:
        T.likely_legs, T.edge_legs, GP.pool_legs, GP.priced_legs, LF.w_for, LF.shift_for = keep
    assert "fit_shift" in GP.LEG_KEYS, "the ticket keeps the shift beside our number"
    assert LF.shifted(0.7, 0.0) == 0.7 and round(LF.shifted(0.5, 0.0), 6) == 0.5
    assert abs(LF.shifted(0.5, -1.0986) - 0.25) < 1e-3, "log-odds: 50% moved by ln(1/3) is 25%"


def test_the_shift_on_file_is_read_and_said_in_the_census():
    path = modelstate.path(LF.FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        LF.fit(_journal({("nfl", "game_three"): _legs(140, 0.68, 0.68, 0.55)}, pool="likely"))
        assert LF.shift_for("nfl", "three") < -0.3 and LF.shift_for("cfb", "three") == 0.0
        assert LF.census("nfl")["three"]["shift"] < -0.3 and "shift_why" in LF.census("nfl")["three"]
    finally:
        if os.path.exists(path):
            os.remove(path)
    assert LF.shift_for("nfl", "three") == 0.0, "no file, no shift"
    src = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    assert "legs now shifted" in src, "the nightly pass says when a league's shift moves"


def test_the_settle_pass_refits_it_beside_the_one_club_bar():
    src = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    i = src.index("sb = gameparlays.fit_side_bar(lconn)")
    assert src.index("lf = legfit.fit(lconn)", i) < src.index('lap("parlays")', i)
    assert "legs now pulled" in src
    json.dumps({"ok": True})


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
