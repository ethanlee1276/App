"""The loss audit: the graded record, read-only, cut until the leaks show.

Ethan, 2026-09-28: "Go" — after six free data sources measured to zero,
the next place to look is where the published picks actually lost.
lossaudit.py reads the ledger in mode=ro, scores each book on its own by
sport, market, side, price, claim, tier, the close and the week, and names
the slices that lose by more than luck. Offline, on a fixture ledger in a
temp directory — never the box's.

Run directly: `python3 tests/test_the_loss_audit_names_the_leaks.py`
"""
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import lossaudit as LA                                         # noqa: E402
from engine import ledger                                      # noqa: E402
from engine.odds import american_to_decimal                    # noqa: E402


def _fixture(path):
    conn = ledger.connect(path)
    n = [0]

    def add(cat, market, side, odds, claim, status, stake=0.1, **kw):
        n[0] += 1
        pnl = (stake * (american_to_decimal(odds) - 1) if status == "won"
               else -stake if status == "lost" else 0.0)
        row = {"ts": "t", "sport": kw.get("sport", "nfl"), "date": kw.get("date", "2026-09-20"),
               "player": f"P{n[0]}", "market": market, "side": side, "line": kw.get("line", 49.5),
               "book": kw.get("book", "fanduel"), "odds": odds, "projection": kw.get("projection"),
               "hit_prob": claim, "grade": kw.get("grade"), "stake_units": stake, "status": status,
               "actual": kw.get("actual"), "pnl_units": pnl, "closing_line": kw.get("closing_line"),
               "closing_odds": kw.get("closing_odds"), "category": cat, "loss_cause": kw.get("cause")}
        conn.execute(f"INSERT INTO bets ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
                     tuple(row.values()))

    # THE PLANTED LEAK: Most Likely overs at -250 claiming 80% that hit 56%,
    # projected 10% high. Unders at -150 claiming 62% that hit 65%.
    for k in range(50):
        add("likely", "rec_yds", "OVER", -250, 0.80, "won" if k < 28 else "lost",
            projection=60.0, actual=54.0 + (k % 5) - 2, cause="variance" if k >= 28 else None)
    for k in range(40):
        add("likely", "rec_yds", "UNDER", -150, 0.62, "won" if k < 26 else "lost", projection=40.0,
            actual=40.0 + (k % 7) - 3)
    # What the reader never sees in a settled figure: a push counts as a
    # push, a void and an open bet are not settled at all.
    add("likely", "rec_yds", "OVER", -150, 0.6, "push")
    add("likely", "rec_yds", "OVER", -150, 0.6, "void")
    add("likely", "rec_yds", "OVER", -150, 0.6, "open")
    # The one board, by tier; and a book the audit does not read.
    for k in range(9):
        add("board", "receptions", "OVER", -180, 0.68, "won" if k % 3 else "lost",
            grade=("Top pick", "Strong", "Worth a look")[k % 3])
    add("longshot", "home_runs", "OVER", 400, 0.2, "lost")
    conn.commit()
    conn.close()


def _report(**kw):
    tmp = tempfile.mkdtemp()
    path = Path(tmp) / "ledger.db"
    _fixture(path)
    return LA.audit(LA.open_ledger(path), **kw), path


def test_the_ledger_is_opened_read_only():
    _rep, path = _report()
    conn = LA.open_ledger(path)
    try:
        conn.execute("UPDATE bets SET status='won'")
        raise AssertionError("the audit's connection wrote to the ledger")
    except sqlite3.OperationalError as exc:
        assert "readonly" in str(exc).replace(" ", "").lower()


def test_each_book_on_its_own_and_only_settled_bets():
    rep, _ = _report()
    assert set(rep["books"]) == {"Most Likely, paper", "The one board"}, "no longshots, no empty books"
    ml = rep["books"]["Most Likely, paper"]["total"]
    assert (ml["w"], ml["l"], ml["p"], ml["n"]) == (54, 36, 1, 90), "pushes counted, voids and open bets not"
    assert "tier" in rep["books"]["The one board"]["slices"]
    assert "tier" not in rep["books"]["Most Likely, paper"]["slices"]
    board = rep["books"]["The one board"]["slices"]["tier"]
    assert board["Top pick"]["l"] == 3 and board["Strong"]["w"] == 3


def test_the_planted_leak_is_named_with_both_reasons_and_the_healthy_side_is_not():
    rep, _ = _report()
    s = rep["books"]["Most Likely, paper"]["slices"]["market and side"]
    over, under = s["NFL rec_yds OVER"], s["NFL rec_yds UNDER"]
    assert over["hit"] == 0.56 and over["claim_avg"] == 0.8 and round(over["price_avg"], 3) == 0.714
    assert over["units"] < 0 and over["z_price"] <= -2 and over["z_claim"] <= -2
    assert under["units"] > 0
    leak = [r for r in rep["leaks"] if r["slice"] == "market and side"]
    assert [r["value"] for r in leak] == ["NFL rec_yds OVER"]
    assert leak[0]["why"] == "hit 56% where the prices needed 71%; hit 56% where we claimed 80%"
    assert rep["leaks"] == sorted(rep["leaks"], key=lambda r: r["units"]), "biggest loss first"
    assert any(r["value"] == "NFL rec_yds OVER" for r in rep["overclaimed"])
    assert not any(r["value"] == "NFL rec_yds UNDER" for r in rep["leaks"] + rep["overclaimed"])


