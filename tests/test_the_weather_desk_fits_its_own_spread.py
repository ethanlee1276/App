"""The weather desk fits its spread from its own record (engine/kalshiwxfit).

The desk prices a daily-high bracket as the chance that Normal(NWS high,
sigma) lands in it, with sigmas of 2.0 / 3.0 / 3.8 °F by lead: priors, and
its docstring promised they would be fit from the logged pairs. The settle
half was never filled, so nothing was fitted; the desk was paused on 3
November, its calls claiming far more than they won. What these hold:

  * every logged forecast is a forecast of its own `date`, the day-late
    rows included, so the fit pairs by (series, date), never by ticker, and
    takes one forecast per city, day and lead;
  * the day's winning bracket is the market that settled YES, read the way
    the desk reads a label; a day with no readable YES, or two, is left out;
  * the fit is maximum likelihood on the interval the winner gives: it
    finds a known spread and bias in made-up days, and a lead with too few
    days keeps its prior;
  * it is saved only when it beats the priors on the newest third of the
    days at the bottom of a 95% interval; a refit that no longer passes
    takes it away; the refit runs once a day and never raises;
  * the board prices with the saved fit (bias added, the lead's sigma) and
    keeps the raw NWS forecast on its row, so the log never holds a
    corrected number; without a fit, nothing changes;
  * the desk stays paused; the build refits before pricing; the audit says
    the fit's verdict; the box command saves nothing.

Run directly: `python3 tests/test_the_weather_desk_fits_its_own_spread.py`
"""
import json
import math
import os
import random
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import kalshiweather as kw                          # noqa: E402
from engine import kalshiwxfit as F                             # noqa: E402


