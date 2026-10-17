"""The research lab: a registry that checks itself, and experiments whose arithmetic is pinned.

Ethan, 2026-10-17, the research spec: every candidate method in a registry
with its prior art, novelty class and evidence status; data sources labelled
VERIFIED / PARTIALLY VERIFIED / UNVERIFIED / UNAVAILABLE; experiments with
their bar written before they run. research/ holds the lab.

What these hold: the committed registry and audit break none of their own
rules, and the checker catches every way an entry could lie (a measured
status with no result, a number outside its own interval, a source that is
not audited, an unknown novelty class); both load into the spec's tables;
EXP-001's distributions are distributions (a pmf sums to one, a CDF climbs)
and CRPS is zero for a perfect forecast; EXP-002's ridge recovers a known
line; EXP-003a's de-vig sums to one and its rates use only earlier weeks;
EXP-003b reads the journal read-only, scores only weeks after enough came
before, and says NOT YET when that is too few; the box audit opens nothing
for writing.

Run directly: `python3 tests/test_research_lab.py`
"""
import copy
import math
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research import registry as R                               # noqa: E402
from research import exp1_two_stage as E1                        # noqa: E402
from research import exp2_interactions as E2                     # noqa: E402
from research import exp3_totals as E3                           # noqa: E402
from research import exp3_props_box as E3B                       # noqa: E402
from research import audit_box as AB                             # noqa: E402
from research import exp1_lines_box as EL                        # noqa: E402
from research import exp4_college_two_stage as E4                # noqa: E402
from research import exp5_symbolic_residuals as E5               # noqa: E402


# --- the registry -------------------------------------------------------------
def test_the_committed_registry_and_audit_are_sound():
    reg, src = R.load(), R.load_sources()
    assert R.problems(reg, src) == [], R.problems(reg, src)
    ids = [e["id"] for e in reg["experiments"]]
    for want in ("EXP-001", "EXP-001b", "EXP-002", "EXP-003a", "EXP-003b"):
        assert want in ids
    statuses = {s["status"] for s in src["sources"]}
    assert statuses <= set(R.SOURCE_STATUSES)
    assert "UNVERIFIED" in statuses, "the vendors not read today stay unverified"
    vendors = {s["id"]: s["status"] for s in src["sources"]}
    assert vendors["SRC-PARLAYAPI"] == vendors["SRC-SPORTSGAMEODDS"] == vendors["SRC-FLASHPROPS"] == "UNVERIFIED"
    assert vendors["SRC-ODDSAPI"] != "VERIFIED", "a product page is never VERIFIED; only counted data is"


def test_the_checker_catches_every_way_an_entry_could_lie():
    reg, src = R.load(), R.load_sources()
    bad = copy.deepcopy(reg)
    e = bad["experiments"][0]
    e["status"] = "HOLDOUT VALIDATED"
    e["results"] = []
    assert any("claims a measurement" in p for p in R.problems(bad, src))
    bad = copy.deepcopy(reg)
    bad["experiments"][0]["results"][0]["value"] = 9.0
    assert any("outside its own interval" in p for p in R.problems(bad, src))
    bad = copy.deepcopy(reg)
    bad["experiments"][0]["data"] = ["SRC-NOWHERE"]
    assert any("not in sources.json" in p for p in R.problems(bad, src))
    bad = copy.deepcopy(reg)
    bad["experiments"][0]["novelty"] = "9"
    assert any("not a known class" in p for p in R.problems(bad, src))
    bad = copy.deepcopy(reg)
    del bad["experiments"][0]["prior_art"]
    assert any("missing prior_art" in p for p in R.problems(bad, src))
    bad = copy.deepcopy(reg)
    bad["experiments"][0]["code"] = "research/nope.py"
    assert any("does not exist" in p for p in R.problems(bad, src))
    badsrc = copy.deepcopy(src)
    badsrc["sources"][0]["status"] = "PROBABLY FINE"
    assert any("is not one of" in p for p in R.problems(reg, badsrc))


