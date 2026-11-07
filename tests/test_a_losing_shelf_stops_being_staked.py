"""The Edge book gets the breaker the likelihood board already had.

Ethan, 2026-09-21: *"what makes people the most money without losing
the most money alongside increasing and boosting our ROI record."*

A FLAT STAKE CANNOT MOVE ROI — `engine/likelysize` proves it and a test
there pins it — so the only honest way the percentage goes up is fewer,
better bets. This is the mechanism for "fewer", and the Edge book did
not have one.

IT IS THE BOOK THAT NEEDED IT MOST: the most real money, the least
evidence. `boards.EDGE_AUC` is 0.468, below a coin flip, and
`engine/haircut` measured the claim at settlement — CFB claimed +12.53%
and landed -0.06%, NFL claimed +9.77% and landed -1.13%. The likelihood
board has cut a losing band since the day it was staked. This one had
nothing.

TWO BARS, NOT ONE. Two standard errors clear of zero on the losing side
(`ledger.LIVE_STOP_Z`, the same bar the likelihood breaker uses), AND
false-discovery control across every shelf tested — because that breaker
judges four bands and this judges every market of every sport, where a z
of -2 throws up a false stop by chance alone.

Run directly:
`python3 tests/test_a_losing_shelf_stops_being_staked.py`
"""

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import ledger                                     # noqa: E402
from engine import shelfstop                                  # noqa: E402

_INS = ("INSERT INTO bets (ts, sport, game_day, date, player, market, side,"
        " line, odds, hit_prob, grade, stake_units, stake_dollars, status,"
        " category, pnl_units) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)")


def _journal():
    conn = ledger.connect(Path(tempfile.mkdtemp()) / "l.db")
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1)
    return conn


def _shelf(conn, sport, market, n, hit, category=None):
    """`n` settled rows on one shelf at a fixed -110, hitting `hit`."""
    cat = category or ledger.BOOK[0]
    for i in range(n):
        won = int((i + 1) * hit) > int(i * hit)
        day = f"2026-09-{1 + i % 20:02d}"
        conn.execute(_INS, ("t", sport, day, day, f"{market}{i}", market,
                            "OVER", 4.5, -110, 0.55, "B", 1.0, 10.0,
                            "won" if won else "lost", cat,
                            0.909 if won else -1.0))
    conn.commit()


def _fake(n=12, **kw):
    """A board of `n` healthy shelves, plus whatever the caller adds."""
    out = [{"sport": "nfl", "market": f"m{i}", "n": 200, "roi": 0.02,
            "hit": 0.55, "z": 0.5} for i in range(n)]
    out.extend(kw.get("extra") or [])
    return out


# --- what gets stopped ---------------------------------------------------
def test_a_shelf_that_is_clearly_losing_is_stopped():
    conn = _journal()
    _shelf(conn, "nfl", "receptions", 200, 0.38)
    got = shelfstop.decide(shelfstop.measure(conn))
    stopped = {(s["sport"], s["market"]) for s in got["stopped"]}
    assert ("nfl", "receptions") in stopped, got["shelves"]


def test_a_shelf_that_is_paying_is_left_alone():
    conn = _journal()
    _shelf(conn, "nfl", "rush_yds", 200, 0.60)
    got = shelfstop.decide(shelfstop.measure(conn))
    assert got["stopped"] == [], got["stopped"]
    assert got["shelves"][0]["verdict"] == "run", got["shelves"]


def test_a_thin_shelf_is_never_stopped_however_bad_it_looks():
    """`pass_td 2 bets -22.20%` is a real line from a 2026-09-16 run.
    Acting on it is the error this repo has made more than any other."""
    conn = _journal()
    _shelf(conn, "nfl", "pass_tds", 6, 0.0)
    got = shelfstop.decide(shelfstop.measure(conn))
    assert got["stopped"] == [], got["stopped"]
    assert "needed before this shelf" in got["shelves"][0]["why"]


