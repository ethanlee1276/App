"""WNBA off the record until the model earns its way back.

Ethan, 2026-09-21: *"Stop recording WNBA on the record and make it paper
till we make the model better and remove wnba from the record so it's
not hurting us. Make it all paper."*

PAPER WOULD NOT HAVE DONE IT, which is why this is not paper mode.
`ledger.BOOK` is ("main", "paper") and `performance` counts both —
because on 2026-08-13 he asked for exactly that: "Combine our paper
record and normal money record." So filing WNBA as paper stops the
DOLLARS and leaves every unit, win, loss and ROI point of it in the
headline, which is the number he asked to stop it hurting. `paper_mode`
is also one global switch, not a per-league one.

A benched league goes to a category OUTSIDE `BOOK`. That is what takes
it out of `performance`, and it is the whole mechanism.

WHAT THE BENCH IS NOT. It is not a deletion and not a silence. The
picks are still made, still journaled, still graded, and still shown —
under their own heading in `SHADOW_SECTIONS`, because a league whose
rows simply stopped appearing is the misleading quiet this project
keeps being fixed for. The bench is a claim we should be held to: we
said the model was not good enough, and this is where that gets
checked.

THE SEALED FORECAST LOG IS UNTOUCHED AND DOES NOT BREAK — and the first
version of this warning, given to Ethan before the schema was read,
said it would. It does not: `verify_forecast_log` recomputes from the
log's OWN copy of `category`, and `seal_forecasts` joins on `bet_id` and
will not re-seal a row already in the chain. The log records what was
CLAIMED at the time; this table records what was decided afterwards.
They are supposed to be able to differ.

MONEY MOVES IN TWO PLACES, NOT ONE. The Edge book is the headline, but
`LIKELY_LIVE_SPORTS` had WNBA staking 0.25u of real dollars on the
likelihood board since 2026-09-19. "Make it all paper" means no WNBA
money anywhere.

Run directly:
`python3 tests/test_a_benched_league_leaves_the_headline.py`
"""

import datetime as dt
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import ledger                                    # noqa: E402

SRC = (ROOT / "engine" / "ledger.py").read_text(encoding="utf-8")
SOON = (dt.datetime.utcnow() + dt.timedelta(days=1)).date().isoformat()
# Yesterday, not a written-down day: a settled fixture pinned to a
# literal date ages out of `RECORD_EPOCH`'s window and starts failing on
# a morning nobody touched this file — the way the day's-pick tests went
# red at midnight on 2026-09-20.
PAST = (dt.datetime.utcnow() - dt.timedelta(days=1)).date().isoformat()

_INS = ("INSERT INTO bets (ts,sport,date,player,market,side,line,odds,"
        "stake_units,stake_dollars,status,category,actual,pnl_units) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)")


def _ledger(path=None):
    conn = ledger.connect(path or (Path(tempfile.mkdtemp()) / "l.db"))
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1)
    return conn


def _settled(conn, sport, category="main"):
    conn.execute(_INS, (PAST + "T00:00:00", sport, PAST, "X",
                        "pts", "OVER", 20.5, -110, 1.0, 10.0, "lost",
                        category, 12, -1.0))
    conn.commit()


def _prop(**kw):
    row = {"player": "A Wilson", "team": "LV", "opponent": "IND",
           "market": "pts", "market_label": "Points", "side": "OVER",
           "line": 20.5, "book": "fanduel", "odds": -115, "hit_prob": 0.62,
           "raw_prob": 0.62, "implied_prob": 0.56, "model_prob": 0.62,
           "projection": 24.0, "game_date": SOON, "date": SOON,
           "has_market": True, "recommended": True, "edge": 0.06,
           "confidence": 0.7, "grade": "A", "stake_units": 1.0,
           "logs": [], "recent_values": []}
    row.update(kw)
    return row


# --- the bench is outside the headline book ----------------------------
def test_the_bench_is_not_in_the_book_the_headline_counts():
    """THE ONE THING THAT MAKES ANY OF THIS WORK. If the bench category
    were inside `BOOK`, every assertion below would pass while the
    number Ethan asked to protect kept moving."""
    assert ledger.BENCH_CATEGORY not in ledger.BOOK
    assert ledger.BENCH_CATEGORY not in ledger.RECOMMENDED_CATEGORIES


