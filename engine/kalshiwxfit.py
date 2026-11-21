"""The weather desk's spread, fitted from its own record (2026-11-07).

The desk prices each daily-high bracket as the chance that Normal(NWS
forecast high, sigma) lands inside it (engine/kalshiweather). The sigmas
there, 2.0 / 3.0 / 3.8 °F by days of lead, were priors from published NWS
verification, with a promise in the module's own docstring: every
(forecast, settle) pair is logged so the sigmas can be fit from our own
history. The settle half was never filled (`kalshi_wx_log.settle_f` is
empty on the box), so the fit never ran, and on 3 November the desk was
paused: its calls claimed far more than they won. Part of that was the
wrong day (WX2: most of the log priced a day late). Part looks like the
spread itself: two-degree brackets at sigma 2 give the bracket holding the
forecast about 38%, and on the record that bracket won about 31%.

THE DATA, all of it on the box already, nothing bought:

  * ``kalshi_wx_log``: every forecast the desk priced with, one row per
    ticker per day priced. Its ``date`` is the day the forecast is FOR
    (pm_build keys the NWS highs by (series, date)), and that holds for
    the day-late rows too: they priced the wrong contract, but with a true
    forecast of their own day. So every row counts, paired by (series,
    date), never by ticker.
  * Kalshi's settled markets for each city's series, from the same free,
    keyless API the desk prices from. Kalshi settles each day's brackets
    on the NWS climate report for the station the desk forecasts, and
    exactly one bracket of a day settles YES: its bounds hold the real
    high (`kalshiweather.parse_bracket`, the desk's own reading of a label).

THE FIT. Interval-censored normal: an event with forecast mu at a lead and
a winning bracket [lo, hi) scores log(Phi((hi - mu - b) / s) - Phi((lo -
mu - b) / s)), an open end counting as infinity. One sigma per lead and
one bias b shared by every lead (the NWS daytime high at a grid point
against one station's midnight-to-midnight maximum), found by a grid,
coarse then fine. Standard library only.

JUDGED HELD OUT, the house rule (engine/boardlearn). Fit on the older two
thirds of the days, scored on the newest third against the priors, event
by event: saved only when the fitted log loss beats the priors' at the
bottom of a 95% interval on the paired difference. The saved numbers are
then the fit on every day. A lead with too few days keeps its prior sigma.
THE LATEST FIT DECIDES: a refit that no longer passes takes the fit away,
and the desk goes back to its priors.

WHERE IT GOES. pm_build refits once a day (`refit_if_due`) and hands the
saved fit to `kalshiweather.weather_board`. The desk stays PAUSED: the fit
changes only the numbers it logs and the shadow picks it grades
(kalshiweather.log_shadow), which is the measure an un-pause needs. The
forecast it logs stays the raw NWS number, so no fit ever learns its own
correction. `python3 -m engine.kalshiwxfit` prints the same fit and saves
nothing. QB_WX_FIT=0 in the service's environment turns the refit off.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
from pathlib import Path

from . import kalshiweather as kw

#: Where the daily refit keeps its verdict and, when one passes, the fit.
FIT_PATH = Path(__file__).resolve().parents[1] / "data" / "models" / "kalshiwx_fit.json"

#: Fewer paired days than this in all and nothing is fitted: not enough.
MIN_EVENTS = 120
#: A lead with fewer training days than this keeps its prior sigma.
MIN_PER_LEAD = 30
#: The held-out third must hold at least this many days to judge anything.
MIN_HELD_OUT = 40
#: The share of days, oldest first, the held-out test fits on.
TRAIN_SHARE = 2 / 3

#: The grids: bias in °F, sigma in °F. Coarse, then fine around the best.
BIAS_COARSE = (-5.0, 5.0, 0.25)
SIGMA_COARSE = (0.75, 8.0, 0.25)
FINE_STEP = 0.05

#: Settled markets come back a page at a time; a city's few months fit in
#: one or two. Cached for most of a day: results do not change.
SETTLED_TTL_S = 20 * 3600
MAX_PAGES = 10


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def event_logp(mu: float, lo, hi, sigma: float, bias: float = 0.0) -> float:
    """log P(the high lands in [lo, hi)) under Normal(mu + bias, sigma)."""
    m = mu + bias
    upper = _phi((hi - m) / sigma) if hi is not None else 1.0
    lower = _phi((lo - m) / sigma) if lo is not None else 0.0
    return math.log(max(upper - lower, 1e-9))


# --- the data ----------------------------------------------------------------
def logged_forecasts(hconn) -> list[tuple]:
    """``[(series, date, lead, forecast_f)]``: one forecast per city, day
    and lead, the median of what the desk logged for it (each ticker of a
    day carries the same forecast, first logged when the ticker appeared).
    """
    import sqlite3
    try:
        rows = hconn.execute(
            "SELECT series, date, lead_days, forecast_f FROM kalshi_wx_log "
            "WHERE forecast_f IS NOT NULL AND lead_days IS NOT NULL").fetchall()
    except sqlite3.Error:
        return []
    by: dict = {}
    for series, date, lead, f in rows:
        if series in kw.CITIES and date:
            by.setdefault((series, str(date)[:10], int(lead)), []).append(float(f))
    out = []
    for (series, date, lead), fs in sorted(by.items()):
        fs.sort()
        n = len(fs)
        med = fs[n // 2] if n % 2 else (fs[n // 2 - 1] + fs[n // 2]) / 2
        out.append((series, date, lead, med))
    return out


def winning_brackets(markets: list[dict]) -> dict:
    """``{date: (lo, hi)}`` from one series' settled markets: the bracket
    that settled YES on each day, read the way the desk reads a label.
    A day with no readable YES, or more than one, is left out."""
    from .ledger import predmarket_event_date
    yes: dict = {}
    for m in markets or []:
        if str(m.get("result") or "").lower() != "yes":
            continue
        day = predmarket_event_date(m.get("ticker"))
        label = m.get("yes_sub_title") or m.get("subtitle") or m.get("title") or ""
        bracket = kw.parse_bracket(label)
        if not day or bracket is None:
            continue
        yes.setdefault(day, []).append(tuple(bracket))
    return {d: bs[0] for d, bs in yes.items() if len(bs) == 1}


def fetch_settled(series: str, since: str, fetch_text=None) -> list[dict]:
    """One city's settled markets that closed on or after ``since``
    (ISO date), every page. ``fetch_text`` is for tests."""
    from .sources.kalshi import KALSHI
    if fetch_text is None:
        from .sources.fetch import fetch_text
    ts = int(_dt.datetime.fromisoformat(f"{since}T00:00:00+00:00").timestamp())
    out: list = []
    cursor = ""
    for page in range(MAX_PAGES):
        url = (f"{KALSHI}/markets?series_ticker={series}&status=settled"
               f"&limit=1000&min_close_ts={ts}" + (f"&cursor={cursor}" if cursor else ""))
        raw = json.loads(fetch_text(url, f"kalshi_settled_{series}_{page}.json",
                                    ttl=SETTLED_TTL_S))
        out.extend(raw.get("markets") or [])
        cursor = raw.get("cursor") or ""
        if not cursor or not raw.get("markets"):
            break
    return out


def pairs(forecasts: list[tuple], brackets: dict) -> list[tuple]:
    """``[(date, lead, mu, lo, hi)]``: each logged forecast beside the
    bracket that won its own day (``brackets`` is {series: {date: (lo, hi)}})."""
    out = []
    for series, date, lead, mu in forecasts:
        b = (brackets.get(series) or {}).get(date)
        if b is not None:
            out.append((date, lead, mu, b[0], b[1]))
    return out


# --- the fit -----------------------------------------------------------------
def _grid(lo: float, hi: float, step: float) -> list[float]:
    n = int(round((hi - lo) / step))
    return [round(lo + i * step, 4) for i in range(n + 1)]


def _best_sigma(rows: list[tuple], bias: float, grid: list[float]) -> tuple:
    best = (-math.inf, None)
    for s in grid:
        ll = sum(event_logp(mu, lo, hi, s, bias) for (_d, _l, mu, lo, hi) in rows)
        if ll > best[0]:
            best = (ll, s)
    return best


def fit(rows: list[tuple]) -> dict:
    """``{"bias_f", "sigma_by_lead", "n_by_lead"}``, by maximum likelihood.
    A lead with under MIN_PER_LEAD days keeps its prior and is fitted out
    of the bias search only through the rows it has."""
    by_lead: dict = {}
    for r in rows:
        by_lead.setdefault(int(r[1]), []).append(r)
    fitted = {l: rs for l, rs in by_lead.items() if len(rs) >= MIN_PER_LEAD}
    prior = {l: kw.SIGMA_BY_LEAD.get(l, kw.SIGMA_BY_LEAD[kw.MAX_LEAD_DAYS])
             for l in by_lead}

    def total(bias: float, sgrid_for) -> tuple:
        ll, sig = 0.0, {}
        for l, rs in by_lead.items():
            if l in fitted:
                one, s = _best_sigma(rs, bias, sgrid_for(l))
            else:
                s = prior[l]
                one = sum(event_logp(mu, lo, hi, s, bias) for (_d, _l, mu, lo, hi) in rs)
            ll += one
            sig[l] = s
        return ll, sig

    coarse = _grid(*SIGMA_COARSE)
    best = (-math.inf, 0.0, {})
    for b in _grid(*BIAS_COARSE):
        ll, sig = total(b, lambda _l: coarse)
        if ll > best[0]:
            best = (ll, b, sig)
    _ll, b0, sig0 = best
    for b in _grid(b0 - BIAS_COARSE[2], b0 + BIAS_COARSE[2], FINE_STEP):
        ll, sig = total(b, lambda l: _grid(max(0.3, sig0.get(l, 2.0) - SIGMA_COARSE[2]),
                                           sig0.get(l, 2.0) + SIGMA_COARSE[2], FINE_STEP))
        if ll > best[0]:
            best = (ll, b, sig)
    _ll, bias, sig = best
    return {"bias_f": round(bias, 2),
            "sigma_by_lead": {str(l): round(s, 2) for l, s in sorted(sig.items())},
            "fitted_leads": sorted(str(l) for l in fitted),
            "n_by_lead": {str(l): len(rs) for l, rs in sorted(by_lead.items())}}


def sigma_for(model: dict | None, lead: int) -> float:
    """The sigma a lead prices with: the fit's when it has the lead, else
    the desk's prior."""
    prior = kw.SIGMA_BY_LEAD.get(lead, kw.SIGMA_BY_LEAD[kw.MAX_LEAD_DAYS])
    if not model:
        return prior
    s = (model.get("sigma_by_lead") or {}).get(str(lead))
    return float(s) if s else prior


