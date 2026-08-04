"""The Lab — every walk-forward harness, run on a cadence and published.

The measured-evidence loop has always existed: half a dozen backtests
replay the PRODUCTION pricer over stored history and report whether the
model actually forecasts better than guessing. All of it printed to a
terminal and vanished. You could not see any of it from a phone, and a
measurement nobody reads is not a measurement.

This module runs what each sport's stored data actually supports,
normalizes every harness into one shape, and writes
``web/data/backtest.json`` for the site's Lab page. It runs weekly from
the maintenance pass — never a command anyone has to remember.

What each sport supports, and why the gaps are gaps:

* **Player props** — MLB replays its own ingested game logs and, where
  a closing price was harvested, prices against *the number a bettor
  could actually have taken*. NFL's harness needs a weekly-stats CSV
  the release feed gates. NBA / WNBA / CFB have no prop harness at all:
  their projections ship, but nothing replays them, and saying so is
  the point of the coverage matrix.
* **Game lines** — spreads and totals replay through the production
  pricer for every sport with harvested closes.

Two honesty rules the page inherits from the harnesses:

* **Basis.** A prop priced against a naive baseline line measures
  predictive skill, NOT an edge over the market. Only the book-priced
  subset speaks to beating a book, so basis travels with every number
  and the page refuses to headline a naive ROI.
* **Skill, not Brier.** "Brier 0.2417" reads like a score out of
  something; it is not. The bar is what you would score predicting the
  base rate every time, and the sharpness figure catches the other
  failure — a model that hedges toward the base rate is perfectly
  calibrated and perfectly useless.

Standard library only; reads the databases the ingests already fill.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

#: Absolute, because the launcher and the maintenance pass do not run from
#: the repo root — a relative default would quietly write the page's data
#: into whatever directory happened to be current.
LAB_PATH = Path(__file__).resolve().parents[1] / "web" / "data" / "backtest.json"

#: Backtests are CPU-heavy and their inputs move slowly — a week's fresh
#: results change a season-long walk-forward by very little. Weekly keeps
#: the page current without spending an evening's compute every launch.
LAB_EVERY_DAYS = 7

#: MLB prop markets worth replaying. Home runs have their own dedicated
#: harness (hr_backtest.py) because a rare event needs different bars.
MLB_MARKETS = ("total_bases", "hits", "strikeouts")

#: Game-line markets, and the sports whose closes can carry them.
GAME_MARKETS = ("total", "spread")
GAME_SPORTS = ("nfl", "mlb", "cfb", "nba", "wnba")

#: A walk-forward needs a real history before its numbers mean anything.
MIN_HISTORY = 8

#: Sports with no player-prop harness, and the honest reason. Absence
#: rendered as an explicit row beats a sport quietly missing from a page.
NO_PROP_HARNESS = {
    "nba": "no walk-forward prop harness yet — projections ship unreplayed",
    "wnba": "no walk-forward prop harness yet — projections ship unreplayed",
    "cfb": "no walk-forward prop harness yet — game lines only",
    "ufc": "fight picks are graded forward in the journal, not backtested",
}


def _round(x, n=4):
    try:
        return round(float(x), n)
    except (TypeError, ValueError):
        return None


def report_to_dict(report, market: str = "", label: str = "") -> dict:
    """One :class:`engine.backtest.BacktestReport` as plain JSON.

    ``basis`` is the headline honesty flag: "book" means every number
    below was priced against a harvested closing line, "naive" means the
    baseline, "mixed" means both and the segments carry the split.
    """
    used, total = report.used_real_lines, report.total_priced
    basis = "naive"
    if used and used >= total:
        basis = "book"
    elif used:
        basis = "mixed"
    out = {
        "market": market,
        "label": label or market,
        "n": report.n,
        "mae": _round(report.mae, 3),
        "rmse": _round(report.rmse, 3),
        "brier": _round(report.brier),
        "ece": _round(report.ece, 3),
        "skill": None,
        "bins": [{"lo": _round(b.lo, 2), "hi": _round(b.hi, 2), "n": b.n,
                  "mean_pred": _round(b.mean_pred, 3),
                  "hit_rate": _round(b.hit_rate, 3)}
                 for b in report.bins if b.n],
        "n_bets": report.n_bets,
        "wins": report.wins,
        "win_rate": _round(report.win_rate, 3),
        "roi": _round(report.roi, 4),
        "net_units": _round(report.net_units, 2),
        "units_staked": _round(report.units_staked, 2),
        "used_real_lines": used,
        "total_priced": total,
        "basis": basis,
        "segments": {},
    }
    sk = report.skill()
    if sk:
        out["skill"] = {"n": sk["n"], "base_rate": _round(sk["base_rate"], 4),
                        "base_brier": _round(sk["base_brier"]),
                        "skill": _round(sk["skill"], 4),
                        "hedged": _round(sk["hedged"], 3)}
    for name, g in (report.segments or {}).items():
        out["segments"][name] = {
            "n_bets": g.get("n_bets", 0), "wins": g.get("wins", 0),
            "win_rate": _round(g.get("win_rate"), 3),
            "roi": _round(g.get("roi"), 4), "net": _round(g.get("net"), 2)}
    return out


# --- player props ------------------------------------------------------------
def mlb_props(conn, markets=MLB_MARKETS, min_history: int = MIN_HISTORY,
              log=print) -> list[dict]:
    """Replay MLB props over ingested logs, priced against harvested closes
    wherever one exists (see engine.mlb.backtest.settled_props_from_logs)."""
    from . import db as _db
    from .mlb.backtest import backtest_from_logs
    from .mlb.models import MARKET_LABELS

    out = []
    for market in markets:
        try:
            entries = _db.entries_for_market(conn, "mlb", market,
                                             min_games=min_history + 1)
            if not entries:
                continue
            real = _db.closing_odds_by_date(conn, "mlb", market)
            rep = backtest_from_logs(entries, market,
                                     min_history=min_history,
                                     real_lines=real or {})
            if rep.n:
                out.append(report_to_dict(
                    rep, market, MARKET_LABELS.get(market, market)))
        except Exception as exc:                   # noqa: BLE001
            log(f"  lab: mlb {market} skipped — {exc}")
    return out


def nfl_props(season: int | None = None, weeks=None, log=print) -> dict:
    """Replay NFL props walk-forward. The weekly-stats feed is release-gated,
    so "no CSV on this machine" is the normal state and reported as such."""
    from .backtest import backtest_from_stats
    from .pipeline import nfl_season_of
    from .sources.fetch import DataUnavailable

    season = season or nfl_season_of(None)
    weeks = list(weeks or range(6, 18))
    try:
        rep = backtest_from_stats(season, weeks)
    except DataUnavailable as exc:
        return {"unavailable": str(exc).split("\n")[0], "season": season}
    except Exception as exc:                       # noqa: BLE001
        log(f"  lab: nfl props skipped — {exc}")
        return {"unavailable": str(exc), "season": season}
    if not rep.n:
        return {"unavailable": f"no settled props in {season} weeks "
                               f"{weeks[0]}–{weeks[-1]}", "season": season}
    d = report_to_dict(rep, "all", "All prop markets")
    d["season"] = season
    d["weeks"] = [weeks[0], weeks[-1]]
    return {"markets": [d], "season": season}


# --- game lines --------------------------------------------------------------
def game_lines(conn, sport: str, log=print) -> dict:
    """Spreads and totals through the production pricer, graded on real
    closing numbers.

    ``engine.gamebets`` refuses to price a sport whose scoring baseline
    and variances were never registered, rather than quietly borrowing
    another league's — so a refusal is reported as the honest gap it is.
    CFB registers its own at import, which is what every real build
    relies on; NBA and WNBA have none, so their game lines genuinely
    cannot be replayed yet.
    """
    from .gamebacktest import backtest_game_lines
    if sport == "cfb":
        from .cfb import ratings as _cfb_ratings      # noqa: F401  (installs)

    out, refusal = [], None
    for market in GAME_MARKETS:
        try:
            r = backtest_game_lines(conn, sport, market=market)
        except ValueError as exc:
            refusal = str(exc).split(" — ")[0]
            continue
        except Exception as exc:                   # noqa: BLE001
            log(f"  lab: {sport} {market} skipped — {exc}")
            continue
        if not getattr(r, "games_priced", 0):
            continue
        out.append({
            "market": market,
            "games_seen": r.games_seen,
            "games_priced": r.games_priced,
            "n_bets": r.n_bets,
            "wins": r.wins,
            "win_rate": _round(r.wins / r.n_bets, 3) if r.n_bets else None,
            "roi": _round(r.roi, 4),
            "net": _round(r.net, 2),
            "mae": _round(getattr(r, "mae", None), 3),
            "refused": getattr(r, "refused", 0),
        })
    if out:
        return {"markets": out}
    if refusal:
        return {"unavailable": refusal}
    return {"unavailable": "no harvested closing lines stored for this sport"}


# --- the whole lab -----------------------------------------------------------
def build(conn=None, hconn=None, log=print, nfl: bool = True) -> dict:
    """Run every harness this machine's data supports and return the page's
    JSON. Each sport reports what it HAS and, where it has nothing, why."""
    from . import db as _db

    close = False
    if hconn is None:
        hconn = _db.connect()
        close = True
    try:
        sports: dict = {}
        props = mlb_props(hconn, log=log)
        sports["mlb"] = {"props": {"markets": props} if props else
                         {"unavailable": "no ingested game logs deep enough "
                                         "to replay yet"},
                         "game_lines": game_lines(hconn, "mlb", log=log)}
        sports["nfl"] = {"props": nfl_props(log=log) if nfl else
                         {"unavailable": "skipped"},
                         "game_lines": game_lines(hconn, "nfl", log=log)}
        for sp in ("cfb", "nba", "wnba"):
            sports[sp] = {"props": {"unavailable": NO_PROP_HARNESS[sp]},
                          "game_lines": game_lines(hconn, sp, log=log)}
        sports["ufc"] = {
            "props": {"unavailable": NO_PROP_HARNESS["ufc"]},
            "game_lines": {"unavailable": "a fight has no spread or total to "
                                          "replay — the moneyline is the market"}}
        return {
            "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
            "sports": sports,
            "min_history": MIN_HISTORY,
            "every_days": LAB_EVERY_DAYS,
            # The caveat that must never be dropped in rendering: a naive
            # basis measures skill against a trailing average, not an edge
            # over a book, and the two get confused constantly.
            "basis_note": ("A prop priced against a NAIVE baseline line "
                           "measures predictive skill, not an edge over the "
                           "market. Only book-priced rows speak to beating "
                           "a sportsbook."),
        }
    finally:
        if close:
            hconn.close()


def _due(path: Path, today: _dt.date) -> bool:
    try:
        prev = json.loads(path.read_text()).get("generated_at") or ""
        last = _dt.date.fromisoformat(prev[:10])
    except (OSError, ValueError, AttributeError):
        return True
    return (today - last).days >= LAB_EVERY_DAYS


def run_if_due(hconn=None, log=print, path: Path | str | None = None,
               force: bool = False, today: _dt.date | None = None,
               nfl: bool = True) -> str:
    """The automatic lane. Returns a status word rather than raising — the
    settle pass must never fail because a backtest did."""
    p = Path(path if path is not None else LAB_PATH)
    today = today or _dt.date.today()
    if not force and not _due(p, today):
        return "already"
    try:
        out = build(hconn=hconn, log=log, nfl=nfl)
    except Exception as exc:                       # noqa: BLE001
        log(f"  lab: skipped — {exc}")
        return "failed"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=1))
    ran = sum(1 for s in out["sports"].values()
              if (s["props"].get("markets")
                  or s["game_lines"].get("markets")))
    log(f"  lab: replayed {ran} sport(s) → {p}")
    return "ok"