def test_paper_would_not_have_worked_and_the_reason_is_written_down():
    """`BOOK` is ("main", "paper") on Ethan's own 2026-08-13 instruction,
    so "make it paper" would have left WNBA in the headline. The next
    person to reach for paper mode has to meet that."""
    assert "paper" in ledger.BOOK, "the premise of this whole file moved"
    i = SRC.index("BENCH_CATEGORY = ")
    why = SRC[max(0, i - 2000):i]
    assert "2026-08-13" in why, "nothing records why paper was not used"
    assert "paper_mode" in why, "nothing says the paper switch is global"


def test_wnba_is_benched_and_the_list_is_the_only_switch():
    assert ledger.is_benched("wnba") and ledger.is_benched("WNBA")
    for sp in ("nfl", "cfb", "mlb", "nba"):
        assert not ledger.is_benched(sp), sp


def test_one_answer_for_which_book_a_fresh_row_belongs_to():
    """`log_recommendations` files props and game bets through two
    separate inserts. A bench honoured by one of them is not a bench —
    the shape `game_day` took when eight inserts of eleven forgot it."""
    assert ledger.book_for("wnba", False) == ledger.BENCH_CATEGORY
    assert ledger.book_for("wnba", True) == ledger.BENCH_CATEGORY
    assert ledger.book_for("nfl", False) == "main"
    assert ledger.book_for("nfl", True) == "paper"


# --- new rows ----------------------------------------------------------
def test_a_new_wnba_pick_is_journaled_to_the_bench_with_no_dollars():
    conn = _ledger()
    ledger.log_recommendations(conn, {
        "sport": "wnba", "date": SOON, "recommendations": [_prop()]})
    got = conn.execute(
        "SELECT category, stake_units, stake_dollars FROM bets").fetchone()
    assert got["category"] == ledger.BENCH_CATEGORY, dict(got)
    assert got["stake_dollars"] == 0.0, dict(got)
    # THE UNITS STAY AS SIZED. That is what keeps the bench measurable —
    # `performance` drops any row staked at zero, so zeroing the units
    # would make the benched record ungradeable and the bench pointless.
    assert got["stake_units"] > 0, dict(got)


def test_a_new_wnba_GAME_bet_is_benched_too():
    """That insert named no category at all and leaned on the schema's
    `DEFAULT 'main'`, so a bench applied only at the props loop would
    have sent every WNBA game bet straight to the headline."""
    conn = _ledger()
    ledger.log_recommendations(conn, {
        "sport": "wnba", "date": SOON, "recommendations": [],
        "game_bets": [{"recommended": True, "bet_type": "moneyline",
                       "market": "moneyline", "pick": "LV", "team": "LV",
                       "home": "LV", "away": "IND", "book": "fanduel",
                       "odds": -122, "win_prob": 0.58, "edge": 0.03,
                       "confidence": 0.7, "grade": "B+", "stake_units": 1.0,
                       "date": SOON, "game_date": SOON}]})
    rows = conn.execute(
        "SELECT category, stake_dollars FROM bets").fetchall()
    assert rows, "the game bet was not journaled at all"
    for r in rows:
        assert r["category"] == ledger.BENCH_CATEGORY, dict(r)
        assert r["stake_dollars"] == 0.0, dict(r)


def test_another_league_is_untouched():
    conn = _ledger()
    ledger.log_recommendations(conn, {
        "sport": "nfl", "date": SOON,
        "recommendations": [_prop(player="J Allen", market="pass_yds",
                                  line=240.5)]})
    got = conn.execute(
        "SELECT category, stake_dollars FROM bets").fetchone()
    assert got["category"] == "main", dict(got)
    assert got["stake_dollars"] > 0, dict(got)


def test_the_likelihood_board_stops_paying_for_wnba_too():
    """It staked 0.25u of REAL dollars on that board from 2026-09-19.
    Asked through `likely_is_staked` rather than by reading the list, so
    the two cannot be edited apart."""
    assert not ledger.likely_is_staked("wnba")
    assert "wnba" not in ledger.LIKELY_LIVE_SPORTS
    assert ledger.likely_is_staked("nfl"), "the other leagues came off too"