def losses(rows: list[tuple], model: dict | None) -> list[float]:
    """Each event's log loss (natural log) under ``model``; None = priors."""
    b = float((model or {}).get("bias_f") or 0.0)
    return [-event_logp(mu, lo, hi, sigma_for(model, int(l)), b)
            for (_d, l, mu, lo, hi) in rows]


def evaluate(rows: list[tuple]) -> dict:
    """The held-out judgement and, when it passes, the fit on every day.

    ``verdict`` is one of: "saved", "not enough days", "no better than the
    priors held out". The numbers behind it ride along either way."""
    days = sorted({r[0] for r in rows})
    out: dict = {"events": len(rows), "days": len(days),
                 "first_day": days[0] if days else None,
                 "last_day": days[-1] if days else None}
    if len(rows) < MIN_EVENTS or len(days) < 3:
        out["verdict"] = "not enough days"
        return out
    cut = days[min(len(days) - 1, max(1, int(len(days) * TRAIN_SHARE)))]
    train = [r for r in rows if r[0] < cut]
    test = [r for r in rows if r[0] >= cut]
    if len(test) < MIN_HELD_OUT:
        out["verdict"] = "not enough days"
        return out
    trial = fit(train)
    lf, lp = losses(test, trial), losses(test, None)
    diffs = [p - f for p, f in zip(lp, lf)]
    n = len(diffs)
    mean = sum(diffs) / n
    sd = math.sqrt(sum((d - mean) ** 2 for d in diffs) / max(1, n - 1))
    low = mean - 1.96 * sd / math.sqrt(n)
    out["held_out"] = {"from": cut, "events": n,
                       "logloss_fit": round(sum(lf) / n, 4),
                       "logloss_prior": round(sum(lp) / n, 4),
                       "gain_low95": round(low, 4), "trial": trial}
    out["calibration"] = calibration(test, trial)
    if low <= 0:
        out["verdict"] = "no better than the priors held out"
        return out
    out["verdict"] = "saved"
    out["fit"] = fit(rows)
    return out