def test_both_load_into_the_spec_tables():
    reg, src = R.load(), R.load_sources()
    conn = sqlite3.connect(":memory:")
    got = R.to_sqlite(conn, reg, src)
    assert got["experiments"] == len(reg["experiments"]) == conn.execute("SELECT COUNT(*) FROM experiments").fetchone()[0]
    assert got["sources"] == conn.execute("SELECT COUNT(*) FROM data_sources").fetchone()[0]
    assert got["results"] == conn.execute("SELECT COUNT(*) FROM experiment_results").fetchone()[0] > 0
    d = conn.execute("SELECT decision FROM experiment_decisions WHERE experiment_id='EXP-001' AND subject='receptions'").fetchone()[0]
    assert d.startswith("ADVANCE")
    again = R.to_sqlite(conn, reg, src)
    assert again == got, "loading twice replaces, never doubles"


# --- EXP-001 ------------------------------------------------------------------
def test_the_two_stage_pieces_are_distributions():
    pmf = E1.nb_pmf(6.0, 5.0, 60)
    assert abs(sum(pmf) - 1.0) < 1e-9
    assert abs(sum(k * p for k, p in enumerate(pmf)) - 6.0) < 0.05
    assert E1.binom_cdf(-1, 5, 0.6) == 0.0 and E1.binom_cdf(5, 5, 0.6) == 1.0
    assert abs(E1.binom_cdf(2, 5, 0.5) - 0.5) < 1e-12
    grid = [float(t) for t in range(0, 16)]
    perfect = [1.0 if t >= 4 else 0.0 for t in grid]
    assert E1.crps(perfect, grid, 4.0) == 0.0
    assert E1.crps([0.5] * 16, grid, 4.0) > 0


def test_the_bootstrap_and_the_decision_follow_the_bar():
    rows = [{"who": f"p{i % 7}", "a": 1.0, "b": 0.9} for i in range(70)]
    mean, lo, hi = E1.boot_diff(rows)
    assert abs(mean + 0.1) < 1e-12 and abs(lo + 0.1) < 1e-9 and abs(hi + 0.1) < 1e-9
    assert E1.decide(+0.01, None).startswith("REJECTED")
    assert E1.decide(-0.01, None).startswith("validation passed")
    assert E1.decide(-0.01, (-0.02, -0.03, -0.001)) == "ADVANCE"
    assert E1.decide(-0.01, (-0.02, -0.04, +0.001)) == "INCONCLUSIVE"
    assert E1.decide(-0.01, (+0.02, -0.01, +0.05)).startswith("REJECTED")


# --- EXP-002 ------------------------------------------------------------------
def test_the_ridge_recovers_a_known_line():
    X = [[1.0, x, x * x] for x in [i / 10 for i in range(50)]]
    y = [2.0 + 3.0 * r[1] - 0.5 * r[2] for r in X]
    w = E2.ridge(X, y, 0.0)
    assert all(abs(a - b) < 1e-6 for a, b in zip(w, (2.0, 3.0, -0.5))), w
    shrunk = E2.ridge(X, y, 1000.0)
    assert shrunk[1] < w[1] - 0.5, (shrunk[1], w[1], "the penalty pulls the slope in, well clear of a rounding")
    flat = E2.ridge(X, y, 1e9)
    assert abs(flat[0] - sum(y) / len(y)) < 1e-3, "the intercept is never penalised: it lands on the mean"


# --- EXP-003a -----------------------------------------------------------------
def test_the_devig_and_the_rates_use_only_what_came_before():
    assert abs(E3.devig(-110, -110) - 0.5) < 1e-12
    p = E3.devig(-130, +110)
    assert 0.5 < p < 1 and abs(E3.devig(+110, -130) - (1 - p)) < 1e-12
    def game(wk, h, a, hs, as_, line):
        return {"season": "2020", "week": str(wk), "game_type": "REG", "home_team": h, "away_team": a,
                "home_score": str(hs), "away_score": str(as_), "total_line": str(line), "over_odds": "-110",
                "under_odds": "-110", "roof": "outdoors", "surface": "grass", "home_rest": "7", "away_rest": "7",
                "div_game": "0"}
    gs = [game(1, "A", "B", 30, 30, 40), game(1, "C", "D", 10, 10, 40),
          game(2, "A", "C", 30, 30, 40), game(2, "B", "D", 10, 10, 40),
          game(3, "A", "D", 99, 99, 41.5)]
    rows = E3.rows(gs)
    assert len(rows) == 1 and rows[0]["wk"] == "2020-03"
    # A scored 60 and allowed 60 over two games; D scored 20 and allowed 20 —
    # week 3's own 198 points are nowhere in the expectation.
    prior = 21.0
    a_sc = (60 + 4 * prior) / 6
    d_al = (20 + 4 * prior) / 6
    assert abs(rows[0]["mu"] - ((a_sc + d_al) / 2 + ((20 + 4 * prior) / 6 + (60 + 4 * prior) / 6) / 2)) < 1e-9


