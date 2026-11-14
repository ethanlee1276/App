"""Two-leg parlays from our own picks (engine/twoleg) — the Parlays page.

Ethan, 2026-10-31: "two-leg parlays ... picked from the most likely bet and
the edge bets ... a section for the edge bet parlays and most likely bet
parlays ... picks that correlate with each other or picks that just make
sense ... one pick on one team, one pick on the other ... same-game parlay
X's where it's two picks from different games ... record that data."

Run directly: `python3 tests/test_two_leg_parlays.py`
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import ledger, parlayledger, stakeplan, twoleg as T     # noqa: E402

DAY = "2099-11-01"


def _prop(player, team, opp, market, side, line, odds, p, book="DraftKings", **kw):
    return {"player": player, "team": team, "opponent": opp, "market": market, "side": side,
            "line": line, "odds": odds, "book": book, "hit_prob": p, "model_prob": p,
            "recommended": True, "has_market": True, "game_date": DAY, "kickoff": f"{DAY}T23:00:00Z",
            "stake_units": 1.0, "grade": "A", **kw}


def _board():
    edge = [_prop("Jared Goff", "DET", "MIN", "pass_yds", "OVER", 254.5, -110, 0.58),
            _prop("Amon-Ra St. Brown", "DET", "MIN", "rec_yds", "OVER", 74.5, -112, 0.57),
            _prop("Justin Jefferson", "MIN", "DET", "receptions", "OVER", 6.5, 105, 0.52),
            _prop("Josh Allen", "BUF", "MIA", "pass_yds", "OVER", 249.5, -105, 0.56),
            _prop("Long Shot", "BUF", "MIA", "rush_yds", "OVER", 60.5, 180, 0.40)]
    likely = [_prop("Jahmyr Gibbs", "DET", "MIN", "rush_yds", "OVER", 49.5, -250, 0.80),
              _prop("Jordan Addison", "MIN", "DET", "receptions", "OVER", 2.5, -300, 0.82),
              _prop("James Cook", "BUF", "MIA", "rush_yds", "OVER", 44.5, -240, 0.79),
              _prop("Tyreek Hill", "MIA", "BUF", "rec_yds", "OVER", 39.5, -260, 0.81)]
    return {"sport": "nfl", "date": "2099-W09", "recommendations": edge, "most_likely": likely,
            "game_bets": []}


# --- the legs and the pairs -------------------------------------------------------------
def test_edge_legs_are_the_staked_kind_and_the_long_price_stays_out():
    legs = T.edge_legs(_board(), "nfl")
    assert {l["player"] for l in legs} == {"Jared Goff", "Amon-Ra St. Brown", "Justin Jefferson", "Josh Allen"}, \
        "past +130 is tracked as a single and never a parlay leg"
    assert all(l["pool"] == "edge" for l in legs)
    assert len(T.likely_legs(_board(), "nfl")) == 4


def test_two_teammates_that_rise_together_make_a_same_game_parlay():
    legs = {l["player"]: l for l in T.edge_legs(_board(), "nfl")}
    t = T.pair("nfl", legs["Jared Goff"], legs["Amon-Ra St. Brown"])
    assert t and t["kind"] == T.SAME_GAME and t["rho"] > 0
    assert t["joint"] > t["independent"], "a positive correlation lifts the chance both hit"
    assert abs(t["price_dec"] - t["naive_dec"] * (1 - T.SGP_CUT)) < 1e-3, "graded under the product"
    assert "rise together" in t["why"]


def test_one_pick_on_each_team_is_a_same_game_pair_and_the_lift_rule_is_the_studys():
    """For one evening a same-game pair had to lift the chance both hit by
    the 10.5% the book's cut takes. The box's second study run (every
    league's games) said no: the pairs it refused broke about even and the
    tightly linked ones it kept lost 15.9%. The board builds every pair that
    makes sense again; the lift rule stays reachable for the study."""
    legs = {l["player"]: l for l in T.edge_legs(_board(), "nfl")}
    t = T.pair("nfl", legs["Amon-Ra St. Brown"], legs["Justin Jefferson"])
    assert t and t["kind"] == T.SAME_GAME and "one pick on each team" in t["why"], \
        "Ethan's one pick on one team, one on the other"
    assert abs(T.SG_MIN_LIFT - 1 / (1 - T.SGP_CUT)) < 1e-12
    assert T.pair("nfl", legs["Amon-Ra St. Brown"], legs["Justin Jefferson"], min_lift=T.SG_MIN_LIFT) is None, \
        "the pace floor alone does not lift it 10.5%"
    qb = T.pair("nfl", legs["Jared Goff"], legs["Amon-Ra St. Brown"], min_lift=T.SG_MIN_LIFT)
    assert qb and qb["joint"] >= T.SG_MIN_LIFT * qb["independent"], "a quarterback and his receiver do"


def test_other_games_are_two_game_parlays_at_the_product():
    legs = {l["player"]: l for l in T.edge_legs(_board(), "nfl")}
    x = T.pair("nfl", legs["Jared Goff"], legs["Josh Allen"])
    assert x and x["kind"] == T.TWO_GAME and x["joint"] == x["independent"]
    assert x["price_dec"] == x["naive_dec"], "one book: the prices multiplied"


def test_two_books_cost_a_little_and_the_same_player_never_pairs():
    a = T._leg(_prop("A", "BUF", "MIA", "pass_yds", "OVER", 249.5, -110, 0.56), 0.56, "edge")
    b = T._leg(_prop("B", "KC", "LV", "rush_yds", "OVER", 60.5, -110, 0.56, book="FanDuel"), 0.56, "edge")
    t = T.pair("nfl", a, b)
    assert abs(t["price_dec"] - t["naive_dec"] * (1 - T.TWO_BOOK_CUT)) < 1e-3
    assert T.pair("nfl", a, dict(a, market="rush_yds")) is None


def test_the_likely_pool_ranks_by_the_chance_both_hit_and_uses_each_leg_once():
    b = T.build(_board(), "nfl", plan={})
    lk = b["likely"]["tickets"]
    assert lk and all(len(t["legs"]) == 2 for t in lk)
    seen = [T._leg_id(l) for t in lk for l in t["legs"]]
    assert len(seen) == len(set(seen)), "every leg once per pool"
    sg = [t for t in lk if t["kind"] == T.SAME_GAME]
    assert [t["joint"] for t in sg] == sorted((t["joint"] for t in sg), reverse=True)


def test_the_edge_pool_posts_only_a_positive_return():
    b = T.build(_board(), "nfl", plan={})
    assert all(t["ev"] > 0 for t in b["edge"]["tickets"])


def test_only_a_two_game_parlay_carries_money():
    """Same-game pairs lost in every run of the study (-9.5% over 213 on the
    box's journal, 2026-10-31) while two-game pairs made 11.1% over 298, so a
    same-game pair is always tracked and a two-game pair is staked when both
    of its legs are."""
    board = _board()
    b = T.build(board, "nfl", plan={})
    edge = b["edge"]["tickets"]
    assert {t["kind"] for t in edge} == {T.SAME_GAME, T.TWO_GAME}, edge
    assert all(t["staked"] == (t["kind"] == T.TWO_GAME) for t in edge), \
        "Edge legs are staked by default; the same-game pair is tracked"
    assert all(t["stake_units"] == (T.STAKE_UNITS if t["staked"] else 0) for t in edge)
    assert not any(t["staked"] for t in b["likely"]["tickets"]), "NFL Most Likely is tracked"
    likely = {l["player"]: l for l in T.likely_legs(board, "nfl")}
    promoted = stakeplan.promoted("nfl")
    two = T.pair("nfl", likely["Jahmyr Gibbs"], likely["James Cook"])
    assert two["kind"] == T.TWO_GAME and T.staked("nfl", two, promoted), "a promoted league stakes it"
    assert not T.staked("nfl", two, {}), "control: NFL Most Likely is tracked"
    same = T.pair("nfl", likely["Jahmyr Gibbs"], likely["Jordan Addison"])
    assert same["kind"] == T.SAME_GAME and not T.staked("nfl", same, promoted)
    stopped = {"nfl": {"edge": {"staked": False}, "likely": {"staked": False}}}
    assert not any(t["staked"] for t in T.build(board, "nfl", plan=stopped)["edge"]["tickets"])


def test_the_reason_reads_in_words_without_the_doctrines_section_numbers():
    """The screen's notes cite the parlay doctrine ("— §4.1's strongest
    usable NFL correlation"); on the page a section number means nothing,
    and our own measurement after it is the part worth reading."""
    b = T.build(_board(), "nfl", plan={})
    whys = [t["why"] for p in ("edge", "likely") for t in b[p]["tickets"]]
    assert whys and not any("§" in w for w in whys), whys
    assert T.plain("one passing game wearing two jerseys — §4.1's strongest usable NFL correlation, "
                   "and measured at +0.64 on 2,844 of our own games") == \
        "one passing game wearing two jerseys — measured at +0.64 on 2,844 of our own games"
    assert T.plain("shared pace and script — §1.1's floor for any two same-game overs") == "shared pace and script"
    assert T.plain("") == ""


def test_a_drawdown_tracks_every_parlay():
    """§10.2 carries over from the screen: "when stakes are halved, parlays
    go to zero — not half"."""
    b = T.build(_board(), "nfl", plan={}, drawdown=True)
    assert b["edge"]["tickets"], "control: the Edge pool still builds"
    assert not any(t["staked"] or t["stake_units"] for p in ("edge", "likely") for t in b[p]["tickets"])
    assert "drawdown" in b["note"] and "drawdown" in T.report(b)


def test_the_board_hook_measures_the_drawdown_and_passes_it_on():
    from engine import parlays as P
    board = _board()
    P.attach(board, "nfl", state="drawdown")
    assert board["two_leg"]["drawdown"] is True
    assert not any(t["staked"] for p in ("edge", "likely") for t in board["two_leg"][p]["tickets"])
    other = {"recommendations": [], "most_likely": []}
    assert "two_leg" not in P.attach(other, "nhl", state="normal"), \
        "the five leagues only (college basketball joined 2026-11-14)"


def test_attach_runs_for_the_four_leagues_and_never_raises():
    board = _board()
    T.attach(board, "nfl", plan={})
    assert "two_leg" in board and board["two_leg"]["edge"]["tickets"]
    other = {"recommendations": [], "most_likely": []}
    T.attach(other, "nhl")
    assert "two_leg" not in other
    broken = {"recommendations": [{"recommended": True, "odds": "x"}], "most_likely": None}
    T.attach(broken, "nba", plan={})
    assert broken["two_leg"]["edge"]["tickets"] == []
    assert "Two-leg parlays:" in T.report(board["two_leg"])


# --- the journal ------------------------------------------------------------------------
def _journal():
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "t.db"))
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    return conn


