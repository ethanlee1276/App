"""The weather desk is paused, dated by its tickers, and has an audit.

Ethan, 2026-11-03, "1, yes": hide the weather picks. The desk's own graded
record said its claims were not its odds: NO calls claimed about 86% and
won about 52% over 3,173 settled paper bets, and the ones it claimed in the
60s won 2%. A number that confident and that wrong is worse than no number,
so while the cause is found:

1. THE PAUSE. `kalshiweather.PAUSED` holds the reason. The board still
   prices every bracket and still logs the forecast (kalshi_wx_log is what
   the audit reads), but no row is a recommendation, so nothing is
   journaled; pm_build publishes no weather rows and the page says why.
2. THE DATE. `_market_date` read `close_time[:10]`, which is UTC: an
   evening market that closes after midnight UTC read a day late and was
   priced against the next day's forecast. The ticker carries the day the
   contract is about (KXHIGHNY-26NOV03-...), which is what the journal
   already reads; the close time is now only the fallback.
3. THE AUDIT. `python3 -m engine.kalshiweather --audit` reads the log and
   the journal read-only and says which it was: the desk pricing the wrong
   day, or pricing the right day too sharply.

Run directly: `python3 tests/test_the_weather_desk_is_paused_and_audited.py`
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import kalshiweather as kw            # noqa: E402
from engine import ledger                          # noqa: E402
from _app import app_js  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def _mkt(**kw_):
    m = {"ticker": "KXHIGHNY-26NOV03-B60", "title": "Highest temperature in NYC",
         "subtitle": "60° to 61°", "prob": 0.20, "price_basis": "book",
         "spread_cents": 2.0, "volume_24h": 5000.0,
         "close_time": "2026-11-03T23:00:00Z"}
    m.update(kw_)
    return m


# --- 1. the pause -----------------------------------------------------------
def test_the_desk_ships_paused_with_a_reason_a_member_can_read():
    assert kw.PAUSED, "the desk was un-paused without the audit saying so"
    assert "paused" in kw.PAUSED.lower()


def test_a_paused_desk_still_prices_but_recommends_nothing():
    """The same market the gate test recommends at +17 points: priced, its
    numbers on the row, and not a recommendation while paused."""
    rows = kw.weather_board({"KXHIGHNY": [_mkt()]},
                            {("KXHIGHNY", "2026-11-03"): 61.0},
                            today="2026-11-03")
    assert len(rows) == 1
    r = rows[0]
    assert r["model_p"] > 0.3 and r["edge_pts"] > kw.WX_MIN_EDGE_PTS
    assert r["rec"] is False and r["rec_side"] is None


def test_a_paused_desk_journals_nothing_but_still_logs_the_forecast():
    rows = kw.weather_board({"KXHIGHNY": [_mkt()]},
                            {("KXHIGHNY", "2026-11-03"): 61.0},
                            today="2026-11-03")
    lconn = ledger.connect(":memory:")
    recs = [dict(r, sport="weather", desk="kalshi_wx") for r in rows if r.get("rec")]
    assert ledger.log_predmarket(lconn, recs, date="2026-11-03") == 0
    hconn = sqlite3.connect(":memory:")
    assert kw.log_forecasts(hconn, rows) == 1, "the audit needs the log"


def test_the_build_publishes_no_weather_rows_while_paused():
    pm = _src("pm_build.py")
    assert 'out["weather"] = [] if kw.PAUSED else weather_rows[:20]' in pm
    assert 'out["weather_paused"] = kw.PAUSED' in pm
    # The forecast is logged BEFORE the pause decides what is published.
    assert pm.index("kw.log_forecasts(conn, weather_rows)") \
        < pm.index('out["weather"] = [] if kw.PAUSED')


def test_the_page_and_the_desk_probe_say_it_is_paused():
    app = app_js()
    assert "const deskPaused = (_railDeskCache || {}).weather_paused;" in app
    assert "escapeHtml(deskPaused)" in app, "the reason is printed escaped"
    launch = _src("launch.py")
    assert 'k.get("weather_paused")' in launch
    # kalshi.json is paid whole, so its public path is a locked stub; the
    # owner's probe reads the full copy a member is served.
    assert "full = _gate._full_dir_for(p) / p.name" in launch
    from engine import gate
    assert "kalshi.json" in gate.PAID_FILES


# --- 2. the date --------------------------------------------------------------
def test_a_market_is_dated_by_its_ticker_not_its_utc_close():
    """An evening market on the 3rd that closes at 04:59 UTC on the 4th."""
    late = _mkt(close_time="2026-11-04T04:59:00Z")
    assert kw._market_date(late) == "2026-11-03"
    rows = kw.weather_board({"KXHIGHNY": [late]},
                            {("KXHIGHNY", "2026-11-03"): 61.0,
                             ("KXHIGHNY", "2026-11-04"): 48.0},
                            today="2026-11-03")
    assert [r["date"] for r in rows] == ["2026-11-03"]
    assert rows[0]["forecast_f"] == 61.0, "priced against the next day's high"
    assert rows[0]["lead_days"] == 0


def test_a_ticker_with_no_date_falls_back_to_the_close():
    assert kw._market_date(_mkt(ticker="KXHIGHNY-B60",
                                close_time="2026-11-05T23:00:00Z")) == "2026-11-05"
    assert kw._market_date(_mkt(ticker="KXHIGHNY-B60", close_time="")) is None
    assert kw._market_date(_mkt(ticker="", close_time="2026")) is None


# --- 3. the audit -------------------------------------------------------------
def _fixture():
    """Three settled paper bets and two logged forecasts:
    A: priced a day late (logged for the 4th, ticker about the 3rd), a NO
       claimed at 90% made on the 3rd, lost.
    B: priced on the right day, a YES claimed at 70% made the day before, won.
    C: a bet whose forecast was never logged (the log began later), won.
    """
    a, b, c = "KXHIGHNY-26NOV03-B60", "KXHIGHNY-26NOV03-B62", "KXHIGHCHI-26OCT20-B55"
    hconn = sqlite3.connect(":memory:")
    base = {"series": "KXHIGHNY", "forecast_f": 61.0, "sigma_f": 2.0,
            "lead_days": 0, "model_p": 0.1, "prob": 0.5}
    kw.log_forecasts(hconn, [dict(base, date="2026-11-04", ticker=a),
                             dict(base, date="2026-11-03", ticker=b)])
    lconn = ledger.connect(":memory:")
    rec = {"rec": True, "sport": "weather", "desk": "kalshi_wx", "prob": 0.5,
           "title": "NYC high"}
    ledger.log_predmarket(lconn, [dict(rec, ticker=a, rec_side="NO", model_p=0.10)],
                          date="2026-11-03")
    ledger.log_predmarket(lconn, [dict(rec, ticker=b, rec_side="YES", model_p=0.70)],
                          date="2026-11-02")
    ledger.log_predmarket(lconn, [dict(rec, ticker=c, rec_side="YES", model_p=0.60)],
                          date="2026-10-20")
    ledger.resolve_predmarket(lconn, {a: "yes", b: "yes", c: "yes"})
    return hconn, lconn


def test_the_audit_sorts_the_log_by_which_day_the_desk_priced():
    hconn, lconn = _fixture()
    rep = kw.audit(hconn, lconn)
    assert rep["logged"] == {"desk a day late": 1, "same day": 1}
    assert rep["samples"] == [{"ticker": "KXHIGHNY-26NOV03-B60",
                               "priced": "2026-11-04", "about": "2026-11-03"}]


def test_the_audit_grades_the_bets_against_what_they_claimed():
    hconn, lconn = _fixture()
    rep = kw.audit(hconn, lconn)
    late = rep["bets"]["desk a day late"]
    assert (late["n"], late["won"], late["lost"]) == (1, 0, 1)
    assert late["claimed_pct"] == 0.9, "a NO at model 10% claims 90%"
    same = rep["bets"]["same day"]
    assert (same["n"], same["won"], same["claimed_pct"]) == (1, 1, 0.7)
    assert rep["bets"]["no forecast logged"]["n"] == 1
    # Days ahead of the high: A and C on the day, B the day before.
    assert rep["by_lead"]["0"]["n"] == 2 and rep["by_lead"]["1"]["n"] == 1


def test_the_audit_writes_nothing():
    hconn, lconn = _fixture()
    before = (hconn.total_changes, lconn.total_changes)
    kw.audit(hconn, lconn)
    assert (hconn.total_changes, lconn.total_changes) == before
    src = _src("engine", "kalshiweather.py")
    assert src.count("?mode=ro\", uri=True)") == 2, "the CLI opens both files read-only"


def test_the_audit_reads_an_empty_box_without_crashing():
    """No log table (a box that never built the desk) and no weather bets."""
    rep = kw.audit(sqlite3.connect(":memory:"), ledger.connect(":memory:"))
    assert rep == {"logged": {}, "samples": [], "bets": {}, "by_lead": {},
                   "shadow": {"graded": {"n": 0}, "by_lead": {}, "waiting": 0}}
    lines = kw._audit_lines(rep)
    assert lines[0].startswith("weather desk audit — 0 forecasts logged")
    assert lines.count("    none") == 2


def test_the_audit_lines_read_as_sentences():
    hconn, lconn = _fixture()
    text = "\n".join(kw._audit_lines(kw.audit(hconn, lconn)))
    assert "2 forecasts logged" in text
    assert "desk a day late" in text and "0-1  won 0%, claimed 90%" in text
    assert "e.g. KXHIGHNY-26NOV03-B60: priced for 2026-11-04, the ticker is about 2026-11-03" in text



# --- 4. the shadow record: the un-pause's own measure ---------------------------
def _board():
    return kw.weather_board({"KXHIGHNY": [_mkt()]},
                            {("KXHIGHNY", "2026-11-03"): 61.0},
                            today="2026-11-03")


def test_the_paused_desk_keeps_what_it_would_have_picked():
    rows = _board()
    assert rows[0]["would_rec"] is True and rows[0]["would_side"] == "YES"
    hconn = sqlite3.connect(":memory:")
    assert kw.log_shadow(hconn, rows, made="2026-11-03") == 1
    assert kw.log_shadow(hconn, rows, made="2026-11-03") == 0, "first time only"
    t, side, claimed, price, lead = hconn.execute(
        "SELECT ticker, side, claimed, price, lead_days FROM kalshi_wx_shadow").fetchone()
    assert (t, side, lead) == ("KXHIGHNY-26NOV03-B60", "YES", 0)
    assert claimed == round(rows[0]["model_p"], 4) and price == 0.2


def test_a_no_shadow_pick_keeps_the_sides_own_numbers():
    rows = [dict(_board()[0], would_side="NO", model_p=0.25, prob=0.60)]
    hconn = sqlite3.connect(":memory:")
    kw.log_shadow(hconn, rows, made="2026-11-03")
    assert hconn.execute("SELECT claimed, price FROM kalshi_wx_shadow").fetchone() == (0.75, 0.4)


def test_a_row_that_misses_the_gate_is_not_a_shadow_pick():
    rows = [dict(_board()[0], would_rec=False, would_side=None)]
    hconn = sqlite3.connect(":memory:")
    assert kw.log_shadow(hconn, rows) == 0


def test_shadow_picks_are_asked_about_after_their_day_for_two_weeks():
    hconn = sqlite3.connect(":memory:")
    kw.log_shadow(hconn, _board(), made="2026-11-03")
    assert kw.shadow_open(hconn, today="2026-11-03") == [], "not before its day ends"
    assert kw.shadow_open(hconn, today="2026-11-04") == ["KXHIGHNY-26NOV03-B60"]
    assert kw.shadow_open(hconn, today="2026-11-20") == [], "given up after 14 days"
    assert kw.shadow_open(sqlite3.connect(":memory:")) == [], "no table, no crash"


def test_shadow_picks_are_graded_and_reported_by_the_audit():
    hconn = sqlite3.connect(":memory:")
    kw.log_shadow(hconn, _board(), made="2026-11-03")
    assert kw.settle_shadow(hconn, {"KXHIGHNY-26NOV03-B60": "no", "OTHER": "yes"}) == 1
    assert kw.settle_shadow(hconn, {"KXHIGHNY-26NOV03-B60": "yes"}) == 0, "graded once"
    assert kw.shadow_open(hconn, today="2026-11-04") == []
    sh = kw.audit(hconn, ledger.connect(":memory:"))["shadow"]
    assert (sh["graded"]["n"], sh["graded"]["won"], sh["waiting"]) == (1, 0, 0)
    assert sh["by_lead"]["0"]["lost"] == 1
    text = "\n".join(kw._audit_lines(kw.audit(hconn, ledger.connect(":memory:"))))
    assert "while paused, the picks it would have made (graded; 0 waiting on a result):" in text


def test_the_build_logs_and_grades_the_shadow_on_the_journals_own_pull():
    pm = _src("pm_build.py")
    assert "kw.log_shadow(conn, weather_rows, made=today)" in pm
    # One settlement pull for both (the fetch caches by batch number).
    assert "kx.fetch_markets_by_tickers(open_tk + shadow_tk)" in pm
    assert pm.count("fetch_markets_by_tickers(") == 1
    assert "kw.settle_shadow(conn, results)" in pm


def test_the_shadow_never_reaches_the_ledger_or_a_member():
    import inspect
    for fn in (kw.log_shadow, kw.shadow_open, kw.settle_shadow):
        assert "ledger" not in inspect.getsource(fn).split('"""')[-1], fn.__name__
    assert "kalshi_wx_shadow" not in _src("engine", "ledger.py")
    assert "would_rec" not in app_js(), "the page never reads the shadow gate"

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