# --- EXP-003b -----------------------------------------------------------------
def _journal(path: str, weeks: int, per_week: int):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE bets (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, sport TEXT, date TEXT, "
                 "game_day TEXT, player TEXT, market TEXT, side TEXT, line REAL, odds INTEGER, hit_prob REAL, "
                 "status TEXT, category TEXT, fair_consensus REAL, lead_min REAL)")
    import datetime as dt
    import random
    rng = random.Random(1)
    d0 = dt.date(2026, 1, 5)
    cols = "ts, sport, date, game_day, player, market, side, line, odds, hit_prob, status, category, fair_consensus, lead_min"
    for w in range(weeks):
        for i in range(per_week):
            truth = rng.uniform(0.35, 0.65)
            won = rng.random() < truth
            day = (d0 + dt.timedelta(days=7 * w + i % 6)).isoformat()
            conn.execute(f"INSERT INTO bets ({cols}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (f"{day}T12:00:00", "nfl", "2026-W%02d" % (w + 1), day, f"P{i}", "receptions",
                          "OVER" if i % 2 else "UNDER", 4.5, -110, min(0.95, truth + 0.08),
                          "won" if won else "lost", "main", truth if i % 2 else 1 - truth, 600.0))
    # No journaled fair: its market chance can only come from our own snapshots.
    conn.execute(f"INSERT INTO bets ({cols}) VALUES ('2026-01-05T12:00:00','nfl','2026-W01','2026-01-05',"
                 "'Snap Man','receptions','OVER',5.5,-110,0.6,'won','likely',NULL,0)")
    # A prediction-market pick: a different product, never read.
    conn.execute(f"INSERT INTO bets ({cols}) VALUES ('2026-01-05T12:00:00','nfl','2026-W01','2026-01-05',"
                 "'Kalshi Guy','receptions','OVER',5.5,-110,0.6,'won','predmarket',0.5,0)")
    conn.commit()
    conn.close()


def _snapshots(path: str):
    import datetime as dt
    import json
    t = dt.datetime(2026, 1, 5, 11, 0, tzinfo=dt.timezone.utc).timestamp()     # an hour before the pick
    with open(path, "w", encoding="utf-8") as fh:
        for book, o, u in (("draftkings", -120, 100), ("fanduel", -118, -102), ("caesars", -125, 105)):
            fh.write(json.dumps({"ts": t, "player": "Snap Man", "market": "receptions", "book": book,
                                 "line": 5.5, "over_odds": o, "under_odds": u}) + "\n")