def test_re_adding_wnba_to_the_live_list_alone_still_pays_it_nothing():
    """The bench is asked FIRST, so the two lists cannot be edited apart.
    Somebody widening the likelihood board back out — a routine edit,
    made for a reason that has nothing to do with this — would otherwise
    quietly put real money back on a benched league."""
    real = ledger.LIKELY_LIVE_SPORTS
    try:
        ledger.LIKELY_LIVE_SPORTS = real + ("wnba",)
        assert not ledger.likely_is_staked("wnba")
    finally:
        ledger.LIKELY_LIVE_SPORTS = real


# --- the rows already on the record ------------------------------------
def test_settled_wnba_rows_leave_the_headline_and_keep_their_result():
    conn = _ledger()
    _settled(conn, "wnba")
    _settled(conn, "nfl")
    assert ledger.performance(conn, sport="wnba")["settled"] == 1
    assert ledger.bench_existing(conn) == {"wnba": 1}
    assert ledger.performance(conn, sport="wnba")["settled"] == 0
    assert ledger.performance(conn, sport="nfl")["settled"] == 1
    # Still there, still graded, still readable — moved, not deleted.
    got = conn.execute(
        "SELECT category, status, pnl_units, stake_dollars FROM bets "
        "WHERE sport='wnba'").fetchone()
    assert got["category"] == ledger.BENCH_CATEGORY, dict(got)
    assert got["status"] == "lost" and got["pnl_units"] == -1.0, dict(got)
    assert got["stake_dollars"] == 0.0, "benched dollars were left standing"


def test_open_wnba_rows_move_too():
    """A bet still running would otherwise settle into the headline days
    after the league left it."""
    conn = _ledger()
    conn.execute(_INS, (PAST + "T00:00:00", "wnba", SOON, "X", "pts",
                        "OVER", 20.5, -110, 1.0, 10.0, "open", "main",
                        None, None))
    conn.commit()
    assert ledger.bench_existing(conn) == {"wnba": 1}
    assert conn.execute("SELECT category FROM bets").fetchone()[0] \
        == ledger.BENCH_CATEGORY


def test_the_paper_half_of_the_book_moves_as_well():
    """`BOOK` is both categories, so a WNBA row filed as paper is in the
    headline too and has to come out with the rest."""
    conn = _ledger()
    _settled(conn, "wnba", category="paper")
    assert ledger.performance(conn, sport="wnba")["settled"] == 1
    ledger.bench_existing(conn)
    assert ledger.performance(conn, sport="wnba")["settled"] == 0


def test_the_sweep_is_idempotent():
    conn = _ledger()
    _settled(conn, "wnba")
    assert ledger.bench_existing(conn) == {"wnba": 1}
    assert ledger.bench_existing(conn) == {}


def test_it_runs_wherever_the_ledger_OPENS_not_by_hand():
    """A manual step gets run on one machine and forgotten on the next —
    the reason `seal_forecasts` is a sweep. Checked across two PROCESSES,
    because `_SCHEMA_DONE` is per-process and a second `connect()` in one
    process deliberately skips the migration path."""
    db = Path(tempfile.mkdtemp()) / "l.db"
    conn = _ledger(db)
    _settled(conn, "wnba")
    conn.close()
    out = subprocess.run(
        [sys.executable, "-c",
         "import sys; from engine import ledger as L;"
         "c = L.connect(sys.argv[1]);"
         "print(c.execute('SELECT category FROM bets').fetchone()[0])",
         str(db)],
        cwd=str(ROOT), capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-500:]
    assert out.stdout.strip() == ledger.BENCH_CATEGORY, out.stdout


# --- the books the bench cannot re-categorise --------------------------
def test_the_pick_of_the_day_pool_drops_the_bench_but_the_cut_keeps_it():
    """`potd` is the key the day-lock, the relock and the live tracker
    all query by, so those rows cannot be moved without breaking "the
    first qualifying pick is the day's pick". They come out of the
    POOLED figure instead — and the per-sport cut still answers in
    full, because a scoped read is somebody asking for the bench."""
    conn = _ledger()
    _settled(conn, "wnba", category=ledger.POTD_CATEGORY)
    _settled(conn, "nfl", category=ledger.POTD_CATEGORY)
    pooled = ledger.performance(conn, category=ledger.POTD_CATEGORY,
                                exclude_sports=ledger.BENCHED_SPORTS)
    assert pooled["settled"] == 1, pooled["settled"]
    scoped = ledger.performance(conn, sport="wnba",
                                category=ledger.POTD_CATEGORY,
                                exclude_sports=ledger.BENCHED_SPORTS)
    assert scoped["settled"] == 1, "the scoped cut went quiet instead"