def _days(n=300, sigma=None, bias=1.5, seed=11, start="2026-08-01"):
    """Made-up (date, lead, mu, lo, hi) days: the real high is drawn around
    the forecast plus ``bias`` with each lead's ``sigma``, and the winner is
    the two-degree bracket of a ladder with edges at x.5 holding it."""
    import datetime as dt
    sigma = sigma or {0: 2.6, 1: 3.4, 2: 4.2}
    rnd = random.Random(seed)
    d0 = dt.date.fromisoformat(start)
    rows = []
    for i in range(n):
        day = (d0 + dt.timedelta(days=i // 3)).isoformat()
        lead = rnd.choice([0, 1, 1, 2])
        mu = round(rnd.gauss(68, 12))
        actual = round(rnd.gauss(mu + bias, sigma[lead]))
        a = 1.5 + 2 * math.floor((actual - 1.5) / 2)
        rows.append((day, lead, float(mu), a, a + 2.0))
    return rows


def _log_db(rows):
    """A history db with kalshi_wx_log rows: (date, ticker, series, f, lead)."""
    conn = sqlite3.connect(":memory:")
    kw.log_forecasts(conn, [{"date": d, "ticker": t, "series": s, "forecast_f": f,
                             "sigma_f": 2.0, "lead_days": l, "model_p": 0.3, "prob": 0.3}
                            for (d, t, s, f, l) in rows])
    return conn


# --- the data -----------------------------------------------------------------
def test_every_logged_forecast_counts_once_per_city_day_and_lead():
    conn = _log_db([
        # Three brackets of one day: one forecast, logged three times.
        ("2026-11-05", "KXHIGHNY-26NOV05-B60.5", "KXHIGHNY", 61.0, 1),
        ("2026-11-05", "KXHIGHNY-26NOV05-B62.5", "KXHIGHNY", 61.0, 1),
        ("2026-11-05", "KXHIGHNY-26NOV05-T64", "KXHIGHNY", 61.0, 1),
        # A day-late row from before WX2: the ticker is the 4th's, the
        # forecast the 5th's at lead 0. It counts, for the 5th.
        ("2026-11-05", "KXHIGHNY-26NOV04-B58.5", "KXHIGHNY", 63.0, 0),
        ("2026-11-05", "KXHIGHCHI-26NOV05-B50.5", "KXHIGHCHI", 49.0, 1),
        ("2026-11-05", "KXNOTACITY-26NOV05-B1", "KXNOTACITY", 1.0, 1),
    ])
    got = F.logged_forecasts(conn)
    assert got == [("KXHIGHCHI", "2026-11-05", 1, 49.0),
                   ("KXHIGHNY", "2026-11-05", 0, 63.0),
                   ("KXHIGHNY", "2026-11-05", 1, 61.0)], got


def test_a_days_winner_is_the_bracket_that_settled_yes():
    markets = [
        {"ticker": "KXHIGHNY-26NOV05-B60.5", "result": "no", "yes_sub_title": "60° to 61°"},
        {"ticker": "KXHIGHNY-26NOV05-B62.5", "result": "yes", "yes_sub_title": "62° to 63°"},
        {"ticker": "KXHIGHNY-26NOV06-T70", "result": "yes", "subtitle": "70° or above"},
        # Two YES on one day: something is wrong with the day; left out.
        {"ticker": "KXHIGHNY-26NOV07-B50.5", "result": "yes", "yes_sub_title": "50° to 51°"},
        {"ticker": "KXHIGHNY-26NOV07-B52.5", "result": "yes", "yes_sub_title": "52° to 53°"},
        # An unreadable label: left out.
        {"ticker": "KXHIGHNY-26NOV08-B1", "result": "yes", "yes_sub_title": "who knows"},
    ]
    assert F.winning_brackets(markets) == {"2026-11-05": (61.5, 63.5),
                                           "2026-11-06": (69.5, None)}


def test_the_forecast_is_paired_with_the_winner_of_its_own_day():
    fc = [("KXHIGHNY", "2026-11-05", 1, 61.0), ("KXHIGHNY", "2026-11-06", 0, 71.0),
          ("KXHIGHCHI", "2026-11-05", 1, 49.0)]
    br = {"KXHIGHNY": {"2026-11-05": (61.5, 63.5), "2026-11-06": (69.5, None)}}
    assert F.pairs(fc, br) == [("2026-11-05", 1, 61.0, 61.5, 63.5),
                               ("2026-11-06", 0, 71.0, 69.5, None)]


def test_the_settled_markets_are_read_page_by_page_from_the_logs_first_day():
    seen = []

    def fetch_text(url, name, ttl=0):
        seen.append(url)
        if "cursor=" not in url:
            return json.dumps({"markets": [{"ticker": "a"}], "cursor": "p2"})
        return json.dumps({"markets": [{"ticker": "b"}], "cursor": ""})
    got = F.fetch_settled("KXHIGHNY", "2026-08-01", fetch_text=fetch_text)
    assert [m["ticker"] for m in got] == ["a", "b"]
    assert "series_ticker=KXHIGHNY" in seen[0] and "status=settled" in seen[0]
    assert "min_close_ts=1785542400" in seen[0], seen[0]      # 2026-08-01 UTC
    assert seen[1].endswith("&cursor=p2")


# --- the fit ------------------------------------------------------------------
def test_the_fit_finds_a_known_spread_and_bias():
    rows = _days(n=1800, sigma={0: 2.6, 1: 3.4, 2: 4.2}, bias=1.5, seed=3)
    f = F.fit(rows)
    assert abs(f["bias_f"] - 1.5) <= 0.3, f
    for lead, want in (("0", 2.6), ("1", 3.4), ("2", 4.2)):
        assert abs(f["sigma_by_lead"][lead] - want) <= 0.35, (lead, f)
    assert f["fitted_leads"] == ["0", "1", "2"]


def test_a_lead_with_too_few_days_keeps_its_prior():
    rows = [r for r in _days(n=600, seed=5) if r[1] != 2] + \
        [r for r in _days(n=600, seed=6) if r[1] == 2][:F.MIN_PER_LEAD - 1]
    f = F.fit(rows)
    assert "2" not in f["fitted_leads"]
    assert f["sigma_by_lead"]["2"] == kw.SIGMA_BY_LEAD[2]


def test_it_is_saved_only_when_it_beats_the_priors_held_out():
    # Wider than the priors and shifted: the fit wins on the newest third.
    win = F.evaluate(_days(n=900, sigma={0: 3.2, 1: 4.0, 2: 4.8}, bias=2.0, seed=8))
    assert win["verdict"] == "saved", win.get("held_out")
    assert win["held_out"]["logloss_fit"] < win["held_out"]["logloss_prior"]
    assert win["fit"]["bias_f"] > 1.0
    # Drawn from the priors themselves: nothing to gain, nothing saved.
    same = F.evaluate(_days(n=900, sigma=dict(kw.SIGMA_BY_LEAD), bias=0.0, seed=9))
    assert same["verdict"] == "no better than the priors held out", same.get("held_out")
    assert "fit" not in same
    # Too few days to say.
    few = F.evaluate(_days(n=F.MIN_EVENTS - 1, seed=10))
    assert few["verdict"] == "not enough days"


def test_the_held_out_days_are_the_newest():
    rep = F.evaluate(_days(n=900, sigma={0: 3.2, 1: 4.0, 2: 4.8}, bias=2.0, seed=8))
    days = sorted({r[0] for r in _days(n=900, seed=8)})
    assert rep["held_out"]["from"] == days[int(len(days) * F.TRAIN_SHARE)]


def test_the_central_bracket_check_says_what_each_model_claimed():
    rows = _days(n=900, sigma={0: 3.2, 1: 4.0, 2: 4.8}, bias=0.0, seed=12)
    c = F.calibration(rows, None)
    # Two-degree brackets at the priors' sigmas claim more for the
    # forecast's own bracket than these wider days deliver.
    assert c["prior_said"] > c["won_pct"], c
    wide = F.calibration(rows, {"bias_f": 0.0, "sigma_by_lead": {"0": "3.2", "1": "4.0", "2": "4.8"}})
    off_fit = abs(wide["fit_said"] - wide["won_pct"])
    off_prior = abs(c["prior_said"] - c["won_pct"])
    assert off_fit + 0.03 < off_prior, (off_fit, off_prior, wide, c)


# --- the daily refit ------------------------------------------------------------
def _box(tmp, n=900, sigma=None, bias=2.0, seed=8):
    """A log and a settled-markets feed made from the same made-up days."""
    rows = _days(n=n, sigma=sigma or {0: 3.2, 1: 4.0, 2: 4.8}, bias=bias, seed=seed)
    import datetime as dt
    logged, markets = [], {}
    seen = set()
    for i, (day, lead, mu, lo, hi) in enumerate(rows):
        series = sorted(kw.CITIES)[i % len(kw.CITIES)]
        d = dt.date.fromisoformat(day)
        tick = f"{series}-{d:%y}{d:%b}{d:%d}".upper()
        if (series, day) in seen:
            continue
        seen.add((series, day))
        logged.append((day, f"{tick}-B{lo + 0.5}", series, mu, lead))
        markets.setdefault(series, []).append(
            {"ticker": f"{tick}-B{lo + 0.5}", "result": "yes",
             "yes_sub_title": f"{int(lo + 0.5)}° to {int(hi - 0.5)}°"})
    conn = _log_db(logged)

    def fetch_text(url, name, ttl=0):
        series = url.split("series_ticker=")[1].split("&")[0]
        return json.dumps({"markets": markets.get(series, []), "cursor": ""})
    return conn, fetch_text


def test_the_refit_runs_once_a_day_keeps_its_verdict_and_hands_back_the_fit():
    tmp = Path(tempfile.mkdtemp())
    path = tmp / "kalshiwx_fit.json"
    conn, fetch_text = _box(tmp)
    calls = []

    def counting(url, name, ttl=0):
        calls.append(url)
        return fetch_text(url, name, ttl)
    got = F.refit_if_due(conn, path=path, today="2026-11-08", fetch_text=counting, log=lambda *_: None)
    assert got and got["bias_f"] > 1.0, got
    doc = json.loads(path.read_text())
    assert doc["verdict"] == "saved" and doc["checked"] == "2026-11-08"
    assert doc["first_saved"] == "2026-11-08"
    n = len(calls)
    again = F.refit_if_due(conn, path=path, today="2026-11-08", fetch_text=counting, log=lambda *_: None)
    assert again == got and len(calls) == n, "a second build the same day refits nothing"
    assert F.load(path) == got
    # The next day it refits, and keeps the day it was first saved.
    F.refit_if_due(conn, path=path, today="2026-11-09", fetch_text=counting, log=lambda *_: None)
    doc = json.loads(path.read_text())
    assert doc["checked"] == "2026-11-09" and doc["first_saved"] == "2026-11-08"


def test_a_refit_that_no_longer_passes_takes_the_fit_away():
    tmp = Path(tempfile.mkdtemp())
    path = tmp / "kalshiwx_fit.json"
    path.write_text(json.dumps({"verdict": "saved", "checked": "2026-11-07",
                                "first_saved": "2026-11-01",
                                "fit": {"bias_f": 2.0, "sigma_by_lead": {"0": 3.0}}}))
    conn, fetch_text = _box(tmp, sigma=dict(kw.SIGMA_BY_LEAD), bias=0.0, seed=9)
    got = F.refit_if_due(conn, path=path, today="2026-11-08", fetch_text=fetch_text, log=lambda *_: None)
    assert got is None and F.load(path) is None
    doc = json.loads(path.read_text())
    assert doc["verdict"] == "no better than the priors held out" and "first_saved" not in doc


def test_the_switch_turns_the_refit_off_and_the_desk_back_to_its_priors():
    tmp = Path(tempfile.mkdtemp())
    path = tmp / "kalshiwx_fit.json"
    conn, fetch_text = _box(tmp)
    os.environ["QB_WX_FIT"] = "0"
    try:
        got = F.refit_if_due(conn, path=path, today="2026-11-08", fetch_text=fetch_text,
                             log=lambda *_: None)
    finally:
        del os.environ["QB_WX_FIT"]
    assert got is None and not path.exists()


def test_a_refit_never_raises_and_a_failed_one_keeps_yesterdays():
    tmp = Path(tempfile.mkdtemp())
    path = tmp / "kalshiwx_fit.json"
    path.write_text(json.dumps({"verdict": "saved", "checked": "2026-11-07",
                                "fit": {"bias_f": 1.0, "sigma_by_lead": {"1": 3.5}}}))

    class _Broken:
        def execute(self, *a, **k):
            raise RuntimeError("disk on fire")
    got = F.refit_if_due(_Broken(), path=path, today="2026-11-08", log=lambda *_: None)
    assert got == {"bias_f": 1.0, "sigma_by_lead": {"1": 3.5}}


# --- the board, the build, the audit ---------------------------------------------
def _mkt(**kw_):
    m = {"ticker": "KXHIGHNY-26NOV08-B60.5", "title": "Highest temperature in NYC",
         "subtitle": "60° to 61°", "prob": 0.20, "price_basis": "book",
         "spread_cents": 2.0, "volume_24h": 5000.0, "close_time": "2026-11-08T23:00:00Z"}
    m.update(kw_)
    return m


def test_the_board_prices_with_the_fit_and_logs_the_raw_forecast():
    markets = {"KXHIGHNY": [_mkt()]}
    highs = {("KXHIGHNY", "2026-11-08"): 60.0}
    plain = kw.weather_board(markets, highs, today="2026-11-08")[0]
    assert plain["sigma_f"] == kw.SIGMA_BY_LEAD[0] and plain["bias_f"] == 0.0
    fit = {"bias_f": 2.0, "sigma_by_lead": {"0": 3.1}}
    row = kw.weather_board(markets, highs, today="2026-11-08", fit=fit)[0]
    assert row["sigma_f"] == 3.1 and row["bias_f"] == 2.0
    assert row["forecast_f"] == 60.0, "the log keeps the raw NWS number"
    assert abs(row["model_p"] - round(kw.bracket_prob(59.5, 61.5, 62.0, 3.1), 4)) < 1e-9
    assert row["model_p"] < plain["model_p"]
    assert row["rec"] is False, "the desk stays paused"


def test_the_build_refits_before_it_prices():
    src = (ROOT / "pm_build.py").read_text(encoding="utf-8")
    i = src.index("kalshiwxfit.refit_if_due(conn, today=today)")
    assert i < src.index("kw.weather_board(by_series, highs, today=today, fit=fit)")
    assert kw.PAUSED, "un-pausing is Ethan's call, after the shadow record holds"


def test_the_audit_says_the_fits_verdict_and_grades_the_picks_since():
    tmp = Path(tempfile.mkdtemp())
    path = tmp / "kalshiwx_fit.json"
    path.write_text(json.dumps({"verdict": "saved", "checked": "2026-11-09",
                                "first_saved": "2026-11-08", "events": 500,
                                "fit": {"bias_f": 1.4, "sigma_by_lead": {"0": 2.9, "1": 3.6},
                                        "n_by_lead": {"0": 200, "1": 300}, "fitted_leads": ["0", "1"]}}))
    h = sqlite3.connect(":memory:")
    kw._shadow_table(h)
    h.executemany("INSERT INTO kalshi_wx_shadow VALUES (?,?,?,?,?,?,?,?)", [
        ("A", "2026-11-06", "2026-11-05", "NO", 0.9, 0.7, 1, "no"),
        ("B", "2026-11-09", "2026-11-08", "NO", 0.8, 0.7, 1, "yes"),
        ("C", "2026-11-10", "2026-11-09", "YES", 0.4, 0.2, 1, None)])
    lg = sqlite3.connect(":memory:")
    lg.execute("CREATE TABLE bets (player TEXT, status TEXT, hit_prob REAL, date TEXT, "
               "sport TEXT, category TEXT)")
    rep = kw.audit(h, lg, fit_path=path)
    assert rep["fit"]["first_saved"] == "2026-11-08"
    assert rep["shadow"]["graded"]["n"] == 2
    assert rep["shadow_fitted"]["graded"] == {"n": 1, "won": 0, "lost": 1, "won_pct": 0.0,
                                              "claimed_pct": 0.8}
    assert rep["shadow_fitted"]["waiting"] == 1
    text = "\n".join(kw._audit_lines(rep))
    assert "the spread fit" in text and "bias +1.4°F" in text
    assert "since the fit first priced them (2026-11-08" in text


def test_the_box_command_saves_nothing():
    import inspect
    src = inspect.getsource(F.main)
    assert "mode=ro" in src and "refit_if_due" not in src and ".write_text" not in src
    assert "python3 -m engine.kalshiwxfit" in (ROOT / "tools" / "catchup.sh").read_text()


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