def test_the_journal_arm_scores_only_later_weeks_and_says_not_yet():
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "ledger.db")
        _journal(db, weeks=10, per_week=80)
        snaps = os.path.join(d, "line_history.jsonl")
        _snapshots(snaps)
        rows, skipped = E3B.load(db, None, snapshots=snaps)
        assert len(rows) == 801 and not skipped, (len(rows), skipped)
        snap = [x for x in rows if x["src"] == "snapshots"]
        assert len(snap) == 1 and 0.5 < snap[0]["c"] < 0.6, "rebuilt from three books' quotes before the pick"
        assert sum(1 for x in rows if x["src"] == "journaled") == 800
        none, skipped = E3B.load(db, None, snapshots=os.path.join(d, "missing.jsonl"))
        assert len(none) == 800 and skipped["no market chance at pick time"] == 1, "no quotes, no market, left out"
        scored = E3B.walk(rows)
        first = min(x["wk"] for x in scored)
        assert sum(1 for x in rows if x["wk"] < first) >= E3B.MIN_TRAIN, "a week is scored only after enough came before"
        ll = {k: sum(E3B._ll(x[k], x["y"]) for x in scored) / len(scored) for k in ("a", "c", "d")}
        assert ll["c"] < ll["a"], "the made-up market is the truth here; ours overclaims by eight points"
        assert ll["d"] <= ll["a"] + 1e-3, "the blend learns to lean on the market"
        with open(db, "rb") as fh:
            before = fh.read()
        E3B.main(["--db", db])
        with open(db, "rb") as fh:
            assert fh.read() == before, "read-only"
        small = os.path.join(d, "small.db")
        _journal(small, weeks=3, per_week=50)
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            E3B.main(["--db", small])
        assert "NOT YET" in buf.getvalue()


# --- EXP-001c ----------------------------------------------------------------
def test_the_real_line_consensus_is_the_fields_and_only_before_the_start():
    assert EL.et_date("2025-09-08T00:15:00Z") == "2025-09-07", "a Sunday night kickoff is Sunday's game"
    assert EL.et_date("2025-10-12T13:30:00Z") == "2025-10-12", "a London morning is the same day"
    q = {"dk": (4.5, -120, 100), "fd": (4.5, -115, -105), "cz": (4.5, -125, 105), "mgm": (5.5, 110, -130)}
    line, fair, books, price = EL.consensus(q)
    assert line == 4.5 and books == 3 and 0.5 < fair < 0.6 and price == -120
    assert EL.consensus({"dk": (4.5, -120, 100), "fd": (4.5, -115, -105)}) is None, "two books are not a field"
    tie = {"a": (3.5, -110, -110), "b": (3.5, -110, -110), "c": (3.5, -110, -110),
           "d": (4.5, -110, -110), "e": (4.5, -110, -110), "f": (4.5, -110, -110)}
    assert EL.consensus(tie)[0] == 3.5, "a tie goes to the lower line"
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "h.db")
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE odds_history (sport TEXT, taken_at TEXT, event_id TEXT, home TEXT, away TEXT, "
                     "player TEXT, market TEXT, book TEXT, line REAL, over_odds INTEGER, under_odds INTEGER, commence_time TEXT)")
        start = "2025-09-07T17:00:00Z"
        rows = [("2025-09-07T12:00:00Z", "dk", 3.5, -110, -110), ("2025-09-07T16:00:00Z", "dk", 4.5, -120, 100),
                ("2025-09-07T16:00:00Z", "fd", 4.5, -115, -105), ("2025-09-07T16:00:00Z", "cz", 4.5, -125, 105),
                ("2025-09-07T18:00:00Z", "fd", 6.5, -300, 240)]          # in play: never read
        for t, b, ln, o, u in rows:
            conn.execute("INSERT INTO odds_history VALUES ('nfl',?,'e1','KC','BUF','Amon-Ra St. Brown','receptions',?,?,?,?,?)",
                         (t, b, ln, o, u, start))
        conn.commit()
        import datetime as dt
        from collections import Counter
        kick = dt.datetime(2025, 9, 7, 17, 0, tzinfo=dt.timezone.utc)
        funnel = Counter()
        props = EL.book_props(conn, {"amon ra st brown": [(kick, "2025-09-07")]}, funnel=funnel)
        conn.close()
    got = props[("amon ra st brown", "2025-09-07", "receptions")]
    assert got[0] == 4.5 and got[2] == 3, "each book's last quote before the kickoff; the in-play 6.5 never counts"
    assert funnel["quotes read"] == 5 and funnel["quotes before his next kickoff"] == 4
    assert funnel["props with a three-book consensus"] == 1
    # The kickoff comes from the schedule, not the row: 1 pm Eastern in September is 17:00 UTC.
    assert EL.kickoff_utc("2025-09-07", "13:00") == kick
    assert EL.kickoff_utc("2025-12-07", "13:00").hour == 18, "standard time is five hours behind"
    assert EL.kickoff_utc("", "13:00") is None