def test_every_posted_parlay_journals_grades_off_its_legs_and_reports_apart():
    conn = _journal()
    board = _board()
    T.attach(board, "nfl", plan={})
    ledger.log_recommendations(conn, board)
    ledger.log_most_likely(conn, board)
    n = parlayledger.log_twoleg(conn, board["two_leg"], "nfl", board["date"])
    posted = len(board["two_leg"]["edge"]["tickets"]) + len(board["two_leg"]["likely"]["tickets"])
    assert n == posted and parlayledger.log_twoleg(conn, board["two_leg"], "nfl", board["date"]) == 0
    conn.execute("UPDATE bets SET status='won', pnl_units=1")
    conn.commit()
    res = parlayledger.settle(conn)
    assert res["settled"] == posted, res
    rep = parlayledger.report_twoleg(conn)
    assert rep["edge"]["graded"] == len(board["two_leg"]["edge"]["tickets"])
    assert rep["edge"]["wins"] == rep["edge"]["graded"] and rep["edge"]["net_units"] > 0
    assert rep["likely"]["staked_units"] == 0, "Most Likely parlays were tracked"
    assert set(rep["likely"]["by_kind"]) <= {T.SAME_GAME, T.TWO_GAME}


def test_a_lost_leg_loses_the_parlay():
    conn = _journal()
    board = _board()
    T.attach(board, "nfl", plan={})
    ledger.log_recommendations(conn, board)
    ledger.log_most_likely(conn, board)
    parlayledger.log_twoleg(conn, board["two_leg"], "nfl", board["date"])
    conn.execute("UPDATE bets SET status='won', pnl_units=1")
    conn.execute("UPDATE bets SET status='lost', pnl_units=-1 WHERE player='Jordan Addison'")
    conn.commit()
    parlayledger.settle(conn)
    lost = conn.execute("SELECT COUNT(*) FROM parlays p JOIN parlay_legs l ON l.parlay_id=p.id "
                        "WHERE l.player='Jordan Addison' AND p.status='lost'").fetchone()[0]
    with_him = conn.execute("SELECT COUNT(*) FROM parlay_legs WHERE player='Jordan Addison'").fetchone()[0]
    assert lost == with_him >= 1