def _own_bracket(mu: float, lo, hi) -> tuple | None:
    """The bracket of that day's ladder that holds the forecast. A day's
    brackets sit edge to edge at the winner's width (two degrees on these
    series), so the winner's edges place every other bracket of the day."""
    edge = lo if lo is not None else hi
    if edge is None:
        return None
    width = (hi - lo) if (lo is not None and hi is not None) else 2.0
    a = edge + width * math.floor((mu - edge) / width)
    return a, a + width


def calibration(rows: list[tuple], model: dict | None) -> dict:
    """The desk's central bracket: on how many days the bracket holding the
    forecast won, against the chance the priors and ``model`` gave it."""
    n = won = 0
    said_prior = said_fit = 0.0
    b = float((model or {}).get("bias_f") or 0.0)
    for (_d, l, mu, lo, hi) in rows:
        own = _own_bracket(mu, lo, hi)
        if own is None:
            continue
        n += 1
        if (lo is None or mu >= lo) and (hi is None or mu < hi):
            won += 1
        said_prior += math.exp(event_logp(mu, own[0], own[1], sigma_for(None, int(l)), 0.0))
        said_fit += math.exp(event_logp(mu, own[0], own[1], sigma_for(model, int(l)), b))
    if not n:
        return {"days": 0}
    return {"days": n, "won_pct": round(won / n, 4),
            "prior_said": round(said_prior / n, 4),
            "fit_said": round(said_fit / n, 4)}