def test_the_calibrator_recovers_a_known_slope_and_the_join_scores_real_lines():
    import random
    rng = random.Random(3)
    pairs = []
    for _ in range(4000):
        p = rng.uniform(0.05, 0.95)
        true = EL._sig(0.5 * EL._logit(p))                     # the forecast is twice too extreme
        pairs.append((p, 1.0 if rng.random() < true else 0.0))
    cal = EL.Calibrator(pairs)
    assert 0.35 < cal.b < 0.65 and abs(cal.a) < 0.15, (cal.a, cal.b)
    # A made-up season, so the test needs no cache file and no network.
    season = [{"player_display_name": "Test Receiver", "position": "WR", "team": "DET", "opponent_team": "GB",
               "season": "2025", "week": str(w), "season_type": "REG", "game_id": f"2025_{w:02d}_DET_GB",
               "targets": "8", "receptions": str(4 + w % 2), "receiving_yards": "60", "carries": "0",
               "rushing_yards": "0", "attempts": "0"} for w in range(1, 6)]
    days = {f"2025_{w:02d}_DET_GB": f"2025-10-{w:02d}" for w in range(1, 6)}
    real_load, real_dates = E1.load, EL.game_dates
    E1.load = lambda s: season if s == 2025 else []
    EL.game_dates = lambda: days
    try:
        x = next(r for r in E1.rows_for(2025) if r["m"] == "receptions")
        day = days[x["gid"]]
        from engine.sources.oddsapi import normalize_name
        line = 0.5 if x["y"] >= 1 else 1.5
        props = {(normalize_name(x["name"]), day, "receptions"): (line, 0.55, 4, -125)}

        class Stub:
            def cdf_a(self, r, t):
                return 0.4

            def cdf_b(self, r, ts):
                return [0.3 for _ in ts]
        ident = EL.Calibrator([(0.2, 0.0), (0.8, 1.0)] * 50)
        out = EL.scored(Stub(), {m: (ident, ident) for m in EL.MARKETS}, props, E1.rows_for(2025))
    finally:
        E1.load, EL.game_dates = real_load, real_dates
    mine = [r for r in out if r["day"] == day]
    assert len(mine) == 1 and mine[0]["A"] == 0.6 and abs(mine[0]["B"] - 0.7) < 1e-12 and mine[0]["C"] == 0.55
    assert mine[0]["y"] == (1.0 if x["y"] > line else 0.0) and not mine[0]["after"], "2025 is development"


def test_the_box_audit_opens_nothing_for_writing():
    with tempfile.TemporaryDirectory() as d:
        db = Path(d) / "h.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE odds_history (sport TEXT, taken_at TEXT, event_id TEXT, home TEXT, away TEXT, "
                     "player TEXT, market TEXT, book TEXT, line REAL, over_odds INTEGER, under_odds INTEGER, commence_time TEXT)")
        conn.execute("INSERT INTO odds_history VALUES ('nfl','2025-09-07T16:00:00Z','e1','KC','BUF','X','player_receptions','fanduel',4.5,-110,-110,'')")
        conn.execute("INSERT INTO odds_history VALUES ('nfl','2025-09-07T16:00:00Z','e1','KC','BUF','','totals','fanduel',47.5,-110,-110,'')")
        conn.commit()
        conn.close()
        ro = AB._ro(db)
        lines = AB.odds_history(ro)
        assert any("1 events" in ln for ln in lines) and any("player_receptions" in ln for ln in lines)
        try:
            ro.execute("DELETE FROM odds_history")
            wrote = True
        except sqlite3.OperationalError:
            wrote = False
        assert not wrote, "the audit's connection must be read-only"
        assert AB._ro(Path(d) / "missing.db") is None


