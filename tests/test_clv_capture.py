"""Closing-line value, made honest before anything is built on it.

CLV grades the DECISION the moment a game starts — it needs no result,
which makes it the fastest-accruing evidence the journal has, and the
natural input to a future sizing rung. All of that rests on the closes
being real, and two ways they weren't:

* **In-play prices masquerading as closes.** The odds adapter's own
  docstring says it plainly: *"during a live game the event-odds
  endpoint returns current (in-play) prices, so the same call yields
  live lines."* On a staggered slate a late pull re-prices the games
  already running, and the close-picker took each day's LAST snapshot —
  so a line quoted while a player already had two hits became his
  "closing line". The sibling function ``closing_lines`` had a
  ``before_ts`` guard documented for exactly this hazard; the function
  production actually calls had none.
* **Cross-date contamination.** ``settle()`` keyed closes on
  ``(player, market)`` alone. In a sport that plays every night that
  resolves to the last price ever seen for that prop — a July bet
  taking August's line as its close.

Snapshots now carry their game's start time, both close-pickers cut at
it, and history recorded before the stamp existed keeps reading exactly
as it did rather than being retroactively reinterpreted.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import ledger, linemoves as lm

T0 = 1_800_000_000.0            # a fixed instant; all offsets are from here
HOUR = 3600.0


class _Line:
    def __init__(self, book, line, over=-110):
        self.book, self.line, self.over_odds = book, line, over


class _Prop:
    def __init__(self, player, market, lines):
        self.player, self.market, self.lines = player, market, lines


class _Slate:
    """Minimum shape record_snapshots needs: props and their games."""

    def __init__(self, props, kickoff):
        self.props, self._kick = props, kickoff

    def game_for(self, prop):
        return type("G", (), {"kickoff": self._kick})()


def _rows(path):
    return [json.loads(l) for l in open(path).read().splitlines() if l.strip()]


# --- the start stamp ---------------------------------------------------------
def test_a_real_timestamp_becomes_an_instant_and_a_bare_clock_does_not():
    """Same rule as capture_lag's minutes_until: a clock with no date is
    not an instant, and guessing a timezone onto one would silently
    decide which snapshots count as pre-game."""
    assert lm.start_epoch("2026-06-20T18:20:00Z") == 1781979600.0
    assert lm.start_epoch("2026-06-20T18:20:00+00:00") == 1781979600.0
    assert lm.start_epoch("13:00") is None          # the NFL board's shape
    assert lm.start_epoch("2026-06-20T18:20:00") is None    # naive = a clock
    assert lm.start_epoch("") is None and lm.start_epoch(None) is None


def test_snapshots_carry_their_games_start_when_it_is_knowable():
    p = os.path.join(tempfile.mkdtemp(), "h.jsonl")
    props = [_Prop("A Batter", "hits", [_Line("dk", 1.5)])]
    lm.record_snapshots(props, ts=T0, path=p,
                        slate=_Slate(props, "2026-06-20T18:20:00Z"))
    assert _rows(p)[0]["start_ts"] == 1781979600.0
    # A bare clock stamps nothing rather than a guess — and the snapshot
    # is still recorded, because a missing cut is not a missing price.
    p2 = os.path.join(tempfile.mkdtemp(), "h.jsonl")
    lm.record_snapshots(props, ts=T0, path=p2, slate=_Slate(props, "13:00"))
    assert "start_ts" not in _rows(p2)[0]
    assert _rows(p2)[0]["line"] == 1.5


def test_a_slate_that_cannot_locate_its_game_still_records_the_price():
    class _Broken(_Slate):
        def game_for(self, prop):
            raise KeyError("no game for this prop")

    p = os.path.join(tempfile.mkdtemp(), "h.jsonl")
    props = [_Prop("A Batter", "hits", [_Line("dk", 1.5)])]
    assert lm.record_snapshots(props, ts=T0, path=p,
                               slate=_Broken(props, "x")) == 1


# --- the pre-game cut --------------------------------------------------------
def _snap(ts, line, start=None, player="A Batter", market="hits"):
    r = {"ts": ts, "player": player, "market": market, "book": "dk",
         "line": line, "over_odds": -110}
    if start is not None:
        r["start_ts"] = start
    return r


def test_an_in_play_reprice_is_not_a_closing_line():
    start = T0 + 2 * HOUR
    rows = [_snap(T0, 1.5, start),                  # morning
            _snap(start - 600, 2.5, start),         # ten minutes out = close
            _snap(start + HOUR, 0.5, start)]        # in play, 2 hits already
    closes = lm.closing_lines_by_date(rows)
    assert list(closes.values()) == [2.5]
    assert list(lm.closing_lines(rows).values()) == [2.5]


def test_legacy_history_is_never_retroactively_reinterpreted():
    """Rows recorded before the stamp existed carry no start, so they read
    exactly as they always have — a fix must not rewrite the past."""
    rows = [_snap(T0, 1.5), _snap(T0 + 3 * HOUR, 2.5)]
    assert list(lm.closing_lines_by_date(rows).values()) == [2.5]


def test_one_stamped_row_supplies_the_start_for_its_whole_game():
    """A slate part-recorded before the stamp and part after is ONE game
    with one start — the known start governs all of its snapshots."""
    start = T0 + 2 * HOUR
    rows = [_snap(T0, 1.5),                          # legacy, pre-game
            _snap(start + HOUR, 0.5, start)]         # stamped, in play
    assert list(lm.closing_lines_by_date(rows).values()) == [1.5]


def test_a_prop_seen_only_in_play_reports_no_close_at_all():
    """Inventing a close from a live number is the bug; silence is the fix."""
    start = T0
    assert lm.closing_lines_by_date([_snap(start + HOUR, 0.5, start)]) == {}
    assert lm.closing_lines([_snap(start + HOUR, 0.5, start)]) == {}


def test_several_books_at_the_close_still_median():
    start = T0 + HOUR
    rows = [_snap(start - 60, 1.5, start), _snap(start - 60, 2.5, start),
            _snap(start - 60, 3.5, start), _snap(start + 60, 9.5, start)]
    assert list(lm.closing_lines_by_date(rows).values()) == [2.5]


# --- the journal side --------------------------------------------------------
def _journal():
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    conn.execute(
        "INSERT INTO bets (sport,date,player,market,side,line,odds,grade,"
        "stake_units,stake_dollars,status,category) VALUES "
        "('mlb','2026-07-01','A Batter','hits','OVER',1.5,-110,'A',"
        "1.0,10.0,'open','main')")
    conn.commit()
    return conn


def test_settle_takes_the_close_from_the_bets_own_night():
    """The undated map keys on (player, market) alone, so in a sport that
    plays nightly a July bet could close on August's line."""
    conn = _journal()
    hist = os.path.join(tempfile.mkdtemp(), "h.jsonl")
    with open(hist, "w") as fh:
        for ts, line, date in ((T0, 2.5, "jul"), (T0 + 30 * 24 * HOUR, 9.5, "aug")):
            fh.write(json.dumps(_snap(ts, line)) + "\n")
    import datetime as _dt
    jul = _dt.datetime.fromtimestamp(T0).strftime("%Y-%m-%d")
    conn.execute("UPDATE bets SET date=?", (jul,))
    conn.commit()

    orig = lm.HISTORY_PATH
    try:
        lm.HISTORY_PATH = __import__("pathlib").Path(hist)
        ledger.settle(conn, {("A Batter", "hits"): 2.0})
    finally:
        lm.HISTORY_PATH = orig
    row = conn.execute("SELECT closing_line FROM bets").fetchone()
    assert row[0] == 2.5, "a later night's price became this bet's close"