# --- the daily refit ---------------------------------------------------------
def collect(hconn, fetch_text=None, log=print) -> list[tuple]:
    """Every pairable (date, lead, mu, lo, hi) on this box."""
    forecasts = logged_forecasts(hconn)
    if not forecasts:
        return []
    since = min(d for (_s, d, _l, _m) in forecasts)
    since = (_dt.date.fromisoformat(since) - _dt.timedelta(days=1)).isoformat()
    brackets = {}
    for series in sorted({s for (s, _d, _l, _m) in forecasts}):
        try:
            brackets[series] = winning_brackets(fetch_settled(series, since, fetch_text))
        except Exception as exc:                          # noqa: BLE001
            log(f"  weather fit: {series} settled markets unreadable — {exc}")
    return pairs(forecasts, brackets)


def load(path=None) -> dict | None:
    """The saved fit, or None (no file, or the last refit took it away)."""
    try:
        doc = json.loads(Path(path or FIT_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict) or doc.get("verdict") != "saved":
        return None
    f = doc.get("fit")
    return f if isinstance(f, dict) and f.get("sigma_by_lead") else None


def _read(path) -> dict:
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def switched_on() -> bool:
    """QB_WX_FIT=0 in the service's environment turns the daily refit off
    and the desk back to its priors, without a deploy."""
    import os
    return os.environ.get("QB_WX_FIT", "1").strip() != "0"


def refit_if_due(hconn, path=None, today: str | None = None,
                 fetch_text=None, log=print) -> dict | None:
    """Once a day: refit from the log and the settled brackets, keep the
    verdict, and return the fit the desk should price with (None: the
    priors). Never raises; a refit that fails keeps yesterday's verdict."""
    if not switched_on():
        return None
    p = Path(path or FIT_PATH)
    today = today or _dt.date.today().isoformat()
    doc = _read(p)
    if doc.get("checked") == today:
        return load(p)
    try:
        rep = evaluate(collect(hconn, fetch_text=fetch_text, log=log))
    except Exception as exc:                              # noqa: BLE001
        log(f"  weather fit skipped — {type(exc).__name__}: {exc}")
        return load(p)
    rep["checked"] = today
    if rep.get("verdict") == "saved":
        rep["first_saved"] = (doc.get("first_saved") if doc.get("verdict") == "saved"
                              else None) or today
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(rep, indent=1, sort_keys=True), encoding="utf-8")
        tmp.replace(p)
    except OSError as exc:
        log(f"  weather fit not saved — {exc}")
    log("  weather fit: " + summary(rep))
    return rep.get("fit") if rep.get("verdict") == "saved" else None