# --- what it would have done -----------------------------------------------------------------
def test_the_backtest_pairs_each_graded_day_and_grades_it():
    conn = _journal()
    for d in ("2099-10-01", "2099-10-02"):
        for i, (team, opp) in enumerate((("DET", "MIN"), ("BUF", "MIA"), ("KC", "LV"), ("SF", "LA"))):
            conn.execute("INSERT INTO bets (ts, sport, date, game_day, player, team, market, side, line, book, odds,"
                         " hit_prob, grade, stake_units, stake_dollars, status, pnl_units, category)"
                         " VALUES ('t','nba',?,?,?,?,'points','OVER',10.5,'DK',-200,?, 'Likely',0.25,0,?,?,'likely')",
                         (d, d, f"P{i}{d}", team, 0.8 - i * 0.01, "won" if i % 2 == 0 else "lost",
                          0.125 if i % 2 == 0 else -0.25))
    conn.commit()
    games = {("nba", "2099-10-01", "DET"): "MIN", ("nba", "2099-10-01", "MIN"): "DET"}
    bt = T.backtest(conn, since="2099-01-01", games=games)
    allrow = next(r for r in bt["rows"] if r["sport"] == "all" and r["pool"] == "likely")
    assert allrow["parlays"] == 4, allrow
    assert allrow["won"] == 0, "every pair holds one loser"
    assert allrow["roi"] == -1.0
    assert "paired the way tonight's board is" in bt["rule"]