def test_an_explicit_closing_map_still_wins():
    conn = _journal()
    ledger.settle(conn, {("A Batter", "hits"): 2.0},
                  closing={("A Batter", "hits"): 1.0})
    assert conn.execute("SELECT closing_line FROM bets").fetchone()[0] == 1.0


# --- coverage, reported honestly ---------------------------------------------
def _settled(conn, sport, n, with_close, close=2.5,
             date=None):
    # Dated ON ledger.RECORD_EPOCH by default. The EXPORT's coverage block
    # is windowed with the record it sits beside — it prints "N of M
    # settled picks have a close", and an M that disagreed with the
    # settled count above it would read as one of the two being wrong.
    # Pinned to the constant so it cannot drift when the epoch moves.
    date = date or ledger.RECORD_EPOCH
    for i in range(n):
        conn.execute(
            "INSERT INTO bets (sport,date,player,market,side,line,odds,grade,"
            "stake_units,stake_dollars,status,category,closing_line,pnl_units)"
            " VALUES (?,?,?,'hits','OVER',1.5,-110,'A',1.0,10.0,'won','main',"
            "?,1.0)",
            (sport, date, f"P{i}", close if i < with_close else None))
    conn.commit()


def test_coverage_reports_what_is_measurable_and_what_is_not():
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    _settled(conn, "mlb", 50, 50)       # plenty, and every close beats us
    _settled(conn, "nba", 10, 2)        # thin
    cov = ledger.clv_coverage(conn)
    assert cov["by_sport"]["mlb"]["with_close"] == 50
    assert cov["by_sport"]["mlb"]["ready"] is True
    assert cov["by_sport"]["mlb"]["avg_clv"] == 1.0        # 2.5 close vs 1.5
    assert cov["by_sport"]["mlb"]["beat_close"] == 1.0
    assert cov["by_sport"]["nba"]["ready"] is False
    assert cov["by_sport"]["nba"]["coverage"] == 0.2
    assert cov["ready_sports"] == ["mlb"]
    assert cov["min_n"] == ledger.CLV_MIN_N


def test_the_export_ships_coverage_so_the_page_can_be_honest():
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    _settled(conn, "mlb", 3, 1)
    out = os.path.join(tempfile.mkdtemp(), "record.json")
    ledger.export_json(conn, out)
    cov = json.load(open(out))["clv_coverage"]
    assert cov["settled"] == 3 and cov["with_close"] == 1


def test_the_doctor_watches_the_capture():
    import doctor
    assert doctor.check_clv_capture in doctor.CHECKS
    assert doctor.check_clv_capture in doctor.DATA_CHECKS


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