def summary(rep: dict) -> str:
    """One line for the build log and the audit."""
    v = rep.get("verdict") or "not run"
    head = f"{v} ({rep.get('events', 0):,} days paired"
    ho = rep.get("held_out") or {}
    if ho:
        head += (f"; held out from {ho['from']}: log loss {ho['logloss_fit']:.3f}"
                 f" fitted vs {ho['logloss_prior']:.3f} the priors")
    head += ")"
    f = rep.get("fit") or ho.get("trial")
    if f:
        sig = ", ".join(f"{l}d {s}°F" for l, s in sorted(f["sigma_by_lead"].items()))
        head += f" — bias {f['bias_f']:+.1f}°F, sigma {sig}"
    return head


def report_lines(rep: dict) -> list[str]:
    out = [f"weather desk spread fit — {summary(rep)}",
           f"  the priors: sigma " + ", ".join(
               f"{l}d {s}°F" for l, s in sorted(kw.SIGMA_BY_LEAD.items())) + ", no bias"]
    if rep.get("first_day"):
        out.append(f"  days paired: {rep['days']:,} from {rep['first_day']} to {rep['last_day']}")
    f = rep.get("fit") or (rep.get("held_out") or {}).get("trial")
    if f:
        out.append("  days by lead: " + ", ".join(
            f"{l}d {n}" for l, n in sorted(f["n_by_lead"].items()))
            + "; fitted: " + (", ".join(f"{l}d" for l in f["fitted_leads"]) or "none"))
    c = rep.get("calibration") or {}
    if c.get("days"):
        out.append(f"  held out, the bracket holding the forecast won {c['won_pct']:.0%}"
                   f" of {c['days']} days; the priors gave it {c['prior_said']:.0%},"
                   f" the fit {c['fit_said']:.0%}")
    return out


def main(argv=None) -> int:
    """Read-only: the fit the daily refit would make today. Saves nothing."""
    import sqlite3
    from . import db as _db
    h = sqlite3.connect(f"file:{_db.DEFAULT_DB}?mode=ro", uri=True)
    try:
        rep = evaluate(collect(h))
    finally:
        h.close()
    for line in report_lines(rep):
        print(line)
    saved = _read(FIT_PATH)
    print(f"  the box's saved verdict: {saved.get('verdict', 'none yet')}"
          + (f", checked {saved['checked']}" if saved.get("checked") else "")
          + (f", saved since {saved['first_saved']}" if saved.get("first_saved") else ""))
    return 0


if __name__ == "__main__":                       # pragma: no cover
    raise SystemExit(main())