def test_the_college_replication_keeps_its_splits_apart_and_its_roles_honest():
    for fam, (markets, train, valid, hold) in E4.FAMILIES.items():
        def span(period):
            return [(s, lo, hi) for s, lo, hi in period]
        last_train = max((s, hi) for s, _lo, hi in span(train))
        first_valid = min((s, lo) for s, lo, _hi in span(valid))
        last_valid = max((s, hi) for s, _lo, hi in span(valid))
        first_hold = min((s, lo) for s, lo, _hi in span(hold))
        assert last_train < first_valid and last_valid < first_hold, f"{fam}: periods overlap"
        assert len(E4.TESTS[fam]) == 2 and all(m in markets for m, _k in E4.TESTS[fam])
    # Receiving never trains on a season whose incompletions mostly name no target.
    assert all(s >= 2025 for s, _lo, _hi in E4.FAMILIES["EXP-004b"][1])
    g = lambda **st: {"stats": st}                                   # noqa: E731
    assert E4.role("WR", []) == "REC" and E4.role("FB", []) == "RB" and E4.role("QB", []) == "QB"
    assert E4.role("", [g(carries=12, targets=1), g(carries=9, targets=2)]) == "RB"
    assert E4.role("", [g(carries=1, targets=6)]) == "REC"
    assert E4.role("", [g(carries=8, pass_att=20)]) is None, "a passer is left out"


def test_the_college_rows_use_only_earlier_games():
    def game(week, carries, yds):
        return {"week": week, "gid": f"g{week}", "pos": "RB",
                "stats": {"carries": float(carries), "rush_yds": float(yds), "targets": 1.0, "receptions": 1.0,
                          "rec_yds": 5.0}}
    season = {("Back One", "State"): [game(w, 15 + w, 70 + 3 * w) for w in range(1, 9)]}
    keep = dict(E4._CACHE)
    E4._CACHE.clear()
    E4._CACHE.update({2030: season, 2029: {}})
    try:
        rows = E4.rows_for(2030, ("rush_yds",))
    finally:
        E4._CACHE.clear()
        E4._CACHE.update(keep)
    assert rows and all(r["week"] >= 4 for r in rows)
    for r in rows:
        before = [x for x in season[("Back One", "State")] if x["week"] < r["week"]]
        assert r["opps"] == sum(x["stats"]["carries"] for x in before), "history is the games before it only"
        assert r["y"] == 70 + 3 * r["week"] and r["o"] == 15 + r["week"]
        assert r["who"] == "Back One|State|2030" and r["pos"] == "RB"


def test_the_equation_search_space_is_what_its_docstring_says():
    eqs = E5.equations()
    assert len(eqs) == 1680 and len({name for name, _c, _s in eqs}) == 1680, "every equation once"
    assert sum(1 for _n, _c, sp in eqs if sp[0] == "leaf") == 24
    assert min(c for _n, c, _s in eqs) == 1 and max(c for _n, c, _s in eqs) == 5
    f = [{"a": 3.0, "b": 0.0, "o": 0.0, "e": 0.0, "w": 0.0, "v": 0.0}]
    assert E5.values(("pair", ("x", "a"), "/", ("x", "b")), f) == [3.0], "division by zero is protected"
    assert E5.ols([1.0, 1.0, 1.0], [0.0, 1.0, 2.0]) is None, "a constant equation has no slope to fit"


def test_the_search_finds_a_planted_shrink_and_refuses_noise():
    class _Fit:
        def mean_b(self, x):
            return 0.5 * x["mu_o"]
    rng = __import__("random").Random(3)

    def rows(n, planted):
        out = []
        for i in range(n):
            a = rng.uniform(1, 9)
            y = a + (2.0 - 0.3 * a if planted else 0.0) + rng.gauss(0, 0.5)
            out.append({"m": "receptions", "mu_a": a, "mu_o": rng.uniform(2, 10), "prod": rng.uniform(5, 40),
                        "opps": rng.uniform(10, 60), "week": rng.randint(4, 17), "y": y})
        return out
    best = E5.search(rows(1500, True), rows(800, True), _Fit())[0]
    assert best[2] == "a", best[2]
    c0, c1 = best[5]
    assert abs(c1 + 0.3) < 0.05 and abs(c0 - 2.0) < 0.3, best[5]
    noise = E5.search(rows(1500, False), rows(800, False), _Fit())
    assert noise[0][2] == "no correction", "with nothing planted the complexity price keeps the baseline"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