def test_the_floor_is_a_real_number_of_rows():
    assert shelfstop.MIN_N >= 60, shelfstop.MIN_N


# --- and what the multiple tests do to that ------------------------------
def test_one_bad_shelf_among_many_is_held_for_review_not_stopped():
    """SIXTY SHELVES AT z -2 THROWS UP MORE THAN ONE FALSE STOP A RUN.
    The likelihood breaker judges four bands and can use the bare z;
    this judges every market of every sport and cannot."""
    marginal = {"sport": "nfl", "market": "odd", "n": 200, "roi": -0.05,
                "hit": 0.47, "z": -2.05}
    got = shelfstop.decide(_fake(40, extra=[marginal]))
    assert got["stopped"] == [], got["stopped"]
    odd = next(s for s in got["shelves"] if s["market"] == "odd")
    assert odd["verdict"] == "review", odd
    assert "every shelf tested is counted" in odd["why"], odd["why"]


def test_a_shelf_that_is_badly_losing_still_survives_the_control():
    """The control must not be so strict it never fires. That is not
    caution, it is a rule written to do nothing."""
    awful = {"sport": "nfl", "market": "bad", "n": 200, "roi": -0.27,
             "hit": 0.38, "z": -4.19}
    got = shelfstop.decide(_fake(40, extra=[awful]))
    assert [(s["sport"], s["market"]) for s in got["stopped"]] == [
        ("nfl", "bad")], got["stopped"]


def test_the_number_of_tests_is_every_eligible_shelf():
    """Shrinking m after peeking is how false-discovery control dies —
    `losspatterns._bh` says so in its own docstring."""
    def awful():
        # A FRESH DICT EACH TIME. `_bh` writes `q` onto the dicts it is
        # given, so passing one object to both runs let the second
        # overwrite the first and the comparison compared a number with
        # itself — which it duly reported as equal.
        return {"sport": "nfl", "market": "bad", "n": 200, "roi": -0.27,
                "hit": 0.38, "z": -4.19}
    few = shelfstop.decide(_fake(2, extra=[awful()]))
    many = shelfstop.decide(_fake(60, extra=[awful()]))
    q_few = next(s for s in few["shelves"] if s["market"] == "bad")["q"]
    q_many = next(s for s in many["shelves"] if s["market"] == "bad")["q"]
    assert q_many > q_few, (q_few, q_many)
    assert few["tested"] == 3 and many["tested"] == 61, (few["tested"],
                                                         many["tested"])


def test_a_thin_shelf_is_not_counted_as_a_test_either():
    """It was never judged, so it cannot dilute the ones that were."""
    got = shelfstop.decide(_fake(4) + [
        {"sport": "nfl", "market": "thin", "n": 5, "roi": -0.9,
         "hit": 0.1, "z": -3.0}])
    assert got["tested"] == 4, got["tested"]


# --- the block reaches every board --------------------------------------
def test_a_stopped_shelf_blocks_and_says_why():
    path = Path(tempfile.mkdtemp()) / "s.json"
    shelfstop.save({"stopped": [{"sport": "nfl", "market": "receptions",
                                 "n": 200, "roi": -0.274, "z": -4.19,
                                 "why": "x"}]}, path)
    why = shelfstop.blocked("nfl", "receptions", path)
    assert why and "stopped" in why, why
    assert "-27.4%" in why and "200" in why, why
    assert shelfstop.blocked("nfl", "rush_yds", path) is None
    assert shelfstop.blocked("mlb", "receptions", path) is None