def test_the_receipts_under_that_pool_match_it():
    """A list still showing a benched league's losses under a total that
    no longer counts them reads as a bug in the arithmetic."""
    conn = _ledger()
    _settled(conn, "wnba", category=ledger.POTD_CATEGORY)
    _settled(conn, "nfl", category=ledger.POTD_CATEGORY)
    got = ledger.recent_settled(conn, 40, category=ledger.POTD_CATEGORY,
                                exclude_sports=ledger.BENCHED_SPORTS)
    assert [r["sport"] for r in got] == ["nfl"], got
    # And the same rule as `performance`: asking FOR the bench answers.
    scoped = ledger.recent_settled(conn, 40, category=ledger.POTD_CATEGORY,
                                   sport="wnba",
                                   exclude_sports=ledger.BENCHED_SPORTS)
    assert [r["sport"] for r in scoped] == ["wnba"], scoped


def test_the_pooled_most_likely_report_drops_the_bench_too():
    """That board journals under `likely`/`likely_live`, which the live
    tracker reads by category as well. Same treatment, same reason —
    and `likely_report(sport="wnba")` still answers."""
    conn = _ledger()
    _settled(conn, "wnba", category="likely")
    _settled(conn, "nfl", category="likely")
    assert ledger.likely_report(conn)["settled"] == 1
    assert ledger.likely_report(conn)["calibration"]["n"] == 1
    assert ledger.likely_report(conn, sport="wnba")["settled"] == 1


def test_the_page_is_SERVED_a_pooled_pick_of_the_day_without_the_bench():
    """The assertions above hold `performance` to it; this holds the
    thing that actually reaches the browser. Two arguments at two call
    sites in `export_json` are exactly the kind that get added to the
    total and forgotten on the receipts."""
    import json
    conn = _ledger()
    _settled(conn, "wnba", category=ledger.POTD_CATEGORY)
    _settled(conn, "nfl", category=ledger.POTD_CATEGORY)
    out = Path(tempfile.mkdtemp()) / "record.json"
    ledger.export_json(conn, out)
    got = json.loads(out.read_text(encoding="utf-8"))
    assert got["potd"]["settled"] == 1, got["potd"]["settled"]
    assert [r["sport"] for r in got["potd_recent"]] == ["nfl"], \
        got["potd_recent"]
    # Shown, not vanished: the per-sport cut still carries it.
    assert got["potd_by_sport"]["wnba"]["settled"] == 1


def test_the_unscoped_headline_is_not_quietly_filtered_by_sport():
    """The Edge book takes the bench by MOVING its rows, which is what
    also zeroes the dollars. If `performance` filtered it by sport
    instead, a benched row would keep its stake and its category and
    only be hidden — and every droplet query, export and settle pass
    that reads the table directly would still see it on the record."""
    conn = _ledger()
    _settled(conn, "wnba")
    assert ledger.performance(conn)["settled"] == 1, \
        "a benched row was hidden from the headline rather than moved"
    ledger.bench_existing(conn)
    assert ledger.performance(conn)["settled"] == 0


# --- and it is shown, not vanished -------------------------------------
def test_the_bench_has_its_own_heading_on_the_record():
    keys = [k for k, _label, _cats in ledger.SHADOW_SECTIONS]
    assert ledger.BENCH_CATEGORY in keys, keys
    label = next(l for k, l, _c in ledger.SHADOW_SECTIONS
                 if k == ledger.BENCH_CATEGORY)
    assert "money" in label.lower() and "graded" in label.lower(), label


def test_the_bench_is_reversible_by_emptying_one_tuple():
    """When the model earns it back, nothing else should have to move."""
    real = ledger.BENCHED_SPORTS
    try:
        ledger.BENCHED_SPORTS = ()
        assert not ledger.is_benched("wnba")
        assert ledger.book_for("wnba", False) == "main"
        assert ledger.likely_is_staked("wnba") is False, \
            "LIKELY_LIVE_SPORTS has to be restored separately — say so"
    finally:
        ledger.BENCHED_SPORTS = real


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{fails} failed" if fails else f"\n{ran} tests passed.")
    sys.exit(1 if fails else 0)