def test_the_close_is_side_aware_on_the_line_and_the_price():
    def b(side, line, cl=None, odds=-110, co=None):
        return {"side": side, "line": line, "closing_line": cl, "odds": odds, "closing_odds": co}
    assert LA.close_verdict(b("OVER", 49.5, 51.5)) == "beat the close"
    assert LA.close_verdict(b("UNDER", 49.5, 51.5)) == "lost the close"
    assert LA.close_verdict(b("OVER", 0.5, 0.5, 400, 350)) == "beat the close", "a line that cannot move, read on price"
    assert LA.close_verdict(b("OVER", 0.5, 0.5, 400, 450)) == "lost the close"
    assert LA.close_verdict(b("OVER", 49.5, 49.5, -110, -110)) == "same as the close"
    assert LA.close_verdict(b("OVER", 49.5)) == "no close captured"


def test_the_projection_lean_is_measured_per_market():
    rep, _ = _report()
    pb = {r["market"]: r for r in rep["books"]["Most Likely, paper"]["projection"]}
    assert pb["NFL rec_yds"]["n"] == 90
    assert pb["NFL rec_yds"]["mean_miss"] < 0 and pb["NFL rec_yds"]["t"] < -2
    assert LA.projection_bias([{"sport": "nfl", "market": "x", "projection": 10, "actual": 9}] * 3) == [], \
        "under the floor a market is not measured"


def test_the_week_is_its_monday_and_the_causes_are_counted():
    assert LA._week({"date": "2026-09-27"}) == "week of 2026-09-21"
    assert LA._week({"date": "2026-09-21"}) == "week of 2026-09-21"
    # A football week label is the week, not ISO week 3 of the year (which
    # is how the box's first run came to file every NFL bet in January).
    assert LA._week({"date": "2026-W03", "sport": "nfl"}) == "NFL week 3"
    assert LA._week({"date": "2026-W12", "sport": "cfb"}) == "CFB week 12"
    rep, _ = _report()
    assert rep["books"]["Most Likely, paper"]["causes"] == {"variance": 22, "not tagged yet": 14}


def test_the_report_reads_as_a_page_and_scopes_by_sport_and_date():
    rep, path = _report()
    text = LA.render(rep)
    assert "=== Most Likely, paper" in text and "THE LEAKS" in text and "OVER-CLAIMED" in text
    assert "Most Likely, paper · market and side: NFL rec_yds OVER" in text
    assert LA.audit(LA.open_ledger(path), sport="mlb")["books"] == {}
    assert LA.audit(LA.open_ledger(path), since="2026-09-21")["books"] == {}
    assert "No settled bets" in LA.render(LA.audit(LA.open_ledger(path), sport="mlb"))


def _bet(**kw):
    d = {c: None for c in LA.COLUMNS}
    d.update({"sport": "nfl", "market": "receptions", "side": "OVER", "date": "2026-10-04",
              "book": "fanduel", "category": "board", "status": "won"})
    d.update(kw)
    return d


def test_each_book_is_cut_by_whether_our_chance_covered_the_price():
    # Ethan, 2026-10-11: 54% won still lost money. The cut that says whether
    # staking only what covers its price (the college rule) would help.
    assert LA.covered(_bet(odds=-150, hit_prob=0.62)) == "our chance covered the price"     # needs 60%
    assert LA.covered(_bet(odds=-200, hit_prob=0.62)) == "the price needed more than our chance"  # 66.7%
    assert LA.covered(_bet(odds=-150, hit_prob=0.60)) == "our chance covered the price", "exactly break-even covers"
    assert LA.covered(_bet(odds=None, hit_prob=0.6)) == "no price or no claim"
    assert LA.covered(_bet(odds=-150, hit_prob=None)) == "no price or no claim"
    rep, _ = _report()
    cut = rep["books"]["Most Likely, paper"]["slices"]["our chance against the price"]
    assert sum(s["n"] for s in cut.values()) == rep["books"]["Most Likely, paper"]["total"]["n"]


def test_bigger_units_multiply_the_same_picks_and_cannot_change_a_loss_into_a_win():
    bets = [_bet(grade="Top pick", odds=-150, stake_units=1.0, pnl_units=-1.0, status="lost"),
            _bet(grade="Strong", odds=-200, stake_units=1.0, pnl_units=0.5),
            _bet(grade="Worth a look", odds=100, stake_units=1.0, pnl_units=1.0),
            _bet(grade="Likely (staked)", odds=-110, stake_units=0.25, pnl_units=-0.25, status="lost")]
    sz = LA.sizing(bets)
    assert sz == {"n": 3, "flat": 16.7, "tiered": -33.3}, sz      # a book without tiers is not counted
    assert LA.sizing([_bet(grade="Likely (staked)", stake_units=0.25, pnl_units=0.2)]) is None
    rep, _ = _report()
    assert rep["books"]["The one board"]["sizing"]["n"] == 9
    assert rep["books"]["Most Likely, paper"]["sizing"] is None
    text = LA.render(rep)
    assert "bigger units on the same 9 picks" in text and "-- by our chance against the price" in text


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