def test_it_goes_through_the_one_door_every_board_already_consults():
    """FOUR ENGINES CALL `losspatterns.veto` TODAY and a fifth will be
    written. A rule added at four of five call sites is the shape
    `game_day` took when eight inserts of eleven forgot it.

    CALLED, NOT GREPPED. The first version of this asserted "shelfstop"
    appeared in the veto's source — and a mutation run replaced the
    whole call with `pass` and still passed, because the COMMENT above
    it says the word. The same trap caught two other tests today.
    """
    from engine import losspatterns
    path = Path(tempfile.mkdtemp()) / "s.json"
    shelfstop.save({"stopped": [{"sport": "nfl", "market": "receptions",
                                 "n": 200, "roi": -0.274, "z": -4.19,
                                 "why": "x"}]}, path)
    real = shelfstop.DEFAULT_PATH
    shelfstop.DEFAULT_PATH = path
    shelfstop._cache.clear()
    try:
        got = losspatterns.veto("nfl", "receptions")
        assert got and "shelf is stopped" in got, got
        assert losspatterns.veto("nfl", "rush_yds") is None
    finally:
        shelfstop.DEFAULT_PATH = real
        shelfstop._cache.clear()


def test_every_board_reaches_it_because_they_all_call_that_veto():
    import re
    hits = []
    for f in (ROOT / "engine").rglob("*.py"):
        if f.name in ("losspatterns.py", "shelfstop.py", "hypotheses.py"):
            continue
        txt = f.read_text(encoding="utf-8")
        if re.search(r"losspatterns import veto|lp_veto\(", txt):
            hits.append(f.name)
    assert len(hits) >= 4, hits
    for name in ("betting.py", "pipeline.py"):
        assert any(name in h for h in hits), hits


def test_an_unreadable_store_never_blocks_everything():
    """A breaker that cannot read must not cancel the night's card. The
    same call this file's veto makes on a read failure."""
    assert shelfstop.blocked("nfl", "receptions",
                             Path("/nonexistent/none.json")) is None
    bad = Path(tempfile.mkdtemp()) / "broken.json"
    bad.write_text("{not json", encoding="utf-8")
    assert shelfstop.blocked("nfl", "receptions", bad) is None


def test_the_veto_survives_a_breaker_that_raises():
    import engine.shelfstop as ss
    from engine import losspatterns
    real = ss.blocked

    def boom(*_a, **_k):
        raise RuntimeError("store is on fire")
    ss.blocked = boom
    try:
        losspatterns.veto("nfl", "receptions")     # must not raise
    finally:
        ss.blocked = real


# --- it is kept up to date ----------------------------------------------
def test_the_settle_pass_re_decides_it_beside_the_miner():
    import re
    src = (ROOT / "launch.py").read_text(encoding="utf-8")
    # COMMENTS OUT FIRST — the note beside this call names the module,
    # so a grep for the word passes with the call deleted.
    src = re.sub(r"(?m)^\s*#.*$", "", src)
    i = src.index("lp = losspatterns.refresh(lconn)")
    near = src[i:i + 1200]
    assert "_ss.refresh(lconn)" in near, "the breaker is never refreshed"
    assert "import shelfstop" in near


def test_a_refresh_writes_a_store_the_block_can_read():
    conn = _journal()
    _shelf(conn, "nfl", "receptions", 200, 0.38)
    path = Path(tempfile.mkdtemp()) / "s.json"
    shelfstop.refresh(conn, path)
    assert json.loads(path.read_text())["stopped"], path.read_text()[:300]
    assert shelfstop.blocked("nfl", "receptions", path)


def test_a_benched_league_is_not_judged_here_either():
    """Its rows are off the record; letting them close a shelf would let
    a league nobody is staking decide what everyone else may bet."""
    conn = _journal()
    # IN A HEADLINE CATEGORY, which is the only way this tests anything.
    # Seeded as `benched` the category filter alone would drop them and
    # the league filter could be deleted with every assertion passing —
    # a mutation run said exactly that. These are rows the sweep has not
    # reached yet, which is a state the migration's own try/except allows.
    _shelf(conn, "wnba", "receptions", 200, 0.38, category=ledger.BOOK[0])
    _shelf(conn, "nfl", "rush_yds", 200, 0.60)
    got = shelfstop.decide(shelfstop.measure(conn))
    seen = {(s["sport"], s["market"]) for s in got["shelves"]}
    assert seen == {("nfl", "rush_yds")}, seen
    assert got["stopped"] == []


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