def test_the_schedule_reads_a_daily_sports_day_from_its_period():
    """The daily sports leave `date` empty and keep the day in `period`
    (engine/db). The first box run read `date` alone, found only football's
    272 games, and graded an MLB or NBA pick on each team of one game as two
    games."""
    import sqlite3
    h = sqlite3.connect(":memory:")
    h.execute("CREATE TABLE games (sport TEXT, season INTEGER, period TEXT, game_id TEXT, "
              "home TEXT, away TEXT, date TEXT)")
    h.executemany("INSERT INTO games VALUES (?,?,?,?,?,?,?)", [
        ("nba", 2026, "2026-10-25", "1", "BOS", "NYK", None),
        ("nfl", 2026, "8", "2", "DET", "MIN", "2026-10-26"),
        ("mlb", 2026, "2026-10-01", "3", "LAD", "SD", None),
        ("cfb", 2026, "9", "4", "UGA", "FLA", None),
        ("nba", 2026, "2026-07-01", "5", "LAL", "DEN", None),
    ])
    g = T.schedule(h, "2026-08-06")
    assert g[("nba", "2026-10-25", "BOS")] == "NYK" and g[("nba", "2026-10-25", "NYK")] == "BOS"
    assert g[("nfl", "2026-10-26", "MIN")] == "DET"
    assert g[("mlb", "2026-10-01", "SD")] == "LAD"
    assert not any(k[1] in ("8", "9") for k in g), "a week label is not a day"
    assert ("nba", "2026-07-01", "LAL") not in g, "before the window"


def test_the_study_prints_every_section_on_a_journal():
    """tools/parlay_study.py, step JD on the box: it must run end to end."""
    import contextlib
    import importlib.util
    import io
    conn = _journal()
    for i, (team, opp) in enumerate((("DET", "MIN"), ("BUF", "MIA"), ("KC", "LV"), ("SF", "LA"))):
        conn.execute("INSERT INTO bets (ts, sport, date, game_day, player, team, market, side, line, book, odds,"
                     " hit_prob, grade, stake_units, stake_dollars, status, pnl_units, category)"
                     " VALUES ('t','nfl','2099-10-04','2099-10-04',?,?,'rec_yds','OVER',40.5,'DK',-200,0.8,"
                     "'Likely',0.25,0,'won',0.125,'likely')", (f"P{i}", team))
    conn.commit()
    path = next(r[2] for r in conn.execute("PRAGMA database_list") if r[1] == "main")
    spec = importlib.util.spec_from_file_location("parlay_study", os.path.join(ROOT, "tools", "parlay_study.py"))
    study = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(study)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert study.main(["--db", path, "--since", "2099-01-01"]) == 0
    text = out.getvalue()
    for head in ("1. As the Record page shows it", "2. How many a day", "3. The two halves",
                 "4. The same-game rule", "5. The parlays the board has journaled live"):
        assert head in text, head


def test_the_export_ships_the_parlays_and_the_backtest():
    src = open(os.path.join(ROOT, "engine", "ledger.py"), encoding="utf-8").read()
    assert '"two_leg": _two_leg_record(conn)' in src


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
                traceback.print_exc()
    if fails:
        print(f"{ran} passed, {fails} failed")
        sys.exit(1)
    print(f"\n{ran} tests passed.")
